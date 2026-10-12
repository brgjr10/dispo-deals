"""The infinite-scroll scaffold must never occupy a product card slot.

The grid is a CSS grid, so every child of #productGrid is a grid item. The
virtualisation scaffold (`vg-sentinel`, `vg-loader`, `vg-end`) is also a child,
so unless it is excluded from the card flow the first card is pushed one place
right - a blank first slot that appears at every viewport width.
"""

import re
from pathlib import Path

import pytest

DASHBOARD = Path(__file__).resolve().parent.parent / "dashboard.html"


@pytest.fixture(scope="module")
def html():
    return DASHBOARD.read_text(encoding="utf-8")


def _css_rule(html, selector):
    """Return the declaration block of a top-level CSS rule."""
    match = re.search(rf"{re.escape(selector)}\s*\{{(.*?)\}}", html, re.DOTALL)
    assert match, f"{selector} rule not found"
    return match.group(1)


class TestScaffoldSpansFullWidth:
    @pytest.mark.parametrize("selector", [".vg-sentinel", ".vg-loader", ".vg-end", ".vg-empty"])
    def test_scaffold_row_spans_every_column(self, html, selector):
        """Without a full-width span a scaffold row still takes a card cell."""
        assert "grid-column: 1 / -1" in _css_rule(html, selector), selector


class TestStaticScaffoldOrder:
    def test_sentinel_is_not_the_first_row(self, html):
        """The sentinel is the one scaffold row not hidden by default.

        Written first, it becomes the first grid cell and pushes the cards one
        place right before a single product has been rendered.
        """
        match = re.search(r'id="productGrid">\s*(.*?)\s*</div>', html, re.DOTALL)
        assert match, "productGrid markup not found"
        first_child = re.search(r'class="([^"]+)"', match.group(1))
        assert first_child, "productGrid has no children"
        assert "vg-sentinel" not in first_child.group(1), (
            "the sentinel is written ahead of the cards, so it takes the first cell"
        )

    def test_sentinel_is_written_last(self, html):
        """It is the infinite-scroll trigger, so it belongs at the bottom."""
        # A non-greedy match would stop at the first nested </div>, so the block
        # is captured by depth counting. The opening <div of productGrid itself
        # has to be counted, or the block ends at the first child's close.
        start = html.index('id="productGrid">')
        open_tag = html.rindex('<div', 0, start)
        depth = 0
        end = open_tag
        for index in range(open_tag, len(html)):
            if html.startswith("<div", index):
                depth += 1
            elif html.startswith("</div>", index):
                depth -= 1
                if depth == 0:
                    end = index
                    break
        block = html[start:end]
        classes = re.findall(r'class="([^"]+)"', block)
        assert classes and classes[-1].strip().startswith("vg-sentinel"), (
            f"sentinel is not the last row: {classes}"
        )


class TestCardsRenderAboveScaffold:
    def _grid_script(self, html):
        blocks = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.DOTALL)
        assert blocks, "no inline script found"
        return blocks[0]

    def test_batch_is_inserted_before_the_footer_rows(self, html):
        """Cards insert at `beforebegin`, so the scaffold stays below them."""
        script = self._grid_script(html)
        assert "insertAdjacentHTML('beforebegin'" in script, (
            "cards appended with 'beforeend', which places them under the scaffold"
        )

    def test_render_writes_scaffold_last(self, html):
        """The scaffold template lists the sentinel after the loader and end."""
        script = self._grid_script(html)
        render = re.search(
            r"function renderVirtualizedGrid\(\).*?function loadMoreProducts",
            script, re.DOTALL,
        )
        assert render, "renderVirtualizedGrid not found"
        template = render.group(0)
        assert template.index("vgSentinel") > template.index("vgLoader")
        assert template.index("vgSentinel") > template.index("vgEnd")


class TestObserverLifecycle:
    def test_sentinel_is_re_observed_after_each_render(self, html):
        """renderVirtualizedGrid recreates the sentinel, so it must re-observe."""
        script = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.DOTALL)[0]
        render = re.search(
            r"function renderVirtualizedGrid\(\).*?function loadMoreProducts",
            script, re.DOTALL,
        )
        assert render and "observeSentinel()" in render.group(0), (
            "the re-created sentinel is not observed, so infinite scroll stops "
            "after the first render"
        )

    def test_stale_sentinels_are_disconnected(self, html):
        """Observing without disconnecting accumulates detached sentinels."""
        script = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.DOTALL)[0]
        observe = re.search(
            r"function observeSentinel\(\).*?\n\}", script, re.DOTALL
        )
        assert observe and "observer.disconnect()" in observe.group(0), (
            "stale sentinels are never dropped"
        )

    def test_scroll_is_bound_on_the_scroll_container(self, html):
        """The scroll container is #productsArea, not the window."""
        script = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.DOTALL)[0]
        assert "getElementById('productsArea')" in script


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
