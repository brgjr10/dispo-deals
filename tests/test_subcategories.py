"""Subcategory canonicalisation.

Stores write the same shelf differently. Inside Pre-Rolls, one store calls the
shelf "infused", another "infused-pre-roll-pack" and a third "Infused Pre Roll
5-Pack", all for the same products. Left alone each becomes its own sidebar row
and splits the counts, so they have to fold into one "infused" shelf.

The rename must stay inside its own shelf: "infused-flower" under Concentrate is
a different product and must not be touched by a Pre-Rolls rule.
"""

import pytest

from utils.categories import (
    canonical_category,
    canonical_subcategory,
    category_key,
)


class TestInfusedPreRolls:
    @pytest.mark.parametrize("sub", [
        "infused",
        "Infused Pre-Roll Pack",
        "infused-pre-roll-pack",
        "Infused Pre-Roll Packs",
        "infused pack",
        "Infused Pack",
        "infused-preroll",
        "infused-prerolls",
    ])
    def test_every_infused_pack_spelling_folds_to_infused(self, sub):
        assert canonical_category(f"Pre-Rolls · {sub}") == "Pre-Rolls · infused"

    def test_plain_short_form(self):
        assert canonical_category("Pre-Rolls · Infused-Pre-Roll-Pack") == "Pre-Rolls · infused"

    def test_infused_alone_is_unchanged(self):
        assert canonical_category("Pre-Rolls · infused") == "Pre-Rolls · infused"

    def test_non_infused_subcategories_are_left_alone(self):
        # These are genuinely different shelves, so they must not be folded.
        assert canonical_category("Pre-Rolls · singles") == "Pre-Rolls · singles"
        assert canonical_category("Pre-Rolls · packs") == "Pre-Rolls · packs"

    def test_two_spellings_collapse_to_the_same_shelf(self):
        a = canonical_category("Pre-Rolls · infused")
        b = canonical_category("Pre-Rolls · Infused Pre-Roll Pack")
        assert a == b, "the two spellings must land on one shelf so they share a row"

    def test_alias_does_not_leak_to_other_shelves(self):
        # Concentrate has its own infused shelf, which is a different product.
        assert canonical_category("Concentrate · infused-flower") == "Concentrate · infused-flower"

    def test_main_category_is_still_canonicalised(self):
        # The main category rename still has to happen alongside the sub rename.
        assert canonical_category("Pre-Roll · Infused Pre-Roll Pack") == "Pre-Rolls · infused"

    def test_bare_pre_rolls_has_no_sub(self):
        assert canonical_category("Pre-Rolls") == "Pre-Rolls"


class TestCanonicalSubcategory:
    def test_unknown_subcategory_is_kept(self):
        assert canonical_subcategory("Pre-Rolls", "something new") == "something new"

    def test_subcategory_is_trimmed(self):
        assert canonical_subcategory("Pre-Rolls", "  singles  ") == "singles"

    def test_empty_subcategory(self):
        assert canonical_subcategory("Pre-Rolls", "") == ""
        assert canonical_subcategory("Pre-Rolls", None) == ""

    def test_same_subcategory_name_can_differ_per_main(self):
        # "infused" means one thing under Pre-Rolls; a shelf with no alias rule
        # must return its own name rather than borrowing another's.
        assert canonical_subcategory("Edible", "sugar-free") == "sugar-free"

    def test_keys_are_punctuation_insensitive(self):
        assert category_key("Infused Pre-Roll Pack") == category_key("infused-prerollpack")


class TestIdempotence:
    def test_canonicalising_twice_changes_nothing(self):
        for raw in [
            "Pre-Rolls · infused",
            "Pre-Rolls · Infused Pre-Roll Pack",
            "Pre-Rolls · singles",
            "Pre-Rolls · packs",
            "Flower · premium",
        ]:
            once = canonical_category(raw)
            assert canonical_category(once) == once, raw
