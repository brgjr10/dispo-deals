with open('config.yaml', 'r', encoding='utf-8') as f:
    content = f.read()
print('Has em dash:', '\u2014' in content)
print('Has replacement:', '\ufffd' in content)
import re
names = re.findall(r'name: "([^"]+)"', content)
for n in names:
    print(repr(n))