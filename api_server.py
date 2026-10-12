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
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import date, datetime, timedelta
from urllib.parse import urlparse, parse_qs, unquote

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

logger = logging.getLogger(__name__)

PLACEHOLDER_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80" viewBox="0 0 80 80">
  <rect width="80" height="80" rx="8" fill="#161b22"/>
  <path d="M40 22c6 0 11 5 11 11 0 4-2 7-5 9 3 3 4 6 4 9v7H30v-7c0-3 1-6 4-9-3-2-5-5-5-9 0-6 5-11 11-11z" fill="#3fb950"/>
</svg>"""


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.storage = SQLiteStorage()
        self.project_root = Path(__file__).parent
        # url_hash -> remote url, built once from the current deal set. Without
        # this every image cache miss scanned the whole deals table.
        self._image_url_index = None
        self._image_url_index_lock = threading.Lock()
        super().__init__(*args, directory=str(self.project_root), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/api/data':
            self.send_api_data()
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
                self.end_headers()
                self.wfile.write(logo_data)
            else:
                self.send_response(200)
                self.send_header('Content-Type', 'image/svg+xml')
                self.send_header('Cache-Control', 'public, max-age=3600')
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
                self.end_headers()
                self.wfile.write(image_data)
            else:
                self.send_response(200)
                self.send_header('Content-Type', 'image/svg+xml')
                self.send_header('Cache-Control', 'public, max-age=3600')
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

        cached = load_image_cache(cache_dir, key)
        if cached:
            # Backfill the DB copy so it is available if the file cache is lost.
            self.storage.save_product_image(key, cached, get_mime_type(cached))
            return cached

        cached = self.storage.get_product_image(key)
        if cached:
            save_image_cache(cached, cache_dir, key)
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
            self.end_headers()
            self.wfile.write(json.dumps(data, default=str, ensure_ascii=False).encode('utf-8'))
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
            deals.append(deal)
        return deals

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