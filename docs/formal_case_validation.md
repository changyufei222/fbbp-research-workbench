# Formal Case Validation

Frozen on `2026-04-18`.

This document records the active FBBP-aligned formal-case validation set for `fbbp-research-workbench`.

The canonical publication/GitHub/demo output is now the deterministic atlas package under:

- `final_results/fbbp_formal_atlas_v2026_04/`

The formal cases below remain the supporting validation layer that backs the interactive DeerFlow runtime.

## Acceptance Result

- Active validation cases: `2`
- Fresh real-runtime rerun status: `2/2` succeeded on `2026-04-16`
- Frozen batch artifact: `batches/20260416_223355_weekly_validation_batch`
- Frozen batch command: `powershell -ExecutionPolicy Bypass -File .\scripts\run_fbbp_formal_batch.ps1 -BatchSlug weekly_validation_batch`

## Canonical Cases

| Case | Canonical run | Result | Official artifacts | Short conclusion |
|---|---|---|---|---|
| `fbbp_knottin_landscape_01` | `runs/20260416_223356_fbbp_knottin_landscape_01` | `full` | `report.md`, `report.json`, `evidence.json`, `tool_calls.jsonl` | retrieved `10` evidence items from the real FBBP runtime and summarized cystine-knot scaffold usage with concrete identifiers including `INT-00146`, `INT-00168`, `PROT-00526`, `PROT-00459`, and `PROT-00472` |
| `fbbp_source_provenance_review_01` | `runs/20260416_223356_fbbp_source_provenance_review_01` | `full` | `report.md`, `report.json`, `evidence.json`, `tool_calls.jsonl` | retrieved `23` evidence items and established that `plmsearch_results.csv` dominates operational coverage at `chunk_count=38079`, while `chunk_count` itself is a coverage metric rather than a quality metric and the final report now carries full source-registry metadata in `evidence_rows` |

## Evidence Paths

- `final_results/fbbp_formal_atlas_v2026_04/atlas_overview.md`
- `final_results/fbbp_formal_atlas_v2026_04/scaffold_atlas.csv`
- `final_results/fbbp_formal_atlas_v2026_04/target_registry.csv`
- `final_results/fbbp_formal_atlas_v2026_04/package_manifest.json`
- `configs/formal_cases/fbbp_knottin_landscape_01.yaml`
- `configs/formal_cases/fbbp_source_provenance_review_01.yaml`
- `batches/20260416_223355_weekly_validation_batch/batch_summary.md`
- `batches/20260416_223355_weekly_validation_batch/formal_scoreboard.json`
- `batches/20260416_223355_weekly_validation_batch/key_metrics_snapshot.json`
- `batches/20260416_223355_weekly_validation_batch/latest_successful_runs.md`
- `runs/20260416_223356_fbbp_knottin_landscape_01/report.json`
- `runs/20260416_223356_fbbp_source_provenance_review_01/report.json`
- `../docs/fbbp_data_contract.md`

## Validation Command

Build the official full-data atlas package:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_fbbp_formal_package.ps1
```

Run the frozen two-case batch from the repo root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_fbbp_formal_batch.ps1 -BatchSlug weekly_validation_batch
```

Run one formal case from the repo root if you only want a single report:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_fbbp_formal_case.ps1 -CaseId fbbp_knottin_landscape_01
```

## Why This Is the Frozen Set

- `fbbp_knottin_landscape_01` covers the scaffold landscape review path against the real FBBP runtime.
- `fbbp_source_provenance_review_01` covers provenance-heavy reporting against the same database line.
- `weekly_validation_batch` is now the one-command frozen rerun surface for this pair of formal cases, with fixed acceptance outputs for UI and portfolio display.
- Archived historical run folders remain useful debugging history, but they are no longer the active naming standard.

