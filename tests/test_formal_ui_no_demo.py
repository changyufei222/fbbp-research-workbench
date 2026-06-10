from __future__ import annotations

import unittest
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = WORKSPACE_ROOT / "upstream-deerflow" / "frontend" / "src"
SHOWCASE_PATH = FRONTEND_ROOT / "components" / "fbbp" / "fbbp-showcase.tsx"
LIB_PATH = FRONTEND_ROOT / "lib" / "fbbp.ts"
ASK_ROUTE_PATH = FRONTEND_ROOT / "app" / "api" / "fbbp" / "ask" / "route.ts"
MCP_SEARCH_ROUTE_PATH = FRONTEND_ROOT / "app" / "api" / "fbbp" / "mcp-search" / "route.ts"
RUN_DEMO_ROUTE_PATH = FRONTEND_ROOT / "app" / "api" / "fbbp" / "run-demo" / "route.ts"
QUERY_SCRIPT_PATH = WORKSPACE_ROOT / "fbbp-research-workbench" / "scripts" / "query_private_rag.py"
START_UI_SCRIPT_PATH = WORKSPACE_ROOT / "fbbp-research-workbench" / "scripts" / "start_deerflow_ui_silent.ps1"
CAPTURE_FORMAL_SCRIPT_PATH = WORKSPACE_ROOT / "fbbp-research-workbench" / "scripts" / "capture_formal_artifacts.ps1"
FORMAL_GATEWAY_PATH = WORKSPACE_ROOT / "upstream-deerflow" / "backend" / "src" / "gateway" / "fbbp_formal.py"
DEERFLOW_FINAL_SUMMARY_PATH = WORKSPACE_ROOT / "fbbp-research-workbench" / "FINAL_RESULT_SUMMARY.md"
MCP_FINAL_SUMMARY_PATH = WORKSPACE_ROOT / "fbbp-mcp-rag-server" / "FINAL_RESULT_SUMMARY.md"


class FormalUiNoDemoTests(unittest.TestCase):
    def test_showcase_removes_demo_buttons_and_sections(self) -> None:
        content = SHOWCASE_PATH.read_text(encoding="utf-8")

        self.assertNotIn("Run RAGPPI Demo", content)
        self.assertNotIn("Run CoVUniBind Demo", content)
        self.assertNotIn("/api/fbtp/run-demo", content)
        self.assertNotIn("RAGPPI Demo", content)
        self.assertNotIn("CoVUniBind Structured Demo", content)
        self.assertNotIn('SelectItem value="ragppi"', content)
        self.assertNotIn('SelectItem value="covunibind"', content)

    def test_frontend_lib_no_longer_exposes_demo_dashboard_contract(self) -> None:
        content = LIB_PATH.read_text(encoding="utf-8")

        self.assertNotIn("export type DemoName", content)
        self.assertNotIn("runDemoScript", content)
        self.assertNotIn("getDemoPaths", content)
        self.assertNotIn("ragppiDemo", content)
        self.assertNotIn("covDemo", content)
        self.assertNotIn("ragppiMarkdown", content)
        self.assertNotIn("covMarkdown", content)
        self.assertNotIn("ragppiEval", content)
        self.assertIn("latestBatch", content)
        self.assertIn("formal_scoreboard.json", content)
        self.assertIn("latest_successful_runs.md", content)

    def test_ask_route_and_query_script_remove_sample_dataset_switches(self) -> None:
        ask_route = ASK_ROUTE_PATH.read_text(encoding="utf-8")
        query_script = QUERY_SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertNotIn("dataset?:", ask_route)
        self.assertNotIn("body.dataset", ask_route)
        self.assertNotIn("--dataset", query_script)
        self.assertNotIn("ragppi", query_script)
        self.assertNotIn("covunibind", query_script)

    def test_frontend_query_runtime_uses_formal_bge_table_not_local_hash_fallback(self) -> None:
        content = LIB_PATH.read_text(encoding="utf-8")

        self.assertNotIn('EMBEDDING_PROVIDER: process.env.EMBEDDING_PROVIDER || "local_hash"', content)
        self.assertNotIn('PGTABLE: "rag_documents"', content)

    def test_query_script_uses_http_mcp_client_for_live_search(self) -> None:
        query_script = QUERY_SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("streamablehttp_client", query_script)
        self.assertIn("ClientSession", query_script)
        self.assertIn('call_tool("search_knowledge"', query_script)
        self.assertIn("_prefer_local_service()", query_script)
        self.assertIn('import_module("fbbp_mcp_server.service")', query_script)
        self.assertIn('"local_service_fallback"', query_script)
        self.assertNotIn("embed_texts", query_script)
        self.assertNotIn('"hostname", "-I"', query_script)
        self.assertNotIn("from fbtp_mcp_server.service import search_knowledge", query_script)

    def test_frontend_live_query_uses_http_mcp_endpoint_not_wsl_pg_routing(self) -> None:
        content = LIB_PATH.read_text(encoding="utf-8")

        self.assertIn("http://127.0.0.1:8001", content)
        self.assertIn("/api/fbbp/formal-search", content)
        self.assertIn("resolveFormalGatewayBaseUrl", content)
        self.assertIn("runRawMcpSearch", content)
        self.assertNotIn("query_private_rag.py", content)
        self.assertNotIn("const wslIp = await getWslIp();", content)
        self.assertNotIn("PGHOST: wslIp", content)

    def test_formal_mcp_search_gateway_route_exists(self) -> None:
        content = MCP_SEARCH_ROUTE_PATH.read_text(encoding="utf-8")

        self.assertIn("runRawMcpSearch", content)
        self.assertIn("includeAnswer", content)
        self.assertIn("recordType", content)
        self.assertNotIn("query_private_rag.py", content)

    def test_silent_ui_start_bootstraps_wsl_pg_for_formal_queries(self) -> None:
        content = START_UI_SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("start_wsl_pgvector.ps1", content)
        self.assertIn("Test-PostgresQueryReady", content)
        self.assertNotIn("Wait-TcpPort -ComputerName '127.0.0.1' -Port 5432", content)

    def test_run_demo_api_route_is_removed(self) -> None:
        self.assertFalse(RUN_DEMO_ROUTE_PATH.exists(), msg="run-demo API route should be removed")

    def test_showcase_surfaces_formal_acceptance_panel_and_structured_query_output(self) -> None:
        content = SHOWCASE_PATH.read_text(encoding="utf-8")

        self.assertIn("Formal Acceptance Panel", content)
        self.assertIn("Official FBBP Atlas Package", content)
        self.assertIn("Stack Status", content)
        self.assertIn("Latest successful runs", content)
        self.assertIn("Structured Claims", content)
        self.assertIn("Key Findings", content)
        self.assertIn("Known Unknowns", content)
        self.assertIn("Provenance Caveats", content)

    def test_live_query_defaults_to_formal_answer_mode_for_summary_questions(self) -> None:
        content = SHOWCASE_PATH.read_text(encoding="utf-8")
        ask_route = ASK_ROUTE_PATH.read_text(encoding="utf-8")
        lib_content = LIB_PATH.read_text(encoding="utf-8")

        self.assertIn('answerMode: "formal"', content)
        self.assertIn('body.answerMode ?? "formal"', ask_route)
        self.assertIn('input.answerMode ?? "formal"', lib_content)

    def test_formal_capture_script_uses_formal_name_not_demo_name(self) -> None:
        self.assertTrue(CAPTURE_FORMAL_SCRIPT_PATH.exists(), msg="capture_formal_artifacts.ps1 should exist")
        content = CAPTURE_FORMAL_SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertNotIn("capture_demo_artifacts.ps1", content)
        self.assertIn("Get-FinalResultsRoot", content)
        self.assertIn("atlas_overview.md", content)

    def test_projects_publish_single_final_result_summary_files(self) -> None:
        for summary_path in (DEERFLOW_FINAL_SUMMARY_PATH, MCP_FINAL_SUMMARY_PATH):
            self.assertTrue(summary_path.exists(), msg=f"Missing {summary_path.name}")
            content = summary_path.read_text(encoding="utf-8")
            self.assertIn("One-line Positioning", content)
            self.assertIn("Reproduction Command", content)
            self.assertIn("Formal Report", content)
            self.assertIn("Key Number", content)
            self.assertIn("Screenshot", content)

    def test_formal_gateway_prefers_fbbp_mcp_server_with_legacy_fallback(self) -> None:
        content = FORMAL_GATEWAY_PATH.read_text(encoding="utf-8")

        self.assertIn('"fbbp_mcp_server"', content)
        self.assertIn('"fbtp_mcp_server"', content)
        self.assertNotIn("import fbtp_mcp_server.service as service_module", content)
        self.assertIn('"EMBEDDING_PROVIDER": "local_hash"', content)
        self.assertIn('"RERANKER_ENABLED": "0"', content)
        self.assertIn("with _formal_query_env()", content)


if __name__ == "__main__":
    unittest.main()
