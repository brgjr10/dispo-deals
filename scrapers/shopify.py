"""A Shopify storefront, read through its products.json endpoint.

Several of the accessory and brand sources run on Shopify, and Shopify publishes
its catalogue as JSON at /products.json. Reading that instead of parsing the
storefront's HTML means the name, price, image and stock are taken from fields
rather than scraped out of markup, so a theme change cannot break the scrape.
"""

import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from scrapers.base import BaseScraper
from models import Deal, StoreConfig
from config import Config
from utils.categories import canonical_category

logger = logging.getLogger(__name__)


class ShopifyScraper(BaseScraper):
    PER_PAGE = 250
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
                f"Shopify page {page}: {len(batch)} products for {self.store_config.name}"
            )
            # A short page means the catalogue ended, so there is no page after it.
            if len(batch) < self.PER_PAGE:
                break
            page += 1

        logger.info(
            f"Shopify fetch complete: {len(deals)} products for {self.store_config.name}"
        )
        return deals

    def _fetch_page(self, base: str, page: int) -> List[Deal]:
        url = f"{base}/products.json?limit={self.PER_PAGE}&page={page}"
        response = self._make_request("GET", url)
        if not response:
            return []
        try:
            payload = response.json()
        except ValueError:
            logger.warning(f"Shopify returned non-JSON for {url}")
            return []

        deals = []
        for product in payload.get("products") or []:
            deal = self._to_deal(product, base)
            if deal:
                deals.append(deal)
        return deals

    def _to_deal(self, product: Dict[str, Any], base: str) -> Optional[Deal]:
        """Turn one Shopify product record into a Deal.

        The first variant is the product's own price. A sale is signalled by
        compare_at_price being set and higher than price, which is Shopify's own
        convention for "was / now".
        """
        variants = product.get("variants") or []
        variant = variants[0] if variants else {}

        price = _money(variant.get("price"))
        compare_at = _money(variant.get("compare_at_price"))
        if price <= 0:
            return None

        on_sale = compare_at > price
        original = compare_at if on_sale else price
        sale = price if on_sale else price

        images = product.get("images") or []
        image_url = images[0].get("src", "") if images else ""

        handle = product.get("handle") or ""
        # A Shopify product_type is a free-text field the merchant fills in, and
        # most of these catalogues leave it blank. An empty category would show
        # up as a nameless row in the sidebar, so a blank one lands on the shelf
        # these sources belong to.
        product_type = (product.get("product_type") or "").strip() or "Accessories"
        return Deal(
            store_id=self.store_config.id,
            product_id=str(product.get("id") or handle),
            name=(product.get("title") or "").strip(),
            category=canonical_category(
                product_type, name=(product.get("title") or "").strip()
            ),
            original_price=original,
            sale_price=sale,
            discount_pct=0.0,
            image_url=image_url,
            product_url=f"{base}/products/{handle}" if handle else base,
            in_stock=bool(variant.get("available", True)),
            weight=(variant.get("title") or "").strip(),
            brand=(product.get("vendor") or "").strip(),
        )

    def fetch_logo(self) -> Optional[bytes]:
        """Fetch the storefront's logo.

        Most Shopify themes publish one at a predictable location, but not all
        do, so the homepage is scraped for a likely logo image and any failure is
        treated as "no logo" rather than an error.
        """
        base = self._base_url()
        response = self._make_request("GET", base)
        if not response:
            return None

        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(response.text, "html.parser")
        except Exception:
            return None

        for candidate in self._logo_candidates(soup, base):
            fetched = self._make_request("GET", candidate)
            if fetched and fetched.content:
                return fetched.content
        return None

    @staticmethod
    def _logo_candidates(soup, base: str) -> List[str]:
        """Likely logo URLs in the order they should be tried."""
        from urllib.parse import urljoin

        candidates = []
        for selector in (
            "img.header__logo-image",
            "img.site-header__logo img",
            "img[class*='logo']",
            "a.site-header__logo-image[href*='.png']",
        ):
            for img in soup.select(selector)[:2]:
                src = img.get("src") or img.get("data-src")
                if src:
                    candidates.append(urljoin(base, src))

        if not candidates:
            meta = soup.find("meta", property="og:image")
            if meta and meta.get("content"):
                candidates.append(urljoin(base, meta["content"]))
        return candidates

    def _base_url(self) -> str:
        """The store root, with any path or query removed.

        A configured URL may point at a collection page, but products.json only
        exists at the domain root.
        """
        raw = (self.store_config.url or "").strip()
        if not raw:
            return ""
        if "://" not in raw:
            raw = f"https://{raw}"
        parsed = urlparse(raw)
        return f"{parsed.scheme}://{parsed.netloc}"


def _money(value: Any) -> float:
    """Parse a Shopify price, which arrives as a string such as '12.50'."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return 0.0


def create_scraper(store_config: StoreConfig, config: Config) -> BaseScraper:
    return ShopifyScraper(store_config, config)
