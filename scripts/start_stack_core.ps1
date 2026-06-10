. (Join-Path $PSScriptRoot 'common.ps1')

& (Join-Path $PSScriptRoot 'start_wsl_pgvector.ps1')
& (Join-Path $PSScriptRoot 'start_fbbp_http_mcp.ps1')
& (Join-Path $PSScriptRoot 'start_deerflow_backend.ps1')

Write-Host ''
Write-Host 'Core stack is ready:'
Write-Host '  PostgreSQL/pgvector in WSL'
Write-Host '  FBBP HTTP MCP at http://127.0.0.1:8000/mcp'
Write-Host '  DeerFlow LangGraph at http://127.0.0.1:2024/docs'
Write-Host '  DeerFlow Gateway at http://127.0.0.1:8001/health'
