import cloudscraper
import json

scraper = cloudscraper.create_scraper(browser='chrome')

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json',
    'Content-Type': 'application/json',
    'Origin': 'https://dutchie.com',
    'Referer': 'https://dutchie.com/stores/culture-cannabis-club-akron',
    'x-dutchie-client': 'web'
}

query = """
query Menu($dispensarySlug: String!, $filters: MenuFiltersInput) {
    menu(dispensarySlug: $dispensarySlug, filters: $filters) {
        id
        dispensary {
            id
            name
            slug
            logo {
                url
            }
        }
        categories {
            id
            name
            products {
                id
                name
                brand {
                    name
                }
                category
                pricing {
                    price
                    originalPrice
                    discount
                }
                images {
                    url
                    thumbnailUrl
                }
                url
                thc
                cbd
                weight
                inStock
            }
        }
    }
}
"""

payload = {"query": query, "variables": {"dispensarySlug": "culture-cannabis-club-akron", "filters": {}}}

r = scraper.post('https://dutchie.com/graphql', json=payload, headers=headers, timeout=30)
print('Status:', r.status_code)
print(r.text[:5000])