# dispo-deals — Project Overview

**The single source of truth for this project.** Everything that used to live in
`goal.md`, `roadmap.md`, `SPEC.md`, `README.md`, `TODO.md`,
`new-update.md`, `CHECKPOINT_DUTCHIE_CLOUDFLARE.md` and the 2026-10-12 QA
campaign has been folded in here. Those files are gone; edit this one.

Legend: `[x]` done · `[ ]` outstanding · `[~]` done with a caveat

---

## 1. The idea

A self-hosted **multi-store dispensary deals dashboard**: the dashboard of a CEO
who runs several dispensaries, except instead of tracking sales it tracks *which
products at which store are discounted right now*, across the whole portfolio,
from one screen.

The feel should be **professional, but also fun and modern**.

Three parts live in one codebase:

| Piece | What it does |
|-------|--------------|
| Scraper (`main.py`) | Fetches every store's menu on a schedule (default every 6h), persists deals and weekly snapshots to SQLite |
| Notifier (`notifier/`) | Sends rich Discord/Slack webhooks for new deals, weekly digests, per-product alerts |
| Dashboard (`dashboard.html` + `api_server.py`) | Cross-store catalogue with filtering, charts, store management |

## What the dashboard shows

**Every product from every source is shown, always.** Nothing is hidden for
being full price, and nothing is hidden for coming from a source that has no
discounts at all — the accessory and brand sites in §8.5 are catalogues with no
sale prices, and their products still belong on the grid alongside the
dispensaries.

A product that is on sale simply **carries a visible discount flag showing the
amount off** (for example `-20%`) on its card. That flag is the whole deal:

| Concept | What it means |
|---------|---------------|
| Product | Anything a source carries. All of it is listed. |
| Deal | A product with a discount. Flagged on the card with the amount off, and nothing more. |
| **Deals only** filter | Narrows the grid to the flagged ones — a view, not a change in what is stored. |
| Webhook alerts | Only genuinely new or deeper discounts notify, so full-price inventory never spams a channel. |

The distinction that matters: **the dashboard shows everything, the notifier
only speaks up about deals.** The default view is the full catalogue with
discounts flagged; `main.py:_process_deals` owns the notification side.

---

## 2. Dashboard structure (current)

- **Header row** — sidebar toggle, page title, search, Add Store, and the
  Store / Category / Brand / Type / Sort selects.
- **Filter row** — All Products ↔ Deals Only segmented control, Stock select,
  active-filter chips (each individually removable), Clear Filters.
- **Sidebar** — Stores, Categories (collapsible groups with subcategories) and
  Brands, each with live product counts.
- **Main** — stats bar (total products, on-deal count, stores with deals),
  Deal Insights charts (best categories / best brands), then the virtualised
  product grid (60-item batches, skeleton loading, IntersectionObserver).
- **Modals and panels** — Quick View per product (with image navigation), Compare
  panel (up to 4 products), Add Store.
- **URL state** — store, category, brand, type, deal, stock, sort and search all
  persist across reloads and are shareable.

---

## 3. Requirements — the notifier spec

From `goal.md` + `SPEC.md`.

### Deal detection
- [x] Scrape each source on a configurable schedule (default every 6 hours).
- [x] Extract name, price, discount %, category, image URL, product URL.
- [x] Deduplicate: only notify on a genuinely new deal.
- [x] Persist seen deals keyed on `store_id + product_id + sale_price + discount_pct`.
- [x] Re-notify only when a discount gets deeper than the previous best.
- [x] Per-store and per-product notification modes, configured per store.

### Rich webhook format
- [x] Per-store message: store logo thumbnail, list of new deals.
- [x] Per-product message: product image, deal details, link.
- [x] Store logo fetched once and cached in `store_logos`.
- [x] Product images cached in `product_images`, resized to the configured budget.

### Weekly menu tracking
- [x] Full menu snapshot per store every week.
- [x] Compare against the previous week, marking each item NEW or CARRYOVER.
- [x] Week 1 marks everything NEW (no prior baseline) and the digest is skipped
      until a previous menu exists to diff against.
- [x] Digest sent once per week per store on the configured day, with the week
      claimed in SQLite *before* sending so a crash or rerun cannot repeat it.

### Tracked sources
- [x] Culture Cannabis Club — Akron (Dutchie)
- [x] Supergood — Ravenna (Dutchie)
- [x] Bliss Ohio — Kent (Dutchie)
- [ ] Klutch Cannabis — **broken, see §7.5**
- [ ] High Intentions, Puffco, CannaStyle, MJ Arsenal, DeMatteo Art — **not built**

---

## 4. Architecture reference

```
dispo-deals/
├── config.yaml            # stores, schedule, webhook, leafly, images
├── main.py                # CLI entry point + scheduler
├── api_server.py          # dashboard API (ThreadingHTTPServer, port 4040)
├── dashboard.html         # the whole dashboard, inline CSS + JS
├── models.py              # Deal, Strain, WeeklySnapshot, SeenDeal, MenuItem, Diff
├── config.py              # typed config loading
├── scrapers/
│   ├── base.py            # BaseScraper (session, retries, headers)
│   ├── dutchie.py         # Dutchie GraphQL
│   ├── klutch.py          # Shopify-style HTML scraper
│   └── __init__.py        # create_scraper()
├── storage/sqlite.py      # SQLiteStorage (WAL mode)
├── notifier/webhook.py    # Discord/Slack payload builder
├── utils/
│   ├── brands.py          # canonical brand names
│   ├── categories.py      # canonical category names
│   ├── diff.py            # weekly menu comparison
│   ├── images.py          # download, cache, resize
│   ├── strain_match.py    # name → Leafly strain resolution
│   └── signal.py          # JWT/Atom feed helpers
└── tests/                 # 219 pytest tests
```

### Data models

```python
Deal      # store_id, product_id, name, category, original_price, sale_price,
          # discount_pct, max_discount_pct, image_url, product_url, in_stock,
          # thc_pct, cbd_pct, weight, brand, strain_name (excluded from hash)
          # hash = store_id + product_id + sale_price + discount_pct

Strain    # name, slug, leafly_id, category (Sativa/Indica/Hybrid),
          # thc_low/pct/high, cbd_low/pct/high, effects, flavors, terpenes,
          # helps_with, rating, review_count, description, image_url,
          # parents, children, source, fetched_at, lookup_count

WeeklySnapshot   # store_id, week_start (Monday), items: List[Deal]
SeenDeal         # hash, store_id, strain_name, first_seen, last_notified,
                 # notify_count, max_discount_pct
MenuItem         # deal + status (NEW / CARRYOVER)
```

### Database tables

`seen_deals` · `weekly_snapshots` · `weekly_summaries` (once-per-week digest
claims) · `known_stores` (stores added at runtime via Add Store) · `store_logos`
· `product_images` · `strains` · `strain_misses`

### Extensibility

A new store source = a `BaseScraper` subclass registered in
`scrapers/__init__.py:create_scraper()`:

```python
class BaseScraper(ABC):
    @abstractmethod
    def fetch_menu(self) -> List[Deal]: ...
    @abstractmethod
    def fetch_logo(self) -> Optional[bytes]: ...
```

plus a `config.yaml` entry. Stores added from the dashboard at runtime go to
`known_stores` and need no config edit.

### Error handling

- Scraper failures are logged and other stores continue; a store whose scrape
  fails is skipped for notifications that run.
- Webhook failures retry with exponential backoff (3 by default).
- Missing images: the local SVG placeholder is served rather than a broken box.
- Strain lookups are non-fatal — a product without a strain simply shows no badge.
- API errors are returned as JSON so the dashboard can show the real reason.

---

## 5. Operational reference

### Quick start (Docker)

```bash
cp .env.example .env        # add your Discord/Slack webhook URL
docker compose up -d
# open http://localhost:4040/dashboard.html
docker compose logs -f scraper
```

| Service | Port | Description |
|---------|------|-------------|
| `api` | 4040 | Dashboard + API |
| `scraper` | — | Background scheduler, runs every 6h |
| `flaresolverr` | 8191 | Cloudflare bypass |

### Local development (no Docker)

```bash
pip install -r requirements.txt
export WEBHOOK_URL="https://discord.com/api/webhooks/..."
python main.py --once --dry-run
python api_server.py
```

### Commands

```bash
python main.py --once                        # one scrape run
python main.py --import-strains              # backfill strains
python main.py --enrich-strains               # full strain profiles
python main.py --strain-status                # coverage report
python main.py --test-webhook                 # send a test payload
docker compose run --rm manual-scrape
```

### Dashboard API

| Route | Purpose |
|-------|---------|
| `GET /api/data` | Dashboard payload (deals, weekly diff) |
| `GET /api/menu` | Full menu from latest snapshots, plus stores/categories/brands |
| `POST /api/stores/add` | Resolve + scrape + persist a store by Dutchie URL |
| `DELETE /api/stores/<id>` | Remove a runtime-added store and its data |
| `GET /api/image/<url_hash>` | Product image via the local proxy |
| `GET /api/logo/<store_id>` | Store logo via the local proxy |

### Configuration (`config.yaml`)

Stores carry `id`, `name`, `url`, `scraper`, `logo_url`, `notification_mode`
(`per-store` / `per-product`), `enabled` and `webhook_enabled`. Leafly is limited
to the categories that can plausibly carry a strain — edibles, topicals and
tinctures are excluded because their names are flavours, not strains.

### Storage

- SQLite at `./data/dispo_deals.db` (mounted `/app/data`), WAL mode.
- Image cache in `./cache/images/` (mounted `/app/cache`).

### Dashboard features

- Full cross-shop browser: stores / categories / brands sidebar with live counts.
- Filters: store, category (group and subcategory), brand, strain type, deals
  only, stock status, free-text search, sort.
- Deal insights: two bar charts ranking categories and brands by most deals,
  best average discount, or deepest single discount, re-ranked over the active
  filters. Collapsible; scrolls away with the grid.
- Quick view modal, compare mode (up to 4 products), URL state persistence.
- Dark theme, glass panels over the tiled background, reduced-motion support.

### Dependencies

Chart.js is **vendored** in `vendor/chart.umd.min.js`, so charts draw on a
self-hosted network with no internet access. `requirements.txt` is otherwise the
only dependency source.

---

## 6. Done — QA campaign 2026-10-12

### Medium

- [x] **A1** No security headers → CSP, HSTS, `X-Content-Type-Options`,
      `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy` on every
      response; API errors returned as JSON.
- [x] **A2** Container ran as root → non-root `appuser` + `USER`.
- [~] **A3** CORS wildcard → left as-is; no credentials or cookies involved and
      the dashboard plus self-hosted consumers both need it.
- [x] **B1** No cache eviction → `LRUCache` with size limits for image and
      strain caches.
- [x] **B2** SQLite concurrency → WAL mode on every connection.
- [x] **C1** SIGTERM unhandled → graceful shutdown for SIGTERM/SIGINT.
- [x] **C2** NUL-byte `scripts/__init__.py` and `scripts/debug/__init__.py`
      → removed.
- [x] **C3** Duplicate resolve methods in `utils/strain_match.py` → deduplicated.
- [x] **D3** Path traversal on image/logo returned a placeholder → 404 now.

### Low

- [~] **E1** Non-semantic `role="button"` on a div → kept deliberately: the card
      contains a nested checkbox, invalid inside a `<button>`.
- [ ] **F1** Outdated dependencies (cloudscraper 1.2.71 has a Python-3.12 TLS
      issue) → blocked on a verified Cloudflare bypass.
- [x] **F3** `datetime.utcnow()` deprecated → `datetime.now(timezone.utc)`.
- [ ] **F4** `docs/schema.md` out of sync with the live database.
- [x] **H1** No `.dockerignore` → added.
- [ ] **I1** No CI/CD pipeline.
- [x] **I2** Dockerfile had no `HEALTHCHECK` → added against `/api/data`.

### The Dutchie/Cloudflare blocker — resolved

The checkpoint recorded scraping as fully broken: region-blocked
`filteredProducts`, no menu reachable, FlareSolverr only partially bypassing.

- [x] **Resolved.** The scraper resolves `filteredDispensaries` (exact
      `cNameOrID`) → `filteredProducts` (`dispensaryID` + `page`/`limit`), which
      is unblocked; DOM extraction kept as fallback. Verified live: Bliss Ohio —
      Kent resolved and scraped 999 products in 24s.

---

## 7. Done — filtering, stores, data and layout

- [x] Sidebar active-state bugs fixed — store, brand and category key off
      `data-*` attributes instead of fragile text/regex matching.
- [x] Sidebar ↔ header select sync in both directions.
- [x] Segmented All Products / Deals Only control.
- [x] Unified filter-select styling with custom caret and focus rings.
- [x] Active-filter chips with individual remove buttons.
- [x] **Add Store by Dutchie URL** — resolves, scrapes, saves logo and snapshot,
      persists to `known_stores` so it survives a restart. Re-adding refreshes
      rather than duplicating.
- [x] **Remove Store** with a hover button on runtime-added stores; configured
      stores refuse deletion because the next scrape would re-add them.
- [x] **Duplicate stores fixed** — `_canonical_store_id` resolves the id from
      whichever existing entry already points at that cName, so Dutchie's
      internal id cannot create a second row for the same dispensary.
- [x] Removing the active store's filter left a stale URL and an empty grid;
      fixed, and `dropFiltersForMissingStores` covers bookmarked dead links.
- [x] Deals-Only never survived a reload (`deal` vs `dealOnly` key mismatch).
- [x] **Brand canonicalisation** (`utils/brands.py`) — 138 → 134 distinct brands.
- [x] Header alignment fixed (`.header-actions` had no CSS rule at all).
- [x] Sidebar group collapse now triggers from anywhere on the group row.
- [x] Main content background is **glass over the tile**, not a solid fill.
- [x] Weekly menu digest with new/carryover markers, once per week per store.

---

## 8. Outstanding — the dashboard update

Ordered roughly by dependency. Full requirement wording is preserved so nothing
is lost again.

### 8.1 Filtering model — multiple filters at once

- [x] **Filters are independently combinable.** Choosing a store used to clear
      the category and brand, choosing a category cleared the brand, and any of
      them silently switched off Deals Only. Store + category + brand + type +
      deal + stock + search now all apply together, each removable on its own.

### 8.2 Strain type — filter and badges

- [x] **Hybrid/Sativa/Indica filter** in the sidebar (counts computed from the
      same detection the grid uses) and in the header select.
- [x] **Badges no longer intersect the compare checkbox.** The checkbox, the deal
      tag, the stock tag and the strain badge were all absolutely positioned at
      the same `top: 8px; right: 8px` corner, so every badge stacked underneath
      the checkbox. The tags now flow in a row that reserves the checkbox's
      width, and the phenotype badge has its own row beneath the image.
- [x] **Badges work with full names and the short forms** `[S]`, `[I]`, `[H]`,
      and with the parenthesised single-letter form (`(I)`), matched
      case-insensitively and on word boundaries.
- [x] **Falls back to the Leafly strain category** when the product name does not
      state a type. The name wins when it does, because it is the store's label
      for that exact product.
- [x] Filtering by type is strict — only products with a confirmed type are
      kept, so filtering to Sativa shows Sativas rather than everything that is
      not Indica or Hybrid.

Data available: `strains.category` holds `Sativa`/`Indica`/`Hybrid` (193 cached
strains); 651 of 2980 deals carry a `strain_name`.

### 8.3 Pre-roll categories

- [ ] Within **Pre-Rolls**, combine the **Infused** and **Infused Pre-Roll Pack**
      subcategories into a single **Infused** shelf.

### 8.4 New pages

- [ ] **Landing page** with three explicit entry points: browse per store, add a
      store, or browse all stores' products together.
- [ ] **"The Weekly Menu" page** — all newly added products for each store for
      the week, presented like a restaurant menu, **without** the bloat of
      prior weeks' items. Distinct from the weekly deals *digest* webhook and
      from the Weekly Deals ranking page.
- [ ] **Weekly Deals page** — the best deals per category across the entire
      catalogue.

### 8.5 Additional store sources

- [ ] **Klutch Cannabis** — `klutchcannabis.com` / `shopklutch.com`. Not a
      Dutchie store. **Currently produces zero real deals.**
  - All six `/collections/*` URLs return **404** on both
    `www.klutchcannabis.com` and `shopklutch.com`, so `fetch_menu` returns
    nothing and `seen_deals` has no `klutch` row at all.
  - `weekly_snapshots` holds two stale **placeholder** snapshots (4 items from
    2026-09-28, 10 from 2026-10-05) built from `example.com` product URLs and
    Unsplash stock images — fake data that must never be shown as real.
  - Needs the real shop URL structure discovered and the stale snapshots cleared.
- [ ] **High Intentions** — `https://www.highintentions.life/collection/?sort=popular`
  (local glass shop, not a Dutchie store).
- [ ] **Puffco** — `https://www.puffco.com/products/`
- [ ] **CannaStyle** — `https://shopcannastyle.com/`
- [ ] **MJ Arsenal** — `https://mjarsenal.com/`
- [ ] **DeMatteo Art** — `https://dematteoart.com/collections/all`

  These four are accessory and brand sites rather than dispensaries: product
  catalogues to browse, not deal feeds.

### 8.6 Look and feel

- [ ] Overall "CEO of several companies" framing — a portfolio view over several
      businesses, weighted toward deals rather than sales.
- [ ] Professional but fun and modern.
- [x] Keep the tiling background image — it is preserved behind the glass main
      panel, never replaced with a solid colour.

### 8.7 Future enhancements (carried from the old TODO)

- [ ] Keyboard shortcuts: arrow-key grid navigation, Escape to close the modal.
- [ ] Product image preloading/caching optimisation.
- [ ] Favourites / wishlist.
- [ ] Price history chart per product.
- [ ] Export/share from the compare panel.
- [ ] Mobile responsive refinement and device testing.
- [ ] **F1** Outdated dependencies (needs a verified Cloudflare bypass first).
- [ ] **F4** `docs/schema.md` sync.
- [ ] **I1** CI/CD pipeline.

---

## 9. Deferred / blocked

- [ ] **Location-based store discovery** — Dutchie's `filteredDispensaries`
      matches `cNameOrID` exactly, and its `city`/`state`/`zipCode`/`country`/
      `radius` filter fields exist in the schema but return **0 results for
      every value tried**, including values read back from a known dispensary's
      own `location { city state country }`. There is no coordinate filter at
      all, so "dispensaries within N miles" cannot be asked of this API.
      Shipped instead: Add Store by URL. To finish, Dutchie would have to expose
      location search, or the app would need a third-party dispensary directory
      plus a reverse geocoder.

---

## 10. Standing rules

- **Never push or commit unless explicitly asked.**
- Obvious bugs and failing logic may be fixed without asking, but the fix must
  be verified afterwards.
- Extend rather than rewrite; match surrounding style; reliability before
  cleverness; never fail silently.
- The tiling background image stays.
