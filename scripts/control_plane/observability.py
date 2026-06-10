from __future__ import annotations

from pathlib import Path
from typing import Any

from formal_run_lib import load_yaml_config


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OBSERVABILITY_CONFIG = REPO_ROOT / "configs" / "control_plane" / "observability.yaml"


def load_observability_config(path: Path | None = None) -> dict[str, Any]:
    return load_yaml_config(path or DEFAULT_OBSERVABILITY_CONFIG)


def build_observability_snapshot(
    run_record: dict[str, Any],
    *,
    route_decision: dict[str, Any],
    result_summary: dict[str, Any],
    judge: dict[str, Any],
) -> dict[str, Any]:
    child_runs = run_record.get("child_runs", []) or []
    a2a = run_record.get("a2a", {}) or {}
    memory = run_record.get("memory", {}) or {}
    preflight = run_record.get("preflight", {}) or {}
    status = str(run_record.get("status") or "unknown")
    tool_succeeded = 1 if status in {"succeeded", "partial"} else 0
    tool_failed = 1 if status == "failed" else 0
    return {
        "run_id": run_record.get("run_id"),
        "primary_route": route_decision.get("primary_route"),
        "secondary_capabilities": route_decision.get("secondary_capabilities", []),
        "status": status,
        "timings_ms": run_record.get("timings_ms", {}),
        "tools": {
            "requested": 1,
            "succeeded": tool_succeeded,
            "failed": tool_failed,
        },
        "memory": {
            "read_hit": memory.get("read_hit"),
            "resume_used": memory.get("resume_used"),
            "write_status": memory.get("write_status"),
        },
        "preflight": {
            "attempted": preflight.get("attempted", False),
            "hit": preflight.get("hit", False),
            "hit_rate": preflight.get("hit_rate", 0.0),
            "mode": preflight.get("mode"),
            "data_source": preflight.get("data_source"),
            "tool_event_count": preflight.get("tool_event_count"),
        },
        "judge": judge,
        "a2a": {
            "schema_version": a2a.get("schema_version"),
            "trace_id": a2a.get("trace_id"),
            "hop_count": a2a.get("hop_count", 0),
            "envelope_count": a2a.get("envelope_count", 0),
        },
        "metrics": run_record.get("metrics", {}),
        "child_run_count": len(child_runs),
        "result_summary": result_summary,
    }
