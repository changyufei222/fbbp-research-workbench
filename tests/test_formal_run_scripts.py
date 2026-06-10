from __future__ import annotations

import json
import importlib.util
import inspect
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
CONFIGS_ROOT = REPO_ROOT / "configs"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))
import formal_run_lib
RUN_FORMAL_CASE_SPEC = importlib.util.spec_from_file_location("formal_run_case_script", SCRIPTS_ROOT / "run_fbbp_formal_case.py")
assert RUN_FORMAL_CASE_SPEC and RUN_FORMAL_CASE_SPEC.loader
run_formal_case = importlib.util.module_from_spec(RUN_FORMAL_CASE_SPEC)
RUN_FORMAL_CASE_SPEC.loader.exec_module(run_formal_case)
DEERFLOW_RUNNER_SPEC = importlib.util.spec_from_file_location("deerflow_embedded_runner_script", SCRIPTS_ROOT / "deerflow_embedded_runner.py")
assert DEERFLOW_RUNNER_SPEC and DEERFLOW_RUNNER_SPEC.loader
deerflow_embedded_runner = importlib.util.module_from_spec(DEERFLOW_RUNNER_SPEC)
DEERFLOW_RUNNER_SPEC.loader.exec_module(deerflow_embedded_runner)
RUN_FORMAL_BATCH_SPEC = importlib.util.spec_from_file_location("formal_run_batch_script", SCRIPTS_ROOT / "run_fbbp_formal_batch.py")
assert RUN_FORMAL_BATCH_SPEC and RUN_FORMAL_BATCH_SPEC.loader
run_formal_batch = importlib.util.module_from_spec(RUN_FORMAL_BATCH_SPEC)
RUN_FORMAL_BATCH_SPEC.loader.exec_module(run_formal_batch)


def _powershell_exe() -> str:
    return "powershell"


class FormalRunScriptTests(unittest.TestCase):
    def test_build_preflight_raw_result_returns_stop_payload_as_raw_result(self) -> None:
        runner_settings = formal_run_lib.resolve_runner_settings(
            {
                "case_id": "fbbp_knottin_landscape_01",
                "runner": {
                    "stop_on_tool_answer": {
                        "tool_name": "search_knowledge",
                        "min_results": 3,
                        "require_answer": True,
                        "require_evidence": True,
                        "allow_low_confidence_answer_with_evidence": True,
                    }
                },
            }
        )

        raw = run_formal_case._build_preflight_raw_result(
            response={
                "ok": True,
                "tool": "search_knowledge",
                "result": {
                    "answer": "Insufficient evidence to answer confidently.",
                    "result_count": 3,
                    "results": [
                        {"source": "interaction_cards_v2.jsonl", "chunk_id": "interaction-v2:INT-00146"},
                        {"source": "interaction_cards_v2.jsonl", "chunk_id": "interaction-v2:INT-00168"},
                        {"source": "interaction_cards_v2.jsonl", "chunk_id": "interaction-v2:INT-01333"},
                    ],
                },
            },
            runner_settings=runner_settings,
            prompt="Review knottin scaffold evidence in the current FBBP runtime.",
            thread_id="fbbp_knottin_landscape_01",
            tool_name="search_knowledge",
        )

        self.assertIsNotNone(raw)
        assert raw is not None
        self.assertEqual(raw["completion_reason"], "preflight:evidence_sufficient_low_confidence_answer")
        self.assertEqual(raw["tool_events"][0]["name"], "search_knowledge")

    def test_read_raw_result_prefers_preflight_when_it_satisfies_stop_policy(self) -> None:
        case_config = formal_run_lib.load_yaml_config(
            CONFIGS_ROOT / "formal_cases" / "fbbp_knottin_landscape_01.yaml"
        )
        args = type(
            "Args",
            (),
            {
                "raw_result_json": None,
                "backend_root": None,
            },
        )()
        fake_raw = {
            "thread_id": "fbbp_knottin_landscape_01",
            "prompt": "Review knottin scaffold evidence in the current FBBP runtime.",
            "answer": "Insufficient evidence to answer confidently.",
            "tool_events": [{"name": "search_knowledge", "content": "{}"}],
            "partial": False,
            "completion_reason": "preflight:evidence_sufficient_low_confidence_answer",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            with (
                mock.patch.object(run_formal_case, "_run_search_preflight", return_value=fake_raw) as mocked_preflight,
                mock.patch.object(run_formal_case, "_resolve_backend_python") as mocked_backend_python,
                mock.patch.object(run_formal_case.subprocess, "run") as mocked_subprocess,
            ):
                raw = run_formal_case._read_raw_result(args, case_config, run_dir)

        mocked_preflight.assert_called_once()
        mocked_backend_python.assert_not_called()
        mocked_subprocess.assert_not_called()
        self.assertEqual(raw["completion_reason"], "preflight:evidence_sufficient_low_confidence_answer")

    def test_build_source_preflight_raw_result_captures_list_and_summary_events(self) -> None:
        raw = run_formal_case._build_source_preflight_raw_result(
            list_response={
                "ok": True,
                "tool": "list_sources",
                "result": {
                    "sources": [
                        {"source": "plmsearch_results.csv", "record_type": "jsonl", "chunk_count": 38079},
                        {"source": "loop_annotations.csv", "record_type": "jsonl", "chunk_count": 3383},
                    ]
                },
            },
            summary_responses=[
                {
                    "ok": True,
                    "tool": "get_source_summary",
                    "request": {"source": "plmsearch_results.csv"},
                    "result": {
                        "source": "plmsearch_results.csv",
                        "record_types": [
                            {"source": "plmsearch_results.csv", "record_type": "jsonl", "chunk_count": 38079}
                        ],
                    },
                }
            ],
            prompt="Which sources dominate the current FBBP runtime?",
            thread_id="fbbp_source_provenance_review_01",
        )

        self.assertEqual(raw["completion_reason"], "preflight:source_provenance_satisfied")
        self.assertEqual(raw["preflight"]["mode"], "source_provenance")
        self.assertEqual(raw["preflight"]["hit_rate"], 1.0)
        self.assertEqual([event["name"] for event in raw["tool_events"]], ["list_sources", "get_source_summary"])

        outputs = formal_run_lib.build_formal_outputs(
            raw,
            case_config={
                "case_id": "fbbp_source_provenance_review_01",
                "title": "FBBP source provenance review",
            },
            dataset_version="fbbp_private_v2026_04",
            contract_version="1.1",
            template_path=REPO_ROOT / "templates" / "formal_report_template.md",
        )

        conclusion = outputs["report_json"]["conclusions"][0]
        self.assertIn("plmsearch_results.csv", conclusion)
        self.assertEqual(outputs["report_json"]["preflight"]["mode"], "source_provenance")

    def test_source_preflight_falls_back_to_file_registry_when_service_fails(self) -> None:
        case_config = formal_run_lib.load_yaml_config(
            CONFIGS_ROOT / "formal_cases" / "fbbp_source_provenance_review_01.yaml"
        )
        runner_settings = formal_run_lib.resolve_runner_settings(case_config)

        with mock.patch.object(
            run_formal_case,
            "_load_formal_gateway_module",
            side_effect=RuntimeError("PostgreSQL unavailable"),
        ):
            raw = run_formal_case._run_source_preflight(
                backend_root=REPO_ROOT.parent / "upstream-deerflow" / "backend",
                case_config=case_config,
                runner_settings=runner_settings,
                prompt="Which sources dominate the current FBBP runtime?",
                thread_id="fbbp_source_provenance_review_01",
            )

        self.assertIsNotNone(raw)
        assert raw is not None
        self.assertEqual(raw["preflight"]["data_source"], "file_source_registry")
        self.assertEqual(raw["preflight"]["hit_rate"], 1.0)
        self.assertEqual([event["name"] for event in raw["tool_events"][:2]], ["list_sources", "get_source_summary"])

        list_payload = json.loads(raw["tool_events"][0]["content"])
        self.assertEqual(list_payload["diagnostics"]["fallback_mode"], "file_source_registry")
        self.assertGreaterEqual(list_payload["result"]["source_count"], 3)

    def test_start_fbbp_http_mcp_passes_formal_identity_defaults(self) -> None:
        script = (SCRIPTS_ROOT / "start_fbbp_http_mcp.ps1").read_text(encoding="utf-8")

        self.assertIn("FBBP_FORMAL_DATASET_VERSION", script)
        self.assertIn("FBBP_FORMAL_RUNTIME_PROFILE", script)
        self.assertIn("-DatasetVersion", script)
        self.assertIn("-RuntimeProfile", script)
        self.assertIn("fbbp_private_v2026_04", script)
        self.assertIn("local_formal", script)
        self.assertIn("FBTP_MCP_USE_SUBPROCESS_WORKER = '0'", script)

    def test_prepare_formal_case_creates_prepared_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            proc = subprocess.run(
                [
                    _powershell_exe(),
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(SCRIPTS_ROOT / "prepare_fbbp_formal_case.ps1"),
                    "-CasePath",
                    str(CONFIGS_ROOT / "formal_cases" / "fbbp_knottin_landscape_01.yaml"),
                    "-OutputRoot",
                    str(Path(temp_dir)),
                    "-SkipHandshake",
                    "-Now",
                    "2026-04-15T20:30:00",
                ],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)
            payload = json.loads(proc.stdout.strip())
            manifest = json.loads(Path(payload["manifest_path"]).read_text(encoding="utf-8"))

        self.assertEqual(payload["run_id"], "20260415_203000_fbbp_knottin_landscape_01")
        self.assertEqual(manifest["status"], "prepared")
        self.assertEqual(manifest["case_id"], "fbbp_knottin_landscape_01")

    def test_run_formal_case_with_raw_result_json_writes_formal_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            run_dir = temp_root / "runs" / "20260415_203000_fbbp_knottin_landscape_01"
            run_dir.mkdir(parents=True, exist_ok=True)
            raw_path = temp_root / "raw_result.json"
            raw_path.write_text(
                json.dumps(
                    {
                        "thread_id": "fbbp_knottin_landscape_01",
                        "prompt": "Summarize the strongest evidence-backed knottin scaffold patterns in the current FBBP database.",
                        "answer": "Supported conclusion.",
                        "tool_events": [
                            {
                                "name": "search_knowledge",
                                "content": json.dumps(
                                    {
                                        "tool": "search_knowledge",
                                        "provenance": {
                                            "dataset_version": "fbbp_private_v2026_04",
                                            "runtime_profile": "local_formal",
                                            "db_identity": "fbbp_formal_pgvector",
                                            "build_id": "fbbp-2026-04-formal",
                                            "source_registry_version": "2026-04-16",
                                        },
                                        "result": {
                                            "answer": "Supported conclusion.",
                                            "results": [
                                                {
                                                    "source": "plmsearch_results.csv",
                                                    "chunk_id": "chunk-1",
                                                    "excerpt": "Representative FBBP knottin evidence.",
                                                    "source_category": "structure_screen",
                                                    "owner_table": "plmsearch_results",
                                                }
                                            ],
                                            "structured_output": {
                                                "claims": [
                                                    {
                                                        "claim_id": "claim_1",
                                                        "text": "Supported conclusion.",
                                                    }
                                                ],
                                                "evidence_rows": [
                                                    {
                                                        "source": "plmsearch_results.csv",
                                                        "chunk_id": "chunk-1",
                                                        "excerpt": "Representative FBBP knottin evidence.",
                                                        "source_category": "structure_screen",
                                                        "owner_table": "plmsearch_results",
                                                    }
                                                ],
                                                "limitations": [],
                                                "provenance_caveats": [
                                                    "Structured formal output came directly from MCP."
                                                ],
                                            },
                                        },
                                    },
                                    ensure_ascii=False,
                                ),
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            manifest_path = run_dir / "run_manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "run_id": "20260415_203000_fbbp_knottin_landscape_01",
                        "case_id": "fbbp_knottin_landscape_01",
                        "status": "prepared",
                        "errors": [],
                        "dataset_version": "fbbp_private_v2026_04",
                        "runtime_profile": "local_formal",
                        "mcp_contract_version": "1.0",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            proc = subprocess.run(
                [
                    "python",
                    str(SCRIPTS_ROOT / "run_fbbp_formal_case.py"),
                    "--case-path",
                    str(CONFIGS_ROOT / "formal_cases" / "fbbp_knottin_landscape_01.yaml"),
                    "--run-dir",
                    str(run_dir),
                    "--raw-result-json",
                    str(raw_path),
                ],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)
            payload = json.loads(proc.stdout.strip())
            report_json = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
            evidence = json.loads((run_dir / "evidence.json").read_text(encoding="utf-8"))
            final_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            report_md_exists = (run_dir / "report.md").exists()
            tool_calls_exists = (run_dir / "tool_calls.jsonl").exists()

        self.assertEqual(payload["status"], "succeeded")
        self.assertEqual(report_json["conclusions"], ["Supported conclusion."])
        self.assertEqual(report_json["claims"][0]["text"], "Supported conclusion.")
        self.assertEqual(report_json["runtime_provenance"]["db_identity"], "fbbp_formal_pgvector")
        self.assertEqual(report_json["provenance_caveats"][0], "Structured formal output came directly from MCP.")
        self.assertEqual(evidence[0]["chunk_id"], "chunk-1")
        self.assertEqual(evidence[0]["owner_table"], "plmsearch_results")
        self.assertEqual(final_manifest["status"], "succeeded")
        self.assertTrue(report_md_exists)
        self.assertTrue(tool_calls_exists)

    def test_build_formal_outputs_synthesizes_provenance_summary_when_answer_is_transition_text(self) -> None:
        raw = {
            "thread_id": "fbbp_source_provenance_review_01",
            "prompt": "Which primary sources dominate the current FBBP database?",
            "answer": "Now I'll get summaries for the top 3 sources by chunk_coun<local_path_removed>",
            "tool_events": [
                {
                    "name": "list_sources",
                    "content": json.dumps(
                        {
                            "tool": "list_sources",
                            "result": {
                                "sources": [
                                    {
                                        "source": "plmsearch_results.csv",
                                        "record_type": "jsonl",
                                        "chunk_count": 38079,
                                    },
                                    {
                                        "source": "loop_annotations.csv",
                                        "record_type": "jsonl",
                                        "chunk_count": 3383,
                                    },
                                    {
                                        "source": "loop_flexibility_results.csv",
                                        "record_type": "jsonl",
                                        "chunk_count": 3383,
                                    },
                                ]
                            },
                            "provenance": {
                                "dataset_version": "fbbp_private_v2026_04",
                                "runtime_profile": "local_formal",
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
                {
                    "name": "get_source_summary",
                    "content": json.dumps(
                        {
                            "tool": "get_source_summary",
                            "result": {
                                "source": "plmsearch_results.csv",
                                "record_types": [
                                    {
                                        "source": "plmsearch_results.csv",
                                        "record_type": "jsonl",
                                        "chunk_count": 38079,
                                    }
                                ],
                                "source_registry": {
                                    "source_category": "structure_screen",
                                    "source_description": "Protein language model similarity search outputs for protein rows.",
                                    "upstream_pipeline": "normalized.schema_tables.plmsearch_results",
                                    "quality_notes": "High-volume computational retrieval table frequently used in provenance inspection.",
                                    "owner_table": "plmsearch_results",
                                },
                            },
                            "provenance": {
                                "dataset_version": "fbbp_private_v2026_04",
                                "runtime_profile": "local_formal",
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }

        outputs = formal_run_lib.build_formal_outputs(
            raw,
            case_config={
                "case_id": "fbbp_source_provenance_review_01",
                "title": "FBBP source provenance review",
            },
            dataset_version="fbbp_private_v2026_04",
            contract_version="1.1",
            template_path=REPO_ROOT / "templates" / "formal_report_template.md",
        )

        conclusion = outputs["report_json"]["conclusions"][0]
        self.assertNotIn("Now I'll get summaries", conclusion)
        self.assertIn("plmsearch_results.csv", conclusion)
        self.assertIn("chunk_count", conclusion)
        self.assertEqual(outputs["report_json"]["runtime_provenance"]["dataset_version"], "fbbp_private_v2026_04")
        enriched_rows = [
            row
            for row in outputs["report_json"]["evidence_rows"]
            if row.get("source_category") == "structure_screen" and row.get("owner_table") == "plmsearch_results"
        ]
        self.assertTrue(enriched_rows)

    def test_prepare_formal_batch_creates_batch_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            proc = subprocess.run(
                [
                    _powershell_exe(),
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(SCRIPTS_ROOT / "prepare_fbbp_formal_batch.ps1"),
                    "-BatchPath",
                    str(CONFIGS_ROOT / "formal_batches" / "weekly_validation_batch.yaml"),
                    "-OutputRoot",
                    str(Path(temp_dir)),
                    "-Now",
                    "2026-04-15T21:00:00",
                ],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)
            payload = json.loads(proc.stdout.strip())
            manifest = json.loads(Path(payload["manifest_path"]).read_text(encoding="utf-8"))

        self.assertEqual(manifest["status"], "prepared")
        self.assertEqual(manifest["batch_slug"], "weekly_validation_batch")

    def test_run_formal_batch_with_raw_result_dir_writes_batch_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            raw_dir = temp_root / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            raw_payload = {
                "prompt": "Summarize the strongest evidence-backed FBBP patterns for the current query.",
                "answer": "Supported conclusion.",
                "tool_events": [
                    {
                        "name": "search_knowledge",
                        "content": '{"result": {"results": [{"source": "cov.csv", "chunk_id": "chunk-1"}]}}',
                    }
                ],
            }
            for case_id in ["fbbp_knottin_landscape_01", "fbbp_source_provenance_review_01"]:
                payload = dict(raw_payload)
                payload["thread_id"] = case_id
                (raw_dir / f"{case_id}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            proc = subprocess.run(
                [
                    "python",
                    str(SCRIPTS_ROOT / "run_fbbp_formal_batch.py"),
                    "--batch-path",
                    str(CONFIGS_ROOT / "formal_batches" / "weekly_validation_batch.yaml"),
                    "--batch-dir",
                    str(temp_root / "batches" / "20260415_210000_weekly_validation_batch"),
                    "--raw-result-dir",
                    str(raw_dir),
                    "--now",
                    "2026-04-15T21:00:00",
                ],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)
            batch_dir = temp_root / "batches" / "20260415_210000_weekly_validation_batch"
            payload = json.loads(proc.stdout.strip())
            batch_manifest = json.loads((batch_dir / "batch_manifest.json").read_text(encoding="utf-8"))
            case_runs = json.loads((batch_dir / "case_runs.json").read_text(encoding="utf-8"))
            batch_results = json.loads((batch_dir / "batch_results.json").read_text(encoding="utf-8"))
            formal_scoreboard = json.loads((batch_dir / "formal_scoreboard.json").read_text(encoding="utf-8"))
            key_metrics_snapshot = json.loads((batch_dir / "key_metrics_snapshot.json").read_text(encoding="utf-8"))
            latest_successful_runs = (batch_dir / "latest_successful_runs.md").read_text(encoding="utf-8")
            summary_exists = (batch_dir / "batch_summary.md").exists()

        self.assertEqual(payload["status"], "succeeded")
        self.assertEqual(batch_manifest["status"], "succeeded")
        self.assertIn("fbbp_knottin_landscape_01", case_runs)
        self.assertEqual(batch_results["case_count"], 2)
        self.assertEqual(formal_scoreboard["batch_id"], "20260415_210000_weekly_validation_batch")
        self.assertEqual(formal_scoreboard["status"], "succeeded")
        self.assertEqual(formal_scoreboard["dataset_version"], "fbbp_private_v2026_04")
        self.assertEqual(key_metrics_snapshot["successful_case_count"], 2)
        self.assertIn("fbbp_knottin_landscape_01", latest_successful_runs)
        self.assertTrue(summary_exists)

    def test_legacy_demo_wrappers_are_removed(self) -> None:
        self.assertFalse((SCRIPTS_ROOT / "run_deerflow_covunibind_demo.ps1").exists())
        self.assertFalse((SCRIPTS_ROOT / "run_deerflow_ragppi_demo.ps1").exists())

    def test_prepare_formal_case_uses_runtime_mcp_url(self) -> None:
        common_script = (SCRIPTS_ROOT / "common.ps1").read_text(encoding="utf-8")
        prepare_script = (SCRIPTS_ROOT / "prepare_fbbp_formal_case.ps1").read_text(encoding="utf-8")

        self.assertIn("function Get-FbbpMcpHttpUrl", common_script)
        self.assertIn("Get-FbbpMcpHttpUrl", prepare_script)
        self.assertNotIn("http://127.0.0.1:8000/mcp", prepare_script)

    def test_prepare_formal_case_uses_shared_ragkb_env_helper(self) -> None:
        prepare_script = (SCRIPTS_ROOT / "prepare_fbbp_formal_case.ps1").read_text(encoding="utf-8")

        self.assertIn("Set-RagkbEnv", prepare_script)

    def test_run_formal_case_exports_deerflow_runtime_env(self) -> None:
        formal_case_script = (SCRIPTS_ROOT / "run_fbbp_formal_case.ps1").read_text(encoding="utf-8")

        self.assertIn("Get-DeerflowRuntimeEnv", formal_case_script)
        self.assertIn('Set-Item -Path "env:$($entry.Key)" -Value $entry.Value', formal_case_script)

    def test_run_formal_batch_exports_deerflow_runtime_env(self) -> None:
        formal_batch_script = (SCRIPTS_ROOT / "run_fbbp_formal_batch.ps1").read_text(encoding="utf-8")

        self.assertIn("Get-DeerflowRuntimeEnv", formal_batch_script)
        self.assertIn('Set-Item -Path "env:$($entry.Key)" -Value $entry.Value', formal_batch_script)

    def test_resolve_backend_python_prefers_backend_venv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend_root = Path(temp_dir)
            backend_python = backend_root / ".venv" / "Scripts" / "python.exe"
            backend_python.parent.mkdir(parents=True, exist_ok=True)
            backend_python.write_text("", encoding="utf-8")

            resolved = run_formal_case._resolve_backend_python(backend_root)

        self.assertEqual(resolved, backend_python)

    def test_run_formal_case_uses_embedded_runner_state_file(self) -> None:
        runner_script = (SCRIPTS_ROOT / "deerflow_embedded_runner.py").read_text(encoding="utf-8")
        formal_case_script = (SCRIPTS_ROOT / "run_fbbp_formal_case.py").read_text(encoding="utf-8")

        self.assertIn("--state-file", runner_script)
        self.assertIn("embedded_runner_state.json", formal_case_script)
        self.assertIn("_resolve_subprocess_timeout", formal_case_script)
        self.assertNotIn("timeout=195", formal_case_script)

    def test_run_formal_case_subprocess_timeout_tracks_runner_settings(self) -> None:
        self.assertEqual(run_formal_case._resolve_subprocess_timeout({"max_seconds": 300}), 330)
        self.assertEqual(run_formal_case._resolve_subprocess_timeout({"max_seconds": 15}), 60)

    def test_run_formal_batch_targets_canonical_fbbp_case_runner(self) -> None:
        self.assertEqual(run_formal_batch.RUN_FORMAL_CASE.name, "run_fbbp_formal_case.py")

    def test_run_embedded_deerflow_accepts_state_file_argument(self) -> None:
        signature = inspect.signature(deerflow_embedded_runner.run_embedded_deerflow)
        self.assertIn("state_file", signature.parameters)

    def test_embedded_runner_tracks_ai_tool_calls_and_final_answer(self) -> None:
        runner_script = (SCRIPTS_ROOT / "deerflow_embedded_runner.py").read_text(encoding="utf-8")

        self.assertIn("nonlocal final_answer", runner_script)
        self.assertIn("msg.tool_calls", runner_script)


if __name__ == "__main__":
    unittest.main()
