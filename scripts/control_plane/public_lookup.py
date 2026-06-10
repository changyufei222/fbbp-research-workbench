from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from typing import Any, Callable

from control_plane.project_links import project_summary, resolved_project_links


REPO_ROOT = Path(__file__).resolve().parents[2]
UNIPROT_RE = re.compile(r"\b(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9][A-Z][A-Z0-9]{2}[0-9])\b")
PDB_RE = re.compile(r"\b[0-9][A-Za-z][A-Za-z0-9]{2}\b")


def _ensure_mcp_server_importable() -> dict[str, Any]:
    links = resolved_project_links()
    project = (links.get("projects") or {}).get("fbbp-mcp-rag-server") or {}
    python_src = project.get("resolved_python_src")
    if python_src and python_src not in sys.path:
        sys.path.insert(0, str(python_src))
    return project


def extract_public_lookup_targets(query: str) -> dict[str, Any]:
    text = query or ""
    lowered = text.lower()
    explicit_pubmed = any(
        keyword in lowered
        for keyword in ("pubmed", "pmid", "paper", "papers", "文献", "公开资料", "公开文献")
    )
    uniprot_ids = []
    for item in UNIPROT_RE.findall(text.upper()):
        if item not in uniprot_ids:
            uniprot_ids.append(item)
    pdb_ids = []
    for item in PDB_RE.findall(text):
        candidate = item.upper()
        if candidate.isdigit():
            continue
        if candidate not in pdb_ids:
            pdb_ids.append(candidate)
    providers: list[str] = []
    if explicit_pubmed or not (uniprot_ids or pdb_ids):
        providers.append("pubmed")
    if uniprot_ids:
        providers.append("uniprot")
    if pdb_ids:
        providers.append("pdb")
    return {
        "query": text,
        "providers": providers,
        "uniprot_accessions": uniprot_ids,
        "pdb_ids": pdb_ids,
        "pubmed_query": text,
    }


def _call_tool(tool_name: str, func: Callable[..., dict[str, Any]], *args: Any, **kwargs: Any) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        payload = func(*args, **kwargs)
        ok = bool(payload.get("ok", True)) if isinstance(payload, dict) else True
        return {
            "tool": tool_name,
            "ok": ok,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "payload": payload,
            "error": payload.get("error") if isinstance(payload, dict) else None,
        }
    except Exception as exc:
        return {
            "tool": tool_name,
            "ok": False,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "payload": {},
            "error": {"code": type(exc).__name__, "message": str(exc).splitlines()[0][:500]},
        }


def run_public_lookup(query: str, *, top_k: int = 5) -> dict[str, Any]:
    mcp_project = _ensure_mcp_server_importable()
    from fbbp_mcp_server.service import get_pdb_entry, get_uniprot_entry, search_pubmed_articles

    targets = extract_public_lookup_targets(query)
    calls: list[dict[str, Any]] = []
    if "pubmed" in targets["providers"]:
        calls.append(_call_tool("search_pubmed", search_pubmed_articles, targets["pubmed_query"], top_k))
    for accession in targets["uniprot_accessions"]:
        calls.append(_call_tool("get_uniprot_entry", get_uniprot_entry, accession))
    for pdb_id in targets["pdb_ids"]:
        calls.append(_call_tool("get_pdb_entry", get_pdb_entry, pdb_id))

    succeeded = sum(1 for call in calls if call["ok"])
    articles = []
    entries = []
    for call in calls:
        payload = call.get("payload") if isinstance(call.get("payload"), dict) else {}
        result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
        if call["tool"] == "search_pubmed":
            articles.extend(result.get("articles") or [])
        else:
            entries.append(result)
    return {
        "ok": bool(calls) and succeeded == len(calls),
        "route": "public_lookup",
        "targets": targets,
        "tool_calls": calls,
        "summary": {
            "provider_count": len(targets["providers"]),
            "tool_call_count": len(calls),
            "tool_success_count": succeeded,
            "tool_success_rate": round(succeeded / len(calls), 4) if calls else 0.0,
            "article_count": len(articles),
            "entry_count": len(entries),
            "connected_projects": project_summary(
                "fbbp-research-workbench",
                "fbbp-mcp-rag-server",
                "llm-rag-knowledge-base",
                "llm-eval-benchmark",
                "minimind-fbtp-lab",
            ),
            "tool_plane": {
                "project": "fbbp-mcp-rag-server",
                "role": mcp_project.get("role"),
                "path": mcp_project.get("resolved_path"),
            },
        },
        "articles": articles,
        "entries": entries,
    }
