"""The WooCommerce Store API parser, parsed from a fake product payload."""

from models import StoreConfig
from scrapers.woocommerce import WooCommerceScraper


def make_scraper():
    scraper = WooCommerceScraper.__new__(WooCommerceScraper)
    scraper.store_config = StoreConfig(
        id="mothership-glass",
        name="Mothership Glass",
        url="https://mothershipglass.com/shop/",
        scraper="woocommerce",
        logo_url="",
    )
    return scraper


def sample_product(**overrides):
    product = {
        "id": 197739,
        "name": "2 Adapters &#8211; Eclipse",
        "permalink": "https://mothershipglass.com/product/x/",
        "on_sale": False,
        "is_in_stock": True,
        "prices": {"price": "50000", "regular_price": "50000", "currency_minor_unit": 2},
        "images": [{"src": "https://mothershipglass.com/img.jpg"}],
        "categories": [{"name": "Direct Sale"}],
        "brands": [{"name": "Mothership"}],
    }
    product.update(overrides)
    return product


class TestParse:
    def test_basic_deal(self):
        deal = make_scraper()._to_deal(sample_product())
        assert deal is not None
        assert deal.store_id == "mothership-glass"
        # Names arrive HTML-escaped from the Store API.
        assert deal.name == "2 Adapters \u2013 Eclipse"
        # Prices are minor units: 50000 / 10**2.
        assert deal.sale_price == 500.0
        assert deal.original_price == 500.0
        assert deal.discount_pct == 0.0
        assert deal.brand == "Mothership"
        assert deal.in_stock is True
        assert deal.image_url == "https://mothershipglass.com/img.jpg"
        assert deal.product_id == "197739"

    def test_sale_sets_discount(self):
        product = sample_product(
            on_sale=True,
            prices={"price": "40000", "regular_price": "50000", "currency_minor_unit": 2},
        )
        deal = make_scraper()._to_deal(product)
        assert deal.sale_price == 400.0
        assert deal.original_price == 500.0
        assert deal.discount_pct == 20.0

    def test_not_on_sale_ignores_higher_regular(self):
        # A regular price with on_sale false must not fabricate a discount.
        product = sample_product(
            on_sale=False,
            prices={"price": "45000", "regular_price": "50000", "currency_minor_unit": 2},
        )
        deal = make_scraper()._to_deal(product)
        assert deal.sale_price == 450.0
        assert deal.original_price == 450.0
        assert deal.discount_pct == 0.0

    def test_zero_price_is_skipped(self):
        product = sample_product(
            prices={"price": "0", "regular_price": "0", "currency_minor_unit": 2}
        )
        assert make_scraper()._to_deal(product) is None

    def test_subcategory_inferred_from_title(self):
        product = sample_product(
            name="Fine Grid Herb Grinder",
            categories=[{"name": "Accessories"}],
        )
        deal = make_scraper()._to_deal(product)
        assert deal.category.startswith("Accessories")
        assert deal.category.endswith("grinders")

    def test_empty_categories_fall_back_to_accessories(self):
        product = sample_product(categories=[], name="Mystery Widget")
        deal = make_scraper()._to_deal(product)
        assert deal.category == "Accessories"
