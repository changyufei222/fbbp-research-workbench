from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from control_plane.a2a import A2A_SCHEMA_VERSION
from control_plane.worker_queue import create_task, get_task
from control_plane import worker_daemon


def _envelope(task_id: str) -> dict[str, object]:
    return {
        "schema_version": A2A_SCHEMA_VERSION,
        "message_id": "msg_worker_daemon_001",
        "correlation_id": "a2ac_worker_daemon_001",
        "message_type": "child_run_request",
        "phase": "requested",
        "trace_id": "trace_worker_daemon_001",
        "parent_run_id": "trace_worker_daemon_001",
        "child_run_id": task_id,
        "hop_index": 1,
        "source_agent": "test-client",
        "target_agent": "fbbp-control-plane",
        "route": "public_lookup",
        "status": "requested",
    }


class ControlPlaneWorkerDaemonTests(unittest.TestCase):
    def test_worker_daemon_claims_executes_and_completes_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            queue_root = root / "queue"
            output_root = root / "worker_runs"
            config = {
                "queue_backend": "file",
                "queue_root": str(queue_root),
                "max_attempts": 1,
                "backoff_seconds": 0,
                "lease_seconds": 60,
            }
            task = create_task(
                envelope=_envelope("task_worker_daemon_001"),
                input_payload={"query": "PubMed knottin", "metadata": {"route": "public_lookup"}},
                queue_root=queue_root,
                config=config,
            )
            fake_stdout = json.dumps(
                {
                    "run_id": "run-public-lookup-1",
                    "run_dir": str(output_root / task["task_id"]),
                    "status": "succeeded",
                    "primary_route": "public_lookup",
                },
                ensure_ascii=False,
            )
            with mock.patch.object(worker_daemon.subprocess, "run") as mocked_run:
                mocked_run.return_value = mock.Mock(returncode=0, stdout=fake_stdout, stderr="")
                result = worker_daemon.run_once(worker_id="worker-test", output_root=output_root, config=config)
            completed = get_task(task["task_id"], queue_root=queue_root, config=config)

        self.assertTrue(result["claimed"])
        self.assertEqual(result["queue_state"], "completed")
        self.assertEqual(completed["status"], "TASK_STATE_COMPLETED")
        self.assertEqual(completed["artifacts"][0]["metadata"]["primary_route"], "public_lookup")


if __name__ == "__main__":
    unittest.main()
