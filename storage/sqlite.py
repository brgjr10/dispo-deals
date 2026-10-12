import sqlite3
import json
import os
from datetime import datetime, date
from typing import List, Optional, Dict, Any
from pathlib import Path
import logging

from models import Deal, WeeklySnapshot, SeenDeal, MenuItem, DealStatus

logger = logging.getLogger(__name__)


class SQLiteStorage:
    def __init__(self, db_path: str = "./data/dispo_deals.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        # timeout guards against "database is locked" when the scraper and api
        # containers share the data volume.
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS seen_deals (
                    hash TEXT PRIMARY KEY,
                    store_id TEXT NOT NULL,
                    product_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    original_price REAL NOT NULL,
                    sale_price REAL NOT NULL,
                    discount_pct REAL NOT NULL,
                    max_discount_pct REAL NOT NULL,
                    image_url TEXT,
                    product_url TEXT,
                    in_stock INTEGER DEFAULT 1,
                    thc_pct REAL,
                    cbd_pct REAL,
                    weight TEXT,
                    brand TEXT,
                    first_seen TEXT NOT NULL,
                    last_notified TEXT NOT NULL,
                    notify_count INTEGER DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS weekly_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    store_id TEXT NOT NULL,
                    week_start TEXT NOT NULL,
                    items TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    UNIQUE(store_id, week_start)
                );

                CREATE TABLE IF NOT EXISTS store_logos (
                    store_id TEXT PRIMARY KEY,
                    image_data BLOB,
                    mime_type TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS product_images (
                    url_hash TEXT PRIMARY KEY,
                    image_data BLOB,
                    mime_type TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_seen_deals_store ON seen_deals(store_id);
                CREATE INDEX IF NOT EXISTS idx_snapshots_store_week ON weekly_snapshots(store_id, week_start);
            """)
            conn.commit()

    def get_seen_deal(self, deal_hash: str) -> Optional[SeenDeal]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM seen_deals WHERE hash = ?", (deal_hash,)
            ).fetchone()
            if row:
                return SeenDeal.from_dict(dict(row))
        return None

    def save_seen_deal(self, deal: Deal) -> SeenDeal:
        now = datetime.utcnow()
        seen = SeenDeal(
            hash=deal.hash,
            store_id=deal.store_id,
            product_id=deal.product_id,
            name=deal.name,
            category=deal.category,
            original_price=deal.original_price,
            sale_price=deal.sale_price,
            discount_pct=deal.discount_pct,
            max_discount_pct=deal.discount_pct,
            image_url=deal.image_url,
            product_url=deal.product_url,
            in_stock=deal.in_stock,
            thc_pct=deal.thc_pct,
            cbd_pct=deal.cbd_pct,
            weight=deal.weight,
            brand=deal.brand,
            first_seen=now,
            last_notified=now,
            notify_count=1,
        )
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO seen_deals (hash, store_id, product_id, name, category, original_price, sale_price, discount_pct, max_discount_pct, image_url, product_url, in_stock, thc_pct, cbd_pct, weight, brand, first_seen, last_notified, notify_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                seen.hash, seen.store_id, seen.product_id, seen.name,
                deal.category, deal.original_price, deal.sale_price, deal.discount_pct, seen.max_discount_pct,
                deal.image_url, deal.product_url, int(deal.in_stock), deal.thc_pct, deal.cbd_pct, deal.weight, deal.brand,
                seen.first_seen.isoformat(), seen.last_notified.isoformat(),
                seen.notify_count
            ))
            conn.commit()
        return seen

    def update_seen_deal(self, deal: Deal, notify: bool = True) -> SeenDeal:
        existing = self.get_seen_deal(deal.hash)
        if not existing:
            return self.save_seen_deal(deal)

        now = datetime.utcnow()
        max_discount = max(existing.max_discount_pct, deal.discount_pct)
        notify_count = existing.notify_count + (1 if notify else 0)

        with self._get_connection() as conn:
            conn.execute("""
                UPDATE seen_deals
                SET sale_price = ?, discount_pct = ?, max_discount_pct = ?,
                    category = ?, original_price = ?, image_url = ?, product_url = ?,
                    in_stock = ?, thc_pct = ?, cbd_pct = ?, weight = ?, brand = ?,
                    last_notified = ?, notify_count = ?
                WHERE hash = ?
            """, (
                deal.sale_price, deal.discount_pct, max_discount,
                deal.category, deal.original_price, deal.image_url, deal.product_url,
                int(deal.in_stock), deal.thc_pct, deal.cbd_pct, deal.weight, deal.brand,
                now.isoformat() if notify else existing.last_notified,
                notify_count, deal.hash
            ))
            conn.commit()

        existing.sale_price = deal.sale_price
        existing.discount_pct = deal.discount_pct
        existing.max_discount_pct = max_discount
        existing.category = deal.category
        existing.original_price = deal.original_price
        existing.image_url = deal.image_url
        existing.product_url = deal.product_url
        existing.in_stock = deal.in_stock
        existing.thc_pct = deal.thc_pct
        existing.cbd_pct = deal.cbd_pct
        existing.weight = deal.weight
        existing.brand = deal.brand
        if notify:
            existing.last_notified = now
            existing.notify_count = notify_count
        return existing

    def is_new_deal(self, deal: Deal, re_notify_on_deeper_discount: bool = True) -> bool:
        existing = self.get_seen_deal(deal.hash)
        if not existing:
            return True
        if re_notify_on_deeper_discount and deal.discount_pct > existing.max_discount_pct:
            return True
        return False

    def save_weekly_snapshot(self, snapshot: WeeklySnapshot) -> bool:
        with self._get_connection() as conn:
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO weekly_snapshots (store_id, week_start, items, captured_at)
                    VALUES (?, ?, ?, ?)
                """, (
                    snapshot.store_id,
                    snapshot.week_start.isoformat(),
                    json.dumps([item.to_dict() for item in snapshot.items]),
                    snapshot.captured_at.isoformat()
                ))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Failed to save weekly snapshot: {e}")
                return False

    def get_weekly_snapshot(self, store_id: str, week_start: date) -> Optional[WeeklySnapshot]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM weekly_snapshots WHERE store_id = ? AND week_start = ?",
                (store_id, week_start.isoformat())
            ).fetchone()
            if row:
                data = dict(row)
                data["items"] = json.loads(data["items"])
                return WeeklySnapshot.from_dict(data)
        return None

    def get_latest_snapshot(self, store_id: str) -> Optional[WeeklySnapshot]:
        with self._get_connection() as conn:
            row = conn.execute("""
                SELECT * FROM weekly_snapshots
                WHERE store_id = ?
                ORDER BY week_start DESC
                LIMIT 1
            """, (store_id,)).fetchone()
            if row:
                data = dict(row)
                data["items"] = json.loads(data["items"])
                return WeeklySnapshot.from_dict(data)
        return None

    def save_store_logo(self, store_id: str, image_data: bytes, mime_type: str = "image/png"):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO store_logos (store_id, image_data, mime_type, updated_at)
                VALUES (?, ?, ?, ?)
            """, (store_id, image_data, mime_type, datetime.utcnow().isoformat()))
            conn.commit()

    def get_store_logo(self, store_id: str) -> Optional[bytes]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT image_data FROM store_logos WHERE store_id = ?", (store_id,)
            ).fetchone()
            return row[0] if row else None

    def save_product_image(self, url_hash: str, image_data: bytes, mime_type: str = "image/jpeg"):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO product_images (url_hash, image_data, mime_type, updated_at)
                VALUES (?, ?, ?, ?)
            """, (url_hash, image_data, mime_type, datetime.utcnow().isoformat()))
            conn.commit()

    def get_product_image(self, url_hash: str) -> Optional[bytes]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT image_data FROM product_images WHERE url_hash = ?", (url_hash,)
            ).fetchone()
            return row[0] if row else None

    def get_all_seen_deals(self, store_id: Optional[str] = None) -> List[SeenDeal]:
        with self._get_connection() as conn:
            if store_id:
                rows = conn.execute(
                    "SELECT * FROM seen_deals WHERE store_id = ? ORDER BY last_notified DESC",
                    (store_id,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM seen_deals ORDER BY last_notified DESC"
                ).fetchall()
            return [SeenDeal.from_dict(dict(row)) for row in rows]

    def cleanup_old_snapshots(self, keep_weeks: int = 8):
        cutoff = date.today().replace(day=1)
        from datetime import timedelta
        cutoff = cutoff - timedelta(weeks=keep_weeks)
        with self._get_connection() as conn:
            conn.execute(
                "DELETE FROM weekly_snapshots WHERE week_start < ?",
                (cutoff.isoformat(),)
            )
            conn.commit()