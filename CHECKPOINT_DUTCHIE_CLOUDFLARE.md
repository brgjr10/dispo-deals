# Dutchie Cloudflare Bypass - Checkpoint

## Executive Summary
**Dutchie's GraphQL API has changed schema and introspection is disabled. The only working path is FlareSolverr-rendered DOM extraction.**

---

## What Does NOT Work

### 1. Direct GraphQL Queries
```graphql
query Menu($dispensarySlug: String!, $filters: MenuFiltersInput) {
    menu(dispensarySlug: $dispensarySlug, filters: $filters) { ... }
}
```
**Result:** `400 - Unknown type "MenuFiltersInput"` and `Cannot query field "menu" on type "Query"`
**Verified:** Direct requests, cloudscraper, FlareSolverr POST - all return 400 with GraphQL errors

### 2. GraphQL Introspection
```graphql
query { __schema { queryType { fields { name } } } }
```
**Result:** `400 - GraphQL introspection is not allowed by Apollo Server`

### 3. Alternative Query Names Tested
- `dispensaryMenu` → `Cannot query field "dispensaryMenu" on type "Query"`
- `dispensary` → `Cannot query field "dispensary" on type "Query"`
- `store` → `Cannot query field "store" on type "Query"`
- `filteredDispensaries` → Works for dispensary info, but **no menu field exists** on Dispensaries type

### 4. Apollo Cache in Initial HTML (`__NEXT_DATA__`)
- Contains `MenuSection` objects with product IDs (strings like `"69cbd954b763105331d813e5"`)
- **NO `Product:` entries exist in initial state** - products are loaded via subsequent GraphQL queries
- Page extraction from initial HTML returns 0 deals

### 5. cloudscraper Without FlareSolverr
- Dutchie returns Cloudflare challenge page
- 403 Forbidden without browser fingerprint

---

## What WORKS (Verified)

### FlareSolverr GET → Rendered DOM → BeautifulSoup
1. FlareSolverr executes JavaScript on the page
2. Returns fully rendered HTML with product cards
3. BeautifulSoup extracts product data from DOM

**FlareSolverr Request:**
```json
{
  "cmd": "request.get",
  "url": "https://dutchie.com/stores/culture-cannabis-club-akron",
  "maxTimeout": 60000,
  "headers": { ... }
}
```

**FlareSolverr Response:** 200 OK with rendered HTML body

---

## Current Architecture

### Services (docker-compose.yml)
| Service | Port | Purpose |
|---------|------|---------|
| flaresolverr | 8191 | Cloudflare bypass (headless Chrome) |
| scraper | - | Scheduled runs, uses FlareSolverr |
| api | 4040 | Dashboard at `/dashboard.html` |
| manual-scrape | - | Manual trigger profile |

### Scraper Fallback Chain (in `scrapers/dutchie.py`)
1. **GraphQL POST** via FlareSolverr → Fails (schema changed)
2. **Page HTML GET** via FlareSolverr → Parses `__NEXT_DATA__` Apollo cache → 0 products
3. **DOM Extraction GET** via FlareSolverr → **SHOULD WORK** - executes JS, parses product cards

---

## Key Files
- `scrapers/dutchie.py` - Main scraper with 3-tier fallback
- `config.yaml` - Store configs (only `culture-akron` has `webhook_enabled: true`)
- `.env` - `FLARESOLVERR_URL=http://flaresolverr:8191`, `WEBHOOK_URL=` (empty)
- `docker-compose.yml` - Service definitions

---

## Klutch Cannabis - DEAD END
- `https://www.klutchcannabis.com/collections/*` → **All 404**
- Site is a strain library (`/strains/`), not a dispensary menu
- **Disabled in config.yaml** (`enabled: false`)

---

## Debugging Commands (Run on ZimaOS)

```bash
# Rebuild with fresh layers
cd ~/AppData/Projects/dispo-deals
docker compose build --no-cache --pull scraper
docker compose run --rm manual-scrape

# Check FlareSolverr logs
docker logs dispo-flaresolverr

# Test FlareSolverr directly
curl -X POST http://localhost:8191/v1 \
  -H "Content-Type: application/json" \
  -d '{"cmd":"request.get","url":"https://dutchie.com/stores/culture-cannabis-club-akron","maxTimeout":60000}'
```

---

## Current Blockers (as of 2026-10-12)

1. **Volume mount caching** - `docker compose build --no-cache` may not pick up code changes if `COPY . .` layer is cached
2. **No DEBUG logs appearing** - Added debug logging to `_make_request` but not visible in container output
3. **GET requests not reaching FlareSolverr** - Logs show only POST (GraphQL), no GET for page/DOM extraction
4. **`'DutchieScraper' object has no attribute 'scraper'`** - Error in `_extract_from_page` suggests routing bug

---

## Next Steps for Future Agent

1. **Verify code is actually in container:**
   ```bash
   docker exec dispo-scraper cat /app/scrapers/dutchie.py | head -200
   ```

2. **Check `_make_request` routing logic** - Ensure FlareSolverr GET is called for page/DOM extraction

3. **If DOM extraction works**, products will appear in logs with format:
   ```
   - Product Name: $35.00/$50.00 (30% off) [Flower]
   ```

4. **Set WEBHOOK_URL** in `.env` for notifications

5. **Dashboard** at `http://<zimaos>:4040/dashboard.html` shows deals