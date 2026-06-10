# FBBP 部署与一键启动说明

## 目标

这份文档把 FBBP Agent Control Plane 的运行方式分成三层：

- 本机全栈启动：适合开发和面试现场 demo
- Docker Compose 支撑层：适合快速拉起 Postgres / Redis / live dashboard service
- 云端部署路线：适合后续生产化，不假装当前已经是 SaaS

## 1. 本机一键启动

推荐面试或本地开发使用：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_fbbp_fullstack.ps1
```

如果只想重新生成 dashboard，不启动 DeerFlow/MCP：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_fbbp_fullstack.ps1 -BuildDashboardOnly
```

输出入口：

- Workbench UI: `http://127.0.0.1:3000/workspace`
- Formal page: `http://127.0.0.1:3000/fbbp`
- Gateway health: `http://127.0.0.1:8001/health`
- MCP endpoint: `http://127.0.0.1:8000/mcp`
- Portfolio dashboard: `http://127.0.0.1:8088`

最终版验收：

```powershell
python .\scripts\control_plane\final_release_check.py
```

输出：

- `runs/control_plane/final_release/latest/final_release_summary.json`
- `runs/control_plane/final_release/latest/final_release_summary.md`

说明：

- 这一步会刷新 hardening summary、长期语义 memory、eval dashboard、portfolio dashboard。
- 它会检查 Docker Compose 静态结构、一键脚本、部署文档、dashboard、memory、FBBP 命名统一。
- 如果本机没有 Docker Desktop，Docker live validation 会作为 optional skip，不影响本地求职展示验收。

## 2. Docker Compose 支撑层

Compose 文件：

- `docker-compose.yml`
- `Dockerfile.dashboard`

启动：

```powershell
docker compose up -d
```

服务：

- Postgres/pgvector: `localhost:5432`
- Redis: `localhost:6379`
- Live dashboard service: `http://127.0.0.1:8088`

说明：

当前 Compose 负责稳定的基础设施和 live dashboard service。DeerFlow runtime、MCP HTTP server、Windows/WSL 桥接仍推荐使用本机脚本启动，因为这部分依赖你当前机器上的模型/API、WSL 和本地 Python 环境。

生产化时可以把 MCP、A2A gateway、worker daemon 也容器化，但不要在求职 demo 里假装已经完成完整 SaaS 部署。

## 3. Redis / Postgres 队列切换

Redis：

```powershell
$env:FBBP_A2A_REDIS_URL = "redis://127.0.0.1:6379/0"
```

Postgres：

```powershell
$env:FBBP_A2A_POSTGRES_DSN = "postgresql://ragkb:ragkb@127.0.0.1:5432/ragkb"
```

配置模板：

- `configs/control_plane/worker_queue.redis.example.yaml`
- `configs/control_plane/worker_queue.postgres.example.yaml`
- `configs/control_plane/a2a.production.example.yaml`

## 4. 云端部署路线

推荐拆成 5 个服务：

| 服务 | 作用 |
|---|---|
| `postgres` | pgvector / RAG metadata / queue backend |
| `redis` | A2A task queue / fast worker coordination |
| `mcp-server` | FBBP MCP tool plane |
| `control-plane-gateway` | A2A gateway / control-plane API |
| `dashboard` | 静态 dashboard 或 Web UI |

推荐云端路径：

1. 用托管 Postgres 或自建 pgvector。
2. 用托管 Redis 或容器 Redis。
3. 把 `fbbp-mcp-rag-server` 打成 Python service。
4. 把 `scripts/control_plane/a2a_gateway.py` 打成 control-plane gateway service。
5. worker daemon 横向扩容，读取 Redis/Postgres queue。
6. 用 OIDC reverse proxy 保护 gateway。
7. 用 Prometheus / Grafana / OpenTelemetry 收集 metrics。
8. dashboard 静态页面可以先用 Nginx/S3/Cloudflare Pages 托管。

### 推荐云端环境变量

```bash
FBBP_A2A_REDIS_URL=redis://redis:6379/0
FBBP_A2A_POSTGRES_DSN=postgresql://ragkb:ragkb@postgres:5432/ragkb
FBBP_A2A_API_KEY=change-me
FBBP_OIDC_ISSUER=https://issuer.example.com
FBBP_OIDC_JWKS_URL=https://issuer.example.com/.well-known/jwks.json
FBBP_PUBLIC_BASE_URL=https://fbbp.example.com
```

### 最小云端拓扑

```mermaid
flowchart LR
  U["User / Interviewer"] --> P["OIDC Reverse Proxy"]
  P --> G["FBBP Control-Plane Gateway"]
  G --> Q["Redis or Postgres Queue"]
  Q --> W["Worker Daemon Pool"]
  W --> M["FBBP MCP Server"]
  M --> R["FBBP RAG Backend / pgvector"]
  G --> D["Static Portfolio Dashboard"]
```

### 上线前检查

- `python scripts/control_plane/final_release_check.py --require-docker-live`
- `docker compose config`
- `docker compose up -d`
- `curl http://127.0.0.1:8088`
- `curl http://127.0.0.1:8001/health`

## 5. 面试讲法

可以这样说：

> 本地 demo 使用 PowerShell 一键启动，保证能在 Windows/WSL 环境稳定复现。生产化层我补了 Docker Compose，用来拉起 Postgres/pgvector、Redis 和静态 dashboard。真正云端部署时会把 MCP server、A2A gateway 和 worker daemon 分成服务，队列切 Redis/Postgres，入口接 OIDC reverse proxy。
