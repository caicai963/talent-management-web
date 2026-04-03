#!/usr/bin/env python3
c = open(r'C:\Users\wb.liujing23\Desktop\talent-management-web\templates\index.html', encoding='utf-8').read()
# Find login form wrapper
idx = c.find('v-if="!isLoggedIn"')
if idx > 0:
    print(repr(c[idx-50:idx+400]))
