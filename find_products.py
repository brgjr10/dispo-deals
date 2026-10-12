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
    
    # Search for all keys containing product-like IDs
    all_keys = list(apollo_state.keys())
    
    # Look for Product:* keys
    product_keys = [k for k in all_keys if 'product' in k.lower() or 'Product' in k]
    print(f'Product-like keys: {len(product_keys)}')
    for k in product_keys[:20]:
        val = apollo_state[k]
        if isinstance(val, dict):
            print(f'  {k}: {val.get("__typename", "no-typename")}')
    
    # Also check for keys that might contain the product IDs we found
    product_ids = set()
    for key, value in apollo_state.items():
        if key.startswith('MenuSection:') and isinstance(value, dict):
            products = value.get('products', [])
            for p in products:
                if isinstance(p, str):
                    product_ids.add(p)
                elif isinstance(p, dict) and '__ref' in p:
                    product_ids.add(p['__ref'])
    
    # Check if any apollo_state key contains these IDs as substrings
    for pid in list(product_ids)[:5]:
        matches = [k for k in all_keys if pid in k]
        if matches:
            print(f'\nID {pid} found in keys:')
            for m in matches[:5]:
                val = apollo_state[m]
                if isinstance(val, dict):
                    print(f'  {m}: {val.get("__typename", "no-typename")}')
                    print(f'    {json.dumps(val, indent=2)[:300]}')