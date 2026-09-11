# 地形高度探测脚本启动器
# 在 UE5 命令行模式下运行 probe_terrain_height.py
# 功能: 加载已保存的 umap, 使用射线追踪测量地形表面 Z 值

$exe = "D:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
$proj = "D:\code\UEEnvironment\MyUETest5_8_2\MyUETest5_8_2\MyUETest5_8_2.uproject"
$log = "c:\Users\25868\Desktop\UE5\MapForgeTest\probe_stdout.log"
$errlog = "c:\Users\25868\Desktop\UE5\MapForgeTest\probe_stderr.log"

# 设置探测日志路径 (probe_terrain_height.py 读取此环境变量)
$env:MAPFORGE_LOG = "c:/Users/25868/Desktop/UE5/MapForgeTest/probe_terrain.log"

$execCmds = 'py c:/Users/25868/Desktop/UE5/MapForgeTest/probe_terrain_height.py | quit'
$argStr = '"' + $proj + '" -unattended -nop4 -nosplash -nullrhi -stdout -ExecCmds="' + $execCmds + '"'

Write-Output "Starting terrain probe..."
Write-Output "Project: $proj"
Write-Output "Log: $($env:MAPFORGE_LOG)"

$proc = Start-Process -FilePath $exe -ArgumentList $argStr -RedirectStandardOutput $log -RedirectStandardError $errlog -PassThru -NoNewWindow -Wait

Write-Output ("EXIT_CODE=" + $proc.ExitCode)
Write-Output "Probe complete. Check probe_terrain.log for results."
