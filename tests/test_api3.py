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
    req = urllib.request.Request('http://localhost:8081/api/data')
    req.add_header('Accept', 'application/json; charset=utf-8')
    with urllib.request.urlopen(req) as resp:
        raw = resp.read()
        print('Raw bytes:', raw[:200])
        data = json.loads(raw.decode('utf-8'))
        print('Stores:', len(data['stores']))
        for s in data['stores']:
            print('  {}: {}'.format(s['id'], s['name']))
except Exception as e:
    print('Error:', e)
    import traceback
    traceback.print_exc()