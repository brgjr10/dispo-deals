import cloudscraper
import re
import json

scraper = cloudscraper.create_scraper(browser='chrome')
url = 'https://dutchie.com/stores/culture-cannabis-club-akron'
r = scraper.get(url, timeout=30)
print(f'Status: {r.status_code}')

# Check for any JSON data in script tags
scripts = re.findall(r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>', r.text, re.DOTALL)
print(f"\nFound {len(scripts)} JSON script tags")
for i, script in enumerate(scripts[:5]):
    try:
        data = json.loads(script)
        print(f"Script {i}: {json.dumps(data, indent=2)[:500]}")
    except:
        print(f"Script {i}: Not valid JSON ({len(script)} chars)")

# Check for window.__INITIAL_STATE__ or similar
init_state = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?});', r.text, re.DOTALL)
if init_state:
    print("\nFound window.__INITIAL_STATE__")
    try:
        data = json.loads(init_state.group(1))
        print(json.dumps(data, indent=2)[:2000])
    except:
        print("Failed to parse")

# Check for any product data in page
if 'product' in r.text.lower():
    print("\nPage contains 'product'")
    # Find context around product mentions
    for match in re.finditer(r'.{0,100}product.{0,100}', r.text, re.IGNORECASE):
        print(f"  ...{match.group()}...")
        break