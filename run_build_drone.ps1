# UE5 无人机起降场场景构建脚本 (PowerShell 版)
# 基于 run_build.ps1 改写, 仅变更场景文件与日志路径, 其余执行模型保持一致
# 场景文件路径通过环境变量 MAPFORGE_SCENE 传入, 避免 ExecCmds 中 | 被当 argv
$exe = "D:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
$proj = "D:\code\UEEnvironment\MyUETest5_8_2\MyUETest5_8_2\MyUETest5_8_2.uproject"
$log = "c:\Users\25868\Desktop\UE5\MapForgeTest\build_drone.log"
$errlog = "c:\Users\25868\Desktop\UE5\MapForgeTest\build_drone.err.log"
$scene = "c:/Users/25868/Desktop/UE5/MapForgeTest/smart_agri_drone_field_2km.json"
$execCmds = 'py c:/Users/25868/Desktop/UE5/MapForgeTest/build_scene.py | quit'
$argStr = '"' + $proj + '" -unattended -nop4 -nosplash -nullrhi -stdout -ExecCmds="' + $execCmds + '"'
$env:MAPFORGE_SCENE = $scene
$proc = Start-Process -FilePath $exe -ArgumentList $argStr -RedirectStandardOutput $log -RedirectStandardError $errlog -PassThru -NoNewWindow -Wait
Write-Output ("EXIT_CODE=" + $proc.ExitCode)
