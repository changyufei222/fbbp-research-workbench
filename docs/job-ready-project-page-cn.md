# FBBP 生物医学 Agent Control Plane 平台

## 一句话介绍

这是一个面向 FBBP 生物医学研究任务的 Agent Control Plane 项目：它把私有 RAG、公开生物医学工具查询、正式 case 执行、批量评测、报告生成、memory、A2A worker queue 和统一观测收束到一个可演示、可验证、可写进简历的工程系统里。

## 这个项目解决什么问题

普通 LLM demo 往往只是“输入问题 -> 调 API -> 输出回答”。这个项目重点不是单次回答，而是让 Agent 系统像一个真正的工程产品：

- 先判断任务类型，而不是所有请求都走同一个 prompt
- 能查自己的私有知识库，也能查 PubMed / UniProt / PDB 这类公开生物医学工具
- 能把任务交给 worker 执行，并记录 trace id、hop metadata、重试和死信
- 能记住 session memory，支持摘要写入和 resume
- 每次运行都生成 run record，后续能做观测、排错和评测
- 能把运行记录汇总成 eval dashboard，用数据证明系统不是“感觉能用”

## 当前可展示证据

完整 readiness 基线：

- `6/6` 检查通过
- 证据文件：`runs/control_plane/readiness/live_full/readiness_summary.json`
- 覆盖 PostgreSQL bridge、A2A worker e2e、MiniMind secondary、private RAG、public lookup、eval dashboard

面试安全 demo：

- `3/3` 检查通过
- 证据文件：`runs/control_plane/readiness/job_demo_fast/readiness_summary.json`
- 覆盖 A2A worker e2e、MiniMind secondary、eval dashboard
- 这个模式故意不依赖 Windows-to-WSL PostgreSQL bridge，适合短时间面试演示

Dashboard 证据：

- `../llm-eval-benchmark/reports/control_plane_dashboard/latest/summary.json`
- 当前已聚合 `50+` 条 control-plane run record

生产化增强证据：

- `runs/control_plane/hardening/latest/production_hardening_summary.json`
- 已补 Redis/Postgres queue backend 模板、OIDC 接入点、A2A conformance coverage check
- 静态 dashboard：`reports/control_plane_portfolio_dashboard/latest/index.html`
- 长期语义记忆 viewer：`reports/control_plane_portfolio_dashboard/latest/semantic_memory.html`
- 部署说明：`docs/deployment-runbook-cn.md`

## 核心模块

### 1. Agent 级 Intent Router

支持六类主路由：

- `private_rag`
- `public_lookup`
- `formal_case`
- `batch_eval`
- `report_generation`
- `fallback_general`

价值：让系统知道“这句话到底是什么活”，避免所有问题都硬塞进一个 RAG prompt。

### 2. Memory 闭环

支持：

- session memory 读取
- compact summary 写入
- resume state
- profile memory 更新

价值：系统不再是完全无状态的 API 调用，而是能延续上下文的多步任务框架。

### 3. A2A-Compatible Adapter

支持：

- HTTP/JSON-RPC gateway
- worker queue
- worker daemon
- trace id / correlation id / hop metadata
- retry
- dead letter
- API-key auth
- streaming / push notification config
- Redis/Postgres backend adapter

价值：以后要接远程 worker、并行 agent、外部执行器时，任务交接不会乱。

### 3.5 生产化增强层

已补：

- Redis queue 配置模板
- Postgres queue 配置模板
- Docker Compose 支撑层
- 一键本地 full-stack launcher
- OIDC reverse-proxy / JWT claims 接入点
- A2A 方法覆盖检查
- production hardening check

说明：这些能力不需要本地付费服务即可展示设计和接入点；真实生产部署时再填 Redis/Postgres DSN、OIDC issuer/JWKS 和权限 scope。

### 4. 统一观测 + Agent Eval

每次运行记录：

- route
- status
- tool success rate
- memory hit
- latency
- cost estimate field
- judge score
- preflight hit rate
- A2A envelope / hop count

价值：出了问题能查，系统质量能量化，不再只是“感觉还行”。

### 5. 长期语义记忆与可视化管理

已补：

- semantic memory store
- 相似记忆自动 merge
- 同路由低相似记忆进入 conflict queue
- memory HTML viewer

价值：这让 memory 不只是 session 摘要，而是可以长期积累、检索、合并和审查的工程模块。

## 多仓库分工

| 仓库 | 作用 |
|---|---|
| `fbbp-research-workbench` | 产品层 control plane、统一入口、路由、memory、A2A、run record、readiness |
| `llm-rag-knowledge-base` | 私有 RAG 后端和证据问答 |
| `fbbp-mcp-rag-server` | MCP 工具层，负责私有检索和公开生物医学工具 |
| `llm-eval-benchmark` | eval dashboard 和 benchmark 输出 |
| `minimind-fbtp-lab` | MiniMind query compiler / structured intent 实验 |
| `upstream-deerflow` | 上游 agent runtime 来源 |

## 面试讲法

可以这样说：

> 这个项目不是单纯调 API。我做的是 agent control plane：它负责判断任务类型、选择执行路径、调用工具、交给 worker、写 memory、生成 run record，并把所有运行汇总进 eval dashboard。LLM 只是其中一个执行依赖，真正的工程重点是路由、工具、记忆、A2A 交接和可观测性。

## 简历标题

推荐标题：

```text
FBBP 生物医学 Agent Control Plane 平台
```

英文标题：

```text
Biomedical Agent Control Plane for FBBP Research Workflows
```
