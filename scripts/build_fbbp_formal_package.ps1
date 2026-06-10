param(
    [string]$OutputRoot,
    [string]$Now
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')

$scriptPath = Join-Path $PSScriptRoot 'build_fbbp_formal_package.py'
$args = @($scriptPath)

if ($OutputRoot) {
    $args += @('--output-root', $OutputRoot)
} else {
    $args += @('--output-root', (Join-Path (Get-FinalResultsRoot) 'fbbp_formal_atlas_v2026_04'))
}

if ($Now) {
    $args += @('--now', $Now)
}

& python @args
