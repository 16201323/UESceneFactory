# UE5 场景构建脚本 — P7 通信塔
# 2座group通信塔: 电信塔scale1.2(城市宏基站), 科幻塔scale3.0(小型基站), skip_z_fix+ground_assembly
$exe = "D:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
$proj = "D:\code\UEEnvironment\MyUETest5_8_2\MyUETest5_8_2\MyUETest5_8_2.uproject"
$log = "c:\Users\25868\Desktop\UE5\MapForgeTest\test_07_comm_tower_build.log"
$errlog = "c:\Users\25868\Desktop\UE5\MapForgeTest\test_07_comm_tower_build.err.log"
$scene = "c:/Users/25868/Desktop/UE5/MapForgeTest/test_07_comm_tower.json"
$execCmds = 'py c:/Users/25868/Desktop/UE5/MapForgeTest/build_scene.py | quit'
$argStr = '"' + $proj + '" -unattended -nop4 -nosplash -nullrhi -stdout -ExecCmds="' + $execCmds + '"'
$env:MAPFORGE_SCENE = $scene
Write-Output "Building: $scene"
Write-Output "Target:  /Game/MapForgeTest/GB_Test_07_CommTower"
$proc = Start-Process -FilePath $exe -ArgumentList $argStr -RedirectStandardOutput $log -RedirectStandardError $errlog -PassThru -NoNewWindow -Wait
Write-Output ("EXIT_CODE=" + $proc.ExitCode)
