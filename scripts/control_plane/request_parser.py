from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the FBBP control plane")
    parser.add_argument("--mode", choices=["auto", "interactive", "formal", "batch", "report"], default="auto")
    parser.add_argument("--query")
    parser.add_argument("--case-path")
    parser.add_argument("--batch-path")
    parser.add_argument("--run-dir")
    parser.add_argument("--report-json")
    parser.add_argument("--evidence-json")
    parser.add_argument("--thread-id")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--record-type", default=None)
    parser.add_argument("--filter", action="append", default=[])
    parser.add_argument("--include-evidence", action="store_true")
    parser.set_defaults(include_answer=True)
    parser.add_argument("--no-include-answer", dest="include_answer", action="store_false")
    parser.add_argument("--answer-mode", default=None)
    parser.add_argument("--force-primary-route")
    parser.add_argument("--secondary-capability", action="append", default=[])
    parser.add_argument("--output-dir")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def _resolve_optional_path(raw: str | None) -> str | None:
    if not raw:
        return None
    return str(Path(raw).resolve())


def normalize_request(args: argparse.Namespace) -> dict[str, Any]:
    request: dict[str, Any] = {
        "requested_mode": args.mode,
        "query": (args.query or "").strip() or None,
        "thread_id": (args.thread_id or "").strip() or None,
        "top_k": int(args.top_k),
        "record_type": (args.record_type or "").strip() or None,
        "filters": [item.strip() for item in args.filter if item and item.strip()],
        "include_evidence": bool(args.include_evidence),
        "include_answer": bool(args.include_answer),
        "answer_mode": (args.answer_mode or "").strip() or None,
        "force_primary_route": (args.force_primary_route or "").strip() or None,
        "requested_secondary_capabilities": [
            item.strip() for item in args.secondary_capability if item and item.strip()
        ],
        "dry_run": bool(args.dry_run),
        "output_dir": _resolve_optional_path(args.output_dir),
    }
    for field in ("case_path", "batch_path", "run_dir", "report_json", "evidence_json"):
        request[field] = _resolve_optional_path(getattr(args, field))

    input_files = []
    for field in ("case_path", "batch_path", "run_dir", "report_json", "evidence_json"):
        value = request.get(field)
        if value:
            input_files.append({"field": field, "path": value})
    request["input_files"] = input_files
    return request
