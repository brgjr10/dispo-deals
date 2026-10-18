"""The per-store scrape-interval throttle: no re-fetch before the interval."""

from datetime import datetime, timedelta, timezone

from main import store_is_due, store_is_due_initial
from models import StoreConfig
from storage.sqlite import SQLiteStorage


def store(**kw):
    base = dict(id="s", name="S", url="https://s.test/", scraper="shopify", logo_url="")
    base.update(kw)
    return StoreConfig(**base)


class TestStoreConfigField:
    def test_parses_interval(self):
        s = StoreConfig.from_dict({
            "id": "x", "name": "X", "url": "https://x.test/", "scraper": "shopify",
            "logo_url": "", "scrape_interval_hours": 24,
        })
        assert s.scrape_interval_hours == 24

    def test_defaults_to_none(self):
        s = store()
        assert s.scrape_interval_hours is None


class TestStoreIsDue:
    def setup_method(self):
        self.now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    def test_no_interval_is_always_due(self):
        assert store_is_due(store(), self.now - timedelta(minutes=1), self.now) is True
        assert store_is_due(store(), None, self.now) is True

    def test_never_scraped_is_due(self):
        assert store_is_due(store(scrape_interval_hours=24), None, self.now) is True

    def test_within_interval_is_not_due(self):
        last = self.now - timedelta(hours=6)
        assert store_is_due(store(scrape_interval_hours=24), last, self.now) is False

    def test_interval_elapsed_is_due(self):
        last = self.now - timedelta(hours=25)
        assert store_is_due(store(scrape_interval_hours=24), last, self.now) is True

    def test_boundary_is_due(self):
        last = self.now - timedelta(hours=24)
        assert store_is_due(store(scrape_interval_hours=24), last, self.now) is True

    def test_naive_datetime_is_treated_as_utc(self):
        last = datetime(2026, 1, 1, 8, 0)  # naive -> 4h ago, within 24h
        assert store_is_due(store(scrape_interval_hours=24), last, self.now) is False


class TestStoreIsDueInitial:
    """The on-launch throttle skips only stores scraped within the hour."""

    def setup_method(self):
        self.now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    def test_never_scraped_is_due(self):
        assert store_is_due_initial(store(), None, self.now) is True

    def test_within_window_is_skipped(self):
        last = self.now - timedelta(minutes=20)
        assert store_is_due_initial(store(), last, self.now, product_count=40) is False

    def test_window_elapsed_is_due(self):
        last = self.now - timedelta(hours=2)
        assert store_is_due_initial(store(), last, self.now, product_count=40) is True

    def test_boundary_is_due(self):
        last = self.now - timedelta(hours=1)
        assert store_is_due_initial(store(), last, self.now, product_count=40) is True

    def test_empty_store_is_never_skipped(self):
        """A scrape that saved nothing must not look fresh.

        Otherwise a block, a timeout or an empty menu stamps the store as
        current and the throttle holds it empty for the whole window, so the
        store silently disappears from the dashboard.
        """
        last = self.now - timedelta(minutes=1)
        assert store_is_due_initial(store(), last, self.now, product_count=0) is True

    def test_no_count_supplied_defaults_to_scraping(self):
        """The safe default: not knowing the catalogue must not skip it."""
        last = self.now - timedelta(minutes=1)
        assert store_is_due_initial(store(), last, self.now) is True

    def test_naive_datetime_is_treated_as_utc(self):
        last = datetime(2026, 1, 1, 11, 30)  # naive -> 30m ago
        assert store_is_due_initial(store(), last, self.now, product_count=10) is False


class TestInitialRunSkipsOnlyNonEmptyStores:
    """run_once's initial path: the skip decision uses what is saved.

    The rule itself lives in store_is_due_initial; this checks the wiring,
    because a store that is wrongly skipped disappears from the dashboard
    entirely until the window elapses.
    """

    @staticmethod
    def _write_config(path, store_id):
        path.write_text(
            "deduplication:\n"
            "  re_notify_on_deeper_discount: true\n"
            "weekly_menu:\n"
            "  enabled: false\n"
            "stores:\n"
            f"  - id: {store_id}\n"
            f"    name: {store_id.title()}\n"
            f"    url: https://{store_id}.test/\n"
            "    scraper: shopify\n"
            '    logo_url: ""\n',
            encoding="utf-8",
        )

    @staticmethod
    def _fake_scraper(menu):
        class FakeScraper:
            def __init__(self, store_config, config):
                self.store_config = store_config

            def fetch_menu(self):
                return menu

            def fetch_logo(self):
                return None

        return FakeScraper

    def _run(self, tmp_path, monkeypatch, store_id, menu, seed):
        import main
        from config import Config
        from main import DispoDeals

        self._write_config(tmp_path / "config.yaml", store_id)
        # main imports create_scraper by name, so the patch goes on main rather
        # than on the scrapers package it came from.
        monkeypatch.setattr(main, "create_scraper", self._fake_scraper(menu))

        app = DispoDeals.__new__(DispoDeals)
        app.config = Config.load(str(tmp_path / "config.yaml"))
        app.storage = SQLiteStorage(db_path=str(tmp_path / "s.db"))
        app.strain_resolver = None
        app.notifier = None
        app.running = True

        seed(app)
        app.run_once(initial_run=True)
        return app

    @staticmethod
    def _deal(store_id, product_id="p1", discount=30.0):
        from models import Deal

        return Deal(
            store_id=store_id, product_id=product_id, name="Product 1",
            category="Flower", original_price=50.0, sale_price=35.0,
            discount_pct=discount, image_url="", product_url="",
        )

    def test_empty_store_is_scraped_despite_a_recent_scrape(self, tmp_path, monkeypatch):
        menu = [self._deal("empty-store", "p1"), self._deal("empty-store", "p2")]

        def seed(app):
            # A scrape that recorded nothing still stamps the store as fresh.
            app.storage.set_store_last_scrape(
                "empty-store", datetime.now(timezone.utc)
            )
            assert app.storage.count_store_products("empty-store") == 0

        app = self._run(tmp_path, monkeypatch, "empty-store", menu, seed)

        # It was scraped rather than skipped, so the menu is now saved.
        assert app.storage.count_store_products("empty-store") == 2

    def test_populated_store_within_the_window_is_skipped(self, tmp_path, monkeypatch):
        # A menu the store would only have if it were scraped again.
        menu = [self._deal("full-store", "p9")]

        def seed(app):
            app.storage.set_store_last_scrape(
                "full-store", datetime.now(timezone.utc)
            )
            app.storage.save_seen_deal(self._deal("full-store", "p1"))

        app = self._run(tmp_path, monkeypatch, "full-store", menu, seed)

        # Skipped, so the seeded product stays and nothing new arrives.
        assert app.storage.count_store_products("full-store") == 1


class TestStorage:
    def test_roundtrip_and_default_none(self, tmp_path):
        storage = SQLiteStorage(db_path=str(tmp_path / "s.db"))
        assert storage.get_store_last_scrape("puffco") is None
        when = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        storage.set_store_last_scrape("puffco", when)
        got = storage.get_store_last_scrape("puffco")
        assert got is not None
        assert got.replace(tzinfo=None) == when.replace(tzinfo=None)
        # overwriting updates, not duplicates
        storage.set_store_last_scrape("puffco", when + timedelta(hours=1))
        got2 = storage.get_store_last_scrape("puffco")
        assert got2.replace(tzinfo=None) == (when + timedelta(hours=1)).replace(tzinfo=None)

    def test_stores_are_independent(self, tmp_path):
        storage = SQLiteStorage(db_path=str(tmp_path / "s.db"))
        when = datetime.now(timezone.utc)
        storage.set_store_last_scrape("a", when)
        assert storage.get_store_last_scrape("b") is None
