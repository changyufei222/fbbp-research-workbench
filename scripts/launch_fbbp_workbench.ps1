param(
    [switch]$NoOpen
)

. (Join-Path $PSScriptRoot 'common.ps1')

Ensure-OpenAIKey

& (Join-Path $PSScriptRoot 'start_fullstack_local_frontend.ps1')

if (-not (Wait-TcpPort -ComputerName '127.0.0.1' -Port 3000 -TimeoutSeconds 30)) {
    throw 'Frontend port 3000 is not ready.'
}

$url = 'http://127.0.0.1:3000/workspace'

Write-Host ''
Write-Host 'DeerFlow FBBP workspace is ready:'
Write-Host "  $url"
Write-Host '  Formal results page: http://127.0.0.1:3000/fbbp'

if (-not $NoOpen) {
    Start-Process $url | Out-Null
}
