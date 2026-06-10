from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from control_plane.project_links import project_summary, resolved_project_links


REPO_ROOT = Path(__file__).resolve().parents[2]


def _minimind_project() -> dict[str, Any]:
    project = (resolved_project_links().get("projects") or {}).get("minimind-fbtp-lab") or {}
    lab_path = project.get("resolved_path")
    if lab_path and lab_path not in sys.path:
        sys.path.insert(0, str(lab_path))
    return project


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _candidate_rows(project: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    lab_root = Path(str(project.get("resolved_path") or ""))
    processed = lab_root / "data" / "processed" / "fbbp_candidate_snapshot.jsonl"
    rows = _load_jsonl(processed)
    if rows:
        return rows, str(processed)

    from query_compiler.candidate_snapshot import build_candidate_snapshot

    rows = build_candidate_snapshot(limit=200)
    return rows, "query_compiler.candidate_snapshot.build_candidate_snapshot(limit=200)"


def run_candidate_query_compile(query: str, *, top_k: int = 5) -> dict[str, Any]:
    started = time.perf_counter()
    project = _minimind_project()
    from query_compiler.executor import execute_query_plan
    from query_compiler.rule_baseline import infer_rule_draft
    from query_compiler.validator import validate_query_draft

    rows, source = _candidate_rows(project)
    scaffold_values = [str(row.get("scaffold_type")) for row in rows if row.get("scaffold_type")]
    raw_draft = infer_rule_draft(query, scaffold_values)
    if top_k:
        raw_draft["limit"] = min(int(raw_draft.get("limit") or top_k), int(top_k))
    normalized = validate_query_draft(raw_draft)
    execution = execute_query_plan(normalized["plan"], rows)
    preview_rows = execution["rows"][: min(top_k, 5)]
    trace = normalized.get("trace", {})
    return {
        "ok": bool(trace.get("schema_ok")),
        "capability": "candidate_query_compile",
        "project": "minimind-fbtp-lab",
        "mode": "rule_baseline_validator_executor",
        "query": query,
        "raw_draft": raw_draft,
        "normalized_plan": normalized["plan"],
        "validator_trace": trace,
        "execution": {
            "metadata": execution["metadata"],
            "preview_rows": preview_rows,
        },
        "source": {
            "candidate_snapshot": source,
            "connected_projects": project_summary("minimind-fbtp-lab", "llm-rag-knowledge-base"),
        },
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
    }
