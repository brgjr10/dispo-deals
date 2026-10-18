import cloudscraper
import json
import re

scraper = cloudscraper.create_scraper(browser='chrome')
url = 'https://dutchie.com/stores/culture-cannabis-club-akron'
r = scraper.get(url, timeout=30)

next_data_match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.DOTALL)
if next_data_match:
    data = json.loads(next_data_match.group(1))
    apollo_state = data.get('props', {}).get('pageProps', {}).get('initialApolloState', {})
    
    # Check one MenuSection in detail
    for key, value in apollo_state.items():
        if key.startswith('MenuSection:') and isinstance(value, dict) and value.get('products'):
            print(f'=== {key} ===')
            print(json.dumps(value, indent=2))
            break
    
    # Check if product IDs in MenuSection are refs
    print("\n--- Checking product ID format ---")
    for key, value in apollo_state.items():
        if key.startswith('MenuSection:') and isinstance(value, dict):
            products = value.get('products', [])
            for p in products[:3]:
                print(f"  Product entry: {p} (type: {type(p).__name__})")
            break