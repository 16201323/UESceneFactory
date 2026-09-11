# UE5 场景重建启动脚本 (PowerShell 版)
# 使用 Start-Process 直接将 stdout 重定向到文件, 避免管道缓冲区死锁
# 场景文件路径通过环境变量 MAPFORGE_SCENE 传入, 避免 ExecCmds 中 | 被当 argv
$exe = "D:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
$proj = "D:\code\UEEnvironment\MyUETest5_8_2\MyUETest5_8_2\MyUETest5_8_2.uproject"
$log = "c:\Users\25868\Desktop\UE5\MapForgeTest\build_ue.log"
$errlog = "c:\Users\25868\Desktop\UE5\MapForgeTest\build_ue.err.log"
$scene = "c:/Users/25868/Desktop/UE5/MapForgeTest/all_terrain_realistic.json"
$execCmds = 'py c:/Users/25868/Desktop/UE5/MapForgeTest/build_scene.py | quit'
$argStr = '"' + $proj + '" -unattended -nop4 -nosplash -nullrhi -stdout -ExecCmds="' + $execCmds + '"'
$env:MAPFORGE_SCENE = $scene
$proc = Start-Process -FilePath $exe -ArgumentList $argStr -RedirectStandardOutput $log -RedirectStandardError $errlog -PassThru -NoNewWindow -Wait
Write-Output ("EXIT_CODE=" + $proc.ExitCode)
