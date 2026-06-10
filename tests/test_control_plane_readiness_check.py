from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
TEST_TMP_ROOT = REPO_ROOT / ".pytest_tmp"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from control_plane import readiness_check


class ControlPlaneReadinessCheckTests(unittest.TestCase):
    def test_write_outputs_records_pass_fail_counts(self) -> None:
        checks = [
            {"name": "a", "ok": True, "elapsed_ms": 1.0},
            {"name": "b", "ok": False, "elapsed_ms": 2.0},
        ]
        TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as temp_dir:
            outputs = readiness_check._write_outputs(Path(temp_dir), checks)
            summary = json.loads(Path(outputs["summary_json"]).read_text(encoding="utf-8"))

        self.assertFalse(summary["ok"])
        self.assertEqual(summary["passed_count"], 1)
        self.assertEqual(summary["failed_count"], 1)

    def test_run_readiness_can_skip_expensive_live_checks(self) -> None:
        fake_ok = {"ok": True, "returncode": 0, "elapsed_ms": 1.0, "payload": {}, "stdout_tail": [], "stderr_tail": []}

        TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as temp_dir:
            with (
                mock.patch.object(readiness_check, "_repair_postgres_bridge", return_value={"name": "postgres_bridge", **fake_ok}),
                mock.patch.object(readiness_check, "_a2a_live_e2e", return_value={"name": "a2a_live_e2e", **fake_ok}),
                mock.patch.object(readiness_check, "_minimind_secondary", return_value={"name": "minimind_secondary", **fake_ok}),
                mock.patch.object(readiness_check, "_private_rag_live") as private_rag,
                mock.patch.object(readiness_check, "_public_lookup_live") as public_lookup,
                mock.patch.object(readiness_check, "_eval_dashboard", return_value={"name": "eval_dashboard", **fake_ok}),
            ):
                result = readiness_check.run_readiness(output_root=Path(temp_dir))

        self.assertTrue(result["ok"])
        self.assertEqual(result["check_count"], 4)
        private_rag.assert_not_called()
        public_lookup.assert_not_called()

    def test_run_readiness_can_skip_postgres_bridge_for_fast_demo(self) -> None:
        fake_ok = {"ok": True, "returncode": 0, "elapsed_ms": 1.0, "payload": {}, "stdout_tail": [], "stderr_tail": []}

        TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as temp_dir:
            with (
                mock.patch.object(readiness_check, "_repair_postgres_bridge") as postgres_bridge,
                mock.patch.object(readiness_check, "_a2a_live_e2e", return_value={"name": "a2a_live_e2e", **fake_ok}),
                mock.patch.object(readiness_check, "_minimind_secondary", return_value={"name": "minimind_secondary", **fake_ok}),
                mock.patch.object(readiness_check, "_eval_dashboard", return_value={"name": "eval_dashboard", **fake_ok}),
            ):
                result = readiness_check.run_readiness(
                    output_root=Path(temp_dir),
                    include_postgres_bridge=False,
                )

        self.assertTrue(result["ok"])
        self.assertEqual(result["check_count"], 3)
        postgres_bridge.assert_not_called()


if __name__ == "__main__":
    unittest.main()
