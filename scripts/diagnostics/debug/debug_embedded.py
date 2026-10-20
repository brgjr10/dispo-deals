import cloudscraper
import re
import json

scraper = cloudscraper.create_scraper(browser='chrome')

# Check embeddedMenuUrl
url = 'https://www.cultureofakron.com/shop'
r = scraper.get(url, timeout=30)
print(f'Embedded menu URL: Status {r.status_code}')

next_data_match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.DOTALL)
if next_data_match:
    data = json.loads(next_data_match.group(1))
    apollo_state = data.get('props', {}).get('pageProps', {}).get('initialApolloState', {})
    
    print(f"\nApollo state keys (first 20):")
    for key in list(apollo_state.keys())[:20]:
        val = apollo_state[key]
        if isinstance(val, dict):
            typename = val.get('__typename', 'no-typename')
            print(f"  {key}: {typename}")
        else:
            print(f"  {key}: {type(val).__name__}")
    
    # Check for Product entries
    for key, value in apollo_state.items():
        if key.startswith('Product:') and isinstance(value, dict):
            print(f'\n=== Found Product: {key} ===')
            print(json.dumps(value, indent=2)[:3000])
            break
    else:
        print("\nNo Product: entries found")
    
    # Check ROOT_QUERY
    root = apollo_state.get('ROOT_QUERY', {})
    print(f"\nROOT_QUERY: {json.dumps(root, indent=2)[:2000]}")