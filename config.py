import os
import yaml
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from pathlib import Path

from models import StoreConfig, NotificationMode


@dataclass
class ScraperConfig:
    dutchie: Dict[str, Any] = field(default_factory=dict)
    klutch: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ImageConfig:
    cache_dir: str = "./cache/images"
    max_width: int = 800
    max_size_kb: int = 500
    formats: List[str] = field(default_factory=lambda: ["jpg", "jpeg", "png", "webp"])


@dataclass
class DeduplicationConfig:
    hash_fields: List[str] = field(default_factory=lambda: ["store_id", "product_id", "sale_price", "discount_pct"])
    re_notify_on_deeper_discount: bool = True


@dataclass
class WeeklyMenuConfig:
    snapshot_day: int = 0
    min_items_for_snapshot: int = 10


@dataclass
class WebhookConfig:
    max_retries: int = 3
    backoff_base_seconds: int = 5
    timeout: int = 15


@dataclass
class Config:
    schedule_cron: str = "0 */6 * * *"
    webhook_url: str = ""
    mode: NotificationMode = NotificationMode.PER_STORE
    dry_run: bool = False
    log_level: str = "INFO"
    stores: List[StoreConfig] = field(default_factory=list)
    scrapers: ScraperConfig = field(default_factory=ScraperConfig)
    images: ImageConfig = field(default_factory=ImageConfig)
    deduplication: DeduplicationConfig = field(default_factory=DeduplicationConfig)
    weekly_menu: WeeklyMenuConfig = field(default_factory=WeeklyMenuConfig)
    webhook: WebhookConfig = field(default_factory=WebhookConfig)

    @classmethod
    def load(cls, path: str = "config.yaml") -> "Config":
        with open(path, "r") as f:
            data = yaml.safe_load(f)

        if not data:
            return cls()

        webhook_url = data.get("webhook_url") or os.environ.get("WEBHOOK_URL", "")

        stores = [StoreConfig.from_dict(s) for s in data.get("stores", []) if s.get("enabled", True)]

        return cls(
            schedule_cron=data.get("schedule_cron", "0 */6 * * *"),
            webhook_url=webhook_url,
            mode=NotificationMode(data.get("mode", "per-store")),
            dry_run=data.get("dry_run", False),
            log_level=data.get("log_level", "INFO"),
            stores=stores,
            scrapers=ScraperConfig(**data.get("scrapers", {})),
            images=ImageConfig(**data.get("images", {})),
            deduplication=DeduplicationConfig(**data.get("deduplication", {})),
            weekly_menu=WeeklyMenuConfig(**data.get("weekly_menu", {})),
            webhook=WebhookConfig(**data.get("webhook", {})),
        )

    def get_store(self, store_id: str) -> Optional[StoreConfig]:
        for store in self.stores:
            if store.id == store_id:
                return store
        return None

    def get_enabled_stores(self) -> List[StoreConfig]:
        return [s for s in self.stores if s.enabled]

    def get_webhook_stores(self) -> List[StoreConfig]:
        return [s for s in self.stores if s.enabled and s.webhook_enabled]