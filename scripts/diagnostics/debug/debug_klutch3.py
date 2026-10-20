import cloudscraper
from bs4 import BeautifulSoup

scraper = cloudscraper.create_scraper(browser='chrome')

url = 'https://www.klutchcannabis.com/strains/'
r = scraper.get(url, timeout=30)
print(f'Strains: Status {r.status_code}')

soup = BeautifulSoup(r.content, 'html.parser')

# Find all links
links = soup.find_all('a', href=True)
strain_links = [l for l in links if '/strains/' in l.get('href', '') and l.get('href') != '/strains/']
print(f'\nFound {len(strain_links)} strain links:')
for link in strain_links[:30]:
    print(f'  {link.get("href")} - {link.get_text(strip=True)[:50]}')

# Check for product cards
product_cards = soup.select("div.product-card, article.product-item, div.grid-view-item, li.product-item, [data-product-id], .product-item, .product-card")
print(f'\nProduct cards found: {len(product_cards)}')