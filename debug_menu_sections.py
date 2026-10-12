import cloudscraper
import json
import re

scraper = cloudscraper.create_scraper(browser='chrome')
url = 'https://dutchie.com/stores/culture-cannabis-club-akron'
r = scraper.get(url, timeout=30)

next_data_match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.DOTALL)
if next_data_match:
    data = json.loads(next_data_match.group(1))
    apollo_state = data.get('props', {}).get('pageProps', {}).get('initialApolloState', {})
    
    # Check menuSections
    disp = apollo_state.get('Dispensaries:64bac95faf74b00009287438', {})
    menu_sections = disp.get('menuSections', [])
    print(f"menuSections: {menu_sections}")
    
    # Check embeddedMenuUrl
    embedded_url = disp.get('embeddedMenuUrl')
    print(f"\nembeddedMenuUrl: {embedded_url}")
    
    # Check menuUrl
    menu_url = disp.get('menuUrl')
    print(f"menuUrl: {menu_url}")