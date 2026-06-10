from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from control_plane.a2a import A2A_SCHEMA_VERSION
from control_plane.worker_queue import create_task, queue_health


def _probe_task() -> dict[str, object]:
    return {
        "schema_version": A2A_SCHEMA_VERSION,
        "message_id": "msg_probe_redis_queue",
        "correlation_id": "a2ac_probe_redis_queue",
        "message_type": "child_run_request",
        "phase": "requested",
        "trace_id": "trace_probe_redis_queue",
        "parent_run_id": "trace_probe_redis_queue",
        "child_run_id": "task_probe_redis_queue",
        "hop_index": 1,
        "source_agent": "probe",
        "target_agent": "fbbp-control-plane",
        "route": "fallback_general",
        "status": "requested",
    }


def _redact_url(url: str) -> str:
    if "@" not in url:
        return url
    scheme, rest = url.split("://", 1) if "://" in url else ("", url)
    host = rest.split("@", 1)[1]
    return f"{scheme}://***@{host}" if scheme else f"***@{host}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe the A2A Redis queue backend without printing secrets.")
    parser.add_argument("--redis-url", default=os.environ.get("FBBP_A2A_REDIS_URL"))
    parser.add_argument("--redis-url-env", default="FBBP_A2A_REDIS_URL")
    parser.add_argument("--key-prefix", default="fbbp:a2a")
    parser.add_argument("--create-probe-task", action="store_true")
    args = parser.parse_args()

    if args.redis_url:
        os.environ[args.redis_url_env] = args.redis_url

    config = {
        "queue_backend": "redis",
        "max_attempts": 1,
        "backoff_seconds": 0,
        "redis": {
            "url_env": args.redis_url_env,
            "key_prefix": args.key_prefix,
        },
    }
    try:
        health = queue_health(config=config)
        redis_status = health["backend_status"]["redis"]
        result = {
            "ok": bool(redis_status["available"]),
            "backend": health["backend_status"]["selected_backend"],
            "redis_available": redis_status["available"],
            "redis_module_installed": redis_status["module_installed"],
            "url_env": redis_status["url_env"],
            "url_configured": redis_status["url_configured"],
            "configured_url": _redact_url(args.redis_url or os.environ.get(args.redis_url_env, "")),
            "key_prefix": redis_status["key_prefix"],
        }
        if args.create_probe_task:
            task = create_task(envelope=_probe_task(), input_payload={"query": "probe redis queue"}, config=config)
            result["probe_task_id"] = task["task_id"]
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error_type": type(exc).__name__,
                    "message": str(exc).splitlines()[0][:300],
                    "url_env": args.redis_url_env,
                    "url_configured": bool(args.redis_url or os.environ.get(args.redis_url_env)),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
