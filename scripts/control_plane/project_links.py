from __future__ import annotations

from pathlib import Path
from typing import Any

from formal_run_lib import load_yaml_config


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROJECT_LINKS = REPO_ROOT / "configs" / "control_plane" / "project_links.yaml"


def load_project_links(path: Path | None = None) -> dict[str, Any]:
    config = load_yaml_config(path or DEFAULT_PROJECT_LINKS)
    return config or {"version": 1, "projects": {}}


def _resolve_path(raw: str | None, *, base: Path) -> str | None:
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = base / path
    return str(path.resolve())


def resolved_project_links(path: Path | None = None) -> dict[str, Any]:
    config = load_project_links(path)
    base = REPO_ROOT
    projects: dict[str, Any] = {}
    for name, project in (config.get("projects") or {}).items():
        if not isinstance(project, dict):
            continue
        item = dict(project)
        item["name"] = name
        item["resolved_path"] = _resolve_path(str(project.get("path") or ""), base=base)
        if project.get("python_src"):
            item["resolved_python_src"] = _resolve_path(str(project.get("python_src")), base=base)
        projects[name] = item
    return {
        "version": config.get("version", 1),
        "workspace_root": _resolve_path(str(config.get("workspace_root") or ".."), base=base),
        "projects": projects,
    }


def project_summary(*names: str, path: Path | None = None) -> list[dict[str, Any]]:
    links = resolved_project_links(path)
    projects = links.get("projects") or {}
    selected = names or tuple(projects.keys())
    summary: list[dict[str, Any]] = []
    for name in selected:
        project = projects.get(name)
        if not isinstance(project, dict):
            continue
        summary.append(
            {
                "name": name,
                "role": project.get("role"),
                "path": project.get("resolved_path"),
                "owns": project.get("owns") or [],
            }
        )
    return summary
