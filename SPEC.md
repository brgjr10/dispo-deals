# Dispo Deals Notifier — Specification

## Overview
A webhook-based notifier that monitors dispensary menus for new deals and weekly menu changes, sending rich-formatted notifications (Discord/Slack/webhook) with store logos and product images.

## Data Sources
| Store | URL | Notes |
|-------|-----|-------|
| Culture Cannabis Club — Akron | https://dutchie.com/stores/culture-cannabis-club-akron | Dutchie |
| Supergood — Ravenna | https://dutchie.com/stores/supergood-ravenna | Dutchie |
| Bliss Ohio — Kent | https://dutchie.com/stores/bliss-ohio-kent/products | Dutchie |
| Klutch Cannabis | https://www.klutchcannabis.com/ | Custom site |
| Other local dispensaries | TBD | Extensible |

## Core Requirements

### 1. Deal Detection
- Scrape each source on a configurable schedule (default: every 6 hours)
- Extract: product name, price, discount %, category, image URL, product URL
- **Deduplication**: Only notify when a deal is *new* (not seen in previous run)
- Persist seen deals (hash: store + product + price + discount) to local SQLite/JSON

### 2. Weekly Menu Tracking
- On each run, capture full menu snapshot per store
- Compare against previous week's snapshot
- Mark each item: `NEW` (not in last week) or `CARRYOVER` (was in last week)
- Week 1: all items marked `NEW` (no prior baseline)

### 3. Notification Modes
| Mode | Trigger | Payload |
|------|---------|---------|
| **Per-store** | New deals found for a store | One message per store: store logo, list of new deals |
| **Per-product** | Individual new deal | One message per deal: product image, deal details |

User configures mode per store or globally.

### 4. Rich Message Format
- **Store logo**: Fetched once, cached locally, attached as thumbnail
- **Product photo**: Attached inline per product (per-product mode) or as grid (per-store mode)
- Fields: product name, original/sale price, discount %, category, link to product
- Timestamp of detection

### 5. Configuration
```yaml
# config.yaml
schedule_cron: "0 */6 * * *"  # every 6 hours
webhook_url: "https://discord.com/api/webhooks/..."
mode: "per-store"  # or "per-product"
stores:
  - id: culture-akron
    name: "Culture Cannabis Club — Akron"
    url: "https://dutchie.com/stores/culture-cannabis-club-akron"
    scraper: "dutchie"
    logo_url: "https://.../logo.png"
    notification_mode: "per-store"
  - id: klutch
    name: "Klutch Cannabis"
    url: "https://www.klutchcannabis.com/"
    scraper: "klutch"
    logo_url: "https://.../logo.png"
```
Extensible: add new stores by adding scraper module + config entry.

## Architecture

### Components
```
dispo-deals/
├── config.yaml
├── main.py                 # entry point, scheduler
├── scrapers/
│   ├── __init__.py
│   ├── base.py             # abstract base scraper
│   ├── dutchie.py          # Dutchie GraphQL/API
│   └── klutch.py           # HTML parse / API
├── storage/
│   ├── __init__.py
│   └── sqlite.py           # seen_deals, weekly_snapshots
├── notifier/
│   ├── __init__.py
│   └── webhook.py          # Discord/Slack payload builder
├── utils/
│   ├── __init__.py
│   ├── images.py           # download, cache, resize
│   ├── diff.py             # menu comparison logic
│   ├── leafly.py           # Leafly search API + strain page client
│   └── strain_match.py     # name -> strain extraction, resolution, caching
└── tests/
```

### Data Models
```python
# Deal
store_id: str
product_id: str
name: str
category: str
original_price: float
sale_price: float
discount_pct: float
image_url: str
product_url: str
detected_at: datetime
strain_name: Optional[str]  # matched Leafly strain; excluded from hash
hash: str  # store_id + product_id + sale_price + discount_pct

# Strain
name: str
slug: str
category: str            # Hybrid / Sativa / Indica
thc_low: Optional[float]     # percentile25
thc_pct: Optional[float]     # percentile50
thc_high: Optional[float]    # percentile75
cbd_low: Optional[float]
cbd_pct: Optional[float]
cbd_high: Optional[float]
effects: List[str]
flavors: List[str]
terpenes: List[str]
helps_with: List[str]
rating: Optional[float]
review_count: Optional[int]
description: str
image_url: str
parents: List[str]
children: List[str]
source: str              # leafly-search | leafly-detail
fetched_at: Optional[datetime]

# WeeklySnapshot
store_id: str
week_start: date  # Monday
items: List[Deal]  # full menu at snapshot time

# SeenDeal
hash: str
strain_name: Optional[str]
first_seen: datetime
last_notified: datetime
```

## Scraper Details

### Dutchie Stores
- Dutchie uses GraphQL endpoint: `https://dutchie.com/graphql`
- Query `menu` with `dispensarySlug` (from URL)
- Response includes: products, categories, images, pricing
- Handle pagination if needed

### Klutch Cannabis
- Static HTML or internal API — inspect network tab
- Likely need to parse product cards from category pages

### Extensibility
New scraper = implement `BaseScraper`:
```python
class BaseScraper(ABC):
    @abstractmethod
    def fetch_menu(self) -> List[Deal]: ...
    @abstractmethod
    def fetch_logo(self) -> bytes: ...
```

## Deduplication Logic
```python
def is_new_deal(deal: Deal) -> bool:
    existing = db.get_seen_deal(deal.hash)
    if not existing:
        db.save_seen_deal(deal)
        return True
    # Optionally re-notify if discount increased
    if deal.discount_pct > existing.max_discount_pct:
        db.update_seen_deal(deal)
        return True
    return False
```

## Weekly Menu Diff
```python
def compute_weekly_diff(current: List[Deal], previous: List[Deal]) -> List[MenuItem]:
    prev_names = {(d.name, d.category) for d in previous}
    result = []
    for deal in current:
        status = "NEW" if (deal.name, deal.category) not in prev_names else "CARRYOVER"
        result.append(MenuItem(deal=deal, status=status))
    return result
```

## Image Handling
- Download logos/product images on first use
- Cache in `./cache/images/` with hash-based filenames
- Resize to max 800px width for webhook payload size limits
- Attach as `multipart/form-data` (Discord) or image URL (Slack)

## Leafly Strain Import
- leafly.py reads Leafly's public consumer search endpoint and strain pages
- strain_match.py turns a product name into a strain candidate and verifies it
  against Leafly, accepting only an exact name match (Leafly ranks an exact
  strain first, so a near-miss means no such strain exists)
- Matched profiles are stored in `strains`; failed candidates in `strain_misses`
  so a proprietary cutting is only ever queried once
- The dashboard renders phenotype, potency, effects, flavours and terpenes per
  product, with attribution back to Leafly

## Error Handling
- Scraper failures: log, continue other stores, alert on repeated failures
- Webhook failures: retry with exponential backoff (max 3)
- Missing images: send notification without image, log warning
- Network timeouts: 30s per request
- Strain lookup failures are non-fatal: a product without a strain still
  appears in the dashboard, just without a strain profile

## Deployment
- Run as systemd service / Docker container / scheduled cron
- Single binary/script, no external DB required (SQLite)
- Config via `config.yaml` + env var for webhook URL

## Testing
- Unit tests for diff logic, deduplication, payload building
- Integration test with recorded HTML/JSON fixtures per scraper
- Dry-run mode: `--dry-run` logs what would be sent without webhook call

## Future Enhancements
- Price drop alerts (notify when existing product price decreases)
- Category filters (only notify for flower, edibles, etc.)
- Multi-webhook targets (Discord + Slack + email)
- Web dashboard for manual review
- Historical price charts