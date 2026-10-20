import os
import sys
import logging

logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')

sys.path.insert(0, r'\\zimaserver\ZimaOS-HD\AppData\Projects\dispo-deals')

from config import Config
from models import StoreConfig
from scrapers.dutchie import DutchieScraper

# Load config from file
config = Config.load("config.yaml")

store = config.get_store("culture-akron")
if not store:
    print("Store not found")
    exit(1)

print(f"Testing scraper for: {store.name}")
print(f"URL: {store.url}")

scraper = DutchieScraper(store, config)

# Test GraphQL
print("\n=== Testing GraphQL ===")
deals = scraper._try_graphql()
print(f"GraphQL found {len(deals)} deals")

# Test page extraction
print("\n=== Testing Page Extraction ===")
deals = scraper._extract_from_page()
print(f"Page extraction found {len(deals)} deals")

# Test DOM extraction
print("\n=== Testing DOM Extraction ===")
deals = scraper._extract_from_rendered_dom()
print(f"DOM extraction found {len(deals)} deals")
for deal in deals[:10]:
    print(f"  - {deal.name}: ${deal.sale_price}/${deal.original_price} ({deal.discount_pct}% off) [{deal.category}]")