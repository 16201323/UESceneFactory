Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WinAPI {
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")]
    public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")]
    public static extern bool IsIconic(IntPtr hWnd);
}
"@
$proc = Get-Process UnrealEditor -ErrorAction SilentlyContinue | Select-Object -First 1
if ($proc -and $proc.MainWindowHandle -ne [IntPtr]::Zero) {
    if ([WinAPI]::IsIconic($proc.MainWindowHandle)) {
        [WinAPI]::ShowWindowAsync($proc.MainWindowHandle, 9) | Out-Null
    }
    [WinAPI]::SetForegroundWindow($proc.MainWindowHandle) | Out-Null
    Start-Sleep -Seconds 2
    Write-Host "UE5 focused"
    [System.Windows.Forms.SendKeys]::SendWait('{ESC}')
    Start-Sleep -Milliseconds 500
    Write-Host "Escape sent"
    [System.Windows.Forms.SendKeys]::SendWait('{F11}')
    Start-Sleep -Seconds 3
    Write-Host "F11 sent"
    [WinAPI]::SetForegroundWindow($proc.MainWindowHandle) | Out-Null
    Start-Sleep -Seconds 1
    Write-Host "Done"
} else {
    Write-Host "ERROR: UE5 not found"
}
