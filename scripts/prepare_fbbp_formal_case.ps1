param(
    [string]$CasePath,
    [string]$CaseId,
    [string]$OutputRoot,
    [switch]$SkipHandshake,
    [string]$Now
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')

if (-not $CasePath) {
    if (-not $CaseId) {
        throw 'Either -CasePath or -CaseId is required.'
    }
    $CasePath = Get-FormalCaseConfigPath -CaseId $CaseId
}

$resolvedCasePath = (Resolve-Path $CasePath).Path
$runRoot = if ($OutputRoot) {
    [System.IO.Path]::GetFullPath($OutputRoot)
} else {
    Get-FormalRunsRoot
}

$caseMetaScript = @"
import json
import sys
from pathlib import Path
sys.path.insert(0, r'$PSScriptRoot')
import formal_run_lib
case_config = formal_run_lib.load_yaml_config(Path(r'$resolvedCasePath'))
print(json.dumps({
    'dataset_version': case_config['dataset_version'],
    'runtime_profile': case_config['runtime_profile'],
}, ensure_ascii=False))
"@
$caseMeta = (& python -c $caseMetaScript) | ConvertFrom-Json
$env:FBBP_FORMAL_DATASET_VERSION = $caseMeta.dataset_version
$env:FBBP_FORMAL_RUNTIME_PROFILE = $caseMeta.runtime_profile
$env:FBTP_FORMAL_DATASET_VERSION = $caseMeta.dataset_version
$env:FBTP_FORMAL_RUNTIME_PROFILE = $caseMeta.runtime_profile

$pythonArgs = @(
    (Join-Path $PSScriptRoot 'run_fbbp_formal_case.py'),
    '--case-path', $resolvedCasePath,
    '--run-dir', (Join-Path $runRoot ([System.IO.Path]::GetFileNameWithoutExtension($resolvedCasePath))),
    '--prepare-only'
)
if ($Now) {
    $pythonArgs += @('--now', $Now)
}

$prepareProbe = @"
import json
import sys
from pathlib import Path
sys.path.insert(0, r'$PSScriptRoot')
import formal_run_lib
case_path = Path(r'$resolvedCasePath')
case_config = formal_run_lib.load_yaml_config(case_path)
now = formal_run_lib.datetime.fromisoformat(r'$Now') if r'$Now' else formal_run_lib.datetime.now()
run_id = formal_run_lib.build_run_id(case_config['case_id'], now)
print(run_id)
"@
$runId = (& python -c $prepareProbe).Trim()
if (-not $runId) {
    throw 'Failed to derive run id.'
}

$pythonArgs = @(
    (Join-Path $PSScriptRoot 'run_fbbp_formal_case.py'),
    '--case-path', $resolvedCasePath,
    '--run-dir', (Join-Path $runRoot $runId),
    '--prepare-only'
)
if ($Now) {
    $pythonArgs += @('--now', $Now)
}

$payload = & python @pythonArgs
if ($LASTEXITCODE -ne 0) {
    throw ($payload | Out-String)
}
$prepared = $payload | ConvertFrom-Json

if (-not $SkipHandshake) {
        $manifestPath = $prepared.manifest_path
        $mcpUrl = Get-FbbpMcpHttpUrl
        try {
            Ensure-LocalFormalPostgresReady -Port 5432 -Database 'ragkb' -User 'ragkb' -Password 'ragkb' | Out-Null
            $resolvedPgHost = Set-RagkbEnv
            if (-not (Test-PostgresQueryReady -ProbeHost $env:PGHOST -Port ([int]$env:PGPORT) -Database $env:PGDATABASE -User $env:PGUSER -Password $env:PGPASSWORD)) {
                throw "PostgreSQL is not reachable at ${resolvedPgHost}:$($env:PGPORT)"
            }

        try {
            $resp = Invoke-WebRequest -Uri $mcpUrl -Method Get -UseBasicParsing -ErrorAction Stop
            if ($resp.StatusCode -lt 200) {
                throw 'Unexpected MCP HTTP response.'
            }
        } catch {
            $statusCode = $_.Exception.Response.StatusCode.value__
            if ($statusCode -notin @(405, 406)) {
                throw
            }
        }

        $mcpRootName = Split-Path -Leaf (Get-McpRoot)
        $mcpProbeRoot = Join-Path (Get-WslAsciiProxyRoot) $mcpRootName
        $probePython = Join-Path $mcpProbeRoot '.venv\Scripts\python.exe'
        if (-not (Test-Path $probePython)) {
            $mcpProbeRoot = Get-McpRoot
            $probePython = Get-McpPython
        }

        $probeScript = @"
import json
import os
import subprocess
import time
import sys
from pathlib import Path
import psycopg
repo_root = Path(r'$mcpProbeRoot')
os.environ['PGHOST'] = r'$($env:PGHOST)'
os.environ['PGPORT'] = r'$($env:PGPORT)'
os.environ['PGDATABASE'] = r'$($env:PGDATABASE)'
os.environ['PGUSER'] = r'$($env:PGUSER)'
os.environ['PGPASSWORD'] = r'$($env:PGPASSWORD)'
os.environ['PGTABLE'] = r'$($env:PGTABLE)'
if os.name == 'nt':
    subprocess.run(['wsl', 'hostname', '-I'], capture_output=True, text=True, check=False, timeout=10)
sys.path = [str(repo_root / 'src'), str(repo_root / '.venv' / 'Lib' / 'site-packages')] + list(sys.path)
db_probe = {'ok': False, 'error': 'not_checked'}
for _ in range(3):
    try:
        conn = psycopg.connect(
            host=os.environ['PGHOST'],
            port=int(os.environ['PGPORT']),
            dbname=os.environ['PGDATABASE'],
            user=os.environ['PGUSER'],
            password=os.environ['PGPASSWORD'],
            connect_timeout=5,
        )
        cur = conn.cursor()
        cur.execute('select 1')
        db_probe = {'ok': True, 'result': cur.fetchone()[0]}
        cur.close()
        conn.close()
        break
    except Exception as exc:
        db_probe = {'ok': False, 'error': str(exc)}
        time.sleep(2)
from fbbp_mcp_server.service import tool_contract_version
payload = {
    'database': db_probe,
    'version': tool_contract_version(),
}
print(json.dumps(payload, ensure_ascii=False))
"@
        $probeDir = Join-Path $prepared.run_dir '.preflight'
        New-Item -ItemType Directory -Force -Path $probeDir | Out-Null
        $probeScriptPath = Join-Path $probeDir 'mcp_probe.py'
        Save-TextFile -Path $probeScriptPath -Content $probeScript
        $probe = $null
        for ($attempt = 1; $attempt -le 3; $attempt++) {
            $probeOutput = & $probePython $probeScriptPath
            if ($LASTEXITCODE -ne 0) {
                throw ($probeOutput | Out-String)
            }
            $probe = $probeOutput | ConvertFrom-Json
            if ($probe.database.ok) {
                break
            }
            if ($attempt -lt 3) {
                Start-Sleep -Seconds 2
            }
        }
        if (-not $probe.database.ok) {
            $dbError = $probe.database.error
            if ($dbError) {
                throw "MCP health check reported database not ready: $dbError"
            }
            throw 'MCP health check reported database not ready.'
        }
    } catch {
        $manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
        $errors = @($manifest.errors)
        $errors += [pscustomobject]@{
            stage = 'preflight'
            code = 'FORMAL_HANDSHAKE_FAILED'
            message = $_.Exception.Message
            retryable = $false
            timestamp_utc = [DateTime]::UtcNow.ToString('o')
        }
        $manifest.status = 'failed'
        $manifest.completed_at_utc = [DateTime]::UtcNow.ToString('o')
        $manifest.errors = $errors
        $manifest | ConvertTo-Json -Depth 12 | Set-Content -Path $manifestPath -Encoding utf8
        throw
    }
}

$prepared | ConvertTo-Json -Compress
