$ErrorActionPreference = 'Stop'

function Get-WorkspaceRoot {
    return (Split-Path -Parent $PSScriptRoot)
}

function Get-WorkspaceDirName {
    return (Split-Path (Get-WorkspaceRoot) -Leaf)
}

function Get-RepoRoot {
    return (Split-Path -Parent (Get-WorkspaceRoot))
}

function Get-WslAsciiProxyRoot {
    $repoRoot = Get-RepoRoot
    $candidates = @('P:', 'R:', 'S:', 'T:')
    $substOutput = @(cmd /c subst)

    foreach ($drive in $candidates) {
        $driveRoot = "${drive}\"
        $workspaceName = Get-WorkspaceDirName
        $probePath = "${driveRoot}${workspaceName}\scripts\start_fbbp_http_mcp_wsl.sh"
        if (Test-Path $probePath) {
            return $driveRoot
        }

        $mappedLine = $substOutput | Where-Object { $_.StartsWith("${drive}\") } | Select-Object -First 1
        if ($mappedLine) {
            continue
        }

        if (Test-Path $driveRoot) {
            continue
        }

        cmd /c "subst $drive `"$repoRoot`"" | Out-Null
        if (Test-Path $probePath) {
            return $driveRoot
        }
    }

    throw 'Could not allocate an ASCII SUBST drive for WSL access.'
}

function Get-DeerflowRoot {
    return (Join-Path (Get-RepoRoot) 'upstream-deerflow')
}

function Get-RagkbRoot {
    return (Join-Path (Get-RepoRoot) 'llm-rag-knowledge-base')
}

function Get-McpRoot {
    $repoRoot = Get-RepoRoot
    foreach ($candidate in @('fbbp-mcp-rag-server', 'fbtp-mcp-rag-server')) {
        $path = Join-Path $repoRoot $candidate
        if (Test-Path $path) {
            return $path
        }
    }
    return (Join-Path $repoRoot 'fbtp-mcp-rag-server')
}

function Get-RuntimeRoot {
    $dir = Join-Path (Get-WorkspaceRoot) 'runtime'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return $dir
}

function Get-LocalNtfsRuntimeRoot {
    $candidates = @()

    if ($env:LOCALAPPDATA) {
        $candidates += (Join-Path $env:LOCALAPPDATA 'fbbp-research-workbench\runtime')
        $candidates += (Join-Path $env:LOCALAPPDATA 'deerflow-fbtp-research-agent\runtime')
    }

    if ($env:USERPROFILE) {
        $candidates += (Join-Path $env:USERPROFILE 'AppData\Local\fbbp-research-workbench\runtime')
        $candidates += (Join-Path $env:USERPROFILE 'AppData\Local\deerflow-fbtp-research-agent\runtime')
    }

    $candidates += '<local_path_removed>
    $candidates += '<local_path_removed>

    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        $driveRoot = [System.IO.Path]::GetPathRoot($candidate)
        if (-not $driveRoot) {
            continue
        }

        $driveLetter = $driveRoot.Substring(0, 1)
        $volume = Get-Volume -DriveLetter $driveLetter -ErrorAction SilentlyContinue
        if (-not $volume) {
            continue
        }

        if ($volume.FileSystem -eq 'exFAT') {
            continue
        }

        New-Item -ItemType Directory -Force -Path $candidate | Out-Null
        return $candidate
    }

    return (Get-RuntimeRoot)
}

function Get-McpPython {
    return (Join-Path (Get-McpRoot) '.venv/Scripts/python.exe')
}

function Get-McpServerScript {
    return (Join-Path (Get-McpRoot) 'server.py')
}

function Get-DeerflowBackendRoot {
    return (Join-Path (Get-DeerflowRoot) 'backend')
}

function Get-FrontendLocalRoot {
    $dir = Join-Path (Get-LocalNtfsRuntimeRoot) 'frontend_local'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return $dir
}

function Get-WslRuntimeRoot {
    $dir = Join-Path (Get-RuntimeRoot) 'wsl'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return $dir
}

function Get-FrontendNextScript {
    $frontendRoot = Get-FrontendLocalRoot
    $candidates = @(
        (Join-Path $frontendRoot 'node_modules\next\dist\bin\next'),
        (Join-Path $frontendRoot 'node_modules\.bin\next')
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    $pnpmNext = Get-ChildItem -Path (Join-Path $frontendRoot 'node_modules\.pnpm') `
        -Filter 'next@*' `
        -Directory `
        -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending |
        Select-Object -First 1

    if ($pnpmNext) {
        $nested = Join-Path $pnpmNext.FullName 'node_modules\next\dist\bin\next'
        if (Test-Path $nested) {
            return $nested
        }
    }

    return (Join-Path $frontendRoot 'node_modules\next\dist\bin\next')
}

function Stop-FrontendLocalProcess {
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -eq 'node.exe' -and (
                $_.CommandLine -like '*frontend_local*next dev*' -or
                $_.CommandLine -like '*frontend_local*node_modules\next\dist\bin\next*'
            )
        } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

function Get-DeerflowBackendPython {
    return (Join-Path (Get-DeerflowBackendRoot) '.venv/Scripts/python.exe')
}

function Get-DeerflowLanggraphExe {
    return (Join-Path (Get-DeerflowBackendRoot) '.venv/Scripts/langgraph.exe')
}

function Get-DeerflowUvicornExe {
    return (Join-Path (Get-DeerflowBackendRoot) '.venv/Scripts/uvicorn.exe')
}

function Get-RagkbPython {
    return (Get-McpPython)
}

function Get-DeerflowGeneratedRoot {
    $dir = Join-Path (Get-WorkspaceRoot) 'generated'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return $dir
}

function Get-DefaultFbbpAgentName {
    return 'fbbp-assistant'
}

function Get-DeerflowHomeRoot {
    $dir = Join-Path (Get-LocalNtfsRuntimeRoot) 'deerflow_home'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return $dir
}

function Sync-DefaultFbbpAgent {
    param(
        [string]$DestinationRoot = (Get-DeerflowHomeRoot)
    )

    $agentName = Get-DefaultFbbpAgentName
    $sourceRoot = Join-Path (Get-WorkspaceRoot) "configs\agents\$agentName"
    $targetRoot = Join-Path $DestinationRoot "agents\$agentName"

    if (-not (Test-Path $sourceRoot)) {
        throw "Default FBBP agent source was not found: $sourceRoot"
    }

    New-Item -ItemType Directory -Force -Path $targetRoot | Out-Null

    foreach ($name in @('config.yaml', 'SOUL.md', 'memory.json')) {
        $sourceFile = Join-Path $sourceRoot $name
        if (-not (Test-Path $sourceFile)) {
            throw "Default FBBP agent file is missing: $sourceFile"
        }
        Copy-Item $sourceFile (Join-Path $targetRoot $name) -Force
    }

    return
}

function Get-FormalRunsRoot {
    $dir = Join-Path (Get-WorkspaceRoot) 'runs'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return $dir
}

function Get-FormalBatchesRoot {
    $dir = Join-Path (Get-WorkspaceRoot) 'batches'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return $dir
}

function Get-FormalCaseConfigsRoot {
    $dir = Join-Path (Get-WorkspaceRoot) 'configs\formal_cases'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return $dir
}

function Get-FormalBatchConfigsRoot {
    $dir = Join-Path (Get-WorkspaceRoot) 'configs\formal_batches'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return $dir
}

function Get-RuntimeProfilesRoot {
    $dir = Join-Path (Get-WorkspaceRoot) 'configs\runtime_profiles'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return $dir
}

function Get-FormalCaseConfigPath {
    param([string]$CaseId)

    return (Join-Path (Get-FormalCaseConfigsRoot) "$CaseId.yaml")
}

function Get-FormalBatchConfigPath {
    param([string]$BatchSlug)

    return (Join-Path (Get-FormalBatchConfigsRoot) "$BatchSlug.yaml")
}

function Get-DeerflowConfigPath {
    return (Join-Path (Get-DeerflowGeneratedRoot) 'fbbp.config.yaml')
}

function Get-DeerflowExtensionsPath {
    return (Join-Path (Get-DeerflowGeneratedRoot) 'extensions_config.fbbp.json')
}

function Get-FbbpMcpHttpUrl {
    Ensure-DeerflowRuntimeConfig

    $extensionsPath = Get-DeerflowExtensionsPath
    $payload = Get-Content $extensionsPath -Raw | ConvertFrom-Json
    $url = $null
    foreach ($serverName in @('fbbp-rag', 'fbtp-rag')) {
        if ($payload.mcpServers.PSObject.Properties.Name -contains $serverName) {
            $url = $payload.mcpServers.$serverName.url
            if ($url) { break }
        }
    }
    if (-not $url) {
        throw "Could not resolve FBBP MCP URL from $extensionsPath"
    }
    return $url
}

function Get-FbtpMcpHttpUrl {
    return (Get-FbbpMcpHttpUrl)
}

function Ensure-DeerflowRuntimeConfig {
    $configPath = Get-DeerflowConfigPath
    $extensionsPath = Get-DeerflowExtensionsPath

    if ((Test-Path $configPath) -and (Test-Path $extensionsPath)) {
        Sync-DefaultFbbpAgent | Out-Null
        return
    }

    $prepareScript = Join-Path (Get-WorkspaceRoot) 'scripts\prepare_deerflow_config.ps1'
    & $prepareScript -OutputPath $configPath -ExtensionsOutputPath $extensionsPath -Quiet | Out-Null
    Sync-DefaultFbbpAgent | Out-Null
}

function Get-ReportsDir {
    $dir = Join-Path (Get-WorkspaceRoot) 'reports'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return $dir
}

function Get-ArtifactsRoot {
    $dir = Join-Path (Get-WorkspaceRoot) 'artifacts'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return $dir
}

function Get-FinalResultsRoot {
    $dir = Join-Path (Get-WorkspaceRoot) 'final_results'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return $dir
}

function Convert-ToWslPath {
    param([string]$Path)

    $resolved = (Resolve-Path $Path).Path
    if ($resolved -match '^(?<drive>[A-Za-z]):\\(?<rest>.*)$') {
        $drive = $Matches['drive'].ToLowerInvariant()
        $rest = ($Matches['rest'] -replace '\\', '/')
        return "/mnt/$drive/$rest"
    }

    throw "Could not convert path to WSL path: $resolved"
}

function Write-Step([string]$Message) {
    Write-Host "==> $Message"
}

function Stop-ProcessesByPort {
    param([int[]]$Ports)

    foreach ($port in $Ports) {
        Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
            Where-Object { $_.LocalPort -eq $port } |
            Select-Object -ExpandProperty OwningProcess -Unique |
            ForEach-Object {
                try {
                    Stop-Process -Id $_ -Force -ErrorAction Stop
                    Write-Host "Stopped process on port $port (PID=$_ )"
                } catch {
                }
            }
    }
}

function Get-PreferredBrowserPath {
    $candidates = @(
        '<local_path_removed>,
        '<local_path_removed>,
        '<local_path_removed>,
        '<local_path_removed>
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }
    return $null
}

function Invoke-HeadlessScreenshot {
    param(
        [string]$Url,
        [string]$OutputPath,
        [int]$Width = 1440,
        [int]$Height = 1200
    )

    $browser = Get-PreferredBrowserPath
    if (-not $browser) {
        return $false
    }

    $outDir = Split-Path -Parent $OutputPath
    if ($outDir) {
        New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    }

    Start-Process -FilePath $browser `
        -ArgumentList '--headless=new', "--window-size=${Width},${Height}", '--disable-gpu', '--hide-scrollbars', "--screenshot=$OutputPath", $Url `
        -Wait -NoNewWindow | Out-Null

    return (Test-Path $OutputPath)
}

function Save-TextFile {
    param(
        [string]$Path,
        [string]$Content
    )

    $dir = Split-Path -Parent $Path
    if ($dir) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

function Test-PythonUsable {
    param([string]$PythonPath)

    if (-not (Test-Path $PythonPath)) {
        return $false
    }

    try {
        & $PythonPath -c "import sys; print(sys.executable)" *> $null
    } catch {
        return $false
    }

    return $LASTEXITCODE -eq 0
}

function Import-EnvFile {
    param(
        [string]$Path,
        [string[]]$Keys,
        [switch]$OnlyIfUnset
    )

    if (-not (Test-Path $Path)) {
        return
    }

    foreach ($line in Get-Content $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#') -or -not $trimmed.Contains('=')) {
            continue
        }

        $parts = $trimmed.Split('=', 2)
        $key = $parts[0].Trim()
        if ($Keys -and $key -notin $Keys) {
            continue
        }

        $value = $parts[1].Trim()
        if (
            ($value.StartsWith("'") -and $value.EndsWith("'")) -or
            ($value.StartsWith('"') -and $value.EndsWith('"'))
        ) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        if ($OnlyIfUnset) {
            $existingValue = [Environment]::GetEnvironmentVariable($key, 'Process')
            if ($null -ne $existingValue -and "$existingValue".Length -gt 0) {
                continue
            }
        }

        Set-Item -Path "env:$key" -Value $value
    }
}

function Ensure-OpenAIKey {
    if (-not $env:OPENAI_API_KEY) {
        $userKey = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'User')
        if ($userKey) {
            $env:OPENAI_API_KEY = $userKey
        }
    }

    if (-not $env:OPENAI_API_KEY) {
        $inputKey = Read-Host 'Please paste your OPENAI_API_KEY'
        if ($inputKey) {
            $env:OPENAI_API_KEY = $inputKey.Trim()
        }
    }

    if (-not $env:OPENAI_API_KEY) {
        throw 'OPENAI_API_KEY is not set.'
    }
}

function Get-WslPrimaryIp {
    $raw = (wsl hostname -I).Trim()
    if (-not $raw) {
        throw 'Could not determine WSL IP.'
    }
    return ($raw -split '\s+')[0]
}

function Wait-TcpPort {
    param(
        [string]$ComputerName,
        [int]$Port,
        [int]$TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $result = Test-NetConnection -ComputerName $ComputerName -Port $Port -WarningAction SilentlyContinue
        if ($result.TcpTestSucceeded) {
            return $true
        }
        Start-Sleep -Seconds 2
    }
    return $false
}

function Get-PostgresProbePython {
    $candidates = @(
        (Get-McpPython),
        (Get-DeerflowBackendPython),
        'python'
    )

    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if ($candidate -eq 'python') {
            return $candidate
        }
        if (Test-PythonUsable $candidate) {
            return $candidate
        }
    }

    return 'python'
}

function Test-PostgresQueryReady {
    param(
        [string]$ProbeHost = 'localhost',
        [int]$Port = 5432,
        [string]$Database = 'ragkb',
        [string]$User = 'ragkb',
        [string]$Password = 'ragkb',
        [int]$TimeoutSeconds = 5
    )

    $python = Get-PostgresProbePython
    $probeScript = @"
import json
import sys

try:
    import psycopg
except Exception:
    print(json.dumps({"ok": False, "error": "psycopg unavailable"}))
    raise SystemExit(0)

payload = {"ok": False}
try:
    with psycopg.connect(
        host=r"$ProbeHost",
        port=$Port,
        dbname=r"$Database",
        user=r"$User",
        password=r"$Password",
        connect_timeout=$TimeoutSeconds,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            payload["ok"] = cur.fetchone()[0] == 1
except Exception as exc:
    payload["error"] = str(exc)

print(json.dumps(payload, ensure_ascii=False))
"@

    try {
        $raw = $probeScript | & $python -
        if ($LASTEXITCODE -ne 0) {
            return $false
        }
        $payload = $raw | ConvertFrom-Json
        return [bool]$payload.ok
    } catch {
        return $false
    }
}

function Remove-LocalPostgresPortProxy {
    param([int]$Port = 5432)

    foreach ($listenAddress in @('127.0.0.1', '0.0.0.0')) {
        try {
            netsh interface portproxy delete v4tov4 listenaddress=$listenAddress listenport=$Port | Out-Null
        } catch {
        }
    }
}

function Ensure-LocalFormalPostgresReady {
    param(
        [int]$Port = 5432,
        [string]$Database = 'ragkb',
        [string]$User = 'ragkb',
        [string]$Password = 'ragkb'
    )

    Set-RagkbEnv | Out-Null

    if (Test-PostgresQueryReady -ProbeHost $env:PGHOST -Port $Port -Database $Database -User $User -Password $Password) {
        return $env:PGHOST
    }

    Remove-LocalPostgresPortProxy -Port $Port

    $wslCommands = @'
set -euo pipefail
if ! command -v pg_ctlcluster >/dev/null 2>&1; then
  echo "PostgreSQL 16 is not installed in WSL."
  exit 1
fi
pg_ctlcluster 16 main start
if ! runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='ragkb'" | grep -q 1; then
  runuser -u postgres -- psql -c "CREATE ROLE ragkb LOGIN PASSWORD 'ragkb';"
fi
if ! runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_database WHERE datname='ragkb'" | grep -q 1; then
  runuser -u postgres -- createdb -O ragkb ragkb
fi
runuser -u postgres -- psql -d ragkb -c "CREATE EXTENSION IF NOT EXISTS vector;"
pg_isready -h 127.0.0.1 -p 5432
'@

    $tempScript = Join-Path ([System.IO.Path]::GetTempPath()) 'deerflow_fbbp_pg_ready.sh'
    Save-TextFile -Path $tempScript -Content ($wslCommands -replace "`r`n", "`n")
    $wslScriptPath = Convert-ToWslPath $tempScript
    try {
        & wsl -u root bash $wslScriptPath
    } finally {
        Remove-Item $tempScript -ErrorAction SilentlyContinue
    }

    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        if (Test-PostgresQueryReady -ProbeHost $env:PGHOST -Port $Port -Database $Database -User $User -Password $Password) {
            return $env:PGHOST
        }
        Start-Sleep -Seconds 2
    }

    throw "PostgreSQL is still not query-ready at ${env:PGHOST}:$Port after WSL startup."
}

function Get-DeerflowRuntimeEnv {
    Ensure-DeerflowRuntimeConfig

    $keysToImport = @(
        'OPENAI_API_KEY',
        'BASE_URL',
        'OPENAI_BASE_URL',
        'OPENAI_API_BASE',
        'LLM_MODEL'
    )

    foreach ($envPath in @((Join-Path (Get-RagkbRoot) '.env'), (Join-Path (Get-McpRoot) '.env'))) {
        Import-EnvFile -Path $envPath -Keys $keysToImport -OnlyIfUnset
    }

    $resolvedOpenAIBaseUrl = $env:OPENAI_BASE_URL
    if (-not $resolvedOpenAIBaseUrl) {
        if ($env:OPENAI_API_BASE) {
            $resolvedOpenAIBaseUrl = $env:OPENAI_API_BASE
        } elseif ($env:BASE_URL) {
            $resolvedOpenAIBaseUrl = $env:BASE_URL
        }
    }
    if ($resolvedOpenAIBaseUrl) {
        $env:OPENAI_BASE_URL = $resolvedOpenAIBaseUrl
        $env:OPENAI_API_BASE = $resolvedOpenAIBaseUrl
        $env:BASE_URL = $resolvedOpenAIBaseUrl
    }

    $formalDatasetVersion = $env:FBBP_FORMAL_DATASET_VERSION
    if (-not $formalDatasetVersion) {
        $formalDatasetVersion = $env:FBTP_FORMAL_DATASET_VERSION
    }
    if (-not $formalDatasetVersion) {
        $datasetConfig = Get-ChildItem -Path (Join-Path (Get-McpRoot) 'configs\datasets') -Filter 'fbbp_*.json' -File -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending |
            Select-Object -First 1
        if ($datasetConfig) {
            $formalDatasetVersion = [System.IO.Path]::GetFileNameWithoutExtension($datasetConfig.Name)
        }
    }
    if (-not $formalDatasetVersion) {
        $formalDatasetVersion = 'fbbp_private_v2026_04'
    }

    $formalRuntimeProfile = $env:FBBP_FORMAL_RUNTIME_PROFILE
    if (-not $formalRuntimeProfile) {
        $formalRuntimeProfile = $env:FBTP_FORMAL_RUNTIME_PROFILE
    }
    if (-not $formalRuntimeProfile) {
        $formalRuntimeProfile = 'local_formal'
    }

    return @{
        'OPENAI_API_KEY' = $env:OPENAI_API_KEY
        'OPENAI_BASE_URL' = $env:OPENAI_BASE_URL
        'BASE_URL' = $env:BASE_URL
        'OPENAI_API_BASE' = $env:OPENAI_API_BASE
        'LLM_MODEL' = $env:LLM_MODEL
        'DEER_FLOW_HOME' = (Get-DeerflowHomeRoot)
        'DEER_FLOW_CONFIG_PATH' = (Get-DeerflowConfigPath)
        'DEER_FLOW_EXTENSIONS_CONFIG_PATH' = (Get-DeerflowExtensionsPath)
        'FBBP_PROJECT_ROOT' = (Get-RepoRoot)
        'FBTP_PROJECT_ROOT' = (Get-RepoRoot)
        'FBBP_MCP_HTTP_URL' = (Get-FbbpMcpHttpUrl)
        'FBTP_MCP_HTTP_URL' = (Get-FbbpMcpHttpUrl)
        'FBBP_FORMAL_DATASET_VERSION' = $formalDatasetVersion
        'FBTP_FORMAL_DATASET_VERSION' = $formalDatasetVersion
        'FBBP_FORMAL_RUNTIME_PROFILE' = $formalRuntimeProfile
        'FBTP_FORMAL_RUNTIME_PROFILE' = $formalRuntimeProfile
    }
}

function Set-RagkbEnv {
    $keysToImport = @(
        'PGPORT',
        'PGDATABASE',
        'PGUSER',
        'PGPASSWORD',
        'PGTABLE',
        'LLM_PROVIDER',
        'LLM_MODEL',
        'ANSWER_MODE',
        'EVIDENCE_MODE',
        'MIN_SCORE',
        'EMBEDDING_PROVIDER',
        'EMBEDDING_MODEL',
        'EMBEDDING_DIM',
        'BGE_M3_USE_FP16',
        'BGE_M3_BATCH_SIZE',
        'BGE_M3_MAX_LENGTH',
        'OPENAI_API_KEY',
        'BASE_URL',
        'OPENAI_BASE_URL',
        'OPENAI_API_BASE'
    )

    foreach ($envPath in @((Join-Path (Get-RagkbRoot) '.env'), (Join-Path (Get-McpRoot) '.env'))) {
        Import-EnvFile -Path $envPath -Keys $keysToImport -OnlyIfUnset
    }

    $resolvedOpenAIBaseUrl = $env:OPENAI_BASE_URL
    if (-not $resolvedOpenAIBaseUrl) {
        if ($env:OPENAI_API_BASE) {
            $resolvedOpenAIBaseUrl = $env:OPENAI_API_BASE
        } elseif ($env:BASE_URL) {
            $resolvedOpenAIBaseUrl = $env:BASE_URL
        }
    }
    if ($resolvedOpenAIBaseUrl) {
        $env:OPENAI_BASE_URL = $resolvedOpenAIBaseUrl
        $env:OPENAI_API_BASE = $resolvedOpenAIBaseUrl
        $env:BASE_URL = $resolvedOpenAIBaseUrl
    }

    $env:PGHOST = 'localhost'
    if (-not $env:PGPORT) { $env:PGPORT = '5432' }
    if (-not $env:PGDATABASE) { $env:PGDATABASE = 'ragkb' }
    if (-not $env:PGUSER) { $env:PGUSER = 'ragkb' }
    if (-not $env:PGPASSWORD) { $env:PGPASSWORD = 'ragkb' }
    if (-not $env:PGTABLE) { $env:PGTABLE = 'rag_documents_bge_m3' }
    $env:PGCONNECT_TIMEOUT = '5'
    return $env:PGHOST
}
