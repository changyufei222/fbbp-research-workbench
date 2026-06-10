. (Join-Path $PSScriptRoot 'common.ps1')

$ErrorActionPreference = 'Stop'

Write-Step 'Starting FBBP HTTP MCP server (Windows preferred, WSL fallback)'

function Test-McpEndpoint {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 30
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-WebRequest -Uri $Url -Method Get -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
            if ($resp.StatusCode -ge 200) {
                return $true
            }
        } catch {
            $statusCode = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { -1 }
            if ($statusCode -in @(405, 406)) {
                return $true
            }
        }
        Start-Sleep -Seconds 2
    }
    return $false
}

function Update-FbbpHttpMcpUrl {
    param([string]$McpUrl)

    foreach ($jsonPath in @(
        (Get-DeerflowExtensionsPath),
        (Join-Path (Get-WorkspaceRoot) 'configs/extensions_config.fbbp.example.json'),
        (Join-Path (Get-WorkspaceRoot) 'configs/extensions_config.fbtp.example.json')
    )) {
        if (-not (Test-Path $jsonPath)) {
            continue
        }
        $obj = Get-Content $jsonPath -Raw | ConvertFrom-Json
        foreach ($serverName in @('fbbp-rag', 'fbtp-rag')) {
            if ($obj.mcpServers.PSObject.Properties.Name -notcontains $serverName) {
                continue
            }
            $obj.mcpServers.$serverName.type = 'http'
            $obj.mcpServers.$serverName.url = $McpUrl
            $obj.mcpServers.$serverName.description = 'Private FBBP knowledge retrieval over ragkb (HTTP MCP)'
            $obj.mcpServers.$serverName.PSObject.Properties.Remove('command')
            $obj.mcpServers.$serverName.PSObject.Properties.Remove('args')
            $obj.mcpServers.$serverName.PSObject.Properties.Remove('env')
        }
        $jsonText = $obj | ConvertTo-Json -Depth 20
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($jsonPath, $jsonText, $utf8NoBom)
    }
}

function Start-WindowsHttpMcp {
    $mcpPython = Get-McpPython
    if (-not (Test-PythonUsable $mcpPython)) {
        Write-Warning "Windows MCP Python is not usable at $mcpPython"
        return $null
    }
    Ensure-LocalFormalPostgresReady -Port 5432 -Database 'ragkb' -User 'ragkb' -Password 'ragkb' | Out-Null
    $resolvedPgHost = Set-RagkbEnv

    if (-not $env:OPENAI_BASE_URL) {
        if ($env:OPENAI_API_BASE) {
            $env:OPENAI_BASE_URL = $env:OPENAI_API_BASE
        } elseif ($env:BASE_URL) {
            $env:OPENAI_BASE_URL = $env:BASE_URL
        }
    }

    $datasetVersion = if ($env:FBBP_FORMAL_DATASET_VERSION) {
        $env:FBBP_FORMAL_DATASET_VERSION
    } elseif ($env:FBTP_FORMAL_DATASET_VERSION) {
        $env:FBTP_FORMAL_DATASET_VERSION
    } else {
        'fbbp_private_v2026_04'
    }
    $runtimeProfile = if ($env:FBBP_FORMAL_RUNTIME_PROFILE) {
        $env:FBBP_FORMAL_RUNTIME_PROFILE
    } elseif ($env:FBTP_FORMAL_RUNTIME_PROFILE) {
        $env:FBTP_FORMAL_RUNTIME_PROFILE
    } else {
        'local_formal'
    }
    $env:FBBP_FORMAL_DATASET_VERSION = $datasetVersion
    $env:FBTP_FORMAL_DATASET_VERSION = $datasetVersion
    $env:FBBP_FORMAL_RUNTIME_PROFILE = $runtimeProfile
    $env:FBTP_FORMAL_RUNTIME_PROFILE = $runtimeProfile

    if (-not (Test-PostgresQueryReady -ProbeHost $env:PGHOST -Port ([int]$env:PGPORT) -Database $env:PGDATABASE -User $env:PGUSER -Password $env:PGPASSWORD)) {
        Write-Warning "PostgreSQL is not reachable at ${resolvedPgHost}:$($env:PGPORT)"
        return $null
    }

    $env:PYTHONNOUSERSITE = '1'
    $env:FBBP_MCP_USE_SUBPROCESS_WORKER = '0'
    $env:FBTP_MCP_USE_SUBPROCESS_WORKER = '0'

    $httpStartScript = Join-Path (Get-McpRoot) 'scripts/start_http_server.ps1'
    $logsDir = Join-Path (Get-RuntimeRoot) 'mcp'
    New-Item -ItemType Directory -Force -Path $logsDir | Out-Null
    $outLog = Join-Path $logsDir 'http_mcp_windows.out.log'
    $errLog = Join-Path $logsDir 'http_mcp_windows.err.log'

    Start-Process -FilePath 'powershell' `
        -ArgumentList @(
            '-NoProfile',
            '-ExecutionPolicy', 'Bypass',
            '-File', $httpStartScript,
            '-ListenHost', '0.0.0.0',
            '-Port', '8000',
            '-PgHost', $env:PGHOST,
            '-PgPort', $env:PGPORT,
            '-PgDatabase', $env:PGDATABASE,
            '-PgUser', $env:PGUSER,
            '-PgPassword', $env:PGPASSWORD,
            '-PgTable', $env:PGTABLE,
            '-DatasetVersion', $datasetVersion,
            '-RuntimeProfile', $runtimeProfile
        ) `
        -WorkingDirectory (Get-McpRoot) `
        -WindowStyle 'Hidden' `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog | Out-Null

    if (Test-McpEndpoint -Url 'http://127.0.0.1:8000/mcp' -TimeoutSeconds 45) {
        return 'http://127.0.0.1:8000/mcp'
    }

    Write-Warning "Windows MCP HTTP probe did not succeed. Check $errLog"
    return $null
}

Stop-ProcessesByPort -Ports @(8000)

$mcpUrl = Start-WindowsHttpMcp
if (-not $mcpUrl) {
    Stop-ProcessesByPort -Ports @(8000)
    Write-Warning 'Falling back to WSL MCP launcher.'
    & (Join-Path $PSScriptRoot 'start_fbbp_http_mcp_wsl.ps1') | Out-Null
    $mcpUrl = Get-FbbpMcpHttpUrl
} else {
    Update-FbbpHttpMcpUrl -McpUrl $mcpUrl
}

Write-Host "FBBP HTTP MCP server is ready at $mcpUrl"
