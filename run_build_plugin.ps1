# Rebuild LandscapeHelper plugin (after position bug fix)
# 修复: 必须使用UnrealBuildTool文件夹内的UBT.exe(自带System.CodeDom.dll+.deps.json)
# 旧路径 AutomationTool\UnrealBuildTool.exe 缺少System.CodeDom.dll, Build.cs改动触发重编译时报
# FileNotFoundException: Could not load assembly 'System.CodeDom'
$ubt = "D:\Program Files\Epic Games\UE_5.8\Engine\Binaries\DotNET\UnrealBuildTool\UnrealBuildTool.exe"
$proj = "D:\code\UEEnvironment\MyUETest5_8_2\MyUETest5_8_2\MyUETest5_8_2.uproject"
$log = "c:\Users\25868\Desktop\UE5\MapForgeTest\build_plugin.log"
$errlog = "c:\Users\25868\Desktop\UE5\MapForgeTest\build_plugin.err.log"
$argStr = "MyUETest5_8_2Editor Win64 Development -Project=$proj -WaitMutex -NoHotReloadFromIDE"
$proc = Start-Process -FilePath $ubt -ArgumentList $argStr -RedirectStandardOutput $log -RedirectStandardError $errlog -PassThru -NoNewWindow -Wait
Write-Output ("EXIT_CODE=" + $proc.ExitCode)
