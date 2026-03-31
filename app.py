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
DATABASE = '/tmp/talent.db'

# 字段映射：数据库字段名 -> Excel列名
COLUMN_MAP = {
    # 模块一：基础信息
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
    # 模块二：人员评价
    "project_count": "业务次数",
    "avg_rating": "历史平均星级",
    "month_rating": "当月星级",
    "overall_summary": "整体评价摘要",
    "detailed_review": "详细业务评价",
    "exam_score": "兼职考试得分",
    # 模块三：业务能力
    "basic_test": "日常跑测/基础测评",
    "desktop_research": "桌面研究（竞品/舆情/资料整理）",
    "issue_list": "问题清单执行",
    "insight_proposal": "洞察提案能力",
    "skills_debug": "Skills生成/调试（AI工具）",
    "agent_debug": "Agent生成/调试",
    "knowledge_base": "AI知识库建设",
    "interview_selection": "访谈执行-玩家甄选",
    "online_interview": "访谈执行-线上访谈",
    "field_interview": "访谈执行-田野调查/外访",
    "questionnaire_design": "访谈提纲/问卷设计",
    "questionnaire_analysis": "问卷调研（录入/整理/分析）",
    "lab_assist": "实验室测试-协助执行",
    "lab_leader": "实验室测试-主负责/主持",
    "data_warehouse": "数仓工作（日志/报表）",
    "data_query": "数据查询/报表开发",
    "web_crawl": "爬虫/数据收集",
    "deep_assessment": "深度测评能力",
    "commercial_research": "商业化研究与分析",
    "excel_level": "Excel技能等级",
    "spss_level": "SPSS技能等级",
    "language_ability": "语言能力",
    # 模块四：游戏品类
    "category_moba": "品类-MOBA类（英雄联盟、王者荣耀等）",
    "category_mmorgp": "品类-MMORPG（逆水寒、梦幻西游等）",
    "category_openworld_rpg": "品类-开放世界RPG（塞尔达、原神等）",
    "category_card_rpg": "品类-卡牌RPG类（阴阳师、崩坏：星穹铁道等）",
    "category_tactical": "品类-战术竞技类（PUBG、和平精英等）",
    "category_shooter": "品类-射击类（穿越火线、CODM等）",
    "category_strategy_slg": "品类-策略/SLG类（文明、率土之滨等）",
    "category_action_fight": "品类-动作/格斗类（只狼、崩坏3等）",
    "category_sandbox_survival": "品类-沙盒/生存类（我的世界、明日之后等）",
    "category_autochess": "品类-自走棋类（金铲铲、多多自走棋等）",
    "category_casual_puzzle": "品类-休闲益智类（羊了个羊、消消乐等）",
    "category_party": "品类-休闲竞技/派对类（蛋仔派对、鹅鸭杀等）",
    "category_etc": "品类-其他（自填）",
    # 模块五：重点游戏
    "key_game_1": "重点游戏-逆水寒",
    "key_game_2": "重点游戏-燕云十六声",
    "key_game_3": "重点游戏-一梦江湖",
    "key_game_4": "重点游戏-阴阳师",
    "key_game_5": "重点游戏-金铲铲之战",
    "key_game_6": "重点游戏-蛋仔派对",
    "key_game_7": "重点游戏-无尽冬日",
    "key_game_8": "重点游戏-率土之滨",
    "key_game_9": "重点游戏-王者荣耀",
    "key_game_10": "重点游戏-英雄联盟",
    "key_game_11": "重点游戏-明日之后",
    "key_game_12": "重点游戏-萤火突击",
    "key_game_13": "重点游戏-三角洲行动",
    # 模块六：深度游戏
    "deep_game_1": "深度游戏1",
    "deep_game_2": "深度游戏2",
    "deep_game_3": "深度游戏3",
    # 模块七：其他
    "proficient_products": "精通产品（1000h+）",
    "familiar_products": "熟悉产品（500h+）",
    "other_game_experience": "其他游戏经历补充",
}

TALENT_FIELDS = list(COLUMN_MAP.keys())

def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """初始化数据库表"""
    conn = get_db()
    cursor = conn.cursor()

    # 创建人才表
    columns = ["id INTEGER PRIMARY KEY AUTOINCREMENT"]
    for field in TALENT_FIELDS:
        columns.append(f"{field} TEXT")

    columns.extend([
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    ])

    create_sql = f"""
    CREATE TABLE IF NOT EXISTS talents (
        {', '.join(columns)}
    )
    """
    cursor.execute(create_sql)

    # 创建用户表（用于权限管理）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT DEFAULT 'user',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()

def ensure_admin():
    """确保默认管理员账号存在"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            ('admin', 'admin123', 'admin')
        )
        conn.commit()
    conn.close()

# 初始化数据库 + 确保管理员存在
init_db()
ensure_admin()

# ========== API 端点 ==========

@app.route('/')
def index():
    """渲染主页"""
    return render_template('index.html')

# ========== 系统初始化 API（用于首次设置账号）==========

@app.route('/api/system/status', methods=['GET'])
def system_status():
    """检查系统状态：是否有账号"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    cursor.execute("SELECT id, username, role FROM users")
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({
        'has_users': count > 0,
        'user_count': count,
        'users': users
    })

@app.route('/api/system/reset-admin', methods=['POST'])
def reset_admin():
    """重置admin账号密码为admin123（紧急修复）"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users")
    cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", ('admin', 'admin123', 'admin'))
    conn.commit()
    conn.close()
    return jsonify({'message': 'admin/admin123 已重置'})

@app.route('/api/system/setup', methods=['POST'])
def system_setup():
    """初始化/重置系统账号（仅当账号数<=1时可用，防止误操作）"""
    data = request.json
    users_to_create = data.get('users', [])

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]

    if count > 1:
        conn.close()
        return jsonify({'error': '系统已有多个账号，请联系管理员删除多余账号后再试'}), 403

    if len(users_to_create) == 0:
        conn.close()
        return jsonify({'error': '请至少创建1个账号'}), 400

    if len(users_to_create) > 5:
        conn.close()
        return jsonify({'error': '最多只能创建5个账号'}), 400

    # 检查用户名重复
    usernames = [u.get('username', '').strip() for u in users_to_create]
    if len(usernames) != len(set(usernames)):
        conn.close()
        return jsonify({'error': '用户名不能重复'}), 400

    for u in users_to_create:
        username = u.get('username', '').strip()
        password = u.get('password', '').strip()
        role = u.get('role', 'user').strip()
        if not username or not password:
            conn.close()
            return jsonify({'error': '用户名和密码不能为空'}), 400

    # 删除除admin外的所有账号（如果有）
    cursor.execute("DELETE FROM users WHERE username != 'admin'")
    # 更新admin账号
    for u in users_to_create:
        username = u.get('username', '').strip()
        password = u.get('password', '').strip()
        role = u.get('role', 'user').strip()
        cursor.execute(
            "INSERT OR REPLACE INTO users (username, password, role) VALUES (?, ?, ?)",
            (username, password, role)
        )

    conn.commit()
    conn.close()
    return jsonify({'message': f'成功创建 {len(users_to_create)} 个账号'})

@app.route('/api/users', methods=['GET'])
def list_users():
    """获取所有账号（仅管理员）"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role, created_at FROM users ORDER BY id")
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(users)

@app.route('/api/users', methods=['POST'])
def create_user():
    """新增账号（仅管理员，最多5个）"""
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
        return jsonify({'error': '最多只能创建5个账号'}), 400

    try:
        cursor.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            (username, password, role)
        )
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        return jsonify({'id': user_id, 'message': '账号创建成功'})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': '用户名已存在'}), 400

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    """删除账号（仅管理员）"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return jsonify({'error': '用户不存在'}), 404
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': '删除成功'})

# ========== 人才管理 API ==========

@app.route('/api/talents', methods=['GET'])
def get_talents():
    """获取人才列表（支持搜索/分页）"""
    conn = get_db()
    cursor = conn.cursor()

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '')
    filters = request.args.get('filters', '')

    offset = (page - 1) * per_page

    query = "SELECT * FROM talents WHERE 1=1"
    params = []

    if search:
        query += " AND (name LIKE ? OR school LIKE ? OR major LIKE ? OR phone LIKE ?)"
        params.extend([f'%{search}%'] * 4)

    if filters:
        try:
            filter_dict = eval(filters)
            for key, value in filter_dict.items():
                if value:
                    query += f" AND {key} = ?"
                    params.append(value)
        except:
            pass

    count_query = query.replace('SELECT *', 'SELECT COUNT(*)')
    cursor.execute(count_query, params)
    total = cursor.fetchone()[0]

    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([per_page, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    talents = [dict(row) for row in rows]

    return jsonify({
        'data': talents,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page
    })

@app.route('/api/talents/<int:talent_id>', methods=['GET'])
def get_talent(talent_id):
    """获取单个人才详情"""
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
    """新增人才"""
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
    """更新人才"""
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
    """删除人才"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM talents WHERE id = ?", (talent_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': '删除成功'})

@app.route('/api/talents/import', methods=['POST'])
def import_talents():
    """批量导入Excel"""
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
        error_rows = []
        for idx, row in df.iterrows():
            fields = []
            placeholders = []
            values = []

            for col_name in df.columns:
                # 尝试用Excel列名匹配
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
                except Exception as e:
                    error_rows.append(f"第{idx+2}行: {str(e)}")

        conn.commit()
        conn.close()

        msg = f'成功导入 {imported_count} 条记录'
        if error_rows:
            msg += f'，{len(error_rows)} 行失败'
        return jsonify({'message': msg, 'count': imported_count, 'errors': error_rows[:10]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/talents/export', methods=['GET'])
def export_talents():
    """导出Excel"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM talents ORDER BY id DESC")
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
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'人才库_{datetime.now().strftime("%Y%m%d")}.xlsx'
    )

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """获取标签统计"""
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

    cursor.execute("SELECT month_rating, COUNT(*) as count FROM talents WHERE month_rating IS NOT NULL AND month_rating != '' GROUP BY month_rating")
    stats['month_rating'] = {row[0]: row[1] for row in cursor.fetchall()}

    skill_fields = ['basic_test', 'desktop_research', 'issue_list', 'insight_proposal',
                   'skills_debug', 'agent_debug', 'knowledge_base', 'interview_selection',
                   'online_interview', 'field_interview', 'questionnaire_design',
                   'questionnaire_analysis', 'lab_assist', 'lab_leader']

    stats['skills'] = {}
    for field in skill_fields:
        cursor.execute(f"SELECT COUNT(*) FROM talents WHERE {field} = '精通'")
        stats['skills'][field] = cursor.fetchone()[0]

    conn.close()
    return jsonify(stats)

# ========== 权限管理 API ==========

@app.route('/api/login', methods=['POST'])
def login():
    """用户登录"""
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    print(f"[DEBUG] Login attempt: username='{username}', password='{password}'")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
    user = cursor.fetchone()

    if user:
        result = {
            'success': True,
            'user': {
                'id': user['id'],
                'username': user['username'],
                'role': user['role']
            }
        }
        conn.close()
        return jsonify(result)

    # 调试：看看库里有什么用户
    cursor.execute("SELECT username, password, role FROM users")
    all_users = [dict(row) for row in cursor.fetchall()]
    print(f"[DEBUG] All users in DB: {all_users}")
    conn.close()

    return jsonify({'success': False, 'error': 'Invalid credentials', 'debug_received': {'username': username, 'password': password}}), 401

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    print("=" * 50)
    print("人才标签管理系统")
    print("=" * 50)
    print(f"访问地址: http://0.0.0.0:{port}")
    print("默认管理员: admin / admin123")
    print("初始化账号请访问: POST /api/system/setup")
    print("=" * 50)
    app.run(debug=debug, port=port, host='0.0.0.0')
