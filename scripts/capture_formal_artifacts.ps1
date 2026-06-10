param(
    [string]$Label = 'manual'
)

. (Join-Path $PSScriptRoot 'common.ps1')

$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$captureDir = Join-Path (Get-ArtifactsRoot) ("${timestamp}_$Label")
New-Item -ItemType Directory -Force -Path $captureDir | Out-Null

$logsDir = Join-Path $captureDir 'logs'
$finalResultsDir = Join-Path $captureDir 'final_results'
$snapshotsDir = Join-Path $captureDir 'snapshots'
$screensDir = Join-Path $captureDir 'screenshots'
New-Item -ItemType Directory -Force -Path $logsDir, $finalResultsDir, $snapshotsDir, $screensDir | Out-Null

Write-Step 'Collecting official final results package'
$officialPackageRoot = Join-Path (Get-FinalResultsRoot) 'fbbp_formal_atlas_v2026_04'
if (Test-Path $officialPackageRoot) {
    Copy-Item (Join-Path $officialPackageRoot '*') $finalResultsDir -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Step 'Collecting backend and frontend logs'
if (Test-Path (Join-Path (Get-DeerflowRoot) 'logs')) {
    Copy-Item (Join-Path (Get-DeerflowRoot) 'logs\*') $logsDir -Recurse -Force -ErrorAction SilentlyContinue
}

$frontendLocal = Get-FrontendLocalRoot
if (Test-Path $frontendLocal) {
    Copy-Item (Join-Path $frontendLocal 'frontend_dev*.log') $logsDir -Force -ErrorAction SilentlyContinue
}

Write-Step 'Collecting WSL MCP logs'
$wslLogsPath = Convert-ToWslPath (Get-WslRuntimeRoot)
$mcpOut = wsl bash -lc "cat '$wslLogsPath/http_mcp.out.log' 2>/dev/null || true"
$mcpErr = wsl bash -lc "cat '$wslLogsPath/http_mcp.err.log' 2>/dev/null || true"
Save-TextFile -Path (Join-Path $logsDir 'http_mcp_wsl.out.log') -Content $mcpOut
Save-TextFile -Path (Join-Path $logsDir 'http_mcp_wsl.err.log') -Content $mcpErr

Write-Step 'Capturing endpoint responses'
$endpointRecords = @()
foreach ($url in @(
    'http://127.0.0.1:3000/',
    'http://127.0.0.1:3000/fbbp',
    'http://127.0.0.1:3000/api/fbbp/dashboard',
    'http://127.0.0.1:8001/health',
    'http://127.0.0.1:8001/api/fbbp/status',
    'http://127.0.0.1:2024/docs',
    'http://127.0.0.1:8000/mcp'
)) {
    try {
        if ($url -like '*8000/mcp') {
            $resp = Invoke-WebRequest -Uri $url -Headers @{ Accept = 'text/event-stream' } -TimeoutSec 20 -UseBasicParsing
        } else {
            $resp = Invoke-WebRequest -Uri $url -TimeoutSec 20 -UseBasicParsing
        }
        $safeName = ($url -replace '^https?://', '' -replace '[^A-Za-z0-9._-]', '_')
        Save-TextFile -Path (Join-Path $snapshotsDir "$safeName.txt") -Content $resp.Content
        $endpointRecords += [pscustomobject]@{ Url = $url; Status = [int]$resp.StatusCode; Saved = "$safeName.txt" }
    } catch {
        $endpointRecords += [pscustomobject]@{ Url = $url; Status = 'ERROR'; Saved = '' }
    }
}

Write-Step 'Capturing screenshots when possible'
$shots = @(
    @{ Url = 'http://127.0.0.1:3000/'; File = 'frontend_home.png' },
    @{ Url = 'http://127.0.0.1:3000/fbbp'; File = 'fbbp_formal_console.png' },
    @{ Url = 'http://127.0.0.1:2024/docs'; File = 'langgraph_docs.png' },
    @{ Url = 'http://127.0.0.1:8001/docs'; File = 'gateway_docs.png' }
)

$shotResults = @()
foreach ($shot in $shots) {
    $out = Join-Path $screensDir $shot.File
    $ok = $false
    try {
        $ok = Invoke-HeadlessScreenshot -Url $shot.Url -OutputPath $out
    } catch {
        $ok = $false
    }
    $shotResults += [pscustomobject]@{ Url = $shot.Url; File = $shot.File; Captured = $ok }
}

Write-Step 'Saving environment and port status'
$wslIp = $null
try { $wslIp = Get-WslPrimaryIp } catch { $wslIp = '' }
$portStatus = @(
    3000, 8000, 8001, 2024
) | ForEach-Object {
    $res = Test-NetConnection -ComputerName '127.0.0.1' -Port $_ -WarningAction SilentlyContinue
    [pscustomobject]@{ Port = $_; Open = $res.TcpTestSucceeded }
}

$summary = [ordered]@{
    timestamp = $timestamp
    label = $Label
    deerflow_config = (Get-DeerflowConfigPath)
    deerflow_extensions = (Get-DeerflowExtensionsPath)
    frontend_local_root = $frontendLocal
    official_package_root = $officialPackageRoot
    wsl_ip = $wslIp
    endpoint_status = $endpointRecords
    screenshot_status = $shotResults
    port_status = $portStatus
    official_package_files = if (Test-Path $officialPackageRoot) { Get-ChildItem $officialPackageRoot -File | Select-Object -ExpandProperty Name } else { @() }
    canonical_overview = if (Test-Path (Join-Path $officialPackageRoot 'atlas_overview.md')) { 'atlas_overview.md' } else { '' }
}

$summaryJson = ($summary | ConvertTo-Json -Depth 20)
Save-TextFile -Path (Join-Path $captureDir 'summary.json') -Content $summaryJson

Write-Host ''
Write-Host 'Artifacts captured to:'
Write-Host "  $captureDir"
