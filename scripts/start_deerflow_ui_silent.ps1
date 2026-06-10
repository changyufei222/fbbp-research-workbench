param(
    [switch]$NoOpen
)

. (Join-Path $PSScriptRoot 'common.ps1')

$logsRoot = Join-Path (Get-RuntimeRoot) 'ui'
New-Item -ItemType Directory -Force -Path $logsRoot | Out-Null
$transcriptPath = Join-Path $logsRoot 'start_deerflow_ui_silent.log'

Start-Transcript -Path $transcriptPath -Append | Out-Null
try {
    $runtimeEnv = Get-DeerflowRuntimeEnv
    if (-not $runtimeEnv['OPENAI_API_KEY']) {
        throw "OPENAI_API_KEY is not configured. See $transcriptPath"
    }

    if (-not (Test-PostgresQueryReady -ProbeHost 'localhost' -Port 5432 -Database 'ragkb' -User 'ragkb' -Password 'ragkb')) {
        Write-Step 'Starting WSL PostgreSQL for formal FBBP queries'
        & (Join-Path $PSScriptRoot 'start_wsl_pgvector.ps1')
    }

    if (-not (Test-PostgresQueryReady -ProbeHost 'localhost' -Port 5432 -Database 'ragkb' -User 'ragkb' -Password 'ragkb')) {
        throw 'PostgreSQL query probe on localhost:5432 is not ready.'
    }

    & (Join-Path $PSScriptRoot 'start_fullstack_local_frontend.ps1')

    if (-not (Wait-TcpPort -ComputerName '127.0.0.1' -Port 3000 -TimeoutSeconds 30)) {
        throw 'Frontend port 3000 is not ready.'
    }

    $url = 'http://127.0.0.1:3000/workspace'

    Write-Host ''
    Write-Host 'Silent DeerFlow UI launcher is ready:'
    Write-Host "  $url"
Write-Host '  Formal results page: http://127.0.0.1:3000/fbbp'
    Write-Host "  Log: $transcriptPath"

    if (-not $NoOpen) {
        Start-Process $url | Out-Null
    }
} finally {
    Stop-Transcript | Out-Null
}
