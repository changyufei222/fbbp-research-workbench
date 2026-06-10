from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from html import escape
from pathlib import Path
from statistics import mean
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_ROOT = REPO_ROOT / "runs" / "control_plane"
DEFAULT_OUTPUT_ROOT = REPO_ROOT.parent / "llm-eval-benchmark" / "reports" / "control_plane_dashboard" / "latest"
DEFAULT_PORTFOLIO_OUTPUT_ROOT = REPO_ROOT / "reports" / "control_plane_portfolio_dashboard" / "latest"


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def collect_run_records(input_root: Path = DEFAULT_INPUT_ROOT) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not input_root.exists():
        return records
    for path in sorted(input_root.rglob("run_record.json")):
        payload = _load_json(path)
        if not payload:
            continue
        payload = dict(payload)
        payload["_record_path"] = str(path)
        records.append(payload)
    return records


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    route_counts = Counter(str(record.get("primary_route") or "unknown") for record in records)
    status_counts = Counter(str(record.get("status") or "unknown") for record in records)
    route_metrics: dict[str, dict[str, Any]] = {}
    by_route: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_route[str(record.get("primary_route") or "unknown")].append(record)

    for route, rows in sorted(by_route.items()):
        latencies = [
            float((row.get("metrics") or {}).get("latency_ms"))
            for row in rows
            if isinstance((row.get("metrics") or {}).get("latency_ms"), (int, float))
        ]
        judge_scores = [
            float((row.get("metrics") or {}).get("judge_score"))
            for row in rows
            if isinstance((row.get("metrics") or {}).get("judge_score"), (int, float))
        ]
        tool_rates = [
            float((row.get("metrics") or {}).get("tool_success_rate"))
            for row in rows
            if isinstance((row.get("metrics") or {}).get("tool_success_rate"), (int, float))
        ]
        route_metrics[route] = {
            "count": len(rows),
            "statuses": dict(Counter(str(row.get("status") or "unknown") for row in rows)),
            "avg_latency_ms": round(mean(latencies), 2) if latencies else None,
            "avg_judge_score": round(mean(judge_scores), 4) if judge_scores else None,
            "avg_tool_success_rate": round(mean(tool_rates), 4) if tool_rates else None,
            "memory_hit_count": sum(1 for row in rows if (row.get("metrics") or {}).get("memory_hit")),
            "preflight_hit_count": sum(1 for row in rows if (row.get("metrics") or {}).get("preflight_hit")),
        }

    return {
        "schema_version": "fbbp.control_plane.eval_dashboard.v1",
        "record_count": len(records),
        "route_counts": dict(route_counts),
        "status_counts": dict(status_counts),
        "route_metrics": route_metrics,
        "eval_harness": {
            "project": "llm-eval-benchmark",
            "output_contract": "reports/control_plane_dashboard/latest",
        },
    }


def write_dashboard(records: list[dict[str, Any]], output_root: Path = DEFAULT_OUTPUT_ROOT) -> dict[str, str]:
    output_root.mkdir(parents=True, exist_ok=True)
    summary = summarize_records(records)
    summary_path = output_root / "summary.json"
    csv_path = output_root / "runs.csv"
    md_path = output_root / "summary.md"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    fields = [
        "run_id",
        "primary_route",
        "status",
        "judge_score",
        "tool_success_rate",
        "memory_hit",
        "preflight_hit",
        "latency_ms",
        "record_path",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            metrics = record.get("metrics") if isinstance(record.get("metrics"), dict) else {}
            writer.writerow(
                {
                    "run_id": record.get("run_id"),
                    "primary_route": record.get("primary_route"),
                    "status": record.get("status"),
                    "judge_score": metrics.get("judge_score"),
                    "tool_success_rate": metrics.get("tool_success_rate"),
                    "memory_hit": metrics.get("memory_hit"),
                    "preflight_hit": metrics.get("preflight_hit"),
                    "latency_ms": metrics.get("latency_ms"),
                    "record_path": record.get("_record_path"),
                }
            )

    lines = [
        "# Control Plane Eval Dashboard",
        "",
        f"- records: {summary['record_count']}",
        f"- routes: {summary['route_counts']}",
        f"- statuses: {summary['status_counts']}",
        "",
        "## Route Metrics",
        "",
    ]
    for route, metrics in summary["route_metrics"].items():
        lines.append(
            f"- {route}: count={metrics['count']}, avg_judge={metrics['avg_judge_score']}, avg_tool_success={metrics['avg_tool_success_rate']}, avg_latency_ms={metrics['avg_latency_ms']}"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"summary_json": str(summary_path), "runs_csv": str(csv_path), "summary_md": str(md_path)}


def _pct(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{value * 100:.1f}%"
    return "n/a"


def _bar(value: Any) -> str:
    percent = 0.0
    if isinstance(value, (int, float)):
        percent = max(0.0, min(100.0, value * 100))
    return f"<div class='bar'><span style='width:{percent:.1f}%'></span></div>"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _compact_recent_runs(records: list[dict[str, Any]], limit: int = 24) -> list[dict[str, Any]]:
    recent: list[dict[str, Any]] = []
    for record in records[-limit:][::-1]:
        metrics = record.get("metrics") if isinstance(record.get("metrics"), dict) else {}
        request_summary = record.get("request_summary") if isinstance(record.get("request_summary"), dict) else {}
        result_summary = record.get("result_summary") if isinstance(record.get("result_summary"), dict) else {}
        recent.append(
            {
                "run_id": str(record.get("run_id") or ""),
                "route": str(record.get("primary_route") or "unknown"),
                "status": str(record.get("status") or "unknown"),
                "latency_ms": metrics.get("latency_ms"),
                "judge_score": metrics.get("judge_score"),
                "tool_success_rate": metrics.get("tool_success_rate"),
                "memory_hit": bool(metrics.get("memory_hit")),
                "preflight_hit": bool(metrics.get("preflight_hit")),
                "query_preview": str(request_summary.get("query_preview") or request_summary.get("case_path") or request_summary.get("batch_path") or ""),
                "result_summary": str(result_summary.get("summary") or result_summary.get("message") or ""),
                "record_path": str(record.get("_record_path") or ""),
            }
        )
    return recent


def write_portfolio_dashboard(
    records: list[dict[str, Any]],
    output_root: Path = DEFAULT_PORTFOLIO_OUTPUT_ROOT,
    *,
    readiness_path: Path | None = None,
    hardening_path: Path | None = None,
    semantic_memory_path: Path | None = None,
) -> dict[str, str]:
    output_root.mkdir(parents=True, exist_ok=True)
    summary = summarize_records(records)
    readiness = _read_json(readiness_path or (REPO_ROOT / "runs" / "control_plane" / "readiness" / "job_demo_fast" / "readiness_summary.json"))
    hardening = _read_json(hardening_path or (REPO_ROOT / "runs" / "control_plane" / "hardening" / "latest" / "production_hardening_summary.json"))
    semantic_memory = _read_json(semantic_memory_path or (REPO_ROOT / "runs" / "control_plane" / "memory" / "semantic_memory.json"))
    deployment_doc = REPO_ROOT / "docs" / "deployment-runbook-cn.md"
    final_release_summary = _read_json(REPO_ROOT / "runs" / "control_plane" / "final_release" / "latest" / "final_release_summary.json")
    route_overview = []
    for route, metrics in summary.get("route_metrics", {}).items():
        route_overview.append(
            {
                "route": route,
                "count": metrics.get("count"),
                "statuses": metrics.get("statuses"),
                "avg_latency_ms": metrics.get("avg_latency_ms"),
                "avg_judge_score": metrics.get("avg_judge_score"),
                "avg_tool_success_rate": metrics.get("avg_tool_success_rate"),
                "memory_hit_count": metrics.get("memory_hit_count"),
                "preflight_hit_count": metrics.get("preflight_hit_count"),
            }
        )
    route_rows = []
    for metrics in route_overview:
        route_rows.append(
            "<tr>"
            f"<td><strong>{escape(str(metrics.get('route') or ''))}</strong></td>"
            f"<td>{metrics.get('count')}</td>"
            f"<td>{escape(str(metrics.get('statuses') or {}))}</td>"
            f"<td>{metrics.get('avg_judge_score') if metrics.get('avg_judge_score') is not None else 'n/a'}</td>"
            f"<td>{_pct(metrics.get('avg_tool_success_rate'))}{_bar(metrics.get('avg_tool_success_rate'))}</td>"
            f"<td>{metrics.get('memory_hit_count')}</td>"
            f"<td>{metrics.get('preflight_hit_count')}</td>"
            "</tr>"
        )

    recent_runs = _compact_recent_runs(records)
    recent_rows = []
    for record in recent_runs[:12]:
        recent_rows.append(
            "<tr>"
            f"<td>{escape(str(record.get('run_id') or ''))}</td>"
            f"<td>{escape(str(record.get('route') or ''))}</td>"
            f"<td><span class='pill {escape(str(record.get('status') or ''))}'>{escape(str(record.get('status') or ''))}</span></td>"
            f"<td>{escape(str(record.get('latency_ms') or 'n/a'))}</td>"
            f"<td>{escape(str(record.get('judge_score') or 'n/a'))}</td>"
            "</tr>"
        )

    readiness_checks = readiness.get("checks") if isinstance(readiness.get("checks"), list) else []
    check_cards = "".join(
        f"<div class='mini {'ok' if item.get('ok') else 'bad'}'><b>{escape(str(item.get('name')))}</b><span>{'PASS' if item.get('ok') else 'FAIL'}</span></div>"
        for item in readiness_checks
    )
    hardening_checks = hardening.get("checks") if isinstance(hardening.get("checks"), list) else []
    hardening_cards = "".join(
        f"<div class='mini {'ok' if item.get('ok') else 'bad'}'><b>{escape(str(item.get('name')))}</b><span>{'PASS' if item.get('ok') else 'FAIL'}</span></div>"
        for item in hardening_checks
    )
    memory_items = semantic_memory.get("items") if isinstance(semantic_memory.get("items"), list) else []
    memory_cards = "".join(
        "<button class='memory-card memory-button' type='button'>"
        f"<b>{escape(str(item.get('route') or ''))}</b>"
        f"<span>{escape(str(item.get('hit_count') or 0))} hits</span>"
        f"<p>{escape(str(item.get('text') or ''))}</p>"
        "</button>"
        for item in memory_items[:6]
    )
    artifact_cards = [
        ("Portfolio Dashboard", str(output_root / "index.html")),
        ("Semantic Memory Viewer", str(output_root / "semantic_memory.html")),
        ("Dashboard Service API", "http://127.0.0.1:8088/api/snapshot"),
        ("Deployment Runbook", str(deployment_doc)),
        ("Final Release Summary", str(REPO_ROOT / "runs" / "control_plane" / "final_release" / "latest" / "final_release_summary.md")),
    ]
    artifact_markup = "".join(
        f"<div class='artifact'><b>{escape(label)}</b><code>{escape(path)}</code></div>"
        for label, path in artifact_cards
    )
    release_status = "ready" if final_release_summary.get("ok") else "in_progress"
    release_required = f"{final_release_summary.get('required_passed_count', '?')}/{final_release_summary.get('required_check_count', '?')}"
    dashboard_state = {
        "schema_version": "fbbp.control_plane.portfolio_dashboard.v2",
        "mode": "live_local_control_console",
        "generated_at_utc": final_release_summary.get("created_at_utc") or readiness.get("created_at_utc"),
        "summary": summary,
        "route_overview": route_overview,
        "recent_runs": recent_runs,
        "readiness": {
            "ok": readiness.get("ok"),
            "passed_count": readiness.get("passed_count"),
            "check_count": readiness.get("check_count"),
            "checks": readiness_checks,
        },
        "hardening": {
            "ok": hardening.get("ok"),
            "passed_count": hardening.get("passed_count"),
            "check_count": hardening.get("check_count"),
            "checks": hardening_checks,
        },
        "semantic_memory": {
            "item_count": len(memory_items),
            "conflict_count": len(semantic_memory.get("conflicts") or []),
            "items": memory_items[:18],
        },
        "final_release": {
            "ok": final_release_summary.get("ok"),
            "required_passed_count": final_release_summary.get("required_passed_count"),
            "required_check_count": final_release_summary.get("required_check_count"),
            "checks": final_release_summary.get("checks"),
        },
        "service_endpoints": {
            "health": "http://127.0.0.1:8088/health",
            "snapshot": "http://127.0.0.1:8088/api/snapshot",
            "semantic_memory": "http://127.0.0.1:8088/api/semantic-memory",
            "rebuild": "http://127.0.0.1:8088/api/rebuild",
        },
        "artifacts": {label: path for label, path in artifact_cards},
    }
    dashboard_state_json = json.dumps(dashboard_state, ensure_ascii=False).replace("</", "<\\/")

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>FBBP Agent Control Plane Dashboard</title>
  <style>
    :root {{ --ink:#15231d; --muted:#66756c; --paper:#fbf8ef; --panel:rgba(255,255,255,.78); --line:#d8e0d6; --green:#1f7a4d; --gold:#c48a2c; --red:#b34a3c; --blue:#2e6f88; --sand:#f4ede0; --teal:#1f5b66; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; color:var(--ink); font-family: Georgia, 'Noto Serif SC', serif; background:
      radial-gradient(circle at top left, rgba(196,138,44,.22), transparent 30%),
      radial-gradient(circle at 80% 10%, rgba(46,111,136,.18), transparent 28%),
      linear-gradient(135deg, #f7f1e4, #eef7ef 55%, #e7f0f4); }}
    main {{ max-width:1240px; margin:0 auto; padding:42px 22px 64px; }}
    header {{ display:grid; grid-template-columns:1.4fr .6fr; gap:24px; align-items:end; }}
    h1 {{ font-size:54px; line-height:.96; margin:0; letter-spacing:-.055em; }}
    h2 {{ margin-top:0; }}
    .lede {{ font-size:18px; color:var(--muted); max-width:760px; }}
    .stamp {{ border:1px solid var(--line); background:var(--panel); border-radius:28px; padding:18px; box-shadow:0 24px 70px rgba(29,54,39,.10); }}
    .grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:16px; margin:30px 0; }}
    .card,.section {{ border:1px solid var(--line); background:var(--panel); border-radius:28px; padding:20px; box-shadow:0 24px 70px rgba(29,54,39,.08); backdrop-filter:blur(10px); }}
    .num {{ font-size:40px; font-weight:800; color:var(--green); letter-spacing:-.04em; }}
    .label {{ color:var(--muted); font-size:13px; text-transform:uppercase; letter-spacing:.1em; }}
    .sections {{ display:grid; grid-template-columns:1fr 1fr; gap:18px; }}
    .hero-grid {{ display:grid; grid-template-columns:1.2fr .8fr; gap:18px; margin:22px 0 18px; }}
    .hero-box {{ border:1px solid var(--line); background:linear-gradient(180deg, rgba(255,255,255,.82), rgba(255,255,255,.68)); border-radius:28px; padding:22px; box-shadow:0 24px 70px rgba(29,54,39,.08); }}
    .console-grid {{ display:grid; grid-template-columns:1.1fr .9fr; gap:18px; margin:0 0 18px; align-items:start; }}
    .toolbar {{ display:flex; flex-wrap:wrap; gap:12px; align-items:end; margin-top:18px; }}
    .toolbar label {{ display:flex; flex-direction:column; gap:6px; font-size:13px; color:var(--muted); min-width:160px; }}
    .toolbar input,.toolbar select {{ border:1px solid var(--line); border-radius:14px; padding:10px 12px; font:inherit; background:rgba(255,255,255,.9); }}
    .toolbar button,.memory-button {{ border:1px solid var(--line); border-radius:14px; padding:10px 14px; font:inherit; cursor:pointer; background:white; color:var(--ink); }}
    .toolbar button:hover,.memory-button:hover,.route-card:hover {{ transform:translateY(-1px); box-shadow:0 10px 24px rgba(29,54,39,.10); }}
    .toggle {{ min-width:auto; }}
    .toggle-row {{ display:flex; gap:8px; align-items:center; }}
    .refresh-note {{ color:var(--teal); font-size:13px; }}
    .route-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; margin-top:14px; }}
    .route-card {{ border:1px solid var(--line); border-radius:18px; padding:14px; background:white; cursor:pointer; transition:transform .12s ease, box-shadow .12s ease; }}
    .route-card strong {{ display:block; font-size:16px; margin-bottom:6px; }}
    .route-card small {{ color:var(--muted); display:block; }}
    .artifact-grid,.memory-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; }}
    .artifact,.memory-card {{ border:1px solid var(--line); border-radius:18px; padding:14px; background:rgba(255,255,255,.82); }}
    .artifact code {{ display:block; margin-top:8px; white-space:pre-wrap; word-break:break-all; color:var(--blue); }}
    .memory-card span {{ color:var(--muted); font-size:13px; display:block; margin:4px 0 8px; }}
    .memory-card p {{ margin:0; color:var(--ink); }}
    .detail-panel {{ min-height:260px; }}
    .detail-panel pre {{ margin:0; white-space:pre-wrap; word-break:break-word; font-size:13px; line-height:1.55; color:#204338; background:rgba(255,255,255,.85); border:1px solid var(--line); border-radius:18px; padding:14px; }}
    .status-badge {{ display:inline-block; padding:6px 10px; border-radius:999px; background:rgba(31,122,77,.12); color:var(--green); font-weight:700; font-size:12px; text-transform:uppercase; letter-spacing:.08em; }}
    .status-badge.pending {{ background:rgba(196,138,44,.14); color:var(--gold); }}
    .callout {{ background:var(--sand); border:1px solid var(--line); border-radius:18px; padding:14px 16px; color:var(--muted); }}
    table {{ width:100%; border-collapse:collapse; overflow:hidden; border-radius:18px; background:white; }}
    th,td {{ text-align:left; padding:12px 13px; border-bottom:1px solid var(--line); vertical-align:top; font-size:14px; }}
    th {{ background:#eaf3e9; color:var(--muted); text-transform:uppercase; letter-spacing:.08em; font-size:12px; }}
    .bar {{ height:7px; background:#edf1ec; border-radius:99px; overflow:hidden; margin-top:7px; }}
    .bar span {{ display:block; height:100%; background:linear-gradient(90deg,var(--green),var(--gold)); }}
    .mini {{ display:flex; justify-content:space-between; gap:12px; padding:12px 14px; border:1px solid var(--line); border-radius:16px; background:rgba(255,255,255,.66); margin:8px 0; }}
    .mini.ok span,.pill.succeeded {{ color:var(--green); }}
    .mini.bad span,.pill.failed {{ color:var(--red); }}
    .pill {{ font-weight:700; }}
    .muted {{ color:var(--muted); }}
    .empty {{ color:var(--muted); padding:12px 0; }}
    @media(max-width:900px) {{ header,.sections,.hero-grid,.console-grid {{ grid-template-columns:1fr; }} .grid,.artifact-grid,.memory-grid,.route-grid {{ grid-template-columns:1fr 1fr; }} h1 {{ font-size:40px; }} }}
    @media(max-width:620px) {{ .grid,.artifact-grid,.memory-grid,.route-grid {{ grid-template-columns:1fr; }} main {{ padding:28px 14px; }} .toolbar label {{ min-width:100%; }} }}
  </style>
</head>
<body>
<main>
  <header>
    <div>
      <div class="label">Biomedical Agent Infrastructure</div>
      <h1>FBBP Agent Control Plane</h1>
      <p class="lede">统一入口、意图路由、A2A worker handoff、memory、public/private lookup、run record 和 agent eval dashboard。这个页面现在由本地 HTTP service 提供，支持筛选、drill-down、自动刷新快照和一键 rebuild。</p>
    </div>
    <div class="stamp">
      <div class="label">Evidence Snapshot</div>
      <p><b>Service mode:</b> <span id="serviceMode">live local console</span></p>
      <p><b>Fast readiness:</b> <span id="readinessSummary">{readiness.get('passed_count','?')}/{readiness.get('check_count','?')}</span></p>
      <p><b>Hardening:</b> <span id="hardeningSummary">{hardening.get('passed_count','?')}/{hardening.get('check_count','?')}</span></p>
      <p><b>Memory items:</b> <span id="memoryItemCount">{len(semantic_memory.get('items') or [])}</span></p>
      <p><b>Final release:</b> <span id="releaseSummary">{release_required}</span></p>
      <p><b>Snapshot:</b> <span id="snapshotTime">{escape(str(dashboard_state.get('generated_at_utc') or 'embedded snapshot'))}</span></p>
    </div>
  </header>
  <section class="hero-grid">
    <div class="hero-box">
      <div class="label">Why This Matters</div>
      <h2>Not just RAG. A real FBBP agent control plane.</h2>
      <p class="lede">这套系统把私有 RAG、公开生物医学查询、A2A worker 交接、长期语义记忆、统一 run record 和 agent eval 收到一条工程主链里。目标不是“调用一下模型”，而是做成可验证、可演示、可解释的 FBBP 工作流基础设施。</p>
      <div class="callout">Current release state: <span class="status-badge {'pending' if release_status != 'ready' else ''}">{escape(release_status)}</span> Required checks {escape(release_required)}</div>
      <div class="toolbar">
        <label>Route Filter
          <select id="routeFilter">
            <option value="">All routes</option>
          </select>
        </label>
        <label>Status Filter
          <select id="statusFilter">
            <option value="">All statuses</option>
          </select>
        </label>
        <label>Search Runs
          <input id="searchInput" type="search" placeholder="query / result / run id" />
        </label>
        <label class="toggle">Console Controls
          <div class="toggle-row">
            <button id="refreshButton" type="button">Refresh Snapshot</button>
            <button id="rebuildButton" type="button">Rebuild Snapshot</button>
            <input id="autoRefreshToggle" type="checkbox" checked />
            <span>Auto Refresh</span>
          </div>
        </label>
      </div>
      <p class="refresh-note" id="refreshStatus">Embedded snapshot loaded. When served over HTTP, this page prefers `/api/snapshot` and falls back to `portfolio_dashboard_summary.json` every 30s.</p>
    </div>
    <div class="hero-box">
      <div class="label">Key Artifacts</div>
      <div class="artifact-grid">{artifact_markup}</div>
    </div>
  </section>
  <section class="grid">
    <div class="card"><div class="num" id="runRecordCount">{summary.get('record_count', 0)}</div><div class="label">Run Records</div></div>
    <div class="card"><div class="num" id="succeededCount">{summary.get('status_counts', {}).get('succeeded', 0)}</div><div class="label">Succeeded</div></div>
    <div class="card"><div class="num" id="routeCount">{len(summary.get('route_counts', {}))}</div><div class="label">Routes</div></div>
    <div class="card"><div class="num" id="memoryConflictCount">{len(semantic_memory.get('conflicts') or [])}</div><div class="label">Memory Conflicts</div></div>
  </section>
  <section class="console-grid">
    <section class="section">
      <h2>Local Control Console</h2>
      <p class="muted">Route Metrics 的摘要卡片可以直接点开，查看该 route 的状态分布、平均 judge 分数、tool success 和 preflight 命中。</p>
      <div class="route-grid" id="routeCards"></div>
    </section>
    <section class="section detail-panel">
      <h2 id="detailTitle">Drill-down Details</h2>
      <pre id="detailBody">Click a route card, memory item, or recent run row to inspect the structured snapshot here.</pre>
    </section>
  </section>
  <section class="section">
    <h2>Route Metrics</h2>
    <table><thead><tr><th>Route</th><th>Count</th><th>Status</th><th>Judge</th><th>Tool Success</th><th>Memory Hits</th><th>Preflight</th></tr></thead><tbody id="routeMetricsBody">{''.join(route_rows)}</tbody></table>
  </section>
  <div class="sections">
    <section class="section"><h2>Readiness</h2><div id="readinessChecks">{check_cards or '<p class="empty">No readiness checks found.</p>'}</div></section>
    <section class="section"><h2>Production Hardening</h2><div id="hardeningChecks">{hardening_cards or '<p class="empty">No hardening checks found.</p>'}</div></section>
  </div>
  <section class="section">
    <h2>Semantic Memory Highlights</h2>
    <div class="memory-grid" id="memoryGrid">{memory_cards or '<p class="empty">No semantic memory yet.</p>'}</div>
  </section>
  <section class="section">
    <h2>Recent Runs</h2>
    <table><thead><tr><th>Run</th><th>Route</th><th>Status</th><th>Latency ms</th><th>Judge</th></tr></thead><tbody id="recentRunsBody">{''.join(recent_rows)}</tbody></table>
  </section>
  <noscript><p class="refresh-note">JavaScript is disabled, so this page stays on the embedded snapshot without client-side filtering or auto refresh.</p></noscript>
</main>
<script id="dashboard-state" type="application/json">{dashboard_state_json}</script>
<script>
  const embeddedState = JSON.parse(document.getElementById("dashboard-state").textContent);
  let dashboardState = embeddedState;

  const routeFilter = document.getElementById("routeFilter");
  const statusFilter = document.getElementById("statusFilter");
  const searchInput = document.getElementById("searchInput");
  const refreshButton = document.getElementById("refreshButton");
  const rebuildButton = document.getElementById("rebuildButton");
  const autoRefreshToggle = document.getElementById("autoRefreshToggle");
  const refreshStatus = document.getElementById("refreshStatus");
  const detailTitle = document.getElementById("detailTitle");
  const detailBody = document.getElementById("detailBody");
  const serviceEndpoints = embeddedState.service_endpoints || {{}};

  function safeText(value) {{
    if (value === null || value === undefined || value === "") {{
      return "n/a";
    }}
    return String(value);
  }}

  function asPercent(value) {{
    return typeof value === "number" ? `${{(value * 100).toFixed(1)}}%` : "n/a";
  }}

  function pillClass(status) {{
    return String(status || "").replace(/[^a-z0-9_-]/gi, "");
  }}

  function showDetail(title, payload) {{
    detailTitle.textContent = title;
    detailBody.textContent = JSON.stringify(payload, null, 2);
  }}

  function hydrateFilters() {{
    const routeValue = routeFilter.value;
    const statusValue = statusFilter.value;
    const routes = (dashboardState.route_overview || []).map((item) => item.route).filter(Boolean);
    const statuses = Array.from(new Set((dashboardState.recent_runs || []).map((item) => item.status).filter(Boolean))).sort();
    routeFilter.innerHTML = '<option value="">All routes</option>' + routes.map((route) => `<option value="${{route}}">${{route}}</option>`).join("");
    statusFilter.innerHTML = '<option value="">All statuses</option>' + statuses.map((status) => `<option value="${{status}}">${{status}}</option>`).join("");
    routeFilter.value = routes.includes(routeValue) ? routeValue : "";
    statusFilter.value = statuses.includes(statusValue) ? statusValue : "";
  }}

  function filteredRuns() {{
    const route = routeFilter.value.trim();
    const status = statusFilter.value.trim();
    const needle = searchInput.value.trim().toLowerCase();
    return (dashboardState.recent_runs || []).filter((item) => {{
      if (route && item.route !== route) return false;
      if (status && item.status !== status) return false;
      if (!needle) return true;
      const haystack = [item.run_id, item.route, item.query_preview, item.result_summary, item.record_path].join(" ").toLowerCase();
      return haystack.includes(needle);
    }});
  }}

  function renderRouteCards() {{
    const container = document.getElementById("routeCards");
    const cards = (dashboardState.route_overview || []).map((item) => `
      <button class="route-card" type="button" data-route="${{item.route}}">
        <strong>${{item.route}}</strong>
        <small>runs: ${{safeText(item.count)}} | judge: ${{safeText(item.avg_judge_score)}} | tool: ${{asPercent(item.avg_tool_success_rate)}}</small>
        <small>memory hits: ${{safeText(item.memory_hit_count)}} | preflight: ${{safeText(item.preflight_hit_count)}}</small>
      </button>
    `).join("");
    container.innerHTML = cards || '<p class="empty">No route metrics yet.</p>';
    container.querySelectorAll("[data-route]").forEach((node) => {{
      node.addEventListener("click", () => {{
        const route = node.getAttribute("data-route");
        const payload = (dashboardState.route_overview || []).find((item) => item.route === route);
        showDetail(`Route: ${{route}}`, payload || {{}});
      }});
    }});
  }}

  function renderRouteTable() {{
    const body = document.getElementById("routeMetricsBody");
    const rows = (dashboardState.route_overview || []).map((item) => `
      <tr>
        <td><strong>${{item.route}}</strong></td>
        <td>${{safeText(item.count)}}</td>
        <td>${{safeText(JSON.stringify(item.statuses || {{}}))}}</td>
        <td>${{safeText(item.avg_judge_score)}}</td>
        <td>${{asPercent(item.avg_tool_success_rate)}}</td>
        <td>${{safeText(item.memory_hit_count)}}</td>
        <td>${{safeText(item.preflight_hit_count)}}</td>
      </tr>
    `).join("");
    body.innerHTML = rows || '<tr><td colspan="7" class="empty">No route metrics yet.</td></tr>';
  }}

  function renderCheckColumn(targetId, checks) {{
    const target = document.getElementById(targetId);
    target.innerHTML = (checks || []).map((item) => `
      <div class="mini ${{item.ok ? "ok" : "bad"}}">
        <b>${{item.name}}</b>
        <span>${{item.ok ? "PASS" : "FAIL"}}</span>
      </div>
    `).join("") || '<p class="empty">No checks found.</p>';
  }}

  function renderMemoryGrid() {{
    const grid = document.getElementById("memoryGrid");
    const cards = (dashboardState.semantic_memory?.items || []).map((item, index) => `
      <button class="memory-card memory-button" type="button" data-memory-index="${{index}}">
        <b>${{safeText(item.route)}}</b>
        <span>${{safeText(item.hit_count)}} hits</span>
        <p>${{safeText(item.text)}}</p>
      </button>
    `).join("");
    grid.innerHTML = cards || '<p class="empty">No semantic memory yet.</p>';
    grid.querySelectorAll("[data-memory-index]").forEach((node) => {{
      node.addEventListener("click", () => {{
        const index = Number(node.getAttribute("data-memory-index"));
        const payload = dashboardState.semantic_memory?.items?.[index];
        showDetail(`Memory Item #${{index + 1}}`, payload || {{}});
      }});
    }});
  }}

  function renderRecentRuns() {{
    const body = document.getElementById("recentRunsBody");
    const runs = filteredRuns();
    body.innerHTML = runs.map((item, index) => `
      <tr data-run-index="${{index}}">
        <td>${{safeText(item.run_id)}}</td>
        <td>${{safeText(item.route)}}</td>
        <td><span class="pill ${{pillClass(item.status)}}">${{safeText(item.status)}}</span></td>
        <td>${{safeText(item.latency_ms)}}</td>
        <td>${{safeText(item.judge_score)}}</td>
      </tr>
    `).join("") || '<tr><td colspan="5" class="empty">No runs match the current filters.</td></tr>';
    body.querySelectorAll("[data-run-index]").forEach((node) => {{
      node.addEventListener("click", () => {{
        const index = Number(node.getAttribute("data-run-index"));
        showDetail(`Run: ${{runs[index].run_id || "unknown"}}`, runs[index] || {{}});
      }});
    }});
  }}

  function renderTopline() {{
    document.getElementById("runRecordCount").textContent = safeText(dashboardState.summary?.record_count);
    document.getElementById("succeededCount").textContent = safeText(dashboardState.summary?.status_counts?.succeeded || 0);
    document.getElementById("routeCount").textContent = safeText(Object.keys(dashboardState.summary?.route_counts || {{}}).length);
    document.getElementById("memoryConflictCount").textContent = safeText(dashboardState.semantic_memory?.conflict_count || 0);
    document.getElementById("readinessSummary").textContent = `${{safeText(dashboardState.readiness?.passed_count)}}/${{safeText(dashboardState.readiness?.check_count)}}`;
    document.getElementById("hardeningSummary").textContent = `${{safeText(dashboardState.hardening?.passed_count)}}/${{safeText(dashboardState.hardening?.check_count)}}`;
    document.getElementById("memoryItemCount").textContent = safeText(dashboardState.semantic_memory?.item_count || 0);
    document.getElementById("releaseSummary").textContent = `${{safeText(dashboardState.final_release?.required_passed_count)}}/${{safeText(dashboardState.final_release?.required_check_count)}}`;
    document.getElementById("snapshotTime").textContent = safeText(dashboardState.generated_at_utc || "embedded snapshot");
    document.getElementById("serviceMode").textContent = safeText(dashboardState.mode || "live_local_control_console");
  }}

  function renderAll() {{
    hydrateFilters();
    renderTopline();
    renderRouteCards();
    renderRouteTable();
    renderCheckColumn("readinessChecks", dashboardState.readiness?.checks || []);
    renderCheckColumn("hardeningChecks", dashboardState.hardening?.checks || []);
    renderMemoryGrid();
    renderRecentRuns();
  }}

  async function refreshSnapshot() {{
    if (window.location.protocol === "file:") {{
      refreshStatus.textContent = "File mode detected. Auto refresh keeps the embedded snapshot because browsers usually block fetch from file URLs.";
      return;
    }}
    refreshStatus.textContent = "Refreshing dashboard snapshot...";
    try {{
      let response = null;
      if (serviceEndpoints.snapshot) {{
        response = await fetch(serviceEndpoints.snapshot + "?ts=" + Date.now(), {{ cache: "no-store" }});
      }}
      if (!response || !response.ok) {{
        response = await fetch("./portfolio_dashboard_summary.json?ts=" + Date.now(), {{ cache: "no-store" }});
      }}
      if (!response.ok) {{
        throw new Error(`HTTP ${{response.status}}`);
      }}
      dashboardState = await response.json();
      refreshStatus.textContent = "Live refresh succeeded from the dashboard service snapshot.";
      renderAll();
    }} catch (error) {{
      refreshStatus.textContent = "Refresh failed, continuing with the embedded snapshot. " + error;
    }}
  }}

  async function rebuildSnapshot() {{
    if (window.location.protocol === "file:") {{
      refreshStatus.textContent = "File mode detected. Rebuild requires the dashboard HTTP service.";
      return;
    }}
    if (!serviceEndpoints.rebuild) {{
      refreshStatus.textContent = "No rebuild endpoint was embedded in this snapshot.";
      return;
    }}
    refreshStatus.textContent = "Rebuilding dashboard artifacts and final release snapshot...";
    try {{
      const response = await fetch(serviceEndpoints.rebuild, {{ method: "POST" }});
      if (!response.ok) {{
        throw new Error(`HTTP ${{response.status}}`);
      }}
      const payload = await response.json();
      if (payload.snapshot) {{
        dashboardState = payload.snapshot;
        renderAll();
      }}
      refreshStatus.textContent = "Rebuild finished. Final release and dashboard artifacts were regenerated.";
    }} catch (error) {{
      refreshStatus.textContent = "Rebuild failed. " + error;
    }}
  }}

  routeFilter.addEventListener("change", renderRecentRuns);
  statusFilter.addEventListener("change", renderRecentRuns);
  searchInput.addEventListener("input", renderRecentRuns);
  refreshButton.addEventListener("click", refreshSnapshot);
  rebuildButton.addEventListener("click", rebuildSnapshot);

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
    html_path = output_root / "index.html"
    summary_path = output_root / "portfolio_dashboard_summary.json"
    html_path.write_text(html, encoding="utf-8")
    summary_path.write_text(
        json.dumps(
            {
                **dashboard_state,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {"portfolio_html": str(html_path), "portfolio_summary_json": str(summary_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a control-plane eval dashboard from run_record.json files.")
    parser.add_argument("--input-root", default=str(DEFAULT_INPUT_ROOT))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--portfolio-output-root", default=str(DEFAULT_PORTFOLIO_OUTPUT_ROOT))
    parser.add_argument("--write-portfolio", action="store_true")
    args = parser.parse_args()
    records = collect_run_records(Path(args.input_root).resolve())
    outputs = write_dashboard(records, Path(args.output_root).resolve())
    if args.write_portfolio:
        outputs.update(write_portfolio_dashboard(records, Path(args.portfolio_output_root).resolve()))
    print(json.dumps({"record_count": len(records), "outputs": outputs}, ensure_ascii=False))


if __name__ == "__main__":
    main()
