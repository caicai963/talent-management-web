#!/usr/bin/env python3
c = open(r'C:\Users\wb.liujing23\Desktop\talent-management-web\templates\index.html', encoding='utf-8').read()

# Find the non-admin tabs and content area
idx = c.find('普通用户视图 -->')
if idx < 0:
    print('Non-admin section not found')
else:
    chunk = c[idx:idx+800]
    print('Non-admin structure:')
    print(repr(chunk[:600]))
    print('...')
    print(repr(chunk[-200:]))
