"""Stores name the same shelf differently, so categories are canonicalised.

Dutchie reports ``Concentrate`` while Klutch scrapes ``/collections/concentrates``
and calls it ``Concentrates``. Left alone, that yields two sidebar groups for one
shelf and splits the category counts. A stale snapshot carried ``Vapes`` where
the live data says ``Vaporizers``, which is the same problem.
"""

import pytest

from utils.categories import (
    canonical_category,
    canonical_category_named,
    category_key,
    infer_subcategory,
    is_canonical,
    main_category,
    sub_category,
)

SEP = " \u00b7 "


class TestCanonicalMainCategory:
    def test_plural_collapses_onto_singular(self):
        assert canonical_category("Concentrates") == "Concentrate"
        assert canonical_category("Edibles") == "Edible"
        assert canonical_category("Flowers") == "Flower"
        assert canonical_category("Tinctures") == "Tincture"

    @pytest.mark.parametrize("raw,expected", [
        ("Concentrate", "Concentrate"),
        ("Concentrates", "Concentrate"),
        ("Extracts", "Concentrate"),
        ("Hash", "Concentrate"),
    ])
    def test_concentrate_synonyms_merge(self, raw, expected):
        assert canonical_category(raw) == expected

    @pytest.mark.parametrize("raw,expected", [
        ("Vapes", "Vaporizers"),
        ("Vape", "Vaporizers"),
        ("Carts", "Vaporizers"),
        ("Cartridges", "Vaporizers"),
        ("Vaporizers", "Vaporizers"),
    ])
    def test_vaporizer_synonyms_merge(self, raw, expected):
        assert canonical_category(raw) == expected

    @pytest.mark.parametrize("raw,expected", [
        ("Pre-Roll", "Pre-Rolls"),
        ("Pre Rolls", "Pre-Rolls"),
        ("Prerolls", "Pre-Rolls"),
        ("Pre-Rolls", "Pre-Rolls"),
    ])
    def test_pre_roll_spellings_merge(self, raw, expected):
        assert canonical_category(raw) == expected

    def test_topical_stays_plural(self):
        """The live data uses "Topicals", so it is the canonical form here."""
        assert canonical_category("Topicals") == "Topicals"
        assert canonical_category("Topical") == "Topicals"


class TestSubcategoryPreserved:
    def test_subcategory_is_kept_verbatim(self):
        assert canonical_category(f"Concentrates{SEP}live resin") == f"Concentrate{SEP}live resin"

    def test_subcategory_of_a_canonical_main_is_unchanged(self):
        raw = f"Flower{SEP}premium"
        assert canonical_category(raw) == raw

    def test_merge_only_touches_the_main_part(self):
        # A store-specific subcategory name is not what differs between stores.
        raw = f"Edibles{SEP}hard candy"
        assert canonical_category(raw) == f"Edible{SEP}hard candy"


class TestAlreadyCanonical:
    @pytest.mark.parametrize("raw", [
        "Flower", f"Flower{SEP}premium", "Concentrate", "Edible",
        "Vaporizers", "Tincture", "Topicals", "Accessories", "Pre-Rolls",
    ])
    def test_idempotent(self, raw):
        assert canonical_category(canonical_category(raw)) == canonical_category(raw)

    @pytest.mark.parametrize("raw", ["Flower", f"Concentrate{SEP}rosin", "Vaporizers"])
    def test_canonical_input_is_reported_canonical(self, raw):
        assert is_canonical(raw)


class TestUnknownCategories:
    def test_unknown_category_is_left_alone(self):
        """Guessing at an unrecognised name could merge two real shelves."""
        assert canonical_category("Merch") == "Merch"
        assert canonical_category("Something Else") == "Something Else"

    @pytest.mark.parametrize("raw,expected", [("", ""), (None, None)])
    def test_empty_and_none_pass_through(self, raw, expected):
        assert canonical_category(raw) == expected


class TestSplitHelpers:
    def test_main_category(self):
        assert main_category(f"Concentrate{SEP}rosin") == "Concentrate"
        assert main_category("Flower") == "Flower"

    def test_sub_category(self):
        assert sub_category(f"Concentrate{SEP}rosin") == "rosin"
        assert sub_category("Flower") == ""

    def test_category_key_ignores_spacing_and_punctuation(self):
        assert category_key("Pre-Rolls") == category_key("Pre Rolls")
        assert category_key("Concentrate") == category_key("concentrate")


class TestStoreNaming:
    def test_klutch_and_dutchie_agree_on_concentrate(self):
        """The two scrapers must not produce two shelves for one category."""
        klutch_name = "Concentrates"
        dutchie_name = "Concentrate"
        assert canonical_category(klutch_name) == canonical_category(dutchie_name)

    def test_stale_vapes_snapshot_matches_live_vaporizers(self):
        assert canonical_category("Vapes") == canonical_category("Vaporizers")


class TestApiCanonicalisesCategories:
    """Existing rows and snapshots were written before canonical names existed."""

    @staticmethod
    def _write_deal(storage, category, product_id):
        from models import Deal
        deal = Deal(
            store_id="s", product_id=product_id, name=f"Item {product_id}",
            category=category, original_price=45.0, sale_price=45.0,
            discount_pct=0.0, image_url="", product_url="",
        )
        storage.save_seen_deal(deal)
        return deal

    @staticmethod
    def _handler(storage):
        """A handler bound to scratch storage, without running __init__."""
        import threading
        from pathlib import Path

        from api_server import DashboardHandler

        handler = DashboardHandler.__new__(DashboardHandler)
        handler.storage = storage
        # Set by __init__; the cache starts empty and is filled on first use.
        handler._strain_index = None
        handler._strain_index_lock = threading.Lock()
        # get_full_menu resolves the enabled store set, which reads config.yaml
        # from the project root.
        handler.project_root = Path(__file__).resolve().parent.parent
        return handler

    def test_deal_rows_are_canonicalised_on_the_way_out(self, tmp_path):
        from storage.sqlite import SQLiteStorage

        storage = SQLiteStorage(db_path=str(tmp_path / "cats.db"))
        self._write_deal(storage, "Concentrates", "1")

        deals = self._handler(storage).get_all_deals()

        assert [d["category"] for d in deals] == ["Concentrate"]

    def test_snapshots_are_canonicalised_on_the_way_out(self, tmp_path):
        from datetime import date, timedelta

        from models import Deal, WeeklySnapshot
        from storage.sqlite import SQLiteStorage

        storage = SQLiteStorage(db_path=str(tmp_path / "cats.db"))

        deal = Deal(
            store_id="s", product_id="1", name="Old Item", category="Vapes",
            original_price=45.0, sale_price=45.0, discount_pct=0.0,
            image_url="", product_url="",
        )
        storage.save_weekly_snapshot(WeeklySnapshot(
            store_id="s", week_start=date.today() - timedelta(days=date.today().weekday()),
            items=[deal],
        ))
        # A store only the dashboard lists is served, so the snapshot's store
        # has to be a real one here.
        storage.save_seen_deal(deal)

        products = self._handler(storage).get_full_menu()

        assert [p["category"] for p in products] == ["Vaporizers"]


class TestConsolidatedShelves:
    """Small shelves and event names that duplicate a bigger category."""

    @pytest.mark.parametrize("raw,expected", [
        # Cleaning supplies are accessories, not a shelf of their own.
        ("Cleaning & Care", "Accessories"),
        ("cleaning care", "Accessories"),
        ("Cleaning Supplies", "Accessories"),
        # Vape coils are replacement parts.
        ("Coil", "Accessories"),
        ("Coils", "Accessories"),
        # Event and artist drops from the glass stores are still glass art.
        ("Ohio Glassblowers Show 2025", "Glass"),
        ("Steve Sizelove Drop 2025", "Glass"),
        # Donation and Insurance are not product shelves.
        ("Donation", "Misc"),
        ("Insurance", "Misc"),
    ])
    def test_small_shelves_fold_into_bigger_ones(self, raw, expected):
        assert canonical_category(raw) == expected

    @pytest.mark.parametrize("raw", [
        "Accessories", "Glass", "Misc", f"Accessories{SEP}dab tools",
        f"Glass{SEP}rigs",
    ])
    def test_consolidation_targets_are_idempotent(self, raw):
        assert canonical_category(canonical_category(raw)) == canonical_category(raw)

    def test_subcategory_survives_consolidation(self):
        raw = f"Cleaning & Care{SEP}supplies"
        assert canonical_category(raw) == f"Accessories{SEP}supplies"


class TestDabMats:
    """Dab mats are their own shelf, not a dab tool and not merch."""

    @pytest.mark.parametrize("raw,expected", [
        ("Dab Mats", "Dab Mats"),
        ("dab mats", "Dab Mats"),
        ("Dab Mat", "Dab Mats"),
        ("mat", "Dab Mats"),
        ("mats", "Dab Mats"),
        ("Dab Pad", "Dab Mats"),
    ])
    def test_spellings_collapse_onto_one_shelf(self, raw, expected):
        assert canonical_category(raw) == expected

    def test_subcategory_is_normalised_under_accessories(self):
        """A store that files mats under Accessories keeps the shelf, but the
        row name stops depending on how that store spells it."""
        assert canonical_category(f"Accessories{SEP}dab mats") == f"Accessories{SEP}dab mats"
        assert canonical_category(f"Accessories{SEP}mats") == f"Accessories{SEP}dab mats"

    def test_other_shelves_are_untouched(self):
        """"mat" must not swallow a shelf that merely contains the letters."""
        assert canonical_category("Merch") == "Merch"
        assert canonical_category("Accessories") == "Accessories"

    def test_idempotent(self):
        raw = "Dab Mats"
        assert canonical_category(canonical_category(raw)) == canonical_category(raw)


class TestDabMatNameRescue:
    """A mat filed under a catch-all shelf with no subcategory is recovered
    from its product name, so it lands on Dab Mats instead of Misc."""

    @pytest.mark.parametrize("category,name", [
        ("misc", "Puffco Dab Mat"),
        ("Misc", "Puffco Dab Mat XL"),
        ("Uncategorized", "Dab Mat"),
        ("", "Dab Mat"),
        (None, "Dab Mat"),
        ("misc", "dab-mat"),
        ("misc", "Dab Pad"),
    ])
    def test_rescued_onto_dab_mats(self, category, name):
        assert canonical_category_named(category, name) == "Dab Mats"

    @pytest.mark.parametrize("category,name", [
        ("misc", "Package Protection"),   # a Misc item stays in Misc
        ("Misc", "Add On Donation"),
        ("", "Grinder"),
    ])
    def test_other_items_left_alone(self, category, name):
        assert canonical_category_named(category, name) == canonical_category(category)

    def test_named_rescue_does_not_touch_real_shelves(self):
        # A mat title must not hijack a product genuinely filed elsewhere.
        assert canonical_category_named("Flower", "Dab Mat Cake") == "Flower"
        assert canonical_category_named("Puffco", "Puffco Dab Mat") == "Puffco"

    def test_canonical_category_signature_unchanged(self):
        # The rescue lives in a separate helper; canonical_category keeps its
        # single-argument contract and None passthrough.
        assert canonical_category("misc") == "Misc"
        assert canonical_category(None) is None


class TestSubcategoryFromTitle:
    """When a product has no subcategory, a known one in its title is used."""

    @pytest.mark.parametrize("main,name,expected_sub", [
        # Accessories: brand stores file these with no product_type beyond the shelf.
        ("Accessories", "Premium Herb Grinder 4pc", "grinders"),
        ("Accessories", "Torch Lighter Refillable", "lighters"),
        ("Accessories", "4 Piece Grinder", "grinders"),
        ("Vaporizers", "510 Thread Cartridge", "cartridges"),
        ("Vaporizers", "Disposable Vape Pen", "disposables"),
        ("Flower", "Small Buds Jar", "small buds"),
        ("Concentrate", "Blue Dream Live Rosin", "live rosin"),
    ])
    def test_known_subcategory_attached_from_title(self, main, name, expected_sub):
        assert canonical_category_named(main, name) == f"{main}{SEP}{expected_sub}"

    def test_existing_subcategory_is_kept(self):
        raw = f"Flower{SEP}premium"
        assert canonical_category_named(raw, "Small Buds") == raw

    def test_main_without_subcategories_is_untouched(self):
        # Apparel, Hats and Bags have no curated subcategories, so the title
        # must not invent one.
        assert canonical_category_named("Apparel", "Graphic Hoodie Blue") == "Apparel"
        assert canonical_category_named("Bags", "Woven Backpack") == "Bags"

    def test_no_match_leaves_main_alone(self):
        assert canonical_category_named("Vaporizers", "Arcata-TL") == "Vaporizers"

    def test_infer_subcategory_helper(self):
        assert infer_subcategory("Concentrate", "live rosin") == "live rosin"
        assert infer_subcategory("Accessories", "cool gadget") == ""
        assert infer_subcategory("Apparel", "hoodie") == ""


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
