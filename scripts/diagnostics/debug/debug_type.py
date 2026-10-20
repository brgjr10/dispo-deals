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

# Get all fields from the Dispensaries type via introspection on that specific type
query = '''
query GetDispensaryFields {
    __type(name: "Dispensaries") {
        fields {
            name
            args { name type { name kind ofType { name kind } } }
            type { name kind ofType { name kind } }
        }
    }
}
'''

r = scraper.post('https://dutchie.com/graphql', json={'query': query}, headers=headers, timeout=30)
print('Status:', r.status_code)
data = r.json()
if 'data' in data and data['data']['__type']:
    for field in data['data']['__type']['fields']:
        type_info = field['type']
        type_str = type_info.get('name') or (type_info.get('ofType', {}) or {}).get('name', 'unknown')
        args = [f"{a['name']}: {a['type'].get('name') or a['type'].get('ofType', {}).get('name', '?')}" for a in field.get('args', [])]
        print(f"  {field['name']}({', '.join(args)}) -> {type_str}")