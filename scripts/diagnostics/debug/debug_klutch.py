import cloudscraper

scraper = cloudscraper.create_scraper(browser='chrome')

base_url = 'https://www.klutchcannabis.com'
categories = ['flower', 'pre-rolls', 'edibles', 'concentrates', 'vapes', 'topicals']

for cat in categories:
    url = f'{base_url}/collections/{cat}'
    r = scraper.get(url, timeout=30)
    print(f'{cat}: Status {r.status_code}')
    if r.status_code == 200:
        # Check if it has product data
        if 'product' in r.text.lower():
            print(f'  -> Has product data')
        else:
            print(f'  -> No product data found')
    else:
        # Try to find what page it redirects to
        print(f'  -> Redirect/Error')