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
        ("Ohio Glassblowers Show 2025", "Gear"),
        ("Steve Sizelove Drop 2025", "Gear"),
        # Donation and Insurance are not product shelves.
        ("Donation", "Gear"),
        ("Insurance", "Gear"),
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


class TestScarfSlidesAreScarves:
    """A scarf slide is a scarf, not footwear.

    The stores sell them beside the scarves, and the name only shares a word
    with sandals. Before this they landed on the Footwear slides row.
    """

    NAME = "Daisy Scarf Slide in Vintage White"

    def test_scarf_slides_category_is_a_scarf(self):
        assert canonical_category("Scarf Slides") == "Apparel"
        assert canonical_category_named("Scarf Slides", self.NAME) == f"Apparel{SEP}Scarves & Gloves"

    def test_a_real_flip_flop_stays_footwear(self):
        assert canonical_category_named("Flip Flop", "Beach Flip Flops") == f"Footwear{SEP}Slides"

    def test_a_scarf_slide_title_is_not_read_as_footwear(self):
        """The title must not pull a scarf onto the slides row either."""
        assert infer_subcategory("Footwear", self.NAME) == ""
        assert infer_subcategory("Apparel", self.NAME) == "Scarves & Gloves"

    def test_other_scarves_are_unaffected(self):
        assert canonical_category_named("Scarf", "Check Scarf") == f"Apparel{SEP}Scarves & Gloves"


class TestShelvesThatStillLeaked:
    """Bare store shelves that were still their own sidebar row.

    Each of these was a top-level group in the rendered nav because only its
    subcategory label had been mapped, not the shelf itself.
    """

    @pytest.mark.parametrize("raw,expected", [
        # 670 products sitting in their own row above Apparel.
        ("Bottoms", "Apparel"),
        ("Jacket", "Apparel"),
        ("jacket", "Apparel"),
        ("Shirt", "Apparel"),
        ("shirt", "Apparel"),
        # Nine separate Puffco rows next to the Puffco group.
        ("Puffco Accessories", "Gear"),
        ("Puffco Attachments", "Gear"),
        ("Puffco Charms", "Gear"),
        ("Puffco Dry Tops", "Gear"),
        ("Puffco Joysticks", "Gear"),
        ("Puffco Pivot Mouthpieces", "Gear"),
        ("Puffco Proxy Attachments", "Gear"),
        # Home goods, jewellery and a smoke-shop shelf.
        ("Blankets", "Gear"),
        ("blanket", "Gear"),
        ("Bracelet", "Accessories"),
        ("bracelet", "Accessories"),
        ("Choker", "Accessories"),
        ("choker", "Accessories"),
        ("Saber Accessory", "Accessories"),
    ])
    def test_shelf_folds_into_its_group(self, raw, expected):
        assert canonical_category(raw) == expected


class TestMousepadsAreDabMats:
    """A mousepad is a dab mat under a different name.

    The stores sell the silicone sheets next to desk mats and file some of
    them under a catch-all shelf, so without these aliases the mats split
    between three shelves.
    """

    @pytest.mark.parametrize("raw", [
        "Mousepad", "Mousepads", "Mouse Pad", "Mouse Pads", "mouse pad",
    ])
    def test_shelf_collapses_onto_dab_mats(self, raw):
        assert canonical_category(raw) == "Gear"

    @pytest.mark.parametrize("raw", [
        f"Accessories{SEP}Mousepad",
        f"Accessories{SEP}mousepads",
        f"Accessories{SEP}Mouse Pad",
    ])
    def test_subcategory_collapses_onto_dab_mats(self, raw):
        assert canonical_category(raw) == f"Accessories{SEP}dab mats"

    @pytest.mark.parametrize("name", [
        "Large Mousepad", "Silicone Mouse Pad", "mouse-pad", "MousePad XL",
    ])
    def test_a_mat_filed_under_a_catch_all_is_rescued(self, name):
        assert canonical_category_named("misc", name) == "Gear"

    @pytest.mark.parametrize("category", [
        "Glass", "Accessories", "Mousepad", "Misc", "Other Shit", "",
        "Accessories · dab mats", "Concentrates",
    ])
    def test_a_mousepad_lands_on_dab_mats_wherever_it_was_filed(self, category):
        """The stores file the silicone sheets beside their other stock.

        A catch-all rescue alone could not reach a mat filed under Glass or
        Accessories, which is how mousepads ended up scattered across shelves.
        """
        assert main_category(canonical_category_named(category, "Custom Mousepad")) == "Gear"

    def test_a_dab_pad_is_not_relocated_out_of_concentrates(self):
        """Only the mousepad spelling is force-moved.

        "Dab pad" is a genuine Concentrates shelf, so relocating it would move
        a real product onto the wrong shelf.
        """
        assert canonical_category_named(
            "Concentrates · quartz", "Quartz Banger Dab Pad"
        ) == f"Concentrate{SEP}quartz"

    def test_a_generic_product_is_not_rescued(self):
        assert canonical_category_named("misc", "Premium Herb Grinder") == "Gear"


class TestBrandStoreShelves:
    """Brand stores file one shelf under dozens of names.

    Each of these was its own row in the sidebar before consolidation, which
    split the counts and buried the real shelves.
    """

    @pytest.mark.parametrize("raw,expected", [
        # Clothing: case, typo and wholesale-code variants of one shelf.
        ("APPAREL", "Apparel"),
        ("T-Shirts", "Apparel"),
        ("tshirts", "Apparel"),
        ("TEE SS PRINTED", "Apparel"),
        ("BOTTOM KNIT SHORT", "Apparel"),
        ("MAXI", "Apparel"),
        ("Mini", "Apparel"),
        # Glass: a beaker size, a Prism series and an artist drop.
        ("45mm beakers", "Gear"),
        ("Clear Models (2nd)", "Gear"),
        ("Hologram Toro", "Gear"),
        ("full color signature", "Gear"),
        # Smoke-shop one-offs.
        ("Accesory", "Accessories"),
        ("Silicone Accessory Kit", "Accessories"),
        ("Spoon Pipe", "Accessories"),
        ("Terp Timer", "Accessories"),
        # Sale flags and placeholders are not product shelves.
        ("Other Shit", "Gear"),
        ("Expivi Product Replica", "Gear"),
        ("Shipping Protection", "Gear"),
        ("Extras Sale", "Gear"),
        # Home goods are not a product shelf either.
        ("Drinkware", "Gear"),
        ("Kitchen & Bar", "Gear"),
        # Cannabis shelves keep their existing canonical spelling.
        ("Concentrates", "Concentrate"),
        ("1g THCA cartridge", "Vaporizers"),
        ("Beverage", "Edible"),
        ("Dabbing Mat", "Gear"),
        ("Thca Diamonds", "Concentrate"),
        ("$55 smalls ounce", "Flower"),
        ("Official Puffco", "Gear"),
        ("Smart Rig Kit", "Gear"),
        ("Skateboard Deck", "Clothing"),
        # A name already canonical is left alone.
        ("Modul", "Modül"),
    ])
    def test_stray_shelf_folds_into_a_main_group(self, raw, expected):
        assert canonical_category(raw) == expected

    @pytest.mark.parametrize("raw,expected", [
        # Wholesale taxonomy codes become readable labels. A printed tee is a
        # t-shirt, so the code folds into that row rather than standing alone.
        (f"Apparel{SEP}TEE SS PRINTED", f"Apparel{SEP}T-Shirts"),
        (f"Apparel{SEP}BOTTOM KNIT SHORT", f"Apparel{SEP}Knit Shorts"),
        (f"Apparel{SEP}HOODED FLEECE CUT/ SEW", f"Apparel{SEP}Hooded Fleece"),
        (f"Apparel{SEP}OUTERWEAR WINDBREAKER CUT/SEW", f"Apparel{SEP}Windbreaker"),
        # Singular, plural and case variants merge onto one row.
        (f"Apparel{SEP}Hoodie", f"Apparel{SEP}Hoodies"),
        (f"Apparel{SEP}Hoodies", f"Apparel{SEP}Hoodies"),
        (f"Apparel{SEP}Smalls", f"Apparel{SEP}Smalls"),
        # Spellings that each used to be their own row.
        (f"Apparel{SEP}long sleeve", f"Apparel{SEP}Tops"),
        (f"Apparel{SEP}longsleeve", f"Apparel{SEP}Tops"),
        (f"Apparel{SEP}Jacket", f"Apparel{SEP}Jackets"),
        (f"Apparel{SEP}APPAREL", f"Apparel{SEP}Clothing"),
        # Spelling and spacing fixes.
        (f"Accessories{SEP}cleaning-solutions", f"Accessories{SEP}cleaning solutions"),
        (f"Accessories{SEP}storage-containers", f"Accessories{SEP}storage"),
        (f"Flower{SEP}Smalls", f"Flower{SEP}small buds"),
        (f"Vaporizers{SEP}All-in-One", f"Vaporizers{SEP}all-in-one"),
        (f"Vaporizers{SEP}live-rosin", f"Vaporizers{SEP}live rosin"),
        (f"Vaporizers{SEP}Kit", f"Vaporizers{SEP}kits"),
        (f"Pre-Rolls{SEP}Pre-Roll Pack", f"Pre-Rolls{SEP}packs"),
        (f"Concentrate{SEP}Resin", f"Concentrate{SEP}live resin"),
        # Rows on the Accessories shelf are lowercase throughout.
        (f"Accessories{SEP}Chillum", f"Accessories{SEP}chillum"),
        (f"Accessories{SEP}Dab Straws", f"Accessories{SEP}dab straws"),
        (f"Concentrate{SEP}Ground Flower", f"Concentrate{SEP}ground flower"),
        (f"Topicals{SEP}Body Oil", f"Topicals{SEP}body oil"),
        (f"Dab Mats{SEP}Dabbing Mat", f"Gear{SEP}Dabbing Mat"),
        (f"Flower{SEP}Indoor Flower", f"Flower{SEP}indoor flower"),
        # Already canonical is left alone.
        (f"Flower{SEP}whole flower", f"Flower{SEP}whole flower"),
    ])
    def test_subcategory_label_is_corrected(self, raw, expected):
        assert canonical_category(raw) == expected

    def test_consolidation_targets_are_idempotent(self):
        for raw in ["45mm beakers", "Other Shit", "T-Shirts", "Accesory",
                    "Beverage", "Concentrates"]:
            once = canonical_category(raw)
            assert canonical_category(once) == once

    def test_merch_is_not_an_accessory(self):
        """Pins and patches are print runs, not smoking gear."""
        assert canonical_category("Patches") == "Clothing"
        assert canonical_category("Posters") == "Clothing"


class TestDabMats:
    """Dab mats are their own shelf, not a dab tool and not merch."""

    @pytest.mark.parametrize("raw,expected", [
        ("Dab Mats", "Gear"),
        ("dab mats", "Gear"),
        ("Dab Mat", "Gear"),
        ("mat", "Gear"),
        ("mats", "Gear"),
        ("Dab Pad", "Gear"),
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
        assert canonical_category("Merch") == "Clothing"
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
        assert canonical_category_named(category, name) == "Gear"

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
        assert canonical_category_named("Puffco", "Puffco Dab Mat") == "Gear"

    def test_canonical_category_signature_unchanged(self):
        # The rescue lives in a separate helper; canonical_category keeps its
        # single-argument contract and None passthrough.
        assert canonical_category("misc") == "Gear"
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
        # A title naming no known shelf must not invent one. Hats and Bags
        # carry curated subcategories now, but "cap" alone is not one of them.
        assert canonical_category_named("Hats", "Black Trucker Cap") == "Hats"
        assert canonical_category_named("Bags", "Woven Backpack") == f"Bags{SEP}Backpacks"
        assert canonical_category_named("Apparel", "Graphic Hoodie Blue") == f"Apparel{SEP}Hoodies"

    def test_no_match_leaves_main_alone(self):
        assert canonical_category_named("Vaporizers", "Arcata-TL") == "Vaporizers"

    def test_infer_subcategory_helper(self):
        assert infer_subcategory("Concentrate", "live rosin") == "live rosin"
        assert infer_subcategory("Accessories", "cool gadget") == ""
        # Apparel subcategories are curated, so a garment name is recognised.
        assert infer_subcategory("Apparel", "hoodie") == "Hoodies"
        assert infer_subcategory("Apparel", "plain onesie") == ""


class TestPhenotypeKeepsCannabis:
    """A product whose title states its I/S/H type is cannabis, always.

    The label is the store's own word for the product, so it beats both the
    shelf it was filed under and the brand it carries: a Puffco-branded
    cartridge called "Indica" is a filled vape, not a device, and stays in
    Cannabis. Without this, the hardware-brand rule would pull it onto Gear.
    """

    @pytest.mark.parametrize("name", [
        "Blue Dream [S]", "Blue Dream (S)", "Blue Dream - Sativa",
        "Blue Dream Sativa", "Blue Dream I/S", "Blue Dream I/S/H",
        "Blue Dream [I]", "Blue Dream (I)", "Blue Dream - Indica",
        "Blue Dream Indica", "Blue Dream [H]", "Blue Dream (H)",
        "Blue Dream - Hybrid", "Blue Dream Hybrid",
    ])
    def test_filled_vape_stays_in_cannabis(self, name):
        # "I/S" and "I/S/H" list all three types; the first matching pattern
        # wins, which is the same rule the dashboard's strainTypeFromName uses.
        # Either way the title states a phenotype, so the product is cannabis.
        assert canonical_category("Vaporizers", name=name) == "Vaporizers"
        assert canonical_category("Concentrate", name=name) == "Concentrate"

    @pytest.mark.parametrize("name", [
        "Puffco Peak Pro", "Puffco Proxy", "Focus V Rouge", "Puffco Peak",
    ])
    def test_hardware_with_no_phenotype_still_goes_to_gear(self, name):
        # The hardware-brand rule still applies when the title is silent: an
        # empty device is gear, not cannabis.
        assert canonical_category("Vaporizers", brand="Puffco", name=name) == "Gear"

    def test_phenotype_beats_hardware_brand(self):
        """A Puffco-branded cartridge labelled Indica is a filled vape."""
        assert canonical_category(
            "Vaporizers", brand="Puffco", name="Puffco Peak Pro [I]"
        ) == "Vaporizers"

    def test_silent_title_keeps_head_shop_hardware_on_gear(self):
        assert canonical_category(
            "Vaporizers", store_id="headshop", brand="Puffco", name="Peak Pro"
        ) == "Gear"

    def test_silent_title_keeps_dispensary_cannabis_in_cannabis(self):
        assert canonical_category(
            "Vaporizers", store_id="dispensary", name="Live Resin Cart"
        ) == "Vaporizers"

    def test_phenotype_does_not_move_non_vape_mains(self):
        # The name check only applies to Vaporizers/Concentrate; a Flower
        # product with a phenotype in its title stays Flower.
        assert canonical_category("Flower", name="Blue Dream Sativa") == "Flower"

    def test_strain_type_from_name_helper(self):
        from utils.categories import _strain_type_from_name
        assert _strain_type_from_name("Blue Dream [S]") == "sativa"
        assert _strain_type_from_name("Blue Dream (I)") == "indica"
        # "I/S/H" lists all three types; the first matching pattern wins, which
        # is the same rule the dashboard's strainTypeFromName uses.
        assert _strain_type_from_name("Blue Dream I/S/H") == "sativa"
        assert _strain_type_from_name("Blue Dream - Indica") == "indica"
        assert _strain_type_from_name("Blue Dream") == ""
        assert _strain_type_from_name("") == ""


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
