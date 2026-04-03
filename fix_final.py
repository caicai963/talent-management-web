#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rewrite non-admin section cleanly"""

with open(r'C:\Users\wb.liujing23\Desktop\talent-management-web\templates\index.html', encoding='utf-8') as f:
    content = f.read()

# Find the non-admin section and replace it with a clean version
old_section = '<!-- 普通用户视图 -->'
idx_start = content.find(old_section)
idx_end = content.find('<!-- 人才列表 -->')

if idx_start < 0 or idx_end < 0:
    print('ERROR: markers not found')
    import sys
    sys.exit(1)

section = content[idx_start:idx_end]
print(f'Old section: {len(section)} chars')

# Create clean new non-admin section
new_section = '''<!-- 普通用户视图 -->
            <div v-else>
                <div class="tabs">
                    <button class="tab" :class="{ active: activeTab === 'register' }" @click="activeTab = 'register'">报名信息</button>
                    <button class="tab" :class="{ active: activeTab === 'mystatus' }" @click="activeTab = 'mystatus'">查询状态</button>
                </div>

                <!-- 报名表单 -->
                <div v-if="activeTab === 'register'" style="max-width: 600px; margin: 40px auto; background: white; padding: 32px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                    <div v-if="currentDemand" style="background: #e3f2fd; padding: 12px; border-radius: 6px; margin-bottom: 20px; text-align: center;">
                        <strong style="color: #1565c0; font-size: 16px;">{{ currentDemand.title }}</strong>
                        <div style="color: #666; font-size: 13px; margin-top: 4px;">{{ currentDemand.business_type }} · {{ currentDemand.tier }}</div>
                    </div>
                    <div v-else style="background: #fff3e0; padding: 12px; border-radius: 6px; margin-bottom: 20px; text-align: center; color: #e65100;">
                        未指定需求，请通过招募链接访问
                    </div>
                    <h3 style="margin-bottom: 20px; color: #333;">填写报名信息</h3>
                    <div style="margin-bottom: 16px;">
                        <label style="display: block; margin-bottom: 4px; color: #666;">姓名</label>
                        <input v-model="registerForm.name" type="text" placeholder="请输入姓名" style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box;">
                    </div>
                    <div style="margin-bottom: 16px;">
                        <label style="display: block; margin-bottom: 4px; color: #666;">手机号</label>
                        <input v-model="registerForm.phone" type="text" placeholder="请输入手机号" style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box;">
                    </div>
                    <div style="margin-bottom: 16px;">
                        <label style="display: block; margin-bottom: 4px; color: #666;">空闲时间</label>
                        <input v-model="registerForm.available_time" type="text" placeholder="例如：周末、平时晚上" style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box;">
                    </div>
                    <div style="margin-bottom: 16px;">
                        <label style="display: block; margin-bottom: 4px; color: #666;">游戏经历</label>
                        <textarea v-model="registerForm.game_experience" placeholder="请描述您的游戏经历" rows="4" style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; resize: vertical;"></textarea>
                    </div>
                    <button @click="submitRegistration" style="width: 100%; padding: 12px; background: #4a90d9; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 16px;">提交报名</button>
                    <div v-if="registerMessage" style="margin-top: 12px; padding: 10px; border-radius: 4px; background: #d4edda; color: #155724;">{{ registerMessage }}</div>
                </div>

                <!-- 查询状态 -->
                <div v-if="activeTab === 'mystatus'" style="max-width: 600px; margin: 40px auto; background: white; padding: 32px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                    <h3 style="margin-bottom: 20px; color: #333;">查询报名状态</h3>
                    <div style="display: flex; gap: 8px; margin-bottom: 16px;">
                        <input v-model="statusPhone" type="text" placeholder="请输入报名时填写的手机号" style="flex: 1; padding: 10px; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box;">
                        <button @click="checkMyStatus" style="padding: 10px 20px; background: #4a90d9; color: white; border: none; border-radius: 4px; cursor: pointer;">查询</button>
                    </div>
                    <div v-if="statusResult && statusResult.found" style="padding: 16px; background: #f8f9fa; border-radius: 4px;">
                        <p style="margin-bottom: 8px;"><strong>姓名：</strong>{{ statusResult.name }}</p>
                        <p style="margin-bottom: 8px;"><strong>报名状态：</strong><span :style="{ color: statusResult.status === '已入选' ? 'green' : statusResult.status === '未入选' ? 'red' : '#666' }">{{ statusResult.status }}</span></p>
                        <p v-if="statusResult.demand_title" style="margin-bottom: 8px;"><strong>需求名称：</strong>{{ statusResult.demand_title }}</p>
                        <p v-if="statusResult.selected_at" style="margin-bottom: 8px;"><strong>入选时间：</strong>{{ statusResult.selected_at }}</p>
                    </div>
                    <div v-else-if="statusChecked" style="padding: 16px; color: #666; text-align: center;">未找到该手机号的报名记录</div>
                </div>
            </div>

'''

content = content[:idx_start] + new_section + content[idx_end:]
print(f'New content: {len(content)} chars')

with open(r'C:\Users\wb.liujing23\Desktop\talent-management-web\templates\index.html', 'w', encoding='utf-8') as f:
    f.write(content)
print('Saved')
