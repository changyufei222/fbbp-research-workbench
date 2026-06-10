from __future__ import annotations

import json
import time
import traceback
from pathlib import Path

from control_plane.a2a import attach_a2a_trace, build_a2a_trace
from control_plane.executor_registry import execute_route
from control_plane.memory_adapter import build_memory_context, update_memory_after_run, write_memory_artifacts
from control_plane.judge import evaluate_run
from control_plane.observability import build_observability_snapshot
from control_plane.request_parser import normalize_request, parse_args
from control_plane.react_trace import build_react_trace, write_react_trace
from control_plane.router import route_request
from control_plane.run_record import (
    append_event,
    attach_run_metrics,
    build_control_plane_run_id,
    finalize_run_record,
    initialize_run_record,
    prepare_run_dir,
    write_json,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    args = parse_args()
    request = normalize_request(args)
    route_started = time.perf_counter()
    route_decision = route_request(request)
    routing_ms = round((time.perf_counter() - route_started) * 1000, 2)
    run_id = build_control_plane_run_id(route_decision["primary_route"])
    run_dir = prepare_run_dir(REPO_ROOT, run_id, request.get("output_dir"))
    events_path = run_dir / "events.jsonl"

    run_record = initialize_run_record(run_id, request, route_decision, run_dir)
    run_record["started_at_utc"] = run_record["created_at_utc"]
    memory_context = build_memory_context(REPO_ROOT, request, route_decision)
    write_memory_artifacts(run_dir, memory_context)
    write_json(run_dir / "run_request.json", request)
    write_json(run_dir / "route_decision.json", route_decision)
    append_event(events_path, "prepared", run_id=run_id, primary_route=route_decision["primary_route"])
    append_event(
        events_path,
        "route_selected",
        primary_route=route_decision["primary_route"],
        decision_source=route_decision.get("decision_source"),
        secondary_capabilities=route_decision.get("secondary_capabilities", []),
        )

    if request.get("dry_run"):
        dry_record = finalize_run_record(
            run_record,
            status="dry_run",
            executor={"name": "none", "mode": "dry_run"},
            timings_ms={"routing": routing_ms, "execution": 0.0, "total": routing_ms},
            artifacts={},
            child_runs=[],
            errors=[],
            result_summary={"message": "dry run only"},
            memory={
                "read_hit": memory_context.get("read_hit", False),
                "resume_used": memory_context.get("resume_used", False),
                "write_status": "dry_run_only",
            },
        )
        a2a_trace = build_a2a_trace(dry_record, request=request, route_decision=route_decision)
        attach_a2a_trace(dry_record, a2a_trace)
        judge = evaluate_run(route_decision, dry_record["status"], dry_record.get("result_summary") or {})
        dry_record["judge"] = judge
        attach_run_metrics(dry_record, judge)
        dry_record["run_record_path"] = str(run_dir / "run_record.json")
        react_trace_paths = write_react_trace(
            run_dir,
            build_react_trace(
                run_id=run_id,
                request=request,
                route_decision=route_decision,
                final_record=dry_record,
                result_summary=dry_record.get("result_summary") or {},
            ),
        )
        dry_record.setdefault("artifacts", {}).update(react_trace_paths)
        observability = build_observability_snapshot(
            dry_record,
            route_decision=route_decision,
            result_summary=dry_record.get("result_summary") or {},
            judge=judge,
        )
        write_json(run_dir / "run_record.json", dry_record)
        write_json(run_dir / "children.json", {"child_runs": [], "a2a_envelopes": [], "trace_id": dry_record.get("trace_id")})
        write_json(run_dir / "a2a_trace.json", a2a_trace)
        write_json(run_dir / "judge.json", judge)
        write_json(run_dir / "observability.json", observability)
        append_event(events_path, "dry_run_completed", run_id=run_id)
        print(json.dumps({"run_id": run_id, "run_dir": str(run_dir), "status": "dry_run"}, ensure_ascii=False))
        return

    try:
        append_event(events_path, "execution_started", primary_route=route_decision["primary_route"])
        execution_started = time.perf_counter()
        result = execute_route(request, route_decision, run_dir)
        execution_ms = round((time.perf_counter() - execution_started) * 1000, 2)
        total_ms = round(routing_ms + execution_ms, 2)
        memory_write = update_memory_after_run(
            REPO_ROOT,
            run_dir,
            request,
            route_decision,
            result.get("result_summary") or {},
        )
        final_record = finalize_run_record(
            run_record,
            status=str(result.get("status") or "succeeded"),
            executor=result.get("executor") or {},
            timings_ms={
                "routing": routing_ms,
                "execution": execution_ms,
                "total": total_ms,
            },
            artifacts=result.get("artifacts") or {},
            child_runs=result.get("child_runs") or [],
            errors=result.get("errors") or [],
            result_summary=result.get("result_summary") or {},
            memory={
                "read_hit": memory_context.get("read_hit", False),
                "resume_used": memory_context.get("resume_used", False),
                "write_status": memory_write.get("write_status"),
                "profile_written": memory_write.get("profile_written", False),
                "profile_memory_path": memory_write.get("profile_memory_path"),
                "resume_state_path": memory_write.get("resume_state_path"),
            },
        )
        a2a_trace = build_a2a_trace(final_record, request=request, route_decision=route_decision)
        attach_a2a_trace(final_record, a2a_trace)
        judge = evaluate_run(route_decision, final_record["status"], final_record.get("result_summary") or {})
        final_record["judge"] = judge
        attach_run_metrics(final_record, judge)
        final_record["run_record_path"] = str(run_dir / "run_record.json")
        react_trace_paths = write_react_trace(
            run_dir,
            build_react_trace(
                run_id=run_id,
                request=request,
                route_decision=route_decision,
                final_record=final_record,
                result_summary=final_record.get("result_summary") or {},
            ),
        )
        final_record.setdefault("artifacts", {}).update(react_trace_paths)
        observability = build_observability_snapshot(
            final_record,
            route_decision=route_decision,
            result_summary=final_record.get("result_summary") or {},
            judge=judge,
        )
        write_json(run_dir / "run_record.json", final_record)
        write_json(
            run_dir / "children.json",
            {
                "child_runs": final_record.get("child_runs", []),
                "a2a_envelopes": a2a_trace.get("envelopes", []),
                "trace_id": final_record.get("trace_id"),
            },
        )
        write_json(run_dir / "a2a_trace.json", a2a_trace)
        write_json(run_dir / "judge.json", judge)
        write_json(run_dir / "observability.json", observability)
        append_event(
            events_path,
            "execution_completed",
            status=final_record["status"],
            child_run_count=len(final_record.get("child_runs", [])),
        )
        print(
            json.dumps(
                {
                    "run_id": run_id,
                    "run_dir": str(run_dir),
                    "status": final_record["status"],
                    "primary_route": route_decision["primary_route"],
                    "preflight": final_record.get("preflight"),
                },
                ensure_ascii=False,
            )
        )
    except Exception as exc:
        error_payload = {
            "message": str(exc),
            "traceback": traceback.format_exc(limit=5),
        }
        failed_record = finalize_run_record(
            run_record,
            status="failed",
            executor={"name": "control_plane", "mode": "failed_before_completion"},
            timings_ms={"routing": routing_ms, "execution": 0.0, "total": routing_ms},
            artifacts={},
            child_runs=[],
            errors=[error_payload],
            result_summary={"message": "control plane execution failed"},
            memory={
                "read_hit": memory_context.get("read_hit", False),
                "resume_used": memory_context.get("resume_used", False),
                "write_status": "failed_before_memory_write",
            },
        )
        a2a_trace = build_a2a_trace(failed_record, request=request, route_decision=route_decision)
        attach_a2a_trace(failed_record, a2a_trace)
        judge = evaluate_run(route_decision, failed_record["status"], failed_record.get("result_summary") or {})
        failed_record["judge"] = judge
        attach_run_metrics(failed_record, judge)
        failed_record["run_record_path"] = str(run_dir / "run_record.json")
        react_trace_paths = write_react_trace(
            run_dir,
            build_react_trace(
                run_id=run_id,
                request=request,
                route_decision=route_decision,
                final_record=failed_record,
                result_summary=failed_record.get("result_summary") or {},
            ),
        )
        failed_record.setdefault("artifacts", {}).update(react_trace_paths)
        observability = build_observability_snapshot(
            failed_record,
            route_decision=route_decision,
            result_summary=failed_record.get("result_summary") or {},
            judge=judge,
        )
        write_json(run_dir / "run_record.json", failed_record)
        write_json(run_dir / "children.json", {"child_runs": [], "a2a_envelopes": [], "trace_id": failed_record.get("trace_id")})
        write_json(run_dir / "a2a_trace.json", a2a_trace)
        write_json(run_dir / "judge.json", judge)
        write_json(run_dir / "observability.json", observability)
        append_event(events_path, "execution_failed", message=str(exc))
        print(json.dumps({"run_id": run_id, "run_dir": str(run_dir), "status": "failed"}, ensure_ascii=False))
        raise


if __name__ == "__main__":
    main()
