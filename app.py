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




    "测试执行": [




        {"label": "2H以内/场", "price": 150},




        {"label": "2~4小时/场", "price": 200},




        {"label": "4~6小时/场", "price": 250},




    ],




    "街访执行": [




        # 街访1（拦截+访谈）




        {"label": "10分钟以内", "price": 30, "base": 120},




        {"label": "30分钟以内", "price": 65, "base": 120},




        {"label": "30~60分钟", "price": 104, "base": 120},




        # 街访2（只拦截不访谈）




        {"label": "千万级", "gmv_rate": 0.05, "gmv_rate_display": "GMV×5%", "base": 120, "fixed": 3000},




        {"label": "百万级", "gmv_rate": 0.10, "gmv_rate_display": "GMV×10%", "base": 120, "fixed": 1500},




        {"label": "十万级", "gmv_rate": 0.20, "gmv_rate_display": "GMV×20%", "base": 120, "fixed": 800},




        {"label": "千级及以下", "gmv_rate": None, "gmv_rate_display": "固定200元", "base": 120, "fixed": 200},




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


    "甄别+外呼": [
        {"label": "5~10mins/个", "price": 10},
        {"label": "10~20mins/个", "price": 10},
        {"label": "20~30mins/个", "price": 16},
        {"label": ">30mins/个", "price": 20},
    ],

    "电访+外呼": [
        {"label": "30mins以内/个", "price": 30},
        {"label": "30~60mins/个", "price": 45},
        {"label": "60~90mins/个（仅限5星兼职）", "price": 80},
        {"label": "90~120mins/个", "price": 100},
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




    if biz in ("甄别", "甄别+外呼", "电访", "电访+外呼", "街访执行", "测试执行") and not gmv:




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









    elif biz == "甄别+外呼":
        outer_tiers = TALENT_PRICE_TABLE.get("甄别+外呼", [])
        outer_tier_data = next((t for t in outer_tiers if t["label"] == tier), None)
        unit_price = outer_tier_data.get("price", 0) if outer_tier_data else 0
        part_time_wage = (unit_price + 20) * quantity
        wage_note = f"({unit_price}+20元呼出)/样本×{quantity} = {int(part_time_wage)}元"
        h = vlookup_h(gmv, LUT_ZHENBIE)
        human_cost = h * 1200
        human_note = f"样本数{gmv}→人力投入{h}×1200 = {int(human_cost)}元"

    elif biz == "甄别":


        unit_price = tier_data.get("price", 0)


        # 甄别（无外呼）：纯样本单价×数量，无呼出费
        part_time_wage = unit_price * quantity
        wage_note = f"{unit_price}元/样本×{quantity}个 = {int(part_time_wage)}元"

        h = vlookup_h(gmv, LUT_ZHENBIE)

        # 甄别+外呼：(样本单价+20元呼出预估)×n，20是每个样本的呼出费用预估
        if brush:
            part_time_wage = (unit_price + 20) * quantity
            wage_note = (f"({unit_price}+20元呼出)/样本×{quantity} = {int(part_time_wage)}元")

        human_cost = h * 1200
        human_note = f"样本数{gmv}→人力投入{h}×1200 = {int(human_cost)}元"
    elif biz == "电访+外呼":
        outer_tiers = TALENT_PRICE_TABLE.get("电访+外呼", [])
        outer_tier_data = next((t for t in outer_tiers if t["label"] == tier), None)
        unit_price = outer_tier_data.get("price", 0) if outer_tier_data else 0
        part_time_wage = (unit_price + 20) * quantity
        wage_note = f"({unit_price}+20元呼出)/个×{quantity} = {int(part_time_wage)}元"
        h = vlookup_h(gmv, LUT_DIANFANG)
        human_cost = h * 1200
        human_note = f"样本数{gmv}→人力投入{h}×1200 = {int(human_cost)}元"

    elif biz == "电访":


        unit_price = tier_data.get("price", 0)


        # 电访（无外呼）：纯样本单价×数量，无呼出费
        part_time_wage = unit_price * quantity
        wage_note = f"{unit_price}元/个×{quantity}个 = {int(part_time_wage)}元"

        h = vlookup_h(gmv, LUT_DIANFANG)

        # 电访+外呼：(样本单价+20元呼出预估)×n，20是每个样本的呼出费用预估
        if brush:
            part_time_wage = (unit_price + 20) * quantity
            wage_note = (f"({unit_price}+20元呼出)/个×{quantity} = {int(part_time_wage)}元")

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









    elif biz == "实验室执行":

        unit_price = tier_data.get("price", 0)
        parttimer_count = demand_data.get("parttimer_count", 1)
        sessions = demand_data.get("sessions_per_parttimer", 1)
        meals_per_day = demand_data.get("meals_per_day", 1)
        start_date_str = demand_data.get("start_date", "")
        end_date_str = demand_data.get("end_date", "")

        days = 1
        if start_date_str and end_date_str:
            try:
                from datetime import datetime
                s = datetime.strptime(start_date_str, "%Y-%m-%d")
                e = datetime.strptime(end_date_str, "%Y-%m-%d")
                delta = (e - s).days + 1
                days = max(1, delta)
            except:
                days = 1

        base_wage = sessions * unit_price
        meal_fee = 30 * meals_per_day * days
        transport_fee = 50 * days
        part_time_wage = parttimer_count * (base_wage + meal_fee + transport_fee)
        wage_note = f"{parttimer_count}人×({sessions}场×{unit_price}元+30×{meals_per_day}餐×{days}天+50×{days}天) = {int(part_time_wage)}元"

        human_cost = 0
        human_note = "无人力成本"

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




                attitude_rating INTEGER,




                quality_rating INTEGER,




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




                attitude_rating INTEGER,




                quality_rating INTEGER,




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




            "INSERT INTO users (username, password, role, email) VALUES (%s, %s, %s, %s)"




            if DATABASE_URL else




            "INSERT INTO users (username, password, role, email) VALUES (?, ?, ?, ?)",




            ('admin', 'admin123', 'admin', "")




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




        cursor.execute("SELECT id, username, role, email FROM users")




    else:




        cursor.execute("SELECT id, username, role, email FROM users")




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




        cursor.execute("SELECT id, username, role, email, created_at FROM users ORDER BY id")




    else:




        cursor.execute("SELECT id, username, role, email, created_at FROM users ORDER BY id")




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




            cursor.execute("INSERT INTO users (username, password, role, email) VALUES (%s, %s, %s, %s)",




                           (username, password, role, data.get("email", "")))




            cursor.execute("SELECT lastval()")




            user_id = cursor.fetchone()[0]




        else:




            cursor.execute("INSERT INTO users (username, password, role, email) VALUES (?, ?, ?, ?)",




                           (username, password, role, data.get("email", "")))




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




        result = {'success': True, 'user': {'id': user['id'], 'username': user['username'], 'role': user['role'], 'email': user.get('email', '')}}




        close_conn(conn)




        return jsonify(result)




    close_conn(conn)




    return jsonify({'success': False, 'error': 'Invalid credentials'}), 401


















def send_email(to_email, subject, html_body, text_body):
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    sh = get_setting("smtp_host", "smtp.163.com")
    sp = int(get_setting("smtp_port", "587"))
    su = get_setting("smtp_user", "j9415821108@163.com")
    sppw = get_setting("smtp_password", "XTT5B8AiKmxBkfHE")
    ss = get_setting("smtp_sender", "j9415821108@163.com")
    if not to_email or not sh:
        return False, "no config"
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = ss
        msg["To"] = to_email
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))
        timeout = 15
        try:
            srv = smtplib.SMTP(sh, sp, timeout=timeout)
            srv.starttls()
        except (OSError, TimeoutError):
            try:
                srv = smtplib.SMTP_SSL(sh, 465, timeout=timeout)
            except (OSError, TimeoutError) as e:
                return False, "SMTP connection failed: " + str(e)
        srv.login(su, sppw)
        srv.sendmail(su, [to_email], msg.as_string())
        srv.quit()
        return True, "sent"
    except Exception as ex:
        return False, str(ex)


@app.route('/api/demands/<int:demand_id>/gongzhang-yiti', methods=['POST'])
def gongzhang_yiti_email(demand_id):
    try:
        conn = get_db()
        cursor = conn.cursor()
        if DATABASE_URL:
            cursor.execute("SELECT * FROM demands WHERE id = %s", (demand_id,))
        else:
            cursor.execute("SELECT * FROM demands WHERE id = ?", (demand_id,))
        demand = fetchone_dict(cursor)
        if not demand:
            close_conn(conn)
            return jsonify({'error': 'Demand not found'}), 404
        if DATABASE_URL:
            cursor.execute("UPDATE demands SET status = 'done', gongzhang_yiti = 1 WHERE id = %s", (demand_id,))
        else:
            cursor.execute("UPDATE demands SET status = 'done', gongzhang_yiti = 1 WHERE id = ?", (demand_id,))
        conn.commit()
        if DATABASE_URL:
            cursor.execute("SELECT t.name, t.phone, COALESCE(t.wechat, '') as wechat FROM demand_applications da JOIN talents t ON da.talent_id = t.id WHERE da.demand_id = %s AND da.status = 'selected'", (demand_id,))
        else:
            cursor.execute("SELECT t.name, t.phone, COALESCE(t.wechat, '') as wechat FROM demand_applications da JOIN talents t ON da.talent_id = t.id WHERE da.demand_id = ? AND da.status = 'selected'", (demand_id,))
        selected_list = fetchall_dicts(cursor)
        try:
            de = ""
            demander_name = ""
            print("DEBUG email: demand_id=%s, demander_id=%s" % (demand_id, demand.get('demander_id')))
            if demand.get('demander_id'):
                cursor.execute("SELECT email, username FROM users WHERE id = %s", (demand.get('demander_id'),))
                ur = fetchone_dict(cursor)
                if ur:
                    de = ur.get('email') or ""
                    demander_name = ur.get('username') or ""
            if de:
                dt = demand.get('title') or demand.get('product_code') or ""
                biz = demand.get('biz_type') or demand.get('business_type') or ""
                parent_oid = demand.get('parent_order') or ""
                base_url = "http://talent-management-web.onrender.com"
                subj = dt + " 兼职需求已完结，请评价"
                # Plain text email
                po_line = ("【父单单号】" + parent_oid + " " if parent_oid else "")
                lines = [
                    "哈喽" + demander_name + "：",
                    "您的" + po_line + "兼职需求已完结，请对下列兼职的工作质量进行评价",
                    "",
                ]
                if biz:
                    lines.append("【业务类型】" + biz)
                lines.append("")
                for t in (selected_list or []):
                    name = t.get('name') or "未知"
                    lines.append(name + "：1-5分（评分）+评语（填空，非必答）")
                    lines.append("")
                tb = "\n".join(lines)
                tb += "\n评价链接：" + base_url + "/evaluate?demand_id=" + str(demand_id) + " 点此评价"
                hl = ["<html><body>",
                      "<p>哈喽" + demander_name + "：</p>",
                      "<p>您的" + po_line + "兼职需求已完结，请对下列兼职的工作质量进行评价</p>"]
                if biz:
                    hl.append("<p>【业务类型】" + biz + "</p>")
                hl.append("<ul>")
                for t in (selected_list or []):
                    name = t.get('name') or "未知"
                    hl.append("<li>" + name + "：1-5分（评分）+评语（填空，非必答）</li>")
                hl.append("</ul>")
                hl.append("<p><a href='" + base_url + "/evaluate?demand_id=" + str(demand_id) + "'>点此评价</a></p>")
                hl.append("</body></html>")
                hb = "".join(hl)
                ok, r = send_email(de, subj, hb, tb)
                if not ok:
                    print("Email failed:", r)
        except Exception as emerr:
            print("Email error:", emerr)
        close_conn(conn)
        return jsonify({'message': 'Done', 'gongzhang_yiti': True, 'selected_count': len(selected_list)})
    except Exception as e:
        return jsonify({'error': 'Server error: ' + str(e)}), 500




@app.route('/api/debug/demand/<int:demand_id>/email-info', methods=['GET'])
def debug_email_info(demand_id):
    """诊断公账已提邮件为什么没发"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        if DATABASE_URL:
            cursor.execute("SELECT * FROM demands WHERE id = %s", (demand_id,))
        else:
            cursor.execute("SELECT * FROM demands WHERE id = ?", (demand_id,))
        demand = fetchone_dict(cursor)
        if not demand:
            close_conn(conn)
            return jsonify({'error': 'Demand not found'}), 404

        result = {
            'demand_id': demand_id,
            'title': demand.get('title'),
            'product_code': demand.get('product_code'),
            'demander_id': demand.get('demander_id'),
            'tidanren': demand.get('tidanren'),
        }

        # Check user email
        if demand.get('demander_id'):
            if DATABASE_URL:
                cursor.execute("SELECT id, username, email FROM users WHERE id = %s", (demand.get('demander_id'),))
            else:
                cursor.execute("SELECT id, username, email FROM users WHERE id = ?", (demand.get('demander_id'),))
            ur = fetchone_dict(cursor)
            if ur:
                result['user'] = {'id': ur['id'], 'username': ur.get('username'), 'email': ur.get('email')}
                result['email_will_send'] = bool(ur.get('email'))
            else:
                result['user'] = None
                result['email_will_send'] = False
                result['reason'] = 'user not found'
        else:
            result['email_will_send'] = False
            result['reason'] = 'demander_id is empty/None'

        # Check selected talents
        if DATABASE_URL:
            cursor.execute("SELECT name, phone FROM demand_applications da JOIN talents t ON da.talent_id = t.id WHERE da.demand_id = %s AND da.status = 'selected'", (demand_id,))
        else:
            cursor.execute("SELECT name, phone FROM demand_applications da JOIN talents t ON da.talent_id = t.id WHERE da.demand_id = ? AND da.status = 'selected'", (demand_id,))
        selected = fetchall_dicts(cursor)
        result['selected_count'] = len(selected)
        result['selected_talents'] = selected

        close_conn(conn)
        return jsonify(result)
    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'trace': traceback.format_exc()[-500:]}), 500


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




        tidanren = request.args.get('tidanren', '')









        conn = get_db()




        cursor = conn.cursor()









        if DATABASE_URL:




            if status:




                if tidanren:




                    cursor.execute("SELECT COUNT(*) FROM demands WHERE status = %s AND tidanren = %s", (status, tidanren))




                else:




                    cursor.execute("SELECT COUNT(*) FROM demands WHERE status = %s", (status,))




            else:




                if tidanren:




                    cursor.execute("SELECT COUNT(*) FROM demands WHERE tidanren = %s", (tidanren,))




                else:




                    cursor.execute("SELECT COUNT(*) FROM demands")




        else:




            if status:




                if tidanren:




                    cursor.execute("SELECT COUNT(*) FROM demands WHERE status = ? AND tidanren = ?", (status, tidanren))




                else:




                    cursor.execute("SELECT COUNT(*) FROM demands WHERE status = ?", (status,))




            else:




                if tidanren:




                    cursor.execute("SELECT COUNT(*) FROM demands WHERE tidanren = ?", (tidanren,))




                else:




                    cursor.execute("SELECT COUNT(*) FROM demands")









        total = cursor.fetchone()[0]









        if DATABASE_URL:




            if status:




                if tidanren:




                    cursor.execute(f"SELECT * FROM demands WHERE status = %s AND tidanren = %s ORDER BY id DESC LIMIT %s OFFSET %s", (status, tidanren, per_page, (page-1)*per_page))




                else:




                    cursor.execute(f"SELECT * FROM demands WHERE status = %s ORDER BY id DESC LIMIT %s OFFSET %s", (status, per_page, (page-1)*per_page))




            else:




                if tidanren:




                    cursor.execute(f"SELECT * FROM demands WHERE tidanren = %s ORDER BY id DESC LIMIT %s OFFSET %s", (tidanren, per_page, (page-1)*per_page))




                else:




                    cursor.execute(f"SELECT * FROM demands ORDER BY id DESC LIMIT %s OFFSET %s", (per_page, (page-1)*per_page))




        else:




            if status:




                if tidanren:




                    cursor.execute(f"SELECT * FROM demands WHERE status = ? AND tidanren = ? ORDER BY id DESC LIMIT ? OFFSET ?", (status, tidanren, per_page, (page-1)*per_page))




                else:




                    cursor.execute(f"SELECT * FROM demands WHERE status = ? ORDER BY id DESC LIMIT ? OFFSET ?", (status, per_page, (page-1)*per_page))




            else:




                if tidanren:




                    cursor.execute(f"SELECT * FROM demands WHERE tidanren = ? ORDER BY id DESC LIMIT ? OFFSET ?", (tidanren, per_page, (page-1)*per_page))




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




                product_code, parent_order, child_order, execution_time




            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s, %s, %s, %s)




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




            data.get('product_code', ''), data.get('parent_order', ''), data.get('child_order', ''), data.get('execution_time', ''),




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




        cursor.execute("SELECT title, tidanren, product_code FROM demands WHERE id = %s", (demand_id,))




    else:




        cursor.execute("SELECT title, tidanren, product_code FROM demands WHERE id = ?", (demand_id,))




    demand_row = fetchone_dict(cursor)




    demand_title = demand_row['title']; tidanren = demand_row.get('tidanren', ''); product_code = demand_row.get('product_code', ''); tidanren = demand_row.get('tidanren', ''); product_code = demand_row.get('product_code', '') if demand_row else '未知需求'









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




    notify_result = send_wecom_group_notification(demand_title, demand_title, tidanren, product_code, selected_list)









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




        cursor.execute("SELECT title, tidanren, product_code FROM demands WHERE id = %s", (demand_id,))




    else:




        cursor.execute("SELECT title, tidanren, product_code FROM demands WHERE id = ?", (demand_id,))




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









    result = send_wecom_group_notification(demand_title, demand_title, tidanren, product_code, selected_list)




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














@app.route('/api/demands/<int:demand_id>/evaluate', methods=['POST'])




def create_evaluation(demand_id):




    data = request.json




    conn = get_db()




    cursor = conn.cursor()




    if DATABASE_URL:




        cursor.execute("""




            INSERT INTO demand_evaluations




                (demand_id, talent_id, rating, comment, evaluated_by, attitude_rating, quality_rating)




            VALUES (%s, %s, %s, %s, %s, %s, %s)




        """, (demand_id, data['talent_id'], (lambda a, q: a * 0.3 + q * 0.7 if (a and q) else (a or q))(int(data.get('attitude_rating') or 0), int(data.get('quality_rating') or 0)),




             data.get('comment', ''), data.get('evaluated_by'), data.get('attitude_rating'), data.get('quality_rating')))




    else:




        cursor.execute("""




            INSERT INTO demand_evaluations




                (demand_id, talent_id, rating, comment, evaluated_by, attitude_rating, quality_rating)




            VALUES (?, ?, ?, ?, ?, ?, ?)




        """, (demand_id, data['talent_id'], (lambda a, q: a * 0.3 + q * 0.7 if (a and q) else (a or q))(int(data.get('attitude_rating') or 0), int(data.get('quality_rating') or 0)),




             data.get('comment', ''), data.get('evaluated_by'), data.get('attitude_rating'), data.get('quality_rating')))




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




    try:




        wecom_url = get_setting('wecom_webhook_url')




        if not wecom_url:




            return {'error': '企微 Webhook URL 未配置，请在系统设置中填写'}




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














def send_wecom_group_notification(title, demand_title, tidanren, product_code, selected_list):




    """入选后发送企微群通知（通过群机器人）




    selected_list: [{'name': '张三', 'phone': '138xxx', 'wechat': 'zhangsan'}]




    """




    # 优先用 wecom_group_webhook_url，没有则复用 wecom_webhook_url（群机器人与个人机器人共享同一key）




    wecom_group_url = get_setting('wecom_group_webhook_url') or get_setting('wecom_webhook_url')




    if not wecom_group_url:




        return {'error': '企微 Webhook URL 未配置，请在系统设置中填写 wecom_webhook_url'}









    msg = f"### ✅ 入选通知\n"




    msg += f"**产品代号：** {product_code or title}\n"




    msg += f"**提单人：** {tidanren}\n" + f"**入选人数：** {len(selected_list)} 人\n\n"




    msg += "**入选名单：**\n"




    for i, t in enumerate(selected_list, 1):




        wechat_info = f"（微信号：{t['wechat']}）" if t.get('wechat') else "（暂无微信号）"




        msg += f"{i}. **{t['name']}** | {t['phone']} {wechat_info}\n"




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




    try:




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

        # 根据 business_type 和 tier 获取样本单价
        def get_sample_price(biz_type, tier):
            sample_prices = {
                "电访": {
                    "30mins以内/个": 30,
                    "30~60mins/个": 45,
                    "60~90mins/个（仅限5星兼职）": 80,
                    "90~120mins/个": 100,
                },
                "甄别": {
                    "5~10mins/个": 8,
                    "10~20mins/个": 12,
                    "20~30mins/个": 16,
                    ">30mins/个": 26,
                },
                "电访+外呼": {
                    "30mins以内/个": 30,
                    "30~60mins/个": 45,
                    "60~90mins/个（仅限5星兼职）": 80,
                    "90~120mins/个": 100,
                },
                "甄别+外呼": {
                    "5~10mins/个": 10,
                    "10~20mins/个": 10,
                    "20~30mins/个": 16,
                    ">30mins/个": 20,
                },
            }
            if biz_type in sample_prices:
                for key, price in sample_prices[biz_type].items():
                    if key in tier:
                        return price
            return 0










        product_code = demand.get('product_code') or demand.get('title', '')



        execution_time = (demand.get('execution_time') or '').strip()



        if not execution_time:



            from datetime import datetime, timedelta



            execution_time = (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d')








        msg_biz = demand.get('business_type') or ''




        msg_tier = demand.get('tier') or ''




        msg_qty = demand.get('quantity') or 0




        msg_deadline = (demand.get('deadline') or '').strip()




        msg_desc = demand.get('description') or ''










        msg = "### New 需求发布\n"



        msg += "**业务类型：** %s\n" % msg_biz



        msg += "**数量：** %s\n" % msg_qty



        if quote:



            pw = quote.get('part_time_wage', 0) or 0



            # Always show 单价 only in 企微 push
            biz = demand.get("business_type","")
            unit_price = get_sample_price(biz, demand.get("tier",""))
            if biz and "外呼" in biz:
                if "电访" in biz:
                    msg += "**单价：** (0.5/呼出+%s/个)\n" % unit_price
                else:
                    msg += "**单价：** (0.5/呼出+%s/样本)\n" % unit_price
            else:
                if "电访" in biz:
                    msg += "**单价：** %s/个\n" % unit_price
                elif "甄别" in biz:
                    msg += "**单价：** %s/样本\n" % unit_price

        msg += "\n**执行时间：** %s\n" % execution_time



        msg += "\n**截止日期：** %s\n" % msg_deadline



        msg += "**需求描述：** %s\n" % msg_desc



        msg += "---\n"



        msg += "> 点击报名：[系统链接](https://talent-management-web.onrender.com/apply?demand_id=%s)" % demand_id



        msg += "\n\n> ⚠️ **重要提示**：报名后请务必先添加管理员企微「菜菜」，否则后续无法通知入选结果"









        result = send_wecom_message(msg)




        if 'error' in result:




            return jsonify(result), 500




        return jsonify({'message': '已发送到企微群', 'result': result})
















    # ---- 人才端：我的报名 & 我的评价 ----














    except Exception as e:




        import traceback




        return jsonify({'error': 'Publish failed: ' + str(e), 'trace': traceback.format_exc()[-500:]}), 500














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


















def migrate_add_missing_columns():



    conn = get_db()



    cursor = conn.cursor()



    new_cols = {



        'product_code': 'TEXT',



        'parent_order': 'TEXT',



        'child_order': 'TEXT',



        'execution_time': 'TEXT',



        'gongzhang_yiti': 'INTEGER DEFAULT 0',
        'email': 'TEXT',



    }



    for col, col_type in new_cols.items():



        try:



            if DATABASE_URL:



                cursor.execute(f"ALTER TABLE demands ADD COLUMN {col} {col_type}")



            else:



                cursor.execute(f"PRAGMA table_info(demands)")



                existing_cols = [row['name'] for row in fetchall_dicts(cursor)]



                if col not in existing_cols:



                    cursor.execute(f"ALTER TABLE demands ADD COLUMN {col} {col_type}")



            conn.commit()



        except:



            conn.rollback()



    user_cols = {
        'email': 'TEXT',
    }

    for col, col_type in user_cols.items():
        try:
            if DATABASE_URL:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")
            else:
                cursor.execute(f"PRAGMA table_info(users)")
                existing_cols = [row['name'] for row in fetchall_dicts(cursor)]
                if col not in existing_cols:
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")
            conn.commit()
        except Exception as mig_err:
            conn.rollback()
            err_str = str(mig_err)
            if 'already exists' in err_str or 'duplicate' in err_str.lower():
                pass  # column already exists, ignore
            else:
                print(f"Migration error for users.{col}: {mig_err}")
    close_conn(conn)













def migrate_eval_columns():
    """Add attitude_rating and quality_rating columns to demand_evaluations"""
    conn = get_db()
    cursor = conn.cursor()
    new_cols = {
        'attitude_rating': 'INTEGER',
        'quality_rating': 'INTEGER',
    }
    for col, col_type in new_cols.items():
        try:
            if DATABASE_URL:
                cursor.execute(f"ALTER TABLE demand_evaluations ADD COLUMN {col} {col_type}")
            else:
                cursor.execute(f"PRAGMA table_info(demand_evaluations)")
                existing = [row['name'] for row in fetchall_dicts(cursor)]
                if col not in existing:
                    cursor.execute(f"ALTER TABLE demand_evaluations ADD COLUMN {col} {col_type}")
            conn.commit()
        except Exception as e:
            conn.rollback()
    close_conn(conn)

if __name__ == '__main__':




    migrate_add_missing_columns()




    migrate_eval_columns()




    init_wecom_settings()




    app.run(host='0.0.0.0', port=5000, debug=True)




else:




    with app.app_context():




        migrate_add_missing_columns()




        migrate_eval_columns()




        init_wecom_settings()





