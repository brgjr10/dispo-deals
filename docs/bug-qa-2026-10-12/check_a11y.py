with open(r'F:\Documents\dispo-deals\dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

import re
# Check for role=application
matches = list(re.finditer('role="application"', content))
print('role=application:', len(matches))

# Check for tabindex without role
matches = list(re.finditer('tabindex=', content))
print('tabindex count:', len(matches))
for m in matches[:5]:
    print('  At', m.start(), ':', content[m.start()-30:m.end()+50])