@echo off
chcp 936 >nul 2>&1
REM ============================================================
REM UE场景工厂 GUI 启动脚本
REM 双击即运行 mapforge_app.py 主程序 (PyQt6 图形界面)
REM 依赖需已安装: pip install -r requirements.txt
REM ============================================================

REM 切到脚本所在目录, 保证相对路径(图标/模板/知识库)可被找到
cd /d "%~dp0"

REM 优先用本地虚拟环境 .venv 的解释器, 没有则回退到 PATH 中的 python
set "PY_EXE="
if exist ".venv\Scripts\python.exe" (
    set "PY_EXE=.venv\Scripts\python.exe"
) else (
    set "PY_EXE=python"
)

REM 启动 GUI 主程序; 失败时暂停以便查看报错
"%PY_EXE%" scripts\mapforge_app.py
if errorlevel 1 (
    echo.
    echo [启动失败] 请检查依赖是否安装: pip install -r requirements.txt
    pause
)
