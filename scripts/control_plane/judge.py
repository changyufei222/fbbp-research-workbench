from __future__ import annotations

from pathlib import Path
from typing import Any

from formal_run_lib import load_yaml_config


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_JUDGES_CONFIG = REPO_ROOT / "configs" / "control_plane" / "judges.yaml"


def _answer_present(result_summary: dict[str, Any]) -> bool:
    preview = str((result_summary or {}).get("answer_preview") or "").strip()
    return bool(preview)


def evaluate_run(
    route_decision: dict[str, Any],
    status: str,
    result_summary: dict[str, Any],
    *,
    judges_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    judges_config = judges_config or load_yaml_config(DEFAULT_JUDGES_CONFIG)
    defaults = judges_config.get("route_defaults") or {}
    route = str(route_decision.get("primary_route") or "fallback_general")
    thresholds = judges_config.get("thresholds") or {}
    pass_threshold = float(thresholds.get("pass") or 0.7)
    review_threshold = float(thresholds.get("review") or 0.4)

    if status == "dry_run":
        score = float(((defaults.get("dry_run") or {}).get("score")) or 0.1)
        reason = str(((defaults.get("dry_run") or {}).get("reason")) or "dry run only")
    elif status == "failed":
        score = 0.0
        reason = "route execution failed"
    elif route == "private_rag":
        route_defaults = defaults.get("private_rag") or {}
        if _answer_present(result_summary):
            score = float(route_defaults.get("success_with_answer") or 0.8)
            reason = "private_rag returned an answer preview"
        else:
            score = float(route_defaults.get("success_without_answer") or 0.45)
            reason = "private_rag completed without answer preview"
    elif route == "report_generation":
        route_defaults = defaults.get("report_generation") or {}
        if str(result_summary.get("title") or "").strip():
            score = float(route_defaults.get("success_with_title") or 0.8)
            reason = "report_generation loaded a titled report"
        else:
            score = float(route_defaults.get("success_without_title") or 0.5)
            reason = "report_generation completed with weak metadata"
    elif route == "public_lookup":
        route_defaults = defaults.get("public_lookup") or {}
        success_rate = float(result_summary.get("tool_success_rate") or 0.0)
        if success_rate >= 1.0 and int(result_summary.get("tool_call_count") or 0) > 0:
            score = float(route_defaults.get("success_all_tools") or 0.8)
            reason = "public_lookup completed all selected tool calls"
        elif success_rate > 0:
            score = float(route_defaults.get("success_partial_tools") or 0.55)
            reason = "public_lookup completed with partial tool success"
        else:
            score = float(route_defaults.get("success_without_tools") or 0.25)
            reason = "public_lookup completed without successful tool calls"
    elif route == "formal_case":
        route_defaults = defaults.get("formal_case") or {}
        score = float(route_defaults.get(status) or route_defaults.get("succeeded") or 0.8)
        reason = f"formal_case status={status}"
    elif route == "batch_eval":
        route_defaults = defaults.get("batch_eval") or {}
        score = float(route_defaults.get(status) or route_defaults.get("succeeded") or 0.8)
        reason = f"batch_eval status={status}"
    else:
        route_defaults = defaults.get("fallback_general") or {}
        if _answer_present(result_summary):
            score = float(route_defaults.get("success_with_answer") or 0.7)
            reason = "fallback_general returned an answer preview"
        else:
            score = float(route_defaults.get("success_without_answer") or 0.35)
            reason = "fallback_general completed without answer preview"

    if score >= pass_threshold:
        judge_status = "pass"
    elif score >= review_threshold:
        judge_status = "review"
    else:
        judge_status = "fail"

    return {
        "score": round(score, 4),
        "status": judge_status,
        "reason": reason,
        "primary_route": route,
    }
