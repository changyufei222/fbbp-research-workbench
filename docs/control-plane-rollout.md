# FBBP Agent Control Plane 主执行蓝图

## 1. 文档目的

这份文档用于把 `FBBP Research Workbench` 从“已有多个可用能力的工作台”推进为“有统一入口、统一判路、统一 run record、统一观测和统一评测的产品层 control plane”。

本文档只解决一件事：

- 把当前已经分散在多个仓库中的能力，收束成一个可执行、可观测、可恢复、可评测的 `Agent Control Plane`

本文档不解决三件事：

- 不重做 `llm-rag-knowledge-base` 的数据库、ingest、schema tables 和底层 RAG 主链
- 不重做 `upstream-deerflow` 的底层 agent runtime、memory plumbing、subagent runtime、sandbox 和 MCP 基础设施
- 不把 `MiniMind` 变成 A2A 主体或正式产品主入口

## 2. 当前基线

按“产品层真正统一落地了多少”来算，当前基线如下：

| 模块 | 当前状态 | 说明 |
|---|---:|---|
| 统一观测 + agent eval | 80%-85% | 已有统一 `run_record.metrics`、parent/child run record、preflight 命中率、A2A 指标；并已输出跨 run dashboard 到 `llm-eval-benchmark/reports/control_plane_dashboard/latest` |
| memory 闭环 | 55%-65% | 已有 session read/write、profile auto-write、resume_state 和短摘要压缩；剩余是更强的长期记忆检索、冲突处理和语义压缩 |
| agent 级 intent router | 75%-85% | 已有规则优先主路由、文件优先判定、`fallback_general`、次级能力检测和执行注册；`public_lookup` 已从 DeerFlow fallback 升级为直接调用 MCP 科学工具层；MiniMind query compiler 已作为 `candidate_query_compile` secondary capability 接入 |
| A2A adapter | 80%-85% | 已有内部 lifecycle envelope、外部 HTTP/JSON-RPC gateway、SSE streaming、push notification config、API key auth、文件型 remote-worker queue、自动重试、死信队列、Redis/Postgres 可选 backend adapter；剩余是远程服务实测、OAuth/OIDC、生产级 streaming 长连接治理 |

### 2.1 小白版解释：这四个东西到底有什么用

如果把整个系统想象成一个办公室，这四个模块分别是：

| 模块 | 小白版比喻 | 实际用处 | 当前是否满足 |
|---|---|---|---|
| agent 级 intent router | 前台分诊台 | 先判断用户这句话应该走哪条工作流，比如查私有库、查公开资料、跑正式 case、批量评测、生成报告，避免所有问题都硬塞进同一个问答接口 | 基本满足。`private_rag / public_lookup / formal_case / batch_eval / report_generation / fallback_general` 已进入规则路由；其中 `public_lookup` 已接入 PubMed / UniProt / PDB 工具执行链 |
| memory 闭环 | 办公室笔记本 | 把本轮做过的事写下来，下次同一个 `thread_id` 能读回来；太长时压成摘要；中断后可以根据 `resume_state.json` 接着做 | 部分满足。已有写入、读取、短摘要、resume；长期记忆冲突合并、语义压缩、可解释检索还要继续补 |
| A2A adapter | 员工之间的交接单 | 主 agent 把任务交给 worker/runner 时，用统一格式记录谁派给谁、任务编号、走了几跳、输入输出在哪里、失败原因是什么 | v1 已满足。已有 `request/result/error` lifecycle envelope、`trace_id`、`correlation_id`、`hop metadata`、HTTP/JSON-RPC gateway、SSE streaming、push notification、API key auth、worker queue、retry、dead letter |
| 统一观测 + agent eval | 行车记录仪 + 成绩单 | 每次运行都留下统一记录：走了哪条路、工具成功率、memory 是否命中、耗时、成本、judge 分数，后面能排查问题、做评测、做 dashboard | 大部分满足。`run_record.json` 和 `observability.json` 已写入核心指标；跨仓库汇总和 dashboard 还未完全收口 |

这四个模块的价值不是“让项目听起来高级”，而是解决真实工程问题：

- 路由让系统知道该做什么活，不再所有请求都靠一个 prompt 硬猜
- memory 让系统能延续上下文，不用每次从零解释
- A2A 让任务交接有凭证，后面才能接外部 worker、并行执行、失败追踪
- 观测和 eval 让系统能被验证，出错能查，效果能量化

### 2.2 A2A 产品化能力满足状态

当前 A2A 已经不是简单 JSON 装饰，已经补成可运行的 v1 产品化能力。但它仍不是“官方全量协议 + 全部高级特性”的最终形态。状态如下：

| 能力 | 当前状态 | 它到底是干嘛的 | 下一步落点 |
|---|---|---|---|
| 外部标准 Agent2Agent 网络协议 | v1 兼容子集已满足 | 让别的 agent 系统通过 HTTP/API 和 workbench 通信，而不是只能读本地 Python/JSON 文件 | `scripts/control_plane/a2a_gateway.py` 已提供 Agent Card、`message/send`、`message/stream`、`tasks/get`、`tasks/cancel`、`tasks/resubscribe`、push notification config set/get、`/message:send`、`/message:stream`、`/a2a/tasks`、`/a2a/events` |
| 远程 worker 队列 | v1 已满足 | 把任务排队，派给本机或其他机器上的 worker 执行；适合 formal/batch 长任务 | `configs/control_plane/worker_queue.yaml` 与 `scripts/control_plane/worker_queue.py` 已提供文件型队列；后续可替换 Redis/Postgres |
| 自动重试 | v1 已满足 | 子任务失败时按规则自动再跑，而不是人工重新点 | `max_attempts`、`backoff_seconds`、`lease_seconds` 已进入 `worker_queue.yaml`，`fail_task()` 会自动回到 pending 或进入 failed |
| 死信队列 | v1 已满足 | 一个任务多次失败后不要无限重跑，而是放进专门目录/表里，方便排查和恢复 | 超过重试次数后写入 `runs/control_plane/dead_letters/`，保留原始 envelope、错误、attempts、最后状态 |
| SSE streaming | v1 已满足 | 客户端保持连接时，可以实时收到 task/status/artifact 事件 | Agent Card 声明 `capabilities.streaming=true`，`/message:stream` 与 `tasks/resubscribe` 输出 `text/event-stream` |
| Push notification | v1 已满足 | 客户端断开时，任务完成/重试/死信后由服务端主动 POST 到 webhook | `tasks/pushNotificationConfig/set/get` 与任务内 `pushNotificationConfig` 已支持，完成/失败时触发 webhook 尝试 |
| 身份认证 | v1 已满足 | 防止任何人都能往 gateway 塞任务或 claim 任务 | `auth.enabled`、`FBBP_A2A_API_KEY`、`Authorization: Bearer`、`X-A2A-API-Key` 已支持 |
| Redis/Postgres 队列后端 | v1 adapter 已加入 | 文件队列不适合多机器生产环境，Redis/Postgres 适合共享队列和持久化 | `queue_backend=file/redis/postgres`，`FBBP_A2A_REDIS_URL`，`FBBP_A2A_POSTGRES_DSN`，health 中显示 backend availability；未配置服务时默认回落文件队列 |

因此最诚实的表述是：

- 已满足：内部 A2A lifecycle envelope、trace id、correlation id、hop metadata、run record 指标、基础校验、HTTP/JSON-RPC gateway、SSE streaming、push notification config、API key auth、文件型 worker queue、自动重试、死信队列、Redis/Postgres optional adapter
- 未完全满足：官方全量协议一致性测试、OAuth/OIDC、真实 Redis/Postgres 服务压测、长连接断线恢复策略、push webhook 签名轮换

这意味着 v1 的设计目标不是“从零开始造一个大系统”，而是：

- 先把已有能力统一接入
- 再把缺口补成产品级闭环

补充进展：

- `Phase 1` control-plane skeleton 已落在 `scripts/control_plane/` 与 `scripts/run_fbbp_control_plane.py`
- `private_rag` live 统一入口已跑通，示例输出位于 `runs/control_plane/private_rag_live_demo_v6/`
- `formal_case` live 统一入口已跑通，最新示例输出位于 `runs/control_plane/formal_case_live_demo_v10/`
- `batch_eval` live 统一入口已跑通，示例输出位于 `runs/control_plane/batch_eval_live_demo_v2/`
- 当前 interactive `private_rag` 采用稳定优先的轻量 profile：
  - 自动引导 `WSL PostgreSQL`
  - 默认 `extractive`
  - 默认 `local_hash + reranker off`
  - 在 `run_record.json` 中显式记录降级信息
- `formal` / `batch` 现在也走稳定优先的显式 runtime profile：
  - 显式注入 `VectorEngine + deepseek-v3.2`
  - 保持 `fbbp_mcp_server` 与旧 `fbtp_mcp_server` 的兼容导入
  - formal gateway 在私有检索时强制 `local_hash + reranker off + extractive`
- memory 闭环已从“只写 session 文件”推进到“可验证的 write + resume”：
  - `private_rag_live_demo_v7` 已把紧凑摘要自动写入 `configs/agents/fbbp-assistant/memory.json`
  - `private_rag_memory_resume_demo_v1` 已验证同 `thread_id` 下 `read_hit=true` 与 `resume_used=true`
- `formal_case` 现已补上 tool-first preflight：
  - 对首跳明确要求 `search_knowledge` 的 case，可先直连 formal gateway 执行固定检索
  - 若证据行已满足 stop policy，则直接生成 formal artifacts，不再进入 DeerFlow 模型续跑
  - `formal_case_live_demo_v10` 已验证 `completion_reason=preflight:evidence_sufficient_low_confidence_answer`
- `source provenance` formal case 现已补上文件优先 preflight：
  - `configs/formal_cases/fbbp_source_provenance_review_01.yaml` 启用 `preflight_source_provenance`
  - `scripts/run_fbbp_formal_case.py` 会先尝试 `list_sources -> get_source_summary`
  - 若 PostgreSQL / DB worker 不可用，会从 `fbbp-mcp-rag-server/configs/datasets/fbbp_private_v2026_04.json` 的 `source_registry` 自动 fallback
  - `source_provenance_preflight_metrics_live_v1` 已验证 `completion_reason=preflight:source_provenance_satisfied`
- `run_record.json` 现已补上统一 `metrics` 块：
  - 包含 `route`、`tool_success_rate`、`memory_hit`、`latency_ms`、`estimated_cost_usd`、`judge_score`、`preflight_hit_rate`
  - `observability.json` 同步携带 `metrics`，可直接作为 dashboard / eval 输入
- `A2A adapter v1` 现已从“child summary 包装”推进为内部 parent/child lifecycle envelope：
  - `scripts/control_plane/a2a.py` 负责生成 `fbbp.a2a.envelope.v1`
  - `configs/control_plane/a2a.schema.json` 固化 envelope 契约
  - 每个 child hop 至少生成 `child_run_request` 与 `child_run_result`，失败时生成 `child_run_error`
  - 同一 child lifecycle 通过 `correlation_id` 关联，`phase` 显式区分 `requested / completed / error`
  - 运行时会调用 envelope/trace validator，缺少错误 payload、非法 message type、缺少 hop metadata 会被拒绝
  - `a2a_trace.json`、`children.json.a2a_envelopes`、`run_record.json.a2a` 三处同步记录 child handoff
  - `a2a_lifecycle_source_provenance_live_v1` 已验证 `request -> result` 生命周期、`correlation_id`、`envelope_count=2`、`artifact_ref`
- `public_lookup` 现已从 fallback 升级为直接 MCP tool-plane 调用：
  - `configs/control_plane/project_links.yaml` 统一记录 workbench、MCP server、ragkb、eval benchmark、MiniMind lab、upstream DeerFlow 的项目连接关系
  - `scripts/control_plane/public_lookup.py` 负责识别 PubMed / UniProt / PDB 目标，并复用 `fbbp-mcp-rag-server` 的 `search_pubmed`、`get_uniprot_entry`、`get_pdb_entry`
  - `scripts/control_plane/executor_registry.py` 将 `public_lookup` 作为独立主路由执行，不再委派到 `fallback_general`
  - `run_record.child_runs` 会记录每个公共工具调用来自 `fbbp-mcp-rag-server`
- `worker daemon` 现已补上本机执行闭环：
  - `scripts/control_plane/worker_daemon.py` 可从 A2A worker queue claim 任务
  - worker 会把 task input 转成 `run_fbbp_control_plane.py` 参数
  - 执行成功后写回 A2A artifact，失败时走 retry / dead letter 逻辑
- `live e2e` 现已补上真实本机闭环：
  - `scripts/control_plane/live_e2e.py` 会提交 A2A message、写入 queue、启动 local worker、调用 control plane、写回 artifact
  - `runs/control_plane/live_e2e_v1/live_e2e_summary.json` 已验证 `queue_state=completed`、`run_record_status=succeeded`
- `MiniMind secondary capability` 现已接入：
  - `scripts/control_plane/minimind_adapter.py` 读取 `minimind-fbtp-lab` 的 candidate snapshot
  - 通过 `rule_baseline -> validator -> executor` 生成 normalized plan 与预览结果
  - `runs/control_plane/minimind_secondary_live_v2/children/candidate_query_compile_output.json` 已验证 `schema_ok=true`、`filtered_count=310`、`returned_count=2`
- `eval dashboard` 现已接入 `llm-eval-benchmark`：
  - `scripts/control_plane/eval_dashboard.py` 扫描所有 `run_record.json`
  - 输出 `summary.json`、`runs.csv`、`summary.md`
  - 当前输出目录为 `llm-eval-benchmark/reports/control_plane_dashboard/latest`
- `real public lookup` 已完成联网实测：
  - `public_lookup_live_v2` 验证 PubMed、UniProt、PDB 三个工具调用成功，`tool_success_rate=1.0`
  - `public_lookup_pubmed_live_v2` 验证 PubMed 返回真实文章，`article_count=2`
- 当前剩余风险已经从“链路打不通”下降为“需要复杂 DeerFlow 规划或多步工具编排的 formal case 仍可能受上游 API quota 约束”

## 3. 系统边界

### 3.1 v1 要做什么

v1 control plane 负责 4 件事：

1. 提供统一入口
2. 做规则优先的主路由判定
3. 把执行委派给现有 interactive/formal/batch runner
4. 把 route、tool、memory、latency、cost、judge 汇总成统一 run record

### 3.2 v1 不做什么

v1 不做以下事情：

- 不直接替代现有 DeerFlow runtime
- 不要求一次性引入复杂 planner 或 LLM-first 路由器
- 不要求先落标准外部 A2A 协议再开始
- 不要求先把 MiniMind 微调完成才能启动 control plane
- 不重构成新的大型后端服务

### 3.3 五个主仓库与一个上游仓库

本蓝图中的“5 个主仓库”定义如下：

| 仓库 | 角色 | 是否属于 v1 主战场 |
|---|---|---|
| `fbbp-research-workbench` | 产品层 control plane、统一入口、run record、观测汇总 | 是 |
| `llm-rag-knowledge-base` | 私有 RAG 后端、底层 query routing、质量检查 | 是 |
| `fbbp-mcp-rag-server` | MCP 工具层、tool contract、provenance、diagnostics、formal runtime | 是 |
| `llm-eval-benchmark` | 统一 agent eval、leaderboard、category breakdown、cost/latency 汇总 | 是 |
| `minimind-fbtp-lab` | query compiler / semantic parser / structured intent layer | 是 |

上游仓库单列说明：

| 仓库 | 角色 | v1 策略 |
|---|---|---|
| `upstream-deerflow` | 上游引擎来源，提供 memory、subagent、MCP、gateway、sandbox、tracing 基础设施 | 只复用，不作为第一阶段主战场 |

## 4. 五个主仓库各自负责什么

### 4.1 `fbbp-research-workbench`

这是 v1 control plane 的唯一产品层主入口。

已经存在的可复用资产：

- `scripts/query_private_rag.py`
- `scripts/deerflow_embedded_runner.py`
- `scripts/run_fbbp_formal_case.py`
- `scripts/run_fbbp_formal_batch.py`
- `configs/formal_cases/`
- `configs/formal_batches/`
- `configs/runtime_profiles/local_formal.yaml`
- `configs/agents/fbbp-assistant/config.yaml`
- `configs/agents/fbbp-assistant/memory.json`

v1 要新增的职责：

- 统一入口
- 主路由判定
- 次级能力调用编排
- parent/child run record
- 文件优先存储
- interactive 同步/流式
- formal 和 batch 异步 run
- 统一观测聚合

### 4.2 `llm-rag-knowledge-base`

这是私有知识检索与回答的执行后端。

已经存在的可复用资产：

- `src/ragkb/retrieval/retriever.py`
- `src/ragkb/graph/workflow.py`
- `src/ragkb/service.py`
- `src/ragkb/quality/deepchecks.py`
- `src/ragkb/retrieval/filters.py`
- `src/ragkb/eval/offline_eval.py`

v1 要补的职责：

- 把现有 query route、filters、diagnostics 更清晰地暴露给 control plane
- 提供对 MiniMind query plan 的适配层
- 输出更稳定的 route/filters/card_type/evidence 结构

### 4.3 `fbbp-mcp-rag-server`

这是 control plane 的工具平面和私有知识工具网关。

已经存在的可复用资产：

- `src/fbbp_mcp_server/service.py`
- `src/fbbp_mcp_server/schemas.py`
- `src/fbbp_mcp_server/health.py`
- `src/fbbp_mcp_server/formal_runtime.py`
- `src/fbbp_mcp_server/server.py`

v1 要补的职责：

- 在 MCP 请求和响应中携带 control-plane 级 trace/run 上下文
- 让 provenance 和 diagnostics 能更容易被主 run record 吸收
- 对工具调用做更统一的 parent/child 关联

### 4.4 `llm-eval-benchmark`

这是统一 agent eval 的落点，不只是 RAG vs Direct。

已经存在的可复用资产：

- `pipelines/compare.py`
- `pipelines/model_sweep.py`
- `metrics/formal_benchmark.py`
- `reports/latest/` 输出契约

v1 要补的职责：

- 从 control-plane run record 读取数据
- 统计 route、tool、memory、latency、cost、judge
- 提供 control-plane 级 summary、category breakdown、leaderboard

### 4.5 `minimind-fbtp-lab`

这是 query compiler，不是 A2A 主体，也不是产品层主入口。

已经存在的可复用资产：

- `query_compiler/dsl.py`
- `query_compiler/rule_baseline.py`
- `query_compiler/validator.py`
- `query_compiler/executor.py`
- `query_compiler/demo.py`
- `query_compiler/field_registry.py`

v1 要补的职责：

- 提供稳定的 query draft / normalized plan 输出契约
- 以“次级能力”的身份接入 control plane
- 先支持 rule baseline，后支持模型版 compiler

## 5. 上游复用边界

以下能力来自 `upstream-deerflow`，v1 不应重做，只应复用：

- memory middleware:
  - `backend/src/agents/middlewares/memory_middleware.py`
  - `backend/src/agents/memory/updater.py`
- memory API:
  - `backend/src/gateway/routers/memory.py`
- subagent execution:
  - `backend/src/subagents/executor.py`
  - `backend/src/tools/builtins/task_tool.py`
- tracing config:
  - `backend/src/config/tracing_config.py`

v1 原则：

- 能在产品层包一层就不要先 fork 上游
- 只有当产品层无法表达所需能力时，才考虑最小化上游补丁

## 6. 总体架构

### 6.1 总体方向

v1 采用以下固定设计决策：

- 产品层
- 从第一天统一接入
- 规则优先
- `primary_route + secondary_capabilities`
- `fallback_general`
- `force_primary_route`
- `parent/child`
- 文件优先
- interactive 保持同步/流式
- formal 和 batch 走异步 run

### 6.2 总体流程

```mermaid
flowchart TD
  U["用户请求 / CLI / UI / 文件输入"] --> CP["fbbp-research-workbench Control Plane"]
  CP --> P["请求标准化 + 文件优先识别"]
  P --> R["规则优先主路由判定"]
  R --> D["生成 route_decision.json"]
  D --> E["执行委派层"]
  E --> PR["private_rag -> query_private_rag.py / MCP / ragkb"]
  E --> PU["public_lookup -> DeerFlow web tools / PubMed / UniProt / PDB"]
  E --> FC["formal_case -> run_fbbp_formal_case.py"]
  E --> BE["batch_eval -> run_fbbp_formal_batch.py / llm-eval-benchmark"]
  E --> RG["report_generation -> formal_run_lib / report templates"]
  E --> FG["fallback_general -> deerflow_embedded_runner.py"]
  E --> MM["candidate_query_compile -> MiniMind worker (secondary capability)"]
  PR --> RR["统一 run record 聚合"]
  PU --> RR
  FC --> RR
  BE --> RR
  RG --> RR
  FG --> RR
  MM --> RR
  RR --> O["events.jsonl / run_record.json / judge.json / memory artifacts"]
```

## 7. 四个核心模块

### 7.1 agent 级 intent router

#### 7.1.1 目标

把“这个请求到底是什么活”变成一个稳定、可追踪、可覆盖的产品层判断。

v1 不做 LLM-first router，采用规则优先：

- 先看是否有文件路径、case YAML、batch YAML
- 再看是否命中 formal/batch/report/public/private 的显式规则
- 允许 `force_primary_route`
- 允许附带 `secondary_capabilities`

#### 7.1.2 v1 主路由集合

| primary_route | 典型请求 | v1 执行器 |
|---|---|---|
| `private_rag` | 查私有库、查 scaffold/target/source/card、解释库内字段 | `scripts/query_private_rag.py` |
| `public_lookup` | 查 PubMed、UniProt、PDB、公开网页、外部校验 | DeerFlow 内置工具 + MCP 公共科学工具 |
| `formal_case` | 跑正式 case、固定模板分析、case yaml 输入 | `scripts/run_fbbp_formal_case.py` |
| `batch_eval` | 跑 batch、跑稳定性评测、跑 leaderboard、多模型 sweep | `scripts/run_fbbp_formal_batch.py` + `llm-eval-benchmark` |
| `report_generation` | 已有 evidence/run dir，要求整理成报告或 memo | `formal_run_lib.py` / 模板渲染 |
| `fallback_general` | 无法明确归类，但仍需要通用 agent 执行 | `scripts/deerflow_embedded_runner.py` |

#### 7.1.3 v1 次级能力集合

| secondary_capability | 用途 | 首选仓库 |
|---|---|---|
| `candidate_query_compile` | 把自然语言候选筛选请求编译成结构化 query plan | `minimind-fbtp-lab` |
| `public_validation` | 对私有结果做 PubMed/UniProt/PDB 外部校验 | `fbbp-mcp-rag-server` |
| `report_polish` | 把已有证据整理成可读报告 | `fbbp-research-workbench` |
| `memory_resume` | 查找最近会话上下文并恢复 | `fbbp-research-workbench` + `upstream-deerflow` |
| `formal_evidence_pack` | 把 evidence/tool outputs 规范化为 formal artifacts | `fbbp-research-workbench` |

#### 7.1.4 v1 路由规则顺序

按以下优先级判路：

1. `force_primary_route`
2. 文件优先
3. formal/batch 显式输入
4. report generation 显式输入
5. private_rag 领域关键词和私有数据语义
6. public_lookup 外部来源语义
7. `fallback_general`

文件优先规则如下：

- 请求中出现 `configs/formal_cases/*.yaml` 或 `--case-path` -> `formal_case`
- 请求中出现 `configs/formal_batches/*.yaml` 或 `--batch-path` -> `batch_eval`
- 请求中出现已有 `runs/<run_id>`、`batches/<batch_id>`、`report.json`、`evidence.json` -> `report_generation`

#### 7.1.5 在各仓库中的落点

`fbbp-research-workbench` 新增：

- `configs/control_plane/routes.yaml`
- `configs/control_plane/secondary_capabilities.yaml`
- `scripts/control_plane/request_parser.py`
- `scripts/control_plane/router.py`
- `scripts/control_plane/executor_registry.py`
- `scripts/run_fbbp_control_plane.py`

`llm-rag-knowledge-base` 复用或调整：

- 复用 `src/ragkb/retrieval/retriever.py`
- 复用 `src/ragkb/graph/workflow.py`
- 更新 `src/ragkb/service.py` 使 route diagnostics 更稳定
- 新增 `src/ragkb/retrieval/query_plan_adapter.py`

`minimind-fbtp-lab` 新增：

- `query_compiler/worker.py`
- `query_compiler/output_contract.py`
- 可选 `scripts/run_query_compiler.py`

#### 7.1.6 v1 验收标准

- 同一类请求多次运行时，主路由稳定
- `force_primary_route` 可显式覆盖
- 每次请求都落 `route_decision.json`
- `secondary_capabilities` 有明确记录，不是隐式发生

### 7.2 memory 闭环

#### 7.2.1 目标

把 memory 从“存在底层 plumbing”升级成“产品层真的可用”：

- 写进去
- 读出来
- 长了会压缩
- 中断后能 resume

#### 7.2.2 v1 memory 分层

v1 采用双层 memory：

1. 长期 profile memory
2. 会话级 working memory

长期 profile memory：

- 文件位置：`configs/agents/fbbp-assistant/memory.json`
- 用途：用户偏好、长期项目背景、稳定术语映射、长期工作上下文

会话级 working memory：

- 文件位置：`runs/control_plane/<run_id>/memory/`
- 用途：本次任务的中间摘要、上次执行状态、待续跑上下文、恢复指针

推荐目录结构：

```text
runs/control_plane/<run_id>/
  run_request.json
  route_decision.json
  run_record.json
  events.jsonl
  memory/
    session_memory.json
    summary.json
    resume_state.json
    write_log.jsonl
```

#### 7.2.3 v1 memory 工作流

1. 请求进入 control plane
2. 根据 `thread_id/session_id/task_id` 查长期 memory 和最近一次 working memory
3. 生成 `memory_read_summary`
4. 把摘要注入运行上下文
5. 执行完成后生成 `memory_write_candidate`
6. 达到阈值时做压缩，写入 `summary.json`
7. 若请求是恢复型请求，则从 `resume_state.json` 恢复

#### 7.2.4 v1 不做的事

- 不直接把所有 tool output 原封不动写进长期 memory
- 不把会话中的上传路径和临时文件路径写进长期 memory
- 不把 memory 当数据库替代品

#### 7.2.5 在各仓库中的落点

`fbbp-research-workbench` 新增：

- `configs/control_plane/memory_policy.yaml`
- `scripts/control_plane/memory_adapter.py`
- `scripts/control_plane/resume.py`
- `scripts/control_plane/artifacts.py`

`fbbp-research-workbench` 更新：

- `configs/agents/fbbp-assistant/memory.json`

`upstream-deerflow` 复用，不作为 v1 主改动点：

- `backend/src/agents/middlewares/memory_middleware.py`
- `backend/src/agents/memory/updater.py`
- `backend/src/gateway/routers/memory.py`

#### 7.2.6 v1 验收标准

- 同一 `thread_id` 的后续请求能命中上次摘要
- 中断的 formal 或 interactive 请求可基于 `resume_state.json` 恢复
- `memory.json` 不再是空壳
- 每次运行都能记录 memory 是否命中、写入是否成功、是否触发压缩

### 7.3 A2A adapter

#### 7.3.1 目标

v1 的 A2A 目标不是一开始就做外部标准协议，而是先做内部统一 envelope，让主 agent、子执行器、formal runner、MiniMind worker 的通信都有同一张“交接单”。

#### 7.3.2 v1 A2A 定位

v1 A2A adapter 负责：

- 统一消息契约
- 统一 `trace_id`
- 统一 `correlation_id`
- 统一 `parent_run_id / child_run_id`
- 统一 `hop`
- 统一 `request / result / error` 生命周期
- 统一输入输出 artifact 链接

v1 A2A adapter 不负责：

- 取代上游 DeerFlow subagent runtime
- 提供完整外部标准 Agent2Agent 协议网关
- 提供远程 worker 队列、自动重试、死信队列
- 直接改造你的数据库 schema

#### 7.3.3 v1 envelope

推荐契约文件：

- `configs/control_plane/a2a.schema.json`

推荐最小 lifecycle envelope：

```json
{
  "schema_version": "fbbp.a2a.envelope.v1",
  "message_id": "a2a_xxx",
  "correlation_id": "a2ac_xxx",
  "message_type": "child_run_request",
  "phase": "requested",
  "trace_id": "trace_xxx",
  "parent_run_id": "20260430_193610_formal_case_4f6f2fd4",
  "child_run_id": "20260430_193611_fbbp_source_provenance_review_01",
  "hop_index": 1,
  "hop_path": [
    "20260430_193610_formal_case_4f6f2fd4",
    "20260430_193611_fbbp_source_provenance_review_01"
  ],
  "source_agent": "fbbp-control-plane",
  "target_agent": "formal_case",
  "target_executor": "run_fbbp_formal_case.py",
  "target_executor_mode": "direct_python_source_preflight",
  "route": "formal_case",
  "status": "requested",
  "input_ref": "configs/formal_cases/fbbp_source_provenance_review_01.yaml",
  "payload_ref": null,
  "artifact_ref": null,
  "error": null
}
```

同一 child 完成后，会使用同一个 `correlation_id` 追加 result envelope：

```json
{
  "schema_version": "fbbp.a2a.envelope.v1",
  "message_id": "a2a_yyy",
  "correlation_id": "a2ac_xxx",
  "message_type": "child_run_result",
  "phase": "completed",
  "trace_id": "trace_xxx",
  "parent_run_id": "20260430_193610_formal_case_4f6f2fd4",
  "child_run_id": "20260430_193611_fbbp_source_provenance_review_01",
  "hop_index": 1,
  "source_agent": "fbbp-control-plane",
  "target_agent": "formal_case",
  "target_executor": "run_fbbp_formal_case.py",
  "route": "formal_case",
  "status": "succeeded",
  "input_ref": "configs/formal_cases/fbbp_source_provenance_review_01.yaml",
  "payload_ref": "runs/control_plane/.../children/formal_case_output.json",
  "artifact_ref": "runs/control_plane/.../children/formal_case_runtime/...",
  "error": null
}
```

#### 7.3.4 parent/child 规则

- interactive 顶层请求生成 `parent_run_id`
- 若调用 MiniMind worker、formal runner、batch runner、子工具任务，则各自产生 `child_run_id`
- `hop=0` 表示顶层 run
- `hop_index>=1` 表示被委派的子执行
- `a2a_trace.json.hop_count` 是该次 control-plane run 的可回放子任务跳数
- `a2a_trace.json.envelope_count` 是可回放 A2A 消息数，通常大于或等于 `hop_count`
- 同一 child lifecycle 的 request/result/error 必须共享同一个 `correlation_id`

#### 7.3.5 sync/async 规则

- interactive -> 同步/流式
- formal_case -> 异步 child run，但父记录保持跟踪
- batch_eval -> 异步 batch parent + 多个 case child run

#### 7.3.6 在各仓库中的落点

`fbbp-research-workbench` 已新增：

- `configs/control_plane/a2a.schema.json`
- `scripts/control_plane/a2a.py`
- `scripts/control_plane/run_record.py` 中的 `metrics.a2a_hop_count`、`metrics.a2a_envelope_count` 与 `metrics.child_success_rate`
- `scripts/run_fbbp_control_plane.py` 中的 `a2a_trace.json` / `children.json.a2a_envelopes` 写入

`fbbp-mcp-rag-server` 后续更新：

- `src/fbbp_mcp_server/schemas.py`
- `src/fbbp_mcp_server/service.py`

目标是让请求和响应中能够透传或回填：

- `trace_id`
- `parent_run_id`
- `child_run_id`
- `origin_route`

`upstream-deerflow` 复用：

- `backend/src/subagents/executor.py`
- `backend/src/tools/builtins/task_tool.py`

#### 7.3.7 v1 验收标准

- 任意子执行都能追溯到父 run
- formal run 的 `trace_id`、`parent_run_id`、`child_run_id`、`hop_index` 已可回放
- 每个 formal child run 至少有 `child_run_request` 与 `child_run_result` 两条 envelope
- 同一个 child lifecycle 的 request/result/error 共享 `correlation_id`
- child 失败时，父记录能明确知道是哪个 hop 出错
- child 失败时，A2A envelope 使用 `message_type=child_run_error`，并带 `phase=error` 与 `error` payload
- `run_record.metrics.a2a_hop_count`、`run_record.metrics.a2a_envelope_count` 与 `run_record.metrics.child_success_rate` 可直接被 eval 读取

### 7.4 统一观测 + agent eval

#### 7.4.1 目标

把当前分散在 RAG、MCP、formal outputs、benchmark reports 里的观测数据收束成单条 run 的可审计记录。

#### 7.4.2 v1 统一 run record

推荐主文件：

- `runs/control_plane/<run_id>/run_record.json`

推荐辅助文件：

- `runs/control_plane/<run_id>/events.jsonl`
- `runs/control_plane/<run_id>/judge.json`
- `runs/control_plane/<run_id>/children.json`

推荐最小字段：

```json
{
  "run_id": "cp_20260426_xxx",
  "parent_run_id": null,
  "trace_id": "trace_20260426_xxx",
  "mode": "interactive",
  "primary_route": "private_rag",
  "secondary_capabilities": ["candidate_query_compile", "public_validation"],
  "forced_primary_route": false,
  "status": "succeeded",
  "timings_ms": {
    "routing": 12.4,
    "execution": 2511.8,
    "reporting": 45.2,
    "total": 2569.4
  },
  "tools": {
    "requested": 4,
    "succeeded": 4,
    "failed": 0
  },
  "memory": {
    "read_hit": true,
    "write_status": "queued",
    "resume_used": false
  },
  "preflight": {
    "attempted": true,
    "hit": true,
    "mode": "source_provenance",
    "data_source": "file_source_registry",
    "hit_rate": 1.0
  },
  "judge": {
    "score": 0.84,
    "status": "pass"
  },
  "metrics": {
    "route": "formal_case",
    "tool_success_rate": 1.0,
    "memory_hit": true,
    "latency_ms": 37901.87,
    "estimated_cost_usd": 0.0,
    "cost_tracked": false,
    "judge_score": 0.8,
    "preflight_hit": true,
    "preflight_hit_rate": 1.0,
    "a2a_hop_count": 1,
    "a2a_envelope_count": 2,
    "a2a_schema_version": "fbbp.a2a.envelope.v1",
    "child_success_rate": 1.0
  },
  "a2a": {
    "schema_version": "fbbp.a2a.envelope.v1",
    "trace_id": "trace_xxx",
    "hop_count": 1,
    "envelope_count": 2
  }
}
```

#### 7.4.3 v1 数据来源

统一 run record 由以下来源汇总而成：

`llm-rag-knowledge-base`

- route info
- planner diagnostics
- quality checks
- monitoring summary
- latency details

`fbbp-mcp-rag-server`

- tool contract version
- provenance
- per-tool diagnostics
- `latency_ms`
- health snapshot

`fbbp-research-workbench`

- parent/child run mapping
- formal outputs
- `report.json`
- `evidence.json`
- `tool_calls.jsonl`
- `preflight` 命中信息
- `metrics` 汇总块

`llm-eval-benchmark`

- summary
- category breakdown
- leaderboard
- CI95
- uplift
- control-plane-level pass/fail judge

#### 7.4.4 v1 指标集合

v1 统一指标包括：

- `primary_route`
- `secondary_capabilities`
- `force_primary_route`
- `tool_success_rate`
- `tool_failure_count`
- `memory_hit_rate`
- `resume_success_rate`
- `latency_ms`
- `estimated_cost_usd`
- `judge_score`
- `judge_status`
- `preflight_hit_rate`
- `preflight_data_source`
- `a2a_hop_count`
- `a2a_envelope_count`
- `child_success_rate`
- `a2a_schema_version`
- `child_run_count`
- `route_override_rate`

#### 7.4.5 在各仓库中的落点

`fbbp-research-workbench` 新增：

- `configs/control_plane/observability.yaml`
- `configs/control_plane/judges.yaml`
- `scripts/control_plane/run_record.py`
- `scripts/control_plane/observability.py`
- `scripts/control_plane/judge.py`
- `scripts/control_plane/costs.py`

`llm-rag-knowledge-base` 更新：

- `src/ragkb/service.py`
- `src/ragkb/quality/deepchecks.py`
- 可选 `src/ragkb/api.py`

`fbbp-mcp-rag-server` 更新：

- `src/fbbp_mcp_server/schemas.py`
- `src/fbbp_mcp_server/service.py`
- `src/fbbp_mcp_server/health.py`

`llm-eval-benchmark` 新增：

- `pipelines/control_plane_eval.py`
- `metrics/control_plane_metrics.py`
- `docs/control_plane_eval_protocol_cn.md`

#### 7.4.6 v1 验收标准

- 每次 run 都有统一 `run_record.json`
- 每次 run 都能回看 route、tools、memory、latency、cost、judge、preflight
- 每次 run 的 `metrics` 块都能直接读到 `tool_success_rate`、`memory_hit`、`latency_ms`、`estimated_cost_usd`、`judge_score`、`preflight_hit_rate`
- 每次含子任务的 run 都能直接读到 `a2a_hop_count`、`a2a_envelope_count` 和 `child_success_rate`
- formal/batch 能生成 parent/child 汇总
- `llm-eval-benchmark` 能从 run record 直接产出 control-plane summary

## 8. 文件与目录设计

### 8.1 `fbbp-research-workbench` 新增目录建议

```text
fbbp-research-workbench/
  configs/
    control_plane/
      routes.yaml
      secondary_capabilities.yaml
      memory_policy.yaml
      observability.yaml
      judges.yaml
      a2a.schema.json
  scripts/
    control_plane/
      __init__.py
      request_parser.py
      router.py
      executor_registry.py
      run_record.py
      observability.py
      memory_adapter.py
      resume.py
      a2a.py
      judge.py
      costs.py
      artifacts.py
      reporting.py
    run_fbbp_control_plane.py
  runs/
    control_plane/
  tests/
    control_plane/
```

### 8.2 `llm-rag-knowledge-base` 新增目录建议

```text
llm-rag-knowledge-base/
  src/ragkb/retrieval/
    query_plan_adapter.py
```

### 8.3 `fbbp-mcp-rag-server` 重点调整文件

```text
fbbp-mcp-rag-server/
  src/fbbp_mcp_server/
    schemas.py
    service.py
    health.py
```

### 8.4 `llm-eval-benchmark` 新增目录建议

```text
llm-eval-benchmark/
  pipelines/
    control_plane_eval.py
  metrics/
    control_plane_metrics.py
  docs/
    control_plane_eval_protocol_cn.md
  reports/
    control_plane_latest/
```

### 8.5 `minimind-fbtp-lab` 新增目录建议

```text
minimind-fbtp-lab/
  query_compiler/
    worker.py
    output_contract.py
  scripts/
    run_query_compiler.py
```

## 9. 分阶段实施顺序

### Phase 1: 搭骨架，不改执行主链

目标：

- 建立产品层统一入口
- 建立 route decision 文件
- 建立统一 run record 基础结构
- 不替换现有 formal/batch/private_rag 执行器

主仓库改动：

`fbbp-research-workbench`

- 新增 `configs/control_plane/`
- 新增 `scripts/control_plane/`
- 新增 `scripts/run_fbbp_control_plane.py`

复用现有执行器：

- `scripts/query_private_rag.py`
- `scripts/run_fbbp_formal_case.py`
- `scripts/run_fbbp_formal_batch.py`
- `scripts/deerflow_embedded_runner.py`

交付物：

- `run_request.json`
- `route_decision.json`
- `run_record.json`
- `events.jsonl`

验收：

- 能从一个统一脚本进入 control plane
- 能把请求稳定路由到现有执行器
- 每次都落文件

### Phase 2: 落地 intent router

目标：

- 补全 `private_rag / public_lookup / formal_case / batch_eval / report_generation / fallback_general`
- 支持 `primary_route + secondary_capabilities`
- 支持 `force_primary_route`

主仓库改动：

`fbbp-research-workbench`

- `scripts/control_plane/router.py`
- `configs/control_plane/routes.yaml`
- `configs/control_plane/secondary_capabilities.yaml`

协同改动：

`llm-rag-knowledge-base`

- `src/ragkb/service.py`
- `src/ragkb/retrieval/query_plan_adapter.py`

`minimind-fbtp-lab`

- `query_compiler/worker.py`

验收：

- private_rag 请求能直接进私有检索链
- formal/batch 输入能稳定进对应 runner
- 请求可附带次级能力
- route 决策有明确理由字段

### Phase 3: 落地 memory 闭环

目标：

- 让 memory 真正可读、可写、可压缩、可恢复

主仓库改动：

`fbbp-research-workbench`

- `scripts/control_plane/memory_adapter.py`
- `scripts/control_plane/resume.py`
- `configs/control_plane/memory_policy.yaml`
- 更新 `configs/agents/fbbp-assistant/memory.json`

复用上游：

- `upstream-deerflow/backend/src/agents/middlewares/memory_middleware.py`
- `upstream-deerflow/backend/src/agents/memory/updater.py`
- `upstream-deerflow/backend/src/gateway/routers/memory.py`

验收：

- 会话连续两轮后 memory 能命中
- 中断运行可从 `resume_state.json` 恢复
- 长期 memory 和 working memory 分层明确

### Phase 4: 落地 A2A adapter

目标：

- 用内部统一 envelope 管理 parent/child 任务
- 先统一内部契约，再考虑外部标准协议
- 明确区分“内部 A2A lifecycle 已完成”和“外部标准 A2A/远程 worker 还未完成”

主仓库改动：

`fbbp-research-workbench`

- `scripts/control_plane/a2a.py`
- `configs/control_plane/a2a.schema.json`
- `scripts/control_plane/run_record.py`
- `scripts/control_plane/observability.py`

协同改动：

`fbbp-mcp-rag-server`

- `src/fbbp_mcp_server/schemas.py`
- `src/fbbp_mcp_server/service.py`

验收：

- 任意 child execution 都能回指 parent
- trace_id 可贯穿工具和子执行
- 每个 child hop 至少有 `child_run_request` 与 `child_run_result`，失败时有 `child_run_error`
- 同一 child lifecycle 共享 `correlation_id`
- `children.json` 与 `a2a_trace.json` 可回放整个执行链
- `run_record.metrics.a2a_hop_count`、`run_record.metrics.a2a_envelope_count`、`run_record.metrics.child_success_rate` 可被 eval 读取

### Phase 4B: A2A 产品化硬化

目标：

- 把内部 A2A envelope 升级为可被外部 worker/agent 使用的任务协议
- 支持长任务排队、失败自动重试、多次失败后进入死信队列

主仓库已新增：

`fbbp-research-workbench`

- `scripts/control_plane/a2a_gateway.py`
- `scripts/control_plane/worker_queue.py`
- `scripts/control_plane/auth.py`
- `scripts/control_plane/push_notifications.py`
- `scripts/control_plane/queue_backends.py`
- `configs/control_plane/worker_queue.yaml`
- `runs/control_plane/dead_letters/`

v1 已支持的协议入口：

- `GET /.well-known/agent-card.json` 获取 Agent Card
- `POST /a2a` 使用 JSON-RPC，支持 `message/send`、`tasks/get`、`tasks/cancel`、`tasks/list`
- `POST /a2a` 使用 JSON-RPC，支持 `message/stream`、`tasks/resubscribe`
- `POST /a2a` 使用 JSON-RPC，支持 `tasks/pushNotificationConfig/set`、`tasks/pushNotificationConfig/get`
- `POST /message:send` 使用 HTTP+JSON 提交任务
- `POST /message:stream` 使用 SSE 返回 task/status/artifact 事件
- `POST /a2a/tasks` 创建任务，输入为 A2A request envelope 或 message
- `GET /a2a/tasks/{task_id}` 查询任务状态
- `POST /a2a/tasks/claim` 外部 worker 领取任务
- `POST /a2a/tasks/{task_id}/result` 回填 result envelope 或 artifact
- `POST /a2a/tasks/{task_id}/fail` 记录失败并触发 retry/dead letter
- `GET /a2a/events?trace_id=...` 查询同一 trace 的事件流

验收：

- 外部 worker 不直接 import workbench 代码，也能领取任务并回填结果
- formal/batch child run 可进入队列执行
- 可配置 `max_attempts`、`backoff_seconds`、`retryable_errors`
- 超过重试次数的任务进入 `dead_letters`
- dead letter 中保留原始 envelope、失败原因、attempts、最后一次 artifact 路径
- `Authorization: Bearer <key>` 或 `X-A2A-API-Key` 可保护 gateway
- Agent Card 声明 `streaming=true`、`pushNotifications=true`
- `queue_health.backend_status` 能显示 file/redis/postgres backend 可用性
- `tests/test_control_plane_worker_queue.py` 覆盖 create/claim/complete/retry/dead letter
- `tests/test_control_plane_a2a_gateway.py` 覆盖 Agent Card、JSON-RPC `message/send`、`tasks/get`、REST claim/result/events、streaming、push config、auth

### Phase 5: 落地统一观测 + agent eval

目标：

- 把 route、tool、memory、latency、cost、judge 汇总到一条 run record
- 让 benchmark repo 直接消费 control-plane artifacts

主仓库改动：

`fbbp-research-workbench`

- `scripts/control_plane/observability.py`
- `scripts/control_plane/judge.py`
- `configs/control_plane/observability.yaml`
- `configs/control_plane/judges.yaml`

协同改动：

`llm-rag-knowledge-base`

- `src/ragkb/service.py`
- `src/ragkb/quality/deepchecks.py`

`fbbp-mcp-rag-server`

- `src/fbbp_mcp_server/health.py`
- `src/fbbp_mcp_server/service.py`

`llm-eval-benchmark`

- `pipelines/control_plane_eval.py`
- `metrics/control_plane_metrics.py`

验收：

- `llm-eval-benchmark` 可从 `runs/control_plane/**/run_record.json` 直接生成 summary
- 有 route breakdown、tool success rate、memory hit、latency、cost、judge score

### Phase 6: 把 MiniMind 作为正式次级能力接入

目标：

- 把 query compiler 作为 `candidate_query_compile` 次级能力接入
- 先规则版，后模型版

主仓库改动：

`minimind-fbtp-lab`

- `query_compiler/worker.py`
- `query_compiler/output_contract.py`

协同改动：

`fbbp-research-workbench`

- `scripts/control_plane/executor_registry.py`
- `configs/control_plane/secondary_capabilities.yaml`

`llm-rag-knowledge-base`

- `src/ragkb/retrieval/query_plan_adapter.py`

验收：

- 自然语言候选筛选请求可先编译再执行
- 编译出的 plan 能被 `ragkb` 消化
- 失败时可退回 rule baseline 或普通 private_rag

## 10. 每一步对应到具体目录、脚本、配置文件

### Step 1: 建 control plane 主入口

新增：

- `fbbp-research-workbench/configs/control_plane/routes.yaml`
- `fbbp-research-workbench/configs/control_plane/secondary_capabilities.yaml`
- `fbbp-research-workbench/scripts/control_plane/router.py`
- `fbbp-research-workbench/scripts/control_plane/executor_registry.py`
- `fbbp-research-workbench/scripts/control_plane/run_record.py`
- `fbbp-research-workbench/scripts/run_fbbp_control_plane.py`

复用：

- `fbbp-research-workbench/scripts/query_private_rag.py`
- `fbbp-research-workbench/scripts/run_fbbp_formal_case.py`
- `fbbp-research-workbench/scripts/run_fbbp_formal_batch.py`
- `fbbp-research-workbench/scripts/deerflow_embedded_runner.py`

### Step 2: 把 private_rag 和 MiniMind 接起来

新增：

- `llm-rag-knowledge-base/src/ragkb/retrieval/query_plan_adapter.py`
- `minimind-fbtp-lab/query_compiler/worker.py`
- `minimind-fbtp-lab/query_compiler/output_contract.py`

更新：

- `llm-rag-knowledge-base/src/ragkb/service.py`
- `fbbp-research-workbench/scripts/control_plane/executor_registry.py`

### Step 3: 把 memory 变成业务闭环

新增：

- `fbbp-research-workbench/scripts/control_plane/memory_adapter.py`
- `fbbp-research-workbench/scripts/control_plane/resume.py`
- `fbbp-research-workbench/configs/control_plane/memory_policy.yaml`

更新：

- `fbbp-research-workbench/configs/agents/fbbp-assistant/memory.json`

复用：

- `upstream-deerflow/backend/src/agents/memory/updater.py`
- `upstream-deerflow/backend/src/gateway/routers/memory.py`

### Step 4: 把 A2A envelope 接入工具和子执行

新增：

- `fbbp-research-workbench/scripts/control_plane/a2a.py`
- `fbbp-research-workbench/configs/control_plane/a2a.schema.json`

更新：

- `fbbp-mcp-rag-server/src/fbbp_mcp_server/schemas.py`
- `fbbp-mcp-rag-server/src/fbbp_mcp_server/service.py`

复用：

- `upstream-deerflow/backend/src/subagents/executor.py`
- `upstream-deerflow/backend/src/tools/builtins/task_tool.py`

### Step 5: 做统一观测和统一 agent eval

新增：

- `fbbp-research-workbench/scripts/control_plane/observability.py`
- `fbbp-research-workbench/scripts/control_plane/judge.py`
- `llm-eval-benchmark/pipelines/control_plane_eval.py`
- `llm-eval-benchmark/metrics/control_plane_metrics.py`

更新：

- `llm-rag-knowledge-base/src/ragkb/quality/deepchecks.py`
- `llm-rag-knowledge-base/src/ragkb/service.py`
- `fbbp-mcp-rag-server/src/fbbp_mcp_server/health.py`

## 11. 推荐的 v1 输出契约

每次 control-plane run 至少输出：

```text
runs/control_plane/<run_id>/
  run_request.json
  route_decision.json
  run_record.json
  events.jsonl
  judge.json
  children.json
  memory/
    session_memory.json
    summary.json
    resume_state.json
```

formal child run 继续保留已有产物：

- `report.json`
- `report.md`
- `evidence.json`
- `tool_calls.jsonl`

batch child run 继续保留已有产物：

- `batch_results.json`
- `formal_scoreboard.json`
- `key_metrics_snapshot.json`

## 12. v1 需要优先避免的风险

### 12.1 不要把 control plane 做成第二套 DeerFlow

控制面只做：

- 统一入口
- 统一判路
- 统一记录
- 统一观测

不做：

- 新的底层 agent runtime
- 新的数据库
- 新的 formal runner

### 12.2 不要让 MiniMind 抢主角

MiniMind 在 v1 是次级能力：

- 是 `candidate_query_compile`
- 不是主路由器
- 不是 A2A 主体
- 不是正式产品入口

### 12.3 不要把 memory 变成杂物堆

长期 memory 只放稳定信息。

运行态文件、tool 原始输出、临时路径、上传路径，不进入长期 memory。

### 12.4 不要在 Phase 1 先改上游

Phase 1 只在产品层包一层。

只有产品层真的表达不了的能力，才进入上游补丁讨论。

## 13. 第一批实际实施任务

如果按施工顺序排，建议先做下面 12 个任务：

1. 在 `fbbp-research-workbench/configs/` 下创建 `control_plane/`
2. 写 `routes.yaml` 和 `secondary_capabilities.yaml`
3. 写 `scripts/control_plane/router.py`
4. 写 `scripts/control_plane/executor_registry.py`
5. 写 `scripts/control_plane/run_record.py`
6. 写统一 CLI 入口 `scripts/run_fbbp_control_plane.py`
7. 先把 `private_rag / formal_case / batch_eval / fallback_general` 接起来
8. 写 `memory_adapter.py`，先把长期 memory 和 working memory 分层
9. 写 `a2a.py`，先统一 envelope，不先做外部标准协议
10. 在 `llm-eval-benchmark` 写 `control_plane_eval.py`，把 run record 吃进去
11. 写 `worker_queue.py`，把 formal/batch child run 变成可排队任务
12. 写 `a2a_gateway.py`，把内部 envelope 暴露给外部 worker/agent

## 14. 当前可立即执行的验证命令

以下命令假设当前工作目录为 `<local_path_removed>

### 14.1 启动当前 workbench

```powershell
powershell -ExecutionPolicy Bypass -File .\fbbp-research-workbench\scripts\launch_fbbp_workbench.ps1
```

### 14.2 验证当前 private RAG 链路

```powershell
python .\fbbp-research-workbench\scripts\query_private_rag.py --query "knottin scaffold landscape" --top-k 5
```

### 14.3 验证当前 formal case 链路

```powershell
python .\fbbp-research-workbench\scripts\run_fbbp_formal_case.py --case-path .\fbbp-research-workbench\configs\formal_cases\fbbp_knottin_landscape_01.yaml
```

### 14.4 验证当前 formal batch 链路

```powershell
python .\fbbp-research-workbench\scripts\run_fbbp_formal_batch.py --batch-path .\fbbp-research-workbench\configs\formal_batches\weekly_validation_batch.yaml
```

### 14.5 验证当前 benchmark 链路

```powershell
cd .\llm-eval-benchmark
python -m pipelines.compare --data-path data/fbtp_eval.jsonl --output-dir reports/control_plane_smoke --eval-mode auto
```

### 14.6 Phase 1 完成后的 control plane 目标命令

```powershell
python .\fbbp-research-workbench\scripts\run_fbbp_control_plane.py --mode interactive --query "总结 knottin scaffold 的私有证据"
python .\fbbp-research-workbench\scripts\run_fbbp_control_plane.py --mode formal --case-path .\fbbp-research-workbench\configs\formal_cases\fbbp_knottin_landscape_01.yaml
python .\fbbp-research-workbench\scripts\run_fbbp_control_plane.py --mode batch --batch-path .\fbbp-research-workbench\configs\formal_batches\weekly_validation_batch.yaml
```

### 14.7 Phase 3 完成后的 memory 验收目标命令

```powershell
python .\fbbp-research-workbench\scripts\run_fbbp_control_plane.py --mode interactive --thread-id demo-memory-001 --query "先记住我现在在做 FBBP control plane"
python .\fbbp-research-workbench\scripts\run_fbbp_control_plane.py --mode interactive --thread-id demo-memory-001 --query "我刚才在做什么？"
```

### 14.8 Source provenance preflight + metrics 验收命令

这条命令用于验证 `list_sources -> get_source_summary` provenance case 是否能在 control plane 中短路成功，并把 `preflight` 与 `metrics` 写入统一 run record。

```powershell
rtk python .\fbbp-research-workbench\scripts\run_fbbp_control_plane.py --mode formal --case-path .\fbbp-research-workbench\configs\formal_cases\fbbp_source_provenance_review_01.yaml --output-dir .\fbbp-research-workbench\runs\control_plane\source_provenance_preflight_metrics_smoke
```

期望结果：

- `run_record.json` 中 `preflight.hit=true`
- `run_record.json` 中 `preflight.mode=source_provenance`
- `run_record.json` 中 `metrics.tool_success_rate=1.0`
- `run_record.json` 中 `metrics.preflight_hit_rate=1.0`
- `tool_calls.jsonl` 中包含 1 次 `list_sources` 和若干次 `get_source_summary`
- PostgreSQL 不可用时允许 `preflight.data_source=file_source_registry`，这表示已走文件优先 fallback

### 14.9 A2A lifecycle envelope 验收命令

这条命令用于验证 formal child run 是否被包装为统一 A2A lifecycle envelope，并同时写入 `a2a_trace.json`、`children.json.a2a_envelopes`、`run_record.json.a2a` 和 `observability.json.a2a`。

```powershell
rtk python .\fbbp-research-workbench\scripts\run_fbbp_control_plane.py --mode formal --case-path .\fbbp-research-workbench\configs\formal_cases\fbbp_source_provenance_review_01.yaml --output-dir .\fbbp-research-workbench\runs\control_plane\a2a_lifecycle_source_provenance_smoke
```

期望结果：

- `a2a_trace.json` 中 `schema_version=fbbp.a2a.envelope.v1`
- `a2a_trace.json` 中 `hop_count=1`
- `a2a_trace.json` 中 `envelope_count=2`
- `a2a_trace.json.envelopes[0].message_type=child_run_request`
- `a2a_trace.json.envelopes[1].message_type=child_run_result`
- 同一 child lifecycle 的两条 envelope 拥有相同 `correlation_id`
- `children.json` 中存在 `a2a_envelopes`
- envelope 中包含 `trace_id / parent_run_id / child_run_id / hop_index`
- envelope 中包含 `source_agent=fbbp-control-plane`
- envelope 中包含 `target_executor` 与 `artifact_ref`
- `run_record.json.metrics.a2a_hop_count=1`
- `run_record.json.metrics.a2a_envelope_count=2`
- `run_record.json.metrics.child_success_rate=1.0`
- `observability.json.a2a.envelope_count=2`

### 14.10 A2A gateway + worker queue + retry + dead letter 验收命令

这条命令用于验证 A2A 产品化 v1：外部 gateway、SSE streaming、push notification config、API key auth、worker queue、自动重试、死信队列和 backend health。

```powershell
rtk python -m pytest .\fbbp-research-workbench\tests\test_control_plane_a2a_gateway.py .\fbbp-research-workbench\tests\test_control_plane_worker_queue.py -q
```

期望结果：

- Agent Card 能声明 JSON-RPC 与 HTTP+JSON 接口
- Agent Card 能声明 `streaming=true` 与 `pushNotifications=true`
- `message/send` 能创建 queued task
- `message/stream` 能返回 SSE event payload
- `tasks/get` 能查询 task
- `tasks/pushNotificationConfig/set/get` 能保存和读取 webhook 配置
- `Authorization: Bearer` 与 `X-A2A-API-Key` 能通过认证校验
- `POST /a2a/tasks/claim` 能让外部 worker 领取任务
- `POST /a2a/tasks/{task_id}/result` 能完成任务并回填 artifact
- `fail_task()` 在未超过 `max_attempts` 时自动回到 pending
- 超过 `max_attempts` 后写入 `runs/control_plane/dead_letters/`
- `queue_health.backend_status` 能报告 file/redis/postgres 后端状态

如果要本地启动 gateway：

```powershell
rtk python .\fbbp-research-workbench\scripts\control_plane\a2a_gateway.py --host 127.0.0.1 --port 8765
```

如果要开启 API key 认证：

```powershell
$env:FBBP_A2A_API_KEY="your-local-api-key"
rtk python .\fbbp-research-workbench\scripts\control_plane\a2a_gateway.py --host 127.0.0.1 --port 8765
```

如果要切换 Postgres 队列后端：

```powershell
$env:FBBP_A2A_POSTGRES_DSN="postgresql://user:password@localhost:5432/fbbp?connect_timeout=5"
rtk python .\fbbp-research-workbench\scripts\control_plane\probe_postgres_queue.py --host-override localhost --connect-timeout 5
# 只有探针返回 ok=true 后，才把 configs/control_plane/worker_queue.yaml 的 queue_backend 改成 postgres
# 可参考 configs/control_plane/worker_queue.postgres.example.yaml，不要把真实密码写入仓库
```

当前这台 Windows 机器的实测结论：

- Windows -> WSL PostgreSQL localhost bridge 已修复，`repair_wsl_postgres_bridge.ps1 -Json` 返回 `ok=true`
- `private_rag_pg_repair_live_v2` 已验证 `private_rag` live 路径恢复，`status=succeeded`、`result_count=2`、`tool_success_rate=1.0`
- `start_wsl_pgvector.ps1` 仍是常规启动入口；如果 Windows 侧再次访问不稳，先运行 `repair_wsl_postgres_bridge.ps1 -Json`
- 默认队列仍保持 `queue_backend: file`，因为 A2A worker queue 不必依赖数据库；如需切 Postgres 队列，仍应先用 `probe_postgres_queue.py` 验证
- 本阶段不要为了切换队列而开放 `0.0.0.0:5432`，除非明确做防火墙、认证和访问范围评估

修复 Windows -> WSL PostgreSQL bridge：

```powershell
rtk powershell -NoProfile -ExecutionPolicy Bypass -File .\fbbp-research-workbench\scripts\repair_wsl_postgres_bridge.ps1 -Json
```

期望结果：

- `ok=true`
- `tcp_ready=true`
- `query_ready=true`
- `wsl_reachable=true`
- `portproxy_empty=true`

如果要切换 Redis 队列后端：

```powershell
$env:FBBP_A2A_REDIS_URL="redis://localhost:6379/0"
# 然后把 configs/control_plane/worker_queue.yaml 的 queue_backend 改成 redis
```

### 14.11 public_lookup + project links + local worker daemon 验收命令

这组命令用于验证“公开资料查询不再只是 fallback”，以及 workbench 和其他项目之间的连接是否已经写入 control plane。

```powershell
rtk python -m pytest .\fbbp-research-workbench\tests\test_control_plane_project_links.py .\fbbp-research-workbench\tests\test_control_plane_executor.py .\fbbp-research-workbench\tests\test_control_plane_worker_daemon.py -q
```

期望结果：

- `project_links.yaml` 能解析到 `fbbp-research-workbench / fbbp-mcp-rag-server / llm-rag-knowledge-base / llm-eval-benchmark / minimind-fbtp-lab`
- `public_lookup` 能识别 PubMed、UniProt accession、PDB id
- `public_lookup` 执行器直接调用 `fbbp-mcp-rag-server` tool plane，不再委派给 DeerFlow fallback
- `worker_daemon.py` 能从 A2A queue claim 任务，调用统一入口执行，再把 artifact 写回任务

只验证路由、不碰外网时使用：

```powershell
rtk python .\fbbp-research-workbench\scripts\run_fbbp_control_plane.py --dry-run --query "查 PubMed 文献并核验 UniProt P12345 和 PDB 1ABC" --output-dir .\fbbp-research-workbench\runs\control_plane\public_lookup_dry_run_v1
```

本机启动 worker daemon：

```powershell
rtk python .\fbbp-research-workbench\scripts\control_plane\worker_daemon.py --worker-id local-control-plane-worker --poll-seconds 2
```

### 14.12 live e2e + MiniMind secondary + eval dashboard 验收命令

这组命令用于验证最后四个 v1 工程化闭环：A2A live e2e、真实 public lookup、MiniMind secondary capability、跨 run eval dashboard。

完整测试：

```powershell
rtk python -m pytest .\fbbp-research-workbench\tests\test_control_plane_live_e2e.py .\fbbp-research-workbench\tests\test_control_plane_eval_dashboard.py .\fbbp-research-workbench\tests\test_control_plane_executor.py -q
```

live e2e：

```powershell
rtk python .\fbbp-research-workbench\scripts\control_plane\live_e2e.py --output-root .\fbbp-research-workbench\runs\control_plane\live_e2e_v1
```

期望结果：

- `live_e2e_summary.json.ok=true`
- `queue_state=completed`
- `task_status=TASK_STATE_COMPLETED`
- worker artifact metadata 中有 `run_dir`
- 对应 `run_record.json.status=succeeded`

真实 public lookup：

```powershell
rtk python .\fbbp-research-workbench\scripts\run_fbbp_control_plane.py --force-primary-route public_lookup --query "PubMed knottin binder UniProt P69905 PDB 1CRN" --top-k 2 --output-dir .\fbbp-research-workbench\runs\control_plane\public_lookup_live_v2
rtk python .\fbbp-research-workbench\scripts\run_fbbp_control_plane.py --force-primary-route public_lookup --query "knottin peptide inhibitor" --top-k 2 --output-dir .\fbbp-research-workbench\runs\control_plane\public_lookup_pubmed_live_v2
```

期望结果：

- `public_lookup_live_v2` 中 `search_pubmed / get_uniprot_entry / get_pdb_entry` 均成功
- `public_lookup_live_v2.run_record.metrics.tool_success_rate=1.0`
- `public_lookup_pubmed_live_v2.children.public_lookup_output.summary.article_count=2`

MiniMind secondary capability：

```powershell
rtk python .\fbbp-research-workbench\scripts\run_fbbp_control_plane.py --force-primary-route report_generation --secondary-capability candidate_query_compile --query "筛选 knottin 有实验亲和力 前 2" --report-json .\fbbp-research-workbench\runs\control_plane\live_e2e_v1\input_report.json --top-k 2 --output-dir .\fbbp-research-workbench\runs\control_plane\minimind_secondary_live_v2
```

期望结果：

- `candidate_query_compile_output.json.project=minimind-fbtp-lab`
- `candidate_query_compile_output.json.validator_trace.schema_ok=true`
- `candidate_query_compile_output.json.execution.metadata.filtered_count=310`
- `run_record.child_runs` 包含 `secondary:candidate_query_compile`

eval dashboard：

```powershell
rtk python .\fbbp-research-workbench\scripts\control_plane\eval_dashboard.py --input-root .\fbbp-research-workbench\runs\control_plane --output-root .\llm-eval-benchmark\reports\control_plane_dashboard\latest
```

期望输出：

- `llm-eval-benchmark/reports/control_plane_dashboard/latest/summary.json`
- `llm-eval-benchmark/reports/control_plane_dashboard/latest/runs.csv`
- `llm-eval-benchmark/reports/control_plane_dashboard/latest/summary.md`

### 14.13 一键 readiness check

这条命令用于一键确认 control plane 当前是否处于可演示状态。默认检查 PostgreSQL bridge、A2A live e2e、MiniMind secondary capability 和 eval dashboard；如果要顺便跑较慢的真实 private/public live checks，可以加参数。

```powershell
rtk python .\fbbp-research-workbench\scripts\control_plane\readiness_check.py --output-root .\fbbp-research-workbench\runs\control_plane\readiness\latest
```

完整 live 版：

```powershell
rtk python .\fbbp-research-workbench\scripts\control_plane\readiness_check.py --include-private-rag --include-public-lookup --output-root .\fbbp-research-workbench\runs\control_plane\readiness\latest
```

期望输出：

- `readiness_summary.json.ok=true`
- `postgres_bridge.ok=true`
- `a2a_live_e2e.ok=true`
- `minimind_secondary.ok=true`
- `eval_dashboard.ok=true`

## 15. 推荐的实施顺序结论

最推荐的落地顺序是：

1. 先搭 `fbbp-research-workbench` 的 control-plane 骨架
2. 再把现有 runner 接进去
3. 再补 memory 闭环
4. 再补 A2A envelope
5. 再补 A2A 产品化硬化：外部 gateway、worker queue、retry、dead letter
6. 最后把 observability 和 agent eval 统一收口

MiniMind 不阻塞 Phase 1，可在 Phase 2 以后作为次级能力接入。

这条路线的核心原则是：

- 先统一接入
- 再统一记录
- 再统一恢复
- 再统一评测

而不是一开始就做一个很重、很聪明、但难稳定的“大总控”。
