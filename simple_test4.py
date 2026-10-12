import cloudscraper
import re
import json
import sys

try:
    scraper = cloudscraper.create_scraper(browser='chrome')
    url = 'https://culturecannabisclub.com/stores/culture-cannabis-club-akron'
    r = scraper.get(url, timeout=30)
    print('Status:', r.status_code, file=sys.stderr)

    next_data_match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.DOTALL)
    if next_data_match:
        data = json.loads(next_data_match.group(1))
        apollo_state = data.get('props', {}).get('pageProps', {}).get('initialApolloState', {})
        print('Apollo state keys count:', len(apollo_state), file=sys.stderr)
        print('First 10 keys:', list(apollo_state.keys())[:10], file=sys.stderr)
        
        product_count = 0
        for key, value in apollo_state.items():
            if key.startswith('Product:') and isinstance(value, dict):
                product_count += 1
                if product_count <= 3:
                    print('Found Product:', key, file=sys.stderr)
        print('Total Product entries:', product_count, file=sys.stderr)
    else:
        print('No NEXT_DATA found', file=sys.stderr)
except Exception as e:
    print('Error:', e, file=sys.stderr)
    import traceback
    traceback.print_exc(file=sys.stderr)