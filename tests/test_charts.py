"""Deal insight charts: the best categories and brands by discount quality.

The bar charts already existed but were unreachable, because the favicon
`<link>` used an unencoded inline SVG in an unquoted-looking attribute. The
HTML parser read its `href` past the intended closing quote and absorbed the
`<script>` tag that followed it, so Chart.js was never requested and both chart
functions silently returned on `typeof Chart === 'undefined'`.
"""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = PROJECT_ROOT / "dashboard" / "dashboard.html"
VENDOR_CHART = PROJECT_ROOT / "vendor" / "chart.umd.min.js"


@pytest.fixture(scope="module")
def html():
    return DASHBOARD.read_text(encoding="utf-8")


def _head(html, tag):
    """The element as a parser would see it, by scanning to the closing tag."""
    match = re.search(rf"<{tag}\b[^>]*>", html)
    return match.group(0) if match else ""


def _inline_script(html):
    """The dashboard's single inline script block."""
    blocks = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.DOTALL)
    assert blocks, "no inline script found"
    return blocks[0]


def _element(html, marker):
    """The outer HTML of the element whose opening tag contains `marker`.

    Depth counted, because a non-greedy match stops at the first nested `</div>`
    and would report a far smaller element than the real one.
    """
    pos = html.index(marker)
    open_tag = html.rindex("<div", 0, pos)
    depth = 0
    for index in range(open_tag, len(html)):
        if html.startswith("<div", index):
            depth += 1
        elif html.startswith("</div>", index):
            depth -= 1
            if depth == 0:
                return html[open_tag:index + len("</div>")]
    raise AssertionError(f"unbalanced divs while reading {marker!r}")


class TestFaviconDoesNotEatTheScript:
    """A regression test for the parser bug that broke the charts entirely."""

    def test_favicon_href_is_percent_encoded(self, html):
        """A raw `<svg` in an attribute value runs past its closing quote."""
        link = _head(html, "link")
        assert 'rel="icon"' in link, "favicon link not found"
        assert "%3Csvg" in link, (
            "the inline SVG must be percent-encoded so it cannot break out of "
            "the href attribute"
        )

    def test_favicon_href_contains_no_raw_svg_markup(self, html):
        link = _head(html, "link")
        assert "<svg" not in link and "</svg>" not in link, (
            "raw SVG markup inside the attribute will swallow following tags"
        )

    def test_script_tag_is_a_separate_element(self, html):
        """The chart script must not be inside the favicon's attribute."""
        link = _head(html, "link")
        assert "<script" not in link, (
            "the favicon href has absorbed the script tag; Chart.js will never load"
        )

    def test_script_tag_points_at_the_vendored_copy(self, html):
        match = re.search(r'<script[^>]*src="([^"]+)"', html)
        assert match, "no external script tag in the head"
        assert match.group(1) == "vendor/chart.umd.min.js"

    def test_no_cdn_dependency_remains(self, html):
        """A self-hosted dashboard should not need a CDN to draw its charts."""
        assert "cdn.jsdelivr.net" not in html


class TestVendoredChartJs:
    def test_vendor_file_exists(self):
        assert VENDOR_CHART.is_file(), (
            "vendor/chart.umd.min.js is missing; the dashboard will have no charts"
        )

    def test_vendor_file_is_substantial_javascript(self):
        size = VENDOR_CHART.stat().st_size
        assert 100_000 < size < 1_000_000, f"unexpected vendored size: {size}"

    def test_vendor_file_is_valid_javascript(self):
        if shutil.which("node") is None:
            pytest.skip("node is required to validate the vendored bundle")
        result = subprocess.run(
            ["node", "--check", str(VENDOR_CHART)], capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr

    def test_vendor_file_exports_chart(self):
        text = VENDOR_CHART.read_text(encoding="utf-8", errors="replace")
        assert "Chart" in text


class TestInsightMarkup:
    def test_two_insight_cards_exist(self, html):
        assert html.count('class="insight-card"') == 2

    def test_metric_selectors_exist(self, html):
        assert 'id="categoryMetric"' in html
        assert 'id="brandMetric"' in html

    @pytest.mark.parametrize("metric", ["count", "avg", "best"])
    def test_all_three_metrics_are_offered(self, html, metric):
        assert f'value="{metric}"' in html, f"{metric} ranking option is missing"

    def test_canvases_are_inside_a_bounded_wrapper(self, html):
        """Chart.js cannot size into a canvas with no fixed-height parent."""
        assert 'class="insight-canvas-wrap"' in html

    def test_empty_states_are_wired(self, html):
        assert 'id="categoryChartEmpty"' in html
        assert 'id="brandChartEmpty"' in html


class TestRankingLogic:
    """The metric computation, extracted and executed with Node."""

    def _script(self, html):
        blocks = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.DOTALL)
        assert blocks, "no inline script found"
        return blocks[0]

    def _extract(self, script, header_pattern, name):
        match = re.search(header_pattern, script, re.MULTILINE)
        assert match, f"{name} not found"
        start = match.start()
        depth = 0
        for index in range(script.index("{", match.end() - 1), len(script)):
            if script[index] == "{":
                depth += 1
            elif script[index] == "}":
                depth -= 1
                if depth == 0:
                    return script[start:index + 1]
        raise AssertionError(f"unbalanced braces reading {name}")

    @pytest.fixture(scope="class")
    def chart_helpers(self, html):
        if shutil.which("node") is None:
            pytest.skip("node is required to run the dashboard helpers")
        script = self._script(html)
        metrics = self._extract(script, r"^\s*const CHART_METRICS\s*=", "CHART_METRICS")
        avg = self._extract(script, r"^\s*function avgDiscountOf\(", "avgDiscountOf")
        return metrics, avg

    @staticmethod
    def _run(chart_helpers, body):
        metrics, avg = chart_helpers
        with tempfile.NamedTemporaryFile(
            "w", suffix=".js", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(metrics + "\n" + avg + "\n" + body)
            path = tmp.name
        try:
            result = subprocess.run(
                ["node", path], capture_output=True, text=True, timeout=30, encoding="utf-8"
            )
            assert result.returncode == 0, result.stderr
            return result.stdout.strip()
        finally:
            import os

            os.unlink(path)

    def test_count_metric_counts_deals(self, chart_helpers):
        out = self._run(chart_helpers, """
          const deals = [{discount_pct: 10}, {discount_pct: 30}, {discount_pct: 20}];
          const r = CHART_METRICS.count.compute(deals);
          console.log(JSON.stringify([r.value, r.display]));
        """)
        assert out == '[3,"3 deals"]'

    def test_avg_metric_averages_discounts(self, chart_helpers):
        out = self._run(chart_helpers, """
          const deals = [{discount_pct: 10}, {discount_pct: 30}, {discount_pct: 20}];
          const r = CHART_METRICS.avg.compute(deals);
          console.log(JSON.stringify([r.value, r.display]));
        """)
        assert out == '[20,"20.0% average"]'

    def test_best_metric_takes_the_deepest_discount(self, chart_helpers):
        out = self._run(chart_helpers, """
          const deals = [{discount_pct: 10}, {discount_pct: 60}, {discount_pct: 20}];
          const r = CHART_METRICS.best.compute(deals);
          console.log(JSON.stringify([r.value, r.display]));
        """)
        assert out == '[60,"60.0% off"]'

    def test_avg_metric_handles_an_empty_group(self, chart_helpers):
        out = self._run(chart_helpers, """
          const r = CHART_METRICS.avg.compute([]);
          console.log(JSON.stringify([r.value, r.display]));
        """)
        assert out == '[0,"0.0% average"]'

    def test_best_metric_handles_an_empty_group(self, chart_helpers):
        out = self._run(chart_helpers, "console.log(JSON.stringify(CHART_METRICS.best.compute([]).value))")
        assert out == "0"

    def test_missing_discount_pct_is_treated_as_zero(self, chart_helpers):
        out = self._run(chart_helpers, """
          const deals = [{discount_pct: 10}, {}, {discount_pct: 20}];
          console.log(JSON.stringify(CHART_METRICS.avg.compute(deals).value));
        """)
        assert out == "10"

    def test_avg_discount_of_formats_for_the_tooltip(self, chart_helpers):
        out = self._run(chart_helpers, "console.log(JSON.stringify(avgDiscountOf([{discount_pct: 25}])))")
        assert out == '"25.0% average"'

    def test_avg_discount_of_handles_no_deals(self, chart_helpers):
        out = self._run(chart_helpers, "console.log(JSON.stringify(avgDiscountOf([])))")
        assert out == '"\u2014"'


class TestChartsFollowFilters:
    """The charts read `displayedProducts`, so they must actually use it."""

    def test_charts_read_the_filtered_view(self, html):
        script = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.DOTALL)[0]
        assert "displayedProducts" in script
        # The old implementation read allData.products, which ignored filters.
        build = script[script.index("function buildInsightChart"):]
        build_end = build.index("\n    }", build.index("window[chartSlot] = new Chart"))
        body = build[:build_end]
        assert "allData.products" not in body, (
            "the insight chart still reads the unfiltered catalogue"
        )

    def test_charts_are_refreshed_with_stats(self, html):
        script = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.DOTALL)[0]
        update_stats = script[script.index("function updateStats"):]
        assert "updateCategoryChart();" in update_stats
        assert "updateBrandChart();" in update_stats

    def test_metric_selectors_re_render_on_change(self, html):
        assert re.search(
            r"getElementById\('categoryMetric'\)\?\.addEventListener\('change'", html
        ), "changing the category metric does not re-render"


class TestChartsAreScrollable:
    """The charts scroll with the grid instead of pinning the top of the screen.

    `.main` is `overflow: hidden` and only `.products-area` scrolls, so a panel
    placed as a sibling of it is fixed in place forever.
    """

    def test_insights_are_inside_the_scroll_container(self, html):
        """The section must be a descendant of #productsArea."""
        assert 'class="insights"' in _element(html, 'id="productsArea"'), (
            "the insights section is outside #productsArea, so it will never scroll away"
        )

    def test_insights_section_is_not_a_sibling_of_products_area(self, html):
        """Nothing about the old fixed placement may come back."""
        stats_end = html.index("</div>", html.index('id="statsBar"'))
        area_pos = html.index('class="products-area"')
        assert stats_end < area_pos, "stats-bar and products-area are nested unexpectedly"
        between = html[stats_end:area_pos]
        assert 'class="insights"' not in between, (
            "the insights section is still a fixed sibling of the scroll container"
        )

    def test_insights_body_is_collapsible(self, html):
        assert 'class="insights-body"' in html
        assert 'id="insightsToggle"' in html

    def test_collapsed_hides_the_body(self, html):
        assert ".insights.collapsed .insights-body { display: none; }" in html

    def test_toggle_button_has_aria_state(self, html):
        assert re.search(r'id="insightsToggle"[^>]*aria-expanded', html), (
            "the collapse button must expose its state to assistive tech"
        )


class TestSidebarToggle:
    def test_sidebar_has_the_id_the_toggle_targets(self, html):
        assert 'id="sidebar"' in html

    def test_toggle_button_exists_in_the_header(self, html):
        assert 'id="sidebarToggle"' in html

    def test_collapsed_sidebar_takes_no_width(self, html):
        """A zero-width slot, not a gap, keeps the layout flowing."""
        assert ".sidebar.collapsed" in html
        assert re.search(r"\.sidebar\.collapsed\s*\{[^}]*width:\s*0", html, re.DOTALL)

    def test_toggle_stays_reachable_when_collapsed(self, html):
        """The button lives in the header, not inside the collapsible panel."""
        header_block = html[:html.index("</header>")]
        assert 'id="sidebarToggle"' in header_block, (
            "the toggle is inside the panel, so it disappears when it collapses"
        )

    def test_panel_states_are_persisted(self, html):
        script = _inline_script(html)
        assert "SIDEBAR_STATE_KEY" in script
        assert "INSIGHTS_STATE_KEY" in script
        assert "localStorage.setItem" in script

    def test_states_are_restored_before_first_render(self, html):
        script = _inline_script(html)
        dom_loaded = script[script.index("DOMContentLoaded"):]
        assert "applyStoredPanelStates()" in dom_loaded
        # Restoring after loadData() would size the charts for a hidden panel.
        assert dom_loaded.index("applyStoredPanelStates()") < dom_loaded.index("loadData()")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
