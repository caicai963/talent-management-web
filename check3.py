#!/usr/bin/env python3
c = open(r'C:\Users\wb.liujing23\Desktop\talent-management-web\templates\index.html', encoding='utf-8').read()

# Find the registerForm ref
idx = c.find('registerForm')
positions = []
import re
for m in re.finditer(r'registerForm', c):
    positions.append(m.start())
print('registerForm positions:', positions)
for pos in positions[:3]:
    print(repr(c[pos-20:pos+60]))
print()

# Find the submitRegistration method
idx2 = c.find('submitRegistration')
print('submitRegistration at:', idx2)
if idx2 > 0:
    print(repr(c[idx2:idx2+200]))
print()

# Check if registerForm ref was added - look at activeTab ref area
idx3 = c.find("const activeTab = ref('list')")
print('activeTab ref at:', idx3)
if idx3 > 0:
    print(repr(c[idx3:idx3+300]))
