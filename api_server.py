#!/usr/bin/env python3
"""
Simple API server for the Dispo Deals dashboard.
Serves data from SQLite and the dashboard HTML.
"""
import json
import sqlite3
import os
import re
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
from typing import Any, Dict, List, Optional

import requests
import yaml

sys.path.insert(0, str(Path(__file__).parent))

from storage.sqlite import SQLiteStorage
from models import WeeklySnapshot
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

# A Dutchie cName slug: lowercase words joined by hyphens. Used to reject a
# stray path segment or an unrelated URL before it is treated as a store.
CN_NAME_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')

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

    def _send_json_error(self, status: int, message: str):
        """Return an API error as JSON rather than an HTML error page.

        The dashboard reads `error` from the body to tell the user what went
        wrong, and `send_error`'s HTML page cannot be parsed as JSON, so the
        real reason would be lost behind a generic status message.
        """
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self._send_security_headers()
        self.end_headers()
        self.wfile.write(
            json.dumps({"error": message}, ensure_ascii=False).encode('utf-8')
        )

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

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
            logger.error(f"send_full_menu failed: {e}")
            self._send_json_error(500, str(e))

    def resolve_dutchie_store(self, url: str) -> Optional[Dict[str, Any]]:
        """Resolve a Dutchie store URL to its real name, id and address.

        The cName slug is taken from the URL and looked up through the same
        `filteredDispensaries` query the scraper uses, so a store only needs to
        publish a link for it to be addable. Returns None when the store does
        not exist or Dutchie cannot be reached.
        """
        slug = self._extract_dutchie_slug(url)
        if not slug:
            return None

        query = """
        query Dispensary($cNameOrID: String) {
            filteredDispensaries(filter: {cNameOrID: $cNameOrID}) {
                id
                name
                cName
                address
                phone
                status
                location { city state country }
            }
        }
        """
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Origin': 'https://dutchie.com',
            'Referer': 'https://dutchie.com/',
        }
        for endpoint in ('https://api.dutchie.com/graphql', 'https://dutchie.com/graphql'):
            try:
                response = requests.post(
                    endpoint,
                    json={'query': query, 'variables': {'cNameOrID': slug}},
                    headers=headers,
                    timeout=30,
                )
                if response.status_code != 200:
                    continue
                body = response.json()
                matches = (body.get('data') or {}).get('filteredDispensaries') or []
                # Prefer the exact slug so a partial match cannot add the
                # wrong dispensary under the name the user pasted.
                match = next(
                    (m for m in matches if str(m.get('cName', '')).lower() == slug.lower()),
                    matches[0] if matches else None,
                )
                if match and match.get('id'):
                    location = match.get('location') or {}
                    return {
                        'id': str(match.get('id')),
                        'name': match.get('name') or slug,
                        'cname': match.get('cName') or slug,
                        'url': f'https://dutchie.com/stores/{slug}',
                        'address': match.get('address') or '',
                        'phone': match.get('phone') or '',
                        'city': location.get('city') or '',
                        'state': location.get('state') or '',
                        'source': 'dutchie',
                    }
            except Exception as e:
                logger.warning(f"Dutchie store resolve failed on {endpoint}: {e}")
                continue
        return None

    @staticmethod
    def _extract_dutchie_slug(url: str) -> str:
        """Pull the cName slug out of any Dutchie store link form.

        Accepts a full URL, a bare host/path, or a bare slug. A candidate is
        only returned when it looks like a cName (lowercase words joined by
        hyphens), so a browse path such as ".../stores/" or an unrelated URL
        yields nothing rather than a nonsense store.
        """
        cleaned = (url or '').strip().split('?')[0].split('#')[0].rstrip('/').strip()
        if not cleaned:
            return ''

        # Normalise to something urlparse can read, then look for the
        # "/stores/<slug>" segment Dutchie's links use.
        for candidate in (cleaned, f'https://{cleaned}'):
            parsed = urlparse(candidate)
            parts = [p for p in parsed.path.split('/') if p]
            if 'stores' in parts:
                idx = parts.index('stores')
                if idx + 1 < len(parts):
                    slug = parts[idx + 1].lower()
                    if CN_NAME_RE.match(slug):
                        return slug
                continue

            # No "/stores/" segment: accept a bare slug only when the whole
            # input is the slug itself and nothing else.
            if not parsed.scheme and not parsed.netloc and len(parts) == 1:
                slug = parts[0].lower()
                if CN_NAME_RE.match(slug):
                    return slug
        return ''

    def _canonical_store_id(self, cname: str) -> str:
        """The id the dashboard should use for a dispensary.

        A store is identified by its cName, not by Dutchie's internal id: a
        hand-written config entry (`bliss-kent`) has no internal id, so keying
        on that would give the same dispensary two entries. This walks the
        existing entries and reuses the id of whichever one already points at
        this cName, falling back to the slug itself for a genuinely new store.
        """
        slug = re.sub(r'[^a-z0-9]+', '-', (cname or '').strip().lower()).strip('-')

        # An already-added store wins: its id is what its products are keyed on.
        for known in self.storage.list_known_stores():
            if known.get('cname') == cname or known.get('id') == slug:
                return known['id']

        try:
            with open(self.project_root / 'config.yaml', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
        except OSError:
            config = {}

        for entry in config.get('stores', []):
            entry_slug = self._extract_dutchie_slug(entry.get('url', ''))
            if entry_slug and entry_slug == cname:
                return entry['id']

        # Fall back to the slug, which is both readable and stable.
        return slug or 'unknown-store'

    def _refresh_store(self, store_id: str, store_info: Dict[str, Any]) -> Dict[str, Any]:
        """Re-scrape a store that is already on the dashboard.

        Re-adding a store should refresh its menu rather than silently do
        nothing, otherwise a stale menu can never be corrected from the UI.
        """
        from models import StoreConfig, NotificationMode
        from config import Config
        from scrapers import create_scraper

        store_config = StoreConfig(
            id=store_id,
            name=store_info['name'],
            url=store_info['url'],
            scraper='dutchie',
            logo_url=store_info.get('logo_url', ''),
            notification_mode=NotificationMode.PER_STORE,
            enabled=True,
            webhook_enabled=False,
        )
        try:
            config = Config.load(str(self.project_root / 'config.yaml'))
        except Exception as e:
            logger.warning(f"Could not load config.yaml while refreshing: {e}")
            config = Config()

        scraper = create_scraper(store_config, config)
        deals = scraper.fetch_menu() or []

        for deal in deals:
            if self.storage.is_new_deal(deal, False):
                self.storage.save_seen_deal(deal)
            else:
                self.storage.update_seen_deal(deal, notify=False)

        try:
            today = date.today()
            week_start = today - timedelta(days=today.weekday())
            self.storage.save_weekly_snapshot(
                WeeklySnapshot(store_id=store_id, week_start=week_start, items=deals)
            )
        except Exception as e:
            logger.warning(f"Failed to snapshot {store_id}: {e}")

        return {
            'store': store_info,
            'product_count': len(deals),
            'new_products': 0,
        }

    def add_store(self, url: str) -> Dict[str, Any]:
        """Resolve, scrape and persist a store added at runtime.

        The store is recorded before its menu is fetched, so a refresh while a
        long scrape is still running does not lose it.
        """
        store_info = self.resolve_dutchie_store(url)
        if not store_info:
            raise ValueError('No Dutchie dispensary found at that link')

        # The store id has to be the *same* one an existing entry uses, or the
        # same dispensary appears twice under two ids. Dutchie's internal id is
        # not usable for that because a hand-written config entry never has it,
        # so the cName slug is what identities a store.
        store_id = self._canonical_store_id(store_info['cname'] or store_info['name'])
        store_info['id'] = store_id

        if any(s['id'] == store_id for s in self.get_stores()):
            # Already on the dashboard: refresh its metadata and menu rather
            # than adding a second copy of the same dispensary.
            self.storage.save_known_store(store_info)
            result = self._refresh_store(store_id, store_info)
            result['already_added'] = True
            return result

        self.storage.save_known_store(store_info)

        from models import StoreConfig, NotificationMode
        from config import Config
        from scrapers import create_scraper

        store_config = StoreConfig(
            id=store_id,
            name=store_info['name'],
            url=store_info['url'],
            scraper='dutchie',
            logo_url=store_info.get('logo_url', ''),
            notification_mode=NotificationMode.PER_STORE,
            enabled=True,
            webhook_enabled=False,
        )

        # A missing or unreadable config must not stop a store being added, so
        # the defaults are used instead of aborting the request.
        try:
            config = Config.load(str(self.project_root / 'config.yaml'))
        except Exception as e:
            logger.warning(f"Could not load config.yaml for the new store: {e}")
            config = Config()

        scraper = create_scraper(store_config, config)
        deals = scraper.fetch_menu() or []

        saved = 0
        for deal in deals:
            if self.storage.is_new_deal(deal, False):
                self.storage.save_seen_deal(deal)
                saved += 1
            else:
                self.storage.update_seen_deal(deal, notify=False)

        # Store the logo so the dashboard can show it next to the new store.
        try:
            logo = scraper.fetch_logo()
            if logo:
                self.storage.save_store_logo(store_id, logo, get_mime_type(logo))
        except Exception as e:
            logger.warning(f"Failed to fetch logo for {store_id}: {e}")

        # The logo is served through the local proxy whether or not the source
        # had one, so record that path rather than the empty value resolved
        # earlier. Re-saving keeps the stored row in step with what the
        # dashboard will actually request.
        store_info['logo_url'] = f'/api/logo/{store_id}'
        self.storage.save_known_store(store_info)

        # A weekly snapshot keyed on today's week means the new store shows up
        # in the menu view straight away.
        try:
            today = date.today()
            week_start = today - timedelta(days=today.weekday())
            self.storage.save_weekly_snapshot(
                WeeklySnapshot(
                    store_id=store_config.id,
                    week_start=week_start,
                    items=deals,
                )
            )
        except Exception as e:
            logger.warning(f"Failed to snapshot {store_config.id}: {e}")

        return {
            'store': store_info,
            'product_count': len(deals),
            'new_products': saved,
            'already_added': False,
        }

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/api/stores/add':
            self.receive_add_store()
        else:
            self._send_json_error(404, 'Not found')

    def do_DELETE(self):
        parsed = urlparse(self.path)
        prefix = '/api/stores/'
        if not parsed.path.startswith(prefix):
            self._send_json_error(404, 'Not found')
            return

        store_id = unquote(parsed.path[len(prefix):].split('?')[0])
        self.receive_delete_store(store_id)

    def receive_delete_store(self, store_id: str):
        """Remove a store that was added at runtime, along with its products."""
        try:
            if not store_id:
                self._send_json_error(400, 'A store id is required')
                return

            # A configured store cannot be deleted here: the next scheduled
            # scrape would simply bring it back.
            try:
                with open(self.project_root / 'config.yaml', encoding='utf-8') as f:
                    config = yaml.safe_load(f) or {}
            except OSError:
                config = {}
            configured_ids = {
                s.get('id') for s in config.get('stores', []) if s.get('enabled', True)
            }
            if store_id in configured_ids:
                self._send_json_error(
                    403,
                    'This store is set in config.yaml, so it would be re-added on '
                    'the next scrape. Remove it there instead.',
                )
                return

            product_count = self.storage.count_store_products(store_id)
            if not self.storage.delete_store_data(store_id):
                self._send_json_error(500, 'Could not remove that store')
                return

            logger.info("Removed store %s (%s products)", store_id, product_count)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(json.dumps({
                "removed": store_id,
                "product_count": product_count,
            }, ensure_ascii=False).encode('utf-8'))
        except Exception as e:
            logger.error(f"delete_store failed: {e}")
            self._send_json_error(500, str(e))

    def receive_add_store(self):
        """Read the JSON body, add the store, and report the outcome."""
        try:
            length = int(self.headers.get('Content-Length') or 0)
            raw = self.rfile.read(length) if length else b''
            try:
                payload = json.loads(raw.decode('utf-8') or '{}')
            except (ValueError, UnicodeDecodeError):
                self._send_json_error(400, 'Request body must be JSON')
                return

            if not isinstance(payload, dict):
                self._send_json_error(400, 'Request body must be a JSON object')
                return

            url = (payload.get('url') or '').strip()
            if not url:
                self._send_json_error(400, 'A Dutchie store URL is required')
                return

            try:
                result = self.add_store(url)
            except ValueError as e:
                self._send_json_error(400, str(e))
                return

            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(json.dumps(result, default=str, ensure_ascii=False).encode('utf-8'))
        except Exception as e:
            logger.error(f"add_store failed: {e}")
            # The request is still open here, so the failure can be reported.
            self._send_json_error(500, str(e))

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
        try:
            with open(self.project_root / "config.yaml", encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
        except OSError:
            # A missing config is not fatal: the dashboard still shows every
            # store that already has products or was added at runtime.
            config = {}
        for s in config.get("stores", []):
            if s.get("enabled") and s["id"] not in store_ids:
                store_ids.append(s["id"])

        # Stores added at runtime carry their real name and logo, so they must
        # win over the slug that an unknown id would otherwise fall back to.
        known = {k["id"]: k for k in self.storage.list_known_stores()}
        for sid in known:
            if sid not in store_ids:
                store_ids.append(sid)

        # A configured store cannot be removed from the dashboard because the
        # next scrape would re-add it, so only runtime stores are removable.
        configured_ids = {
            s.get("id") for s in config.get("stores", []) if s.get("enabled", True)
        }

        stores = []
        for sid in store_ids:
            cfg = next((s for s in config.get("stores", []) if s["id"] == sid), {})
            added = known.get(sid)
            removable = added is not None and sid not in configured_ids
            if added:
                # The local /api/logo proxy is preferred so the logo is served
                # from this server rather than hotlinked.
                logo = added.get("logo_url") or f"/api/logo/{sid}"
                stores.append({
                    "id": sid,
                    "name": added.get("name") or cfg.get("name", sid),
                    "logo_url": logo,
                    "enabled": cfg.get("enabled", True),
                    "address": added.get("address") or "",
                    "phone": added.get("phone") or "",
                    "removable": removable,
                })
                continue
            stores.append({
                "id": sid,
                "name": cfg.get("name", sid),
                "logo_url": cfg.get("logo_url", ""),
                "enabled": cfg.get("enabled", True),
                "removable": False,
            })
        return stores

    def _brand_canonicalizer(self):
        """Build the brand canonicaliser for the current catalogue once.

        Every product is served through the same function so the sidebar, the
        brand list and brand filtering all agree on one spelling per brand.
        """
        if getattr(self, "_brand_canon", None) is None:
            from utils.brands import make_brand_canonicalizer
            conn = self.storage._get_connection()
            try:
                rows = conn.execute(
                    "SELECT DISTINCT brand FROM seen_deals "
                    "WHERE brand IS NOT NULL AND brand != ''"
                ).fetchall()
            finally:
                conn.close()
            self._brand_canon = make_brand_canonicalizer(r[0] for r in rows)
        return self._brand_canon

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
            # Brands are typed per store, so the same brand arrives with
            # different spellings and would otherwise split into several rows.
            deal["brand"] = self._brand_canonicalizer()(deal.get("brand"))
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
                    # Snapshots store the brand exactly as it was typed when
                    # the menu was scraped, so the same canonicalisation has to
                    # be applied here or the menu view splits brands again.
                    item["brand"] = self._brand_canonicalizer()(item.get("brand"))
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