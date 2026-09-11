# UE5 MCP 截图验证脚本
# 通过编辑器自带 ModelContextProtocol HTTP 服务(127.0.0.1:8000)驱动:
#   1. SceneTools.load_level 加载 GB_SmartAgriDroneFieldTerrain
#   2. 每个视角调用 EditorAppToolset.CaptureViewport(带captureTransform) 截图
#   3. base64 PNG 解码保存到 shots 目录, 汇总写入 result.txt
$session = '39163d4644b75600a75be88c84104a3c'
$base = 'http://127.0.0.1:8000/mcp'
$headers = @{ 'Accept' = 'application/json, text/event-stream'; 'mcp-session-id' = $session }
$script:id = 100
$shotDir = 'c:\Users\25868\Desktop\UE5\MapForgeTest\shots'
$resultFile = 'c:\Users\25868\Desktop\UE5\MapForgeTest\shots\result.txt'

# --- MCP 工具调用封装 ---
function Invoke-McpTool($toolset, $tool, $toolArgs, $timeoutSec = 180) {
    $script:id++
    $payload = @{
        jsonrpc = '2.0'; id = $script:id
        method  = 'tools/call'
        params  = @{ name = 'call_tool'; arguments = @{ toolset_name = $toolset; tool_name = $tool; arguments = $toolArgs } }
    }
    $body = $payload | ConvertTo-Json -Depth 15 -Compress
    $resp = Invoke-WebRequest -Uri $base -Method Post -Body $body -ContentType 'application/json' -Headers $headers -TimeoutSec $timeoutSec -UseBasicParsing
    return ($resp.Content | ConvertFrom-Json)
}

function Log-Line($msg) {
    Add-Content -Path $resultFile -Value $msg -Encoding utf8
    Write-Output $msg
}

Set-Content -Path $resultFile -Value ('=== MCP capture start ' + (Get-Date -Format 'HH:mm:ss') + ' ===') -Encoding utf8

# --- 1. 加载关卡 (阻塞式, 超时600s) ---
Log-Line ('loading level ...')
$r = Invoke-McpTool 'editor_toolset.toolsets.scene.SceneTools' 'load_level' @{ level_path = '/Game/MapForgeTest/GB_SmartAgriDroneFieldTerrain' } 600
if ($r.error) { Log-Line ('LOAD_ERROR: ' + ($r.error | ConvertTo-Json -Compress)); exit 1 }
Log-Line ('load_level done: ' + (($r.result | ConvertTo-Json -Depth 4 -Compress).Substring(0, 300)))

# 等待关卡流送/渲染资源就绪
Start-Sleep -Seconds 60
$r2 = Invoke-McpTool 'editor_toolset.toolsets.scene.SceneTools' 'get_current_level' @{}
Log-Line ('current_level: ' + (($r2.result.content[0].text)))

# --- 2. 8 个验证视角 (相机位置cm/旋转角度, 坐标来自场景JSON分区) ---
$viewpoints = @(
    @{ name = '01_overview';      loc = @{ x = 0;       y = 0;       z = 420000  }; rot = @{ pitch = -89.5; yaw = 0;   roll = 0 } },
    @{ name = '02_pad_fence';     loc = @{ x = 0;       y = 20000;   z = 6000    }; rot = @{ pitch = -32;   yaw = 180; roll = 0 } },
    @{ name = '03_pv_west';       loc = @{ x = -16000;  y = -12000;  z = 2600    }; rot = @{ pitch = -35;   yaw = 25;  roll = 0 } },
    @{ name = '04_wheat_ne';      loc = @{ x = 60000;   y = 30000;   z = 1800    }; rot = @{ pitch = -35;   yaw = 40;  roll = 0 } },
    @{ name = '05_forest_north';  loc = @{ x = 0;       y = 165000;  z = 3500    }; rot = @{ pitch = -8;    yaw = 90;  roll = 0 } },
    @{ name = '06_hv_nw';         loc = @{ x = -208000; y = 208000;  z = 8000    }; rot = @{ pitch = -15;   yaw = 135; roll = 0 } },
    @{ name = '07_village';       loc = @{ x = -108000; y = 16000;   z = 2500    }; rot = @{ pitch = -15;   yaw = 150; roll = 0 } },
    @{ name = '08_comm_sw';       loc = @{ x = -185000; y = -185000; z = 5000    }; rot = @{ pitch = -25;   yaw = 225; roll = 0 } }
)

foreach ($v in $viewpoints) {
    try {
        $capArgs = @{ captureTransform = @{ location = $v.loc; rotation = $v.rot }; bShowUI = $false }
        $r = Invoke-McpTool 'EditorToolset.EditorAppToolset' 'CaptureViewport' $capArgs 180
        if ($r.error) { Log-Line ($v.name + ' ERROR: ' + ($r.error.message)); continue }
        # 返回值一般在 result.content[0].text (JSON字符串) 或直接 result.returnValue
        $txt = $r.result.content[0].text
        $obj = $null
        try { $obj = $txt | ConvertFrom-Json } catch { }
        $img = $null
        if ($obj -and $obj.returnValue -and $obj.returnValue.image) { $img = $obj.returnValue.image }
        elseif ($obj -and $obj.image) { $img = $obj.image }
        if ($img -and $img.data) {
            $png = [IO.File]::WriteAllBytes((Join-Path $shotDir ($v.name + '.png')), [Convert]::FromBase64String($img.data))
            Log-Line ($v.name + ' saved ' + $img.mimeType + ' b64len=' + $img.data.Length)
        } else {
            Log-Line ($v.name + ' NO_IMAGE: ' + (($txt | Out-String).Substring(0, [Math]::Min(300, ($txt | Out-String).Length))))
        }
    } catch {
        Log-Line ($v.name + ' EXCEPTION: ' + $_.Exception.Message)
    }
}
Log-Line ('=== MCP capture done ' + (Get-Date -Format 'HH:mm:ss') + ' ===')
