#!/usr/bin/env python3
import argparse
import logging
import sys
import signal
from datetime import datetime, date, timedelta
from typing import List, Optional

from config import Config
from models import StoreConfig, Deal, WeeklySnapshot, DealStatus, NotificationMode
from utils.diff import WeeklyDiff
from utils.strain_match import StrainResolver, ResolutionStats, enrich_deals
from scrapers import create_scraper
from storage import SQLiteStorage
from notifier import WebhookNotifier
from utils import compute_weekly_diff


def setup_logging(level: str):
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


class DispoDeals:
    def __init__(self, config: Config):
        self.config = config
        self.storage = SQLiteStorage()
        self.notifier = WebhookNotifier(config, self.storage)
        self.running = True
        # Strains are optional: when Leafly is disabled the app behaves exactly
        # as it did before the integration was added.
        self.strain_resolver = self._build_strain_resolver()

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _build_strain_resolver(self) -> Optional[StrainResolver]:
        leafly = getattr(self.config, "leafly", None)
        if not leafly or not leafly.enabled:
            logging.getLogger(__name__).info("Leafly strain import disabled")
            return None

        from utils.leafly import LeaflyClient

        client = LeaflyClient(
            search_endpoint=leafly.search_endpoint,
            site_url=leafly.site_url,
            timeout=leafly.timeout,
            max_retries=leafly.max_retries,
            request_delay_seconds=leafly.request_delay_seconds,
        )
        return StrainResolver(
            storage=self.storage,
            client=client,
            enabled=True,
            categories=list(leafly.categories),
            match_threshold=leafly.match_threshold,
            cache_days=leafly.cache_days,
        )

    def _signal_handler(self, signum, frame):
        logging.getLogger(__name__).info("Shutdown signal received")
        self.running = False

    def run_once(self) -> bool:
        logger = logging.getLogger(__name__)
        logger.info("Starting dispo-deals run")

        all_new_deals = []
        store_results = {}

        for store in self.config.get_enabled_stores():
            try:
                logger.info(f"Scraping {store.name}...")
                scraper = create_scraper(store, self.config)
                deals = scraper.fetch_menu()

                if not deals:
                    logger.warning(f"No deals found for {store.name}")
                    store_results[store.id] = {"deals": [], "error": "No deals found"}
                    continue

                self._enrich_strains(deals)

                new_deals = self._process_deals(store, deals)
                all_new_deals.extend(new_deals)
                store_results[store.id] = {"deals": new_deals, "error": None}

                self._save_weekly_snapshot(store, deals)

            except Exception as e:
                logger.error(f"Error processing {store.name}: {e}")
                store_results[store.id] = {"deals": [], "error": str(e)}

        if all_new_deals:
            self._send_notifications(store_results)

        self._maybe_send_weekly_summary(store_results)

        logger.info(f"Run complete. Found {len(all_new_deals)} new deals across {len(store_results)} stores")
        return True

    def _enrich_strains(self, deals: List[Deal]) -> ResolutionStats:
        """Match each product to a Leafly strain and stamp the name onto it."""
        if not self.strain_resolver:
            return ResolutionStats()

        stats = ResolutionStats()
        enrich_deals(deals, self.strain_resolver, stats)
        count = stats.as_dict()
        logging.getLogger(__name__).info(
            "Strain enrichment: %(resolved)s/%(looked_up)s products matched, "
            "%(api_calls)s Leafly requests, %(from_cache)s from cache",
            count,
        )
        return stats

    def import_strains(self) -> bool:
        """Backfill strains for products already stored.

        Products are keyed by their strain candidate, so this costs roughly one
        API call per distinct strain rather than per product; already-matched and
        already-missed candidates are served from the SQLite cache.
        """
        logger = logging.getLogger(__name__)
        if not self.strain_resolver:
            logger.error("Leafly strain import is unavailable (disabled in config)")
            return False

        deals = self.storage.get_deals_missing_strain(limit=100000)
        logger.info("Backfilling strains for %s products without a strain", len(deals))

        stats = ResolutionStats()
        updated = 0
        for deal in deals:
            strain = self.strain_resolver.resolve_for_product(
                deal.name, brand=deal.brand, category=deal.category
            )
            stats.record(deal.name, strain is not None)
            if strain and self.storage.set_deal_strain(deal.hash, strain.name):
                updated += 1

        logger.info(
            "Strain backfill complete: %s of %s matched, %s deals updated "
            "(%s cached strains, %s cached misses)",
            stats.resolved, stats.looked_up, updated,
            self.storage.count_strains(), self.storage.count_strain_misses(),
        )
        return True

    def enrich_strains(self, limit: int = 2000) -> bool:
        """Fill in flavours and the full description from each strain's page.

        Leafly's search endpoint returns effects, terpenes and potency but never
        flavours, so a second request per strain is what makes the imported
        profiles complete. Only strains missing flavours are fetched, and the
        results overwrite the cached profile.
        """
        logger = logging.getLogger(__name__)
        client = getattr(self.strain_resolver, "client", None)
        if not self.strain_resolver or not client:
            logger.error("Leafly strain import is unavailable (disabled in config)")
            return False

        pending = self.storage.get_strains_needing_detail(limit)
        logger.info("Enriching %s strains with detail-page data", len(pending))

        enriched = 0
        for strain in pending:
            if not strain.slug:
                continue
            try:
                detail = client.get_strain_by_slug(strain.slug)
            except Exception as e:
                logger.warning("Failed to fetch detail for %s: %s", strain.slug, e)
                continue
            if not detail:
                continue
            if self.storage.save_strain(client.merge_strain(strain, detail)):
                enriched += 1

        logger.info("Strain enrichment complete: %s of %s strains enriched", enriched, len(pending))
        return True

    def _process_deals(self, store: StoreConfig, deals: List[Deal]) -> List[Deal]:
        """Track every product, but only return the ones worth notifying about.

        Every product is persisted so the dashboard can browse the full menu,
        while `new_deals` stays restricted to genuine discounts. Without that
        split, the first run after a store starts reporting undiscounted stock
        would blast its whole catalogue to the webhook.
        """
        new_deals = []
        for deal in deals:
            if self.storage.is_new_deal(deal, self.config.deduplication.re_notify_on_deeper_discount):
                self.storage.save_seen_deal(deal)
                if deal.is_deal:
                    new_deals.append(deal)
            else:
                self.storage.update_seen_deal(deal, notify=False)
        return new_deals

    def _save_weekly_snapshot(self, store: StoreConfig, deals: List[Deal]):
        today = date.today()
        week_start = today - timedelta(days=today.weekday())

        existing = self.storage.get_weekly_snapshot(store.id, week_start)
        if existing and len(existing.items) >= self.config.weekly_menu.min_items_for_snapshot:
            return

        snapshot = WeeklySnapshot(
            store_id=store.id,
            week_start=week_start,
            items=deals,
        )
        self.storage.save_weekly_snapshot(snapshot)

    def _send_notifications(self, store_results: dict):
        for store in self.config.get_webhook_stores():
            result = store_results.get(store.id, {})
            new_deals = result.get("deals", [])
            error = result.get("error")

            if error or not new_deals:
                continue

            if store.notification_mode == NotificationMode.PER_STORE:
                weekly_diff = self._get_weekly_diff(store)
                self.notifier.send_store_notification(store, new_deals, weekly_diff)
            else:
                for deal in new_deals:
                    self.notifier.send_product_notification(store, deal)

    def _get_weekly_diff(self, store: StoreConfig) -> Optional[WeeklyDiff]:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        prev_week_start = week_start - timedelta(weeks=1)

        current_snapshot = self.storage.get_weekly_snapshot(store.id, week_start)
        prev_snapshot = self.storage.get_weekly_snapshot(store.id, prev_week_start)

        if not current_snapshot:
            return None

        if not prev_snapshot:
            return compute_weekly_diff(current_snapshot.items, [])

        return compute_weekly_diff(current_snapshot.items, prev_snapshot.items)

    def _maybe_send_weekly_summary(self, store_results: dict):
        """Send each store's weekly menu digest, once per week, on the send day.

        This is a separate stream from the new-deal alerts: a digest goes out on
        a fixed weekday with every item marked new or carried over from last
        week, whereas a deal alert fires the moment a discount appears. The
        week is claimed from storage *before* the message is sent, so a crash,
        a retry, or another run later the same week cannot repeat it.
        """
        logger = logging.getLogger(__name__)
        weekly = self.config.weekly_menu
        if not weekly.enabled:
            return

        today = date.today()
        if today.weekday() != weekly.send_day:
            return

        week_start = today - timedelta(days=today.weekday())
        prev_week_start = week_start - timedelta(weeks=1)

        for store in self.config.get_webhook_stores():
            # A store whose scrape failed has no trustworthy snapshot this week.
            if store_results.get(store.id, {}).get("error"):
                continue

            # On the very first week there is no previous menu, so every item
            # would be marked new and the digest would carry no information.
            if weekly.require_previous_week:
                if not self.storage.get_weekly_snapshot(store.id, prev_week_start):
                    continue

            if not self.storage.claim_weekly_summary(store.id, week_start):
                continue

            diff = self._get_weekly_diff(store)
            if diff is None:
                continue

            if diff.new_count == 0 and diff.carryover_count == 0:
                continue

            if self.notifier.send_weekly_summary(store, diff):
                logger.info(
                    "Sent weekly menu digest for %s (%s new, %s carryover)",
                    store.name, diff.new_count, diff.carryover_count,
                )
            else:
                logger.warning("Failed to send weekly menu digest for %s", store.name)

    def run_scheduler(self):
        import schedule
        import time

        schedule.every().day.at("06:00").do(self.run_once)
        schedule.every().day.at("12:00").do(self.run_once)
        schedule.every().day.at("18:00").do(self.run_once)
        schedule.every().day.at("00:00").do(self.run_once)

        logging.getLogger(__name__).info("Scheduler started. Press Ctrl+C to stop.")

        while self.running:
            schedule.run_pending()
            time.sleep(60)


def main():
    parser = argparse.ArgumentParser(description="Dispo Deals Notifier")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--dry-run", action="store_true", help="Dry run (no webhook sends)")
    parser.add_argument("--store", help="Run for specific store ID only")
    parser.add_argument("--test-webhook", action="store_true", help="Send test webhook")
    parser.add_argument(
        "--import-strains",
        action="store_true",
        help="Import Leafly strain data for products already in the database, then exit",
    )
    parser.add_argument(
        "--enrich-strains",
        action="store_true",
        help="Fetch full profiles (flavours, description) for cached strains, then exit",
    )
    parser.add_argument(
        "--no-enrich",
        action="store_true",
        help="With --import-strains, skip fetching full strain profiles",
    )
    parser.add_argument(
        "--strain-status",
        action="store_true",
        help="Report how many products carry a Leafly strain, then exit",
    )
    args = parser.parse_args()

    config = Config.load(args.config)
    if args.dry_run:
        config.dry_run = True

    if args.store:
        config.stores = [s for s in config.stores if s.id == args.store]
        if not config.stores:
            print(f"Store not found: {args.store}")
            return 1

    setup_logging(config.log_level)

    app = DispoDeals(config)

    if args.test_webhook:
        from models import Deal
        test_deal = Deal(
            store_id="culture-akron",
            product_id="test",
            name="Test Deal - Blue Dream",
            category="Flower",
            original_price=50.0,
            sale_price=35.0,
            discount_pct=30.0,
            image_url="",
            product_url="https://dutchie.com/stores/culture-cannabis-club-akron",
        )
        store = config.get_store("culture-akron") or config.stores[0]
        app.notifier.send_product_notification(store, test_deal)
        print("Test webhook sent")
        return 0

    if args.strain_status:
        print_strain_status(app.storage)
        return 0

    if args.enrich_strains:
        return 0 if app.enrich_strains() else 1

    if args.import_strains:
        if not app.import_strains():
            return 1
        if args.no_enrich:
            return 0
        return 0 if app.enrich_strains() else 1

    if args.once:
        success = app.run_once()
        return 0 if success else 1
    else:
        app.run_scheduler()
        return 0


def print_strain_status(storage: SQLiteStorage):
    """Summarise strain coverage so an import can be checked without SQL."""
    conn = storage._get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) FROM seen_deals").fetchone()[0]
        with_strain = conn.execute(
            "SELECT COUNT(*) FROM seen_deals WHERE strain_name IS NOT NULL AND strain_name != ''"
        ).fetchone()[0]
        per_store = conn.execute("""
            SELECT store_id,
                   COUNT(*) AS products,
                   SUM(CASE WHEN strain_name IS NOT NULL AND strain_name != '' THEN 1 ELSE 0 END) AS matched
            FROM seen_deals
            GROUP BY store_id
            ORDER BY products DESC
        """).fetchall()
    finally:
        conn.close()

    pct = (with_strain / total * 100) if total else 0.0
    print(f"Products with a strain: {with_strain} / {total} ({pct:.1f}%)")
    print(f"Cached strains:         {storage.count_strains()}")
    print(f"Cached misses:          {storage.count_strain_misses()}")
    print(f"Fresh strains:          {storage.count_fresh_strains()}")
    print("\nBy store:")
    for row in per_store:
        store_pct = (row["matched"] / row["products"] * 100) if row["products"] else 0.0
        print(
            f"  {row['store_id']:<20} {row['matched']:>5} / {row['products']:<5} "
            f"({store_pct:.1f}%)"
        )


if __name__ == "__main__":
    sys.exit(main())