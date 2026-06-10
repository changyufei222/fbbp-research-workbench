from __future__ import annotations

import hashlib
from typing import Any


A2A_SCHEMA_VERSION = "fbbp.a2a.envelope.v1"
CONTROL_PLANE_AGENT_ID = "fbbp-control-plane"
VALID_MESSAGE_TYPES = {"child_run_request", "child_run_result", "child_run_error"}


def _stable_hash(prefix: str, *parts: object) -> str:
    raw = "|".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:16]}"


def _stable_message_id(trace_id: str, hop_index: int, child_run_id: str, message_type: str) -> str:
    return _stable_hash("a2a", trace_id, hop_index, child_run_id, message_type)


def _stable_correlation_id(trace_id: str, hop_index: int, child_run_id: str) -> str:
    return _stable_hash("a2ac", trace_id, hop_index, child_run_id)


def _request_input_ref(request_summary: dict[str, Any]) -> str | None:
    for key in ("case_path", "batch_path", "run_dir"):
        value = request_summary.get(key)
        if value:
            return str(value)
    return None


def _message_type_for_status(status: str) -> str:
    return "child_run_error" if status in {"failed", "cancelled", "error"} else "child_run_result"


def _phase_for_message_type(message_type: str) -> str:
    if message_type == "child_run_request":
        return "requested"
    if message_type == "child_run_error":
        return "error"
    return "completed"


def _status_for_message_type(message_type: str, child_status: str) -> str:
    if message_type == "child_run_request":
        return "requested"
    return child_status or "unknown"


def _child_context(run_record: dict[str, Any], child_run: dict[str, Any], hop_index: int) -> dict[str, str]:
    trace_id = str(run_record.get("trace_id") or "")
    parent_run_id = str(run_record.get("run_id") or "")
    child_run_id = str(child_run.get("child_run_id") or f"{parent_run_id}:child:{hop_index}")
    child_route = str(child_run.get("route") or run_record.get("primary_route") or "unknown")
    status = str(child_run.get("status") or "unknown")
    return {
        "trace_id": trace_id,
        "parent_run_id": parent_run_id,
        "child_run_id": child_run_id,
        "child_route": child_route,
        "status": status,
    }


def build_child_envelope(
    *,
    run_record: dict[str, Any],
    child_run: dict[str, Any],
    hop_index: int,
    message_type: str | None = None,
) -> dict[str, Any]:
    child = _child_context(run_record, child_run, hop_index)
    trace_id = child["trace_id"]
    parent_run_id = child["parent_run_id"]
    child_run_id = child["child_run_id"]
    child_route = child["child_route"]
    child_status = child["status"]
    message_type = message_type or _message_type_for_status(child_status)
    if message_type not in VALID_MESSAGE_TYPES:
        raise ValueError(f"Unsupported A2A message_type: {message_type}")

    executor = run_record.get("executor") if isinstance(run_record.get("executor"), dict) else {}
    artifacts = run_record.get("artifacts") if isinstance(run_record.get("artifacts"), dict) else {}
    request_summary = run_record.get("request_summary") if isinstance(run_record.get("request_summary"), dict) else {}
    is_request = message_type == "child_run_request"

    error_payload = child_run.get("error")
    if message_type == "child_run_error" and not error_payload:
        error_payload = {"message": f"child run ended with status={child_status}"}

    envelope = {
        "schema_version": A2A_SCHEMA_VERSION,
        "message_id": _stable_message_id(trace_id, hop_index, child_run_id, message_type),
        "correlation_id": _stable_correlation_id(trace_id, hop_index, child_run_id),
        "message_type": message_type,
        "phase": _phase_for_message_type(message_type),
        "trace_id": trace_id,
        "parent_run_id": parent_run_id,
        "child_run_id": child_run_id,
        "hop_index": hop_index,
        "hop_path": [item for item in (parent_run_id, child_run_id) if item],
        "source_agent": CONTROL_PLANE_AGENT_ID,
        "target_agent": child_route,
        "target_executor": executor.get("name"),
        "target_executor_mode": executor.get("mode"),
        "route": child_route,
        "status": _status_for_message_type(message_type, child_status),
        "created_at_utc": run_record.get("completed_at_utc") or run_record.get("started_at_utc") or run_record.get("created_at_utc"),
        "input_ref": _request_input_ref(request_summary),
        "payload_ref": None if is_request else artifacts.get("primary_output_json"),
        "artifact_ref": None if is_request else child_run.get("artifact_dir"),
        "error": error_payload if message_type == "child_run_error" else None,
        "metadata": {
            "primary_route": run_record.get("primary_route"),
            "requested_mode": run_record.get("requested_mode"),
            "forced_primary_route": run_record.get("forced_primary_route", False),
        },
    }
    assert_valid_envelope(envelope)
    return envelope


def build_child_envelopes(
    *,
    run_record: dict[str, Any],
    child_run: dict[str, Any],
    hop_index: int,
) -> list[dict[str, Any]]:
    result_type = _message_type_for_status(str(child_run.get("status") or "unknown"))
    return [
        build_child_envelope(
            run_record=run_record,
            child_run=child_run,
            hop_index=hop_index,
            message_type="child_run_request",
        ),
        build_child_envelope(
            run_record=run_record,
            child_run=child_run,
            hop_index=hop_index,
            message_type=result_type,
        ),
    ]


def validate_envelope(envelope: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = (
        "schema_version",
        "message_id",
        "correlation_id",
        "message_type",
        "phase",
        "trace_id",
        "parent_run_id",
        "child_run_id",
        "hop_index",
        "source_agent",
        "target_agent",
        "route",
        "status",
    )
    for key in required:
        if envelope.get(key) in (None, ""):
            errors.append(f"missing {key}")
    if envelope.get("schema_version") != A2A_SCHEMA_VERSION:
        errors.append("invalid schema_version")
    if envelope.get("message_type") not in VALID_MESSAGE_TYPES:
        errors.append("invalid message_type")
    hop_index = envelope.get("hop_index")
    if not isinstance(hop_index, int) or hop_index < 1:
        errors.append("hop_index must be a positive integer")
    if envelope.get("message_type") == "child_run_request" and envelope.get("phase") != "requested":
        errors.append("request envelope must use requested phase")
    if envelope.get("message_type") == "child_run_error" and not envelope.get("error"):
        errors.append("error envelope must include error")
    return errors


def assert_valid_envelope(envelope: dict[str, Any]) -> None:
    errors = validate_envelope(envelope)
    if errors:
        raise ValueError("Invalid A2A envelope: " + "; ".join(errors))


def validate_a2a_trace(trace: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    envelopes = trace.get("envelopes") if isinstance(trace.get("envelopes"), list) else []
    for index, envelope in enumerate(envelopes, start=1):
        if not isinstance(envelope, dict):
            errors.append(f"envelope {index} is not an object")
            continue
        errors.extend([f"envelope {index}: {error}" for error in validate_envelope(envelope)])
    hop_count = len({envelope.get("hop_index") for envelope in envelopes if isinstance(envelope, dict)})
    if int(trace.get("hop_count") or 0) != hop_count:
        errors.append("hop_count does not match unique envelope hop count")
    if int(trace.get("envelope_count") or 0) != len(envelopes):
        errors.append("envelope_count does not match envelope list length")
    return errors


def build_a2a_trace(
    run_record: dict[str, Any],
    *,
    request: dict[str, Any] | None = None,
    route_decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    child_runs = run_record.get("child_runs") if isinstance(run_record.get("child_runs"), list) else []
    envelopes: list[dict[str, Any]] = []
    for index, child_run in enumerate(child_runs, start=1):
        if isinstance(child_run, dict):
            envelopes.extend(build_child_envelopes(run_record=run_record, child_run=child_run, hop_index=index))
    trace = {
        "schema_version": A2A_SCHEMA_VERSION,
        "trace_id": run_record.get("trace_id"),
        "parent_run_id": run_record.get("run_id"),
        "primary_route": (route_decision or {}).get("primary_route") or run_record.get("primary_route"),
        "requested_mode": (request or {}).get("requested_mode") or run_record.get("requested_mode"),
        "hop_count": len(child_runs),
        "envelope_count": len(envelopes),
        "envelopes": envelopes,
    }
    errors = validate_a2a_trace(trace)
    if errors:
        raise ValueError("Invalid A2A trace: " + "; ".join(errors))
    return trace


def attach_a2a_trace(run_record: dict[str, Any], a2a_trace: dict[str, Any]) -> dict[str, Any]:
    run_record["a2a"] = {
        "schema_version": a2a_trace.get("schema_version"),
        "trace_id": a2a_trace.get("trace_id"),
        "hop_count": a2a_trace.get("hop_count", 0),
        "envelope_count": a2a_trace.get("envelope_count", 0),
        "envelopes": a2a_trace.get("envelopes", []),
    }
    return run_record
