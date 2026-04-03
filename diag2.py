#!/usr/bin/env python3
c = open(r'C:\Users\wb.liujing23\Desktop\talent-management-web\templates\index.html', encoding='utf-8').read()

# Check the non-admin section HTML structure near the tabs
idx = c.find('普通用户视图 -->')
chunk = c[idx:idx+500]
print('Non-admin section structure:')
# Count the structure
lines = chunk.split('\n')
for i, line in enumerate(lines[:25]):
    print(f'{i+1}: {line[:100]}')
