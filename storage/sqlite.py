import sqlite3
import json
import os
from datetime import datetime, date, timedelta, timezone
from typing import List, Optional, Dict, Any
from pathlib import Path
import logging

from models import Deal, Strain, WeeklySnapshot, SeenDeal, MenuItem, DealStatus
from utils.strain_match import normalize_name

logger = logging.getLogger(__name__)

PRUNE_MIN_MENU_RATIO = 0.5

DEFAULT_DB_PATH = Path(__file__).parent.parent / "data" / "dispo_deals.db"


class SQLiteStorage:
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(DEFAULT_DB_PATH)
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        # timeout guards against "database is locked" when the scraper and api
        # containers share the data volume.
        # WAL mode enables better concurrency for read-heavy workloads.
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
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

                -- One row per weekly menu digest actually sent. The unique
                -- constraint is what makes "once per week" atomic: a claim
                -- either inserts a new row or hits the constraint and reports
                -- that the week is already taken.
                CREATE TABLE IF NOT EXISTS weekly_summaries (
                    store_id TEXT NOT NULL,
                    week_start TEXT NOT NULL,
                    sent_at TEXT NOT NULL,
                    PRIMARY KEY (store_id, week_start)
                );

                -- Stores added at runtime rather than hard-coded in config.yaml.
                -- Resolved from Dutchie, so the name and logo are the store's
                -- own rather than a slug used as a display name.
                CREATE TABLE IF NOT EXISTS known_stores (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    cname TEXT,
                    url TEXT NOT NULL,
                    logo_url TEXT,
                    address TEXT,
                    phone TEXT,
                    source TEXT DEFAULT 'dutchie',
                    added_at TEXT NOT NULL
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

                CREATE TABLE IF NOT EXISTS strains (
                    name TEXT PRIMARY KEY,
                    slug TEXT,
                    leafly_id TEXT,
                    category TEXT,
                    thc_pct REAL,
                    thc_low REAL,
                    thc_high REAL,
                    cbd_pct REAL,
                    cbd_low REAL,
                    cbd_high REAL,
                    effects TEXT,
                    flavors TEXT,
                    terpenes TEXT,
                    helps_with TEXT,
                    rating REAL,
                    review_count INTEGER,
                    description TEXT,
                    image_url TEXT,
                    parents TEXT,
                    children TEXT,
                    source TEXT,
                    fetched_at TEXT NOT NULL,
                    lookup_count INTEGER DEFAULT 1
                );

                -- Candidate names that produced no Leafly strain. Without this
                -- cache every run would re-query the many products whose names
                -- are flavours or proprietary cuttings Leafly does not carry.
                CREATE TABLE IF NOT EXISTS strain_misses (
                    name TEXT PRIMARY KEY,
                    attempted_at TEXT NOT NULL,
                    attempts INTEGER DEFAULT 1
                );

                -- Favorites / wishlist: user can mark products to track across sessions
                -- cross_store_key enables cross-store favorites (same product at multiple dispensaries)
                CREATE TABLE IF NOT EXISTS favorites (
                    store_id TEXT NOT NULL,
                    product_id TEXT NOT NULL,
                    cross_store_key TEXT,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (store_id, product_id)
                );

                -- Price history: records price points for charting trends
                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    store_id TEXT NOT NULL,
                    product_id TEXT NOT NULL,
                    original_price REAL NOT NULL,
                    sale_price REAL NOT NULL,
                    discount_pct REAL NOT NULL,
                    recorded_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_seen_deals_store ON seen_deals(store_id);
                CREATE INDEX IF NOT EXISTS idx_snapshots_store_week ON weekly_snapshots(store_id, week_start);
                CREATE INDEX IF NOT EXISTS idx_price_history_store_product ON price_history(store_id, product_id, recorded_at);
            """)
            conn.commit()
        self._migrate_schema()

    def _migrate_schema(self):
        """Bring an older database up to the current schema.

        SQLite has no "add column if absent", and the databases in the wild
        predate the strain fields, so the columns are added by inspection rather
        than by assuming a fresh schema. The strain index has to be created
        afterwards, because it references the column being added.
        """
        with self._get_connection() as conn:
            columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(seen_deals)").fetchall()
            }
            if "strain_name" not in columns:
                conn.execute("ALTER TABLE seen_deals ADD COLUMN strain_name TEXT")
                logger.info("Added strain_name column to seen_deals")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_seen_deals_strain ON seen_deals(strain_name)"
            )
            # Migrate favorites table for cross-store favorites
            fav_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(favorites)").fetchall()
            }
            if "cross_store_key" not in fav_columns:
                conn.execute("ALTER TABLE favorites ADD COLUMN cross_store_key TEXT")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_favorites_cross_store ON favorites(cross_store_key)")
                logger.info("Added cross_store_key column to favorites")
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
        now = datetime.now(timezone.utc)
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
            strain_name=deal.strain_name,
            first_seen=now,
            last_notified=now,
            notify_count=1,
        )
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO seen_deals (hash, store_id, product_id, name, category, original_price, sale_price, discount_pct, max_discount_pct, image_url, product_url, in_stock, thc_pct, cbd_pct, weight, brand, strain_name, first_seen, last_notified, notify_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                seen.hash, seen.store_id, seen.product_id, seen.name,
                deal.category, deal.original_price, deal.sale_price, deal.discount_pct, seen.max_discount_pct,
                deal.image_url, deal.product_url, int(deal.in_stock), deal.thc_pct, deal.cbd_pct, deal.weight, deal.brand,
                deal.strain_name,
                seen.first_seen.isoformat(), seen.last_notified.isoformat(),
                seen.notify_count
            ))
            conn.commit()
        return seen

    def update_seen_deal(self, deal: Deal, notify: bool = True) -> SeenDeal:
        existing = self.get_seen_deal(deal.hash)
        if not existing:
            return self.save_seen_deal(deal)

        now = datetime.now(timezone.utc)
        max_discount = max(existing.max_discount_pct, deal.discount_pct)
        notify_count = existing.notify_count + (1 if notify else 0)

        with self._get_connection() as conn:
            conn.execute("""
                UPDATE seen_deals
                SET sale_price = ?, discount_pct = ?, max_discount_pct = ?,
                    category = ?, original_price = ?, image_url = ?, product_url = ?,
                    in_stock = ?, thc_pct = ?, cbd_pct = ?, weight = ?, brand = ?,
                    strain_name = ?, last_notified = ?, notify_count = ?
                WHERE hash = ?
            """, (
                deal.sale_price, deal.discount_pct, max_discount,
                deal.category, deal.original_price, deal.image_url, deal.product_url,
                int(deal.in_stock), deal.thc_pct, deal.cbd_pct, deal.weight, deal.brand,
                # Keep an existing strain when this run resolved nothing, so an
                # empty enrichment never wipes good data.
                deal.strain_name or existing.strain_name,
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
        existing.strain_name = deal.strain_name or existing.strain_name
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

    def get_most_recent_scrape_time(self) -> Optional[datetime]:
        """Return the most recent capture time across all weekly snapshots."""
        with self._get_connection() as conn:
            row = conn.execute("""
                SELECT captured_at FROM weekly_snapshots
                ORDER BY captured_at DESC
                LIMIT 1
            """).fetchone()
            if row and row[0]:
                try:
                    return datetime.fromisoformat(row[0].replace('Z', '+00:00'))
                except Exception:
                    pass
        return None

    def get_store_last_scrape(self, store_id: str) -> Optional[datetime]:
        """When this store was last successfully scraped.

        Powers the per-store scrape-interval throttle; None means it has never
        been scraped, so the throttle lets it run.
        """
        with self._get_connection() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS store_scrape_state "
                "(store_id TEXT PRIMARY KEY, last_scraped_at TEXT)"
            )
            row = conn.execute(
                "SELECT last_scraped_at FROM store_scrape_state WHERE store_id = ?",
                (store_id,),
            ).fetchone()
            if row and row[0]:
                try:
                    return datetime.fromisoformat(row[0].replace('Z', '+00:00'))
                except Exception:
                    return None
        return None

    def set_store_last_scrape(self, store_id: str, when: datetime) -> None:
        """Record a successful scrape time for the throttle."""
        with self._get_connection() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS store_scrape_state "
                "(store_id TEXT PRIMARY KEY, last_scraped_at TEXT)"
            )
            conn.execute(
                "INSERT OR REPLACE INTO store_scrape_state (store_id, last_scraped_at) VALUES (?, ?)",
                (store_id, when.isoformat()),
            )
            conn.commit()

    def claim_weekly_summary(self, store_id: str, week_start: date) -> bool:
        """Reserve the right to send this store's weekly menu for this week.

        Returns True when this call is the one that reserved it. The row is
        committed before the message goes out, so a crash, a retry or a second
        run later the same week cannot repeat the digest: the insert either
        succeeds once or hits the primary key and reports the week is taken.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO weekly_summaries (store_id, week_start, sent_at) VALUES (?, ?, ?)",
                (
                    store_id,
                    week_start.isoformat(),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
            return cursor.rowcount > 0

    def save_known_store(self, store: Dict[str, Any]) -> bool:
        """Record a store added at runtime, keyed by its stable id.

        The id is Dutchie's dispensary id rather than the cName slug, so a
        re-add of the same store updates the row instead of duplicating it.
        """
        with self._get_connection() as conn:
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO known_stores
                    (id, name, cname, url, logo_url, address, phone, source, added_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        store["id"],
                        store["name"],
                        store.get("cname", ""),
                        store["url"],
                        store.get("logo_url", ""),
                        store.get("address", ""),
                        store.get("phone", ""),
                        store.get("source", "dutchie"),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Failed to save known store {store.get('id')!r}: {e}")
                return False

    def list_known_stores(self) -> List[Dict[str, Any]]:
        """Return every store added at runtime, newest first."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM known_stores ORDER BY added_at DESC, name ASC"
            ).fetchall()
        return [dict(row) for row in rows]

    def count_store_products(self, store_id: str) -> int:
        """How many products this store currently has on the dashboard."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM seen_deals WHERE store_id = ?", (store_id,)
            ).fetchone()
        return row[0] if row else 0

    def prune_missing_products(self, store_id: str, current_hashes: List[str]) -> int:
        """Remove products for a store that are no longer in the current scrape.

        Guarded by PRUNE_MIN_MENU_RATIO: if the new menu is less than 50% of
        the existing menu size, assume a partial/failed scrape and prune nothing.
        This prevents a Cloudflare block or timeout from wiping the catalogue.
        """
        if not current_hashes:
            return 0

        with self._get_connection() as conn:
            # Count existing products for this store
            existing_count = conn.execute(
                "SELECT COUNT(*) FROM seen_deals WHERE store_id = ?", (store_id,)
            ).fetchone()[0]

            # Guard: if new menu is less than 50% of existing, don't prune
            if existing_count > 0 and len(current_hashes) < existing_count * PRUNE_MIN_MENU_RATIO:
                logger.info(
                    f"Prune skipped for {store_id}: new menu ({len(current_hashes)}) "
                    f"< {PRUNE_MIN_MENU_RATIO * 100:.0f}% of existing ({existing_count})"
                )
                return 0

            # Delete products whose hash is not in the current scrape
            placeholders = ",".join("?" for _ in current_hashes)
            query = f"""
                DELETE FROM seen_deals
                WHERE store_id = ? AND hash NOT IN ({placeholders})
            """
            cursor = conn.execute(query, [store_id] + current_hashes)
            conn.commit()
            pruned = cursor.rowcount
            if pruned:
                logger.info(f"Pruned {pruned} stale products for {store_id}")
            return pruned

    def delete_store_data(self, store_id: str) -> bool:
        """Remove every trace of a store that was added at runtime.

        Product *images* are deliberately left alone: they are cached by URL
        hash, and another store can legitimately serve the same image, so
        deleting them here could drop a still-referenced cache entry. They are
        a cache, so leaving them costs only disk space.
        """
        with self._get_connection() as conn:
            try:
                conn.execute("DELETE FROM known_stores WHERE id = ?", (store_id,))
                conn.execute("DELETE FROM seen_deals WHERE store_id = ?", (store_id,))
                conn.execute("DELETE FROM weekly_snapshots WHERE store_id = ?", (store_id,))
                conn.execute("DELETE FROM weekly_summaries WHERE store_id = ?", (store_id,))
                conn.execute("DELETE FROM store_logos WHERE store_id = ?", (store_id,))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Failed to delete store {store_id}: {e}")
                conn.rollback()
                return False

    def is_added_store(self, store_id: str) -> bool:
        """True when this store came from the runtime Add Store flow."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM known_stores WHERE id = ?", (store_id,)
            ).fetchone()
        return row is not None

    def save_store_logo(self, store_id: str, image_data: bytes, mime_type: str = "image/png"):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO store_logos (store_id, image_data, mime_type, updated_at)
                VALUES (?, ?, ?, ?)
            """, (store_id, image_data, mime_type, datetime.now(timezone.utc).isoformat()))
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
            """, (url_hash, image_data, mime_type, datetime.now(timezone.utc).isoformat()))
            conn.commit()

    def get_product_image(self, url_hash: str) -> Optional[bytes]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT image_data FROM product_images WHERE url_hash = ?", (url_hash,)
            ).fetchone()
            return row[0] if row else None

    # ---- strains ----

    def get_strain(self, normalized_name: str) -> Optional[Strain]:
        """Look up a cached strain by its normalised name."""
        row = self._get_strain_row(normalized_name)
        return self._strain_from_row(row) if row else None

    def get_strains(self, normalized_names: List[str]) -> dict:
        """Look up many cached strains in one pass, keyed by normalised name."""
        if not normalized_names:
            return {}

        found: dict = {}
        # Chunked so a long IN (...) never trips SQLite's bound-parameter limit.
        for start in range(0, len(normalized_names), 400):
            chunk = normalized_names[start:start + 400]
            placeholders = ",".join("?" for _ in chunk)
            query = f"SELECT * FROM strains WHERE lower(name) IN ({placeholders})"
            try:
                with self._get_connection() as conn:
                    rows = conn.execute(query, chunk).fetchall()
            except Exception as e:
                logger.warning(f"Failed to load strains: {e}")
                continue
            for row in rows:
                strain = self._strain_from_row(row)
                if strain:
                    found[strain.name.strip().lower()] = strain
        return found

    def get_strain_index(self) -> dict:
        """Every cached strain keyed by normalised display name.

        Strain profiles are few and small, so the API loads them all in one
        query and indexes in Python. That avoids the mismatch of normalising in
        SQL: "GG#4" and "gg4" are the same strain for lookups but not for a
        ``lower(name)`` comparison.
        """
        index: dict = {}
        try:
            with self._get_connection() as conn:
                rows = conn.execute("SELECT * FROM strains").fetchall()
        except Exception as e:
            # A database that predates the strain schema simply has no strains.
            logger.debug(f"Failed to load strain index: {e}")
            return index

        for row in rows:
            strain = self._strain_from_row(row)
            if strain:
                index[normalize_name(strain.name)] = strain
        return index

    def get_strain_names_by_hash(self) -> dict:
        """Deal hash -> strain display name, one query for the whole menu.

        Snapshots written before the strain importer ran carry no strain name,
        so joining through the live deals table is what keeps the dashboard
        working off older weekly snapshots.
        """
        mapping: dict = {}
        try:
            with self._get_connection() as conn:
                rows = conn.execute("""
                    SELECT hash, strain_name FROM seen_deals
                    WHERE strain_name IS NOT NULL AND strain_name != ''
                """).fetchall()
        except Exception as e:
            logger.debug(f"Failed to load strain names: {e}")
            return mapping
        for row in rows:
            mapping[row["hash"]] = row["strain_name"]
        return mapping

    def get_strain_rows_for_names(self, names: List[str]) -> List[Strain]:
        """Return cached strains whose display name matches any of `names`."""
        if not names:
            return []
        lowered = [n.strip().lower() for n in names if n and n.strip()]
        if not lowered:
            return []
        return list(self.get_strains(lowered).values())

    def _get_strain_row(self, normalized_name: str):
        # The lookup key is a normalised (lower-cased) name while the column
        # holds Leafly's display casing, so the comparison is case-insensitive.
        # Without this the resolver's cache would never hit and every run would
        # re-query Leafly for strains it had already imported.
        with self._get_connection() as conn:
            return conn.execute(
                "SELECT * FROM strains WHERE name = ? COLLATE NOCASE", (normalized_name,)
            ).fetchone()

    @staticmethod
    def _strain_from_row(row) -> Optional[Strain]:
        if not row:
            return None
        data = dict(row)
        for field_name in ("effects", "flavors", "terpenes", "helps_with", "parents", "children"):
            try:
                data[field_name] = json.loads(data.get(field_name) or "[]")
            except (TypeError, ValueError):
                data[field_name] = []
        try:
            # `fetched_at` is left as its stored string: Strain.from_dict is the
            # single place that converts it, so parsing it here too would try to
            # parse a datetime and fail.
            return Strain.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to parse cached strain {data.get('name')!r}: {e}")
            return None

    def save_strain(self, strain: Strain) -> bool:
        """Insert or refresh a strain profile, preserving lookup counts."""
        now = datetime.now(timezone.utc).isoformat()
        if strain.fetched_at is None:
            strain.fetched_at = datetime.now(timezone.utc)
        try:
            with self._get_connection() as conn:
                existing = conn.execute(
                    "SELECT lookup_count FROM strains WHERE name = ?", (strain.name,)
                ).fetchone()
                lookup_count = (existing[0] + 1) if existing else 1
                conn.execute("""
                    INSERT OR REPLACE INTO strains
                    (name, slug, leafly_id, category, thc_pct, thc_low, thc_high,
                     cbd_pct, cbd_low, cbd_high, effects, flavors, terpenes,
                     helps_with, rating, review_count, description, image_url,
                     parents, children, source, fetched_at, lookup_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    strain.name, strain.slug, strain.leafly_id, strain.category,
                    strain.thc_pct, strain.thc_low, strain.thc_high,
                    strain.cbd_pct, strain.cbd_low, strain.cbd_high,
                    json.dumps(strain.effects), json.dumps(strain.flavors),
                    json.dumps(strain.terpenes), json.dumps(strain.helps_with),
                    strain.rating, strain.review_count, strain.description,
                    strain.image_url,
                    json.dumps(strain.parents), json.dumps(strain.children),
                    strain.source, strain.fetched_at.isoformat(), lookup_count,
                ))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save strain {strain.name!r}: {e}")
            return False

    def record_strain_miss(self, normalized_name: str) -> None:
        """Remember that a candidate produced no strain, to avoid re-querying."""
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO strain_misses (name, attempted_at, attempts)
                    VALUES (?, ?, 1)
                    ON CONFLICT(name) DO UPDATE SET
                        attempted_at = excluded.attempted_at,
                        attempts = attempts + 1
                """, (normalized_name, now))
                conn.commit()
        except Exception as e:
            logger.warning(f"Failed to record strain miss for {normalized_name!r}: {e}")

    def is_strain_miss(self, normalized_name: str) -> Optional[str]:
        """Return when a candidate last failed to match, or None."""
        try:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT attempted_at FROM strain_misses WHERE name = ?", (normalized_name,)
                ).fetchone()
        except Exception as e:
            logger.warning(f"Failed to read strain miss for {normalized_name!r}: {e}")
            return None
        return row[0] if row else None

    def clear_strain_misses(self) -> int:
        """Drop the miss cache so every candidate is tried against Leafly again."""
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM strain_misses")
            conn.commit()
            return cursor.rowcount

    def count_strains(self) -> int:
        with self._get_connection() as conn:
            row = conn.execute("SELECT COUNT(*) FROM strains").fetchone()
        return row[0] if row else 0

    def get_strains_needing_detail(self, limit: int = 500) -> List[Strain]:
        """Return cached strains whose flavour list is still empty.

        Leafly's search endpoint carries effects and terpenes but not flavours;
        those only exist on the strain's own page. This is how the importer
        finds the profiles worth a second request.
        """
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM strains
                WHERE (flavors IS NULL OR flavors = '' OR flavors = '[]')
                ORDER BY lookup_count DESC, name
                LIMIT ?
            """, (limit,)).fetchall()
        strains = [self._strain_from_row(row) for row in rows]
        return [s for s in strains if s]

    def count_strain_misses(self) -> int:
        with self._get_connection() as conn:
            row = conn.execute("SELECT COUNT(*) FROM strain_misses").fetchone()
        return row[0] if row else 0

    def get_deals_missing_strain(self, limit: int = 500) -> List[SeenDeal]:
        """Return strain-eligible deals that have no strain attached yet."""
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM seen_deals
                WHERE (strain_name IS NULL OR strain_name = '')
                ORDER BY last_notified DESC
                LIMIT ?
            """, (limit,)).fetchall()
        return [SeenDeal.from_dict(dict(row)) for row in rows]

    def set_deal_strain(self, deal_hash: str, strain_name: Optional[str]) -> bool:
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE seen_deals SET strain_name = ? WHERE hash = ?",
                (strain_name, deal_hash),
            )
            conn.commit()
        return True

    def count_fresh_strains(self, max_age_days: int = 30) -> int:
        """Number of cached strains younger than `max_age_days`."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM strains WHERE fetched_at >= ?", (cutoff,)
            ).fetchone()
        return row[0] if row else 0

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

    @staticmethod
    def _cross_store_key(name: str, brand: str, category: str, weight: str) -> str:
        """Generate cross-store dedupe key matching API server logic."""
        name = (name or "").strip().lower()
        brand = (brand or "").strip().lower()
        category = (category or "").strip().lower()
        weight = (weight or "").strip().lower().replace(" ", "")
        return f"{name}|{brand}|{category}|{weight}"

    def add_favorite(self, store_id: str, product_id: str, cross_store_key: str = None) -> bool:
        """Add a product to favorites. If cross_store_key provided, favorites all stores carrying it."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            if cross_store_key:
                # Favorite all stores carrying this product (same cross_store_key in seen_deals)
                # First, find all products with this cross_store_key
                rows = conn.execute("""
                    SELECT store_id, product_id FROM seen_deals
                    WHERE lower(name) || '|' || lower(brand) || '|' || lower(category) || '|' || REPLACE(lower(weight), ' ', '') = ?
                """, (cross_store_key,)).fetchall()
                for row in rows:
                    conn.execute(
                        "INSERT OR REPLACE INTO favorites (store_id, product_id, cross_store_key, created_at) VALUES (?, ?, ?, ?)",
                        (row[0], row[1], cross_store_key, now),
                    )
            else:
                conn.execute(
                    "INSERT OR REPLACE INTO favorites (store_id, product_id, cross_store_key, created_at) VALUES (?, ?, ?, ?)",
                    (store_id, product_id, cross_store_key, now),
                )
            conn.commit()
        return True

    def remove_favorite(self, store_id: str, product_id: str, cross_store_key: str = None) -> bool:
        """Remove a product from favorites. If cross_store_key provided, removes from all stores."""
        with self._get_connection() as conn:
            if cross_store_key:
                conn.execute(
                    "DELETE FROM favorites WHERE cross_store_key = ?",
                    (cross_store_key,),
                )
            else:
                conn.execute(
                    "DELETE FROM favorites WHERE store_id = ? AND product_id = ?",
                    (store_id, product_id),
                )
            conn.commit()
        return True

    def get_favorites(self) -> List[Dict[str, Any]]:
        """Get all favorited products with their details."""
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT f.store_id, f.product_id, f.created_at, f.cross_store_key,
                       s.name, s.category, s.original_price, s.sale_price,
                       s.discount_pct, s.image_url, s.product_url, s.in_stock,
                       s.thc_pct, s.cbd_pct, s.weight, s.brand, s.strain_name
                FROM favorites f
                JOIN seen_deals s ON s.store_id = f.store_id AND s.product_id = f.product_id
                ORDER BY f.created_at DESC
            """).fetchall()
        return [dict(row) for row in rows]

    def is_favorite(self, store_id: str, product_id: str, cross_store_key: str = None) -> bool:
        """Check if a product is favorited. If cross_store_key provided, checks any store."""
        with self._get_connection() as conn:
            if cross_store_key:
                row = conn.execute(
                    "SELECT 1 FROM favorites WHERE cross_store_key = ?",
                    (cross_store_key,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT 1 FROM favorites WHERE store_id = ? AND product_id = ?",
                    (store_id, product_id),
                ).fetchone()
        return row is not None

    # ---- Price History ----

    def record_price_history(self, deal: Deal) -> bool:
        """Record a price point for a product."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO price_history (store_id, product_id, original_price, sale_price, discount_pct, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (deal.store_id, deal.product_id, deal.original_price, deal.sale_price, deal.discount_pct, now),
            )
            conn.commit()
        return True

    def get_price_history(self, store_id: str, product_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get price history for a product."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT original_price, sale_price, discount_pct, recorded_at
                FROM price_history
                WHERE store_id = ? AND product_id = ?
                ORDER BY recorded_at DESC
                LIMIT ?
                """,
                (store_id, product_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]