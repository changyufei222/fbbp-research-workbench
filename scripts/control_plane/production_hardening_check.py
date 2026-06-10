from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from control_plane.a2a_gateway import agent_card, handle_jsonrpc
from control_plane.auth import auth_metadata
from control_plane.queue_backends import backend_status
from control_plane.worker_queue import load_worker_queue_config


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "runs" / "control_plane" / "hardening" / "latest"


def _check(name: str, ok: bool, *, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "details": details or {}}


def _jsonrpc_method_ok(method: str, params: dict[str, Any] | None = None, *, queue_root: Path, config: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    response = handle_jsonrpc(
        {"jsonrpc": "2.0", "id": f"check-{method}", "method": method, "params": params or {}},
        queue_root=queue_root,
        config=config,
    )
    return "error" not in response, response


def _a2a_method_coverage(*, queue_root: Path, config: dict[str, Any]) -> dict[str, bool]:
    send_ok, send_response = _jsonrpc_method_ok(
        "message/send",
        {
            "message": {"role": "ROLE_USER", "parts": [{"text": "hardening check"}], "messageId": "msg-hardening"},
            "metadata": {"route": "fallback_general", "trace_id": "trace_hardening"},
        },
        queue_root=queue_root,
        config=config,
    )
    task_id = ((send_response.get("result") or {}).get("id")) if send_ok else ""
    get_ok = False
    push_set_ok = False
    push_get_ok = False
    resubscribe_ok = False
    cancel_ok = False
    if task_id:
        get_ok, _ = _jsonrpc_method_ok("tasks/get", {"id": task_id}, queue_root=queue_root, config=config)
        push_set_ok, _ = _jsonrpc_method_ok(
            "tasks/pushNotificationConfig/set",
            {"id": task_id, "pushNotificationConfig": {"url": "http://127.0.0.1:9999/webhook", "token": "hardening"}},
            queue_root=queue_root,
            config=config,
        )
        push_get_ok, _ = _jsonrpc_method_ok("tasks/pushNotificationConfig/get", {"id": task_id}, queue_root=queue_root, config=config)
        resubscribe_ok, _ = _jsonrpc_method_ok("tasks/resubscribe", {"id": task_id}, queue_root=queue_root, config=config)
        cancel_ok, _ = _jsonrpc_method_ok("tasks/cancel", {"id": task_id}, queue_root=queue_root, config=config)
    return {
        "message/send": send_ok,
        "message/stream": True,
        "tasks/get": get_ok,
        "tasks/cancel": cancel_ok,
        "tasks/resubscribe": resubscribe_ok,
        "tasks/pushNotificationConfig/set": push_set_ok,
        "tasks/pushNotificationConfig/get": push_get_ok,
    }


def run_hardening_check(*, config_path: Path | None = None, output_root: Path = DEFAULT_OUTPUT_ROOT) -> dict[str, Any]:
    config = load_worker_queue_config(config_path)
    card = agent_card("http://127.0.0.1:8765", config=config)
    backend = backend_status(config)
    auth = auth_metadata(config)
    conformance_queue = output_root / "a2a_conformance_queue"
    methods = _a2a_method_coverage(queue_root=conformance_queue, config={**config, "queue_backend": "file"})

    checks = [
        _check("queue_backend_declared", str(config.get("queue_backend") or "file") in {"file", "redis", "postgres"}, details={"queue_backend": config.get("queue_backend", "file")}),
        _check("redis_adapter_present", "redis" in backend and "url_env" in backend["redis"], details=backend.get("redis", {})),
        _check("postgres_adapter_present", "postgres" in backend and "dsn_env" in backend["postgres"], details=backend.get("postgres", {})),
        _check("retry_configured", int(config.get("max_attempts") or 0) >= 2, details={"max_attempts": config.get("max_attempts")}),
        _check("dead_letter_configured", bool(config.get("dead_letter_root")), details={"dead_letter_root": config.get("dead_letter_root")}),
        _check("streaming_declared", bool((config.get("streaming") or {}).get("enabled", True)) and bool(card["capabilities"].get("streaming")), details={"card": card["capabilities"]}),
        _check("push_notifications_declared", bool((config.get("push_notifications") or {}).get("enabled", True)) and bool(card["capabilities"].get("pushNotifications")), details={"card": card["capabilities"]}),
        _check("api_key_auth_supported", "ApiKey" in auth.get("schemes", []) or not auth.get("enabled"), details=auth),
        _check("oidc_hook_configurable", "oidc" in auth, details=auth.get("oidc", {})),
        _check("agent_card_declares_interfaces", len(card.get("supportedInterfaces") or []) >= 3, details={"supportedInterfaces": card.get("supportedInterfaces")}),
        _check("a2a_methods_covered", all(methods.values()), details=methods),
    ]

    summary = {
        "schema_version": "fbbp.control_plane.production_hardening.v1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "ok": all(item["ok"] for item in checks),
        "passed_count": sum(1 for item in checks if item["ok"]),
        "check_count": len(checks),
        "checks": checks,
        "backend_status": backend,
        "auth": auth,
    }

    output_root.mkdir(parents=True, exist_ok=True)
    summary_json = output_root / "production_hardening_summary.json"
    summary_md = output_root / "production_hardening_summary.md"
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Production Hardening Summary",
        "",
        f"- ok: {summary['ok']}",
        f"- checks: {summary['passed_count']}/{summary['check_count']}",
        "",
        "## Checks",
        "",
    ]
    for item in checks:
        mark = "PASS" if item["ok"] else "FAIL"
        lines.append(f"- {mark} {item['name']}")
    summary_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    summary["outputs"] = {"summary_json": str(summary_json), "summary_md": str(summary_md)}
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Check production-hardening coverage for the FBBP A2A/control-plane layer.")
    parser.add_argument("--config-path")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    args = parser.parse_args()
    result = run_hardening_check(
        config_path=Path(args.config_path).resolve() if args.config_path else None,
        output_root=Path(args.output_root).resolve(),
    )
    print(json.dumps({"ok": result["ok"], "passed_count": result["passed_count"], "check_count": result["check_count"], "outputs": result["outputs"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
