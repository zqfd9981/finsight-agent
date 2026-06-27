## Context

当前仓库已经完成工程层拆分：

- `frontend/streamlit_app/` 作为 V1 Streamlit 工作台入口
- `backend/apps/api/` 作为后端 API 入口
- `shared/` 作为跨前后端稳定共享对象目录

现有正式 spec 已经要求前端只能通过稳定接口消费后端结果，但还没有明确：

- 前端发分析请求的统一入口是什么
- 首轮分析和追问如何在协议层区分
- 稳定响应如何把 `FinalResponse`、`TraceBlock` 和 `GuardrailOrErrorResponse` 组织起来
- 什么情况下应该返回稳定业务响应，什么情况下才使用协议级错误码

如果这些约束不先落 spec，后面的最小实现很容易让 frontend 直接耦合 backend 内部 service，或者让 request/response payload 在实现中临时发散。

## Goals / Non-Goals

**Goals:**

- 为 V1 工作台定义一个单一、稳定、可测试的 backend API 边界
- 支持首轮分析与 follow-up 追问共用一套请求入口
- 让共享 contract 能完整表达 request 与 response envelope
- 让后续 `metric_lookup` 最小链路实现可以直接按 spec 落地

**Non-Goals:**

- 不在这次 change 中切换到 streaming、SSE 或 WebSocket
- 不在这次 change 中引入鉴权、多租户或公开开放平台 API 设计
- 不重写现有 `FinalResponse`、`TraceBlock`、`GuardrailOrErrorResponse` 的核心语义
- 不直接实现真实业务逻辑

## Decisions

### Decision 1：V1 使用单一同步 HTTP 分析入口

采用单一同步 endpoint 作为 workbench 到 backend 的调用边界，推荐形式为：

- `POST /api/v1/analysis/turns`

原因：

- V1 先要打通最小可运行链路，同步请求-响应成本最低
- 对 Streamlit workbench 更简单，易于做 mock-first 联调
- 不把“边界规范化”和“流式交互升级”绑在一次 change 里

备选方案：

- 拆成“新建会话”和“继续追问”两个 endpoint
  - 优点：语义更直白
  - 缺点：接口面更大，首轮与追问的公共 contract 被重复表达
- 直接采用流式返回
  - 优点：更适合长分析链路
  - 缺点：超出 V1 最小链路范围，也会显著增加 workbench 实现复杂度

### Decision 2：请求对象保持极简，靠 `session_id` 表达首轮与追问

V1 请求对象仅稳定承诺最小字段：

- `query`：必填，用户输入
- `session_id`：可选；缺失表示首轮分析，存在表示继续已有会话
- `include_trace`：可选；V1 workbench 默认请求 trace

原因：

- 这是当前 workbench 已知必需信息的最小闭包
- 可以先把会话续接规则定住，不提前发明复杂 follow-up payload
- 后续如果需要 `client_turn_id`、`response_mode_hint` 等字段，可以通过 optional 字段向后兼容扩展

备选方案：

- 显式加入 `turn_mode`
  - 优点：语义更显式
  - 缺点：和 `session_id` 会产生重复表达
- 在请求中加入完整 `follow_up_context`
  - 优点：前端控制更强
  - 缺点：会让前端过早感知后端内部会话语义

### Decision 3：响应使用稳定 envelope，承载主响应与 trace

V1 response 不直接裸返回 `FinalResponse`，而是使用顶层 envelope：

- `version`
- `session_id`
- `turn_id`
- `response`
- `trace_blocks`

其中：

- `response` 必须是 `FinalResponse` 或 `GuardrailOrErrorResponse`
- `trace_blocks` 必须是 `TraceBlock` 列表

原因：

- 现有 shared contract 已把“主结果”和“trace”拆成不同对象
- envelope 可以承接 session continuity，而不污染已有 `FinalResponse`
- 前端渲染时只需要理解一个固定的 API 返回外壳

备选方案：

- 把 trace 内嵌回 `FinalResponse`
  - 优点：对象更少
  - 缺点：会混淆主结果语义和调试/可解释性语义
- 成功与错误使用完全不同的顶层结构
  - 优点：类型区分更强
  - 缺点：前端消费分支更多，不利于稳定联调

### Decision 4：尽量用稳定业务响应表达 guardrail 与可恢复执行错误

V1 约束：

- 业务层能建模的 `guardrail`、`degraded` 和可恢复 `error`，应尽量返回稳定 response envelope
- 非 2xx 状态码只用于协议级错误或完全无法构造稳定 envelope 的故障

原因：

- workbench 需要稳定渲染降级态，而不是把业务失败退化成裸 HTTP 错误
- 这能避免前端为了错误态去读取后端私有异常结构

备选方案：

- 任何异常都直接返回 5xx
  - 优点：实现简单
  - 缺点：和当前 workbench spec 的“稳定降级展示”目标冲突

## Risks / Trade-offs

- [请求字段过少，未来可能需要补更多上下文] → 先冻结最小必需字段，并把新增字段限定为 optional 向后兼容扩展
- [同步接口对长链路体验一般] → 当前先服务 V1 最小链路，后续单独起 change 讨论流式升级
- [response envelope 会引入新 shared contract] → 在 shared-analysis-contracts 中明确 owner、字段语义和 fixture，降低联调歧义
- [前端可能仍绕过 API 直连 backend 内部模块] → 在后续实现任务中加入 adapter 与测试，显式检查边界

## Migration Plan

1. 新增 `workbench-backend-api-boundary` spec，定义请求、响应和状态语义
2. 修改 `shared-analysis-contracts` spec，加入 API request / response envelope contract
3. 在实现 change 中补齐：
   - `shared/contracts/` 请求与 envelope 对象
   - `backend/apps/api/` 的最小 FastAPI endpoint
   - `frontend/streamlit_app/` 的最小 HTTP client / adapter
4. 用 fixture 和 contract 测试先打通 `metric_lookup` 最小联调链路

回退策略：

- 如果评审发现接口字段不稳定，可以保留工程层拆分和当前 shared contracts，不立即实现 API 入口
- 如果后续确认要改成流式接口，可在保留 shared contracts 的前提下新增 streaming 变更，而不是重写本次同步接口 spec

## Open Questions

- `turn_id` 是否需要在第一版就进入 shared envelope，还是允许先只暴露 `session_id`
- `include_trace` 是否默认对所有 workbench 请求开启，还是由前端显式控制
