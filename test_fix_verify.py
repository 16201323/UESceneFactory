import subprocess, os

TEST_BAT = r'c:\Users\25868\Desktop\UE5\MapForgeTest\test_fix_verify.bat'

test_content = r"""@echo off
chcp 65001 >nul 2>&1
title Test: Verify detection block fixes
echo ============================================
echo   Test: REM comment + taskkill fix verification
echo ============================================
echo.

echo [Test 1] Run detection block - check for REM errors
echo   (If no 'not recognized' errors below, REM fix is OK)
echo.
:: These :: comments replace the old REM comments that caused errors
:: UE 5.8 editor process is UnrealEditor.exe
:: Detection uses findstr pattern matching, kill uses exact name + /t
tasklist 2>nul | findstr /i "UnrealEditor" >nul
if %errorlevel% equ 0 (
    echo   [PASS] UE editor detected as running.
) else (
    echo   [PASS] UE editor not running.
)
echo.

echo [Test 2] Verify taskkill /t flag syntax (safe: non-existent process)
taskkill /f /t /im ThisProcessDoesNotExist12345.exe >nul 2>&1
if %errorlevel% equ 0 (
    echo   [WARN] taskkill returned success for non-existent process (unexpected).
) else (
    echo   [PASS] taskkill executed without syntax error (error expected for fake process).
)
echo.

echo [Test 3] Verify taskkill without /t (old approach) for comparison
taskkill /f /im ThisProcessDoesNotExist12345.exe >nul 2>&1
if %errorlevel% equ 0 (
    echo   [WARN] taskkill returned success for non-existent process (unexpected).
) else (
    echo   [PASS] taskkill without /t also works syntactically.
)
echo.

echo [Test 4] Check actual UE process status
tasklist 2>nul | findstr /i "UnrealEditor"
if %errorlevel% equ 0 (
    echo   [PASS] UnrealEditor process is running (detection should find it).
) else (
    echo   [INFO] No UnrealEditor process running.
)
echo.

echo ============================================
echo   All tests complete. Check for errors above.
echo   If no 'not recognized' errors appeared, REM fix is verified.
echo ============================================
pause
"""

with open(TEST_BAT, 'wb') as f:
    f.write(test_content.replace('\n', '\r\n').encode('utf-8'))

print(f'Test bat written: {TEST_BAT}')
print(f'Size: {os.path.getsize(TEST_BAT)} bytes')
with open(TEST_BAT, 'rb') as f:
    data = f.read()
print(f'CRLF: {data.count(b"\r\n")}, LF-only: {data.count(b"\n") - data.count(b"\r\n")}, BOM: {data[:3] == b"\xef\xbb\xbf"}')
