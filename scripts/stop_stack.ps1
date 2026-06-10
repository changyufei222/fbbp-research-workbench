param(
    [switch]$KeepPostgres
)

. (Join-Path $PSScriptRoot 'common.ps1')

Write-Step 'Stopping Windows-side DeerFlow services'
Stop-ProcessesByPort -Ports @(2024, 8001, 8000, 3000)

Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -eq 'node.exe' -and (
            $_.CommandLine -like '*frontend_local*' -or
            $_.CommandLine -like '*next dev*'
        )
    } |
    ForEach-Object {
        try {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop
            Write-Host "Stopped frontend node process PID=$($_.ProcessId)"
        } catch {
        }
    }

Write-Step 'Stopping WSL-side MCP / nginx / optional PostgreSQL'

wsl bash -lc "pkill -f 'fbbp_mcp_server.server --transport streamable-http' || true; pkill -f 'fbtp_mcp_server.server --transport streamable-http' || true"
wsl bash -lc "nginx -s quit 2>/dev/null || true"

if (-not $KeepPostgres) {
    wsl -u root bash -lc "pg_ctlcluster 16 main stop || true"
    Write-Host 'Stopped PostgreSQL cluster in WSL.'
} else {
    Write-Host 'Keeping PostgreSQL cluster running.'
}

Write-Host ''
Write-Host 'Stop sequence finished.'
