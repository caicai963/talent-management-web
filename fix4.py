#!/usr/bin/env python3
c = open(r'C:\Users\wb.liujing23\Desktop\talent-management-web\templates\index.html', encoding='utf-8').read()

# Find where non-admin section ends (before 人才列表)
idx_end = c.find('<!-- 人才列表 -->')
if idx_end < 0:
    print('ERROR: 人才列表 not found')
else:
    # Get 200 chars before it
    print('Before 人才列表:')
    print(repr(c[idx_end-200:idx_end+30]))

# Also find the non-admin tabs closing div
idx_tabs = c.find('普通用户视图 -->')
chunk = c[idx_tabs:idx_tabs+400]
print()
print('Tabs and after:')
print(repr(chunk))
