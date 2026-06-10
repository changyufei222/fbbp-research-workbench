param(
    [string]$BatchPath,
    [string]$BatchSlug,
    [string]$OutputRoot,
    [switch]$SkipStackStart,
    [string]$Now,
    [string]$RawResultDir
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')

if (-not $BatchPath) {
    if (-not $BatchSlug) {
        throw 'Either -BatchPath or -BatchSlug is required.'
    }
    $BatchPath = Get-FormalBatchConfigPath -BatchSlug $BatchSlug
}

$resolvedBatchPath = (Resolve-Path $BatchPath).Path
$batchMetaScript = @"
import json
import sys
from pathlib import Path
sys.path.insert(0, r'$PSScriptRoot')
import formal_run_lib
batch_config = formal_run_lib.load_yaml_config(Path(r'$resolvedBatchPath'))
print(json.dumps({
    'dataset_version': batch_config['dataset_version'],
    'runtime_profile': batch_config['runtime_profile'],
}, ensure_ascii=False))
"@
$batchMeta = (& python -c $batchMetaScript) | ConvertFrom-Json
$env:FBBP_FORMAL_DATASET_VERSION = $batchMeta.dataset_version
$env:FBBP_FORMAL_RUNTIME_PROFILE = $batchMeta.runtime_profile
$env:FBTP_FORMAL_DATASET_VERSION = $batchMeta.dataset_version
$env:FBTP_FORMAL_RUNTIME_PROFILE = $batchMeta.runtime_profile

if (-not $SkipStackStart -and -not $RawResultDir) {
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
    '-File', (Join-Path $PSScriptRoot 'prepare_fbbp_formal_batch.ps1'),
    '-BatchPath', $resolvedBatchPath
)
if ($OutputRoot) {
    $prepareArgs += @('-OutputRoot', $OutputRoot)
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
    (Join-Path $PSScriptRoot 'run_fbbp_formal_batch.py'),
    '--batch-path', $resolvedBatchPath,
    '--batch-dir', $prepared.batch_dir
)
if ($RawResultDir) {
    $runArgs += @('--raw-result-dir', (Resolve-Path $RawResultDir).Path)
}
if ($Now) {
    $runArgs += @('--now', $Now)
}

$result = & python @runArgs
if ($LASTEXITCODE -ne 0) {
    throw ($result | Out-String)
}

$result
