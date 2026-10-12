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
- Tables: `seen_deals`, `weekly_snapshots`, `store_logos`, `product_images`
- Image cache in `./cache/images/` (mounted as `/app/cache`)

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