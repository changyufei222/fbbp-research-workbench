from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from control_plane.dashboard_server import handle_request
from control_plane.eval_dashboard import collect_run_records, summarize_records, write_dashboard, write_portfolio_dashboard


class ControlPlaneEvalDashboardTests(unittest.TestCase):
    def test_dashboard_summarizes_run_records_and_writes_eval_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_a = root / "run_a"
            run_b = root / "run_b"
            run_a.mkdir()
            run_b.mkdir()
            (run_a / "run_record.json").write_text(
                json.dumps(
                    {
                        "run_id": "run-a",
                        "primary_route": "public_lookup",
                        "status": "succeeded",
                        "metrics": {
                            "latency_ms": 100,
                            "judge_score": 0.8,
                            "tool_success_rate": 1.0,
                            "memory_hit": False,
                            "preflight_hit": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            (run_b / "run_record.json").write_text(
                json.dumps(
                    {
                        "run_id": "run-b",
                        "primary_route": "private_rag",
                        "status": "dry_run",
                        "metrics": {
                            "latency_ms": 50,
                            "judge_score": 0.1,
                            "tool_success_rate": 1.0,
                            "memory_hit": True,
                            "preflight_hit": False,
                        },
                    }
                ),
                encoding="utf-8",
            )

            records = collect_run_records(root)
            summary = summarize_records(records)
            outputs = write_dashboard(records, root / "dashboard")
            summary_exists = Path(outputs["summary_json"]).exists()
            csv_exists = Path(outputs["runs_csv"]).exists()
            md_exists = Path(outputs["summary_md"]).exists()

        self.assertEqual(summary["record_count"], 2)
        self.assertEqual(summary["route_counts"]["public_lookup"], 1)
        self.assertTrue(summary_exists)
        self.assertTrue(csv_exists)
        self.assertTrue(md_exists)

    def test_portfolio_dashboard_writes_html_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_a = root / "run_a"
            run_a.mkdir()
            (run_a / "run_record.json").write_text(
                json.dumps(
                    {
                        "run_id": "run-a",
                        "primary_route": "report_generation",
                        "status": "succeeded",
                        "metrics": {
                            "latency_ms": 10,
                            "judge_score": 0.8,
                            "tool_success_rate": 1.0,
                            "memory_hit": True,
                            "preflight_hit": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            readiness = root / "readiness.json"
            hardening = root / "hardening.json"
            memory = root / "semantic_memory.json"
            readiness.write_text(json.dumps({"ok": True, "passed_count": 3, "check_count": 3, "checks": [{"name": "a2a", "ok": True}]}), encoding="utf-8")
            hardening.write_text(json.dumps({"ok": True, "passed_count": 2, "check_count": 2, "checks": [{"name": "oidc", "ok": True}]}), encoding="utf-8")
            memory.write_text(json.dumps({"items": [{"id": "mem_1"}], "conflicts": [], "updated_at_utc": "now"}), encoding="utf-8")

            records = collect_run_records(root)
            outputs = write_portfolio_dashboard(
                records,
                root / "portfolio",
                readiness_path=readiness,
                hardening_path=hardening,
                semantic_memory_path=memory,
            )
            portfolio_html_exists = Path(outputs["portfolio_html"]).exists()
            portfolio_summary_exists = Path(outputs["portfolio_summary_json"]).exists()

        self.assertTrue(portfolio_html_exists)
        self.assertTrue(portfolio_summary_exists)

    def test_dashboard_server_handles_health_and_snapshot_routes(self) -> None:
        portfolio_root = REPO_ROOT / "reports" / "control_plane_portfolio_dashboard" / "latest"
        final_release_root = REPO_ROOT / "runs" / "control_plane" / "final_release" / "latest"
        portfolio_root.mkdir(parents=True, exist_ok=True)
        final_release_root.mkdir(parents=True, exist_ok=True)
        (portfolio_root / "portfolio_dashboard_summary.json").write_text(
            json.dumps(
                {
                    "mode": "live_local_control_console",
                    "route_overview": [{"route": "private_rag"}],
                    "recent_runs": [{"run_id": "run-a"}],
                    "semantic_memory": {"item_count": 1},
                }
            ),
            encoding="utf-8",
        )
        (portfolio_root / "semantic_memory.json").write_text(
            json.dumps({"items": [{"id": "mem_1"}], "conflicts": []}),
            encoding="utf-8",
        )
        (final_release_root / "final_release_summary.json").write_text(
            json.dumps({"ok": True, "required_passed_count": 1, "required_check_count": 1}),
            encoding="utf-8",
        )

        status, _, health_body = handle_request("GET", "/health", base_url="http://127.0.0.1:8088")
        snapshot_status, _, snapshot_body = handle_request("GET", "/api/snapshot", base_url="http://127.0.0.1:8088")

        self.assertEqual(status, 200)
        self.assertEqual(snapshot_status, 200)
        self.assertIn("http://127.0.0.1:8088/api/rebuild", health_body.decode("utf-8"))
        self.assertIn("live_local_control_console", snapshot_body.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
