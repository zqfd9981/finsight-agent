# Session Context Follow-up Design

## 背景

截至 2026-07-01，FinSight V1 已经完成了首版 orchestrator 最小执行链：

- `metric_lookup` 可以走真实 `route -> plan -> orchestrate -> envelope`
- `evidence_lookup` 可以走真实 retrieval facade
- `WorkbenchBackendApiService` 已经不再返回 stub 响应

但当前多轮续接仍停留在 contract 级：

- `AnalysisRequest` 可以携带 `session_id`
- `SessionContext` contract 已经稳定
- router 已经能够消费 `SessionContext` 做 `follow_up_type` 判别与 target 继承

真正缺失的部分是：

- 统一入口没有真实加载 `SessionContext`
- 首轮执行后没有真实写回 session state
- follow-up 在线链路还不能依赖真实会话上下文闭环

因此，下一阶段的重点不是继续扩 orchestrator stage，而是把 `conversation-session-state` 从“结构已定义”推进到“统一入口真实消费”的首版闭环。

本设计不修改任何现有 OpenSpec 主 spec，也不改动既有 shared contracts。它只新增一份实现准备文档，用于约束首版 session 接线方式。

## 目标

本轮设计目标是为 `conversation-session-state` 定义一个首版最小可运行方案，使统一入口能够稳定支撑 follow-up。

具体目标：

- 明确 session 模块与 memory 的关系和职责边界
- 定义首版保留多少历史、以什么粒度保留
- 明确 `SessionContext` 各字段从哪里抽取
- 说明为什么首版以结构化抽取为主，而不是 LLM 自由总结
- 定义 `WorkbenchBackendApiService` 的读写接线时机
- 定义历史缺失时的降级语义
- 为后续 implementation plan 提供足够具体的模块与任务边界

## 非目标

本轮不包含以下内容：

- 不修改 `openspec/specs/conversation-session-state/spec.md`
- 不修改 `shared/contracts/session_context.py`
- 不实现长期用户画像记忆
- 不实现向量化语义 memory
- 不把完整原始对话逐轮回放给 router / planner
- 不在首版引入“LLM 作为唯一 session 抽取器”
- 不提前建设完整的多表数据库会话系统
- 不把 session state 逻辑塞进 orchestrator 或 retrieval 内部

## 定位：它是不是 memory

`conversation-session-state` 可以被视为 FinSight V1 的短期记忆机制，但它不是一个泛化 memory 平台。

更准确地说，它是：

- 一个面向多轮分析续接的会话级工作记忆层
- 一个受 shared contract 约束的压缩上下文机制
- 一个服务于 router / planner / unified API 的状态模块

它不是：

- 长期个性化用户记忆
- 任意文本都可写入的开放式记忆库
- retrieval 的替代品
- LLM 自由生成和自由消费的黑盒摘要层

因此，首版设计应围绕“受控、可测、结构化、可降级”的短期记忆，而不是追求泛化 memory 能力。

## 当前仓库现状

### 已经稳定的部分

#### 统一 request / response contract

当前统一入口已经稳定支持：

- `query`
- `query_mode`
- optional `session_id`
- optional `include_trace`

并且响应 envelope 已经稳定暴露：

- `session_id`
- `response`
- `trace_blocks`

#### `SessionContext` contract

当前共享 contract 已冻结这些字段：

- `session_id`
- `active_topic`
- `active_candidates`
- `key_evidence_refs`
- `history_summary`
- `available_follow_ups`

这意味着首版 session 设计不需要再发明新的对外字段，只需要定义这些字段如何被生产与消费。

#### router 的现有消费点

router 已经真实使用 `SessionContext` 进行：

- `follow_up_type` 判别
- compare / drilldown / expand / redirect 的启发式判断
- evidence lookup 中 target 的历史继承

这说明一旦统一入口能够真实加载 `SessionContext`，线上 follow-up 行为会立即开始受益。

### 当前缺失的部分

目前仓库中还没有：

- `SessionService`
- `SessionRepository`
- turn snapshot 存储结构
- 从执行结果回写 `SessionContext` 的 extractor
- 统一入口中的 session load / save 生命周期

这也是为什么当前 `WorkbenchBackendApiService` 仍然只透传 `session_id`，却没有真正续接上下文。

## 核心问题

这轮设计需要回答 5 个问题：

1. 首版需要保留多少历史
2. `SessionContext` 应该从什么数据源抽取
3. 抽取逻辑是否依赖 LLM
4. session 在统一入口的读写时机是什么
5. 历史缺失时如何降级

## 设计决策

### 决策 1：首版只保留“最近 1 个有效 turn snapshot”，而不是最近 N 条原始消息

首版 session 不直接保留“最近 N 条聊天消息全文”，而是保留：

- 1 条最近有效 turn snapshot
- 1 份与之对应的压缩 `SessionContext`

这里的“有效 turn”指：

- 成功完成并产出 `FinalResponse` 的轮次
- 或者至少完成了稳定可消费的 guardrail / degraded 结果的轮次

这样设计的原因：

- 当前 follow-up 主要依赖上一轮主题、候选对象、关键证据和摘要结论
- router 的现有规则也主要依赖“最近一轮的活跃主题与候选对象”
- 直接保留最近 N 条原始消息会扩大噪声、增加 token 压力，并带来更多压缩策略复杂度

这意味着首版不做“多轮全文记忆”，而做“上一轮结构化快照记忆”。

### 决策 2：`SessionContext` 首版由结构化执行产物抽取，而不是由 LLM 自由总结

首版 `SessionContext` 的主生产方式应为 deterministic extractor，从结构化产物中抽取，而不是让 LLM 读取整轮历史后自由生成。

优点：

- 更稳定，不受 prompt 漂移影响
- 更可测，可以为每种 turn 类型写确定性单测
- 更容易降级，字段缺失时可以显式留空
- 更符合当前仓库“shared contract 驱动”的设计方向

首版不排斥后续加 LLM enhancement，但只能作为：

- topic 命名润色
- summary 文案优化

不能作为唯一真相来源。

### 决策 3：首版用“规则化摘要 + 结构化字段抽取”，而不是完整 turn replay

首版不把完整 turn 的原始 request、trace、evidence 原文直接传给 router / planner。

统一入口只向下游暴露：

- `SessionContext`
- 必要时内部保存的 turn snapshot

router / planner 仍然只消费压缩后的 `SessionContext`。

这样可以把“对外可消费上下文”和“内部调试/回放数据”分层隔离。

### 决策 4：session 读写都放在统一入口，而不是放进 orchestrator

`SessionContext` 的 load / save 生命周期应由 `WorkbenchBackendApiService` 负责：

1. 请求进入统一入口
2. 若携带 `session_id`，先尝试加载 session snapshot
3. 得到 `SessionContext | None`
4. 将其传给 router
5. plan / orchestrate 正常执行
6. 请求结束后基于本轮结构化产物构造新的 snapshot 并保存

这样设计的原因：

- orchestrator 的职责是“执行编排”，不应拥有 session state 主权
- session 模块天然属于统一入口与控制面之间的接线能力
- 未来若前端或 API boundary 发生变化，session 接线更容易独立演化

## 首版最小状态模型

### 1. 持久化对象

首版建议在 session 模块内部维护一个轻量持久化对象 `SessionSnapshot`。

它不是 shared contract，不直接暴露给前端。

建议字段：

- `session_id`
- `last_query`
- `last_query_mode`
- `last_intent`
- `last_follow_up_type`
- `last_plan_stages`
- `context`
- `updated_at`

其中：

- `context` 为 `SessionContext`
- `last_plan_stages` 用于后续判断哪些 follow-up 可以合理继续
- `updated_at` 只用于内部排序或调试，不进入 shared contract

首版不强制把完整 observation / trace 全量写入 snapshot 主对象，避免状态膨胀。

### 2. 对外可消费对象

统一入口、router、planner 只消费 `SessionContext`。

首版继续使用现有 shared contract：

- `session_id`
- `active_topic`
- `active_candidates`
- `key_evidence_refs`
- `history_summary`
- `available_follow_ups`
- `notes`

## 字段提取设计

### `active_topic`

首版优先从结构化结果中提取：

1. `router_result.intent`
2. `router_result.entities`
3. `final_response.summary`

建议规则：

- `metric_lookup`
  - 模板：`{company} {time_scope} {metric}`
- `evidence_lookup`
  - 优先使用 `target + claim` 的压缩表达
- `event_impact_analysis`
  - 模板：`{event} 对 {themes} 的影响`

如果必要字段缺失，则保守回退为：

- `final_response.summary` 的前一段主题化截断
- 若仍缺失，则置空

### `active_candidates`

首版优先从“明确被系统选中的对象”里提取，而不是从原始 query 任意抓词。

优先级建议：

1. `router_result.entities` 中的 target / company
2. `final_response.report_blocks` 中明确列出的候选对象
3. 与 retrieval/evidence stage 绑定的目标对象

规则要求：

- 去重
- 保持顺序稳定
- 首版限制最多保留前 3 个候选对象

原因：

- follow-up compare 主要只需要最近一轮的少量活跃对象
- 候选对象过多会削弱 router 判别稳定性

### `key_evidence_refs`

首版只保留关键证据引用，不保留证据全文。

优先来源：

1. `retrieve_evidence` stage 输出中的 evidence ids / refs
2. `FinalResponse.report_blocks` 里已经引用过的证据标识

规则要求：

- 只保留可稳定回指的 ref / id
- 首版限制最多保留前 5 个
- 不把 retrieval 中间态全文塞进 `SessionContext`

### `history_summary`

首版不使用 LLM 直接生成自由摘要，而采用模板化摘要拼接。

建议模板信息：

- 上一轮任务类型
- 上一轮关注主题
- 当前候选对象
- 是否已完成证据展开
- 是否存在不确定性或待继续动作

示例：

- `上一轮已完成宁德时代 2024 年净利润查询，并返回结构化简答。`
- `上一轮已围绕红海局势升级分析航运链影响，当前候选对象包括中远海能、招商轮船，并已补充关键证据引用。`

规则要求：

- 首版尽量控制在 1 到 2 句
- 用结构化字段驱动模板，而不是回看原始聊天全文
- 缺失时允许为空，但必须在内部 notes 中说明原因

### `available_follow_ups`

首版由规则生成，不由模型猜测。

建议规则：

- 有 `active_candidates`
  - 允许 `compare`
- 有 `key_evidence_refs` 或 evidence/report 输出
  - 允许 `drilldown`
- 有稳定 topic 且不是 out_of_scope
  - 允许 `expand`
- 首轮无有效上下文或已经 redirect 后的新主题
  - 可为空，或仅保留最保守集合

不建议首版在 `SessionContext` 中预计算 `redirect`，因为 `redirect` 更适合作为“当前 query 相对历史是否偏题”的在线判别结果，而不是静态可用动作。

## 历史范围与压缩策略

### 首版历史范围

首版压缩策略应收敛为：

- 不读取最近 N 条原始消息
- 不读取整段聊天 transcript
- 只读取最近 1 条 `SessionSnapshot`

这是一个明确的产品化折中：

- 换取最小实现成本
- 换取 router follow-up 行为快速上线
- 为后续“多 turn 累积压缩”留下演化空间

### 后续可扩展方向

后续若需要支持更复杂多轮比较，可以再扩展为：

- `last_snapshot + rolling_summary`
- 或 `recent_turns <= 3` 的受限压缩

但这不是首版必需。

## 统一入口接线设计

### 请求进入阶段

`WorkbenchBackendApiService` 首版应增加以下 session 生命周期：

1. 读取 `request.session_id`
2. 若为空，生成新 `session_id`
3. 若不为空，尝试加载 `SessionSnapshot`
4. 从 snapshot 中取得 `SessionContext`
5. 将 `SessionContext` 传入 router

planner 首版可以继续只消费 `RouterResult`，不强制引入新的 planner session 依赖。

### 请求完成阶段

请求完成后，统一入口应收集：

- `request`
- `router_result`
- `plan`
- `orchestration_result`

然后通过 `SessionContextExtractor` 构造新的：

- `SessionContext`
- `SessionSnapshot`

再持久化到 session repository。

### 短路与 guardrail

即使本轮被 short-circuit 为 `out_of_scope`，统一入口也可以选择：

- 不覆盖旧 snapshot
- 或仅记录极简 last turn metadata

首版更推荐：

- `out_of_scope` 不重置既有有效会话上下文
- 只在内部记录一次轻量访问痕迹

这样可以避免一次无关追问把之前有效主题冲掉。

## 降级语义

### 场景 1：携带 `session_id` 但查不到历史

处理原则：

- 不伪造 `SessionContext`
- 保守回退为 `session_context=None`
- 允许 router 将该轮判为 `none` 或 `redirect`

这与现有 spec 一致。

### 场景 2：历史存在但字段不完整

处理原则：

- 缺字段时按字段级降级
- 不因为某一个字段缺失就整体丢弃 session

例如：

- 缺 `key_evidence_refs` 时，仍可保留 `active_topic`
- 缺 `active_candidates` 时，仍可保留 `history_summary`

### 场景 3：本轮执行失败

处理原则：

- 不用失败中的不完整中间态覆盖旧 snapshot
- 只有在能形成稳定结果对象时才更新 session

首版建议：

- 成功 / degraded / guardrail 可建模结果可以更新
- 未建模异常不更新

## 方案比较

### 方案 A：最小会话快照方案

做法：

- 只维护最近 1 条 `SessionSnapshot`
- 只暴露 `SessionContext`
- 由结构化 extractor 写回

优点：

- 最轻量
- 最符合当前阶段
- 最容易让 evidence follow-up 在线闭环

缺点：

- 多轮深追问能力有限
- 需要后续再扩展 richer turn history

### 方案 B：完整 turn log + 在线压缩方案

做法：

- 每轮全量保存 request / router / plan / observations / response
- follow-up 时再现算 `SessionContext`

优点：

- 可追溯性最强
- 后续评测、debug、回放很方便

缺点：

- 首版过重
- 需要更多内部数据结构
- 容易把这轮设计目标从“接线”拉成“完整会话平台”

### 方案 C：纯内存 dict 缓存方案

做法：

- 只在进程内用 map 保存 `SessionContext`

优点：

- 开发最快
- 本地 demo 成本最低

缺点：

- 重启丢失
- 与 spec 中“持久化 session state”的方向不完全一致
- 容易遗留技术债

## 推荐方案

推荐 **方案 A：最小会话快照方案**。

理由：

- 它最贴合当前项目阶段
- 它能直接解决真实 follow-up 接线问题
- 它不会把 session 模块膨胀成新的复杂系统
- 它允许后续在不改 shared contract 的前提下逐步演化内部 snapshot 模型

## 建议的模块切分

仓库里已经预留了 `backend/src/finsight_agent/control_plane/session/` 骨架，因此首版建议直接复用这一目录，而不是再新开平行模块。

首版可在该目录下新增或补齐以下内部模块：

- `backend/src/finsight_agent/control_plane/session/models.py`
  - `SessionSnapshot`
- `backend/src/finsight_agent/control_plane/session/repository.py`
  - `SessionRepository`
- `backend/src/finsight_agent/control_plane/session/service.py`
  - `SessionService`
- `backend/src/finsight_agent/control_plane/session/extractor.py`
  - `SessionContextExtractor`

职责建议：

- `SessionRepository`
  - 负责 load / save
- `SessionService`
  - 负责统一入口侧读写编排
- `SessionContextExtractor`
  - 负责从结构化执行产物提取 `SessionContext`

首版 repository 可以先使用轻量文件或本地存储实现，但不在本设计中先绑定具体基础设施。

## 与现有模块的衔接点

### `WorkbenchBackendApiService`

需要新增：

- 请求进入时加载 snapshot
- 把 `SessionContext` 传给 router
- 请求结束后保存 snapshot

### router

不需要改 contract，只需要开始消费真实 session context。

### planner

首版无需新增 planner 专属 session 逻辑，继续通过 `RouterResult.follow_up_type` 和现有结构工作。

### orchestrator

不拥有 session state 主权。

但其结构化输出将成为 `SessionContextExtractor` 的主要数据源之一。

## 首版验收口径

首版 session follow-up 设计落地后，应至少满足：

1. 首轮请求未提供 `session_id` 时，系统能创建稳定会话并写入 snapshot
2. follow-up 请求携带已有 `session_id` 时，router 能真实收到 `SessionContext`
3. evidence follow-up 能在统一 API 路径下复用上一轮候选对象或主题
4. 历史缺失时系统不会伪造上下文，而会显式降级
5. `SessionContext` 的核心字段由结构化 extractor 产出，而不是依赖 LLM 自由总结

## 开放问题

以下问题可以留到 implementation plan 或下一轮实现中进一步细化：

- 首版 repository 用文件、sqlite 还是别的轻量本地存储
- `FinalResponse.report_blocks` 中候选对象抽取是否需要单独 helper
- `history_summary` 的模板是否需要按 intent 分开
- 后续是否需要 `rolling_summary` 来支持 2 到 3 轮以上的复杂追问

## 结论

下一阶段最合理的推进方式，不是直接上完整 memory 平台，也不是把 LLM 拉进来做黑盒摘要，而是先把 `conversation-session-state` 做成一个受控的短期记忆层：

- 只保留最近 1 条有效 turn snapshot
- 只向 router / planner 暴露压缩后的 `SessionContext`
- 由结构化 extractor 生产记忆
- 由统一入口负责 load / save 生命周期

这样既能快速打通 evidence follow-up 在线链路，也能保持现有控制面和 shared contract 的稳定边界。
