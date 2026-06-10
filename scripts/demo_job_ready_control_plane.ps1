param(
    [switch]$Fast,
    [switch]$Full,
    [switch]$SkipLive,
    [string]$OutputRoot = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$WorkspaceRoot = Resolve-Path (Join-Path $RepoRoot "..")
$TempRoot = Join-Path $WorkspaceRoot ".codex_tmp"
New-Item -ItemType Directory -Force -Path $TempRoot | Out-Null
$env:TEMP = $TempRoot
$env:TMP = $TempRoot

if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    if ($Full) {
        $OutputRoot = Join-Path $RepoRoot "runs\control_plane\readiness\job_demo_full"
    } else {
        $OutputRoot = Join-Path $RepoRoot "runs\control_plane\readiness\job_demo_fast"
    }
}

Write-Host "== FBBP Agent Control Plane job-ready demo =="
Write-Host "Repo: $RepoRoot"
Write-Host "Output: $OutputRoot"
Write-Host ""

if (-not $SkipLive) {
    $ReadinessArgs = @(
        (Join-Path $RepoRoot "scripts\control_plane\readiness_check.py"),
        "--output-root",
        $OutputRoot
    )
    if (-not $Full) {
        $ReadinessArgs += "--skip-postgres-bridge"
    }
    if ($Full) {
        $ReadinessArgs += "--include-private-rag"
        $ReadinessArgs += "--include-public-lookup"
        $ReadinessArgs += "--include-hardening"
    }

    Write-Host "== Running readiness checks =="
    & python @ReadinessArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Readiness checks failed with exit code $LASTEXITCODE"
    }
    Write-Host ""
} else {
    Write-Host "== Skipping live checks; using existing readiness evidence =="
    Write-Host ""
}

Write-Host "== Refreshing eval dashboard =="
& python (Join-Path $RepoRoot "scripts\control_plane\eval_dashboard.py")
if ($LASTEXITCODE -ne 0) {
    throw "Eval dashboard generation failed with exit code $LASTEXITCODE"
}

if ($SkipLive) {
    $ReadinessSummary = Join-Path $RepoRoot "runs\control_plane\readiness\live_full\readiness_summary.json"
} else {
    $ReadinessSummary = Join-Path $OutputRoot "readiness_summary.json"
}
$DashboardSummary = Join-Path $WorkspaceRoot "llm-eval-benchmark\reports\control_plane_dashboard\latest\summary.json"
$PortfolioPage = Join-Path $RepoRoot "docs\job-ready-project-page.md"
$ArchitecturePage = Join-Path $RepoRoot "docs\agent-control-plane-architecture.md"
$ResumeBullets = Join-Path $RepoRoot "docs\resume-bullets.md"

Write-Host ""
Write-Host "== Interview artifacts =="
Write-Host "Readiness summary: $ReadinessSummary"
Write-Host "Eval dashboard:    $DashboardSummary"
Write-Host "Project page:      $PortfolioPage"
Write-Host "Architecture:      $ArchitecturePage"
Write-Host "Resume bullets:    $ResumeBullets"
Write-Host ""
Write-Host "Suggested pitch:"
Write-Host "Built a biomedical Agent Control Plane integrating intent routing, private RAG, public scientific lookup, A2A-compatible worker delegation, session memory, unified observability, and eval dashboard."
