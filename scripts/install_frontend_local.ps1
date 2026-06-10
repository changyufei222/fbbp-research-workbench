. (Join-Path $PSScriptRoot 'common.ps1')

& (Join-Path $PSScriptRoot 'sync_frontend_local.ps1')

$frontend = Get-FrontendLocalRoot

Write-Step 'Installing frontend dependencies in project-local frontend runtime'
Push-Location $frontend
try {
    pnpm install --reporter append-only
} finally {
    Pop-Location
}

if (-not (Test-Path (Get-FrontendNextScript))) {
    throw 'Frontend install completed but next executable is still missing.'
}

Write-Host 'Frontend dependencies are ready.'
