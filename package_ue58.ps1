# ============================================================================
# package_ue58.ps1 - UE5.8 项目 + ProjectAirSim 插件 -> exe 一键打包工具
# ============================================================================
# 用法:
#   powershell -ExecutionPolicy Bypass -File package_ue58.ps1
#   powershell -ExecutionPolicy Bypass -File package_ue58.ps1 -Umap "/Game/MapForgeTest/GB_SmartAgriDroneField2km_2"
#   powershell -ExecutionPolicy Bypass -File package_ue58.ps1 -Umap "/Game/MapForgeTest/GB_SmartAgriDroneField2km_2" -RebuildCoreSim
#   powershell -ExecutionPolicy Bypass -File package_ue58.ps1 -Config Development -ForceKill
#
# 参数说明:
#   -Umap           : 指定打包后 exe 默认加载的关卡包路径 (如 /Game/MapForgeTest/xxx)
#                     省略则沿用 DefaultEngine.ini 中已有的 GameDefaultMap, 不改 ini
#   -RebuildCoreSim : 打包前先用 CMake 重新编译 core_sim 并把新的 core_sim.lib
#                     拷贝到插件 SimLibs 目录 (仅 core_sim 源码有改动时才需要, 默认不重建)
#   -Config         : 打包配置, Shipping (默认, 发布版) 或 Development (带控制台日志, 便于调试)
#   -TimeoutSec     : 打包超时秒数 (默认 60 分钟; 大项目首次打包 shader 可能更久, 可调大)
#   -ForceKill      : 跳过编辑器关闭询问, 直接终止 UE 进程 (无人值守模式)
#   -KeepLogs       : 时间戳日志保留份数 (旧的自动清理, 默认 20)
#
# 产物:
#   打包后的 exe 位于归档目录:
#     <ArchiveDir>\Windows\<ProjectName>\Binaries\Win64\<ProjectName>-Win64-<Config>.exe
#   例如:
#     c:\Users\25868\Desktop\UE5\MapForgeTest\Packaged\Windows\MyUETest5_8_2\Binaries\Win64\MyUETest5_8_2-Win64-Shipping.exe
#
# 机制说明 (为什么 ProjectAirSim 不需要额外打包步骤):
#   1. ProjectAirSim 已作为 Runtime 插件 (EnabledByDefault) 集成在 Plugins\ 下,
#      其 Build.cs 静态链接 SimLibs\core_sim\Release\core_sim.lib 等原生库;
#      UAT (Unreal Automation Tool) 的 BuildCookRun 会自动编译插件并随项目一起 Cook/Stage,
#      无需额外步骤。只有当 core_sim C++ 源码改动后才需 -RebuildCoreSim 更新链接库。
#   2. 打包后 exe 默认加载哪个关卡由 DefaultEngine.ini 的 GameDefaultMap 决定,
#      -Umap 参数会在打包前临时修改该值 (并备份原 ini 为 .bak, 保留最初原始状态)。
#   3. UAT 命令 (经验证可用, 见 package_shipping.log):
#        RunUAT BuildCookRun -project=<> -platform=Win64 -clientconfig=Shipping
#          -cook -build -stage -pak -package -archive -archivedirectory=<>
#          -unattended -nop4 -nosplash
#      各阶段含义: -build 编译代码 -> -cook 烘焙资产 -> -stage 收集依赖 ->
#                  -pak 打 pak 包 -> -package 生成可运行结构 -> -archive 复制到归档目录
# ============================================================================

param(
    # 关卡包路径 (如 /Game/MapForgeTest/GB_SmartAgriDroneField2km_2), 省略则不改 ini
    [string]$Umap = "",

    # 是否打包前重建 core_sim 原生库
    [switch]$RebuildCoreSim,

    # 打包配置: Shipping(发布) / Development(调试)
    [ValidateSet("Shipping","Development")]
    [string]$Config = "Shipping",

    # 打包超时秒数 (默认 60 分钟)
    [int]$TimeoutSec = 3600,

    # 跳过编辑器关闭询问, 直接终止 (无人值守)
    [switch]$ForceKill,

    # 时间戳日志保留份数
    [int]$KeepLogs = 20
)

# ---- 固定路径配置 (与 build_umap.ps1 保持一致) ----
# UE 引擎根目录 (含 RunUAT 入口)
$EngineRoot  = "D:\Program Files\Epic Games\UE_5.8"
# RunUAT.bat 是调用 Unreal Automation Tool 的标准入口
$RunUAT      = Join-Path $EngineRoot "Engine\Build\BatchFiles\RunUAT.bat"
# UE 工程文件 (.uproject)
$Proj        = "D:\code\UEEnvironment\MyUETest5_8_2\MyUETest5_8_2\MyUETest5_8_2.uproject"
# 工程名 (决定产物 exe 文件名)
$ProjectName = "MyUETest5_8_2"
# 工程内容根 (用于校验 -Umap 指定的关卡文件是否存在)
$ContentRoot = "D:\code\UEEnvironment\MyUETest5_8_2\MyUETest5_8_2\Content"
# DefaultEngine.ini (含 GameDefaultMap 设置, 控制打包后默认关卡)
$IniPath     = "D:\code\UEEnvironment\MyUETest5_8_2\MyUETest5_8_2\Config\DefaultEngine.ini"
# ProjectAirSim 插件目录
$PluginDir   = "D:\code\UEEnvironment\MyUETest5_8_2\MyUETest5_8_2\Plugins\ProjectAirSim"
# 脚本所在工作目录 (日志与归档产物的根)
$Dir         = "c:\Users\25868\Desktop\UE5\MapForgeTest"
# 归档目录 (-archive 参数指向此处, 打包产物最终落盘于此)
$ArchiveDir  = Join-Path $Dir "Packaged"

# core_sim CMake 产出路径 (-RebuildCoreSim 时的拷贝源)
$CmakeLibSrc = "D:\code\projectairsim\ProjectAirSim\build\win64\Release\core_sim\src\core_sim.lib"
# core_sim 插件链接位置 (Build.cs 实际链接的路径, 拷贝目标)
$CmakeLibDst = Join-Path $PluginDir "SimLibs\core_sim\Release\core_sim.lib"
# core_sim CMake 构建脚本 (初始化 MSVC 环境 + cmake --build)
$BuildCoreSimBat = "c:\Users\25868\Desktop\UE5\build_core_sim.bat"

# 时间戳主日志: 记录 [HEADER]头 + [UATOUT]UAT完整输出 + [STDERR]错误流 + [SUMMARY]摘要
$TimeStamp   = Get-Date -Format "yyyyMMdd_HHmmss"
$MainLogPath = Join-Path $Dir ("package_ue58_" + $TimeStamp + ".log")

# ---- 控制台彩色输出辅助函数 (与 build_umap.ps1 风格一致) ----
function Write-Step($msg)  { Write-Host ("[步骤] " + $msg) -ForegroundColor Cyan }
function Write-Ok($msg)    { Write-Host ("[OK]   " + $msg) -ForegroundColor Green }
function Write-Warn2($msg) { Write-Host ("[警告] " + $msg) -ForegroundColor Yellow }
function Write-Fail($msg)  { Write-Host ("[失败] " + $msg) -ForegroundColor Red }

# 追加一行到主日志
function Add-MainLog($line) {
    Add-Content -Path $MainLogPath -Value $line -Encoding UTF8
}

# 先写头部到主日志 (UAT 输出稍后追加, 不覆盖头部)
Add-MainLog ("[HEADER] ==================== UE5.8 打包日志 ====================")
Add-MainLog ("[HEADER] 打包开始时间 : " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
Add-MainLog ("[HEADER] 工程文件     : " + $Proj)
Add-MainLog ("[HEADER] 打包配置     : " + $Config)
Add-MainLog ("[HEADER] 指定关卡     : " + $(if ($Umap) { $Umap } else { "(沿用 ini 当前值)" }))
Add-MainLog ("[HEADER] 重建core_sim : " + $(if ($RebuildCoreSim) { "是" } else { "否" }))
Add-MainLog ("[HEADER] 归档目录     : " + $ArchiveDir)
Add-MainLog ("[HEADER] 主日志文件   : " + $MainLogPath)
Add-MainLog ("[HEADER] ========================================================")

# ========== 步骤0: 校验关键路径 ==========
Write-Step "校验关键路径..."
$missing = @()
if (-not (Test-Path $RunUAT))  { $missing += $RunUAT }
if (-not (Test-Path $Proj))    { $missing += $Proj }
if (-not (Test-Path $IniPath)) { $missing += $IniPath }
if ($missing.Count -gt 0) {
    Write-Fail "关键路径缺失, 打包中止:"
    $missing | ForEach-Object { Write-Host ("    " + $_) -ForegroundColor Red }
    exit 1
}
Write-Ok "关键路径校验通过 (RunUAT / uproject / ini 均存在)"

# ========== 步骤1: 清理 UE 进程 ==========
# 1.1 无头残留进程 UnrealEditor-Cmd: 上次构建挂起的残留, 直接终止无风险
$headless = Get-Process -Name "UnrealEditor-Cmd" -ErrorAction SilentlyContinue
if ($headless) {
    foreach ($p in $headless) {
        Write-Warn2 ("终止无头残留进程 UnrealEditor-Cmd (PID " + $p.Id + ")")
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
    Write-Ok "无头残留进程已清理"
}
# 1.2 GUI 编辑器 UnrealEditor: 锁定插件 DLL + 占用资产句柄, 必须关闭才能打包
$editors = Get-Process -Name "UnrealEditor" -ErrorAction SilentlyContinue
if ($editors) {
    foreach ($p in $editors) {
        Write-Warn2 ("检测到 UE 编辑器正在运行 (PID " + $p.Id + ")")
    }
    if ($ForceKill) {
        Write-Warn2 "-ForceKill 已指定, 直接终止编辑器 (未保存的修改将丢失)"
        $answer = "Y"
    } else {
        $answer = Read-Host "打包需要关闭 UE 编辑器 (否则插件 DLL 被锁定无法构建)。关闭? [Y/n]"
        if ([string]::IsNullOrWhiteSpace($answer)) { $answer = "Y" }
    }
    if ($answer -match '^[Yy]') {
        foreach ($p in $editors) {
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 3
        Write-Ok "编辑器已关闭"
    } else {
        Write-Fail "用户选择不关闭编辑器, 打包中止"
        exit 1
    }
} else {
    Write-Ok "无 UE 编辑器进程运行"
}

# ========== 步骤2: 指定 umap -> 校验关卡文件 + 临时修改 DefaultEngine.ini ==========
$iniPatched = $false
if ($Umap) {
    Write-Step ("指定关卡: " + $Umap)
    # 2.1 校验关卡文件存在: /Game/MapForgeTest/xxx -> Content\MapForgeTest\xxx.umap
    $rel = $Umap -replace '^/Game/', ''
    $umapFile = Join-Path $ContentRoot ($rel + ".umap")
    if (-not (Test-Path $umapFile)) {
        Write-Warn2 ("关卡文件未找到: " + $umapFile + " (继续打包, 由 Cook 阶段决定; 路径写错会导致 exe 加载默认空关卡)")
    } else {
        Write-Ok ("关卡文件存在: " + $umapFile)
    }
    # 2.2 备份原始 ini (只保留第一次备份, 保留最初的原始状态便于还原)
    $bakPath = $IniPath + ".bak"
    if (-not (Test-Path $bakPath)) {
        Copy-Item -Path $IniPath -Destination $bakPath -Force
        Write-Ok ("已备份原始 ini -> " + $bakPath + " (还原: 删除 .bak 前先拷回)")
    }
    # 2.3 读取 ini 全文, 用正则替换 GameDefaultMap= 这一行
    #     用 .NET API 读写避免 PowerShell Set-Content 写入 BOM (UE ini 不应有 BOM)
    $content    = [System.IO.File]::ReadAllText($IniPath)
    $newContent = $content -replace 'GameDefaultMap=[^\r\n]*', ("GameDefaultMap=" + $Umap)
    if ($newContent -eq $content) {
        Write-Warn2 "ini 中未找到 GameDefaultMap 行, 跳过修改 (请检查 DefaultEngine.ini)"
    } else {
        [System.IO.File]::WriteAllText($IniPath, $newContent)
        $iniPatched = $true
        Write-Ok ("GameDefaultMap 已更新为 " + $Umap)
    }
} else {
    Write-Ok "未指定 -Umap, 沿用 ini 当前 GameDefaultMap"
}

# ========== 步骤3: (可选) 重建 core_sim 并拷贝到插件 SimLibs ==========
# ProjectAirSim 插件通过 Build.cs 静态链接 SimLibs\core_sim\Release\core_sim.lib;
# 只有当 core_sim C++ 源码改动后才需要重建, 否则可跳过 (lib 已存在)
if ($RebuildCoreSim) {
    Write-Step "重建 core_sim (CMake) ..."
    if (-not (Test-Path $BuildCoreSimBat)) {
        Write-Fail ("build_core_sim.bat 不存在: " + $BuildCoreSimBat)
        exit 1
    }
    # 调用 CMake 构建脚本 (内部会初始化 MSVC 环境 + cmake --build core_sim), 等待结束
    # stdout/stderr 重定向到临时文件, 提取尾部追加到主日志
    $coreLog = Join-Path $env:TEMP ("core_sim_" + $TimeStamp + ".log")
    cmd /c $BuildCoreSimBat `> $coreLog `2`>`&1
    $coreExit = $LASTEXITCODE
    if (Test-Path $coreLog) {
        Add-MainLog ""
        Add-MainLog "[CORESIM] ---------- core_sim CMake 构建输出 (尾部 30 行) ----------"
        Get-Content $coreLog -ErrorAction SilentlyContinue | Select-Object -Last 30 | ForEach-Object { Add-MainLog ("[CORESIM] " + $_) }
        Remove-Item $coreLog -Force -ErrorAction SilentlyContinue
    }
    if ($coreExit -ne 0) {
        Write-Fail ("core_sim 构建失败 (退出码 " + $coreExit + "), 打包中止")
        exit 1
    }
    Write-Ok "core_sim 构建成功"
    # 把新产出的 core_sim.lib 拷贝到插件链接位置 (确保目标目录存在)
    if (Test-Path $CmakeLibSrc) {
        $libDir = Split-Path $CmakeLibDst -Parent
        if (-not (Test-Path $libDir)) { New-Item -ItemType Directory -Path $libDir -Force | Out-Null }
        Copy-Item -Path $CmakeLibSrc -Destination $CmakeLibDst -Force
        Write-Ok ("已更新插件链接库: " + $CmakeLibDst)
    } else {
        Write-Warn2 ("未找到 CMake 产出的 core_sim.lib: " + $CmakeLibSrc + " (保持现有库不变)")
    }
} else {
    Write-Ok "跳过 core_sim 重建 (如 core_sim 源码有改动请加 -RebuildCoreSim)"
}

# ========== 步骤4: 运行 UAT BuildCookRun 打包 ==========
Write-Step "启动 UAT BuildCookRun 打包 (可能需要 20~60 分钟, 首次编译 shader 更久)..."
# stderr 重定向到独立临时文件 (不能与 stdout 同一文件), 打包后合并进主日志
$TmpOutPath = Join-Path $env:TEMP ("package_ue58_stdout_" + [guid]::NewGuid().ToString("N").Substring(0,8) + ".tmp")
$TmpErrPath = Join-Path $env:TEMP ("package_ue58_stderr_" + [guid]::NewGuid().ToString("N").Substring(0,8) + ".tmp")

# UAT BuildCookRun 参数 (经验证可用, 见 package_shipping.log 历史)
$argList = @(
    "BuildCookRun",
    ("-project=" + $Proj),
    "-platform=Win64",
    ("-clientconfig=" + $Config),
    "-cook",          # 烘焙资产 (将编辑器资产转为运行时格式)
    "-build",         # 编译工程代码 (含 ProjectAirSim 插件)
    "-stage",         # 收集运行时依赖到暂存目录
    "-pak",           # 打包为 pak 文件 (单文件分发)
    "-package",       # 生成可运行的目录结构
    "-archive",       # 复制最终产物到归档目录
    ("-archivedirectory=" + $ArchiveDir),
    "-unattended",    # 无人值守 (不弹交互对话框)
    "-nop4",          # 不走 Perforce
    "-nosplash"       # 不显示启动画面
)
Write-Host ("[命令] " + $RunUAT)
Write-Host ("[参数] " + ($argList -join " "))

$sw = [System.Diagnostics.Stopwatch]::StartNew()
# Start-Process 调用 RunUAT.bat; stdout/stderr 分别重定向到临时文件
$proc = Start-Process -FilePath $RunUAT -ArgumentList $argList `
    -RedirectStandardOutput $TmpOutPath -RedirectStandardError $TmpErrPath `
    -PassThru -WindowStyle Hidden

# ========== 步骤5: 监控打包进度 (超时保护 + 实时尾随输出) ==========
Write-Step ("监控打包进程 (PID " + $proc.Id + "), 超时 " + $TimeoutSec + " 秒...")
$timeout = $false
$lastTick = 0
while (-not $proc.HasExited) {
    # 总超时检查
    if ($sw.Elapsed.TotalSeconds -gt $TimeoutSec) {
        Write-Fail ("打包超时 (" + $TimeoutSec + " 秒), 强制结束进程")
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        # UAT 可能派生子进程 (UBT/ShaderCompiler), 一并清理
        Get-Process -Name "UnrealBuildTool","AutomationTool","ShaderCompileWorker" -ErrorAction SilentlyContinue |
            Stop-Process -Force -ErrorAction SilentlyContinue
        $timeout = $true
        break
    }
    # 每 30 秒打印一次进度, 并尝试显示 UAT 最新输出行 (尾随临时 stdout 文件)
    $now = [int]$sw.Elapsed.TotalSeconds
    if ($now - $lastTick -ge 30) {
        $lastTick = $now
        $tail = ""
        if (Test-Path $TmpOutPath) {
            $t = Get-Content $TmpOutPath -Tail 1 -ErrorAction SilentlyContinue
            if ($t) { $tail = $t.Trim() }
        }
        Write-Host ("[进度] 已运行 " + $now + " 秒 ..." + $tail) -ForegroundColor DarkGray
    }
    Start-Sleep -Seconds 5
}
$sw.Stop()

# ========== 步骤6: 合并 UAT 输出到主日志 ==========
Add-MainLog ""
Add-MainLog "[UATOUT] ---------- UAT BuildCookRun 完整输出 ----------"
if (Test-Path $TmpOutPath) {
    # 批量读取整文件后一次性写入, 比逐行 Add-Content 快得多
    $outLines = Get-Content $TmpOutPath -ErrorAction SilentlyContinue
    if ($outLines) { Add-Content -Path $MainLogPath -Value $outLines -Encoding UTF8 }
    Remove-Item $TmpOutPath -Force -ErrorAction SilentlyContinue
}
# stderr 合并 (通常为空, 有内容则多为警告/错误)
if (Test-Path $TmpErrPath) {
    if ((Get-Item $TmpErrPath).Length -gt 0) {
        Add-MainLog ""
        Add-MainLog "[STDERR] ---------- UAT stderr ----------"
        $errLines = Get-Content $TmpErrPath -ErrorAction SilentlyContinue
        if ($errLines) { Add-Content -Path $MainLogPath -Value $errLines -Encoding UTF8 }
    }
    Remove-Item $TmpErrPath -Force -ErrorAction SilentlyContinue
}

# ========== 步骤7: 验证产物 ==========
# 归档后 exe 路径: <ArchiveDir>\Windows\<ProjectName>\Binaries\Win64\<ProjectName>-Win64-<Config>.exe
$exeName   = $ProjectName + "-Win64-" + $Config + ".exe"
$exePath   = Join-Path $ArchiveDir ("Windows\" + $ProjectName + "\Binaries\Win64\" + $exeName)
$exeExists = Test-Path $exePath

# 成败判定: 以产物 exe 是否生成为主 (UAT 退出码在强杀时不可靠, 故以文件存在为准)
$buildOk = $false
if (-not $timeout -and $exeExists) {
    Write-Ok "打包成功 (产物 exe 已生成)"
    $buildOk = $true
} else {
    Write-Fail ("打包失败 (超时=" + $timeout + ", 退出码=" + $proc.ExitCode + ", exe存在=" + $exeExists + ")")
}

# ========== 步骤8: 结果摘要 (控制台 + 主日志) ==========
$elapsed = [int]$sw.Elapsed.TotalSeconds
$summary = @()
$summary += "==================== 打包结果摘要 ===================="
$summary += ("工程文件    : " + $Proj)
$summary += ("打包配置    : " + $Config)
$summary += ("指定关卡    : " + $(if ($Umap) { $Umap } else { "(沿用 ini)" }))
$summary += ("ini 已修改  : " + $(if ($iniPatched) { "是 (原 ini 已备份为 .bak)" } else { "否" }))
$summary += ("core_sim    : " + $(if ($RebuildCoreSim) { "已重建并更新" } else { "未重建" }))
$summary += ("打包耗时    : " + $elapsed + " 秒")
$summary += ("UAT 退出码  : " + $proc.ExitCode)
if ($exeExists) {
    $f = Get-Item $exePath
    $summary += ("产物 exe    : " + $exePath)
    $summary += ("            大小 " + [math]::Round($f.Length / 1MB, 2) + " MB  保存时间 " + $f.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss"))
} else {
    $summary += ("产物 exe    : 未找到 " + $exePath)
}
$summary += ("归档目录    : " + $ArchiveDir)
$summary += ("主日志文件  : " + $MainLogPath)
$summary += ("            标签速查: [HEADER]头 [CORESIM]原生库 [UATOUT]UAT输出 [STDERR]错误流 [SUMMARY]本摘要")
$summary += "======================================================"

Write-Host ""
foreach ($l in $summary) { Write-Host $l -ForegroundColor Magenta }
Add-MainLog ""
foreach ($l in $summary) { Add-MainLog ("[SUMMARY] " + $l) }

# ========== 步骤9: 历史日志自动清理 ==========
# 时间戳日志持续累积, 只保留最近 $KeepLogs 份, 旧的自动删除防目录膨胀
$oldLogs = Get-ChildItem -Path $Dir -Filter "package_ue58_*.log" -ErrorAction SilentlyContinue |
           Sort-Object LastWriteTime -Descending |
           Select-Object -Skip $KeepLogs
if ($oldLogs) {
    foreach ($ol in $oldLogs) {
        Remove-Item $ol.FullName -Force -ErrorAction SilentlyContinue
    }
    Write-Host ("[清理] 已删除 " + $oldLogs.Count + " 份过期打包日志 (保留最近 " + $KeepLogs + " 份)")
}

if ($buildOk) { exit 0 } else { exit 1 }
