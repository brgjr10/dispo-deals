import cloudscraper
import json

scraper = cloudscraper.create_scraper(browser='chrome')

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json',
    'Content-Type': 'application/json',
    'Origin': 'https://dutchie.com',
    'Referer': 'https://dutchie.com/stores/culture-cannabis-club-akron',
    'x-dutchie-client': 'web'
}

# Introspect schema
introspection = '''
query Introspection {
  __schema {
    queryType { fields { name args { name type { name kind ofType { name kind } } } } }
  }
}
'''

r = scraper.post('https://dutchie.com/graphql', json={'query': introspection}, headers=headers, timeout=30)
print('Status:', r.status_code)
data = r.json()
if 'data' in data:
    for field in data['data']['__schema']['queryType']['fields']:
        if any(kw in field['name'].lower() for kw in ['menu', 'dispensary', 'store', 'product', 'category']):
            print(f"\n{field['name']}:")
            for arg in field['args']:
                type_info = arg['type']
                type_str = type_info.get('name') or (type_info.get('ofType', {}) or {}).get('name', 'unknown')
                print(f"  {arg['name']}: {type_str}")