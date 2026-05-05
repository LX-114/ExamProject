@echo off
:: 解决乱码问题
chcp 65001 >nul

echo [1/2] 正在检查环境依赖...
:: 使用 python -m 调用 pip 更加稳妥
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

echo [2/2] 正在通过浏览器启动 Web 界面...
:: 核心修复：使用 python -m streamlit 绕过环境变量问题
python -m streamlit run app.py

pause