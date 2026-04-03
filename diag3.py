#!/usr/bin/env python3
c = open(r'C:\Users\wb.liujing23\Desktop\talent-management-web\templates\index.html', encoding='utf-8').read()

# Find the non-admin section boundaries
idx_start = c.find('普通用户视图 -->')
idx_end = c.find('<!-- 人才列表 -->')
section = c[idx_start:idx_end]
print(f'Non-admin section: {len(section)} chars')

# Show content around the transition from tabs to content
# The tabs close with </div> then there should be the v-else closing </div>
# then the content divs start
transition = section.find('</div>')
chunk = section[transition:transition+300]
print('After first </div>:')
print(repr(chunk[:200]))
