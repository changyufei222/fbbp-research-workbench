from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SCRIPTS_ROOT.parent
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from deerflow_embedded_runner import run_embedded_deerflow
from formal_run_lib import build_run_id, load_yaml_config, resolve_runner_settings
from control_plane.minimind_adapter import run_candidate_query_compile
from control_plane.public_lookup import run_public_lookup


DEFAULT_BACKEND_ROOT = REPO_ROOT.parent / "upstream-deerflow" / "backend"
PRIVATE_RAG_BOOTSTRAP_SCRIPT = SCRIPTS_ROOT / "start_wsl_pgvector.ps1"
POSTGRES_BRIDGE_REPAIR_SCRIPT = SCRIPTS_ROOT / "repair_wsl_postgres_bridge.ps1"
FORMAL_CASE_WRAPPER = SCRIPTS_ROOT / "run_fbbp_formal_case.ps1"
BATCH_EVAL_WRAPPER = SCRIPTS_ROOT / "run_fbbp_formal_batch.ps1"
FORMAL_ENV_KEYS = (
    "OPENAI_API_KEY",
    "BASE_URL",
    "OPENAI_BASE_URL",
    "OPENAI_API_BASE",
    "LLM_MODEL",
)


def _candidate_python_paths() -> list[Path]:
    return [
        REPO_ROOT.parent / "fbbp-mcp-rag-server" / ".venv" / "Scripts" / "python.exe",
        REPO_ROOT.parent / "upstream-deerflow" / "backend" / ".venv" / "Scripts" / "python.exe",
        Path(sys.executable),
    ]


def _select_python_for_query_private_rag() -> str:
    for candidate in _candidate_python_paths():
        if candidate.exists():
            return str(candidate)
    return sys.executable


def _write_child_output(run_dir: Path, name: str, payload: Any) -> str:
    child_dir = run_dir / "children"
    child_dir.mkdir(parents=True, exist_ok=True)
    path = child_dir / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    payload: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        payload[key.strip()] = value.strip().strip('"').strip("'")
    return payload


def _normalize_openai_base_env(env: dict[str, str]) -> dict[str, str]:
    resolved = (
        env.get("OPENAI_BASE_URL")
        or env.get("OPENAI_API_BASE")
        or env.get("BASE_URL")
        or ""
    ).strip()
    if resolved:
        env["OPENAI_BASE_URL"] = resolved
        env["OPENAI_API_BASE"] = resolved
        env["BASE_URL"] = resolved
    return env


def _normalize_formal_model(env: dict[str, str]) -> dict[str, str]:
    aliases = {
        "DeepSeek-V3.2": "deepseek-v3.2",
    }
    raw_model = str(env.get("LLM_MODEL") or "").strip()
    if raw_model in aliases:
        env["LLM_MODEL"] = aliases[raw_model]
    return env


def _formal_runtime_env() -> dict[str, str]:
    env = dict(os.environ)
    for env_path in (
        REPO_ROOT.parent / "llm-rag-knowledge-base" / ".env",
        REPO_ROOT.parent / "fbbp-mcp-rag-server" / ".env",
    ):
        values = _read_env_file(env_path)
        for key in FORMAL_ENV_KEYS:
            if env.get(key):
                continue
            value = values.get(key)
            if value:
                env[key] = value
    return _normalize_formal_model(_normalize_openai_base_env(env))


def _apply_case_runtime_env(env: dict[str, str], case_config: dict[str, Any]) -> dict[str, str]:
    dataset_version = str(case_config.get("dataset_version") or "").strip()
    runtime_profile = str(case_config.get("runtime_profile") or "").strip()
    if dataset_version:
        env["FBBP_FORMAL_DATASET_VERSION"] = dataset_version
        env["FBTP_FORMAL_DATASET_VERSION"] = dataset_version
    if runtime_profile:
        env["FBBP_FORMAL_RUNTIME_PROFILE"] = runtime_profile
        env["FBTP_FORMAL_RUNTIME_PROFILE"] = runtime_profile
    env.setdefault("FBBP_PROJECT_ROOT", str(REPO_ROOT.parent))
    env.setdefault("FBTP_PROJECT_ROOT", str(REPO_ROOT.parent))
    return env


def _uses_source_provenance_preflight(case_config: dict[str, Any]) -> bool:
    settings = resolve_runner_settings(case_config)
    return bool((settings.get("preflight_source_provenance") or {}).get("enabled"))


def _run_command_capture(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout_seconds: int | None = None,
) -> tuple[int, str, str]:
    stdout_tmp = NamedTemporaryFile("w", encoding="utf-8", delete=False)
    stderr_tmp = NamedTemporaryFile("w", encoding="utf-8", delete=False)
    stdout_tmp.close()
    stderr_tmp.close()
    stdout_path = Path(stdout_tmp.name)
    stderr_path = Path(stderr_tmp.name)
    try:
        with stdout_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open(
            "w",
            encoding="utf-8",
        ) as stderr_handle:
            proc = subprocess.run(
                command,
                stdout=stdout_handle,
                stderr=stderr_handle,
                cwd=REPO_ROOT,
                check=False,
                env=env,
                timeout=timeout_seconds,
                text=True,
            )
        stdout = stdout_path.read_text(encoding="utf-8")
        stderr = stderr_path.read_text(encoding="utf-8")
        return proc.returncode, stdout, stderr
    finally:
        for path in (stdout_path, stderr_path):
            try:
                path.unlink(missing_ok=True)
            except PermissionError:
                pass


def _run_python_json(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    try:
        returncode, stdout, stderr = _run_command_capture(
            command,
            env=env,
            timeout_seconds=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"command timed out after {timeout_seconds} seconds: {' '.join(command)}"
        ) from exc
    if returncode != 0:
        raise RuntimeError((stderr or stdout).strip() or f"command failed: {' '.join(command)}")
    stdout = stdout.strip()
    if not stdout:
        return {}
    return json.loads(stdout)


def _run_powershell_script(
    script_path: Path,
    *,
    env: dict[str, str] | None = None,
    timeout_seconds: int | None = None,
) -> None:
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
    ]
    try:
        returncode, stdout, stderr = _run_command_capture(
            command,
            env=env,
            timeout_seconds=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"bootstrap script timed out after {timeout_seconds} seconds: {script_path}"
        ) from exc
    if returncode != 0:
        raise RuntimeError((stderr or stdout).strip() or f"bootstrap script failed: {script_path}")


def _run_powershell_json(
    arguments: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        *arguments,
    ]
    try:
        returncode, stdout, stderr = _run_command_capture(
            command,
            env=env,
            timeout_seconds=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"powershell command timed out after {timeout_seconds} seconds: {' '.join(command)}"
        ) from exc
    if returncode != 0:
        raise RuntimeError((stderr or stdout).strip() or f"powershell command failed: {' '.join(command)}")
    stdout = stdout.strip()
    if not stdout:
        return {}
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    return json.loads(lines[-1])


def _private_rag_env(request: dict[str, Any]) -> dict[str, str]:
    env = dict(os.environ)
    env["FBBP_LIVE_QUERY_PREFER_LOCAL"] = "1"
    env["FBTP_LIVE_QUERY_PREFER_LOCAL"] = "1"
    env["EMBEDDING_PROVIDER"] = "local_hash"
    env["RERANKER_ENABLED"] = "0"
    env["ANSWER_MODE"] = "extractive"
    env["FBBP_MCP_DEFAULT_ANSWER_MODE"] = "extractive"
    env["FBTP_MCP_DEFAULT_ANSWER_MODE"] = "extractive"
    if request.get("answer_mode"):
        env["ANSWER_MODE"] = str(request["answer_mode"])
    return env


def _ensure_private_rag_runtime(env: dict[str, str]) -> None:
    if PRIVATE_RAG_BOOTSTRAP_SCRIPT.exists():
        try:
            _run_powershell_script(PRIVATE_RAG_BOOTSTRAP_SCRIPT, env=env, timeout_seconds=180)
        except RuntimeError as exc:
            message = str(exc)
            bridge_failure = (
                "PostgreSQL is still not query-ready" in message
                or "connection timeout expired" in message
                or "localhost:5432" in message
            )
            if not bridge_failure or not POSTGRES_BRIDGE_REPAIR_SCRIPT.exists():
                raise
            _run_powershell_script(POSTGRES_BRIDGE_REPAIR_SCRIPT, env=env, timeout_seconds=240)


def _private_rag(request: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    if not request.get("query"):
        raise ValueError("private_rag execution requires --query")
    env = _private_rag_env(request)
    _ensure_private_rag_runtime(env)
    answer_mode = str(request.get("answer_mode") or env.get("ANSWER_MODE") or "extractive")
    command = [
        _select_python_for_query_private_rag(),
        str(SCRIPTS_ROOT / "query_private_rag.py"),
        "--query",
        str(request["query"]),
        "--top-k",
        str(request.get("top_k") or 5),
        "--answer-mode",
        answer_mode,
    ]
    if request.get("record_type"):
        command.extend(["--record-type", str(request["record_type"])])
    for item in request.get("filters", []):
        command.extend(["--filter", str(item)])
    if request.get("include_evidence"):
        command.append("--include-evidence")
    if not request.get("include_answer", True):
        command.append("--no-include-answer")

    started = time.perf_counter()
    payload = _run_python_json(command, env=env, timeout_seconds=180)
    elapsed = round((time.perf_counter() - started) * 1000, 2)
    artifact = _write_child_output(run_dir, "private_rag_output.json", payload)
    result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
    diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), dict) else {}
    diagnostics.setdefault("control_plane_profile", "interactive_fast_local_hash")
    diagnostics.setdefault("control_plane_bootstrap", "start_wsl_pgvector.ps1")
    summary = {
        "answer_preview": str((result or {}).get("answer") or "")[:200] if isinstance(result, dict) else None,
        "result_count": (result or {}).get("result_count") if isinstance(result, dict) else None,
        "diagnostics": diagnostics,
    }
    return {
        "status": "succeeded" if payload.get("ok", True) else "failed",
        "executor": {"name": "query_private_rag.py", "mode": "subprocess"},
        "timings_ms": {"execution": elapsed},
        "artifacts": {"primary_output_json": artifact},
        "child_runs": [],
        "result_summary": summary,
        "errors": [] if payload.get("ok", True) else [payload.get("error") or {"message": "private_rag failed"}],
    }


def _formal_case(request: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    case_path = request.get("case_path")
    if not case_path:
        raise ValueError("formal_case execution requires --case-path")
    started = time.perf_counter()
    child_output_root = run_dir / "children" / "formal_case_runtime"
    case_config = load_yaml_config(Path(case_path).resolve())
    env = _apply_case_runtime_env(_formal_runtime_env(), case_config)
    if _uses_source_provenance_preflight(case_config):
        child_run_id = build_run_id(str(case_config["case_id"]), datetime.now())
        child_run_dir = child_output_root / child_run_id
        payload = _run_python_json(
            [
                sys.executable,
                str(SCRIPTS_ROOT / "run_fbbp_formal_case.py"),
                "--case-path",
                str(case_path),
                "--run-dir",
                str(child_run_dir),
            ],
            env=env,
            timeout_seconds=180,
        )
        executor = {"name": "run_fbbp_formal_case.py", "mode": "direct_python_source_preflight"}
    else:
        payload = _run_powershell_json(
            [
                "-File",
                str(FORMAL_CASE_WRAPPER),
                "-CasePath",
                str(case_path),
                "-OutputRoot",
                str(child_output_root),
            ],
            env=env,
            timeout_seconds=420,
        )
        executor = {"name": "run_fbbp_formal_case.ps1", "mode": "powershell_wrapper"}
    elapsed = round((time.perf_counter() - started) * 1000, 2)
    artifact = _write_child_output(run_dir, "formal_case_output.json", payload)
    child_runs = [
        {
            "child_run_id": payload.get("run_id"),
            "route": "formal_case",
            "status": payload.get("status"),
            "artifact_dir": payload.get("run_dir"),
        }
    ]
    return {
        "status": str(payload.get("status") or "failed"),
        "executor": executor,
        "timings_ms": {"execution": elapsed},
        "artifacts": {"primary_output_json": artifact},
        "child_runs": child_runs,
        "result_summary": payload,
        "errors": [] if payload.get("status") == "succeeded" else [{"message": "formal_case failed"}],
    }


def _batch_eval(request: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    batch_path = request.get("batch_path")
    if not batch_path:
        raise ValueError("batch_eval execution requires --batch-path")
    started = time.perf_counter()
    child_output_root = run_dir / "children" / "batch_eval_runtime"
    env = _formal_runtime_env()
    payload = _run_powershell_json(
        [
            "-File",
            str(BATCH_EVAL_WRAPPER),
            "-BatchPath",
            str(batch_path),
            "-OutputRoot",
            str(child_output_root),
        ],
        env=env,
        timeout_seconds=1800,
    )
    elapsed = round((time.perf_counter() - started) * 1000, 2)
    artifact = _write_child_output(run_dir, "batch_eval_output.json", payload)
    child_runs = [
        {
            "child_run_id": payload.get("batch_id"),
            "route": "batch_eval",
            "status": payload.get("status"),
            "artifact_dir": payload.get("batch_dir"),
        }
    ]
    return {
        "status": str(payload.get("status") or "failed"),
        "executor": {"name": "run_fbbp_formal_batch.ps1", "mode": "powershell_wrapper"},
        "timings_ms": {"execution": elapsed},
        "artifacts": {"primary_output_json": artifact},
        "child_runs": child_runs,
        "result_summary": payload,
        "errors": [] if payload.get("status") in {"succeeded", "partial"} else [{"message": "batch_eval failed"}],
    }


def _report_generation(request: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    report_json = request.get("report_json")
    if not report_json and request.get("run_dir"):
        candidate = Path(str(request["run_dir"])) / "report.json"
        if candidate.exists():
            report_json = str(candidate.resolve())
    if not report_json:
        raise ValueError("report_generation requires --report-json or a --run-dir containing report.json")

    report_payload = json.loads(Path(str(report_json)).read_text(encoding="utf-8"))
    artifact = _write_child_output(run_dir, "report_generation_output.json", report_payload)
    conclusions = report_payload.get("conclusions") if isinstance(report_payload.get("conclusions"), list) else []
    summary = {
        "title": report_payload.get("title"),
        "completion_mode": report_payload.get("completion_mode"),
        "conclusion_preview": str(conclusions[0])[:200] if conclusions else None,
    }
    return {
        "status": "succeeded",
        "executor": {"name": "report_json_loader", "mode": "local_file"},
        "timings_ms": {"execution": 0.0},
        "artifacts": {"primary_output_json": artifact, "report_json": report_json},
        "child_runs": [],
        "result_summary": summary,
        "errors": [],
    }


def _public_lookup(request: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    query = str(request.get("query") or "").strip()
    if not query:
        raise ValueError("public_lookup execution requires --query")
    started = time.perf_counter()
    payload = run_public_lookup(query, top_k=int(request.get("top_k") or 5))
    elapsed = round((time.perf_counter() - started) * 1000, 2)
    artifact = _write_child_output(run_dir, "public_lookup_output.json", payload)
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    tool_calls = payload.get("tool_calls") if isinstance(payload.get("tool_calls"), list) else []
    child_runs = [
        {
            "child_run_id": f"public_lookup:{index + 1}:{call.get('tool')}",
            "route": "public_lookup",
            "status": "succeeded" if call.get("ok") else "failed",
            "tool": call.get("tool"),
            "project": "fbbp-mcp-rag-server",
            "latency_ms": call.get("latency_ms"),
        }
        for index, call in enumerate(tool_calls)
    ]
    if payload.get("ok"):
        status = "succeeded"
        errors: list[dict[str, Any]] = []
    elif any(call.get("ok") for call in tool_calls):
        status = "partial"
        errors = [call.get("error") or {"message": "public lookup call failed"} for call in tool_calls if not call.get("ok")]
    else:
        status = "failed"
        errors = [call.get("error") or {"message": "public lookup failed"} for call in tool_calls] or [{"message": "public lookup produced no tool calls"}]
    return {
        "status": status,
        "executor": {"name": "public_lookup.py", "mode": "direct_mcp_tool_plane"},
        "timings_ms": {"execution": elapsed},
        "artifacts": {"primary_output_json": artifact},
        "child_runs": child_runs,
        "result_summary": {
            **summary,
            "targets": payload.get("targets"),
            "article_preview": (payload.get("articles") or [{}])[0] if payload.get("articles") else None,
            "entry_preview": (payload.get("entries") or [{}])[0] if payload.get("entries") else None,
        },
        "errors": errors,
    }


def _fallback_general(request: dict[str, Any], run_dir: Path, *, proxy_name: str = "deerflow_embedded_runner.py") -> dict[str, Any]:
    prompt = str(request.get("query") or "").strip()
    if not prompt:
        raise ValueError("fallback_general execution requires --query")
    started = time.perf_counter()
    state_file = run_dir / "children" / "fallback_general_state.json"
    payload = run_embedded_deerflow(
        backend_root=DEFAULT_BACKEND_ROOT,
        prompt=prompt,
        thread_id=str(request.get("thread_id") or run_dir.name),
        recursion_limit=8,
        max_seconds=180,
        runner_settings=None,
        state_file=state_file,
    )
    elapsed = round((time.perf_counter() - started) * 1000, 2)
    artifact = _write_child_output(run_dir, "fallback_general_output.json", payload)
    summary = {
        "answer_preview": str(payload.get("answer") or "")[:200],
        "completion_reason": payload.get("completion_reason"),
        "partial": bool(payload.get("partial")),
    }
    return {
        "status": "succeeded",
        "executor": {"name": proxy_name, "mode": "embedded"},
        "timings_ms": {"execution": elapsed},
        "artifacts": {
            "primary_output_json": artifact,
            "state_file": str(state_file),
        },
        "child_runs": [],
        "result_summary": summary,
        "errors": [],
    }


def _apply_secondary_capabilities(
    result: dict[str, Any],
    request: dict[str, Any],
    route_decision: dict[str, Any],
    run_dir: Path,
) -> dict[str, Any]:
    capabilities = [str(item) for item in route_decision.get("secondary_capabilities", [])]
    if "candidate_query_compile" not in capabilities:
        return result
    query = str(request.get("query") or "").strip()
    if not query:
        return result
    payload = run_candidate_query_compile(query, top_k=int(request.get("top_k") or 5))
    artifact = _write_child_output(run_dir, "candidate_query_compile_output.json", payload)
    result.setdefault("artifacts", {})["candidate_query_compile_output_json"] = artifact
    result.setdefault("child_runs", []).append(
        {
            "child_run_id": "secondary:candidate_query_compile",
            "route": str(route_decision.get("primary_route") or ""),
            "status": "succeeded" if payload.get("ok") else "review",
            "capability": "candidate_query_compile",
            "project": "minimind-fbtp-lab",
            "artifact_path": artifact,
            "latency_ms": payload.get("latency_ms"),
        }
    )
    summary = result.setdefault("result_summary", {})
    secondary = summary.setdefault("secondary_capabilities", {})
    execution = payload.get("execution") if isinstance(payload.get("execution"), dict) else {}
    metadata = execution.get("metadata") if isinstance(execution.get("metadata"), dict) else {}
    trace = payload.get("validator_trace") if isinstance(payload.get("validator_trace"), dict) else {}
    secondary["candidate_query_compile"] = {
        "ok": payload.get("ok"),
        "mode": payload.get("mode"),
        "schema_ok": trace.get("schema_ok"),
        "errors": trace.get("errors", []),
        "repairs": trace.get("repairs", []),
        "filtered_count": metadata.get("filtered_count"),
        "returned_count": metadata.get("returned_count"),
        "artifact": artifact,
    }
    return result


def _execute_primary_route(request: dict[str, Any], route_decision: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    route = str(route_decision["primary_route"])
    if route == "private_rag":
        return _private_rag(request, run_dir)
    if route == "formal_case":
        return _formal_case(request, run_dir)
    if route == "batch_eval":
        return _batch_eval(request, run_dir)
    if route == "report_generation":
        return _report_generation(request, run_dir)
    if route == "public_lookup":
        return _public_lookup(request, run_dir)
    return _fallback_general(request, run_dir)


def execute_route(request: dict[str, Any], route_decision: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    result = _execute_primary_route(request, route_decision, run_dir)
    return _apply_secondary_capabilities(result, request, route_decision, run_dir)
