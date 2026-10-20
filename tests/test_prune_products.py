"""Pruning stale products after a scrape.

When a store's menu changes, old listings that are no longer carried should be
removed from the dashboard. The prune is guarded by ``PRUNE_MIN_MENU_RATIO`` so a
scraper timeout or Cloudflare block — which would return an empty or partial
menu — does not wipe the whole catalogue.
"""

import pytest

from models import Deal
from storage.sqlite import SQLiteStorage, PRUNE_MIN_MENU_RATIO


def make_deal(store_id, product_id, name="Product", sale_price=35.0):
    return Deal(
        store_id=store_id,
        product_id=product_id,
        name=name,
        category="Flower",
        original_price=50.0,
        sale_price=sale_price,
        discount_pct=0.0,
        image_url="",
        product_url="",
    )


@pytest.fixture
def storage(tmp_path):
    return SQLiteStorage(db_path=str(tmp_path / "prune.db"))


class TestPruneConstant:
    def test_ratio_is_half(self):
        assert PRUNE_MIN_MENU_RATIO == 0.5


class TestPruneRemovesStaleProducts:
    def test_disappeared_product_is_removed(self, storage):
        storage.save_seen_deal(make_deal("store-1", "p1", "Blue Dream"))
        storage.save_seen_deal(make_deal("store-1", "p2", "GMO Cookies"))

        still_seen = make_deal("store-1", "p2", "GMO Cookies")
        pruned = storage.prune_missing_products("store-1", [still_seen.hash])
        assert pruned == 1
        assert storage.count_store_products("store-1") == 1

    def test_kept_products_are_not_touched(self, storage):
        storage.save_seen_deal(make_deal("store-1", "p1", "Blue Dream"))
        storage.save_seen_deal(make_deal("store-1", "p2", "GMO Cookies"))

        hashes = [
            make_deal("store-1", "p1", "Blue Dream").hash,
            make_deal("store-1", "p2", "GMO Cookies").hash,
        ]
        pruned = storage.prune_missing_products("store-1", hashes)
        assert pruned == 0
        assert storage.count_store_products("store-1") == 2

    def test_price_change_creates_new_listing(self, storage):
        storage.save_seen_deal(make_deal("store-1", "p1", sale_price=35.0))

        new_deal = make_deal("store-1", "p1", sale_price=30.0)
        storage.save_seen_deal(new_deal)

        pruned = storage.prune_missing_products("store-1", [new_deal.hash])
        assert pruned == 1

        remaining = storage.get_seen_deal(new_deal.hash)
        assert remaining is not None




class TestPruneSkipsOnSmallMenu:
    def test_empty_hashes_does_nothing(self, storage):
        storage.save_seen_deal(make_deal("store-1", "p1"))

        pruned = storage.prune_missing_products("store-1", [])
        assert pruned == 0
        assert storage.count_store_products("store-1") == 1

    def test_menu_below_threshold_is_not_pruned(self, storage):
        for i in range(10):
            storage.save_seen_deal(make_deal("store-1", f"p{i}", f"Strain {i}"))

        # New scrape has 3 items (30% of 10) — below the 50% guard.
        small_hashes = [make_deal("store-1", f"p{i}", f"Strain {i}").hash for i in range(3)]
        pruned = storage.prune_missing_products("store-1", small_hashes)
        assert pruned == 0
        assert storage.count_store_products("store-1") == 10

    def test_menu_at_threshold_is_pruned(self, storage):
        for i in range(10):
            storage.save_seen_deal(make_deal("store-1", f"p{i}", f"Strain {i}"))

        # Exactly 50% of the existing products — boundary passes.
        half_hashes = [make_deal("store-1", f"p{i}", f"Strain {i}").hash for i in range(5)]
        pruned = storage.prune_missing_products("store-1", half_hashes)
        assert pruned == 5
        assert storage.count_store_products("store-1") == 5

    def test_no_existing_products_does_not_trigger_guard(self, storage):
        new_hashes = [make_deal("store-1", "p1").hash]
        pruned = storage.prune_missing_products("store-1", new_hashes)
        assert pruned == 0


class TestPruneScope:
    def test_only_the_specified_store_is_affected(self, storage):
        storage.save_seen_deal(make_deal("store-1", "p1", "Store1 Product"))
        storage.save_seen_deal(make_deal("store-2", "p1", "Store2 Product"))

        pruned = storage.prune_missing_products("store-1", [])
        assert pruned == 0
        assert storage.count_store_products("store-1") == 1
        assert storage.count_store_products("store-2") == 1

    def test_pruning_one_store_does_not_see_other_store_hashes(self, storage):
        storage.save_seen_deal(make_deal("store-1", "p1", "Blue Dream"))
        storage.save_seen_deal(make_deal("store-2", "p2", "GMO Cookies"))

        hashes = [make_deal("store-1", "p1", "Blue Dream").hash]
        pruned = storage.prune_missing_products("store-1", hashes)
        assert pruned == 0
        assert storage.count_store_products("store-1") == 1
        assert storage.count_store_products("store-2") == 1
