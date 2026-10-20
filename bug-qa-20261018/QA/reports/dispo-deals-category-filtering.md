# Investigation — Category Auto-Filtering (dispo-deals)

Scope: sole focus on category auto-filtering — backend canonicalization
(`utils/categories.py`) and the dashboard filter contract
(`dashboard.html` filterProducts / sidebarMain).

## Baseline

- Ran `tests/test_categories.py test_magento.py test_sidebar.py test_strains.py
  test_dutchie.py` → **390 passed**.
- `py_compile utils/categories.py` → OK.

## Pipeline overview

### Backend (`utils/categories.py`)
- `canonical_category(category, store_id, brand, name)` — remaps store-specific
  shelf spellings to canonical mains via `CATEGORY_ALIASES`, then applies
  `MAIN_REMAP` (Glass/Puffco/Dab Mats/Kits/Misc → Gear; Skate/Merch → Clothing),
  then `_vape_remap` (Vaporizers/Concentrate → Gear for head shops/hardware
  brands; Cannabis POS stays in Cannabis).
- `canonical_category_named(...)` — adds title-based recovery: dab mats/mousepads
  on catch-alls → Gear; cap names → Gear; subcategory inference when none present.
- `exclude_terms` — applies **only** in `scrapers/magento.py` (`_is_excluded`),
  with word-boundary, case-insensitive matching; empty list disables filtering.
  `config.yaml` sets `exclude_terms: [candy, chew, sour, rotten]` for
  `zumiez-420`. Not applied by dutchie/shopify/klutch/etc., not applied at
  dashboard/API time (stale rows persist until `maintenance/clear_store.py` is run).

### Frontend (`dashboard.html`)
- `filterProducts(products)` (line 5247) — filters by store/category/brand/strain/deal/favorites/stock/search.
- Category branch: normalises both sides via `sidebarMain` + `normalizeCategorySub`,
  so a group selection ("Flower") matches every subcategory beneath it, and a
  subcategory selection ("Apparel · Hoodies") matches every merged spelling.
- `sidebarMain` unpacks "Gear · <sub>" back to its former shelf name so bare
  Gear rows filter correctly.

## Confirmed findings

### Finding 1 — Dead code in `_vape_remap` (utils/categories.py:1618-1627)
Lines 1618-1627 are unreachable: they duplicate the function body after
`return "Gear"` (line 1617). The final `if canonical == "Concentrate": return canonical`
can never execute because every path returns earlier.
- Severity: Low (harmless unreachable code, no runtime effect).
- Status: Not fixed — investigation only. Recommend removal.

### Finding 2 — Triplicated `_MOUSEPAD_NAME_RE` (utils/categories.py:1695-1712)
The same compiled regex (`\bmouse\s*-?\s*pads?\b`) is defined four times
with identical content; the last binding wins, so behavior is correct but the
first three bindings are dead duplication.
- Severity: Low (code smell, no runtime effect).
- Status: Not fixed — investigation only. Recommend dedup to one definition.

### Finding 3 — exclude_terms is scraper-scoped, not global
`_is_excluded` lives only in `scrapers/magento.py`. No other scraper (dutchie,
shopify, klutch, bigcartel, etc.) honors `store_config.exclude_terms`. And the
dashboard/API never re-filters, so products already in SQLite survive a later
`exclude_terms` change until `maintenance/clear_store.py` purges them.
- Severity: Medium (a store expecting global filtering gets scraper-dependent behavior).
- Status: Documented; not fixed — investigation only.

### Verified-clean: filter self-consistency
Mirrored `filterProducts`/`sidebarMain`/`normalizeCategorySub` in Python and
checked 32 canonical product categories the backend can produce → **0 filter
gaps**: selecting a product's own category, or its sidebar group key, always
re-includes the product. The backend→frontend category contract is sound.

## What was NOT found (no evidence)
- No category cross-merging bug (e.g. "Edible" never filters "Edibles" beyond
  the curated alias table; sidebar tests pin `Edible`→`Edible · gummies` only).
- No case-sensitivity leak in dashboard category matching (`categoryKey` strips
  case/punctuation on both sides).
- No `exclude_terms` word-boundary over-match beyond magento's documented behavior
  (`\b` prevents "Candyman" from matching "candy").

## Recommendation
Fix 1 and 2 (dead code) are trivial cleanups safe to apply. Finding 3 is a
behavior/design question for the owner (make exclude_terms global vs. keep
magento-scoped). None of these are runtime crashes.
