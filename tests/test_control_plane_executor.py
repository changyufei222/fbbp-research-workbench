from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from control_plane import executor_registry


class ControlPlaneExecutorTests(unittest.TestCase):
    def test_private_rag_uses_fast_local_profile_and_bootstrap(self) -> None:
        fake_payload = {
            "ok": True,
            "result": {
                "answer": "Fast extractive answer",
                "result_count": 1,
            },
            "diagnostics": {
                "query_transport": "local_service_fallback",
            },
        }
        request = {
            "query": "ITI-D2",
            "top_k": 2,
            "filters": [],
            "include_answer": True,
            "include_evidence": False,
        }
        route_decision = {"primary_route": "private_rag"}

        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            with (
                mock.patch.object(executor_registry, "_run_powershell_script") as mocked_bootstrap,
                mock.patch.object(executor_registry, "_run_python_json", return_value=fake_payload) as mocked_query,
                mock.patch.object(executor_registry, "_select_python_for_query_private_rag", return_value="python"),
            ):
                result = executor_registry.execute_route(request, route_decision, run_dir)

        mocked_bootstrap.assert_called_once()
        command = mocked_query.call_args.args[0]
        env = mocked_query.call_args.kwargs["env"]
        timeout_seconds = mocked_query.call_args.kwargs["timeout_seconds"]

        self.assertIn("--answer-mode", command)
        self.assertIn("extractive", command)
        self.assertEqual(env["FBBP_LIVE_QUERY_PREFER_LOCAL"], "1")
        self.assertEqual(env["EMBEDDING_PROVIDER"], "local_hash")
        self.assertEqual(env["RERANKER_ENABLED"], "0")
        self.assertEqual(env["ANSWER_MODE"], "extractive")
        self.assertEqual(timeout_seconds, 180)
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["result_summary"]["result_count"], 1)
        self.assertEqual(
            result["result_summary"]["diagnostics"]["control_plane_profile"],
            "interactive_fast_local_hash",
        )

    def test_private_rag_bootstrap_repairs_wsl_postgres_bridge_once(self) -> None:
        with mock.patch.object(executor_registry, "_run_powershell_script") as mocked_bootstrap:
            mocked_bootstrap.side_effect = [
                RuntimeError("PostgreSQL is still not query-ready at localhost:5432 after WSL startup."),
                None,
            ]
            executor_registry._ensure_private_rag_runtime({})

        self.assertEqual(mocked_bootstrap.call_count, 2)
        self.assertIn("start_wsl_pgvector.ps1", str(mocked_bootstrap.call_args_list[0].args[0]))
        self.assertIn("repair_wsl_postgres_bridge.ps1", str(mocked_bootstrap.call_args_list[1].args[0]))

    def test_formal_case_uses_powershell_wrapper_and_child_runtime_root(self) -> None:
        fake_payload = {
            "run_id": "formal-run-1",
            "run_dir": "<local_path_removed>",
            "status": "succeeded",
        }
        request = {
            "case_path": str(
                (
                    REPO_ROOT
                    / "configs"
                    / "formal_cases"
                    / "fbbp_knottin_landscape_01.yaml"
                ).resolve()
            )
        }
        route_decision = {"primary_route": "formal_case"}

        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            with mock.patch.object(
                executor_registry,
                "_run_powershell_json",
                return_value=fake_payload,
            ) as mocked_run:
                result = executor_registry.execute_route(request, route_decision, run_dir)

        arguments = mocked_run.call_args.args[0]
        env = mocked_run.call_args.kwargs["env"]
        self.assertIn("run_fbbp_formal_case.ps1", " ".join(arguments))
        self.assertIn("-OutputRoot", arguments)
        self.assertEqual(env["OPENAI_BASE_URL"], "https://api.vectorengine.cn/v1")
        self.assertEqual(env["LLM_MODEL"], "deepseek-v3.2")
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["executor"]["mode"], "powershell_wrapper")

    def test_batch_eval_uses_powershell_wrapper_and_formal_runtime_env(self) -> None:
        fake_payload = {
            "batch_id": "batch-1",
            "batch_dir": "<local_path_removed>",
            "status": "partial",
        }
        request = {
            "batch_path": str(
                (
                    REPO_ROOT
                    / "configs"
                    / "formal_batches"
                    / "weekly_validation_batch.yaml"
                ).resolve()
            )
        }
        route_decision = {"primary_route": "batch_eval"}

        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            with mock.patch.object(
                executor_registry,
                "_run_powershell_json",
                return_value=fake_payload,
            ) as mocked_run:
                result = executor_registry.execute_route(request, route_decision, run_dir)

        arguments = mocked_run.call_args.args[0]
        env = mocked_run.call_args.kwargs["env"]
        self.assertIn("run_fbbp_formal_batch.ps1", " ".join(arguments))
        self.assertIn("-OutputRoot", arguments)
        self.assertEqual(env["OPENAI_BASE_URL"], "https://api.vectorengine.cn/v1")
        self.assertEqual(env["LLM_MODEL"], "deepseek-v3.2")
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["executor"]["mode"], "powershell_wrapper")

    def test_public_lookup_uses_direct_mcp_tool_plane(self) -> None:
        fake_payload = {
            "ok": True,
            "targets": {"providers": ["pubmed"], "pubmed_query": "knottin binder"},
            "tool_calls": [
                {
                    "tool": "search_pubmed",
                    "ok": True,
                    "latency_ms": 12.0,
                    "payload": {"result": {"articles": [{"pmid": "1", "title": "A paper"}]}},
                }
            ],
            "summary": {
                "tool_call_count": 1,
                "tool_success_count": 1,
                "tool_success_rate": 1.0,
                "article_count": 1,
                "entry_count": 0,
                "connected_projects": [],
            },
            "articles": [{"pmid": "1", "title": "A paper"}],
            "entries": [],
        }
        request = {"query": "knottin binder PubMed", "top_k": 1}
        route_decision = {"primary_route": "public_lookup"}

        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            with mock.patch.object(executor_registry, "run_public_lookup", return_value=fake_payload) as mocked_lookup:
                result = executor_registry.execute_route(request, route_decision, run_dir)
            artifact_exists = (run_dir / "children" / "public_lookup_output.json").exists()

        mocked_lookup.assert_called_once_with("knottin binder PubMed", top_k=1)
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["executor"]["mode"], "direct_mcp_tool_plane")
        self.assertEqual(result["child_runs"][0]["project"], "fbbp-mcp-rag-server")
        self.assertEqual(result["result_summary"]["tool_success_rate"], 1.0)
        self.assertTrue(artifact_exists)

    def test_candidate_query_compile_secondary_capability_attaches_minimind_artifact(self) -> None:
        fake_primary = {
            "status": "succeeded",
            "executor": {"name": "query_private_rag.py", "mode": "subprocess"},
            "timings_ms": {"execution": 10.0},
            "artifacts": {},
            "child_runs": [],
            "result_summary": {"answer_preview": "ok"},
            "errors": [],
        }
        fake_compile = {
            "ok": True,
            "mode": "rule_baseline_validator_executor",
            "validator_trace": {"schema_ok": True, "errors": [], "repairs": []},
            "execution": {"metadata": {"filtered_count": 2, "returned_count": 2}},
            "latency_ms": 3.0,
        }
        request = {"query": "筛选 knottin 有实验亲和力 前 2", "top_k": 2}
        route_decision = {
            "primary_route": "private_rag",
            "secondary_capabilities": ["candidate_query_compile"],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            with (
                mock.patch.object(executor_registry, "_private_rag", return_value=fake_primary),
                mock.patch.object(executor_registry, "run_candidate_query_compile", return_value=fake_compile) as mocked_compile,
            ):
                result = executor_registry.execute_route(request, route_decision, run_dir)
            artifact_exists = (run_dir / "children" / "candidate_query_compile_output.json").exists()

        mocked_compile.assert_called_once_with("筛选 knottin 有实验亲和力 前 2", top_k=2)
        self.assertTrue(artifact_exists)
        self.assertEqual(result["child_runs"][0]["project"], "minimind-fbtp-lab")
        self.assertTrue(result["result_summary"]["secondary_capabilities"]["candidate_query_compile"]["schema_ok"])


if __name__ == "__main__":
    unittest.main()
