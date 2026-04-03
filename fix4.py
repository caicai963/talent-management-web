#!/usr/bin/env python3
c = open(r'C:\Users\wb.liujing23\Desktop\talent-management-web\templates\index.html', encoding='utf-8').read()

# Check admin section
idx = c.find('管理员视图')
if idx > 0:
    chunk = c[idx:idx+600]
    print('Admin section chunk:')
    print(repr(chunk))
