import requests

# Try the embed/widget API that Dutchie provides for menus
url = 'https://dutchie.com/embed/menu/culture-cannabis-club-akron'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
}
r = requests.get(url, headers=headers, timeout=30)
print('Embed Status:', r.status_code)
print(r.text[:2000])