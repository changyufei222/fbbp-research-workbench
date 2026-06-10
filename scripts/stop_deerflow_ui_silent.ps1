. (Join-Path $PSScriptRoot 'common.ps1')

$logsRoot = Join-Path (Get-RuntimeRoot) 'ui'
New-Item -ItemType Directory -Force -Path $logsRoot | Out-Null
$transcriptPath = Join-Path $logsRoot 'stop_deerflow_ui_silent.log'

Start-Transcript -Path $transcriptPath -Append | Out-Null
try {
    & (Join-Path $PSScriptRoot 'stop_stack.ps1')

    Write-Host ''
    Write-Host 'Silent DeerFlow UI stop is complete.'
    Write-Host "  Log: $transcriptPath"
} finally {
    Stop-Transcript | Out-Null
}
