from scrapers.base import BaseScraper
from scrapers.dutchie import DutchieScraper
from scrapers.magento import MagentoScraper
from scrapers.shopify import ShopifyScraper
from scrapers.shoplightspeed import ShoplightspeedScraper
from models import StoreConfig
from config import Config


__all__ = [
    "BaseScraper",
    "DutchieScraper",
    "MagentoScraper",
    "ShopifyScraper",
    "ShoplightspeedScraper",
    "create_scraper",
]


def create_scraper(store_config: StoreConfig, config: Config) -> BaseScraper:
    """Instantiate the scraper a store config names.

    The registry is a dict rather than an if-chain so adding a source is one
    line, and an unknown name raises rather than falling back to a scraper that
    would silently read the wrong site.
    """
    scraper_classes = {
        "dutchie": DutchieScraper,
        "magento": MagentoScraper,
        "shopify": ShopifyScraper,
        "shoplightspeed": ShoplightspeedScraper,
    }

    scraper_class = scraper_classes.get(store_config.scraper)
    if not scraper_class:
        raise ValueError(f"Unknown scraper: {store_config.scraper}")
    return scraper_class(store_config, config)
