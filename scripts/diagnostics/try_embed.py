import cloudscraper
import json

scraper = cloudscraper.create_scraper(browser='chrome')

# Try the embed menu
url = 'https://dutchie.com/embed/menu/culture-cannabis-club-akron'
r = scraper.get(url, timeout=30)
print('Embed Status:', r.status_code)
print('Length:', len(r.text))

# Check for JSON data in the embed
import re
scripts = re.findall(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', r.text, re.DOTALL)
print('JSON scripts:', len(scripts))
for i, s in enumerate(scripts[:5]):
    print(f'Script {i}: {s[:300]}')