# UE5 MCP capture script v4 (ASCII-only comments to avoid PS5.1 encoding issues)
# Flow: MCP handshake -> get_current_level -> CaptureViewport x8 -> save PNG + labels
$base = 'http://127.0.0.1:8000/mcp'
$shotDir = 'c:\Users\25868\Desktop\UE5\MapForgeTest\shots'
$resultFile = 'c:\Users\25868\Desktop\UE5\MapForgeTest\shots\result3.txt'
$script:id = 0

$initBody = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"trae-agent","version":"1.0"}}}'
$resp = Invoke-WebRequest -Uri $base -Method Post -Body $initBody -ContentType 'application/json' -Headers @{'Accept'='application/json, text/event-stream'} -TimeoutSec 30 -UseBasicParsing
$session = $resp.Headers['mcp-session-id']
if (-not $session) { Write-Output 'FATAL: no session id'; exit 1 }
$headers = @{ 'Accept' = 'application/json, text/event-stream'; 'mcp-session-id' = $session }
try { Invoke-WebRequest -Uri $base -Method Post -Body '{"jsonrpc":"2.0","method":"notifications/initialized"}' -ContentType 'application/json' -Headers $headers -TimeoutSec 15 -UseBasicParsing | Out-Null } catch {}
Write-Output ('session=' + $session)

function Invoke-McpTool($toolset, $tool, $toolArgs, $timeoutSec = 240) {
    $script:id++
    $payload = @{
        jsonrpc = '2.0'; id = (1000 + $script:id)
        method  = 'tools/call'
        params  = @{ name = 'call_tool'; arguments = @{ toolset_name = $toolset; tool_name = $tool; arguments = $toolArgs } }
    }
    $body = $payload | ConvertTo-Json -Depth 15 -Compress
    $r = Invoke-WebRequest -Uri $base -Method Post -Body $body -ContentType 'application/json' -Headers $headers -TimeoutSec $timeoutSec -UseBasicParsing
    $rawFile = Join-Path $shotDir ('raw_' + $tool + '_' + $script:id + '.txt')
    [IO.File]::WriteAllText($rawFile, $r.Content)
    return ($r.Content | ConvertFrom-Json)
}

function Log-Line($msg) {
    Add-Content -Path $resultFile -Value $msg -Encoding utf8
    Write-Output $msg
}

Set-Content -Path $resultFile -Value ('=== capture v4 start ' + (Get-Date -Format 'HH:mm:ss') + ' session=' + $session + ' ===') -Encoding utf8

$r = Invoke-McpTool 'editor_toolset.toolsets.scene.SceneTools' 'get_current_level' @{}
$lv = ''
try { $lv = ($r.result.content[0].text | ConvertFrom-Json).returnValue } catch { $lv = '[parse_err] ' + $r.result.content[0].text }
Log-Line ('current_level: ' + $lv)
if (-not ($lv -match 'GB_SmartAgriDroneFieldTerrain')) {
    Log-Line 'level not loaded, loading...'
    $r = Invoke-McpTool 'editor_toolset.toolsets.scene.SceneTools' 'load_level' @{ level_path = '/Game/MapForgeTest/GB_SmartAgriDroneFieldTerrain' } 600
    Start-Sleep -Seconds 90
    $r = Invoke-McpTool 'editor_toolset.toolsets.scene.SceneTools' 'get_current_level' @{}
    try { $lv = ($r.result.content[0].text | ConvertFrom-Json).returnValue } catch { $lv = '[parse_err]' }
    Log-Line ('current_level after load: ' + $lv)
}

# annotations: grid disabled (gridSpacing=0) but actor labels on; only StaticMeshActor labeled
$ann = @{
    gridSpacing      = 0
    gridExtent       = 0
    gridHeight       = 0
    maxLabelDistance = 300000
    classFilter      = @{ refPath = '/Script/Engine.StaticMeshActor' }
    maxLabels        = 20
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
        $r = Invoke-McpTool 'EditorToolset.EditorAppToolset' 'CaptureViewport' $capArgs
        if ($r.error) { Log-Line ($v.name + ' ERROR: ' + ($r.error | ConvertTo-Json -Compress)); Start-Sleep -Seconds 3; continue }
        $txt = ''
        try { $txt = [string]$r.result.content[0].text } catch { Log-Line ($v.name + ' CONTENT_PARSE_FAIL'); Start-Sleep -Seconds 3; continue }
        $obj = $null
        try { $obj = $txt | ConvertFrom-Json } catch { }
        $ret = $null
        if ($obj -and $obj.returnValue) { $ret = $obj.returnValue } elseif ($obj) { $ret = $obj }
        if ($ret -and $ret.image -and $ret.image.data) {
            [IO.File]::WriteAllBytes((Join-Path $shotDir ($v.name + '.png')), [Convert]::FromBase64String($ret.image.data))
            Log-Line ($v.name + ' SAVED png b64len=' + $ret.image.data.Length + ' fov=' + $ret.cameraFOV)
            if ($ret.labeledActors) {
                foreach ($la in ($ret.labeledActors | Select-Object -First 20)) {
                    Log-Line ('  label: ' + $la.name + ' dist=' + [Math]::Round($la.distanceCm / 100.0, 1) + 'm pos=(' + [Math]::Round($la.worldLocation.x / 100.0, 0) + ',' + [Math]::Round($la.worldLocation.y / 100.0, 0) + ',' + [Math]::Round($la.worldLocation.z / 100.0, 0) + ')m')
                }
            }
        } else {
            Log-Line ($v.name + ' NO_IMAGE raw=raw_CaptureViewport_' + $script:id + '.txt')
        }
    } catch {
        Log-Line ($v.name + ' EXCEPTION: ' + $_.Exception.Message)
    }
    Start-Sleep -Seconds 3
}
Log-Line ('=== capture v4 done ' + (Get-Date -Format 'HH:mm:ss') + ' ===')
