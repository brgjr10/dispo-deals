import sys
sys.path.insert(0, r'F:\Documents\dispo-deals')
import storage.sqlite as sql_module
import inspect
import re

source = inspect.getsource(sql_module)
print('=== Checking for string concatenation in SQL ===')
for i, line in enumerate(source.split('\n'), 1):
    if 'execute' in line and ('f"' in line or '+ "' in line or '" +' in line or '%' in line):
        # Check if it's using parameterized queries properly
        if '?' in line or '(' in line:
            continue
        print(f'Line {i}: {line.strip()}')