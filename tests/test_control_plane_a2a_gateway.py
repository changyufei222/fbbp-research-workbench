from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import base64
import json

import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from control_plane.a2a_gateway import agent_card, handle_jsonrpc, handle_rest
from control_plane.worker_queue import get_task
from control_plane.auth import authenticate_headers, auth_metadata
from control_plane.production_hardening_check import run_hardening_check


class ControlPlaneA2AGatewayTests(unittest.TestCase):
    def test_agent_card_declares_a2a_interfaces(self) -> None:
        card = agent_card("http://localhost:9999", config={"auth": {"enabled": True}})

        self.assertEqual(card["name"], "FBBP Research Workbench Control Plane")
        self.assertIn("supportedInterfaces", card)
        self.assertEqual(card["supportedInterfaces"][0]["protocolBinding"], "JSONRPC")
        self.assertEqual(card["supportedInterfaces"][0]["protocolVersion"], "1.0")
        self.assertTrue(card["capabilities"]["streaming"])
        self.assertTrue(card["capabilities"]["pushNotifications"])
        self.assertIn("securitySchemes", card)

    def test_message_send_jsonrpc_enqueues_task_and_tasks_get_returns_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            queue_root = Path(temp_dir) / "queue"
            request = {
                "jsonrpc": "2.0",
                "id": "req-1",
                "method": "message/send",
                "params": {
                    "message": {
                        "role": "ROLE_USER",
                        "parts": [{"text": "run source provenance formal case"}],
                        "messageId": "msg-1",
                    },
                    "metadata": {
                        "trace_id": "trace_gateway_001",
                        "route": "formal_case",
                    },
                },
            }

            response = handle_jsonrpc(request, queue_root=queue_root, config={"max_attempts": 2, "backoff_seconds": 0})
            task_id = response["result"]["id"]
            fetched = handle_jsonrpc(
                {"jsonrpc": "2.0", "id": "req-2", "method": "tasks/get", "params": {"id": task_id}},
                queue_root=queue_root,
            )
            raw_task = get_task(task_id, queue_root=queue_root)

        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertEqual(response["result"]["status"]["state"], "TASK_STATE_SUBMITTED")
        self.assertEqual(fetched["result"]["id"], task_id)
        self.assertEqual(raw_task["envelope"]["message_type"], "child_run_request")
        self.assertEqual(raw_task["envelope"]["trace_id"], "trace_gateway_001")
        self.assertEqual(raw_task["envelope"]["route"], "formal_case")

    def test_rest_claim_and_result_complete_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            queue_root = Path(temp_dir) / "queue"
            _, submitted = handle_rest(
                "POST",
                "/message:send",
                {
                    "message": {
                        "role": "ROLE_USER",
                        "parts": [{"text": "summarize private evidence"}],
                        "messageId": "msg-2",
                    },
                    "metadata": {"route": "private_rag"},
                },
                queue_root=queue_root,
                config={"max_attempts": 2, "backoff_seconds": 0},
            )
            task_id = submitted["task"]["id"]
            _, claimed = handle_rest(
                "POST",
                "/a2a/tasks/claim",
                {"worker_id": "worker-rest"},
                queue_root=queue_root,
            )
            status_code, fetched = handle_rest(
                "GET",
                f"/a2a/tasks/{task_id}",
                None,
                queue_root=queue_root,
            )
            _, completed = handle_rest(
                "POST",
                f"/a2a/tasks/{task_id}/result",
                {"artifacts": [{"artifactId": "artifact-rest", "parts": [{"text": "done"}]}]},
                queue_root=queue_root,
            )
            _, events = handle_rest(
                "GET",
                f"/a2a/events?trace_id={claimed['task']['contextId']}",
                None,
                queue_root=queue_root,
            )

        self.assertEqual(claimed["task"]["id"], task_id)
        self.assertEqual(status_code, 200)
        self.assertEqual(fetched["task"]["id"], task_id)
        self.assertEqual(claimed["task"]["status"]["state"], "TASK_STATE_WORKING")
        self.assertEqual(completed["task"]["status"]["state"], "TASK_STATE_COMPLETED")
        self.assertEqual(completed["task"]["artifacts"][0]["artifactId"], "artifact-rest")
        self.assertIn("task_claimed", [event["event"] for event in events["events"]])

    def test_message_stream_returns_sse_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            queue_root = Path(temp_dir) / "queue"
            status, payload = handle_rest(
                "POST",
                "/message:stream",
                {
                    "id": "stream-1",
                    "message": {
                        "role": "ROLE_USER",
                        "parts": [{"text": "stream this task"}],
                        "messageId": "msg-stream",
                    },
                    "metadata": {"route": "fallback_general"},
                },
                queue_root=queue_root,
            )

        self.assertEqual(status, 200)
        self.assertTrue(payload["sse_events"])
        self.assertTrue(payload["sse_events"][0].startswith("event: task"))
        self.assertIn("TASK_STATE_SUBMITTED", "".join(payload["sse_events"]))

    def test_push_notification_config_jsonrpc_set_and_get(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            queue_root = Path(temp_dir) / "queue"
            submitted = handle_jsonrpc(
                {
                    "jsonrpc": "2.0",
                    "id": "req-push-1",
                    "method": "message/send",
                    "params": {
                        "message": {"role": "ROLE_USER", "parts": [{"text": "push me"}], "messageId": "msg-push"},
                        "metadata": {"route": "formal_case"},
                    },
                },
                queue_root=queue_root,
            )
            task_id = submitted["result"]["id"]
            set_response = handle_jsonrpc(
                {
                    "jsonrpc": "2.0",
                    "id": "req-push-2",
                    "method": "tasks/pushNotificationConfig/set",
                    "params": {
                        "id": task_id,
                        "pushNotificationConfig": {"url": "http://127.0.0.1:9999/webhook", "token": "demo-token"},
                    },
                },
                queue_root=queue_root,
            )
            get_response = handle_jsonrpc(
                {
                    "jsonrpc": "2.0",
                    "id": "req-push-3",
                    "method": "tasks/pushNotificationConfig/get",
                    "params": {"id": task_id},
                },
                queue_root=queue_root,
            )

        self.assertEqual(set_response["result"]["pushNotificationConfig"]["token"], "demo-token")
        self.assertEqual(get_response["result"]["pushNotificationConfig"]["url"], "http://127.0.0.1:9999/webhook")

    def test_authenticate_headers_supports_bearer_and_api_key(self) -> None:
        config = {"auth": {"enabled": True, "api_keys": ["secret"], "header_names": ["Authorization", "X-A2A-API-Key"]}}

        self.assertEqual(authenticate_headers({"Authorization": "Bearer secret"}, config), (True, "authenticated"))
        self.assertEqual(authenticate_headers({"X-A2A-API-Key": "secret"}, config), (True, "authenticated"))
        self.assertEqual(authenticate_headers({}, config), (False, "missing_api_key"))
        self.assertEqual(authenticate_headers({"Authorization": "Bearer wrong"}, config), (False, "invalid_api_key"))

    def test_authenticate_headers_supports_oidc_proxy_headers(self) -> None:
        config = {
            "auth": {
                "oidc": {
                    "enabled": True,
                    "trust_proxy_headers": True,
                    "user_header": "X-Forwarded-User",
                    "groups_header": "X-Forwarded-Groups",
                    "required_groups": ["fbbp-agent-users"],
                }
            }
        }

        self.assertEqual(
            authenticate_headers(
                {"X-Forwarded-User": "alice@example.com", "X-Forwarded-Groups": "other,fbbp-agent-users"},
                config,
            ),
            (True, "oidc_proxy_authenticated"),
        )
        self.assertEqual(
            authenticate_headers({"X-Forwarded-User": "alice@example.com", "X-Forwarded-Groups": "other"}, config),
            (False, "missing_required_oidc_group"),
        )

    def test_authenticate_headers_supports_unverified_oidc_claims_for_local_demo(self) -> None:
        def encode_segment(payload: dict[str, object]) -> str:
            raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

        token = ".".join(
            [
                encode_segment({"alg": "none"}),
                encode_segment({"iss": "https://issuer.example.com", "aud": "fbbp-a2a-gateway", "scope": "a2a:submit a2a:read"}),
                "signature",
            ]
        )
        config = {
            "auth": {
                "oidc": {
                    "enabled": True,
                    "issuer": "https://issuer.example.com",
                    "audience": "fbbp-a2a-gateway",
                    "required_scopes": ["a2a:submit"],
                    "verify_signature": False,
                }
            }
        }

        self.assertEqual(authenticate_headers({"Authorization": f"Bearer {token}"}, config), (True, "oidc_jwt_claims_authenticated"))
        self.assertIn("OIDC", auth_metadata(config)["schemes"])

    def test_production_hardening_check_reports_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_hardening_check(output_root=Path(temp_dir) / "hardening")

        self.assertTrue(result["ok"])
        self.assertGreaterEqual(result["passed_count"], 10)
        self.assertIn("backend_status", result)


if __name__ == "__main__":
    unittest.main()
