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
    
    # Check for Product: prefix
    product_ids = ["69cbd954b763105331d813e5", "69d557c6db5036d2b97918e1", "69bc4ac04cf2adc54d57a268"]
    
    for pid in product_ids:
        # Try with Product: prefix
        key1 = f"Product:{pid}"
        # Try without prefix
        key2 = pid
        
        found = False
        for key, value in apollo_state.items():
            if key == key1 or key == key2:
                if isinstance(value, dict):
                    print(f'=== {key} ===')
                    print(json.dumps(value, indent=2)[:3000])
                    found = True
                    break
        if not found:
            print(f"Product {pid}: NOT FOUND in apollo_state")
    
    # Also check all keys that might contain product data
    print("\n--- All keys containing 'product' (case insensitive) ---")
    for key, value in apollo_state.items():
        if 'product' in key.lower():
            print(f"  {key}: {type(value).__name__}")