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

# Try different query names
queries = [
    # Try "dispensaryMenu"
    '''
    query GetMenu($dispensarySlug: String!) {
        dispensaryMenu(dispensarySlug: $dispensarySlug) {
            id
            categories {
                name
                products {
                    id
                    name
                    brand { name }
                    category
                    pricing { price originalPrice discount }
                    images { url thumbnailUrl }
                    url
                    thc
                    cbd
                    weight
                    inStock
                }
            }
        }
    }
    ''',
    # Try "dispensary" with menu
    '''
    query GetDispensary($slug: String!) {
        dispensary(slug: $slug) {
            id
            name
            slug
            menu {
                categories {
                    name
                    products {
                        id
                        name
                        brand { name }
                        category
                        pricing { price originalPrice discount }
                        images { url thumbnailUrl }
                        url
                        thc
                        cbd
                        weight
                        inStock
                    }
                }
            }
        }
    }
    ''',
    # Try "store" 
    '''
    query GetStore($slug: String!) {
        store(slug: $slug) {
            id
            name
            slug
            menu {
                categories {
                    name
                    products {
                        id
                        name
                        brand { name }
                        category
                        pricing { price originalPrice discount }
                        images { url thumbnailUrl }
                        url
                        thc
                        cbd
                        weight
                        inStock
                    }
                }
            }
        }
    }
    ''',
]

for i, query in enumerate(queries):
    payload = {"query": query, "variables": {"dispensarySlug": "culture-cannabis-club-akron", "slug": "culture-cannabis-club-akron"}}
    r = scraper.post('https://dutchie.com/graphql', json=payload, headers=headers, timeout=30)
    print(f"\n=== Query {i+1} ===")
    print(f"Status: {r.status_code}")
    print(r.text[:2000])