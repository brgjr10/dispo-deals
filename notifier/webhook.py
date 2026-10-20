import json
import logging
import time
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from models import Deal, MenuItem, StoreConfig, NotificationMode
from utils.diff import WeeklyDiff
from config import Config, WebhookConfig
from utils.images import download_image, resize_image, get_mime_type, hash_url, save_image_cache, load_image_cache

logger = logging.getLogger(__name__)


@dataclass
class WebhookPayload:
    content: Optional[str] = None
    embeds: List[Dict[str, Any]] = None
    attachments: List[Dict[str, Any]] = None

    def __post_init__(self):
        if self.embeds is None:
            self.embeds = []
        if self.attachments is None:
            self.attachments = []

    def to_dict(self) -> Dict[str, Any]:
        result = {}
        if self.content:
            result["content"] = self.content
        if self.embeds:
            result["embeds"] = self.embeds
        if self.attachments:
            result["attachments"] = self.attachments
        return result


class WebhookNotifier:
    def __init__(self, config: Config, storage=None):
        self.config = config
        self.webhook_url = config.webhook_url
        self.webhook_config = config.webhook
        self.session = self._create_session()
        self.storage = storage
        self.image_cache: Dict[str, bytes] = {}
        self._cache_dir = config.images.cache_dir

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        retry_strategy = Retry(
            total=self.webhook_config.max_retries,
            backoff_factor=self.webhook_config.backoff_base_seconds,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def _send(self, payload: WebhookPayload, files: Optional[Dict[str, Any]] = None) -> bool:
        if not self.webhook_url:
            logger.error("Webhook URL not configured")
            return False

        if self.config.dry_run:
            logger.info(f"DRY RUN: Would send webhook with {len(payload.embeds)} embeds")
            return True

        try:
            if files:
                data = {"payload_json": json.dumps(payload.to_dict())}
                response = self.session.post(
                    self.webhook_url,
                    data=data,
                    files=files,
                    timeout=self.webhook_config.timeout,
                )
            else:
                response = self.session.post(
                    self.webhook_url,
                    json=payload.to_dict(),
                    timeout=self.webhook_config.timeout,
                )
            response.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.error(f"Webhook send failed: {e}")
            return False

    def _get_store_logo(self, store: StoreConfig) -> Optional[bytes]:
        cache_key = f"logo:{store.id}"
        if cache_key in self.image_cache:
            return self.image_cache[cache_key]

        # Try SQLite cache first
        if self.storage:
            logo_data = self.storage.get_store_logo(store.id)
            if logo_data:
                self.image_cache[cache_key] = logo_data
                return logo_data

        # Try file cache
        url_hash = hash_url(store.logo_url)
        logo_data = load_image_cache(self._cache_dir, url_hash)
        if logo_data:
            if self.storage:
                mime = get_mime_type(logo_data)
                self.storage.save_store_logo(store.id, logo_data, mime)
            self.image_cache[cache_key] = logo_data
            return logo_data

        # Download fresh
        logo_data = download_image(store.logo_url)
        if logo_data:
            logo_data = resize_image(logo_data, max_width=200, max_size_kb=100)
            # Save to both caches
            if self.storage:
                mime = get_mime_type(logo_data)
                self.storage.save_store_logo(store.id, logo_data, mime)
            save_image_cache(logo_data, self._cache_dir, url_hash)
            self.image_cache[cache_key] = logo_data
        return logo_data

    def _get_product_image(self, deal: Deal) -> Optional[bytes]:
        url_hash = hash_url(deal.image_url)
        cache_key = f"product:{url_hash}"
        if cache_key in self.image_cache:
            return self.image_cache[cache_key]

        # Try SQLite cache first
        if self.storage:
            img_data = self.storage.get_product_image(url_hash)
            if img_data:
                self.image_cache[cache_key] = img_data
                return img_data

        # Try file cache
        img_data = load_image_cache(self._cache_dir, url_hash)
        if img_data:
            if self.storage:
                mime = get_mime_type(img_data)
                self.storage.save_product_image(url_hash, img_data, mime)
            self.image_cache[cache_key] = img_data
            return img_data

        # Download fresh
        img_data = download_image(deal.image_url)
        if img_data:
            img_data = resize_image(img_data, max_width=400, max_size_kb=200)
            # Save to both caches
            if self.storage:
                mime = get_mime_type(img_data)
                self.storage.save_product_image(url_hash, img_data, mime)
            save_image_cache(img_data, self._cache_dir, url_hash)
            self.image_cache[cache_key] = img_data
        return img_data

    def send_store_notification(self, store: StoreConfig, new_deals: List[Deal], weekly_diff: Optional[WeeklyDiff] = None) -> bool:
        if not new_deals:
            return True

        logo_data = self._get_store_logo(store)
        files = {}
        embed = self._build_store_embed(store, new_deals, weekly_diff, logo_data is not None)

        payload = WebhookPayload(embeds=[embed])

        if logo_data:
            files["logo.png"] = ("logo.png", logo_data, get_mime_type(logo_data))
            embed["thumbnail"] = {"url": "attachment://logo.png"}

        return self._send(payload, files if files else None)

    def send_product_notification(self, store: StoreConfig, deal: Deal) -> bool:
        img_data = self._get_product_image(deal)
        files = {}
        embed = self._build_product_embed(store, deal, img_data is not None)

        payload = WebhookPayload(embeds=[embed])

        if img_data:
            ext = "png" if get_mime_type(img_data) == "image/png" else "jpg"
            files[f"product.{ext}"] = (f"product.{ext}", img_data, get_mime_type(img_data))
            embed["image"] = {"url": f"attachment://product.{ext}"}
            embed["thumbnail"] = {"url": f"attachment://product.{ext}"}

        return self._send(payload, files if files else None)

    def _build_store_embed(self, store: StoreConfig, deals: List[Deal], weekly_diff: Optional[WeeklyDiff], has_logo: bool) -> Dict[str, Any]:
        fields = []
        for deal in deals[:10]:
            value = (
                f"**${deal.sale_price:.2f}** ~~${deal.original_price:.2f}~~ "
                f"({deal.discount_pct:.1f}% off)\n"
                f"Category: {deal.category}"
            )
            if deal.brand:
                value += f"\nBrand: {deal.brand}"
            if deal.thc_pct:
                value += f"\nTHC: {deal.thc_pct}%"
            fields.append({
                "name": deal.name[:256],
                "value": value[:1024],
                "inline": True,
            })

        if len(deals) > 10:
            fields.append({
                "name": f"... and {len(deals) - 10} more deals",
                "value": f"[View all on {store.name}]({store.url})",
                "inline": False,
            })

        description = f"Found **{len(deals)}** new deal(s) at {store.name}"
        if weekly_diff:
            description += f"\nWeekly menu: **{weekly_diff.new_count} new**, {weekly_diff.carryover_count} carryover"

        embed = {
            "title": f"🔥 New Deals: {store.name}",
            "description": description,
            "color": 0x3fb950,
            "fields": fields,
            "footer": {
                "text": f"Dispo Deals • {store.name}",
            },
            "timestamp": deals[0].detected_at.isoformat() if deals else None,
        }

        if has_logo:
            embed["author"] = {
                "name": store.name,
                "url": store.url,
                "icon_url": "attachment://logo.png",
            }

        return embed

    def _build_product_embed(self, store: StoreConfig, deal: Deal, has_image: bool) -> Dict[str, Any]:
        fields = [
            {
                "name": "Sale Price",
                "value": f"${deal.sale_price:.2f}",
                "inline": True,
            },
            {
                "name": "Original Price",
                "value": f"${deal.original_price:.2f}",
                "inline": True,
            },
            {
                "name": "Discount",
                "value": f"{deal.discount_pct:.1f}% off",
                "inline": True,
            },
            {
                "name": "Category",
                "value": deal.category,
                "inline": True,
            },
        ]

        if deal.brand:
            fields.append({"name": "Brand", "value": deal.brand, "inline": True})
        if deal.thc_pct:
            fields.append({"name": "THC", "value": f"{deal.thc_pct}%", "inline": True})
        if deal.cbd_pct:
            fields.append({"name": "CBD", "value": f"{deal.cbd_pct}%", "inline": True})
        if deal.weight:
            fields.append({"name": "Weight", "value": deal.weight, "inline": True})

        embed = {
            "title": deal.name[:256],
            "description": f"New deal at **{store.name}**",
            "url": deal.product_url,
            "color": 0x3fb950 if deal.discount_pct >= 20 else 0x3fb950,
            "fields": fields,
            "footer": {
                "text": f"Dispo Deals • {store.name}",
            },
            "timestamp": deal.detected_at.isoformat(),
        }

        if has_image:
            embed["image"] = {"url": "attachment://product.jpg"}

        return embed

    def send_weekly_summary(self, store: StoreConfig, weekly_diff: WeeklyDiff) -> bool:
        if weekly_diff.new_count == 0 and weekly_diff.carryover_count == 0:
            return True

        logo_data = self._get_store_logo(store)
        files = {}

        fields = []
        for item in weekly_diff.new_items[:15]:
            deal = item.deal
            fields.append({
                "name": f"🆕 {deal.name[:256]}",
                "value": f"${deal.sale_price:.2f} ~~${deal.original_price:.2f}~~ ({deal.discount_pct:.1f}% off)",
                "inline": True,
            })

        for item in weekly_diff.carryover_items[:10]:
            deal = item.deal
            fields.append({
                "name": f"📦 {deal.name[:256]}",
                "value": f"${deal.sale_price:.2f} ~~${deal.original_price:.2f}~~ ({deal.discount_pct:.1f}% off)",
                "inline": True,
            })

        embed = {
            "title": f"📋 Weekly Menu Update: {store.name}",
            "description": f"**{weekly_diff.new_count} new items**, {weekly_diff.carryover_count} carryover from last week",
            "color": 0x3fb950,
            "fields": fields,
            "footer": {"text": f"Dispo Deals • {store.name}"},
        }

        if logo_data:
            files["logo.png"] = ("logo.png", logo_data, get_mime_type(logo_data))
            embed["thumbnail"] = {"url": "attachment://logo.png"}

        payload = WebhookPayload(embeds=[embed])
        return self._send(payload, files if files else None)