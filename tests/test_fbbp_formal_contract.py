from __future__ import annotations

import unittest
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
ROOT_DOCS_CONTRACT = WORKSPACE_ROOT / "docs" / "fbbp_data_contract.md"
README_NOW_PATH = WORKSPACE_ROOT / "README_NOW.md"
PROJECT_MAP_PATH = WORKSPACE_ROOT / "PROJECT_DIRECTORY_MAP.md"
PORTFOLIO_SUMMARY_PATH = WORKSPACE_ROOT / "PORTFOLIO_FINAL_SUMMARIES.md"

DEERFLOW_ROOT = WORKSPACE_ROOT / "fbbp-research-workbench"
DEERFLOW_SUMMARY_PATH = DEERFLOW_ROOT / "FINAL_RESULT_SUMMARY.md"
FORMAL_RUNBOOK_PATH = DEERFLOW_ROOT / "docs" / "formal_runbook.md"
FORMAL_VALIDATION_PATH = DEERFLOW_ROOT / "docs" / "formal_case_validation.md"
SCRIPTED_RUNBOOK_PATH = DEERFLOW_ROOT / "docs" / "scripted_runbook.md"
FORMAL_CASES_ROOT = DEERFLOW_ROOT / "configs" / "formal_cases"
PROMPTS_ROOT = DEERFLOW_ROOT / "examples" / "prompts"

FRONTEND_SHOWCASE_PATH = (
    WORKSPACE_ROOT / "upstream-deerflow" / "frontend" / "src" / "components" / "fbbp" / "fbbp-showcase.tsx"
)
FRONTEND_LIB_PATH = WORKSPACE_ROOT / "upstream-deerflow" / "frontend" / "src" / "lib" / "fbbp.ts"

MCP_CONTRACT_PATH = WORKSPACE_ROOT / "fbbp-mcp-rag-server" / "docs" / "formal_tool_contract.md"
MCP_ACCEPTANCE_PATH = WORKSPACE_ROOT / "fbbp-mcp-rag-server" / "docs" / "formal_acceptance_evidence.md"
MCP_SUMMARY_PATH = WORKSPACE_ROOT / "fbbp-mcp-rag-server" / "FINAL_RESULT_SUMMARY.md"


class FbbpFormalContractTests(unittest.TestCase):
    def test_cross_project_fbbp_contract_doc_exists_and_names_real_downstream_consumers(self) -> None:
        self.assertTrue(ROOT_DOCS_CONTRACT.exists(), msg="Expected a canonical FBBP data contract doc")
        content = ROOT_DOCS_CONTRACT.read_text(encoding="utf-8")

        self.assertIn("FBBP", content)
        self.assertIn("llm-rag-knowledge-base", content)
        self.assertIn("fbbp-mcp-rag-server", content)
        self.assertIn("fbbp-research-workbench", content)
        self.assertIn("llm-eval-benchmark", content)
        self.assertIn("minimind-fbtp-lab", content)
        self.assertIn("dataset_version", content)
        self.assertIn("PGTABLE", content)

    def test_root_docs_stop_pointing_users_to_demo_commands_and_use_fbbp_identity(self) -> None:
        readme_now = README_NOW_PATH.read_text(encoding="utf-8")
        project_map = PROJECT_MAP_PATH.read_text(encoding="utf-8")
        portfolio = PORTFOLIO_SUMMARY_PATH.read_text(encoding="utf-8")

        self.assertNotIn("Run RAGPPI demo", readme_now)
        self.assertNotIn("Run CoVUniBind demo", readme_now)
        self.assertIn("FBBP", readme_now)

        self.assertNotIn("demo 脚本", project_map)
        self.assertIn("FBBP", project_map)
        self.assertIn("FBBP", portfolio)

    def test_deerflow_formal_docs_use_fbbp_language_and_no_legacy_demo_section(self) -> None:
        deerflow_summary = DEERFLOW_SUMMARY_PATH.read_text(encoding="utf-8")
        formal_runbook = FORMAL_RUNBOOK_PATH.read_text(encoding="utf-8")
        formal_validation = FORMAL_VALIDATION_PATH.read_text(encoding="utf-8")
        scripted_runbook = SCRIPTED_RUNBOOK_PATH.read_text(encoding="utf-8")

        self.assertIn("FBBP", deerflow_summary)
        self.assertNotIn("covunibind", deerflow_summary.lower())
        self.assertNotIn("ragppi", deerflow_summary.lower())

        self.assertIn("FBBP", formal_runbook)
        self.assertNotIn("Legacy Demo", formal_runbook)

        self.assertIn("FBBP", formal_validation)
        self.assertNotIn("covunibind", formal_validation.lower())
        self.assertNotIn("ragppi", formal_validation.lower())

        self.assertIn("FBBP", scripted_runbook)
        self.assertNotIn("Legacy Demo Commands", scripted_runbook)

    def test_formal_case_configs_and_prompts_are_fbbp_named(self) -> None:
        case_files = sorted(
            file for file in FORMAL_CASES_ROOT.iterdir() if file.is_file() and file.suffix.lower() in {".yaml", ".yml"}
        )
        prompt_files = sorted(file for file in PROMPTS_ROOT.iterdir() if file.is_file() and file.suffix.lower() == ".txt")

        self.assertTrue(case_files, msg="Expected at least one formal case config")
        self.assertTrue(prompt_files, msg="Expected at least one prompt file")

        self.assertTrue(
            all(file.name.startswith("fbbp_") for file in case_files),
            msg="All active formal case configs should use fbbp_* naming",
        )
        self.assertTrue(
            all(file.name.startswith("fbbp_") for file in prompt_files),
            msg="All active prompt files should use fbbp_* naming",
        )

        for case_file in case_files:
            content = case_file.read_text(encoding="utf-8")
            self.assertIn("case_id: fbbp_", content)
            self.assertIn("dataset_version: fbbp_", content)
            self.assertIn("prompt_file: examples/prompts/fbbp_", content)
            self.assertNotIn("covunibind", content.lower())
            self.assertNotIn("ragppi", content.lower())

    def test_active_fbbp_prompts_are_optimized_for_real_runtime_queries(self) -> None:
        knottin_prompt = (PROMPTS_ROOT / "fbbp_knottin_landscape_01.txt").read_text(encoding="utf-8")
        provenance_prompt = (PROMPTS_ROOT / "fbbp_source_provenance_review_01.txt").read_text(encoding="utf-8")
        knottin_case = (FORMAL_CASES_ROOT / "fbbp_knottin_landscape_01.yaml").read_text(encoding="utf-8")
        provenance_case = (FORMAL_CASES_ROOT / "fbbp_source_provenance_review_01.yaml").read_text(encoding="utf-8")

        self.assertIn("answer_mode='extractive'", knottin_prompt)
        self.assertIn("top_k=5", knottin_prompt)
        self.assertIn("max_seconds: 300", knottin_case)

        self.assertIn("list_sources", provenance_prompt)
        self.assertIn("get_source_summary", provenance_prompt)
        self.assertIn("chunk_count", provenance_prompt)
        self.assertIn("filename-based inference", provenance_prompt)
        self.assertIn("Do not call `search_knowledge` just to explain what a source filename means", provenance_prompt)
        self.assertIn("max_seconds: 300", provenance_case)

    def test_frontend_formal_console_copy_uses_fbbp_identity(self) -> None:
        showcase = FRONTEND_SHOWCASE_PATH.read_text(encoding="utf-8")
        frontend_lib = FRONTEND_LIB_PATH.read_text(encoding="utf-8")

        self.assertIn("FBBP 正式结果与状态工作台", showcase)
        self.assertIn("Ask FBBP DB", showcase)
        self.assertIn('value="FBBP private DB"', showcase)
        self.assertIn("export function FbbpShowcase", showcase)

        self.assertIn('startsWith("fbbp_")', frontend_lib)
        self.assertNotIn('startsWith("fbtp_")', frontend_lib)
        self.assertIn("FBBP_FORMAL_DATASET_VERSION", frontend_lib)
        self.assertIn("FBBP_FORMAL_RUNTIME_PROFILE", frontend_lib)

    def test_mcp_docs_use_fbbp_for_real_database_contract(self) -> None:
        mcp_contract = MCP_CONTRACT_PATH.read_text(encoding="utf-8")
        mcp_acceptance = MCP_ACCEPTANCE_PATH.read_text(encoding="utf-8")
        mcp_summary = MCP_SUMMARY_PATH.read_text(encoding="utf-8")

        self.assertIn("FBBP", mcp_contract)
        self.assertIn("FBBP", mcp_acceptance)
        self.assertIn("FBBP", mcp_summary)


if __name__ == "__main__":
    unittest.main()
