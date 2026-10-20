import cloudscraper
import json
import re

scraper = cloudscraper.create_scraper(browser='chrome')

# First get the dispensary ID
url = 'https://dutchie.com/stores/culture-cannabis-club-akron'
r = scraper.get(url, timeout=30)

next_data_match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.DOTALL)
if next_data_match:
    data = json.loads(next_data_match.group(1))
    apollo_state = data.get('props', {}).get('pageProps', {}).get('initialApolloState', {})
    
    # Get dispensary ID
    root = apollo_state.get('ROOT_QUERY', {})
    for k, v in root.items():
        if isinstance(v, list) and v and isinstance(v[0], dict) and '__ref' in v[0]:
            dispensary_ref = v[0]['__ref']
            dispensary = apollo_state.get(dispensary_ref, {})
            print(f'Dispensary: {dispensary.get("name")} (id: {dispensary.get("id")})')
            print(f'  slug: {dispensary.get("slug")}')
            print(f'  externalId: {dispensary.get("externalId")}')
            print(f'  locationId: {dispensary.get("locationId")}')