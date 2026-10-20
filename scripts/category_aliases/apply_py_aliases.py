"""Insert the generated aliases into utils/categories.py, grouped by target.

Only new keys are added; nothing already in the file is rewritten, so the
existing documented behaviour is preserved verbatim. Run gen_categories.py first.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gen_categories as g  # noqa: E402

PATH = os.path.join(g.PROJECT_ROOT, "utils", "categories.py")

# Human-readable group headers for the new aliases, in file order.
MAIN_GROUPS = [
    ("Apparel", "Apparel. Clothing stores name the same garment differently, and a\n    # wholesale taxonomy uses ALL-CAPS codes for the same shelves."),
    ("Hats", "Hats, including the headwear codes and the cap/beanie spellings."),
    ("Beanies", "Beanies, which are a separate shelf from hats in the source data."),
    ("Bags", "Bags. Every store spells a bag differently, and the wallets section\n    # is the same shelf."),
    ("Footwear", "Footwear. Boots, platforms and slides are all the same shelf."),
    ("Accessories", "Accessories. One-off shelves from the glass and smoke shops."),
    ("Concentrate", "Concentrate. Diamonds, quartz and hash are all concentrates."),
    ("Edible", "Edible. Beverages and syrups are drunk, not smoked."),
    ("Flower", "Flower. Ounce and smalls deals are still flower."),
    ("Vaporizers", "Vaporizers. A 1g cartridge and a 2g disposable are both vapes."),
    ("Pre-Rolls", "Pre-Rolls."),
    ("Tincture", "Tincture."),
    ("Topicals", "Topicals."),
    ("Oral", "Oral products, which Dutchie reports as their own shelf."),
    ("Glass", "Glass. Beaker sizes, Prism series and artist drops are all glass art."),
    ("Puffco", "Puffco. Modul, charms and attachments are Puffco accessories."),
    ("Kits", "Kits."),
    ("Merch", "Merch."),
    ("Skate", "Skate."),
    ("Dab Mats", "Dab Mats."),
    ("Gift Cards", "Gift Cards."),
    ("Knitwear", "Knitwear."),
    ("Misc", "Misc. Sale flags, service line items, placeholders and home goods\n    # are not product shelves, so they collapse onto the catch-all."),
]

SUB_GROUPS = [
    ("Apparel", "Apparel subcategories: the wholesale taxonomy codes and every\n    # singular/plural and case variant of the same garment."),
    ("Hats", "Hat subcategories."),
    ("Beanies", "Beanie subcategories."),
    ("Bags", "Bag subcategories."),
    ("Footwear", "Footwear subcategories."),
    ("Accessories", "Accessory subcategories, including the shelves a store files\n    # as its own top-level category."),
    ("Concentrate", "Concentrate subcategories."),
    ("Edible", "Edible subcategories."),
    ("Flower", "Flower subcategories."),
    ("Vaporizers", "Vaporizer subcategories."),
    ("Pre-Rolls", "Pre-roll subcategories."),
    ("Tincture", "Tincture subcategories."),
    ("Topicals", "Topical subcategories."),
    ("Oral", "Oral subcategories."),
    ("Glass", "Glass subcategories."),
    ("Puffco", "Puffco subcategories."),
    ("Kits", "Kit subcategories."),
    ("Skate", "Skate subcategories."),
    ("Knitwear", "Knitwear subcategories."),
    ("Dab Mats", "Dab mat subcategories."),
    ("Merch", "Merch subcategories."),
    ("Misc", "Misc subcategories. Sale flags, junk placeholders and home goods\n    # collapse onto a handful of readable rows."),
]


def existing_dicts(src):
    """The alias dicts as they already are in the file."""
    ns = {}
    exec(compile(src[src.index("CATEGORY_ALIASES = {"):src.index("SUB_SEPARATOR =")],
                 "cats", "exec"), ns)
    ns2 = {}
    exec(compile(src[src.index("SUBCATEGORY_ALIASES = {"):src.index("def canonical_subcategory")],
                 "cats2", "exec"), ns2)
    return ns["CATEGORY_ALIASES"], ns2["SUBCATEGORY_ALIASES"]


def render_main(py_main, existing):
    out = []
    for target, header in MAIN_GROUPS:
        entries = sorted(k for k, v in py_main.items()
                         if v == target and k not in existing)
        if not entries:
            continue
        out.append(f"    # {header}")
        for k in entries:
            out.append(f'    "{k}": "{py_main[k]}",')
        out.append("")
    return "\n".join(out).rstrip("\n")


def render_sub(py_sub, existing):
    out = []
    for target, header in SUB_GROUPS:
        keys = sorted(k for k, v in py_sub.items()
                      if k[0] == g.key(target) and k not in existing)
        if not keys:
            continue
        out.append(f"    # {header}")
        for m, s in keys:
            out.append(f'    ("{m}", "{s}"): "{py_sub[(m, s)]}",')
        out.append("")
    return "\n".join(out).rstrip("\n")


def patch_title_regexes(src):
    """Keep the title-rescue regexes in step with the alias table.

    The regexes live in the table above so the mousepad spelling cannot be lost
    when the file is regenerated from git. _CATCH_ALL_MAINS is left alone: it
    names the shelves that are never right for any product and does not change
    with the alias table.
    """
    block = re.compile(
        r"_DAB_MAT_NAME_RE = re\.compile\(\n\s*r\"[^\"]*\",\n?\s*re\.IGNORECASE,?\n\)"
    )
    replacement = (
        "_DAB_MAT_NAME_RE = re.compile(\n"
        f'    r"{g.DAB_MAT_NAME_RE}",\n'
        "    re.IGNORECASE,\n"
        ")\n"
        "# A mousepad is moved onto the Dab Mats shelf whatever shelf the store\n"
        "# filed it under, because the glass and accessory vendors list the\n"
        "# silicone sheets beside their other stock.\n"
        "_MOUSEPAD_NAME_RE = re.compile(\n"
        f'    r"{g.MOUSEPAD_NAME_RE}",\n'
        "    re.IGNORECASE,\n"
        ")"
    )
    new, count = block.subn(lambda _m: replacement, src)
    if count == 0:
        raise AssertionError("_DAB_MAT_NAME_RE block not found in categories.py")
    return new


def _dict_end(src, name):
    """Index of the closing brace of a top-level ``NAME = { ... }`` dict."""
    start = src.index(f"{name} = {{")
    depth = 0
    for index in range(src.index("{", start), len(src)):
        if src[index] == "{":
            depth += 1
        elif src[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    raise AssertionError(f"unbalanced braces while reading {name}")


def main():
    js_main, py_main, js_sub, py_sub, _ = g.build()
    src = open(PATH, encoding="utf-8").read()
    existing_main, existing_sub = existing_dicts(src)
    print(f"existing: {len(existing_main)} mains, {len(existing_sub)} subs")

    # ---- CATEGORY_ALIASES -------------------------------------------------
    # Insert just inside the closing brace, so re-running on an already patched
    # file finds the same place rather than depending on the last entry.
    end = _dict_end(src, "CATEGORY_ALIASES")
    new_main = render_main(py_main, existing_main)
    if new_main:
        body = src[:end].rstrip("\n")
        src = body + "\n\n" + new_main + "\n" + src[end:]
    else:
        print("no new main aliases to add")

    # ---- SUBCATEGORY_ALIASES ----------------------------------------------
    start = src.index("SUBCATEGORY_ALIASES = {")
    end = _dict_end(src, "SUBCATEGORY_ALIASES")
    new_sub = render_sub(py_sub, existing_sub)
    if new_sub:
        body = src[start:end].rstrip("\n")
        src = src[:start] + body + "\n\n" + new_sub + "\n" + src[end:]
    else:
        print("no new sub aliases to add")

    # The rescue regexes are declared after both tables.
    src = patch_title_regexes(src)

    open(PATH, "w", encoding="utf-8").write(src)
    print(f"patched {PATH}: +{len(new_main.splitlines())} main lines, "
          f"+{len(new_sub.splitlines())} sub lines, dab-mat regex synced")


if __name__ == "__main__":
    main()
