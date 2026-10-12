import json
import re
import os
import random
import requests
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse, urljoin
import cloudscraper
from bs4 import BeautifulSoup

from scrapers.base import BaseScraper
from models import Deal, StoreConfig
from config import Config
from utils.categories import canonical_category

# Dutchie's live storefront menu comes from the consumer GraphQL API. The
# dutchie.com endpoint exposes the identical schema and is a safe fallback.
DEFAULT_GRAPHQL_ENDPOINTS = [
    "https://api.dutchie.com/graphql",
    "https://dutchie.com/graphql",
]

# Dutchie rate-limits with intermittent 403s; retry transient failures with
# jittered exponential backoff before giving up on a request. The full run
# issues hundreds of paginated requests, so a 403 burst is expected.
GRAPHQL_MAX_ATTEMPTS = 5
GRAPHQL_BACKOFF_SECONDS = 2

# Dutchie exposes a product photo as a 32-hex object hash. It arrives on one of
# several hosts (CDN, legacy S3 bucket, or path-only), so match on the hash
# rather than the host. Anything else is a category key such as "flower".
DUTCHIE_IMAGE_HASH_RE = re.compile(r'/([0-9a-f]{32})(?:[/?]|$)')
DUTCHIE_IMAGE_HOST_RE = re.compile(r'(?:dutchie-images[./]|images\.dutchie\.com/)')

# Products without their own photo get Dutchie's category stock photo instead,
# so every card still shows a relevant image.
CATEGORY_STOCK_PHOTOS = {
    "flower": "https://images.dutchie.com/category-stock-photos/flower/flower-1.png",
    "pre-roll": "https://images.dutchie.com/category-stock-photos/pre-rolls/pre-rolls-1.png",
    "preroll": "https://images.dutchie.com/category-stock-photos/pre-rolls/pre-rolls-1.png",
    "pre-rolls": "https://images.dutchie.com/category-stock-photos/pre-rolls/pre-rolls-1.png",
    "vaporizer": "https://images.dutchie.com/category-stock-photos/vaporizers/vaporizers-1.png",
    "vaporizers": "https://images.dutchie.com/category-stock-photos/vaporizers/vaporizers-1.png",
    "edible": "https://images.dutchie.com/category-stock-photos/edibles/edibles-1.png",
    "edibles": "https://images.dutchie.com/category-stock-photos/edibles/edibles-1.png",
    "tincture": "https://images.dutchie.com/category-stock-photos/tinctures/tinctures-1.png",
    "tinctures": "https://images.dutchie.com/category-stock-photos/tinctures/tinctures-1.png",
    "concentrate": "https://images.dutchie.com/category-stock-photos/concentrates/concentrates-1.png",
    "concentrates": "https://images.dutchie.com/category-stock-photos/concentrates/concentrates-1.png",
    "topical": "https://images.dutchie.com/category-stock-photos/topicals/topicals-1.png",
    "topicals": "https://images.dutchie.com/category-stock-photos/topicals/topicals-1.png",
}


def normalise_category_key(value) -> str:
    """Normalise a Dutchie category string to a CATEGORY_STOCK_PHOTOS key.

    Handles the cases Dutchie actually emits, e.g. "Flower", "flower",
    "Pre-Rolls", "pre-rolls", "Concentrates".
    """
    if not value or not isinstance(value, str):
        return ""
    return value.strip().lower().replace(" ", "-").replace("_", "-")


def stock_photo_for_category(value) -> str:
    """Return Dutchie's category stock photo for a product type, or ''."""
    key = normalise_category_key(value)
    if not key:
        return ""

    if key in CATEGORY_STOCK_PHOTOS:
        return CATEGORY_STOCK_PHOTOS[key]

    # Try the singular/plural variants Dutchie's type values actually use,
    # e.g. "Pre-Rolls" vs "Pre-Roll", "Concentrates" vs "Concentrate".
    for variant in {key.rstrip('s'), key + 's', key.replace('-', '')}:
        if variant in CATEGORY_STOCK_PHOTOS:
            return CATEGORY_STOCK_PHOTOS[variant]
    return ""


def resolve_dutchie_image(url: str) -> str:
    """Resolve a Dutchie image reference to a usable URL, or '' if there is none.

    Real product photos arrive as a 32-hex object hash on one of several hosts;
    those are normalised onto the CDN. Products without a photo carry a
    category key ("flower") which maps to Dutchie's category stock photo, so
    every card still shows a relevant picture.
    """
    if not url or not isinstance(url, str):
        return ""

    image_hash = extract_dutchie_image_hash(url)
    if image_hash:
        return f"https://images.dutchie.com/{image_hash}?w=400&q=80&fm=jpg"

    return category_stock_photo(url)


def category_stock_photo(url: str) -> str:
    """Map a category-key or existing stock-photo URL onto a stock photo URL."""
    clean = str(url).split('?')[0].rstrip('/').lower()
    if not clean:
        return ""

    if 'category-stock-photos/' in clean:
        # Already a stock photo path: recover the category from it.
        category = clean.split('category-stock-photos/', 1)[1].split('/')[0]
    else:
        # Bare category key ("flower"), or a CDN path ending in the key.
        category = clean.split('/')[-1]

    return CATEGORY_STOCK_PHOTOS.get(category, "")


def extract_dutchie_image_hash(url: str) -> str:
    """Return the 32-char image object hash from any Dutchie image URL form."""
    if not url or not isinstance(url, str):
        return ""
    match = DUTCHIE_IMAGE_HASH_RE.search(url)
    if not match:
        return ""
    # Guard against matching a hex path segment on an unrelated host.
    if not DUTCHIE_IMAGE_HOST_RE.search(url):
        return ""
    return match.group(1)


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
        # Dutchie's live consumer menu is served from api.dutchie.com; the
        # dutchie.com endpoint keeps the same schema and works as a fallback.
        configured = config.scrapers.dutchie.get(
            "graphql_endpoint", DEFAULT_GRAPHQL_ENDPOINTS[0]
        )
        self.graphql_endpoint = configured
        self.graphql_endpoints = self._build_endpoints(configured)
        
        # Initialize Cloudflare bypass
        self.flaresolverr_url = os.environ.get('FLARESOLVERR_URL')
        if self.flaresolverr_url:
            self.session = requests.Session()
            self.scraper = None
        else:
            self.scraper = cloudscraper.create_scraper(browser='chrome')
        # The JSON GraphQL API is not Cloudflare-challenged, so it goes through
        # a plain session. Routing it through FlareSolverr (as the HTML fallback
        # paths do) is both much slower and unreliable for JSON responses.
        self.api_session = requests.Session()
        # Resolved lazily and cached: each lookup costs a rate-limited request.
        self._dispensary_id = None

    @staticmethod
    def _build_endpoints(configured: str) -> List[str]:
        """Order endpoints so the configured one is tried first."""
        endpoints = [configured] + [
            e for e in DEFAULT_GRAPHQL_ENDPOINTS if e != configured
        ]
        return endpoints

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
        """Fetch products from Dutchie's consumer GraphQL API.

        Dutchie's storefront is a client-side SPA, so the menu used to be
        embedded in the initial HTML. It no longer is; the live storefront
        instead resolves the dispensary by cName and pages through
        `filteredProducts`. This mirrors that flow so we get real products
        with real image URLs and real pricing.
        """
        import logging
        logger = logging.getLogger(__name__)

        dispensary_id = self._resolve_dispensary_id()
        if not dispensary_id:
            logger.warning(f"Could not resolve dispensary id for slug: {self.dispensary_slug}")
            return []

        deals: List[Deal] = []
        page = 1
        per_page = 100
        max_pages = 25

        while page <= max_pages:
            batch, products_seen = self._fetch_products_page(dispensary_id, page, per_page)
            if products_seen == 0:
                break
            deals.extend(batch)
            logger.debug(
                f"Fetched page {page}: {products_seen} products, "
                f"{len(batch)} deals (total deals {len(deals)})"
            )
            if products_seen < per_page:
                break
            page += 1

        logger.info(
            f"GraphQL fetch complete: {len(deals)} deals for {self.store_config.name}"
        )
        return deals

    def _resolve_dispensary_id(self) -> Optional[str]:
        """Resolve the cName slug to Dutchie's internal dispensary id.

        Cached because every call costs a request, and Dutchie rate-limits.
        """
        import logging
        logger = logging.getLogger(__name__)

        if self._dispensary_id:
            return self._dispensary_id

        response = self._graphql_request(
            self.DISPENSARY_QUERY,
            {"cNameOrID": self.dispensary_slug},
        )
        if not response:
            return None

        dispensaries = response.get("data", {}).get("filteredDispensaries") or []
        if not dispensaries:
            return None

        # Prefer an exact cName match so a search-like slug cannot resolve the wrong store.
        target = self.dispensary_slug.lower()
        for candidate in dispensaries:
            if str(candidate.get("cName", "")).lower() == target:
                return candidate.get("id")

        return dispensaries[0].get("id")

    def _fetch_products_page(self, dispensary_id: str, page: int, per_page: int) -> tuple:
        """Fetch and parse a single page of products for a dispensary.

        Returns (deals, products_seen). The product count is what drives
        pagination, because most products are not deals.
        """
        response = self._graphql_request(
            self.PRODUCTS_QUERY,
            {
                "productsFilter": {"dispensaryId": dispensary_id},
                "page": page,
                "perPage": per_page,
            },
        )
        if not response:
            return [], 0

        result = response.get("data", {}).get("filteredProducts")
        if not result:
            return [], 0

        products = result.get("products", []) or []
        deals: List[Deal] = []
        for product in products:
            deal = self._parse_dutchie_product(product)
            if deal:
                deals.append(deal)
        return deals, len(products)

    def _graphql_request(self, query: str, variables: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """POST a GraphQL document to Dutchie's consumer API.

        Dutchie rate-limits with intermittent 403s, so transient failures are
        retried with exponential backoff before giving up.
        """
        import logging
        import time
        logger = logging.getLogger(__name__)

        payload = {"query": query, "variables": variables}
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Origin': 'https://dutchie.com',
            'Referer': f'https://dutchie.com/stores/{self.dispensary_slug}',
        }
        timeout = getattr(
            self.config.scrapers, self.store_config.scraper, {}
        ).get("timeout", 30)
        retry_statuses = {403, 408, 425, 429, 500, 502, 503, 504}

        last_error: Optional[str] = None
        for attempt in range(GRAPHQL_MAX_ATTEMPTS):
            for endpoint in self.graphql_endpoints:
                try:
                    response = self.api_session.post(
                        endpoint, json=payload, headers=headers, timeout=timeout
                    )
                    status = response.status_code
                    if status == 200:
                        data = response.json()
                        if isinstance(data, dict) and "errors" not in data:
                            return data
                        last_error = f"GraphQL errors: {str(data)[:200]}"
                        continue
                    last_error = f"HTTP {status}"
                    # Non-transient failures (e.g. 400) will not improve on retry.
                    if status in retry_statuses:
                        break
                    continue
                except Exception as e:
                    last_error = str(e)
                    continue

            if attempt < GRAPHQL_MAX_ATTEMPTS - 1:
                # Jitter avoids hammering in lockstep with other clients.
                delay = GRAPHQL_BACKOFF_SECONDS * (2 ** attempt)
                delay += random.uniform(0, delay * 0.25)
                logger.debug(
                    f"GraphQL attempt {attempt + 1}/{GRAPHQL_MAX_ATTEMPTS} failed "
                    f"({last_error}); retrying in {delay:.1f}s"
                )
                time.sleep(delay)

        if last_error:
            logger.warning(f"GraphQL request failed on all endpoints: {last_error}")
        return None

    def _parse_dutchie_product(self, product: Dict[str, Any]) -> Optional[Deal]:
        """Convert a Dutchie `Products` record into a Deal.

        Dutchie exposes parallel `recPrices` / `recSpecialPrices` arrays (one
        entry per variant). A deal exists when a special price undercuts the
        regular price for the same variant, but the record is still returned
        when it does not: the menu is meant to hold every product a store
        carries, not only the discounted ones, so the dashboard can browse the
        whole catalogue and filter to deals itself.
        """
        try:
            name = product.get("Name") or product.get("name") or ""
            if not name:
                return None

            rec_prices = self._as_float_list(product.get("recPrices"))
            special_prices = self._as_float_list(product.get("recSpecialPrices"))
            if not rec_prices:
                return None

            original_price = 0.0
            sale_price = 0.0

            if special_prices:
                # Pick the variant with the deepest advertised discount.
                best = None
                for idx, regular in enumerate(rec_prices):
                    special = special_prices[idx] if idx < len(special_prices) else None
                    if special is None or special <= 0 or regular <= 0:
                        continue
                    if special >= regular:
                        continue
                    pct = ((regular - special) / regular) * 100
                    if best is None or pct > best[0]:
                        best = (pct, regular, special)
                if best:
                    original_price = best[1]
                    sale_price = best[2]
                else:
                    # Priced but not discounted: fall through with a 0% discount
                    # so the product still appears in the menu.
                    original_price = rec_prices[0]
                    sale_price = rec_prices[0]
            else:
                # No special pricing on this product, so there is no discount.
                original_price = rec_prices[0]
                sale_price = rec_prices[0]

            image_url = self._extract_product_image_url(product)
            brand = self._extract_brand_name(product)
            thc_pct = self._extract_potency(product.get("THCContent"), product.get("THC"))
            cbd_pct = self._extract_potency(product.get("CBDContent"), product.get("CBD"))

            category = product.get("type") or product.get("_id") and "" or "Uncategorized"
            subcategory = product.get("subcategory") or ""
            if subcategory:
                category = f"{category} · {subcategory}" if category != "Uncategorized" else subcategory
            # Dutchie is already consistent, but a store reporting "Concentrates"
            # would otherwise sit next to the canonical "Concentrate" shelf.
            category = canonical_category(category)

            options = product.get("Options") or []
            weight = options[0] if options and options[0] and options[0] != "N/A" else None

            product_id = str(product.get("id") or product.get("_id") or "")
            if not product_id:
                return None

            return Deal(
                store_id=self.store_config.id,
                product_id=product_id,
                name=name,
                category=category or "Uncategorized",
                original_price=float(original_price),
                sale_price=float(sale_price),
                discount_pct=0.0,
                image_url=image_url,
                product_url=f"https://dutchie.com/stores/{self.dispensary_slug}/products/{product_id}",
                in_stock=True,
                thc_pct=thc_pct,
                cbd_pct=cbd_pct,
                weight=weight,
                brand=brand,
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug(f"Failed to parse Dutchie product: {e}")
            return None

    @staticmethod
    def _as_float_list(value: Any) -> List[Optional[float]]:
        """Normalise a price array into floats, tolerating junk entries."""
        if not isinstance(value, list):
            return []
        parsed: List[Optional[float]] = []
        for item in value:
            try:
                parsed.append(float(item))
            except (TypeError, ValueError):
                parsed.append(None)
        return parsed

    def _extract_product_image_url(self, product: Dict[str, Any]) -> str:
        """Resolve the best product image URL.

        Prefers a real product photo. Products without one fall back to
        Dutchie's category stock photo, derived from the image reference when
        Dutchie supplies one, otherwise from the product's own type.
        """
        candidates: List[str] = []

        images = product.get("images")
        if isinstance(images, list):
            for image in images:
                if isinstance(image, dict) and image.get("url"):
                    if image.get("active") is False:
                        continue
                    candidates.append(image["url"])

        primary = product.get("Image")
        if isinstance(primary, str) and primary:
            candidates.append(primary)

        for url in candidates:
            resolved = resolve_dutchie_image(url)
            if resolved:
                return resolved

        # No image reference at all: fall back to the product's own category.
        for hint in (product.get("subcategory"), product.get("type")):
            stock = stock_photo_for_category(hint)
            if stock:
                return stock

        return ""

    @staticmethod
    def _extract_brand_name(product: Dict[str, Any]) -> Optional[str]:
        brand = product.get("brand")
        if isinstance(brand, dict):
            brand_name = brand.get("name")
            if brand_name:
                return brand_name
        brand_name = product.get("brandName")
        return brand_name or None

    @staticmethod
    def _extract_potency(content: Any, fallback: Any) -> Optional[float]:
        """Read a potency *percentage*, ignoring milligram-based readings.

        Two subtleties are handled here:
        - Edibles report total THC in milligrams (e.g. a 100mg 10-pack), which
          is not a percentage, so those values are dropped rather than
          mislabelled.
        - Potency is often a min/max range like [0, 21], where 0 is just the
          floor of the range. The meaningful value is the upper bound, and a
          result of 0 means "no potency recorded", so it is dropped.
        """
        if isinstance(content, dict):
            # Only percentages can be shown as a %
            if str(content.get("unit", "")).upper() not in ("PERCENTAGE", "%", ""):
                return None
            range_values = content.get("range")
            if isinstance(range_values, list):
                numeric = [
                    float(v) for v in range_values
                    if isinstance(v, (int, float)) and not isinstance(v, bool)
                ]
                if numeric:
                    return round(max(numeric), 1) or None
            value = content.get("value")
            if value is not None:
                try:
                    return round(float(value), 1) or None
                except (TypeError, ValueError):
                    pass
        if isinstance(fallback, (int, float)) and not isinstance(fallback, bool):
            return round(float(fallback), 1) or None
        if isinstance(fallback, str):
            try:
                return round(float(fallback.replace("%", "").strip()), 1) or None
            except ValueError:
                return None
        return None

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

    DISPENSARY_QUERY = """
    query Dispensary($cNameOrID: String) {
        filteredDispensaries(filter: {cNameOrID: $cNameOrID}) {
            id
            name
            cName
        }
    }
    """

    PRODUCTS_QUERY = """
    query FilteredProducts($productsFilter: productsFilterInput!, $page: Int, $perPage: Int) {
        filteredProducts(filter: $productsFilter, page: $page, perPage: $perPage) {
            products {
                id
                _id
                Name
                brandName
                brand {
                    name
                    imageUrl
                }
                Image
                images {
                    url
                    active
                }
                type
                subcategory
                THC
                THCContent {
                    unit
                    range
                }
                CBD
                CBDContent {
                    unit
                    range
                }
                Options
                recPrices
                recSpecialPrices
                special
            }
            queryInfo {
                totalCount
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