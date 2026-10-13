with open(r'F:\Documents\dispo-deals\dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

import re

# Check for onclick on non-button elements
onclick_elements = re.findall(r'<[^>]+onclick=[^>]*>', content)
print('=== Elements with onclick ===')
for el in onclick_elements:
    tag = re.match(r'<(\w+)', el)
    if tag and tag.group(1) not in ['button', 'a']:
        print(f'  {tag.group(1)}: {el[:100]}')

# Check for role=button without keyboard support
role_button = re.findall(r'role="button"[^>]*>', content)
print(f'\nElements with role=button: {len(role_button)}')
for rb in role_button:
    if 'tabindex' not in rb and 'onkeydown' not in rb and 'onkeyup' not in rb:
        print(f'  Missing keyboard support: {rb[:100]}')

# Check for tabindex on clickable elements
clickable_with_tabindex = re.findall(r'<[^>]+onclick=[^>]*tabindex=[^>]*>', content)
print(f'\nClickable with tabindex: {len(clickable_with_tabindex)}')

# Check product cards - they seem to be clickable divs
product_card_clickable = re.findall(r'class="product-card[^"]*"[^>]*onclick', content)
print(f'Product cards with onclick: {len(product_card_clickable)}')

# Check product card definition
for m in re.finditer(r'class="product-card[^"]*"', content):
    start = max(0, m.start() - 50)
    end = min(len(content), m.end() + 200)
    print(f'Product card class: {content[start:end]}')
    break