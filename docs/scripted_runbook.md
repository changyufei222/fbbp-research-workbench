# Scripted Runbook

This workspace now includes a reproducible startup and formal FBBP flow.

This document describes the scripted operational path for the real FBBP runtime.

For the formal primary path, use [formal_runbook.md](/E:/项目/fbbp-research-workbench/docs/formal_runbook.md).

## Startup Order
1. `scripts/start_wsl_pgvector.ps1`
2. `scripts/start_fbbp_http_mcp_wsl.ps1`
3. `scripts/start_deerflow_backend.ps1`

## One-Click Launch

If you want the simplest possible flow, use:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/launch_fbbp_workbench.ps1
```

This will:
- ensure the API key is available (or prompt you for it)
- start the stable backend stack
- start the stable local frontend
- automatically open `http://127.0.0.1:3000/workspace`

The advanced formal surface remains available at:

- `http://127.0.0.1:3000/fbbp`

Or simply run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_stack_core.ps1
```

## Formal FBBP Commands

### Run a checked-in FBBP case
```powershell
$env:OPENAI_API_KEY = '...'
powershell -ExecutionPolicy Bypass -File scripts/run_fbbp_formal_case.ps1 -CaseId fbbp_knottin_landscape_01
```

## Utility Scripts

### Stop all running services
```powershell
powershell -ExecutionPolicy Bypass -File scripts/stop_stack.ps1
```

Keep PostgreSQL running if you want:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/stop_stack.ps1 -KeepPostgres
```

### Build the official full-data atlas package
```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_fbbp_formal_package.ps1
```

This writes the canonical full-data package to:

- `final_results/fbbp_formal_atlas_v2026_04/`

### Capture logs, results, and screenshots
```powershell
powershell -ExecutionPolicy Bypass -File scripts/capture_formal_artifacts.ps1 -Label before_share
```

## Formal Outputs

Formal runs write to:

- `runs/<run_id>/`
- `batches/<batch_id>/`

The canonical publication/GitHub/demo output writes to:

- `final_results/fbbp_formal_atlas_v2026_04/`

## Stable Frontend Mode

Because the mixed `Windows + WSL + mounted-drive` setup makes Next.js installs flaky inside the upstream repo, this workspace uses a project-local runtime copy under `fbbp-research-workbench/runtime/frontend_local`.

### Prepare frontend local copy
```powershell
powershell -ExecutionPolicy Bypass -File scripts/install_frontend_local.ps1
```

### Start full stack in stable mode
```powershell
$env:OPENAI_API_KEY = '...'
powershell -ExecutionPolicy Bypass -File scripts/start_fullstack_local_frontend.ps1
```

### Stable frontend endpoints
- Primary workspace UI: `http://127.0.0.1:3000/workspace`
- Formal results/status UI: `http://127.0.0.1:3000/fbbp`
- Gateway: `http://127.0.0.1:8001/health`
- LangGraph: `http://127.0.0.1:2024/docs`

## What The Scripts Actually Start
- PostgreSQL + pgvector inside WSL
- FBBP HTTP MCP server inside WSL from project-local sources and project-local WSL site-packages
- DeerFlow LangGraph + Gateway on Windows
- Next.js frontend from the project-local runtime copy

## Current Frontend Status
- DeerFlow backend services are stable and scriptable.
- The recommended frontend path is now the **project-local runtime copy** under `fbbp-research-workbench/runtime/frontend_local`.
- This avoids the mounted-drive installation instability seen under the original repo path.

