. (Join-Path $PSScriptRoot 'common.ps1')

Ensure-OpenAIKey

& (Join-Path $PSScriptRoot 'start_stack_core.ps1')
& (Join-Path $PSScriptRoot 'start_frontend_local.ps1')

Write-Host ''
Write-Host 'Full stack (stable mode) is ready:'
Write-Host '  App:       http://127.0.0.1:3000'
Write-Host '  Gateway:   http://127.0.0.1:8001/health'
Write-Host '  LangGraph: http://127.0.0.1:2024/docs'
Write-Host '  MCP:       http://127.0.0.1:8000/mcp or the WSL IP equivalent'

