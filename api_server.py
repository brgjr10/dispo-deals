#!/usr/bin/env python3
"""
Simple API server for the Dispo Deals dashboard.
Serves data from SQLite and the dashboard HTML.
"""
import json
import sqlite3
import os
import sys
import logging
import signal
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import date, datetime, timedelta
from urllib.parse import urlparse, parse_qs, unquote
from functools import lru_cache
from collections import OrderedDict

sys.path.insert(0, str(Path(__file__).parent))

from storage.sqlite import SQLiteStorage
from utils.diff import compute_weekly_diff
from utils.images import (
    download_image,
    hash_url,
    load_image_cache,
    save_image_cache,
    get_mime_type,
    resize_image,
)
from utils.strain_match import normalize_name
from utils.categories import canonical_category

logger = logging.getLogger(__name__)

PLACEHOLDER_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80" viewBox="0 0 80 80">
  <rect width="80" height="80" rx="8" fill="#161b22"/>
  <path d="M40 22c6 0 11 5 11 11 0 4-2 7-5 9 3 3 4 6 4 9v7H30v-7c0-3 1-6 4-9-3-2-5-5-5-9 0-6 5-11 11-11z" fill="#3fb950"/>
</svg>"""

# Security headers to add to all responses
SECURITY_HEADERS = {
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self'; connect-src 'self'",
    'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
    'Permissions-Policy': 'accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()',
}

class LRUCache:
    """Simple LRU cache with max size."""
    def __init__(self, maxsize=1000):
        self.maxsize = maxsize
        self.cache = OrderedDict()
        self.lock = threading.Lock()

    def get(self, key):
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
            return None

    def set(self, key, value):
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
            self.cache[key] = value
            if len(self.cache) > self.maxsize:
                self.cache.popitem(last=False)

    def clear(self):
        with self.lock:
            self.cache.clear()

    def __len__(self):
        with self.lock:
            return len(self.cache)


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.storage = SQLiteStorage()
        self.project_root = Path(__file__).parent
        # url_hash -> remote url, built once from the current deal set. Without
        # this every image cache miss scanned the whole deals table.
        self._image_url_index = None
        self._image_url_index_lock = threading.Lock()
        # normalised strain name -> profile, loaded once per process. Strain
        # profiles are shared across every product carrying that strain.
        self._strain_index = None
        self._strain_index_lock = threading.Lock()
        # LRU caches with size limits to prevent unbounded memory growth
        self._image_cache = LRUCache(maxsize=500)
        self._strain_cache = LRUCache(maxsize=1000)
        super().__init__(*args, directory=str(self.project_root), **kwargs)

    def _send_security_headers(self):
        """Add security headers to the response."""
        for header, value in SECURITY_HEADERS.items():
            self.send_header(header, value)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/api/data':
            self.send_api_data()
        elif path == '/api/menu':
            self.send_full_menu()
        elif path.startswith('/api/image/'):
            self.send_image(path[len('/api/image/'):])
        elif path.startswith('/api/logo/'):
            self.send_logo(path[len('/api/logo/'):])
        elif path == '/' or path == '/dashboard.html':
            self.path = '/dashboard.html'
            # Serve HTML with explicit UTF-8 charset
            try:
                with open(self.project_root / 'dashboard.html', 'r', encoding='utf-8') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self._send_security_headers()
                self.end_headers()
                self.wfile.write(content.encode('utf-8'))
            except Exception as e:
                self.send_error(500, str(e))
        else:
            super().do_GET()

    def send_logo(self, store_id):
        """Serve a store logo by id, downloading it once and caching it.

        Falls back to the shared SVG placeholder so a broken logo never leaves
        a gap in the store header.
        """
        try:
            store_id = unquote(store_id).split('?')[0]
            logo_data = self._resolve_logo(store_id)
            if logo_data:
                self.send_response(200)
                self.send_header('Content-Type', get_mime_type(logo_data))
                self.send_header('Cache-Control', 'public, max-age=604800')
                self._send_security_headers()
                self.end_headers()
                self.wfile.write(logo_data)
            else:
                self.send_response(200)
                self.send_header('Content-Type', 'image/svg+xml')
                self.send_header('Cache-Control', 'public, max-age=3600')
                self._send_security_headers()
                self.end_headers()
                self.wfile.write(PLACEHOLDER_SVG.encode('utf-8'))
        except Exception as e:
            self.send_error(500, str(e))

    def _resolve_logo(self, store_id):
        """Look up a store logo in SQLite, then download it from configured URL."""
        cached = self.storage.get_store_logo(store_id)
        if cached:
            return cached

        logo_url = self._find_store_logo_url(store_id)
        if not logo_url:
            return None

        downloaded = download_image(logo_url)
        if downloaded:
            mime = get_mime_type(downloaded)
            self.storage.save_store_logo(store_id, downloaded, mime)
        return downloaded

    def _find_store_logo_url(self, store_id):
        """Read the configured logo URL for a store from config.yaml."""
        try:
            import yaml
            config_path = self.project_root / "config.yaml"
            config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except Exception:
            return None

        for store in config.get("stores", []):
            if store.get("id") == store_id:
                return store.get("logo_url")
        return None

    def send_image(self, key):
        """Serve a product image by URL hash, downloading it if needed.

        Images are cached in SQLite (survives container restarts) and on disk,
        so the dashboard only ever fetches from the local server. If the
        remote image is unavailable a local placeholder is returned instead,
        so the dashboard never shows a broken image box.
        """
        try:
            key = unquote(key).split('?')[0]
            image_data = self._resolve_image(key)
            if image_data:
                self.send_response(200)
                self.send_header('Content-Type', get_mime_type(image_data))
                self.send_header('Cache-Control', 'public, max-age=604800')
                self._send_security_headers()
                self.end_headers()
                self.wfile.write(image_data)
            else:
                self.send_response(404)
                self.send_header('Content-Type', 'image/svg+xml')
                self.send_header('Cache-Control', 'public, max-age=3600')
                self._send_security_headers()
                self.end_headers()
                self.wfile.write(PLACEHOLDER_SVG.encode('utf-8'))
        except Exception as e:
            self.send_error(500, str(e))

    def _resolve_image(self, key):
        """Look up an image on disk, then in SQLite, then download it.

        The file cache is checked first: it lives in the mounted cache volume,
        so it survives restarts and needs no database locks. SQLite is only
        consulted when the file cache was cleared but the DB was not.

        Downloaded images are resized to the configured dashboard budget so a
        single oversized PNG cannot dominate the payload.
        """
        cache_dir = str(self.project_root / 'cache' / 'images')

        # Check LRU cache first
        cached = self._image_cache.get(key)
        if cached:
            return cached

        cached = load_image_cache(cache_dir, key)
        if cached:
            # Backfill the DB copy so it is available if the file cache is lost.
            self.storage.save_product_image(key, cached, get_mime_type(cached))
            self._image_cache.set(key, cached)
            return cached

        cached = self.storage.get_product_image(key)
        if cached:
            save_image_cache(cached, cache_dir, key)
            self._image_cache.set(key, cached)
            return cached

        remote_url = self._get_image_url_for_hash(key)
        if not remote_url:
            return None

        downloaded = download_image(remote_url)
        if downloaded:
            downloaded = self._resize_for_cache(downloaded)
            mime = get_mime_type(downloaded)
            save_image_cache(downloaded, cache_dir, key)
            self.storage.save_product_image(key, downloaded, mime)
            self._image_cache.set(key, downloaded)
        return downloaded

    def _resize_for_cache(self, image_data):
        """Resize to the configured budget, falling back to the original."""
        try:
            max_width = self._image_config("max_width", 400)
            max_size_kb = self._image_config("max_size_kb", 500)
            return resize_image(
                image_data, max_width=max_width, max_size_kb=max_size_kb
            )
        except Exception:
            return image_data

    def _image_config(self, key, default):
        try:
            import yaml
            if not hasattr(self, "_images_config"):
                config = yaml.safe_load(
                    (self.project_root / "config.yaml").read_text(encoding="utf-8")
                )
                self._images_config = config.get("images", {}) or {}
            value = self._images_config.get(key)
            return value if value is not None else default
        except Exception:
            return default

    def _get_image_url_for_hash(self, key):
        """Recover the remote URL for a hash from the current deal set."""
        if self._image_url_index is None:
            with self._image_url_index_lock:
                if self._image_url_index is None:
                    self._image_url_index = self._build_image_url_index()
        return self._image_url_index.get(key)

    def _build_image_url_index(self):
        """Build the url_hash -> remote url map in a single pass."""
        index = {}
        conn = self.storage._get_connection()
        try:
            rows = conn.execute(
                "SELECT image_url FROM seen_deals WHERE image_url IS NOT NULL AND image_url != ''"
            ).fetchall()
            for (url,) in rows:
                h = hash_url(url)
                if h not in index:
                    index[h] = url
        except Exception as e:
            logger.warning(f"Failed to build image url index: {e}")
        finally:
            conn.close()
        return index

    def send_api_data(self):
        try:
            data = self.get_dashboard_data()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(json.dumps(data, default=str, ensure_ascii=False).encode('utf-8'))
        except Exception as e:
            self.send_error(500, str(e))

    def send_full_menu(self):
        try:
            products = self.get_full_menu()
            stores = self.get_stores()
            # Get unique categories
            categories = sorted(set(p.get("category", "") for p in products if p.get("category")))
            # Get unique brands
            brands = sorted(set(p.get("brand", "") for p in products if p.get("brand")))

            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(json.dumps({
                "products": products,
                "stores": stores,
                "categories": categories,
                "brands": brands
            }, default=str, ensure_ascii=False).encode('utf-8'))
        except Exception as e:
            self.send_error(500, str(e))

    def get_dashboard_data(self):
        stores = self.get_stores()
        deals = self.get_all_deals()
        weekly_diff = self.get_weekly_diff()

        return {
            "stores": stores,
            "deals": deals,
            "snapshots": [],
            "weeklyDiff": weekly_diff.to_dict() if weekly_diff else None
        }

    def _strain_index_map(self):
        """Load every cached strain once, keyed by normalised name.

        Strain profiles are small and there are only a few thousand, so one
        lookup serves the whole menu instead of a query per product.
        """
        if self._strain_index is None:
            with self._strain_index_lock:
                if self._strain_index is None:
                    self._strain_index = self.storage.get_strain_index()
        return self._strain_index

    def _attach_strains(self, products):
        """Attach a `strain` profile to each product, in place.

        The strain name is read from the product when it carries one, otherwise
        through the deal hash, because weekly snapshots written before the
        strain importer existed have no strain field of their own.
        """
        if not products:
            return products
        index = self._strain_index_map()
        by_hash = self.storage.get_strain_names_by_hash()

        for product in products:
            name = product.get("strain_name") or by_hash.get(product.get("hash"))
            strain = index.get(normalize_name(name)) if name else None
            product["strain"] = strain.to_dict() if strain else None
        return products

    def get_stores(self):
        # Return store configs from the database or config
        conn = self.storage._get_connection()
        try:
            rows = conn.execute("""
                SELECT DISTINCT store_id FROM seen_deals
            """).fetchall()
        finally:
            conn.close()
        store_ids = [r[0] for r in rows]

        # Also include configured stores
        import yaml
        with open(self.project_root / "config.yaml", encoding='utf-8') as f:
            config = yaml.safe_load(f)
        for s in config.get("stores", []):
            if s.get("enabled") and s["id"] not in store_ids:
                store_ids.append(s["id"])

        stores = []
        for sid in store_ids:
            cfg = next((s for s in config.get("stores", []) if s["id"] == sid), {})
            stores.append({
                "id": sid,
                "name": cfg.get("name", sid),
                "logo_url": cfg.get("logo_url", ""),
                "enabled": cfg.get("enabled", True)
            })
        return stores

    def get_all_deals(self):
        conn = self.storage._get_connection()
        try:
            rows = conn.execute("""
                SELECT * FROM seen_deals ORDER BY last_notified DESC
            """).fetchall()
        finally:
            conn.close()

        deals = []
        for row in rows:
            deal = dict(row)
            # Expose the cache key so the dashboard can route images through
            # the local /api/image proxy instead of hotlinking the CDN.
            deal["image_key"] = hash_url(deal["image_url"]) if deal.get("image_url") else ""
            # Add weekly status if we can compute it
            deal["weekly_status"] = "NEW"  # Default
            # Rows written before the canonical names existed keep the raw one,
            # so normalise here too or the sidebar still splits the shelf.
            deal["category"] = canonical_category(deal.get("category"))
            deals.append(deal)
        return self._attach_strains(deals)

    def get_full_menu(self):
        """Get the complete menu from latest weekly snapshots across all stores."""
        conn = self.storage._get_connection()
        try:
            # Get latest snapshot for each store
            rows = conn.execute("""
                SELECT ws.* FROM weekly_snapshots ws
                INNER JOIN (
                    SELECT store_id, MAX(week_start) as max_week
                    FROM weekly_snapshots
                    GROUP BY store_id
                ) latest ON ws.store_id = latest.store_id AND ws.week_start = latest.max_week
            """).fetchall()
        finally:
            conn.close()

        all_products = []
        for row in rows:
            data = dict(row)
            try:
                items = json.loads(data["items"])
                for item in items:
                    # Ensure each item has the store_id and image_key
                    item["store_id"] = data["store_id"]
                    item["image_key"] = hash_url(item["image_url"]) if item.get("image_url") else ""
                    # Mark whether it is actually on sale. Snapshots written
                    # before this field existed only hold deals, so anything
                    # without a discount percentage is a full-priced product.
                    item["is_deal"] = (item.get("discount_pct") or 0) > 0
                    # Weekly status from diff
                    item["weekly_status"] = item.get("weekly_status", "NEW")
                    # Stores disagree on shelf names, and a snapshot written by
                    # an older scraper can still carry a stale one, so the
                    # category is canonicalised on the way out.
                    item["category"] = canonical_category(item.get("category"))
                    all_products.append(item)
            except Exception as e:
                logger.warning(f"Failed to parse snapshot for {data['store_id']}: {e}")

        # Snapshots are written before the strain import ran, so a stored item
        # may not carry its strain yet; the live deals table has the newer data.
        self._attach_strains(all_products)
        return all_products

    def get_weekly_diff(self):
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        prev_week_start = week_start - timedelta(weeks=1)

        # Get all stores that have data
        conn = self.storage._get_connection()
        try:
            store_rows = conn.execute("SELECT DISTINCT store_id FROM weekly_snapshots").fetchall()
        finally:
            conn.close()

        all_new = []
        all_carryover = []
        all_removed = []

        for (store_id,) in store_rows:
            current = self.storage.get_weekly_snapshot(store_id, week_start)
            previous = self.storage.get_weekly_snapshot(store_id, prev_week_start)

            if not current:
                continue

            if not previous:
                # First week - everything is new
                for deal in current.items:
                    deal.weekly_status = "NEW"
                    all_new.append(deal)
            else:
                diff = compute_weekly_diff(current.items, previous.items)
                for item in diff.new_items:
                    item.deal.weekly_status = "NEW"
                    all_new.append(item.deal)
                for item in diff.carryover_items:
                    item.deal.weekly_status = "CARRYOVER"
                    all_carryover.append(item.deal)
                for deal in diff.removed_items:
                    deal.weekly_status = "REMOVED"
                    all_removed.append(deal)

        # Create a combined diff object
        class CombinedDiff:
            def __init__(self, new, carryover, removed):
                self.new_items = [type('obj', (object,), {'deal': d}) for d in new]
                self.carryover_items = [type('obj', (object,), {'deal': d}) for d in carryover]
                self.removed_items = removed
                self.new_count = len(new)
                self.carryover_count = len(carryover)
                self.removed_count = len(removed)

            def to_dict(self):
                return {
                    "new_count": self.new_count,
                    "carryover_count": self.carryover_count,
                    "removed_count": self.removed_count,
                    "new_items": [{"deal": d.deal.to_dict()} for d in self.new_items],
                    "carryover_items": [{"deal": d.deal.to_dict()} for d in self.carryover_items],
                    "removed_items": [d.to_dict() for d in self.removed_items],
                }

        return CombinedDiff(all_new, all_carryover, all_removed)

    def log_message(self, format, *args):
        # Suppress default log messages
        pass


def run_server(port=4040):
    # Images are served per-deal, so the dashboard issues many concurrent
    # requests; a single-threaded server serialises them into visible stalls.
    server = ThreadingHTTPServer(('', port), DashboardHandler)
    print(f"Dashboard server running at http://localhost:{port}")
    print(f"Open http://localhost:{port}/dashboard.html in your browser")

    def shutdown_handler(signum, frame):
        print(f"\nReceived signal {signum}, shutting down gracefully...")
        server.shutdown()

    # Handle both SIGTERM (Docker) and SIGINT (Ctrl+C)
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=4040)
    args = parser.parse_args()
    run_server(args.port)