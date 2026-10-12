# Dispo Deals

Automated dispensary deal tracker with HTML dashboard and webhook alerts. Runs as a Docker Compose stack with FlareSolverr for Cloudflare bypass.

## Architecture

| Component | Purpose |
|-----------|---------|
| **Scraper** (`main.py`) | Runs on schedule (cron), scrapes all stores, saves to SQLite |
| **Dashboard API** (`api_server.py`) | Serves dashboard HTML + `/api/data` endpoint |
| **FlareSolverr** | Bypasses Cloudflare for Dutchie GraphQL/HTML |
| **Webhook Alert** | Only **Culture Cannabis Club** — sends Discord/Slack notifications |

## Quick Start (Docker)

```bash
# 1. Configure webhook
cp .env.example .env
# Edit .env and add your Discord/Slack webhook URL

# 2. Start the stack
docker compose up -d

# 3. Open dashboard
# http://localhost:4040/dashboard.html

# 4. View logs
docker compose logs -f scraper
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| `api` | 4040 | Dashboard + API |
| `scraper` | — | Background scheduler (runs every 6hrs) |
| `flaresolverr` | 8191 | Cloudflare bypass for Dutchie |

## Manual Commands

```bash
# Run scraper once (outside scheduler)
docker compose run --rm manual-scrape

# Run scraper once in existing container
docker compose exec scraper python main.py --once

# View dashboard logs
docker compose logs -f api

# Test webhook
docker compose exec scraper python main.py --test-webhook
```

## Local Development (No Docker)

```bash
pip install -r requirements.txt
export WEBHOOK_URL="https://discord.com/api/webhooks/..."
python main.py --once --dry-run
python api_server.py
# Open http://localhost:4040/dashboard.html
```

## Dashboard Features

- **By Store** tab: All deals grouped by store, filterable
- **Best per Category** tab: Top deal in each category across all stores
- **Weekly Diff** tab: NEW / CARRYOVER / REMOVED vs last week
- Search, filter by store/category/status
- Dark theme, translucent panels, tiling background, responsive

## Webhook Alerts

Only **Culture Cannabis Club** triggers webhooks (`webhook_enabled: true` in config.yaml). Other stores are scraped for the dashboard only.

## Supported Stores

| Store | Scraper | Dashboard | Webhook |
|-------|---------|-----------|---------|
| Culture Cannabis Club (Dutchie) | GraphQL + Apollo cache | ✅ | ✅ |
| Supergood — Ravenna (Dutchie) | GraphQL + Apollo cache | ✅ | ❌ |
| Bliss Ohio — Kent (Dutchie) | GraphQL + Apollo cache | ✅ | ❌ |
| Klutch Cannabis | HTML | ✅ | ❌ |

## Configuration

Edit `config.yaml`:

```yaml
webhook_url: ""  # Or set WEBHOOK_URL env var
schedule_cron: "0 */6 * * *"

stores:
  - id: culture-akron
    webhook_enabled: true   # Only this one sends webhooks
    ...
  - id: supergood-ravenna
    webhook_enabled: false  # Dashboard only
    ...
```

## Data Storage

- SQLite at `./data/dispo_deals.db` (mounted as `/app/data`)
- Tables: `seen_deals`, `weekly_snapshots`, `store_logos`, `product_images`, `strains`, `strain_misses`
- Image cache in `./cache/images/` (mounted as `/app/cache`)

## Products vs Deals

Every product a store carries is captured, not only the discounted ones. The
dashboard browses the full menu, and a "Deals only" toggle narrows it to
products with a `discount_pct > 0`.

Webhook alerts are deliberately limited to real deals, so a store that lists
mostly full-price stock (Culture Akron carries ~380 of them against ~20 sales)
still loads a full catalogue without spamming a channel. The split lives in
`main.py:_process_deals`.

This is also why store counts differ so much in the dashboard: Bliss Ohio has
94% of its menu on sale, while Culture Akron runs one blanket 20% promotion
across a small slice of its menu.

## Leafly Strain Data

Each product's strain is resolved against Leafly when a scrape runs, so the
dashboard can show the strain's phenotype, typical potency, effects and flavours
instead of just the dispensary's name for it.

```yaml
leafly:
  enabled: true
  # Categories that can plausibly carry a strain. Edibles, topicals and
  # tinctures are excluded because their names are flavours, not strains.
  categories: [Flower, Pre-Rolls, Concentrate, Vaporizers]
  request_delay_seconds: 0.4
  cache_days: 30
```

Commands:

```bash
# Backfill strains for products already in the database
python main.py --import-strains

# Fetch full profiles (flavours, description, genetics) for cached strains
python main.py --enrich-strains

# Report coverage
python main.py --strain-status

# Force every candidate to be re-tried against Leafly
python main.py --import-strains   # after clearing the miss cache
```

**How matching works.** Leafly has no public self-serve strain API. The importer
uses the search endpoint the Leafly site itself calls, which resolves a name to
Leafly's canonical strain record and carries phenotype, cannabinoid percentiles,
effects, terpenes and rating. Strain pages are then read for the fields that
endpoint omits, mainly flavours and the full description.

Leafly ranks an exact strain first whenever it exists and only falls back to
fuzzy near-misses ("Gas Apples" for "Ap Gas") when it does not, so a hit is
accepted only when its name matches the candidate exactly. The bias is towards
precision: a missing strain badge costs nothing, while a wrong one would show
someone the wrong effects and potency.

Two caches keep this cheap. `strains` holds matched profiles; `strain_misses`
holds candidates that produced nothing, so the many products whose names are
proprietary cuttings Leafly does not carry are only queried once.

## Adding a Store

1. Add scraper in `scrapers/` implementing `BaseScraper`
2. Register in `scrapers/__init__.py` `create_scraper()`
3. Add to `config.yaml` with `enabled: true` and `webhook_enabled: false` (or true for alerts)

## Testing

```bash
pytest tests/
```

## Production Notes

- FlareSolverr handles Cloudflare challenges for Dutchie
- The Dutchie scraper falls back to Apollo cache extraction if GraphQL fails
- Scheduler runs at 06:00, 12:00, 18:00, 00:00 (configurable via `schedule_cron`)
- Webhook retries with exponential backoff (3 retries default)