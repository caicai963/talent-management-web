#!/usr/bin/env python3
c = open(r'C:\Users\wb.liujing23\Desktop\talent-management-web\templates\index.html', encoding='utf-8').read()

# Find non-admin section start and end
idx_start = c.find('普通用户视图 -->')
idx_end = c.find('<!-- 人才列表 -->')
section = c[idx_start:idx_end]

# Find the admin-wrapper closing div
# It has 8 spaces indentation: '\n            </div>'
admin_close_marker = '\n            </div>'
admin_close_pos = section.rfind(admin_close_marker)
print(f'Admin-wrapper closing </div> at offset {admin_close_pos}')

# Find the v-else closing div
# It has 12 spaces indentation: '\n            </div>'
# Actually v-else closing is at 12 spaces: '\n            </div>'
# But that's same pattern as admin... Let me find differently
# Look at the raw bytes
last_chunk = section[admin_close_pos:]

import re
# Find all occurrences of </div> in the last chunk
divs = [(m.start(), m.group()) for m in re.finditer(r'</div>', last_chunk)]
print('Closing </div> in last chunk:')
for pos, tag in divs:
    # Show context (20 chars before)
    ctx = last_chunk[pos-20:pos+10]
    print(f'  offset {pos}: {repr(ctx)}')

# The second-to-last </div> should be v-else closing
if len(divs) >= 2:
    v_else_close = divs[-2][0]
    print(f'v-else closing at offset {v_else_close} from section start = {admin_close_pos + v_else_close}')
    print('Context:', repr(last_chunk[v_else_close-20:v_else_close+30]))
