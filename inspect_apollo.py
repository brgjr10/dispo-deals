import cloudscraper
import json
import re

scraper = cloudscraper.create_scraper(browser='chrome')

url = 'https://dutchie.com/stores/culture-cannabis-club-akron'
r = scraper.get(url, timeout=30)

# Extract the NEXT_DATA script
next_data_match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.DOTALL)
if next_data_match:
    data = json.loads(next_data_match.group(1))
    apollo_state = data.get('props', {}).get('pageProps', {}).get('initialApolloState', {})
    
    # Print all keys to understand structure
    print('Apollo state keys (first 50):')
    for i, key in enumerate(list(apollo_state.keys())[:50]):
        val = apollo_state[key]
        if isinstance(val, dict):
            typename = val.get('__typename', 'no-typename')
            print(f'  {key}: {typename}')
        else:
            print(f'  {key}: {type(val).__name__}')