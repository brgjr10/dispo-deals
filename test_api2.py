import urllib.request
import json
import threading
import time
import sys
sys.path.insert(0, '.')

from api_server import DashboardHandler
from http.server import HTTPServer

def run_server():
    server = HTTPServer(('', 8081), DashboardHandler)
    server.serve_forever()

t = threading.Thread(target=run_server, daemon=True)
t.start()
time.sleep(1)

try:
    with urllib.request.urlopen('http://localhost:8081/api/data') as resp:
        data = json.load(resp)
        print('Stores:', len(data['stores']))
        for s in data['stores']:
            print('  {}: {}'.format(s['id'], s['name']))
        print('Deals:', len(data['deals']))
        for d in data['deals'][:3]:
            img = d.get('image_url', 'N/A')
            if len(img) > 50:
                img = img[:50] + '...'
            print('  {}: {} | {} | ${:.2f} | {:.1f}% | img: {}'.format(d['store_id'], d['name'], d['category'], d['sale_price'], d['discount_pct'], img))
except Exception as e:
    print('Error:', e)