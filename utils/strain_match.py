"""Matches dispensary products to Leafly strain records.

Two problems are solved here:

1. *Which part of a product name is the strain?* Dispensary menus are not
   consistent. The same strain appears as ``Cresco - Ap Gas - 2.83g - Sativa``,
   ``Modified Cookies | 14.15g Premium`` and ``&Shine - Distillate Cart -
   Blueberry Starkiller [I]``. The candidate extractor splits a product name
   into its segments and yields the plausible strain segments in order.

2. *Is a candidate genuinely a Leafly strain?* Leafly's search ranks the exact
   strain first whenever it exists, and only falls back to fuzzy near-misses
   ("Gas Apples" for "Ap Gas") when it does not. So resolution accepts a hit
   only when the normalised names are equal, scanning every hit in relevance
   order because a legitimate match is not always first ("Monkey Bread #1"
   arrives behind two other Monkey strains).

The bias is deliberately toward precision: a missing strain badge costs nothing,
while a wrong one would show someone the wrong effects and potency.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

from models import Strain
from utils.categories import canonical_category, main_category
from utils.leafly import LeaflyClient

logger = logging.getLogger(__name__)

# Segments of a product name that describe the product rather than the plant.
# These are matched case-insensitively against the whole segment.
NOISE_WORDS = {
    # dose / size
    "select", "premium", "small", "smalls", "small-buds", "bulk", "pre-ground",
    "shake", "trim", "shake-trim", "popcorn", "minis", "miniz",
    # product forms
    "cart", "cartridge", "pod", "pods", "disposable", "disposables",
    "vape", "vapes", "pen", "pens", "all-in-one", "aio",
    "pre-roll", "preroll", "prerolls", "pre-rolls", "roll", "joint", "blunt",
    "single", "singles", "pack", "packs", "multi-pack", "infused",
    "concentrate", "extract", "distillate", "live-resin", "live-rosin",
    "rosin", "sauce", "wax", "shatter", "crumble", "badder", "budder",
    "sugar", "diamonds", "rso", "hash", "kief", "tincture", "spray",
    "gummies", "gummy", "gummie", "chocolate", "chocolates", "bar", "bars",
    "capsules", "capsule", "tablets", "tablet", "mints", "drink", "drinks",
    "beverage", "edible", "edibles", "sublingual",
    # application / misc
    "topical", "topicals", "balm", "balms", "lotion", "salve", "patch",
    "suppository", "applicators", "applicator", "flower", "whole-flower",
    "high-dose", "higher-dose", "high-dose-thc", "1:1", "ratio",
}

# A candidate that must never be treated as a strain, even when Leafly has a
# record for the word. These are materials and gem names that appear in glass
# and hardware product titles: "Opal" is a gem used in pendants and rigs, and
# Leafly also lists a hybrid called Opal, so without this the badge would claim
# a piece of glass is a cannabis strain. Compared against the normalised name.
STRAIN_NAME_BLACKLIST = {
    "opal",
}

PHENOTYPE_RE = re.compile(
    r"^(sativa|indica|hybrid|sativa-dominant|indica-dominant|"
    r"sativa\s*dominant|indica\s*dominant|cbd|thc|balanced)[\s\-]*(dominant)?$",
    re.IGNORECASE,
)
# A segment that is only a measurement, e.g. "3.5g", "100mg", "10pk", "1g".
MEASUREMENT_RE = re.compile(
    r"^\(?[\d.,]+\s*(g|gram|grams|mg|ml|oz|ounce|pk|pack|pc|pcs|ct|count)\)?$",
    re.IGNORECASE,
)
# A segment that carries no letters at all, e.g. "10", "2 x 1g".
DIGITS_ONLY_RE = re.compile(r"^[\d\s.x/]+$")
PARENTHETICAL_RE = re.compile(r"\s*\([^)]*\)")
BRACKETED_RE = re.compile(r"\s*\[[^\]]*\]")
TRAILING_NOISE_RE = re.compile(r"[\s\-–—:;,|]+$")
LEADING_NOISE_RE = re.compile(r"^[\s\-–—:;,|]+")
PHENOTYPE_SUFFIX_RE = re.compile(r"\s*#\s*\d+$")
# Dose ratios leak into strain segments on edible products, e.g. "1:1", "4:1".
LEADING_RATIO_RE = re.compile(r"^\d+(?::\d+)+\s*")
TRAILING_RATIO_RE = re.compile(r"\s*\d+(?::\d+)+\s*(thc|cbd|cbn|cbg|cbc)?\s*$", re.IGNORECASE)
# A trailing "THC:CBN"-style label, which appears after the flavour name.
TRAILING_CANNABINOID_LABEL_RE = re.compile(
    r"\s*(?:thc|cbd|cbn|cbg|cbc)(?::(?:thc|cbd|cbn|cbg|cbc))+\s*$",
    re.IGNORECASE,
)
# Some menus paste a literal "HYPHEN" where a separator belonged, either side
# of the surrounding words.
HYPHEN_TOKEN_RE = re.compile(r"\s+HYPHEN\b", re.IGNORECASE)
LEADING_HYPHEN_TOKEN_RE = re.compile(r"^\s*HYPHEN\b", re.IGNORECASE)

WORD_SPLIT_RE = re.compile(r"[^a-z0-9]+")
NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
# Punctuation is dropped (not turned into a space) when normalising names, so
# that "GG#4" and "GG4" compare equal.
NON_ALNUM_OR_SPACE_RE = re.compile(r"[^a-z0-9\s]")


def normalize_name(name: str) -> str:
    """Canonical form for comparing a candidate against a Leafly name.

    Punctuation is *removed* rather than replaced, so that ``GG#4`` and ``GG4``
    compare equal and ``Humboldt's Most Wanted`` matches ``Humboldts Most
    Wanted``. Spaces are preserved, because they separate the words of a
    multi-word strain name.
    """
    if not name:
        return ""
    lowered = name.lower()
    squeezed = NON_ALNUM_OR_SPACE_RE.sub("", lowered)
    return re.sub(r"\s+", " ", squeezed).strip()


def slugify(name: str) -> str:
    if not name:
        return ""
    return NON_ALNUM_RE.sub("-", name.lower()).strip("-")


def match_key(name: str) -> str:
    """Aggressive comparison key: letters, digits and nothing else.

    Used only to decide whether a candidate and a Leafly name are the *same*
    strain. Stripping spaces as well as punctuation means "GG#4" matches "GG4",
    "Ice-Cream Cake" matches "Ice Cream Cake", and "Humboldt's Most Wanted"
    matches "Humboldts Most Wanted" - all of which dispensary menus produce.

    It is deliberately separate from ``normalize_name``, which keeps spaces and
    therefore stays usable as a stable, human-recognisable cache key.
    """
    squeezed = NON_ALNUM_RE.sub("", (name or "").lower())
    return squeezed.strip()


def _clean_segment(segment: str) -> str:
    """Strip packaging annotations that Leafly would never carry in a name."""
    cleaned = BRACKETED_RE.sub("", segment)
    cleaned = PARENTHETICAL_RE.sub("", cleaned)
    cleaned = HYPHEN_TOKEN_RE.sub("", cleaned)
    cleaned = LEADING_HYPHEN_TOKEN_RE.sub("", cleaned)
    cleaned = LEADING_RATIO_RE.sub("", cleaned)
    cleaned = TRAILING_RATIO_RE.sub("", cleaned)
    cleaned = TRAILING_CANNABINOID_LABEL_RE.sub("", cleaned)
    cleaned = TRAILING_NOISE_RE.sub("", cleaned)
    cleaned = LEADING_NOISE_RE.sub("", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _is_noise(segment: str) -> bool:
    """True when a segment describes the product instead of the strain."""
    compact = segment.strip().lower()
    if not compact:
        return True

    # Multi-word phrases are matched whole first: "Pre-Roll" and "All-in-One"
    # are in the noise list but split into words they are not, and checking
    # the words alone would let them through as strain candidates.
    if compact in NOISE_WORDS:
        return True

    # A bare weight or a phenotype label such as "3.5g", "100mg", "Sativa".
    if MEASUREMENT_RE.match(compact) or DIGITS_ONLY_RE.match(compact):
        return True
    if PHENOTYPE_RE.match(compact):
        return True

    # Word-by-word: "Cart 1g" and "Pre-Roll 5pk" should both count as noise.
    words = [w for w in WORD_SPLIT_RE.split(compact) if w]
    if not words:
        return True
    if all(w in NOISE_WORDS for w in words):
        return True

    # A short segment that is mostly a dose, e.g. "100mg 10pk".
    if len(words) <= 2 and any(MEASUREMENT_RE.match(w) for w in words):
        return True
    return False


def _strip_brand(name: str, brand: Optional[str]) -> str:
    """Remove a leading brand label from a product name.

    Two guards matter here:

    * The boundary check stops a brand that is one character shorter than the
      text it matches ("Appalachian Pharm" vs "Appalachian Pharms Strawberry")
      from leaving a mangled "s Strawberry" behind, so a strip only applies when
      the brand is followed by a separator or whitespace.
    * The comparison ignores spacing and punctuation, because the same menu
      spells the brand "&Shine" and its products "& Shine Northern Lights".
      Without that, the brand survives into the candidate and the strain is
      never found.
    """
    if not brand:
        return name

    brand_clean = brand.strip()
    if not brand_clean:
        return name

    working = name.strip()
    if not working:
        return working

    if working.lower().startswith(brand_clean.lower()):
        remainder = working[len(brand_clean):]
        if not remainder or not remainder[0].isalnum():
            return remainder
        return working

    # Fall back to matching on alphanumerics only, and consume the raw prefix
    # that the brand actually occupies.
    target = re.sub(r"[^a-z0-9]", "", brand_clean.lower())
    if not target:
        return working

    consumed = 0
    cut = -1
    for index, char in enumerate(working.lower()):
        if consumed == len(target):
            cut = index
            break
        if char.isalnum():
            if char != target[consumed]:
                return working
            consumed += 1
    else:
        # The name ran out. If the brand was fully consumed this is an exact
        # match with nothing left over; otherwise the brand does not match.
        if consumed != len(target):
            return working
        cut = len(working)

    if cut < 0:
        cut = len(working)

    remainder = working[cut:]
    if not remainder or not remainder[0].isalnum():
        return remainder
    return working


def extract_candidates(name: str, brand: Optional[str] = None) -> List[str]:
    """Return plausible strain names from a product name, best guess first.

    Every dispensary in this project names products differently, so the whole
    name is split and each non-packaging segment is offered as a candidate.
    Resolution then verifies each one against Leafly, and the order only
    decides which is tried first when several segments look like strains.
    """
    if not name or not name.strip():
        return []

    working = _strip_brand(name, brand)
    working = working.split("|", 1)[0]
    if not working.strip():
        return []

    candidates: List[str] = []
    seen = set()

    def offer(value: str):
        cleaned = _clean_segment(value)
        if not cleaned or _is_noise(cleaned):
            return

        variants = [cleaned]
        # A genotype marker is part of the name ("Monkey Bread #1"), but a
        # trailing "#4" on an unknown name is usually a batch number, so both
        # the full and the stripped form are tried.
        stripped = PHENOTYPE_SUFFIX_RE.sub("", cleaned).strip()
        if stripped and stripped.lower() != cleaned.lower():
            variants.append(stripped)

        # A trailing product form ("Cart", "Pod") is packaging, not part of the
        # plant name, so peel recognised forms and doses off the end one at a
        # time. Only known form words and bare measurements are removed, which
        # keeps "Ghost Train" from being derived from "Ghost Train Haze" while
        # still recovering "Blueberry" from "Blueberry 1g Cart".
        peek = stripped if stripped else cleaned
        while True:
            words = peek.rsplit(None, 1)
            if len(words) < 2:
                break
            head, tail = words
            if tail.lower() not in NOISE_WORDS and not MEASUREMENT_RE.match(tail):
                break
            head = _clean_segment(head)
            if head:
                variants.append(head)
            peek = head

        for variant in variants:
            normalized = normalize_name(variant)
            # A single letter is never a strain name, and matches nothing but
            # produces a wasted API call.
            if len(normalized) < 3 or normalized in seen:
                continue
            seen.add(normalized)
            candidates.append(variant)

    for segment in re.split(r"\s+[-–—]\s+|/|\+", working):
        offer(segment)

    return candidates


@dataclass
class ResolutionStats:
    looked_up: int = 0
    resolved: int = 0
    from_cache: int = 0
    from_leafly: int = 0
    api_calls: int = 0
    failed: int = 0
    samples: List[tuple] = field(default_factory=list)

    def record(self, name: str, resolved: bool):
        self.looked_up += 1
        if resolved:
            self.resolved += 1
        elif len(self.samples) < 25:
            self.samples.append((name, resolved))

    def as_dict(self) -> dict:
        return {
            "looked_up": self.looked_up,
            "resolved": self.resolved,
            "resolved_pct": round(self.resolved / self.looked_up * 100, 1)
            if self.looked_up else 0.0,
            "from_cache": self.from_cache,
            "from_leafly": self.from_leafly,
            "api_calls": self.api_calls,
            "failed": self.failed,
        }


class StrainResolver:
    """Resolves product strain names against Leafly and caches the results.

    Two caches exist and both live in SQLite:

    * ``strains`` - names that matched, with their full profile.
    * ``strain_misses`` - names that did not match, so the ~majority of products
      that carry no Leafly strain are only ever queried once instead of on
      every six-hourly run.
    """

    def __init__(
        self,
        storage,
        client: Optional[LeaflyClient] = None,
        enabled: bool = True,
        categories: Optional[Sequence[str]] = None,
        match_threshold: float = 0.6,
        cache_days: int = 30,
    ):
        self.storage = storage
        self.client = client or LeaflyClient()
        self.enabled = enabled
        self.categories = set(categories or [])
        self.cache_days = cache_days
        self._memory_cache: Dict[str, Optional[Strain]] = {}

    # ---- public API ----

    def matches_category(self, category: str) -> bool:
        """True when a category can plausibly carry a strain."""
        if not self.categories:
            return True
        # Compared against the canonical name so a store calling the same shelf
        # "Concentrates" is not silently excluded.
        top = main_category(canonical_category(category))
        if not top:
            return False
        return any(
            top.lower() == allowed.lower()
            or top.lower().startswith(allowed.lower())
            for allowed in self.categories
        )

    def resolve_for_product(
        self,
        name: str,
        brand: Optional[str] = None,
        category: str = "",
        stats: Optional[ResolutionStats] = None,
    ) -> Optional[Strain]:
        """Resolve the strain for a single product, or None."""
        if not self.enabled or not name:
            return None

        if not self.matches_category(category):
            return None

        for candidate in extract_candidates(name, brand):
            strain = self.resolve(candidate, stats)
            if strain:
                return strain
        return None

    def resolve(self, candidate: str, stats: Optional[ResolutionStats] = None) -> Optional[Strain]:
        """Resolve one candidate name against the caches, then Leafly."""
        if not self.enabled:
            return None

        key = normalize_name(candidate)
        if not key:
            return None

        # Checked before the caches so an already-stored record for a blacklisted
        # word stays inert, and before Leafly so it is never queried for it.
        if key in STRAIN_NAME_BLACKLIST:
            logger.debug("Skipping blacklisted strain candidate %r", candidate)
            return None

        if key in self._memory_cache:
            return self._memory_cache[key]

        cached = self.storage.get_strain(key)
        if cached is not None and not self._is_stale(cached):
            self._memory_cache[key] = cached
            if stats:
                stats.from_cache += 1
            return cached

        missed = self.storage.is_strain_miss(key)
        if missed and not self._is_miss_stale(missed):
            self._memory_cache[key] = None
            return None

        strain = self._resolve_from_leafly(candidate, stats)
        if strain:
            self._memory_cache[key] = strain
            return strain

        self.storage.record_strain_miss(key)
        self._memory_cache[key] = None
        return None

    def _resolve_from_leafly(
        self, candidate: str, stats: Optional[ResolutionStats] = None
    ) -> Optional[Strain]:
        if stats:
            stats.api_calls += 1
        hits = self.client.search_hits(candidate, take=10)
        if not hits:
            logger.debug("No Leafly hits for strain candidate %r", candidate)
            return None

        target = match_key(candidate)
        for hit in hits:
            hit_name = (hit.get("name") or "").strip()
            if not hit_name or match_key(hit_name) != target:
                continue

            strain = self.client.strain_from_hit(hit)
            if strain:
                self.storage.save_strain(strain)
                if stats:
                    stats.from_leafly += 1
                logger.debug("Matched strain %r -> %r", candidate, strain.name)
                return strain

        logger.debug(
            "No exact Leafly strain for candidate %r (closest was %r)",
            candidate,
            hits[0].get("name"),
        )
        return None

    # ---- cache freshness ----

    @staticmethod
    def _as_utc(value):
        """Return a UTC-aware datetime for a value read from the database.

        `fetched_at` is stored as an ISO string, so it may arrive as either a
        datetime already parsed by `Strain.from_dict` or the raw string. It may
        also be naive: rows written before timestamps were stored UTC-aware
        carry a naive value, and subtracting a naive one from an aware one
        raises. Reading a naive value as UTC is what the writer meant, since
        every value the app writes is UTC.
        """
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value)
            except ValueError:
                return None
        if not isinstance(value, datetime):
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    def _is_stale(self, strain: Strain) -> bool:
        if not strain.fetched_at:
            return True
        fetched_at = self._as_utc(strain.fetched_at)
        if fetched_at is None:
            return True
        age = datetime.now(timezone.utc) - fetched_at
        return age > timedelta(days=self.cache_days)

    def _is_miss_stale(self, attempted_at: Optional[str]) -> bool:
        if not attempted_at:
            return True
        attempted = self._as_utc(attempted_at)
        if attempted is None:
            return True
        return (
            datetime.now(timezone.utc) - attempted
            > timedelta(days=self.cache_days)
        )


def enrich_deals(
    deals: Iterable[Any],
    resolver: Optional[StrainResolver],
    stats: Optional[ResolutionStats] = None,
) -> List[Any]:
    """Attach matched strain names to deals in place, returning them."""
    if resolver is None:
        return list(deals)

    enriched = []
    for deal in deals:
        try:
            strain = resolver.resolve_for_product(
                deal.name,
                brand=getattr(deal, "brand", None),
                category=deal.category,
                stats=stats,
            )
        except Exception as e:  # a bad product name must not abort the run
            logger.warning("Strain resolution failed for %r: %s", deal.name, e)
            if stats:
                stats.failed += 1
            enriched.append(deal)
            continue

        if strain:
            deal.strain_name = strain.name
        if stats:
            stats.record(deal.name, strain is not None)
        enriched.append(deal)

    return enriched
