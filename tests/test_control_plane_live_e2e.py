from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from control_plane.live_e2e import run_live_e2e


class ControlPlaneLiveE2ETests(unittest.TestCase):
    def test_live_e2e_reaches_queue_worker_run_record_and_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            summary = run_live_e2e(Path(temp_dir))

        self.assertTrue(summary["ok"])
        self.assertEqual(summary["queue_state"], "completed")
        self.assertEqual(summary["run_record_status"], "succeeded")
        self.assertEqual(summary["primary_route"], "report_generation")


if __name__ == "__main__":
    unittest.main()
