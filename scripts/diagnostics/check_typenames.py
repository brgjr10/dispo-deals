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
    
    # Collect all product IDs from MenuSections
    product_ids = set()
    for key, value in apollo_state.items():
        if key.startswith('MenuSection:') and isinstance(value, dict):
            products = value.get('products', [])
            for p in products:
                if isinstance(p, str):
                    product_ids.add(p)
                elif isinstance(p, dict) and '__ref' in p:
                    product_ids.add(p['__ref'])
    
    # Check typenames for all product IDs
    typenames = {}
    for pid in product_ids:
        product = apollo_state.get(pid)
        if product and isinstance(product, dict):
            tn = product.get('__typename', 'NO_TYPENAME')
            typenames[tn] = typenames.get(tn, 0) + 1
    
    print('Typenames found:')
    for tn, count in typenames.items():
        print(f'  {tn}: {count}')