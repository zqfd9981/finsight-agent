## ADDED Requirements

### Requirement: V1 工作台必须通过统一分析入口调用后端
系统 MUST 为 V1 workbench 提供一个统一、同步、稳定的后端分析入口，用于承接首轮分析和 follow-up 追问，而不是让前端自行拼装多套私有调用路径。

#### Scenario: 用户发起首轮分析
- **WHEN** 前端工作台提交一个新的分析请求且未提供 `session_id`
- **THEN** 后端 MUST 将其视为一轮新会话分析，并返回可继续用于后续追问的稳定会话标识

#### Scenario: 用户继续已有会话
- **WHEN** 前端工作台提交分析请求并携带已有 `session_id`
- **THEN** 后端 MUST 将其视为同一分析会话中的后续轮次，而不是静默创建新的独立会话

### Requirement: V1 分析请求必须使用稳定的最小 request contract
系统 MUST 为 workbench 到 backend 的分析请求定义稳定的最小 request contract，至少覆盖用户 query、会话续接信息和 trace 请求偏好，避免前端依赖后端私有参数。

#### Scenario: 前端提交首轮或追问请求
- **WHEN** 前端工作台向统一分析入口发送请求
- **THEN** 请求体 MUST 至少支持 `query` 必填字段，并允许通过 optional `session_id` 表达会话续接，通过 optional trace 标记表达是否请求 trace 数据

#### Scenario: 请求缺少必填分析字段
- **WHEN** 请求体缺少 `query` 或出现与 contract 不兼容的结构错误
- **THEN** 后端 MUST 以协议级客户端错误拒绝该请求，而不是将其当作业务降级结果继续处理

### Requirement: V1 分析响应必须返回稳定的 response envelope
系统 MUST 用稳定的 response envelope 返回分析结果，使前端可以在同一顶层结构中消费主响应、trace 和会话续接信息，而不需要理解后端内部中间对象。

#### Scenario: 后端成功或降级完成一轮分析
- **WHEN** 后端能够产出 `FinalResponse` 或 `GuardrailOrErrorResponse`
- **THEN** 后端 MUST 返回一个稳定 envelope，其中至少包含 `version`、`session_id`、主 `response` 对象和 `trace_blocks` 列表

#### Scenario: 前端渲染分析结果
- **WHEN** 工作台收到稳定 response envelope
- **THEN** 工作台 MUST 只依赖该 envelope 及其包含的共享 contract 渲染主结果、trace 和降级状态，而不应依赖后端内部控制面或能力层私有对象

### Requirement: HTTP 状态语义必须区分协议错误与可建模业务结果
系统 MUST 将协议级错误与可建模业务结果区分表达，避免把可解释的 guardrail、degraded 或可恢复执行错误退化成不可消费的裸 HTTP 异常。

#### Scenario: 后端能够构造稳定错误或 guardrail 结果
- **WHEN** 一次请求在业务执行中触发信息不足、降级处理或可恢复错误，但后端仍能构造稳定响应对象
- **THEN** 后端 MUST 优先返回稳定 response envelope，而不是直接退回未建模的 5xx 响应

#### Scenario: 后端完全无法构造稳定 envelope
- **WHEN** 请求在协议层、反序列化层或不可恢复基础设施故障中失败，导致后端无法生成稳定 envelope
- **THEN** 后端 MAY 返回非 2xx 状态码，但必须保持与 workbench API boundary 一致的错误类别语义
