from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from formal_run_lib import load_yaml_config


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROUTES_CONFIG = REPO_ROOT / "configs" / "control_plane" / "routes.yaml"
DEFAULT_SECONDARY_CONFIG = REPO_ROOT / "configs" / "control_plane" / "secondary_capabilities.yaml"


def load_routes_config(path: Path | None = None) -> dict[str, Any]:
    return load_yaml_config(path or DEFAULT_ROUTES_CONFIG)


def load_secondary_config(path: Path | None = None) -> dict[str, Any]:
    return load_yaml_config(path or DEFAULT_SECONDARY_CONFIG)


def _rel_path_str(raw: str | Path) -> str:
    path = Path(raw)
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except Exception:
        return path.resolve().as_posix()


def _field_paths(rule: dict[str, Any], request: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for field in rule.get("fields", []):
        raw = request.get(field)
        if raw:
            paths.append(Path(str(raw)).resolve())
    return paths


def _path_matches(rule: dict[str, Any], request: dict[str, Any]) -> tuple[bool, list[str]]:
    matched: list[str] = []
    paths = _field_paths(rule, request)
    if not paths:
        return False, matched

    globs = [str(item) for item in rule.get("path_globs", [])]
    required_children = [str(item) for item in rule.get("required_children", [])]

    for path in paths:
        rel = _rel_path_str(path)
        if globs and any(fnmatch(rel, pattern) for pattern in globs):
            matched.append(rel)
            continue
        if path.is_dir() and required_children:
            for child_name in required_children:
                child = path / child_name
                if child.exists():
                    matched.append(_rel_path_str(child))
                    break
        elif not globs:
            matched.append(rel)
    return bool(matched), matched


def _query_text(request: dict[str, Any]) -> str:
    query = str(request.get("query") or "")
    route_hint_parts = [Path(item["path"]).name for item in request.get("input_files", []) if item.get("path")]
    return " ".join([query, *route_hint_parts]).strip().lower()


def _detect_keyword_route(request: dict[str, Any], config: dict[str, Any]) -> tuple[str | None, dict[str, list[str]]]:
    text = _query_text(request)
    matches: dict[str, list[str]] = {}
    for route, rule in (config.get("keyword_rules") or {}).items():
        found = [keyword for keyword in rule.get("any_keywords", []) if keyword.lower() in text]
        if found:
            matches[route] = found
    if not matches:
        return None, {}
    ranked = sorted(matches.items(), key=lambda item: len(item[1]), reverse=True)
    return ranked[0][0], matches


def _requested_mode_route(request: dict[str, Any], config: dict[str, Any]) -> str | None:
    mode = str(request.get("requested_mode") or "").strip().lower()
    if not mode or mode == "auto":
        return None
    override = (config.get("mode_overrides") or {}).get(mode)
    return str(override).strip() or None


def _detect_secondary_capabilities(
    request: dict[str, Any],
    primary_route: str,
    config: dict[str, Any],
) -> tuple[list[str], dict[str, list[str]]]:
    text = _query_text(request)
    requested = [str(item) for item in request.get("requested_secondary_capabilities", [])]
    selected: list[str] = []
    reasons: dict[str, list[str]] = {}

    for item in requested:
        if item not in selected:
            selected.append(item)
            reasons[item] = ["explicit_request"]

    for name, rule in (config.get("capabilities") or {}).items():
        applies = [str(item) for item in rule.get("applies_to_routes", [])]
        if applies and primary_route not in applies:
            continue
        local_reasons: list[str] = []
        if primary_route in [str(item) for item in rule.get("always_on_routes", [])]:
            local_reasons.append("always_on_route")
        for keyword in rule.get("trigger_keywords", []):
            if str(keyword).lower() in text:
                local_reasons.append(f"keyword:{keyword}")
        if local_reasons and name not in selected:
            selected.append(name)
            reasons[name] = local_reasons
        elif local_reasons:
            reasons.setdefault(name, []).extend(local_reasons)
    return selected, reasons


def route_request(
    request: dict[str, Any],
    *,
    routes_config: dict[str, Any] | None = None,
    secondary_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    routes_config = routes_config or load_routes_config()
    secondary_config = secondary_config or load_secondary_config()

    reasons: list[str] = []
    matched_file_rules: list[dict[str, Any]] = []
    keyword_matches: dict[str, list[str]] = {}

    forced = str(request.get("force_primary_route") or "").strip()
    if forced:
        primary_route = forced
        reasons.append(f"force_primary_route:{forced}")
        decision_source = "force_primary_route"
    else:
        primary_route = _requested_mode_route(request, routes_config)
        if primary_route:
            reasons.append(f"mode_override:{request.get('requested_mode')}")
            decision_source = "mode_override"
        else:
            decision_source = "default"
            for rule in routes_config.get("file_rules", []):
                matched, matched_paths = _path_matches(rule, request)
                if matched:
                    primary_route = str(rule["route"])
                    matched_file_rules.append(
                        {
                            "route": primary_route,
                            "matched_paths": matched_paths,
                            "reason": str(rule.get("reason") or "file_rule"),
                        }
                    )
                    reasons.append(f"file_rule:{rule.get('reason') or primary_route}")
                    decision_source = "file_rule"
                    break
            if not primary_route:
                primary_route, keyword_matches = _detect_keyword_route(request, routes_config)
                if primary_route:
                    reasons.append(f"keyword_rule:{primary_route}")
                    decision_source = "keyword_rule"
            if not primary_route:
                primary_route = str(routes_config.get("default_primary_route") or "fallback_general")
                reasons.append(f"default_route:{primary_route}")

    secondary_capabilities, secondary_reasons = _detect_secondary_capabilities(
        request,
        primary_route,
        secondary_config,
    )
    return {
        "primary_route": primary_route,
        "secondary_capabilities": secondary_capabilities,
        "secondary_capability_reasons": secondary_reasons,
        "forced_primary_route": bool(forced),
        "requested_mode": request.get("requested_mode"),
        "decision_source": decision_source,
        "reasons": reasons,
        "matched_file_rules": matched_file_rules,
        "keyword_matches": keyword_matches,
        "input_files": list(request.get("input_files", [])),
    }

