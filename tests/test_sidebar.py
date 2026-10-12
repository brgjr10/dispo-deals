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

DASHBOARD = Path(__file__).resolve().parent.parent / "dashboard.html"


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


@pytest.fixture(scope="module")
def helpers():
    """The category helpers, loaded into a throwaway Node context."""
    if shutil.which("node") is None:
        pytest.skip("node is required to exercise the dashboard helpers")

    script = _extract_script()
    functions = _extract_functions(
        script, ["categoryMain", "categorySub", "getExpandedGroups", "filterProducts"]
    )

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
        "      } else if (p.category !== currentFilters.category) return false;",
        "    }",
        "    return true;",
        "  })",
        "};",
    ])
    return functions, harness


def _run_js(helpers, body):
    """Run JS in Node from a UTF-8 temp file.

    Passing source through `node -e` mangles the middle dot on Windows, and that
    separator is exactly what these helpers split on.
    """
    functions, harness = helpers
    source = (
        functions["categoryMain"] + "\n" +
        functions["categorySub"] + "\n" +
        harness + "\n" +
        body
    )

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


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
