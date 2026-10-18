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
    
    # Find all unique typenames
    typenames = set()
    for key, value in apollo_state.items():
        if isinstance(value, dict):
            typename = value.get('__typename', 'no-typename')
            typenames.add(typename)
    
    print("All typenames:")
    for t in sorted(typenames):
        print(f"  {t}")