from __future__ import annotations

import tempfile
import unittest
import os
from pathlib import Path
from unittest import mock

import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from control_plane.a2a import A2A_SCHEMA_VERSION
from control_plane.worker_queue import (
    claim_next_task,
    complete_task,
    create_task,
    fail_task,
    get_task,
    list_task_events,
    to_a2a_task,
)
from control_plane.push_notifications import build_push_payload
from control_plane.queue_backends import _pg_connect, _with_pg_connect_timeout, backend_status
from control_plane.react_trace import build_react_trace, write_react_trace
from formal_run_lib import load_yaml_config


def _request_envelope(task_id: str = "task_demo_001") -> dict[str, object]:
    return {
        "schema_version": A2A_SCHEMA_VERSION,
        "message_id": "msg_demo_001",
        "correlation_id": "a2ac_demo_001",
        "message_type": "child_run_request",
        "phase": "requested",
        "trace_id": "trace_demo_001",
        "parent_run_id": "trace_demo_001",
        "child_run_id": task_id,
        "hop_index": 1,
        "source_agent": "external-a2a-client",
        "target_agent": "fbbp-control-plane",
        "route": "formal_case",
        "status": "requested",
    }


class ControlPlaneWorkerQueueTests(unittest.TestCase):
    def test_create_claim_and_complete_task(self) -> None:
        config = {"max_attempts": 2, "backoff_seconds": 0, "lease_seconds": 10}
        with tempfile.TemporaryDirectory() as temp_dir:
            queue_root = Path(temp_dir) / "queue"
            task = create_task(
                envelope=_request_envelope(),
                input_payload={"query": "run formal case"},
                queue_root=queue_root,
                config=config,
            )

            claimed = claim_next_task(queue_root=queue_root, worker_id="worker-a")
            completed = complete_task(
                task["task_id"],
                artifacts=[{"artifactId": "artifact-1", "parts": [{"text": "ok"}]}],
                queue_root=queue_root,
            )
            a2a_task = to_a2a_task(completed)

        self.assertIsNotNone(claimed)
        self.assertEqual(claimed["queue_state"], "running")
        self.assertEqual(claimed["attempts"], 1)
        self.assertEqual(a2a_task["status"]["state"], "TASK_STATE_COMPLETED")
        self.assertEqual(a2a_task["artifacts"][0]["artifactId"], "artifact-1")

    def test_retry_then_dead_letter_after_max_attempts(self) -> None:
        config = {
            "max_attempts": 2,
            "backoff_seconds": 0,
            "lease_seconds": 10,
            "dead_letter_root": "dead_letters",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config["dead_letter_root"] = str(root / "dead_letters")
            queue_root = root / "queue"
            task = create_task(
                envelope=_request_envelope("task_retry_001"),
                input_payload={"query": "retry me"},
                queue_root=queue_root,
                config=config,
            )

            first = claim_next_task(queue_root=queue_root, worker_id="worker-a")
            retry = fail_task(
                task["task_id"],
                error={"message": "timeout while calling external worker"},
                queue_root=queue_root,
                config=config,
            )
            second = claim_next_task(queue_root=queue_root, worker_id="worker-a")
            failed = fail_task(
                task["task_id"],
                error={"message": "timeout again"},
                queue_root=queue_root,
                config=config,
            )
            events = list_task_events(task["task_id"], queue_root=queue_root)
            dead_letter_exists = (Path(config["dead_letter_root"]) / f"{task['task_id']}.json").exists()

        self.assertEqual(first["attempts"], 1)
        self.assertEqual(retry["queue_state"], "pending")
        self.assertEqual(second["attempts"], 2)
        self.assertEqual(failed["queue_state"], "failed")
        self.assertTrue(dead_letter_exists)
        self.assertIn("task_dead_lettered", [event["event"] for event in events])

    def test_get_task_returns_none_for_missing_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertIsNone(get_task("missing", queue_root=Path(temp_dir) / "queue"))

    def test_task_stores_push_notification_config_and_builds_payload(self) -> None:
        config = {"max_attempts": 1, "backoff_seconds": 0, "push_notifications": {"enabled": True}}
        with tempfile.TemporaryDirectory() as temp_dir:
            queue_root = Path(temp_dir) / "queue"
            task = create_task(
                envelope=_request_envelope("task_push_001"),
                input_payload={
                    "query": "notify me",
                    "configuration": {
                        "pushNotificationConfig": {
                            "url": "http://127.0.0.1:9999/webhook",
                            "token": "demo-token",
                        }
                    },
                },
                queue_root=queue_root,
                config=config,
            )
            payload = build_push_payload(task, "task_queued")

        self.assertEqual(task["push_notification_config"]["token"], "demo-token")
        self.assertEqual(payload["taskId"], "task_push_001")
        self.assertEqual(payload["traceId"], "trace_demo_001")

    def test_backend_status_reports_file_and_optional_backends(self) -> None:
        status = backend_status(
            {
                "queue_backend": "file",
                "redis": {"url_env": "FBBP_A2A_TEST_REDIS_URL"},
                "postgres": {"dsn_env": "FBBP_A2A_TEST_POSTGRES_DSN"},
            }
        )

        self.assertTrue(status["file"]["available"])
        self.assertTrue(status["file"]["active"])
        self.assertIn("module_installed", status["redis"])
        self.assertIn("module_installed", status["postgres"])

    def test_postgres_backend_adds_default_connect_timeout(self) -> None:
        dsn = _with_pg_connect_timeout("postgresql://u:p@localhost:5432/db", 3)

        self.assertIn("connect_timeout=3", dsn)

    def test_postgres_backend_can_fallback_to_psycopg2(self) -> None:
        class FakePsycopg2:
            @staticmethod
            def connect(dsn: str) -> str:
                return f"psycopg2:{dsn}"

        config = {"postgres": {"dsn_env": "FBBP_A2A_TEST_POSTGRES_DSN"}}
        with mock.patch.dict(sys.modules, {"psycopg": None, "psycopg2": FakePsycopg2}), mock.patch.dict(
            os.environ,
            {"FBBP_A2A_TEST_POSTGRES_DSN": "postgresql://u:p@localhost:5432/db"},
        ):
            conn = _pg_connect(config)

        self.assertTrue(str(conn).startswith("psycopg2:"))

    def test_react_trace_artifact_records_plan_tool_observation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            trace = build_react_trace(
                run_id="cp_demo",
                request={"query": "find evidence", "top_k": 5},
                route_decision={"primary_route": "private_rag", "decision_source": "rules"},
                final_record={
                    "status": "succeeded",
                    "executor": {"name": "query_private_rag.py", "mode": "subprocess"},
                    "artifacts": {"primary_output_json": "out.json"},
                    "child_runs": [],
                    "errors": [],
                    "judge": {"score": 1.0},
                },
                result_summary={"answer_preview": "evidence found"},
            )
            paths = write_react_trace(run_dir, trace)
            lines = (run_dir / "react_trace.jsonl").read_text(encoding="utf-8").splitlines()

        self.assertEqual([item["phase"] for item in trace], ["plan", "tool_call", "observation", "revise", "report"])
        self.assertEqual(len(lines), 5)
        self.assertIn("react_trace_jsonl", paths)

    def test_redis_and_production_templates_are_loadable(self) -> None:
        redis_config = load_yaml_config(REPO_ROOT / "configs" / "control_plane" / "worker_queue.redis.example.yaml")
        production_config = load_yaml_config(REPO_ROOT / "configs" / "control_plane" / "a2a.production.example.yaml")

        self.assertEqual(redis_config["queue_backend"], "redis")
        self.assertEqual(production_config["queue_backend"], "postgres")
        self.assertTrue(production_config["auth"]["oidc"]["enabled"])
        self.assertIn("redis", production_config)


if __name__ == "__main__":
    unittest.main()
