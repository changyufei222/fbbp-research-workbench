from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from formal_run_lib import load_yaml_config

from control_plane.resume import find_recent_thread_runs
from control_plane.semantic_memory import retrieve_semantic_memory, upsert_memory_from_run


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MEMORY_POLICY = REPO_ROOT / "configs" / "control_plane" / "memory_policy.yaml"


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def _default_profile_memory() -> dict[str, Any]:
    return {
        "version": "1.0",
        "lastUpdated": _now_utc(),
        "user": {
            "workContext": {"summary": "", "updatedAt": ""},
            "preferences": {"summary": "", "updatedAt": ""},
        },
        "history": {
            "recentSessions": {"summary": "", "updatedAt": ""},
        },
        "facts": [],
    }


def _normalize_profile_memory(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or not payload:
        return _default_profile_memory()
    base = _default_profile_memory()
    base.update({key: value for key, value in payload.items() if key in {"version", "lastUpdated", "user", "history", "facts"}})
    if not isinstance(base.get("user"), dict):
        base["user"] = _default_profile_memory()["user"]
    if not isinstance(base.get("history"), dict):
        base["history"] = _default_profile_memory()["history"]
    if not isinstance(base.get("facts"), list):
        base["facts"] = []
    return base


def load_memory_policy(path: Path | None = None) -> dict[str, Any]:
    return load_yaml_config(path or DEFAULT_MEMORY_POLICY)


def _profile_memory_path(repo_root: Path, policy: dict[str, Any]) -> Path:
    agent_name = str(policy.get("agent_name") or "fbbp-assistant")
    return repo_root / "configs" / "agents" / agent_name / "memory.json"


def load_profile_memory(repo_root: Path, policy: dict[str, Any]) -> dict[str, Any]:
    path = _profile_memory_path(repo_root, policy)
    if not path.exists():
        return _default_profile_memory()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _default_profile_memory()
    return _normalize_profile_memory(payload)


def save_profile_memory(repo_root: Path, policy: dict[str, Any], payload: dict[str, Any]) -> str:
    path = _profile_memory_path(repo_root, policy)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = _normalize_profile_memory(payload)
    normalized["lastUpdated"] = _now_utc()
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _build_session_summary(recent_runs: list[dict[str, Any]], char_limit: int) -> str:
    if not recent_runs:
        return ""
    lines: list[str] = []
    for item in recent_runs:
        line = f"{item.get('run_id')}: route={item.get('primary_route')} status={item.get('status')} query={item.get('query_preview') or ''}"
        lines.append(" ".join(line.split()))
    summary = " | ".join(lines)
    if len(summary) > char_limit:
        return summary[: char_limit - 3] + "..."
    return summary


def _build_profile_summary_text(
    request: dict[str, Any],
    route_decision: dict[str, Any],
    result_summary: dict[str, Any],
    *,
    char_limit: int = 240,
) -> str:
    route = str(route_decision.get("primary_route") or "unknown")
    status = str(result_summary.get("status") or "")
    query = str(request.get("query") or "").strip()
    case_path = str(request.get("case_path") or "").strip()
    batch_path = str(request.get("batch_path") or "").strip()
    report_json = str(request.get("report_json") or "").strip()

    if query:
        summary = f"route={route}; query={query}"
    elif case_path:
        summary = f"route={route}; case={Path(case_path).name}; status={status or 'completed'}"
    elif batch_path:
        summary = f"route={route}; batch={Path(batch_path).name}; status={status or 'completed'}"
    elif report_json:
        summary = f"route={route}; report={Path(report_json).name}; status={status or 'completed'}"
    else:
        summary = f"route={route}; status={status or 'completed'}"

    normalized = " ".join(summary.split())
    if len(normalized) > char_limit:
        return normalized[: char_limit - 3] + "..."
    return normalized


def build_memory_context(repo_root: Path, request: dict[str, Any], route_decision: dict[str, Any]) -> dict[str, Any]:
    policy = load_memory_policy()
    profile_enabled = bool(((policy.get("profile_memory") or {}).get("enabled")))
    session_enabled = bool(((policy.get("session_memory") or {}).get("enabled")))
    thread_id = str(request.get("thread_id") or "")

    profile_memory = load_profile_memory(repo_root, policy) if profile_enabled else _default_profile_memory()
    recent_runs: list[dict[str, Any]] = []
    if session_enabled and thread_id:
        lookback = int(((policy.get("session_memory") or {}).get("lookback_runs")) or 5)
        recent_runs = find_recent_thread_runs(repo_root / "runs" / "control_plane", thread_id, limit=lookback)

    char_limit = int(((policy.get("session_memory") or {}).get("summary_char_limit")) or 400)
    session_summary = _build_session_summary(recent_runs, char_limit)
    semantic_hits: list[dict[str, Any]] = []
    query_text = str(request.get("query") or "")
    if query_text:
        semantic_hits = retrieve_semantic_memory(repo_root, query_text, top_k=5).get("hits", [])
    work_context = ((profile_memory.get("user") or {}).get("workContext") or {}).get("summary") or ""
    preferences = ((profile_memory.get("user") or {}).get("preferences") or {}).get("summary") or ""

    return {
        "thread_id": thread_id or None,
        "profile_memory_enabled": profile_enabled,
        "session_memory_enabled": session_enabled,
        "profile_memory_path": str(_profile_memory_path(repo_root, policy)),
        "profile_summary": {
            "work_context": work_context,
            "preferences": preferences,
        },
        "recent_runs": recent_runs,
        "session_summary": session_summary,
        "semantic_hits": semantic_hits,
        "read_hit": bool(recent_runs or work_context or preferences),
        "resume_used": bool(recent_runs),
        "policy": policy,
        "route": route_decision.get("primary_route"),
    }


def write_memory_artifacts(run_dir: Path, memory_context: dict[str, Any]) -> None:
    memory_dir = run_dir / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    (memory_dir / "session_memory.json").write_text(
        json.dumps(
            {
                "thread_id": memory_context.get("thread_id"),
                "recent_runs": memory_context.get("recent_runs", []),
                "semantic_hits": memory_context.get("semantic_hits", []),
                "read_hit": memory_context.get("read_hit", False),
                "resume_used": memory_context.get("resume_used", False),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (memory_dir / "summary.json").write_text(
        json.dumps(
            {
                "profile_summary": memory_context.get("profile_summary", {}),
                "session_summary": memory_context.get("session_summary", ""),
                "semantic_hit_count": len(memory_context.get("semantic_hits", []) or []),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def update_memory_after_run(
    repo_root: Path,
    run_dir: Path,
    request: dict[str, Any],
    route_decision: dict[str, Any],
    result_summary: dict[str, Any],
) -> dict[str, Any]:
    policy = load_memory_policy()
    memory_dir = run_dir / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    session_payload = {
        "thread_id": request.get("thread_id"),
        "primary_route": route_decision.get("primary_route"),
        "query": request.get("query"),
        "result_summary": result_summary,
        "written_at_utc": _now_utc(),
    }
    (memory_dir / "resume_state.json").write_text(
        json.dumps(session_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (memory_dir / "write_log.jsonl").write_text(
        json.dumps(
            {
                "timestamp_utc": _now_utc(),
                "event": "session_memory_written",
                "thread_id": request.get("thread_id"),
                "primary_route": route_decision.get("primary_route"),
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    profile_policy = policy.get("profile_memory") or {}
    auto_write = bool(profile_policy.get("auto_write"))
    promote_keywords = [str(item).lower() for item in profile_policy.get("promote_on_keywords", [])]
    query_text = str(request.get("query") or "")
    lowered_query = query_text.lower()
    explicit_promote = any(keyword and keyword in lowered_query for keyword in promote_keywords)
    profile_summary_text = _build_profile_summary_text(request, route_decision, result_summary)
    profile_written = False
    profile_path = str(_profile_memory_path(repo_root, policy))
    if (auto_write or explicit_promote) and profile_summary_text:
        profile_payload = load_profile_memory(repo_root, policy)
        profile_payload.setdefault("user", {}).setdefault("workContext", {})
        profile_payload.setdefault("history", {}).setdefault("recentSessions", {})
        profile_payload["user"]["workContext"] = {
            "summary": profile_summary_text,
            "updatedAt": _now_utc(),
        }
        profile_payload["history"]["recentSessions"] = {
            "summary": profile_summary_text,
            "updatedAt": _now_utc(),
        }
        save_profile_memory(repo_root, policy, profile_payload)
        profile_written = True

    semantic_result = upsert_memory_from_run(
        repo_root,
        request,
        route_decision,
        result_summary,
        run_id=run_dir.name,
        policy=policy,
    )

    return {
        "read_hit": None,
        "resume_used": None,
        "write_status": "session_written",
        "profile_written": profile_written,
        "profile_memory_path": profile_path,
        "resume_state_path": str(memory_dir / "resume_state.json"),
        "semantic_memory": semantic_result,
    }
