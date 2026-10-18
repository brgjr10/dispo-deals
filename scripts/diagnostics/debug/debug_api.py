import cloudscraper
import re

scraper = cloudscraper.create_scraper(browser='chrome')
url = 'https://dutchie.com/stores/culture-cannabis-club-akron'
r = scraper.get(url, timeout=30)

# Search for API endpoints in the page
patterns = [
    r'"/api/[^"]+"',
    r"'/api/[^']+'",
    r'fetch\(["\']([^"\']+)',
    r'axios\.[getpost]+\(["\']([^"\']+)',
    r'graphql',
    r'GraphQL',
    r'/graphql',
    r'menu',
    r'dispensary',
]

for pattern in patterns:
    matches = re.findall(pattern, r.text, re.IGNORECASE)
    if matches:
        unique = list(set(matches))
        print(f"\nPattern: {pattern}")
        for m in unique[:10]:
            print(f"  {m}")