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
    "concentraterigs": "Concentrate",
    "concentraterig": "Concentrate",
    "dabrig": "Concentrate",
    "dabrigs": "Concentrate",
    "oilrig": "Concentrate",
    "oilrigs": "Concentrate",
    "carbcap": "Concentrate",
    "carbcaps": "Concentrate",
    "carb": "Concentrate",
    "concentrateaccessories": "Concentrate",
    "concentrateaccessory": "Concentrate",
    "dabaccessories": "Concentrate",
    "dabaccessory": "Concentrate",
    "quartz": "Concentrate",
    "banger": "Concentrate",
    "bangers": "Concentrate",
    "nail": "Concentrate",
    "nails": "Concentrate",
    "terpslurper": "Concentrate",
    "terpslurpers": "Concentrate",
    "terppearl": "Concentrate",
    "terppearls": "Concentrate",
    "pearl": "Concentrate",
    "pearls": "Concentrate",
    # Vaporizers.
    "vaporizers": "Vaporizers",
    "vaporizer": "Vaporizers",
    "vapes": "Vaporizers",
    "vape": "Vaporizers",
    "carts": "Vaporizers",
    "cartridges": "Vaporizers",
    "erigs": "Vaporizers",
    "erig": "Vaporizers",
    "erigsvaporizers": "Vaporizers",
    "electronicrig": "Vaporizers",
    "electronicrigs": "Vaporizers",
    # Edibles.
    "edible": "Edible",
    "edibles": "Edible",
    # Pre-rolls, which are only ever spelled inconsistently.
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
    # Accessories - consolidate all accessory types.
    "accessory": "Accessories",
    "accessories": "Accessories",
    "rollingcones": "Accessories",
    "rollingconesaccessories": "Accessories",
    "cleaningsupplies": "Accessories",
    "cleaningsupply": "Accessories",
    "cleaning": "Accessories",
    "batteries": "Accessories",
    "battery": "Accessories",
    # Glass - consolidate glass pieces.
    "bong": "Glass",
    "bongs": "Glass",
    "rig": "Glass",
    "rigs": "Glass",
    "bubbler": "Glass",
    "bubblers": "Glass",
    "ashcatcher": "Glass",
    "ashcatchers": "Glass",
    "bowl": "Glass",
    "bowls": "Glass",
    "pipe": "Glass",
    "pipes": "Glass",
    "mouthpiece": "Glass",
    "mouthpieces": "Glass",
    "jointbubbler": "Glass",
    "jointbubblers": "Glass",
    "waterpipe": "Glass",
    "waterpipes": "Glass",
    "waterpipe": "Glass",
    "waterpipes": "Glass",
    "slide": "Glass",
    "slides": "Glass",
    "flowerpipe": "Glass",
    "flowerpipes": "Glass",
    "flowerpipesandaccessories": "Glass",
    "pendant": "Glass",
    "pendants": "Glass",
    # Puffco devices and accessories.
    "peak": "Puffco",
    "peakaccessories": "Puffco",
    "peakpro": "Puffco",
    "peakproaccessories": "Puffco",
    "pivot": "Puffco",
    "pivotaccessories": "Puffco",
    "pivotaccessory": "Puffco",
    "proxyaccessory": "Puffco",
    "proxycoreaccessory": "Puffco",
    # Misc accessory types that go under Accessories.
    "batteries": "Accessories",
    "battery": "Accessories",
    "charger": "Accessories",
    "chargers": "Accessories",
    "grinder": "Accessories",
    "grinders": "Accessories",
    "lighter": "Accessories",
    "lighters": "Accessories",
    "lightercases": "Accessories",
    "lightercase": "Accessories",
    "tray": "Accessories",
    "trays": "Accessories",
    "rollingtray": "Accessories",
    "rollingtrays": "Accessories",
    "storage": "Accessories",
    "jointcase": "Accessories",
    "jointcases": "Accessories",
    "jointholder": "Accessories",
    "jointholders": "Accessories",
    "rollingpapers": "Accessories",
    "rollingpaper": "Accessories",
    "cone": "Accessories",
    "cones": "Accessories",
    "ashtray": "Accessories",
    "ashtrays": "Accessories",
    "dabaccessories": "Accessories",
    "dabaccessory": "Accessories",
    "dabtools": "Accessories",
    "dabtool": "Accessories",
    "tools": "Accessories",
    "tool": "Accessories",
    "replacementpart": "Accessories",
    "replacementparts": "Accessories",
    "protection": "Accessories",
    "pearl": "Accessories",
    "pearls": "Accessories",
    "glassware": "Accessories",
    "character": "Accessories",
    # Gift cards.
    "giftcard": "Gift Cards",
    "giftcards": "Gift Cards",
    # Kits.
    "kit": "Kits",
    "kits": "Kits",
    # Dab mats get their own shelf. A mat is a large silicone sheet rather than
    # a dab tool, so folding it into "dab tools" would hide the biggest items
    # on the shelf behind the smallest, and "mat" on its own is used by stores
    # that mean nothing else.
    "dabmat": "Dab Mats",
    "dabmats": "Dab Mats",
    "dab-mat": "Dab Mats",
    "dab-mats": "Dab Mats",
    "dabpad": "Dab Mats",
    "dabpads": "Dab Mats",
    "mat": "Dab Mats",
    "mats": "Dab Mats",
    # "cleaningcare" folds cleaning supplies into Accessories, which already
    # owns the plain "cleaning" alias above. Vape coils are replacement parts.
    "cleaningcare": "Accessories",
    "cleaningsupplies": "Accessories",
    "cleaningsupply": "Accessories",
    "coil": "Accessories",
    "coils": "Accessories",
    # Event and artist drops from the glass stores are still glass art.
    "ohioglassblowersshow2025": "Glass",
    "ohioglassblowersshow": "Glass",
    "stevesizelovedrop2025": "Glass",
    "stevesizelovedrop": "Glass",
    # Donation and Insurance are not product shelves; fold them into Misc.
    "donation": "Misc",
    "insurance": "Misc",
    "misc": "Misc",
    # Merch.
    "merch": "Merch",
    "merchandise": "Merch",
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
    # Pre-Rolls subcategories
    ("prerolls", "infused"): "infused",
    ("prerolls", "infusedprerollpack"): "infused",
    ("prerolls", "infusedprerollpacks"): "infused",
    ("prerolls", "infusedpack"): "infused",
    ("prerolls", "infusedpacks"): "infused",
    ("prerolls", "infusedpreroll"): "infused",
    ("prerolls", "infusedprerolls"): "infused",
    ("prerolls", "singles"): "singles",
    ("prerolls", "single"): "singles",
    ("prerolls", "packs"): "packs",
    ("prerolls", "pack"): "packs",

    # Concentrate subcategories
    ("concentrate", "liveresin"): "live resin",
    ("concentrate", "liveresindisposable"): "live resin disposable",
    ("concentrate", "liveresincartridge"): "live resin cartridge",
    ("concentrate", "rosin"): "rosin",
    ("concentrate", "liverosin"): "live rosin",
    ("concentrate", "badder"): "badder",
    ("concentrate", "budder"): "budder",
    ("concentrate", "shatter"): "shatter",
    ("concentrate", "sauce"): "sauce",
    ("concentrate", "sugar"): "sugar",
    ("concentrate", "crumble"): "crumble",
    ("concentrate", "wax"): "wax",
    ("concentrate", "rso"): "rso",
    ("concentrate", "applicators"): "applicators",
    ("concentrate", "applicator"): "applicators",
    ("concentrate", "infusedflower"): "infused-flower",

    # Edible subcategories
    ("edible", "gummies"): "gummies",
    ("edible", "gummy"): "gummies",
    ("edible", "liveresingummies"): "live resin gummies",
    ("edible", "liverosingummies"): "live rosin gummies",
    ("edible", "chocolates"): "chocolates",
    ("edible", "chocolate"): "chocolates",
    ("edible", "drinks"): "drinks",
    ("edible", "drink"): "drinks",
    ("edible", "beverages"): "drinks",
    ("edible", "hardcandy"): "hard candy",
    ("edible", "capsulestablets"): "capsules & tablets",
    ("edible", "capsules&tablets"): "capsules & tablets",
    ("edible", "tablets"): "capsules & tablets",
    ("edible", "dissolvables"): "dissolvables",
    ("edible", "dissolvable"): "dissolvables",
    ("edible", "mints"): "mints",
    ("edible", "mint"): "mints",

    # Flower subcategories
    ("flower", "smallbuds"): "small buds",
    ("flower", "shaketrim"): "shake & trim",
    ("flower", "shake&trim"): "shake & trim",
    ("flower", "premium"): "premium",
    ("flower", "wholeflower"): "whole flower",
    ("flower", "bulkflower"): "bulk flower",
    ("flower", "preground"): "pre-ground",

    # Vaporizers subcategories
    ("vaporizers", "disposables"): "disposables",
    ("vaporizers", "disposable"): "disposables",
    ("vaporizers", "cartridges"): "cartridges",
    ("vaporizers", "cartridge"): "cartridges",
    ("vaporizers", "pods"): "pods",
    ("vaporizers", "pod"): "pods",
    ("vaporizers", "liveresindisposable"): "live resin disposable",
    ("vaporizers", "liveresincartridge"): "live resin cartridge",

    # Accessories subcategories
    ("accessories", "batteries"): "batteries",
    ("accessories", "battery"): "batteries",
    ("accessories", "devices"): "devices",
    ("accessories", "device"): "devices",
    ("accessories", "grinders"): "grinders",
    ("accessories", "grinder"): "grinders",
    ("accessories", "lighters"): "lighters",
    ("accessories", "lighter"): "lighters",
    ("accessories", "trays"): "trays",
    ("accessories", "tray"): "trays",
    ("accessories", "glassware"): "glassware",
    ("accessories", "dabtools"): "dab tools",
    ("accessories", "dabtool"): "dab tools",
    # Keys are normalised, so "dab-mats" and "dab mats" both arrive as dabmats.
    ("accessories", "dabmats"): "dab mats",
    ("accessories", "dabmat"): "dab mats",
    ("accessories", "mats"): "dab mats",
    ("accessories", "mat"): "dab mats",
    ("accessories", "papersrollingsupplies"): "papers & rolling supplies",
    ("accessories", "papersrollingsupplies"): "papers & rolling supplies",
    ("accessories", "ashtrays"): "ashtrays",
    ("accessories", "ashtray"): "ashtrays",
    ("accessories", "cones"): "cones",
    ("accessories", "cone"): "cones",
    ("accessories", "rollingpapers"): "rolling papers",
    ("accessories", "rollingpaper"): "rolling papers",
    ("accessories", "rollingtrays"): "rolling trays",
    ("accessories", "rollingtray"): "rolling trays",
    ("accessories", "storage"): "storage",
    ("accessories", "jointcases"): "joint cases",
    ("accessories", "jointcase"): "joint cases",
    ("accessories", "jointholders"): "joint holders",
    ("accessories", "jointholder"): "joint holders",
    ("accessories", "lightercases"): "lighter cases",
    ("accessories", "lightercase"): "lighter cases",
    ("accessories", "tools"): "tools",
    ("accessories", "tool"): "tools",
    ("accessories", "replacementparts"): "replacement parts",
    ("accessories", "replacementpart"): "replacement parts",
    ("accessories", "ashcatchers"): "ash catchers",
    ("accessories", "ashcatcher"): "ash catchers",
    ("accessories", "bowls"): "bowls",
    ("accessories", "bowl"): "bowls",
    ("accessories", "pipes"): "pipes",
    ("accessories", "pipe"): "pipes",
    ("accessories", "mouthpieces"): "mouthpieces",
    ("accessories", "mouthpiece"): "mouthpieces",
    ("accessories", "protection"): "protection",
    ("accessories", "pearls"): "pearls",
    ("accessories", "pearl"): "pearls",
    ("accessories", "chargers"): "chargers",
    ("accessories", "charger"): "chargers",

    # Glass subcategories
    ("glass", "bongs"): "bongs",
    ("glass", "bong"): "bongs",
    ("glass", "rigs"): "rigs",
    ("glass", "rig"): "rigs",
    ("glass", "bubblers"): "bubblers",
    ("glass", "bubbler"): "bubblers",
    ("glass", "jointbubblers"): "joint bubblers",
    ("glass", "jointbubbler"): "joint bubblers",

    # Puffco subcategories
    ("puffco", "peak"): "peak",
    ("puffco", "peakaccessories"): "peak accessories",
    ("puffco", "peakpro"): "peak pro",
    ("puffco", "peakproaccessories"): "peak pro accessories",
    ("puffco", "pivot"): "pivot",
    ("puffco", "pivotaccessories"): "pivot accessories",
    ("puffco", "pivotaccessory"): "pivot accessories",
    ("puffco", "proxyaccessories"): "proxy accessories",
    ("puffco", "proxyaccessory"): "proxy accessories",
    ("puffco", "proxycoreaccessories"): "proxy core accessories",
    ("puffco", "proxycoreaccessory"): "proxy core accessories",

    # Tincture subcategories
    ("tincture", "sprays"): "sprays",
    ("tincture", "spray"): "sprays",
    ("tincture", "unflavored"): "unflavored",
    ("tincture", "ratio"): "ratio",

    # Topicals subcategories
    ("topicals", "balms"): "balms",
    ("topicals", "balm"): "balms",
    ("topicals", "lotions"): "lotions",
    ("topicals", "lotion"): "lotions",
    ("topicals", "transdermalpatches"): "transdermal patches",
    ("topicals", "suppositories"): "suppositories",
    ("topicals", "suppository"): "suppositories",
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
