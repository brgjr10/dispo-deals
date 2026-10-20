import os
import sys
import logging
import re
import json

logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')

sys.path.insert(0, r'\\zimaserver\ZimaOS-HD\AppData\Projects\dispo-deals')

import cloudscraper
from bs4 import BeautifulSoup

scraper = cloudscraper.create_scraper(browser='chrome')
url = 'https://dutchie.com/stores/culture-cannabis-club-akron'
r = scraper.get(url, timeout=30)
print(f'Status: {r.status_code}')

soup = BeautifulSoup(r.content, "html.parser")

# Check for product cards with various selectors
selectors = [
    "[data-testid='product-card']",
    "[data-testid='product-tile']",
    ".product-card",
    ".product-tile",
    "[data-product-id]",
    "article.product-item",
    ".menu-product",
    ".product-item",
    "[role='listitem']",
]

for selector in selectors:
    cards = soup.select(selector)
    print(f"\nSelector: {selector} -> {len(cards)} matches")
    if cards:
        for card in cards[:3]:
            print(f"  HTML: {str(card)[:200]}")

# Also check for any element with product-related data attributes
print("\n=== Elements with data-product-id ===")
cards = soup.find_all(attrs={"data-product-id": True})
print(f"Found: {len(cards)}")
for card in cards[:3]:
    print(f"  HTML: {str(card)[:200]}")

# Check for product links
print("\n=== Product links ===")
links = soup.find_all('a', href=re.compile(r'/product'))
print(f"Found: {len(links)}")
for link in links[:10]:
    print(f"  {link.get('href')} - {link.get_text(strip=True)[:50]}")