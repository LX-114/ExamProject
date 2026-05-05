import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import os
import json
import ddddocr
import time

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
        "营养学": "https://cdcas.suwankj.com/user/exam?nodeId=1841541&examId=1016123",
        "生态学": "https://cdcas.suwankj.com/user/exam?nodeId=1847312&examId=1016124",
        "沟通理论与技巧": "https://cdcas.suwankj.com/user/exam?nodeId=1847310&examId=1016131",
        "低碳能源": "https://cdcas.suwankj.com/user/exam?nodeId=1841648&examId=1016128"
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
# 3. 核心爬虫类
# ========================================================
class AutoExamScraper:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.base_url = "https://cdcas.suwankj.com"
        self.session = requests.Session()
        self.ocr = ddddocr.DdddOcr(show_ad=False)
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'X-Requested-With': 'XMLHttpRequest'
        }

    def login(self):
        try:
            self.session.cookies.clear()
            resp_code = self.session.get(f"{self.base_url}/service/code", timeout=10)
            if resp_code.status_code != 200:
                return False, f"验证码接口异常，状态码: {resp_code.status_code}"
            captcha_text = self.ocr.classification(resp_code.content)
            login_data = {"username": self.username, "password": self.password, "code": captcha_text, "redirect": ""}
            resp = self.session.post(f"{self.base_url}/user/login", data=login_data, headers=self.headers, timeout=10)
            try:
                decoded_text = resp.content.decode('utf-8-sig')
                res_json = json.loads(decoded_text)
                return res_json.get('status'), res_json.get('msg', '未知错误')
            except json.JSONDecodeError:
                return False, "接口未返回JSON (账号密码可能错误或被拦截)"
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

with st.sidebar:
    st.header("批量账户设置")
    acc_list_raw = st.text_area("请输入账户列表 (每行一个：账号 密码)", height=250)
    parsed_accounts = []
    if acc_list_raw.strip():
        for line in acc_list_raw.strip().split('\n'):
            parts = line.split()
            if len(parts) >= 2:
                parsed_accounts.append({"user": parts[0], "pwd": parts[1]})
    if parsed_accounts: st.success(f"✅ 已识别 {len(parsed_accounts)} 个账户")

st.title("粟湾/如仁题库中心")

current_conf = load_courses()
t_sync, t_view, t_manage = st.tabs(["题库同步更新", "题库在线浏览", "课程管理设置"])

# --- Tab 1: 同步 ---
with t_sync:
    st.subheader("抓取新题目")
    if not current_conf:
        st.warning("请添加课程。")
    else:
        sel_name = st.selectbox("请选择要同步的课程", list(current_conf.keys()))
        if st.button("开始同步更新", type="primary"):
            if not parsed_accounts:
                st.error("请输入账户列表！")
            else:
                total_new = 0
                success_details = [] # 用于存储每个账号新增的数量
                progress_text = st.empty()
                
                for idx, acc in enumerate(parsed_accounts):
                    u_acc, u_pwd = acc['user'], acc['pwd']
                    progress_text.info(f"🔄 处理中 ({idx+1}/{len(parsed_accounts)}): {u_acc}")
                    
                    scr = AutoExamScraper(u_acc, u_pwd)
                    ok, msg = scr.login()
                    if ok:
                        items = scr.fetch_data(current_conf[sel_name], sel_name)
                        db = load_data()
                        old_keys = {f"{i['Course']}_{i['Content']}" for i in db}
                        added = [i for i in items if f"{i['Course']}_{i['Content']}" not in old_keys]
                        if added:
                            save_data(db + added)
                            count = len(added)
                            total_new += count
                            success_details.append(f"{u_acc} 新增 {count} 道题目")
                        st.toast(f"{u_acc} 同步完毕")
                    else:
                        st.error(f"❌ 账户 {u_acc} 登录失败: {msg}")
                    time.sleep(0.5)
                
                # 在红框区域显示详细汇总信息
                if success_details:
                    summary_msg = "🏁 批量同步任务完成！\n\n" + "\n\n".join(success_details) + f"\n\n**本次共累计新增 {total_new} 道题目。**"
                    progress_text.success(summary_msg)
                else:
                    progress_text.success(f"🏁 任务结束。本次未发现新题目。")

# --- Tab 2: 浏览与删除 ---
with t_view:
    db = load_data()
    if not db:
        st.info("暂无数据。")
    else:
        col_f1, col_f2 = st.columns([1, 1])
        c_filter = col_f1.selectbox("筛选课程", ["全部"] + sorted(list(set(i['Course'] for i in db))))
        s_key = col_f2.text_input("搜索题目关键词")
        
        if c_filter != "全部":
            if st.button(f"🗑️ 清空【{c_filter}】的所有题库数据"):
                new_db = [i for i in db if i['Course'] != c_filter]
                save_data(new_db)
                st.rerun()
        
        filtered = db if c_filter == "全部" else [i for i in db if i['Course'] == c_filter]
        if s_key: filtered = [i for i in filtered if s_key in i['Content']]
        
        for idx, item in enumerate(filtered):
            with st.container():
                c1, c2 = st.columns([10, 1])
                c1.markdown(f"**{idx+1}. [{item['Course']}]** {item['Content']}")
                c1.caption(f"选项: {' | '.join(item['options'])}  \n答案: {', '.join(item['Answers'])}")
                if c2.button("删除", key=f"del_{idx}"):
                    db = [i for i in db if not (i['Course'] == item['Course'] and i['Content'] == item['Content'])]
                    save_data(db)
                    st.rerun()
                st.divider()
        st.markdown(f"### 📊 统计：当前显示 **{len(filtered)}** 道题目")

# --- Tab 3: 管理 ---
with t_manage:
    st.subheader("管理课程清单")
    with st.expander("➕ 添加课程"):
        with st.form("add_form"):
            n, l = st.text_input("课程名"), st.text_input("URL")
            if st.form_submit_button("确认"):
                if n and l:
                    conf = load_courses(); conf[n] = l; save_courses(conf); st.rerun()
    for name, url in list(current_conf.items()):
        c1, c2, c3 = st.columns([1, 4, 1])
        c1.write(f"**{name}**")
        c2.code(url)
        if c3.button("删除", key=f"c_{name}"):
            del current_conf[name]; save_courses(current_conf); st.rerun()
