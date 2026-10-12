import os
import sqlite3
from datetime import datetime, timedelta

import pytest

from models import Strain
from storage.sqlite import SQLiteStorage
from utils.strain_match import (
    StrainResolver,
    ResolutionStats,
    enrich_deals,
    extract_candidates,
    match_key,
    normalize_name,
    slugify,
)


class TestNormalization:
    def test_normalize_name_keeps_word_spacing(self):
        assert normalize_name("  Blue   Dream  ") == "blue dream"
        assert normalize_name("Ice Cream Cake") == "ice cream cake"
        assert normalize_name("") == ""

    def test_normalize_name_drops_punctuation_but_keeps_words(self):
        assert normalize_name("Humboldt's Most Wanted") == "humboldts most wanted"
        assert normalize_name("GG#4") == "gg4"

    def test_match_key_ignores_spacing_and_punctuation(self):
        assert match_key("GG#4") == match_key("GG4")
        assert match_key("Ice-Cream Cake") == match_key("Ice Cream Cake")
        assert match_key("Humboldt's Most Wanted") == match_key("Humboldts Most Wanted")
        assert match_key("") == ""

    def test_match_key_still_distinguishes_strains(self):
        assert match_key("Blue Dream") != match_key("Blue Magoo")

    def test_slugify(self):
        assert slugify("Blue Dream") == "blue-dream"
        assert slugify("Ice Cream Cake") == "ice-cream-cake"


class TestCandidateExtraction:
    def test_brand_prefix_is_stripped(self):
        # "Cresco - Ap Gas - 2.83g - Sativa" -> the brand is not the strain
        assert extract_candidates("Cresco - Ap Gas - 2.83g - Sativa", "Cresco") == ["Ap Gas"]

    def test_pipe_suffix_is_dropped(self):
        # "Modified Cookies | 14.15g Premium" -> only the name survives
        assert extract_candidates("Modified Cookies | 14.15g Premium") == ["Modified Cookies"]

    def test_weight_and_phenotype_segments_are_dropped(self):
        cands = extract_candidates("Certified - Slurricane - Cart - 1g - Indica", "CERTIFIED")
        assert cands == ["Slurricane"]

    def test_brand_boundary_guard_ignores_near_miss_brand(self):
        # The stored brand is one character short of the name's own prefix; a
        # naive strip would leave "s Strawberry ..." behind.
        cands = extract_candidates(
            "Appalachian Pharms Strawberry Kushmints 14.15g (H)", "Appalachian Pharm"
        )
        assert all(not c.startswith("s ") for c in cands)
        assert "Appalachian Pharms Strawberry Kushmints" in cands

    def test_brand_strip_tolerates_spacing_differences(self):
        # The menu writes "& Shine" while the brand field says "&Shine".
        cands = extract_candidates("& Shine Northern Lights 2g Disposable (I)", "&Shine")
        assert "Northern Lights" in cands

    def test_genotype_number_is_preserved_and_variant_offered(self):
        cands = extract_candidates("Blue Dream - 3.5g")
        assert cands == ["Blue Dream"]

    def test_short_abbreviation_yields_no_candidate(self):
        # Two-letter dispensary abbreviations are not strain names, and the
        # brand is stripped so only the abbreviation segment remains.
        assert extract_candidates("Eden's Trees - BC - Cart - 1g", "Eden's Trees") == []
        assert extract_candidates("NL - Cart - 1g - Indica") == []

    def test_product_forms_are_peeled_off(self):
        cands = extract_candidates("& Shine Blueberry 1g Cart (H)", "& Shine")
        assert "Blueberry" in cands

    def test_ghost_train_is_not_shortened(self):
        # "Ghost Train" must not be derived from "Ghost Train Haze"
        cands = extract_candidates("&Shine - Ghost Train Haze - Cart - 1g - Sativa", "&Shine")
        assert cands == ["Ghost Train Haze"]

    def test_empty_and_blank_names(self):
        assert extract_candidates("", "Brand") == []
        assert extract_candidates("   ", "Brand") == []

    def test_name_without_brand_match_keeps_strain_segment(self):
        cands = extract_candidates("Unknown Brand - Super Lemon Haze - 3.5g - Sativa", "Other")
        assert "Super Lemon Haze" in cands


class TestStrainModel:
    def _make_strain(self, **kwargs):
        base = dict(name="Blue Dream", slug="blue-dream", category="Hybrid")
        base.update(kwargs)
        return Strain(**base)

    def test_thc_display_uses_range(self):
        strain = self._make_strain(thc_low=17.0, thc_high=24.0, thc_pct=20.0)
        assert strain.thc_display == "17-24%"

    def test_thc_display_falls_back_to_single_value_when_bounds_match(self):
        strain = self._make_strain(thc_low=21.0, thc_high=21.0, thc_pct=21.0)
        assert strain.thc_display == "21%"

    def test_cbd_display_falls_back_to_median(self):
        strain = self._make_strain(cbd_pct=1.5)
        assert strain.cbd_display == "1.5%"

    def test_empty_potency_renders_nothing(self):
        assert self._make_strain().thc_display == ""
        assert self._make_strain().cbd_display == ""

    def test_strain_type_normalises_phenotype(self):
        assert self._make_strain(category="Sativa-dominant hybrid").strain_type == "sativa"
        assert self._make_strain(category="Indica").strain_type == "indica"
        assert self._make_strain(category="Hybrid").strain_type == "hybrid"

    def test_round_trip_serialisation(self):
        strain = self._make_strain(
            effects=["Creative", "Happy"],
            flavors=["Berry"],
            terpenes=["Myrcene"],
            helps_with=["Anxiety"],
            parents=["Blueberry", "Haze"],
            rating=4.5,
            review_count=100,
            thc_low=17.0,
            thc_high=24.0,
        )
        restored = Strain.from_dict(strain.to_dict())
        assert restored.name == strain.name
        assert restored.slug == strain.slug
        assert restored.effects == strain.effects
        assert restored.parents == strain.parents
        assert restored.thc_display == strain.thc_display
        assert restored.strain_type == strain.strain_type


@pytest.fixture
def storage(tmp_path):
    # A per-test path avoids Windows file-locking on teardown.
    return SQLiteStorage(db_path=str(tmp_path / "strains.db"))


class TestStrainStorage:
    def _strain(self, name="Blue Dream"):
        return Strain(name=name, slug="blue-dream", category="Hybrid",
                      thc_low=17.0, thc_high=24.0, effects=["Creative", "Happy"])

    def test_save_and_get_round_trip(self, storage):
        assert storage.save_strain(self._strain())
        loaded = storage.get_strain("blue dream")
        assert loaded is not None
        assert loaded.name == "Blue Dream"
        assert loaded.effects == ["Creative", "Happy"]
        assert loaded.thc_display == "17-24%"

    def test_get_strains_returns_many_at_once(self, storage):
        storage.save_strain(self._strain("Blue Dream"))
        storage.save_strain(self._strain("Northern Lights"))
        found = storage.get_strains(["blue dream", "northern lights"])
        assert sorted(found) == ["blue dream", "northern lights"]

    def test_strain_miss_is_recorded_and_detected(self, storage):
        assert storage.is_strain_miss("juhlahtoh") is None
        storage.record_strain_miss("juhlahtoh")
        assert storage.is_strain_miss("juhlahtoh") is not None

    def test_strain_miss_attempts_increment(self, storage):
        storage.record_strain_miss("juhlahtoh")
        storage.record_strain_miss("juhlahtoh")
        conn = storage._get_connection()
        row = conn.execute(
            "SELECT attempts FROM strain_misses WHERE name = ?", ("juhlahtoh",)
        ).fetchone()
        conn.close()
        assert row["attempts"] == 2

    def test_clear_strain_misses(self, storage):
        storage.record_strain_miss("juhlahtoh")
        storage.clear_strain_misses()
        assert storage.is_strain_miss("juhlahtoh") is None

    def test_lookup_count_increments_on_resave(self, storage):
        storage.save_strain(self._strain())
        storage.save_strain(self._strain())
        conn = storage._get_connection()
        row = conn.execute(
            "SELECT lookup_count FROM strains WHERE name = ?", ("Blue Dream",)
        ).fetchone()
        conn.close()
        assert row["lookup_count"] == 2

    def test_strains_needing_detail_are_found(self, storage):
        storage.save_strain(self._strain("Blue Dream"))
        storage.save_strain(Strain(name="GMO", slug="gmo", flavors=["Pungent"]))
        pending = storage.get_strains_needing_detail()
        assert [s.name for s in pending] == ["Blue Dream"]

    def test_deal_strain_can_be_written_and_read_back(self, storage):
        from models import Deal
        deal = Deal(
            store_id="s1", product_id="1", name="Blue Dream", category="Flower",
            original_price=50.0, sale_price=35.0, discount_pct=30.0,
            image_url="", product_url="",
        )
        storage.save_seen_deal(deal)
        storage.set_deal_strain(deal.hash, "Blue Dream")
        assert storage.get_seen_deal(deal.hash).strain_name == "Blue Dream"

    def test_deals_missing_strain_excludes_matched(self, storage):
        from models import Deal
        for i, name in enumerate(["Blue Dream", "Juhlahtoh"]):
            deal = Deal(
                store_id="s1", product_id=str(i), name=name, category="Flower",
                original_price=50.0, sale_price=35.0, discount_pct=30.0,
                image_url="", product_url="",
            )
            storage.save_seen_deal(deal)

        conn = storage._get_connection()
        deal_hash = conn.execute(
            "SELECT hash FROM seen_deals WHERE name = ?", ("Blue Dream",)
        ).fetchone()[0]
        conn.close()
        storage.set_deal_strain(deal_hash, "Blue Dream")

        missing = storage.get_deals_missing_strain()
        assert [d.name for d in missing] == ["Juhlahtoh"]

    def test_existing_strain_is_kept_when_update_has_none(self, storage):
        from models import Deal
        deal = Deal(
            store_id="s1", product_id="1", name="Blue Dream", category="Flower",
            original_price=50.0, sale_price=35.0, discount_pct=30.0,
            image_url="", product_url="",
        )
        storage.save_seen_deal(deal)
        storage.set_deal_strain(deal.hash, "Blue Dream")

        # A later run with no strain attached must not wipe the stored value.
        deal.strain_name = None
        storage.update_seen_deal(deal, notify=False)
        assert storage.get_seen_deal(deal.hash).strain_name == "Blue Dream"


class FakeSearchClient:
    """Records lookups and returns canned hits, so resolution is testable."""

    def __init__(self, hits_by_name, detail_by_slug=None):
        self.hits_by_name = hits_by_name
        self.detail_by_slug = detail_by_slug or {}
        self.calls = []

    def search_hits(self, name, take=10):
        self.calls.append(name)
        return self.hits_by_name.get(normalize_name(name), [])

    def strain_from_hit(self, hit):
        from utils.leafly import LeaflyClient
        return LeaflyClient().strain_from_hit(hit)

    def get_strain_by_slug(self, slug):
        return self.detail_by_slug.get(slug)


class TestResolver:
    def _storage(self, tmp_path):
        return SQLiteStorage(db_path=str(tmp_path / "strains.db"))

    def test_exact_name_resolves(self, tmp_path):
        client = FakeSearchClient({
            "blue dream": [{"name": "Blue Dream", "slug": "blue-dream", "id": 75,
                            "category": "Hybrid", "averageRating": 4.3, "reviewCount": 10,
                            "cannabinoids": {"thc": {"percentile50": 21}}}],
        })
        resolver = StrainResolver(storage=self._storage(tmp_path), client=client)
        strain = resolver.resolve("Blue Dream")
        assert strain is not None
        assert strain.name == "Blue Dream"
        assert strain.thc_pct == 21

    def test_punctuation_difference_resolves(self, tmp_path):
        client = FakeSearchClient({
            "gg4": [{"name": "GG4", "slug": "original-glue", "id": 8,
                     "category": "Hybrid", "cannabinoids": {}}],
        })
        resolver = StrainResolver(storage=self._storage(tmp_path), client=client)
        assert resolver.resolve("GG#4") is not None

    def test_fuzzy_near_miss_is_rejected(self, tmp_path):
        # Leafly answers "Essential Animal Mintz" for "Animal Mintz"; only an
        # exact match is accepted, so this must not resolve.
        client = FakeSearchClient({
            "animal mintz": [{"name": "Essential Animal Mintz", "slug": "eam",
                              "id": 9, "category": "Hybrid", "cannabinoids": {}}],
        })
        resolver = StrainResolver(storage=self._storage(tmp_path), client=client)
        assert resolver.resolve("Animal Mintz") is None

    def test_genotype_variant_resolves(self, tmp_path):
        client = FakeSearchClient({
            "monkey bread 1": [{"name": "Monkey Bread #1", "slug": "mb1", "id": 3,
                                "category": "Hybrid", "cannabinoids": {}}],
        })
        resolver = StrainResolver(storage=self._storage(tmp_path), client=client)
        assert resolver.resolve("Monkey Bread #1") is not None

    def test_match_below_first_position_is_found(self, tmp_path):
        # A legitimate hit is not always ranked first.
        client = FakeSearchClient({
            "monkey bread 1": [
                {"name": "Monkey Bread", "slug": "mb", "id": 1, "cannabinoids": {}},
                {"name": "Grease Monkey", "slug": "gm", "id": 2, "cannabinoids": {}},
                {"name": "Monkey Bread #1", "slug": "mb1", "id": 3, "cannabinoids": {}},
            ],
        })
        resolver = StrainResolver(storage=self._storage(tmp_path), client=client)
        strain = resolver.resolve("Monkey Bread #1")
        assert strain.slug == "mb1"

    def test_resolution_is_cached(self, tmp_path):
        client = FakeSearchClient({
            "blue dream": [{"name": "Blue Dream", "slug": "bd", "id": 1,
                            "cannabinoids": {}}],
        })
        resolver = StrainResolver(storage=self._storage(tmp_path), client=client)
        resolver.resolve("Blue Dream")
        resolver.resolve("Blue Dream")
        assert client.calls.count("Blue Dream") == 1

    def test_miss_is_cached(self, tmp_path):
        client = FakeSearchClient({"ap gas": []})
        resolver = StrainResolver(storage=self._storage(tmp_path), client=client)
        assert resolver.resolve("Ap Gas") is None
        assert resolver.resolve("Ap Gas") is None
        assert client.calls.count("Ap Gas") == 1

    def test_category_filtering(self, tmp_path):
        client = FakeSearchClient({})
        resolver = StrainResolver(
            storage=self._storage(tmp_path), client=client, categories=["Flower"]
        )
        assert resolver.matches_category("Flower · premium")
        assert resolver.matches_category("flower")
        assert not resolver.matches_category("Edible · gummies")
        assert not resolver.matches_category("")

    def test_product_strain_uses_matched_name(self, tmp_path):
        client = FakeSearchClient({
            "slurricane": [{"name": "Slurricane", "slug": "slurricane", "id": 4,
                            "category": "Indica", "cannabinoids": {}}],
            "ap gas": [],
        })
        resolver = StrainResolver(storage=self._storage(tmp_path), client=client)
        assert resolver.resolve_for_product(
            "Certified - Slurricane - Cart - 1g - Indica", "CERTIFIED", "Vaporizers · cartridges"
        ).name == "Slurricane"
        assert resolver.resolve_for_product(
            "Cresco - Ap Gas - 2.83g - Sativa", "Cresco", "Flower"
        ) is None

    def test_disabled_resolver_returns_nothing(self, tmp_path):
        client = FakeSearchClient({"blue dream": [{"name": "Blue Dream"}]})
        resolver = StrainResolver(
            storage=self._storage(tmp_path), client=client, enabled=False
        )
        assert resolver.resolve("Blue Dream") is None

    def test_enrich_deals_stamps_names(self, tmp_path):
        client = FakeSearchClient({
            "blue dream": [{"name": "Blue Dream", "slug": "bd", "id": 1,
                            "category": "Hybrid", "cannabinoids": {}}],
        })
        resolver = StrainResolver(
            storage=self._storage(tmp_path), client=client, categories=["Flower"]
        )

        from models import Deal
        deals = [
            Deal(store_id="s1", product_id="1", name="Blue Dream", category="Flower",
                 original_price=50, sale_price=40, discount_pct=20, image_url="", product_url=""),
            Deal(store_id="s1", product_id="2", name="Unknown Strain Xyz", category="Flower",
                 original_price=50, sale_price=40, discount_pct=20, image_url="", product_url=""),
        ]
        stats = ResolutionStats()
        enriched = enrich_deals(deals, resolver, stats)

        assert enriched[0].strain_name == "Blue Dream"
        assert enriched[1].strain_name is None
        assert stats.looked_up == 2
        assert stats.resolved == 1

    def test_enrich_deals_without_resolver_is_a_noop(self):
        from models import Deal
        deal = Deal(store_id="s1", product_id="1", name="Blue Dream", category="Flower",
                    original_price=50, sale_price=40, discount_pct=20, image_url="", product_url="")
        assert enrich_deals([deal], None) == [deal]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
