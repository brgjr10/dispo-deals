"""Scraper/notifier behaviour for capturing a store's full menu.

The menu is meant to hold every product a store carries, not only its sales, so
these tests pin both halves of that contract: the scraper keeps undiscounted
products, and the notifier is never fed them.
"""

import types

from models import Deal
from scrapers.dutchie import DutchieScraper
from storage.sqlite import SQLiteStorage
from main import DispoDeals


class FakeConfig:
    class _Scrapers:
        dutchie = types.SimpleNamespace(timeout=5)

    class _Dedup:
        re_notify_on_deeper_discount = True

    scrapers = _Scrapers()
    deduplication = _Dedup()


class FakeStore:
    id = "test-store"
    name = "Test Store"
    scraper = "dutchie"
    slug = "test-store"


def make_scraper():
    scraper = DutchieScraper.__new__(DutchieScraper)
    scraper.config = FakeConfig()
    scraper.store_config = FakeStore()
    scraper.dispensary_slug = "test-store"
    scraper.graphql_endpoints = []
    scraper.graphql_session = None
    return scraper


class TestDutchieFullMenuCapture:
    """Undiscounted products must survive parsing as zero-discount entries."""

    def test_product_without_special_price_is_kept(self):
        scraper = make_scraper()
        product = {
            "Name": "Blue Dream",
            "id": "prod-1",
            "recPrices": [45.0],
            "recSpecialPrices": [],
        }

        deal = scraper._parse_dutchie_product(product)

        assert deal is not None
        assert deal.original_price == 45.0
        assert deal.sale_price == 45.0
        assert deal.discount_pct == 0.0
        assert deal.is_deal is False

    def test_product_without_special_price_uses_first_variant(self):
        scraper = make_scraper()
        product = {
            "Name": "Blue Dream",
            "id": "prod-1",
            "recPrices": [45.0, 12.0],
            "recSpecialPrices": [],
        }

        deal = scraper._parse_dutchie_product(product)

        # The first reported variant is the representative price.
        assert deal.original_price == 45.0
        assert deal.discount_pct == 0.0
        assert deal.is_deal is False

    def test_special_price_list_of_zeros_is_kept(self):
        """A present-but-zero special price must not block the product."""
        scraper = make_scraper()
        product = {
            "Name": "Blue Dream",
            "id": "prod-1",
            "recPrices": [45.0],
            "recSpecialPrices": [0.0],
        }

        deal = scraper._parse_dutchie_product(product)

        assert deal is not None
        assert deal.discount_pct == 0.0
        assert deal.is_deal is False

    def test_real_deal_is_still_parsed(self):
        scraper = make_scraper()
        product = {
            "Name": "Slurricane",
            "id": "prod-2",
            "recPrices": [50.0],
            "recSpecialPrices": [35.0],
        }

        deal = scraper._parse_dutchie_product(product)

        assert deal.original_price == 50.0
        assert deal.sale_price == 35.0
        assert deal.discount_pct == 30.0
        assert deal.is_deal is True

    def test_equal_special_price_is_not_a_deal(self):
        scraper = make_scraper()
        product = {
            "Name": "Blue Dream",
            "id": "prod-1",
            "recPrices": [45.0],
            "recSpecialPrices": [45.0],
        }

        deal = scraper._parse_dutchie_product(product)

        assert deal is not None
        assert deal.is_deal is False

    def test_nameless_and_unpriced_products_are_dropped(self):
        scraper = make_scraper()
        assert scraper._parse_dutchie_product({"recPrices": [45.0]}) is None
        assert scraper._parse_dutchie_product({"Name": "Blue Dream", "recPrices": []}) is None


class TestNotificationOnlyForDeals:
    """Full-price stock must never reach the webhook."""

    @staticmethod
    def _deals(tmp_path):
        # A full-priced product: same original and sale price, zero discount.
        # Passing a lower sale price with 0% would be contradictory, and the
        # model derives the discount from the prices in that case.
        return [
            Deal(store_id="s", product_id="1", name="Blue Dream", category="Flower",
                 original_price=45.0, sale_price=45.0, discount_pct=0.0,
                 image_url="", product_url=""),
            Deal(store_id="s", product_id="2", name="Northern Lights", category="Flower",
                 original_price=45.0, sale_price=35.0, discount_pct=25.0,
                 image_url="", product_url=""),
        ]

    def test_only_deals_are_reported(self, tmp_path):
        app = DispoDeals.__new__(DispoDeals)
        app.storage = SQLiteStorage(db_path=str(tmp_path / "menu.db"))

        class _Cfg:
            class deduplication:
                re_notify_on_deeper_discount = True

        app.config = _Cfg()

        reported = app._process_deals(FakeStore(), self._deals(tmp_path))

        assert len(reported) == 1
        assert reported[0].is_deal is True
        assert reported[0].name == "Northern Lights"

    def test_full_catalogue_is_still_persisted(self, tmp_path):
        app = DispoDeals.__new__(DispoDeals)
        app.storage = SQLiteStorage(db_path=str(tmp_path / "menu.db"))

        class _Cfg:
            class deduplication:
                re_deepen = True
                re_notify_on_deeper_discount = True

        app.config = _Cfg()

        app._process_deals(FakeStore(), self._deals(tmp_path))

        stored = app.storage.get_all_seen_deals()
        assert len(stored) == 2

    def test_deal_stock_only_is_unchanged(self, tmp_path):
        """A store selling nothing at a discount reports nothing."""
        app = DispoDeals.__new__(DispoDeals)
        app.storage = SQLiteStorage(db_path=str(tmp_path / "menu.db"))

        class _Cfg:
            class deduplication:
                re_notify_on_deeper_discount = True

        app.config = _Cfg()
        full_price = [
            Deal(store_id="s", product_id="1", name="Blue Dream", category="Flower",
                 original_price=45.0, sale_price=45.0, discount_pct=0.0,
                 image_url="", product_url=""),
        ]

        assert app._process_deals(FakeStore(), full_price) == []

    def test_weekly_snapshot_holds_full_menu(self, tmp_path):
        """`_save_weekly_snapshot` must persist deals and full-price items."""
        import datetime

        app = DispoDeals.__new__(DispoDeals)
        app.storage = SQLiteStorage(db_path=str(tmp_path / "menu.db"))

        class _Cfg:
            class weekly_menu:
                min_items_for_snapshot = 10

            deduplication = None

        app.config = _Cfg()

        app._save_weekly_snapshot(FakeStore(), self._deals(tmp_path))

        snapshot = app.storage.get_weekly_snapshot(
            "test-store",
            datetime.date.today() - datetime.timedelta(days=datetime.date.today().weekday()),
        )
        assert len(snapshot.items) == 2


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
