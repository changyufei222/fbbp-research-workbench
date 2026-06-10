from __future__ import annotations

import unittest
from pathlib import Path

import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from control_plane.request_parser import normalize_request, parse_args


class ControlPlaneRequestParserTests(unittest.TestCase):
    def test_answer_mode_is_none_when_not_explicitly_requested(self) -> None:
        args = parse_args(["--mode", "interactive", "--query", "ITI-D2"])
        request = normalize_request(args)

        self.assertIsNone(request["answer_mode"])


if __name__ == "__main__":
    unittest.main()
