import requests
from bs4 import BeautifulSoup

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

url = 'https://dutchie.com/stores/culture-cannabis-club-akron'
r = requests.get(url, headers=headers, timeout=30)
print('Status:', r.status_code)
print('Length:', len(r.text))

# Look for embedded data
soup = BeautifulSoup(r.text, 'html.parser')

# Check for script tags with data
scripts = soup.find_all('script', type='application/json')
print('JSON scripts:', len(scripts))
for i, s in enumerate(scripts[:5]):
    print(f'Script {i}: {s.get_text()[:200]}')

# Check for next.js data
scripts2 = soup.find_all('script', id=lambda x: x and 'NEXT_DATA' in x)
print('NEXT_DATA scripts:', len(scripts2))
for s in scripts2:
    print(s.get_text()[:500])