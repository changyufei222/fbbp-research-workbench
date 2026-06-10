# FBBP Research Workbench

[English](./README.md) | **中文**

这是 FBBP 研究栈的统一产品层和 Agent 控制平面。它把私有 RAG、MCP 工具、正式案例、批量评估、报告生成、运行记录和可观测性整合为一个可演示、可追溯的生物医学研究工作台。

## 项目定位

本仓库不是单一聊天界面，也不是简单 RAG Demo。它负责识别研究意图、路由执行器、保存运行记录，并把证据与评估结果导出为可审计产物。

## 快速导航

| 目标 | 入口 |
|---|---|
| 理解系统架构 | [docs/agent-control-plane-architecture.md](./docs/agent-control-plane-architecture.md) |
| 运行演示 | [docs/interview-demo-runbook.md](./docs/interview-demo-runbook.md) |
| 查看求职版项目说明 | [docs/job-ready-project-page-cn.md](./docs/job-ready-project-page-cn.md) |
| 查看正式案例配置 | [configs/formal_cases/](./configs/formal_cases/) |
| 查看最终结果 | [FINAL_RESULT_SUMMARY.md](./FINAL_RESULT_SUMMARY.md) |

## 已公开的工程能力

- 规则优先的研究意图路由
- FBBP 私有知识检索与公共科学查询
- 正式案例、批处理和报告生成
- 会话记忆、运行恢复和父子任务追踪
- A2A 网关、任务队列、重试与死信处理
- 路由、工具成功率、延迟和评估指标导出

## 运行边界

完整演示依赖相邻仓库、数据库、模型端点与本地运行配置。公开仓库保留可复核配置、脚本、截图和结果摘要，但不包含真实密钥或私有数据库凭证。

详细界面说明见 [INTERFACE_GUIDE_CN.md](./INTERFACE_GUIDE_CN.md)。
