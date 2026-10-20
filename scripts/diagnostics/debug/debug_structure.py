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
    
    # Print full structure of first MenuSection
    for key, value in apollo_state.items():
        if key.startswith('MenuSection:') and isinstance(value, dict) and value.get('products'):
            print(f'\n=== {key} ===')
            print(json.dumps(value, indent=2)[:2000])
            break
    
    # Also check ROOT_QUERY fully
    root = apollo_state.get('ROOT_QUERY', {})
    print('\n=== ROOT_QUERY ===')
    print(json.dumps(root, indent=2)[:3000])