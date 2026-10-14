"""The Sweed POS shop API parser, driven from a fake product payload."""

import types

from models import StoreConfig
from scrapers.sweed import SweedScraper


def make_scraper():
    store = StoreConfig(
        id="curaleaf-cuyahoga-falls",
        name="Curaleaf — Cuyahoga Falls",
        url="https://oh.curaleaf.com/shop/ohio/curaleaf-cuyahoga-falls/recreational",
        scraper="sweed",
        logo_url="",
        scraper_options={
            "api_host": "https://web-ui-curaleaf.sweedpos.com",
            "storeid": "142",
            "sale_type": "Recreational",
        },
    )
    scraper = SweedScraper.__new__(SweedScraper)
    scraper.store_config = store
    scraper.store_id = "142"
    scraper.sale_type = "Recreational"
    scraper.api_base = "https://web-ui-curaleaf.sweedpos.com"
    return scraper


def product(**overrides):
    base = {
        "id": 36840,
        "name": "Miracle Mintz",
        "category": {"id": 690, "name": "Flower", "canonicalName": "flower"},
        "subcategory": {"id": 709, "name": "Small Buds", "canonicalName": "small-buds"},
        "images": ["https://media.sweedpos.com/x.png"],
        "brand": {"name": "Grassroots"},
        "variants": [
            {
                "id": 168398,
                "name": "14g",
                "images": ["https://media.sweedpos.com/v.avif"],
                "price": 125.0,
                "promoPrice": 100.0,
                "availableQty": 83.0,
                "labTests": {"thc": {"value": [25.5926]}},
            }
        ],
    }
    base.update(overrides)
    return base


class TestParse:
    def test_shelf_and_subcategory_from_source(self):
        deal = make_scraper()._to_deal(product())
        assert deal.category == "Flower \u00b7 small buds"
        assert deal.brand == "Grassroots"
        assert deal.thc_pct == 25.5926

    def test_promo_price_is_the_sale(self):
        deal = make_scraper()._to_deal(product())
        assert deal.original_price == 125.0
        assert deal.sale_price == 100.0
        assert deal.discount_pct == 20.0
        assert deal.is_deal is True

    def test_no_promo_means_no_discount(self):
        p = product()
        p["variants"][0]["promoPrice"] = None
        deal = make_scraper()._to_deal(p)
        assert deal.sale_price == 125.0
        assert deal.original_price == 125.0
        assert deal.discount_pct == 0.0

    def test_out_of_stock_variant_falls_back_to_priced(self):
        p = product()
        p["variants"][0]["availableQty"] = 0
        deal = make_scraper()._to_deal(p)
        assert deal.in_stock is False
        assert deal.sale_price == 100.0

    def test_prefers_an_in_stock_variant(self):
        p = product()
        p["variants"] = [
            {"id": 1, "name": "3.5g", "price": 40.0, "promoPrice": 40.0, "availableQty": 0},
            {"id": 2, "name": "14g", "price": 120.0, "promoPrice": 90.0, "availableQty": 5},
        ]
        deal = make_scraper()._to_deal(p)
        assert deal.sale_price == 90.0
        assert deal.in_stock is True

    def test_product_url_uses_category_and_variant(self):
        deal = make_scraper()._to_deal(product())
        assert deal.product_id == "36840"
        assert deal.product_url.endswith("/menu/flower-690/miracle-mintz-168398")

    def test_missing_category_falls_back_to_name(self):
        p = product(category={}, subcategory={})
        deal = make_scraper()._to_deal(p)
        # No shelf on the source -> canonical_category_named keeps it unnamed
        # rather than inventing one for a strain-named product.
        assert deal.name == "Miracle Mintz"

    def test_variant_selection_helper(self):
        scraper = make_scraper()
        vs = [
            {"price": 0, "availableQty": 0},
            {"price": 40.0, "availableQty": 3},
            {"price": 120.0, "availableQty": 5},
        ]
        assert scraper._choose_variant(vs)["price"] == 40.0
        assert SweedScraper._choose_variant([{"price": 50.0, "availableQty": 0}])["price"] == 50.0
        assert SweedScraper._choose_variant([{"price": 0}]) is None
