from __future__ import annotations

import unittest
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
DEERFLOW_README = WORKSPACE_ROOT / "fbbp-research-workbench" / "README.md"
RUNBOOK = WORKSPACE_ROOT / "fbbp-research-workbench" / "docs" / "scripted_runbook.md"
FRONTEND_README = WORKSPACE_ROOT / "upstream-deerflow" / "frontend" / "README.md"
SHOWCASE = WORKSPACE_ROOT / "upstream-deerflow" / "frontend" / "src" / "components" / "fbbp" / "fbbp-showcase.tsx"
SILENT_LAUNCHER = WORKSPACE_ROOT / "fbbp-research-workbench" / "scripts" / "start_deerflow_ui_silent.ps1"


class DeerflowNativeAlignmentTests(unittest.TestCase):
    def test_workspace_is_the_primary_interactive_entry_everywhere(self) -> None:
        for path in (DEERFLOW_README, RUNBOOK, FRONTEND_README, SILENT_LAUNCHER):
            content = path.read_text(encoding="utf-8")
            self.assertIn("/workspace", content, msg=f"/workspace missing in {path.name}")

    def test_formal_page_is_described_as_results_status_surface(self) -> None:
        content = SHOWCASE.read_text(encoding="utf-8").lower()
        self.assertIn("formal results", content)
        self.assertIn("status", content)
        self.assertIn("workspace", content)


if __name__ == "__main__":
    unittest.main()
