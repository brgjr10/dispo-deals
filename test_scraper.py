import os
import sys
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
print("Fetching menu...")
deals = scraper.fetch_menu()
print(f"Found {len(deals)} deals")
for deal in deals[:10]:
    print(f"  - {deal.name}: ${deal.sale_price}/${deal.original_price} ({deal.discount_pct}% off) [{deal.category}]")
if len(deals) > 10:
    print(f"  ... and {len(deals) - 10} more")