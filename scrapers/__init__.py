import logging

from scrapers.base import BaseScraper
from scrapers.dutchie import DutchieScraper
from scrapers.magento import MagentoScraper
from scrapers.shopify import ShopifyScraper
from scrapers.shoplightspeed import ShoplightspeedScraper
from scrapers.sweed import SweedScraper
from scrapers.woocommerce import WooCommerceScraper
from models import StoreConfig
from config import Config

logger = logging.getLogger(__name__)

# bigcartel and fourthwall ship as untracked modules in some checkouts. Import
# them opportunistically so `import scrapers` never hard-fails on a clean
# clone; stores naming those scrapers then get a clear "Unknown scraper" error
# instead of a crash at import time.
try:
    from scrapers.bigcartel import BigCartelScraper  # noqa: F401
except ImportError as e:
    logger.warning(f"bigcartel scraper not available: {e}")
    BigCartelScraper = None
try:
    from scrapers.fourthwall import FourthwallScraper  # noqa: F401
except ImportError as e:
    logger.warning(f"fourthwall scraper not available: {e}")
    FourthwallScraper = None


__all__ = [
    "BaseScraper",
    "DutchieScraper",
    "MagentoScraper",
    "ShopifyScraper",
    "ShoplightspeedScraper",
    "SweedScraper",
    "WooCommerceScraper",
    "create_scraper",
]

if BigCartelScraper is not None:
    __all__.append("BigCartelScraper")
if FourthwallScraper is not None:
    __all__.append("FourthwallScraper")


def create_scraper(store_config: StoreConfig, config: Config) -> BaseScraper:
    """Instantiate the scraper a store config names.

    The registry is a dict rather than an if-chain so adding a source is one
    line, and an unknown name raises rather than falling back to a scraper that
    would silently read the wrong site.
    """
    scraper_classes = {
        "bigcartel": BigCartelScraper,
        "dutchie": DutchieScraper,
        "fourthwall": FourthwallScraper,
        "magento": MagentoScraper,
        "shopify": ShopifyScraper,
        "shoplightspeed": ShoplightspeedScraper,
        "sweed": SweedScraper,
        "woocommerce": WooCommerceScraper,
    }

    scraper_class = scraper_classes.get(store_config.scraper)
    if not scraper_class:
        raise ValueError(f"Unknown scraper: {store_config.scraper}")
    return scraper_class(store_config, config)
