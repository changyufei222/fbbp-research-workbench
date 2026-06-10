# Resume Bullets

## Recommended Project Title

Biomedical Agent Control Plane for FBBP Research Workflows

## Chinese Resume Version

**FBBP 生物医学 Agent Control Plane 平台**  
技术栈：`Python`、`MCP`、`PostgreSQL/pgvector`、`WSL`、`LangGraph-style RAG`、`JSON-RPC/HTTP`、`MiniMind`、`PowerShell`

- 构建面向 FBBP 生物医学研究场景的 Agent Control Plane，将私有 RAG、公开生物医学查询、正式 case、批量评测和报告生成收束到统一入口。
- 实现规则优先的 agent 级 intent router，支持 `private_rag / public_lookup / formal_case / batch_eval / report_generation / fallback_general` 六类主路由，并接入 MiniMind query compiler 作为次级能力。
- 设计 A2A-compatible v1 任务交接层，支持 JSON-RPC/HTTP gateway、worker queue、trace id、hop metadata、自动重试、dead-letter、SSE streaming、push notification config 与 API-key auth。
- 补齐生产化 hardening 层，提供 Redis/Postgres queue backend 模板、OIDC reverse-proxy/JWT claims 接入点、A2A conformance coverage check 和 hardening summary。
- 打通 session memory 写入、读取、压缩摘要和 resume state，使系统从 stateless API 调用升级为可延续的多轮任务执行框架。
- 实现长期语义记忆 store，支持相似记忆自动 merge、冲突队列、语义检索和 HTML 可视化管理页面。
- 统一 run record 与 observability 指标，记录 route、tool success rate、memory hit、latency、cost placeholder、judge score、preflight hit rate，并将 `50+` 条运行记录汇总到 eval dashboard。
- 完成本地 live readiness 验证，覆盖 PostgreSQL bridge、A2A worker e2e、MiniMind secondary、private RAG、public lookup 和 eval dashboard，当前 `6/6` 检查通过。

## English Resume Version

**Biomedical Agent Control Plane for FBBP Research Workflows**  
Stack: `Python`, `MCP`, `PostgreSQL/pgvector`, `WSL`, `LangGraph-style RAG`, `JSON-RPC/HTTP`, `MiniMind`, `PowerShell`

- Built a biomedical agent control plane that unifies private RAG, public biomedical lookup, formal case execution, batch evaluation, and report generation under one product entry point.
- Implemented a rule-first intent router covering `private_rag`, `public_lookup`, `formal_case`, `batch_eval`, `report_generation`, and `fallback_general`, with MiniMind query compilation as a secondary capability.
- Designed an A2A-compatible v1 handoff layer with JSON-RPC/HTTP gateway, worker queue, trace ids, hop metadata, automatic retry, dead-letter handling, SSE streaming, push notification configuration, and API-key auth.
- Added a production-hardening layer with Redis/Postgres queue backend templates, OIDC reverse-proxy/JWT-claims hooks, A2A conformance coverage checks, and hardening summaries.
- Added session memory read/write, compact summaries, and resume state so multi-step research workflows can continue across runs instead of behaving as stateless API calls.
- Implemented a long-term semantic memory store with automatic merge, conflict queue, semantic retrieval, and an HTML management view.
- Standardized run records and observability metrics including route, tool success rate, memory hit, latency, cost placeholder, judge score, and preflight hit rate, then exported `50+` run records into an eval dashboard.
- Verified the live system with `6/6` readiness checks across PostgreSQL bridge, A2A worker e2e, MiniMind secondary capability, private RAG, public lookup, and eval dashboard generation.

## Short Version For A Crowded Resume

- Built a biomedical Agent Control Plane integrating intent routing, private RAG, public scientific lookup, A2A-compatible worker delegation, session memory, unified observability, and an eval dashboard.
- Implemented a six-route rule-first router plus MiniMind secondary query compilation; verified live readiness across private RAG, public lookup, A2A e2e, and dashboard generation.
- Standardized run records across `50+` executions, tracking tool success rate, memory hit, latency, judge score, preflight hit rate, and A2A metadata.

## Interview Talking Points

- The project is not just an LLM wrapper; the main contribution is the control-plane architecture around the model.
- The router prevents every request from being forced through the same RAG prompt.
- A2A-compatible task handoff makes agent-to-worker delegation inspectable and recoverable.
- Run records and dashboard outputs turn agent behavior into measurable engineering evidence.
- The MiniMind compiler is a secondary structured-intent capability, not the main production runtime.
