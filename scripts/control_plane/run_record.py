from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _slug(text: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in text.lower())
    return "_".join(part for part in cleaned.split("_") if part) or "run"


def build_control_plane_run_id(primary_route: str) -> str:
    return f"{datetime.now():%Y%m%d_%H%M%S}_{_slug(primary_route)}_{uuid.uuid4().hex[:8]}"


def prepare_run_dir(repo_root: Path, run_id: str, output_dir: str | None = None) -> Path:
    if output_dir:
        run_dir = Path(output_dir).resolve()
    else:
        run_dir = (repo_root / "runs" / "control_plane" / run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "children").mkdir(parents=True, exist_ok=True)
    (run_dir / "memory").mkdir(parents=True, exist_ok=True)
    return run_dir


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_event(path: Path, event_type: str, **fields: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"timestamp_utc": _utc_now(), "event_type": event_type, **fields}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def initialize_run_record(run_id: str, request: dict[str, Any], route_decision: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    query = str(request.get("query") or "")
    preview = " ".join(query.split())
    if len(preview) > 160:
        preview = preview[:157] + "..."
    return {
        "run_id": run_id,
        "parent_run_id": None,
        "trace_id": f"trace_{uuid.uuid4().hex[:12]}",
        "requested_mode": request.get("requested_mode"),
        "primary_route": route_decision["primary_route"],
        "secondary_capabilities": route_decision.get("secondary_capabilities", []),
        "forced_primary_route": route_decision.get("forced_primary_route", False),
        "status": "prepared",
        "created_at_utc": _utc_now(),
        "started_at_utc": None,
        "completed_at_utc": None,
        "request_summary": {
            "query_preview": preview or None,
            "case_path": request.get("case_path"),
            "batch_path": request.get("batch_path"),
            "run_dir": request.get("run_dir"),
            "thread_id": request.get("thread_id"),
        },
        "files": {
            "run_request": str(run_dir / "run_request.json"),
            "route_decision": str(run_dir / "route_decision.json"),
            "run_record": str(run_dir / "run_record.json"),
            "events": str(run_dir / "events.jsonl"),
            "children": str(run_dir / "children.json"),
            "a2a_trace": str(run_dir / "a2a_trace.json"),
            "judge": str(run_dir / "judge.json"),
            "observability": str(run_dir / "observability.json"),
        },
        "executor": {},
        "timings_ms": {},
        "artifacts": {},
        "child_runs": [],
        "a2a": {
            "schema_version": "fbbp.a2a.envelope.v1",
            "trace_id": None,
            "hop_count": 0,
            "envelope_count": 0,
            "envelopes": [],
        },
        "preflight": {
            "attempted": False,
            "hit": False,
            "hit_rate": 0.0,
        },
        "memory": {
            "read_hit": False,
            "resume_used": False,
            "write_status": "not_started",
        },
        "errors": [],
    }


def build_run_metrics(run_record: dict[str, Any], judge: dict[str, Any] | None = None) -> dict[str, Any]:
    status = str(run_record.get("status") or "unknown")
    child_runs = run_record.get("child_runs") if isinstance(run_record.get("child_runs"), list) else []
    a2a = run_record.get("a2a") if isinstance(run_record.get("a2a"), dict) else {}
    a2a_envelopes = a2a.get("envelopes") if isinstance(a2a.get("envelopes"), list) else []
    preflight = run_record.get("preflight") if isinstance(run_record.get("preflight"), dict) else {}
    memory = run_record.get("memory") if isinstance(run_record.get("memory"), dict) else {}
    timings = run_record.get("timings_ms") if isinstance(run_record.get("timings_ms"), dict) else {}
    judge = judge or (run_record.get("judge") if isinstance(run_record.get("judge"), dict) else {})

    if child_runs:
        requested = len(child_runs)
        succeeded = sum(1 for child in child_runs if str(child.get("status") or "") in {"succeeded", "partial"})
    else:
        requested = 1 if run_record.get("executor") else 0
        succeeded = 1 if status in {"succeeded", "dry_run", "partial"} and requested else 0
    success_rate = round(succeeded / requested, 4) if requested else 0.0

    return {
        "route": run_record.get("primary_route"),
        "status": status,
        "tool_success_rate": success_rate,
        "tools_requested": requested,
        "tools_succeeded": succeeded,
        "memory_hit": bool(memory.get("read_hit") or memory.get("resume_used")),
        "memory_read_hit": bool(memory.get("read_hit")),
        "memory_resume_used": bool(memory.get("resume_used")),
        "latency_ms": timings.get("total"),
        "execution_latency_ms": timings.get("execution"),
        "estimated_cost_usd": 0.0,
        "cost_tracked": False,
        "cost_source": "not_metered",
        "judge_score": judge.get("score"),
        "judge_status": judge.get("status"),
        "preflight_hit": bool(preflight.get("hit", False)),
        "preflight_hit_rate": float(preflight.get("hit_rate") or 0.0),
        "preflight_mode": preflight.get("mode"),
        "preflight_data_source": preflight.get("data_source"),
        "preflight_tool_event_count": preflight.get("tool_event_count"),
        "a2a_hop_count": int(a2a.get("hop_count") or 0),
        "a2a_envelope_count": int(a2a.get("envelope_count") or len(a2a_envelopes) or 0),
        "a2a_schema_version": a2a.get("schema_version"),
        "child_success_rate": success_rate,
    }


def attach_run_metrics(run_record: dict[str, Any], judge: dict[str, Any] | None = None) -> dict[str, Any]:
    run_record["metrics"] = build_run_metrics(run_record, judge)
    return run_record


def finalize_run_record(
    run_record: dict[str, Any],
    *,
    status: str,
    executor: dict[str, Any],
    timings_ms: dict[str, float],
    artifacts: dict[str, Any],
    child_runs: list[dict[str, Any]],
    errors: list[dict[str, Any]] | None = None,
    result_summary: dict[str, Any] | None = None,
    memory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_record = dict(run_record)
    run_record["status"] = status
    if run_record.get("started_at_utc") is None:
        run_record["started_at_utc"] = _utc_now()
    run_record["completed_at_utc"] = _utc_now()
    run_record["executor"] = executor
    run_record["timings_ms"] = timings_ms
    run_record["artifacts"] = artifacts
    run_record["child_runs"] = child_runs
    if memory is not None:
        run_record["memory"] = memory
    run_record["errors"] = errors or []
    if result_summary is not None:
        run_record["result_summary"] = result_summary
        preflight = result_summary.get("preflight") if isinstance(result_summary, dict) else None
        if isinstance(preflight, dict):
            run_record["preflight"] = preflight
    return run_record
