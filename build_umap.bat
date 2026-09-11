@echo off
chcp 936 >nul 2>&1
REM ============================================================
REM build_umap.bat - JSON scene -> UE5 umap 一键构建工具
REM Usage: build_umap.bat <scene.json> [options]
REM Options (空格分隔):
REM   forcekill : 跳过关闭UE编辑器询问, 直接终止 (无人值守)
REM   open      : 构建完成后自动打开UE编辑器并加载umap
REM Example: build_umap.bat all_terrain_realistic.json open
REM ============================================================
setlocal enabledelayedexpansion
if "%~1"=="" (
    echo 用法: build_umap.bat ^<scene_json_path^> [forcekill] [open]
    exit /b 1
)
where python >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 python, 请确保 Python 已安装并加入 PATH 环境变量
    exit /b 1
)
set ARGS=--scene-json "%~1"
if /i "%~2"=="forcekill" set ARGS=%ARGS% --force-kill
if /i "%~3"=="forcekill" set ARGS=%ARGS% --force-kill
if /i "%~2"=="open" set ARGS=%ARGS% --open-editor
if /i "%~3"=="open" set ARGS=%ARGS% --open-editor
python "%~dp0build_umap.py" %ARGS%
exit /b %ERRORLEVEL%