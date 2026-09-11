# UE5 MCP 截图脚本 (第2版: 补上必需的 annotations 参数)
# 关卡已加载, 只做8个视角 CaptureViewport + 保存PNG + 汇总标签
$session = '39163d4644b75600a75be88c84104a3c'
$base = 'http://127.0.0.1:8000/mcp'
$headers = @{ 'Accept' = 'application/json, text/event-stream'; 'mcp-session-id' = $session }
$script:id = 200
$shotDir = 'c:\Users\25868\Desktop\UE5\MapForgeTest\shots'
$resultFile = 'c:\Users\25868\Desktop\UE5\MapForgeTest\shots\result2.txt'

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

Set-Content -Path $resultFile -Value ('=== capture v2 start ' + (Get-Date -Format 'HH:mm:ss') + ' ===') -Encoding utf8

# annotations: gridSpacing=0 禁用网格但绘制Actor标签; maxLabelDistance=300000(3km内标签)
$ann = @{
    gridSpacing     = 0
    gridExtent      = 0
    gridHeight      = 0
    maxLabelDistance = 300000
    classFilter     = @{ refPath = '' }
    maxLabels       = 20
}

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
        $capArgs = @{ captureTransform = @{ location = $v.loc; rotation = $v.rot }; annotations = $ann; bShowUI = $false }
        $r = Invoke-McpTool 'EditorToolset.EditorAppToolset' 'CaptureViewport' $capArgs 180
        if ($r.error) { Log-Line ($v.name + ' ERROR: ' + ($r.error.message)); continue }
        $txt = $r.result.content[0].text
        $obj = $null
        try { $obj = $txt | ConvertFrom-Json } catch { }
        $ret = $null
        if ($obj -and $obj.returnValue) { $ret = $obj.returnValue } elseif ($obj) { $ret = $obj }
        if ($ret -and $ret.image -and $ret.image.data) {
            [IO.File]::WriteAllBytes((Join-Path $shotDir ($v.name + '.png')), [Convert]::FromBase64String($ret.image.data))
            Log-Line ($v.name + ' SAVED png b64len=' + $ret.image.data.Length + ' cam_fov=' + $ret.cameraFOV)
            # 汇总标签: Actor名 + 距离
            if ($ret.labeledActors) {
                foreach ($la in ($ret.labeledActors | Select-Object -First 20)) {
                    Log-Line ('  label: ' + $la.name + ' [' + ($la.class.refPath) + '] dist=' + [Math]::Round($la.distanceCm / 100.0, 1) + 'm')
                }
            }
        } else {
            Log-Line ($v.name + ' NO_IMAGE: ' + (($txt | Out-String).Substring(0, [Math]::Min(400, ($txt | Out-String).Length))))
        }
    } catch {
        Log-Line ($v.name + ' EXCEPTION: ' + $_.Exception.Message)
    }
}
Log-Line ('=== capture v2 done ' + (Get-Date -Format 'HH:mm:ss') + ' ===')
