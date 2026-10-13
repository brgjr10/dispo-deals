"""Canonical brand names.

Brands are typed once per store, so the same brand reaches the dashboard with a
different spelling depending on who entered it: ``Wellspring Fields`` at one
dispensary and ``Wellsprings Field`` at another, ``FireBrand`` and
``Firebrand`` for the same producer, ``Tom & Berry`` with a stray trailing
space. Left alone each variant becomes its own sidebar row, so filtering by
brand misses half of that brand's products and the counts are wrong.

Two rules fix it:

1. The comparison key ignores case, spacing and punctuation, so ``Tom & Berry``
   and ``Tom &Berry`` fold together. The spelling that occurs most often in the
   catalogue wins, because that is what the stores actually type, and the
   displayed name is that real spelling rather than an invented one.
2. An explicit alias list handles the typos folding cannot, where the two
   spellings are genuinely different words rather than formatting.
"""

import re
from collections import Counter

# Corrections for brand spellings that differ by more than case or spacing.
# Keys are comparison keys (see brand_key), so they are already case and
# punctuation insensitive.
BRAND_ALIASES = {
    # The proper name is "Wellspring Fields"; one store types "Wellsprings
    # Field", which reads as a different brand but is the same producer.
    "wellspringsfield": "Wellspring Fields",
    "wellspringfields": "Wellspring Fields",
}

_KEY_RE = re.compile(r"[^a-z0-9]+")


def brand_key(name: str) -> str:
    """Comparison key for a brand name, ignoring spacing and punctuation."""
    return _KEY_RE.sub("", (name or "").lower())


def clean_brand(name: str) -> str:
    """Trim and collapse internal whitespace, leaving the spelling alone.

    Only whitespace is touched: the ampersand spacing is part of how a brand is
    actually written, and rewriting it would invent a spelling no store uses.
    Matching across such variants is what :func:`brand_key` is for.
    """
    if not name or not name.strip():
        return ""
    return re.sub(r"\s+", " ", name).strip()


def resolve_brand_variants(names) -> dict:
    """Map every comparison key in ``names`` to the display name to use.

    The spelling with the highest count wins, since that is what most of the
    catalogue uses. Ties are broken by preferring the most capitalised spelling
    (so a stray all-caps entry does not win on frequency alone), then
    alphabetically, so the result does not depend on input order.
    """
    tally_by_key = {}

    for raw in names:
        cleaned = clean_brand(raw)
        if not cleaned:
            continue
        tally_by_key.setdefault(brand_key(raw), Counter())[cleaned] += 1

    winners = {}
    for key, tally in tally_by_key.items():
        alias = BRAND_ALIASES.get(key)
        if alias:
            winners[key] = alias
            continue
        winners[key] = sorted(
            tally.items(),
            key=lambda kv: (-kv[1], -sum(1 for ch in kv[0] if ch.isupper()), kv[0]),
        )[0][0]
    return winners


def make_brand_canonicalizer(names):
    """Build a one-argument canonicaliser covering every brand in ``names``.

    A single pass over the catalogue produces the spelling map once, rather
    than re-deciding it per product.
    """
    winners = resolve_brand_variants(names)

    def canonical_brand(name: str) -> str:
        if not name or not name.strip():
            return name or ""
        return winners.get(brand_key(name), clean_brand(name))

    return canonical_brand
