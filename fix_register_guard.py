#!/usr/bin/env python3
c = open(r'C:\Users\wb.liujing23\Desktop\talent-management-web\templates\index.html', encoding='utf-8').read()
old = '<div v-if="activeTab === \'register\'" style="max-width: 600px;'
new = '<div v-if="activeTab === \'register\' && registerDemandId" style="max-width: 600px;'
if old in c:
    c = c.replace(old, new, 1)
    open(r'C:\Users\wb.liujing23\Desktop\talent-management-web\templates\index.html', 'w', encoding='utf-8').write(c)
    print('SUCCESS: Fixed register form v-if guard')
else:
    print('ERROR: Pattern not found')
    print('Looking for:', repr(old[:80]))
