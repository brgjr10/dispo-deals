import cloudscraper
import re
import json
import sys

try:
    scraper = cloudscraper.create_scraper(browser='chrome')
    url = 'https://culturecannabisclub.com/stores/culture-cannabis-club-akron'
    r = scraper.get(url, timeout=30)
    print('Status:', r.status_code, file=sys.stderr)

    # Check for any script tags with data
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', r.text, re.DOTALL)
    for i, script in enumerate(scripts):
        if 'product' in script.lower() or 'menu' in script.lower() or 'shop' in script.lower():
            print(f'Script {i} (first 500 chars):', script[:500], file=sys.stderr)
            print('---', file=sys.stderr)
except Exception as e:
    print('Error:', e, file=sys.stderr)
    import traceback
    traceback.print_exc(file=sys.stderr)