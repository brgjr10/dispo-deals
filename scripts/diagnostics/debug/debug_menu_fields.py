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

# Check menu fields for errors
menu_fields = ['menu', 'menuCategories', 'categories', 'products', 'menuItems', 'dispensaryMenu', 'storeMenu', 'availableProducts']

for field in menu_fields:
    query = f'''
    query GetDispensary($filter: dispensariesFilterInput!) {{
        filteredDispensaries(filter: $filter) {{
            {field}
        }}
    }}
    '''
    payload = {"query": query, "variables": {"filter": {"cNameOrID": "culture-cannabis-club-akron"}}}
    r = scraper.post('https://dutchie.com/graphql', json=payload, headers=headers, timeout=30)
    data = r.json()
    if 'errors' in data:
        print(f"\n=== {field} - ERROR ===")
        for e in data['errors']:
            print(f"  {e['message']}")
    else:
        print(f"\n=== {field} ===")
        print(json.dumps(data, indent=2)[:1000])