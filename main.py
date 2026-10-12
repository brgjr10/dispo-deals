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
        self.notifier = WebhookNotifier(config)
        self.running = True

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

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

                new_deals = self._process_deals(store, deals)
                all_new_deals.extend(new_deals)
                store_results[store.id] = {"deals": new_deals, "error": None}

                self._save_weekly_snapshot(store, deals)

            except Exception as e:
                logger.error(f"Error processing {store.name}: {e}")
                store_results[store.id] = {"deals": [], "error": str(e)}

        if all_new_deals:
            self._send_notifications(store_results)

        logger.info(f"Run complete. Found {len(all_new_deals)} new deals across {len(store_results)} stores")
        return True

    def _process_deals(self, store: StoreConfig, deals: List[Deal]) -> List[Deal]:
        new_deals = []
        for deal in deals:
            if self.storage.is_new_deal(deal, self.config.deduplication.re_notify_on_deeper_discount):
                self.storage.save_seen_deal(deal)
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

    if args.once:
        success = app.run_once()
        return 0 if success else 1
    else:
        app.run_scheduler()
        return 0


if __name__ == "__main__":
    sys.exit(main())