from typing import List, Dict, Set, Tuple
from dataclasses import dataclass

from models import Deal, MenuItem, DealStatus


@dataclass
class WeeklyDiff:
    store_id: str
    new_items: List[MenuItem]
    carryover_items: List[MenuItem]
    removed_items: List[Deal]
    total_current: int
    total_previous: int

    @property
    def new_count(self) -> int:
        return len(self.new_items)

    @property
    def carryover_count(self) -> int:
        return len(self.carryover_items)

    @property
    def removed_count(self) -> int:
        return len(self.removed_items)


def compute_weekly_diff(current: List[Deal], previous: List[Deal]) -> WeeklyDiff:
    prev_keys: Set[Tuple[str, str]] = set()
    prev_by_key: Dict[Tuple[str, str], Deal] = {}

    for deal in previous:
        key = (deal.name.strip().lower(), deal.category.strip().lower())
        prev_keys.add(key)
        prev_by_key[key] = deal

    curr_keys: Set[Tuple[str, str]] = set()
    new_items: List[MenuItem] = []
    carryover_items: List[MenuItem] = []

    for deal in current:
        key = (deal.name.strip().lower(), deal.category.strip().lower())
        curr_keys.add(key)

        if key in prev_keys:
            carryover_items.append(MenuItem(deal=deal, status=DealStatus.CARRYOVER))
        else:
            new_items.append(MenuItem(deal=deal, status=DealStatus.NEW))

    removed_keys = prev_keys - curr_keys
    removed_items = [prev_by_key[key] for key in removed_keys]

    return WeeklyDiff(
        store_id=current[0].store_id if current else "",
        new_items=new_items,
        carryover_items=carryover_items,
        removed_items=removed_items,
        total_current=len(current),
        total_previous=len(previous),
    )


def filter_deals_by_category(deals: List[Deal], categories: List[str]) -> List[Deal]:
    if not categories:
        return deals
    cat_set = {c.strip().lower() for c in categories}
    return [d for d in deals if d.category.strip().lower() in cat_set]


def filter_deals_by_discount(deals: List[Deal], min_discount: float = 0.0) -> List[Deal]:
    return [d for d in deals if d.discount_pct >= min_discount]


def sort_deals(deals: List[Deal], by: str = "discount", descending: bool = True) -> List[Deal]:
    key_funcs = {
        "discount": lambda d: d.discount_pct,
        "price": lambda d: d.sale_price,
        "savings": lambda d: d.savings,
        "name": lambda d: d.name.lower(),
        "category": lambda d: d.category.lower(),
    }
    key_func = key_funcs.get(by, key_funcs["discount"])
    return sorted(deals, key=key_func, reverse=descending)