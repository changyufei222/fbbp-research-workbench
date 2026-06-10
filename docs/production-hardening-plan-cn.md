# 生产化增强说明：Redis、OAuth/OIDC、官方 A2A 兼容

## 先回答：为什么之前没有一开始就全补

不是主要因为钱。

真正原因是工程边界：Redis、OAuth/OIDC、官方 A2A 全兼容都属于生产化基础设施。如果在项目主链路还没稳定时强行加入，很容易变成“配置很多、链路不稳、面试说不清”的半成品。

现在 control plane 主链路已经稳定，因此这些能力可以作为 production hardening 层补进去。这样既不影响本地 demo，也能回答面试官关于多 worker、安全、协议兼容的问题。

## 当前已经补进去的内容

### 1. Redis / Postgres Queue Backend

当前状态：

- file queue：本地默认可运行，适合 demo 和复现
- Redis adapter：已提供配置模板和 availability check
- Postgres adapter：已提供配置模板、表初始化、任务和事件持久化

相关文件：

- `scripts/control_plane/queue_backends.py`
- `configs/control_plane/worker_queue.redis.example.yaml`
- `configs/control_plane/worker_queue.postgres.example.yaml`
- `configs/control_plane/a2a.production.example.yaml`

生产环境怎么启用：

```powershell
$env:FBBP_A2A_REDIS_URL = "redis://localhost:6379/0"
```

或：

```powershell
$env:FBBP_A2A_POSTGRES_DSN = "postgresql://user:password@host:5432/db"
```

然后把 `queue_backend` 切成 `redis` 或 `postgres`。

面试说法：

> 本地 v1 默认 file queue，保证可复现；生产部署可以切 Redis/Postgres backend。队列层已经抽象成 adapter，并且保留 retry、lease、dead letter 和 event history。

### 2. OAuth/OIDC 接入点

当前状态：

- API key / Bearer token 已可用
- OIDC reverse-proxy trust mode 已加入
- OIDC JWT claims demo validation 已加入
- 真实签名校验需要生产环境提供 issuer、JWKS、audience 和部署策略

相关文件：

- `scripts/control_plane/auth.py`
- `configs/control_plane/a2a.production.example.yaml`
- `tests/test_control_plane_a2a_gateway.py`

支持两种生产接法：

1. 反向代理模式：由 API Gateway / Nginx / Cloudflare Access / 企业网关完成 OIDC 登录，control plane 信任 `X-Forwarded-User` 和 `X-Forwarded-Groups`。
2. JWT claims 模式：control plane 解析 Bearer JWT 的 issuer、audience、scope；真实生产签名校验需要接 JWKS。

面试说法：

> 当前项目不是多租户 SaaS，所以本地默认 API key。为了生产化，我补了 OIDC 接入点：可以走反向代理信任模式，也可以走 JWT claims 验证。真正上线时我会接公司 IdP 的 JWKS，并按 submit、claim、read、admin 拆 scope。

### 3. A2A Conformance Coverage

当前状态：

- Agent Card
- `message/send`
- `message/stream`
- `tasks/get`
- `tasks/cancel`
- `tasks/resubscribe`
- `tasks/pushNotificationConfig/set`
- `tasks/pushNotificationConfig/get`
- task event history
- trace id / correlation id / hop metadata
- retry / dead letter

相关文件：

- `scripts/control_plane/a2a_gateway.py`
- `scripts/control_plane/a2a.py`
- `configs/control_plane/a2a.schema.json`
- `scripts/control_plane/production_hardening_check.py`

注意边界：

这仍然应该描述为 `A2A-compatible v1 subset`，不是官方完整认证。

面试说法：

> 我实现了 A2A-compatible v1 子集，覆盖 agent card、message send/stream、task lifecycle、resubscribe、push config 和 trace metadata。没有夸成官方 full compliant；如果岗位需要，我会下一步接官方 conformance suite 和更完整的事件类型。

## 新增生产化检查

运行：

```powershell
python .\scripts\control_plane\production_hardening_check.py
```

输出：

- `runs/control_plane/hardening/latest/production_hardening_summary.json`
- `runs/control_plane/hardening/latest/production_hardening_summary.md`

它检查：

- queue backend 是否声明
- Redis adapter 是否存在
- Postgres adapter 是否存在
- retry 是否配置
- dead letter 是否配置
- streaming 是否声明
- push notification 是否声明
- API key auth 是否支持
- OIDC hook 是否可配置
- Agent Card 是否声明多个接口
- A2A 方法覆盖是否通过

## 求职时怎么讲边界

不要说：

> 我已经完整实现了生产级 OAuth 和官方 A2A 全协议。

应该说：

> 我把生产化接入点和验证框架补进去了。当前本地 demo 不依赖真实 Redis/OIDC 服务，但项目已经有 Redis/Postgres adapter、OIDC proxy/JWT claims 接入点、A2A conformance checklist 和 hardening check。真正部署时只需要接入公司的 Redis/Postgres DSN、OIDC issuer/JWKS、权限 scope 和部署网关。

这个说法最稳，也最像真实工程师。

## 还需要真实环境才能完成的部分

- 真实 Redis 服务压测
- 真实 Postgres 队列压测
- 企业 OIDC issuer / JWKS 签名校验
- OAuth scope 与角色权限策略
- 官方 A2A conformance suite
- 多 worker 横向扩容压测
- webhook 签名轮换
- 指标接 Prometheus / Grafana / OpenTelemetry

这些不是当前本地求职 demo 的必要前提，但已经有清楚的升级路径。

