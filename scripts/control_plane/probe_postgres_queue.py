from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit, urlunsplit


SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from control_plane.worker_queue import create_task, queue_health
from control_plane.a2a import A2A_SCHEMA_VERSION


REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _with_connect_timeout(dsn: str, timeout_seconds: int) -> str:
    if "connect_timeout=" in dsn:
        return dsn
    parts = urlsplit(dsn)
    query = parts.query
    addition = urlencode({"connect_timeout": str(timeout_seconds)})
    query = f"{query}&{addition}" if query else addition
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def _dsn_from_env(values: dict[str, str], *, host_override: str | None = None, connect_timeout: int = 5) -> str:
    host = host_override or values.get("PGHOST") or "localhost"
    port = values.get("PGPORT") or "5432"
    database = values.get("PGDATABASE") or "ragkb"
    user = values.get("PGUSER") or "ragkb"
    password = values.get("PGPASSWORD") or ""
    dsn = f"postgresql://{quote(user)}:{quote(password)}@{host}:{port}/{quote(database)}"
    return _with_connect_timeout(dsn, connect_timeout)


def _redact(message: str, secrets: list[str]) -> str:
    redacted = message
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "***")
            redacted = redacted.replace(quote(secret), "***")
    return redacted


def _probe_task() -> dict[str, object]:
    return {
        "schema_version": A2A_SCHEMA_VERSION,
        "message_id": "msg_probe_postgres_queue",
        "correlation_id": "a2ac_probe_postgres_queue",
        "message_type": "child_run_request",
        "phase": "requested",
        "trace_id": "trace_probe_postgres_queue",
        "parent_run_id": "trace_probe_postgres_queue",
        "child_run_id": "task_probe_postgres_queue",
        "hop_index": 1,
        "source_agent": "probe",
        "target_agent": "fbbp-control-plane",
        "route": "fallback_general",
        "status": "requested",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe the A2A Postgres queue backend without printing secrets.")
    parser.add_argument("--env-path", default=str((REPO_ROOT.parent / "llm-rag-knowledge-base" / ".env").resolve()))
    parser.add_argument("--host-override")
    parser.add_argument("--connect-timeout", type=int, default=5)
    parser.add_argument("--create-probe-task", action="store_true")
    args = parser.parse_args()

    values = _read_env(Path(args.env_path))
    dsn = os.environ.get("FBBP_A2A_POSTGRES_DSN") or _dsn_from_env(
        values,
        host_override=args.host_override,
        connect_timeout=max(args.connect_timeout, 1),
    )
    dsn = _with_connect_timeout(dsn, max(args.connect_timeout, 1))
    os.environ["FBBP_A2A_POSTGRES_DSN"] = dsn
    config = {
        "queue_backend": "postgres",
        "max_attempts": 1,
        "backoff_seconds": 0,
        "postgres": {
            "dsn_env": "FBBP_A2A_POSTGRES_DSN",
            "table_name": "fbbp_a2a_tasks",
        },
    }
    try:
        health = queue_health(config=config)
        result = {
            "ok": bool(health["backend_status"]["postgres"]["available"]),
            "backend": health["backend_status"]["selected_backend"],
            "postgres_available": health["backend_status"]["postgres"]["available"],
            "postgres_module_installed": health["backend_status"]["postgres"]["module_installed"],
            "dsn_configured": health["backend_status"]["postgres"]["dsn_configured"],
            "host": args.host_override or values.get("PGHOST") or "localhost",
            "database": values.get("PGDATABASE") or "ragkb",
            "user": values.get("PGUSER") or "ragkb",
        }
        if args.create_probe_task:
            task = create_task(envelope=_probe_task(), input_payload={"query": "probe postgres queue"}, config=config)
            result["probe_task_id"] = task["task_id"]
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        safe_message = _redact(str(exc).splitlines()[0][:300], [values.get("PGPASSWORD", "")])
        print(
            json.dumps(
                {
                    "ok": False,
                    "error_type": type(exc).__name__,
                    "message": safe_message,
                    "host": args.host_override or values.get("PGHOST") or "localhost",
                    "database": values.get("PGDATABASE") or "ragkb",
                    "user": values.get("PGUSER") or "ragkb",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
