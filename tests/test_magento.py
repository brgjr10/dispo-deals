"""Magento storefront parsing, which is what Zumiez runs on.

The scraper reads the catalogue from Magento's GraphQL API rather than the
themed HTML, so these tests pin the deal conversion: a sale is ``regular_price``
above ``final_price``, a zero price means "no price reported" rather than a free
product, and the collection URL decides which category is read.
"""

import types

from scrapers.magento import MagentoScraper


class FakeConfig:
    class _Scrapers:
        magento = types.SimpleNamespace(timeout=5)

    scrapers = _Scrapers()


class FakeStore:
    id = "zumiez-420"
    name = "Zumiez 420"
    scraper = "magento"
    url = "https://www.zumiez.com/collections/weed.html"
    dispensary_id = None


def make_scraper(url="https://www.zumiez.com/collections/weed.html"):
    scraper = MagentoScraper.__new__(MagentoScraper)
    scraper.config = FakeConfig()
    scraper.store_config = FakeStore()
    if url is not None:
        scraper.store_config.url = url
    return scraper


def make_product(
    name="Ethika Boyshort",
    sku="us414459",
    url_key="ethika-boyshort",
    final=21.95,
    regular=21.95,
    in_stock=True,
):
    return {
        "name": name,
        "sku": sku,
        "url_key": url_key,
        "image": {"url": "https://scene7.zumiez.com/is/image/zumiez/boyshort.jpg"},
        "stock_status": "IN_STOCK" if in_stock else "OUT_OF_STOCK",
        "price_range": {
            "minimum_price": {
                "final_price": {"value": final},
                "regular_price": {"value": regular},
            }
        },
    }


class TestDealConversion:
    def test_full_price_product_has_no_discount(self):
        deal = make_scraper()._to_deal(make_product(), "https://www.zumiez.com")

        assert deal is not None
        assert deal.original_price == 21.95
        assert deal.sale_price == 21.95
        assert deal.discount_pct == 0.0

    def test_sale_price_becomes_a_discount(self):
        deal = make_scraper()._to_deal(
            make_product(final=10.0, regular=13.95), "https://www.zumiez.com"
        )

        assert deal.original_price == 13.95
        assert deal.sale_price == 10.0
        assert round(deal.discount_pct, 1) == 28.3

    def test_zero_price_is_skipped(self):
        """An out-of-stock variant reports 0, which would read as free."""
        deal = make_scraper()._to_deal(
            make_product(final=0, regular=13.95), "https://www.zumiez.com"
        )

        assert deal is None

    def test_stock_status_maps_to_in_stock(self):
        in_stock = make_scraper()._to_deal(make_product(in_stock=True), "https://x")
        out_of_stock = make_scraper()._to_deal(make_product(in_stock=False), "https://x")

        assert in_stock.in_stock is True
        assert out_of_stock.in_stock is False

    def test_product_url_keeps_the_html_suffix(self):
        deal = make_scraper()._to_deal(make_product(), "https://www.zumiez.com")

        assert deal.product_url == "https://www.zumiez.com/ethika-boyshort.html"

    def test_image_and_identity_are_taken_from_fields(self):
        deal = make_scraper()._to_deal(make_product(), "https://www.zumiez.com")

        assert deal.product_id == "us414459"
        assert deal.store_id == "zumiez-420"
        assert deal.image_url.endswith("boyshort.jpg")
        assert deal.category == "Accessories"


class TestExcludedTerms:
    """A skate shop's 420 collection mixes in candy-branded merch."""

    def test_candy_is_excluded_by_default(self):
        deal = make_scraper()._to_deal(make_product(name="Sour Candy Tee"), "https://x")

        assert deal is None

    def test_exclusion_matches_the_whole_word(self):
        """'Candyman' contains 'candy' but is a different product name."""
        deal = make_scraper()._to_deal(make_product(name="Candyman Socks"), "https://x")

        assert deal is not None

    def test_exclusion_is_case_insensitive(self):
        for spelling in ("CANDY", "Candy", "candy", "CANdy"):
            assert make_scraper()._to_deal(make_product(name=spelling), "https://x") is None

    def test_other_products_survive(self):
        deal = make_scraper()._to_deal(make_product(name="HUF Plantlife Socks"), "https://x")

        assert deal is not None

    def test_a_store_can_override_the_terms(self):
        store = types.SimpleNamespace(
            id="s", name="S", scraper="magento",
            url="https://www.zumiez.com/collections/weed.html",
            dispensary_id=None, exclude_terms=["socks"],
        )
        scraper = make_scraper()
        scraper.store_config = store

        assert scraper._to_deal(make_product(name="Crew Socks"), "https://x") is None
        assert scraper._to_deal(make_product(name="Sour Candy Tee"), "https://x") is not None

    def test_an_empty_list_disables_filtering(self):
        store = types.SimpleNamespace(
            id="s", name="S", scraper="magento",
            url="https://www.zumiez.com/collections/weed.html",
            dispensary_id=None, exclude_terms=[],
        )
        scraper = make_scraper()
        scraper.store_config = store

        assert scraper._to_deal(make_product(name="Sour Candy Tee"), "https://x") is not None


class TestCollectionUrlHandling:
    def test_search_term_drops_the_html_suffix(self):
        assert make_scraper()._search_term() == "weed"

    def test_search_term_uses_the_last_segment(self):
        scraper = make_scraper("https://www.zumiez.com/collections/420-collection.html")
        assert scraper._search_term() == "420-collection"

    def test_base_url_drops_path_and_query(self):
        scraper = make_scraper("https://www.zumiez.com/collections/weed.html?srsltid=abc")
        assert scraper._base_url() == "https://www.zumiez.com"

    def test_bare_domain_gets_a_scheme(self):
        scraper = make_scraper("www.zumiez.com/collections/weed.html")
        assert scraper._base_url() == "https://www.zumiez.com"
