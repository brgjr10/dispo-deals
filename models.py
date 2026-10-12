from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, List
from enum import Enum
import hashlib
import json


class NotificationMode(str, Enum):
    PER_STORE = "per-store"
    PER_PRODUCT = "per-product"


class DealStatus(str, Enum):
    NEW = "NEW"
    CARRYOVER = "CARRYOVER"


@dataclass
class Deal:
    store_id: str
    product_id: str
    name: str
    category: str
    original_price: float
    sale_price: float
    discount_pct: float
    image_url: str
    product_url: str
    detected_at: datetime = field(default_factory=datetime.utcnow)
    in_stock: bool = True
    thc_pct: Optional[float] = None
    cbd_pct: Optional[float] = None
    weight: Optional[str] = None
    brand: Optional[str] = None

    def __post_init__(self):
        if self.original_price > 0:
            self.discount_pct = round(
                ((self.original_price - self.sale_price) / self.original_price) * 100, 1
            )
        else:
            self.discount_pct = 0.0

    @property
    def hash(self) -> str:
        key = f"{self.store_id}|{self.product_id}|{self.sale_price}|{self.discount_pct}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    @property
    def savings(self) -> float:
        return round(self.original_price - self.sale_price, 2)

    def to_dict(self) -> dict:
        return {
            "store_id": self.store_id,
            "product_id": self.product_id,
            "name": self.name,
            "category": self.category,
            "original_price": self.original_price,
            "sale_price": self.sale_price,
            "discount_pct": self.discount_pct,
            "image_url": self.image_url,
            "product_url": self.product_url,
            "detected_at": self.detected_at.isoformat(),
            "in_stock": self.in_stock,
            "thc_pct": self.thc_pct,
            "cbd_pct": self.cbd_pct,
            "weight": self.weight,
            "brand": self.brand,
            "hash": self.hash,
            "savings": self.savings,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Deal":
        deal = cls(
            store_id=data["store_id"],
            product_id=data["product_id"],
            name=data["name"],
            category=data["category"],
            original_price=data["original_price"],
            sale_price=data["sale_price"],
            discount_pct=data.get("discount_pct", 0.0),
            image_url=data["image_url"],
            product_url=data["product_url"],
            in_stock=data.get("in_stock", True),
            thc_pct=data.get("thc_pct"),
            cbd_pct=data.get("cbd_pct"),
            weight=data.get("weight"),
            brand=data.get("brand"),
        )
        if "detected_at" in data:
            deal.detected_at = datetime.fromisoformat(data["detected_at"])
        return deal


@dataclass
class MenuItem:
    deal: Deal
    status: DealStatus = DealStatus.NEW

    def to_dict(self) -> dict:
        return {
            "deal": self.deal.to_dict(),
            "status": self.status.value,
        }


@dataclass
class WeeklySnapshot:
    store_id: str
    week_start: date
    items: List[Deal]
    captured_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "store_id": self.store_id,
            "week_start": self.week_start.isoformat(),
            "items": [item.to_dict() for item in self.items],
            "captured_at": self.captured_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WeeklySnapshot":
        return cls(
            store_id=data["store_id"],
            week_start=date.fromisoformat(data["week_start"]),
            items=[Deal.from_dict(item) for item in data["items"]],
            captured_at=datetime.fromisoformat(data["captured_at"]),
        )


@dataclass
class SeenDeal:
    hash: str
    store_id: str
    product_id: str
    name: str
    category: str
    original_price: float
    sale_price: float
    discount_pct: float
    max_discount_pct: float
    image_url: str
    product_url: str
    in_stock: bool
    thc_pct: Optional[float]
    cbd_pct: Optional[float]
    weight: Optional[str]
    brand: Optional[str]
    first_seen: datetime
    last_notified: datetime
    notify_count: int = 1

    def to_dict(self) -> dict:
        return {
            "hash": self.hash,
            "store_id": self.store_id,
            "product_id": self.product_id,
            "name": self.name,
            "category": self.category,
            "original_price": self.original_price,
            "sale_price": self.sale_price,
            "discount_pct": self.discount_pct,
            "max_discount_pct": self.max_discount_pct,
            "image_url": self.image_url,
            "product_url": self.product_url,
            "in_stock": self.in_stock,
            "thc_pct": self.thc_pct,
            "cbd_pct": self.cbd_pct,
            "weight": self.weight,
            "brand": self.brand,
            "first_seen": self.first_seen.isoformat(),
            "last_notified": self.last_notified.isoformat(),
            "notify_count": self.notify_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SeenDeal":
        return cls(
            hash=data["hash"],
            store_id=data["store_id"],
            product_id=data["product_id"],
            name=data["name"],
            category=data.get("category", ""),
            original_price=data.get("original_price", 0),
            sale_price=data["sale_price"],
            discount_pct=data["discount_pct"],
            max_discount_pct=data.get("max_discount_pct", data["discount_pct"]),
            image_url=data.get("image_url", ""),
            product_url=data.get("product_url", ""),
            in_stock=data.get("in_stock", True),
            thc_pct=data.get("thc_pct"),
            cbd_pct=data.get("cbd_pct"),
            weight=data.get("weight"),
            brand=data.get("brand"),
            first_seen=datetime.fromisoformat(data["first_seen"]),
            last_notified=datetime.fromisoformat(data["last_notified"]),
            notify_count=data.get("notify_count", 1),
        )


@dataclass
class StoreConfig:
    id: str
    name: str
    url: str
    scraper: str
    logo_url: str
    notification_mode: NotificationMode = NotificationMode.PER_STORE
    enabled: bool = True
    webhook_enabled: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "StoreConfig":
        return cls(
            id=data["id"],
            name=data["name"],
            url=data["url"],
            scraper=data["scraper"],
            logo_url=data["logo_url"],
            notification_mode=NotificationMode(data.get("notification_mode", "per-store")),
            enabled=data.get("enabled", True),
            webhook_enabled=data.get("webhook_enabled", False),
        )