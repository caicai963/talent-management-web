#!/usr/bin/env python3
c = open(r'C:\Users\wb.liujing23\Desktop\talent-management-web\templates\index.html', encoding='utf-8').read()

old_return = """            activeTab,
            currentView,
            isAdmin,
            demands,
            selectedDemand,
            showDemandForm,
            editingDemand,
            editingDemandId,
            showAppFormModal,
            selectedApplication,
            stats,"""

new_return = """            activeTab,
            currentView,
            isAdmin,
            registerForm,
            registerMessage,
            statusPhone,
            statusResult,
            statusChecked,
            currentDemand,
            registerDemandId,
            demands,
            selectedDemand,
            showDemandForm,
            editingDemand,
            editingDemandId,
            showAppFormModal,
            selectedApplication,
            stats,"""

if old_return in c:
    c = c.replace(old_return, new_return, 1)
    print('Fixed return block')
    with open(r'C:\Users\wb.liujing23\Desktop\talent-management-web\templates\index.html', 'w', encoding='utf-8') as f:
        f.write(c)
    print('Saved')
else:
    print('ERROR: return block pattern not found')
