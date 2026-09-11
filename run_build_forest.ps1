# UE5 场景构建脚本 — P10 密集森林(HISM距离剔除验证)
# 11种杉树instanced_grid: 上层4种5x5=100棵 + 下层7种3x3=63棵, 共163棵HISM实例
# 验证点: HISM每实例距离剔除 cull_start=17000(170m) cull_end=20000(200m), >200m不渲染GPU
$exe = "D:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
$proj = "D:\code\UEEnvironment\MyUETest5_8_2\MyUETest5_8_2\MyUETest5_8_2.uproject"
$log = "c:\Users\25868\Desktop\UE5\MapForgeTest\test_10_forest_build.log"
$errlog = "c:\Users\25868\Desktop\UE5\MapForgeTest\test_10_forest_build.err.log"
$scene = "c:/Users/25868/Desktop/UE5/MapForgeTest/test_10_forest.json"
$execCmds = 'py c:/Users/25868/Desktop/UE5/MapForgeTest/build_scene.py | quit'
$argStr = '"' + $proj + '" -unattended -nop4 -nosplash -nullrhi -stdout -ExecCmds="' + $execCmds + '"'
$env:MAPFORGE_SCENE = $scene
$env:MAPFORGE_LOG = "c:/Users/25868/Desktop/UE5/build_scene.log"
Write-Output "Building: $scene"
Write-Output "Target:  /Game/MapForgeTest/GB_Test_10_Forest"
Write-Output "Verify:  HISM_CULL should appear 11 times in build_scene.log"
$proc = Start-Process -FilePath $exe -ArgumentList $argStr -RedirectStandardOutput $log -RedirectStandardError $errlog -PassThru -NoNewWindow -Wait
Write-Output ("EXIT_CODE=" + $proc.ExitCode)
