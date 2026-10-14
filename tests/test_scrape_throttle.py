"""The per-store scrape-interval throttle: no re-fetch before the interval."""

from datetime import datetime, timedelta, timezone

from main import store_is_due
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
