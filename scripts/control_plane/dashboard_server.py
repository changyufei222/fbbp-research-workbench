from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from control_plane.final_release_check import run_final_release_check


REPO_ROOT = Path(__file__).resolve().parents[2]
PORTFOLIO_ROOT = REPO_ROOT / "reports" / "control_plane_portfolio_dashboard" / "latest"
FINAL_RELEASE_ROOT = REPO_ROOT / "runs" / "control_plane" / "final_release" / "latest"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _guess_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def _json_response(payload: Any, *, status: int = 200) -> tuple[int, str, bytes]:
    return status, "application/json; charset=utf-8", json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def _file_response(path: Path) -> tuple[int, str, bytes]:
    if not path.exists() or not path.is_file():
        return _json_response({"error": "not found", "path": str(path)}, status=404)
    return 200, _guess_type(path), path.read_bytes()


def _resolve_static_path(request_path: str) -> Path:
    clean = request_path.lstrip("/") or "index.html"
    resolved = (PORTFOLIO_ROOT / clean).resolve()
    portfolio_root = PORTFOLIO_ROOT.resolve()
    if resolved != portfolio_root and portfolio_root not in resolved.parents:
        return PORTFOLIO_ROOT / "index.html"
    if resolved.is_dir():
        return resolved / "index.html"
    return resolved


def _service_snapshot(base_url: str) -> dict[str, Any]:
    portfolio_summary = _read_json(PORTFOLIO_ROOT / "portfolio_dashboard_summary.json")
    semantic_memory = _read_json(PORTFOLIO_ROOT / "semantic_memory.json")
    final_release = _read_json(FINAL_RELEASE_ROOT / "final_release_summary.json")
    return {
        "service": {
            "mode": "live_local_control_console",
            "base_url": base_url,
            "health_url": f"{base_url}/health",
            "snapshot_url": f"{base_url}/api/snapshot",
            "semantic_memory_url": f"{base_url}/api/semantic-memory",
            "rebuild_url": f"{base_url}/api/rebuild",
        },
        "portfolio_summary_exists": bool(portfolio_summary),
        "semantic_memory_exists": bool(semantic_memory),
        "final_release_exists": bool(final_release),
        "portfolio_summary_path": str(PORTFOLIO_ROOT / "portfolio_dashboard_summary.json"),
        "semantic_memory_path": str(PORTFOLIO_ROOT / "semantic_memory.json"),
        "final_release_path": str(FINAL_RELEASE_ROOT / "final_release_summary.json"),
        "generated_at_utc": portfolio_summary.get("generated_at_utc")
        or semantic_memory.get("updated_at_utc")
        or final_release.get("created_at_utc"),
    }


def _portfolio_payload(base_url: str) -> dict[str, Any]:
    payload = _read_json(PORTFOLIO_ROOT / "portfolio_dashboard_summary.json")
    payload.setdefault("service_endpoints", {})
    payload["service_endpoints"].update(
        {
            "health": f"{base_url}/health",
            "snapshot": f"{base_url}/api/snapshot",
            "semantic_memory": f"{base_url}/api/semantic-memory",
            "rebuild": f"{base_url}/api/rebuild",
        }
    )
    payload["mode"] = "live_local_control_console"
    return payload


def _semantic_memory_payload(base_url: str) -> dict[str, Any]:
    payload = _read_json(PORTFOLIO_ROOT / "semantic_memory.json")
    payload.setdefault("service_endpoints", {})
    payload["service_endpoints"].update(
        {
            "health": f"{base_url}/health",
            "snapshot": f"{base_url}/api/snapshot",
            "semantic_memory": f"{base_url}/api/semantic-memory",
            "rebuild": f"{base_url}/api/rebuild",
        }
    )
    payload["mode"] = "live_local_control_console"
    return payload


def handle_request(method: str, path: str, *, base_url: str) -> tuple[int, str, bytes]:
    parsed = urlparse(path)
    clean_path = parsed.path.rstrip("/") or "/"

    if method == "GET" and clean_path == "/health":
        return _json_response(_service_snapshot(base_url))
    if method == "GET" and clean_path == "/api/snapshot":
        return _json_response(_portfolio_payload(base_url))
    if method == "GET" and clean_path == "/api/semantic-memory":
        return _json_response(_semantic_memory_payload(base_url))
    if method == "GET" and clean_path == "/api/final-release":
        return _json_response(_read_json(FINAL_RELEASE_ROOT / "final_release_summary.json"))
    if method == "POST" and clean_path == "/api/rebuild":
        result = run_final_release_check(output_root=FINAL_RELEASE_ROOT, require_docker_live=False)
        return _json_response(
            {
                "ok": result.get("ok"),
                "passed_count": result.get("passed_count"),
                "check_count": result.get("check_count"),
                "required_passed_count": result.get("required_passed_count"),
                "required_check_count": result.get("required_check_count"),
                "outputs": result.get("outputs"),
                "snapshot": _portfolio_payload(base_url),
            }
        )
    return _file_response(_resolve_static_path(clean_path))


class DashboardServerHandler(BaseHTTPRequestHandler):
    server_version = "FBBPDashboardServer/0.1"

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        status, content_type, body = handle_request("GET", self.path, base_url=self.server.base_url)
        self._send(status, content_type, body)

    def do_POST(self) -> None:  # noqa: N802
        status, content_type, body = handle_request("POST", self.path, base_url=self.server.base_url)
        self._send(status, content_type, body)

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write("dashboard_server: " + (format % args) + "\n")


class DashboardServer(ThreadingHTTPServer):
    base_url: str


def run_server(host: str, port: int) -> None:
    server = DashboardServer((host, port), DashboardServerHandler)
    server.base_url = f"http://{host}:{port}"
    print(json.dumps({"status": "listening", "host": host, "port": port, "portfolio_root": str(PORTFOLIO_ROOT)}, ensure_ascii=False))
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the live FBBP portfolio dashboard and rebuild APIs.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8088)
    args = parser.parse_args()
    run_server(args.host, args.port)


if __name__ == "__main__":
    main()
