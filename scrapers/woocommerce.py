"""A WooCommerce storefront, read through its Store API.

Illadelph and Mothership Glass run on WooCommerce, which publishes a public,
keyless REST endpoint at /wp-json/wc/store/v1/products (the "Store API"). It is
the same idea as a Shopify storefront's /products.json: name, price, image,
stock and category come from fields rather than scraped out of markup, so a
theme change cannot break the scrape. Prices arrive in minor units (cents)
scaled by the store's currency_minor_unit, and a sale is signalled by the
``on_sale`` flag with a higher ``regular_price``.
"""

import html
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from scrapers.base import BaseScraper
from models import Deal, StoreConfig
from config import Config
from utils.categories import canonical_category_named

logger = logging.getLogger(__name__)

PAGE_SIZE = 100


class WooCommerceScraper(BaseScraper):
    MAX_PAGES = 20

    def fetch_menu(self) -> List[Deal]:
        base = self._base_url()
        deals: List[Deal] = []
        page = 1

        while page <= self.MAX_PAGES:
            batch = self._fetch_page(base, page)
            if not batch:
                break
            deals.extend(batch)
            logger.debug(
                f"WooCommerce page {page}: {len(batch)} products for {self.store_config.name}"
            )
            # A short page means the catalogue ended, so there is no page after it.
            if len(batch) < PAGE_SIZE:
                break
            page += 1

        logger.info(
            f"WooCommerce fetch complete: {len(deals)} products for {self.store_config.name}"
        )
        return deals

    def _base_url(self) -> str:
        """The store root, with any path or query removed.

        A configured URL may point at a shop page, but the Store API only lives
        at the domain root.
        """
        raw = (self.store_config.url or "").strip()
        if not raw:
            return ""
        if "://" not in raw:
            raw = f"https://{raw}"
        parsed = urlparse(raw)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _fetch_page(self, base: str, page: int) -> List[Deal]:
        url = f"{base}/wp-json/wc/store/v1/products?per_page={PAGE_SIZE}&page={page}&orderby=date&order=desc"
        response = self._make_request("GET", url)
        if not response:
            return []
        try:
            payload = response.json()
        except ValueError:
            logger.warning(f"WooCommerce returned non-JSON for {url}")
            return []

        deals = []
        for product in payload if isinstance(payload, list) else []:
            deal = self._to_deal(product)
            if deal:
                deals.append(deal)
        return deals

    def _to_deal(self, product: Dict[str, Any]) -> Optional[Deal]:
        """Turn one Store API product into a Deal.

        Prices are minor units (cents) scaled by the store's minor unit, and a
        sale is ``on_sale`` with a strictly higher ``regular_price``.
        """
        prices = product.get("prices") or {}
        minor = prices.get("currency_minor_unit")
        minor = int(minor) if isinstance(minor, int) and 0 <= minor <= 4 else 2
        divisor = 10 ** minor

        def money(key: str) -> float:
            raw = prices.get(key)
            if raw in (None, ""):
                return 0.0
            try:
                return int(str(raw)) / divisor
            except (TypeError, ValueError):
                return 0.0

        price = money("price")
        regular = money("regular_price")
        if price <= 0:
            return None

        on_sale = bool(product.get("on_sale")) and regular > price
        original = regular if on_sale else price
        sale = price

        images = product.get("images") or []
        image_url = images[0].get("src", "") if images else ""

        categories = product.get("categories") or []
        category_name = html.unescape(categories[0].get("name", "")) if categories else ""
        category_name = category_name.strip() or "Accessories"

        brands = product.get("brands") or []
        vendor = html.unescape(brands[0].get("name", "")) if brands else ""

        name = html.unescape((product.get("name") or "").strip())

        return Deal(
            store_id=self.store_config.id,
            product_id=str(product.get("id") or ""),
            name=name,
            # The title is passed so a product with no useful category shelf
            # still lands on the right one via its name.
            category=canonical_category_named(category_name, name),
            original_price=original,
            sale_price=sale,
            discount_pct=0.0,
            image_url=image_url,
            product_url=product.get("permalink") or self._base_url(),
            in_stock=bool(product.get("is_in_stock", True)),
            weight="",
            brand=vendor,
        )


    def fetch_logo(self) -> Optional[bytes]:
        """Return the configured logo, if the store has one.

        WooCommerce themes publish a logo in many places, and none of these
        brand sources configure one, so a missing logo is "no logo" rather than
        a hunt through the markup.
        """
        configured = self.store_config.logo_url
        if not configured:
            return None
        response = self._make_request("GET", configured)
        return response.content if response and response.content else None


def create_scraper(store_config: StoreConfig, config: Config) -> BaseScraper:
    return WooCommerceScraper(store_config, config)
