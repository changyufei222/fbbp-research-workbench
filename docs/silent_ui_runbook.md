# Silent DeerFlow UI Runbook

Use these repo-root entry points on Windows:

- `Open_DeerFlow_UI.vbs`
- `Stop_DeerFlow_UI.vbs`
- `Check_DeerFlow_UI_Status.cmd`

What they do:

- `Open_DeerFlow_UI.vbs`
  - starts PostgreSQL access, MCP, DeerFlow backend, and frontend for the real FBBP runtime in the background
- opens `http://127.0.0.1:3000/fbbp`
  - avoids the extra black console windows from the spawned child processes
- `Stop_DeerFlow_UI.vbs`
  - stops the Windows-side DeerFlow services and the WSL-side MCP helpers
- `Check_DeerFlow_UI_Status.cmd`
  - prints the current port and HTTP health status for frontend, gateway, LangGraph, MCP, and PostgreSQL

Important logs:

- frontend: `<local_path_removed>
- DeerFlow backend: `<local_path_removed>
- MCP: `<local_path_removed>
- silent UI wrapper logs: `<local_path_removed>

