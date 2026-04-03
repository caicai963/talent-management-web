#!/usr/bin/env python3
c = open(r'C:\Users\wb.liujing23\Desktop\talent-management-web\templates\index.html', encoding='utf-8').read()
idx = c.find('const registerForm')
print(repr(c[idx:idx+200]))
