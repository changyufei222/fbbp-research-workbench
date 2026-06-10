. (Join-Path $PSScriptRoot 'common.ps1')

Write-Step 'Starting WSL PostgreSQL + pgvector'
Remove-LocalPostgresPortProxy -Port 5432
$readyHost = Ensure-LocalFormalPostgresReady -Port 5432 -Database 'ragkb' -User 'ragkb' -Password 'ragkb'

Write-Host "WSL PostgreSQL is ready."
Write-Host "Windows can query PostgreSQL at ${readyHost}:5432"

try {
    $wslIp = Get-WslPrimaryIp
    Write-Host "Current WSL IP: $wslIp"
} catch {
}
