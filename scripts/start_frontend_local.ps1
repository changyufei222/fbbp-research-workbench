. (Join-Path $PSScriptRoot 'common.ps1')

Stop-FrontendLocalProcess
& (Join-Path $PSScriptRoot 'sync_frontend_local.ps1')

$frontend = Get-FrontendLocalRoot
$nextScript = Get-FrontendNextScript

if (-not (Test-Path $nextScript)) {
    & (Join-Path $PSScriptRoot 'install_frontend_local.ps1')
}

Write-Step 'Starting local frontend on port 3000'

$runtimeEnv = Get-DeerflowRuntimeEnv
foreach ($entry in $runtimeEnv.GetEnumerator()) {
    if ($entry.Value) {
        Set-Item -Path "env:$($entry.Key)" -Value $entry.Value
    }
}

$env:NEXT_PUBLIC_BACKEND_BASE_URL = 'http://127.0.0.1:8001'
$env:NEXT_PUBLIC_LANGGRAPH_BASE_URL = 'http://127.0.0.1:2024'

$envFile = Join-Path $frontend '.env'
$envLocalFile = Join-Path $frontend '.env.local'
$envLines = @(
    'NEXT_PUBLIC_BACKEND_BASE_URL=http://127.0.0.1:8001',
    'NEXT_PUBLIC_LANGGRAPH_BASE_URL=http://127.0.0.1:2024'
)

foreach ($key in @('OPENAI_API_KEY', 'OPENAI_BASE_URL', 'BASE_URL', 'OPENAI_API_BASE', 'LLM_MODEL')) {
    $value = $runtimeEnv[$key]
    if ($value) {
        $envLines += "${key}=${value}"
    }
}
Remove-Item $envFile -Force -ErrorAction SilentlyContinue
[System.IO.File]::WriteAllText($envLocalFile, ($envLines -join [Environment]::NewLine) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))

$out = Join-Path $frontend 'frontend_dev.out.log'
$err = Join-Path $frontend 'frontend_dev.err.log'

Start-Process -FilePath 'node.exe' `
    -ArgumentList $nextScript,'dev','--webpack','--hostname','127.0.0.1','--port','3000' `
    -WorkingDirectory $frontend `
    -WindowStyle 'Hidden' `
    -RedirectStandardOutput $out `
    -RedirectStandardError $err | Out-Null
if (-not (Wait-TcpPort -ComputerName '127.0.0.1' -Port 3000 -TimeoutSeconds 120)) {
    throw "Frontend did not start on port 3000. Check $err"
}

Write-Host 'Frontend is ready at http://127.0.0.1:3000'
Write-Host 'This frontend is configured to call backend APIs directly on 8001 / 2024.'
