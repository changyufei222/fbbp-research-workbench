. (Join-Path $PSScriptRoot 'common.ps1')

Ensure-OpenAIKey

Write-Step 'Starting DeerFlow backend services (LangGraph + Gateway)'

$runtimeEnv = Get-DeerflowRuntimeEnv
$logsDir = Join-Path (Get-DeerflowRoot) 'logs'
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

$langOut = Join-Path $logsDir 'langgraph_win.out.log'
$langErr = Join-Path $logsDir 'langgraph_win.err.log'
$gateOut = Join-Path $logsDir 'gateway_win.out.log'
$gateErr = Join-Path $logsDir 'gateway_win.err.log'

Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -in 2024, 8001 } |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }

foreach ($kv in $runtimeEnv.GetEnumerator()) {
    Set-Item -Path "env:$($kv.Key)" -Value $kv.Value
}

Start-Process -FilePath (Get-DeerflowLanggraphExe) `
    -ArgumentList 'dev','--no-browser','--allow-blocking','--no-reload' `
    -WorkingDirectory (Get-DeerflowBackendRoot) `
    -WindowStyle 'Hidden' `
    -RedirectStandardOutput $langOut `
    -RedirectStandardError $langErr | Out-Null

Start-Process -FilePath (Get-DeerflowUvicornExe) `
    -ArgumentList 'src.gateway.app:app','--host','0.0.0.0','--port','8001' `
    -WorkingDirectory (Get-DeerflowBackendRoot) `
    -WindowStyle 'Hidden' `
    -RedirectStandardOutput $gateOut `
    -RedirectStandardError $gateErr | Out-Null

if (-not (Wait-TcpPort -ComputerName '127.0.0.1' -Port 2024 -TimeoutSeconds 90)) {
    throw "LangGraph did not start. Check $langErr"
}

if (-not (Wait-TcpPort -ComputerName '127.0.0.1' -Port 8001 -TimeoutSeconds 90)) {
    throw "Gateway did not start. Check $gateErr"
}

Write-Host 'DeerFlow backend is ready:'
Write-Host '  LangGraph: http://127.0.0.1:2024/docs'
Write-Host '  Gateway:   http://127.0.0.1:8001/health'
