from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from control_plane.a2a import (
    A2A_SCHEMA_VERSION,
    attach_a2a_trace,
    build_a2a_trace,
    validate_a2a_trace,
    validate_envelope,
)
from control_plane.run_record import build_run_metrics


class ControlPlaneA2ATests(unittest.TestCase):
    def test_build_a2a_trace_wraps_child_run_with_hop_metadata(self) -> None:
        run_record = {
            "run_id": "parent_run_001",
            "trace_id": "trace_demo_001",
            "requested_mode": "formal",
            "primary_route": "formal_case",
            "forced_primary_route": False,
            "completed_at_utc": "2026-04-30T14:30:00+00:00",
            "request_summary": {
                "case_path": "configs/formal_cases/fbbp_source_provenance_review_01.yaml",
            },
            "executor": {
                "name": "run_fbbp_formal_case.py",
                "mode": "direct_python_source_preflight",
            },
            "artifacts": {
                "primary_output_json": "children/formal_case_output.json",
            },
            "child_runs": [
                {
                    "child_run_id": "20260430_143000_fbbp_source_provenance_review_01",
                    "route": "formal_case",
                    "status": "succeeded",
                    "artifact_dir": "children/formal_case_runtime/20260430_143000_fbbp_source_provenance_review_01",
                }
            ],
        }

        trace = build_a2a_trace(run_record)

        self.assertEqual(trace["schema_version"], A2A_SCHEMA_VERSION)
        self.assertEqual(trace["hop_count"], 1)
        self.assertEqual(trace["envelope_count"], 2)
        request_envelope = trace["envelopes"][0]
        envelope = trace["envelopes"][1]
        self.assertEqual(request_envelope["message_type"], "child_run_request")
        self.assertEqual(request_envelope["phase"], "requested")
        self.assertEqual(request_envelope["status"], "requested")
        self.assertIsNone(request_envelope["payload_ref"])
        self.assertEqual(request_envelope["correlation_id"], envelope["correlation_id"])
        self.assertEqual(envelope["schema_version"], A2A_SCHEMA_VERSION)
        self.assertEqual(envelope["message_type"], "child_run_result")
        self.assertEqual(envelope["phase"], "completed")
        self.assertEqual(envelope["trace_id"], "trace_demo_001")
        self.assertEqual(envelope["parent_run_id"], "parent_run_001")
        self.assertEqual(envelope["hop_index"], 1)
        self.assertEqual(envelope["source_agent"], "fbbp-control-plane")
        self.assertEqual(envelope["target_agent"], "formal_case")
        self.assertEqual(envelope["target_executor"], "run_fbbp_formal_case.py")
        self.assertEqual(envelope["payload_ref"], "children/formal_case_output.json")
        self.assertEqual(envelope["status"], "succeeded")
        self.assertEqual(validate_a2a_trace(trace), [])

    def test_a2a_metrics_count_hops_and_child_success_rate(self) -> None:
        run_record = {
            "run_id": "parent_run_002",
            "trace_id": "trace_demo_002",
            "primary_route": "batch_eval",
            "status": "partial",
            "executor": {"name": "run_fbbp_formal_batch.ps1"},
            "timings_ms": {"total": 10.0, "execution": 9.0},
            "memory": {"read_hit": False, "resume_used": False},
            "preflight": {"hit": False, "hit_rate": 0.0},
            "child_runs": [
                {"child_run_id": "child_ok", "route": "formal_case", "status": "succeeded"},
                {"child_run_id": "child_fail", "route": "formal_case", "status": "failed"},
            ],
        }
        attach_a2a_trace(run_record, build_a2a_trace(run_record))

        metrics = build_run_metrics(run_record, {"score": 0.5, "status": "review"})

        self.assertEqual(metrics["a2a_hop_count"], 2)
        self.assertEqual(metrics["a2a_envelope_count"], 4)
        self.assertEqual(metrics["child_success_rate"], 0.5)
        self.assertEqual(metrics["tool_success_rate"], 0.5)
        self.assertEqual(metrics["a2a_schema_version"], A2A_SCHEMA_VERSION)

    def test_validate_envelope_rejects_missing_error_payload(self) -> None:
        envelope = {
            "schema_version": A2A_SCHEMA_VERSION,
            "message_id": "a2a_error",
            "correlation_id": "a2ac_error",
            "message_type": "child_run_error",
            "phase": "error",
            "trace_id": "trace_demo_003",
            "parent_run_id": "parent_run_003",
            "child_run_id": "child_error",
            "hop_index": 1,
            "source_agent": "fbbp-control-plane",
            "target_agent": "formal_case",
            "route": "formal_case",
            "status": "failed",
        }

        self.assertIn("error envelope must include error", validate_envelope(envelope))


if __name__ == "__main__":
    unittest.main()
