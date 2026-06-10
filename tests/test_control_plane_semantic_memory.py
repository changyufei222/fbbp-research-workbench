from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from control_plane.semantic_memory import (
    backfill_memory_from_runs,
    load_semantic_memory,
    retrieve_semantic_memory,
    resolve_memory_conflict,
    upsert_memory_from_run,
    write_memory_dashboard,
)


class ControlPlaneSemanticMemoryTests(unittest.TestCase):
    def test_upsert_and_retrieve_semantic_memory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            (repo_root / "configs" / "control_plane").mkdir(parents=True, exist_ok=True)
            (repo_root / "configs" / "control_plane" / "memory_policy.yaml").write_text(
                "\n".join(
                    [
                        "version: 1",
                        "semantic_memory:",
                        "  enabled: true",
                        "  store_path: runs/control_plane/memory/semantic_memory.json",
                        "  max_items: 50",
                        "  max_conflicts_per_key: 5",
                        "  similarity_threshold: 0.3",
                        "  conflict_threshold: 0.1",
                        "  promote_statuses:",
                        "    - succeeded",
                        "  promote_routes:",
                        "    - private_rag",
                    ]
                ),
                encoding="utf-8",
            )
            policy = {
                "semantic_memory": {
                    "enabled": True,
                    "store_path": "runs/control_plane/memory/semantic_memory.json",
                    "max_items": 50,
                    "max_conflicts_per_key": 5,
                    "similarity_threshold": 0.3,
                    "conflict_threshold": 0.1,
                    "promote_statuses": ["succeeded"],
                    "promote_routes": ["private_rag"],
                }
            }
            first = upsert_memory_from_run(
                repo_root,
                {"query": "总结 knottin scaffold 的私有证据"},
                {"primary_route": "private_rag"},
                {"summary": "命中 knottin 证据"},
                run_id="run_a",
                policy=policy,
            )
            second = upsert_memory_from_run(
                repo_root,
                {"query": "总结 knottin scaffold 相关私有证据"},
                {"primary_route": "private_rag"},
                {"summary": "更多 knottin 证据"},
                run_id="run_b",
                policy=policy,
            )
            result = retrieve_semantic_memory(repo_root, "knottin scaffold", top_k=3, policy=policy)
            store = load_semantic_memory(repo_root, policy)
            outputs = write_memory_dashboard(repo_root, repo_root / "reports" / "dashboard")
            semantic_json_exists = Path(outputs["semantic_memory_json"]).exists()
            semantic_html_exists = Path(outputs["semantic_memory_html"]).exists()
            semantic_html = Path(outputs["semantic_memory_html"]).read_text(encoding="utf-8")

        self.assertTrue(first["written"])
        self.assertIn(second["action"], {"inserted", "merged"})
        self.assertTrue(result["hits"])
        self.assertGreaterEqual(len(store["items"]), 1)
        self.assertTrue(semantic_json_exists)
        self.assertTrue(semantic_html_exists)
        self.assertIn("memory-state", semantic_html)
        self.assertIn("Auto Refresh", semantic_html)

    def test_conflict_queue_records_low_similarity_same_route(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            policy = {
                "semantic_memory": {
                    "enabled": True,
                    "store_path": "runs/control_plane/memory/semantic_memory.json",
                    "max_items": 50,
                    "max_conflicts_per_key": 5,
                    "similarity_threshold": 0.95,
                    "conflict_threshold": 0.05,
                    "promote_statuses": ["succeeded"],
                    "promote_routes": ["private_rag"],
                }
            }
            upsert_memory_from_run(
                repo_root,
                {"query": "knottin scaffold oral stability evidence"},
                {"primary_route": "private_rag"},
                {"summary": "first memory"},
                run_id="run_1",
                policy=policy,
            )
            result = upsert_memory_from_run(
                repo_root,
                {"query": "different binder provenance review"},
                {"primary_route": "private_rag"},
                {"summary": "second memory"},
                run_id="run_2",
                policy=policy,
            )
            store = load_semantic_memory(repo_root, policy)

        self.assertTrue(result["written"])
        self.assertTrue(store["conflicts"])

    def test_backfill_memory_from_run_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            run_dir = repo_root / "runs" / "control_plane" / "run_private"
            run_dir.mkdir(parents=True)
            (run_dir / "run_request.json").write_text(
                json.dumps({"query": "查找 FBBP knottin 私有证据"}, ensure_ascii=False),
                encoding="utf-8",
            )
            (run_dir / "route_decision.json").write_text(
                json.dumps({"primary_route": "private_rag"}, ensure_ascii=False),
                encoding="utf-8",
            )
            (run_dir / "run_record.json").write_text(
                json.dumps(
                    {
                        "run_id": "run_private",
                        "primary_route": "private_rag",
                        "status": "succeeded",
                        "result_summary": {"summary": "private RAG evidence found"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            policy = {
                "semantic_memory": {
                    "enabled": True,
                    "store_path": "runs/control_plane/memory/semantic_memory.json",
                    "max_items": 50,
                    "max_conflicts_per_key": 5,
                    "similarity_threshold": 0.3,
                    "conflict_threshold": 0.1,
                    "promote_statuses": ["succeeded"],
                    "promote_routes": ["private_rag"],
                }
            }
            stats = backfill_memory_from_runs(repo_root, repo_root / "runs" / "control_plane", policy=policy)
            store = load_semantic_memory(repo_root, policy)

        self.assertEqual(stats["records_seen"], 1)
        self.assertEqual(stats["records_promoted"], 1)
        self.assertEqual(len(store["items"]), 1)

    def test_resolve_memory_conflict_dismisses_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            policy = {
                "semantic_memory": {
                    "enabled": True,
                    "store_path": "runs/control_plane/memory/semantic_memory.json",
                    "max_items": 50,
                    "max_conflicts_per_key": 5,
                    "similarity_threshold": 0.9,
                    "conflict_threshold": 0.05,
                    "promote_statuses": ["succeeded"],
                    "promote_routes": ["private_rag"],
                }
            }
            upsert_memory_from_run(
                repo_root,
                {"query": "knottin scaffold oral stability evidence"},
                {"primary_route": "private_rag"},
                {"summary": "first memory"},
                run_id="run_1",
                policy=policy,
            )
            upsert_memory_from_run(
                repo_root,
                {"query": "knottin binder provenance review"},
                {"primary_route": "private_rag"},
                {"summary": "second memory"},
                run_id="run_2",
                policy=policy,
            )
            store = load_semantic_memory(repo_root, policy)
            conflict_id = store["conflicts"][0]["id"]
            result = resolve_memory_conflict(repo_root, conflict_id, "dismiss", note="test", policy=policy)
            updated = load_semantic_memory(repo_root, policy)

        self.assertTrue(result["resolved"])
        self.assertEqual(updated["conflicts"][0]["status"], "resolved_dismiss")

    def test_backfill_is_idempotent_for_same_run_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            run_dir = repo_root / "runs" / "control_plane" / "run_private"
            run_dir.mkdir(parents=True)
            (run_dir / "run_request.json").write_text(
                json.dumps({"query": "查找 FBBP knottin 私有证据"}, ensure_ascii=False),
                encoding="utf-8",
            )
            (run_dir / "route_decision.json").write_text(
                json.dumps({"primary_route": "private_rag"}, ensure_ascii=False),
                encoding="utf-8",
            )
            (run_dir / "run_record.json").write_text(
                json.dumps(
                    {
                        "run_id": "run_private",
                        "primary_route": "private_rag",
                        "status": "succeeded",
                        "result_summary": {"summary": "private RAG evidence found"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            policy = {
                "semantic_memory": {
                    "enabled": True,
                    "store_path": "runs/control_plane/memory/semantic_memory.json",
                    "max_items": 50,
                    "max_conflicts_per_key": 5,
                    "similarity_threshold": 0.3,
                    "conflict_threshold": 0.1,
                    "promote_statuses": ["succeeded"],
                    "promote_routes": ["private_rag"],
                }
            }
            first = backfill_memory_from_runs(repo_root, repo_root / "runs" / "control_plane", policy=policy)
            second = backfill_memory_from_runs(repo_root, repo_root / "runs" / "control_plane", policy=policy)
            store = load_semantic_memory(repo_root, policy)

        self.assertEqual(first["records_promoted"], 1)
        self.assertEqual(second["records_promoted"], 1)
        self.assertEqual(second["merged"], 0)
        self.assertEqual(store["items"][0]["hit_count"], 1)

    def test_backfill_skips_failed_status_when_not_promoted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            run_dir = repo_root / "runs" / "control_plane" / "run_failed"
            run_dir.mkdir(parents=True)
            (run_dir / "run_request.json").write_text(
                json.dumps({"query": "失败的查询"}, ensure_ascii=False),
                encoding="utf-8",
            )
            (run_dir / "route_decision.json").write_text(
                json.dumps({"primary_route": "private_rag"}, ensure_ascii=False),
                encoding="utf-8",
            )
            (run_dir / "run_record.json").write_text(
                json.dumps(
                    {
                        "run_id": "run_failed",
                        "primary_route": "private_rag",
                        "status": "failed",
                        "result_summary": {"summary": "failed run"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            policy = {
                "semantic_memory": {
                    "enabled": True,
                    "store_path": "runs/control_plane/memory/semantic_memory.json",
                    "max_items": 50,
                    "max_conflicts_per_key": 5,
                    "similarity_threshold": 0.3,
                    "conflict_threshold": 0.1,
                    "promote_statuses": ["succeeded", "partial"],
                    "promote_routes": ["private_rag"],
                }
            }
            stats = backfill_memory_from_runs(repo_root, repo_root / "runs" / "control_plane", policy=policy)
            store = load_semantic_memory(repo_root, policy)

        self.assertEqual(stats["records_seen"], 1)
        self.assertEqual(stats["records_promoted"], 0)
        self.assertEqual(stats["skipped"], 1)
        self.assertFalse(store["items"])


if __name__ == "__main__":
    unittest.main()
