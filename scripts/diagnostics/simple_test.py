import cloudscraper
import re
import json

scraper = cloudscraper.create_scraper(browser='chrome')
url = 'https://www.cultureofakron.com/shop'
r = scraper.get(url, timeout=30)
print('Status:', r.status_code)

next_data_match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.DOTALL)
if next_data_match:
    data = json.loads(next_data_match.group(1))
    apollo_state = data.get('props', {}).get('pageProps', {}).get('initialApolloState', {})
    product_count = 0
    for key, value in apollo_state.items():
        if key.startswith('Product:') and isinstance(value, dict):
            product_count += 1
            if product_count <= 3:
                print('Found Product:', key)
    print('Total Product entries:', product_count)
    root = apollo_state.get('ROOT_QUERY', {})
    print('ROOT_QUERY keys:', list(root.keys()))