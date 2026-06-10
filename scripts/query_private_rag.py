from __future__ import annotations

import argparse
import anyio
from importlib import import_module
import json
import os
from pathlib import Path
import sys
from typing import Any


DEFAULT_FBBP_MCP_HTTP_URL = "http://127.0.0.1:8000/mcp"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query the real local FBBP private knowledge base via HTTP MCP")
    parser.add_argument("--query", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--record-type", default=None)
    parser.add_argument("--filter", action="append", default=[])
    parser.add_argument("--include-evidence", action="store_true")
    parser.set_defaults(include_answer=True)
    parser.add_argument("--no-include-answer", dest="include_answer", action="store_false")
    parser.add_argument("--answer-mode", default="openai")
    parser.add_argument("--min-score", type=float, default=0.0)
    return parser.parse_args()


def _resolve_mcp_http_url() -> str:
    for key in ("FBBP_MCP_HTTP_URL", "FBTP_MCP_HTTP_URL"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return DEFAULT_FBBP_MCP_HTTP_URL


def _prefer_local_service() -> bool:
    for key in ("FBBP_LIVE_QUERY_PREFER_LOCAL", "FBTP_LIVE_QUERY_PREFER_LOCAL"):
        value = os.environ.get(key, "").strip().lower()
        if value in {"1", "true", "yes", "on"}:
            return True
    return False


def _extract_tool_payload(tool_result: Any) -> dict[str, Any]:
    for content in getattr(tool_result, "content", []) or []:
        text = getattr(content, "text", None)
        if isinstance(text, str) and text.strip():
            return json.loads(text)
    raise RuntimeError("MCP tool result did not contain JSON text content.")


def _project_root() -> Path:
    for key in ("FBBP_PROJECT_ROOT", "FBTP_PROJECT_ROOT"):
        value = os.environ.get(key, "").strip()
        if value:
            return Path(value)
    return Path(__file__).resolve().parents[2]


def _ensure_local_import_paths() -> None:
    project_root = _project_root()
    candidate_paths = [
        project_root / "fbbp-mcp-rag-server" / "src",
        project_root / "fbtp-mcp-rag-server" / "src",
        project_root / "llm-rag-knowledge-base" / "src",
    ]
    for candidate in reversed(candidate_paths):
        rendered = str(candidate)
        if candidate.exists() and rendered not in sys.path:
            sys.path.insert(0, rendered)


def _run_local_service_fallback(request: dict[str, Any], reason: str) -> dict[str, Any]:
    _ensure_local_import_paths()
    service_module = import_module("fbbp_mcp_server.service")
    response = service_module.search_knowledge(
        query=request["query"],
        top_k=request["top_k"],
        record_type=request.get("record_type"),
        filters=request.get("filters") or [],
        include_answer=request.get("include_answer", True),
        include_evidence=request.get("include_evidence", False),
        answer_mode=request.get("answer_mode"),
    )
    diagnostics = dict(response.get("diagnostics") or {})
    diagnostics["query_transport"] = "local_service_fallback"
    diagnostics["mcp_failure_reason"] = reason
    response["diagnostics"] = diagnostics
    return response


async def _run_query(args: argparse.Namespace) -> dict[str, Any]:
    request: dict[str, Any] = {
        "query": args.query,
        "top_k": args.top_k,
        "filters": [item.strip() for item in args.filter if item.strip()],
        "include_answer": args.include_answer,
        "include_evidence": args.include_evidence,
        "answer_mode": args.answer_mode,
    }
    if args.record_type:
        request["record_type"] = args.record_type

    if _prefer_local_service():
        return _run_local_service_fallback(request, "live_query_prefer_local")

    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    try:
        async with streamablehttp_client(_resolve_mcp_http_url()) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool("search_knowledge", request)
        payload = _extract_tool_payload(result)
    except Exception as exc:
        return _run_local_service_fallback(request, f"transport_error: {exc}")

    if payload.get("ok"):
        diagnostics = dict(payload.get("diagnostics") or {})
        diagnostics["query_transport"] = "http_mcp"
        payload["diagnostics"] = diagnostics
        return payload

    error = payload.get("error") or {}
    reason = str(error.get("message") or error.get("code") or "unknown_mcp_error")
    return _run_local_service_fallback(request, reason)


def main() -> None:
    args = _parse_args()
    result = anyio.run(_run_query, args)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
