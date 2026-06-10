param(
    [switch]$Open
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

Write-Host "== Building FBBP portfolio dashboard =="
& python (Join-Path $RepoRoot "scripts\control_plane\final_release_check.py")
if ($LASTEXITCODE -ne 0) {
    throw "final_release_check.py failed"
}

$Dashboard = Join-Path $RepoRoot "reports\control_plane_portfolio_dashboard\latest\index.html"
Write-Host "Dashboard: $Dashboard"
Write-Host "Live console URL after starting the service: http://127.0.0.1:8088"

if ($Open) {
    Start-Process $Dashboard | Out-Null
}
