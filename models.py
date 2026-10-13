from dataclasses import dataclass, field
from datetime import datetime, date, timezone
from typing import Optional, List, Dict, Any
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
class Strain:
    """A cannabis strain profile imported from Leafly.

    `category` is the Leafly phenotype (Hybrid / Sativa / Indica). The THC and
    CBD values are medians of lab-tested samples, so they describe the strain
    generally rather than any one dispensary's cut of it.
    """

    name: str
    slug: str = ""
    leafly_id: Optional[str] = None
    category: str = ""
    thc_pct: Optional[float] = None
    thc_low: Optional[float] = None
    thc_high: Optional[float] = None
    cbd_pct: Optional[float] = None
    cbd_low: Optional[float] = None
    cbd_high: Optional[float] = None
    effects: List[str] = field(default_factory=list)
    flavors: List[str] = field(default_factory=list)
    terpenes: List[str] = field(default_factory=list)
    helps_with: List[str] = field(default_factory=list)
    rating: Optional[float] = None
    review_count: Optional[int] = None
    description: str = ""
    image_url: str = ""
    parents: List[str] = field(default_factory=list)
    children: List[str] = field(default_factory=list)
    source: str = ""
    fetched_at: Optional[datetime] = None

    @property
    def thc_display(self) -> str:
        """Render potency as a range when the bounds differ, else a single value."""
        if self.thc_low is not None and self.thc_high is not None and self.thc_high > self.thc_low:
            return f"{self.thc_low:g}-{self.thc_high:g}%"
        if self.thc_pct is not None:
            return f"{self.thc_pct:g}%"
        if self.thc_high is not None:
            return f"{self.thc_high:g}%"
        return ""

    @property
    def cbd_display(self) -> str:
        if self.cbd_low is not None and self.cbd_high is not None and self.cbd_high > self.cbd_low:
            return f"{self.cbd_low:g}-{self.cbd_high:g}%"
        if self.cbd_pct is not None:
            return f"{self.cbd_pct:g}%"
        if self.cbd_high is not None:
            return f"{self.cbd_high:g}%"
        return ""

    @property
    def strain_type(self) -> str:
        """Normalise the phenotype to a single lowercase keyword for CSS/tests."""
        value = (self.category or "").lower()
        if "sativa" in value and "indica" not in value:
            return "sativa"
        if "indica" in value and "sativa" not in value:
            return "indica"
        if "sativa" in value and "indica" in value:
            return "hybrid"
        if "hybrid" in value:
            return "hybrid"
        return ""

    @property
    def top_effects(self, limit: int = 3) -> List[str]:
        return self.effects[:limit]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "slug": self.slug,
            "leafly_id": self.leafly_id,
            "category": self.category,
            "thc_pct": self.thc_pct,
            "thc_low": self.thc_low,
            "thc_high": self.thc_high,
            "cbd_pct": self.cbd_pct,
            "cbd_low": self.cbd_low,
            "cbd_high": self.cbd_high,
            "effects": list(self.effects),
            "flavors": list(self.flavors),
            "terpenes": list(self.terpenes),
            "helps_with": list(self.helps_with),
            "rating": self.rating,
            "review_count": self.review_count,
            "description": self.description,
            "image_url": self.image_url,
            "parents": list(self.parents),
            "children": list(self.children),
            "source": self.source,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
            "thc_display": self.thc_display,
            "cbd_display": self.cbd_display,
            "strain_type": self.strain_type,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Strain":
        fetched_at = data.get("fetched_at")
        return cls(
            name=data["name"],
            slug=data.get("slug", ""),
            leafly_id=data.get("leafly_id"),
            category=data.get("category", ""),
            thc_pct=data.get("thc_pct"),
            thc_low=data.get("thc_low"),
            thc_high=data.get("thc_high"),
            cbd_pct=data.get("cbd_pct"),
            cbd_low=data.get("cbd_low"),
            cbd_high=data.get("cbd_high"),
            effects=list(data.get("effects", []) or []),
            flavors=list(data.get("flavors", []) or []),
            terpenes=list(data.get("terpenes", []) or []),
            helps_with=list(data.get("helps_with", []) or []),
            rating=data.get("rating"),
            review_count=data.get("review_count"),
            description=data.get("description", ""),
            image_url=data.get("image_url", ""),
            parents=list(data.get("parents", []) or []),
            children=list(data.get("children", []) or []),
            source=data.get("source", ""),
            fetched_at=datetime.fromisoformat(fetched_at) if fetched_at else None,
        )


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
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    in_stock: bool = True
    thc_pct: Optional[float] = None
    cbd_pct: Optional[float] = None
    weight: Optional[str] = None
    brand: Optional[str] = None
    # Name of the Leafly strain matched to this product, resolved after the
    # scrape. It is deliberately excluded from `hash` so enriching a deal does
    # not make previously-seen deals look new to the notifier.
    strain_name: Optional[str] = None

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
    def is_deal(self) -> bool:
        """True when this product is actually discounted.

        The menu holds every product a store carries, not only its sales, so
        this is what separates the two. The notifier is gated on it while the
        dashboard uses it to offer a "deals only" view.
        """
        return (self.discount_pct or 0) > 0

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
            "strain_name": self.strain_name,
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
            strain_name=data.get("strain_name"),
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
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

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
    strain_name: Optional[str]
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
            "strain_name": self.strain_name,
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
            strain_name=data.get("strain_name"),
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