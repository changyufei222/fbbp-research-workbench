from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from formal_run_lib import append_error, build_batch_id, build_run_id, initialize_batch_manifest, load_yaml_config, write_json


REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_FORMAL_CASE = REPO_ROOT / "scripts" / "run_fbbp_formal_case.py"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one formal DeerFlow batch")
    parser.add_argument("--batch-path", required=True)
    parser.add_argument("--batch-dir")
    parser.add_argument("--raw-result-dir")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--now")
    return parser.parse_args()


def _parse_now(raw: str | None) -> datetime:
    if raw:
        return datetime.fromisoformat(raw)
    return datetime.now()


def _batch_dir(batch_config: dict[str, Any], batch_dir: str | None, now: datetime) -> tuple[str, Path]:
    if batch_dir:
        resolved = Path(batch_dir).resolve()
        return resolved.name, resolved
    batch_id = build_batch_id(batch_config["batch_slug"], now)
    return batch_id, REPO_ROOT / "batches" / batch_id


def _prepare_manifest(batch_config: dict[str, Any], batch_id: str, batch_dir: Path) -> Path:
    batch_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = batch_dir / "batch_manifest.json"
    if not manifest_path.exists():
        manifest = initialize_batch_manifest(
            batch_id=batch_id,
            batch_config=batch_config,
            runtime_profile=batch_config["runtime_profile"],
            mcp_contract_version=batch_config["mcp_contract_version"],
        )
        write_json(manifest_path, manifest)
    return manifest_path


def _run_root_for_batch(batch_dir: Path) -> Path:
    return batch_dir.parent.parent / "runs"


def _summary_markdown(batch_id: str, case_runs: dict[str, Any], batch_results: dict[str, Any]) -> str:
    lines = [
        "# Formal Batch Summary",
        "",
        f"- Batch ID: `{batch_id}`",
        f"- Status: `{batch_results['status']}`",
        f"- Case count: `{batch_results['case_count']}`",
        "",
        "## Case Runs",
    ]
    for case_id, row in case_runs.items():
        lines.append(f"- `{case_id}` -> `{row['run_id']}` (`{row['status']}`)")
    return "\n".join(lines) + "\n"


def _load_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _preview(value: str | None, limit: int = 180) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def _build_acceptance_artifacts(
    *,
    batch_id: str,
    batch_config: dict[str, Any],
    batch_results: dict[str, Any],
    case_runs: dict[str, Any],
    run_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    case_summaries: list[dict[str, Any]] = []
    total_claims = 0
    total_evidence_rows = 0
    full_completion_count = 0
    partial_completion_count = 0

    for case_id, row in case_runs.items():
        run_id = row["run_id"]
        run_dir = run_root / run_id
        report = _load_json_if_exists(run_dir / "report.json") or {}
        claims = report.get("claims") if isinstance(report.get("claims"), list) else []
        evidence_rows = report.get("evidence_rows") if isinstance(report.get("evidence_rows"), list) else []
        completion_mode = report.get("completion_mode")
        if completion_mode == "full":
            full_completion_count += 1
        elif completion_mode:
            partial_completion_count += 1
        total_claims += len(claims)
        total_evidence_rows += len(evidence_rows)
        case_summaries.append(
            {
                "case_id": case_id,
                "run_id": run_id,
                "status": row["status"],
                "completion_mode": completion_mode,
                "claim_count": len(claims),
                "evidence_row_count": len(evidence_rows),
                "conclusion_preview": _preview((report.get("conclusions") or [None])[0]),
            }
        )

    formal_scoreboard = {
        "batch_id": batch_id,
        "status": batch_results["status"],
        "dataset_version": batch_config["dataset_version"],
        "runtime_profile": batch_config["runtime_profile"],
        "mcp_contract_version": batch_config["mcp_contract_version"],
        "case_count": batch_results["case_count"],
        "successful_case_count": batch_results["succeeded_count"],
        "failed_case_count": batch_results["failed_count"],
        "cases": case_summaries,
    }
    key_metrics_snapshot = {
        "case_count": batch_results["case_count"],
        "successful_case_count": batch_results["succeeded_count"],
        "failed_case_count": batch_results["failed_count"],
        "full_completion_count": full_completion_count,
        "partial_completion_count": partial_completion_count,
        "claim_count": total_claims,
        "evidence_row_count": total_evidence_rows,
    }

    lines = [
        "# Latest successful runs",
        "",
        f"- Batch ID: `{batch_id}`",
        "",
    ]
    for row in case_summaries:
        if row["status"] != "succeeded":
            continue
        lines.append(f"## {row['case_id']}")
        lines.append(f"- Run ID: `{row['run_id']}`")
        lines.append(f"- Completion mode: `{row['completion_mode'] or 'unknown'}`")
        lines.append(f"- Claim count: `{row['claim_count']}`")
        lines.append(f"- Evidence rows: `{row['evidence_row_count']}`")
        if row["conclusion_preview"]:
            lines.append(f"- Preview: {row['conclusion_preview']}")
        lines.append("")
    latest_successful_runs = "\n".join(lines).rstrip() + "\n"
    return formal_scoreboard, key_metrics_snapshot, latest_successful_runs


def main() -> None:
    args = _parse_args()
    batch_path = Path(args.batch_path).resolve()
    batch_config = load_yaml_config(batch_path)
    now = _parse_now(args.now)
    batch_id, batch_dir = _batch_dir(batch_config, args.batch_dir, now)
    manifest_path = _prepare_manifest(batch_config, batch_id, batch_dir)

    if args.prepare_only:
        print(
            json.dumps(
                {"batch_id": batch_id, "batch_dir": str(batch_dir), "manifest_path": str(manifest_path)},
                ensure_ascii=False,
            )
        )
        return

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "running"
    manifest["started_at_utc"] = datetime.now(UTC).isoformat()
    write_json(manifest_path, manifest)

    raw_result_dir = Path(args.raw_result_dir).resolve() if args.raw_result_dir else None
    run_root = _run_root_for_batch(batch_dir)
    run_root.mkdir(parents=True, exist_ok=True)

    case_runs: dict[str, Any] = {}
    failures = 0
    continue_on_error = bool((batch_config.get("execution") or {}).get("continue_on_error", False))

    try:
        for case_id in batch_config.get("cases", []):
            case_path = REPO_ROOT / "configs" / "formal_cases" / f"{case_id}.yaml"
            run_id = build_run_id(case_id, now)
            run_dir = run_root / run_id
            cmd = [sys.executable, str(RUN_FORMAL_CASE), "--case-path", str(case_path), "--run-dir", str(run_dir)]
            if raw_result_dir:
                raw_path = raw_result_dir / f"{case_id}.json"
                if raw_path.exists():
                    cmd.extend(["--raw-result-json", str(raw_path)])
            if args.now:
                cmd.extend(["--now", args.now])

            proc = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT, check=False)
            status = "failed"
            if proc.returncode == 0:
                payload = json.loads(proc.stdout.strip())
                status = payload.get("status", "failed")
            if status != "succeeded":
                failures += 1
                if not continue_on_error:
                    case_runs[case_id] = {"run_id": run_id, "status": status}
                    break
            case_runs[case_id] = {"run_id": run_id, "status": status}

        succeeded = sum(1 for row in case_runs.values() if row["status"] == "succeeded")
        batch_status = "succeeded"
        if failures:
            batch_status = "partial" if continue_on_error and succeeded else "failed"

        batch_results = {
            "batch_id": batch_id,
            "status": batch_status,
            "case_count": len(batch_config.get("cases", [])),
            "succeeded_count": succeeded,
            "failed_count": failures,
            "case_runs": case_runs,
        }
        write_json(batch_dir / "batch_results.json", batch_results)
        write_json(batch_dir / "case_runs.json", case_runs)
        (batch_dir / "batch_summary.md").write_text(
            _summary_markdown(batch_id, case_runs, batch_results),
            encoding="utf-8",
        )
        formal_scoreboard, key_metrics_snapshot, latest_successful_runs = _build_acceptance_artifacts(
            batch_id=batch_id,
            batch_config=batch_config,
            batch_results=batch_results,
            case_runs=case_runs,
            run_root=run_root,
        )
        write_json(batch_dir / "formal_scoreboard.json", formal_scoreboard)
        write_json(batch_dir / "key_metrics_snapshot.json", key_metrics_snapshot)
        (batch_dir / "latest_successful_runs.md").write_text(latest_successful_runs, encoding="utf-8")
        (batch_dir / "logs").mkdir(parents=True, exist_ok=True)

        manifest["status"] = batch_status
        manifest["completed_at_utc"] = datetime.now(UTC).isoformat()
        write_json(manifest_path, manifest)
        print(json.dumps({"batch_id": batch_id, "batch_dir": str(batch_dir), "status": batch_status}, ensure_ascii=False))
    except Exception as exc:
        append_error(manifest, "batch_orchestration", "FORMAL_BATCH_FAILED", str(exc), False)
        manifest["status"] = "failed"
        manifest["completed_at_utc"] = datetime.now(UTC).isoformat()
        write_json(manifest_path, manifest)
        print(json.dumps({"batch_id": batch_id, "batch_dir": str(batch_dir), "status": "failed"}, ensure_ascii=False))
        raise


if __name__ == "__main__":
    main()
