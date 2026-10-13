"""Brand canonicalisation: the same brand must not appear twice.

Brands are typed once per store, so the catalogue carries several spellings of
one producer. Left alone each becomes its own sidebar row, brand filtering
misses half the products, and the counts are wrong.
"""

from utils.brands import (
    brand_key,
    clean_brand,
    make_brand_canonicalizer,
    resolve_brand_variants,
)


class TestBrandKey:
    def test_ignores_case(self):
        assert brand_key("FireBrand") == brand_key("Firebrand")

    def test_ignores_spacing_and_punctuation(self):
        assert brand_key("Tom & Berry") == brand_key("Tom &Berry")
        assert brand_key("Tom & Berry ") == brand_key("Tom&Berry")
        assert brand_key("Wellspring Fields") == brand_key("wellspring-fields")

    def test_ampersand_is_not_significant(self):
        # The "&" symbol itself is punctuation, so spacing around it and its
        # presence do not split a brand: "Tom & Berry" and "Tom Berry" fold.
        assert brand_key("Tom & Berry") == brand_key("Tom Berry")
        assert brand_key("Tom &Berry") == brand_key("Tom&Berry")

    def test_symbol_and_word_ampersand_are_distinct(self):
        # "and" is a word, not punctuation, so it is kept. Folding it would
        # merge "Seed & Strain" with "Seed and Strain", which are plausibly
        # different labels, so the two are left separate.
        assert brand_key("&Shine") != brand_key("and Shine")

    def test_distinguishes_real_brands(self):
        assert brand_key("FireBrand") != brand_key("Firebrand Infusions")
        assert brand_key("Standard Farms") != brand_key("The Standard")

    def test_empty_key(self):
        assert brand_key("") == ""
        assert brand_key(None) == ""


class TestCleanBrand:
    def test_collapses_internal_whitespace(self):
        assert clean_brand("The   Solid") == "The Solid"

    def test_strips_surrounding_whitespace(self):
        assert clean_brand("  Tom & Berry ") == "Tom & Berry"
        assert clean_brand("\tThe Standard\n") == "The Standard"

    def test_preserves_the_spelling_itself(self):
        # The ampersand spacing is how the brand is really written, so it is
        # left alone rather than rewritten into a spelling no store uses.
        assert clean_brand("&Shine") == "&Shine"
        assert clean_brand("Tom &Berry") == "Tom &Berry"

    def test_empty_stays_empty(self):
        assert clean_brand("") == ""
        assert clean_brand("   ") == ""
        assert clean_brand(None) == ""


class TestResolveBrandVariants:
    def test_most_common_spelling_wins(self):
        names = ["Firebrand"] * 5 + ["FireBrand"] * 2
        assert resolve_brand_variants(names)["firebrand"] == "Firebrand"

    def test_specific_typo_alias_wins(self):
        names = ["Wellspring Fields"] * 16 + ["Wellsprings Field"] * 8
        winners = resolve_brand_variants(names)
        assert winners["wellspringsfield"] == "Wellspring Fields"
        assert winners["wellspringfields"] == "Wellspring Fields"

    def test_ties_are_stable(self):
        # Equal counts must not depend on the order the names arrive in.
        forward = resolve_brand_variants(["FireBrand", "Firebrand"])
        backward = resolve_brand_variants(["Firebrand", "FireBrand"])
        assert forward == backward

    def test_ties_prefer_the_more_capitalised_spelling(self):
        assert resolve_brand_variants(["FireBrand", "Firebrand"])["firebrand"] == "FireBrand"

    def test_different_brands_stay_separate(self):
        winners = resolve_brand_variants(["FireBrand", "Firebrand Infusions"])
        assert winners["firebrand"] == "FireBrand"
        assert winners["firebrandinfusions"] == "Firebrand Infusions"

    def test_blank_names_are_ignored(self):
        assert resolve_brand_variants(["", "   ", None, "Kiva"]) == {"kiva": "Kiva"}


class TestCanonicalizer:
    def test_folds_typo_into_the_proper_name(self):
        canonical = make_brand_canonicalizer(["Wellspring Fields", "Wellsprings Field"])
        assert canonical("Wellsprings Field") == "Wellspring Fields"
        assert canonical("Wellspring Fields") == "Wellspring Fields"

    def test_folds_case_variants(self):
        canonical = make_brand_canonicalizer(["ORIA"] * 3)
        assert canonical("Oria") == "ORIA"

    def test_keeps_the_real_spelling(self):
        canonical = make_brand_canonicalizer(["&Shine"] * 3)
        assert canonical("&Shine") == "&Shine"

    def test_unknown_brand_is_still_cleaned(self):
        canonical = make_brand_canonicalizer(["Kiva"])
        # Whitespace is still collapsed for a brand the catalogue has never seen.
        assert canonical("  Kiva  ") == "Kiva"

    def test_empty_brand_passes_through(self):
        canonical = make_brand_canonicalizer(["Kiva"])
        assert canonical("") == ""
        assert canonical(None) == ""

    def test_idempotent(self):
        canonical = make_brand_canonicalizer(["Wellspring Fields", "Wellsprings Field"])
        once = canonical("Wellsprings Field")
        assert canonical(once) == once
