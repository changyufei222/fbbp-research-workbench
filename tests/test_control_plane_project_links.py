from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from control_plane.project_links import project_summary, resolved_project_links
from control_plane.public_lookup import extract_public_lookup_targets


class ControlPlaneProjectLinksTests(unittest.TestCase):
    def test_project_links_resolve_core_repositories(self) -> None:
        links = resolved_project_links()
        projects = links["projects"]

        self.assertIn("fbbp-research-workbench", projects)
        self.assertIn("fbbp-mcp-rag-server", projects)
        self.assertIn("llm-rag-knowledge-base", projects)
        self.assertIn("llm-eval-benchmark", projects)
        self.assertIn("minimind-fbtp-lab", projects)
        self.assertTrue(Path(projects["fbbp-mcp-rag-server"]["resolved_python_src"]).exists())

    def test_project_summary_is_compact_for_run_records(self) -> None:
        summary = project_summary("fbbp-mcp-rag-server", "minimind-fbtp-lab")

        self.assertEqual([item["name"] for item in summary], ["fbbp-mcp-rag-server", "minimind-fbtp-lab"])
        self.assertEqual(summary[0]["role"], "tool_plane")

    def test_public_lookup_target_extraction_detects_public_sources(self) -> None:
        targets = extract_public_lookup_targets("查 PubMed 文献并核验 UniProt P12345 和 PDB 1ABC")

        self.assertIn("pubmed", targets["providers"])
        self.assertIn("uniprot", targets["providers"])
        self.assertIn("pdb", targets["providers"])
        self.assertEqual(targets["uniprot_accessions"], ["P12345"])
        self.assertEqual(targets["pdb_ids"], ["1ABC"])


if __name__ == "__main__":
    unittest.main()
