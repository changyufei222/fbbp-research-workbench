from __future__ import annotations

import asyncio
import argparse
import json
from pathlib import Path
from typing import Any

from formal_run_lib import evaluate_tool_stop_condition


async def _run_embedded(
    *,
    backend_root: Path,
    prompt: str,
    thread_id: str,
    recursion_limit: int = 8,
    max_seconds: int = 180,
    runner_settings: dict[str, Any] | None = None,
    state_file: Path | None = None,
) -> dict[str, Any]:
    import sys

    backend_root = backend_root.resolve()
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
    from src.client import DeerFlowClient
    from src.mcp.cache import initialize_mcp_tools

    await initialize_mcp_tools()
    client = DeerFlowClient(config_path=None, thinking_enabled=False)
    config = client._get_runnable_config(thread_id, recursion_limit=recursion_limit, thinking_enabled=False)
    client._ensure_agent(config)
    available_tools = [getattr(tool, "name", str(tool)) for tool in client._get_tools(model_name=None, subagent_enabled=False)]
    state = {"messages": [HumanMessage(content=prompt)]}
    context = {"thread_id": thread_id}

    final_answer = ""
    completion_reason: str | None = None
    tool_events: list[dict[str, Any]] = []
    seen_message_ids: set[str] = set()

    def _snapshot(
        *,
        partial: bool,
        termination_reason: str | None = None,
        termination_error: str | None = None,
        completion_reason: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "thread_id": thread_id,
            "prompt": prompt,
            "available_tools": available_tools,
            "answer": final_answer,
            "tool_events": tool_events,
            "partial": partial,
        }
        if completion_reason:
            payload["completion_reason"] = completion_reason
        if termination_reason:
            payload["termination_reason"] = termination_reason
        if termination_error:
            payload["termination_error"] = termination_error
        return payload

    def _write_state(payload: dict[str, Any]) -> None:
        if state_file is None:
            return
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    _write_state(_snapshot(partial=False))

    async def _consume_stream() -> None:
        nonlocal final_answer
        nonlocal completion_reason
        async for chunk in client._agent.astream(state, config=config, context=context, stream_mode="values"):
            messages = chunk.get("messages", [])
            for msg in messages:
                msg_id = getattr(msg, "id", None)
                if msg_id and msg_id in seen_message_ids:
                    continue
                if msg_id:
                    seen_message_ids.add(msg_id)

                if isinstance(msg, ToolMessage):
                    tool_events.append(
                        {
                            "name": getattr(msg, "name", None),
                            "tool_call_id": getattr(msg, "tool_call_id", None),
                            "content": msg.content if isinstance(msg.content, str) else str(msg.content),
                        }
                    )
                    stop_payload = evaluate_tool_stop_condition(tool_events[-1], runner_settings or {})
                    if stop_payload is not None:
                        final_answer = stop_payload.get("answer") or final_answer
                        completion_reason = (
                            f"stop_policy:{stop_payload.get('stop_reason')}"
                            if stop_payload.get("stop_reason")
                            else "stop_policy_satisfied"
                        )
                        _write_state(_snapshot(partial=False, completion_reason=completion_reason))
                        return
                elif isinstance(msg, AIMessage):
                    if msg.tool_calls:
                        for tool_call in msg.tool_calls:
                            tool_events.append(
                                {
                                    "name": tool_call.get("name"),
                                    "tool_call_id": tool_call.get("id"),
                                    "content": json.dumps({"tool_call": tool_call}, ensure_ascii=False),
                                }
                            )
                    text = client._extract_text(msg.content)
                    if text:
                        final_answer = text
                _write_state(_snapshot(partial=False))

    try:
        await asyncio.wait_for(_consume_stream(), timeout=max_seconds)
    except Exception as exc:
        if exc.__class__.__name__ != "GraphRecursionError":
            if not isinstance(exc, TimeoutError):
                raise
        payload = _snapshot(
            partial=True,
            termination_reason="timeout" if isinstance(exc, TimeoutError) else "recursion_limit",
            termination_error=str(exc),
            completion_reason=completion_reason,
        )
        _write_state(payload)
        return payload

    payload = _snapshot(partial=False, completion_reason=completion_reason)
    _write_state(payload)
    return payload


def run_embedded_deerflow(
    *,
    backend_root: Path,
    prompt: str,
    thread_id: str,
    recursion_limit: int = 8,
    max_seconds: int = 180,
    runner_settings: dict[str, Any] | None = None,
    state_file: Path | None = None,
) -> dict[str, Any]:
    return asyncio.run(
        _run_embedded(
            backend_root=backend_root,
            prompt=prompt,
            thread_id=thread_id,
            recursion_limit=recursion_limit,
            max_seconds=max_seconds,
            runner_settings=runner_settings,
            state_file=state_file,
        )
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run embedded DeerFlow and emit JSON")
    parser.add_argument("--backend-root", required=True)
    parser.add_argument("--prompt-file", required=True)
    parser.add_argument("--thread-id", required=True)
    parser.add_argument("--recursion-limit", type=int, default=8)
    parser.add_argument("--max-seconds", type=int, default=180)
    parser.add_argument("--runner-settings-json")
    parser.add_argument("--state-file")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = run_embedded_deerflow(
        backend_root=Path(args.backend_root),
        prompt=Path(args.prompt_file).read_text(encoding="utf-8"),
        thread_id=args.thread_id,
        recursion_limit=args.recursion_limit,
        max_seconds=args.max_seconds,
        runner_settings=json.loads(args.runner_settings_json) if args.runner_settings_json else None,
        state_file=Path(args.state_file) if args.state_file else None,
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
