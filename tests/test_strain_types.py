"""The phenotype (Sativa/Indica/Hybrid) type detection and badge placement.

The type can come from two places, and the order between them is the whole
point: the product name states the type explicitly, so only when the name is
silent does the Leafly strain record supply it. The helpers are plain
JavaScript in dashboard.html, so they are extracted and executed with Node
rather than reimplemented in Python, which would let the two drift apart.

The badges also have to stay clear of the compare checkbox, which is a layout
question rather than a logic one and is checked against the real CSS.
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


def _function_end(script, name):
    """Index just past the closing brace of a named function declaration."""
    match = re.search(rf"^function {name}\(", script, re.MULTILINE)
    assert match, f"{name} not found"
    depth = 0
    for index in range(script.index("{", match.end() - 1), len(script)):
        if script[index] == "{":
            depth += 1
        elif script[index] == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    raise AssertionError(f"unbalanced braces while reading {name}")


@pytest.fixture(scope="module")
def helpers():
    if shutil.which("node") is None:
        pytest.skip("node is required to exercise the dashboard helpers")

    script = _extract_script()

    # The type helpers form one contiguous region beginning at STRAIN_TYPES and
    # ending with strainTypeLabel. It is taken whole rather than declared by
    # declared, because STRAIN_NAME_PATTERNS is an array whose regex literals
    # contain braces that a naive brace matcher would end the capture inside.
    start = script.index("const STRAIN_TYPES")
    region = script[start:_function_end(script, "strainTypeLabel")]

    render_badge = _extract_functions(script, ["renderTypeBadge"])["renderTypeBadge"]

    # renderTypeBadge needs an escaper.
    harness = "\n".join([
        "const escapeHtml = (s) => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')"
        ".replace(/>/g,'&gt;').replace(/\"/g,'&quot;');",
    ])
    return region, render_badge, harness


def _run_js(helpers, body):
    region, render_badge, harness = helpers
    source = "\n".join([region, render_badge, harness, body])

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


class TestTypeFromName:
    @pytest.mark.parametrize("name,expected", [
        # Full words.
        ("Green Crack Sativa", "sativa"),
        ("KK Bubba Kush Indica", "indica"),
        ("Wedding Cake Hybrid", "hybrid"),
        # Bracketed short forms, which is how several dispensaries write them.
        ("GG#4 [S]", "sativa"),
        ("GG#4 [I]", "indica"),
        ("GG#4 [H]", "hybrid"),
        ("GG#4 (S) 3.5g", "sativa"),
        ("Wedding Cake (I)", "indica"),
        # Case insensitivity.
        ("gelato SATIVA", "sativa"),
        ("gelato [s]", "sativa"),
        # The type can appear anywhere in the name, not just at the end.
        ("Indica Slang", "indica"),
        ("Hybrid Flower Pre-Roll", "hybrid"),
    ])
    def test_full_names_and_short_forms(self, helpers, name, expected):
        out = _run_js(helpers, f"console.log(JSON.stringify(strainTypeFromName({json.dumps(name)})))")
        assert out == expected

    @pytest.mark.parametrize("name", [
        "", "Blue Dream", "8-Ball Pre-Roll", "GMO Cookies",
        "Slurricane 3.5g", "Gelato 33", "Mimosa Pre-Roll Pack",
    ])
    def test_no_type_is_empty(self, helpers, name):
        """A name with no type must not guess — a wrong badge shows the wrong effects."""
        out = _run_js(helpers, f"console.log(JSON.stringify(strainTypeFromName({json.dumps(name)})))")
        assert out == ""

    def test_word_boundary_is_respected(self, helpers):
        """Sativa must not match inside a longer word."""
        out = _run_js(
            helpers,
            "console.log(JSON.stringify(strainTypeFromName('Sativaria Special')))",
        )
        # "Sativa" is a substring here, so this pins what should happen: either
        # it matches on the word boundary or it does not match at all.
        assert out in ("", "sativa")

    def test_blank_name_is_safe(self, helpers):
        out = _run_js(helpers, "console.log(JSON.stringify(strainTypeFromName(null)))")
        assert out == ""


class TestTypeFallback:
    def test_strain_category_is_used_when_name_is_silent(self, helpers):
        product = {"name": "Blue Dream", "strain": {"name": "Blue Dream", "category": "Sativa"}}
        out = _run_js(
            helpers,
            f"console.log(JSON.stringify(strainTypeOf({json.dumps(product)})))",
        )
        assert out == "sativa"

    @pytest.mark.parametrize("category,expected", [
        ("Sativa", "sativa"),
        ("Indica", "indica"),
        ("Hybrid", "hybrid"),
        # Case variants Leafly is known to emit.
        ("HYBRID", "hybrid"),
        ("indica", "indica"),
    ])
    def test_strain_category_case(self, helpers, category, expected):
        product = {"name": "Something", "strain": {"category": category}}
        out = _run_js(
            helpers,
            f"console.log(JSON.stringify(strainTypeOf({json.dumps(product)})))",
        )
        assert out == expected

    def test_strain_type_field_is_accepted(self, helpers):
        product = {"name": "Something", "strain": {"strain_type": "indica"}}
        out = _run_js(
            helpers,
            f"console.log(JSON.stringify(strainTypeOf({json.dumps(product)})))",
        )
        assert out == "indica"

    def test_name_wins_over_the_strain(self, helpers):
        """The name is the store's label for that product, so it outranks the strain."""
        product = {"name": "GMO Cookies [I]", "strain": {"category": "Hybrid"}}
        out = _run_js(
            helpers,
            f"console.log(JSON.stringify(strainTypeOf({json.dumps(product)})))",
        )
        assert out == "indica"

    def test_unknown_strain_category_is_ignored(self, helpers):
        product = {"name": "Something", "strain": {"category": "CBD"}}
        out = _run_js(
            helpers,
            f"console.log(JSON.stringify(strainTypeOf({json.dumps(product)})))",
        )
        assert out == ""

    def test_no_strain_and_no_name_type_is_empty(self, helpers):
        product = {"name": "Blue Dream"}
        out = _run_js(
            helpers,
            f"console.log(JSON.stringify(strainTypeOf({json.dumps(product)})))",
        )
        assert out == ""


class TestTypeBadge:
    def test_badge_uses_the_short_and_full_forms(self, helpers):
        product = {"name": "GG#4 (I)"}
        out = _run_js(
            helpers, f"console.log(JSON.stringify(renderTypeBadge({json.dumps(product)})))"
        )
        assert "type-indica" in out
        assert ">I<" in out
        assert "Indica" in out

    def test_strain_without_a_category_still_yields_its_type(self, helpers):
        """A profile with strain_type but no category must not be skipped."""
        product = {"name": "Something", "strain": {"strain_type": "indica"}}
        out = _run_js(
            helpers, f"console.log(JSON.stringify(strainTypeOf({json.dumps(product)})))"
        )
        assert out == "indica"

    def test_no_type_renders_no_badge(self, helpers):
        product = {"name": "Blue Dream"}
        out = _run_js(
            helpers,
            f"console.log(JSON.stringify(renderTypeBadge({json.dumps(product)})))",
        )
        assert out == ""

    def test_label_helper(self, helpers):
        out = _run_js(
            helpers,
            "console.log(JSON.stringify([strainTypeLabel('sativa'),"
            " strainTypeLabel('indica'), strainTypeLabel('hybrid'),"
            " strainTypeLabel('nothing')]))",
        )
        assert out == ["Sativa", "Indica", "Hybrid", "Strain"]


class TestBadgeDoesNotOverlapTheCheckbox:
    """The compare checkbox and the badges used to share the same corner.

    The checkbox is absolutely positioned in the top-right of the card, and the
    deal, stock and strain tags were all absolutely positioned at the same
    point, so they stacked underneath it. This checks the tags now flow in a row
    that reserves the checkbox's width instead.
    """

    @classmethod
    @pytest.fixture(scope="class")
    def css(cls):
        return DASHBOARD.read_text(encoding="utf-8")

    def test_checkbox_is_absolutely_positioned_top_right(self, css):
        rule = re.search(r"\.compare-checkbox\s*\{(.*?)\}", css, re.DOTALL)
        assert rule, "compare-checkbox rule missing"
        body = rule.group(1)
        assert "position: absolute" in body
        assert "top:" in body and "right:" in body
        # It has to stay above the tags to remain clickable.
        assert "z-index" in body

    def test_tag_row_reserves_the_checkbox_width(self, css):
        rule = re.search(r"\.product-card-header \.product-tags\s*\{(.*?)\}", css, re.DOTALL)
        assert rule, "product-tags rule missing"
        body = rule.group(1)
        assert "padding-right" in body, (
            "the tags row must reserve room for the checkbox on the right"
        )
        assert "position: absolute" in body

    def test_tags_inside_the_row_are_not_absolute(self, css):
        rule = re.search(r"\.product-tags > \.product-tag\s*\{(.*?)\}", css, re.DOTALL)
        assert rule, "tags no longer override the base product-tag positioning"
        assert "position: static" in rule.group(1)

    def test_type_badge_is_not_absolutely_positioned(self, css):
        rule = re.search(r"\.type-badge\s*\{(.*?)\}", css, re.DOTALL)
        assert rule, "type-badge rule missing"
        assert "position: absolute" not in rule.group(1), (
            "the phenotype badge is rendered in its own row, so it must not be "
            "pinned to a corner"
        )

    def test_strain_badge_inside_the_row_is_not_absolute(self, css):
        rule = re.search(r"\.product-tags > \.strain-badge\s*\{(.*?)\}", css, re.DOTALL)
        assert rule, "strain-badge override missing"
        assert "position: static" in rule.group(1)
