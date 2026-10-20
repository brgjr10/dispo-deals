import threading, time, sys, json, urllib.request, re
sys.path.insert(0, '.')

from api_server import DashboardHandler
from http.server import HTTPServer

def run_server():
    server = HTTPServer(('', 8082), DashboardHandler)
    server.serve_forever()

t = threading.Thread(target=run_server, daemon=True)
t.start()
time.sleep(0.5)

# Test HTML serving
req = urllib.request.Request('http://localhost:8082/dashboard.html')
with urllib.request.urlopen(req) as resp:
    print('HTML Content-Type:', resp.headers.get('Content-Type'))
    html = resp.read().decode('utf-8')
    print('Has em dash:', '\u2014' in html)
    names = re.findall(r'store-name">([^<]+)', html)
    for n in names[:4]:
        print('  Store:', repr(n))