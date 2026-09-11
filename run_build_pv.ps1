# UE5 场景构建脚本 — P5 光伏板
# group加载全部 Material* 资产, scale 0.01, roll -90
$exe = "D:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
$proj = "D:\code\UEEnvironment\MyUETest5_8_2\MyUETest5_8_2\MyUETest5_8_2.uproject"
$log = "c:\Users\25868\Desktop\UE5\MapForgeTest\build_pv_solar.log"
$errlog = "c:\Users\25868\Desktop\UE5\MapForgeTest\build_pv_solar.err.log"
$scene = "c:/Users/25868/Desktop/UE5/MapForgeTest/pv_solar.json"
$execCmds = 'py c:/Users/25868/Desktop/UE5/MapForgeTest/build_scene.py | quit'
$argStr = '"' + $proj + '" -unattended -nop4 -nosplash -nullrhi -stdout -ExecCmds="' + $execCmds + '"'
$env:MAPFORGE_SCENE = $scene
Write-Output "Building: $scene"
Write-Output "Target:  /Game/MapForgeTest/GB_PV_Solar_Panels"
$proc = Start-Process -FilePath $exe -ArgumentList $argStr -RedirectStandardOutput $log -RedirectStandardError $errlog -PassThru -NoNewWindow -Wait
Write-Output ("EXIT_CODE=" + $proc.ExitCode)
