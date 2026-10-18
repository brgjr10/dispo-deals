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

# Try filteredDispensaries with minimal fields
query = '''
query GetDispensary($filter: FilterInput!) {
    filteredDispensaries(filter: $filter) {
        id
        name
        cName
    }
}
'''

# Try different filter input types
for filter_type in ['FilterInput', 'DispensariesFilter', 'DispensaryFilter', 'String']:
    q = query.replace('FilterInput', filter_type)
    payload = {"query": q, "variables": {"filter": {"cNameOrID": "culture-cannabis-club-akron"}}}
    r = scraper.post('https://dutchie.com/graphql', json=payload, headers=headers, timeout=30)
    print(f'\n=== Filter type: {filter_type} ===')
    print(f'Status: {r.status_code}')
    print(r.text[:1000])