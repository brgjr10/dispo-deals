"""A WooCommerce storefront, read through its Store API or its HTML.

Mothership Glass and Illadelph both run on WooCommerce. Where the public,
keyless Store API is available (/wp-json/wc/store/v1/products) it is used, since
name, price, image, stock and category come from fields rather than scraped out
of markup. Some stores disable that API (Illadelph returns 404), so the scraper
then falls back to parsing the /shop/ product loop in the storefront HTML, which
is standard WooCommerce markup (li.product cards). Either way the title is
passed to canonical_category_named so a product with no useful shelf is still
filed by its name.
"""

import html
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from scrapers.base import BaseScraper
from models import Deal, StoreConfig
from config import Config
from utils.categories import CATEGORY_ALIASES, canonical_category_named

logger = logging.getLogger(__name__)

PAGE_SIZE = 100
_KNOWN_MAINS = set(CATEGORY_ALIASES.values())
_PRICE_RE = re.compile(r"[\d,]+(?:\.\d+)?")
_POST_ID_RE = re.compile(r"\bpost-(\d+)\b")
_CAT_SLUG_RE = re.compile(r"product_cat-([a-z0-9-]+)")


class WooCommerceScraper(BaseScraper):
    MAX_PAGES = 20

    def fetch_menu(self) -> List[Deal]:
        base = self._base_url()
        if self._store_api_available(base):
            return self._fetch_menu_api(base)
        logger.info(
            f"WooCommerce Store API unavailable for {self.store_config.name}; "
            f"parsing the storefront HTML instead"
        )
        return self._fetch_menu_html()

    def _base_url(self) -> str:
        """The store root, with any path or query removed."""
        raw = (self.store_config.url or "").strip()
        if not raw:
            return ""
        if "://" not in raw:
            raw = f"https://{raw}"
        parsed = urlparse(raw)
        return f"{parsed.scheme}://{parsed.netloc}"

    # -- Store API path ----------------------------------------------------

    def _store_api_available(self, base: str) -> bool:
        """True when the public Store API answers with a product list."""
        url = f"{base}/wp-json/wc/store/v1/products?per_page=1"
        response = self._make_request("GET", url)
        if not response:
            return False
        try:
            payload = response.json()
        except ValueError:
            return False
        return isinstance(payload, list)

    def _fetch_menu_api(self, base: str) -> List[Deal]:
        deals: List[Deal] = []
        page = 1
        while page <= self.MAX_PAGES:
            batch = self._fetch_page_api(base, page)
            if not batch:
                break
            deals.extend(batch)
            # A short page means the catalogue ended.
            if len(batch) < PAGE_SIZE:
                break
            page += 1
        return deals

    def _fetch_page_api(self, base: str, page: int) -> List[Deal]:
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

    # -- Storefront HTML path ---------------------------------------------

    def _listing_url(self) -> str:
        """The shop archive to scrape when the Store API is unavailable."""
        raw = (self.store_config.url or "").strip()
        if not raw:
            return ""
        if "://" not in raw:
            raw = f"https://{raw}"
        parsed = urlparse(raw)
        path = parsed.path or "/shop"
        if path in ("", "/"):
            path = "/shop"
        root = f"{parsed.scheme}://{parsed.netloc}"
        return f"{root}{path.rstrip('/')}"

    def _fetch_menu_html(self) -> List[Deal]:
        listing = self._listing_url()
        deals: List[Deal] = []
        page = 1
        while page <= self.MAX_PAGES:
            url = listing if page == 1 else f"{listing}/page/{page}/"
            response = self._make_request("GET", url)
            if not response:
                break
            batch = self._parse_html(response.text, url)
            if not batch:
                break
            deals.extend(batch)
            logger.debug(f"WooCommerce HTML page {page}: {len(batch)} products")
            page += 1
        return deals

    def _parse_html(self, page_html: str, base: str) -> List[Deal]:
        try:
            from bs4 import BeautifulSoup
        except Exception:
            return []
        soup = BeautifulSoup(page_html, "html.parser")
        deals = []
        for card in soup.select("li.product"):
            deal = self._card_to_deal(card, base)
            if deal:
                deals.append(deal)
        return deals

    def _card_to_deal(self, card, base: str) -> Optional[Deal]:
        link = card.select_one("a.woocommerce-loop-product__link")
        href = link.get("href") if link else None
        title_el = card.select_one(".woocommerce-loop-product__title")
        title = html.unescape(title_el.get_text(strip=True)) if title_el else ""
        if not title:
            return None

        classes = card.get("class") or []
        m = _POST_ID_RE.search(" ".join(classes))
        product_id = m.group(1) if m else (href or title)

        price_el = card.select_one(".price")
        original, sale = self._prices_from_card(price_el)
        if sale <= 0:
            return None

        img = card.select_one("img")
        image_url = (img.get("src") or img.get("data-src")) if img else ""

        in_stock = "outofstock" not in classes

        category = self._category_from_classes(card, title)

        return Deal(
            store_id=self.store_config.id,
            product_id=str(product_id),
            name=title,
            category=category,
            original_price=original,
            sale_price=sale,
            discount_pct=0.0,
            image_url=image_url or "",
            product_url=href or base,
            in_stock=in_stock,
            weight="",
            brand=self.store_config.name,
        )

    @staticmethod
    def _amount(element) -> float:
        if element is None:
            return 0.0
        text = element.get_text(" ", strip=True)
        m = _PRICE_RE.search(text.replace(",", ""))
        return float(m.group()) if m else 0.0

    def _prices_from_card(self, price_el):
        """(original, sale) from a loop card's .price block.

        A sale shows <del>was</del><ins>now</ins>; a range shows two amounts,
        in which case the first (min) is used and no discount is implied.
        """
        if price_el is None:
            return 0.0, 0.0
        del_amt = self._amount(price_el.select_one("del .woocommerce-Price-amount"))
        ins_amt = self._amount(price_el.select_one("ins .woocommerce-Price-amount"))
        if del_amt > 0 and ins_amt > 0:
            return del_amt, ins_amt
        amounts = [self._amount(a) for a in price_el.select(".woocommerce-Price-amount")]
        amounts = [a for a in amounts if a > 0]
        if not amounts:
            return 0.0, 0.0
        # A range lists min and max; taking the min as both implies no discount.
        return amounts[0], amounts[0]

    def _category_from_classes(self, card, title: str) -> str:
        """A category shelf derived from the card's product_cat-* classes.

        Slugs that map to a known main win, so an item filed under both
        "accessories" and a niche collection lands on the known shelf.
        """
        classes = " ".join(card.get("class") or [])
        slugs = _CAT_SLUG_RE.findall(classes)
        chosen = ""
        for slug in slugs:
            pretty = slug.replace("-", " ")
            if canonical_category_named(pretty, "") in _KNOWN_MAINS:
                chosen = pretty
                break
        if not chosen and slugs:
            chosen = slugs[0].replace("-", " ")
        if not chosen:
            chosen = "Accessories"
        return canonical_category_named(chosen, title)

    def fetch_logo(self) -> Optional[bytes]:
        """Return the configured logo, if the store has one."""
        configured = self.store_config.logo_url
        if not configured:
            return None
        response = self._make_request("GET", configured)
        return response.content if response and response.content else None


def create_scraper(store_config: StoreConfig, config: Config) -> BaseScraper:
    return WooCommerceScraper(store_config, config)
