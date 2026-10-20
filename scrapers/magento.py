"""A Magento storefront, read through its GraphQL API.

Zumiez runs on Magento with the ScandiPWA frontend, which is neither Shopify
nor Dutchie. Magento publishes an unauthenticated GraphQL endpoint at
``/graphql``, so the catalogue is read from fields rather than parsed out of
the themed HTML, and a frontend change cannot break the scrape.

A store is configured with the collection page URL. The category is resolved
from that URL's path (``collections/weed.html`` is the ``collections/weed``
category), and if no category matches, the last path segment is used as a
search term instead.
"""

import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from scrapers.base import BaseScraper
from models import Deal, StoreConfig
from config import Config
from utils.categories import canonical_category

logger = logging.getLogger(__name__)


class MagentoScraper(BaseScraper):
    PAGE_SIZE = 100
    MAX_PAGES = 10

    # Titles containing any of these words are dropped entirely. Zumiez is a
    # skate shop, so its 420 collection also carries candy-branded apparel and
    # accessories that are not cannabis products and would show up as noise on
    # the deals board. A store can override the list in its config.
    EXCLUDE_TERMS = ("candy",)

    CATEGORY_QUERY = """
    query($path: String) {
      categories(filters: { url_path: { eq: $path } }) {
        items { uid name }
      }
    }
    """

    PRODUCTS_BY_CATEGORY_QUERY = """
    query($uid: String, $pageSize: Int, $currentPage: Int) {
      products(filter: { category_uid: { eq: $uid } }, pageSize: $pageSize, currentPage: $currentPage) {
        total_count
        items {
          name
          sku
          url_key
          image { url }
          stock_status
          price_range {
            minimum_price {
              final_price { value }
              regular_price { value }
            }
          }
        }
      }
    }
    """

    PRODUCTS_BY_SEARCH_QUERY = """
    query($term: String, $pageSize: Int, $currentPage: Int) {
      products(search: $term, pageSize: $pageSize, currentPage: $currentPage) {
        total_count
        items {
          name
          sku
          url_key
          image { url }
          stock_status
          price_range {
            minimum_price {
              final_price { value }
              regular_price { value }
            }
          }
        }
      }
    }
    """

    def fetch_menu(self) -> List[Deal]:
        base = self._base_url()
        if not base:
            return []

        deals: List[Deal] = []

        category_uid = self._resolve_category_uid(base)
        if category_uid:
            logger.info(
                f"Magento category {category_uid} for {self.store_config.name}"
            )
            page = 1
            while page <= self.MAX_PAGES:
                batch, returned = self._fetch_by_category(base, category_uid, page)
                if not returned:
                    break
                deals.extend(batch)
                logger.debug(
                    f"Magento page {page}: {returned} items, {len(batch)} priced"
                )
                # Pagination follows the API's item count, not the priced count:
                # an out-of-stock item reports no price and is dropped, so a
                # short page of deals does not mean the catalogue ended.
                if returned < self.PAGE_SIZE:
                    break
                page += 1
        else:
            # No category matched, so fall back to the URL's last segment as a
            # search term. That still yields the collection the link points at
            # for stores that do not name the category after its path.
            term = self._search_term()
            logger.info(
                f"Magento search '{term}' for {self.store_config.name}"
            )
            page = 1
            while page <= self.MAX_PAGES:
                batch, returned = self._fetch_by_search(base, term, page)
                if not returned:
                    break
                deals.extend(batch)
                if returned < self.PAGE_SIZE:
                    break
                page += 1

        logger.info(
            f"Magento fetch complete: {len(deals)} products for {self.store_config.name}"
        )
        return deals

    def _graphql(self, base: str, query: str, variables: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        response = self._make_request(
            "POST",
            f"{base}/graphql",
            json={"query": query, "variables": variables},
            headers={"Content-Type": "application/json"},
        )
        if not response:
            return None
        try:
            payload = response.json()
        except ValueError:
            logger.warning(f"Magento returned non-JSON for {self.store_config.name}")
            return None
        if payload.get("errors"):
            logger.warning(
                f"Magento GraphQL errors for {self.store_config.name}: {payload['errors']}"
            )
            return None
        return payload.get("data")

    def _resolve_category_uid(self, base: str) -> Optional[str]:
        """The category id behind the configured collection URL, if there is one."""
        path = urlparse(self.store_config.url or "").path.strip("/")
        if not path:
            return None
        # A collection page ends in .html; the stored url_path does not.
        path = path[:-5] if path.endswith(".html") else path

        data = self._graphql(base, self.CATEGORY_QUERY, {"path": path})
        items = (data or {}).get("categories", {}).get("items") or []
        if not items:
            return None
        return items[0].get("uid")

    def _search_term(self) -> str:
        path = urlparse(self.store_config.url or "").path.strip("/")
        if not path:
            return ""
        segment = path.split("/")[-1]
        return segment[:-5] if segment.endswith(".html") else segment

    def _fetch_by_category(self, base: str, uid: str, page: int) -> tuple:
        data = self._graphql(
            base,
            self.PRODUCTS_BY_CATEGORY_QUERY,
            {"uid": uid, "pageSize": self.PAGE_SIZE, "currentPage": page},
        )
        products = (data or {}).get("products", {})
        items = products.get("items") or []
        deals = []
        for product in items:
            deal = self._to_deal(product, base)
            if deal:
                deals.append(deal)
        return deals, len(items)

    def _fetch_by_search(self, base: str, term: str, page: int) -> tuple:
        if not term:
            return [], 0
        data = self._graphql(
            base,
            self.PRODUCTS_BY_SEARCH_QUERY,
            {"term": term, "pageSize": self.PAGE_SIZE, "currentPage": page},
        )
        products = (data or {}).get("products", {})
        items = products.get("items") or []
        deals = []
        for product in items:
            deal = self._to_deal(product, base)
            if deal:
                deals.append(deal)
        return deals, len(items)

    def _to_deal(self, product: Dict[str, Any], base: str) -> Optional[Deal]:
        """Turn one Magento product record into a Deal.

        A sale is ``regular_price`` being set and higher than ``final_price``,
        which is Magento's own "was / now" convention.
        """
        name = (product.get("name") or "").strip()
        if self._is_excluded(name):
            return None

        price_range = (product.get("price_range") or {}).get("minimum_price") or {}
        final = price_range.get("final_price") or {}
        regular = price_range.get("regular_price") or {}

        price = final.get("value") or 0.0
        compare_at = regular.get("value") or 0.0

        # An out-of-stock variant reports 0 rather than its price, and a zero
        # price would show as a free product in the dashboard.
        if price <= 0:
            return None

        on_sale = compare_at > price
        original = compare_at if on_sale else price
        sale = price
        discount_pct = (
            round((original - sale) / original * 100, 1) if original > 0 else 0.0
        )

        image = (product.get("image") or {}).get("url", "")
        url_key = product.get("url_key") or ""
        # ScandiPWA product URLs keep the Magento .html suffix.
        product_url = f"{base}/{url_key}.html" if url_key else base

        return Deal(
            store_id=self.store_config.id,
            product_id=str(product.get("sku") or url_key),
            name=name,
            category=canonical_category("Accessories", name=name),
            original_price=original,
            sale_price=sale,
            discount_pct=discount_pct,
            image_url=image,
            product_url=product_url,
            in_stock=(product.get("stock_status") == "IN_STOCK"),
            weight="",
            brand="",
        )

    def _is_excluded(self, name: str) -> bool:
        """True when a product title carries an excluded term.

        Matched on word boundaries so "candy" drops "Sour Candy Tee" but leaves
        "Candyman" alone. An empty override list disables filtering, which is
        what a store with no exclusions should get.
        """
        terms = getattr(self.store_config, "exclude_terms", None)
        if terms is None:
            terms = self.EXCLUDE_TERMS
        if not name or not terms:
            return False
        lowered = name.lower()
        return any(
            re.search(rf"\b{re.escape(str(term).lower())}\b", lowered)
            for term in terms
            if str(term).strip()
        )

    def fetch_logo(self) -> Optional[bytes]:
        """No logo: these sources are accessory and apparel brands, and the
        dashboard keeps a generic mark rather than blocking on a logo fetch."""
        return None

    def _base_url(self) -> str:
        """The store root, with any path or query removed."""
        raw = (self.store_config.url or "").strip()
        if not raw:
            return ""
        if "://" not in raw:
            raw = f"https://{raw}"
        parsed = urlparse(raw)
        return f"{parsed.scheme}://{parsed.netloc}"


def create_scraper(store_config: StoreConfig, config: Config) -> BaseScraper:
    return MagentoScraper(store_config, config)
