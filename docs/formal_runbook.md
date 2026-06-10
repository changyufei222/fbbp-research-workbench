# Formal Runbook

This is the primary formal path for the real `FBBP` database.

## Formal Case

Run one checked-in case:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_fbbp_formal_case.ps1 -CaseId fbbp_knottin_landscape_01
```

Outputs are written to:

- `runs/<run_id>/run_manifest.json`
- `runs/<run_id>/report.md`
- `runs/<run_id>/report.json`
- `runs/<run_id>/evidence.json`
- `runs/<run_id>/tool_calls.jsonl`

## Formal Batch

Run one checked-in batch:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_fbbp_formal_batch.ps1 -BatchSlug weekly_validation_batch
```

Outputs are written to:

- `batches/<batch_id>/batch_manifest.json`
- `batches/<batch_id>/batch_summary.md`
- `batches/<batch_id>/batch_results.json`
- `batches/<batch_id>/case_runs.json`

## Active FBBP Cases

- `fbbp_knottin_landscape_01`
- `fbbp_source_provenance_review_01`
