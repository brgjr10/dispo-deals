import cloudscraper
import json
import re

scraper = cloudscraper.create_scraper(browser='chrome')
url = 'https://dutchie.com/stores/culture-cannabis-club-akron'
r = scraper.get(url, timeout=30)

next_data_match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.DOTALL)
if next_data_match:
    data = json.loads(next_data_match.group(1))
    
    # Check pageProps for any menu data
    page_props = data.get('props', {}).get('pageProps', {})
    print("pageProps keys:")
    for key in page_props.keys():
        val = page_props[key]
        if isinstance(val, dict):
            print(f"  {key}: dict with keys {list(val.keys())[:10]}")
        elif isinstance(val, list):
            print(f"  {key}: list of {len(val)} items")
        else:
            print(f"  {key}: {type(val).__name__}")
    
    # Check for any menu-related data
    print("\n--- Searching for menu in pageProps ---")
    def find_menu(obj, path=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if 'menu' in k.lower() or 'product' in k.lower() or 'category' in k.lower():
                    print(f"  {path}.{k}: {type(v).__name__}")
                    if isinstance(v, (dict, list)) and len(str(v)) < 500:
                        print(f"    Value: {v}")
                find_menu(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                find_menu(v, f"{path}[{i}]")
    
    find_menu(page_props)