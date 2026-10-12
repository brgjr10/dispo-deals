import cloudscraper
import re
import sys

try:
    scraper = cloudscraper.create_scraper(browser='chrome')
    url = 'https://www.cultureofakron.com/shop'
    r = scraper.get(url, timeout=30)
    print('Status:', r.status_code, file=sys.stderr)
    print('Content-Type:', r.headers.get('Content-Type'), file=sys.stderr)
    
    # Check for platform indicators
    content = r.text.lower()
    if 'shopify' in content:
        print('Platform: Shopify', file=sys.stderr)
    if 'woocommerce' in content:
        print('Platform: WooCommerce', file=sys.stderr)
    if 'dutchie' in content:
        print('Platform: Dutchie', file=sys.stderr)
    if 'bigcommerce' in content:
        print('Platform: BigCommerce', file=sys.stderr)
    
    # Check for product data in page
    if 'product' in content:
        print('Has product references', file=sys.stderr)
    
    # Print first 2000 chars
    print('First 2000 chars:', file=sys.stderr)
    print(r.text[:2000], file=sys.stderr)
except Exception as e:
    print('Error:', e, file=sys.stderr)
    import traceback
    traceback.print_exc(file=sys.stderr)