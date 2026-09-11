Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32 {
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();
}
"@

$proc = Get-Process -Id 16492 -ErrorAction SilentlyContinue
if (-not $proc) {
    Write-Host "[ERROR] UE editor process 16492 not found"
    exit 1
}
$hwnd = $proc.MainWindowHandle
Write-Host "[OK] Found UE editor window: $hwnd"

[Win32]::ShowWindow($hwnd, 9)
Start-Sleep -Milliseconds 300
[Win32]::SetForegroundWindow($hwnd)
Start-Sleep -Milliseconds 800

$bt = [char]96
Write-Host "[STEP] Sending backtick key to open console..."
[System.Windows.Forms.SendKeys]::SendWait($bt)
Start-Sleep -Milliseconds 800

$cmd = 'py "C:\Users\25868\Desktop\UE5\MapForgeTest\diagnose_material_api.py"'
Write-Host "[STEP] Pasting command: $cmd"
[System.Windows.Forms.Clipboard]::SetText($cmd)
Start-Sleep -Milliseconds 200
[System.Windows.Forms.SendKeys]::SendWait('^v')
Start-Sleep -Milliseconds 500

Write-Host "[STEP] Pressing Enter..."
[System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
Start-Sleep -Milliseconds 500

Write-Host "[DONE] Command sent"
