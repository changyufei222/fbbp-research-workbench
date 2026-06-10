# Biomedical Agent Control Plane For FBBP Research

## Project Summary

I built a job-ready biomedical agent system that turns separate RAG, MCP, formal-runner, eval, and small-model compiler components into one observable agent control plane.

The system receives a user request, decides the correct primary route, optionally invokes secondary capabilities, delegates execution to the right runner or worker, writes a structured run record, and exports metrics into an evaluation dashboard.

## Why This Project Matters

Many AI demos stop at "call an LLM and return an answer." This project focuses on the engineering layer needed for a real agent product:

- Intent routing instead of one prompt handling every task
- Private RAG and public biomedical tool lookup in the same product layer
- A2A-compatible task handoff with trace ids and retry/dead-letter handling
- Session memory and resume artifacts
- Unified run records for observability and agent evaluation
- A dashboard that makes system behavior inspectable over time

## Verified Status

The full-readiness baseline evidence shows:

- `6/6` readiness checks passing
- PostgreSQL bridge reachable from Windows to WSL
- A2A live e2e completed through worker execution
- MiniMind secondary query compiler returned a schema-valid plan
- Private RAG live path succeeded
- Public lookup live path succeeded
- Eval dashboard generated from `50+` control-plane run records

The interview-safe fast demo currently verifies:

- A2A worker e2e
- MiniMind secondary capability
- Eval dashboard generation

Key evidence files:

- `runs/control_plane/readiness/live_full/readiness_summary.json`
- `../llm-eval-benchmark/reports/control_plane_dashboard/latest/summary.json`
- `../llm-eval-benchmark/reports/control_plane_dashboard/latest/runs.csv`

## Core Capabilities

### Agent-Level Intent Router

The router classifies work into stable product routes:

- `private_rag`
- `public_lookup`
- `formal_case`
- `batch_eval`
- `report_generation`
- `fallback_general`

It also supports secondary capabilities, including MiniMind candidate query compilation.

### Memory Closure

The memory layer supports:

- Session memory read
- Compact memory write
- Resume state
- Profile-level memory update

This makes the system more than stateless request-response.

### A2A-Compatible Adapter

The A2A layer supports:

- Lifecycle envelope
- Trace id and correlation id
- Hop metadata
- HTTP/JSON-RPC gateway
- Worker queue
- Worker daemon
- Automatic retry
- Dead-letter handling
- API-key authentication
- Streaming and push notification configuration
- Optional Redis/Postgres backend adapters

This is best described as an A2A-compatible v1 subset, not a claim of complete official protocol coverage.

### Unified Observability And Agent Eval

Every run can write:

- Primary route
- Status
- Tool success rate
- Memory hit
- Latency
- Cost estimate field
- Judge score
- Preflight hit rate
- A2A hop/envelope counts

The eval dashboard aggregates these records into `llm-eval-benchmark`.

## Cross-Repository Architecture

| Repository | Role |
|---|---|
| `fbbp-research-workbench` | Product control plane, unified entry, router, memory, A2A, run records, readiness |
| `llm-rag-knowledge-base` | Private RAG backend and evidence-grounded answering |
| `fbbp-mcp-rag-server` | MCP tool plane for private search and public biomedical lookup |
| `llm-eval-benchmark` | Aggregated eval dashboard and benchmark outputs |
| `minimind-fbtp-lab` | Query compiler and structured intent research |
| `upstream-deerflow` | Upstream agent runtime source |

## Technical Stack

- Python
- PowerShell
- PostgreSQL / pgvector
- WSL
- MCP
- LangGraph-style RAG workflow
- JSON-RPC / HTTP
- SSE-style streaming
- MiniMind query compiler
- Eval dashboard generated from JSON/CSV artifacts

## Demo

Fast demo:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\demo_job_ready_control_plane.ps1 -Fast
```

Full readiness demo:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\demo_job_ready_control_plane.ps1 -Full
```

## Resume Positioning

Best-fit roles:

- AI Engineer
- RAG Engineer
- Agent Infrastructure Engineer
- Applied LLM Engineer
- Bio-AI / Scientific AI Engineer

Recommended one-line project title:

```text
Biomedical Agent Control Plane for FBBP Research Workflows
```

## What I Would Improve Next

For job-search purposes, the feature set is already strong. The next improvements are mostly packaging and production hardening:

- Add a small static dashboard UI
- Add long-term semantic memory governance
- Run official A2A conformance checks if needed
- Swap local file queue to real Redis/Postgres queue service in a deployed environment
- Add a public anonymized demo dataset
