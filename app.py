import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import os
import json
import ddddocr

# ========================================================
# 1. 配置文件路径定义
# ========================================================
COURSES_FILE = "courses_config.json"
DATABASE_FILE = "database.json"

# ========================================================
# 2. 数据持久化助手函数
# ========================================================
def load_courses():
    if os.path.exists(COURSES_FILE):
        with open(COURSES_FILE, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    default_courses = {
        "领导力": "https://cdcas.suwankj.com/user/exam?nodeId=1841638&examId=1016116",
        "营养学": "https://cdcas.suwankj.com/user/exam?nodeId=1841541&examId=1016123"
    }
    save_courses(default_courses)
    return default_courses

def save_courses(courses_dict):
    with open(COURSES_FILE, "w", encoding="utf-8") as f:
        json.dump(courses_dict, f, ensure_ascii=False, indent=4)

def load_data():
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    return []

def save_data(data):
    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# ========================================================
# 3. 核心爬虫类 (支持传入账号对象)
# ========================================================
class AutoExamScraper:
    def __init__(self, account_info):
        self.username = account_info['u']
        self.password = account_info['p']
        self.base_url = "https://cdcas.suwankj.com"
        self.session = requests.Session()
        self.ocr = ddddocr.DdddOcr(show_ad=False)
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36...',
            'X-Requested-With': 'XMLHttpRequest'
        }

    def login(self):
        try:
            self.session.cookies.clear()
            resp_code = self.session.get(f"{self.base_url}/service/code", timeout=10)
            captcha_text = self.ocr.classification(resp_code.content)
            login_data = {"username": self.username, "password": self.password, "code": captcha_text, "redirect": ""}
            resp = self.session.post(f"{self.base_url}/user/login", data=login_data, headers=self.headers, timeout=10)
            decoded_text = resp.content.decode('utf-8-sig')
            res_json = json.loads(decoded_text)
            return res_json.get('status'), res_json.get('msg', '未知错误')
        except Exception as e:
            return False, f"网络异常: {str(e)}"

    def fetch_data(self, url, course_name):
        try:
            resp = self.session.get(url, timeout=15)
            soup = BeautifulSoup(resp.text, 'html.parser')
            questions = soup.find_all('div', class_='courseexamcon-main')
            extracted = []
            for q in questions:
                name_div = q.find('div', class_='name')
                if not name_div: continue
                opts, ans = [], []
                for ipt in q.select('input'):
                    txt_span = ipt.find_next('span', class_='txt')
                    if txt_span:
                        val = txt_span.get_text(strip=True)
                        opts.append(val)
                        if ipt.has_attr('checked'): ans.append(val)
                q_type = "多选题" if len(ans) > 1 else ("判断题" if any(w in "".join(ans) for w in ["正确", "错误"]) else "单选题")
                extracted.append({"Course": course_name, "Type": q_type, "Content": name_div.get_text(strip=True), "options": opts, "Answers": ans})
            return extracted
        except: return []

# ========================================================
# 4. Streamlit UI
# ========================================================
st.set_page_config(page_title="粟湾/如仁题库中心", layout="wide")

# 左侧批量账户解析
with st.sidebar:
    st.header("批量账户设置")
    accounts_raw = st.text_area("格式：账号 密码 (每行一个)", height=200, placeholder="Acconut password")
    
    parsed_accounts = []
    if accounts_raw.strip():
        for line in accounts_raw.strip().split('\n'):
            parts = line.split()
            if len(parts) >= 2:
                parsed_accounts.append({'u': parts[0], 'p': parts[1]})
    
    if parsed_accounts:
        st.success(f"已识别 {len(parsed_accounts)} 个账户")
        selected_acc_idx = st.selectbox("当前使用的同步账户", range(len(parsed_accounts)), format_func=lambda x: parsed_accounts[x]['u'])
        active_acc = parsed_accounts[selected_acc_idx]
    else:
        st.error("请输入至少一个有效账户")
        active_acc = None

st.title("粟湾/如仁题库中心")

current_conf = load_courses()
tab_sync, tab_view, tab_manage = st.tabs(["题库同步更新", "题库在线浏览", "系统管理设置"])

# --- Tab 1: 同步 ---
with tab_sync:
    st.subheader("抓取新题目")
    if not current_conf:
        st.warning("请先在系统管理中添加课程。")
    else:
        sel_name = st.selectbox("目标课程", list(current_conf.keys()))
        if st.button("开始同步", type="primary"):
            if not active_acc:
                st.error("请先设置左侧账户")
            else:
                scraper = AutoExamScraper(active_acc)
                with st.spinner(f"正在使用 {active_acc['u']} 同步中..."):
                    ok, msg = scraper.login()
                    if ok:
                        items = scraper.fetch_data(current_conf[sel_name], sel_name)
                        db = load_data()
                        old_keys = {f"{i['Course']}_{i['Content']}" for i in db}
                        added = [i for i in items if f"{i['Course']}_{i['Content']}" not in old_keys]
                        if added:
                            save_data(db + added)
                            st.success(f"同步成功！新增 {len(added)} 题")
                        else: st.info("暂无新题")
                    else: st.error(f"登录失败: {msg}")

# --- Tab 2: 浏览与删除 ---
with tab_view:
    db = load_data()
    if not db:
        st.info("题库为空")
    else:
        col_ctrl1, col_ctrl2 = st.columns([1, 1])
        c_filter = col_ctrl1.selectbox("筛选课程", ["全部"] + sorted(list(set(i['Course'] for i in db))))
        s_key = col_ctrl2.text_input("搜索关键词")
        
        # 过滤
        filtered = []
        for i in db:
            if (c_filter == "全部" or i['Course'] == c_filter) and (not s_key or s_key in i['Content']):
                filtered.append(i)
        
        # 危险操作区
        with st.expander("⚠️ 批量删除"):
            c1, c2 = st.columns(2)
            if c1.button(f"清空【{c_filter}】的全部题目"):
                new_db = [i for i in db if i not in filtered]
                save_data(new_db)
                st.rerun()
            if c2.button("清空本地所有题库数据"):
                save_data([])
                st.rerun()

        # 数据表格与逐行删除
        for idx, item in enumerate(filtered):
            with st.container():
                col_info, col_del = st.columns([9, 1])
                col_info.markdown(f"**{idx+1}. [{item['Course']}]** {item['Content']}")
                col_info.caption(f"选项: {' | '.join(item['options'])}  \n答案: {', '.join(item['Answers'])}")
                if col_del.button("删除", key=f"del_q_{idx}"):
                    db.remove(item)
                    save_data(db)
                    st.rerun()
                st.divider()
        
        st.markdown(f"**当前显示: {len(filtered)} 题**")
        js = json.dumps(filtered, ensure_ascii=False, indent=4)
        st.download_button("下载 JSON", js, f"data_{c_filter}.json")

# --- Tab 3: 管理课程 ---
with tab_manage:
    st.subheader("课程列表管理")
    with st.expander("➕ 添加课程"):
        with st.form("add_course"):
            cn, cu = st.text_input("课程名"), st.text_input("URL")
            if st.form_submit_button("保存"):
                if cn and cu:
                    current_conf[cn] = cu
                    save_courses(current_conf)
                    st.rerun()
    
    st.write("---")
    for name, url in list(current_conf.items()):
        c1, c2, c3 = st.columns([1, 4, 1])
        c1.write(f"**{name}**")
        c2.code(url)
        if c3.button("删除", key=f"del_c_{name}"):
            del current_conf[name]
            save_courses(current_conf)
            st.rerun()
