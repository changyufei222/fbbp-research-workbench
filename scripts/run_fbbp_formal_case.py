from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from formal_run_lib import (
    append_error,
    build_formal_outputs,
    build_run_id,
    evaluate_tool_stop_condition,
    initialize_run_manifest,
    load_yaml_config,
    resolve_runner_settings,
    write_json,
    write_jsonl,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = REPO_ROOT / "templates" / "formal_report_template.md"
DEFAULT_BACKEND_ROOT = REPO_ROOT.parent / "upstream-deerflow" / "backend"
DEFAULT_EMBEDDED_RUNNER = REPO_ROOT / "scripts" / "deerflow_embedded_runner.py"
SUBPROCESS_TIMEOUT_BUFFER_SECONDS = 30
DEFAULT_MCP_ROOT = REPO_ROOT.parent / "fbbp-mcp-rag-server"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one formal DeerFlow case")
    parser.add_argument("--case-path", required=True)
    parser.add_argument("--run-dir")
    parser.add_argument("--raw-result-json")
    parser.add_argument("--backend-root")
    parser.add_argument("--template-path", default=str(DEFAULT_TEMPLATE))
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--now")
    return parser.parse_args()


def _parse_now(raw: str | None) -> datetime:
    if raw:
        return datetime.fromisoformat(raw)
    return datetime.now()


def _run_dir(case_config: dict[str, Any], run_dir: str | None, now: datetime) -> tuple[str, Path]:
    if run_dir:
        resolved = Path(run_dir).resolve()
        return resolved.name, resolved
    run_id = build_run_id(case_config["case_id"], now)
    return run_id, REPO_ROOT / "runs" / run_id


def _load_manifest(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_backend_python(backend_root: Path) -> Path:
    candidates = [
        backend_root / ".venv" / "Scripts" / "python.exe",
        backend_root / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Could not find DeerFlow backend Python under {backend_root}")


def _prepare_manifest(case_config: dict[str, Any], run_id: str, run_dir: Path) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = run_dir / "run_manifest.json"
    manifest = _load_manifest(manifest_path)
    if manifest is None:
        manifest = initialize_run_manifest(
            run_id=run_id,
            case_config=case_config,
            runtime_profile=case_config["runtime_profile"],
            mcp_contract_version=case_config["mcp_contract_version"],
        )
        write_json(manifest_path, manifest)
    return manifest_path


def _apply_case_runtime_env(case_config: dict[str, Any]) -> None:
    dataset_version = str(case_config.get("dataset_version") or "").strip()
    runtime_profile = str(case_config.get("runtime_profile") or "").strip()
    if dataset_version:
        for key in ("FBBP_FORMAL_DATASET_VERSION", "FBTP_FORMAL_DATASET_VERSION"):
            if not os.environ.get(key):
                os.environ[key] = dataset_version
    if runtime_profile:
        for key in ("FBBP_FORMAL_RUNTIME_PROFILE", "FBTP_FORMAL_RUNTIME_PROFILE"):
            if not os.environ.get(key):
                os.environ[key] = runtime_profile


def _resolve_subprocess_timeout(runner_settings: dict[str, Any]) -> int:
    max_seconds = int(runner_settings.get("max_seconds") or 180)
    return max(max_seconds + SUBPROCESS_TIMEOUT_BUFFER_SECONDS, 60)


def _set_status(manifest_path: Path, status: str) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = status
    if status == "running":
        manifest["started_at_utc"] = datetime.now(UTC).isoformat()
    elif status in {"succeeded", "failed", "cancelled"}:
        manifest["completed_at_utc"] = datetime.now(UTC).isoformat()
    write_json(manifest_path, manifest)
    return manifest


def _read_partial_state(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _load_formal_gateway_module(backend_root: Path):
    import sys

    backend_root = backend_root.resolve()
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    module_path = backend_root / "src" / "gateway" / "fbbp_formal.py"
    spec = importlib.util.spec_from_file_location("fbbp_formal_preflight_module", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load formal preflight module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_preflight_raw_result(
    *,
    response: dict[str, Any],
    runner_settings: dict[str, Any],
    prompt: str,
    thread_id: str,
    tool_name: str,
) -> dict[str, Any] | None:
    tool_event = {
        "name": tool_name,
        "tool_call_id": "preflight_search_knowledge",
        "content": json.dumps(response, ensure_ascii=False),
    }
    stop_payload = evaluate_tool_stop_condition(tool_event, runner_settings)
    if stop_payload is None:
        return None
    return {
        "thread_id": thread_id,
        "prompt": prompt,
        "available_tools": [tool_name],
        "answer": stop_payload.get("answer") or "",
        "tool_events": [tool_event],
        "partial": False,
        "completion_reason": (
            f"preflight:{stop_payload.get('stop_reason')}"
            if stop_payload.get("stop_reason")
            else "preflight:stop_policy_satisfied"
        ),
        "preflight": {
            "attempted": True,
            "hit": True,
            "mode": "search_knowledge",
            "tool_event_count": 1,
            "hit_rate": 1.0,
        },
    }


def _run_search_preflight(
    *,
    backend_root: Path,
    runner_settings: dict[str, Any],
    prompt: str,
    thread_id: str,
) -> dict[str, Any] | None:
    preflight = (runner_settings or {}).get("preflight_search_knowledge") or {}
    if not preflight.get("enabled"):
        return None
    query = str(preflight.get("query") or "").strip()
    if not query:
        return None

    module = _load_formal_gateway_module(backend_root)

    response = module.run_formal_search(
        query=query,
        top_k=int(preflight.get("top_k") or 5),
        record_type=preflight.get("record_type"),
        filters=list(preflight.get("filters") or []),
        include_answer=bool(preflight.get("include_answer", True)),
        include_evidence=bool(preflight.get("include_evidence", True)),
        answer_mode=str(preflight.get("answer_mode") or "extractive"),
        request_source=str(preflight.get("request_source") or "formal_preflight"),
    )
    if not bool(response.get("ok")):
        return None

    return _build_preflight_raw_result(
        response=response,
        runner_settings=runner_settings,
        prompt=prompt,
        thread_id=thread_id,
        tool_name=str(preflight.get("tool_name") or "search_knowledge"),
    )


def _tool_event(name: str, content: dict[str, Any], *, tool_call_id: str) -> dict[str, Any]:
    return {
        "name": name,
        "tool_call_id": tool_call_id,
        "content": json.dumps(content, ensure_ascii=False),
    }


def _build_source_preflight_raw_result(
    *,
    list_response: dict[str, Any],
    summary_responses: list[dict[str, Any]],
    prompt: str,
    thread_id: str,
    data_source: str = "mcp_db_worker",
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    tool_events = [_tool_event("list_sources", list_response, tool_call_id="preflight_list_sources")]
    for index, response in enumerate(summary_responses, start=1):
        source = ((response.get("request") or {}).get("source") or f"source_{index}")
        tool_events.append(
            _tool_event(
                "get_source_summary",
                response,
                tool_call_id=f"preflight_get_source_summary:{source}",
            )
        )
    return {
        "thread_id": thread_id,
        "prompt": prompt,
        "available_tools": ["list_sources", "get_source_summary"],
        "answer": "",
        "tool_events": tool_events,
        "partial": False,
        "completion_reason": "preflight:source_provenance_satisfied",
        "preflight": {
            "attempted": True,
            "hit": True,
            "mode": "source_provenance",
            "data_source": data_source,
            "tool_event_count": len(tool_events),
            "hit_rate": 1.0,
            **({"fallback_reason": fallback_reason[:500]} if fallback_reason else {}),
        },
    }


def _mark_preflight_response(response: dict[str, Any], request_source: str) -> dict[str, Any]:
    diagnostics = response.get("diagnostics") if isinstance(response.get("diagnostics"), dict) else {}
    diagnostics["request_source"] = request_source
    response["diagnostics"] = diagnostics
    return response


def _source_record_type(source: str) -> str:
    suffix = Path(source).suffix.lower().lstrip(".")
    return suffix or "unknown"


def _known_chunk_count(source: str, descriptor: dict[str, Any]) -> int | None:
    stats = descriptor.get("statistics") if isinstance(descriptor.get("statistics"), dict) else {}
    mapping = {
        "raw_records.jsonl": "raw_record_count",
        "protein_cards_v2.jsonl": "protein_card_v2_count",
        "interaction_cards_v2.jsonl": "interaction_card_v2_count",
    }
    key = mapping.get(source)
    if not key:
        return None
    try:
        return int(stats.get(key))
    except (TypeError, ValueError):
        return None


def _runtime_provenance_from_descriptor(case_config: dict[str, Any], descriptor: dict[str, Any]) -> dict[str, Any]:
    return {
        "dataset_version": case_config.get("dataset_version", "unknown"),
        "runtime_profile": case_config.get("runtime_profile", "unknown"),
        "formal_db_mode": descriptor.get("formal_db_mode", "file_source_registry_fallback"),
        "db_identity": descriptor.get("db_identity", "unknown"),
        "build_id": descriptor.get("build_id", "unknown"),
        "source_registry_version": descriptor.get("source_registry_version", "unknown"),
    }


def _dataset_descriptor_for_case(case_config: dict[str, Any]) -> dict[str, Any]:
    dataset_version = str(case_config.get("dataset_version") or "").strip()
    if not dataset_version:
        return {}
    descriptor_path = DEFAULT_MCP_ROOT / "configs" / "datasets" / f"{dataset_version}.json"
    if not descriptor_path.exists():
        return {}
    return json.loads(descriptor_path.read_text(encoding="utf-8"))


def _source_registry_rows(
    *,
    case_config: dict[str, Any],
    preflight: dict[str, Any],
    descriptor: dict[str, Any],
) -> list[dict[str, Any]]:
    registry = descriptor.get("source_registry") if isinstance(descriptor.get("source_registry"), dict) else {}
    record_type_filter = str(preflight.get("record_type") or "").strip().lower()
    rows: list[dict[str, Any]] = []
    for source, metadata in registry.items():
        if not isinstance(metadata, dict):
            continue
        record_type = _source_record_type(str(source))
        if record_type_filter and record_type != record_type_filter:
            continue
        chunk_count = _known_chunk_count(str(source), descriptor)
        row = {
            "source": str(source),
            "record_type": record_type,
            "source_category": metadata.get("source_category"),
            "source_description": metadata.get("source_description"),
            "upstream_pipeline": metadata.get("upstream_pipeline"),
            "quality_notes": metadata.get("quality_notes"),
            "owner_table": metadata.get("owner_table"),
        }
        if chunk_count is not None:
            row["chunk_count"] = chunk_count
        rows.append(row)
    rows.sort(key=lambda row: (row.get("chunk_count") is not None, row.get("chunk_count") or -1, row["source"]), reverse=True)
    limit = max(int(preflight.get("list_limit") or 20), 0)
    return rows[:limit] if limit else rows


def _file_source_listing_response(
    *,
    case_config: dict[str, Any],
    preflight: dict[str, Any],
    descriptor: dict[str, Any],
    fallback_reason: str | None,
) -> dict[str, Any]:
    rows = _source_registry_rows(case_config=case_config, preflight=preflight, descriptor=descriptor)
    return {
        "ok": True,
        "tool": "list_sources",
        "request": {"record_type": preflight.get("record_type"), "limit": preflight.get("list_limit")},
        "result": {
            "sources": rows,
            "source_count": len(rows),
            "source_registry_count": len(descriptor.get("source_registry") or {}),
        },
        "provenance": {
            **_runtime_provenance_from_descriptor(case_config, descriptor),
            "fallback_mode": "file_source_registry",
        },
        "diagnostics": {
            "worker_action": "list_sources",
            "fallback_mode": "file_source_registry",
            **({"fallback_reason": fallback_reason[:500]} if fallback_reason else {}),
        },
    }


def _file_source_summary_response(
    *,
    case_config: dict[str, Any],
    source: str,
    descriptor: dict[str, Any],
    fallback_reason: str | None,
) -> dict[str, Any]:
    registry = descriptor.get("source_registry") if isinstance(descriptor.get("source_registry"), dict) else {}
    metadata = registry.get(source) if isinstance(registry.get(source), dict) else {}
    chunk_count = _known_chunk_count(source, descriptor)
    record_type = _source_record_type(source)
    return {
        "ok": True,
        "tool": "get_source_summary",
        "request": {"source": source, "limit": None},
        "result": {
            "source": source,
            "total_chunks": chunk_count,
            "record_types": [{"source": source, "record_type": record_type, "chunk_count": chunk_count}],
            "source_registry": metadata,
        },
        "provenance": {
            "source": source,
            **_runtime_provenance_from_descriptor(case_config, descriptor),
            "fallback_mode": "file_source_registry",
        },
        "diagnostics": {
            "worker_action": "get_source_summary",
            "fallback_mode": "file_source_registry",
            **({"fallback_reason": fallback_reason[:500]} if fallback_reason else {}),
        },
    }


def _run_source_file_fallback(
    *,
    case_config: dict[str, Any],
    runner_settings: dict[str, Any],
    prompt: str,
    thread_id: str,
    fallback_reason: str | None,
) -> dict[str, Any] | None:
    preflight = (runner_settings or {}).get("preflight_source_provenance") or {}
    descriptor = _dataset_descriptor_for_case(case_config)
    if not descriptor:
        return None
    list_response = _file_source_listing_response(
        case_config=case_config,
        preflight=preflight,
        descriptor=descriptor,
        fallback_reason=fallback_reason,
    )
    request_source = str(preflight.get("request_source") or "formal_source_preflight")
    list_response = _mark_preflight_response(list_response, request_source)
    sources = (list_response.get("result") or {}).get("sources")
    if not isinstance(sources, list) or len(sources) < int(preflight.get("min_sources") or 1):
        return None

    summary_responses: list[dict[str, Any]] = []
    summary_count = max(int(preflight.get("summary_count") or 0), 0)
    for row in sources[:summary_count]:
        source = str((row or {}).get("source") or "").strip()
        if not source:
            continue
        response = _file_source_summary_response(
            case_config=case_config,
            source=source,
            descriptor=descriptor,
            fallback_reason=fallback_reason,
        )
        summary_responses.append(_mark_preflight_response(response, request_source))
    if summary_count and not summary_responses:
        return None

    return _build_source_preflight_raw_result(
        list_response=list_response,
        summary_responses=summary_responses,
        prompt=prompt,
        thread_id=thread_id,
        data_source="file_source_registry",
        fallback_reason=fallback_reason,
    )


def _run_source_preflight(
    *,
    backend_root: Path,
    case_config: dict[str, Any],
    runner_settings: dict[str, Any],
    prompt: str,
    thread_id: str,
) -> dict[str, Any] | None:
    preflight = (runner_settings or {}).get("preflight_source_provenance") or {}
    if not preflight.get("enabled"):
        return None

    fallback_reason: str | None = None
    try:
        module = _load_formal_gateway_module(backend_root)
        service_module = module._service_module()
        list_response = service_module.list_available_sources(
            record_type=preflight.get("record_type"),
            limit=int(preflight.get("list_limit") or 20),
        )
    except Exception as exc:
        return _run_source_file_fallback(
            case_config=case_config,
            runner_settings=runner_settings,
            prompt=prompt,
            thread_id=thread_id,
            fallback_reason=f"{type(exc).__name__}: {exc}",
        )
    request_source = str(preflight.get("request_source") or "formal_source_preflight")
    list_response = _mark_preflight_response(
        list_response,
        request_source,
    )
    if not bool(list_response.get("ok")):
        error = list_response.get("error") if isinstance(list_response.get("error"), dict) else {}
        fallback_reason = str(error.get("message") or error or "list_sources returned ok=false")
        return _run_source_file_fallback(
            case_config=case_config,
            runner_settings=runner_settings,
            prompt=prompt,
            thread_id=thread_id,
            fallback_reason=fallback_reason,
        )
    sources = (list_response.get("result") or {}).get("sources")
    if not isinstance(sources, list) or len(sources) < int(preflight.get("min_sources") or 1):
        return None

    summary_responses: list[dict[str, Any]] = []
    summary_count = max(int(preflight.get("summary_count") or 0), 0)
    for row in sources[:summary_count]:
        if not isinstance(row, dict) or not row.get("source"):
            continue
        response = service_module.get_source_summary(
            source=str(row["source"]),
            limit=int(preflight.get("summary_limit") or 1000),
        )
        response = _mark_preflight_response(response, request_source)
        if bool(response.get("ok")):
            summary_responses.append(response)
    if summary_count and not summary_responses:
        return None

    return _build_source_preflight_raw_result(
        list_response=list_response,
        summary_responses=summary_responses,
        prompt=prompt,
        thread_id=thread_id,
        data_source="mcp_db_worker",
    )


def _read_raw_result(args: argparse.Namespace, case_config: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    if args.raw_result_json:
        return json.loads(Path(args.raw_result_json).read_text(encoding="utf-8"))
    backend_root = Path(args.backend_root).resolve() if args.backend_root else DEFAULT_BACKEND_ROOT
    runner_settings = resolve_runner_settings(case_config)
    subprocess_timeout = _resolve_subprocess_timeout(runner_settings)
    prompt_path = (REPO_ROOT / case_config["prompt_file"]).resolve()
    prompt_text = prompt_path.read_text(encoding="utf-8")
    thread_id = case_config.get("thread_id_hint") or case_config["case_id"]
    preflight_raw = _run_source_preflight(
        backend_root=backend_root,
        case_config=case_config,
        runner_settings=runner_settings,
        prompt=prompt_text,
        thread_id=thread_id,
    )
    if preflight_raw is not None:
        return preflight_raw
    preflight_raw = _run_search_preflight(
        backend_root=backend_root,
        runner_settings=runner_settings,
        prompt=prompt_text,
        thread_id=thread_id,
    )
    if preflight_raw is not None:
        return preflight_raw
    backend_python = _resolve_backend_python(backend_root)
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    state_path = logs_dir / "embedded_runner_state.json"
    cmd = [
        str(backend_python),
        str(DEFAULT_EMBEDDED_RUNNER),
        "--backend-root",
        str(backend_root),
        "--prompt-file",
        str(prompt_path),
        "--thread-id",
        thread_id,
        "--recursion-limit",
        str(runner_settings["recursion_limit"]),
        "--max-seconds",
        str(runner_settings["max_seconds"]),
        "--runner-settings-json",
        json.dumps(runner_settings, ensure_ascii=False),
        "--state-file",
        str(state_path),
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            check=False,
            timeout=subprocess_timeout,
        )
    except subprocess.TimeoutExpired:
        partial = _read_partial_state(state_path)
        if partial is not None:
            partial["partial"] = True
            partial["termination_reason"] = "timeout"
            partial["termination_error"] = (
                f"Embedded DeerFlow runner exceeded {subprocess_timeout} seconds."
            )
            return partial
        raise RuntimeError(
            f"Embedded DeerFlow runner exceeded {subprocess_timeout} seconds without writing partial state"
        )
    if proc.returncode != 0:
        partial = _read_partial_state(state_path)
        if partial is not None and partial.get("tool_events"):
            partial["partial"] = True
            partial.setdefault("termination_reason", "subprocess_error")
            partial.setdefault("termination_error", (proc.stderr or proc.stdout).strip() or "Embedded DeerFlow run failed")
            return partial
        raise RuntimeError((proc.stderr or proc.stdout).strip() or "Embedded DeerFlow run failed")
    return json.loads(proc.stdout.strip())


def main() -> None:
    args = _parse_args()
    case_path = Path(args.case_path).resolve()
    case_config = load_yaml_config(case_path)
    _apply_case_runtime_env(case_config)
    now = _parse_now(args.now)
    run_id, run_dir = _run_dir(case_config, args.run_dir, now)
    manifest_path = _prepare_manifest(case_config, run_id, run_dir)

    if args.prepare_only:
        print(
            json.dumps(
                {
                    "run_id": run_id,
                    "run_dir": str(run_dir),
                    "manifest_path": str(manifest_path),
                },
                ensure_ascii=False,
            )
        )
        return

    try:
        manifest = _set_status(manifest_path, "running")
        raw = _read_raw_result(args, case_config, run_dir)
        outputs = build_formal_outputs(
            raw,
            case_config=case_config,
            dataset_version=case_config["dataset_version"],
            contract_version=case_config["mcp_contract_version"],
            template_path=Path(args.template_path).resolve(),
        )

        write_json(run_dir / "report.json", outputs["report_json"])
        (run_dir / "report.md").write_text(outputs["report_markdown"], encoding="utf-8")
        (run_dir / "evidence.json").write_text(
            json.dumps(outputs["evidence"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        write_jsonl(run_dir / "tool_calls.jsonl", outputs["tool_call_rows"])
        (run_dir / "artifacts").mkdir(parents=True, exist_ok=True)
        (run_dir / "logs").mkdir(parents=True, exist_ok=True)

        manifest["status"] = "succeeded"
        manifest["completed_at_utc"] = datetime.now(UTC).isoformat()
        manifest["outputs"] = {
            "report_md": str(run_dir / "report.md"),
            "report_json": str(run_dir / "report.json"),
            "evidence_json": str(run_dir / "evidence.json"),
            "tool_calls_jsonl": str(run_dir / "tool_calls.jsonl"),
        }
        if isinstance(raw.get("preflight"), dict):
            manifest["preflight"] = raw["preflight"]
        write_json(manifest_path, manifest)
        print(
            json.dumps(
                {
                    "run_id": run_id,
                    "run_dir": str(run_dir),
                    "status": "succeeded",
                    "preflight": raw.get("preflight") if isinstance(raw.get("preflight"), dict) else None,
                },
                ensure_ascii=False,
            )
        )
    except Exception as exc:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        append_error(manifest, "case_execution", "FORMAL_CASE_FAILED", str(exc), False)
        manifest["status"] = "failed"
        manifest["completed_at_utc"] = datetime.now(UTC).isoformat()
        write_json(manifest_path, manifest)
        print(json.dumps({"run_id": run_id, "run_dir": str(run_dir), "status": "failed"}, ensure_ascii=False))
        raise


if __name__ == "__main__":
    main()
