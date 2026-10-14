"""The maintenance clear_store helper purges a store's products only."""

from datetime import date, timedelta

from maintenance.clear_store import clear_store
from models import Deal, WeeklySnapshot
from storage.sqlite import SQLiteStorage


def make_storage(tmp_path):
    return SQLiteStorage(db_path=str(tmp_path / "clear.db"))


def seed(storage, store_id, names):
    week = date.today() - timedelta(days=date.today().weekday())
    items = []
    for i, name in enumerate(names):
        deal = Deal(
            store_id=store_id,
            product_id=f"{store_id}-{i}",
            name=name,
            category="Apparel",
            original_price=20.0,
            sale_price=20.0,
            discount_pct=0.0,
            image_url="",
            product_url="",
        )
        storage.save_seen_deal(deal)
        items.append(deal)
    storage.save_weekly_snapshot(
        WeeklySnapshot(store_id=store_id, week_start=week, items=items)
    )


class TestClearStore:
    def test_purges_only_the_named_store(self, tmp_path):
        storage = make_storage(tmp_path)
        seed(storage, "zumiez-420", ["Sour Candy Tee", "Candy Skate Deck"])
        seed(storage, "cookies-sf", ["Cookies Hoodie"])

        before = storage.count_store_products("zumiez-420")
        assert before >= 1

        results = clear_store(storage, ["zumiez-420"])

        assert results["zumiez-420"] == (before, True)
        assert storage.count_store_products("zumiez-420") == 0
        # A different store is untouched.
        assert storage.count_store_products("cookies-sf") >= 1

    def test_reports_failure_without_raising(self, tmp_path, monkeypatch):
        storage = make_storage(tmp_path)

        def boom(store_id):
            raise RuntimeError("db down")

        monkeypatch.setattr(storage, "delete_store_data", boom)

        results = clear_store(storage, ["zumiez-420"])

        assert results["zumiez-420"][1] is False

    def test_multiple_store_ids(self, tmp_path):
        storage = make_storage(tmp_path)
        seed(storage, "a", ["x"])
        seed(storage, "b", ["y"])
        results = clear_store(storage, ["a", "b"])
        assert results["a"][1] is True and results["b"][1] is True
        assert storage.count_store_products("a") == 0
        assert storage.count_store_products("b") == 0
