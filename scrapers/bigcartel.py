"""BigCartel storefront, read through its products.json endpoint.

BigCartel publishes its catalogue as JSON at /products.json (returns a list directly,
not an object with a "products" key like Shopify). This scraper mirrors the Shopify
one but handles the different response format.
"""

import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urljoin

from scrapers.base import BaseScraper
from models import Deal, StoreConfig
from config import Config
from utils.categories import canonical_category

logger = logging.getLogger(__name__)


class BigCartelScraper(BaseScraper):
    PER_PAGE = 100
    MAX_PAGES = 10

    def fetch_menu(self) -> List[Deal]:
        base = self._base_url()
        deals: List[Deal] = []

        # BigCartel returns all products in a single list at /products.json
        url = f"{base}/products.json"
        response = self._make_request("GET", url)
        if not response:
            return []

        try:
            products = response.json()
        except ValueError:
            logger.warning(f"BigCartel returned non-JSON for {url}")
            return []

        if not isinstance(products, list):
            logger.warning(f"BigCartel products.json is not a list for {url}")
            return []

        for product in products:
            deal = self._to_deal(product, base)
            if deal:
                deals.append(deal)

        logger.info(f"BigCartel fetch complete: {len(deals)} products for {self.store_config.name}")
        return deals

    def _to_deal(self, product: Dict[str, Any], base: str) -> Optional[Deal]:
        """Turn one BigCartel product record into a Deal."""
        name = (product.get("name") or "").strip()
        if not name:
            return None

        price = _money(product.get("price"))
        default_price = _money(product.get("default_price"))
        on_sale = product.get("on_sale", False)
        if default_price > price and default_price > 0:
            on_sale = True

        original = default_price if on_sale and default_price > price else price
        sale = price

        images = product.get("images") or []
        image_url = images[0].get("url", "") if images else ""

        # Use the url field which includes /product/ prefix, fallback to permalink
        product_url = product.get("url") or ""
        if product_url and not product_url.startswith("http"):
            product_url = urljoin(base, product_url)
        permalink = product.get("permalink") or ""
        product_id = str(product.get("id") or permalink)

        # Category from first category or default
        categories = product.get("categories") or []
        product_type = ""
        if categories and isinstance(categories[0], dict):
            product_type = categories[0].get("name", "") or ""
        product_type = product_type.strip() or "Accessories"

        # sold_out field is null; use status field instead
        status = product.get("status", "")
        in_stock = status != "sold-out"

        return Deal(
            store_id=self.store_config.id,
            product_id=product_id,
            name=name,
            category=canonical_category(product_type, name=name),
            original_price=original,
            sale_price=sale,
            discount_pct=0.0,
            image_url=image_url,
            product_url=product_url if product_url else (f"{base}/product/{permalink}" if permalink else base),
            in_stock=in_stock,
            weight="",
            brand="",
        )

    def fetch_logo(self) -> Optional[bytes]:
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
        from urllib.parse import urljoin
        candidates = []
        for selector in (
            "img.logo",
            "img[class*='logo']",
            "a.logo img",
            "header img[alt*='logo']",
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
        raw = (self.store_config.url or "").strip()
        if not raw:
            return ""
        if "://" not in raw:
            raw = f"https://{raw}"
        parsed = urlparse(raw)
        return f"{parsed.scheme}://{parsed.netloc}"


def _money(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "").replace("$", ""))
    except ValueError:
        return 0.0


def create_scraper(store_config: StoreConfig, config: Config) -> BaseScraper:
    return BigCartelScraper(store_config, config)