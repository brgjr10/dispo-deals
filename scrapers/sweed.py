"""A Sweed POS storefront, read through its public shop API.

Curaleaf's oh.curaleaf.com runs on Sweed POS. The storefront is a single-page
app that reads its menu from ``https://web-ui-<brand>.sweedpos.com/_api/proxy``,
so the catalogue is fetched from ``Products/GetProductList`` (POST, paged)
rather than rendered in HTML. Each request carries the numeric ``storeid`` for
the location, a sale type ("Recreational") and a per-call ``traceid`` GUID.
Prices come back per variant as ``price`` and ``promoPrice`` (a ""sale"") with
``availableQty`` for stock, and every product already carries a category and a
subcategory, so the shelf is taken from the source rather than guessed.
"""

import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from scrapers.base import BaseScraper
from models import Deal, StoreConfig
from config import Config
from utils.categories import SUB_SEPARATOR, canonical_category, canonical_category_named

logger = logging.getLogger(__name__)

PAGE_SIZE = 100


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


class SweedScraper(BaseScraper):
    MAX_PAGES = 25

    def __init__(self, store_config: StoreConfig, config: Config):
        super().__init__(store_config, config)
        opts = store_config.scraper_options or {}
        self.store_id = str(opts.get("storeid", ""))
        self.sale_type = opts.get("sale_type", "Recreational")
        self.api_base = opts.get("api_host", "").rstrip("/")

    def fetch_menu(self) -> List[Deal]:
        deals: List[Deal] = []
        total: Optional[int] = None
        page = 1
        while page <= self.MAX_PAGES:
            payload = self._get_page(page)
            rows = payload.get("list") or []
            total = payload.get("total", total)
            if not rows:
                break
            for product in rows:
                deal = self._to_deal(product)
                if deal:
                    deals.append(deal)
            # Stop when the last page is reached. ``total`` is the catalogue
            # size, so once we've collected it there is nothing more to fetch.
            if total is not None and len(deals) >= int(total):
                break
            page += 1
        logger.info(
            f"Sweed fetch complete: {len(deals)} products "
            f"(of ~{total}) for {self.store_config.name}"
        )
        return deals

    def _api_base_from_url(self) -> str:
        if self.api_base:
            return self.api_base
        raw = (self.store_config.url or "").strip()
        if "://" not in raw:
            raw = f"https://{raw}"
        return raw

    def _headers(self) -> Dict[str, str]:
        headers = {
            "accept": "*/*",
            "content-type": "application/json",
            "origin": self._site_root(),
            "referer": f"{self._site_root()}/",
            "platform": "web",
            "ssr": "false",
            "storeid": self.store_id,
            "traceid": str(uuid.uuid4()),
            "saletype": self.sale_type,
            # The storefront sets this age-gate cookie; without it the shop API
            # refuses to serve the menu to a non-browser client.
            "x-cookie": "ageGateConfirmed=1",
        }
        headers.update(self._get_headers(self.store_config.scraper))
        # storeid/traceid must not be overridden by shared config headers.
        headers["storeid"] = self.store_id
        headers["traceid"] = str(uuid.uuid4())
        return headers

    def _site_root(self) -> str:
        raw = (self.store_config.url or "").strip()
        if not raw:
            return ""
        if "://" not in raw:
            raw = f"https://{raw}"
        parsed = urlparse(raw)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _get_page(self, page: int) -> Dict[str, Any]:
        base = self.api_base or ""
        url = f"{base}/_api/proxy/Products/GetProductList"
        body = {"saleType": self.sale_type, "platformOs": "web", "page": page, "pageSize": PAGE_SIZE}
        response = self._make_request("POST", url, headers=self._headers(), data=json.dumps(body))
        if not response:
            return {}
        try:
            payload = response.json()
        except ValueError:
            logger.warning(f"Sweed returned non-JSON for {url}")
            return {}
        return payload if isinstance(payload, dict) else {}

    def _to_deal(self, product: Dict[str, Any]) -> Optional[Deal]:
        variant = self._choose_variant(product.get("variants") or [])
        if variant is None:
            return None

        price = _num(variant.get("price"))
        promo = _num(variant.get("promoPrice"))
        if price <= 0:
            return None
        on_sale = 0 < promo < price
        original = price
        sale = promo if on_sale else price
        if sale <= 0:
            return None

        category = product.get("category") or {}
        subcategory = product.get("subcategory") or {}
        cat_name = category.get("name", "")
        sub_name = subcategory.get("name", "")
        # The source already separates shelf and sub-shelf, so build the pair
        # and canonicalise it; only fall back to the title when the shelf is
        # missing entirely.
        if cat_name:
            cat = canonical_category(f"{cat_name}{SUB_SEPARATOR}{sub_name}" if sub_name else cat_name)
        else:
            cat = canonical_category_named("", product.get("name", ""))

        images = product.get("images") or []
        variant_images = variant.get("images") or []
        image_url = (images[0] if images else (variant_images[0] if variant_images else ""))

        thc = _first(variant, "labTests", "thc", "value")
        in_stock = _num(variant.get("availableQty")) > 0
        brand = (product.get("brand") or {}).get("name", "")

        name = (product.get("name") or "").strip()
        product_id = product.get("id")
        variant_id = variant.get("id")

        return Deal(
            store_id=self.store_config.id,
            product_id=str(product_id if product_id is not None else variant_id),
            name=name,
            category=cat,
            original_price=original,
            sale_price=sale,
            discount_pct=0.0,
            image_url=image_url,
            product_url=self._product_url(product, category, variant_id),
            in_stock=in_stock,
            weight=str(variant.get("name", "") or ""),
            brand=brand,
            thc_pct=thc,
        )

    @staticmethod
    def _choose_variant(variants: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Pick the variant to advertise: first in stock, else first priced.

        A product with several sizes still contributes one deal, so the first
        available variant is used and only a fully out-of-stock product falls
        back to its first priced variant.
        """
        available = next(
            (v for v in variants if _num(v.get("price")) > 0 and _num(v.get("availableQty")) > 0),
            None,
        )
        if available:
            return available
        return next((v for v in variants if _num(v.get("price")) > 0), None)

    def _product_url(self, product: Dict[str, Any], category: Dict[str, Any], variant_id: Any) -> str:
        menu = (self.store_config.url or "").rstrip("/")
        if not menu:
            return ""
        cat_slug = f"{category.get('canonicalName', '')}-{category.get('id', '')}".strip("-")
        slug = _slug(product.get("name", ""))
        return f"{menu}/menu/{cat_slug}/{slug}-{variant_id}" if cat_slug and slug else menu

    def fetch_logo(self) -> Optional[bytes]:
        configured = self.store_config.logo_url
        if not configured:
            return None
        response = self._make_request("GET", configured)
        return response.content if response and response.content else None


def _num(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return 0.0


def _first(obj: Any, *path: str) -> Any:
    """Read a nested key whose final value is a list, returning its first item."""
    cur = obj
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    if isinstance(cur, list) and cur:
        return cur[0]
    return None


def create_scraper(store_config: StoreConfig, config: Config) -> BaseScraper:
    return SweedScraper(store_config, config)
