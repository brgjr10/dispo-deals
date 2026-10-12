import cloudscraper
import json

scraper = cloudscraper.create_scraper(browser='chrome')

# The actual GraphQL query used by Dutchie frontend
query = """
query Menu($dispensarySlug: String!, $filters: MenuFiltersInput) {
  menu(dispensarySlug: $dispensarySlug, filters: $filters) {
    id
    dispensary {
      id
      name
      slug
      logo { url }
    }
    categories {
      id
      name
      products {
        id
        name
        brand { name }
        category
        pricing { price originalPrice discount }
        images { url thumbnailUrl }
        url
        thc
        cbd
        weight
        inStock
      }
    }
  }
}
"""

variables = {
    "dispensarySlug": "culture-cannabis-club-akron",
    "filters": {}
}

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json',
    'Content-Type': 'application/json',
    'Origin': 'https://dutchie.com',
    'Referer': 'https://dutchie.com/stores/culture-cannabis-club-akron',
    'x-dutchie-client': 'web'
}

payload = {"query": query, "variables": variables}

r = scraper.post('https://dutchie.com/graphql', json=payload, headers=headers, timeout=30)
print('Status:', r.status_code)
if r.status_code == 200:
    data = r.json()
    print('Response keys:', data.keys())
    if 'data' in data:
        menu = data['data'].get('menu')
        if menu:
            print(f'Dispensary: {menu.get("dispensary", {}).get("name")}')
            for cat in menu.get('categories', []):
                cat_name = cat.get('name')
                products = cat.get('products', [])
                print(f'\nCategory: {cat_name} ({len(products)} products)')
                for p in products[:5]:
                    images = p.get('images', [])
                    img = images[0].get('thumbnailUrl', '') if images else ''
                    pricing = p.get('pricing', {})
                    brand = p.get('brand', {})
                    print(f"  {p['name']} | ${pricing.get('price')} | {p['category']} | brand: {brand.get('name') if isinstance(brand, dict) else brand} | img: {img[:80] if img else 'none'} | thc: {p.get('thc')} | weight: {p.get('weight')}")
else:
    print('Error:', r.text[:500])