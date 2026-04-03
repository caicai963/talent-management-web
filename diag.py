#!/usr/bin/env python3
c = open(r'C:\Users\wb.liujing23\Desktop\talent-management-web\templates\index.html', encoding='utf-8').read()

# Find loadDemandInfo function and check for issues
idx = c.find('const loadDemandInfo = async')
if idx > 0:
    print('loadDemandInfo function:')
    print(c[idx:idx+600])
else:
    print('loadDemandInfo NOT found')

# Check if register section v-if is properly formed
idx2 = c.find('v-if="activeTab === \'register\'">')
print()
print('register v-if at:', idx2)
if idx2 > 0:
    print(repr(c[idx2-20:idx2+100]))
