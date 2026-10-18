import re
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper
from scrapers.dutchie import DutchieScraper
from models import Deal, StoreConfig
from config import Config
from utils.categories import canonical_category


class KlutchScraper(BaseScraper):
    def __init__(self, store_config: StoreConfig, config: Config):
        super().__init__(store_config, config)
        self.base_url = store_config.url.rstrip("/")

    def fetch_menu(self) -> List[Deal]:
        deals = []

        category_urls = [
            f"{self.base_url}/collections/flower",
            f"{self.base_url}/collections/pre-rolls",
            f"{self.base_url}/collections/edibles",
            f"{self.base_url}/collections/concentrates",
            f"{self.base_url}/collections/vapes",
            f"{self.base_url}/collections/topicals",
        ]

        for cat_url in category_urls:
            cat_deals = self._scrape_category(cat_url)
            deals.extend(cat_deals)

        return deals

    def _scrape_category(self, url: str) -> List[Deal]:
        response = self._make_request("GET", url)
        if not response:
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        deals = []

        category = self._extract_category_name(url)

        product_cards = soup.select("div.product-card, article.product-item, div.grid-view-item, li.product-item")
        if not product_cards:
            product_cards = soup.select("[data-product-id], .product-item, .product-card")

        for card in product_cards:
            deal = self._parse_product_card(card, category)
            if deal:
                deals.append(deal)

        return deals

    def _extract_category_name(self, url: str) -> str:
        match = re.search(r"/collections/([^/?]+)", url)
        if match:
            # Klutch's collection slugs are plural ("concentrates", "vapes"),
            # which would show up as separate shelves from the singular names
            # the Dutchie stores report.
            return canonical_category(match.group(1).replace("-", " ").title())
        return "Uncategorized"

    def _parse_product_card(self, card, category: str) -> Optional[Deal]:
        try:
            product_id = card.get("data-product-id") or card.get("data-id") or ""
            if not product_id:
                link = card.select_one("a[href*='/products/']")
                if link:
                    match = re.search(r"/products/([^/?]+)", link.get("href", ""))
                    if match:
                        product_id = match.group(1)

            name_elem = card.select_one(".product-title, .product-name, h3, h4, .title")
            name = name_elem.get_text(strip=True) if name_elem else "Unknown"

            price_elem = card.select_one(".price__regular, .price-item--regular, .product-price, .price")
            original_price = self._parse_price(price_elem)

            sale_elem = card.select_one(".price__sale, .price-item--sale, .sale-price")
            sale_price = self._parse_price(sale_elem) if sale_elem else original_price

            if original_price == 0 or sale_price == 0:
                return None

            image_elem = card.select_one("img")
            image_url = ""
            if image_elem:
                image_url = image_url = image_elem.get("src") or image_elem.get("data-src") or ""
                if image_url and not image_url.startswith("http"):
                    image_url = urljoin(self.base_url, image_url)

            link_elem = card.select_one("a[href*='/products/']")
            product_url = ""
            if link_elem:
                product_url = link_elem.get("href", "")
                if product_url and not product_url.startswith("http"):
                    product_url = urljoin(self.base_url, product_url)

            brand_elem = card.select_one(".product-vendor, .brand, .vendor")
            brand = brand_elem.get_text(strip=True) if brand_elem else None

            return Deal(
                store_id=self.store_config.id,
                product_id=str(product_id),
                name=name,
                category=canonical_category(category, name=name, brand=brand),
                original_price=original_price,
                sale_price=sale_price,
                discount_pct=0.0,
                image_url=image_url,
                product_url=product_url,
                in_stock=True,
                brand=brand,
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to parse Klutch product card: {e}")
            return None

    def _parse_price(self, elem) -> float:
        if not elem:
            return 0.0
        text = elem.get_text(strip=True)
        match = re.search(r"[\d,]+\.?\d*", text.replace(",", ""))
        if match:
            return float(match.group())
        return 0.0

    def fetch_logo(self) -> Optional[bytes]:
        logo_url = self.store_config.logo_url
        if not logo_url:
            return None

        response = self._make_request("GET", logo_url)
        if response and response.content:
            return response.content
        return None


def create_scraper(store_config: StoreConfig, config: Config) -> BaseScraper:
    scrapers = {
        "dutchie": DutchieScraper,
        "klutch": KlutchScraper,
    }
    scraper_class = scrapers.get(store_config.scraper)
    if not scraper_class:
        raise ValueError(f"Unknown scraper: {store_config.scraper}")
    return scraper_class(store_config, config)