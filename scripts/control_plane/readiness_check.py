from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from control_plane.eval_dashboard import collect_run_records, write_dashboard
from control_plane.minimind_adapter import run_candidate_query_compile
from control_plane.production_hardening_check import run_hardening_check


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = REPO_ROOT.parent
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "runs" / "control_plane" / "readiness" / "latest"


def _workspace_env() -> dict[str, str]:
    env = dict(os.environ)
    temp_root = WORKSPACE_ROOT / ".codex_tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    env["TEMP"] = str(temp_root)
    env["TMP"] = str(temp_root)
    env.setdefault("FBBP_SCI_RETRY_ATTEMPTS", "1")
    env.setdefault("FBBP_SCI_MIN_INTERVAL_SECONDS", "0")
    return env


def _json_from_stdout(stdout: str) -> dict[str, Any]:
    for line in reversed([item.strip() for item in stdout.splitlines() if item.strip()]):
        if line.startswith("{") and line.endswith("}"):
            return json.loads(line)
    return {}


def _run_command(name: str, command: list[str], *, timeout_seconds: int = 180) -> dict[str, Any]:
    started = datetime.now(UTC)
    proc = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=_workspace_env(),
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_seconds,
    )
    elapsed_ms = round((datetime.now(UTC) - started).total_seconds() * 1000, 2)
    payload = _json_from_stdout(proc.stdout)
    return {
        "name": name,
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "elapsed_ms": elapsed_ms,
        "payload": payload,
        "stdout_tail": proc.stdout.strip().splitlines()[-5:],
        "stderr_tail": proc.stderr.strip().splitlines()[-5:],
    }


def _repair_postgres_bridge() -> dict[str, Any]:
    return _run_command(
        "postgres_bridge",
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(REPO_ROOT / "scripts" / "repair_wsl_postgres_bridge.ps1"),
            "-Json",
        ],
        timeout_seconds=240,
    )


def _a2a_live_e2e(output_root: Path) -> dict[str, Any]:
    return _run_command(
        "a2a_live_e2e",
        [
            sys.executable,
            str(SCRIPTS_ROOT / "control_plane" / "live_e2e.py"),
            "--output-root",
            str(output_root / "live_e2e"),
        ],
        timeout_seconds=180,
    )


def _private_rag_live(output_root: Path) -> dict[str, Any]:
    return _run_command(
        "private_rag_live",
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "run_fbbp_control_plane.py"),
            "--force-primary-route",
            "private_rag",
            "--query",
            "knottin scaffold landscape",
            "--top-k",
            "2",
            "--answer-mode",
            "extractive",
            "--output-dir",
            str(output_root / "private_rag_live"),
        ],
        timeout_seconds=240,
    )


def _public_lookup_live(output_root: Path) -> dict[str, Any]:
    return _run_command(
        "public_lookup_live",
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "run_fbbp_control_plane.py"),
            "--force-primary-route",
            "public_lookup",
            "--query",
            "knottin peptide inhibitor",
            "--top-k",
            "2",
            "--output-dir",
            str(output_root / "public_lookup_live"),
        ],
        timeout_seconds=180,
    )


def _minimind_secondary() -> dict[str, Any]:
    started = datetime.now(UTC)
    try:
        payload = run_candidate_query_compile("筛选 knottin 有实验亲和力 前 2", top_k=2)
        ok = bool(payload.get("ok"))
        error = None
    except Exception as exc:
        payload = {}
        ok = False
        error = {"code": type(exc).__name__, "message": str(exc).splitlines()[0][:500]}
    return {
        "name": "minimind_secondary",
        "ok": ok,
        "returncode": 0 if ok else 1,
        "elapsed_ms": round((datetime.now(UTC) - started).total_seconds() * 1000, 2),
        "payload": {
            "ok": payload.get("ok"),
            "project": payload.get("project"),
            "schema_ok": (payload.get("validator_trace") or {}).get("schema_ok") if isinstance(payload.get("validator_trace"), dict) else None,
            "filtered_count": ((payload.get("execution") or {}).get("metadata") or {}).get("filtered_count")
            if isinstance(payload.get("execution"), dict)
            else None,
            "returned_count": ((payload.get("execution") or {}).get("metadata") or {}).get("returned_count")
            if isinstance(payload.get("execution"), dict)
            else None,
            "error": error,
        },
        "stdout_tail": [],
        "stderr_tail": [],
    }


def _eval_dashboard() -> dict[str, Any]:
    started = datetime.now(UTC)
    try:
        output_root = WORKSPACE_ROOT / "llm-eval-benchmark" / "reports" / "control_plane_dashboard" / "latest"
        records = collect_run_records(REPO_ROOT / "runs" / "control_plane")
        outputs = write_dashboard(records, output_root)
        payload = {"record_count": len(records), "outputs": outputs}
        ok = True
        error = None
    except Exception as exc:
        payload = {}
        ok = False
        error = {"code": type(exc).__name__, "message": str(exc).splitlines()[0][:500]}
    return {
        "name": "eval_dashboard",
        "ok": ok,
        "returncode": 0 if ok else 1,
        "elapsed_ms": round((datetime.now(UTC) - started).total_seconds() * 1000, 2),
        "payload": payload if ok else {"error": error},
        "stdout_tail": [],
        "stderr_tail": [],
    }


def _production_hardening(output_root: Path) -> dict[str, Any]:
    started = datetime.now(UTC)
    try:
        payload = run_hardening_check(output_root=output_root / "production_hardening")
        ok = bool(payload.get("ok"))
        error = None
    except Exception as exc:
        payload = {}
        ok = False
        error = {"code": type(exc).__name__, "message": str(exc).splitlines()[0][:500]}
    return {
        "name": "production_hardening",
        "ok": ok,
        "returncode": 0 if ok else 1,
        "elapsed_ms": round((datetime.now(UTC) - started).total_seconds() * 1000, 2),
        "payload": payload if ok else {"error": error},
        "stdout_tail": [],
        "stderr_tail": [],
    }


def _write_outputs(output_root: Path, checks: list[dict[str, Any]]) -> dict[str, str]:
    output_root.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema_version": "fbbp.control_plane.readiness.v1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "ok": all(item["ok"] for item in checks),
        "check_count": len(checks),
        "passed_count": sum(1 for item in checks if item["ok"]),
        "failed_count": sum(1 for item in checks if not item["ok"]),
        "checks": checks,
    }
    summary_path = output_root / "readiness_summary.json"
    md_path = output_root / "readiness_summary.md"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Control Plane Readiness",
        "",
        f"- ok: {summary['ok']}",
        f"- checks: {summary['passed_count']}/{summary['check_count']}",
        "",
        "## Checks",
        "",
    ]
    for check in checks:
        mark = "PASS" if check["ok"] else "FAIL"
        lines.append(f"- {mark} {check['name']} ({check['elapsed_ms']} ms)")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"summary_json": str(summary_path), "summary_md": str(md_path)}


def run_readiness(
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    include_postgres_bridge: bool = True,
    include_private_rag: bool = False,
    include_public_lookup: bool = False,
    include_hardening: bool = False,
) -> dict[str, Any]:
    checks = []
    if include_postgres_bridge:
        checks.append(_repair_postgres_bridge())
    checks.extend(
        [
            _a2a_live_e2e(output_root),
            _minimind_secondary(),
        ]
    )
    if include_private_rag:
        checks.append(_private_rag_live(output_root))
    if include_public_lookup:
        checks.append(_public_lookup_live(output_root))
    checks.append(_eval_dashboard())
    if include_hardening:
        checks.append(_production_hardening(output_root))
    outputs = _write_outputs(output_root, checks)
    return {
        "ok": all(item["ok"] for item in checks),
        "passed_count": sum(1 for item in checks if item["ok"]),
        "check_count": len(checks),
        "outputs": outputs,
        "checks": [{"name": item["name"], "ok": item["ok"]} for item in checks],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run FBBP control-plane readiness checks.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--skip-postgres-bridge", action="store_true")
    parser.add_argument("--include-private-rag", action="store_true")
    parser.add_argument("--include-public-lookup", action="store_true")
    parser.add_argument("--include-hardening", action="store_true")
    args = parser.parse_args()
    result = run_readiness(
        output_root=Path(args.output_root).resolve(),
        include_postgres_bridge=not args.skip_postgres_bridge,
        include_private_rag=args.include_private_rag,
        include_public_lookup=args.include_public_lookup,
        include_hardening=args.include_hardening,
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
