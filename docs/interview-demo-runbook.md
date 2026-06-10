# Interview Demo Runbook

This runbook is for job interviews, resume project walkthroughs, and portfolio demos. The goal is to show a complete engineering system in 10 to 15 minutes without getting lost in implementation details.

## 30-Second Opening

I built a biomedical agent control plane for FBBP research workflows. It routes requests into private RAG, public biomedical lookup, formal case execution, batch eval, and report generation. It also records every run with memory, A2A handoff metadata, tool success rate, latency, and judge score, then exports those records into an eval dashboard.

## Demo Command

Fast demo:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\demo_job_ready_control_plane.ps1 -Fast
```

The fast demo intentionally avoids the Windows-to-WSL PostgreSQL bridge check, because that dependency is useful for full readiness but too brittle for a short interview screen-share. It still verifies the control-plane demo path: A2A worker e2e, MiniMind secondary capability, and eval dashboard generation.

Full live demo:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\demo_job_ready_control_plane.ps1 -Full
```

If the machine is offline or an external service is unavailable, use:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\demo_job_ready_control_plane.ps1 -SkipLive
```

Production hardening check:

```powershell
python .\scripts\control_plane\production_hardening_check.py
```

Portfolio dashboard:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_portfolio_dashboard.ps1 -Open
```

Local full-stack launcher:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_fbbp_fullstack.ps1
```

## 10-Minute Walkthrough

1. Show the architecture diagram in `docs/agent-control-plane-architecture.md`.
2. Run the fast demo wrapper and show that it writes readiness artifacts.
3. Open `runs/control_plane/readiness/job_demo_fast/readiness_summary.json`.
4. Open `../llm-eval-benchmark/reports/control_plane_dashboard/latest/summary.json`.
5. Explain one route: `private_rag` for private database questions.
6. Explain one external tool route: `public_lookup` for PubMed / UniProt / PDB.
7. Explain A2A: gateway and queue let the control plane hand tasks to workers with trace ids and retry/dead-letter handling.
8. Explain memory: each run can read previous session context and write compact summaries for resume.
9. Explain eval: every run becomes a structured record, so the system can be debugged and compared over time.
10. Explain production hardening: Redis/Postgres backend templates, OIDC hook, A2A conformance coverage, retry, dead letter, streaming, and push notification.

## Files To Show In An Interview

- `README.md`
- `docs/job-ready-project-page.md`
- `docs/agent-control-plane-architecture.md`
- `scripts/run_fbbp_control_plane.py`
- `scripts/control_plane/router.py`
- `scripts/control_plane/a2a_gateway.py`
- `scripts/control_plane/worker_queue.py`
- `scripts/control_plane/readiness_check.py`
- `scripts/control_plane/production_hardening_check.py`
- `reports/control_plane_portfolio_dashboard/latest/index.html`
- `docs/deployment-runbook-cn.md`
- `../llm-eval-benchmark/reports/control_plane_dashboard/latest/summary.md`

## What To Say If Asked "Is This Just Calling An API?"

No. The LLM/API is only one execution dependency. The engineering value is the control plane around it:

- Route selection decides which workflow should run.
- Tool calls are typed and traceable.
- Memory creates continuity across runs.
- A2A handoff makes worker delegation observable.
- Readiness checks prove the system is alive.
- Eval dashboard turns run history into metrics.

## Honest Limitations

- It is an engineering v1, not a production multi-tenant service.
- A2A is a compatible v1 subset, not official full protocol conformance.
- Redis/Postgres queue backends are adapter-ready, but the local demo can still use the file queue.
- OIDC hooks exist, but a real production deployment still needs company issuer/JWKS/scope policy.
- Long-term semantic memory governance is not fully productized.
- Some formal DeerFlow planning paths can still be limited by upstream provider quota.
