"""The WooCommerce Store API parser, parsed from a fake product payload."""

import pytest

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


SHOP_HTML = """
<ul class="products columns-3">
  <li class="product type-product post-1713 status-publish instock product_cat-accessories product_cat-hemp-grinder has-post-thumbnail">
    <a href="https://illadelphclothing.com/product/grinder-3pc/" class="woocommerce-LoopProduct-link woocommerce-loop-product__link">
      <img width="324" height="324" src="https://illadelphclothing.com/thumb.png" class="attachment-woocommerce_thumbnail">
      <h2 class="woocommerce-loop-product__title">Shredder Grinder 3pc</h2>
      <span class="price"><span class="woocommerce-Price-amount amount"><bdi><span class="woocommerce-Price-currencySymbol">&#36;</span>45.00</bdi></span></span>
    </a>
  </li>
  <li class="product type-product post-1720 status-publish outofstock product_cat-accessories">
    <a href="https://illadelphclothing.com/product/tee/" class="woocommerce-LoopProduct-link woocommerce-loop-product__link">
      <h2 class="woocommerce-loop-product__title">Logo Tee</h2>
      <span class="price"><del aria-hidden="true"><span class="woocommerce-Price-amount amount"><bdi><span class="woocommerce-Price-currencySymbol">&#36;</span>30.00</bdi></span></del><ins><span class="woocommerce-Price-amount amount"><bdi><span class="woocommerce-Price-currencySymbol">&#36;</span>20.00</bdi></span></ins></span>
    </a>
  </li>
</ul>
"""


class TestHtmlFallback:
    """When the Store API is disabled, the /shop/ loop is parsed instead."""

    def test_parses_product_cards(self):
        deals = make_scraper()._parse_html(SHOP_HTML, "https://illadelphclothing.com/shop")
        assert [d.name for d in deals] == ["Shredder Grinder 3pc", "Logo Tee"]
        assert [d.product_id for d in deals] == ["1713", "1720"]

    def test_plain_price_has_no_discount(self):
        deals = make_scraper()._parse_html(SHOP_HTML, "x")
        grinder = deals[0]
        assert grinder.sale_price == 45.0
        assert grinder.original_price == 45.0
        assert grinder.discount_pct == 0.0
        assert grinder.in_stock is True

    def test_sale_card_reports_discount_and_stock(self):
        deals = make_scraper()._parse_html(SHOP_HTML, "x")
        tee = deals[1]
        assert tee.sale_price == 20.0
        assert tee.original_price == 30.0
        assert tee.discount_pct == 33.3
        assert tee.in_stock is False

    def test_known_category_wins_and_title_infers_subcategory(self):
        # product_cat-accessories + product_cat-hemp-grinder: the known shelf
        # (Accessories) wins, and the title adds the subcategory.
        deals = make_scraper()._parse_html(SHOP_HTML, "x")
        assert deals[0].category.startswith("Accessories")
        assert deals[0].category.endswith("grinders")

    def test_range_price_uses_min_without_discount(self):
        html = """<li class="product post-1 instock product_cat-accessories">
          <a href="https://x/p/" class="woocommerce-loop-product__link">
            <h2 class="woocommerce-loop-product__title">Variable Thing</h2>
            <span class="price"><span class="woocommerce-Price-amount amount"><bdi>10.00</bdi></span> &ndash;
            <span class="woocommerce-Price-amount amount"><bdi>25.00</bdi></span></span>
          </a></li>"""
        deals = make_scraper()._parse_html(html, "x")
        assert len(deals) == 1
        assert deals[0].sale_price == 10.0
        assert deals[0].original_price == 10.0
        assert deals[0].discount_pct == 0.0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
