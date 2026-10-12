import cloudscraper
from bs4 import BeautifulSoup

scraper = cloudscraper.create_scraper(browser='chrome')

base_url = 'https://www.klutchcannabis.com'
r = scraper.get(base_url, timeout=30)
print(f'Homepage: Status {r.status_code}')

soup = BeautifulSoup(r.content, 'html.parser')

# Find all links
links = soup.find_all('a', href=True)
collection_links = [l for l in links if '/collections/' in l.get('href', '')]
print(f'\nFound {len(collection_links)} collection links:')
for link in collection_links[:20]:
    print(f'  {link.get("href")} - {link.get_text(strip=True)[:50]}')

# Also check navigation/menu
nav = soup.find('nav')
if nav:
    nav_links = nav.find_all('a', href=True)
    print(f'\nNav links:')
    for link in nav_links[:20]:
        print(f'  {link.get("href")} - {link.get_text(strip=True)[:50]}')