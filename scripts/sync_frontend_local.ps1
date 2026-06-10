. (Join-Path $PSScriptRoot 'common.ps1')

Write-Step 'Syncing DeerFlow frontend to local NTFS runtime workspace'

$source = Join-Path (Get-DeerflowRoot) 'frontend'
$target = Get-FrontendLocalRoot

New-Item -ItemType Directory -Force -Path $target | Out-Null

robocopy $source $target /MIR /XD node_modules .next .turbo .git /XF pnpm_install.log frontend_dev.out.log frontend_dev.err.log .env .env.local | Out-Null

Write-Host "Frontend local workspace: $target"
