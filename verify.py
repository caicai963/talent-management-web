#!/usr/bin/env python3
c = open(r'C:\Users\wb.liujing23\Desktop\talent-management-web\templates\index.html', encoding='utf-8').read()
print('v-else open count:', c.count('<div v-else>'))
idx = c.find('普通用户视图')
chunk = c[idx:idx+400]
print('Non-admin structure:')
print(repr(chunk[:300]))
