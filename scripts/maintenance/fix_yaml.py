import yaml

config = {
    'schedule_cron': '0 */6 * * *',
    'webhook_url': '',
    'mode': 'per-store',
    'dry_run': False,
    'log_level': 'INFO',
    'stores': [
        {'id': 'culture-akron', 'name': 'Culture Cannabis Club — Akron', 'url': 'https://dutchie.com/stores/culture-cannabis-club-akron', 'scraper': 'dutchie', 'logo_url': 'https://dutchie.com/assets/images/dutchie-logo.svg', 'notification_mode': 'per-store', 'enabled': True, 'webhook_enabled': True},
        {'id': 'supergood-ravenna', 'name': 'Supergood — Ravenna', 'url': 'https://dutchie.com/stores/supergood-ravenna', 'scraper': 'dutchie', 'logo_url': 'https://dutchie.com/assets/images/dutchie-logo.svg', 'notification_mode': 'per-store', 'enabled': True, 'webhook_enabled': False},
        {'id': 'bliss-kent', 'name': 'Bliss Ohio — Kent', 'url': 'https://dutchie.com/stores/bliss-ohio-kent/products', 'scraper': 'dutchie', 'logo_url': 'https://dutchie.com/assets/images/dutchie-logo.svg', 'notification_mode': 'per-store', 'enabled': True, 'webhook_enabled': False},
        {'id': 'klutch', 'name': 'Klutch Cannabis', 'url': 'https://www.klutchcannabis.com/', 'scraper': 'klutch', 'logo_url': 'https://www.klutchcannabis.com/logo.png', 'notification_mode': 'per-store', 'enabled': True, 'webhook_enabled': False},
    ],
    'scrapers': {
        'dutchie': {'graphql_endpoint': 'https://dutchie.com/graphql', 'timeout': 30, 'headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Accept': 'application/json', 'Content-Type': 'application/json'}},
        'klutch': {'timeout': 30, 'headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}}
    },
    'images': {'cache_dir': './cache/images', 'max_width': 800, 'max_size_kb': 500, 'formats': ['jpg', 'jpeg', 'png', 'webp']},
    'deduplication': {'hash_fields': ['store_id', 'product_id', 'sale_price', 'discount_pct'], 're_notify_on_deeper_discount': True},
    'weekly_menu': {'snapshot_day': 0, 'min_items_for_snapshot': 10},
    'webhook': {'max_retries': 3, 'backoff_base_seconds': 5, 'timeout': 15}
}

with open('config.yaml', 'w', encoding='utf-8') as f:
    yaml.dump(config, f, allow_unicode=True, sort_keys=False)

print('config.yaml written with actual em dashes')