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
DATABASE = 'talent.db'

# 75个字段定义
TALENT_FIELDS = [
    # 模块一：基础信息（12列）
    "name", "gender", "birth_date", "identity_tag", "city", "city_level",
    "school", "major", "education", "graduate_year", "phone", "wechat",
    # 模块二：人员评价（6列）
    "project_count", "avg_rating", "month_rating", "overall_summary",
    "detailed_review", "exam_score",
    # 模块三：业务能力（22列）
    "basic_test", "desktop_research", "issue_list", "insight_proposal",
    "skills_debug", "agent_debug", "knowledge_base", "interview_selection",
    "online_interview", "field_interview", "questionnaire_design",
    "questionnaire_analysis", "lab_assist", "lab_leader",
    # 模块四：工作经历（35列）
    "company_1", "position_1", "duration_1", "description_1",
    "company_2", "position_2", "duration_2", "description_2",
    "company_3", "position_3", "duration_3", "description_3",
    "company_4", "position_4", "duration_4", "description_4",
    "company_5", "position_5", "duration_5", "description_5",
    # 更多工作经历和标签
    "skill_tags", "availability", "hourly_rate", "preferred_city",
    "preferred_industry", "self_introduction", "source",
    "registration_date", "last_update", "status", "remarks"
]

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
        for _, row in df.iterrows():
            fields = []
            placeholders = []
            values = []

            for field in TALENT_FIELDS:
                if field in row.index:
                    value = row[field]
                    if pd.notna(value):
                        fields.append(field)
                        placeholders.append('?')
                        values.append(str(value))

            if fields:
                sql = f"INSERT INTO talents ({', '.join(fields)}) VALUES ({', '.join(placeholders)})"
                cursor.execute(sql, values)
                imported_count += 1

        conn.commit()
        conn.close()

        return jsonify({'message': f'成功导入 {imported_count} 条记录', 'count': imported_count})
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
