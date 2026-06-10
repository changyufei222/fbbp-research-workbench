from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from control_plane.worker_queue import claim_next_task, complete_task, fail_task, load_worker_queue_config, queue_root_from_config


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_PLANE_SCRIPT = REPO_ROOT / "scripts" / "run_fbbp_control_plane.py"


def _task_to_control_plane_args(task: dict[str, Any], output_root: Path) -> list[str]:
    task_input = task.get("input") if isinstance(task.get("input"), dict) else {}
    envelope = task.get("envelope") if isinstance(task.get("envelope"), dict) else {}
    metadata = task_input.get("metadata") if isinstance(task_input.get("metadata"), dict) else {}
    route = str(metadata.get("route") or metadata.get("primary_route") or envelope.get("route") or "fallback_general")
    run_dir = output_root / str(task["task_id"])
    args = [
        sys.executable,
        str(CONTROL_PLANE_SCRIPT),
        "--mode",
        "auto",
        "--force-primary-route",
        route,
        "--output-dir",
        str(run_dir),
    ]
    query = str(task_input.get("query") or "")
    if query:
        args.extend(["--query", query])
    for field, option in (
        ("case_path", "--case-path"),
        ("batch_path", "--batch-path"),
        ("run_dir", "--run-dir"),
        ("report_json", "--report-json"),
        ("evidence_json", "--evidence-json"),
        ("thread_id", "--thread-id"),
    ):
        value = task_input.get(field) or metadata.get(field)
        if value:
            args.extend([option, str(value)])
    if task_input.get("include_evidence"):
        args.append("--include-evidence")
    return args


def execute_claimed_task(task: dict[str, Any], *, output_root: Path, config: dict[str, Any]) -> dict[str, Any]:
    command = _task_to_control_plane_args(task, output_root)
    proc = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    task_id = str(task["task_id"])
    if proc.returncode != 0:
        return fail_task(
            task_id,
            error={
                "code": "CONTROL_PLANE_TASK_FAILED",
                "message": (proc.stderr or proc.stdout or "control-plane task failed").strip()[:1000],
            },
            config=config,
        )
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    artifact = {
        "artifactId": "control-plane-run",
        "parts": [
            {
                "text": json.dumps(
                    {
                        "run_id": payload.get("run_id"),
                        "run_dir": payload.get("run_dir"),
                        "status": payload.get("status"),
                        "primary_route": payload.get("primary_route"),
                    },
                    ensure_ascii=False,
                )
            }
        ],
        "metadata": payload,
    }
    return complete_task(task_id, artifacts=[artifact], config=config)


def run_once(*, worker_id: str, output_root: Path, config: dict[str, Any]) -> dict[str, Any]:
    queue_root = queue_root_from_config(config)
    task = claim_next_task(queue_root=queue_root, worker_id=worker_id, config=config)
    if not task:
        return {"claimed": False, "worker_id": worker_id}
    completed = execute_claimed_task(task, output_root=output_root, config=config)
    return {
        "claimed": True,
        "task_id": completed.get("task_id"),
        "queue_state": completed.get("queue_state"),
        "status": completed.get("status"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a local A2A worker daemon for the FBBP control plane.")
    parser.add_argument("--worker-id", default="local-control-plane-worker")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--max-tasks", type=int, default=0, help="0 means run until interrupted.")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--output-root", default=str(REPO_ROOT / "runs" / "control_plane_worker"))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = load_worker_queue_config()
    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    completed = 0
    while True:
        result = run_once(worker_id=args.worker_id, output_root=output_root, config=config)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if result.get("claimed"):
            completed += 1
        if args.once or (args.max_tasks and completed >= args.max_tasks):
            break
        time.sleep(max(args.poll_seconds, 0.1))


if __name__ == "__main__":
    main()
