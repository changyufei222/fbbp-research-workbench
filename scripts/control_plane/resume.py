from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def find_recent_thread_runs(runs_root: Path, thread_id: str, limit: int = 5) -> list[dict[str, Any]]:
    if not thread_id or not runs_root.exists():
        return []

    matches: list[dict[str, Any]] = []
    for run_request in runs_root.rglob("run_request.json"):
        child = run_request.parent
        run_record = child / "run_record.json"
        if not run_request.exists() or not run_record.exists():
            continue
        try:
            request_payload = json.loads(run_request.read_text(encoding="utf-8"))
            record_payload = json.loads(run_record.read_text(encoding="utf-8"))
        except Exception:
            continue
        if str(request_payload.get("thread_id") or "") != thread_id:
            continue
        matches.append(
            {
                "run_id": record_payload.get("run_id"),
                "run_dir": str(child.resolve()),
                "primary_route": record_payload.get("primary_route"),
                "status": record_payload.get("status"),
                "completed_at_utc": record_payload.get("completed_at_utc"),
                "query_preview": ((record_payload.get("request_summary") or {}).get("query_preview")),
                "result_summary": record_payload.get("result_summary") or {},
            }
        )

    matches.sort(key=lambda item: str(item.get("completed_at_utc") or ""), reverse=True)
    return matches[:limit]
