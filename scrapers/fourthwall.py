"""Fourthwall storefront scraper using JSON-LD structured data.

Fourthwall sites don't expose a products.json like Shopify, but they embed
schema.org/Product JSON-LD in each product page. We collect product links from
a collection page and fetch each product page to extract the structured data.
"""

import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper
from models import Deal, StoreConfig
from config import Config
from utils.categories import canonical_category

logger = logging.getLogger(__name__)


class FourthwallScraper(BaseScraper):
    def __init__(self, store_config: StoreConfig, config: Config):
        super().__init__(store_config, config)
        self._product_links_cache: Optional[List[str]] = None

    def fetch_menu(self) -> List[Deal]:
        base = self._base_url()
        if not base:
            return []

        # Get product links from collection page
        product_links = self._get_product_links(base)
        if not product_links:
            logger.warning(f"No product links found for {self.store_config.name}")
            return []

        deals: List[Deal] = []
        for link in product_links:
            try:
                deal = self._fetch_product(link, base)
                if deal:
                    deals.append(deal)
            except Exception as e:
                logger.debug(f"Failed to fetch product {link}: {e}")

        logger.info(f"Fourthwall fetch complete: {len(deals)} products for {self.store_config.name}")
        return deals

    def _get_product_links(self, base: str) -> List[str]:
        """Extract product links from the collection page."""
        # Try common collection URLs
        collection_paths = [
            "/collections/all",
            "/collections/shop",
            "/shop",
            "/products",
        ]

        for path in collection_paths:
            url = urljoin(base, path)
            response = self._make_request("GET", url)
            if not response or response.status_code != 200:
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            links = soup.find_all("a", href=True)
            product_links = []
            for link in links:
                href = link["href"]
                if "/products/" in href and not href.endswith("/products"):
                    full_url = urljoin(base, href)
                    product_links.append(full_url)

            if product_links:
                # Deduplicate while preserving order
                seen = set()
                unique = []
                for u in product_links:
                    if u not in seen:
                        seen.add(u)
                        unique.append(u)
                logger.debug(f"Found {len(unique)} product links at {url}")
                return unique

        logger.warning(f"No collection page yielded products for {self.store_config.name}")
        return []

    def _fetch_product(self, product_url: str, base: str) -> Optional[Deal]:
        """Fetch a single product page and parse JSON-LD."""
        response = self._make_request("GET", product_url)
        if not response or response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        # Find JSON-LD Product data
        scripts = soup.find_all("script", type="application/ld+json")
        product_data = None
        for script in scripts:
            if not script.string:
                continue
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and data.get("@type") == "Product":
                    product_data = data
                    break
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get("@type") == "Product":
                            product_data = item
                            break
            except json.JSONDecodeError:
                continue

        if not product_data:
            logger.debug(f"No JSON-LD Product found at {product_url}")
            return None

        return self._to_deal(product_data, product_url, base)

    def _to_deal(self, product: Dict[str, Any], product_url: str, base: str) -> Optional[Deal]:
        """Convert JSON-LD Product to Deal."""
        name = (product.get("name") or "").strip()
        if not name:
            return None

        # Get image
        images = product.get("image") or []
        image_url = ""
        if images:
            if isinstance(images, list):
                image_url = images[0]
            else:
                image_url = images

        # Get price from offers - use the lowest price as the "sale" price
        offers = product.get("offers") or []
        if isinstance(offers, dict):
            offers = [offers]

        prices = []
        in_stock = False
        for offer in offers:
            if not isinstance(offer, dict):
                continue
            price_str = offer.get("price")
            if price_str:
                try:
                    prices.append(float(price_str))
                except (ValueError, TypeError):
                    pass
            avail = offer.get("availability", "")
            if "InStock" in avail:
                in_stock = True

        if not prices:
            return None

        # Use minimum price as the sale price
        price = min(prices)
        original_price = price  # Fourthwall doesn't expose compare_at_price easily

        # Extract handle from URL for product_id
        handle = product_url.split("/products/")[-1].split("?")[0]
        product_id = handle

        # Category from product type or default
        product_type = (product.get("category") or "").strip() or "Apparel"

        return Deal(
            store_id=self.store_config.id,
            product_id=product_id,
            name=name,
            category=canonical_category(product_type, name=name),
            original_price=original_price,
            sale_price=price,
            discount_pct=0.0,
            image_url=image_url,
            product_url=product_url,
            in_stock=in_stock,
            weight="",
            brand=(product.get("brand", {}).get("name") if isinstance(product.get("brand"), dict) else "") or "",
        )

    def fetch_logo(self) -> Optional[bytes]:
        base = self._base_url()
        response = self._make_request("GET", base)
        if not response:
            return None

        try:
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
        raw = (self.store_config.url or "").strip()
        if not raw:
            return ""
        if "://" not in raw:
            raw = f"https://{raw}"
        parsed = urlparse(raw)
        return f"{parsed.scheme}://{parsed.netloc}"


import json  # noqa: E402


def create_scraper(store_config: StoreConfig, config: Config) -> BaseScraper:
    return FourthwallScraper(store_config, config)