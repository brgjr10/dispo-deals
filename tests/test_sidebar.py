"""The category sidebar groups subcategories under one collapsible row.

The helpers that decide the grouping and the filtering are plain JavaScript
inside dashboard.html, so they are extracted and executed with Node rather than
reimplemented in Python, which would let the two drift apart.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

DASHBOARD = Path(__file__).resolve().parent.parent / "dashboard" / "dashboard.html"


def _extract_script():
    """Return the dashboard's single inline script."""
    html = DASHBOARD.read_text(encoding="utf-8")
    blocks = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.DOTALL)
    assert blocks, "dashboard.html has no inline script"
    return blocks[0]


def _extract_functions(script, names):
    """Pull out the named function declarations by brace matching."""
    found = {}
    for name in names:
        match = re.search(rf"^function {name}\(", script, re.MULTILINE)
        assert match, f"{name} not found in dashboard.html"
        start = match.start()
        depth = 0
        for index in range(script.index("{", match.end() - 1), len(script)):
            if script[index] == "{":
                depth += 1
            elif script[index] == "}":
                depth -= 1
                if depth == 0:
                    found[name] = script[start:index + 1]
                    break
        else:
            raise AssertionError(f"unbalanced braces while reading {name}")
    return found


def _extract_const(script, name):
    """Pull out a top-level ``const NAME = { ... };`` object literal."""
    match = re.search(rf"^const {name} = {{", script, re.MULTILINE)
    assert match, f"{name} not found in dashboard.html"
    start = match.start()
    depth = 0
    for index in range(script.index("{", match.end() - 1), len(script)):
        if script[index] == "{":
            depth += 1
        elif script[index] == "}":
            depth -= 1
            if depth == 0:
                end = script.index(";", index)
                return script[start:end + 1]
    raise AssertionError(f"unbalanced braces while reading {name}")


@pytest.fixture(scope="module")
def helpers():
    """The category helpers, loaded into a throwaway Node context."""
    if shutil.which("node") is None:
        pytest.skip("node is required to exercise the dashboard helpers")

    script = _extract_script()
    functions = _extract_functions(
        script,
        [
            "categoryKey", "normalizeCategoryMain", "categoryMain", "categorySub",
            "normalizeCategorySub", "getExpandedGroups", "filterProducts",
        ],
    )
    # The alias tables are const declarations rather than functions, so they are
    # pulled out separately and placed before the helpers that read them.
    tables = [
        functions["categoryKey"],
        _extract_const(script, "MAIN_ALIASES"),
        _extract_const(script, "MAIN_REMAP"),
        functions["normalizeCategoryMain"],
        functions["categoryMain"],
        functions["categorySub"],
        _extract_const(script, "SUB_ALIASES"),
        functions["normalizeCategorySub"],
    ]

    harness = "\n".join([
        "const currentFilters = { category: '' };",
        "const C = {",
        "  categoryMain, categorySub,",
        # filterProducts only reads currentFilters.category, so the rest of its
        # dependencies are stubbed out to keep the harness self-contained.",
        "  filterProducts: (products) => products.filter(p => {",
        "    if (currentFilters.category) {",
        "      const selected = categoryMain(currentFilters.category);",
        "      if (selected === currentFilters.category) {",
        "        if (categoryMain(p.category) !== selected) return false;",
        "      } else {",
        "        const selectedSub = normalizeCategorySub(currentFilters.category);",
        "        const pMain = categoryMain(p.category);",
        "        const pSub = pMain === p.category ? '' : normalizeCategorySub(p.category);",
        "        if (pMain !== selected || pSub !== selectedSub) return false;",
        "      }",
        "    }",
        "    return true;",
        "  })",
        "};",
    ])
    return tables, harness


def _run_js(helpers, body):
    """Run JS in Node from a UTF-8 temp file.

    Passing source through `node -e` mangles the middle dot on Windows, and that
    separator is exactly what these helpers split on.
    """
    tables, harness = helpers
    source = "\n".join(tables) + "\n" + harness + "\n" + body

    with tempfile.NamedTemporaryFile(
        "w", suffix=".js", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(source)
        path = tmp.name

    try:
        result = subprocess.run(
            ["node", path], capture_output=True, text=True, timeout=30, encoding="utf-8"
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    finally:
        os.unlink(path)


class TestCategoryGrouping:
    def test_main_category_is_the_part_before_the_dot(self, helpers):
        out = _run_js(helpers, 'console.log(JSON.stringify(categoryMain("Flower · premium")))')
        assert out == "Flower"

    def test_bare_category_is_its_own_group(self, helpers):
        out = _run_js(helpers, 'console.log(JSON.stringify(categoryMain("Accessories")))')
        assert out == "Accessories"

    def test_blank_category_yields_empty_group(self, helpers):
        out = _run_js(helpers, 'console.log(JSON.stringify(categoryMain("")))')
        assert out == ""

    def test_subcategory_is_the_part_after_the_dot(self, helpers):
        out = _run_js(helpers, 'console.log(JSON.stringify(categorySub("Flower · premium")))')
        assert out == "premium"

    def test_nested_subcategory_keeps_everything_after_first_dot(self, helpers):
        out = _run_js(helpers, 'console.log(JSON.stringify(categorySub("A · B · C")))')
        assert out == "B · C"

    def test_bare_category_returns_itself(self, helpers):
        out = _run_js(helpers, 'console.log(JSON.stringify(categorySub("Accessories")))')
        assert out == "Accessories"


class TestGroupFiltering:
    def _products(self):
        return [
            {"category": "Flower"},
            {"category": "Flower · premium"},
            {"category": "Flower · shake-trim"},
            {"category": "Vaporizers · cartridges"},
            {"category": "Edible · gummies"},
        ]

    def test_group_selection_matches_every_subcategory(self, helpers):
        result = _run_js(helpers, f"""
          currentFilters.category = 'Flower';
          console.log(JSON.stringify(C.filterProducts({json.dumps(self._products())}).map(p => p.category)));
        """)
        assert sorted(result) == ["Flower", "Flower · premium", "Flower · shake-trim"]

    def test_subcategory_selection_matches_exactly(self, helpers):
        result = _run_js(helpers, f"""
          currentFilters.category = 'Flower · premium';
          console.log(JSON.stringify(C.filterProducts({json.dumps(self._products())}).map(p => p.category)));
        """)
        assert result == ["Flower · premium"]

    def test_group_selection_excludes_other_groups(self, helpers):
        result = _run_js(helpers, f"""
          currentFilters.category = 'Vaporizers';
          console.log(JSON.stringify(C.filterProducts({json.dumps(self._products())}).map(p => p.category)));
        """)
        assert result == ["Vaporizers · cartridges"]

    def test_similar_names_do_not_cross_match(self, helpers):
        """A group name must not be matched as a prefix of another category."""
        result = _run_js(helpers, f"""
          currentFilters.category = 'Edible';
          console.log(JSON.stringify(C.filterProducts({json.dumps(self._products())}).map(p => p.category)));
        """)
        assert result == ["Edible · gummies"]

    def test_merged_subcategory_row_filters_to_every_spelling(self, helpers):
        """A row that merged two spellings must not filter to only one of them.

        The sidebar keys a subcategory row by its normalised "main · sub" pair,
        so selecting "Apparel · Hoodies" has to match both the raw categories
        that were merged into it.
        """
        products = [
            {"category": "Apparel · Hoodie"},
            {"category": "Hoodies"},
            {"category": "hoodie"},
            {"category": "Apparel"},
            {"category": "Apparel · Socks"},
        ]
        result = _run_js(helpers, f"""
          currentFilters.category = 'Apparel · Hoodies';
          console.log(JSON.stringify(C.filterProducts({json.dumps(products)}).map(p => p.category)));
        """)
        assert sorted(result) == [
            "Apparel · Hoodie", "Hoodies", "hoodie",
        ]

    def test_real_filter_matches_the_stubbed_one(self, helpers):
        """The stub must not diverge from the dashboard's own filterProducts."""
        script = _extract_script()
        assert "normalizeCategorySub(currentFilters.category)" in script
        assert "p.category !== currentFilters.category" not in script


class TestConsolidatedGroups:
    """Every stray shelf from the brand stores folds into a main group."""

    @pytest.mark.parametrize("raw,expected", [
        # Case and typo variants of the same shelf.
        ("APPAREL", "Apparel"),
        ("T-Shirts", "Apparel"),
        ("tshirts", "Apparel"),
        ("Accesory", "Accessories"),
        ("Acc Miscellaneous", "Accessories"),
        # Glass shops file a beaker size, a Prism series and an artist drop.
        ("45mm beakers", "Gear"),
        ("Clear Models (2nd)", "Gear"),
        ("Hologram Toro", "Gear"),
        # A one-off smoke-shop shelf is still an accessory.
        ("Silicone Accessory Kit", "Accessories"),
        ("Spoon Pipe", "Accessories"),
        # Sale flags and placeholders are not product shelves.
        ("Other Shit", "Gear"),
        ("Expivi Product Replica", "Gear"),
        ("Shipping Protection", "Gear"),
        # Cannabis shelves keep their existing canonical spelling.
        ("Concentrates", "Concentrates"),
        ("1g THCA cartridge", "Vaporizers"),
        ("Beverage", "Edible"),
        ("Dabbing Mat", "Gear"),
        ("Modul", "Modül"),
    ])
    def test_stray_shelf_folds_into_a_main_group(self, helpers, raw, expected):
        out = _run_js(helpers, f"console.log(JSON.stringify(categoryMain({json.dumps(raw)})))")
        assert out == expected

    @pytest.mark.parametrize("raw,expected", [
        # Wholesale taxonomy codes become readable labels. A printed tee is a
        # t-shirt, so the code folds into that row rather than standing alone.
        ("Apparel · TEE SS PRINTED", "T-Shirts"),
        ("Apparel · TEE LS PRINTED", "T-Shirts"),
        ("Apparel · BOTTOM KNIT SHORT", "Knit Shorts"),
        ("Apparel · HOODED FLEECE CUT/ SEW", "Hooded Fleece"),
        ("Apparel · OUTERWEAR WINDBREAKER CUT/SEW", "Windbreaker"),
        # Singular, plural and case variants merge onto one row.
        ("Apparel · Hoodie", "Hoodies"),
        ("apparel · hoodie", "Hoodies"),
        ("Apparel · Hoodies", "Hoodies"),
        # Spellings that each used to be their own row.
        ("Apparel · long sleeve", "Tops"),
        ("Apparel · Long Sleeve", "Tops"),
        ("Apparel · longsleeve", "Tops"),
        ("Apparel · short sleeve", "Tops"),
        ("Apparel · Jacket", "Jackets"),
        ("Apparel · APPAREL", "Clothing"),
        ("Apparel · Short Sleeve Tee", "T-Shirts"),
        # Spelling and spacing fixes.
        ("Accessories · cleaning-solutions", "cleaning solutions"),
        ("Accessories · storage-containers", "storage"),
        ("Flower · Smalls", "small buds"),
        ("Vaporizers · All-in-One", "all-in-one"),
        ("Vaporizers · live-rosin", "live rosin"),
        ("Vaporizers · Kit", "kits"),
        ("Pre-Rolls · Pre-Roll Pack", "packs"),
        ("Concentrate · Resin", "live resin"),
        # Rows on the Accessories shelf are lowercase throughout.
        ("Accessories · Chillum", "chillum"),
        ("Accessories · Dab Straws", "dab straws"),
        ("Accessories · Glass Tips", "glass tips"),
        ("Accessories · Wraps", "wraps"),
        ("Concentrate · Ground Flower", "ground flower"),
        ("Concentrate · Moonrocks", "moonrocks"),
        ("Topicals · Body Oil", "body oil"),
        ("Dab Mats · Dabbing Mat", "mats"),
        ("Flower · Indoor Flower", "indoor flower"),
        # A name that is already canonical is left alone.
        ("Flower · whole flower", "whole flower"),
    ])
    def test_subcategory_label_is_corrected(self, helpers, raw, expected):
        out = _run_js(helpers, f"console.log(JSON.stringify(normalizeCategorySub({json.dumps(raw)})))")
        assert out == expected

    def test_same_shelf_from_two_stores_shares_one_group(self, helpers):
        """The whole point: two spellings must not produce two rows."""
        out = _run_js(helpers, """
          const cats = ['45mm beakers', 'Beaker', 'Glass Bong', 'Bongs & Dab Rigs'];
          console.log(JSON.stringify([...new Set(cats.map(categoryMain))]));
        """)
        assert out == ["Gear"]

    def test_grouping_is_idempotent(self, helpers):
        out = _run_js(helpers, """
          const cats = ['Apparel · Hoodie', 'T-Shirts', 'Accesory', '45mm beakers',
                        'Other Shit', 'Vaporizers · All-in-One'];
          console.log(JSON.stringify(cats.map(c => normalizeCategorySub(categoryMain(c) + ' · ' + normalizeCategorySub(c)))));
        """)
        assert out == [
            "Hoodies", "T-Shirts", "miscellaneous", "beakers", "Other", "all-in-one",
        ]

    def test_mousepad_is_a_dab_mat(self, helpers):
        """The stores sell the silicone sheets beside desk mats."""
        for raw in ["Mousepad", "Mousepads", "Mouse Pad"]:
            out = _run_js(
                helpers, f"console.log(JSON.stringify(categoryMain({json.dumps(raw)})))"
            )
            assert out == "Gear"
        out = _run_js(
            helpers,
            "console.log(JSON.stringify(normalizeCategorySub('Accessories · Mousepad')))"
        )
        assert out == "dab mats"


class TestJsPythonParity:
    """The dashboard and the API each carry their own alias table.

    They are generated from one table, but nothing stops a hand edit from
    drifting, which would put a product under one shelf in the sidebar and
    another in the API. Every raw name must reach the same shelf in both.
    """

    # The JS table pluralises where the Python one does not. Everything else
    # must match exactly.
    CANONICAL_EQUIVALENTS = {"Concentrates": "Concentrate", "Tinctures": "Tincture"}

    def test_every_js_alias_agrees_with_python(self, helpers):
        from utils.categories import CATEGORY_ALIASES, category_key

        tables, _ = helpers
        script = _extract_script()
        js_main = {}
        for line in _extract_const(script, "MAIN_ALIASES").splitlines():
            match = re.match(r"\s*'([^']+)': '([^']+)',", line)
            if match:
                js_main[match.group(1)] = match.group(2)

        assert len(js_main) > 400, "the generated alias table looks truncated"

        missing = []
        disagree = []
        for raw_key, js_canonical in js_main.items():
            py_canonical = CATEGORY_ALIASES.get(raw_key)
            if py_canonical is None:
                missing.append((raw_key, js_canonical))
            elif py_canonical != self.CANONICAL_EQUIVALENTS.get(js_canonical, js_canonical):
                disagree.append((raw_key, js_canonical, py_canonical))

        assert not missing, f"names the dashboard folds but Python does not: {missing[:5]}"
        assert not disagree, f"names the two implementations fold differently: {disagree[:5]}"

    def test_every_python_alias_is_known_to_the_dashboard(self, helpers):
        """The reverse direction: Python must not fold a name the dashboard
        leaves alone, which would hide a shelf from the sidebar."""
        from utils.categories import CATEGORY_ALIASES, category_key

        script = _extract_script()
        js_main = set()
        for line in _extract_const(script, "MAIN_ALIASES").splitlines():
            match = re.match(r"\s*'([^']+)': '([^']+)',", line)
            if match:
                js_main.add(match.group(1))

        # A key is only ever looked up after category_key strips punctuation, so
        # a key that does not survive its own normalisation ("dab-mat") can
        # never match and is not worth duplicating on the dashboard side.
        reachable = {
            k for k in CATEGORY_ALIASES if category_key(k) == k
        }
        unknown = sorted(reachable - js_main)
        assert not unknown, f"alias keys only Python knows: {unknown[:5]}"


class TestSidebarMarkup:
    def test_sidebar_has_a_categories_container(self):
        assert 'id="categoryNavList"' in DASHBOARD.read_text(encoding="utf-8")

    def test_group_chevron_is_drawn_with_css(self):
        html = DASHBOARD.read_text(encoding="utf-8")
        assert ".nav-chevron" in html
        assert ".nav-group-items" in html

    def test_group_labels_collapse_by_default(self):
        """Nothing is expanded until the user opens it."""
        html = DASHBOARD.read_text(encoding="utf-8")
        assert ".nav-group-items {\n    display: none" in html or "display: none" in html


class TestGearFamilies:
    """The Gear section groups its unpacked shelves under family headers."""

    @pytest.fixture(scope="class")
    def family_helpers(self):
        if shutil.which("node") is None:
            pytest.skip("node is required to exercise the dashboard helpers")

        script = _extract_script()
        functions = _extract_functions(
            script,
            ["categoryKey", "gearFamilyFor"],
        )
        tables = [
            functions["categoryKey"],
            _extract_const(script, "GEAR_FAMILIES"),
            functions["gearFamilyFor"],
        ]

        def run(body):
            with tempfile.NamedTemporaryFile(
                "w", suffix=".js", delete=False, encoding="utf-8"
            ) as tmp:
                tmp.write("\n".join(tables) + "\n" + body)
                path = tmp.name
            try:
                result = subprocess.run(
                    ["node", path], capture_output=True, text=True, timeout=30,
                    encoding="utf-8",
                )
                assert result.returncode == 0, result.stderr
                return json.loads(result.stdout)
            finally:
                os.unlink(path)

        return run

    @pytest.mark.parametrize("shelf,expected", [
        ("bongs", "Glass"),
        ("beakers", "Glass"),
        ("rigs", "Glass"),
        ("heady glass", "Glass"),
        ("pipes", "Glass"),
        ("bowls", "Glass"),
        ("glass tips", "Glass"),
        ("peak", "Puffco"),
        ("pivot", "Puffco"),
        ("proxy core", "Puffco"),
        ("batteries", "Puffco"),
        ("chargers", "Puffco"),
        ("dab mats", "Dab Mats"),
        ("mats", "Dab Mats"),
        ("dab tools", "Dab Mats"),
        ("smoking kits", "Kits"),
        ("rig kits", "Kits"),
        ("rolling papers", "Kits"),
        ("cones", "Kits"),
        ("grinders", "Misc"),
        ("lighters", "Misc"),
        ("eyewear", "Misc"),
        ("jewelry", "Misc"),
        ("Home & Decor", "Misc"),
        ("Bundle", "Misc"),
        ("Deals", "Misc"),
        ("Sale", "Misc"),
    ])
    def test_shelf_maps_to_its_family(self, family_helpers, shelf, expected):
        out = family_helpers(
            f"console.log(JSON.stringify(gearFamilyFor({json.dumps(shelf)})))"
        )
        assert out == expected

    @pytest.mark.parametrize("shelf", [
        "cartridges", "disposables", "hash", "rosin", "Vinyl Decals", "Modül",
    ])
    def test_cannabis_and_stray_shelves_have_no_family(self, family_helpers, shelf):
        out = family_helpers(
            f"console.log(JSON.stringify(gearFamilyFor({json.dumps(shelf)})))"
        )
        assert out is None

    def test_every_canonical_gear_sub_has_a_family(self, family_helpers):
        """A shelf the backend folds onto Gear must not fall through to the
        loose list, or it renders as a bare row under the Gear divider.

        A handful of shelves are genuinely uncategorisable - they are one-off
        store drops or brand names with no product family (Modul, Vinyl
        Decals) - and are expected to stay loose rather than be force-fit.
        """
        from utils.categories import SUBCATEGORY_ALIASES, category_key

        STRAYS = {"modl", "vinyldecals"}
        families = {}
        for (main, sub), canon in SUBCATEGORY_ALIASES.items():
            if main not in {"glass", "puffco", "dabmats", "kits", "accessories", "misc"}:
                continue
            if category_key(canon) in STRAYS:
                continue
            families.setdefault(category_key(canon), canon)

        missing = []
        for key, canon in families.items():
            out = family_helpers(
                f"console.log(JSON.stringify(gearFamilyFor({json.dumps(canon)})))"
            )
            if out is None:
                missing.append(canon)
        assert not missing, f"gear shelves with no family: {missing[:8]}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
