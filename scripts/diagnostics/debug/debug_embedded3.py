import cloudscraper
import re
import json

scraper = cloudscraper.create_scraper(browser='chrome')

# Check embeddedMenuUrl
url = 'https://www.cultureofakron.com/shop'
r = scraper.get(url, timeout=30)

next_data_match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.DOTALL)
if next_data_match:
    data = json.loads(next_data_match.group(1))
    apollo_state = data.get('props', {}).get('pageProps', {}).get('initialApolloState', {})
    
    # Check for Product entries
    product_count = 0
    results = []
    for key, value in apollo_state.items():
        if key.startswith('Product:') and isinstance(value, dict):
            product_count += 1
            if product_count <= 3:
                results.append(f'\n=== Found Product: {key} ===\n{json.dumps(value, indent=2)[:3000]}')
    results.append(f"\nTotal Product: entries: {product_count}")
    
    # Check ROOT_QUERY
    root = apollo_state.get('ROOT_QUERY', {})
    results.append(f"\nROOT_QUERY keys: {list(root.keys())}")
    
    with open('embedded_debug_output.txt', 'w') as f:
        f.write('\n'.join(results))
    print("Output written to embedded_debug_output.txt")