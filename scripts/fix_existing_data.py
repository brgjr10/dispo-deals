"""Fix existing seen_deals entries: repair mojibake in brand/category and
re-canonicalize categories so misfiled shelves (e.g. Stündenglass Modül
landing under Puffco) are corrected.

Run inside the running dispo-api/dispo-scraper container where the live
dispo-data volume is mounted at /app/data:

    docker exec -it dispo-api python scripts/fix_existing_data.py

Or against a local copy of the DB:

    python scripts/fix_existing_data.py /path/to/dispo_deals.db
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.categories import canonical_category_named, SUB_SEPARATOR


def repair_mojibake(text: str) -> str:
    """Undo UTF-8 bytes misread as Latin-1 (StÃ¼ndenglass -> Stündenglass).

    Returns the original text unchanged when it isn't mojibake.
    """
    if not text:
        return text
    try:
        repaired = text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    return repaired if repaired != text else text


def fold_text(text: str) -> str:
    """Lowercase and fold common accented/umlaut chars to ASCII for matching.

    So "stündenglass" and "stÃ¼ndenglass" both match "stundenglass".
    """
    if not text:
        return ""
    n = text.lower()
    for a, b in (("ü", "u"), ("ö", "o"), ("ä", "a"), ("ß", "s"), ("è", "e"), ("é", "e")):
        n = n.replace(a, b)
    return n


def main() -> None:
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/dispo_deals.db")
    if not db_path.exists():
        print(f"DB not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        "SELECT rowid, hash, name, category, brand FROM seen_deals "
        "WHERE category IS NOT NULL AND category != '' "
        "   OR brand IS NOT NULL AND brand != ''"
    )
    rows = cur.fetchall()

    fixed_category = 0
    fixed_brand = 0
    fixed_name = 0
    total = len(rows)

    for r in rows:
        rowid = r["rowid"]
        name = r["name"] or ""
        category = r["category"] or ""
        brand = r["brand"] or ""

        new_category = category
        new_brand = brand
        new_name = name

        # --- Repair mojibake first (brand, name), since canonicalization uses
        #     the name to infer a subcategory from the product title. ---
        if name:
            repaired = repair_mojibake(name)
            if repaired != name:
                new_name = repaired
                fixed_name += 1
                name = new_name
        if brand:
            repaired = repair_mojibake(brand)
            if repaired != brand:
                new_brand = repaired
                fixed_brand += 1
                brand = new_brand

        # --- Category: repair mojibake, then re-canonicalize ---
        if category:
            repaired = repair_mojibake(category)
            canonical = canonical_category_named(repaired, name)

            # Correct misfiles: Stündenglass products that were wrongly routed to
            # the Puffco shelf because the bare "modl" alias remapped "Modul" ->
            # "Puffco". Move them onto their own Modul shelf instead.
            main_part = canonical.split(SUB_SEPARATOR, 1)[0]
            folded = fold_text(repair_mojibake(brand) + " " + repair_mojibake(name))
            is_stundenglass = "stundenglass" in folded
            if main_part == "Puffco" and is_stundenglass and "puffco" not in folded:
                sub_part = canonical.split(SUB_SEPARATOR, 1)[1] if SUB_SEPARATOR in canonical else ""
                canonical = "Modul" + (SUB_SEPARATOR + sub_part if sub_part else "")

            if canonical != category:
                new_category = canonical
                fixed_category += 1

        if new_category != category or new_brand != brand or new_name != name:
            cur.execute(
                "UPDATE seen_deals SET category = ?, brand = ?, name = ? WHERE rowid = ?",
                (new_category, new_brand, new_name, rowid),
            )

    conn.commit()
    conn.close()

    print(f"Scanned {total} entries")
    print(f"  categories re-canonicalized: {fixed_category}")
    print(f"  brands mojibake-repaired:    {fixed_brand}")
    print(f"  names mojibake-repaired:     {fixed_name}")


if __name__ == "__main__":
    main()
