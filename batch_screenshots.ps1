$ErrorActionPreference = "Stop"
$SignalDir = "c:\Users\25868\Desktop\UE5\MapForgeTest\signals"
$ShotDir = "c:\Users\25868\Desktop\UE5\screenshots"
$ShotScript = "c:\Users\25868\Desktop\UE5\MapForgeTest\take_screenshot.ps1"

if (-not (Test-Path $ShotDir)) { New-Item -ItemType Directory -Path $ShotDir | Out-Null }

$labels = @(
    "01_heliport", "02_wirefence", "03_hangar", "04_charging", "05_solar",
    "06_trees", "07_comm_tower", "08_hv_tower", "09_village", "10_forest"
)

function TakeShot($name) {
    $out = "$ShotDir\shot_$name.png"
    & powershell -ExecutionPolicy Bypass -File $ShotScript -OutPath $out
    Write-Host "  Screenshot: $out"
}

for ($sceneNum = 1; $sceneNum -le 10; $sceneNum++) {
    $readyFile = "$SignalDir\READY_$sceneNum.txt"
    # 用${sceneNum}花括号包裹变量名，避免PowerShell把"sceneNum:"误解析为驱动器/作用域引用
    Write-Host "=== Scene ${sceneNum}: $($labels[$sceneNum - 1]) ==="
    Write-Host "Waiting for READY_$sceneNum ..."
    $start = Get-Date
    $found = $false
    while ((Get-Date) - $start -lt [TimeSpan]::FromSeconds(120)) {
        Start-Sleep -Seconds 2
        if (Test-Path $readyFile) {
            $found = $true
            Write-Host "READY_$sceneNum found!"
            break
        }
        $elapsed = [math]::Round(((Get-Date) - $start).TotalSeconds)
        Write-Host "  Waiting... (${elapsed}s)"
    }
    if (-not $found) {
        Write-Host "ERROR - READY_$sceneNum timeout!"
        break
    }
    Start-Sleep -Seconds 2
    TakeShot $labels[$sceneNum - 1]
    $goFile = "$SignalDir\GO_$sceneNum.txt"
    [System.IO.File]::WriteAllText($goFile, "go")
    Write-Host "GO_$sceneNum sent"
}

$doneFile = "$SignalDir\ALL_DONE.txt"
$start = Get-Date
while ((Get-Date) - $start -lt [TimeSpan]::FromSeconds(60)) {
    Start-Sleep -Seconds 3
    if (Test-Path $doneFile) {
        Write-Host "ALL_DONE received!"
        break
    }
}

Write-Host "`n=== Screenshots Summary ==="
Get-ChildItem "$ShotDir\shot_*.png" | ForEach-Object {
    $hash = (Get-FileHash $_.FullName -Algorithm MD5).Hash
    Write-Host "$($_.Name) - $($_.Length) bytes - $hash"
}
