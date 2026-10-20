"""The strain-name blacklist.

"Opal" is both a gem used in glass pendants and rigs and a hybrid on Leafly, so
without a blacklist a piece of glass is labelled a cannabis strain. The check
must sit ahead of the caches, because a record stored before the blacklist
existed would otherwise keep answering.
"""

from models import Strain
from utils.strain_match import (
    STRAIN_NAME_BLACKLIST,
    StrainResolver,
    match_key,
    normalize_name,
)


class FakeStorage:
    """Serves one stored record, as if it had been cached before any blacklist."""

    def __init__(self, stored=None):
        self.stored = stored or {}
        self.saved = []

    def get_strain(self, key):
        return self.stored.get(key)

    def is_strain_miss(self, key):
        return None

    def record_strain_miss(self, key):
        pass

    def save_strain(self, strain):
        self.saved.append(strain)


class FakeClient:
    """Answers every search with a single Opal hit, as Leafly does."""

    def __init__(self):
        self.calls = []

    def search_hits(self, name, take=10):
        self.calls.append(name)
        return [{"name": "Opal", "slug": "opal"}]

    def strain_from_hit(self, hit):
        return Strain(name=hit["name"], slug=hit["slug"], category="Hybrid")


def make_resolver(storage=None, client=None):
    return StrainResolver(
        storage=storage if storage is not None else FakeStorage(),
        client=client if client is not None else FakeClient(),
        enabled=True,
    )


class TestBlacklist:
    def test_opal_is_blacklisted(self):
        assert normalize_name("Opal") in STRAIN_NAME_BLACKLIST

    def test_opal_resolves_to_nothing(self):
        client = FakeClient()
        resolver = make_resolver(client=client)

        assert resolver.resolve("Opal") is None
        assert client.calls == [], "blacklisted word must not reach Leafly"

    def test_every_case_and_spelling_is_blocked(self):
        resolver = make_resolver()

        for spelling in ("Opal", "opal", "OPAL", " opal "):
            assert resolver.resolve(spelling) is None

    def test_a_stored_record_stays_inert(self):
        """The check runs before the cache, so stale data cannot leak through."""
        stored_strain = Strain(name="Opal", slug="opal", category="Hybrid")
        storage = FakeStorage(stored={normalize_name("Opal"): stored_strain})
        resolver = make_resolver(storage=storage)

        assert resolver.resolve("Opal") is None

    def test_other_strains_still_resolve(self):
        client = FakeClient()

        def hits(name, take=10):
            client.calls.append(name)
            if match_key(name) == "bluedream":
                return [{"name": "Blue Dream", "slug": "blue-dream"}]
            return []

        client.search_hits = hits
        resolver = make_resolver(client=client)

        assert resolver.resolve("Blue Dream") is not None
        assert client.calls[-1] == "Blue Dream"

    def test_a_blacklisted_candidate_does_not_stop_the_search(self):
        """Skipping "Opal" only drops that candidate, not the whole product."""
        client = FakeClient()

        def hits(name, take=10):
            client.calls.append(name)
            if match_key(name) == "bluedream":
                return [{"name": "Blue Dream", "slug": "blue-dream"}]
            return []

        client.search_hits = hits
        resolver = make_resolver(client=client)

        # A pendant rig whose title starts with the gem name still yields its
        # real strain.
        strain = resolver.resolve_for_product(
            "Opal Pendant Rig - Blue Dream", category="Glass"
        )

        assert strain is not None
        assert strain.name == "Blue Dream"
