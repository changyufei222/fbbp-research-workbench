param(
    [string]$BatchPath,
    [string]$BatchSlug,
    [string]$OutputRoot,
    [string]$Now
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
$batchRoot = if ($OutputRoot) {
    [System.IO.Path]::GetFullPath($OutputRoot)
} else {
    Get-FormalBatchesRoot
}

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

$batchIdScript = @"
import sys
from pathlib import Path
sys.path.insert(0, r'$PSScriptRoot')
import formal_run_lib
batch_config = formal_run_lib.load_yaml_config(Path(r'$resolvedBatchPath'))
now = formal_run_lib.datetime.fromisoformat(r'$Now') if r'$Now' else formal_run_lib.datetime.now()
print(formal_run_lib.build_batch_id(batch_config['batch_slug'], now))
"@
$batchId = (& python -c $batchIdScript).Trim()
if (-not $batchId) {
    throw 'Failed to derive batch id.'
}

$args = @(
    (Join-Path $PSScriptRoot 'run_fbbp_formal_batch.py'),
    '--batch-path', $resolvedBatchPath,
    '--batch-dir', (Join-Path $batchRoot $batchId),
    '--prepare-only'
)
if ($Now) {
    $args += @('--now', $Now)
}

$payload = & python @args
if ($LASTEXITCODE -ne 0) {
    throw ($payload | Out-String)
}

$payload
