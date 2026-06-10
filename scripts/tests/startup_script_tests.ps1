$ErrorActionPreference = 'Stop'

. (Join-Path (Split-Path -Parent $PSScriptRoot) 'common.ps1')

function Assert-Equal {
    param(
        [string]$Expected,
        [string]$Actual,
        [string]$Message
    )

    if ($Expected -ne $Actual) {
        throw "$Message`nExpected: $Expected`nActual:   $Actual"
    }
}

$expectedMcpPython = Join-Path (Get-McpRoot) '.venv/Scripts/python.exe'
$expectedServerScript = Join-Path (Get-McpRoot) 'server.py'
$expectedRuntimeRoot = Get-LocalNtfsRuntimeRoot

Assert-Equal $expectedMcpPython (Get-McpPython) 'MCP Python path should use the repo-local virtualenv.'
Assert-Equal $expectedServerScript (Get-McpServerScript) 'MCP server entry should use the repo-local server.py.'

$frontendRoot = Get-FrontendLocalRoot
if ($frontendRoot -notlike "$expectedRuntimeRoot*") {
    throw "Frontend runtime root should stay inside the NTFS runtime directory, but got '$frontendRoot'."
}

$frontendNext = Get-FrontendNextScript
if (-not $frontendNext -or $frontendNext -notlike "$frontendRoot*") {
    throw "Frontend next entry should resolve inside the project-local frontend runtime, but got '$frontendNext'."
}

if (-not (Test-Path $frontendNext)) {
    throw "Frontend next entry should point to an existing executable, but got '$frontendNext'."
}

$wslScriptPath = Convert-ToWslPath (Join-Path $PSScriptRoot '..\start_fbbp_http_mcp_wsl.sh')
if ($wslScriptPath -notlike '/mnt/*') {
    throw "WSL path conversion should return a /mnt/... path, but got '$wslScriptPath'."
}

$deerflowConfig = Get-Content -Raw (Get-DeerflowConfigPath)
if ($deerflowConfig -match '\.codex/memories|C:/Users/Administrator') {
    throw 'DeerFlow config should not reference user-profile skills paths.'
}

$wslLauncher = Get-Content -Raw (Join-Path $PSScriptRoot '..\start_fbbp_http_mcp_wsl.sh')
if ($wslLauncher -match '\.codex/memories|ragkb_proj|deerflow_frontend_local2') {
    throw 'WSL MCP launcher should not reference external memory directories.'
}

if ($wslLauncher -match 'local_hash|extractive') {
    throw 'WSL MCP launcher should not force fallback local_hash/extractive mode.'
}

Remove-Item env:EMBEDDING_PROVIDER -ErrorAction SilentlyContinue
Remove-Item env:ANSWER_MODE -ErrorAction SilentlyContinue

Set-RagkbEnv | Out-Null

if ($env:EMBEDDING_PROVIDER -ne 'bge_m3') {
    throw "Set-RagkbEnv should use the repo real-mode EMBEDDING_PROVIDER, but got '$env:EMBEDDING_PROVIDER'."
}

if ($env:ANSWER_MODE -ne 'openai') {
    throw "Set-RagkbEnv should use the repo real-mode ANSWER_MODE, but got '$env:ANSWER_MODE'."
}

Write-Host 'startup_script_tests: PASS'
