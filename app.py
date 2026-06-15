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
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
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
TALENT_PRICE_TABLE =  {
    "甄别": [
        {"label": "5~10mins/个", "price": 8},
        {"label": "10~20mins/个", "price": 12},
        {"label": "20~30mins/个", "price": 16},
        {"label": ">30mins/个", "price": 26},
    ],
    "甄别+外呼": [
        {"label": "5~10mins/个", "price": 28},
        {"label": "10~20mins/个", "price": 32},
        {"label": "20~30mins/个", "price": 36},
        {"label": ">30mins/个", "price": 46},
    ],
    "电访": [
        {"label": "30mins以内/个", "price": 30},
        {"label": "30~60mins/个", "price": 45},
        {"label": "60~90mins/个（仅限5星兼职）", "price": 80},
        {"label": "90~120mins/个", "price": 100},
    ],
    "电访+外呼": [
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
    if biz in ("甄别", "电访", "街访执行", "测试执行") and not gmv:
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

    elif biz == "甄别":
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
        gmv_rate = tier_data.get("gmv_rate")
        if gmv_rate is not None:
            # 街访2：只拦截不访谈，按GMV比例
            base = tier_data.get("base", 120)
            part_time_wage = base + gmv * gmv_rate
            wage_note = f"120元/天底薪+ GMV({gmv}元)×{gmv_rate*100:.0f}%"
        elif "fixed" in tier_data:
            # 街访2：固定档位
            base = tier_data.get("base", 120)
            fixed = tier_data.get("fixed", 0)
            part_time_wage = base + fixed
            wage_note = f"120元/天底薪+ 固定{fixed}元"
        else:
            # 街访1：拦截+访谈，按样本数×单价
            base = tier_data.get("base", 120)
            price = tier_data.get("price", 0)
            part_time_wage = base + price * quantity
            wage_note = f"120元/天底薪+ {price}元/个× {quantity}个"
        h = vlookup_h(gmv, LUT_JIEFANG)
        human_cost = h * 1200
        human_note = f"样本数{gmv}→人力投入{h}×1200 = {int(human_cost)}元"

    elif biz == "测试执行":
        unit_price = tier_data.get("price", 0)
        part_time_wage = unit_price * quantity
        wage_note = f"{unit_price}元/场× {quantity}场"
        h = vlookup_h(gmv, LUT_CESHI)
        human_cost = h * 1200
        human_note = f"样本数{gmv}→人力投入{h}×1200 = {int(human_cost)}元"

    elif biz == "电访+外呼":
        unit_price = tier_data.get("price", 0)
        part_time_wage = unit_price * quantity + 20 * quantity  # 样本单价 + 20元呼出费
        wage_note = f"({unit_price}+20元/样本呼出费)×{quantity}个"
        h = vlookup_h(quantity, LUT_DIANFANG)
        human_cost = h * 1200
        human_note = f"样本数{quantity}→人力投入{h}×1200 = {int(human_cost)}元"

    elif biz == "实验室执行":
        unit_price = tier_data.get("price", 0)
        part_time_wage = unit_price * quantity
        wage_note = f"{unit_price}元/场× {quantity}场"
        lab_extra = calc_human_cost_lab(tier, end_time, cross_meal, scheduled_hours)
        human_cost = lab_extra["subtotal"]
        human_note = lab_extra["note"]

    elif biz == "甄别+外呼":
        unit_price = tier_data.get("price", 0)
        part_time_wage = unit_price * quantity + 20 * quantity  # 样本单价 + 20元呼出费
        wage_note = f"({unit_price}+20元/样本呼出费)×{quantity}个"
        h = vlookup_h(quantity, LUT_ZHENBIE)
        human_cost = h * 1200
        human_note = f"样本数{quantity}→人力投入{h}×1200 = {int(human_cost)}元"

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
        # Migration: add wechat column if not exists
        try:
            if DATABASE_URL:
                cursor.execute("ALTER TABLE talents ADD COLUMN IF NOT EXISTS wechat TEXT")
            else:
                cursor.execute("ALTER TABLE talents ADD COLUMN IF NOT EXISTS wechat TEXT")
        except Exception:
            pass
        cursor.execute("""
  
        # Migration: add quality_rating and attitude_rating to talents
    try:
        if DATABASE_URL:
            cursor.execute("ALTER TABLE talents ADD COLUMN IF NOT EXISTS quality_rating REAL DEFAULT 0")
            cursor.execute("ALTER TABLE talents ADD COLUMN IF NOT EXISTS attitude_rating REAL DEFAULT 0")
        else:
            cursor.execute("ALTER TABLE talents ADD COLUMN IF NOT EXISTS quality_rating REAL DEFAULT 0")
            cursor.execute("ALTER TABLE talents ADD COLUMN IF NOT EXISTS attitude_rating REAL DEFAULT 0")
    except Exception:
        pass

# Migration: add execution_time and parttimer_count to demands
        try:
            if DATABASE_URL:
                cursor.execute("ALTER TABLE demands ADD COLUMN IF NOT EXISTS execution_time TEXT")
                cursor.execute("ALTER TABLE demands ADD COLUMN IF NOT EXISTS parttimer_count INTEGER DEFAULT 1
        # Migration: add evaluation_type to demand_evaluations
        try:
            if DATABASE_URL:
                cursor.execute("ALTER TABLE demand_evaluations ADD COLUMN IF NOT EXISTS evaluation_type TEXT DEFAULT 'quality'")
            else:
                cursor.execute("ALTER TABLE demand_evaluations ADD COLUMN IF NOT EXISTS evaluation_type TEXT DEFAULT 'quality'")
        except Exception:
            pass")
            else:
                cursor.execute("ALTER TABLE demands ADD COLUMN IF NOT EXISTS execution_time TEXT")
                cursor.execute("ALTER TABLE demands ADD COLUMN IF NOT EXISTS parttimer_count INTEGER DEFAULT 1
        # Migration: add evaluation_type to demand_evaluations
        try:
            if DATABASE_URL:
                cursor.execute("ALTER TABLE demand_evaluations ADD COLUMN IF NOT EXISTS evaluation_type TEXT DEFAULT 'quality'")
            else:
                cursor.execute("ALTER TABLE demand_evaluations ADD COLUMN IF NOT EXISTS evaluation_type TEXT DEFAULT 'quality'")
        except Exception:
            pass")
        except Exception:
            pass
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
            CREATE TABLE IF NOT EXISTS talent_registration_tokens (
                id SERIAL PRIMARY KEY,
                token TEXT UNIQUE NOT NULL,
                label TEXT,
                created_by INTEGER,
                status TEXT DEFAULT 'active',
                use_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW()
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
                parttimer_count INTEGER DEFAULT 1,
                brush_list INTEGER DEFAULT 0,
                gmv REAL DEFAULT 0,
                scheduled_hours REAL DEFAULT 0,
                end_time TEXT,
                cross_meal_count INTEGER DEFAULT 0,
                execution_time TEXT,
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
                evaluation_type TEXT DEFAULT 'quality',
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
                parttimer_count INTEGER DEFAULT 1,
                brush_list INTEGER DEFAULT 0,
                gmv REAL DEFAULT 0,
                scheduled_hours REAL DEFAULT 0,
                end_time TEXT,
                cross_meal_count INTEGER DEFAULT 0,
                execution_time TEXT,
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

@app.route('/apply')
def apply_page():
    """报名页面入口，企微等外部浏览器直接打开此路径"""
    return render_template('index.html')


@app.route('/register/<token>')
def register_page(token):
    return render_template('register.html')


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




# ---- Self Registration API ----
@app.route('/api/talents/registration-tokens', methods=['GET'])
def list_registration_tokens():
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("SELECT id, token, label, status, use_count, created_at FROM talent_registration_tokens ORDER BY id DESC")
    else:
        cursor.execute("SELECT id, token, label, status, use_count, created_at FROM talent_registration_tokens ORDER BY id DESC")
    tokens = fetchall_dicts(cursor)
    close_conn(conn)
    return jsonify({'tokens': tokens})


@app.route('/api/talents/registration-tokens', methods=['POST'])
def create_registration_token():
    import secrets
    data = request.json or {}
    token = secrets.token_urlsafe(16)
    label = data.get('label', '')
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("INSERT INTO talent_registration_tokens (token, label) VALUES (%s, %s) RETURNING id", (token, label))
        token_id = cursor.fetchone()[0]
    else:
        cursor.execute("INSERT INTO talent_registration_tokens (token, label) VALUES (?, ?)", (token, label))
        token_id = cursor.lastrowid
    conn.commit()
    close_conn(conn)
    base_url = request.host_url.rstrip('/')
    link = f"{base_url}/register/{token}"
    return jsonify({'id': token_id, 'token': token, 'label': label, 'link': link})


@app.route('/api/talents/registration-tokens/<int:token_id>', methods=['DELETE'])
def revoke_registration_token(token_id):
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("UPDATE talent_registration_tokens SET status = 'revoked' WHERE id = %s", (token_id,))
    else:
        cursor.execute("UPDATE talent_registration_tokens SET status = 'revoked' WHERE id = ?", (token_id,))
    conn.commit()
    close_conn(conn)
    return jsonify({'message': 'revoked'})


@app.route('/api/public/register/<token>', methods=['GET'])
def check_registration_token(token):
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("SELECT id, label, status, use_count FROM talent_registration_tokens WHERE token = %s", (token,))
    else:
        cursor.execute("SELECT id, label, status, use_count FROM talent_registration_tokens WHERE token = ?", (token,))
    tk = fetchone_dict(cursor)
    close_conn(conn)
    if not tk:
        return jsonify({'valid': False, 'error': 'Link not found'}), 404
    if tk['status'] != 'active':
        return jsonify({'valid': False, 'error': 'Link expired'}), 403
    return jsonify({'valid': True, 'label': tk['label'] or '', 'use_count': tk['use_count']})


@app.route('/api/public/register/<token>', methods=['POST'])
def submit_registration(token):
    data = request.json or {}
    name = (data.get('name') or '').strip()
    phone = (data.get('phone') or '').strip()
    password = (data.get('password') or '').strip()
    if not name or not phone or not password:
        return jsonify({'success': False, 'error': 'Name/phone/password required'}), 400
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("SELECT id FROM talent_registration_tokens WHERE token = %s AND status = 'active'", (token,))
    else:
        cursor.execute("SELECT id FROM talent_registration_tokens WHERE token = ? AND status = 'active'", (token,))
    tk = cursor.fetchone()
    if not tk:
        close_conn(conn)
        return jsonify({'success': False, 'error': 'Invalid or expired link'}), 403
    if DATABASE_URL:
        cursor.execute("SELECT id FROM users WHERE username = %s", (phone,))
    else:
        cursor.execute("SELECT id FROM users WHERE username = ?", (phone,))
    if cursor.fetchone():
        close_conn(conn)
        return jsonify({'success': False, 'error': 'Phone already registered, please login directly'}), 400
    if DATABASE_URL:
        cursor.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, 'talent')", (phone, password))
    else:
        cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, 'talent')", (phone, password))
    talent_fields = [
        'name', 'gender', 'birth_date', 'identity_tag', 'city', 'city_level', 'school', 'major', 'education', 'graduate_year',
        'phone', 'wechat', 'project_count', 'avg_rating', 'month_rating', 'overall_summary', 'detailed_review', 'exam_score',
        'basic_test', 'desktop_research', 'issue_list', 'insight_proposal', 'skills_debug', 'agent_debug', 'knowledge_base',
        'interview_selection', 'online_interview', 'field_interview', 'questionnaire_design', 'questionnaire_analysis',
        'lab_assist', 'lab_leader', 'data_warehouse', 'data_query', 'web_crawl', 'deep_assessment', 'commercial_research',
        'excel_level', 'spss_level', 'language_ability',
        'category_moba', 'category_mmorgp', 'category_openworld_rpg', 'category_card_rpg', 'category_tactical',
        'category_shooter', 'category_strategy_slg', 'category_action_fight', 'category_sandbox_survival',
        'category_autochess', 'category_casual_puzzle', 'category_party', 'category_etc',
        'key_game_1', 'key_game_2', 'key_game_3', 'key_game_4', 'key_game_5', 'key_game_6', 'key_game_7', 'key_game_8',
        'key_game_9', 'key_game_10', 'key_game_11', 'key_game_12', 'key_game_13',
        'deep_game_1', 'deep_game_2', 'deep_game_3',
        'proficient_products', 'familiar_products', 'other_game_experience'
    ]
    fields_to_insert = []
    values_to_insert = []
    for f in talent_fields:
        v = data.get(f, '')
        if v is not None and str(v).strip() != '':
            fields_to_insert.append(f)
            values_to_insert.append(str(v).strip())
    if fields_to_insert:
        placeholders = ','.join(['%s'] * len(fields_to_insert)) if DATABASE_URL else ','.join(['?'] * len(fields_to_insert))
        cols_str = ','.join(fields_to_insert)
        if DATABASE_URL:
            cursor.execute(f"INSERT INTO talents ({cols_str}) VALUES ({placeholders})", tuple(values_to_insert))
        else:
            cursor.execute(f"INSERT INTO talents ({cols_str}) VALUES ({placeholders})", tuple(values_to_insert))
    if DATABASE_URL:
        cursor.execute("UPDATE talent_registration_tokens SET use_count = use_count + 1 WHERE token = %s", (token,))
    else:
        cursor.execute("UPDATE talent_registration_tokens SET use_count = use_count + 1 WHERE token = ?", (token,))
    conn.commit()
    close_conn(conn)
    return jsonify({'success': True, 'message': 'Registration successful, please login with phone and password'})


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
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        status = request.args.get('status', '')
        role = request.args.get('role', '')

        conn = get_db()
        cursor = conn.cursor()

        if DATABASE_URL:
            if status:
                cursor.execute("SELECT COUNT(*) FROM demands WHERE status = %s", (status,))
            else:
                cursor.execute("SELECT COUNT(*) FROM demands")
        else:
            if status:
                cursor.execute("SELECT COUNT(*) FROM demands WHERE status = ?", (status,))
            else:
                cursor.execute("SELECT COUNT(*) FROM demands")

        total = cursor.fetchone()[0]

        if DATABASE_URL:
            if status:
                cursor.execute(f"SELECT * FROM demands WHERE status = %s ORDER BY id DESC LIMIT %s OFFSET %s", (status, per_page, (page-1)*per_page))
            else:
                cursor.execute(f"SELECT * FROM demands ORDER BY id DESC LIMIT %s OFFSET %s", (per_page, (page-1)*per_page))
        else:
            if status:
                cursor.execute(f"SELECT * FROM demands WHERE status = ? ORDER BY id DESC LIMIT ? OFFSET ?", (status, per_page, (page-1)*per_page))
            else:
                cursor.execute(f"SELECT * FROM demands ORDER BY id DESC LIMIT ? OFFSET ?", (per_page, (page-1)*per_page))

        rows = fetchall_dicts(cursor)
        close_conn(conn)
        return jsonify({'data': rows, 'total': total, 'page': page, 'per_page': per_page})
    except Exception as e:
        import traceback
        try: close_conn(conn)
        except: pass
        return jsonify({'error': 'get_demands失败: ' + str(e)[:200], 'trace': traceback.format_exc()[-500:]}), 500


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
                deadline, demander_id, tidanren, status,
                execution_time, parttimer_count
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s, %s)
        """, (
            data.get('title', ''), data.get('description', ''), data.get('requirements', ''),
            data.get('business_type', ''), data.get('tier', ''),
            data.get('quantity', 1),
            1 if data.get('brush_list') else 0,
            data.get('gmv', 0),
            data.get('scheduled_hours', 0), data.get('end_time', ''), data.get('cross_meal_count', 0),
            data.get('human_cost', 0),
            data.get('budget_min'), data.get('budget_max'),
            data.get('deadline'), data.get('demander_id'), data.get('tidanren'), data.get('execution_time', ''), data.get('parttimer_count', 1),
        ))
        demand_id = cursor.lastrowid
    else:
        cursor.execute("""
            INSERT INTO demands (
                title, description, requirements, business_type, tier,
                quantity, brush_list, gmv,
                scheduled_hours, end_time, cross_meal_count,
                human_cost, budget_min, budget_max,
                deadline, demander_id, tidanren, status,
                execution_time, parttimer_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
        """, (
            data.get('title', ''), data.get('description', ''), data.get('requirements', ''),
            data.get('business_type', ''), data.get('tier', ''),
            data.get('quantity', 1),
            1 if data.get('brush_list') else 0,
            data.get('gmv', 0),
            data.get('scheduled_hours', 0), data.get('end_time', ''), data.get('cross_meal_count', 0),
            data.get('human_cost', 0),
            data.get('budget_min'), data.get('budget_max'),
            data.get('deadline'), data.get('demander_id'), data.get('tidanren'), data.get('execution_time', ''), data.get('parttimer_count', 1),
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
    """报名接口：接收{name, phone}，根据手机号查找或创建人才记录然后创建报名。"""
    data = request.json
    name = (data.get('name') or '').strip()
    phone = (data.get('phone') or '').strip()
    if not phone:
        return jsonify({'error': '手机号不能为空'}), 400

    conn = get_db()
    cursor = conn.cursor()

    # 1. Find or create talent by phone
    if DATABASE_URL:
        cursor.execute('SELECT id FROM talents WHERE phone = %s', (phone,))
    else:
        cursor.execute('SELECT id FROM talents WHERE phone = ?', (phone,))
    row = cursor.fetchone()
    if row:
        talent_id = row[0]
    else:
        wechat = (data.get('wechat') or '').strip()
        if DATABASE_URL:
            cursor.execute(
                'INSERT INTO talents (name, phone, wechat) VALUES (%s, %s, %s)',
                (name or '未知', phone, wechat)
            )
        else:
            cursor.execute(
                'INSERT INTO talents (name, phone, wechat) VALUES (?, ?, ?)',
                (name or '未知', phone, wechat)
            )
        talent_id = cursor.lastrowid

    # 2. Check if already applied
    if DATABASE_URL:
        cursor.execute('SELECT id FROM demand_applications WHERE demand_id = %s AND talent_id = %s',
                     (demand_id, talent_id))
    else:
        cursor.execute('SELECT id FROM demand_applications WHERE demand_id = ? AND talent_id = ?',
                     (demand_id, talent_id))
    if cursor.fetchone():
        close_conn(conn)
        return jsonify({'error': '已经报过名了'}), 400

    # 3. Create application
    if DATABASE_URL:
        cursor.execute(
            'INSERT INTO demand_applications (demand_id, talent_id, status) VALUES (%s, %s, %s)',
            (demand_id, talent_id, 'applied')
        )
    else:
        cursor.execute(
            'INSERT INTO demand_applications (demand_id, talent_id, status) VALUES (?, ?, ?)',
            (demand_id, talent_id, 'applied')
        )
    app_id = cursor.lastrowid
    close_conn(conn)
    return jsonify({'id': app_id, 'message': '报名成功', 'talent_id': talent_id})
@app.route('/api/demands/<int:demand_id>/public', methods=['GET'])
def get_demand_public(demand_id):
    """公开接口：获取需求基本信息（用于报名页面）"""
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("""
            SELECT d.id, d.title, d.description, d.business_type, d.tier,
                   d.quantity, d.brush_list, d.deadline, d.status,
                   d.demander_id, d.tidanren
            FROM demands d
            WHERE d.id = %s
        """, (demand_id,))
    else:
        cursor.execute("""
            SELECT d.id, d.title, d.description, d.business_type, d.tier,
                   d.quantity, d.brush_list, d.deadline, d.status,
                   d.demander_id, d.tidanren
            FROM demands d
            WHERE d.id = ?
        """, (demand_id,))
    demand = fetchone_dict(cursor)
    close_conn(conn)
    if not demand:
        return jsonify({'error': '需求不存在'}), 404
    return jsonify(demand)


@app.route('/api/demands/<int:demand_id>/apply/status', methods=['GET'])
def get_apply_status(demand_id):
    """公开接口：根据手机号查询当前需求的报名状态"""
    phone = request.args.get('phone', '').strip()
    if not phone:
        return jsonify({'error': '手机号不能为空'}), 400
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("""
            SELECT da.id, da.status, da.applied_at, da.selected_at,
                   t.name as talent_name
            FROM demand_applications da
            JOIN talents t ON da.talent_id = t.id
            WHERE da.demand_id = %s AND t.phone = %s
            ORDER BY da.applied_at DESC
            LIMIT 1
        """, (demand_id, phone))
    else:
        cursor.execute("""
            SELECT da.id, da.status, da.applied_at, da.selected_at,
                   t.name as talent_name
            FROM demand_applications da
            JOIN talents t ON da.talent_id = t.id
            WHERE da.demand_id = ? AND t.phone = ?
            ORDER BY da.applied_at DESC
            LIMIT 1
        """, (demand_id, phone))
    row = fetchone_dict(cursor)
    close_conn(conn)
    if not row:
        return jsonify({'applied': False, 'message': '未找到报名记录'})
    return jsonify({'applied': True, **row})




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

    # 获取当前 application 信息（demand_id + talent_id）
    if DATABASE_URL:
        cursor.execute("SELECT demand_id, talent_id FROM demand_applications WHERE id = %s", (app_id,))
    else:
        cursor.execute("SELECT demand_id, talent_id FROM demand_applications WHERE id = ?", (app_id,))
    app_row = fetchone_dict(cursor)
    if not app_row:
        close_conn(conn)
        return jsonify({'error': '未找到报名记录'}), 404
    demand_id = app_row['demand_id']
    talent_id = app_row['talent_id']

    # 更新状态为已入选
    if DATABASE_URL:
        cursor.execute("UPDATE demand_applications SET status = 'selected', selected_at = NOW() WHERE id = %s", (app_id,))
    else:
        cursor.execute("UPDATE demand_applications SET status = 'selected', selected_at = CURRENT_TIMESTAMP WHERE id = ?", (app_id,))

    # 获取需求标题
    if DATABASE_URL:
        cursor.execute("SELECT title FROM demands WHERE id = %s", (demand_id,))
    else:
        cursor.execute("SELECT title FROM demands WHERE id = ?", (demand_id,))
    demand_row = fetchone_dict(cursor)
    demand_title = demand_row['title'] if demand_row else '未知需求'

    # 获取所有已入选的兼职信息
    if DATABASE_URL:
        cursor.execute("""
            SELECT t.name, t.phone, COALESCE(t.wechat, '') as wechat
            FROM demand_applications da
            JOIN talents t ON da.talent_id = t.id
            WHERE da.demand_id = %s AND da.status = 'selected'
        """, (demand_id,))
    else:
        cursor.execute("""
            SELECT t.name, t.phone, COALESCE(t.wechat, '') as wechat
            FROM demand_applications da
            JOIN talents t ON da.talent_id = t.id
            WHERE da.demand_id = ? AND da.status = 'selected'
        """, (demand_id,))
    selected_list = fetchall_dicts(cursor)
    close_conn(conn)

    # 发送企微执行群通知
    notify_result = send_wecom_group_notification(demand_title, demand_title, selected_list)

    return jsonify({'message': '已选中该人才', 'notified': 'error' not in notify_result, 'notify_result': notify_result})


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


@app.route('/api/demands/<int:demand_id>/notify-group', methods=['POST'])
def notify_group_for_demand(demand_id):
    """手动触发入选通知到企微执行群"""
    conn = get_db()
    cursor = conn.cursor()

    # 获取需求标题
    if DATABASE_URL:
        cursor.execute("SELECT title FROM demands WHERE id = %s", (demand_id,))
    else:
        cursor.execute("SELECT title FROM demands WHERE id = ?", (demand_id,))
    demand_row = fetchone_dict(cursor)
    if not demand_row:
        close_conn(conn)
        return jsonify({'error': '需求不存在'}), 404
    demand_title = demand_row['title']

    # 获取所有已入选的兼职
    if DATABASE_URL:
        cursor.execute("""
            SELECT t.name, t.phone, COALESCE(t.wechat, '') as wechat
            FROM demand_applications da
            JOIN talents t ON da.talent_id = t.id
            WHERE da.demand_id = %s AND da.status = 'selected'
        """, (demand_id,))
    else:
        cursor.execute("""
            SELECT t.name, t.phone, COALESCE(t.wechat, '') as wechat
            FROM demand_applications da
            JOIN talents t ON da.talent_id = t.id
            WHERE da.demand_id = ? AND da.status = 'selected'
        """, (demand_id,))
    selected_list = fetchall_dicts(cursor)
    close_conn(conn)

    if not selected_list:
        return jsonify({'error': '暂无已入选的兼职'}), 400

    result = send_wecom_group_notification(demand_title, demand_title, selected_list)
    if 'error' in result:
        return jsonify({'error': result['error']}), 500
    return jsonify({'message': '已发送企微执行群', 'count': len(selected_list)})



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


@app.route('/api/demands/<int:demand_id>/final-ratings', methods=['GET'])
def get_final_ratings(demand_id):
    """Get final aggregated ratings for all talents in a demand"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get all evaluations for this demand
    if DATABASE_URL:
        cursor.execute("""
            SELECT de.talent_id, de.evaluation_type, de.rating, de.comment, 
                   t.name as talent_name, u.username as evaluator_name
            FROM demand_evaluations de
            JOIN talents t ON de.talent_id = t.id
            LEFT JOIN users u ON de.evaluated_by = u.id
            WHERE de.demand_id = %s
        """, (demand_id,))
    else:
        cursor.execute("""
            SELECT de.talent_id, de.evaluation_type, de.rating, de.comment,
                   t.name as talent_name, u.username as evaluator_name
            FROM demand_evaluations de
            JOIN talents t ON de.talent_id = t.id
            LEFT JOIN users u ON de.evaluated_by = u.id
            WHERE de.demand_id = ?
        """, (demand_id,))
    
    rows = fetchall_dicts(cursor)
    close_conn(conn)
    
    # Group by talent
    talent_evals = {}
    for row in rows:
        tid = row['talent_id']
        if tid not in talent_evals:
            talent_evals[tid] = {
                'talent_id': tid,
                'talent_name': row['talent_name'],
                'quality_rating': 4,  # default
                'quality_comment': '',
                'attitude_rating': 4,  # default
                'attitude_comment': '',
                'quality_evaluator': None,
                'attitude_evaluator': None
            }
        if row['evaluation_type'] == 'quality':
            talent_evals[tid]['quality_rating'] = row['rating'] or 4
            talent_evals[tid]['quality_comment'] = row['comment'] or ''
            talent_evals[tid]['quality_evaluator'] = row['evaluator_name']
        elif row['evaluation_type'] == 'attitude':
            talent_evals[tid]['attitude_rating'] = row['rating'] or 4
            talent_evals[tid]['attitude_comment'] = row['comment'] or ''
            talent_evals[tid]['attitude_evaluator'] = row['evaluator_name']
    
    # Calculate weighted final rating
    result = []
    for tid, data in talent_evals.items():
        final = data['quality_rating'] * 0.7 + data['attitude_rating'] * 0.3
        result.append({
            'talent_id': tid,
            'talent_name': data['talent_name'],
            'quality_rating': data['quality_rating'],
            'attitude_rating': data['attitude_rating'],
            'final_rating': round(final, 1),
            'quality_comment': data['quality_comment'],
            'attitude_comment': data['attitude_comment'],
            'quality_evaluator': data['quality_evaluator'],
            'attitude_evaluator': data['attitude_evaluator']
        })
    
    return jsonify(result)


@app.route('/api/demands/<int:demand_id>/evaluation-status', methods=['GET'])
def get_demand_evaluation_status(demand_id):
    """Get which talents have been evaluated (quality/attitude) for a demand"""
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("""
            SELECT talent_id, evaluation_type, rating, comment
            FROM demand_evaluations
            WHERE demand_id = %s
        """, (demand_id,))
    else:
        cursor.execute("""
            SELECT talent_id, evaluation_type, rating, comment
            FROM demand_evaluations
            WHERE demand_id = ?
        """, (demand_id,))
    rows = fetchall_dicts(cursor)
    close_conn(conn)
    
    status = {}
    for row in rows:
        tid = row['talent_id']
        etype = row['evaluation_type']
        if tid not in status:
            status[tid] = {'talent_id': tid, 'quality_done': False, 'attitude_done': False,
                          'quality_rating': None, 'attitude_rating': None,
                          'quality_comment': '', 'attitude_comment': ''}
        if etype == 'quality':
            status[tid]['quality_done'] = True
            status[tid]['quality_rating'] = row['rating']
            status[tid]['quality_comment'] = row['comment'] or ''
        elif etype == 'attitude':
            status[tid]['attitude_done'] = True
            status[tid]['attitude_rating'] = row['rating']
            status[tid]['attitude_comment'] = row['comment'] or ''
    
    return jsonify(list(status.values()))


    return jsonify(result)


@app.route('/api/demands/<int:demand_id>/evaluate', methods=['POST'])
def create_evaluation(demand_id):
    data = request.json
    talent_id = data.get('talent_id')
    rating = data.get('rating')
    evaluated_by = data.get('evaluated_by')
    
    if not talent_id or not rating:
        return jsonify({'error': '缺少必要参数'}), 400
    
    # Determine evaluation_type from user's role
    # Get user role from database
    conn_user = get_db()
    cursor_user = conn_user.cursor()
    user_role = None
    if DATABASE_URL:
        cursor_user.execute("SELECT role FROM users WHERE id = %s", (evaluated_by,))
    else:
        cursor_user.execute("SELECT role FROM users WHERE id = ?", (evaluated_by,))
    user_row = fetchone_dict(cursor_user)
    if user_row:
        user_role = user_row.get('role')
    close_conn(conn_user)
    
    # Role-based evaluation_type: admin=attitude, demander=quality
    if user_role == 'admin':
        evaluation_type = 'attitude'
    else:
        evaluation_type = 'quality'
    
    # Check for duplicate evaluation
    # Ensure evaluation_type column exists (migration for existing tables)
    try:
        conn_mig = get_db()
        cursor_mig = conn_mig.cursor()
        if DATABASE_URL:
            cursor_mig.execute("ALTER TABLE demand_evaluations ADD COLUMN IF NOT EXISTS evaluation_type TEXT DEFAULT 'quality'")
        else:
            cursor_mig.execute("ALTER TABLE demand_evaluations ADD COLUMN IF NOT EXISTS evaluation_type TEXT DEFAULT 'quality'")
        close_conn(conn_mig)
    except Exception:
        pass

    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("""
            SELECT id FROM demand_evaluations
            WHERE demand_id = %s AND talent_id = %s AND evaluation_type = %s
        """, (demand_id, talent_id, evaluation_type))
    else:
        cursor.execute("""
            SELECT id FROM demand_evaluations
            WHERE demand_id = ? AND talent_id = ? AND evaluation_type = ?
        """, (demand_id, talent_id, evaluation_type))
    existing = fetchone_dict(cursor)
    if existing:
        close_conn(conn)
        return jsonify({'error': '该兼职已被评价，请勿重复评价'}), 400
    
    # Insert evaluation
    if DATABASE_URL:
        cursor.execute("""
            INSERT INTO demand_evaluations
                (demand_id, talent_id, rating, comment, evaluation_type, evaluated_by)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (demand_id, talent_id, rating,
             data.get('comment', ''), evaluation_type,
             evaluated_by))
    else:
        cursor.execute("""
            INSERT INTO demand_evaluations
                (demand_id, talent_id, rating, comment, evaluation_type, evaluated_by)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (demand_id, talent_id, rating,
             data.get('comment', ''), evaluation_type,
             evaluated_by))
    eval_id = cursor.lastrowid
    close_conn(conn)
    
    # Update talent's ratings
    update_talent_ratings(talent_id)
    
    return jsonify({'id': eval_id, 'message': '评价已保存'})



def update_talent_ratings(talent_id):
    """Update talent's quality_rating and attitude_rating based on evaluations"""
    conn = get_db()
    cursor = conn.cursor()
    # Get quality ratings average
    if DATABASE_URL:
        cursor.execute("""
            SELECT AVG(rating) as avg_rating, COUNT(*) as cnt
            FROM demand_evaluations
            WHERE talent_id = %s AND evaluation_type = 'quality'
        """, (talent_id,))
    else:
        cursor.execute("""
            SELECT AVG(rating) as avg_rating, COUNT(*) as cnt
            FROM demand_evaluations
            WHERE talent_id = ? AND evaluation_type = 'quality'
        """, (talent_id,))
    q_row = fetchone_dict(cursor)
    quality_avg = round(float(q_row['avg_rating']), 1) if q_row and q_row['avg_rating'] else 0

    # Get attitude ratings average
    if DATABASE_URL:
        cursor.execute("""
            SELECT AVG(rating) as avg_rating
            FROM demand_evaluations
            WHERE talent_id = %s AND evaluation_type = 'attitude'
        """, (talent_id,))
    else:
        cursor.execute("""
            SELECT AVG(rating) as avg_rating
            FROM demand_evaluations
            WHERE talent_id = ? AND evaluation_type = 'attitude'
        """, (talent_id,))
    a_row = fetchone_dict(cursor)
    attitude_avg = round(float(a_row['avg_rating']), 1) if a_row and a_row['avg_rating'] else 0

    # Count total evaluations
    if DATABASE_URL:
        cursor.execute("SELECT COUNT(*) as cnt FROM demand_evaluations WHERE talent_id = %s", (talent_id,))
    else:
        cursor.execute("SELECT COUNT(*) as cnt FROM demand_evaluations WHERE talent_id = ?", (talent_id,))
    count_row = fetchone_dict(cursor)
    total_count = count_row['cnt'] or 0

    # Combined avg_rating for backward compatibility
    if quality_avg > 0 and attitude_avg > 0:
        combined_avg = round(quality_avg * 0.7 + attitude_avg * 0.3, 1)
    elif quality_avg > 0:
        combined_avg = quality_avg
    elif attitude_avg > 0:
        combined_avg = attitude_avg
    else:
        combined_avg = 0

    if DATABASE_URL:
        cursor.execute(
            "UPDATE talents SET quality_rating = %s, attitude_rating = %s, avg_rating = %s, month_rating = %s, project_count = %s WHERE id = %s",
            (quality_avg, attitude_avg, combined_avg, combined_avg, total_count, talent_id))
    else:
        cursor.execute(
            "UPDATE talents SET quality_rating = ?, attitude_rating = ?, avg_rating = ?, month_rating = ?, project_count = ? WHERE id = ?",
            (quality_avg, attitude_avg, combined_avg, combined_avg, total_count, talent_id))
    close_conn(conn)



@app.route('/api/evaluations/auto-default', methods=['POST'])
def auto_default_missing_evaluations():
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("""
            SELECT id FROM demands
            WHERE status = 'done'
            AND updated_at < NOW() - INTERVAL '24 hours'
        """)
    else:
        cursor.execute("""
            SELECT id FROM demands
            WHERE status = 'done'
            AND updated_at < datetime('now', '-24 hours')
        """)
    done_demands = fetchall_dicts(cursor)
    defaulted = []
    for demand_row in done_demands:
        demand_id = demand_row['id']
        if DATABASE_URL:
            cursor.execute("SELECT DISTINCT talent_id FROM demand_evaluations WHERE demand_id = %s", (demand_id,))
        else:
            cursor.execute("SELECT DISTINCT talent_id FROM demand_evaluations WHERE demand_id = ?", (demand_id,))
        talents = fetchall_dicts(cursor)
        for t in talents:
            talent_id = t['talent_id']
            if DATABASE_URL:
                cursor.execute("SELECT id FROM demand_evaluations WHERE demand_id = %s AND talent_id = %s AND evaluation_type = 'quality'", (demand_id, talent_id))
            else:
                cursor.execute("SELECT id FROM demand_evaluations WHERE demand_id = ? AND talent_id = ? AND evaluation_type = 'quality'", (demand_id, talent_id))
            has_quality = cursor.fetchone() is not None
            if DATABASE_URL:
                cursor.execute("SELECT id FROM demand_evaluations WHERE demand_id = %s AND talent_id = %s AND evaluation_type = 'attitude'", (demand_id, talent_id))
            else:
                cursor.execute("SELECT id FROM demand_evaluations WHERE demand_id = ? AND talent_id = ? AND evaluation_type = 'attitude'", (demand_id, talent_id))
            has_attitude = cursor.fetchone() is not None
            if has_quality and not has_attitude:
                if DATABASE_URL:
                    cursor.execute("""
                        INSERT INTO demand_evaluations (demand_id, talent_id, rating, comment, evaluation_type, evaluated_by)
                        VALUES (%s, %s, 4, 'auto_default', 'attitude', NULL)
                    """, (demand_id, talent_id))
                else:
                    cursor.execute("""
                        INSERT INTO demand_evaluations (demand_id, talent_id, rating, comment, evaluation_type, evaluated_by)
                        VALUES (?, ?, 4, 'auto_default', 'attitude', NULL)
                    """, (demand_id, talent_id))
                defaulted.append({'demand_id': demand_id, 'talent_id': talent_id, 'type': 'attitude'})
                update_talent_ratings(talent_id)
            elif has_attitude and not has_quality:
                if DATABASE_URL:
                    cursor.execute("""
                        INSERT INTO demand_evaluations (demand_id, talent_id, rating, comment, evaluation_type, evaluated_by)
                        VALUES (%s, %s, 4, 'auto_default', 'quality', NULL)
                    """, (demand_id, talent_id))
                else:
                    cursor.execute("""
                        INSERT INTO demand_evaluations (demand_id, talent_id, rating, comment, evaluation_type, evaluated_by)
                        VALUES (?, ?, 4, 'auto_default', 'quality', NULL)
                    """, (demand_id, talent_id))
                defaulted.append({'demand_id': demand_id, 'talent_id': talent_id, 'type': 'quality'})
                update_talent_ratings(talent_id)
    close_conn(conn)
    return jsonify({'message': 'auto_default_done', 'count': len(defaulted), 'details': defaulted})
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


def send_wecom_group_notification(title, demand_title, selected_list):
    """入选后发送企微群通知（通过群机器人）
    selected_list: [{'name': '张三', 'phone': '138xxx', 'wechat': 'zhangsan'}]
    """
    # 优先用 wecom_group_webhook_url，没有则复用 wecom_webhook_url（群机器人与个人机器人共享同一key）
    wecom_group_url = get_setting('wecom_group_webhook_url') or get_setting('wecom_webhook_url')
    if not wecom_group_url:
        return {'error': '企微 Webhook URL 未配置，请在系统设置中填写 wecom_webhook_url'}

    msg = f"### ✅ 入选通知\n"
    msg += f"**需求：** {demand_title}\n"
    msg += f"**入选人数：** {len(selected_list)} 人\n\n"
    msg += "**入选名单：**\n"
    for i, t in enumerate(selected_list, 1):
        wechat_info = f"（微信号：{t['wechat']}）" if t.get('wechat') else "（暂无微信号）"
        msg += f"{i}. {t['name']} | {t['phone']} {wechat_info}\n"
    msg += f"\n请相关执行负责人尽快拉群并通知以上人员。"

    try:
        import urllib.request
        import json as json_lib
        payload = {'msgtype': 'markdown', 'markdown': {'content': msg}}
        req = urllib.request.Request(
            wecom_group_url,
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

    msg_biz = demand['business_type'] or ""
    msg_tier = demand['tier'] or ""
    msg_qty = demand.get('parttimer_count', 0) or 0
    msg_exec_time = demand.get('execution_time', '') or "未填写"
    msg_req = demand.get('requirements', '') or "无"

    if quote:
        biz = demand.get('business_type', '')
        tier = demand.get('tier', '')
        qty = demand.get('quantity', 1) or 1
        pw = quote['part_time_wage'] or 0
        if '+外呼' in biz:
            # Get tier price from TPT for display
            tier_price = 0
            if biz in TALENT_PRICE_TABLE:
                for t in TALENT_PRICE_TABLE[biz]:
                    if t['label'] == tier:
                        tier_price = t.get('price', 0)
                        break
            sample_price = tier_price - 20 if "甄别" in biz else tier_price
            quote_str = "0.5元/呼出 + %s元/样本" % sample_price
        else:
            unit_price = int(pw) // int(qty) if qty else 0
            quote_str = "%s元/样本" % unit_price
    else:
        quote_str = "待确认"

    msg = "### New 需求发布\n"
    msg += "**需求类型：** %s - %s\n" % (msg_biz, msg_tier)
    msg += "**兼职人数：** %s\n" % msg_qty
    msg += "**单价：** %s\n" % quote_str
    msg += "**执行时间：** %s\n" % msg_exec_time
    msg += "**具体要求：** %s\n" % msg_req
    msg += "---\n"
    msg += "> 点击报名：[系统链接](https://talent-management-web.onrender.com/apply?demand_id=%s)" % demand_id
    msg += "\n\n> ⚠️ **重要提示**：报名后请务必先添加管理员企微「菜菜」，否则后续无法通知入选结果"

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


def init_wecom_settings():
    """启动时自动保存企微应用凭证（已配置则跳过）"""
    settings_to_save = {
        'wecom_corp_id': 'wwc64a71014d7be247',
        'wecom_agent_id': '1000009',
    }
    for key, value in settings_to_save.items():
        existing = get_setting(key)
        if not existing:
            conn = get_db()
            cursor = conn.cursor()
            if DATABASE_URL:
                cursor.execute(
                    "INSERT INTO system_settings (key, value) VALUES (%s, %s) ON CONFLICT(key) DO NOTHING",
                    (key, value)
                )
            else:
                cursor.execute(
                    "INSERT INTO system_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO NOTHING",
                    (key, value)
                )
            close_conn(conn)


if __name__ == '__main__':
    init_wecom_settings()
    app.run(host='0.0.0.0', port=5000, debug=True)
