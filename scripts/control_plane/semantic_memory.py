from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any


SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from formal_run_lib import load_yaml_config


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MEMORY_POLICY = REPO_ROOT / "configs" / "control_plane" / "memory_policy.yaml"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "control_plane_portfolio_dashboard" / "latest"
DEFAULT_RUN_ROOT = REPO_ROOT / "runs" / "control_plane"
TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def load_memory_policy(path: Path | None = None) -> dict[str, Any]:
    return load_yaml_config(path or DEFAULT_MEMORY_POLICY)


def semantic_config(policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = policy or load_memory_policy()
    config = policy.get("semantic_memory") if isinstance(policy.get("semantic_memory"), dict) else {}
    return {
        "enabled": bool(config.get("enabled", True)),
        "store_path": str(config.get("store_path") or "runs/control_plane/memory/semantic_memory.json"),
        "max_items": int(config.get("max_items") or 500),
        "max_conflicts_per_key": int(config.get("max_conflicts_per_key") or 5),
        "similarity_threshold": float(config.get("similarity_threshold") or 0.35),
        "conflict_threshold": float(config.get("conflict_threshold") or 0.22),
        "promote_statuses": [str(item) for item in config.get("promote_statuses", [])],
        "promote_routes": [str(item) for item in config.get("promote_routes", [])],
    }


def semantic_store_path(repo_root: Path = REPO_ROOT, policy: dict[str, Any] | None = None) -> Path:
    configured = Path(semantic_config(policy)["store_path"])
    return configured if configured.is_absolute() else repo_root / configured


def _default_store() -> dict[str, Any]:
    return {
        "schema_version": "fbbp.semantic_memory.v1",
        "updated_at_utc": _now_utc(),
        "items": [],
        "conflicts": [],
        "stats": {"item_count": 0, "conflict_count": 0},
    }


def load_semantic_memory(repo_root: Path = REPO_ROOT, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    path = semantic_store_path(repo_root, policy)
    if not path.exists():
        return _default_store()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _default_store()
    if not isinstance(payload, dict):
        return _default_store()
    payload.setdefault("schema_version", "fbbp.semantic_memory.v1")
    payload.setdefault("items", [])
    payload.setdefault("conflicts", [])
    payload.setdefault("stats", {})
    return payload


def _load_json_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def save_semantic_memory(store: dict[str, Any], repo_root: Path = REPO_ROOT, policy: dict[str, Any] | None = None) -> str:
    path = semantic_store_path(repo_root, policy)
    path.parent.mkdir(parents=True, exist_ok=True)
    store["updated_at_utc"] = _now_utc()
    store["stats"] = {"item_count": len(store.get("items") or []), "conflict_count": len(store.get("conflicts") or [])}
    path.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text or "") if token.strip()]


def _vector(text: str) -> Counter[str]:
    return Counter(tokenize(text))


def similarity(a: str, b: str) -> float:
    va = _vector(a)
    vb = _vector(b)
    if not va or not vb:
        return 0.0
    dot = sum(va[token] * vb.get(token, 0) for token in va)
    norm_a = math.sqrt(sum(value * value for value in va.values()))
    norm_b = math.sqrt(sum(value * value for value in vb.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return round(dot / (norm_a * norm_b), 4)


def _stable_id(text: str) -> str:
    return "mem_" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def _memory_key(route: str, text: str) -> str:
    tokens = [token for token in tokenize(text) if len(token) > 1][:8]
    raw = f"{route}:" + "-".join(tokens)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _has_source_run(item: dict[str, Any], run_id: str | None) -> bool:
    return bool(run_id and run_id in (item.get("source_run_ids") or []))


def _extract_text(request: dict[str, Any], route_decision: dict[str, Any], result_summary: dict[str, Any]) -> str:
    route = str(route_decision.get("primary_route") or "unknown")
    query = str(request.get("query") or "").strip()
    case_path = str(request.get("case_path") or "").strip()
    batch_path = str(request.get("batch_path") or "").strip()
    message = str(result_summary.get("message") or result_summary.get("summary") or "").strip()
    parts = [f"route={route}"]
    if query:
        parts.append(f"query={query}")
    if case_path:
        parts.append(f"case={Path(case_path).name}")
    if batch_path:
        parts.append(f"batch={Path(batch_path).name}")
    if message:
        parts.append(f"result={message}")
    return "; ".join(parts)


def _status_allowed(status: str, config: dict[str, Any]) -> bool:
    promote_statuses = {str(item) for item in config.get("promote_statuses") or []}
    return not promote_statuses or status in promote_statuses


def upsert_memory_from_run(
    repo_root: Path,
    request: dict[str, Any],
    route_decision: dict[str, Any],
    result_summary: dict[str, Any],
    *,
    run_id: str | None = None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = policy or load_memory_policy()
    config = semantic_config(policy)
    if not config["enabled"]:
        return {"enabled": False, "written": False, "conflict": False}
    route = str(route_decision.get("primary_route") or "unknown")
    status = str(result_summary.get("run_status") or result_summary.get("status") or "")
    if status and not _status_allowed(status, config):
        return {"enabled": True, "written": False, "conflict": False, "reason": "status_not_promoted", "status": status}
    promote_routes = set(config.get("promote_routes") or [])
    if promote_routes and route not in promote_routes:
        return {"enabled": True, "written": False, "conflict": False, "reason": "route_not_promoted"}

    text = _extract_text(request, route_decision, result_summary)
    if not text.strip():
        return {"enabled": True, "written": False, "conflict": False, "reason": "empty_text"}

    store = load_semantic_memory(repo_root, policy)
    items = store.setdefault("items", [])
    conflicts = store.setdefault("conflicts", [])
    if run_id:
        existing_source_item = next((item for item in items if _has_source_run(item, run_id)), None)
        if existing_source_item:
            return {
                "enabled": True,
                "written": True,
                "conflict": False,
                "action": "unchanged",
                "item_id": existing_source_item.get("id"),
                "similarity": 1.0,
                "semantic_memory_path": str(semantic_store_path(repo_root, policy)),
            }
    key = _memory_key(route, text)
    item_id = _stable_id(f"{key}:{text}")
    best_item = None
    best_score = 0.0
    for item in items:
        if item.get("route") != route:
            continue
        score = similarity(text, str(item.get("text") or ""))
        if score > best_score:
            best_score = score
            best_item = item

    conflict = False
    action = "inserted"
    if best_item and best_score >= config["similarity_threshold"]:
        duplicate_source = _has_source_run(best_item, run_id)
        best_item["text"] = text if len(text) > len(str(best_item.get("text") or "")) else best_item.get("text")
        best_item["updated_at_utc"] = _now_utc()
        best_item.setdefault("source_run_ids", [])
        if not duplicate_source:
            best_item["hit_count"] = int(best_item.get("hit_count") or 1) + 1
        if run_id and run_id not in best_item["source_run_ids"]:
            best_item["source_run_ids"].append(run_id)
        action = "unchanged" if duplicate_source else "merged"
        item_id = str(best_item.get("id") or item_id)
    else:
        if best_item and config["conflict_threshold"] <= best_score < config["similarity_threshold"]:
            conflict = True
            conflicts.append(
                {
                    "id": "conflict_" + hashlib.sha1(f"{item_id}:{best_item.get('id')}".encode("utf-8")).hexdigest()[:12],
                    "created_at_utc": _now_utc(),
                    "route": route,
                    "new_item_id": item_id,
                    "existing_item_id": best_item.get("id"),
                    "similarity": best_score,
                    "status": "needs_review",
                    "reason": "same_route_not_merged",
                }
            )
        items.append(
            {
                "id": item_id,
                "key": key,
                "route": route,
                "text": text,
                "tokens": tokenize(text)[:40],
                "created_at_utc": _now_utc(),
                "updated_at_utc": _now_utc(),
                "hit_count": 1,
                "source_run_ids": [run_id] if run_id else [],
            }
        )

    items[:] = sorted(items, key=lambda item: str(item.get("updated_at_utc") or ""), reverse=True)[: config["max_items"]]
    conflicts[:] = conflicts[-config["max_conflicts_per_key"] * 20 :]
    path = save_semantic_memory(store, repo_root, policy)
    return {
        "enabled": True,
        "written": True,
        "conflict": conflict,
        "action": action,
        "item_id": item_id,
        "similarity": best_score,
        "semantic_memory_path": path,
    }


def _request_from_run_record(run_dir: Path, record: dict[str, Any]) -> dict[str, Any]:
    files = record.get("files") if isinstance(record.get("files"), dict) else {}
    candidates = [Path(str(files.get("run_request")))] if files.get("run_request") else []
    candidates.append(run_dir / "run_request.json")
    request: dict[str, Any] = {}
    for path in candidates:
        request = _load_json_file(path)
        if request:
            break
    summary = record.get("request_summary") if isinstance(record.get("request_summary"), dict) else {}
    if summary:
        request.setdefault("query", summary.get("query_preview"))
        request.setdefault("case_path", summary.get("case_path"))
        request.setdefault("batch_path", summary.get("batch_path"))
        request.setdefault("run_dir", summary.get("run_dir"))
        request.setdefault("thread_id", summary.get("thread_id"))
    return request


def _route_from_run_record(run_dir: Path, record: dict[str, Any]) -> dict[str, Any]:
    files = record.get("files") if isinstance(record.get("files"), dict) else {}
    candidates = [Path(str(files.get("route_decision")))] if files.get("route_decision") else []
    candidates.append(run_dir / "route_decision.json")
    route = {}
    for path in candidates:
        route = _load_json_file(path)
        if route:
            break
    route.setdefault("primary_route", record.get("primary_route") or "unknown")
    route.setdefault("secondary_capabilities", record.get("secondary_capabilities") or [])
    return route


def backfill_memory_from_runs(
    repo_root: Path = REPO_ROOT,
    input_root: Path = DEFAULT_RUN_ROOT,
    *,
    reset: bool = False,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = policy or load_memory_policy()
    if reset:
        save_semantic_memory(_default_store(), repo_root, policy)

    stats = {
        "records_seen": 0,
        "records_promoted": 0,
        "inserted": 0,
        "merged": 0,
        "conflicts": 0,
        "skipped": 0,
        "semantic_memory_path": str(semantic_store_path(repo_root, policy)),
    }
    if not input_root.exists():
        return stats

    for record_path in sorted(input_root.rglob("run_record.json")):
        record = _load_json_file(record_path)
        if not record:
            continue
        stats["records_seen"] += 1
        run_dir = record_path.parent
        request = _request_from_run_record(run_dir, record)
        route_decision = _route_from_run_record(run_dir, record)
        result_summary = record.get("result_summary") if isinstance(record.get("result_summary"), dict) else {}
        if not result_summary:
            result_summary = {"summary": record.get("status") or "completed"}
        result_summary = dict(result_summary)
        result_summary["run_status"] = record.get("status") or "unknown"
        result = upsert_memory_from_run(
            repo_root,
            request,
            route_decision,
            result_summary,
            run_id=str(record.get("run_id") or run_dir.name),
            policy=policy,
        )
        if not result.get("written"):
            stats["skipped"] += 1
            continue
        stats["records_promoted"] += 1
        action = str(result.get("action") or "inserted")
        if action in {"inserted", "merged"}:
            stats[action] += 1
        if result.get("conflict"):
            stats["conflicts"] += 1
    store = load_semantic_memory(repo_root, policy)
    stats["item_count"] = len(store.get("items") or [])
    stats["conflict_count"] = len(store.get("conflicts") or [])
    return stats


def resolve_memory_conflict(
    repo_root: Path,
    conflict_id: str,
    action: str,
    *,
    note: str = "",
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if action not in {"merge", "dismiss", "keep_new", "keep_existing"}:
        raise ValueError("action must be one of: merge, dismiss, keep_new, keep_existing")
    store = load_semantic_memory(repo_root, policy)
    conflicts = store.get("conflicts") if isinstance(store.get("conflicts"), list) else []
    conflict = next((item for item in conflicts if item.get("id") == conflict_id), None)
    if not conflict:
        return {"resolved": False, "reason": "conflict_not_found"}

    items = store.get("items") if isinstance(store.get("items"), list) else []
    new_item = next((item for item in items if item.get("id") == conflict.get("new_item_id")), None)
    existing_item = next((item for item in items if item.get("id") == conflict.get("existing_item_id")), None)

    if action == "merge":
        if not new_item or not existing_item:
            return {"resolved": False, "reason": "merge_items_not_found"}
        existing_text = str(existing_item.get("text") or "")
        new_text = str(new_item.get("text") or "")
        if new_text and new_text not in existing_text:
            existing_item["text"] = f"{existing_text}\nMERGED MEMORY: {new_text}".strip()
        existing_item["updated_at_utc"] = _now_utc()
        existing_item["hit_count"] = int(existing_item.get("hit_count") or 0) + int(new_item.get("hit_count") or 1)
        existing_sources = list(existing_item.get("source_run_ids") or [])
        for source_id in new_item.get("source_run_ids") or []:
            if source_id not in existing_sources:
                existing_sources.append(source_id)
        existing_item["source_run_ids"] = existing_sources
        items[:] = [item for item in items if item.get("id") != new_item.get("id")]
    elif action == "keep_existing" and new_item:
        items[:] = [item for item in items if item.get("id") != new_item.get("id")]

    conflict["status"] = f"resolved_{action}"
    conflict["resolved_at_utc"] = _now_utc()
    conflict["resolution_note"] = note
    path = save_semantic_memory(store, repo_root, policy)
    return {"resolved": True, "action": action, "semantic_memory_path": path}


def retrieve_semantic_memory(repo_root: Path, query: str, *, top_k: int = 5, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    store = load_semantic_memory(repo_root, policy)
    scored = []
    for item in store.get("items") or []:
        score = similarity(query, str(item.get("text") or ""))
        if score > 0:
            scored.append({"score": score, "item": item})
    scored.sort(key=lambda row: row["score"], reverse=True)
    return {"query": query, "hits": scored[:top_k], "store_stats": store.get("stats", {})}


def write_memory_dashboard(repo_root: Path = REPO_ROOT, output_root: Path = DEFAULT_OUTPUT_ROOT) -> dict[str, str]:
    store = load_semantic_memory(repo_root)
    output_root.mkdir(parents=True, exist_ok=True)
    json_path = output_root / "semantic_memory.json"
    html_path = output_root / "semantic_memory.html"
    json_path.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    route_counts = Counter(str(item.get("route") or "unknown") for item in store.get("items", []))
    rows = []
    for item in store.get("items", [])[:100]:
        rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('route') or ''))}</td>"
            f"<td>{escape(str(item.get('hit_count') or 0))}</td>"
            f"<td>{escape(str(item.get('updated_at_utc') or ''))}</td>"
            f"<td>{escape(str(item.get('text') or ''))}<br><small>{escape(str(item.get('id') or ''))}</small></td>"
            "</tr>"
        )
    conflict_rows = []
    for item in store.get("conflicts", [])[-50:]:
        conflict_rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('id') or ''))}</td>"
            f"<td>{escape(str(item.get('route') or ''))}</td>"
            f"<td>{escape(str(item.get('similarity') or ''))}</td>"
            f"<td>{escape(str(item.get('status') or ''))}</td>"
            f"<td>{escape(str(item.get('reason') or ''))}</td>"
            "</tr>"
        )
    memory_state = {
        "schema_version": "fbbp.semantic_memory.viewer.v2",
        "mode": "live_local_control_console",
        "generated_at_utc": store.get("updated_at_utc"),
        "stats": {
            "item_count": len(store.get("items") or []),
            "conflict_count": len(store.get("conflicts") or []),
        },
        "route_counts": dict(route_counts),
        "items": (store.get("items") or [])[:120],
        "conflicts": (store.get("conflicts") or [])[-120:],
        "service_endpoints": {
            "health": "http://127.0.0.1:8088/health",
            "snapshot": "http://127.0.0.1:8088/api/snapshot",
            "semantic_memory": "http://127.0.0.1:8088/api/semantic-memory",
            "rebuild": "http://127.0.0.1:8088/api/rebuild",
        },
    }
    memory_state_json = json.dumps(memory_state, ensure_ascii=False).replace("</", "<\\/")
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>FBBP Semantic Memory</title>
  <style>
    :root {{ --ink:#17211b; --muted:#5b6b61; --line:#d7e1d8; --panel:#f8fbf5; --accent:#1c7c54; --warn:#b85c38; --teal:#235b67; }}
    body {{ margin:0; font-family: Georgia, 'Noto Serif SC', serif; color:var(--ink); background:linear-gradient(135deg,#f5f1e8,#edf7ef 48%,#e8f1f7); }}
    main {{ max-width:1180px; margin:0 auto; padding:42px 22px; }}
    h1 {{ font-size:42px; margin:0 0 8px; letter-spacing:-.03em; }}
    .lede {{ color:var(--muted); font-size:18px; max-width:820px; }}
    .cards {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:16px; margin:28px 0; }}
    .card {{ background:rgba(255,255,255,.75); border:1px solid var(--line); border-radius:22px; padding:18px; box-shadow:0 20px 50px rgba(37,61,45,.08); }}
    .num {{ font-size:34px; font-weight:700; color:var(--accent); }}
    .console {{ display:grid; grid-template-columns:1.1fr .9fr; gap:18px; margin:0 0 24px; align-items:start; }}
    .toolbar {{ display:flex; flex-wrap:wrap; gap:12px; margin-top:18px; }}
    .toolbar label {{ display:flex; flex-direction:column; gap:6px; min-width:160px; font-size:13px; color:var(--muted); }}
    .toolbar input,.toolbar select {{ border:1px solid var(--line); border-radius:14px; padding:10px 12px; font:inherit; background:white; }}
    .toolbar button {{ border:1px solid var(--line); border-radius:14px; padding:10px 14px; font:inherit; background:white; cursor:pointer; }}
    .toolbar button:hover,.route-chip:hover {{ box-shadow:0 10px 24px rgba(37,61,45,.10); transform:translateY(-1px); }}
    .toggle-row {{ display:flex; gap:8px; align-items:center; }}
    .refresh-note {{ color:var(--teal); font-size:13px; }}
    .detail-panel {{ min-height:280px; background:rgba(255,255,255,.75); border:1px solid var(--line); border-radius:22px; padding:18px; box-shadow:0 20px 50px rgba(37,61,45,.08); }}
    .detail-panel pre {{ margin:0; white-space:pre-wrap; word-break:break-word; font-size:13px; line-height:1.55; color:#214438; background:white; border:1px solid var(--line); border-radius:18px; padding:14px; }}
    .route-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; margin-top:14px; }}
    .route-chip {{ border:1px solid var(--line); border-radius:18px; padding:14px; background:white; cursor:pointer; }}
    .route-chip strong {{ display:block; }}
    table {{ width:100%; border-collapse:collapse; background:rgba(255,255,255,.8); border-radius:18px; overflow:hidden; }}
    th,td {{ text-align:left; padding:12px 14px; border-bottom:1px solid var(--line); vertical-align:top; }}
    th {{ background:#e8f3ea; font-size:13px; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); }}
    section {{ margin-top:30px; }}
    .muted {{ color:var(--muted); }}
    .empty {{ color:var(--muted); padding:12px 0; }}
    @media(max-width:900px) {{ .console {{ grid-template-columns:1fr; }} .route-grid {{ grid-template-columns:1fr 1fr; }} }}
    @media(max-width:800px) {{ .cards,.route-grid {{ grid-template-columns:1fr; }} h1 {{ font-size:32px; }} .toolbar label {{ min-width:100%; }} }}
  </style>
</head>
<body>
<main>
  <h1>FBBP Semantic Memory</h1>
  <p class="lede">长期语义记忆、合并和冲突队列。这个页面现在由 dashboard HTTP service 提供，支持 route 过滤、搜索、冲突细查和自动刷新快照。</p>
  <div class="cards">
    <div class="card"><div class="num" id="memoryItemsCount">{len(store.get('items') or [])}</div><div>Memory Items</div></div>
    <div class="card"><div class="num" id="conflictCount">{len(store.get('conflicts') or [])}</div><div>Conflict Records</div></div>
    <div class="card"><div class="num" id="memoryUpdatedAt">{escape(str(store.get('updated_at_utc') or ''))}</div><div>Last Updated</div></div>
  </div>
  <section class="console">
    <div class="card">
      <h2>Memory Console</h2>
      <p class="muted">Route chips、搜索框和 conflict 状态过滤会一起作用在下面两张表上，适合快速确认 memory merge / conflict 的走向。</p>
      <div class="toolbar">
        <label>Route Filter
          <select id="routeFilter">
            <option value="">All routes</option>
          </select>
        </label>
        <label>Conflict Filter
          <select id="conflictFilter">
            <option value="">All conflicts</option>
            <option value="needs_review">needs_review</option>
            <option value="resolved_dismiss">resolved_dismiss</option>
            <option value="resolved_merge">resolved_merge</option>
            <option value="resolved_keep_new">resolved_keep_new</option>
            <option value="resolved_keep_existing">resolved_keep_existing</option>
          </select>
        </label>
        <label>Search Memory
          <input id="searchInput" type="search" placeholder="route / text / id" />
        </label>
        <label>Refresh
          <div class="toggle-row">
            <button id="refreshButton" type="button">Refresh Snapshot</button>
            <input id="autoRefreshToggle" type="checkbox" checked />
            <span>Auto Refresh</span>
          </div>
        </label>
      </div>
      <p class="refresh-note" id="refreshStatus">Embedded snapshot loaded. When served over HTTP, this page prefers `/api/semantic-memory` and falls back to `semantic_memory.json` every 30s.</p>
      <div class="route-grid" id="routeGrid"></div>
    </div>
    <aside class="detail-panel">
      <h2 id="detailTitle">Memory Detail</h2>
      <pre id="detailBody">Click a route chip, memory row, or conflict row to inspect the underlying payload here.</pre>
    </aside>
  </section>
  <section>
    <h2>Memory Items</h2>
    <table><thead><tr><th>Route</th><th>Hits</th><th>Updated</th><th>Text</th></tr></thead><tbody id="memoryRows">{''.join(rows) or '<tr><td colspan="4" class="empty">No memory yet.</td></tr>'}</tbody></table>
  </section>
  <section>
    <h2>Conflict Queue</h2>
    <table><thead><tr><th>Conflict ID</th><th>Route</th><th>Similarity</th><th>Status</th><th>Reason</th></tr></thead><tbody id="conflictRows">{''.join(conflict_rows) or '<tr><td colspan="5" class="empty">No conflicts.</td></tr>'}</tbody></table>
    <p class="lede">Resolve example: python scripts/control_plane/semantic_memory.py --resolve-conflict conflict_id --action merge</p>
  </section>
  <noscript><p class="refresh-note">JavaScript is disabled, so filtering and auto refresh stay unavailable and this page shows only the embedded snapshot.</p></noscript>
</main>
<script id="memory-state" type="application/json">{memory_state_json}</script>
<script>
  function shapeState(payload) {{
    const items = Array.isArray(payload.items) ? payload.items : [];
    const conflicts = Array.isArray(payload.conflicts) ? payload.conflicts : [];
    const routeCounts = items.reduce((acc, item) => {{
      const route = String(item.route || "unknown");
      acc[route] = (acc[route] || 0) + 1;
      return acc;
    }}, {{}});
    return {{
      schema_version: payload.schema_version || "fbbp.semantic_memory.viewer.v2",
      mode: payload.mode || "local_control_console",
      generated_at_utc: payload.generated_at_utc || payload.updated_at_utc || "",
      stats: {{
        item_count: items.length,
        conflict_count: conflicts.length,
      }},
      route_counts: routeCounts,
      items,
      conflicts,
    }};
  }}

  let memoryState = shapeState(JSON.parse(document.getElementById("memory-state").textContent));
  const routeFilter = document.getElementById("routeFilter");
  const conflictFilter = document.getElementById("conflictFilter");
  const searchInput = document.getElementById("searchInput");
  const refreshButton = document.getElementById("refreshButton");
  const autoRefreshToggle = document.getElementById("autoRefreshToggle");
  const refreshStatus = document.getElementById("refreshStatus");
  const detailTitle = document.getElementById("detailTitle");
  const detailBody = document.getElementById("detailBody");
  const serviceEndpoints = memoryState.service_endpoints || {{}};

  function safeText(value) {{
    if (value === null || value === undefined || value === "") {{
      return "n/a";
    }}
    return String(value);
  }}

  function showDetail(title, payload) {{
    detailTitle.textContent = title;
    detailBody.textContent = JSON.stringify(payload, null, 2);
  }}

  function hydrateRouteFilter() {{
    const previous = routeFilter.value;
    const options = Object.keys(memoryState.route_counts || {{}}).sort();
    routeFilter.innerHTML = '<option value="">All routes</option>' + options.map((route) => `<option value="${{route}}">${{route}}</option>`).join("");
    routeFilter.value = options.includes(previous) ? previous : "";
  }}

  function filteredItems() {{
    const route = routeFilter.value.trim();
    const needle = searchInput.value.trim().toLowerCase();
    return (memoryState.items || []).filter((item) => {{
      if (route && String(item.route || "") !== route) return false;
      if (!needle) return true;
      const haystack = [item.route, item.text, item.id, ...(item.source_run_ids || [])].join(" ").toLowerCase();
      return haystack.includes(needle);
    }});
  }}

  function filteredConflicts() {{
    const route = routeFilter.value.trim();
    const status = conflictFilter.value.trim();
    const needle = searchInput.value.trim().toLowerCase();
    return (memoryState.conflicts || []).filter((item) => {{
      if (route && String(item.route || "") !== route) return false;
      if (status && String(item.status || "") !== status) return false;
      if (!needle) return true;
      const haystack = [item.id, item.route, item.status, item.reason, item.new_item_id, item.existing_item_id].join(" ").toLowerCase();
      return haystack.includes(needle);
    }});
  }}

  function renderTopline() {{
    document.getElementById("memoryItemsCount").textContent = safeText(memoryState.stats?.item_count || 0);
    document.getElementById("conflictCount").textContent = safeText(memoryState.stats?.conflict_count || 0);
    document.getElementById("memoryUpdatedAt").textContent = safeText(memoryState.generated_at_utc || "embedded snapshot");
  }}

  function renderRouteGrid() {{
    const container = document.getElementById("routeGrid");
    const cards = Object.entries(memoryState.route_counts || {{}}).sort((a, b) => b[1] - a[1]).map(([route, count]) => `
      <button class="route-chip" type="button" data-route="${{route}}">
        <strong>${{route}}</strong>
        <span>${{count}} memory items</span>
      </button>
    `).join("");
    container.innerHTML = cards || '<p class="empty">No route-level memory yet.</p>';
    container.querySelectorAll("[data-route]").forEach((node) => {{
      node.addEventListener("click", () => {{
        const route = node.getAttribute("data-route");
        routeFilter.value = route;
        renderTables();
        const items = (memoryState.items || []).filter((item) => String(item.route || "") === route);
        showDetail(`Route: ${{route}}`, {{ route, item_count: items.length, items: items.slice(0, 8) }});
      }});
    }});
  }}

  function renderTables() {{
    const itemRows = filteredItems().slice(0, 100).map((item, index) => `
      <tr data-item-index="${{index}}">
        <td>${{safeText(item.route)}}</td>
        <td>${{safeText(item.hit_count)}}</td>
        <td>${{safeText(item.updated_at_utc)}}</td>
        <td>${{safeText(item.text)}}<br><small>${{safeText(item.id)}}</small></td>
      </tr>
    `).join("");
    const items = filteredItems();
    document.getElementById("memoryRows").innerHTML = itemRows || '<tr><td colspan="4" class="empty">No memory items match the current filters.</td></tr>';
    document.querySelectorAll("#memoryRows [data-item-index]").forEach((node) => {{
      node.addEventListener("click", () => {{
        const item = items[Number(node.getAttribute("data-item-index"))];
        showDetail(`Memory Item: ${{item?.id || "unknown"}}`, item || {{}});
      }});
    }});

    const conflicts = filteredConflicts();
    const conflictRows = conflicts.slice(0, 80).map((item, index) => `
      <tr data-conflict-index="${{index}}">
        <td>${{safeText(item.id)}}</td>
        <td>${{safeText(item.route)}}</td>
        <td>${{safeText(item.similarity)}}</td>
        <td>${{safeText(item.status)}}</td>
        <td>${{safeText(item.reason)}}</td>
      </tr>
    `).join("");
    document.getElementById("conflictRows").innerHTML = conflictRows || '<tr><td colspan="5" class="empty">No conflicts match the current filters.</td></tr>';
    document.querySelectorAll("#conflictRows [data-conflict-index]").forEach((node) => {{
      node.addEventListener("click", () => {{
        const item = conflicts[Number(node.getAttribute("data-conflict-index"))];
        showDetail(`Conflict: ${{item?.id || "unknown"}}`, item || {{}});
      }});
    }});
  }}

  function renderAll() {{
    hydrateRouteFilter();
    renderTopline();
    renderRouteGrid();
    renderTables();
  }}

  async function refreshSnapshot() {{
    if (window.location.protocol === "file:") {{
      refreshStatus.textContent = "File mode detected. Auto refresh keeps the embedded snapshot because browsers usually block fetch from file URLs.";
      return;
    }}
    refreshStatus.textContent = "Refreshing semantic memory snapshot...";
    try {{
      let response = null;
      if (serviceEndpoints.semantic_memory) {{
        response = await fetch(serviceEndpoints.semantic_memory + "?ts=" + Date.now(), {{ cache: "no-store" }});
      }}
      if (!response || !response.ok) {{
        response = await fetch("./semantic_memory.json?ts=" + Date.now(), {{ cache: "no-store" }});
      }}
      if (!response.ok) {{
        throw new Error(`HTTP ${{response.status}}`);
      }}
      memoryState = shapeState(await response.json());
      refreshStatus.textContent = "Live refresh succeeded from the dashboard service semantic-memory snapshot.";
      renderAll();
    }} catch (error) {{
      refreshStatus.textContent = "Refresh failed, continuing with the embedded snapshot. " + error;
    }}
  }}

  routeFilter.addEventListener("change", renderTables);
  conflictFilter.addEventListener("change", renderTables);
  searchInput.addEventListener("input", renderTables);
  refreshButton.addEventListener("click", refreshSnapshot);

  setInterval(() => {{
    if (autoRefreshToggle.checked) {{
      refreshSnapshot();
    }}
  }}, 30000);

  renderAll();
</script>
</body>
</html>
"""
    html_path.write_text(html, encoding="utf-8")
    return {"semantic_memory_json": str(json_path), "semantic_memory_html": str(html_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect or render FBBP semantic memory.")
    parser.add_argument("--query")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--backfill-runs", action="store_true")
    parser.add_argument("--input-root", default=str(DEFAULT_RUN_ROOT))
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--resolve-conflict")
    parser.add_argument("--action", choices=["merge", "dismiss", "keep_new", "keep_existing"], default="dismiss")
    parser.add_argument("--note", default="")
    args = parser.parse_args()
    if args.backfill_runs:
        print(
            json.dumps(
                backfill_memory_from_runs(REPO_ROOT, Path(args.input_root).resolve(), reset=args.reset),
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    if args.resolve_conflict:
        print(
            json.dumps(
                resolve_memory_conflict(REPO_ROOT, args.resolve_conflict, args.action, note=args.note),
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    if args.query:
        print(json.dumps(retrieve_semantic_memory(REPO_ROOT, args.query, top_k=args.top_k), ensure_ascii=False, indent=2))
        return
    outputs = write_memory_dashboard(REPO_ROOT, Path(args.output_root).resolve())
    print(json.dumps(outputs, ensure_ascii=False))


if __name__ == "__main__":
    main()
