import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import os
import json
import ddddocr
import time

# ========================================================
# 1. 配置文件路径
# ========================================================
COURSES_FILE = "courses_config.json"
DATABASE_FILE = "database.json"

# ========================================================
# 2. 数据持久化助手
# ========================================================
def load_courses():
    if os.path.exists(COURSES_FILE):
        with open(COURSES_FILE, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    return {"领导力": "https://cdcas.suwankj.com/user/exam?nodeId=1841638&examId=1016116"}

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
# 3. 核心爬虫类
# ========================================================
class AutoExamScraper:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.base_url = "https://cdcas.suwankj.com"
        self.session = requests.Session()
        self.ocr = ddddocr.DdddOcr(show_ad=False)
        self.headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36...'}

    def login(self):
        try:
            self.session.cookies.clear()
            resp_code = self.session.get(f"{self.base_url}/service/code", timeout=10)
            captcha_text = self.ocr.classification(resp_code.content)
            login_data = {"username": self.username, "password": self.password, "code": captcha_text, "redirect": ""}
            resp = self.session.post(f"{self.base_url}/user/login", data=login_data, timeout=10)
            res_json = json.loads(resp.content.decode('utf-8-sig'))
            return res_json.get('status'), res_json.get('msg', '未知错误')
        except Exception as e:
            return False, f"网络错误: {str(e)}"

    def fetch_data(self, url, course_name):
        try:
            resp = self.session.get(url, timeout=15)
            soup = BeautifulSoup(resp.text, 'html.parser')
            questions = soup.find_all('div', class_='courseexamcon-main')
            extracted = []
            for q in questions:
                name = q.find('div', class_='name')
                if not name: continue
                opts, ans = [], []
                for ipt in q.select('input'):
                    txt = ipt.find_next('span', class_='txt')
                    if txt:
                        val = txt.get_text(strip=True)
                        opts.append(val)
                        if ipt.has_attr('checked'): ans.append(val)
                q_type = "多选题" if len(ans) > 1 else ("判断题" if any(w in "".join(ans) for w in ["正确", "错误"]) else "单选题")
                extracted.append({"Course": course_name, "Type": q_type, "Content": name.get_text(strip=True), "options": opts, "Answers": ans})
            return extracted
        except: return []

# ========================================================
# 4. Streamlit UI
# ========================================================
st.set_page_config(page_title="粟湾/如仁题库中心", layout="wide")

# 左侧账户批量设置
with st.sidebar:
    st.header("批量账户设置")
    accounts_input = st.text_area("格式：账号 密码 (每行一个)", height=250, placeholder="Acconut password")
    
    parsed_accounts = []
    if accounts_input.strip():
        for line in accounts_input.strip().split('\n'):
            parts = line.split()
            if len(parts) >= 2:
                parsed_accounts.append({'u': parts[0], 'p': parts[1]})
    
    if parsed_accounts:
        st.success(f"✅ 已识别 {len(parsed_accounts)} 个账户")
    else:
        st.warning("⚠️ 请输入账号和密码")

st.title("粟湾/如仁题库中心")

current_conf = load_courses()
tab_sync, tab_view, tab_manage = st.tabs(["题库同步更新", "题库在线浏览", "系统管理设置"])

# --- Tab 1: 自动化批量同步 ---
with tab_sync:
    st.subheader("全自动抓取新题目")
    if not current_conf:
        st.error("请先在‘系统管理’中添加课程链接")
    else:
        target_course = st.selectbox("目标课程", list(current_conf.keys()))
        
        if st.button("开始批量同步", type="primary"):
            if not parsed_accounts:
                st.error("左侧账户列表为空，无法开始同步")
            else:
                total_new = 0
                progress_bar = st.progress(0)
                status_text = st.empty()
                log_container = st.container()
                
                with log_container:
                    st.info(f"开始执行批量同步任务，目标课程：{target_course}")
                    
                    for i, acc in enumerate(parsed_accounts):
                        # 更新进度
                        progress = (i + 1) / len(parsed_accounts)
                        progress_bar.progress(progress)
                        status_text.text(f"正在处理第 {i+1}/{len(parsed_accounts)} 个账户: {acc['u']}")
                        
                        # 执行登录与抓取
                        scraper = AutoExamScraper(acc['u'], acc['p'])
                        ok, msg = scraper.login()
                        
                        if ok:
                            data = scraper.fetch_data(current_conf[target_course], target_course)
                            db = load_data()
                            old_keys = {f"{item['Course']}_{item['Content']}" for item in db}
                            added = [item for item in data if f"{item['Course']}_{item['Content']}" not in old_keys]
                            
                            if added:
                                save_data(db + added)
                                total_new += len(added)
                                st.write(f"✔️ 账户 {acc['u']}: 同步成功，新增 {len(added)} 题")
                            else:
                                st.write(f"⚪ 账户 {acc['u']}: 已是最新，无新题")
                        else:
                            st.error(f"❌ 账户 {acc['u']}: 登录失败 ({msg})")
                        
                        # 稍微停顿，防止请求过快
                        time.sleep(0.5)
                
                st.success(f"🎉 任务完成！本次批量操作共累计新增 {total_new} 道题目。")

# --- Tab 2: 浏览与单题管理 ---
with tab_view:
    db = load_data()
    if not db:
        st.info("题库为空")
    else:
        col1, col2 = st.columns([1, 1])
        f_course = col1.selectbox("筛选课程", ["全部"] + sorted(list(set(i['Course'] for i in db))))
        f_search = col2.text_input("搜索关键词")
        
        filtered = [i for i in db if (f_course == "全部" or i['Course'] == f_course) and (not f_search or f_search in i['Content'])]
        
        # 批量工具
        with st.expander("🛠️ 批量管理选项"):
            if st.button(f"清空【{f_course}】课程下的所有题目"):
                new_db = [i for i in db if i not in filtered]
                save_data(new_db)
                st.rerun()
        
        # 列表展示
        for idx, item in enumerate(filtered):
            with st.container():
                c_main, c_del = st.columns([10, 1])
                c_main.markdown(f"**{idx+1}.** {item['Content']}")
                c_main.caption(f"[{item['Course']} | {item['Type']}] 选项: {' / '.join(item['options'])} | 答案: {', '.join(item['Answers'])}")
                if c_del.button("删除", key=f"del_{idx}"):
                    db.remove(item)
                    save_data(db)
                    st.rerun()
                st.divider()

# --- Tab 3: 课程管理 ---
with tab_manage:
    st.subheader("课程列表管理")
    with st.expander("➕ 添加新课程链接"):
        with st.form("add_c"):
            name = st.text_input("课程名称")
            url = st.text_input("抓取页面的URL")
            if st.form_submit_button("保存"):
                if name and url:
                    conf = load_courses()
                    conf[name] = url
                    save_courses(conf)
                    st.rerun()
    
    st.write("---")
    conf = load_courses()
    for name, url in list(conf.items()):
        c1, c2, c3 = st.columns([1, 4, 1])
        c1.write(f"**{name}**")
        c2.code(url)
        if c3.button("删除", key=f"c_del_{name}"):
            del conf[name]
            save_courses(conf)
            st.rerun()
