# 道路验证脚本启动器 (PowerShell)
# 加载关卡, 检查道路 actor 是否存在
$exe = "D:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
$proj = "D:\code\UEEnvironment\MyUETest5_8_2\MyUETest5_8_2\MyUETest5_8_2.uproject"
$log = "c:\Users\25868\Desktop\UE5\MapForgeTest\verify_roads_ue.log"
$errlog = "c:\Users\25868\Desktop\UE5\MapForgeTest\verify_roads_ue.err.log"
$execCmds = 'py c:/Users/25868/Desktop/UE5/MapForgeTest/verify_roads.py | quit'
$argStr = '"' + $proj + '" -unattended -nop4 -nosplash -nullrhi -stdout -ExecCmds="' + $execCmds + '"'
$proc = Start-Process -FilePath $exe -ArgumentList $argStr -RedirectStandardOutput $log -RedirectStandardError $errlog -PassThru -NoNewWindow -Wait
Write-Output ("EXIT_CODE=" + $proc.ExitCode)
