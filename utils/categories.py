"""Canonical dispensary category names.

Every store names its shelves differently. Dutchie reports ``Concentrate``,
Klutch scrapes ``/collections/concentrates`` and calls it ``Concentrates``, and
a stale snapshot carried ``Vapes`` where the live data says ``Vaporizers``.
Left alone, the same shelf shows up as two rows in the sidebar and splits the
"Deals only" category breakdown.

The canonical forms below are the ones the live Dutchie data uses, so nothing
that is already consistent gets renamed.
"""

import re

# Anything not listed is left untouched rather than guessed at.
CATEGORY_ALIASES = {
    # Concentrate and every synonym Dutchie or Klutch uses for the same shelf.
    "concentrate": "Concentrate",
    "concentrates": "Concentrate",
    "extract": "Concentrate",
    "extracts": "Concentrate",
    "hash": "Concentrate",
    # Vaporizers.
    "vaporizers": "Vaporizers",
    "vaporizer": "Vaporizers",
    "vapes": "Vaporizers",
    "vape": "Vaporizers",
    "carts": "Vaporizers",
    "cartridges": "Vaporizers",
    # Edibles.
    "edible": "Edible",
    "edibles": "Edible",
    # Pre-rolls, which are only ever spelled inconsistently.
    "pre-roll": "Pre-Rolls",
    "pre-rolls": "Pre-Rolls",
    "preroll": "Pre-Rolls",
    "prerolls": "Pre-Rolls",
    # Flower.
    "flower": "Flower",
    "flowers": "Flower",
    # Tinctures.
    "tincture": "Tincture",
    "tinctures": "Tincture",
    # Topicals, which the live data keeps plural.
    "topical": "Topicals",
    "topicals": "Topicals",
    # Accessories.
    "accessory": "Accessories",
    "accessories": "Accessories",
}

SUB_SEPARATOR = " \u00b7 "

_KEY_RE = re.compile(r"[^a-z0-9]+")


def category_key(name: str) -> str:
    """Comparison key for a category name, ignoring spacing and punctuation."""
    return _KEY_RE.sub("", (name or "").lower())


def main_category(category: str) -> str:
    """The top-level category, with any subcategory removed."""
    return (category or "").split(SUB_SEPARATOR.strip(), 1)[0].strip()


def sub_category(category: str) -> str:
    """The subcategory part after the separator, or an empty string."""
    parts = (category or "").split(SUB_SEPARATOR.strip(), 1)
    return parts[1].strip() if len(parts) > 1 else ""


# Subcategory names that mean the same shelf but are written differently by
# different stores. Keyed by (main category key, subcategory key) so a rename
# can never leak across shelves - "infused" under Pre-Rolls has nothing to do
# with "infused-flower" under Concentrate.
#
# Within Pre-Rolls, every way of saying an infused pack collapses to "infused".
# One store calls the shelf "infused", another "infused-pre-roll-pack", and a
# third writes "Infused Pre Roll 5-Pack", all for the same thing. Left alone
# they appear as three separate rows in the sidebar and split the counts.
SUBCATEGORY_ALIASES = {
    ("prerolls", "infused"): "infused",
    ("prerolls", "infusedprerollpack"): "infused",
    ("prerolls", "infusedprerollpacks"): "infused",
    ("prerolls", "infusedpack"): "infused",
    ("prerolls", "infusedpacks"): "infused",
    ("prerolls", "infusedpreroll"): "infused",
    ("prerolls", "infusedprerolls"): "infused",
}


def canonical_subcategory(main: str, sub: str) -> str:
    """Rename a subcategory to its canonical form within its main category."""
    if not sub or not sub.strip():
        return ""
    alias = SUBCATEGORY_ALIASES.get((category_key(main), category_key(sub)))
    return alias or sub.strip()


def canonical_category(category: str) -> str:
    """Return the category renamed to its canonical main category.

    The subcategory is canonicalised too, because that is where stores disagree
    most: an infused pre-roll pack is the same shelf however it is spelled.
    """
    if not category or not category.strip():
        return category

    main = main_category(category)
    key = category_key(main)
    canonical = CATEGORY_ALIASES.get(key, main)

    sub = canonical_subcategory(canonical, sub_category(category))
    return f"{canonical}{SUB_SEPARATOR}{sub}" if sub else canonical


def is_canonical(category: str) -> bool:
    """True when the category already uses its canonical main category."""
    return canonical_category(category) == category
