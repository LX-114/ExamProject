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
# 2. 数据持久化助手函数 (统一使用 utf-8-sig)
# ========================================================
def load_courses():
    """加载课程配置"""
    if os.path.exists(COURSES_FILE):
        with open(COURSES_FILE, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    # 默认课程列表
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
    """保存课程配置"""
    with open(COURSES_FILE, "w", encoding="utf-8") as f:
        json.dump(courses_dict, f, ensure_ascii=False, indent=4)

def load_data():
    """加载本地题库数据"""
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    return []

def save_data(data):
    """保存题库数据"""
    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# ========================================================
# 3. 核心爬虫类 (增强调试与容错版)
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
        """执行登录并捕获非JSON异常响应"""
        try:
            self.session.cookies.clear()
            # 1. 获取验证码
            resp_code = self.session.get(f"{self.base_url}/service/code", timeout=10)
            if resp_code.status_code != 200:
                return False, f"验证码接口异常，状态码: {resp_code.status_code}"
                
            captcha_text = self.ocr.classification(resp_code.content)
            
            # 2. 提交登录
            login_data = {
                "username": self.username, 
                "password": self.password, 
                "code": captcha_text, 
                "redirect": ""
            }
            resp = self.session.post(f"{self.base_url}/user/login", data=login_data, headers=self.headers, timeout=10)
            
            # 3. 结果解析
            try:
                # 优先处理 BOM 字符
                decoded_text = resp.content.decode('utf-8-sig')
                if not decoded_text.strip():
                    return False, "服务器返回了空内容"
                
                # 尝试解析 JSON
                res_json = json.loads(decoded_text)
                return res_json.get('status'), res_json.get('msg', '未知错误')
                
            except json.JSONDecodeError:
                # 如果解析失败，获取页面预览用于排查（可能是防火墙拦截）
                preview = resp.text[:100].replace('\n', ' ')
                return False, f"接口未返回JSON (可能被拦截/重定向): {preview}..."
                
        except Exception as e:
            return False, f"网络连接异常: {str(e)}"

    def fetch_data(self, url, course_name):
        """解析网页题目数据"""
        try:
            resp = self.session.get(url, timeout=15)
            soup = BeautifulSoup(resp.text, 'html.parser')
            questions = soup.find_all('div', class_='courseexamcon-main')
            
            extracted = []
            for q in questions:
                name_div = q.find('div', class_='name')
                if not name_div: continue
                
                options_text, answers_text = [], []
                for ipt in q.select('input'):
                    txt_span = ipt.find_next('span', class_='txt')
                    if txt_span:
                        val = txt_span.get_text(strip=True)
                        options_text.append(val)
                        if ipt.has_attr('checked'):
                            answers_text.append(val)
                
                # 题型判断
                if len(answers_text) > 1: q_type = "多选题"
                elif any(word in "".join(answers_text) for word in ["正确", "错误"]): q_type = "判断题"
                else: q_type = "单选题"
                    
                extracted.append({
                    "Course": course_name,
                    "Type": q_type, 
                    "Content": name_div.get_text(strip=True), 
                    "options": options_text, 
                    "Answers": answers_text
                })
            return extracted
        except Exception:
            return []

# ========================================================
# 4. Streamlit UI
# ========================================================
st.set_page_config(page_title="粟湾/如仁题库中心", layout="wide")

with st.sidebar:
    st.header("账户设置")
    u_acc = st.text_input("登录账号")
    u_pwd = st.text_input("登录密码", type="password")
    st.divider()
    st.info("💡 建议：如果登录反复失败，请尝试在浏览器中重新登录该网站以解除可能的临时锁定。")

st.title("粟湾/如仁题库中心")

current_conf = load_courses()
t_sync, t_view, t_manage = st.tabs(["题库同步更新", "题库在线浏览", "课程管理设置"])

# --- Tab 1: 同步 ---
with t_sync:
    st.subheader("抓取新题目")
    if not current_conf:
        st.warning("请先在课程管理中添加课程。")
    else:
        sel_name = st.selectbox("请选择要同步的课程", list(current_conf.keys()))
        target_u = current_conf[sel_name]
        
        if st.button("开始同步更新", type="primary"):
            if not u_acc or not u_pwd:
                st.error("请先输入账号密码！")
            else:
                scr = AutoExamScraper(u_acc, u_pwd)
                with st.spinner(f"正在同步【{sel_name}】..."):
                    ok, msg = scr.login()
                    if ok:
                        new_items = scr.fetch_data(target_u, sel_name)
                        db = load_data()
                        old_keys = {f"{i['Course']}_{i['Content']}" for i in db}
                        added = [i for i in new_items if f"{i['Course']}_{i['Content']}" not in old_keys]
                        
                        if added:
                            save_data(db + added)
                            st.success(f"同步成功！新增 {len(added)} 题。")
                        else:
                            st.info("未发现新题目。")
                    else:
                        st.error(f"登录失败: {msg}")

# --- Tab 2: 浏览 ---
with t_view:
    db = load_data()
    if not db:
        st.info("暂无数据。")
    else:
        c_filter = st.selectbox("筛选课程", ["全部"] + sorted(list(set(i['Course'] for i in db))))
        s_key = st.text_input("搜索题目关键词")
        
        filtered = db if c_filter == "全部" else [i for i in db if i['Course'] == c_filter]
        if s_key:
            filtered = [i for i in filtered if s_key in i['Content']]
        
        show_df = pd.DataFrame([
            {
                "序号": idx + 1,
                "课程": i['Course'],
                "题型": i['Type'],
                "题目内容": i['Content'],
                "选项": " | ".join(i['options']),
                "答案": "、".join(i['Answers'])
            } for idx, i in enumerate(filtered)
        ])
        
        st.dataframe(show_df.set_index("序号"), use_container_width=True, height=500)
        
        st.divider()
        f_col1, f_col2 = st.columns([3, 1])
        f_col1.markdown(f"### 📊 统计：当前共计 **{len(filtered)}** 道题目")
        
        js_data = json.dumps(filtered, ensure_ascii=False, indent=4)
        f_col2.download_button("下载当前题库 (JSON)", js_data, f"db_{c_filter}.json", "application/json")

# --- Tab 3: 管理 ---
with t_manage:
    st.subheader("管理课程清单")
    
    with st.expander("➕ 添加课程"):
        with st.form("add_form"):
            n = st.text_input("课程名")
            l = st.text_input("课程URL")
            if st.form_submit_button("确认"):
                if n and l:
                    current_conf[n] = l
                    save_courses(current_conf)
                    st.rerun()
    
    st.write("---")
    for name, url in list(current_conf.items()):
        c1, c2, c3 = st.columns([1, 4, 1])
        c1.write(f"**{name}**")
        c2.code(url)
        if c3.button("删除", key=f"del_{name}"):
            del current_conf[name]
            save_courses(current_conf)
            st.rerun()