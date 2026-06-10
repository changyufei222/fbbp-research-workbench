from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from formal_run_lib import load_yaml_config

from control_plane.eval_dashboard import collect_run_records, write_dashboard, write_portfolio_dashboard
from control_plane.production_hardening_check import run_hardening_check
from control_plane.semantic_memory import backfill_memory_from_runs, load_semantic_memory, write_memory_dashboard


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = REPO_ROOT.parent
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "runs" / "control_plane" / "final_release" / "latest"
PORTFOLIO_ROOT = REPO_ROOT / "reports" / "control_plane_portfolio_dashboard" / "latest"


def _check(name: str, ok: bool, *, details: dict[str, Any] | None = None, severity: str = "required") -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "severity": severity, "details": details or {}}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _required_files() -> dict[str, Path]:
    return {
        "docker_compose": REPO_ROOT / "docker-compose.yml",
        "dashboard_dockerfile": REPO_ROOT / "Dockerfile.dashboard",
        "dashboard_server": REPO_ROOT / "scripts" / "control_plane" / "dashboard_server.py",
        "fullstack_launcher": REPO_ROOT / "scripts" / "start_fbbp_fullstack.ps1",
        "dashboard_builder": REPO_ROOT / "scripts" / "build_portfolio_dashboard.ps1",
        "deployment_runbook": REPO_ROOT / "docs" / "deployment-runbook-cn.md",
        "project_page_cn": REPO_ROOT / "docs" / "job-ready-project-page-cn.md",
        "portfolio_dashboard": PORTFOLIO_ROOT / "index.html",
        "semantic_memory_viewer": PORTFOLIO_ROOT / "semantic_memory.html",
        "semantic_memory_store": REPO_ROOT / "runs" / "control_plane" / "memory" / "semantic_memory.json",
    }


def check_required_files() -> dict[str, Any]:
    files = _required_files()
    missing = {name: str(path) for name, path in files.items() if not path.exists()}
    return _check(
        "required_release_files",
        not missing,
        details={"missing": missing, "files": {name: str(path) for name, path in files.items()}},
    )


def check_compose_static() -> dict[str, Any]:
    compose_path = REPO_ROOT / "docker-compose.yml"
    try:
        compose = load_yaml_config(compose_path)
    except Exception as exc:
        return _check("docker_compose_static", False, details={"error": str(exc), "path": str(compose_path)})
    services = compose.get("services") if isinstance(compose.get("services"), dict) else {}
    required = {"postgres", "redis", "dashboard"}
    missing = sorted(required - set(services))
    healthchecks = {name: bool((services.get(name) or {}).get("healthcheck")) for name in ["postgres", "redis"]}
    dashboard = services.get("dashboard") if isinstance(services.get("dashboard"), dict) else {}
    ok = (
        not missing
        and all(healthchecks.values())
        and bool(dashboard.get("build"))
        and bool(dashboard.get("healthcheck"))
        and "8088:8088" in [str(item) for item in dashboard.get("ports", [])]
    )
    return _check(
        "docker_compose_static",
        ok,
        details={
            "path": str(compose_path),
            "services": sorted(services),
            "missing": missing,
            "healthchecks": healthchecks,
            "dashboard_ports": dashboard.get("ports", []),
            "dashboard_healthcheck": bool(dashboard.get("healthcheck")),
        },
    )


def check_docker_live(require: bool = False) -> dict[str, Any]:
    docker = shutil.which("docker")
    if not docker:
        return _check(
            "docker_compose_live",
            not require,
            severity="required" if require else "optional",
            details={"status": "skipped_no_docker_binary", "require": require},
        )
    proc = subprocess.run(
        [docker, "compose", "config"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    return _check(
        "docker_compose_live",
        proc.returncode == 0,
        details={
            "returncode": proc.returncode,
            "stdout_tail": proc.stdout.strip().splitlines()[-8:],
            "stderr_tail": proc.stderr.strip().splitlines()[-8:],
        },
    )


def check_dashboard_assets() -> dict[str, Any]:
    summary = _read_json(PORTFOLIO_ROOT / "portfolio_dashboard_summary.json")
    html = (PORTFOLIO_ROOT / "index.html").read_text(encoding="utf-8", errors="ignore") if (PORTFOLIO_ROOT / "index.html").exists() else ""
    semantic = summary.get("semantic_memory") if isinstance(summary.get("semantic_memory"), dict) else {}
    core_text = ["FBBP Agent Control Plane", "Route Metrics", "Production Hardening", "Memory", "Local Control Console", "Auto Refresh"]
    interactive_markers = ["dashboard-state", "portfolio_dashboard_summary.json", "Drill-down Details"]
    ok = (
        bool(summary)
        and summary.get("mode") == "live_local_control_console"
        and bool(summary.get("route_overview"))
        and bool(summary.get("recent_runs"))
        and all(text in html for text in core_text)
        and all(marker in html for marker in interactive_markers)
        and int(semantic.get("item_count") or 0) > 0
        and bool((summary.get("service_endpoints") or {}).get("rebuild"))
    )
    return _check(
        "portfolio_dashboard_assets",
        ok,
        details={
            "summary_path": str(PORTFOLIO_ROOT / "portfolio_dashboard_summary.json"),
            "html_path": str(PORTFOLIO_ROOT / "index.html"),
            "mode": summary.get("mode"),
            "route_overview_count": len(summary.get("route_overview") or []),
            "recent_run_count": len(summary.get("recent_runs") or []),
            "record_count": ((summary.get("summary") or {}).get("record_count") if isinstance(summary.get("summary"), dict) else None),
            "semantic_memory": semantic,
            "required_text": core_text,
            "interactive_markers": interactive_markers,
        },
    )


def check_semantic_memory_state() -> dict[str, Any]:
    store = load_semantic_memory(REPO_ROOT)
    items = store.get("items") if isinstance(store.get("items"), list) else []
    conflicts = store.get("conflicts") if isinstance(store.get("conflicts"), list) else []
    promoted_sources = sum(len(item.get("source_run_ids") or []) for item in items if isinstance(item, dict))
    ok = len(items) >= 1 and promoted_sources >= len(items)
    return _check(
        "semantic_memory_state",
        ok,
        details={
            "item_count": len(items),
            "conflict_count": len(conflicts),
            "promoted_source_run_count": promoted_sources,
            "store_path": str(REPO_ROOT / "runs" / "control_plane" / "memory" / "semantic_memory.json"),
        },
    )


def check_fbbp_naming() -> dict[str, Any]:
    public_docs = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "docs" / "job-ready-project-page-cn.md",
        REPO_ROOT / "docs" / "interview-demo-runbook.md",
        WORKSPACE_ROOT / "PORTFOLIO_OVERVIEW_CN.md",
        WORKSPACE_ROOT / "Resume_Projects_CN.md",
        WORKSPACE_ROOT / "PROJECT_DIRECTORY_MAP.md",
    ]
    uppercase_hits: list[str] = []
    for path in public_docs:
        if not path.exists():
            continue
        for idx, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
            if "FBTP" in line:
                uppercase_hits.append(f"{path}:{idx}:{line.strip()}")
    return _check(
        "fbbp_public_naming",
        not uppercase_hits,
        details={
            "rule": "Public narrative must use FBBP. Lowercase fbtp is allowed only as legacy path text.",
            "uppercase_fbtp_hits": uppercase_hits,
        },
    )


def _refresh_release_artifacts() -> dict[str, Any]:
    hardening = run_hardening_check(output_root=REPO_ROOT / "runs" / "control_plane" / "hardening" / "latest")
    memory_backfill = backfill_memory_from_runs(REPO_ROOT, REPO_ROOT / "runs" / "control_plane")
    memory_outputs = write_memory_dashboard(REPO_ROOT, PORTFOLIO_ROOT)
    records = collect_run_records(REPO_ROOT / "runs" / "control_plane")
    eval_outputs = write_dashboard(records, WORKSPACE_ROOT / "llm-eval-benchmark" / "reports" / "control_plane_dashboard" / "latest")
    portfolio_outputs = write_portfolio_dashboard(records, PORTFOLIO_ROOT)
    return {
        "hardening": {"ok": hardening.get("ok"), "passed_count": hardening.get("passed_count"), "check_count": hardening.get("check_count")},
        "memory_backfill": memory_backfill,
        "memory_outputs": memory_outputs,
        "eval_outputs": eval_outputs,
        "portfolio_outputs": portfolio_outputs,
    }


def _write_summary(output_root: Path, checks: list[dict[str, Any]], refresh: dict[str, Any]) -> dict[str, str]:
    output_root.mkdir(parents=True, exist_ok=True)
    required_checks = [item for item in checks if item.get("severity") != "optional"]
    summary = {
        "schema_version": "fbbp.control_plane.final_release.v1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "ok": all(item["ok"] for item in required_checks),
        "check_count": len(checks),
        "required_check_count": len(required_checks),
        "passed_count": sum(1 for item in checks if item["ok"]),
        "required_passed_count": sum(1 for item in required_checks if item["ok"]),
        "checks": checks,
        "refresh": refresh,
        "artifacts": {
            "portfolio_dashboard": str(PORTFOLIO_ROOT / "index.html"),
            "semantic_memory_viewer": str(PORTFOLIO_ROOT / "semantic_memory.html"),
            "deployment_runbook": str(REPO_ROOT / "docs" / "deployment-runbook-cn.md"),
            "docker_compose": str(REPO_ROOT / "docker-compose.yml"),
        },
        "known_boundary": "Docker live validation is optional on machines without Docker Desktop; static Compose validation remains required.",
    }
    json_path = output_root / "final_release_summary.json"
    md_path = output_root / "final_release_summary.md"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# FBBP Final Release Summary",
        "",
        f"- ok: {summary['ok']}",
        f"- required checks: {summary['required_passed_count']}/{summary['required_check_count']}",
        f"- all checks: {summary['passed_count']}/{summary['check_count']}",
        "",
        "## Checks",
        "",
    ]
    for item in checks:
        skipped = str((item.get("details") or {}).get("status") or "").startswith("skipped")
        mark = "SKIP" if item.get("severity") == "optional" and skipped else ("PASS" if item["ok"] else ("SKIP" if item.get("severity") == "optional" else "FAIL"))
        lines.append(f"- {mark} {item['name']} ({item.get('severity', 'required')})")
    lines.extend(
        [
            "",
            "## Main Artifacts",
            "",
            f"- Portfolio dashboard: `{summary['artifacts']['portfolio_dashboard']}`",
            f"- Semantic memory viewer: `{summary['artifacts']['semantic_memory_viewer']}`",
            f"- Deployment runbook: `{summary['artifacts']['deployment_runbook']}`",
            f"- Docker Compose: `{summary['artifacts']['docker_compose']}`",
            "",
            f"Known boundary: {summary['known_boundary']}",
        ]
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"summary_json": str(json_path), "summary_md": str(md_path)}


def run_final_release_check(*, output_root: Path = DEFAULT_OUTPUT_ROOT, require_docker_live: bool = False) -> dict[str, Any]:
    refresh = _refresh_release_artifacts()
    checks = [
        check_required_files(),
        check_compose_static(),
        check_docker_live(require=require_docker_live),
        check_dashboard_assets(),
        check_semantic_memory_state(),
        check_fbbp_naming(),
    ]
    hardening_summary = _read_json(REPO_ROOT / "runs" / "control_plane" / "hardening" / "latest" / "production_hardening_summary.json")
    checks.append(
        _check(
            "production_hardening_summary",
            bool(hardening_summary.get("ok")) and int(hardening_summary.get("passed_count") or 0) == int(hardening_summary.get("check_count") or -1),
            details={
                "path": str(REPO_ROOT / "runs" / "control_plane" / "hardening" / "latest" / "production_hardening_summary.json"),
                "passed_count": hardening_summary.get("passed_count"),
                "check_count": hardening_summary.get("check_count"),
            },
        )
    )
    outputs = _write_summary(output_root, checks, refresh)
    required_checks = [item for item in checks if item.get("severity") != "optional"]
    return {
        "ok": all(item["ok"] for item in required_checks),
        "passed_count": sum(1 for item in checks if item["ok"]),
        "check_count": len(checks),
        "required_passed_count": sum(1 for item in required_checks if item["ok"]),
        "required_check_count": len(required_checks),
        "outputs": outputs,
        "checks": [{"name": item["name"], "ok": item["ok"], "severity": item.get("severity", "required")} for item in checks],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the final job-ready release check for the FBBP control-plane package.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--require-docker-live", action="store_true")
    args = parser.parse_args()
    result = run_final_release_check(output_root=Path(args.output_root).resolve(), require_docker_live=args.require_docker_live)
    print(json.dumps(result, ensure_ascii=False))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
