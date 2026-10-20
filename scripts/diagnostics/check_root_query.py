import cloudscraper
import json
import re

scraper = cloudscraper.create_scraper(browser='chrome')

url = 'https://dutchie.com/stores/culture-cannabis-club-akron'
r = scraper.get(url, timeout=30)

# Search for all GraphQL queries in the page
next_data_match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.DOTALL)
if next_data_match:
    data = json.loads(next_data_match.group(1))
    apollo_state = data.get('props', {}).get('pageProps', {}).get('initialApolloState', {})
    
    # Search for any query/mutation in the apollo state that might contain products
    # Also check for cache keys that contain product data
    for key, value in apollo_state.items():
        if isinstance(value, dict) and value.get('__typename') in ['Product', 'MenuItem', 'DispensaryProduct']:
            print(f'Found product-like: {key}')
            print(json.dumps(value, indent=2)[:500])
    
    # The products might be loaded via a separate query - let's check the ROOT_QUERY more carefully
    root = apollo_state.get('ROOT_QUERY', {})
    print('\nROOT_QUERY entries:')
    for k, v in root.items():
        if isinstance(v, list):
            print(f'  {k}: list of {len(v)} items')
            for item in v[:3]:
                if isinstance(item, dict) and '__ref' in item:
                    ref = item['__ref']
                    print(f'    -> {ref}')
                    if ref in apollo_state:
                        ref_data = apollo_state[ref]
                        if isinstance(ref_data, dict):
                            print(f'       {ref_data.get("__typename")}: {ref_data.get("name", ref_data.get("id"))}')
        else:
            print(f'  {k}: {type(v)}')