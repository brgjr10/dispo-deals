import cloudscraper
import json
import re

scraper = cloudscraper.create_scraper(browser='chrome')

url = 'https://dutchie.com/stores/culture-cannabis-club-akron'
r = scraper.get(url, timeout=30)
print('Status:', r.status_code)

# Extract the NEXT_DATA script
next_data_match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.DOTALL)
if next_data_match:
    data = json.loads(next_data_match.group(1))
    apollo_state = data.get('props', {}).get('pageProps', {}).get('initialApolloState', {})
    
    # Find products in Apollo cache
    products = []
    for key, value in apollo_state.items():
        if key.startswith('Product:') and isinstance(value, dict):
            images = value.get('images', [])
            img_url = ''
            if images and isinstance(images, list) and len(images) > 0:
                img_ref = images[0]
                if isinstance(img_ref, dict) and '__ref' in img_ref:
                    img_key = img_ref['__ref']
                    img_data = apollo_state.get(img_key, {})
                    img_url = img_data.get('url', '')
                elif isinstance(img_ref, str):
                    img_data = apollo_state.get(img_ref, {})
                    img_url = img_data.get('url', '')
            
            pricing = value.get('pricing', {})
            products.append({
                'id': value.get('id'),
                'name': value.get('name'),
                'brand': value.get('brand', {}).get('name') if isinstance(value.get('brand'), dict) else value.get('brand'),
                'category': value.get('category'),
                'price': pricing.get('price'),
                'originalPrice': pricing.get('originalPrice'),
                'discount': pricing.get('discount'),
                'url': value.get('url'),
                'image_url': img_url,
                'thc': value.get('thc'),
                'cbd': value.get('cbd'),
                'weight': value.get('weight'),
                'inStock': value.get('inStock'),
            })
    
    print(f'Found {len(products)} products')
    for p in products[:10]:
        print(f"  {p['name']} | ${p['price']} | {p['category']} | img: {p['image_url'][:80] if p['image_url'] else 'none'}")

# Also check categories
categories = {}
for key, value in apollo_state.items():
    if key.startswith('Category:') and isinstance(value, dict):
        categories[value.get('id')] = value.get('name')

print(f'\nCategories: {categories}')