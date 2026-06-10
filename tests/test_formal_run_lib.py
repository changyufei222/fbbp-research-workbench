from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import formal_run_lib  # type: ignore  # noqa: E402


class FormalRunLibTests(unittest.TestCase):
    def test_build_run_id_uses_timestamp_and_case_id(self) -> None:
        run_id = formal_run_lib.build_run_id(
            "fbbp_knottin_landscape_01",
            datetime(2026, 4, 15, 20, 30, 0),
        )

        self.assertEqual(run_id, "20260415_203000_fbbp_knottin_landscape_01")

    def test_initialize_run_manifest_starts_in_prepared_state(self) -> None:
        manifest = formal_run_lib.initialize_run_manifest(
            run_id="20260415_203000_fbbp_knottin_landscape_01",
            case_config={
                "case_id": "fbbp_knottin_landscape_01",
                "dataset_version": "fbbp_private_v2026_04",
            },
            runtime_profile="local_formal",
            mcp_contract_version="1.0",
        )

        self.assertEqual(manifest["status"], "prepared")
        self.assertEqual(manifest["errors"], [])
        self.assertEqual(manifest["case_id"], "fbbp_knottin_landscape_01")
        self.assertEqual(manifest["dataset_version"], "fbbp_private_v2026_04")

    def test_normalize_evidence_item_requires_source_and_locator(self) -> None:
        with self.assertRaises(ValueError):
            formal_run_lib.normalize_evidence_item({"tool": "search_knowledge"}, "fbbp_private_v2026_04", "1.0")

    def test_write_jsonl_writes_one_json_object_per_line(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = Path(temp_dir) / "tool_calls.jsonl"
            formal_run_lib.write_jsonl(
                out_path,
                [
                    {"tool": "search_knowledge", "status": "ok"},
                    {"tool": "get_document_chunk", "status": "ok"},
                ],
            )

            lines = out_path.read_text(encoding="utf-8").strip().splitlines()

        self.assertEqual(len(lines), 2)
        self.assertIn('"tool": "search_knowledge"', lines[0])

    def test_build_formal_outputs_from_raw_deerflow_result(self) -> None:
        raw = {
            "thread_id": "fbbp_knottin_landscape_01",
            "prompt": "Summarize the strongest evidence-backed knottin scaffold patterns in the current FBBP database.",
            "answer": "Supported conclusion.",
            "tool_events": [
                {
                    "name": "search_knowledge",
                    "content": '{"result": {"results": [{"source": "cov.csv", "chunk_id": "chunk-1", "metadata": {"record_type": "csv"}}]}}',
                }
            ],
        }

        outputs = formal_run_lib.build_formal_outputs(
            raw,
            case_config={
                "case_id": "fbbp_knottin_landscape_01",
                "title": "FBBP knottin scaffold landscape review",
            },
            dataset_version="fbbp_private_v2026_04",
            contract_version="1.0",
            template_path=REPO_ROOT / "templates" / "formal_report_template.md",
        )

        self.assertIn("report_json", outputs)
        self.assertIn("report_markdown", outputs)
        self.assertEqual(outputs["evidence"][0]["chunk_id"], "chunk-1")
        self.assertEqual(outputs["evidence"][0]["dataset_version"], "fbbp_private_v2026_04")
        self.assertEqual(outputs["tool_call_rows"][0]["tool"], "search_knowledge")

    def test_build_formal_outputs_supports_partial_evidence_only_completion(self) -> None:
        raw = {
            "thread_id": "fbbp_knottin_landscape_01",
            "prompt": "Summarize the strongest evidence-backed knottin scaffold patterns in the current FBBP database.",
            "answer": "",
            "partial": True,
            "termination_reason": "recursion_limit",
            "termination_error": "GraphRecursionError",
            "tool_events": [
                {
                    "name": "search_knowledge",
                    "content": '{"result": {"results": [{"source": "cov.csv", "chunk_id": "chunk-1"}]}}',
                }
            ],
        }

        outputs = formal_run_lib.build_formal_outputs(
            raw,
            case_config={
                "case_id": "fbbp_knottin_landscape_01",
                "title": "FBBP knottin scaffold landscape review",
            },
            dataset_version="fbbp_private_v2026_04",
            contract_version="1.0",
            template_path=REPO_ROOT / "templates" / "formal_report_template.md",
        )

        self.assertEqual(outputs["report_json"]["completion_mode"], "partial_evidence_only")
        self.assertIn("captured evidence only", outputs["report_json"]["conclusions"][0])
        self.assertIn("recursion_limit", outputs["report_json"]["limitations"][0])
        self.assertIn("Execution Notes", outputs["report_markdown"])

    def test_build_formal_outputs_parses_langchain_text_block_tool_payload(self) -> None:
        raw = {
            "thread_id": "fbbp_knottin_landscape_01",
            "prompt": "Summarize the strongest evidence-backed knottin scaffold patterns in the current FBBP database.",
            "answer": "",
            "tool_events": [
                {
                    "name": "search_knowledge",
                    "content": "[{'type': 'text', 'text': '{\"result\": {\"results\": [{\"source\": \"cov.csv\", \"chunk_id\": \"chunk-1\"}]}}'}]",
                }
            ],
        }

        outputs = formal_run_lib.build_formal_outputs(
            raw,
            case_config={
                "case_id": "fbbp_knottin_landscape_01",
                "title": "FBBP knottin scaffold landscape review",
            },
            dataset_version="fbbp_private_v2026_04",
            contract_version="1.0",
            template_path=REPO_ROOT / "templates" / "formal_report_template.md",
        )

        self.assertEqual(outputs["evidence"][0]["source"], "cov.csv")
        self.assertEqual(outputs["evidence"][0]["chunk_id"], "chunk-1")

    def test_build_formal_outputs_prefers_tool_answer_for_partial_completion(self) -> None:
        raw = {
            "thread_id": "fbbp_knottin_landscape_01",
            "prompt": "Summarize the strongest evidence-backed knottin scaffold patterns in the current FBBP database.",
            "answer": "Now let me search for more specific PDB resolution data:",
            "partial": True,
            "termination_reason": "recursion_limit",
            "tool_events": [
                {
                    "name": "search_knowledge",
                    "content": "[{'type': 'text', 'text': '{\"result\": {\"answer\": \"Antibody 35b5 is strongly supported for RBD binding.\", \"results\": [{\"source\": \"cov.csv\", \"chunk_id\": \"chunk-1\"}, {\"source\": \"cov.csv\", \"chunk_id\": \"chunk-1\"}]}}'}]",
                }
            ],
        }

        outputs = formal_run_lib.build_formal_outputs(
            raw,
            case_config={
                "case_id": "fbbp_knottin_landscape_01",
                "title": "FBBP knottin scaffold landscape review",
            },
            dataset_version="fbbp_private_v2026_04",
            contract_version="1.0",
            template_path=REPO_ROOT / "templates" / "formal_report_template.md",
        )

        self.assertEqual(
            outputs["report_json"]["conclusions"][0],
            "Antibody 35b5 is strongly supported for RBD binding.",
        )
        self.assertEqual(len(outputs["evidence"]), 1)

    def test_build_formal_outputs_extracts_evidence_from_source_summary_tools(self) -> None:
        raw = {
            "thread_id": "fbbp_source_provenance_review_01",
            "prompt": "Review which indexed sources dominate the current FBBP runtime.",
            "answer": "The indexed runtime is dominated by plmsearch results and several 1996-chunk assay tables.",
            "tool_events": [
                {
                    "name": "list_sources",
                    "content": json.dumps(
                        {
                            "result": {
                                "sources": [
                                    {"source": "plmsearch_results.csv", "record_type": "jsonl", "chunk_count": 38079},
                                    {"source": "protein_cards_v2.jsonl", "record_type": "jsonl", "chunk_count": 1996},
                                ]
                            }
                        },
                        ensure_ascii=False,
                    ),
                },
                {
                    "name": "get_source_summary",
                    "content": json.dumps(
                        {
                            "result": {
                                "source": "protein_cards_v2.jsonl",
                                "record_types": [
                                    {"source": "protein_cards_v2.jsonl", "record_type": "jsonl", "chunk_count": 1996}
                                ],
                                "total_chunks": 1996,
                            }
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
            contract_version="1.0",
            template_path=REPO_ROOT / "templates" / "formal_report_template.md",
        )

        self.assertEqual(len(outputs["evidence"]), 3)
        self.assertEqual(outputs["evidence"][0]["source"], "plmsearch_results.csv")
        self.assertIn("chunk_count=38079", outputs["evidence"][0]["chunk_id"])
        self.assertEqual(outputs["evidence"][1]["source"], "protein_cards_v2.jsonl")
        self.assertEqual(outputs["evidence"][2]["source"], "protein_cards_v2.jsonl")

    def test_build_formal_outputs_synthesizes_provenance_summary_when_agent_answer_is_placeholder(self) -> None:
        raw = {
            "thread_id": "fbbp_source_provenance_review_01",
            "prompt": "Review which indexed sources dominate the current FBBP runtime.",
            "answer": "I'll follow your instructions step by step to analyze the FBBP database sources.",
            "tool_events": [
                {
                    "name": "list_sources",
                    "content": json.dumps(
                        {
                            "result": {
                                "sources": [
                                    {"source": "plmsearch_results.csv", "record_type": "jsonl", "chunk_count": 38079},
                                    {"source": "loop_annotations.csv", "record_type": "jsonl", "chunk_count": 3383},
                                    {"source": "loop_flexibility_results.csv", "record_type": "jsonl", "chunk_count": 3383},
                                    {"source": "protein_cards_v2.jsonl", "record_type": "jsonl", "chunk_count": 1996},
                                ]
                            }
                        },
                        ensure_ascii=False,
                    ),
                },
                {
                    "name": "get_source_summary",
                    "content": json.dumps(
                        {
                            "result": {
                                "source": "plmsearch_results.csv",
                                "record_types": [
                                    {"source": "plmsearch_results.csv", "record_type": "jsonl", "chunk_count": 38079}
                                ],
                                "total_chunks": 38079,
                            }
                        },
                        ensure_ascii=False,
                    ),
                },
                {
                    "name": "get_source_summary",
                    "content": json.dumps(
                        {
                            "result": {
                                "source": "loop_annotations.csv",
                                "record_types": [
                                    {"source": "loop_annotations.csv", "record_type": "jsonl", "chunk_count": 3383}
                                ],
                                "total_chunks": 3383,
                            }
                        },
                        ensure_ascii=False,
                    ),
                },
                {
                    "name": "get_source_summary",
                    "content": json.dumps(
                        {
                            "result": {
                                "source": "loop_flexibility_results.csv",
                                "record_types": [
                                    {"source": "loop_flexibility_results.csv", "record_type": "jsonl", "chunk_count": 3383}
                                ],
                                "total_chunks": 3383,
                            }
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
            contract_version="1.0",
            template_path=REPO_ROOT / "templates" / "formal_report_template.md",
        )

        conclusion = outputs["report_json"]["conclusions"][0]
        self.assertIn("plmsearch_results.csv", conclusion)
        self.assertIn("38079", conclusion)
        self.assertIn("loop_annotations.csv", conclusion)
        self.assertIn("`chunk_count` measures indexed coverage", conclusion)

    def test_build_formal_outputs_synthesizes_knottin_summary_when_agent_answer_is_placeholder(self) -> None:
        raw = {
            "thread_id": "fbbp_knottin_landscape_01",
            "prompt": "Review knottin scaffold evidence in the current FBBP runtime.",
            "answer": "I'll start by searching the private FBBP knowledge base for information about knottin scaffold structural features and target classes.",
            "tool_events": [
                {
                    "name": "search_knowledge",
                    "content": json.dumps(
                        {
                            "result": {
                                "results": [
                                    {
                                        "source": "interaction_cards_v2.jsonl",
                                        "chunk_id": "interaction-v2:INT-00146",
                                        "excerpt": "Interaction Centered Card: INT-00146\nProtein Context\n- Canonical Name: Ecballium elaterium trypsin inhibitor EETI-II\n- Description: CYSTINE KNOT SCAFFOLD PLATFORM\nDomain Context\n- Domain Name: VEGF_CKP9.63\n- Sequence: GCDVMQPYWGCKQDSDCLAGCVCHWYNSCG\n- Is Engineered: Yes\n- Scaffold Type: knottin",
                                    },
                                    {
                                        "source": "interaction_cards_v2.jsonl",
                                        "chunk_id": "interaction-v2:INT-00168",
                                        "excerpt": "Interaction Centered Card: INT-00168\nProtein Context\n- Canonical Name: EETI-II\n- Description: CYSTINE KNOT SCAFFOLD PLATFORM\nDomain Context\n- Domain Name: LRP6_CKP6\n- Sequence: GCRNSIKRCKQNSDCLAGCVCSVGHGCG\n- Is Engineered: Yes\n- Scaffold Type: knottin",
                                    },
                                    {
                                        "source": "interaction_cards_v2.jsonl",
                                        "chunk_id": "interaction-v2:INT-01333",
                                        "excerpt": "Interaction Centered Card: INT-01333\nDomain Context\n- Domain Name: R1333_knottin_SEQ_1AF9D7A48DBF\n- Is Engineered: No\n- Scaffold Type: knottin",
                                    },
                                ]
                            }
                        },
                        ensure_ascii=False,
                    ),
                }
            ],
        }

        outputs = formal_run_lib.build_formal_outputs(
            raw,
            case_config={
                "case_id": "fbbp_knottin_landscape_01",
                "title": "FBBP knottin scaffold landscape review",
            },
            dataset_version="fbbp_private_v2026_04",
            contract_version="1.0",
            template_path=REPO_ROOT / "templates" / "formal_report_template.md",
        )

        conclusion = outputs["report_json"]["conclusions"][0]
        self.assertIn("interaction_cards_v2.jsonl", conclusion)
        self.assertIn("VEGF_CKP9.63", conclusion)
        self.assertIn("LRP6_CKP6", conclusion)
        self.assertIn("cystine knot scaffold", conclusion.lower())

    def test_build_formal_outputs_downgrades_assertive_answer_when_tool_answer_is_low_confidence(self) -> None:
        raw = {
            "thread_id": "fbbp_knottin_landscape_01",
            "prompt": "Review knottin scaffold evidence in the current FBBP runtime.",
            "answer": "Based on the evidence retrieved from the FBBP knowledge base, knottins broadly target viral pathogens and insect pests across the database.",
            "tool_events": [
                {
                    "name": "search_knowledge",
                    "content": json.dumps(
                        {
                            "result": {
                                "answer": "Insufficient evidence to answer confidently.",
                                "structured_output": {
                                    "claims": [
                                        {
                                            "claim_id": "claim_1",
                                            "text": "Insufficient evidence to answer confidently.",
                                            "support": "retrieved_evidence",
                                            "evidence_count": 3,
                                        }
                                    ]
                                },
                                "results": [
                                    {
                                        "source": "interaction_cards_v2.jsonl",
                                        "chunk_id": "interaction-v2:INT-00146",
                                        "excerpt": "Interaction Centered Card: INT-00146\nProtein Context\n- Canonical Name: Ecballium elaterium trypsin inhibitor EETI-II\n- Description: CYSTINE KNOT SCAFFOLD PLATFORM\nDomain Context\n- Domain Name: VEGF_CKP9.63\n- Sequence: GCDVMQPYWGCKQDSDCLAGCVCHWYNSCG\n- Is Engineered: Yes\n- Scaffold Type: knottin",
                                    },
                                    {
                                        "source": "interaction_cards_v2.jsonl",
                                        "chunk_id": "interaction-v2:INT-00168",
                                        "excerpt": "Interaction Centered Card: INT-00168\nProtein Context\n- Canonical Name: EETI-II\n- Description: CYSTINE KNOT SCAFFOLD PLATFORM\nDomain Context\n- Domain Name: LRP6_CKP6\n- Sequence: GCRNSIKRCKQNSDCLAGCVCSVGHGCG\n- Is Engineered: Yes\n- Scaffold Type: knottin",
                                    },
                                    {
                                        "source": "interaction_cards_v2.jsonl",
                                        "chunk_id": "interaction-v2:INT-01333",
                                        "excerpt": "Interaction Centered Card: INT-01333\nDomain Context\n- Domain Name: R1333_knottin_SEQ_1AF9D7A48DBF\n- Is Engineered: No\n- Scaffold Type: knottin",
                                    },
                                ],
                            }
                        },
                        ensure_ascii=False,
                    ),
                }
            ],
        }

        outputs = formal_run_lib.build_formal_outputs(
            raw,
            case_config={
                "case_id": "fbbp_knottin_landscape_01",
                "title": "FBBP knottin scaffold landscape review",
            },
            dataset_version="fbbp_private_v2026_04",
            contract_version="1.0",
            template_path=REPO_ROOT / "templates" / "formal_report_template.md",
        )

        conclusion = outputs["report_json"]["conclusions"][0]
        self.assertIn("Retrieved knottin evidence is concentrated", conclusion)
        self.assertNotIn("broadly target viral pathogens and insect pests across the database", conclusion)
        self.assertNotEqual(outputs["report_json"]["claims"][0]["text"], "Insufficient evidence to answer confidently.")
        self.assertIn("low-confidence", outputs["report_json"]["limitations"][-1])
        self.assertIn("constrained to retrieved evidence", outputs["report_json"]["provenance_caveats"][-1])

    def test_resolve_runner_settings_supports_case_overrides(self) -> None:
        settings = formal_run_lib.resolve_runner_settings(
            {
                "case_id": "fbbp_knottin_landscape_01",
                "runner": {
                    "recursion_limit": 12,
                    "max_seconds": 240,
                    "stop_on_tool_answer": {
                        "tool_name": "search_knowledge",
                        "min_results": 5,
                        "require_answer": True,
                        "require_evidence": True,
                    },
                },
            }
        )

        self.assertEqual(settings["recursion_limit"], 12)
        self.assertEqual(settings["max_seconds"], 240)
        self.assertEqual(settings["stop_on_tool_answer"]["tool_name"], "search_knowledge")
        self.assertEqual(settings["stop_on_tool_answer"]["min_results"], 5)
        self.assertFalse(settings["stop_on_tool_answer"]["allow_low_confidence_answer_with_evidence"])
        self.assertFalse(settings["preflight_search_knowledge"]["enabled"])
        self.assertFalse(settings["preflight_source_provenance"]["enabled"])

    def test_evaluate_tool_stop_condition_returns_answer_when_primary_tool_is_sufficient(self) -> None:
        runner_settings = formal_run_lib.resolve_runner_settings(
            {
                "case_id": "fbbp_knottin_landscape_01",
                "runner": {
                    "stop_on_tool_answer": {
                        "tool_name": "search_knowledge",
                        "min_results": 2,
                        "require_answer": True,
                        "require_evidence": True,
                    }
                },
            }
        )
        stop_payload = formal_run_lib.evaluate_tool_stop_condition(
            {
                "name": "search_knowledge",
                "content": json.dumps(
                    {
                        "result": {
                            "answer": "Antibody 35b5 is strongly supported for RBD binding.",
                            "results": [
                                {"source": "cov.csv", "chunk_id": "chunk-1"},
                                {"source": "cov.csv", "chunk_id": "chunk-2"},
                            ],
                        }
                    },
                    ensure_ascii=False,
                ),
            },
            runner_settings,
        )

        self.assertIsNotNone(stop_payload)
        assert stop_payload is not None
        self.assertEqual(
            stop_payload["answer"],
            "Antibody 35b5 is strongly supported for RBD binding.",
        )
        self.assertEqual(stop_payload["result_count"], 2)
        self.assertEqual(stop_payload["stop_reason"], "usable_tool_answer")

    def test_evaluate_tool_stop_condition_rejects_placeholder_tool_answer(self) -> None:
        runner_settings = formal_run_lib.resolve_runner_settings(
            {
                "case_id": "fbbp_knottin_landscape_01",
                "runner": {
                    "stop_on_tool_answer": {
                        "tool_name": "search_knowledge",
                        "min_results": 2,
                        "require_answer": True,
                        "require_evidence": True,
                    }
                },
            }
        )

        stop_payload = formal_run_lib.evaluate_tool_stop_condition(
            {
                "name": "search_knowledge",
                "content": json.dumps(
                    {
                        "result": {
                            "answer": "Insufficient evidence to answer confidently.",
                            "results": [
                                {"source": "cov.csv", "chunk_id": "chunk-1"},
                                {"source": "cov.csv", "chunk_id": "chunk-2"},
                            ],
                        }
                    },
                    ensure_ascii=False,
                ),
            },
            runner_settings,
        )

        self.assertIsNone(stop_payload)

    def test_evaluate_tool_stop_condition_accepts_low_confidence_answer_when_evidence_is_sufficient(self) -> None:
        runner_settings = formal_run_lib.resolve_runner_settings(
            {
                "case_id": "fbbp_knottin_landscape_01",
                "runner": {
                    "stop_on_tool_answer": {
                        "tool_name": "search_knowledge",
                        "min_results": 2,
                        "require_answer": True,
                        "require_evidence": True,
                        "allow_low_confidence_answer_with_evidence": True,
                    }
                },
            }
        )

        stop_payload = formal_run_lib.evaluate_tool_stop_condition(
            {
                "name": "search_knowledge",
                "content": json.dumps(
                    {
                        "result": {
                            "answer": "Insufficient evidence to answer confidently.",
                            "results": [
                                {"source": "cov.csv", "chunk_id": "chunk-1"},
                                {"source": "cov.csv", "chunk_id": "chunk-2"},
                            ],
                        }
                    },
                    ensure_ascii=False,
                ),
            },
            runner_settings,
        )

        self.assertIsNotNone(stop_payload)
        assert stop_payload is not None
        self.assertEqual(stop_payload["answer_confidence"], "low")
        self.assertEqual(stop_payload["stop_reason"], "evidence_sufficient_low_confidence_answer")


if __name__ == "__main__":
    unittest.main()
