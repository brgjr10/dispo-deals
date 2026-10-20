import requests

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json',
    'Content-Type': 'application/json',
    'Origin': 'https://dutchie.com',
    'Referer': 'https://dutchie.com/stores/culture-cannabis-club-akron',
    'x-dutchie-client': 'web'
}

# Try introspection to see schema
introspection = '''
query Introspection {
  __schema {
    queryType { fields { name args { name type { name kind ofType { name kind } } } } }
  }
}
'''

r = requests.post('https://dutchie.com/graphql', json={'query': introspection}, headers=headers, timeout=30)
print('Status:', r.status_code)
import json
data = r.json()
if 'data' in data:
    for field in data['data']['__schema']['queryType']['fields']:
        if 'menu' in field['name'].lower() or 'dispensary' in field['name'].lower() or 'store' in field['name'].lower():
            print(field['name'], field['args'])