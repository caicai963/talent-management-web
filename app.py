"""
人才标签管理系统 - Flask 后端
"""
from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import sqlite3
import os
import pandas as pd
from datetime import datetime
import io

app = Flask(__name__)
CORS(app)

# 使用内存数据库（Render 免费服务无持久化存储）
DATABASE = ':memory:'

# 字段映射：数据库字段名 -> Excel 列名
COLUMN_MAP = {
    "name": "姓名",
    "gender": "性别",
    "birth_date": "出生年月",
    "identity_tag": "身份标签",
    "city": "常住城市",
    "city_level": "城市级别",
    "school": "学校",
    "major": "专业",
    "education": "在读学历",
    "graduate_year": "预计毕业年份",
    "phone": "手机号",
    "wechat": "微信号",
    "project_count": "业务次数",
    "avg_rating": "历史平均星级",
    "month_rating": "当月星级",
    "overall_summary": "整体评价摘要",
    "detailed_review": "详细业务评价",
    "exam_score": "兼职考试得分",
    "basic_test": "日常跑测/基础测评",
    "desktop_research": "桌面研究",
    "issue_list": "问题清单执行",
    "insight_proposal": "洞察提案能力",
    "skills_debug": "Skills 生成/调试",
    "agent_debug": "Agent 生成/调试",
    "knowledge_base": "AI 知识库建设",
    "interview_selection": "访谈执行 - 玩家甄选",
    "online_interview": "访谈执行 - 线上访谈",
    "field_interview": "访谈执行 - 田野调查/外访",
    "questionnaire_design": "访谈提纲/问卷设计",
    "questionnaire_analysis": "问卷调研",
    "lab_assist": "实验室测试 - 协助执行",
    "lab_leader": "实验室测试 - 主负责",
    "data_warehouse": "数仓工作",
    "data_query": "数据查询/报表开发",
    "web_crawl": "爬虫/数据收集",
    "deep_assessment": "深度测评能力",
    "commercial_research": "商业化研究与分析",
    "excel_level": "Excel 技能等级",
    "spss_level": "SPSS 技能等级",
    "language_ability": "语言能力",
    "category_moba": "MOBA 类",
    "category_mmorgp": "MMORPG",
    "category_openworld_rpg": "开放世界 RPG",
    "category_card_rpg": "卡牌 RPG 类",
    "category_tactical": "战术竞技类",
    "category_shooter": "射击类",
    "category_strategy_slg": "策略/SLG 类",
    "category_action_fight": "动作/格斗类",
    "category_sandbox_survival": "沙盒/生存类",
    "category_autochess": "自走棋类",
    "category_casual_puzzle": "休闲益智类",
    "category_party": "休闲竞技/派对类",
    "category_etc": "其他品类",
    "key_game_1": "逆水寒",
    "key_game_2": "燕云十六声",
    "key_game_3": "一梦江湖",
    "key_game_4": "阴阳师",
    "key_game_5": "金铲铲之战",
    "key_game_6": "蛋仔派对",
    "key_game_7": "无尽冬日",
    "key_game_8": "率土之滨",
    "key_game_9": "王者荣耀",
    "key_game_10": "英雄联盟",
    "key_game_11": "明日之后",
    "key_game_12": "萤火突击",
    "key_game_13": "三角洲行动",
    "deep_game_1": "深度游戏 1",
    "deep_game_2": "深度游戏 2",
    "deep_game_3": "深度游戏 3",
    "proficient_products": "精通产品",
    "familiar_products": "熟悉产品",
    "other_game_experience": "其他游戏经历",
}

TALENT_FIELDS = list(COLUMN_MAP.keys())

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    columns = ["id INTEGER PRIMARY KEY AUTOINCREMENT"]
    for field in TALENT_FIELDS:
        columns.append(f"{field} TEXT")
    columns.extend(["created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP", "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"])
    create_sql = f"CREATE TABLE IF NOT EXISTS talents ({', '.join(columns)})"
    cursor.execute(create_sql)
    cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, role TEXT DEFAULT 'user', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    conn.commit()
    conn.close()

def ensure_admin():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", ('admin', 'admin123', 'admin'))
        conn.commit()
    conn.close()

with app.app_context():
    init_db()
    ensure_admin()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/talents', methods=['GET'])
def get_talents():
    conn = get_db()
    cursor = conn.cursor()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '')
    offset = (page - 1) * per_page
    query = "SELECT * FROM talents WHERE 1=1"
    params = []
    if search:
        query += " AND (name LIKE ? OR school LIKE ? OR major LIKE ? OR phone LIKE ?)"
        params.extend([f'%{search}%'] * 4)
    count_query = query.replace('SELECT *', 'SELECT COUNT(*)')
    cursor.execute(count_query, params)
    total = cursor.fetchone()[0]
    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([per_page, offset])
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    talents = [dict(row) for row in rows]
    return jsonify({'data': talents, 'total': total, 'page': page, 'per_page': per_page, 'total_pages': (total + per_page - 1) // per_page})

@app.route('/api/talents/<int:talent_id>', methods=['GET'])
def get_talent(talent_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM talents WHERE id = ?", (talent_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return jsonify(dict(row))
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/talents', methods=['POST'])
def create_talent():
    data = request.json
    conn = get_db()
    cursor = conn.cursor()
    fields = []
    placeholders = []
    values = []
    for field in TALENT_FIELDS:
        if field in data:
            fields.append(field)
            placeholders.append('?')
            values.append(data[field])
    if fields:
        sql = f"INSERT INTO talents ({', '.join(fields)}) VALUES ({', '.join(placeholders)})"
        cursor.execute(sql, values)
        talent_id = cursor.lastrowid
        conn.commit()
    conn.close()
    return jsonify({'id': talent_id, 'message': '创建成功'})

@app.route('/api/talents/<int:talent_id>', methods=['PUT'])
def update_talent(talent_id):
    data = request.json
    conn = get_db()
    cursor = conn.cursor()
    updates = []
    values = []
    for field in TALENT_FIELDS:
        if field in data:
            updates.append(f"{field} = ?")
            values.append(data[field])
    if updates:
        updates.append("updated_at = CURRENT_TIMESTAMP")
        values.append(talent_id)
        sql = f"UPDATE talents SET {', '.join(updates)} WHERE id = ?"
        cursor.execute(sql, values)
        conn.commit()
    conn.close()
    return jsonify({'message': '更新成功'})

@app.route('/api/talents/<int:talent_id>', methods=['DELETE'])
def delete_talent(talent_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM talents WHERE id = ?", (talent_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': '删除成功'})

@app.route('/api/talents/import', methods=['POST'])
def import_talents():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    file = request.files['file']
    if not file.filename.endswith(('.xlsx', '.xls')):
        return jsonify({'error': 'Please upload Excel file'}), 400
    try:
        df = pd.read_excel(file)
        conn = get_db()
        cursor = conn.cursor()
        imported_count = 0
        for idx, row in df.iterrows():
            fields = []
            placeholders = []
            values = []
            for col_name in df.columns:
                field = None
                col_str = str(col_name).strip()
                if col_str in COLUMN_MAP.values():
                    field = [k for k, v in COLUMN_MAP.items() if v == col_str][0]
                elif col_str in COLUMN_MAP:
                    field = col_str
                if field:
                    value = row[col_name]
                    if pd.notna(value):
                        fields.append(field)
                        placeholders.append('?')
                        values.append(str(value))
            if fields:
                try:
                    sql = f"INSERT INTO talents ({', '.join(fields)}) VALUES ({', '.join(placeholders)})"
                    cursor.execute(sql, values)
                    imported_count += 1
                except:
                    pass
        conn.commit()
        conn.close()
        return jsonify({'message': f'成功导入 {imported_count} 条记录', 'count': imported_count})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/talents/export', methods=['GET'])
def export_talents():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM talents ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        return jsonify({'error': 'No data'}), 400
    data = [dict(row) for row in rows]
    df = pd.DataFrame(data)
    for col in ['created_at', 'updated_at']:
        if col in df.columns:
            df = df.drop(columns=[col])
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='人才库')
    output.seek(0)
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name=f'人才库_{datetime.now().strftime("%Y%m%d")}.xlsx')

@app.route('/api/stats', methods=['GET'])
def get_stats():
    conn = get_db()
    cursor = conn.cursor()
    stats = {}
    cursor.execute("SELECT COUNT(*) FROM talents")
    stats['total'] = cursor.fetchone()[0]
    cursor.execute("SELECT education, COUNT(*) as count FROM talents WHERE education IS NOT NULL AND education != '' GROUP BY education")
    stats['education'] = {row[0]: row[1] for row in cursor.fetchall()}
    cursor.execute("SELECT identity_tag, COUNT(*) as count FROM talents WHERE identity_tag IS NOT NULL AND identity_tag != '' GROUP BY identity_tag")
    stats['identity_tag'] = {row[0]: row[1] for row in cursor.fetchall()}
    cursor.execute("SELECT city, COUNT(*) as count FROM talents WHERE city IS NOT NULL AND city != '' GROUP BY city ORDER BY count DESC LIMIT 10")
    stats['city'] = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    return jsonify(stats)

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
    user = cursor.fetchone()
    if user:
        result = {'success': True, 'user': {'id': user['id'], 'username': user['username'], 'role': user['role']}}
        conn.close()
        return jsonify(result)
    conn.close()
    return jsonify({'success': False, 'error': 'Invalid credentials'}), 401

@app.route('/api/users', methods=['GET'])
def list_users():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role, created_at FROM users ORDER BY id")
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(users)

@app.route('/api/users', methods=['POST'])
def create_user():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    role = data.get('role', 'user').strip()
    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] >= 5:
        conn.close()
        return jsonify({'error': '最多只能创建 5 个账号'}), 400
    try:
        cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", (username, password, role))
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        return jsonify({'id': user_id, 'message': '账号创建成功'})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': '用户名已存在'}), 400

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': '删除成功'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug, port=port, host='0.0.0.0')
