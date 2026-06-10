# Final Result Summary

Frozen on `2026-04-18`.

This file is the official portfolio summary for `FBBP Research Workbench` (repo path: `fbbp-research-workbench`). Use it instead of mixing `README`, `docs`, and many historical run folders.

## Positioning

`fbbp-research-workbench` is a formal FBBP research workspace that both executes private-MCP-grounded cases and publishes a deterministic full-data atlas package for GitHub, resume, demo, and paper-facing use.

## Official Status

- Status: active formal surface aligned to the real FBBP database, with the canonical full-data atlas package frozen on `2026-04-18`
- Frozen validation report: `docs/formal_case_validation.md`
- Frozen batch rerun: `batches/20260416_223355_weekly_validation_batch`
- Official package root: `final_results/fbbp_formal_atlas_v2026_04`

## Resume Evidence Chain

### One-line Positioning

Formal FBBP research workspace with private MCP grounding plus a deterministic full-data atlas package.

### Reproduction Command

`powershell -ExecutionPolicy Bypass -File .\scripts\build_fbbp_formal_package.ps1`

### Formal Report

`final_results/fbbp_formal_atlas_v2026_04/atlas_overview.md`

### Key Number

`12` scaffold classes summarized from the current full formal FBBP snapshot.

### Screenshot

`artifacts/20260418_155831_fbbp_formal_console_v2/screenshots/fbbp_formal_console.png`

### Resume Bullet

Built a formal FBBP research workspace that turns the real private database into a deterministic atlas package plus reproducible case artifacts, with one-command rebuild for GitHub, demo, and paper-facing reuse.

## Interactive Entry

- Primary UI: `http://127.0.0.1:3000/workspace`
- Formal results/status page: `http://127.0.0.1:3000/fbbp`

## Canonical Artifacts

- `../docs/fbbp_data_contract.md`
- `final_results/fbbp_formal_atlas_v2026_04/atlas_overview.md`
- `final_results/fbbp_formal_atlas_v2026_04/scaffold_atlas.csv`
- `final_results/fbbp_formal_atlas_v2026_04/target_registry.csv`
- `final_results/fbbp_formal_atlas_v2026_04/package_manifest.json`
- `docs/formal_case_validation.md`
- `docs/formal_runbook.md`
- `batches/20260416_223355_weekly_validation_batch/batch_summary.md`
- `batches/20260416_223355_weekly_validation_batch/formal_scoreboard.json`
- `batches/20260416_223355_weekly_validation_batch/key_metrics_snapshot.json`
- `batches/20260416_223355_weekly_validation_batch/latest_successful_runs.md`
- `runs/20260416_223356_fbbp_knottin_landscape_01/report.json`
- `runs/20260416_223356_fbbp_source_provenance_review_01/report.json`
- `configs/formal_cases/fbbp_knottin_landscape_01.yaml`
- `configs/formal_cases/fbbp_source_provenance_review_01.yaml`

## Notes

- Active formal naming is now `fbbp_*`.
- The canonical publication/GitHub/demo result is now `final_results/fbbp_formal_atlas_v2026_04`, not the legacy demo `reports/` folder.
- The atlas package is generated deterministically from the checked-in formal snapshot under the sibling MCP repo `../fbbp-mcp-rag-server/formal_snapshots/fbbp_private_v2026_04/`.
- Formal batch outputs now include a fixed acceptance panel contract: `batch_summary.md`, `formal_scoreboard.json`, `key_metrics_snapshot.json`, and `latest_successful_runs.md`.
- The frozen weekly batch rerun produced:
  - `fbbp_knottin_landscape_01` -> `runs/20260416_223356_fbbp_knottin_landscape_01`
  - `fbbp_source_provenance_review_01` -> `runs/20260416_223356_fbbp_source_provenance_review_01`
- Final frozen batch metrics:
  - `2/2` cases succeeded
  - `2/2` cases reached `full` completion
  - `33` total evidence rows were captured across the frozen batch
- Historical pre-alignment run folders remain on disk as archived evidence, but they are no longer the active naming standard for this workspace.

