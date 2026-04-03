#!/usr/bin/env python3
c = open(r'C:\Users\wb.liujing23\Desktop\talent-management-web\templates\index.html', encoding='utf-8').read()

# 1. Remove loadDemandInfo from register tab click to prevent JS errors
old1 = "activeTab.value = 'register'; loadDemandInfo()"
new1 = "activeTab.value = 'register'"
if old1 in c:
    c = c.replace(old1, new1, 1)
    print('Removed loadDemandInfo from register tab click')
else:
    print('loadDemandInfo in tab click: not found')

# 2. Add try-catch to loadDemandInfo to prevent Vue crash
old2 = """const loadDemandInfo = async () => {
                    const params = new URLSearchParams(window.location.search);
                    const demandId = params.get('demand_id');
                    if (!demandId) {
                        currentDemand.value = null;
                        registerDemandId.value = null;
                        return;
                    }
                    registerDemandId.value = demandId;
                    try {
                        const res = await api.get('/api/demands/' + demandId + '/public');
                        currentDemand.value = res.data;
                    } catch (e) {
                        console.error(e);
                    }
                };"""
new2 = """const loadDemandInfo = async () => {
                    try {
                        const params = new URLSearchParams(window.location.search);
                        const demandId = params.get('demand_id');
                        registerDemandId.value = demandId || null;
                        if (!demandId) {
                            currentDemand.value = null;
                            return;
                        }
                        const res = await api.get('/api/demands/' + demandId + '/public');
                        currentDemand.value = res.data;
                    } catch (e) {
                        currentDemand.value = { title: '加载失败' };
                    }
                };"""

if old2 in c:
    c = c.replace(old2, new2, 1)
    print('Fixed loadDemandInfo try-catch')
else:
    print('loadDemandInfo function pattern: not found')

# 3. Also check the register section HTML - make sure it's complete
# The issue might be that the div structure is wrong
# Let me check if the non-admin content divs are properly placed
old3 = """<!-- 普通用户视图 -->

            <div v-else>

                <div class="tabs">

                    <button class="tab" :class="{ active: activeTab === 'register' }" @click="activeTab.value = 'register'">报名信息</button>

                    <button class="tab" :class="{ active: activeTab === 'mystatus' }" @click="activeTab.value = 'mystatus'">查询状态</button>


                </div>


            <!-- 普通用户内容"""

new3 = """<!-- 普通用户视图 -->

            <div v-else>

                <div class="tabs">

                    <button class="tab" :class="{ active: activeTab === 'register' }" @click="activeTab = 'register'; loadDemandInfo()">报名信息</button>

                    <button class="tab" :class="{ active: activeTab === 'mystatus' }" @click="activeTab = 'mystatus'; loadDemandInfo()">查询状态</button>


                </div>


            <!-- 普通用户内容"""

if old3 in c:
    c = c.replace(old3, new3, 1)
    print('Fixed non-admin tabs with loadDemandInfo')
else:
    print('Non-admin tabs pattern: not found')

open(r'C:\Users\wb.liujing23\Desktop\talent-management-web\templates\index.html', 'w', encoding='utf-8').write(c)
print('Saved')
