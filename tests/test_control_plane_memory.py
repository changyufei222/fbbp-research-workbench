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

from control_plane.memory_adapter import build_memory_context, update_memory_after_run


class ControlPlaneMemoryTests(unittest.TestCase):
    def test_auto_write_promotes_regular_query_into_profile_memory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            agent_dir = repo_root / "configs" / "agents" / "fbbp-assistant"
            agent_dir.mkdir(parents=True, exist_ok=True)
            (agent_dir / "memory.json").write_text("{}", encoding="utf-8")
            run_dir = repo_root / "runs" / "control_plane" / "demo"
            run_dir.mkdir(parents=True, exist_ok=True)

            result = update_memory_after_run(
                repo_root,
                run_dir,
                request={"thread_id": "thread-1", "query": "总结 knottin scaffold 的私有证据"},
                route_decision={"primary_route": "private_rag"},
                result_summary={"status": "succeeded"},
            )

            memory_payload = json.loads((agent_dir / "memory.json").read_text(encoding="utf-8"))

        self.assertTrue(result["profile_written"])
        self.assertIn("route=private_rag", memory_payload["user"]["workContext"]["summary"])
        self.assertIn("knottin scaffold", memory_payload["user"]["workContext"]["summary"])

    def test_auto_write_promotes_formal_case_without_query(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            agent_dir = repo_root / "configs" / "agents" / "fbbp-assistant"
            agent_dir.mkdir(parents=True, exist_ok=True)
            (agent_dir / "memory.json").write_text("{}", encoding="utf-8")
            run_dir = repo_root / "runs" / "control_plane" / "demo"
            run_dir.mkdir(parents=True, exist_ok=True)

            result = update_memory_after_run(
                repo_root,
                run_dir,
                request={
                    "thread_id": "thread-2",
                    "case_path": "E:/项目/fbbp-research-workbench/configs/formal_cases/fbbp_knottin_landscape_01.yaml",
                },
                route_decision={"primary_route": "formal_case"},
                result_summary={"status": "succeeded"},
            )

            memory_payload = json.loads((agent_dir / "memory.json").read_text(encoding="utf-8"))

        self.assertTrue(result["profile_written"])
        self.assertIn("route=formal_case", memory_payload["history"]["recentSessions"]["summary"])
        self.assertIn("fbbp_knottin_landscape_01.yaml", memory_payload["history"]["recentSessions"]["summary"])

    def test_explicit_remember_query_promotes_profile_memory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            agent_dir = repo_root / "configs" / "agents" / "fbbp-assistant"
            agent_dir.mkdir(parents=True, exist_ok=True)
            (agent_dir / "memory.json").write_text("{}", encoding="utf-8")
            run_dir = repo_root / "runs" / "control_plane" / "demo"
            run_dir.mkdir(parents=True, exist_ok=True)

            result = update_memory_after_run(
                repo_root,
                run_dir,
                request={"thread_id": "thread-1", "query": "请记住我现在在搭 control plane"},
                route_decision={"primary_route": "fallback_general"},
                result_summary={"message": "dry run only"},
            )

            memory_payload = json.loads((agent_dir / "memory.json").read_text(encoding="utf-8"))

        self.assertTrue(result["profile_written"])
        self.assertIn("请记住我现在在搭 control plane", memory_payload["user"]["workContext"]["summary"])

    def test_build_memory_context_returns_semantic_hits_when_store_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            agent_dir = repo_root / "configs" / "agents" / "fbbp-assistant"
            agent_dir.mkdir(parents=True, exist_ok=True)
            (agent_dir / "memory.json").write_text("{}", encoding="utf-8")
            semantic_store = repo_root / "runs" / "control_plane" / "memory"
            semantic_store.mkdir(parents=True, exist_ok=True)
            (semantic_store / "semantic_memory.json").write_text(
                json.dumps(
                    {
                        "schema_version": "fbbp.semantic_memory.v1",
                        "items": [
                            {
                                "id": "mem_1",
                                "route": "private_rag",
                                "text": "route=private_rag; query=总结 knottin scaffold 的私有证据; result=命中 knottin",
                            }
                        ],
                        "conflicts": [],
                        "stats": {"item_count": 1, "conflict_count": 0},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            context = build_memory_context(
                repo_root,
                {"thread_id": "thread-1", "query": "knottin scaffold"},
                {"primary_route": "private_rag"},
            )

        self.assertTrue(context["semantic_hits"])
