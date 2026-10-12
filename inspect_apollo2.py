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
    
    # Check ROOT_QUERY
    root = apollo_state.get('ROOT_QUERY', {})
    print('ROOT_QUERY keys:')
    for k in root.keys():
        print(f'  {k}')
    
    # Check MenuSection
    for key, value in apollo_state.items():
        if key.startswith('MenuSection:') and isinstance(value, dict):
            print(f'\n{key}:')
            print(f'  name: {value.get("name")}')
            products = value.get('products', [])
            print(f'  products: {products}')