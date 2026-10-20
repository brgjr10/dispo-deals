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

# Try queries that take dispensary ID or slug
queries_to_try = [
    # Try with dispensary ID
    ('menuByDispensaryId', 'dispensaryId'),
    ('menuByDispensary', 'dispensaryId'),
    ('getMenu', 'dispensaryId'),
    ('dispensaryMenu', 'dispensaryId'),
    ('storeMenu', 'storeId'),
    ('menu', 'dispensarySlug'),  # original but with different args
    ('menu', 'slug'),
    ('menu', 'cName'),
    ('menu', 'dispensaryId'),
    ('products', 'dispensaryId'),
    ('categories', 'dispensaryId'),
    ('menuCategories', 'dispensaryId'),
]

for query_name, arg_name in queries_to_try:
    query = f'''
    query GetMenu(${arg_name}: String!) {{
        {query_name}({arg_name}: ${arg_name}) {{
            id
            categories {{
                name
                products {{
                    id
                    name
                    brand {{ name }}
                    category
                    pricing {{ price originalPrice discount }}
                    images {{ url thumbnailUrl }}
                    url
                    thc
                    cbd
                    weight
                    inStock
                }}
            }}
        }}
    }}
    '''
    payload = {"query": query, "variables": {arg_name: "culture-cannabis-club-akron"}}
    r = scraper.post('https://dutchie.com/graphql', json=payload, headers=headers, timeout=30)
    if r.status_code == 200:
        data = r.json()
        if 'errors' not in data and data.get('data', {}).get(query_name):
            print(f"\n=== SUCCESS: {query_name}({arg_name}) ===")
            print(json.dumps(data, indent=2)[:3000])
            break
        elif 'errors' in data:
            for e in data['errors']:
                if 'Cannot query field' in e['message']:
                    pass  # Expected
                else:
                    print(f"\n=== {query_name}({arg_name}) - OTHER ERROR ===")
                    print(e['message'][:200])