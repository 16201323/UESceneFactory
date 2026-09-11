# UE5 场景构建脚本 — 方形铁丝网围栏
# 中心原点, 长100m(X) x 宽50m(Y), 150块面板, 长边yaw=0 短边yaw=90
$exe = "D:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
$proj = "D:\code\UEEnvironment\MyUETest5_8_2\MyUETest5_8_2\MyUETest5_8_2.uproject"
$log = "c:\Users\25868\Desktop\UE5\MapForgeTest\build_square_fence.log"
$errlog = "c:\Users\25868\Desktop\UE5\MapForgeTest\build_square_fence.err.log"
$scene = "c:/Users/25868/Desktop/UE5/MapForgeTest/square_fence.json"
$execCmds = 'py c:/Users/25868/Desktop/UE5/MapForgeTest/build_scene.py | quit'
$argStr = '"' + $proj + '" -unattended -nop4 -nosplash -nullrhi -stdout -ExecCmds="' + $execCmds + '"'
$env:MAPFORGE_SCENE = $scene
Write-Output "Building: $scene"
Write-Output "Target:  /Game/MapForgeTest/GB_Square_Wirefence"
$proc = Start-Process -FilePath $exe -ArgumentList $argStr -RedirectStandardOutput $log -RedirectStandardError $errlog -PassThru -NoNewWindow -Wait
Write-Output ("EXIT_CODE=" + $proc.ExitCode)
