from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import uuid4


SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from control_plane.a2a import A2A_SCHEMA_VERSION, CONTROL_PLANE_AGENT_ID, assert_valid_envelope
from control_plane.auth import auth_metadata, authenticate_headers
from control_plane.queue_backends import external_backend_available, iter_tasks as backend_iter_tasks
from control_plane.worker_queue import (
    cancel_task,
    claim_next_task,
    complete_task,
    create_task,
    fail_task,
    get_push_notification_config,
    get_task,
    list_task_events,
    load_worker_queue_config,
    queue_health,
    queue_root_from_config,
    set_push_notification_config,
    to_a2a_task,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
A2A_PROTOCOL_VERSION = "1.0"


def _json_response(payload: Any, status: int = 200) -> tuple[int, dict[str, str], bytes]:
    return (
        status,
        {"Content-Type": "application/a2a+json; charset=utf-8"},
        json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
    )


def _error_payload(message: str, *, code: int = -32603, data: Any | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        payload["data"] = data
    return payload


def agent_card(base_url: str = "http://127.0.0.1:8765", *, config: dict[str, Any] | None = None) -> dict[str, Any]:
    auth = auth_metadata(config)
    return {
        "name": "FBBP Research Workbench Control Plane",
        "description": "A2A gateway for FBBP private RAG, formal cases, batch evaluation, reports, and worker handoff.",
        "version": "0.1.0",
        "url": f"{base_url.rstrip('/')}/a2a",
        "supportedInterfaces": [
            {"url": f"{base_url.rstrip('/')}/a2a", "protocolBinding": "JSONRPC", "protocolVersion": A2A_PROTOCOL_VERSION},
            {"url": f"{base_url.rstrip('/')}/message:send", "protocolBinding": "HTTP+JSON", "protocolVersion": A2A_PROTOCOL_VERSION},
            {"url": f"{base_url.rstrip('/')}/message:stream", "protocolBinding": "SSE", "protocolVersion": A2A_PROTOCOL_VERSION},
        ],
        "capabilities": {
            "streaming": True,
            "pushNotifications": True,
            "stateTransitionHistory": True,
            "extendedAgentCard": False,
        },
        "securitySchemes": {
            "Bearer": {"type": "http", "scheme": "bearer"},
            "ApiKey": {"type": "apiKey", "in": "header", "name": "X-A2A-API-Key"},
        } if auth["enabled"] else {},
        "security": [{"Bearer": []}, {"ApiKey": []}] if auth["enabled"] else [],
        "x-fbbp-auth": auth,
        "defaultInputModes": ["application/json", "text/plain"],
        "defaultOutputModes": ["application/json", "text/plain"],
        "skills": [
            {
                "id": "fbbp-control-plane-routing",
                "name": "FBBP control-plane routing",
                "description": "Routes requests to private_rag, public_lookup, formal_case, batch_eval, report_generation, or fallback_general.",
                "tags": ["fbbp", "routing", "rag", "formal-case", "eval"],
                "inputModes": ["application/json", "text/plain"],
                "outputModes": ["application/json", "text/plain"],
            }
        ],
    }


def _message_text(message: dict[str, Any]) -> str:
    parts = message.get("parts") if isinstance(message.get("parts"), list) else []
    texts: list[str] = []
    for part in parts:
        if isinstance(part, dict) and part.get("text"):
            texts.append(str(part["text"]))
    return "\n".join(texts).strip()


def _build_gateway_envelope(params: dict[str, Any], *, task_id: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    message = params.get("message") if isinstance(params.get("message"), dict) else {}
    metadata = params.get("metadata") if isinstance(params.get("metadata"), dict) else {}
    query = _message_text(message) or str(params.get("query") or "")
    task_id = task_id or str(metadata.get("task_id") or f"task_{uuid4().hex[:16]}")
    trace_id = str(metadata.get("trace_id") or params.get("contextId") or f"trace_{uuid4().hex[:12]}")
    route = str(metadata.get("route") or metadata.get("primary_route") or "fallback_general")
    source_agent = str(metadata.get("source_agent") or "external-a2a-client")
    envelope = {
        "schema_version": A2A_SCHEMA_VERSION,
        "message_id": str(message.get("messageId") or f"msg_{uuid4().hex[:16]}"),
        "correlation_id": str(metadata.get("correlation_id") or f"a2ac_{uuid4().hex[:16]}"),
        "message_type": "child_run_request",
        "phase": "requested",
        "trace_id": trace_id,
        "parent_run_id": str(metadata.get("parent_run_id") or trace_id),
        "child_run_id": task_id,
        "hop_index": int(metadata.get("hop_index") or 1),
        "hop_path": [str(metadata.get("parent_run_id") or trace_id), task_id],
        "source_agent": source_agent,
        "target_agent": str(metadata.get("target_agent") or CONTROL_PLANE_AGENT_ID),
        "target_executor": metadata.get("target_executor"),
        "target_executor_mode": metadata.get("target_executor_mode"),
        "route": route,
        "status": "requested",
        "created_at_utc": metadata.get("created_at_utc"),
        "input_ref": metadata.get("input_ref"),
        "payload_ref": None,
        "artifact_ref": None,
        "error": None,
        "metadata": {
            "a2a_protocol_version": A2A_PROTOCOL_VERSION,
            "gateway": "fbbp-control-plane-a2a-gateway",
            "requested_mode": metadata.get("requested_mode"),
            "force_primary_route": route,
        },
    }
    assert_valid_envelope(envelope)
    input_payload = {
        "query": query,
        "message": message,
        "configuration": params.get("configuration") or {},
        "metadata": metadata,
    }
    return envelope, input_payload


def submit_message(params: dict[str, Any], *, queue_root: Path | None = None, config: dict[str, Any] | None = None) -> dict[str, Any]:
    envelope, input_payload = _build_gateway_envelope(params)
    task = create_task(envelope=envelope, input_payload=input_payload, queue_root=queue_root, config=config)
    return {"task": to_a2a_task(task)}


def _stream_event(event_name: str, payload: dict[str, Any]) -> str:
    return f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def build_stream_events(task: dict[str, Any], *, request_id: Any = None, final: bool = False) -> list[str]:
    a2a_task = to_a2a_task(task)
    status_event = {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "id": task["task_id"],
            "status": a2a_task["status"],
            "final": final or a2a_task["status"]["state"] in {"TASK_STATE_COMPLETED", "TASK_STATE_FAILED", "TASK_STATE_CANCELED", "TASK_STATE_REJECTED"},
            "metadata": a2a_task.get("metadata", {}),
        },
    }
    events = [_stream_event("task", {"jsonrpc": "2.0", "id": request_id, "result": a2a_task})]
    events.append(_stream_event("status", status_event))
    for artifact in a2a_task.get("artifacts", []):
        events.append(
            _stream_event(
                "artifact",
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "id": task["task_id"],
                        "artifact": artifact,
                        "metadata": a2a_task.get("metadata", {}),
                    },
                },
            )
        )
    return events


def handle_jsonrpc(payload: dict[str, Any], *, queue_root: Path | None = None, config: dict[str, Any] | None = None) -> dict[str, Any]:
    request_id = payload.get("id")
    method = str(payload.get("method") or "")
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    try:
        if payload.get("jsonrpc") != "2.0":
            raise ValueError("jsonrpc must be 2.0")
        if method in {"message/send", "SendMessage", "message/stream"}:
            result = submit_message(params, queue_root=queue_root, config=config)["task"]
        elif method in {"tasks/get", "GetTask"}:
            task_id = str(params.get("id") or params.get("taskId") or "")
            task = get_task(task_id, queue_root=queue_root, config=config)
            if not task:
                return {"jsonrpc": "2.0", "id": request_id, "error": _error_payload("Task not found", code=-32001, data={"task_id": task_id})}
            result = to_a2a_task(task)
        elif method in {"tasks/cancel", "CancelTask"}:
            task = cancel_task(str(params.get("id") or params.get("taskId") or ""), queue_root=queue_root, config=config)
            result = to_a2a_task(task)
        elif method in {"tasks/resubscribe", "TaskResubscription"}:
            task_id = str(params.get("id") or params.get("taskId") or "")
            task = get_task(task_id, queue_root=queue_root, config=config)
            if not task:
                return {"jsonrpc": "2.0", "id": request_id, "error": _error_payload("Task not found", code=-32001, data={"task_id": task_id})}
            result = {"events": build_stream_events(task, request_id=request_id)}
        elif method in {"tasks/pushNotificationConfig/set", "SetTaskPushNotificationConfig"}:
            task_id = str(params.get("id") or params.get("taskId") or "")
            push_config = params.get("pushNotificationConfig") or params.get("pushNotification") or params.get("config")
            if not isinstance(push_config, dict):
                raise ValueError("pushNotificationConfig must be an object")
            task = set_push_notification_config(task_id, push_config, queue_root=queue_root, config=config)
            result = {"task": to_a2a_task(task), "pushNotificationConfig": push_config}
        elif method in {"tasks/pushNotificationConfig/get", "GetTaskPushNotificationConfig"}:
            task_id = str(params.get("id") or params.get("taskId") or "")
            push_config = get_push_notification_config(task_id, queue_root=queue_root, config=config)
            result = {"id": task_id, "pushNotificationConfig": push_config}
        elif method in {"tasks/list", "ListTasks"}:
            result = queue_health(queue_root=queue_root, config=config)
        else:
            return {"jsonrpc": "2.0", "id": request_id, "error": _error_payload("Method not found", code=-32601, data={"method": method})}
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except Exception as exc:
        return {"jsonrpc": "2.0", "id": request_id, "error": _error_payload(str(exc), code=-32603)}


def handle_rest(method: str, path: str, body: dict[str, Any] | None, *, queue_root: Path | None = None, config: dict[str, Any] | None = None, base_url: str = "http://127.0.0.1:8765") -> tuple[int, dict[str, Any]]:
    parsed = urlparse(path)
    clean_path = parsed.path.rstrip("/") or "/"
    body = body or {}

    if method == "GET" and clean_path in {"/.well-known/agent-card.json", "/agent-card.json"}:
        return 200, agent_card(base_url, config=config)
    if method == "GET" and clean_path == "/health":
        return 200, queue_health(queue_root=queue_root, config=config)
    if method == "POST" and clean_path in {"/a2a", "/jsonrpc"}:
        return 200, handle_jsonrpc(body, queue_root=queue_root, config=config)
    if method == "POST" and clean_path == "/message:send":
        return 200, submit_message(body, queue_root=queue_root, config=config)
    if method == "POST" and clean_path == "/message:stream":
        submitted = submit_message(body, queue_root=queue_root, config=config)
        task = get_task(submitted["task"]["id"], queue_root=queue_root, config=config)
        return 200, {"sse_events": build_stream_events(task or {"task_id": submitted["task"]["id"], "status": "TASK_STATE_SUBMITTED"}, request_id=body.get("id"))}
    if method == "POST" and clean_path == "/a2a/tasks":
        envelope = body.get("envelope") if isinstance(body.get("envelope"), dict) else None
        input_payload = body.get("input") if isinstance(body.get("input"), dict) else body
        if envelope is None:
            envelope, input_payload = _build_gateway_envelope({"message": body.get("message") or {}, "query": body.get("query"), "metadata": body.get("metadata") or {}})
        task = create_task(envelope=envelope, input_payload=input_payload, queue_root=queue_root, config=config)
        return 200, {"task": to_a2a_task(task)}
    if method == "POST" and clean_path == "/a2a/tasks/claim":
        task = claim_next_task(queue_root=queue_root, worker_id=str(body.get("worker_id") or "external-worker"), config=config)
        return 200, {"task": to_a2a_task(task) if task else None}
    if method == "GET" and clean_path == "/tasks":
        return 200, queue_health(queue_root=queue_root, config=config)
    if method == "GET" and clean_path.startswith("/tasks/"):
        task_id = clean_path.split("/", 2)[2]
        task = get_task(task_id, queue_root=queue_root, config=config)
        if not task:
            return 404, {"error": "task not found", "task_id": task_id}
        return 200, {"task": to_a2a_task(task)}
    if method == "GET" and clean_path.startswith("/a2a/tasks/"):
        task_id = clean_path.split("/")[3]
        task = get_task(task_id, queue_root=queue_root, config=config)
        if not task:
            return 404, {"error": "task not found", "task_id": task_id}
        return 200, {"task": to_a2a_task(task)}
    if method == "GET" and clean_path == "/a2a/events":
        query = parse_qs(parsed.query)
        task_id = (query.get("task_id") or query.get("taskId") or [""])[0]
        trace_id = (query.get("trace_id") or query.get("traceId") or [""])[0]
        if task_id:
            return 200, {"events": list_task_events(task_id, queue_root=queue_root, config=config)}
        if trace_id:
            events: list[dict[str, Any]] = []
            root = queue_root or queue_root_from_config(config)
            if config and external_backend_available(config):
                tasks = [task for state_dir in ("pending", "running", "completed", "failed") for task in backend_iter_tasks(config, state_dir)]
            else:
                tasks = []
                for state_dir in ("pending", "running", "completed", "failed"):
                    tasks.extend(json.loads(task_path.read_text(encoding="utf-8")) for task_path in (root / state_dir).glob("*.json"))
            for task in tasks:
                if task.get("envelope", {}).get("trace_id") == trace_id:
                    events.extend(list_task_events(str(task.get("task_id")), queue_root=root, config=config))
            return 200, {"events": events}
        return 200, {"events": []}
    if method == "POST" and clean_path.endswith("/result") and clean_path.startswith("/a2a/tasks/"):
        task_id = clean_path.split("/")[3]
        envelope = body.get("envelope") if isinstance(body.get("envelope"), dict) else None
        artifacts = body.get("artifacts") if isinstance(body.get("artifacts"), list) else []
        task = complete_task(task_id, result_envelope=envelope, artifacts=artifacts, queue_root=queue_root, config=config)
        return 200, {"task": to_a2a_task(task)}
    if method == "POST" and clean_path.endswith("/fail") and clean_path.startswith("/a2a/tasks/"):
        task_id = clean_path.split("/")[3]
        error = body.get("error") if isinstance(body.get("error"), dict) else {"message": str(body.get("message") or "worker failed")}
        task = fail_task(task_id, error=error, queue_root=queue_root, config=config)
        return 200, {"task": to_a2a_task(task)}
    if method == "POST" and clean_path.endswith("/pushNotificationConfig") and clean_path.startswith("/a2a/tasks/"):
        task_id = clean_path.split("/")[3]
        push_config = body.get("pushNotificationConfig") if isinstance(body.get("pushNotificationConfig"), dict) else body
        task = set_push_notification_config(task_id, push_config, queue_root=queue_root, config=config)
        return 200, {"task": to_a2a_task(task), "pushNotificationConfig": push_config}
    if method == "GET" and clean_path.endswith("/pushNotificationConfig") and clean_path.startswith("/a2a/tasks/"):
        task_id = clean_path.split("/")[3]
        return 200, {"id": task_id, "pushNotificationConfig": get_push_notification_config(task_id, queue_root=queue_root, config=config)}
    return 404, {"error": "not found", "path": clean_path}


class A2AGatewayHandler(BaseHTTPRequestHandler):
    server_version = "FBBPA2AGateway/0.1"

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        response_status, headers, body = _json_response(payload, status)
        self.send_response(response_status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_sse(self, events: list[str]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        for event in events:
            self.wfile.write(event.encode("utf-8"))
            self.wfile.flush()

    def _authorized(self) -> tuple[bool, str]:
        public_paths = {"/.well-known/agent-card.json", "/agent-card.json"}
        allow_public_card = bool((self.server.queue_config.get("auth") or {}).get("allow_public_agent_card", True))
        if allow_public_card and urlparse(self.path).path in public_paths:
            return True, "public_agent_card"
        return authenticate_headers(self.headers, self.server.queue_config)

    def do_GET(self) -> None:  # noqa: N802
        authorized, reason = self._authorized()
        if not authorized:
            self._send(401, {"error": "unauthorized", "reason": reason})
            return
        status, payload = handle_rest("GET", self.path, None, queue_root=self.server.queue_root, config=self.server.queue_config, base_url=self.server.base_url)
        self._send(status, payload)

    def do_POST(self) -> None:  # noqa: N802
        try:
            authorized, reason = self._authorized()
            if not authorized:
                self._send(401, {"error": "unauthorized", "reason": reason})
                return
            body = self._read_json()
            if urlparse(self.path).path in {"/message:stream", "/tasks/resubscribe"}:
                if urlparse(self.path).path == "/tasks/resubscribe":
                    task_id = str(body.get("id") or body.get("taskId") or "")
                    task = get_task(task_id, queue_root=self.server.queue_root, config=self.server.queue_config)
                    if not task:
                        self._send(404, {"error": "task not found", "task_id": task_id})
                        return
                    self._send_sse(build_stream_events(task, request_id=body.get("id")))
                    return
                status, payload = handle_rest("POST", self.path, body, queue_root=self.server.queue_root, config=self.server.queue_config, base_url=self.server.base_url)
                if status != 200:
                    self._send(status, payload)
                    return
                self._send_sse(payload.get("sse_events", []))
                return
            status, payload = handle_rest("POST", self.path, body, queue_root=self.server.queue_root, config=self.server.queue_config, base_url=self.server.base_url)
        except Exception as exc:
            status, payload = 500, {"error": str(exc)}
        self._send(status, payload)

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write("a2a_gateway: " + (format % args) + "\n")


class A2AGatewayServer(ThreadingHTTPServer):
    queue_root: Path
    queue_config: dict[str, Any]
    base_url: str


def run_server(host: str, port: int, *, queue_root: Path | None = None) -> None:
    config = load_worker_queue_config()
    resolved_queue_root = queue_root or queue_root_from_config(config)
    server = A2AGatewayServer((host, port), A2AGatewayHandler)
    server.queue_root = resolved_queue_root
    server.queue_config = config
    server.base_url = f"http://{host}:{port}"
    print(json.dumps({"status": "listening", "host": host, "port": port, "queue_root": str(resolved_queue_root)}, ensure_ascii=False))
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the FBBP A2A gateway.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--queue-root")
    args = parser.parse_args()
    run_server(args.host, args.port, queue_root=Path(args.queue_root) if args.queue_root else None)


if __name__ == "__main__":
    main()
