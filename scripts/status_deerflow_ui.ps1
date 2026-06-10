param(
    [switch]$Json
)

. (Join-Path $PSScriptRoot 'common.ps1')

function Test-HttpEndpoint {
    param(
        [string]$Url,
        [int[]]$AcceptStatusCodes = @(200),
        [int]$TimeoutSeconds = 2
    )

    try {
        $response = Invoke-WebRequest -Uri $Url -Method Get -UseBasicParsing -TimeoutSec $TimeoutSeconds -ErrorAction Stop
        return [ordered]@{
            ok = $response.StatusCode -in $AcceptStatusCodes
            status_code = [int]$response.StatusCode
            error = $null
        }
    } catch {
        $statusCode = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { $null }
        return [ordered]@{
            ok = $statusCode -in $AcceptStatusCodes
            status_code = $statusCode
            error = if ($statusCode -in $AcceptStatusCodes) { $null } else { $_.Exception.Message }
        }
    }
}

function Test-TcpPortFast {
    param(
        [string]$ComputerName,
        [int]$Port,
        [int]$TimeoutMs = 800
    )

    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $async = $client.BeginConnect($ComputerName, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) {
            return $false
        }
        $client.EndConnect($async)
        return $client.Connected
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Test-LocalListeningPort {
    param([int]$Port)

    return [bool](Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -eq $Port } |
        Select-Object -First 1)
}

$frontendRoot = Get-FrontendLocalRoot
$backendLogsRoot = Join-Path (Get-DeerflowRoot) 'logs'
$mcpLogsRoot = Join-Path (Get-RuntimeRoot) 'mcp'
$uiLogsRoot = Join-Path (Get-RuntimeRoot) 'ui'

$wslIp = $null
try {
    $wslIp = Get-WslPrimaryIp
} catch {
}

$frontendTcp = Test-LocalListeningPort -Port 3000
$gatewayTcp = Test-LocalListeningPort -Port 8001
$langgraphTcp = Test-LocalListeningPort -Port 2024
$mcpTcp = Test-LocalListeningPort -Port 8000

$frontendHttp = if ($frontendTcp) { Test-HttpEndpoint -Url 'http://127.0.0.1:3000/fbbp' -AcceptStatusCodes @(200) -TimeoutSeconds 5 } else { [ordered]@{ ok = $false; status_code = $null; error = 'TCP port is not ready.' } }
$gatewayHttp = if ($gatewayTcp) { Test-HttpEndpoint -Url 'http://127.0.0.1:8001/health' -AcceptStatusCodes @(200) } else { [ordered]@{ ok = $false; status_code = $null; error = 'TCP port is not ready.' } }
$langgraphHttp = if ($langgraphTcp) { Test-HttpEndpoint -Url 'http://127.0.0.1:2024/docs' -AcceptStatusCodes @(200) } else { [ordered]@{ ok = $false; status_code = $null; error = 'TCP port is not ready.' } }
$mcpHttp = if ($mcpTcp) { Test-HttpEndpoint -Url 'http://127.0.0.1:8000/mcp' -AcceptStatusCodes @(200, 405, 406) } else { [ordered]@{ ok = $false; status_code = $null; error = 'TCP port is not ready.' } }

$payload = [ordered]@{
ui_url = 'http://127.0.0.1:3000/fbbp'
    components = [ordered]@{
        frontend = [ordered]@{
            port = 3000
            tcp_ready = $frontendTcp
            http = $frontendHttp
        }
        gateway = [ordered]@{
            port = 8001
            tcp_ready = $gatewayTcp
            http = $gatewayHttp
        }
        langgraph = [ordered]@{
            port = 2024
            tcp_ready = $langgraphTcp
            http = $langgraphHttp
        }
        mcp = [ordered]@{
            port = 8000
            tcp_ready = $mcpTcp
            http = $mcpHttp
        }
        postgres = [ordered]@{
            host = 'localhost'
            port = 5432
            tcp_ready = Test-TcpPortFast -ComputerName '127.0.0.1' -Port 5432
            query_ready = Test-PostgresQueryReady -ProbeHost 'localhost' -Port 5432 -Database 'ragkb' -User 'ragkb' -Password 'ragkb'
            wsl_ip = $wslIp
        }
    }
    logs = [ordered]@{
        frontend_out = (Join-Path $frontendRoot 'frontend_dev.out.log')
        frontend_err = (Join-Path $frontendRoot 'frontend_dev.err.log')
        langgraph_out = (Join-Path $backendLogsRoot 'langgraph_win.out.log')
        langgraph_err = (Join-Path $backendLogsRoot 'langgraph_win.err.log')
        gateway_out = (Join-Path $backendLogsRoot 'gateway_win.out.log')
        gateway_err = (Join-Path $backendLogsRoot 'gateway_win.err.log')
        mcp_out = (Join-Path $mcpLogsRoot 'http_mcp_windows.out.log')
        mcp_err = (Join-Path $mcpLogsRoot 'http_mcp_windows.err.log')
        ui_start = (Join-Path $uiLogsRoot 'start_deerflow_ui_silent.log')
        ui_stop = (Join-Path $uiLogsRoot 'stop_deerflow_ui_silent.log')
    }
}

if ($Json) {
    $payload | ConvertTo-Json -Depth 8
} else {
    $payload | ConvertTo-Json -Depth 8
}
