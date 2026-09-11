@echo off
chcp 936 >nul 2>&1
echo ============================================================
echo  MapForge - 打包构建脚本
echo  将 mapforge_app.py + build_scene.py 打包为 MapForge.exe
echo ============================================================
echo.

REM 使用脚本自身所在目录, 不硬编码用户路径
cd /d "%~dp0"

echo [1/2] 清理旧的构建产物...
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"

echo [2/2] 开始 PyInstaller 打包 (使用 MapForge.spec 配置)...
pyinstaller MapForge.spec --noconfirm

if errorlevel 1 (
    echo.
    echo [错误] 打包失败! 错误码见上
    pause
    exit /b 1
)

echo.
echo 打包完成! 输出文件: dist\MapForge.exe
dir "dist\MapForge.exe"
echo.
echo 可以将 dist\MapForge.exe 复制到任意位置使用
echo.
pause
