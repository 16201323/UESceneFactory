@echo off
chcp 936 >nul 2>&1
REM ============================================================
REM UE场景工厂 测试运行脚本
REM 运行全部 pytest 测试用例 (排除需要 UE 编辑器环境的 tools/check)
REM 依赖需已安装: pip install -r requirements.txt
REM ============================================================

REM 切到脚本所在目录
cd /d "%~dp0"

REM 优先用本地虚拟环境 .venv 的解释器, 没有则回退到 PATH 中的 python
set "PY_EXE="
if exist ".venv\Scripts\python.exe" (
    set "PY_EXE=.venv\Scripts\python.exe"
) else (
    set "PY_EXE=python"
)

REM 运行测试; --ignore=tools/check 排除需要 unreal 模块的测试
REM -v 显示详细测试名称, --tb=short 简化错误回溯
"%PY_EXE%" -m pytest --ignore=tools/check -v --tb=short
if errorlevel 1 (
    echo.
    echo [测试失败] 部分测试未通过, 请查看上方输出
    pause
) else (
    echo.
    echo [全部通过] 所有测试均已通过
    pause
)
