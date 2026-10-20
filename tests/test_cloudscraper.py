import cloudscraper

scraper = cloudscraper.create_scraper(browser='chrome')

url = 'https://dutchie.com/stores/culture-cannabis-club-akron'
r = scraper.get(url, timeout=30)
print('Status:', r.status_code)
print('Length:', len(r.text))

# Check for embedded data
if 'products' in r.text.lower() or 'menu' in r.text.lower():
    print('Found product/menu data in response')
    
# Look for JSON data in scripts
import re
scripts = re.findall(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', r.text, re.DOTALL)
print('JSON scripts:', len(scripts))
for i, s in enumerate(scripts[:3]):
    print(f'Script {i}: {s[:300]}')

# Check for NEXT_DATA
next_data = re.findall(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.DOTALL)
print('NEXT_DATA scripts:', len(next_data))
for s in next_data:
    print(f'NEXT_DATA: {s[:500]}')