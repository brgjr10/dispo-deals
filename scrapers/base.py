from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from models import Deal, StoreConfig
from config import Config


logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    def __init__(self, store_config: StoreConfig, config: Config):
        self.store_config = store_config
        self.config = config
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        # A 429 is the store throttling us, so honour the Retry-After it sends
        # (Shopify and WooCommerce both do) rather than hammering again on our
        # own short timer, which is what exhausts the retries and fails a page.
        # backoff_factor=1 yields ~{0,2,4}s between attempts unless Retry-After
        # asks for longer, so a throttle storm is ridden out instead of given up.
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def _get_headers(self, scraper_key: str) -> Dict[str, str]:
        scraper_config = getattr(self.config.scrapers, scraper_key, {})
        headers = scraper_config.get("headers", {})
        # Allow per-store header overrides via scraper_options
        store_options = getattr(self.store_config, "scraper_options", {}) or {}
        store_headers = store_options.get("headers", {})
        if store_headers:
            headers = {**headers, **store_headers}
        return headers

    @abstractmethod
    def fetch_menu(self) -> List[Deal]:
        pass

    @abstractmethod
    def fetch_logo(self) -> Optional[bytes]:
        pass

    def _make_request(self, method: str, url: str, **kwargs) -> Optional[requests.Response]:
        try:
            timeout = kwargs.pop("timeout", getattr(self.config.scrapers, self.store_config.scraper, {}).get("timeout", 30))
            headers = self._get_headers(self.store_config.scraper)
            headers.update(kwargs.pop("headers", {}))
            response = self.session.request(method, url, headers=headers, timeout=timeout, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            logger.error(f"Request failed for {self.store_config.name}: {e}")
            return None