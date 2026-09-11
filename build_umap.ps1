# ============================================================================
# build_umap.ps1 - JSON 场景 → UE5 umap 一键构建工具
# ============================================================================
# 用法:
#   powershell -ExecutionPolicy Bypass -File build_umap.ps1 -SceneJson <场景.json>
#   或通过 build_umap.bat <场景.json> [forcekill] [open] 调用
#   -ForceKill 开关: 跳过编辑器关闭询问, 直接终止 (用于无人值守场景)
#   -OpenEditor 开关: 构建成功后自动打开 UE 编辑器并加载生成的 umap
#
# 日志策略 (每次构建一个带时间戳的日志文件):
#   每次转换生成 build_umap_<yyyyMMdd_HHmmss>.log, 自动保留最近 20 份 (-KeepLogs 可调),
#   旧日志自动清理; 文件头部打印场景 JSON 全路径, 正文用前置标签区分类型:
#   [DUMP]  场景参数转储 (地形坐标/图层/河流道路折点/资产坐标高度值)
#   [BUILD] 构建流程进度 (Python 端)
#   [CARVE] C++ 地形雕刻日志 (河床冲刷/道路平整, 构建后从引擎日志提取)
#   [ERROR] 错误行 (构建后从引擎日志提取)
#   [SUMMARY] 构建结果摘要
#   注: UE 引擎自身的日志 (Saved/Logs/MyUETest5_8_2.log) 由引擎固定写入,
#       本脚本只从中提取关键行追加到主日志, 不作为独立产物维护。
#
# UE 进程策略:
#   - GUI 编辑器 (UnrealEditor.exe): 锁定插件 DLL 且占用资产, 必须关闭;
#     默认交互询问 (防止丢失未保存修改), -ForceKill 跳过询问
#   - 无头残留 (UnrealEditor-Cmd.exe): 上次构建挂起的残留, 直接终止
# ============================================================================

param(
    # 场景 JSON 文件路径 (必填)
    [Parameter(Mandatory = $true)]
    [string]$SceneJson,

    # 构建超时秒数 (默认 30 分钟)
    [int]$TimeoutSec = 1800,

    # 完成标记出现后等待引擎自然退出的宽限秒数
    [int]$GraceSec = 90,

    # 跳过编辑器关闭询问, 直接终止 (无人值守模式)
    [switch]$ForceKill,

    # 构建成功后自动打开 UE 编辑器并加载生成的 umap
    [switch]$OpenEditor,

    # 时间戳日志保留份数 (旧的自动清理, 默认 20)
    [int]$KeepLogs = 20
)

# ---- 固定路径配置 ----
$Exe     = "D:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
$Proj    = "D:\code\UEEnvironment\MyUETest5_8_2\MyUETest5_8_2\MyUETest5_8_2.uproject"
$Dir     = $PSScriptRoot
# 唯一主日志: 所有构建过程 (转储/进度/雕刻/错误/摘要) 都写入此文件
# 文件名带时间戳 => 每次转换生成独立日志, 历史构建记录全部保留可回溯
$TimeStamp = Get-Date -Format "yyyyMMdd_HHmmss"
$MainLogPath = Join-Path $Dir ("build_umap_" + $TimeStamp + ".log")
# UE 引擎自身日志 (只读来源, 从中提取 C++ 雕刻日志与错误行)
$EngineLogPath = "D:\code\UEEnvironment\MyUETest5_8_2\MyUETest5_8_2\Saved\Logs\MyUETest5_8_2.log"

function Write-Step($msg)  { Write-Host ("[步骤] " + $msg) -ForegroundColor Cyan }
function Write-Ok($msg)     { Write-Host ("[OK]   " + $msg) -ForegroundColor Green }
function Write-Warn2($msg)  { Write-Host ("[警告] " + $msg) -ForegroundColor Yellow }
function Write-Fail($msg)   { Write-Host ("[失败] " + $msg) -ForegroundColor Red }

# 写一行到主日志 (构建完成后脚本侧追加内容用; 构建期间由 build_scene.py 直写)
function Add-MainLog($line) {
    Add-Content -Path $MainLogPath -Value $line -Encoding UTF8
}

# ========== 步骤1: 校验场景 JSON ==========
Write-Step ("校验场景文件: " + $SceneJson)
$SceneJson = [System.IO.Path]::GetFullPath($SceneJson)
if (-not (Test-Path $SceneJson)) {
    Write-Fail ("场景文件不存在: " + $SceneJson)
    exit 1
}

# 用 python 校验 JSON 语法 + 读取场景元数据 (名称/目标关卡)
$metaJson = python -c "import json,sys; d=json.load(open(sys.argv[1],encoding='utf-8')); s=d.get('scene',{}); print(json.dumps({'name':s.get('name',''),'target_level':s.get('target_level','')},ensure_ascii=False))" $SceneJson 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Fail ("JSON 语法错误: " + $metaJson)
    exit 1
}
$meta = $metaJson | ConvertFrom-Json
Write-Ok ("JSON 语法合法  场景名=" + $meta.name + "  目标关卡=" + $meta.target_level)

# ========== 步骤1.5: 资产路径预校验 ==========
# 在启动 2 分钟的 UE 构建前, 秒级校验 JSON 引用的全部资产路径存在于 Content 目录,
# 路径写错立即报出, 避免构建完才发现资产缺失
Write-Step "资产路径预校验..."
$Validator = Join-Path $Dir "validate_scene_assets.py"
$checkOut = python $Validator $SceneJson 2>&1
if ($LASTEXITCODE -ne 0) {
    # asset_prefix 模式匹配可能导致预校验误报, 实际构建时由 UE5 引擎解析
    # 改为警告而非中止, 避免误报阻断构建流程
    Write-Warn2 "资产路径预校验有缺失项 (可能为 asset_prefix 误报), 继续构建..."
    $checkOut | ForEach-Object { Write-Host ("    " + $_) -ForegroundColor Yellow }
}
Write-Ok ($checkOut | Where-Object { $_ -match "ASSET_CHECK_OK" })

# ========== 步骤1.6: 目标 umap 存在性检查 ==========
# 构建前检查目标 umap 是否已存在, 避免误覆盖已有产物
$umapPath = ""
if ($meta.target_level) {
    $rel = $meta.target_level -replace "^/Game/", ""
    $umapPath = Join-Path "D:\code\UEEnvironment\MyUETest5_8_2\MyUETest5_8_2\Content" ($rel + ".umap")
}
if ($umapPath -and (Test-Path $umapPath)) {
    Add-Type -AssemblyName System.Windows.Forms
    $f = Get-Item $umapPath
    $msg = "目标 umap 文件已存在: " + $umapPath + "`n`n大小: " + [math]::Round($f.Length / 1MB, 2) + " MB`n最后修改: " + $f.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss") + "`n`n继续将删除已有 umap 并重新构建。是否继续?"
    $result = [System.Windows.Forms.MessageBox]::Show($msg, "umap 文件已存在", [System.Windows.Forms.MessageBoxButtons]::YesNo, [System.Windows.Forms.MessageBoxIcon]::Warning)
    if ($result -eq [System.Windows.Forms.DialogResult]::Yes) {
        Remove-Item $umapPath -Force -ErrorAction Stop
        Write-Warn2 ("已删除已有 umap: " + $umapPath)
    } else {
        Write-Fail "用户取消构建 (umap 文件已存在)"
        exit 1
    }
}

# ========== 步骤2: 清理 UE 进程 ==========
# 2.1 无头残留进程 (UnrealEditor-Cmd): 上次构建挂起的残留, 直接终止无风险
$headless = Get-Process -Name "UnrealEditor-Cmd" -ErrorAction SilentlyContinue
if ($headless) {
    foreach ($p in $headless) {
        Write-Warn2 ("终止无头残留进程 UnrealEditor-Cmd (PID " + $p.Id + ")")
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
    Write-Ok "无头残留进程已清理"
}

# 2.2 GUI 编辑器 (UnrealEditor): 锁定插件 DLL + 占用资产句柄, 必须关闭才能构建
#     默认交互询问 (强杀会丢失编辑器内未保存的修改), -ForceKill 跳过询问
$editors = Get-Process -Name "UnrealEditor" -ErrorAction SilentlyContinue
if ($editors) {
    foreach ($p in $editors) {
        Write-Warn2 ("检测到 UE 编辑器正在运行 (PID " + $p.Id + ")")
    }
    if ($ForceKill) {
        Write-Warn2 "-ForceKill 已指定, 直接终止编辑器 (未保存的修改将丢失)"
        $answer = "Y"
    } else {
        # 交互询问: 默认回车=Y 关闭
        $answer = Read-Host "构建需要关闭 UE 编辑器 (否则插件 DLL 被锁定/资产写入冲突)。关闭? [Y/n]"
        if ([string]::IsNullOrWhiteSpace($answer)) { $answer = "Y" }
    }
    if ($answer -match '^[Yy]') {
        foreach ($p in $editors) {
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 3
        Write-Ok "编辑器已关闭"
    } else {
        Write-Fail "用户选择不关闭编辑器, 构建中止 (插件 DLL 被锁定, 无法安全构建)"
        exit 1
    }
} else {
    Write-Ok "无 UE 编辑器进程运行"
}

# ========== 步骤3: 无头模式构建 ==========
Write-Step "启动 UE5 无头模式构建 (可能需要 10~20 分钟)..."
# 主日志文件名带时间戳, 无旧日志覆盖问题; 先写入构建头部信息 (JSON 全路径等)
# 注: build_scene.py 以追加模式打开本文件, 头部内容不会被清掉
Add-MainLog ("[HEADER] ==================== 构建日志 ====================")
Add-MainLog ("[HEADER] 构建开始时间 : " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
Add-MainLog ("[HEADER] 场景 JSON 全路径 : " + $SceneJson)
Add-MainLog ("[HEADER] 目标关卡 : " + $meta.target_level)
Add-MainLog ("[HEADER] ====================================================")
# stdout/stderr 重定向到临时文件 (引擎输出大量噪音, 不作产物保留, 构建后删除)
$TmpOutPath = Join-Path $env:TEMP ("build_umap_stdout_" + [guid]::NewGuid().ToString("N").Substring(0,8) + ".tmp")
$TmpErrPath = Join-Path $env:TEMP ("build_umap_stderr_" + [guid]::NewGuid().ToString("N").Substring(0,8) + ".tmp")

# 场景路径与主日志路径都经环境变量传递:
#   MAPFORGE_SCENE - 场景 JSON (避免 ExecCmds 中 | 被当作 argv 分隔符)
#   MAPFORGE_LOG   - build_scene.py 的直写日志文件 (log() 内部逐行 flush, 实时可靠),
#                    指定为主日志 => 全部 Python 端输出 (含 [DUMP] 转储) 进同一文件
$env:MAPFORGE_SCENE = $SceneJson
$env:MAPFORGE_LOG = $MainLogPath
$execCmds = 'py ' + ($Dir -replace '\\', '/') + '/build_scene.py | quit'
$argStr = '"' + $Proj + '" -unattended -nop4 -nosplash -nullrhi -stdout -ExecCmds="' + $execCmds + '"'

$sw = [System.Diagnostics.Stopwatch]::StartNew()
$proc = Start-Process -FilePath $Exe -ArgumentList $argStr `
    -RedirectStandardOutput $TmpOutPath -RedirectStandardError $TmpErrPath `
    -PassThru -NoNewWindow

# ========== 步骤4: 监控构建进度 ==========
Write-Step ("监控构建进程 (PID " + $proc.Id + "), 超时 " + $TimeoutSec + " 秒...")
$doneMarker = $false
$timeout = $false
while ($true) {
    # 引擎已自然退出 → 结束监控
    if ($proc.HasExited) { break }

    # 检测完成标记 (主日志由 build_scene.py 逐行 flush, 实时可靠)
    if (-not $doneMarker -and (Test-Path $MainLogPath)) {
        $hit = Select-String -Path $MainLogPath -Pattern "BUILD_SCENE_DONE" -SimpleMatch -ErrorAction SilentlyContinue
        if ($hit) {
            $doneMarker = $true
            Write-Ok ("检测到 BUILD_SCENE_DONE (耗时 " + [int]$sw.Elapsed.TotalSeconds + " 秒), 等待引擎退出 (宽限 " + $GraceSec + " 秒)...")
            $graceSw = [System.Diagnostics.Stopwatch]::StartNew()
        }
    }
    # 完成标记已出现但引擎迟迟不退出 → 宽限期满强杀 (UMAP 已落盘, 强杀无害)
    if ($doneMarker -and $graceSw.Elapsed.TotalSeconds -gt $GraceSec) {
        Write-Warn2 "引擎保存完成后挂起未退出, 强制结束进程 (UMAP 已落盘, 不受影响)"
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        break
    }
    # 总超时
    if ($sw.Elapsed.TotalSeconds -gt $TimeoutSec) {
        Write-Fail ("构建超时 (" + $TimeoutSec + " 秒), 强制结束进程")
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        $timeout = $true
        break
    }
    Start-Sleep -Seconds 5
}
$sw.Stop()

# 删除临时 stdout/stderr 文件 (噪音输出不作产物)
Remove-Item $TmpOutPath, $TmpErrPath -Force -ErrorAction SilentlyContinue

# ========== 步骤4.5: 从引擎日志提取 C++ 雕刻日志与错误行, 追加进主日志 ==========
# C++ 插件 (LandscapeHelper) 的 UE_LOG 只进引擎日志, 这里提取关键行以
# [CARVE]/[ERROR] 标签追加到主日志, 实现单一日志文件
$carveLines = @()
$errLines = @()
if (Test-Path $EngineLogPath) {
    # 去掉引擎日志的时间戳前缀 [2026.xx.xx-xx.xx.xx:xxx][  0]
    $stripTs = { param($line) ($line -replace '^\[[^\]]+\]\[\s*\d+\]\s*', '').Trim() }

    $carveLines = Select-String -Path $EngineLogPath -Pattern "河床冲刷|道路推平|LandscapeHelper\[(Scatter|Water|Road|Building|Grass|Layers)\].*(已放置|已创建|解析到|完成|草地)" -ErrorAction SilentlyContinue |
                  Select-Object -First 50 | ForEach-Object { & $stripTs $_.Line }
    $errLines = Select-String -Path $EngineLogPath -Pattern "Error:|Fatal error" -ErrorAction SilentlyContinue |
                Where-Object { $_.Line -notmatch "google.com|LogHttp|LogAutomationTest" } |
                Select-Object -First 10 | ForEach-Object { & $stripTs $_.Line }

    if ($carveLines.Count -gt 0 -or $errLines.Count -gt 0) {
        Add-MainLog ""
        Add-MainLog "[CARVE] ---------- C++ 地形雕刻日志 (提取自引擎日志) ----------"
        foreach ($l in $carveLines) { Add-MainLog ("[CARVE] " + $l) }
        if ($errLines.Count -gt 0) {
            Add-MainLog ""
            Add-MainLog "[ERROR] ---------- 引擎日志错误行 (前10条, 已滤噪音) ----------"
            foreach ($e in $errLines) { Add-MainLog ("[ERROR] " + $e) }
        }
    }
}

# ========== 步骤5: 构建结果摘要 (控制台显示 + 追加主日志) ==========
$elapsed = [int]$sw.Elapsed.TotalSeconds

# 5.1 转储统计: [DUMP] 行数 = 场景档案详细程度
$dumpCount = (Select-String -Path $MainLogPath -Pattern "[DUMP]" -SimpleMatch -ErrorAction SilentlyContinue | Measure-Object).Count
# 5.2 umap 产物路径 (已在上方步骤1.6中计算, 此处直接复用)

# 摘要行 (数组, 同步输出到控制台与主日志)
$summary = @()
$summary += "==================== 构建结果摘要 ===================="
$summary += ("场景文件    : " + $SceneJson)
$summary += ("场景名称    : " + $meta.name)
$summary += ("目标关卡    : " + $meta.target_level)
$summary += ("构建耗时    : " + $elapsed + " 秒")
$summary += ("完成标记    : " + $(if ($doneMarker) { "BUILD_SCENE_DONE 已出现" } else { "未出现" }))
$summary += ("场景转储    : " + $dumpCount + " 行 [DUMP] (地形坐标/图层/河流道路折点/资产坐标高度)")
if ($carveLines.Count -gt 0) {
    $summary += ("地形雕刻    : 河流冲刷 + 道路平整共 " + $carveLines.Count + " 条, 见主日志 [CARVE] 段")
}
if ($umapPath -and (Test-Path $umapPath)) {
    $f = Get-Item $umapPath
    $summary += ("UMAP 产物   : " + $umapPath)
    $summary += ("            大小 " + [math]::Round($f.Length / 1MB, 2) + " MB  保存时间 " + $f.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss"))
} else {
    $summary += ("UMAP 产物   : 未找到 " + $umapPath)
}
$summary += ("主日志文件  : " + $MainLogPath)
$summary += ("            标签速查: [HEADER]构建头 [DUMP]参数转储 [CARVE]雕刻 [ERROR]错误 [SUMMARY]本摘要")
$summary += "======================================================"

Write-Host ""
foreach ($l in $summary) { Write-Host $l -ForegroundColor Magenta }
# 摘要写入主日志
Add-MainLog ""
foreach ($l in $summary) { Add-MainLog ("[SUMMARY] " + $l) }

# 成败判定: 完成标记出现 + umap 文件存在 (引擎退出码在挂起强杀时不可靠)
$buildOk = $false
if ($doneMarker -and $umapPath -and (Test-Path $umapPath)) {
    Write-Ok "构建成功"
    $buildOk = $true
} else {
    Write-Fail "构建失败, 请检查主日志中的 [ERROR] 段"
}

# ========== 步骤6: 历史日志自动清理 ==========
# 时间戳日志会持续累积, 只保留最近 $KeepLogs 份, 旧的自动删除防目录膨胀
$oldLogs = Get-ChildItem -Path $Dir -Filter "build_umap_*.log" -ErrorAction SilentlyContinue |
           Sort-Object LastWriteTime -Descending |
           Select-Object -Skip $KeepLogs
if ($oldLogs) {
    foreach ($ol in $oldLogs) {
        Remove-Item $ol.FullName -Force -ErrorAction SilentlyContinue
    }
    Write-Host ("[清理] 已删除 " + $oldLogs.Count + " 份过期构建日志 (保留最近 " + $KeepLogs + " 份)")
}

# ========== 步骤7: 构建成功后自动打开编辑器 (可选) ==========
# -OpenEditor 开关: 启动 UE 编辑器并直接加载刚生成的 umap, 免手动开工程找关卡
if ($buildOk -and $OpenEditor) {
    Write-Step ("打开 UE 编辑器并加载关卡: " + $meta.target_level)
    # UE 命令行直接带关卡路径打开: UnrealEditor.exe <uproject> <关卡> 
    $editorExe = "D:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe"
    Start-Process -FilePath $editorExe -ArgumentList ('"' + $Proj + '" "' + $meta.target_level + '"')
    Write-Ok "编辑器已启动"
}

if ($buildOk) { exit 0 } else { exit 1 }
