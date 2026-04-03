#!/usr/bin/env python3
c = open(r'C:\Users\wb.liujing23\Desktop\talent-management-web\templates\index.html', encoding='utf-8').read()

idx_start = c.find('普通用户视图 -->')
idx_end = c.find('<!-- 人才列表 -->')
section = c[idx_start:idx_end]

# Show the last 500 chars before 人才列表
print('Last 500 chars of non-admin section:')
print(repr(section[-500:]))
