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
    print('Apollo state keys count:', len(apollo_state))
    print('First 10 keys:', list(apollo_state.keys())[:10])