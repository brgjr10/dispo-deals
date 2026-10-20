import cloudscraper
import json

scraper = cloudscraper.create_scraper(browser='chrome')

# Try different query names that Dutchie might use
queries_to_try = [
    "dispensaryMenu",
    "menuV2", 
    "getMenu",
    "storeMenu",
    "dispensaryProducts",
    "products",
    "catalog"
]

for query_name in queries_to_try:
    query = f"""
    query {query_name}($dispensarySlug: String!) {{
      {query_name}(dispensarySlug: $dispensarySlug) {{
        id
        name
        products {{
          id
          name
        }}
      }}
    }}
    """
    
    payload = {"query": query, "variables": {"dispensarySlug": "culture-cannabis-club-akron"}}
    
    r = scraper.post('https://dutchie.com/graphql', json=payload, timeout=15)
    if r.status_code == 200:
        data = r.json()
        if 'errors' not in data or not data['errors']:
            print(f'SUCCESS: {query_name}')
            print(json.dumps(data, indent=2)[:1000])
            break
        else:
            print(f'{query_name}: {data["errors"][0]["message"][:100]}')
    else:
        print(f'{query_name}: HTTP {r.status_code}')