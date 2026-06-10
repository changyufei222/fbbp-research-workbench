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

from control_plane.final_release_check import check_compose_static, run_final_release_check


class ControlPlaneFinalReleaseTests(unittest.TestCase):
    def test_check_compose_static_passes_for_repo_file(self) -> None:
        result = check_compose_static()
        self.assertTrue(result["ok"])

    def test_run_final_release_check_writes_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "final_release"
            with (
                mock.patch("control_plane.final_release_check.run_hardening_check", return_value={"ok": True, "passed_count": 2, "check_count": 2}),
                mock.patch(
                    "control_plane.final_release_check.backfill_memory_from_runs",
                    return_value={"records_seen": 1, "records_promoted": 1, "inserted": 1, "merged": 0, "conflicts": 0, "skipped": 0},
                ),
                mock.patch(
                    "control_plane.final_release_check.write_memory_dashboard",
                    return_value={"semantic_memory_json": "a", "semantic_memory_html": "b"},
                ),
                mock.patch(
                    "control_plane.final_release_check.collect_run_records",
                    return_value=[{"run_id": "run-a", "primary_route": "report_generation", "status": "succeeded", "metrics": {}}],
                ),
                mock.patch(
                    "control_plane.final_release_check.write_dashboard",
                    return_value={"summary_json": "c", "runs_csv": "d", "summary_md": "e"},
                ),
                mock.patch(
                    "control_plane.final_release_check.write_portfolio_dashboard",
                    return_value={"portfolio_html": "f", "portfolio_summary_json": "g"},
                ),
                mock.patch(
                    "control_plane.final_release_check.check_required_files",
                    return_value={"name": "required_release_files", "ok": True, "severity": "required", "details": {}},
                ),
                mock.patch(
                    "control_plane.final_release_check.check_compose_static",
                    return_value={"name": "docker_compose_static", "ok": True, "severity": "required", "details": {}},
                ),
                mock.patch(
                    "control_plane.final_release_check.check_docker_live",
                    return_value={"name": "docker_compose_live", "ok": True, "severity": "optional", "details": {}},
                ),
                mock.patch(
                    "control_plane.final_release_check.check_dashboard_assets",
                    return_value={"name": "portfolio_dashboard_assets", "ok": True, "severity": "required", "details": {}},
                ),
                mock.patch(
                    "control_plane.final_release_check.check_semantic_memory_state",
                    return_value={"name": "semantic_memory_state", "ok": True, "severity": "required", "details": {}},
                ),
                mock.patch(
                    "control_plane.final_release_check.check_fbbp_naming",
                    return_value={"name": "fbbp_public_naming", "ok": True, "severity": "required", "details": {}},
                ),
                mock.patch(
                    "control_plane.final_release_check._read_json",
                    return_value={"ok": True, "passed_count": 11, "check_count": 11},
                ),
            ):
                result = run_final_release_check(output_root=output_root)
                summary_path = output_root / "final_release_summary.json"
                summary_exists = summary_path.exists()
                payload = json.loads(summary_path.read_text(encoding="utf-8"))

        self.assertTrue(result["ok"])
        self.assertTrue(summary_exists)
        self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()
