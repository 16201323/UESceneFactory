# UE5 乡间土路材质创建启动脚本 (PowerShell 版)
# 使用 Start-Process 直接将 stdout 重定向到文件, 避免管道缓冲区死锁 (与 mapforge_app.py 成熟做法一致)
# ExecCmds 外层加双引号, 内部脚本路径不加引号 (UE5 ExecCmds 解析器无法处理嵌套引号)
$exe = "D:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
$proj = "D:\code\UEEnvironment\MyUETest5_8_2\MyUETest5_8_2\MyUETest5_8_2.uproject"
$log = "c:\Users\25868\Desktop\UE5\MapForgeTest\setup_road_ue.log"
$errlog = "c:\Users\25868\Desktop\UE5\MapForgeTest\setup_road_ue.err.log"
$execCmds = 'py c:/Users/25868/Desktop/UE5/MapForgeTest/setup_road_texture.py | quit'
$argStr = '"' + $proj + '" -unattended -nop4 -nosplash -nullrhi -stdout -ExecCmds="' + $execCmds + '"'
$proc = Start-Process -FilePath $exe -ArgumentList $argStr -RedirectStandardOutput $log -RedirectStandardError $errlog -PassThru -NoNewWindow -Wait
Write-Output ("EXIT_CODE=" + $proc.ExitCode)
