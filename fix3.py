#!/usr/bin/env python3
c = open(r'C:\Users\wb.liujing23\Desktop\talent-management-web\templates\index.html', encoding='utf-8').read()

# Find the activeTab ref in the JS section
old = "const activeTab = ref('list');\n\n                const stats = ref({});"
new = """const activeTab = ref('list');

                // 普通用户报名相关
                const registerForm = ref({ name: '', phone: '', available_time: '', game_experience: '' });
                const registerMessage = ref('');
                const statusPhone = ref('');
                const statusResult = ref(null);
                const statusChecked = ref(false);

                const stats = ref({});"""

if old in c:
    c = c.replace(old, new, 1)
    print('Added Vue refs successfully')
else:
    print('ERROR: Could not find activeTab ref location')
    # Try alternative
    old2 = "const activeTab = ref('list');"
    if old2 in c:
        count = c.count(old2)
        print(f'Found {count} occurrences of activeTab ref')
        # Find the one in JS section (not in HTML)
        idx = c.find(old2)
        print(f'First at {idx}')
        print(repr(c[idx:idx+80]))

# Now add the Vue methods - find loadStats and add before it
old_methods = "const loadStats = async () => {"
new_methods = """const submitRegistration = async () => {
                    try {
                        const res = await api.post('/api/talents/register', registerForm.value);
                        registerMessage.value = res.data.message || '提交成功';
                        registerForm.value = { name: '', phone: '', available_time: '', game_experience: '' };
                        setTimeout(() => { registerMessage.value = ''; }, 3000);
                    } catch (e) {
                        registerMessage.value = '提交失败: ' + (e.response?.data?.error || e.message);
                    }
                };

                const checkMyStatus = async () => {
                    if (!statusPhone.value.trim()) {
                        alert('请输入手机号');
                        return;
                    }
                    try {
                        const res = await api.get('/api/talents/register/status', {
                            params: { phone: statusPhone.value.trim() }
                        });
                        statusResult.value = res.data;
                        statusChecked.value = true;
                    } catch (e) {
                        statusResult.value = { name: '查询失败', status: '请稍后重试' };
                        statusChecked.value = true;
                    }
                };

                const loadStats = async () => {"""

if 'const submitRegistration = async ()' not in c:
    if old_methods in c:
        c = c.replace(old_methods, new_methods, 1)
        print('Added Vue methods successfully')
    else:
        print('ERROR: Could not find loadStats location')
else:
    print('Vue methods already exist')

# Also fix demands tab for non-admin - remove demands from non-admin tabs
# Currently non-admin has: 报名信息, 查询状态, 需求管理
# Should remove 需求管理
old_nonadmin_tabs = """<button class="tab" :class="{ active: activeTab === 'demands' }" @click="activeTab = 'demands'; loadDemands()">需求管理</button>
                </div>
            </div>"""
new_nonadmin_tabs = """</div>
            </div>"""
if old_nonadmin_tabs in c:
    c = c.replace(old_nonadmin_tabs, new_nonadmin_tabs, 1)
    print('Removed 需求管理 from non-admin tabs')
else:
    print('Non-admin tabs pattern not found, trying simpler approach')
    # Just remove the demands button from non-admin section
    idx = c.find('普通用户视图')
    if idx > 0:
        # Find the demands button in non-admin section
        chunk = c[idx:idx+500]
        demands_idx = chunk.find("activeTab === 'demands'")
        if demands_idx > 0:
            print('Found demands button in non-admin at offset', demands_idx)
        else:
            print('demands button NOT in non-admin section')

open(r'C:\Users\wb.liujing23\Desktop\talent-management-web\templates\index.html', 'w', encoding='utf-8').write(c)
print('File saved')
