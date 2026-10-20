import cloudscraper
import re

scraper = cloudscraper.create_scraper(browser='chrome')
url = 'https://dutchie.com/stores/culture-cannabis-club-akron'
r = scraper.get(url, timeout=30)

# Search for GraphQL queries in the page
patterns = [
    r'query\s+\w+\s*\([^)]*\)\s*\{[^}]+\}',
    r'operationName["\']?\s*:\s*["\']([^"\']+)',
    r'query\s+(\w+)',
    r'menu\(',
    r'dispensary',
]

print("Searching for GraphQL queries in page...")
for pattern in patterns:
    matches = re.findall(pattern, r.text, re.IGNORECASE | re.DOTALL)
    if matches:
        print(f"\nPattern: {pattern}")
        for m in matches[:5]:
            print(f"  {m[:200]}")