#!/usr/bin/env python3
c = open(r'C:\Users\wb.liujing23\Desktop\talent-management-web\templates\index.html', encoding='utf-8').read()
idx = c.find("activeTab === 'register'")
if idx > 0:
    print(repr(c[idx-30:idx+80]))
