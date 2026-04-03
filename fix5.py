#!/usr/bin/env python3
c = open(r'C:\Users\wb.liujing23\Desktop\talent-management-web\templates\index.html', encoding='utf-8').read()

# Find the non-admin section: from <!-- 普通用户视图 --> to <!-- 人才列表 -->
idx_start = c.find('普通用户视图 -->')
idx_end = c.find('<!-- 人才列表 -->')
section = c[idx_start:idx_end]
print(f'Non-admin section: {len(section)} chars')

# Count opening and closing divs
open_div = section.count('<div')
close_div = section.count('</div>')
print(f'Opening divs: {open_div}, Closing divs: {close_div}')

# Find the v-else closing div
import re
v_else_matches = list(re.finditer(r'<div v-else>', section))
print(f'v-else open count: {len(v_else_matches)}')

# Find the v-else closing 
v_else_close = section.rfind('</div>')
print(f'Last </div> at offset {v_else_close}')
print('Last 200 chars:', repr(section[v_else_close-100:]))

# Show where the mystatus div ends
mystatus_end = section.rfind('</div>', 0, v_else_close)
print(f'Last </div> before v-else close: {mystatus_end}')
print(repr(section[mystatus_end-100:mystatus_end+20]))
