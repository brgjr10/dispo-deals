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
        print('Deals:', len(data['deals']))
        print('WeeklyDiff:', data['weeklyDiff'] is not None)
        if data['weeklyDiff']:
            print('  New:', data['weeklyDiff']['new_count'])
            print('  Carryover:', data['weeklyDiff']['carryover_count'])
            print('  Removed:', data['weeklyDiff']['removed_count'])
        for d in data['deals'][:3]:
            print('  {}: {} | {} | ${:.2f} | {:.1f}%'.format(d['store_id'], d['name'], d['category'], d['sale_price'], d['discount_pct']))
except Exception as e:
    print('Error:', e)