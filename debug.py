#!/usr/bin/env python3
c = open(r'C:\Users\wb.liujing23\Desktop\talent-management-web\templates\index.html', encoding='utf-8').read()

# Find full non-admin section
idx_start = c.find('普通用户视图 -->')
idx_end = c.find('<!-- 人才列表 -->')
if idx_start > 0 and idx_end > 0:
    section = c[idx_start:idx_end]
    print(f'Non-admin section: {len(section)} chars')
    print(repr(section[:800]))
    print('...')
    print(repr(section[-200:]))
