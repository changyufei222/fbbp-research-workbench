from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _preview(value: Any, limit: int = 320) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def build_react_trace(
    *,
    run_id: str,
    request: dict[str, Any],
    route_decision: dict[str, Any],
    final_record: dict[str, Any],
    result_summary: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    result_summary = result_summary or {}
    primary_route = str(route_decision.get("primary_route") or "fallback_general")
    executor = final_record.get("executor") if isinstance(final_record.get("executor"), dict) else {}
    artifacts = final_record.get("artifacts") if isinstance(final_record.get("artifacts"), dict) else {}
    errors = final_record.get("errors") if isinstance(final_record.get("errors"), list) else []
    child_runs = final_record.get("child_runs") if isinstance(final_record.get("child_runs"), list) else []

    return [
        {
            "step": 1,
            "phase": "plan",
            "timestamp_utc": _now_utc(),
            "run_id": run_id,
            "thought_summary": "Classify the user request and choose the safest control-plane route.",
            "route": primary_route,
            "decision_source": route_decision.get("decision_source"),
            "secondary_capabilities": route_decision.get("secondary_capabilities", []),
            "query_preview": _preview(request.get("query") or request.get("case_path") or request),
        },
        {
            "step": 2,
            "phase": "tool_call",
            "timestamp_utc": _now_utc(),
            "run_id": run_id,
            "tool_name": executor.get("name") or primary_route,
            "tool_mode": executor.get("mode"),
            "route": primary_route,
            "input_refs": {
                "case_path": request.get("case_path"),
                "top_k": request.get("top_k"),
                "record_type": request.get("record_type"),
            },
        },
        {
            "step": 3,
            "phase": "observation",
            "timestamp_utc": _now_utc(),
            "run_id": run_id,
            "status": final_record.get("status"),
            "artifact_keys": sorted(artifacts),
            "child_run_count": len(child_runs),
            "error_count": len(errors),
            "summary_preview": _preview(result_summary.get("message") or result_summary.get("answer_preview") or result_summary),
        },
        {
            "step": 4,
            "phase": "revise",
            "timestamp_utc": _now_utc(),
            "run_id": run_id,
            "status": final_record.get("status"),
            "next_action": "finalize_report" if final_record.get("status") in {"succeeded", "dry_run"} else "inspect_errors_or_retry",
            "judge_score": (final_record.get("judge") or {}).get("score") if isinstance(final_record.get("judge"), dict) else None,
        },
        {
            "step": 5,
            "phase": "report",
            "timestamp_utc": _now_utc(),
            "run_id": run_id,
            "status": final_record.get("status"),
            "run_record": str(final_record.get("run_record_path") or "run_record.json"),
            "observability": "observability.json",
            "a2a_trace": "a2a_trace.json",
        },
    ]


def write_react_trace(run_dir: Path, trace: list[dict[str, Any]]) -> dict[str, str]:
    jsonl_path = run_dir / "react_trace.jsonl"
    json_path = run_dir / "react_trace.json"
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for item in trace:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    json_path.write_text(json.dumps({"trace": trace}, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"react_trace_jsonl": str(jsonl_path), "react_trace_json": str(json_path)}
