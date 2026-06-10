from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from control_plane.a2a import A2A_SCHEMA_VERSION, assert_valid_envelope
from control_plane.queue_backends import (
    append_event as backend_append_event,
    backend_status,
    counts as backend_counts,
    external_backend_available,
    get_task as backend_get_task,
    initialize_external_backend,
    iter_tasks as backend_iter_tasks,
    list_events as backend_list_events,
    put_task as backend_put_task,
)
from formal_run_lib import load_yaml_config


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QUEUE_CONFIG = REPO_ROOT / "configs" / "control_plane" / "worker_queue.yaml"
TERMINAL_STATES = {"TASK_STATE_COMPLETED", "TASK_STATE_FAILED", "TASK_STATE_CANCELED", "TASK_STATE_REJECTED"}


def _int_value(value: Any, default: int) -> int:
    if value is None:
        return default
    return int(value)


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_epoch() -> float:
    return time.time()


def _task_id() -> str:
    return f"task_{uuid4().hex[:16]}"


def _context_id(task_id: str) -> str:
    return f"ctx_{task_id}"


def load_worker_queue_config(path: Path | None = None) -> dict[str, Any]:
    config = load_yaml_config(path or DEFAULT_QUEUE_CONFIG)
    return config or {}


def _use_external_backend(config: dict[str, Any]) -> bool:
    return str(config.get("queue_backend") or "file") in {"redis", "postgres"} and external_backend_available(config)


def queue_root_from_config(config: dict[str, Any] | None = None, *, repo_root: Path = REPO_ROOT) -> Path:
    config = config or load_worker_queue_config()
    configured = Path(str(config.get("queue_root") or "runs/control_plane/a2a_queue"))
    return configured if configured.is_absolute() else repo_root / configured


def dead_letter_root_from_config(config: dict[str, Any] | None = None, *, repo_root: Path = REPO_ROOT) -> Path:
    config = config or load_worker_queue_config()
    configured = Path(str(config.get("dead_letter_root") or "runs/control_plane/dead_letters"))
    return configured if configured.is_absolute() else repo_root / configured


def initialize_queue(queue_root: Path) -> None:
    for name in ("pending", "running", "completed", "failed", "events"):
        (queue_root / name).mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _task_path(queue_root: Path, state_dir: str, task_id: str) -> Path:
    return queue_root / state_dir / f"{task_id}.json"


def _event_path(queue_root: Path, task_id: str) -> Path:
    return queue_root / "events" / f"{task_id}.jsonl"


def _find_task_file(queue_root: Path, task_id: str) -> Path | None:
    for state_dir in ("pending", "running", "completed", "failed"):
        candidate = _task_path(queue_root, state_dir, task_id)
        if candidate.exists():
            return candidate
    return None


def _task_status_from_queue_state(queue_state: str) -> str:
    return {
        "pending": "TASK_STATE_SUBMITTED",
        "running": "TASK_STATE_WORKING",
        "completed": "TASK_STATE_COMPLETED",
        "failed": "TASK_STATE_FAILED",
        "dead_letter": "TASK_STATE_FAILED",
        "canceled": "TASK_STATE_CANCELED",
    }.get(queue_state, "TASK_STATE_UNSPECIFIED")


def _push_config_from_input(input_payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(input_payload, dict):
        return None
    direct = input_payload.get("pushNotificationConfig") or input_payload.get("pushNotification")
    if isinstance(direct, dict):
        return direct
    configuration = input_payload.get("configuration")
    if isinstance(configuration, dict):
        nested = configuration.get("pushNotificationConfig") or configuration.get("pushNotification")
        if isinstance(nested, dict):
            return nested
    metadata = input_payload.get("metadata")
    if isinstance(metadata, dict):
        nested = metadata.get("pushNotificationConfig") or metadata.get("pushNotification")
        if isinstance(nested, dict):
            return nested
    return None


def _append_event(
    queue_root: Path,
    task_id: str,
    event: str,
    *,
    config: dict[str, Any] | None = None,
    **payload: Any,
) -> None:
    event_payload = {
        "timestamp_utc": _now_utc(),
        "event": event,
        "task_id": task_id,
        **payload,
    }
    if config and _use_external_backend(config):
        backend_append_event(config, task_id, event_payload)
        return
    path = _event_path(queue_root, task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event_payload, ensure_ascii=False) + "\n")


def _put_task(queue_root: Path, task: dict[str, Any], *, config: dict[str, Any]) -> None:
    if _use_external_backend(config):
        backend_put_task(config, task)
        return
    _write_json(_task_path(queue_root, str(task.get("queue_state") or "pending"), str(task["task_id"])), task)


def _move_task(
    queue_root: Path,
    task: dict[str, Any],
    target_state: str,
    *,
    config: dict[str, Any],
) -> dict[str, Any]:
    task_id = str(task["task_id"])
    source = None if _use_external_backend(config) else _find_task_file(queue_root, task_id)
    task["queue_state"] = target_state
    task["status"] = _task_status_from_queue_state(target_state)
    task["updated_at_utc"] = _now_utc()
    _put_task(queue_root, task, config=config)
    if source:
        target = _task_path(queue_root, target_state, task_id)
        if source.resolve() != target.resolve():
            source.unlink(missing_ok=True)
    return task


def _send_push_event(
    queue_root: Path,
    task: dict[str, Any],
    event_type: str,
    *,
    config: dict[str, Any],
) -> dict[str, Any]:
    from control_plane.push_notifications import send_push_notification

    result = send_push_notification(task, event_type, queue_config=config)
    _append_event(queue_root, str(task["task_id"]), "push_notification", config=config, event_type=event_type, result=result)
    return result


def create_task(
    *,
    envelope: dict[str, Any],
    input_payload: dict[str, Any] | None = None,
    queue_root: Path | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    assert_valid_envelope(envelope)
    config = config or load_worker_queue_config()
    queue_root = queue_root or queue_root_from_config(config)
    if _use_external_backend(config):
        initialize_external_backend(config)
    else:
        initialize_queue(queue_root)
    task_id = str(envelope.get("child_run_id") or _task_id())
    envelope["child_run_id"] = task_id
    task = {
        "task_id": task_id,
        "context_id": str(envelope.get("trace_id") or _context_id(task_id)),
        "queue_state": "pending",
        "status": "TASK_STATE_SUBMITTED",
        "attempts": 0,
        "max_attempts": _int_value(config.get("max_attempts"), 3),
        "backoff_seconds": _int_value(config.get("backoff_seconds"), 30),
        "lease_seconds": _int_value(config.get("lease_seconds"), 900),
        "next_attempt_epoch": _now_epoch(),
        "created_at_utc": _now_utc(),
        "updated_at_utc": _now_utc(),
        "envelope": envelope,
        "input": input_payload or {},
        "push_notification_config": _push_config_from_input(input_payload),
        "artifacts": [],
        "history": [
            {
                "role": "ROLE_USER",
                "parts": [{"text": str((input_payload or {}).get("query") or envelope.get("input_ref") or "A2A task")}],
                "messageId": str(envelope.get("message_id")),
            }
        ],
        "error": None,
    }
    _put_task(queue_root, task, config=config)
    _append_event(queue_root, task_id, "task_queued", config=config, status=task["status"])
    return task


def get_task(
    task_id: str,
    *,
    queue_root: Path | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    config = config or load_worker_queue_config()
    if _use_external_backend(config):
        return backend_get_task(config, task_id)
    queue_root = queue_root or queue_root_from_config(config)
    path = _find_task_file(queue_root, task_id)
    if not path:
        return None
    return _read_json(path)


def set_push_notification_config(
    task_id: str,
    push_config: dict[str, Any],
    *,
    queue_root: Path | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or load_worker_queue_config()
    queue_root = queue_root or queue_root_from_config(config)
    task = get_task(task_id, queue_root=queue_root, config=config)
    if not task:
        raise FileNotFoundError(f"task not found: {task_id}")
    task["push_notification_config"] = push_config
    task["updated_at_utc"] = _now_utc()
    _put_task(queue_root, task, config=config)
    _append_event(queue_root, task_id, "push_notification_config_set", config=config, has_url=bool(push_config.get("url")))
    return task


def get_push_notification_config(
    task_id: str,
    *,
    queue_root: Path | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    task = get_task(task_id, queue_root=queue_root, config=config)
    if not task:
        raise FileNotFoundError(f"task not found: {task_id}")
    push_config = task.get("push_notification_config")
    return push_config if isinstance(push_config, dict) else None


def list_task_events(
    task_id: str,
    *,
    queue_root: Path | None = None,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    config = config or load_worker_queue_config()
    if _use_external_backend(config):
        return backend_list_events(config, task_id)
    queue_root = queue_root or queue_root_from_config(config)
    path = _event_path(queue_root, task_id)
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


def claim_next_task(
    *,
    queue_root: Path | None = None,
    worker_id: str = "external-worker",
    now_epoch: float | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    config = config or load_worker_queue_config()
    queue_root = queue_root or queue_root_from_config(config)
    if _use_external_backend(config):
        initialize_external_backend(config)
        candidates = backend_iter_tasks(config, "pending")
    else:
        initialize_queue(queue_root)
        candidates = [_read_json(path) for path in sorted((queue_root / "pending").glob("*.json"))]
    now_epoch = _now_epoch() if now_epoch is None else now_epoch
    for task in candidates:
        if float(task.get("next_attempt_epoch") or 0) > now_epoch:
            continue
        task["attempts"] = int(task.get("attempts") or 0) + 1
        task["worker_id"] = worker_id
        task["lease_expires_epoch"] = now_epoch + _int_value(task.get("lease_seconds"), 900)
        task = _move_task(queue_root, task, "running", config=config)
        _append_event(queue_root, str(task["task_id"]), "task_claimed", config=config, worker_id=worker_id, attempts=task["attempts"])
        return task
    return None


def complete_task(
    task_id: str,
    *,
    result_envelope: dict[str, Any] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    queue_root: Path | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or load_worker_queue_config()
    queue_root = queue_root or queue_root_from_config(config)
    task = get_task(task_id, queue_root=queue_root, config=config)
    if not task:
        raise FileNotFoundError(f"task not found: {task_id}")
    if result_envelope is not None:
        assert_valid_envelope(result_envelope)
        task["result_envelope"] = result_envelope
    task["artifacts"] = artifacts or task.get("artifacts") or []
    task["error"] = None
    completed = _move_task(queue_root, task, "completed", config=config)
    _append_event(queue_root, task_id, "task_completed", config=config, artifact_count=len(completed.get("artifacts") or []))
    _send_push_event(queue_root, completed, "task_completed", config=config)
    return completed


def fail_task(
    task_id: str,
    *,
    error: dict[str, Any],
    queue_root: Path | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or load_worker_queue_config()
    queue_root = queue_root or queue_root_from_config(config)
    task = get_task(task_id, queue_root=queue_root, config=config)
    if not task:
        raise FileNotFoundError(f"task not found: {task_id}")
    task["error"] = error
    attempts = int(task.get("attempts") or 0)
    max_attempts = _int_value(task.get("max_attempts", config.get("max_attempts")), 3)
    if attempts < max_attempts:
        task["next_attempt_epoch"] = _now_epoch() + _int_value(task.get("backoff_seconds", config.get("backoff_seconds")), 30)
        task = _move_task(queue_root, task, "pending", config=config)
        _append_event(queue_root, task_id, "task_retry_scheduled", config=config, attempts=attempts, max_attempts=max_attempts, error=error)
        _send_push_event(queue_root, task, "task_retry_scheduled", config=config)
        return task

    failed = _move_task(queue_root, task, "failed", config=config)
    dead_root = dead_letter_root_from_config(config)
    dead_path = dead_root / f"{task_id}.json"
    dead_payload = dict(failed)
    dead_payload["queue_state"] = "dead_letter"
    dead_payload["dead_lettered_at_utc"] = _now_utc()
    _write_json(dead_path, dead_payload)
    _append_event(queue_root, task_id, "task_dead_lettered", config=config, attempts=attempts, max_attempts=max_attempts, error=error, dead_letter_path=str(dead_path))
    _send_push_event(queue_root, failed, "task_dead_lettered", config=config)
    return failed


def cancel_task(
    task_id: str,
    *,
    queue_root: Path | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or load_worker_queue_config()
    queue_root = queue_root or queue_root_from_config(config)
    task = get_task(task_id, queue_root=queue_root, config=config)
    if not task:
        raise FileNotFoundError(f"task not found: {task_id}")
    if task.get("status") in TERMINAL_STATES:
        return task
    task = _move_task(queue_root, task, "failed", config=config)
    task["status"] = "TASK_STATE_CANCELED"
    _put_task(queue_root, task, config=config)
    _append_event(queue_root, task_id, "task_canceled", config=config)
    return task


def to_a2a_task(task: dict[str, Any]) -> dict[str, Any]:
    artifacts = task.get("artifacts") if isinstance(task.get("artifacts"), list) else []
    payload = {
        "id": task["task_id"],
        "contextId": task.get("context_id") or task.get("envelope", {}).get("trace_id"),
        "status": {
            "state": task.get("status") or _task_status_from_queue_state(str(task.get("queue_state") or "")),
            "timestamp": task.get("updated_at_utc") or task.get("created_at_utc"),
        },
        "history": task.get("history") or [],
        "artifacts": artifacts,
        "metadata": {
            "queue_state": task.get("queue_state"),
            "attempts": task.get("attempts", 0),
            "max_attempts": task.get("max_attempts"),
            "trace_id": task.get("envelope", {}).get("trace_id") if isinstance(task.get("envelope"), dict) else None,
            "correlation_id": task.get("envelope", {}).get("correlation_id") if isinstance(task.get("envelope"), dict) else None,
            "dead_lettered": bool(task.get("queue_state") == "dead_letter"),
            "push_notifications": bool(task.get("push_notification_config")),
        },
    }
    if task.get("error"):
        payload["status"]["message"] = {
            "role": "ROLE_AGENT",
            "parts": [{"text": str(task["error"].get("message") if isinstance(task["error"], dict) else task["error"])}],
            "messageId": f"{task['task_id']}:error",
        }
    return payload


def queue_health(*, queue_root: Path | None = None, config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or load_worker_queue_config()
    queue_root = queue_root or queue_root_from_config(config)
    if _use_external_backend(config):
        initialize_external_backend(config)
        state_counts = backend_counts(config)
    else:
        initialize_queue(queue_root)
        state_counts = {
            "pending": len(list((queue_root / "pending").glob("*.json"))),
            "running": len(list((queue_root / "running").glob("*.json"))),
            "completed": len(list((queue_root / "completed").glob("*.json"))),
            "failed": len(list((queue_root / "failed").glob("*.json"))),
        }
    dead_root = dead_letter_root_from_config(config)
    streaming_config = config.get("streaming") if isinstance(config.get("streaming"), dict) else {}
    push_config = config.get("push_notifications") if isinstance(config.get("push_notifications"), dict) else {}
    return {
        "queue_backend": config.get("queue_backend", "file"),
        "queue_root": str(queue_root),
        "pending": state_counts["pending"],
        "running": state_counts["running"],
        "completed": state_counts["completed"],
        "failed": state_counts["failed"],
        "dead_letters": len(list(dead_root.glob("*.json"))) if dead_root.exists() else 0,
        "schema_version": A2A_SCHEMA_VERSION,
        "backend_status": backend_status(config),
        "streaming": streaming_config.get("enabled", True),
        "push_notifications": push_config.get("enabled", True),
    }
