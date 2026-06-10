from __future__ import annotations

import unittest
from pathlib import Path

import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from control_plane.router import route_request


class ControlPlaneRouterTests(unittest.TestCase):
    def test_formal_case_file_is_routed_to_formal_case(self) -> None:
        request = {
            "requested_mode": "auto",
            "case_path": str((REPO_ROOT / "configs" / "formal_cases" / "fbbp_knottin_landscape_01.yaml").resolve()),
            "batch_path": None,
            "run_dir": None,
            "report_json": None,
            "evidence_json": None,
            "query": None,
            "force_primary_route": None,
            "requested_secondary_capabilities": [],
            "input_files": [
                {
                    "field": "case_path",
                    "path": str((REPO_ROOT / "configs" / "formal_cases" / "fbbp_knottin_landscape_01.yaml").resolve()),
                }
            ],
        }

        decision = route_request(request)

        self.assertEqual(decision["primary_route"], "formal_case")
        self.assertEqual(decision["decision_source"], "file_rule")

    def test_batch_file_is_routed_to_batch_eval(self) -> None:
        request = {
            "requested_mode": "auto",
            "case_path": None,
            "batch_path": str((REPO_ROOT / "configs" / "formal_batches" / "weekly_validation_batch.yaml").resolve()),
            "run_dir": None,
            "report_json": None,
            "evidence_json": None,
            "query": None,
            "force_primary_route": None,
            "requested_secondary_capabilities": [],
            "input_files": [
                {
                    "field": "batch_path",
                    "path": str((REPO_ROOT / "configs" / "formal_batches" / "weekly_validation_batch.yaml").resolve()),
                }
            ],
        }

        decision = route_request(request)

        self.assertEqual(decision["primary_route"], "batch_eval")

    def test_force_primary_route_wins(self) -> None:
        request = {
            "requested_mode": "auto",
            "query": "请查一下 knottin 的私有证据",
            "case_path": None,
            "batch_path": None,
            "run_dir": None,
            "report_json": None,
            "evidence_json": None,
            "force_primary_route": "fallback_general",
            "requested_secondary_capabilities": [],
            "input_files": [],
        }

        decision = route_request(request)

        self.assertEqual(decision["primary_route"], "fallback_general")
        self.assertTrue(decision["forced_primary_route"])

    def test_private_rag_query_enables_candidate_compile_when_filter_like(self) -> None:
        request = {
            "requested_mode": "interactive",
            "query": "筛选 knottin scaffold 里 target 是 EGFR 的候选并按 score 排序",
            "case_path": None,
            "batch_path": None,
            "run_dir": None,
            "report_json": None,
            "evidence_json": None,
            "force_primary_route": None,
            "requested_secondary_capabilities": [],
            "input_files": [],
        }

        decision = route_request(request)

        self.assertEqual(decision["primary_route"], "private_rag")
        self.assertIn("candidate_query_compile", decision["secondary_capabilities"])

    def test_formal_mode_enables_formal_evidence_pack(self) -> None:
        request = {
            "requested_mode": "formal",
            "query": None,
            "case_path": str((REPO_ROOT / "configs" / "formal_cases" / "fbbp_knottin_landscape_01.yaml").resolve()),
            "batch_path": None,
            "run_dir": None,
            "report_json": None,
            "evidence_json": None,
            "force_primary_route": None,
            "requested_secondary_capabilities": [],
            "input_files": [
                {
                    "field": "case_path",
                    "path": str((REPO_ROOT / "configs" / "formal_cases" / "fbbp_knottin_landscape_01.yaml").resolve()),
                }
            ],
        }

        decision = route_request(request)

        self.assertEqual(decision["primary_route"], "formal_case")
        self.assertIn("formal_evidence_pack", decision["secondary_capabilities"])
