"""
浜烘墠鏍囩绠＄悊绯荤粺 - Flask 鍚庣
鍖呭惈锛氫汉鎵嶇鐞?+ 闇€姹傛帴鍗曟祦绋?鏀寔锛歋QLite锛堟湰鍦帮級 / PostgreSQL锛圫upabase 浜戞暟鎹簱锛?"""
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

# 閰嶇疆 Jinja2 浣跨敤 <% %> 鏇夸唬 {{ }}锛岄伩鍏嶄笌 Vue 鍐茬獊
app.jinja_env.variable_start_string = '<%'
app.jinja_env.variable_end_string = '%>'

# 鏁版嵁搴撻厤缃細浼樺厛浣跨敤 DATABASE_URL锛圫upabase PostgreSQL锛夛紝鍚﹀垯鐢ㄦ湰鍦?SQLite
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db():
    """杩斿洖鏁版嵁搴撹繛鎺ワ紙鑷姩鍦ㄨ缁撴潫鏃跺叧闂級"""
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
    """鍏抽棴杩炴帴锛坧sycopg2 闇€瑕?commit+close锛宻qlite3 鍙 close锛?""
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
    # Flask 璇锋眰缁撴潫鍚庤嚜鍔ㄦ竻鐞嗚繛鎺ワ紙閫氳繃 request context锛?    pass

# ============================================================
# 浜烘墠宸ヨ祫鍗曚环琛紙鍗曚綅锛氬厓锛?# ============================================================
TALENT_PRICE_TABLE = {
    "鐢勫埆": [
        {"label": "5~10mins/涓?, "price": 8},
        {"label": "10~20mins/涓?, "price": 12},
        {"label": "20~30mins/涓?, "price": 16},
        {"label": ">30mins/涓?, "price": 26},
    ],
    "鐢佃": [
        {"label": "30mins浠ュ唴/涓?, "price": 30},
        {"label": "30~60mins/涓?, "price": 45},
        {"label": "60~90mins/涓紙浠呴檺5鏄熷吋鑱岋級", "price": 80},
        {"label": "90~120mins/涓?, "price": 100},
    ],
    "瀹為獙瀹ゆ墽琛?: [
        {"label": "2H浠ュ唴/鍦?, "price": 150},
        {"label": "2~4灏忔椂/鍦?, "price": 200},
        {"label": "4~6灏忔椂/鍦?, "price": 250},
    ],
    "琛楄1": [
        {"label": "10鍒嗛挓浠ュ唴", "price": 30, "base": 120},
        {"label": "30鍒嗛挓浠ュ唴", "price": 65, "base": 120},
        {"label": "30~60鍒嗛挓", "price": 104, "base": 120},
    ],
    "琛楄2": [
        {"label": "鍗冧竾绾?, "gmv_rate": 0.05, "gmv_rate_display": "GMV脳5%", "base": 120, "fixed": 3000},
        {"label": "鐧句竾绾?, "gmv_rate": 0.10, "gmv_rate_display": "GMV脳10%", "base": 120, "fixed": 1500},
        {"label": "鍗佷竾绾?, "gmv_rate": 0.20, "gmv_rate_display": "GMV脳20%", "base": 120, "fixed": 800},
        {"label": "鍗冪骇鍙婁互涓?, "gmv_rate": None, "gmv_rate_display": "鍥哄畾200鍏?, "base": 120, "fixed": 200},
    ],
    "鑸嗘儏鎵撴爣": [
        {"label": "鏉?, "price": 0.3},
    ],
    "娲炲療鏀堕泦/妗岄潰鐮旂┒": [
        {"label": "<0.5H/浜?, "price": 10},
        {"label": "<1H/浜?, "price": 30},
        {"label": "1~3H/浜?, "price": 100},
        {"label": "3~6H/浜?, "price": 150},
    ],
    "閭€绾︽媺鏂?: [
        {"label": "鏉?, "price": 3},
    ],
}

BRUSH_LIST_FEE = 15
OVERTIME_FEE_PER_HOUR = 50
MEAL_FEE_PER_MEAL = 30
TRANSPORT_SUBSIDY = 50
LAB_TIER_HOURS = {"2H浠ュ唴/鍦?: 2, "2~4灏忔椂/鍦?: 4, "4~6灏忔椂/鍦?: 6}


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
        note_parts.append(f"瓒呮椂{int(overtime_hours)}灏忔椂脳50={overtime_fee}鍏?)
    if meal_fee > 0:
        note_parts.append(f"椁愯ˉ{cross_meal_count}椤棵?0={meal_fee}鍏?)
    if end_time_str:
        try:
            h, m = map(int, end_time_str.split(":"))
            if h > 21 or (h == 21 and m > 0):
                transport_fee = TRANSPORT_SUBSIDY
                note_parts.append(f"浜ら€氳ˉ璐?0鍏?)
        except:
            pass
    subtotal = overtime_fee + meal_fee + transport_fee
    note = "锛?.join(note_parts) if note_parts else "鏃犻澶栬ˉ璐?
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
    if biz in ("鐢勫埆鎵ц", "鐢佃", "琛楄鎵ц", "娴嬭瘯鎵ц") and not gmv:
        gmv = quantity
    scheduled_hours = demand_data.get("scheduled_hours", 0)
    end_time = demand_data.get("end_time", "")
    cross_meal = demand_data.get("cross_meal_count", 0)

    if biz not in TALENT_PRICE_TABLE:
        return {"error": f"鏈煡涓氬姟绫诲瀷: {biz}"}
    tiers = TALENT_PRICE_TABLE[biz]
    tier_data = next((t for t in tiers if t["label"] == tier), None)
    if not tier_data:
        return {"error": f"鏈煡妗ｄ綅: {tier}"}

    part_time_wage = 0
    human_cost = 0
    wage_note = ""
    human_note = ""

    if biz == "琛楄1":
        base = tier_data.get("base", 120)
        price = tier_data.get("price", 0)
        part_time_wage = base + price * quantity
        wage_note = f"120鍏?澶╁簳钖? {price}鍏?涓?{quantity}涓?

    elif biz == "琛楄2":
        base = tier_data.get("base", 120)
        fixed = tier_data.get("fixed", 0)
        gmv_rate = tier_data.get("gmv_rate")
        rate_display = tier_data.get("gmv_rate_display", "")
        if gmv_rate is not None:
            part_time_wage = base + gmv * gmv_rate
            wage_note = f"120鍏?澶╁簳钖? GMV({gmv}鍏?脳{gmv_rate*100:.0f}%"
        else:
            part_time_wage = base + fixed
            wage_note = f"120鍏?澶╁簳钖? 鍥哄畾{fixed}鍏?

    elif biz == "鐢勫埆鎵ц":
        unit_price = tier_data.get("price", 0)
        part_time_wage = unit_price * quantity
        wage_note = f"{unit_price}鍏?涓?{quantity}涓?
        h = vlookup_h(gmv, LUT_ZHENBIE)
        human_cost = h * 1200
        human_note = f"鏍锋湰鏁皗gmv}鈫掍汉鍔涙姇鍏h}脳1200 = {int(human_cost)}鍏?

    elif biz == "鐢佃":
        unit_price = tier_data.get("price", 0)
        part_time_wage = unit_price * quantity
        wage_note = f"{unit_price}鍏?涓?{quantity}涓?
        h = vlookup_h(gmv, LUT_DIANFANG)
        human_cost = h * 1200
        human_note = f"鏍锋湰鏁皗gmv}鈫掍汉鍔涙姇鍏h}脳1200 = {int(human_cost)}鍏?

    elif biz == "琛楄鎵ц":
        unit_price = tier_data.get("price", 0)
        part_time_wage = unit_price * quantity
        wage_note = f"{unit_price}鍏?涓?{quantity}涓?
        h = vlookup_h(gmv, LUT_JIEFANG)
        human_cost = h * 1200
        human_note = f"鏍锋湰鏁皗gmv}鈫掍汉鍔涙姇鍏h}脳1200 = {int(human_cost)}鍏?

    elif biz == "娴嬭瘯鎵ц":
        unit_price = tier_data.get("price", 0)
        part_time_wage = unit_price * quantity
        wage_note = f"{unit_price}鍏?涓?{quantity}涓?
        h = vlookup_h(gmv, LUT_CESHI)
        human_cost = h * 1200
        human_note = f"鏍锋湰鏁皗gmv}鈫掍汉鍔涙姇鍏h}脳1200 = {int(human_cost)}鍏?

    elif biz == "瀹為獙瀹ゆ墽琛?:
        unit_price = tier_data.get("price", 0)
        part_time_wage = unit_price * quantity
        wage_note = f"{unit_price}鍏?鍦好?{quantity}鍦?
        lab_extra = calc_human_cost_lab(tier, end_time, cross_meal, scheduled_hours)
        human_cost = lab_extra["subtotal"]
        human_note = lab_extra["note"]

    else:
        unit_price = tier_data.get("price", 0)
        if brush:
            unit_price_brush = unit_price + BRUSH_LIST_FEE
            part_time_wage = unit_price_brush * quantity
            wage_note = (f"({unit_price}+15鍏?鏍锋湰)脳{quantity}={part_time_wage}鍏冿紝"
                         f"鍛煎嚭璐圭敤鏍规嵁鎷ㄦ墦闅惧害鏈夋墍涓嶅悓锛屼互瀹為檯浜х敓缁撶畻")
        else:
            part_time_wage = unit_price * quantity
            wage_note = f"{unit_price}鍏?涓?{quantity}涓?

    total = round(part_time_wage + human_cost, 2)
    return {
        "part_time_wage": round(part_time_wage, 2),
        "human_cost": round(human_cost, 2),
        "total": total,
        "wage_note": wage_note,
        "human_note": human_note,
    }


# ============================================================
# 浜烘墠瀛楁鏄犲皠
# ============================================================
COLUMN_MAP = {
    "name": "濮撳悕", "gender": "鎬у埆", "birth_date": "鍑虹敓骞存湀",
    "identity_tag": "韬唤鏍囩", "city": "甯镐綇鍩庡競", "city_level": "鍩庡競绾у埆",
    "school": "瀛︽牎", "major": "涓撲笟", "education": "鍦ㄨ瀛﹀巻",
    "graduate_year": "棰勮姣曚笟骞翠唤", "phone": "鎵嬫満鍙?, "wechat": "寰俊鍙?,
    "project_count": "涓氬姟娆℃暟", "avg_rating": "鍘嗗彶骞冲潎鏄熺骇",
    "month_rating": "褰撴湀鏄熺骇", "overall_summary": "鏁翠綋璇勪环鎽樿",
    "detailed_review": "璇︾粏涓氬姟璇勪环", "exam_score": "鍏艰亴鑰冭瘯寰楀垎",
    "basic_test": "鏃ュ父璺戞祴/鍩虹娴嬭瘎",
    "desktop_research": "妗岄潰鐮旂┒锛堢珵鍝佽垎鎯?璧勬枡鏁寸悊锛?,
    "issue_list": "闂娓呭崟鎵ц", "insight_proposal": "娲炲療鎻愭鑳藉姏",
    "skills_debug": "Skills鐢熸垚/璋冭瘯锛圓I宸ュ叿锛?,
    "agent_debug": "Agent鐢熸垚/璋冭瘯", "knowledge_base": "AI鐭ヨ瘑搴撳缓璁?,
    "interview_selection": "璁胯皥鎵ц-鐜╁鐢勫埆",
    "online_interview": "璁胯皥鎵ц-绾夸笂璁胯皥",
    "field_interview": "璁胯皥鎵ц-鐢伴噹璋冩煡/澶栬",
    "questionnaire_design": "璁胯皥鎻愮翰/闂嵎璁捐",
    "questionnaire_analysis": "闂嵎璋冪爺锛堝綍鍏ユ暣鐞?鍒嗘瀽锛?,
    "lab_assist": "瀹為獙瀹ゆ祴璇曞崗鍔╂墽琛?, "lab_leader": "瀹為獙瀹ゆ祴璇曚富璐熻矗/涓绘寔",
    "data_warehouse": "鏁颁粨宸ヤ綔锛堟棩甯告姤琛級",
    "data_query": "鏁版嵁鏌ヨ/鎶ヨ〃寮€鍙?, "web_crawl": "鐖櫕/鏁版嵁鏀堕泦",
    "deep_assessment": "娣卞害娴嬭瘎鑳藉姏",
    "commercial_research": "鍟嗕笟鍖栫爺绌朵笌鍒嗘瀽",
    "excel_level": "Excel鎶€鑳界瓑绾?, "spss_level": "SPSS鎶€鑳界瓑绾?,
    "language_ability": "璇█鑳藉姏",
    "category_moba": "鍝佺被-MOBA绫伙紙鑻遍泟鑱旂洘銆佺帇鑰呰崳鑰€绛夛級",
    "category_mmorgp": "鍝佺被-MMORPG锛堥€嗘按瀵掋€佹ⅵ骞昏タ娓哥瓑锛?,
    "category_openworld_rpg": "鍝佺被-寮€鏀句笘鐣孯PG锛堝灏旇揪锛屽師绁炵瓑锛?,
    "category_card_rpg": "鍝佺被-鍗＄墝RPG绫伙紙闃撮槼甯堛€佸穿鍧忥細鏄熺┕閾侀亾绛夛級",
    "category_tactical": "鍝佺被-鎴樻湳绔炴妧绫伙紙PUBG銆佸拰骞崇簿鑻辩瓑锛?,
    "category_shooter": "鍝佺被-灏勫嚮绫伙紙绌胯秺鐏嚎銆丆ODM绛夛級",
    "category_strategy_slg": "鍝佺被-绛栫暐/SLG绫伙紙鏂囨槑銆佺巼鍦熶箣婊ㄧ瓑锛?,
    "category_action_fight": "鍝佺被-鍔ㄤ綔/鏍兼枟绫伙紙鍙嫾銆佸穿鍧忕瓑锛?,
    "category_sandbox_survival": "鍝佺被-娌欑洅/鐢熷瓨绫伙紙鎴戠殑涓栫晫銆佹槑鏃ヤ箣鍚庣瓑锛?,
    "category_autochess": "鍝佺被-鑷蛋妫嬬被锛堥噾閾查摬銆佸澶氳嚜璧版绛夛級",
    "category_casual_puzzle": "鍝佺被-浼戦棽鐩婃櫤绫伙紙缇婁簡涓緤銆佹秷娑堜箰绛夛級",
    "category_party": "鍝佺被-浼戦棽绔炴妧/娲惧绫伙紙铔嬩粩娲惧銆侀箙楦潃绛夛級",
    "category_etc": "鍝佺被-鍏朵粬锛堣嚜濉級",
    "key_game_1": "閲嶇偣娓告垙-閫嗘按瀵?, "key_game_2": "閲嶇偣娓告垙-鐕曚簯鍗佸叚澹?,
    "key_game_3": "閲嶇偣娓告垙-涓€姊︽睙婀?, "key_game_4": "閲嶇偣娓告垙-闃撮槼甯?,
    "key_game_5": "閲嶇偣娓告垙-閲戦摬閾蹭箣鎴?, "key_game_6": "閲嶇偣娓告垙-铔嬩粩娲惧",
    "key_game_7": "閲嶇偣娓告垙-鏃犲敖鍐棩", "key_game_8": "閲嶇偣娓告垙-鐜囧湡涔嬫花",
    "key_game_9": "閲嶇偣娓告垙-鐜嬭€呰崳鑰€", "key_game_10": "閲嶇偣娓告垙-鑻遍泟鑱旂洘",
    "key_game_11": "閲嶇偣娓告垙-鏄庢棩涔嬪悗", "key_game_12": "閲嶇偣娓告垙-钀ょ伀绐佸嚮",
    "key_game_13": "閲嶇偣娓告垙-涓夎娲茶鍔?,
    "deep_game_1": "娣卞害娓告垙1", "deep_game_2": "娣卞害娓告垙2", "deep_game_3": "娣卞害娓告垙3",
    "proficient_products": "绮鹃€氫骇鍝侊紙1000h+锛?,
    "familiar_products": "鐔熸倝浜у搧锛?00h+锛?,
    "other_game_experience": "鍏朵粬娓告垙缁忓巻琛ュ厖",
}
TALENT_FIELDS = list(COLUMN_MAP.keys())


# ============================================================
# 鏁版嵁搴撳垵濮嬪寲
# ============================================================
def init_db():
    conn = get_db()
    cursor = conn.cursor()

    if DATABASE_URL:
        # PostgreSQL 妯″紡
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
        # SQLite 鏈湴寮€鍙戞ā寮?        cols = ["id INTEGER PRIMARY KEY AUTOINCREMENT"]
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
    print(f"[WARN] 鏁版嵁搴撳垵濮嬪寲澶辫触锛堢◢鍚庡彲璁块棶 /api/init 閲嶈瘯锛? {e}")
    _db_init_ok = False


# ============================================================
# 璋冭瘯鐢細鎵嬪姩鍒濆鍖栨暟鎹簱锛堥儴缃插悗璋冪敤涓€娆″嵆鍙級
# ============================================================
@app.route('/api/init', methods=['GET'])
def manual_init():
    import traceback
    try:
        init_db()
        ensure_admin()
        _db_init_ok = True
        return jsonify({'message': '鏁版嵁搴撳垵濮嬪寲瀹屾垚'})
    except Exception as e:
        import sys
        tb = traceback.format_exception(type(e), e, e.__traceback__)
        tb_str = ''.join(tb)
        # 鎵炬渶鍚庝竴涓湁浠峰€肩殑琛?        lines = [l for l in tb_str.split('\n') if 'app.py' in l]
        last_app_line = lines[-1].strip() if lines else tb_str[-200:]
        return jsonify({'error': str(e), 'type': type(e).__name__, 'location': last_app_line}), 500


# ============================================================
# 璺敱鍜?API
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
    return jsonify({'message': 'admin/admin123 宸查噸缃?})


@app.route('/api/system/setup', methods=['POST'])
def system_setup():
    data = request.json
    users_to_create = data.get('users', [])
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] > 1:
        close_conn(conn)
        return jsonify({'error': '绯荤粺宸叉湁澶氫釜璐﹀彿'}), 403
    if not (1 <= len(users_to_create) <= 5):
        close_conn(conn)
        return jsonify({'error': '璇峰垱寤?~5涓处鍙?}), 400
    usernames = [u.get('username', '').strip() for u in users_to_create]
    if len(usernames) != len(set(usernames)):
        close_conn(conn)
        return jsonify({'error': '鐢ㄦ埛鍚嶄笉鑳介噸澶?}), 400
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
    return jsonify({'message': f'鎴愬姛鍒涘缓 {len(users_to_create)} 涓处鍙?})


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
        return jsonify({'error': '鐢ㄦ埛鍚嶅拰瀵嗙爜涓嶈兘涓虹┖'}), 400
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] >= 200:
        close_conn(conn)
        return jsonify({'error': '鏈€澶氬彧鑳藉垱寤?00涓处鍙?}), 400
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
        return jsonify({'id': user_id, 'message': '璐﹀彿鍒涘缓鎴愬姛'})
    except Exception as e:
        close_conn(conn)
        err_msg = str(e)
        if 'unique' in err_msg.lower() or 'duplicate' in err_msg.lower():
            return jsonify({'error': '鐢ㄦ埛鍚嶅凡瀛樺湪'}), 400
        return jsonify({'error': err_msg}), 400


@app.route('/api/users/import', methods=['POST'])
def import_users():
    """鎵归噺瀵煎叆璐﹀彿锛圗xcel 鏂囦欢锛?""
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    file = request.files['file']
    if not file.filename.endswith(('.xlsx', '.xls')):
        return jsonify({'error': '璇蜂笂浼?Excel 鏂囦欢'}), 400
    try:
        df = pd.read_excel(file)
        # 楠岃瘉蹇呴渶鍒?        required_cols = ['username', 'password']
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            return jsonify({'error': f'Excel 缂哄皯蹇呴渶鍒? {", ".join(missing)}锛屽彲閫夊垪: role'}), 400

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

            # 闄愬埗鎬绘暟涓嶈秴杩?200 涓?            cursor.execute("SELECT COUNT(*) FROM users")
            if cursor.fetchone()[0] >= 200:
                skipped += 1
                errors.append(f"绗瑊idx+2}琛? 宸茶揪鍒拌处鍙蜂笂闄愶紙200涓級")
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
                    errors.append(f"绗瑊idx+2}琛屻€寋username}銆? 鐢ㄦ埛鍚嶅凡瀛樺湪")
                else:
                    errors.append(f"绗瑊idx+2}琛屻€寋username}銆? {err_msg}")

        close_conn(conn)
        msg = f'鎴愬姛瀵煎叆 {imported} 涓处鍙?
        if skipped:
            msg += f'锛岃烦杩?{skipped} 琛?
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
    return jsonify({'message': '鍒犻櫎鎴愬姛'})


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


# ---- 浜烘墠绠＄悊 API ----

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
        return jsonify({'id': None, 'message': '鍒涘缓鎴愬姛锛堟棤瀛楁锛?})
    return jsonify({'id': talent_id, 'message': '鍒涘缓鎴愬姛'})


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
    return jsonify({'message': '鏇存柊鎴愬姛'})


@app.route('/api/talents/<int:talent_id>', methods=['DELETE'])
def delete_talent(talent_id):
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("DELETE FROM talents WHERE id = %s", (talent_id,))
    else:
        cursor.execute("DELETE FROM talents WHERE id = ?", (talent_id,))
    close_conn(conn)
    return jsonify({'message': '鍒犻櫎鎴愬姛'})


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
                    errors.append(f"绗瑊idx+2}琛? {str(e)}")
        close_conn(conn)
        msg = f'鎴愬姛瀵煎叆 {imported} 鏉¤褰?
        if errors:
            msg += f'锛寋len(errors)} 琛屽け璐?
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
        df.to_excel(writer, index=False, sheet_name='浜烘墠搴?)
    output.seek(0)
    return send_file(output,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True,
                     download_name=f'浜烘墠搴揰{datetime.now().strftime("%Y%m%d")}.xlsx')


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
            cursor.execute(f"SELECT COUNT(*) FROM talents WHERE {field} = '绮鹃€?")
        else:
            cursor.execute(f"SELECT COUNT(*) FROM talents WHERE {field} = '绮鹃€?")
        stats['skills'][field] = cursor.fetchone()[0]
    close_conn(conn)
    return jsonify(stats)


# ============================================================
# 闇€姹傛帴鍗曟ā鍧?API
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
    return jsonify({'id': demand_id, 'message': '闇€姹傚垱寤烘垚鍔?})


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
    return jsonify({'message': '鏇存柊鎴愬姛'})


@app.route('/api/demands/<int:demand_id>', methods=['DELETE'])
def delete_demand(demand_id):
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute('DELETE FROM demands WHERE id = %s', (demand_id,))
    else:
        cursor.execute('DELETE FROM demands WHERE id = ?', (demand_id,))
    close_conn(conn)
    return jsonify({'message': '鍒犻櫎鎴愬姛'})


# ---- 鎶ヤ环 API ----

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
        return jsonify({'error': '闇€姹備笉瀛樺湪'}), 404
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
    return jsonify({'id': quote_id, 'message': '鎶ヤ环宸蹭繚瀛?})


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
    return jsonify({'message': '鎶ヤ环宸茬‘璁わ紝杩涘叆鎷涘嫙闃舵'})


# ---- 鎶ュ悕 API ----

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
        return jsonify({'error': '宸茬粡鎶ュ悕杩囦簡'}), 400
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
    return jsonify({'id': app_id, 'message': '鎶ュ悕鎴愬姛'})


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
    return jsonify({'message': '宸查€変腑璇ヤ汉鎵?})


@app.route('/api/applications/<int:app_id>/reject', methods=['POST'])
def reject_talent(app_id):
    conn = get_db()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("UPDATE demand_applications SET status = 'rejected' WHERE id = %s", (app_id,))
    else:
        cursor.execute("UPDATE demand_applications SET status = 'rejected' WHERE id = ?", (app_id,))
    close_conn(conn)
    return jsonify({'message': '宸叉嫆缁?})


# ---- 璇勪环 API ----

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
    return jsonify({'id': eval_id, 'message': '璇勪环宸蹭繚瀛?})


# ---- 浼佸井 Webhook ----

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
        return {'error': '浼佸井 Webhook URL 鏈厤缃紝璇峰湪绯荤粺璁剧疆涓～鍐?}
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
            return {'error': result.get('errmsg', '鍙戦€佸け璐?)}
    except Exception as e:
        return {'error': str(e)}


@app.route('/api/demands/<int:demand_id>/publish', methods=['POST'])
def publish_to_wecom(demand_id):
    wecom_url = get_setting('wecom_webhook_url')
    if not wecom_url:
        return jsonify({'error': '浼佸井 Webhook URL 鏈厤缃?}), 400

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
        return jsonify({'error': '闇€姹備笉瀛樺湪'}), 404

    if DATABASE_URL:
        cursor.execute("SELECT * FROM demand_quotes WHERE demand_id = %s AND status = 'confirmed'", (demand_id,))
    else:
        cursor.execute("SELECT * FROM demand_quotes WHERE demand_id = ? AND status = 'confirmed'", (demand_id,))
    quote = fetchone_dict(cursor)
    close_conn(conn)

    quote = quote if quote else None

    brush_str = "锛堝埛鍚嶅崟锛? if demand['brush_list'] else ""
    msg_title = demand['title'] or ""
    msg_biz = demand['business_type'] or ""
    msg_tier = demand['tier'] or ""
    msg_qty = demand['quantity'] or 0
    msg_deadline = demand['deadline'] or "寰呭畾"
    msg_desc = demand['description'] or "鏃?
    msg_demander_tidan = demand.get('tidanren', '') or demand.get('demander_name', '')

    if quote:
        pw = quote['part_time_wage'] or 0
        hc = quote['human_cost'] or 0
        total = quote['total_quote'] or 0
        quote_str = "%s鍏冿紙鍏艰亴宸ヨ祫%s鍏?+ 浜哄姏鎴愭湰%s鍏冿級" % (total, pw, hc)
    else:
        quote_str = "寰呯‘璁?

    msg = "### New 闇€姹傚彂甯僜n"
    msg += "**鎻愬崟浜猴細** %s\n" % msg_demander_tidan
    msg += "**闇€姹傛爣棰橈細** %s\n" % msg_title
    msg += "**涓氬姟绫诲瀷锛?* %s - %s %s\n" % (msg_biz, msg_tier, brush_str)
    msg += "**鏁伴噺锛?* %s\n" % msg_qty
    msg += "**鎴鏃ユ湡锛?* %s\n" % msg_deadline
    msg += "**闇€姹傛弿杩帮細** %s\n" % msg_desc
    msg += "**鎶ヤ环锛?* %s\n" % quote_str
    msg += "---\n"
    msg += "> 鐐瑰嚮鎶ュ悕锛歔绯荤粺閾炬帴](https://talent-management-web.onrender.com)"

    result = send_wecom_message(msg)
    if 'error' in result:
        return jsonify(result), 500
    return jsonify({'message': '宸插彂閫佸埌浼佸井缇?, 'result': result})


# ---- 浜烘墠绔細鎴戠殑鎶ュ悕 & 鎴戠殑璇勪环 ----

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


# ---- 绯荤粺璁剧疆 API ----

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
    return jsonify({'message': '璁剧疆宸蹭繚瀛?, 'key': key, 'value': value})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
