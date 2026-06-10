param(
    [string]$CasePath,
    [string]$CaseId,
    [string]$OutputRoot,
    [switch]$SkipHandshake,
    [switch]$SkipStackStart,
    [string]$Now,
    [string]$RawResultJson
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

if (-not $SkipStackStart -and -not $RawResultJson) {
    Ensure-OpenAIKey
    & (Join-Path $PSScriptRoot 'start_stack_core.ps1') | Out-Null
}

$deerflowRuntimeEnv = Get-DeerflowRuntimeEnv
foreach ($entry in $deerflowRuntimeEnv.GetEnumerator()) {
    if ($null -ne $entry.Value -and "$($entry.Value)".Length -gt 0) {
        Set-Item -Path "env:$($entry.Key)" -Value $entry.Value
    }
}

$prepareArgs = @(
    '-NoProfile',
    '-ExecutionPolicy', 'Bypass',
    '-File', (Join-Path $PSScriptRoot 'prepare_fbbp_formal_case.ps1'),
    '-CasePath', $resolvedCasePath
)
if ($OutputRoot) {
    $prepareArgs += @('-OutputRoot', $OutputRoot)
}
if ($SkipHandshake) {
    $prepareArgs += '-SkipHandshake'
}
if ($Now) {
    $prepareArgs += @('-Now', $Now)
}

$preparedJson = & powershell @prepareArgs
if ($LASTEXITCODE -ne 0) {
    throw ($preparedJson | Out-String)
}
$prepared = $preparedJson | ConvertFrom-Json

$runArgs = @(
    (Join-Path $PSScriptRoot 'run_fbbp_formal_case.py'),
    '--case-path', $resolvedCasePath,
    '--run-dir', $prepared.run_dir
)
if ($RawResultJson) {
    $runArgs += @('--raw-result-json', (Resolve-Path $RawResultJson).Path)
}
if ($Now) {
    $runArgs += @('--now', $Now)
}

$result = & python @runArgs
if ($LASTEXITCODE -ne 0) {
    throw ($result | Out-String)
}

$result
