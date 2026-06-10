from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "run_fbbp_control_plane.py"


class ControlPlaneScriptTests(unittest.TestCase):
    def test_dry_run_writes_core_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "cp_run"
            proc = subprocess.run(
                [
                    "python",
                    str(SCRIPT),
                    "--dry-run",
                    "--mode",
                    "interactive",
                    "--query",
                    "总结 knottin scaffold 的私有证据",
                    "--output-dir",
                    str(run_dir),
                ],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)
            payload = json.loads(proc.stdout.strip())
            route_decision = json.loads((run_dir / "route_decision.json").read_text(encoding="utf-8"))
            run_record = json.loads((run_dir / "run_record.json").read_text(encoding="utf-8"))
            children = json.loads((run_dir / "children.json").read_text(encoding="utf-8"))
            a2a_trace = json.loads((run_dir / "a2a_trace.json").read_text(encoding="utf-8"))
            events = (run_dir / "events.jsonl").read_text(encoding="utf-8").strip().splitlines()
            judge_exists = (run_dir / "judge.json").exists()
            observability_exists = (run_dir / "observability.json").exists()

        self.assertEqual(payload["status"], "dry_run")
        self.assertEqual(route_decision["primary_route"], "private_rag")
        self.assertEqual(run_record["status"], "dry_run")
        self.assertIn("memory", run_record)
        self.assertEqual(run_record["preflight"]["hit_rate"], 0.0)
        self.assertEqual(run_record["metrics"]["route"], "private_rag")
        self.assertEqual(run_record["metrics"]["tool_success_rate"], 1.0)
        self.assertEqual(run_record["metrics"]["a2a_hop_count"], 0)
        self.assertFalse(run_record["metrics"]["cost_tracked"])
        self.assertEqual(a2a_trace["schema_version"], "fbbp.a2a.envelope.v1")
        self.assertEqual(a2a_trace["hop_count"], 0)
        self.assertEqual(children["a2a_envelopes"], [])
        self.assertTrue(judge_exists)
        self.assertTrue(observability_exists)
        self.assertGreaterEqual(len(events), 2)

    def test_report_generation_executes_from_local_report_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            report_json = temp_root / "report.json"
            report_json.write_text(
                json.dumps(
                    {
                        "title": "Synthetic report",
                        "completion_mode": "full",
                        "conclusions": ["Synthetic conclusion for control-plane report loading."],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            run_dir = temp_root / "cp_report_run"
            proc = subprocess.run(
                [
                    "python",
                    str(SCRIPT),
                    "--mode",
                    "report",
                    "--report-json",
                    str(report_json),
                    "--output-dir",
                    str(run_dir),
                ],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)
            payload = json.loads(proc.stdout.strip())
            route_decision = json.loads((run_dir / "route_decision.json").read_text(encoding="utf-8"))
            run_record = json.loads((run_dir / "run_record.json").read_text(encoding="utf-8"))
            observability = json.loads((run_dir / "observability.json").read_text(encoding="utf-8"))

        self.assertEqual(payload["status"], "succeeded")
        self.assertEqual(route_decision["primary_route"], "report_generation")
        self.assertEqual(run_record["status"], "succeeded")
        self.assertEqual(run_record["result_summary"]["title"], "Synthetic report")
        self.assertEqual(run_record["judge"]["status"], "pass")
        self.assertEqual(run_record["metrics"]["judge_score"], run_record["judge"]["score"])
        self.assertEqual(run_record["metrics"]["memory_hit"], run_record["memory"]["read_hit"])
        self.assertEqual(observability["a2a"]["hop_count"], 0)

    def test_thread_memory_resume_is_visible_on_second_run(self) -> None:
        control_plane_root = REPO_ROOT / "runs" / "control_plane"
        control_plane_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=control_plane_root) as temp_dir:
            temp_root = Path(temp_dir)
            first_run = temp_root / "run_a"
            second_run = temp_root / "run_b"
            thread_id = "cp-memory-test-thread"

            proc_one = subprocess.run(
                [
                    "python",
                    str(SCRIPT),
                    "--dry-run",
                    "--mode",
                    "interactive",
                    "--thread-id",
                    thread_id,
                    "--query",
                    "先记住我现在在做 control plane",
                    "--output-dir",
                    str(first_run),
                ],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                check=False,
            )
            self.assertEqual(proc_one.returncode, 0, msg=proc_one.stderr or proc_one.stdout)

            proc_two = subprocess.run(
                [
                    "python",
                    str(SCRIPT),
                    "--dry-run",
                    "--mode",
                    "interactive",
                    "--thread-id",
                    thread_id,
                    "--query",
                    "我刚才在做什么？",
                    "--output-dir",
                    str(second_run),
                ],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                check=False,
            )
            self.assertEqual(proc_two.returncode, 0, msg=proc_two.stderr or proc_two.stdout)
            session_memory = json.loads((second_run / "memory" / "session_memory.json").read_text(encoding="utf-8"))
            run_record = json.loads((second_run / "run_record.json").read_text(encoding="utf-8"))

        self.assertTrue(session_memory["recent_runs"])
        self.assertTrue(run_record["memory"]["read_hit"])
