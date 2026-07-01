# Event Analysis Orchestrator Design

## 背景

截至 2026-07-01，FinSight V1 的控制面和数据证据面已经形成了一个清晰但尚未接线完成的结构：

- router 已能把用户问题稳定路由为 `metric_lookup`、`event_impact_analysis`、`evidence_lookup`、`out_of_scope`
- planner 已能把路由结果转换成结构化 `Plan`，并显式给出 `stages` 与 `stage_constraints`
- retrieval facade 已能返回统一的 `RetrievalResult`，包含 `evidence_items`、`retrieval_notes` 与 `retrieval_trace`
- shared contracts 已冻结 `RouterResult`、`Plan`、`StageObservation`、`FinalResponse`、`TraceBlock`
- orchestrator 目录目前仍只有骨架文件，尚未消费真实 `Plan` 和真实能力输出

因此，当前下一步的核心不是再扩 router、planner 或 retrieval，而是把现有能力串成一条真实可执行、可观察、可降级的主执行链。

本设计不修改现有 OpenSpec 主 spec，也不改动既有 shared contracts。它只为 `event-analysis-orchestration` 的首版实现准备一份新增设计文档，用于约束接线方式和实施顺序。

## 目标

本轮设计目标是把 orchestrator 收敛成一个可以正式落地的首版执行框架：

- 明确 orchestrator 的职责边界、输入输出和不拥有的内容
- 定义首版最小可运行路径
- 选择一个适合当前仓库状态的实现结构
- 明确 orchestrator 与 router / planner / retrieval / structured data / reporting / API 入口的衔接点
- 为后续 implementation plan 提供足够具体的文件级设计

## 非目标

本轮不包含以下内容：

- 不修改 `openspec/specs/event-analysis-orchestration/spec.md`
- 不修改 `openspec/specs/semantic-routing-and-planning/spec.md`
- 不重做 retrieval 主链路
- 不在本轮补齐真实 session 持久化
- 不在本轮实现完整 event 四阶段真实能力
- 不把 guardrail、reporting、trace、session 的全部设计细节都并入 orchestrator
- 不把 orchestrator 做成新的单体业务中心

## 当前仓库现状

### 已经具备的稳定输入

#### `RouterResult`

router 已经能输出稳定的结构化路由结果，至少包含：

- `intent`
- `follow_up_type`
- `entities`
- `needs`
- `constraints`

其中当前规则实现已经覆盖：

- `metric_lookup`
- `event_impact_analysis`
- `evidence_lookup`
- `out_of_scope`

#### `Plan`

planner 已能把 `RouterResult` 转成有序计划，并且已经具备长短路径两种形态：

- `metric_lookup`
  - `query_structured_data`
  - `synthesize_brief_answer`
- `evidence_lookup`
  - `retrieve_evidence`
  - `synthesize_report`
- `event_impact_analysis`
  - `collect_event_context`
  - `analyze_targets`
  - `retrieve_evidence`
  - `synthesize_report`

#### retrieval facade

retrieval 已具备统一在线接口：

- `retrieve_evidence(...) -> RetrievalResult`

返回对象已包含：

- `normalized_claim`
- `evidence_items`
- `retrieval_notes`
- `retrieval_trace`

这意味着 orchestrator 在证据检索阶段已经有稳定的下游可接，不需要再感知 PDF acquisition、parsing、chunking 或索引重建细节。

### 当前尚未具备的能力

以下能力仍处于骨架或占位状态：

- orchestrator 本体
- session service / repository
- guardrail service
- 复杂 reporting / report assembly
- 真实 structured market data 数据源
- event 主链路中的 `collect_event_context` 与 `analyze_targets` 真实下游实现

因此首版 orchestrator 必须围绕“先打通真实执行链”而不是“先做满完整 V1 愿景”来设计。

## 职责边界

### orchestrator 负责什么

orchestrator 的职责应严格限定为以下 6 项：

1. 消费单轮 `RouterResult` 与 `Plan`
2. 按 `Plan.stages` 顺序执行阶段
3. 在阶段内执行有限的本地控制逻辑
4. 记录标准化 `StageObservation`
5. 组织最终响应装配所需的最小输入
6. 对超范围和可降级失败执行受约束停止

### orchestrator 不负责什么

orchestrator 不应承担以下职责：

- 不重做意图识别
- 不重做 plan 生成
- 不拥有 retrieval 的中间命中结构定义主权
- 不拥有 structured data 的底层数据定义主权
- 不拥有 session 存储与压缩策略主权
- 不直接定义复杂 report block 结构
- 不把所有阶段逻辑都硬编码进一个超大函数

一句话概括：

orchestrator 是“执行编排者”，不是“语义理解者”、不是“能力实现者”，也不是“结果展示者”。

## 上下游接口

### 上游输入

首版 orchestrator 输入应包含：

- `AnalysisRequest`
- `RouterResult`
- `Plan`
- `SessionContext | None`

其中：

- `AnalysisRequest` 用于提供当前 query、session_id、trace 开关
- `RouterResult` 提供 intent 和语义实体
- `Plan` 提供顶层阶段顺序和阶段约束
- `SessionContext` 首版允许为空，不作为阻塞条件

### 下游能力

首版 orchestrator 直接依赖的能力服务应尽量少而稳：

- `StructuredDataService`
- `RetrievalFacade`
- `ReportingService`

后续可扩展但首版不强依赖：

- `SessionService`
- `GuardrailService`
- `CollectEventContextService`
- `TargetAnalysisService`

### 下游输出

首版 orchestrator 不应直接只返回 `FinalResponse`，否则中间结果会再次被吞掉。

建议它先返回一个内部聚合结果对象，例如 `OrchestrationResult`，其中至少包含：

- `final_response`
- `guardrail_response`
- `stage_observations`
- `trace_blocks`
- `router_result`
- `plan`

再由统一 API 入口把它封装进 `AnalysisResponseEnvelope`。

这样做的原因是：

- 便于 workbench 入口直接消费
- 便于后续 session / trace / evaluation 接入
- 避免 orchestrator 既编排又顺手承担 API 封装职责

## 方案对比

### 方案 A：中心化 Orchestrator + 阶段 Runner 注册表

结构：

- `OrchestratorService` 负责流程控制
- 每个 stage 对应一个 runner
- orchestrator 根据 `Plan.stages` 调度 runner
- runner 返回统一阶段结果
- observation builder 把阶段结果映射为 `StageObservation`

优点：

- 最贴合当前 `Plan` 与 `StageName` 设计
- 能先落短路径，后补长路径
- 容易保持 orchestrator 本身足够薄
- 后续加有限回退、局部重试、统一 trace 更自然

缺点：

- 需要补一层内部阶段结果抽象
- 首轮文件数量会比大函数方案多一些

### 方案 B：单体 Orchestrator if/else 分支执行

结构：

- 所有阶段逻辑直接写进 `OrchestratorService.execute()`

优点：

- 开工最快
- 适合一次性原型验证

缺点：

- 很快膨胀
- 不利于测试
- 容易吞掉下游能力边界
- 后面补 event 四阶段时维护成本高

### 方案 C：按 intent 拆多个 flow 类

结构：

- `MetricLookupFlow`
- `EvidenceLookupFlow`
- `EventImpactFlow`

优点：

- 对单条路径实现很直观
- 可快速为不同 intent 做局部优化

缺点：

- 会削弱 `Plan` 作为统一编排语言的价值
- observation 与 trace 容易分叉
- 后续 follow-up、回退、统一停止策略更难收口

## 推荐方案

采用 **方案 A：中心化 Orchestrator + 阶段 Runner 注册表**。

推荐原因：

1. 当前仓库最稳定的“中间语言”就是 `Plan.stages`，方案 A 最尊重现有设计。
2. 当前最缺的是真实接线，不是多种执行形态共存；方案 A 可以用最少结构补出真实执行链。
3. 方案 A 能先只实现 `metric_lookup` 和 `evidence_lookup` 的 runner，而不假装 event 主链已经 ready。
4. 后续如果要补步骤级回退、局部重试、execution trace，方案 A 的扩展面最平滑。

## 总体设计

### 核心设计原则

首版 orchestrator 采用 4 个原则：

1. 顶层只按 `Plan.stages` 调度，不绕开 planner 另起炉灶
2. 阶段实现拆成独立 runner，不把能力细节塞进 orchestrator
3. observation 在每个阶段结束后立即标准化产出
4. 首版只承诺真实打通短路径，不阻塞于长路径未完工

### 建议模块结构

建议在 `backend/src/finsight_agent/control_plane/orchestrator/` 下形成以下结构：

- `service.py`
  - orchestrator 主入口
- `policies.py`
  - 停止条件、有限回退、budget 判断等策略函数
- `models.py`
  - orchestrator 内部结果模型，例如 `OrchestrationResult`、`StageExecutionResult`
- `observation_builder.py`
  - 阶段结果到 `StageObservation` 的映射
- `trace_builder.py`
  - execution trace 轻量摘要
- `stage_runners/query_structured_data.py`
- `stage_runners/synthesize_brief_answer.py`
- `stage_runners/retrieve_evidence.py`
- `stage_runners/synthesize_report.py`
- `stage_runners/__init__.py`

后续再扩：

- `stage_runners/collect_event_context.py`
- `stage_runners/analyze_targets.py`

### 内部对象建议

#### `StageExecutionResult`

这是 runner 的统一返回对象，建议至少包含：

- `stage_name`
- `status`
- `output_payload`
- `confidence_signals`
- `evidence_refs`
- `degraded_reason`
- `user_summary`

设计意图：

- runner 不直接产出共享 contract
- runner 先产出内部统一结果
- builder 再把内部结果映射到 `StageObservation`

这样可以把“阶段业务语义”和“共享 contract 形状”解耦。

#### `OrchestrationResult`

建议至少包含：

- `session_id`
- `router_result`
- `plan`
- `stage_observations`
- `final_response`
- `guardrail_response`
- `trace_blocks`

设计意图：

- 让 orchestrator 成为“控制面结果聚合器”
- 让 API 入口继续保持薄封装

## 阶段 Runner 设计

### runner 统一接口

建议每个 runner 采用统一签名：

- 输入：
  - `request`
  - `router_result`
  - `plan`
  - `session_context`
  - `execution_state`
  - `stage_constraints`
- 输出：
  - `StageExecutionResult`

其中 `execution_state` 是 orchestrator 内部累积上下文，用来承接前序阶段输出，而不是重新发明新的跨模块 contract。

### `query_structured_data` runner

职责：

- 从 `router_result.entities` 中读取 `company`、`metric`、`time_scope`
- 调用 `StructuredDataService.query_metric_lookup(...)`
- 返回结构化查询结果

首版要求：

- 即使底层值仍是占位，也要把执行链跑通
- 不在 runner 内实现复杂财务逻辑

### `synthesize_brief_answer` runner

职责：

- 读取 `query_structured_data` 的结果
- 组装一个可直接面向用户展示的简短总结
- 调用 `StructuredDataService.to_brief_response(...)` 或 `ReportingService.build_brief_response(...)`

首版要求：

- 采用规则化文本组装即可
- 不等待完整 report block 系统成熟

### `retrieve_evidence` runner

职责：

- 从 `router_result.entities` 中读取 `claim`、`target`
- 结合 `stage_constraints.retrieval_budget`
- 调用 `RetrievalFacade.retrieve_evidence(...)`
- 把 `RetrievalResult` 回填到 execution state

首版要求：

- 直接消费现有 retrieval facade
- 不侵入 retrieval 内部实现
- `evidence_refs` 直接来源于返回的 `evidence_items`

### `synthesize_report` runner

职责：

- 消费 `RetrievalResult`
- 生成一个首版可用的 `FinalResponse`
- 明确不确定性和下一步建议

首版要求：

- 先做轻量 report synthesis
- 不等待完整 reporting 模块成长为复杂报告系统

建议首版至少输出：

- `summary`
- 1 到 2 个简短 `report_blocks`
- `uncertainty_notes`
- `next_actions`

## 最小可运行路径

### 路径一：`metric_lookup`

首版第一条真实链路：

1. `AnalysisRequest.query`
2. `RouterService.route()`
3. `PlannerService.build_plan()`
4. `OrchestratorService.execute()`
5. `query_structured_data`
6. `synthesize_brief_answer`
7. 返回 `AnalysisResponseEnvelope`

这条路径的目标不是“真实财务数据已经接好”，而是：

- 统一入口已经不再返回 stub
- planner 的短路径被真实执行
- orchestrator 能产生两条标准 `StageObservation`
- workbench trace 能看到 routing / planning / execution

### 路径二：`evidence_lookup`

首版第二条真实链路：

1. `AnalysisRequest.query`
2. `RouterService.route()`
3. `PlannerService.build_plan()`
4. `OrchestratorService.execute()`
5. `retrieve_evidence`
6. `synthesize_report`
7. 返回 `AnalysisResponseEnvelope`

这条路径是当前最重要的真实价值链，因为它第一次把：

- control plane
- retrieval facade
- response assembly

串成同一轮分析。

### 为什么首版不先做 event 四阶段

原因很明确：

- `collect_event_context` 暂无稳定下游能力
- `analyze_targets` 暂无稳定结构化候选分析能力
- 如果先硬做 event 主链，会把大量设计不确定性重新吸回 orchestrator

因此首版应先把“短路径 + observation + trace + 停止逻辑”做扎实，再补 event 长路径。

## Observation 设计

### observation 生成时机

每个 stage 执行结束后，orchestrator 都应立即生成一条 `StageObservation`。

不应等到全部 stage 完成后再统一回填，因为那样会：

- 丢失阶段级状态
- 让失败轮次难以定位
- 增加后续 session / trace 接入成本

### success / degraded / failed 语义

首版建议：

- `success`
  - 阶段产出完整可用结果
- `partial`
  - 阶段结果可继续消费，但有明显缺口
- `degraded`
  - 阶段未完全完成，但仍可面向用户给出降级结果
- `failed`
  - 阶段无法继续，也无法形成可读降级产物

### observation 内容映射

`StageObservation` 建议至少记录：

- `input_summary`
  - 当前 query
  - 关键实体
  - 关键约束
- `key_outputs`
  - 当前阶段产出的核心结果摘要
- `confidence_signals`
  - 结果强弱
  - 是否使用 fallback
  - 命中数量等信号
- `evidence_refs`
  - 证据项 id
  - 或 retrieval request / citation 引用

首版 observation 先保持内存态产出即可，不把 repository 持久化作为前置条件。

## Guardrail 与停止策略

### out_of_scope 停止

如果 `RouterResult.intent` 为 `out_of_scope`，orchestrator 不应进入常规阶段执行。

首版行为建议：

- 不执行 stage runners
- 直接返回 `GuardrailOrErrorResponse`
- 可附带 routing / planning trace

### 阶段失败停止

首版建议优先实现“保守停止”：

- 某阶段失败时，如果当前路径无法形成可信降级结果，则直接停止
- 某阶段失败时，如果还能形成有限回答，则返回 `degraded` 响应

### 为什么首版不先做完整步骤级回退

虽然主 spec 允许有限回退，但当前仓库状态还不适合首轮把它做满：

- event 路径下游能力不完整
- 还没有稳定 execution state 模型
- 先把两条短路径跑通更重要

因此首版设计建议：

- 在 `policies.py` 中先预留回退判定函数
- 先不在首轮实现真正的阶段回退执行
- 把“有限回退”作为第二批 orchestrator 能力

这不违背当前方向，因为主 spec 描述的是 V1 能力目标，而不是要求首个接线提交必须一次性做满全部子能力。

## 与统一 API 入口的接线

### 当前问题

`WorkbenchBackendApiService` 目前仍返回 stub 响应，尚未形成真实后端主链。

### 推荐接线方式

统一入口应改为：

1. 解析 `AnalysisRequest`
2. 获取或构造 `SessionContext`
3. `RouterService.route(...)`
4. `PlannerService.build_plan(...)`
5. `OrchestratorService.execute(...)`
6. 将 `OrchestrationResult` 封装为 `AnalysisResponseEnvelope`

### trace 拼装建议

首版 trace block 建议至少包含：

- routing
- planning
- execution

如果是 `evidence_lookup` 并且 request 要求 trace，可额外附带：

- retrieval

这里的 retrieval trace 不由 orchestrator 自己重建，而是直接摘要自 `RetrievalResult.retrieval_trace`。

## 测试策略

首版 orchestrator 测试重点应围绕“接线正确”和“边界不越位”：

1. `metric_lookup` 计划只执行短路径阶段
2. `evidence_lookup` 计划只执行检索与综合阶段
3. `out_of_scope` 不执行任何常规 runner
4. 每个执行阶段都会生成一条 `StageObservation`
5. `retrieve_evidence` runner 会消费真实 `RetrievalResult`
6. `WorkbenchBackendApiService` 会返回真实 routing / planning / execution trace

首版不强求：

- 真实 session repository 测试
- 真实 event 四阶段全链路测试
- 复杂回退策略测试

## 分阶段实施建议

### 第一批

先落以下内容：

- `OrchestratorService`
- runner 注册表
- `query_structured_data` runner
- `synthesize_brief_answer` runner
- `retrieve_evidence` runner
- `synthesize_report` runner
- `StageObservation` builder
- 统一 API 入口接线

目标：

- `metric_lookup` 跑通
- `evidence_lookup` 跑通

### 第二批

再补：

- execution trace 收口优化
- degraded / guardrail 细化
- 局部 budget 控制
- 首版阶段失败策略

### 第三批

最后再补：

- `collect_event_context`
- `analyze_targets`
- 有限步骤级回退
- session 持久化联动

## 成功标准

本设计对应的首版实现完成后，应满足以下标准：

- 统一后端入口不再只返回 stub
- orchestrator 能真实消费 `Plan`
- `metric_lookup` 短路径能端到端执行
- `evidence_lookup` 路径能端到端执行
- 每个执行阶段都能产生标准化 `StageObservation`
- retrieval 结果通过 orchestrator 进入最终响应
- orchestrator 本身保持薄编排结构，而不是吞下 retrieval / structured data / reporting 细节

## 设计结论

当前最合适的实现路线不是直接冲完整 event 四阶段，而是采用 **中心化 Orchestrator + 阶段 Runner 注册表**，先打通两条真实最小执行链：

- `metric_lookup`
- `evidence_lookup`

这样既能让控制面正式接入已有 retrieval 与 response 能力，又能守住已有 spec 规定的职责边界，为后续 event 主链、session 和记分式 trace 留出稳定扩展位。
