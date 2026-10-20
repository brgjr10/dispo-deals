import cloudscraper
import json
import re

scraper = cloudscraper.create_scraper(browser='chrome')

url = 'https://dutchie.com/stores/culture-cannabis-club-akron'
r = scraper.get(url, timeout=30)

next_data_match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.DOTALL)
if next_data_match:
    data = json.loads(next_data_match.group(1))
    apollo_state = data.get('props', {}).get('pageProps', {}).get('initialApolloState', {})
    
    # Collect all product IDs from MenuSections
    product_ids = set()
    for key, value in apollo_state.items():
        if key.startswith('MenuSection:') and isinstance(value, dict):
            products = value.get('products', [])
            for p in products:
                if isinstance(p, str):
                    product_ids.add(p)
                elif isinstance(p, dict) and '__ref' in p:
                    product_ids.add(p['__ref'])
    
    print(f'Found {len(product_ids)} product IDs')
    
    # Look up each product
    count = 0
    for pid in product_ids:
        product = apollo_state.get(pid)
        if product and isinstance(product, dict) and product.get('__typename') == 'Product':
            images = product.get('images', [])
            img_url = ''
            if images and len(images) > 0:
                img_ref = images[0]
                if isinstance(img_ref, dict) and '__ref' in img_ref:
                    img_key = img_ref['__ref']
                    img_data = apollo_state.get(img_key, {})
                    img_url = img_data.get('url', '')
                elif isinstance(img_ref, str):
                    img_data = apollo_state.get(img_ref, {})
                    img_url = img_data.get('url', '')
            
            pricing = product.get('pricing', {})
            brand = product.get('brand', {})
            brand_name = brand.get('name') if isinstance(brand, dict) else brand
            
            print(f"  {product.get('name')} | ${pricing.get('price')} | {product.get('category')} | brand: {brand_name} | img: {img_url[:80] if img_url else 'none'} | thc: {product.get('thc')} | weight: {product.get('weight')}")
            count += 1
    
    print(f'\nTotal products extracted: {count}')