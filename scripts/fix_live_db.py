"""Deterministic fix for the live dispo_data DB.

Repairs mojibake (UTF-8 read as Latin-1, e.g. StÃ¼ndenglass -> Stündenglass)
and re-canonicalizes categories/brands in both seen_deals and
weekly_snapshots.items (the table /api/menu actually serves).

Moves Stündenglass products off the wrongly-assigned Puffco shelf (caused by
the old bare "modl" -> Puffco alias) onto their own Modul shelf.

Run inside the dispo-api container:

    docker exec -e PYTHONPATH=/app dispo-api python /tmp/fix_live_db.py /app/data/dispo_deals.db
"""

import json
import re
import sqlite3
import sys
from pathlib import Path

DB = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/app/data/dispo_deals.db")
conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row
cur = conn.cursor()

sys.path.insert(0, "/app")
from utils.categories import canonical_category_named, SUB_SEPARATOR, main_category

# Patch _vape_remap: head-shop glass filed under "Concentrate" routes to Gear
# automatically; dispos keep Concentrate/Vaporizers (item checks there).
import types as _types  # noqa: E402
from utils import categories as _cat  # noqa: E402

_CAP_NAME_RE = re.compile(
    r"\b(carb|bubble|spinner|spin|directional|slurper|dab|marble|maria|marios|terp|banger)\s+cap\b",
    re.IGNORECASE,
)


def _vape_remap_fixed(canonical, store_id=None, brand=None, name=""):
    if canonical not in ("Vaporizers", "Concentrate"):
        return canonical
    # A product whose title states its I/S/H type is cannabis no matter what
    # shelf or brand it carries; the store's own label beats both.
    if _cat._strain_type_from_name(name):
        return canonical
    if _cat._is_hardware_brand(brand):
        return "Gear"
    if store_id is None:
        return canonical
    scraper = _cat._store_scraper(store_id)
    if scraper is None:
        return canonical
    if scraper in _cat.CANNABIS_VAPE_SCRAPERS:
        return canonical  # dispo: cannabis concentrates/vapes stay
    return "Gear"  # head shop: hardware/glass → Gear


_cat._vape_remap = _vape_remap_fixed

# Patch CATEGORY_RELOCATIONS: glass accessories filed under Accessories → Glass → Gear
_cat.CATEGORY_RELOCATIONS.update({
    _cat.category_key("Accessories · cap"): "Glass · caps",
    _cat.category_key("Accessories · caps"): "Glass · caps",
    _cat.category_key("Accessories · banger cap"): "Glass · banger caps",
    _cat.category_key("Accessories · spinner cap"): "Glass · spinner caps",
    _cat.category_key("Accessories · carb cap"): "Glass · carb caps",
    _cat.category_key("Accessories · directional cap"): "Glass · directional caps",
    _cat.category_key("Accessories · dab cap"): "Glass · dab caps",
    _cat.category_key("Accessories · bubble cap"): "Glass · bubble caps",
    _cat.category_key("Accessories · banger"): "Glass · bangers",
    _cat.category_key("Accessories · nail"): "Glass · nails",
    _cat.category_key("Accessories · bucket"): "Glass · bangers",
})


def repair_mojibake(text):
    if not text:
        return text
    try:
        repaired = text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    return repaired if repaired != text else text


def fold(text):
    if not text:
        return ""
    n = text.lower()
    for a, b in (("ü", "u"), ("ö", "o"), ("ä", "a"), ("ß", "s"), ("ã¼", "u")):
        n = n.replace(a, b)
    return n


def fix_item(item):
    """Return (changed, item) with mojibake repaired and category canonicalised."""
    changed = False
    name = repair_mojibake(item.get("name") or "")
    brand = repair_mojibake(item.get("brand") or "")
    category = repair_mojibake(item.get("category") or "")

    if name != (item.get("name") or ""):
        item["name"] = name
        changed = True
    if brand != (item.get("brand") or ""):
        item["brand"] = brand
        changed = True

    canon = canonical_category_named(category, name, item.get("store_id"), brand)
    # A cap (carb cap, bubble cap, slurper cap, ...) is always a glass
    # accessory; route it onto Gear wherever the store filed it.
    if _CAP_NAME_RE.search(name) and canon.split(SUB_SEPARATOR, 1)[0] != "Gear":
        canon = "Gear"
    main_part = canon.split(SUB_SEPARATOR, 1)[0]
    folded = fold(brand + " " + name)
    if (
        main_part == "Puffco"
        and "stundenglass" in folded
        and "puffco" not in folded
    ):
        sub_part = canon.split(SUB_SEPARATOR, 1)[1] if SUB_SEPARATOR in canon else ""
        canon = "Modul" + (SUB_SEPARATOR + sub_part if sub_part else "")

    if canon != category:
        item["category"] = canon
        changed = True

    return changed, item


stats = {"seen_deals": 0, "snapshots": 0, "snapshot_items": 0}

# --- seen_deals ---
cur.execute(
    "SELECT rowid, store_id, name, category, brand FROM seen_deals "
    "WHERE category IS NOT NULL AND category != '' "
    "   OR brand IS NOT NULL AND brand != '' "
    "   OR name IS NOT NULL AND name != ''"
)
for r in cur.fetchall():
    rowid = r["rowid"]
    store_id = r["store_id"]
    name = repair_mojibake(r["name"] or "")
    brand = repair_mojibake(r["brand"] or "")
    category = repair_mojibake(r["category"] or "")
    canon = canonical_category_named(category, name, store_id, brand)
    # A cap (carb cap, bubble cap, slurper cap, ...) is always a glass
    # accessory; route it onto Gear wherever the store filed it.
    if _CAP_NAME_RE.search(name) and canon.split(SUB_SEPARATOR, 1)[0] != "Gear":
        canon = "Gear"
    main_part = canon.split(SUB_SEPARATOR, 1)[0]
    folded = fold(brand + " " + name)
    if main_part == "Puffco" and "stundenglass" in folded and "puffco" not in folded:
        sub_part = canon.split(SUB_SEPARATOR, 1)[1] if SUB_SEPARATOR in canon else ""
        canon = "Modul" + (SUB_SEPARATOR + sub_part if sub_part else "")
    if name != (r["name"] or "") or brand != (r["brand"] or "") or canon != (r["category"] or ""):
        cur.execute(
            "UPDATE seen_deals SET name = ?, brand = ?, category = ? WHERE rowid = ?",
            (name, brand, canon, rowid),
        )
        stats["seen_deals"] += 1

# --- weekly_snapshots (what /api/menu actually serves) ---
cur.execute("SELECT id, items FROM weekly_snapshots WHERE items IS NOT NULL AND items != ''")
for r in cur.fetchall():
    try:
        items = json.loads(r["items"])
    except (json.JSONDecodeError, TypeError):
        continue
    snap_changed = False
    for item in items:
        if not isinstance(item, dict):
            continue
        changed, item = fix_item(item)
        if changed:
            snap_changed = True
            stats["snapshot_items"] += 1
    if snap_changed:
        cur.execute(
            "UPDATE weekly_snapshots SET items = ? WHERE id = ?",
            (json.dumps(items, ensure_ascii=False), r["id"]),
        )
        stats["snapshots"] += 1

conn.commit()
conn.close()

print(f"seen_deals rows fixed:     {stats['seen_deals']}")
print(f"snapshots fixed:           {stats['snapshots']}")
print(f"snapshot items fixed:      {stats['snapshot_items']}")
