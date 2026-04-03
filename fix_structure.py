#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fix non-admin section structure: move content divs inside v-else"""

with open(r'C:\Users\wb.liujing23\Desktop\talent-management-web\templates\index.html', encoding='utf-8') as f:
    content = f.read()

# Find the non-admin section
idx_start = content.find('<!-- 普通用户视图 -->')
idx_end = content.find('<!-- 人才列表 -->')
if idx_start < 0 or idx_end < 0:
    print('ERROR: markers not found')
    import sys
    sys.exit(1)

section = content[idx_start:idx_end]
print(f'Non-admin section: {len(section)} chars')

# The non-admin section currently has:
# <!-- 普通用户视图 -->
# <div v-else>
#     <div class="tabs">
#         buttons...
#     </div>
# </div>    <- v-else closes here
#
# <!-- 普通用户内容：报名信息 -->
# <div v-if="activeTab === 'register'">...
# <!-- 普通用户内容：查询状态 -->
# <div v-if="activeTab === 'mystatus'">...

# We need to change it to:
# <!-- 普通用户视图 -->
# <div v-else>
#     <div class="tabs">
#         buttons...
#     </div>
#
#     <!-- 普通用户内容：报名信息 -->
#     <div v-if="activeTab === 'register'">...
#     <!-- 普通用户内容：查询状态 -->
#     <div v-if="activeTab === 'mystatus'">...
# </div>

# Find where the v-else </div> is - it's right after the tabs </div>
# The pattern is: tabs </div> then a blank line then </div> (v-else close)
old_section = '''<!-- 普通用户视图 -->

            <div v-else>

                <div class="tabs">

                    <button class="tab" :class="{ active: activeTab === 'register' }" @click="activeTab = 'register'">报名信息</button>

                    <button class="tab" :class="{ active: activeTab === 'mystatus' }" @click="activeTab = 'mystatus'">查询状态</button>


                </div>

            </div>


            <!-- 普通用户内容'''

new_section = '''<!-- 普通用户视图 -->

            <div v-else>

                <div class="tabs">

                    <button class="tab" :class="{ active: activeTab === 'register' }" @click="activeTab = 'register'; loadDemandInfo()">报名信息</button>

                    <button class="tab" :class="{ active: activeTab === 'mystatus' }" @click="activeTab = 'mystatus'; loadDemandInfo()">查询状态</button>


                </div>


            <!-- 普通用户内容'''

if old_section in content:
    content = content.replace(old_section, new_section, 1)
    print('Fixed non-admin section structure')
else:
    print('ERROR: old_section not found')
    import sys
    sys.exit(1)

# Now we need to add a closing </div> for the v-else AFTER all content sections
# Find where <!-- 人才列表 --> section starts
idx_talist = content.find('<!-- 人才列表 -->')
# The content before <!-- 人才列表 --> ends with: </div>\n\n\n            <!-- 普通用户内容... --> (ending of last content div)
# We need to insert </div> just before <!-- 人才列表 -->

# Find the end of mystatus section
mystatus_end = content.find('<!-- 人才列表 -->')
if mystatus_end > 0:
    # Go backwards from <!-- 人才列表 to find the </div> that closes mystatus
    before = content[:mystatus_end]
    # The last occurrence of </div> followed by blank lines before <!-- 人才列表
    last_div = before.rfind('</div>')
    print(f'Last </div> before 人才列表 at {last_div}')
    print('Context:', repr(content[last_div:last_div+50]))
    
    # Insert </div> for v-else closing
    new_close = content[:last_div] + '</div>\n\n\n            ' + content[last_div:]
    content = new_close
    print('Added v-else closing </div>')
else:
    print('ERROR: 人才列表 marker not found')

with open(r'C:\Users\wb.liujing23\Desktop\talent-management-web\templates\index.html', 'w', encoding='utf-8') as f:
    f.write(content)
print('Saved')
