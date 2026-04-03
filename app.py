"""
人才标签管理系统 - Flask 后端
包含：人才管理 + 需求接单流程
支持：SQLite（本地） / PostgreSQL（Supabase 云数据库）
"""
import os
import sqlite3
import psycopg2
import psycopg2.extras
import pandas as pd
from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
from datetime import datetime
import io

app = Flask(__name__)
CORS(app)

# 配置 Jinja2 使用 <% %> 替代 {{ }}，避免与 Vue 冲突
app.jinja_env.variable_start_string = '<%'
app.jinja_env.variable_end_string = '%>'

# 数据库配置：优先使用 DATABASE_URL（Supabase PostgreSQL），否则用本地 SQLite
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db():
    """返回数据库连接（自动在行结束时关闭）"""
    if DATABASE_URL:
        conn = psycopg2.connect(DATABASE_URL)
    else:
        conn = sqlite3.connect('/tmp/talent.db')
        conn.row_factory = sqlite3.Row
    return conn


def dict_from_row(row):
    if row is None:
        return None
    if hasattr(row, 'keys'):
        return dict(row)
    return row


def fetchall_dicts(cursor):
    rows = cursor.fetchall()
    if not rows:
        return []
    if hasattr(rows[0], 'keys'):
        return [dict(row) for row in rows]
    cols = [desc[0] for desc in cursor.description]
    return [dict(zip(cols, row)) for row in rows]


def fetchone_dict(cursor):
    row = cursor.fetchone()
    if row is None:
        return None
    if hasattr(row, 'keys'):
        return dict(row)
    cols = [desc[0] for desc in cursor.description]
    return dict(zip(cols, row))

def close_conn(conn):
    """关闭连接（psycopg2 需要 commit+close，sqlite3 只管 close）"""
    try:
        conn.commit()
    except Exception:
        pass
    try:
        conn.close()
    except Exception:
        pass

@app.teardown_appcontext
def shutdown_session(exception=None):
    # Flask 请求结束后自动清理连接（通过 request context）
    pass

# ============================================================
# 人才工资单价表（单位：元）
# ============================================================
TALENT_PRICE_TABLE = {
    "甄别": [
        {"label": "5~10mins/个", "price": 8},
        {"label": "10~20mins/个", "price": 12},
        {"label": "20~30mins/个", "price": 16},
        {"label": ">30mins/个", "price": 26},
    ],
    "电访": [
        {"label": "30mins以内/个", "price": 30},
        {"label": "30~60mins/个", "price": 45},
        {"label": "60~90mins/个（仅限5星兼职）", "price": 80},
        {"label": "90~120mins/个", "price": 100},
    ],
    "实验室执行": [
        {"label": "2H以内/场", "price": 150},
        {"label": "2~4小时/场", "price": 200},
        {"label": "4~6小时/场", "price": 250},
    ],
    "街访1": [
        {"label": "10分钟以内", "price": 30, "base": 120},
        {"label": "30分钟以内", "price": 65, "base": 120},
        {"label": "30~60分钟", "price": 104, "base": 120},
    ],
    "街访2": [
        {"label": "千万级", "gmv_rate": 0.05, "gmv_rate_display": "GMV×5%", "base": 120, "fixed": 3000},
        {"label": "百万级", "gmv_rate": 0.10, "gmv_rate_display": "GMV×10%", "base": 120, "fixed": 1500},
        {"label": "十万级", "gmv_rate": 0.20, "gmv_rate_display": "GMV×20%", "base": 120, "fixed": 800},
        {"label": "千级及以下", "gmv_rate": None, "gmv_rate_display": "固定200元", "base": 120, "fixed": 200},
    ],
    "舆情打标": [
        {"label": "条", "price": 0.3},
    ],
    "洞察收集/桌面研究": [
        {"label": "<0.5H/人", "price": 10},
        {"label": "<1H/人", "price": 30},
        {"label": "1~3H/人", "price": 100},
        {"label": "3~6H/人", "price": 150},
    ],
    "邀约拉新": [
        {"label": "条", "price": 3},
    ],
}

BRUSH_LIST_FEE = 15
OVERTIME_FEE_PER_HOUR = 50
MEAL_FEE_PER_MEAL = 30
TRANSPORT_SUBSIDY = 50
LAB_TIER_HOURS = {"2H以内/场": 2, "2~4小时/场": 4, "4~6小时/场": 6}


def calc_human_cost_lab(tier_label, end_time_str, cross_meal_count, scheduled_hours):
    overtime_hours = 0
    overtime_fee = 0
    meal_fee = cross_meal_count * MEAL_FEE_PER_MEAL
    transport_fee = 0
    note_parts = []
    std_hours = LAB_TIER_HOURS.get(tier_label, 0)
    if scheduled_hours > std_hours:
        overtime_hours = round(scheduled_hours - std_hours, 2)
        overtime_fee = int(overtime_hours) * OVERTIME_FEE_PER_HOUR
        note_parts.append(f"超时{int(overtime_hours)}小时×50={overtime_fee}元")
    if meal_fee > 0:
        note_parts.append(f"餐补{cross_meal_count}顿×30={meal_fee}元")
    if end_time_str:
        try:
            h, m = map(int, end_time_str.split(":"))
            if h > 21 or (h == 21 and m > 0):
                transport_fee = TRANSPORT_SUBSIDY
                note_parts.append(f"交通补贴50元")
        except:
            pass
    subtotal = overtime_fee + meal_fee + transport_fee
    note = "，".join(note_parts) if note_parts else "无额外补贴"
    return {
        "overtime_hours": overtime_hours,
        "overtime_fee": overtime_fee,
        "meal_fee": meal_fee,
        "transport_fee": transport_fee,
        "subtotal": subtotal,
        "note": note,
    }


def vlookup_h(gmv_val, lut):
    if not gmv_val or gmv_val <= 0:
        return 0
    keys = sorted(lut.keys())
    result = 0
    for k in keys:
        if k <= gmv_val:
            result = lut[k]
        else:
            break
    return result


LUT_ZHENBIE = {1:0.2, 8:0.2, 13:0.3, 17:0.3, 21:0.4, 25:0.4,
               29:0.6, 33:0.6, 37:0.7, 41:1.0, 45:1.0, 49:1.0,
               53:1.2, 62:1.2, 100:1.3}
LUT_DIANFANG = {1:0.3, 8:0.4, 13:0.5, 17:0.6, 21:0.7, 25:0.7,
                29:0.7, 33:0.8, 37:0.8, 41:1.0, 45:1.0, 49:1.0,
                53:1.2, 62:1.2, 100:1.2}
LUT_JIEFANG = {1:0.5, 8:0.5, 13:0.5, 17:0.5, 21:0.6, 25:0.6,
               29:0.6, 33:1.0, 37:1.0, 41:1.0, 45:1.0, 49:1.5,
               53:1.5, 62:1.5, 100:2.0}
LUT_CESHI = {1:0.5, 8:0.5, 13:0.5, 17:1.0, 21:1.0, 25:1.0,
             29:1.0, 33:1.5, 37:1.5, 41:1.5, 45:1.5, 100:1.5}


def calc_quote(demand_data):
    biz = demand_data.get("business_type", "")
    tier = demand_data.get("tier", "")
    quantity = demand_data.get("quantity", 1)
    brush = demand_data.get("brush_list", False)
    gmv = demand_data.get("gmv", 0)
    if biz in ("甄别执行", "电访", "街访执行", "测试执行") and not gmv:
        gmv = quantity
    scheduled_hours = demand_data.get("scheduled_hours", 0)
    end_time = demand_data.get("end_time", "")
    cross_meal = demand_data.get("cross_meal_count", 0)

    if biz not in TALENT_PRICE_TABLE:
        return {"error": f"未知业务类型: {biz}"}
    tiers = TALENT_PRICE_TABLE[biz]
    tier_data = next((t for t in tiers if t["label"] == tier), None)
    if not tier_data:
        return {"error": f"未知档位: {tier}"}

    part_time_wage = 0
    human_cost = 0
    wage_note = ""
    human_note = ""

    if biz == "街访1":
        base = tier_data.get("base", 120)
        price = tier_data.get("price", 0)
        part_time_wage = base + price * quantity
        wage_note = f"120元/天底薪+ {price}元/个× {quantity}个"

    elif biz == "街访2":
        base = tier_data.get("base", 120)
        fixed = tier_data.get("fixed", 0)
        gmv_rate = tier_data.get("gmv_rate")
        rate_display = tier_data.get("gmv_rate_display", "")
        if gmv_rate is not None:
            part_time_wage = base + gmv * gmv_rate
            wage_note = f"120元/天底薪+ GMV({gmv}元)×{gmv_rate*100:.0f}%"
        else:
            part_time_wage = base + fixed
            wage_note = f"120元/天底薪+ 固定{fixed}元"

    elif biz == "甄别执行":
        unit_price = tier_data.get("price", 0)
        part_time_wage = unit_price * quantity
        wage_note = f"{unit_price}元/个× {quantity}个"
        h = vlookup_h(gmv, LUT_ZHENBIE)
        human_cost = h * 1200
        human_note = f"样本数{gmv}→人力投入{h}×1200 = {int(human_cost)}元"

    elif biz == "电访":
        unit_price = tier_data.get("price", 0)
        part_time_wage = unit_price * quantity
        wage_note = f"{unit_price}元/个× {quantity}个"
        h = vlookup_h(gmv, LUT_DIANFANG)
        human_cost = h * 1200
        human_note = f"样本数{gmv}→人力投入{h}×1200 = {int(human_cost)}元"

    elif biz == "街访执行":
        unit_price = tier_data.get("price", 0)
        part_time_wage = unit_price * quantity
        wage_note = f"{unit_price}元/个× {quantity}个"
        h = vlookup_h(gmv, LUT_JIEFANG)
        human_cost = h * 1200
        human_note = f"样本数{gmv}→人力投入{h}×1200 = {int(human_cost)}元"

    elif biz == "测试执行":
        unit_price = tier_data.get("price", 0)
        part_time_wage = unit_price * quantity
        wage_note = f"{unit_price}元/个× {quantity}个"
        h = vlookup_h(gmv, LUT_CESHI)
        human_cost = h * 1200
        human_note = f"样本数{gmv}→人力投入{h}×1200 = {int(human_cost)}元"

    elif biz == "实验室执行":
        unit_price = tier_data.get("price", 0)
        part_time_wage = unit_price * quantity
        wage_note = f"{unit_price}元/场× {quantity}场"
        lab_extra = calc_human_cost_lab(tier, end_time, cross_meal, scheduled_hours)
        human_cost = lab_extra["subtotal"]
        human_note = lab_extra["note"]

    else:
        unit_price = tier_data.get("price", 0)
        if brush:
            unit_price_brush = unit_price + BRUSH_LIST_FEE
            part_time_wage = unit_price_brush * quantity
            wage_note = (f"({unit_price}+15元/样本)×{quantity}={part_time_wage}元，"
                         f"呼出费用根据拨打难度有所不同，以实际产生结算")
        else:
            part_time_wage = unit_price * quantity
            wage_note = f"{unit_price}元/个× {quantity}个"

    total = round(part_time_wage + human_cost, 2)
    return {
        "part_time_wage": round(part_time_wage, 2),
        "human_cost": round(human_cost, 2),
        "total": total,
        "wage_note": wage_note,
        "human_note": human_note,
    }


# ============================================================
# 人才字段映射
# ============================================================
COLUMN_MAP = {
    "name": "姓名", "gender": "性别", "birth_date": "出生年月",
    "identity_tag": "身份标签", "city": "常住城市", "city_level": "城市级别",
    "school": "学校", "major": "专业", "education": "在读学历",
    "graduate_year": "预计毕业年份", "phone": "手机号", "wechat": "微信号",
    "project_count": "业务次数", "avg_rating": "历史平均星级",
    "month_rating": "当月星级", "overall_summary": "整体评价摘要",
    "detailed_review": "详细业务评价", "exam_score": "兼职考试得分",
    "basic_test": "日常跑测/基础测评",
    "desktop_research": "桌面研究（竞品舆情/资料整理）",
    "issue_list": "问题清单执行", "insight_proposal": "洞察提案能力",
    "skills_debug": "Skills生成/调试（AI工具）",
    "agent_debug": "Agent生成/调试", "knowledge_base": "AI知识库建设",
    "interview_selection": "访谈执行-玩家甄别",
    "online_interview": "访谈执行-线上访谈",
    "field_interview": "访谈执行-田野调查/外访",
    "questionnaire_design": "访谈提纲/问卷设计",
    "questionnaire_analysis": "问卷调研（录入整理/分析）",
    "lab_assist": "实验室测试协助执行", "lab_leader": "实验室测试主负责/主持",
    "data_warehouse": "数仓工作（日常报表）",
    "data_query": "数据查询/报表开发", "web_crawl": "爬虫/数据收集",
    "deep_assessment": "深度测评能力",
    "commercial_research": "商业化研究与分析",
    "excel_level": "Excel技能等级", "spss_level": "SPSS技能等级",
    "language_ability": "语言能力",
    "category_moba": "品类-MOBA类（英雄联盟、王者荣耀等）",
    "category_mmorgp": "品类-MMORPG（逆水寒、梦幻西游等）",
    "category_openworld_rpg": "品类-开放世界RPG（塞尔达，原神等）",
    "category_card_rpg": "品类-卡牌RPG类（阴阳师、崩坏：星穹铁道等）",
    "category_tactical": "品类-战术竞技类（PUBG、和平精英等）",
    "category_shooter": "品类-射击类（穿越火线、CODM等）",
    "category_strategy_slg": "品类-策略/SLG类（文明、率土之滨等）",
    "category_action_fight": "品类-动作/格斗类（只狼、崩坏等）",
    "category_sandbox_survival": "品类-沙盒/生存类（我的世界、明日之后等）",
    "category_autochess": "品类-自走棋类（金铲铲、多多自走棋等）",
    "category_casual_puzzle": "品类-休闲益智类（羊了个羊、消消乐等）",
    "category_party": "品类-休闲竞技/派对类（蛋仔派对、鹅鸭杀等）",
    "category_etc": "品类-其他（自填）",
    "key_game_1": "重点游戏-逆水寒", "key_game_2": "重点游戏-燕云十六声",
    "key_game_3": "重点游戏-一梦江湖", "key_game_4": "重点游戏-阴阳师",
    "key_game_5": "重点游戏-金铲铲之战", "key_game_6": "重点游戏-蛋仔派对",
    "key_game_7": "重点游戏-无尽冬日", "key_game_8": "重点游戏-率土之滨",
    "key_game_9": "重点游戏-王者荣耀", "key_game_10": "重点游戏-英雄联盟",
    "key_game_11": "重点游戏-明日之后", "key_game_12": "重点游戏-萤火突击",
    "key_game_13": "重点游戏-三角洲行动",
    "deep_game_1": "深度游戏1", "deep_game_2": "深度游戏2", "deep_game_3": "深度游戏3",
    "proficient_products": "精通产品（1000h+）",
    "familiar_products": "熟悉产品（500h+）",
    "other_game_experience": "其他游戏经历补充",
}
TALENT_FIELDS = list(COLUMN_MAP.keys())


# ============================================================
# 数据库初始化
# ============================================================
def init_db():
    conn = get_db()
    cursor = conn.cursor()

    if DATABASE_URL:
        # PostgreSQL 模式
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS talents (
                id SERIAL PRIMARY KEY,
                name TEXT,
                gender TEXT,
                birth_date TEXT,
                identity_tag TEXT,
                city TEXT,
                city_level TEXT,
                school TEXT,
                major TEXT,
                education TEXT,
                graduate_year TEXT,
                phone TEXT,
                wechat TEXT,
                project_count TEXT,
                avg_rating TEXT,
                month_rating TEXT,
                overall_summary TEXT,
                detailed_review TEXT,
                exam_score TEXT,
                basic_test TEXT,
                desktop_research TEXT,
                issue_list TEXT,
                insight_proposal TEXT,
                skills_debug TEXT,
                agent_debug TEXT,
                knowledge_base TEXT,
                interview_selection TEXT,
                online_interview TEXT,
                field_interview TEXT,
                questionnaire_design TEXT,
                questionnaire_analysis TEXT,
                lab_assist TEXT,
                lab_leader TEXT,
                data_warehouse TEXT,
                data_query TEXT,
                web_crawl TEXT,
                deep_assessment TEXT,
                commercial_research TEXT,
                excel_level TEXT,
                spss_level TEXT,
                language_ability TEXT,
                category_moba TEXT,
                category_mmorgp TEXT,
                category_openworld_rpg TEXT,
                category_card_rpg TEXT,
                category_tactical TEXT,
                category_shooter TEXT,
                category_strategy_slg TEXT,
                category_action_fight TEXT,
                category_sandbox_survival TEXT,
                category_autochess TEXT,
                category_casual_puzzle TEXT,
                category_party TEXT,
                category_etc TEXT,
                key_game_1 TEXT,
                key_game_2 TEXT,
                key_game_3 TEXT,
                key_game_4 TEXT,
                key_game_5 TEXT,
                key_game_6 TEXT,
                key_game_7 TEXT,
                key_game_8 TEXT,
                key_game_9 TEXT,
                key_game_10 TEXT,
                key_game_11 TEXT,
                key_game_12 TEXT,
                key_game_13 TEXT,
                deep_game_1 TEXT,
                deep_game_2 TEXT,
                deep_game_3 TEXT,
                proficient_products TEXT,
                familiar_products TEXT,
                other_game_experience TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS demands (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                requirements TEXT,
                business_type TEXT NOT NULL,
                tier TEXT NOT NULL,
                quantity INTEGER DEFAULT 1,
                brush_list INTEGER DEFAULT 0,
                gmv REAL DEFAULT 0,
                scheduled_hours REAL DEFAULT 0,
                end_time TEXT,
                cross_meal_count INTEGER DEFAULT 0,
                human_cost REAL DEFAULT 0,
                budget_min REAL,
                budget_max REAL,
                deadline TEXT,
                demander_id INTEGER,
                tidanren TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS demand_quotes (
                id SERIAL PRIMARY KEY,
                demand_id INTEGER NOT NULL,
                part_time_wage REAL NOT NULL,
                human_cost REAL DEFAULT 0,
                total_quote REAL NOT NULL,
                quote_note TEXT,
                status TEXT DEFAULT 'pending',
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT NOW(),
                confirmed_at TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS demand_applications (
                id SERIAL PRIMARY KEY,
                demand_id INTEGER NOT NULL,
                talent_id INTEGER NOT NULL,
                status TEXT DEFAULT 'applied',
                applied_at TIMESTAMP DEFAULT NOW(),
                selected_at TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS demand_evaluations (
                id SERIAL PRIMARY KEY,
                demand_id INTEGER NOT NULL,
                talent_id INTEGER NOT NULL,
                rating INTEGER,
                comment TEXT,
                evaluated_by INTEGER,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
    else:
        # SQLite 本地开发模式
        cols = ["id INTEGER PRIMARY KEY AUTOINCREMENT"]
        for f in TALENT_FIELDS:
            cols.append(f"{f} TEXT")
        cols.extend(["created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP", "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"])
        cursor.execute(f"CREATE TABLE IF NOT EXISTS talents ({', '.join(cols)})")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS demands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                requirements TEXT,
                business_type TEXT NOT NULL,
                tier TEXT NOT NULL,
                quantity INTEGER DEFAULT 1,
                brush_list INTEGER DEFAULT 0,
                gmv REAL DEFAULT 0,
                scheduled_hours REAL DEFAULT 0,
                end_time TEXT,
                cross_meal_count INTEGER DEFAULT 0,
                human_cost REAL DEFAULT 0,
                budget_min REAL,
                budget_max REAL,
                deadline TEXT,
                demander_id INTEGER,
                tidanren TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS demand_quotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                demand_id INTEGER NOT NULL,
                part_time_wage REAL NOT NULL,
                human_cost REAL DEFAULT 0,
                total_quote REAL NOT NULL,
                quote_note TEXT,
                status TEXT DEFAULT 'pending',
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                confirmed_at TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS demand_applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                demand_id INTEGER NOT NULL,
                talent_id INTEGER NOT NULL,
                status TEXT DEFAULT 'applied',
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                selected_at TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS demand_evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                demand_id INTEGER NOT NULL,
                talent_id INTEGER NOT NULL,
                rating INTEGER,
                comment TEXT,
                evaluated_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    close_conn(conn)


def ensure_admin():
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
    else:
        cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)"
            if DATABASE_URL else
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            ('admin', 'admin123', 'admin')
        )
        close_conn(conn)
    else:
        close_conn(conn)

try:
    init_db()
    ensure_admin()
    _db_init_ok = True
except Exception as e:
    print(f"[WARN] 数据库初始化失败（稍后可访问 /api/init 重试）: {e}")
    _db_init_ok = False


# ============================================================
# 调试用：手动初始化数据库（部署后调用一次即可）
# ============================================================
@app.route('/api/init', methods=['GET'])
def manual_init():
    import traceback
    try:
        init_db()
        ensure_admin()
        _db_init_ok = True
        return jsonify({'message': '数据库初始化完成'})
    except Exception as e:
        import sys
        tb = traceback.format_exception(type(e), e, e.__traceback__)
        tb_str = ''.join(tb)
        # 找最后一个有价值的行
        lines = [l for l in tb_str.split('\n') if 'app.py' in l]
        last_app_line = lines[-1].strip() if lines else tb_str[-200:]
        return jsonify({'error': str(e), 'type': type(e).__name__, 'location': last_app_line}), 500


# ============================================================
# 路由和 API
# ============================================================

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/system/status', methods=['GET'])
def system_status():
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("SELECT COUNT(*) FROM users")
    else:
        cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    if DATABASE_URL:
        cursor.execute("SELECT id, username, role FROM users")
    else:
        cursor.execute("SELECT id, username, role FROM users")
    users = fetchall_dicts(cursor)
    close_conn(conn)
    return jsonify({'has_users': count > 0, 'user_count': count, 'users': users})


@app.route('/api/system/reset-admin', methods=['POST'])
def reset_admin():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users")
    if DATABASE_URL:
        cursor.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                       ('admin', 'admin123', 'admin'))
    else:
        cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                       ('admin', 'admin123', 'admin'))
    close_conn(conn)
    return jsonify({'message': 'admin/admin123 已重置'})


@app.route('/api/system/setup', methods=['POST'])
def system_setup():
    data = request.json
    users_to_create = data.get('users', [])
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] > 1:
        close_conn(conn)
        return jsonify({'error': '系统已有多个账号'}), 403
    if not (1 <= len(users_to_create) <= 5):
        close_conn(conn)
        return jsonify({'error': '请创建1~5个账号'}), 400
    usernames = [u.get('username', '').strip() for u in users_to_create]
    if len(usernames) != len(set(usernames)):
        close_conn(conn)
        return jsonify({'error': '用户名不能重复'}), 400
    cursor.execute("DELETE FROM users WHERE username != 'admin'")
    for u in users_to_create:
        uname = u.get('username', '').strip()
        pwd = u.get('password', '').strip()
        role = u.get('role', 'user').strip()
        if DATABASE_URL:
            cursor.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                           (uname, pwd, role))
        else:
            cursor.execute("INSERT OR REPLACE INTO users (username, password, role) VALUES (?, ?, ?)",
                           (uname, pwd, role))
    close_conn(conn)
    return jsonify({'message': f'成功创建 {len(users_to_create)} 个账号'})


@app.route('/api/users', methods=['GET'])
def list_users():
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("SELECT id, username, role, created_at FROM users ORDER BY id")
    else:
        cursor.execute("SELECT id, username, role, created_at FROM users ORDER BY id")
    users = fetchall_dicts(cursor)
    close_conn(conn)
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
    if cursor.fetchone()[0] >= 200:
        close_conn(conn)
        return jsonify({'error': '最多只能创建200个账号'}), 400
    try:
        if DATABASE_URL:
            cursor.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                           (username, password, role))
            cursor.execute("SELECT lastval()")
            user_id = cursor.fetchone()[0]
        else:
            cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                           (username, password, role))
            user_id = cursor.lastrowid
        close_conn(conn)
        return jsonify({'id': user_id, 'message': '账号创建成功'})
    except Exception as e:
        close_conn(conn)
        err_msg = str(e)
        if 'unique' in err_msg.lower() or 'duplicate' in err_msg.lower():
            return jsonify({'error': '用户名已存在'}), 400
        return jsonify({'error': err_msg}), 400


@app.route('/api/users/import', methods=['POST'])
def import_users():
    """批量导入账号（Excel 文件）"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    file = request.files['file']
    if not file.filename.endswith(('.xlsx', '.xls')):
        return jsonify({'error': '请上传 Excel 文件'}), 400
    try:
        df = pd.read_excel(file)
        # 验证必需列
        required_cols = ['username', 'password']
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            return jsonify({'error': f'Excel 缺少必需列: {", ".join(missing)}，可选列: role'}), 400

        conn = get_db()
        cursor = conn.cursor()
        imported, skipped, errors = 0, 0, []

        for idx, row in df.iterrows():
            username = str(row.get('username', '')).strip()
            password = str(row.get('password', '')).strip()
            role = str(row.get('role', 'user')).strip() or 'user'

            if not username or not password:
                skipped += 1
                continue

            # 限制总数不超过 200 个
            cursor.execute("SELECT COUNT(*) FROM users")
            if cursor.fetchone()[0] >= 200:
                skipped += 1
                errors.append(f"第{idx+2}行: 已达到账号上限（200个）")
                continue

            try:
                if DATABASE_URL:
                    cursor.execute(
                        "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                        (username, password, role))
                else:
                    cursor.execute(
                        "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                        (username, password, role))
                imported += 1
            except Exception as e:
                skipped += 1
                err_msg = str(e)
                if 'unique' in err_msg.lower() or 'duplicate' in err_msg.lower():
                    errors.append(f"第{idx+2}行「{username}」: 用户名已存在")
                else:
                    errors.append(f"第{idx+2}行「{username}」: {err_msg}")

        close_conn(conn)
        msg = f'成功导入 {imported} 个账号'
        if skipped:
            msg += f'，跳过 {skipped} 行'
        return jsonify({'message': msg, 'count': imported, 'skipped': skipped, 'errors': errors[:20]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
    else:
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    close_conn(conn)
    return jsonify({'message': '删除成功'})


@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s",
                       (username, password))
    else:
        cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?",
                       (username, password))
    user = fetchone_dict(cursor)
    if user:
        result = {'success': True, 'user': {'id': user['id'], 'username': user['username'], 'role': user['role']}}
        close_conn(conn)
        return jsonify(result)
    close_conn(conn)
    return jsonify({'success': False, 'error': 'Invalid credentials'}), 401


# ============================================================
# 公开报名 API（无需登录）
# ============================================================
@app.route('/api/talents/register', methods=['POST'])
def register_talent():
    """公开报名接口：姓名 + 手机号 + 空闲时间 + 游戏经历"""
    data = request.json
    name = str(data.get('name', '')).strip()
    phone = str(data.get('phone', '')).strip()
    available_time = str(data.get('available_time', '')).strip()
    game_experience = str(data.get('game_experience', '')).strip()

    if not name or not phone:
        return jsonify({'error': '姓名和手机号不能为空'}), 400

    conn = get_db()
    cursor = conn.cursor()

    # 检查是否已报名
    if DATABASE_URL:
        cursor.execute("SELECT id FROM talents WHERE phone = %s", (phone,))
    else:
        cursor.execute("SELECT id FROM talents WHERE phone = ?", (phone,))
    existing = fetchone_dict(cursor)
    if existing:
        cursor.execute("""
            UPDATE talents SET name = %s, available_time = %s, game_experience = %s, updated_at = NOW()
            WHERE phone = %s
        """ if DATABASE_URL else """
            UPDATE talents SET name = ?, available_time = ?, game_experience = ?, updated_at = CURRENT_TIMESTAMP
            WHERE phone = ?
        """, (name, available_time, game_experience, phone))
        close_conn(conn)
        return jsonify({'message': '报名信息已更新', 'phone': phone})

    # 新报名
    if DATABASE_URL:
        cursor.execute("""
            INSERT INTO talents (name, phone, available_time, game_experience, updated_at)
            VALUES (%s, %s, %s, %s, NOW())
        """, (name, phone, available_time, game_experience))
    else:
        cursor.execute("""
            INSERT INTO talents (name, phone, available_time, game_experience, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (name, phone, available_time, game_experience))
    close_conn(conn)
    return jsonify({'message': '报名成功', 'phone': phone})


@app.route('/api/talents/register/status', methods=['GET'])
def check_registration_status():
    """公开查询接口：输入手机号查询是否入选"""
    phone = request.args.get('phone', '').strip()
    if not phone:
        return jsonify({'error': '手机号不能为空'}), 400

    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("""
            SELECT t.name, t.phone, t.registration_status,
                   da.status as application_status, da.selected_at,
                   d.title as demand_title, d.business_type, d.tier
            FROM talents t
            LEFT JOIN demand_applications da ON da.talent_id = t.id
            LEFT JOIN demands d ON da.demand_id = d.id
            WHERE t.phone = %s
            ORDER BY da.applied_at DESC
            LIMIT 1
        """, (phone,))
    else:
        cursor.execute("""
            SELECT t.name, t.phone, t.registration_status,
                   da.status as application_status, da.selected_at,
                   d.title as demand_title, d.business_type, d.tier
            FROM talents t
            LEFT JOIN demand_applications da ON da.talent_id = t.id
            LEFT JOIN demands d ON da.demand_id = d.id
            WHERE t.phone = ?
            ORDER BY da.applied_at DESC
            LIMIT 1
        """, (phone,))
    row = fetchone_dict(cursor)
    close_conn(conn)

    if not row:
        return jsonify({'found': False, 'message': '未找到报名记录'})

    status_text = {
        None: '待审核',
        'pending': '审核中',
        'selected': '已入选',
        'rejected': '未入选'
    }.get(row.get('application_status'), '待审核')

    return jsonify({
        'found': True,
        'name': row.get('name'),
        'status': status_text,
        'demand_title': row.get('demand_title'),
        'business_type': row.get('business_type'),
        'tier': row.get('tier'),
        'selected_at': row.get('selected_at')
    })


# ---- 人才管理 API ----

@app.route('/api/talents', methods=['GET'])
def get_talents():
    conn = get_db()
    cursor = conn.cursor()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '')
    filters = request.args.get('filters', '')
    offset = (page - 1) * per_page

    base_query = "SELECT * FROM talents WHERE 1=1"
    count_query = "SELECT COUNT(*) FROM talents WHERE 1=1"
    params = []
    count_params = []

    if search:
        if DATABASE_URL:
            search_clause = " AND (name ILIKE %s OR school ILIKE %s OR major ILIKE %s OR phone ILIKE %s)"
        else:
            search_clause = " AND (name LIKE ? OR school LIKE ? OR major LIKE ? OR phone LIKE ?)"
        base_query += search_clause
        count_query += search_clause
        pattern = f'%{search}%'
        params.extend([pattern] * 4)
        count_params.extend([pattern] * 4)

    if filters:
        try:
            fd = eval(filters)
            for k, v in fd.items():
                if v:
                    if DATABASE_URL:
                        base_query += f" AND {k} = %s"
                        count_query += f" AND {k} = %s"
                        params.append(v)
                        count_params.append(v)
                    else:
                        base_query += f" AND {k} = ?"
                        count_query += f" AND {k} = ?"
                        params.append(v)
                        count_params.append(v)
        except Exception:
            pass

    # total count
    cursor.execute(count_query, count_params)
    total = cursor.fetchone()[0]

    # data with pagination
    if DATABASE_URL:
        base_query += " ORDER BY id DESC LIMIT %s OFFSET %s"
    else:
        base_query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([per_page, offset])
    cursor.execute(base_query, params)
    rows = fetchall_dicts(cursor)
    close_conn(conn)
    return jsonify({
        'data': rows,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page
    })


@app.route('/api/talents/<int:talent_id>', methods=['GET'])
def get_talent(talent_id):
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("SELECT * FROM talents WHERE id = %s", (talent_id,))
    else:
        cursor.execute("SELECT * FROM talents WHERE id = ?", (talent_id,))
    row = fetchone_dict(cursor)
    close_conn(conn)
    if row:
        return jsonify(row)
    return jsonify({'error': 'Not found'}), 404


@app.route('/api/talents', methods=['POST'])
def create_talent():
    data = request.json
    conn = get_db()
    cursor = conn.cursor()
    fields, placeholders, values = [], [], []
    for field in TALENT_FIELDS:
        if field in data and data[field] not in (None, ''):
            fields.append(field)
            if DATABASE_URL:
                placeholders.append('%s')
            else:
                placeholders.append('?')
            values.append(data[field])
    if fields:
        if DATABASE_URL:
            cursor.execute(
                f"INSERT INTO talents ({', '.join(fields)}) VALUES ({', '.join(placeholders)})",
                values)
        else:
            cursor.execute(
                f"INSERT INTO talents ({', '.join(fields)}) VALUES ({', '.join(placeholders)})",
                values)
        talent_id = cursor.lastrowid
        close_conn(conn)
    else:
        close_conn(conn)
        return jsonify({'id': None, 'message': '创建成功（无字段）'})
    return jsonify({'id': talent_id, 'message': '创建成功'})


@app.route('/api/talents/<int:talent_id>', methods=['PUT'])
def update_talent(talent_id):
    data = request.json
    conn = get_db()
    cursor = conn.cursor()
    updates, values = [], []
    for field in TALENT_FIELDS:
        if field in data:
            updates.append(f"{field} = %s" if DATABASE_URL else f"{field} = ?")
            values.append(data[field])
    if updates:
        if DATABASE_URL:
            updates.append("updated_at = NOW()")
            cursor.execute(f"UPDATE talents SET {', '.join(updates)} WHERE id = %s",
                           values + [talent_id])
        else:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            cursor.execute(f"UPDATE talents SET {', '.join(updates)} WHERE id = ?",
                           values + [talent_id])
        close_conn(conn)
    else:
        close_conn(conn)
    return jsonify({'message': '更新成功'})


@app.route('/api/talents/<int:talent_id>', methods=['DELETE'])
def delete_talent(talent_id):
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("DELETE FROM talents WHERE id = %s", (talent_id,))
    else:
        cursor.execute("DELETE FROM talents WHERE id = ?", (talent_id,))
    close_conn(conn)
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
        imported, errors = 0, []
        for idx, row in df.iterrows():
            fields, placeholders, values = [], [], []
            for col_name in df.columns:
                col_str = str(col_name).strip()
                field = None
                if col_str in COLUMN_MAP.values():
                    field = [k for k, v in COLUMN_MAP.items() if v == col_str][0]
                elif col_str in COLUMN_MAP:
                    field = col_str
                if field:
                    value = row[col_name]
                    if pd.notna(value):
                        fields.append(field)
                        if DATABASE_URL:
                            placeholders.append('%s')
                        else:
                            placeholders.append('?')
                        values.append(str(value))
            if fields:
                try:
                    if DATABASE_URL:
                        cursor.execute(
                            f"INSERT INTO talents ({', '.join(fields)}) VALUES ({', '.join(placeholders)})",
                            values)
                    else:
                        cursor.execute(
                            f"INSERT INTO talents ({', '.join(fields)}) VALUES ({', '.join(placeholders)})",
                            values)
                    imported += 1
                except Exception as e:
                    errors.append(f"第{idx+2}行: {str(e)}")
        close_conn(conn)
        msg = f'成功导入 {imported} 条记录'
        if errors:
            msg += f'，{len(errors)} 行失败'
        return jsonify({'message': msg, 'count': imported, 'errors': errors[:10]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/talents/export', methods=['GET'])
def export_talents():
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("SELECT * FROM talents ORDER BY id DESC")
    else:
        cursor.execute("SELECT * FROM talents ORDER BY id DESC")
    rows = fetchall_dicts(cursor)
    close_conn(conn)
    if not rows:
        return jsonify({'error': 'No data'}), 400
    df = pd.DataFrame(rows)
    for col in ['created_at', 'updated_at']:
        if col in df.columns:
            df = df.drop(columns=[col])
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='人才库')
    output.seek(0)
    return send_file(output,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True,
                     download_name=f'人才库_{datetime.now().strftime("%Y%m%d")}.xlsx')


@app.route('/api/stats', methods=['GET'])
def get_stats():
    conn = get_db()
    cursor = conn.cursor()
    stats = {}
    if DATABASE_URL:
        cursor.execute("SELECT COUNT(*) FROM talents")
    else:
        cursor.execute("SELECT COUNT(*) FROM talents")
    stats['total'] = cursor.fetchone()[0]
    for col, name in [('education', 'education'), ('identity_tag', 'identity_tag'),
                      ('city', 'city'), ('month_rating', 'month_rating')]:
        if DATABASE_URL:
            cursor.execute(f"SELECT {col}, COUNT(*) as c FROM talents WHERE {col} IS NOT NULL AND {col} != '' GROUP BY {col}")
        else:
            cursor.execute(f"SELECT {col}, COUNT(*) as c FROM talents WHERE {col} IS NOT NULL AND {col} != '' GROUP BY {col}")
        stats[name] = {row[0]: row[1] for row in cursor.fetchall()}
    skill_fields = ['basic_test', 'desktop_research', 'issue_list', 'insight_proposal',
                    'skills_debug', 'agent_debug', 'knowledge_base', 'interview_selection',
                    'online_interview', 'field_interview', 'questionnaire_design',
                    'questionnaire_analysis', 'lab_assist', 'lab_leader']
    stats['skills'] = {}
    for field in skill_fields:
        if DATABASE_URL:
            cursor.execute(f"SELECT COUNT(*) FROM talents WHERE {field} = '精通'")
        else:
            cursor.execute(f"SELECT COUNT(*) FROM talents WHERE {field} = '精通'")
        stats['skills'][field] = cursor.fetchone()[0]
    close_conn(conn)
    return jsonify(stats)


# ============================================================
# 需求接单模块 API
# ============================================================

@app.route('/api/demand/meta', methods=['GET'])
def demand_meta():
    result = {}
    for biz, tiers in TALENT_PRICE_TABLE.items():
        tiers_out = []
        for t in tiers:
            tiers_out.append({
                "label": t["label"],
                "price": t.get("price"),
                "base": t.get("base"),
                "gmv_rate": t.get("gmv_rate"),
                "gmv_rate_display": t.get("gmv_rate_display"),
                "fixed": t.get("fixed"),
            })
        result[biz] = tiers_out
    return jsonify(result)


@app.route('/api/demands', methods=['GET'])
def get_demands():
    conn = get_db()
    cursor = conn.cursor()
    status = request.args.get('status', '')
    role = request.args.get('role', '')
    user_id = request.args.get('user_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    offset = (page - 1) * per_page

    if DATABASE_URL:
        base_query = """
            SELECT d.*, u.username as demander_name
            FROM demands d
            LEFT JOIN users u ON d.demander_id = u.id
            WHERE 1=1
        """
        count_query = "SELECT COUNT(*) FROM demands d WHERE 1=1"
        params = []
        count_params = []
        if status:
            base_query += " AND d.status = %s"
            count_query += " AND d.status = %s"
            params.append(status)
            count_params.append(status)
        if role == 'demander' and user_id:
            base_query += " AND d.demander_id = %s"
            count_query += " AND d.demander_id = %s"
            params.append(user_id)
            count_params.append(user_id)
        cursor.execute(count_query, count_params)
        total = cursor.fetchone()[0]
        base_query += " ORDER BY d.id DESC LIMIT %s OFFSET %s"
        params.extend([per_page, offset])
        cursor.execute(base_query, params)
    else:
        base_query = """
            SELECT d.*, u.username as demander_name
            FROM demands d
            LEFT JOIN users u ON d.demander_id = u.id
            WHERE 1=1
        """
        count_query = "SELECT COUNT(*) FROM demands d WHERE 1=1"
        params = []
        count_params = []
        if status:
            base_query += " AND d.status = ?"
            count_query += f" AND d.status = '{status}'"
            params.append(status)
            count_params.append(status)
        if role == 'demander' and user_id:
            base_query += " AND d.demander_id = ?"
            count_query += f" AND d.demander_id = {user_id}"
            params.append(user_id)
            count_params.append(user_id)
        cursor.execute(count_query, count_params)
        total = cursor.fetchone()[0]
        base_query += " ORDER BY d.id DESC LIMIT ? OFFSET ?"
        params.extend([per_page, offset])
        cursor.execute(base_query, params)

    rows = fetchall_dicts(cursor)
    close_conn(conn)
    return jsonify({'data': rows, 'total': total, 'page': page, 'per_page': per_page})


@app.route('/api/demands/<int:demand_id>', methods=['GET'])
def get_demand(demand_id):
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("""
            SELECT d.*, u.username as demander_name
            FROM demands d
            LEFT JOIN users u ON d.demander_id = u.id
            WHERE d.id = %s
        """, (demand_id,))
    else:
        cursor.execute("""
            SELECT d.*, u.username as demander_name
            FROM demands d
            LEFT JOIN users u ON d.demander_id = u.id
            WHERE d.id = ?
        """, (demand_id,))
    row = fetchone_dict(cursor)
    close_conn(conn)
    if row:
        return jsonify(row)
    return jsonify({'error': 'Not found'}), 404


@app.route('/api/demands', methods=['POST'])
def create_demand():
    data = request.json
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("""
            INSERT INTO demands (
                title, description, requirements, business_type, tier,
                quantity, brush_list, gmv,
                scheduled_hours, end_time, cross_meal_count,
                human_cost, budget_min, budget_max,
                deadline, demander_id, tidanren, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
        """, (
            data.get('title', ''), data.get('description', ''), data.get('requirements', ''),
            data.get('business_type', ''), data.get('tier', ''),
            data.get('quantity', 1),
            1 if data.get('brush_list') else 0,
            data.get('gmv', 0),
            data.get('scheduled_hours', 0), data.get('end_time', ''), data.get('cross_meal_count', 0),
            data.get('human_cost', 0),
            data.get('budget_min'), data.get('budget_max'),
            data.get('deadline'), data.get('demander_id'), data.get('tidanren'),
        ))
        demand_id = cursor.lastrowid
    else:
        cursor.execute("""
            INSERT INTO demands (
                title, description, requirements, business_type, tier,
                quantity, brush_list, gmv,
                scheduled_hours, end_time, cross_meal_count,
                human_cost, budget_min, budget_max,
                deadline, demander_id, tidanren, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        """, (
            data.get('title', ''), data.get('description', ''), data.get('requirements', ''),
            data.get('business_type', ''), data.get('tier', ''),
            data.get('quantity', 1),
            1 if data.get('brush_list') else 0,
            data.get('gmv', 0),
            data.get('scheduled_hours', 0), data.get('end_time', ''), data.get('cross_meal_count', 0),
            data.get('human_cost', 0),
            data.get('budget_min'), data.get('budget_max'),
            data.get('deadline'), data.get('demander_id'), data.get('tidanren'),
        ))
        demand_id = cursor.lastrowid
    close_conn(conn)
    return jsonify({'id': demand_id, 'message': '需求创建成功'})


@app.route('/api/demands/<int:demand_id>', methods=['PUT'])
def update_demand(demand_id):
    data = request.json
    conn = get_db()
    cursor = conn.cursor()
    if 'status' in data:
        if DATABASE_URL:
            cursor.execute(
                "UPDATE demands SET status = %s, updated_at = NOW() WHERE id = %s",
                (data['status'], demand_id))
        else:
            cursor.execute(
                "UPDATE demands SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (data['status'], demand_id))
    close_conn(conn)
    return jsonify({'message': '更新成功'})


@app.route('/api/demands/<int:demand_id>', methods=['DELETE'])
def delete_demand(demand_id):
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute('DELETE FROM demands WHERE id = %s', (demand_id,))
    else:
        cursor.execute('DELETE FROM demands WHERE id = ?', (demand_id,))
    close_conn(conn)
    return jsonify({'message': '删除成功'})


# ---- 报价 API ----

@app.route('/api/demands/<int:demand_id>/calc-quote', methods=['POST'])
def calc_demand_quote(demand_id):
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute('SELECT * FROM demands WHERE id = %s', (demand_id,))
    else:
        cursor.execute('SELECT * FROM demands WHERE id = ?', (demand_id,))
    demand = fetchone_dict(cursor)
    close_conn(conn)
    if not demand:
        return jsonify({'error': '需求不存在'}), 404
    demand_data = {
        'business_type': demand['business_type'],
        'tier': demand['tier'],
        'quantity': demand['quantity'],
        'brush_list': bool(demand['brush_list']),
        'gmv': demand['gmv'] or 0,
        'scheduled_hours': demand['scheduled_hours'] or 0,
        'end_time': demand['end_time'] or '',
        'cross_meal_count': demand['cross_meal_count'] or 0,
    }
    result = calc_quote(demand_data)
    if 'error' in result:
        return jsonify(result), 400
    return jsonify(result)


@app.route('/api/demands/<int:demand_id>/quote', methods=['POST'])
def save_quote(demand_id):
    data = request.json
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute('SELECT id FROM demand_quotes WHERE demand_id = %s', (demand_id,))
    else:
        cursor.execute('SELECT id FROM demand_quotes WHERE demand_id = ?', (demand_id,))
    existing = cursor.fetchone()
    if existing:
        if DATABASE_URL:
            cursor.execute("""
                UPDATE demand_quotes SET
                    part_time_wage = %s, human_cost = %s, total_quote = %s,
                    quote_note = %s, status = 'pending'
                WHERE demand_id = %s
            """, (data['part_time_wage'], data['human_cost'],
                 data['total_quote'], data.get('note', ''), demand_id))
        else:
            cursor.execute("""
                UPDATE demand_quotes SET
                    part_time_wage = ?, human_cost = ?, total_quote = ?,
                    quote_note = ?, status = 'pending'
                WHERE demand_id = ?
            """, (data['part_time_wage'], data['human_cost'],
                 data['total_quote'], data.get('note', ''), demand_id))
        quote_id = existing['id'] if hasattr(existing, '__getitem__') else existing[0]
    else:
        if DATABASE_URL:
            cursor.execute("""
                INSERT INTO demand_quotes
                    (demand_id, part_time_wage, human_cost, total_quote, quote_note, status)
                VALUES (%s, %s, %s, %s, %s, 'pending')
            """, (demand_id, data['part_time_wage'], data['human_cost'],
                 data['total_quote'], data.get('note', '')))
        else:
            cursor.execute("""
                INSERT INTO demand_quotes
                    (demand_id, part_time_wage, human_cost, total_quote, quote_note, status)
                VALUES (?, ?, ?, ?, ?, 'pending')
            """, (demand_id, data['part_time_wage'], data['human_cost'],
                 data['total_quote'], data.get('note', '')))
        quote_id = cursor.lastrowid
    close_conn(conn)
    return jsonify({'id': quote_id, 'message': '报价已保存'})


@app.route('/api/demands/<int:demand_id>/quote', methods=['GET'])
def get_quote(demand_id):
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute('SELECT * FROM demand_quotes WHERE demand_id = %s', (demand_id,))
    else:
        cursor.execute('SELECT * FROM demand_quotes WHERE demand_id = ?', (demand_id,))
    row = fetchone_dict(cursor)
    close_conn(conn)
    if row:
        return jsonify(row)
    return jsonify({})


@app.route('/api/demands/<int:demand_id>/quote/confirm', methods=['POST'])
def confirm_quote(demand_id):
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("""
            UPDATE demand_quotes SET status = 'confirmed', confirmed_at = NOW()
            WHERE demand_id = %s
        """, (demand_id,))
        cursor.execute("""
            UPDATE demands SET status = 'recruiting', updated_at = NOW()
            WHERE id = %s
        """, (demand_id,))
    else:
        cursor.execute("""
            UPDATE demand_quotes SET status = 'confirmed', confirmed_at = CURRENT_TIMESTAMP
            WHERE demand_id = ?
        """, (demand_id,))
        cursor.execute("""
            UPDATE demands SET status = 'recruiting', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (demand_id,))
    close_conn(conn)
    return jsonify({'message': '报价已确认，进入招募阶段'})


# ---- 报名 API ----

@app.route('/api/demands/<int:demand_id>/apply', methods=['POST'])
def apply_demand(demand_id):
    data = request.json
    talent_id = data.get('talent_id')
    if not talent_id:
        return jsonify({'error': 'talent_id required'}), 400
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute('SELECT id FROM demand_applications WHERE demand_id = %s AND talent_id = %s',
                     (demand_id, talent_id))
    else:
        cursor.execute('SELECT id FROM demand_applications WHERE demand_id = ? AND talent_id = ?',
                     (demand_id, talent_id))
    if cursor.fetchone():
        close_conn(conn)
        return jsonify({'error': '已经报名过了'}), 400
    if DATABASE_URL:
        cursor.execute("""
            INSERT INTO demand_applications (demand_id, talent_id, status)
            VALUES (%s, %s, 'applied')
        """, (demand_id, talent_id))
    else:
        cursor.execute("""
            INSERT INTO demand_applications (demand_id, talent_id, status)
            VALUES (?, ?, 'applied')
        """, (demand_id, talent_id))
    app_id = cursor.lastrowid
    close_conn(conn)
    return jsonify({'id': app_id, 'message': '报名成功'})


@app.route('/api/demands/<int:demand_id>/applications', methods=['GET'])
def get_demand_applications(demand_id):
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("""
            SELECT da.*, t.name, t.phone, t.month_rating, t.avg_rating,
                   t.overall_summary, t.detailed_review
            FROM demand_applications da
            JOIN talents t ON da.talent_id = t.id
            WHERE da.demand_id = %s
            ORDER BY da.applied_at DESC
        """, (demand_id,))
    else:
        cursor.execute("""
            SELECT da.*, t.name, t.phone, t.month_rating, t.avg_rating,
                   t.overall_summary, t.detailed_review
            FROM demand_applications da
            JOIN talents t ON da.talent_id = t.id
            WHERE da.demand_id = ?
            ORDER BY da.applied_at DESC
        """, (demand_id,))
    rows = fetchall_dicts(cursor)
    close_conn(conn)
    return jsonify(rows)


@app.route('/api/applications/<int:app_id>/select', methods=['POST'])
def select_talent(app_id):
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("UPDATE demand_applications SET status = 'selected', selected_at = NOW() WHERE id = %s",
                     (app_id,))
    else:
        cursor.execute("UPDATE demand_applications SET status = 'selected', selected_at = CURRENT_TIMESTAMP WHERE id = ?",
                     (app_id,))
    close_conn(conn)
    return jsonify({'message': '已选中该人才'})


@app.route('/api/applications/<int:app_id>/reject', methods=['POST'])
def reject_talent(app_id):
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("UPDATE demand_applications SET status = 'rejected' WHERE id = %s", (app_id,))
    else:
        cursor.execute("UPDATE demand_applications SET status = 'rejected' WHERE id = ?", (app_id,))
    close_conn(conn)
    return jsonify({'message': '已拒绝'})


# ---- 评价 API ----

@app.route('/api/demands/<int:demand_id>/evaluations', methods=['GET'])
def get_evaluations(demand_id):
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("""
            SELECT de.*, t.name as talent_name, u.username as evaluator_name
            FROM demand_evaluations de
            JOIN talents t ON de.talent_id = t.id
            LEFT JOIN users u ON de.evaluated_by = u.id
            WHERE de.demand_id = %s
        """, (demand_id,))
    else:
        cursor.execute("""
            SELECT de.*, t.name as talent_name, u.username as evaluator_name
            FROM demand_evaluations de
            JOIN talents t ON de.talent_id = t.id
            LEFT JOIN users u ON de.evaluated_by = u.id
            WHERE de.demand_id = ?
        """, (demand_id,))
    rows = fetchall_dicts(cursor)
    close_conn(conn)
    return jsonify(rows)


@app.route('/api/demands/<int:demand_id>/evaluate', methods=['POST'])
def create_evaluation(demand_id):
    data = request.json
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("""
            INSERT INTO demand_evaluations
                (demand_id, talent_id, rating, comment, evaluated_by)
            VALUES (%s, %s, %s, %s, %s)
        """, (demand_id, data['talent_id'], data['rating'],
             data.get('comment', ''), data.get('evaluated_by')))
    else:
        cursor.execute("""
            INSERT INTO demand_evaluations
                (demand_id, talent_id, rating, comment, evaluated_by)
            VALUES (?, ?, ?, ?, ?)
        """, (demand_id, data['talent_id'], data['rating'],
             data.get('comment', ''), data.get('evaluated_by')))
    eval_id = cursor.lastrowid
    close_conn(conn)
    return jsonify({'id': eval_id, 'message': '评价已保存'})


# ---- 企微 Webhook ----

def get_setting(key, default=''):
    env_val = os.environ.get(key.upper())
    if env_val:
        return env_val
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute('SELECT value FROM system_settings WHERE key = %s', (key,))
    else:
        cursor.execute('SELECT value FROM system_settings WHERE key = ?', (key,))
    row = fetchone_dict(cursor)
    close_conn(conn)
    return row['value'] if row else default


def send_wecom_message(content):
    wecom_url = get_setting('wecom_webhook_url')
    if not wecom_url:
        return {'error': '企微 Webhook URL 未配置，请在系统设置中填写'}
    try:
        import urllib.request
        import json as json_lib
        payload = {
            "msgtype": "markdown",
            "markdown": {"content": content}
        }
        req = urllib.request.Request(
            wecom_url,
            data=json_lib.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json_lib.loads(resp.read().decode('utf-8'))
            if result.get('errcode') == 0:
                return {'success': True}
            return {'error': result.get('errmsg', '发送失败')}
    except Exception as e:
        return {'error': str(e)}


@app.route('/api/demands/<int:demand_id>/publish', methods=['POST'])
def publish_to_wecom(demand_id):
    wecom_url = get_setting('wecom_webhook_url')
    if not wecom_url:
        return jsonify({'error': '企微 Webhook URL 未配置'}), 400

    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("""
            SELECT d.*, u.username as demander_name
            FROM demands d
            LEFT JOIN users u ON d.demander_id = u.id
            WHERE d.id = %s
        """, (demand_id,))
    else:
        cursor.execute("""
            SELECT d.*, u.username as demander_name
            FROM demands d
            LEFT JOIN users u ON d.demander_id = u.id
            WHERE d.id = ?
        """, (demand_id,))
    demand = fetchone_dict(cursor)
    if not demand:
        close_conn(conn)
        return jsonify({'error': '需求不存在'}), 404

    if DATABASE_URL:
        cursor.execute("SELECT * FROM demand_quotes WHERE demand_id = %s AND status = 'confirmed'", (demand_id,))
    else:
        cursor.execute("SELECT * FROM demand_quotes WHERE demand_id = ? AND status = 'confirmed'", (demand_id,))
    quote = fetchone_dict(cursor)
    close_conn(conn)

    quote = quote if quote else None

    brush_str = "（刷名单）" if demand['brush_list'] else ""
    msg_title = demand['title'] or ""
    msg_biz = demand['business_type'] or ""
    msg_tier = demand['tier'] or ""
    msg_qty = demand['quantity'] or 0
    msg_deadline = demand['deadline'] or "待定"
    msg_desc = demand['description'] or "无"
    msg_demander_tidan = demand.get('tidanren', '') or demand.get('demander_name', '')

    if quote:
        pw = quote['part_time_wage'] or 0
        hc = quote['human_cost'] or 0
        total = quote['total_quote'] or 0
        quote_str = "%s元（兼职工资%s元 + 人力成本%s元）" % (total, pw, hc)
    else:
        quote_str = "待确认"

    msg = "### New 需求发布\n"
    msg += "**提单人：** %s\n" % msg_demander_tidan
    msg += "**需求标题：** %s\n" % msg_title
    msg += "**业务类型：** %s - %s %s\n" % (msg_biz, msg_tier, brush_str)
    msg += "**数量：** %s\n" % msg_qty
    msg += "**截止日期：** %s\n" % msg_deadline
    msg += "**需求描述：** %s\n" % msg_desc
    msg += "**报价：** %s\n" % quote_str
    msg += "---\n"
    msg += "> 点击报名：[系统链接](https://talent-management-web.onrender.com)"

    result = send_wecom_message(msg)
    if 'error' in result:
        return jsonify(result), 500
    return jsonify({'message': '已发送到企微群', 'result': result})


# ---- 人才端：我的报名 & 我的评价 ----

@app.route('/api/talents/<int:talent_id>/my-applications', methods=['GET'])
def my_applications(talent_id):
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("""
            SELECT da.*, d.title, d.business_type, d.tier, d.status as demand_status,
                   d.deadline, d.quantity, d.brush_list
            FROM demand_applications da
            JOIN demands d ON da.demand_id = d.id
            WHERE da.talent_id = %s
            ORDER BY da.applied_at DESC
        """, (talent_id,))
    else:
        cursor.execute("""
            SELECT da.*, d.title, d.business_type, d.tier, d.status as demand_status,
                   d.deadline, d.quantity, d.brush_list
            FROM demand_applications da
            JOIN demands d ON da.demand_id = d.id
            WHERE da.talent_id = ?
            ORDER BY da.applied_at DESC
        """, (talent_id,))
    rows = fetchall_dicts(cursor)
    close_conn(conn)
    return jsonify(rows)


@app.route('/api/talents/<int:talent_id>/my-evaluations', methods=['GET'])
def my_evaluations(talent_id):
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("""
            SELECT de.*, d.title as demand_title, u.username as evaluator_name
            FROM demand_evaluations de
            JOIN demands d ON de.demand_id = d.id
            LEFT JOIN users u ON de.evaluated_by = u.id
            WHERE de.talent_id = %s
            ORDER BY de.created_at DESC
        """, (talent_id,))
    else:
        cursor.execute("""
            SELECT de.*, d.title as demand_title, u.username as evaluator_name
            FROM demand_evaluations de
            JOIN demands d ON de.demand_id = d.id
            LEFT JOIN users u ON de.evaluated_by = u.id
            WHERE de.talent_id = ?
            ORDER BY de.created_at DESC
        """, (talent_id,))
    rows = fetchall_dicts(cursor)
    close_conn(conn)
    return jsonify(rows)


# ---- 系统设置 API ----

@app.route('/api/settings/<key>', methods=['GET'])
def get_setting_api(key):
    value = get_setting(key)
    return jsonify({'key': key, 'value': value})


@app.route('/api/settings/<key>', methods=['POST'])
def set_setting_api(key):
    data = request.json
    value = data.get('value', '')
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("""
            INSERT INTO system_settings (key, value) VALUES (%s, %s)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, value))
    else:
        cursor.execute("""
            INSERT INTO system_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, value))
    close_conn(conn)
    return jsonify({'message': '设置已保存', 'key': key, 'value': value})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
