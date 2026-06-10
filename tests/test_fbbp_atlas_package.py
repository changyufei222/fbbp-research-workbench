from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
DEERFLOW_ROOT = WORKSPACE_ROOT / "fbbp-research-workbench"
MCP_ROOT = WORKSPACE_ROOT / "fbbp-mcp-rag-server"

BUILD_SCRIPT_PY = DEERFLOW_ROOT / "scripts" / "build_fbbp_formal_package.py"
BUILD_SCRIPT_PS1 = DEERFLOW_ROOT / "scripts" / "build_fbbp_formal_package.ps1"
PACKAGE_ROOT = DEERFLOW_ROOT / "final_results" / "fbbp_formal_atlas_v2026_04"
PACKAGE_MANIFEST = PACKAGE_ROOT / "package_manifest.json"
ATLAS_OVERVIEW_MD = PACKAGE_ROOT / "atlas_overview.md"
ATLAS_OVERVIEW_JSON = PACKAGE_ROOT / "atlas_overview.json"
SCAFFOLD_ATLAS_JSON = PACKAGE_ROOT / "scaffold_atlas.json"
SCAFFOLD_ATLAS_CSV = PACKAGE_ROOT / "scaffold_atlas.csv"
TARGET_REGISTRY_JSON = PACKAGE_ROOT / "target_registry.json"
TARGET_REGISTRY_CSV = PACKAGE_ROOT / "target_registry.csv"
SOURCE_REGISTRY_JSON = PACKAGE_ROOT / "source_registry_snapshot.json"
DEERFLOW_SUMMARY = DEERFLOW_ROOT / "FINAL_RESULT_SUMMARY.md"
DEERFLOW_README = DEERFLOW_ROOT / "README.md"


class FbbpAtlasPackageTests(unittest.TestCase):
    def test_build_scripts_exist_and_target_checked_in_formal_snapshot(self) -> None:
        self.assertTrue(BUILD_SCRIPT_PY.exists(), msg="Missing Python atlas package builder")
        self.assertTrue(BUILD_SCRIPT_PS1.exists(), msg="Missing PowerShell atlas package wrapper")

        content = BUILD_SCRIPT_PY.read_text(encoding="utf-8")
        self.assertIn("formal_snapshots", content)
        self.assertIn("fbbp_private_v2026_04", content)
        self.assertIn("final_results", content)
        self.assertIn("source_registry_snapshot.json", content)
        self.assertNotIn("reports\\covunibind_demo", content)
        self.assertNotIn("reports\\ragppi_demo", content)

    def test_official_package_exists_with_required_files(self) -> None:
        self.assertTrue(PACKAGE_ROOT.exists(), msg="Official atlas package directory is missing")

        for required_path in (
            PACKAGE_MANIFEST,
            ATLAS_OVERVIEW_MD,
            ATLAS_OVERVIEW_JSON,
            SCAFFOLD_ATLAS_JSON,
            SCAFFOLD_ATLAS_CSV,
            TARGET_REGISTRY_JSON,
            TARGET_REGISTRY_CSV,
            SOURCE_REGISTRY_JSON,
        ):
            self.assertTrue(required_path.exists(), msg=f"Missing official atlas artifact: {required_path.name}")

    def test_package_manifest_reports_real_fbbp_identity(self) -> None:
        manifest = json.loads(PACKAGE_MANIFEST.read_text(encoding="utf-8"))

        self.assertEqual(manifest["dataset_name"], "FBBP")
        self.assertEqual(manifest["dataset_version"], "fbbp_private_v2026_04")
        self.assertEqual(manifest["runtime_profile"], "local_formal")
        self.assertEqual(manifest["db_identity"], "fbbp_formal_pgvector")
        self.assertIn("snapshot_manifest", manifest)
        self.assertIn("scaffold_count", manifest)
        self.assertIn("package_version", manifest)

    def test_scaffold_atlas_covers_the_full_formal_scaffold_set(self) -> None:
        atlas_rows = json.loads(SCAFFOLD_ATLAS_JSON.read_text(encoding="utf-8"))
        atlas_csv_rows = list(csv.DictReader(SCAFFOLD_ATLAS_CSV.read_text(encoding="utf-8").splitlines()))
        atlas_overview = json.loads(ATLAS_OVERVIEW_JSON.read_text(encoding="utf-8"))

        self.assertEqual(len(atlas_rows), 12)
        self.assertEqual(len(atlas_csv_rows), 12)
        self.assertEqual(atlas_overview["scaffold_count"], 12)
        self.assertIn("knottin", {str(row["scaffold"]).lower() for row in atlas_rows})
        self.assertIn("kunitz", {str(row["scaffold"]).lower() for row in atlas_rows})

    def test_target_registry_and_source_snapshot_are_non_demo_formal_outputs(self) -> None:
        target_rows = json.loads(TARGET_REGISTRY_JSON.read_text(encoding="utf-8"))
        source_snapshot = json.loads(SOURCE_REGISTRY_JSON.read_text(encoding="utf-8"))

        self.assertTrue(target_rows, msg="Expected target appendix rows")
        self.assertTrue(source_snapshot, msg="Expected source registry snapshot rows")
        self.assertIn("owner_table", source_snapshot[0])
        self.assertIn("source_category", source_snapshot[0])
        self.assertNotIn("covunibind", json.dumps(target_rows, ensure_ascii=False).lower())
        self.assertNotIn("ragppi", json.dumps(target_rows, ensure_ascii=False).lower())

    def test_deerflow_docs_point_to_the_official_atlas_package(self) -> None:
        readme = DEERFLOW_README.read_text(encoding="utf-8")
        summary = DEERFLOW_SUMMARY.read_text(encoding="utf-8")

        self.assertIn("final_results/fbbp_formal_atlas_v2026_04", readme)
        self.assertIn("atlas_overview.md", readme)
        self.assertIn("final_results/fbbp_formal_atlas_v2026_04", summary)
        self.assertIn("scaffold_atlas.csv", summary)


if __name__ == "__main__":
    unittest.main()
