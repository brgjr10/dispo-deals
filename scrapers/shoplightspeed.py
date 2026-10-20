"""A Shoplightspeed storefront, read from its collection pages.

High Intentions runs on Shoplightspeed, which publishes no products.json the way
Shopify does. Instead each collection page carries one `div.product-block` per
product holding the name, brand, image and price in the markup, and carries the
sale comparison in a `data-metadata` JSON blob on the card's add-to-cart link.
Reading that blob avoids a second request per product just to learn the price.

Each collection page also has an AJAX endpoint (`/pageN.ajax`) that returns
structured JSON with an `available` boolean for each product, which is the
reliable way to detect sold-out status since the HTML stock element is filled
in by JavaScript after page load.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from scrapers.base import BaseScraper
from models import Deal, StoreConfig
from config import Config
from utils.categories import canonical_category

logger = logging.getLogger(__name__)


class ShoplightspeedScraper(BaseScraper):
    """A collection-paged catalogue whose cards are one div each."""

    MAX_PAGES = 40

    def fetch_menu(self) -> List[Deal]:
        deals: List[Deal] = []
        seen_urls = set()
        # Track seen product IDs per category to detect pagination loops
        seen_per_category: Dict[str, set] = {}

        for url, category in self._collection_pages():
            response = self._make_request("GET", url)
            if not response:
                continue

            # Fetch AJAX data for inventory
            ajax_data = self._fetch_ajax_inventory(url)
            inventory = {str(p["id"]): p.get("available", True) for p in ajax_data.get("products", [])}

            batch = self._parse_page(response.text, url, inventory, category)
            
            # Track fresh products per category
            cat_seen = seen_per_category.setdefault(category, set())
            fresh = [d for d in batch if d.product_url not in seen_urls and d.product_id not in cat_seen]
            
            # If no fresh products for this category, we've hit the end of this category
            if not fresh:
                logger.debug(f"No new products in {category} at {url}, moving to next category")
                continue

            # Reset empty pages counter since we got fresh products
            for deal in batch:
                seen_urls.add(deal.product_url)
                cat_seen.add(deal.product_id)
            deals.extend(batch)
            logger.debug(
                f"Shoplightspeed {url}: {len(batch)} products ({len(fresh)} new) for {self.store_config.name}"
            )

        logger.info(
            f"Shoplightspeed fetch complete: {len(deals)} products for {self.store_config.name}"
        )
        return deals

    def _fetch_ajax_inventory(self, page_url: str) -> Dict:
        """Fetch the AJAX endpoint for a collection page to get inventory data.

        The AJAX URL is derived from the page URL by replacing .html with .ajax
        or appending /pageN.ajax for the first page.
        """
        import re
        from urllib.parse import urlparse
        parsed = urlparse(page_url)
        path = parsed.path.rstrip("/")
        query = f"?{parsed.query}" if parsed.query else ""
        root = f"{parsed.scheme}://{parsed.netloc}"

        # First page uses /collection/page1.ajax or /category/page1.ajax
        if path.endswith("/collection") or not re.search(r"/page\d+\.html$", path):
            # Check if it's a first page (no pageN.html in path)
            if path.endswith("/collection"):
                ajax_path = f"{path}/page1.ajax"
            else:
                # Category collection first page: /category/ -> /category/page1.ajax
                ajax_path = f"{path}/page1.ajax"
        else:
            # Extract page number from path like /collection/page2.html or /category/page2.html
            match = re.search(r"/page(\d+)\.html$", path)
            if match:
                page_num = match.group(1)
                ajax_path = path.replace(f"/page{page_num}.html", f"/page{page_num}.ajax")
            else:
                ajax_path = f"{path}.ajax"

        ajax_url = f"{root}{ajax_path}{query}"
        response = self._make_request("GET", ajax_url)
        if response:
            try:
                return response.json()
            except ValueError:
                logger.debug(f"Failed to parse AJAX response from {ajax_url}")
        return {}

    def _collection_pages(self) -> List[tuple[str, str]]:
        """Discover and return all category collection URLs with their categories.

        First fetches the configured URL to find category filter links,
        then returns paginated URLs for each category collection.
        """
        first = self._collection_url()
        parsed = urlparse(first)
        path = parsed.path.rstrip("/")
        query = f"?{parsed.query}" if parsed.query else ""
        root = f"{parsed.scheme}://{parsed.netloc}"

        # Fetch main page to discover category collection URLs
        category_urls = []
        response = self._make_request("GET", first)
        if response:
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.text, "html.parser")
                # Find category filter links: <a class="cat-list-title" href="/concentrate-rigs/">
                for link in soup.select("a.cat-list-title[href]"):
                    href = link.get("href", "").strip()
                    if href and not href == "#":
                        # Handle both relative and absolute URLs
                        if href.startswith("http"):
                            cat_url = href
                        else:
                            cat_url = f"{root}{href}"
                        # Preserve query string
                        if query and "?" not in cat_url:
                            cat_url += query
                        cat_name = link.get_text(strip=True)
                        category_urls.append((cat_url, cat_name))
            except Exception as e:
                logger.debug(f"Failed to parse category filters from {first}: {e}")

        # If no categories found, fall back to the configured URL
        if not category_urls:
            category = ""
            if path and not path.endswith("/collection"):
                category = path.strip("/").split("/")[-1].replace("-", " ").title()
            category_urls = [(first, category)]
        else:
            # Categories found - skip the main collection to avoid duplicates
            logger.info(f"Discovered {len(category_urls)} category collections for {self.store_config.name}")
            # Filter out any main collection URLs from category_urls
            category_urls = [(url, cat) for url, cat in category_urls if not urlparse(url).path.rstrip("/").endswith("/collection")]

        # Expand each category URL with its paginated pages
        all_pages = []
        for cat_url, category in category_urls:
            cat_parsed = urlparse(cat_url)
            cat_path = cat_parsed.path.rstrip("/")
            cat_query = f"?{cat_parsed.query}" if cat_parsed.query else query
            cat_root = f"{cat_parsed.scheme}://{cat_parsed.netloc}"

            if cat_path.endswith("/collection"):
                # Main collection - paginate
                all_pages.append((cat_url, category))
                all_pages.extend(
                    [(f"{cat_root}{cat_path}/page{page}.html{cat_query}", category)
                     for page in range(2, self.MAX_PAGES + 1)]
                )
            else:
                # Category collection - paginate from that path
                all_pages.append((cat_url, category))
                all_pages.extend(
                    [(f"{cat_root}{cat_path}/page{page}.html{cat_query}", category)
                     for page in range(2, self.MAX_PAGES + 1)]
                )

        return all_pages

    def _parse_page(self, html: str, base: str, inventory: Dict[str, bool], category: str) -> List[Deal]:
        try:
            from bs4 import BeautifulSoup
        except Exception:
            return []

        soup = BeautifulSoup(html, "html.parser")
        deals = []
        for card in soup.select("div.product-block"):
            deal = self._card_to_deal(card, base, inventory, category)
            if deal:
                deals.append(deal)
        return deals

    def _card_to_deal(self, card, base: str, inventory: Dict[str, bool], category: str) -> Optional[Deal]:
        link = card.select_one("a.product-block-title, a.product-grid-img-holder")
        if not link or not link.get("href"):
            return None

        url = urljoin(base, link["href"])
        name_el = card.select_one("a.product-block-title")
        name = (name_el or link).get_text(strip=True)
        if not name:
            return None

        brand_el = card.select_one(".product-col-brand")

        # Use metadata JSON for reliable price data (sale price + original price)
        price = 0.0
        price_old = 0.0
        for anchor in card.select("a[data-metadata]"):
            try:
                meta = json.loads(anchor.get("data-metadata") or "{}")
            except ValueError:
                continue
            price_obj = (meta.get("price") or {})
            price = _money(price_obj.get("price"))
            price_old = _money(price_obj.get("price_old"))
            break

        # Fallback to HTML if metadata missing
        if price == 0:
            price_el = card.select_one(".product-block-price .price-incl.bold, .product-block-price .price-incl:not(.price-old)")
            price_text = price_el.get_text(strip=True) if price_el else ""
            price = _money(price_text)

        on_sale = price > 0 and price_old > price
        original = price_old if on_sale else price

        img_el = card.select_one("img.product-grid-img")
        image_url = ""
        if img_el:
            image_url = img_el.get("src") or img_el.get("data-src") or ""

        # Use AJAX inventory data for reliable stock status
        product_id = card.get("data-pid") or url.rsplit("/", 1)[-1]
        in_stock = inventory.get(str(product_id), True)

        return Deal(
            store_id=self.store_config.id,
            product_id=product_id,
            name=name,
            category=canonical_category(category, name=name),
            original_price=original,
            sale_price=price,
            discount_pct=0.0,
            image_url=image_url,
            product_url=url,
            in_stock=in_stock,
            brand=brand_el.get_text(strip=True) if brand_el else "",
        )

    def fetch_logo(self) -> Optional[bytes]:
        configured = self.store_config.logo_url
        if not configured:
            return None
        response = self._make_request("GET", configured)
        return response.content if response and response.content else None

    def _root(self) -> str:
        raw = (self.store_config.url or "").strip()
        if not raw:
            return ""
        if "://" not in raw:
            raw = f"https://{raw}"
        return raw

    def _collection_url(self) -> str:
        """The configured URL, which points at the collection to scrape."""
        raw = self._root()
        parsed = urlparse(raw)
        path = parsed.path or "/collection/"
        query = f"?{parsed.query}" if parsed.query else ""
        root = f"{parsed.scheme}://{parsed.netloc}"
        return f"{root}{path}{query}"


def _money(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"[\d,]+\.?\d*", str(value).replace(",", ""))
    if not match:
        return 0.0
    try:
        return float(match.group())
    except ValueError:
        return 0.0


def create_scraper(store_config: StoreConfig, config: Config) -> BaseScraper:
    return ShoplightspeedScraper(store_config, config)
