# 房屋悬浮根因探测启动器
# 在 UE5 命令行模式下运行 probe_house_float.py
# 功能: 加载已保存的 umap, 对比两种房屋蓝图组件结构 + 测量地形高度

$exe = "D:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
$proj = "D:\code\UEEnvironment\MyUETest5_8_2\MyUETest5_8_2\MyUETest5_8_2.uproject"
$log = "c:\Users\25868\Desktop\UE5\MapForgeTest\probe_house_stdout.log"
$errlog = "c:\Users\25868\Desktop\UE5\MapForgeTest\probe_house_stderr.log"

$execCmds = 'py c:/Users/25868/Desktop/UE5/MapForgeTest/probe_house_float.py | quit'
$argStr = '"' + $proj + '" -unattended -nop4 -nosplash -nullrhi -stdout -ExecCmds="' + $execCmds + '"'

Write-Output "Starting house float probe..."
Write-Output "Project: $proj"

$proc = Start-Process -FilePath $exe -ArgumentList $argStr -RedirectStandardOutput $log -RedirectStandardError $errlog -PassThru -NoNewWindow -Wait

Write-Output ("EXIT_CODE=" + $proc.ExitCode)
Write-Output "Probe complete. Check probe_house_float.txt for results."
