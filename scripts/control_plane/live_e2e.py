from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from control_plane.a2a_gateway import submit_message
from control_plane.worker_daemon import run_once
from control_plane.worker_queue import get_task


REPO_ROOT = Path(__file__).resolve().parents[2]


def run_live_e2e(output_root: Path) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    queue_root = output_root / "queue"
    worker_output_root = output_root / "worker_runs"
    report_json = output_root / "input_report.json"
    report_json.write_text(
        json.dumps(
            {
                "title": "A2A live e2e smoke report",
                "completion_mode": "synthetic_smoke",
                "conclusions": ["A2A request reached queue, worker, control plane, run_record, and artifact."],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    config = {
        "queue_backend": "file",
        "queue_root": str(queue_root),
        "max_attempts": 1,
        "backoff_seconds": 0,
        "lease_seconds": 120,
    }
    submitted = submit_message(
        {
            "message": {
                "role": "ROLE_USER",
                "parts": [{"text": "Run local report_generation e2e smoke"}],
                "messageId": "msg_live_e2e_smoke",
            },
            "metadata": {
                "route": "report_generation",
                "report_json": str(report_json),
                "source_agent": "live-e2e-smoke",
            },
        },
        config=config,
    )
    task_id = submitted["task"]["id"]
    worker_result = run_once(worker_id="live-e2e-worker", output_root=worker_output_root, config=config)
    completed = get_task(task_id, queue_root=queue_root, config=config) or {}
    artifact_metadata = {}
    artifacts = completed.get("artifacts") if isinstance(completed.get("artifacts"), list) else []
    if artifacts:
        artifact_metadata = artifacts[0].get("metadata") or {}
    run_dir = Path(str(artifact_metadata.get("run_dir") or ""))
    run_record_path = run_dir / "run_record.json" if run_dir else None
    run_record = json.loads(run_record_path.read_text(encoding="utf-8")) if run_record_path and run_record_path.exists() else {}
    summary = {
        "ok": completed.get("queue_state") == "completed" and bool(run_record),
        "task_id": task_id,
        "queue_state": completed.get("queue_state"),
        "task_status": completed.get("status"),
        "worker_result": worker_result,
        "artifact_metadata": artifact_metadata,
        "run_record_path": str(run_record_path) if run_record_path else None,
        "run_record_status": run_record.get("status"),
        "primary_route": run_record.get("primary_route"),
        "metrics": run_record.get("metrics"),
    }
    (output_root / "live_e2e_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a live A2A queue -> worker -> control-plane e2e smoke.")
    parser.add_argument("--output-root", default=str(REPO_ROOT / "runs" / "control_plane" / "live_e2e_v1"))
    args = parser.parse_args()
    print(json.dumps(run_live_e2e(Path(args.output_root).resolve()), ensure_ascii=False))


if __name__ == "__main__":
    main()
