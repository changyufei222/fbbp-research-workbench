from __future__ import annotations

import json
import urllib.request
from typing import Any
from urllib.parse import urlparse


def _push_config(task: dict[str, Any]) -> dict[str, Any] | None:
    config = task.get("push_notification_config")
    return config if isinstance(config, dict) else None


def _queue_push_config(queue_config: dict[str, Any] | None) -> dict[str, Any]:
    config = (queue_config or {}).get("push_notifications")
    return config if isinstance(config, dict) else {}


def _allowed_url(url: str, queue_config: dict[str, Any] | None) -> bool:
    push_config = _queue_push_config(queue_config)
    allowed = [str(item) for item in push_config.get("allowed_url_prefixes", [])]
    if not allowed:
        return True
    return any(url.startswith(prefix) for prefix in allowed)


def _headers_for(config: dict[str, Any]) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    token = config.get("token") or ((config.get("authentication") or {}).get("credentials") if isinstance(config.get("authentication"), dict) else None)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    api_key = config.get("api_key") or config.get("apiKey")
    if api_key:
        headers["X-A2A-Webhook-Key"] = str(api_key)
    return headers


def build_push_payload(task: dict[str, Any], event_type: str) -> dict[str, Any]:
    return {
        "event": event_type,
        "taskId": task.get("task_id"),
        "contextId": task.get("context_id"),
        "status": task.get("status"),
        "queueState": task.get("queue_state"),
        "attempts": task.get("attempts", 0),
        "traceId": (task.get("envelope") or {}).get("trace_id") if isinstance(task.get("envelope"), dict) else None,
        "correlationId": (task.get("envelope") or {}).get("correlation_id") if isinstance(task.get("envelope"), dict) else None,
        "artifacts": task.get("artifacts") or [],
        "error": task.get("error"),
    }


def send_push_notification(task: dict[str, Any], event_type: str, *, queue_config: dict[str, Any] | None = None) -> dict[str, Any]:
    global_config = _queue_push_config(queue_config)
    if not bool(global_config.get("enabled", True)):
        return {"sent": False, "reason": "push_disabled"}
    config = _push_config(task)
    if not config:
        return {"sent": False, "reason": "no_push_config"}
    url = str(config.get("url") or "").strip()
    if not url:
        return {"sent": False, "reason": "missing_url"}
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return {"sent": False, "reason": "invalid_url_scheme", "url": url}
    if not _allowed_url(url, queue_config):
        return {"sent": False, "reason": "url_not_allowed", "url": url}

    payload = build_push_payload(task, event_type)
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=_headers_for(config),
        method="POST",
    )
    timeout = int(global_config.get("timeout_seconds") or 5)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return {
                "sent": True,
                "status": response.status,
                "url": url,
            }
    except Exception as exc:
        return {
            "sent": False,
            "reason": "delivery_failed",
            "url": url,
            "error": str(exc),
        }
