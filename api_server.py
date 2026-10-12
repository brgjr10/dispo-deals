#!/usr/bin/env python3
"""
Simple API server for the Dispo Deals dashboard.
Serves data from SQLite and the dashboard HTML.
"""
import json
import sqlite3
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from datetime import date, datetime, timedelta
from urllib.parse import urlparse, parse_qs
import sys

sys.path.insert(0, str(Path(__file__).parent))

from storage.sqlite import SQLiteStorage
from utils.diff import compute_weekly_diff


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.storage = SQLiteStorage()
        self.project_root = Path(__file__).parent
        super().__init__(*args, directory=str(self.project_root), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/api/data':
            self.send_api_data()
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
        rows = conn.execute("""
            SELECT DISTINCT store_id FROM seen_deals
        """).fetchall()
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
        rows = conn.execute("""
            SELECT * FROM seen_deals ORDER BY last_notified DESC
        """).fetchall()

        deals = []
        for row in rows:
            deal = dict(row)
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
        store_rows = conn.execute("SELECT DISTINCT store_id FROM weekly_snapshots").fetchall()

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
    server = HTTPServer(('', port), DashboardHandler)
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