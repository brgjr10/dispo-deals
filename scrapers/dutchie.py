import json
import re
import os
import requests
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse, urljoin
import cloudscraper
from bs4 import BeautifulSoup

from scrapers.base import BaseScraper
from models import Deal, StoreConfig
from config import Config


class DutchieScraper(BaseScraper):
    """Dutchie scraper with Cloudflare bypass.
    
    Supports multiple backends:
    1. FlareSolverr (via FLARESOLVERR_URL env var) - recommended for Docker
    2. cloudscraper (fallback) - works locally
    3. Direct requests with cloudscraper session
    
    Note: Dutchie's GraphQL schema changes frequently. The Apollo cache approach
    from the page HTML works but requires parsing the embedded __NEXT_DATA__.
    """

    def __init__(self, store_config: StoreConfig, config: Config):
        super().__init__(store_config, config)
        self.dispensary_slug = self._extract_slug(store_config.url)
        self.graphql_endpoint = config.scrapers.dutchie.get("graphql_endpoint", "https://dutchie.com/graphql")
        
        # Initialize Cloudflare bypass
        self.flaresolverr_url = os.environ.get('FLARESOLVERR_URL')
        if self.flaresolverr_url:
            self.session = requests.Session()
            self.scraper = None
        else:
            self.scraper = cloudscraper.create_scraper(browser='chrome')

    def _extract_slug(self, url: str) -> str:
        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.split("/") if p]
        if "stores" in path_parts:
            idx = path_parts.index("stores")
            if idx + 1 < len(path_parts):
                return path_parts[idx + 1]
        return path_parts[-1] if path_parts else ""

    def _make_request_with_flaresolverr(self, method: str, url: str, **kwargs) -> Optional[requests.Response]:
        """Make request through FlareSolverr."""
        try:
            payload = {
                "cmd": "request.get" if method == "GET" else "request.post",
                "url": url,
                "maxTimeout": 60000
            }
            headers = kwargs.get("headers", {})
            if headers:
                payload["headers"] = headers
            if method == "POST":
                payload["postData"] = json.dumps(kwargs.get("json", {}))
            
            response = self.session.post(
                f"{self.flaresolverr_url}/v1",
                json=payload,
                timeout=65
            )
            if response.status_code == 200:
                result = response.json()
                if result.get("status") == "ok":
                    fs_response = result.get("response", {})
                    actual_status = fs_response.get("status", 200)
                    actual_body = fs_response.get("body", "")
                    actual_headers = fs_response.get("headers", {})
                    
                    if actual_body and "<pre>" in actual_body:
                        import re
                        pre_match = re.search(r"<pre>(.*?)</pre>", actual_body, re.DOTALL)
                        if pre_match:
                            actual_body = pre_match.group(1)
                    
                    class FSResponse:
                        def __init__(self, status, body, headers):
                            self.status_code = status
                            self._body = body
                            self._headers = headers
                            self._parsed_json = None
                        
                        def json(self):
                            if self._parsed_json is None:
                                try:
                                    self._parsed_json = json.loads(self._body)
                                except json.JSONDecodeError:
                                    self._parsed_json = {}
                            return self._parsed_json
                        
                        @property
                        def content(self):
                            return self._body.encode() if isinstance(self._body, str) else self._body
                        
                        @property
                        def text(self):
                            return self._body if isinstance(self._body, str) else self._body.decode('utf-8', errors='replace')
                        
                        @property
                        def headers(self):
                            return self._headers
                        
                        def raise_for_status(self):
                            if self.status_code >= 400:
                                raise requests.HTTPError(f"{self.status_code} Error")
                    
                    return FSResponse(actual_status, actual_body, actual_headers)
            return None
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug(f"FlareSolverr request failed: {e}")
            return None

    def fetch_menu(self) -> List[Deal]:
        deals = self._try_graphql()
        if deals:
            return deals
        deals = self._extract_from_page()
        if deals:
            return deals
        return self._extract_from_rendered_dom()

    def _try_graphql(self) -> List[Deal]:
        variables = {
            "dispensarySlug": self.dispensary_slug,
            "filters": {}
        }
        payload = {"query": self.GRAPHQL_QUERY, "variables": variables}
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Origin': 'https://dutchie.com',
            'Referer': f'https://dutchie.com/stores/{self.dispensary_slug}',
            'x-dutchie-client': 'web'
        }
        
        try:
            response = self._make_request("POST", self.graphql_endpoint, json=payload, headers=headers)
            
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"GraphQL response status: {response.status_code if response else 'None'}")
            
            if not response or response.status_code != 200:
                logger.warning(f"GraphQL HTTP error: {response.status_code if response else 'No response'}")
                return []
            
            data = response.json()
            logger.debug(f"GraphQL data keys: {list(data.keys()) if isinstance(data, dict) else 'not dict'}")
            
            if 'errors' in data:
                logger.warning(f"GraphQL errors: {data['errors']}")
                return []
            
            menu = data.get("data", {}).get("menu")
            if not menu:
                return []
            
            deals = []
            for category in menu.get("categories", []):
                cat_name = category.get("name", "Uncategorized")
                for product in category.get("products", []):
                    deal = self._parse_product(product, cat_name)
                    if deal:
                        deals.append(deal)
            return deals
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"GraphQL failed: {e}")
            return []

    def _make_request(self, method: str, url: str, **kwargs) -> Optional[requests.Response]:
        """Make HTTP request using FlareSolverr (in Docker) or cloudscraper (locally)."""
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"_make_request called: method={method}, url={url}, flaresolverr_url={bool(self.flaresolverr_url)}")
        
        try:
            if self.flaresolverr_url:
                logger.info("Using FlareSolverr for request")
                return self._make_request_with_flaresolverr(method, url, **kwargs)
            else:
                if not hasattr(self, 'scraper') or self.scraper is None:
                    import cloudscraper
                    self.scraper = cloudscraper.create_scraper(browser='chrome')
                logger.info("Using cloudscraper")
                return getattr(self.scraper, method.lower())(url, **kwargs)
        except Exception as e:
            logger.error(f"Request failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def _extract_from_page(self) -> List[Deal]:
        """Extract products from the page's embedded Apollo cache (initial HTML)."""
        url = f"https://dutchie.com/stores/{self.dispensary_slug}"
        try:
            response = self._make_request("GET", url, timeout=30)
            
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Page extraction response status: {response.status_code if response else 'None'}")
            
            if not response or response.status_code != 200:
                logger.warning(f"Page extraction HTTP error: {response.status_code if response else 'No response'}")
                return []
            
            next_data_match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', response.text, re.DOTALL)
            if not next_data_match:
                logger.warning("No __NEXT_DATA__ found in page")
                return []
            
            data = json.loads(next_data_match.group(1))
            apollo_state = data.get('props', {}).get('pageProps', {}).get('initialApolloState', {})
            logger.info(f"Apollo state keys: {len(apollo_state)}")
            
            product_ids = set()
            for key, value in apollo_state.items():
                if key.startswith('MenuSection:') and isinstance(value, dict):
                    products = value.get('products', [])
                    for p in products:
                        if isinstance(p, str):
                            product_ids.add(p)
                        elif isinstance(p, dict) and '__ref' in p:
                            product_ids.add(p['__ref'])
            
            deals = []
            for pid in product_ids:
                product = apollo_state.get(pid)
                if not product and not pid.startswith('Product:'):
                    product = apollo_state.get(f'Product:{pid}')
                if not product:
                    for k, v in apollo_state.items():
                        if isinstance(v, dict) and v.get('id') == pid:
                            product = v
                            break
                
                if product and isinstance(product, dict):
                    deal = self._parse_product_apollo(product, apollo_state)
                    if deal:
                        deals.append(deal)
            
            return deals
        except Exception as e:
            import logging
            import traceback
            logging.getLogger(__name__).error(f"Page extraction failed: {e}\n{traceback.format_exc()}")
            return []

    def _extract_from_rendered_dom(self) -> List[Deal]:
        """Extract products from the fully rendered DOM (after JS execution via FlareSolverr)."""
        url = f"https://dutchie.com/stores/{self.dispensary_slug}"
        try:
            response = self._make_request("GET", url, timeout=60)
            
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"DOM extraction response status: {response.status_code if response else 'None'}")
            
            if not response or response.status_code != 200:
                logger.warning(f"DOM extraction HTTP error: {response.status_code if response else 'No response'}")
                return []
            
            soup = BeautifulSoup(response.content, "html.parser")
            logger.info(f"DOM content length: {len(response.content)}")
            deals = []
            
            product_selectors = [
                "[data-testid='product-card']",
                "[data-testid='product-tile']",
                ".product-card",
                ".product-tile",
                "[data-product-id]",
                "article.product-item",
                ".menu-product",
                ".product-item",
                "[role='listitem']",
            ]
            
            product_cards = []
            for selector in product_selectors:
                product_cards = soup.select(selector)
                if product_cards:
                    break
            
            if not product_cards:
                product_cards = soup.find_all(attrs={"data-product-id": True})
            
            for card in product_cards:
                deal = self._parse_product_card(card)
                if deal:
                    deals.append(deal)
            
            return deals
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"DOM extraction failed: {e}")
            return []

    def _parse_product_card(self, card) -> Optional[Deal]:
        """Parse a product card from rendered DOM."""
        try:
            product_id = card.get("data-product-id") or card.get("data-id") or ""
            if not product_id:
                link = card.select_one("a[href*='/product/'], a[href*='/products/']")
                if link:
                    match = re.search(r"/product[s]?/([^/?]+)", link.get("href", ""))
                    if match:
                        product_id = match.group(1)
            
            name_elem = card.select_one("[data-testid='product-name'], .product-name, .product-title, h3, h4, .title")
            name = name_elem.get_text(strip=True) if name_elem else "Unknown"
            
            price_selectors = [
                "[data-testid='price']",
                "[data-testid='sale-price']",
                ".price__sale",
                ".price-item--sale",
                ".sale-price",
                ".product-price",
                ".price"
            ]
            
            original_price = 0.0
            sale_price = 0.0
            
            for selector in price_selectors:
                price_elem = card.select_one(selector)
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    price_match = re.search(r"[\d,]+\.?\d*", price_text.replace(",", ""))
                    if price_match:
                        sale_price = float(price_match.group())
                        break
            
            original_elem = card.select_one(".price__regular, .price-item--regular, .original-price, .was-price, s, del")
            if original_elem:
                price_text = original_elem.get_text(strip=True)
                price_match = re.search(r"[\d,]+\.?\d*", price_text.replace(",", ""))
                if price_match:
                    original_price = float(price_match.group())
            
            if original_price == 0:
                original_price = sale_price
            
            if sale_price == 0:
                return None
            
            image_elem = card.select_one("img")
            image_url = ""
            if image_elem:
                image_url = image_elem.get("src") or image_elem.get("data-src") or ""
                if image_url and not image_url.startswith("http"):
                    image_url = urljoin("https://dutchie.com", image_url)
            
            link_elem = card.select_one("a[href*='/product/'], a[href*='/products/']")
            product_url = ""
            if link_elem:
                product_url = link_elem.get("href", "")
                if product_url and not product_url.startswith("http"):
                    product_url = urljoin("https://dutchie.com", product_url)
            
            category = card.get("data-category", "Uncategorized")
            if category == "Uncategorized":
                parent_section = card.find_parent("section", class_=re.compile(r"category|menu-section"))
                if parent_section:
                    category = parent_section.get("data-category") or parent_section.get("id", "Uncategorized").replace("-", " ").title()
            
            brand_elem = card.select_one("[data-testid='brand'], .brand, .product-brand, .vendor")
            brand = brand_elem.get_text(strip=True) if brand_elem else None
            
            thc = None
            cbd = None
            thc_elem = card.select_one("[data-testid='thc'], .thc, .thc-percent")
            if thc_elem:
                thc_text = thc_elem.get_text(strip=True)
                thc_match = re.search(r"([\d.]+)%?", thc_text)
                if thc_match:
                    try:
                        thc = float(thc_match.group(1))
                    except ValueError:
                        pass
            
            cbd_elem = card.select_one("[data-testid='cbd'], .cbd, .cbd-percent")
            if cbd_elem:
                cbd_text = cbd_elem.get_text(strip=True)
                cbd_match = re.search(r"([\d.]+)%?", cbd_text)
                if cbd_match:
                    try:
                        cbd = float(cbd_match.group(1))
                    except ValueError:
                        pass
            
            weight_elem = card.select_one("[data-testid='weight'], .weight, .product-weight")
            weight = weight_elem.get_text(strip=True) if weight_elem else None
            
            return Deal(
                store_id=self.store_config.id,
                product_id=str(product_id) if product_id else f"unknown_{name}",
                name=name,
                category=category,
                original_price=original_price,
                sale_price=sale_price,
                discount_pct=0.0,
                image_url=image_url,
                product_url=product_url,
                in_stock=True,
                thc_pct=thc,
                cbd_pct=cbd,
                weight=weight,
                brand=brand,
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug(f"Failed to parse product card: {e}")
            return None

    def _parse_product_apollo(self, product: Dict[str, Any], apollo_state: Dict) -> Optional[Deal]:
        try:
            pricing = product.get('pricing', {})
            original_price = pricing.get('originalPrice') or pricing.get('price', 0)
            sale_price = pricing.get('price', 0)
            if original_price == 0 or sale_price == 0:
                return None
            
            images = product.get('images', [])
            image_url = ''
            if images:
                img_ref = images[0]
                if isinstance(img_ref, dict) and '__ref' in img_ref:
                    img_key = img_ref['__ref']
                    img_data = apollo_state.get(img_key, {})
                    image_url = img_data.get('url', '')
                elif isinstance(img_ref, str):
                    img_data = apollo_state.get(img_ref, {})
                    image_url = img_data.get('url', '')
            
            brand = product.get('brand', {})
            brand_name = brand.get('name') if isinstance(brand, dict) else brand
            
            thc = product.get('thc')
            cbd = product.get('cbd')
            if thc:
                try:
                    thc = float(thc.replace('%', ''))
                except (ValueError, AttributeError):
                    thc = None
            if cbd:
                try:
                    cbd = float(cbd.replace('%', ''))
                except (ValueError, AttributeError):
                    cbd = None
            
            return Deal(
                store_id=self.store_config.id,
                product_id=str(product.get('id', '')),
                name=product.get('name', 'Unknown'),
                category=product.get('category', 'Uncategorized'),
                original_price=float(original_price),
                sale_price=float(sale_price),
                discount_pct=0.0,
                image_url=image_url,
                product_url=f"https://dutchie.com{product.get('url', '')}",
                in_stock=product.get('inStock', True),
                thc_pct=thc,
                cbd_pct=cbd,
                weight=product.get('weight'),
                brand=brand_name,
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to parse Apollo product: {e}")
            return None

    GRAPHQL_QUERY = """
    query Menu($dispensarySlug: String!, $filters: MenuFiltersInput) {
        menu(dispensarySlug: $dispensarySlug, filters: $filters) {
            id
            dispensary {
                id
                name
                slug
                logo {
                    url
                }
            }
            categories {
                id
                name
                products {
                    id
                    name
                    brand {
                        name
                    }
                    category
                    pricing {
                        price
                        originalPrice
                        discount
                    }
                    images {
                        url
                        thumbnailUrl
                    }
                    url
                    thc
                    cbd
                    weight
                    inStock
                }
            }
        }
    }
    """

    def _parse_product(self, product: Dict[str, Any], category: str) -> Optional[Deal]:
        try:
            pricing = product.get("pricing", {})
            original_price = pricing.get("originalPrice") or pricing.get("price", 0)
            sale_price = pricing.get("price", 0)

            if original_price == 0 or sale_price == 0:
                return None

            images = product.get("images", [])
            image_url = ""
            if images:
                image_url = images[0].get("thumbnailUrl") or images[0].get("url", "")

            brand = product.get("brand", {})
            brand_name = brand.get("name") if brand else None

            thc = product.get("thc")
            cbd = product.get("cbd")
            if thc:
                try:
                    thc = float(thc.replace("%", ""))
                except (ValueError, AttributeError):
                    thc = None
            if cbd:
                try:
                    cbd = float(cbd.replace("%", ""))
                except (ValueError, AttributeError):
                    cbd = None

            return Deal(
                store_id=self.store_config.id,
                product_id=str(product.get("id", "")),
                name=product.get("name", "Unknown"),
                category=category,
                original_price=float(original_price),
                sale_price=float(sale_price),
                discount_pct=0.0,
                image_url=image_url,
                product_url=f"https://dutchie.com{product.get('url', '')}",
                in_stock=product.get("inStock", True),
                thc_pct=thc,
                cbd_pct=cbd,
                weight=product.get("weight"),
                brand=brand_name,
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to parse product: {e}")
            return None

    def fetch_logo(self) -> Optional[bytes]:
        logo_url = self.store_config.logo_url
        if not logo_url:
            return None
        response = self._make_request("GET", logo_url)
        if response and response.content:
            return response.content
        return None