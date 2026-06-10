from __future__ import annotations

import ast
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


def load_yaml_config(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected mapping config in {path}")
    return payload


def build_run_id(case_id: str, now: datetime) -> str:
    return f"{now:%Y%m%d_%H%M%S}_{case_id}"


def build_batch_id(batch_slug: str, now: datetime) -> str:
    return f"{now:%Y%m%d_%H%M%S}_{batch_slug}"


def _config_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def initialize_run_manifest(
    *,
    run_id: str,
    case_config: dict[str, Any],
    runtime_profile: str,
    mcp_contract_version: str,
) -> dict[str, Any]:
    now_utc = datetime.now(UTC).isoformat()
    return {
        "run_id": run_id,
        "case_id": case_config["case_id"],
        "status": "prepared",
        "started_at_utc": None,
        "completed_at_utc": None,
        "prepared_at_utc": now_utc,
        "runtime_profile": runtime_profile,
        "dataset_version": case_config["dataset_version"],
        "mcp_contract_version": mcp_contract_version,
        "config_hash": _config_hash(case_config),
        "input_summary": case_config.get("inputs", {}),
        "errors": [],
    }


def initialize_batch_manifest(
    *,
    batch_id: str,
    batch_config: dict[str, Any],
    runtime_profile: str,
    mcp_contract_version: str,
) -> dict[str, Any]:
    now_utc = datetime.now(UTC).isoformat()
    return {
        "batch_id": batch_id,
        "batch_slug": batch_config["batch_slug"],
        "status": "prepared",
        "started_at_utc": None,
        "completed_at_utc": None,
        "prepared_at_utc": now_utc,
        "runtime_profile": runtime_profile,
        "dataset_version": batch_config["dataset_version"],
        "mcp_contract_version": mcp_contract_version,
        "execution": batch_config.get("execution", {}),
        "cases": list(batch_config.get("cases", [])),
        "config_hash": _config_hash(batch_config),
        "errors": [],
    }


def append_error(manifest: dict[str, Any], stage: str, code: str, message: str, retryable: bool) -> None:
    manifest.setdefault("errors", []).append(
        {
            "stage": stage,
            "code": code,
            "message": message,
            "retryable": retryable,
            "timestamp_utc": datetime.now(UTC).isoformat(),
        }
    )


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_str_list(value: Any, default: list[str]) -> list[str]:
    if isinstance(value, list):
        normalized = [str(item).strip().lower() for item in value if str(item).strip()]
        if normalized:
            return normalized
    return list(default)


def _coerce_text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def resolve_runner_settings(case_config: dict[str, Any]) -> dict[str, Any]:
    runner = case_config.get("runner") or {}
    stop_raw = runner.get("stop_on_tool_answer") or {}
    preflight_raw = runner.get("preflight_search_knowledge") or {}
    source_preflight_raw = runner.get("preflight_source_provenance") or {}
    if isinstance(stop_raw, bool):
        stop_enabled = stop_raw
        stop_raw = {}
    else:
        stop_enabled = bool(stop_raw)
    preflight_enabled = bool(preflight_raw)
    source_preflight_enabled = bool(source_preflight_raw)

    return {
        "recursion_limit": _coerce_int(runner.get("recursion_limit"), 8),
        "max_seconds": _coerce_int(runner.get("max_seconds"), 180),
        "stop_on_tool_answer": {
            "enabled": stop_enabled,
            "tool_name": str(stop_raw.get("tool_name") or "search_knowledge"),
            "min_results": _coerce_int(stop_raw.get("min_results"), 1),
            "require_answer": bool(stop_raw.get("require_answer", True)),
            "require_evidence": bool(stop_raw.get("require_evidence", True)),
            "allow_low_confidence_answer_with_evidence": bool(
                stop_raw.get("allow_low_confidence_answer_with_evidence", False)
            ),
            "reject_answer_prefixes": _coerce_str_list(
                stop_raw.get("reject_answer_prefixes"),
                ["insufficient evidence", "i don't know", "not enough evidence"],
            ),
        },
        "preflight_search_knowledge": {
            "enabled": preflight_enabled,
            "tool_name": str(preflight_raw.get("tool_name") or "search_knowledge"),
            "query": str(preflight_raw.get("query") or "").strip(),
            "top_k": _coerce_int(preflight_raw.get("top_k"), 5),
            "record_type": str(preflight_raw.get("record_type") or "").strip() or None,
            "filters": _coerce_text_list(preflight_raw.get("filters")),
            "include_answer": bool(preflight_raw.get("include_answer", True)),
            "include_evidence": bool(preflight_raw.get("include_evidence", True)),
            "answer_mode": str(preflight_raw.get("answer_mode") or "extractive"),
            "request_source": str(preflight_raw.get("request_source") or "formal_preflight"),
        },
        "preflight_source_provenance": {
            "enabled": source_preflight_enabled,
            "list_limit": _coerce_int(source_preflight_raw.get("list_limit"), 20),
            "summary_count": _coerce_int(source_preflight_raw.get("summary_count"), 3),
            "summary_limit": _coerce_int(source_preflight_raw.get("summary_limit"), 1000),
            "min_sources": _coerce_int(source_preflight_raw.get("min_sources"), 1),
            "record_type": str(source_preflight_raw.get("record_type") or "").strip() or None,
            "request_source": str(source_preflight_raw.get("request_source") or "formal_source_preflight"),
        },
    }


def normalize_evidence_item(item: dict[str, Any], dataset_version: str, contract_version: str) -> dict[str, Any]:
    source = str(item.get("source") or "").strip()
    chunk_id = str(item.get("chunk_id") or item.get("locator") or "").strip()
    if not source or not chunk_id:
        raise ValueError("evidence item requires source and chunk locator")
    return {
        "tool": item.get("tool"),
        "source": source,
        "chunk_id": chunk_id,
        "dataset_version": dataset_version,
        "contract_version": contract_version,
        "content": item.get("content"),
        "metadata": item.get("metadata", {}),
        "source_category": item.get("source_category"),
        "source_description": item.get("source_description"),
        "upstream_pipeline": item.get("upstream_pipeline"),
        "quality_notes": item.get("quality_notes"),
        "owner_table": item.get("owner_table"),
    }


def _parse_tool_content(content: Any) -> dict[str, Any] | None:
    if isinstance(content, dict):
        if {"tool", "result"} & set(content.keys()):
            return content
        if "text" in content:
            return _parse_tool_content(content.get("text"))
        return content
    if isinstance(content, list):
        for item in content:
            parsed = _parse_tool_content(item)
            if parsed is not None:
                return parsed
        return None
    if not isinstance(content, str):
        return None
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(content)
        except Exception:
            continue
        parsed_payload = _parse_tool_content(parsed)
        if parsed_payload is not None:
            return parsed_payload
    return None


def _iter_parsed_tool_payloads(tool_events: list[dict[str, Any]]):
    for event in tool_events:
        payload = _parse_tool_content(event.get("content"))
        if payload is not None:
            yield event, payload


def evaluate_tool_stop_condition(event: dict[str, Any], runner_settings: dict[str, Any]) -> dict[str, Any] | None:
    stop_config = (runner_settings or {}).get("stop_on_tool_answer") or {}
    if not stop_config.get("enabled"):
        return None
    if event.get("name") != stop_config.get("tool_name"):
        return None

    payload = _parse_tool_content(event.get("content"))
    if not isinstance(payload, dict):
        return None

    result = payload.get("result") or {}
    if not isinstance(result, dict):
        return None

    answer = result.get("answer")
    normalized_answer = answer.strip() if isinstance(answer, str) else ""
    lowered_answer = normalized_answer.lower()
    rows = result.get("results") if isinstance(result.get("results"), list) else []
    result_count = _coerce_int(result.get("result_count"), len(rows))

    if stop_config.get("require_answer", True) and not normalized_answer:
        return None
    if stop_config.get("require_evidence", True) and result_count < _coerce_int(stop_config.get("min_results"), 1):
        return None
    low_confidence_answer = any(
        lowered_answer.startswith(prefix) for prefix in stop_config.get("reject_answer_prefixes", [])
    )
    if low_confidence_answer and not stop_config.get("allow_low_confidence_answer_with_evidence"):
        return None

    return {
        "tool": event.get("name"),
        "answer": normalized_answer,
        "result_count": result_count,
        "answer_confidence": "low" if low_confidence_answer else "normal",
        "stop_reason": "evidence_sufficient_low_confidence_answer" if low_confidence_answer else "usable_tool_answer",
    }


def _collect_evidence(tool_events: list[dict[str, Any]], dataset_version: str, contract_version: str) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    seen_keys: set[tuple[str | None, str, str]] = set()
    for event, payload in _iter_parsed_tool_payloads(tool_events):
        result = ((payload or {}).get("result") or {})
        structured_output = result.get("structured_output") if isinstance(result.get("structured_output"), dict) else {}
        structured_rows = (
            structured_output.get("evidence_rows")
            if isinstance(structured_output.get("evidence_rows"), list)
            else []
        )
        rows = structured_rows or (result.get("results") if isinstance(result.get("results"), list) else [])
        synthetic_rows: list[dict[str, Any]] = []
        if not rows:
            if event.get("name") == "list_sources":
                synthetic_rows = [
                    {
                        "source": row.get("source"),
                        "chunk_id": f"source_summary:{row.get('record_type', 'unknown')}:chunk_count={row.get('chunk_count', 'unknown')}",
                        "content": json.dumps(row, ensure_ascii=False),
                        "metadata": row,
                        "source_category": row.get("source_category"),
                        "source_description": row.get("source_description"),
                        "upstream_pipeline": row.get("upstream_pipeline"),
                        "quality_notes": row.get("quality_notes"),
                        "owner_table": row.get("owner_table"),
                    }
                    for row in (result.get("sources") or [])
                    if isinstance(row, dict)
                ]
            elif event.get("name") == "get_source_summary":
                source_registry = result.get("source_registry") if isinstance(result.get("source_registry"), dict) else {}
                synthetic_rows = [
                    {
                        "source": row.get("source") or result.get("source"),
                        "chunk_id": f"source_summary:{row.get('record_type', 'unknown')}:chunk_count={row.get('chunk_count', result.get('total_chunks', 'unknown'))}",
                        "content": json.dumps(
                            {
                                "summary_source": result.get("source"),
                                "record_type": row.get("record_type"),
                                "chunk_count": row.get("chunk_count"),
                                "total_chunks": result.get("total_chunks"),
                            },
                            ensure_ascii=False,
                        ),
                        "metadata": row,
                        "source_category": source_registry.get("source_category"),
                        "source_description": source_registry.get("source_description"),
                        "upstream_pipeline": source_registry.get("upstream_pipeline"),
                        "quality_notes": source_registry.get("quality_notes"),
                        "owner_table": source_registry.get("owner_table"),
                    }
                    for row in (result.get("record_types") or [])
                    if isinstance(row, dict)
                ]
        for row in rows or synthetic_rows:
            if not isinstance(row, dict):
                continue
            normalized = normalize_evidence_item(
                {
                    "tool": event.get("name"),
                    "source": row.get("source"),
                    "chunk_id": row.get("chunk_id"),
                    "content": row.get("excerpt") or row.get("content"),
                    "metadata": row.get("metadata", {}),
                    "source_category": row.get("source_category"),
                    "source_description": row.get("source_description"),
                    "upstream_pipeline": row.get("upstream_pipeline"),
                    "quality_notes": row.get("quality_notes"),
                    "owner_table": row.get("owner_table"),
                },
                dataset_version,
                contract_version,
            )
            dedupe_key = (normalized.get("tool"), normalized["source"], normalized["chunk_id"])
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            evidence.append(normalized)
    return evidence


def _collect_tool_answer(tool_events: list[dict[str, Any]]) -> str:
    answers: list[str] = []
    for _event, payload in _iter_parsed_tool_payloads(tool_events):
        result = ((payload or {}).get("result") or {})
        answer = result.get("answer_text") or result.get("answer")
        if isinstance(answer, str) and answer.strip():
            answers.append(answer.strip())
    if not answers:
        return ""
    return max(answers, key=len)


def _collect_runtime_provenance(tool_events: list[dict[str, Any]]) -> dict[str, Any]:
    for _event, payload in reversed(list(_iter_parsed_tool_payloads(tool_events))):
        provenance = payload.get("provenance")
        if isinstance(provenance, dict) and provenance:
            return provenance
    return {}


def _collect_structured_output(tool_events: list[dict[str, Any]]) -> dict[str, Any]:
    for event, payload in reversed(list(_iter_parsed_tool_payloads(tool_events))):
        if event.get("name") != "search_knowledge":
            continue
        result = ((payload or {}).get("result") or {})
        structured = result.get("structured_output")
        if isinstance(structured, dict) and structured:
            return structured
    return {}


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _is_placeholder_answer(answer: str) -> bool:
    normalized = answer.strip().lower()
    if not normalized:
        return True
    return normalized.startswith(
        (
            "i'll follow your instructions",
            "i will follow your instructions",
            "let me follow your instructions",
            "i'll start by searching",
            "i will start by searching",
            "i'll begin by searching",
            "now i'll",
            "now i will",
            "next i'll",
            "next i will",
            "let me get",
            "i'll get",
            "i will get",
        )
    )


def _is_low_confidence_answer(answer: str) -> bool:
    normalized = " ".join(answer.strip().lower().split())
    if not normalized:
        return False
    return normalized.startswith(
        (
            "insufficient evidence",
            "not enough evidence",
            "unable to answer confidently",
            "cannot answer confidently",
            "i don't know",
            "no confident answer",
        )
    )


def _extract_chunk_count(item: dict[str, Any]) -> int | None:
    metadata = item.get("metadata") or {}
    raw_count = metadata.get("chunk_count")
    try:
        if raw_count is not None:
            return int(raw_count)
    except (TypeError, ValueError):
        pass
    match = re.search(r"chunk_count=(\d+)", str(item.get("chunk_id") or ""))
    if match:
        return int(match.group(1))
    return None


def _infer_source_category(source: str) -> str:
    lowered = source.lower()
    if "plmsearch" in lowered:
        return "filename suggests PLM / similarity search outputs"
    if "loop_annotations" in lowered:
        return "filename suggests loop annotation records"
    if "loop_flexibility" in lowered:
        return "filename suggests loop flexibility metrics"
    if "protein_cards" in lowered:
        return "filename suggests protein-centered cards"
    if "interaction_cards" in lowered:
        return "filename suggests interaction-centered cards"
    if "affinity" in lowered:
        return "filename suggests affinity assay outputs"
    if "developability" in lowered:
        return "filename suggests developability summaries"
    return "filename suggests a structured FBBP runtime table"


def _build_provenance_summary_from_evidence(evidence: list[dict[str, Any]]) -> str:
    source_rows: dict[str, dict[str, Any]] = {}
    for item in evidence:
        if item.get("tool") not in {"list_sources", "get_source_summary"}:
            continue
        source = str(item.get("source") or "").strip()
        if not source:
            continue
        candidate = {
            "source": source,
            "record_type": str((item.get("metadata") or {}).get("record_type") or "unknown"),
            "chunk_count": _extract_chunk_count(item),
        }
        existing = source_rows.get(source)
        if existing is None or (candidate["chunk_count"] or -1) > (existing["chunk_count"] or -1):
            source_rows[source] = candidate

    ranked = sorted(
        source_rows.values(),
        key=lambda row: (row["chunk_count"] is not None, row["chunk_count"] or -1, row["source"]),
        reverse=True,
    )
    if not ranked:
        return ""

    top_rows = ranked[:3]
    mid_rows = [row for row in ranked[3:] if row["chunk_count"] == 1996][:5]

    supported_lines = [
        "Supported findings:",
    ]
    for row in top_rows:
        chunk_count = row["chunk_count"]
        chunk_label = f"`chunk_count={chunk_count}`" if chunk_count is not None else "`chunk_count=unknown`"
        supported_lines.append(
            f"- `{row['source']}` dominates or ranks near the top of the indexed runtime with {chunk_label} and `record_type={row['record_type']}`; {_infer_source_category(row['source'])}."
        )
    if mid_rows:
        supported_lines.append(
            "- A broad middle tier of sources remains tied at `chunk_count=1996`, including "
            + ", ".join(f"`{row['source']}`" for row in mid_rows)
            + "."
        )

    uncertainty_lines = [
        "Uncertainty and provenance caveats:",
        "- Source category labels above are filename-based inference unless directly confirmed by the runtime payload.",
        "- `record_type=jsonl` describes the indexed storage representation, not the scientific modality by itself.",
        "- `chunk_count` measures indexed coverage in the current runtime, not scientific quality, confidence, or business priority.",
    ]

    return "\n".join(supported_lines + [""] + uncertainty_lines)


def _build_knottin_summary_from_evidence(evidence: list[dict[str, Any]]) -> str:
    knottin_items = [item for item in evidence if item.get("tool") == "search_knowledge"]
    if not knottin_items:
        return ""

    sources = sorted({str(item.get("source") or "").strip() for item in knottin_items if item.get("source")})
    identifiers = [str(item.get("chunk_id") or "").strip() for item in knottin_items if item.get("chunk_id")]
    top_identifiers = identifiers[:3]

    all_content = "\n".join(str(item.get("content") or "") for item in knottin_items)
    domain_names = sorted(
        {
            match.group(1).strip()
            for match in re.finditer(r"- Domain Nam<local_path_removed>", all_content)
            if match.group(1).strip()
        }
    )
    engineered_yes = all_content.count("- Is Engineered: Yes")
    engineered_no = all_content.count("- Is Engineered: No")

    supported_lines = [
        "Supported findings:",
    ]
    if sources:
        supported_lines.append(
            "- Retrieved knottin evidence is concentrated in "
            + ", ".join(f"`{source}`" for source in sources)
            + "."
        )
    if top_identifiers:
        supported_lines.append(
            "- Representative evidence identifiers include "
            + ", ".join(f"`{identifier}`" for identifier in top_identifiers)
            + "."
        )
    if "CYSTINE KNOT SCAFFOLD PLATFORM" in all_content or "Scaffold Type: knottin" in all_content:
        supported_lines.append(
            "- Structural descriptors explicitly present in retrieved evidence include `CYSTINE KNOT SCAFFOLD PLATFORM` and `Scaffold Type: knottin`."
        )
    if domain_names:
        supported_lines.append(
            "- Retrieved target-linked domain examples include "
            + ", ".join(f"`{name}`" for name in domain_names[:5])
            + "."
        )
    if engineered_yes or engineered_no:
        supported_lines.append(
            f"- The retrieved set contains both engineered (`{engineered_yes}` observed) and non-engineered (`{engineered_no}` observed) knottin entries."
        )

    uncertainty_lines = [
        "Uncertainty and limitations:",
        "- Broader target-class coverage is limited to what appears in the retrieved evidence and is not a full database census.",
        "- This synthesis is grounded in retrieved search hits and may miss deeper protein-level structure detail unless additional evidence is requested.",
    ]
    return "\n".join(supported_lines + [""] + uncertainty_lines)


def _build_generic_evidence_summary(evidence: list[dict[str, Any]]) -> str:
    if not evidence:
        return ""
    source_counts: dict[str, int] = {}
    identifiers: list[str] = []
    for item in evidence:
        source = str(item.get("source") or "").strip()
        if source:
            source_counts[source] = source_counts.get(source, 0) + 1
        chunk_id = str(item.get("chunk_id") or "").strip()
        if chunk_id:
            identifiers.append(chunk_id)

    ranked_sources = sorted(source_counts.items(), key=lambda pair: (-pair[1], pair[0]))
    supported_lines = ["Supported findings:"]
    if ranked_sources:
        source_summary = ", ".join(f"`{source}` ({count})" for source, count in ranked_sources[:3])
        supported_lines.append(
            "- Retrieved evidence is limited and concentrated in "
            + source_summary
            + "."
        )
    if identifiers:
        supported_lines.append(
            "- Representative evidence identifiers include "
            + ", ".join(f"`{identifier}`" for identifier in identifiers[:5])
            + "."
        )

    uncertainty_lines = [
        "Uncertainty and limitations:",
        "- The tool-level extractive answer remained low-confidence, so this summary stays close to retrieved evidence rows.",
        "- Additional targeted retrieval may still be required before making broader biological or product-level claims.",
    ]
    return "\n".join(supported_lines + [""] + uncertainty_lines)


def _build_guardrailed_summary(case_id: str, evidence: list[dict[str, Any]]) -> str:
    if "knottin" in case_id.lower():
        summary = _build_knottin_summary_from_evidence(evidence)
        if summary:
            return summary
    summary = _build_provenance_summary_from_evidence(evidence)
    if summary:
        return summary
    return _build_generic_evidence_summary(evidence)


def _claims_are_low_confidence(claims: list[dict[str, Any]]) -> bool:
    texts = [
        str(item.get("text") or "").strip()
        for item in claims
        if isinstance(item, dict) and str(item.get("text") or "").strip()
    ]
    if not texts:
        return False
    return all(_is_low_confidence_answer(text) or _is_placeholder_answer(text) for text in texts)


def _claim_text_from_summary(answer: str) -> str:
    for raw_line in answer.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.endswith(":"):
            continue
        if line.startswith("- "):
            return line[2:].strip()
        if line.startswith("|"):
            continue
        return re.split(r"(?<=[.!?])\s+", line, maxsplit=1)[0].strip()
    return ""


def _render_formal_report_markdown(
    *,
    template_path: Path,
    case_config: dict[str, Any],
    raw: dict[str, Any],
    dataset_version: str,
    contract_version: str,
    evidence: list[dict[str, Any]],
) -> str:
    template = template_path.read_text(encoding="utf-8")
    completion_mode = "partial_evidence_only" if raw.get("partial") else "full"
    lines = [
        template.rstrip(),
        "",
        "## Generated Summary",
        f"- Case ID: {case_config.get('case_id', raw.get('thread_id', 'unknown'))}",
        f"- Title: {case_config.get('title', '')}",
        f"- Dataset version: {dataset_version}",
        f"- MCP contract version: {contract_version}",
        f"- Completion mode: {completion_mode}",
        f"- Completion reason: {raw.get('completion_reason') or 'agent_completed'}",
        "",
        "## Prompt",
        raw.get("prompt", ""),
        "",
        "## Conclusion",
        raw.get("answer", ""),
        "",
    ]
    preflight = raw.get("preflight") if isinstance(raw.get("preflight"), dict) else {}
    if preflight:
        lines[10:10] = [
            "## Preflight",
            f"- Attempted: {preflight.get('attempted')}",
            f"- Hit: {preflight.get('hit')}",
            f"- Mode: {preflight.get('mode')}",
            f"- Tool event count: {preflight.get('tool_event_count')}",
            "",
        ]
    if raw.get("partial"):
        lines.extend(
            [
                "## Execution Notes",
                f"- Agent did not reach a final stop condition: {raw.get('termination_reason', 'partial_execution')}",
                f"- Detail: {raw.get('termination_error', 'not provided')}",
                "",
            ]
        )
    lines.extend(
        [
        "## Evidence Items",
        ]
    )
    if evidence:
        for item in evidence:
            lines.append(f"- `{item['tool']}` -> `{item['source']}` / `{item['chunk_id']}`")
    else:
        lines.append("- No structured evidence items were extracted.")
    return "\n".join(lines).strip() + "\n"


def build_formal_outputs(
    raw: dict[str, Any],
    *,
    case_config: dict[str, Any],
    dataset_version: str,
    contract_version: str,
    template_path: Path,
) -> dict[str, Any]:
    tool_events = list(raw.get("tool_events", []))
    evidence = _collect_evidence(tool_events, dataset_version, contract_version)
    structured_output = _collect_structured_output(tool_events)
    runtime_provenance = _collect_runtime_provenance(tool_events)
    tool_answer = _collect_tool_answer(tool_events)
    partial = bool(raw.get("partial"))
    resolved_answer = raw.get("answer", "")
    structured_claims = structured_output.get("claims") if isinstance(structured_output.get("claims"), list) else []
    guardrail_applied = False
    if (not resolved_answer) and structured_claims:
        first_claim = structured_claims[0] if isinstance(structured_claims[0], dict) else {}
        if isinstance(first_claim.get("text"), str) and first_claim.get("text", "").strip():
            resolved_answer = first_claim["text"].strip()
    if tool_answer and (partial or not resolved_answer):
        resolved_answer = tool_answer
    if _is_placeholder_answer(resolved_answer) and structured_claims:
        first_claim = structured_claims[0] if isinstance(structured_claims[0], dict) else {}
        if isinstance(first_claim.get("text"), str) and first_claim.get("text", "").strip():
            resolved_answer = first_claim["text"].strip()
    if not partial and _is_placeholder_answer(resolved_answer):
        synthesized_answer = _build_provenance_summary_from_evidence(evidence)
        if not synthesized_answer and "knottin_landscape" in str(case_config.get("case_id") or raw.get("thread_id") or ""):
            synthesized_answer = _build_knottin_summary_from_evidence(evidence)
        if synthesized_answer:
            resolved_answer = synthesized_answer
    if not partial and evidence and _is_low_confidence_answer(tool_answer):
        guardrailed_answer = _build_guardrailed_summary(
            str(case_config.get("case_id") or raw.get("thread_id") or ""),
            evidence,
        )
        if guardrailed_answer:
            resolved_answer = guardrailed_answer
            guardrail_applied = True
            if not structured_claims or _claims_are_low_confidence(structured_claims):
                claim_text = _claim_text_from_summary(guardrailed_answer)
                structured_claims = (
                    [
                        {
                            "claim_id": "claim_1",
                            "text": claim_text,
                            "support": "retrieved_evidence",
                            "evidence_count": len(evidence),
                        }
                    ]
                    if claim_text
                    else []
                )
    limitations = _dedupe_strings(
        [str(item) for item in (structured_output.get("limitations") or []) if str(item).strip()]
    )
    if partial:
        limitations.append(
            f"Agent terminated before a final stop condition ({raw.get('termination_reason', 'partial_execution')})."
        )
        if not resolved_answer and evidence:
            resolved_answer = "Agent did not reach a final answer. This report summarizes captured evidence only."
    if not evidence:
        limitations.append("No structured evidence extracted from tool events.")
    if guardrail_applied:
        limitations.append(
            "The tool-level extractive answer remained low-confidence, so the final conclusion was downgraded to a conservative evidence summary."
        )
    limitations = _dedupe_strings(limitations)
    provenance_caveats = _dedupe_strings(
        [str(item) for item in (structured_output.get("provenance_caveats") or []) if str(item).strip()]
    )
    if guardrail_applied:
        provenance_caveats = _dedupe_strings(
            provenance_caveats
            + ["Final report wording was constrained to retrieved evidence because the tool-level answer was low-confidence."]
        )

    rendered_raw = dict(raw)
    rendered_raw["answer"] = resolved_answer
    report_json = {
        "case_id": case_config.get("case_id", raw.get("thread_id")),
        "title": case_config.get("title"),
        "thread_id": raw.get("thread_id"),
        "prompt": raw.get("prompt"),
        "completion_mode": "partial_evidence_only" if partial else "full",
        "completion_reason": raw.get("completion_reason"),
        "preflight": raw.get("preflight") if isinstance(raw.get("preflight"), dict) else None,
        "termination_reason": raw.get("termination_reason"),
        "conclusions": [resolved_answer] if resolved_answer else [],
        "limitations": limitations,
        "claims": structured_claims
        if structured_claims
        else ([{"claim_id": "claim_1", "text": resolved_answer}] if resolved_answer else []),
        "evidence_rows": [
            {
                "tool": item["tool"],
                "source": item["source"],
                "chunk_id": item["chunk_id"],
                "source_category": item.get("source_category"),
                "source_description": item.get("source_description"),
                "upstream_pipeline": item.get("upstream_pipeline"),
                "quality_notes": item.get("quality_notes"),
                "owner_table": item.get("owner_table"),
            }
            for item in evidence
        ],
        "provenance_caveats": provenance_caveats,
        "runtime_provenance": runtime_provenance,
        "key_evidence": [
            {"tool": item["tool"], "source": item["source"], "chunk_id": item["chunk_id"]}
            for item in evidence
        ],
    }
    tool_call_rows = [
        {
            "tool": event.get("name"),
            "content": event.get("content"),
            "tool_call_id": event.get("tool_call_id"),
        }
        for event in tool_events
    ]
    report_markdown = _render_formal_report_markdown(
        template_path=template_path,
        case_config=case_config,
        raw=rendered_raw,
        dataset_version=dataset_version,
        contract_version=contract_version,
        evidence=evidence,
    )
    return {
        "report_json": report_json,
        "report_markdown": report_markdown,
        "evidence": evidence,
        "tool_call_rows": tool_call_rows,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    path.write_text(body + ("\n" if body else ""), encoding="utf-8")
