from __future__ import annotations

import importlib.util
import json
import os
import re
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def backend_status(config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or {}
    backend = str(config.get("queue_backend") or "file")
    redis_config = config.get("redis") if isinstance(config.get("redis"), dict) else {}
    postgres_config = config.get("postgres") if isinstance(config.get("postgres"), dict) else {}
    redis_url_env = str(redis_config.get("url_env") or "FBBP_A2A_REDIS_URL")
    postgres_dsn_env = str(postgres_config.get("dsn_env") or "FBBP_A2A_POSTGRES_DSN")
    return {
        "selected_backend": backend,
        "file": {
            "available": True,
            "active": backend == "file",
        },
        "redis": {
            "available": _module_available("redis") and bool(os.environ.get(redis_url_env)),
            "active": backend == "redis",
            "module_installed": _module_available("redis"),
            "url_env": redis_url_env,
            "url_configured": bool(os.environ.get(redis_url_env)),
            "key_prefix": redis_config.get("key_prefix") or "fbbp:a2a",
        },
        "postgres": {
            "available": (_module_available("psycopg") or _module_available("psycopg2")) and bool(os.environ.get(postgres_dsn_env)),
            "active": backend == "postgres",
            "module_installed": _module_available("psycopg") or _module_available("psycopg2"),
            "dsn_env": postgres_dsn_env,
            "dsn_configured": bool(os.environ.get(postgres_dsn_env)),
            "table_name": postgres_config.get("table_name") or "fbbp_a2a_tasks",
        },
    }


def external_backend_available(config: dict[str, Any] | None = None) -> bool:
    status = backend_status(config)
    selected = status["selected_backend"]
    if selected == "redis":
        return bool(status["redis"]["available"])
    if selected == "postgres":
        return bool(status["postgres"]["available"])
    return False


def _selected_backend(config: dict[str, Any]) -> str:
    return str(config.get("queue_backend") or "file")


def _redis_client(config: dict[str, Any]):
    redis_config = config.get("redis") if isinstance(config.get("redis"), dict) else {}
    url = os.environ.get(str(redis_config.get("url_env") or "FBBP_A2A_REDIS_URL"))
    if not url:
        raise RuntimeError("Redis queue backend requires Redis URL env")
    import redis  # type: ignore

    return redis.from_url(url, decode_responses=True)


def _redis_key(config: dict[str, Any], *parts: str) -> str:
    redis_config = config.get("redis") if isinstance(config.get("redis"), dict) else {}
    prefix = str(redis_config.get("key_prefix") or "fbbp:a2a")
    return ":".join([prefix, *parts])


def _pg_connect(config: dict[str, Any]):
    pg_config = config.get("postgres") if isinstance(config.get("postgres"), dict) else {}
    dsn = os.environ.get(str(pg_config.get("dsn_env") or "FBBP_A2A_POSTGRES_DSN"))
    if not dsn:
        raise RuntimeError("Postgres queue backend requires DSN env")
    dsn = _with_pg_connect_timeout(dsn, pg_config.get("connect_timeout_seconds", 5))
    try:
        import psycopg  # type: ignore

        return psycopg.connect(dsn)
    except ModuleNotFoundError:
        import psycopg2  # type: ignore

        return psycopg2.connect(dsn)


def _with_pg_connect_timeout(dsn: str, timeout_seconds: Any) -> str:
    if "connect_timeout=" in dsn:
        return dsn
    try:
        timeout = max(int(timeout_seconds), 1)
    except (TypeError, ValueError):
        timeout = 5
    parts = urlsplit(dsn)
    addition = urlencode({"connect_timeout": str(timeout)})
    query = f"{parts.query}&{addition}" if parts.query else addition
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def _pg_table(config: dict[str, Any]) -> str:
    pg_config = config.get("postgres") if isinstance(config.get("postgres"), dict) else {}
    table = str(pg_config.get("table_name") or "fbbp_a2a_tasks")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
        raise ValueError("Invalid postgres table_name")
    return table


def _pg_events_table(config: dict[str, Any]) -> str:
    return f"{_pg_table(config)}_events"


def initialize_external_backend(config: dict[str, Any]) -> None:
    backend = _selected_backend(config)
    if backend == "redis":
        _redis_client(config).ping()
        return
    if backend == "postgres":
        table = _pg_table(config)
        events_table = _pg_events_table(config)
        with _pg_connect(config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {table} (
                        task_id TEXT PRIMARY KEY,
                        queue_state TEXT NOT NULL,
                        status TEXT NOT NULL,
                        next_attempt_epoch DOUBLE PRECISION,
                        payload TEXT NOT NULL,
                        updated_at TIMESTAMPTZ DEFAULT now()
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {events_table} (
                        id BIGSERIAL PRIMARY KEY,
                        task_id TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        created_at TIMESTAMPTZ DEFAULT now()
                    )
                    """
                )
            conn.commit()


def put_task(config: dict[str, Any], task: dict[str, Any]) -> None:
    backend = _selected_backend(config)
    if backend == "redis":
        client = _redis_client(config)
        task_id = str(task["task_id"])
        current = get_task(config, task_id)
        if current:
            client.srem(_redis_key(config, "state", str(current.get("queue_state") or "pending")), task_id)
        client.set(_redis_key(config, "task", task_id), json.dumps(task, ensure_ascii=False))
        client.sadd(_redis_key(config, "state", str(task.get("queue_state") or "pending")), task_id)
        return
    if backend == "postgres":
        initialize_external_backend(config)
        table = _pg_table(config)
        payload = json.dumps(task, ensure_ascii=False)
        with _pg_connect(config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO {table} (task_id, queue_state, status, next_attempt_epoch, payload, updated_at)
                    VALUES (%s, %s, %s, %s, %s, now())
                    ON CONFLICT (task_id) DO UPDATE SET
                        queue_state = EXCLUDED.queue_state,
                        status = EXCLUDED.status,
                        next_attempt_epoch = EXCLUDED.next_attempt_epoch,
                        payload = EXCLUDED.payload,
                        updated_at = now()
                    """,
                    (
                        str(task["task_id"]),
                        str(task.get("queue_state") or "pending"),
                        str(task.get("status") or ""),
                        float(task.get("next_attempt_epoch") or 0),
                        payload,
                    ),
                )
            conn.commit()


def get_task(config: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    backend = _selected_backend(config)
    if backend == "redis":
        raw = _redis_client(config).get(_redis_key(config, "task", task_id))
        return json.loads(raw) if raw else None
    if backend == "postgres":
        initialize_external_backend(config)
        table = _pg_table(config)
        with _pg_connect(config) as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT payload FROM {table} WHERE task_id = %s", (task_id,))
                row = cur.fetchone()
                return json.loads(row[0]) if row else None
    raise RuntimeError(f"Unsupported external queue backend: {backend}")


def iter_tasks(config: dict[str, Any], queue_state: str) -> list[dict[str, Any]]:
    backend = _selected_backend(config)
    if backend == "redis":
        client = _redis_client(config)
        tasks: list[dict[str, Any]] = []
        for task_id in sorted(client.smembers(_redis_key(config, "state", queue_state))):
            raw = client.get(_redis_key(config, "task", task_id))
            if raw:
                tasks.append(json.loads(raw))
        return tasks
    if backend == "postgres":
        initialize_external_backend(config)
        table = _pg_table(config)
        with _pg_connect(config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT payload FROM {table} WHERE queue_state = %s ORDER BY updated_at ASC",
                    (queue_state,),
                )
                return [json.loads(row[0]) for row in cur.fetchall()]
    raise RuntimeError(f"Unsupported external queue backend: {backend}")


def append_event(config: dict[str, Any], task_id: str, event: dict[str, Any]) -> None:
    backend = _selected_backend(config)
    if backend == "redis":
        _redis_client(config).rpush(_redis_key(config, "events", task_id), json.dumps(event, ensure_ascii=False))
        return
    if backend == "postgres":
        initialize_external_backend(config)
        events_table = _pg_events_table(config)
        with _pg_connect(config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"INSERT INTO {events_table} (task_id, payload, created_at) VALUES (%s, %s, now())",
                    (task_id, json.dumps(event, ensure_ascii=False)),
                )
            conn.commit()
        return
    raise RuntimeError(f"Unsupported external queue backend: {backend}")


def list_events(config: dict[str, Any], task_id: str) -> list[dict[str, Any]]:
    backend = _selected_backend(config)
    if backend == "redis":
        return [json.loads(item) for item in _redis_client(config).lrange(_redis_key(config, "events", task_id), 0, -1)]
    if backend == "postgres":
        initialize_external_backend(config)
        events_table = _pg_events_table(config)
        with _pg_connect(config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT payload FROM {events_table} WHERE task_id = %s ORDER BY id ASC",
                    (task_id,),
                )
                return [json.loads(row[0]) for row in cur.fetchall()]
    raise RuntimeError(f"Unsupported external queue backend: {backend}")


def counts(config: dict[str, Any]) -> dict[str, int]:
    return {
        state: len(iter_tasks(config, state))
        for state in ("pending", "running", "completed", "failed")
    }
