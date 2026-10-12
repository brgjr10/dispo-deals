import cloudscraper
import json

scraper = cloudscraper.create_scraper(browser='chrome')

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json',
    'Content-Type': 'application/json',
}

# Simple introspection
introspection = '''
query {
  __schema {
    queryType { name }
  }
}
'''

r = scraper.post('https://dutchie.com/graphql', json={'query': introspection}, headers=headers, timeout=30)
print('Status:', r.status_code)
print(r.text[:1000])