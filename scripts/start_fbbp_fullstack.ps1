param(
    [switch]$NoOpen,
    [switch]$SkipCore,
    [switch]$BuildDashboardOnly
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

Write-Host "== FBBP full-stack launcher =="
Write-Host "Repo: $RepoRoot"

& (Join-Path $RepoRoot "scripts\build_portfolio_dashboard.ps1")
if ($LASTEXITCODE -ne 0) {
    throw "Portfolio dashboard build failed."
}

if (-not $BuildDashboardOnly) {
    if (-not $SkipCore) {
        & (Join-Path $RepoRoot "scripts\start_stack_core.ps1")
    }
    & (Join-Path $RepoRoot "scripts\start_frontend_local.ps1")

    $PythonCandidates = @(
        (Join-Path $RepoRoot ".venv\Scripts\python.exe"),
        "python"
    )
    $PythonExe = $PythonCandidates | Where-Object { if ($_ -eq "python") { $true } else { Test-Path $_ } } | Select-Object -First 1
    if (-not $PythonExe) {
        throw "Could not resolve a Python executable for the dashboard server."
    }

    $DashboardPortBusy = $false
    try {
        $DashboardPortBusy = [bool](Get-NetTCPConnection -LocalPort 8088 -State Listen -ErrorAction Stop)
    } catch {
        $DashboardPortBusy = $false
    }
    if (-not $DashboardPortBusy) {
        Start-Process -FilePath $PythonExe `
            -ArgumentList @((Join-Path $RepoRoot "scripts\control_plane\dashboard_server.py"), "--host", "127.0.0.1", "--port", "8088") `
            -WorkingDirectory $RepoRoot `
            -WindowStyle Hidden | Out-Null
    }
}

$Dashboard = "http://127.0.0.1:8088"
Write-Host ""
Write-Host "FBBP full-stack assets are ready:"
Write-Host "  Portfolio dashboard: $Dashboard"
Write-Host "  Workbench UI:        http://127.0.0.1:3000/workspace"
Write-Host "  Formal page:         http://127.0.0.1:3000/fbbp"
Write-Host "  Gateway health:      http://127.0.0.1:8001/health"
Write-Host "  MCP endpoint:        http://127.0.0.1:8000/mcp"

if (-not $NoOpen) {
    Start-Process $Dashboard | Out-Null
}
