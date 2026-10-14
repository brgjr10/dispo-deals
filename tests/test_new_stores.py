"""The stores added from the requested URLs, and the Dutchie custom domain.

Pure Ohio Wellness serves its menu from Dutchie behind its own domain, so the
dispensary id is configured explicitly: a cName like ``tallmadge`` is shared
across chains and could resolve the wrong store.
"""

import types

from config import Config
from models import StoreConfig
from scrapers.dutchie import DutchieScraper


class FakeConfig:
    class _Scrapers:
        dutchie = types.SimpleNamespace(timeout=5)

    scrapers = _Scrapers()


def make_dutchie_scraper(store):
    scraper = DutchieScraper.__new__(DutchieScraper)
    scraper.config = FakeConfig()
    scraper.store_config = store
    scraper.dispensary_slug = "tallmadge"
    scraper._dispensary_id = None
    return scraper


class TestDispensaryId:
    def test_configured_id_is_used_without_a_lookup(self):
        store = StoreConfig(
            id="pure-ohio-tallmadge",
            name="Pure Ohio Wellness — Tallmadge",
            url="https://pureohiowellness.com/stores/tallmadge",
            scraper="dutchie",
            logo_url="",
            dispensary_id="685b09c970977ec2ed6c2f92",
        )
        scraper = make_dutchie_scraper(store)

        # No resolver call is made, so a network failure cannot change the result.
        resolved = scraper._resolve_dispensary_id()

        assert resolved == "685b09c970977ec2ed6c2f92"

    def test_no_configured_id_falls_back_to_the_slug_lookup(self):
        store = StoreConfig(
            id="dutchie-canton-menu",
            name="Dutchie — Canton Menu",
            url="https://dutchie.com/dispensary/canton-menu",
            scraper="dutchie",
            logo_url="",
        )
        scraper = make_dutchie_scraper(store)

        calls = []
        scraper._graphql_request = lambda *a, **kw: calls.append(a) or None

        assert scraper._resolve_dispensary_id() is None
        assert calls, "expected the cName lookup to run"

    def test_store_config_parses_dispensary_id(self):
        store = StoreConfig.from_dict({
            "id": "x", "name": "X", "url": "https://x.test/",
            "scraper": "dutchie", "logo_url": "",
            "dispensary_id": "abc123",
        })

        assert store.dispensary_id == "abc123"


class TestAyrAkron:
    def test_embedded_menu_url_slugs_to_ayr_akron(self):
        store = StoreConfig(
            id="ayr-akron",
            name="AYR Ohio — Akron",
            url="https://dutchie.com/embedded-menu/ayr-akron",
            scraper="dutchie",
            logo_url="",
        )
        scraper = make_dutchie_scraper(store)

        assert scraper._extract_slug(store.url) == "ayr-akron"


class TestConfiguredStores:
    """Every store the run reads must be in config.yaml with a known scraper."""

    EXPECTED = {
        "push-trees": "shopify",
        "cookies-sf": "shopify",
        "ripndip": "shopify",
        "zumiez-420": "magento",
        "pure-ohio-tallmadge": "dutchie",
        "dutchie-akron-menu": "dutchie",
        "mothership-cannabis": "dutchie",
        "dutchie-canton-menu": "dutchie",
        "ayr-parma-heights": "dutchie",
        "daily-high-club": "shopify",
        "focus-v": "shopify",
        "calibear-glass": "shopify",
        "empire-smokes": "shopify",
        "tuff-tethers": "shopify",
        "the-dopest-shop": "shopify",
        "rove-brand": "shopify",
        "mothership-glass": "woocommerce",
        "illadelph-clothing": "woocommerce",
        "curaleaf-cuyahoga-falls": "sweed",
        "ayr-akron": "dutchie",
    }

    def _stores(self):
        return {s.id: s for s in Config.load("config.yaml").stores}

    def test_new_stores_are_configured(self):
        stores = self._stores()
        for store_id, scraper in self.EXPECTED.items():
            assert store_id in stores, f"{store_id} is missing from config.yaml"
            assert stores[store_id].scraper == scraper

    def test_new_stores_are_enabled_by_default(self):
        stores = self._stores()
        for store_id in self.EXPECTED:
            assert stores[store_id].enabled is True

    def test_pure_ohio_carries_its_dispensary_id(self):
        stores = self._stores()
        assert stores["pure-ohio-tallmadge"].dispensary_id == "685b09c970977ec2ed6c2f92"

    def test_every_store_has_a_unique_id(self):
        ids = [s.id for s in Config.load("config.yaml").stores]
        assert len(ids) == len(set(ids))
