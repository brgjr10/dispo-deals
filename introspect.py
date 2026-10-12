import cloudscraper
import json

scraper = cloudscraper.create_scraper(browser='chrome')

# Introspection query to find the correct menu query
introspection = """
query Introspection {
  __schema {
    queryType {
      fields {
        name
        args { name type { name kind ofType { name kind } } }
      }
    }
  }
}
"""

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json',
    'Content-Type': 'application/json',
}

payload = {"query": introspection}

r = scraper.post('https://dutchie.com/graphql', json=payload, headers=headers, timeout=30)
print('Status:', r.status_code)
if r.status_code == 200:
    data = r.json()
    if 'data' in data:
        for field in data['data']['__schema']['queryType']['fields']:
            name = field['name']
            if any(term in name.lower() for term in ['menu', 'dispensary', 'store', 'product', 'catalog']):
                args = [f"{a['name']}: {a['type']['name'] if a['type']['name'] else a['type'].get('ofType', {}).get('name', '?')}" for a in field['args']]
                print(f'{name}({", ".join(args)})')