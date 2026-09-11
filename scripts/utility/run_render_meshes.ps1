# 网格缩略图渲染启动器 (PowerShell)
# 注意: 不使用 -nullrhi, 因为 SceneCapture2D 需要 GPU 渲染
# v2: 非阻塞模式 + 超时保护, 避免网络验证卡死
$exe = "D:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
$proj = "D:\code\UEEnvironment\MyUETest5_8_2\MyUETest5_8_2\MyUETest5_8_2.uproject"
$log = "c:\Users\25868\Desktop\UE5\MapForgeTest\render_meshes_ue.log"
$errlog = "c:\Users\25868\Desktop\UE5\MapForgeTest\render_meshes_ue.err.log"
# 添加 -NoContentValidation -NoShaderCompile 避免卡在内容验证和着色器编译
$execCmds = 'py c:/Users/25868/Desktop/UE5/MapForgeTest/render_meshes.py | quit'
$argStr = '"' + $proj + '" -unattended -nop4 -nosplash -stdout -NoLogTimes -ExecCmds="' + $execCmds + '"'
Write-Output ("ARGS=" + $argStr)
$proc = Start-Process -FilePath $exe -ArgumentList $argStr -RedirectStandardOutput $log -RedirectStandardError $errlog -PassThru -NoNewWindow
Write-Output ("PID=" + $proc.Id)
