param(
    [int]$Port = 5432,
    [string]$Database = 'ragkb',
    [string]$User = 'ragkb',
    [string]$Password = 'ragkb',
    [switch]$RestartWsl,
    [switch]$Json
)

. (Join-Path $PSScriptRoot 'common.ps1')

if ($RestartWsl) {
    Write-Step 'Restarting WSL before PostgreSQL bridge repair'
    & wsl --shutdown
    Start-Sleep -Seconds 2
}

Write-Step 'Repairing Windows -> WSL PostgreSQL localhost bridge'
Remove-LocalPostgresPortProxy -Port $Port
$readyHost = Ensure-LocalFormalPostgresReady -Port $Port -Database $Database -User $User -Password $Password

$tcpReady = $false
$tcpProbeHost = if ($readyHost -eq 'localhost') { '127.0.0.1' } else { $readyHost }
try {
    $tcpReady = [bool](Test-NetConnection -ComputerName $tcpProbeHost -Port $Port -InformationLevel Quiet)
} catch {
    $tcpReady = $false
}

$queryReady = Test-PostgresQueryReady -ProbeHost $readyHost -Port $Port -Database $Database -User $User -Password $Password
$wslReachable = $false
try {
    $wslIpRaw = ((& wsl bash -lc "hostname -I") -join ' ').Trim()
    $wslReachable = -not [string]::IsNullOrWhiteSpace($wslIpRaw)
} catch {
    $wslReachable = $false
}

$portProxy = ''
try {
    $portProxy = ((& netsh interface portproxy show all) -join "`n").Trim()
} catch {
    $portProxy = ''
}

$payload = [ordered]@{
    ok = ($tcpReady -and $queryReady)
    ready_host = $readyHost
    tcp_probe_host = $tcpProbeHost
    port = $Port
    tcp_ready = $tcpReady
    query_ready = $queryReady
    wsl_reachable = $wslReachable
    portproxy_empty = [string]::IsNullOrWhiteSpace($portProxy)
}

if ($Json) {
    $payload | ConvertTo-Json -Compress
} else {
    $payload | ConvertTo-Json
}

if (-not $payload.ok) {
    throw "Windows -> WSL PostgreSQL bridge is not ready at ${readyHost}:$Port"
}
