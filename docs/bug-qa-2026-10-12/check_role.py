with open(r'F:\Documents\dispo-deals\dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

import re
# role=button - find all occurrences
count = 0
for m in re.finditer('role="button"', content):
    count += 1
    print('role=button at', m.start(), ':', content[m.start()-50:m.end()+100])
    print()
print('Total:', count)