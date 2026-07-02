# Event Impact Analysis Stage Design

## 背景

截至 2026-07-02，FinSight 已经具备以下基础能力：

- `semantic-routing-and-planning` 已能稳定输出 `event_impact_analysis` 的四阶段 `Plan`
- orchestrator 已打通 `metric_lookup` 与 `evidence_lookup` 两条真实执行链
- `retrieve_evidence` runner 已预留对 `collect_event_context` 和 `analyze_targets` 输出的消费位点
- 本地结构化市场数据首版已落地，`metric_lookup` 已不再返回 `TODO`
- retrieval facade 已能稳定返回结构化 `RetrievalResult`

当前最大空洞在于：`event_impact_analysis` 已能被 router 与 planner 识别并规划，但 orchestrator 仍缺少前两阶段的真实执行能力，导致主分析链仍停留在“可规划、不可执行”的状态。

本设计只新增本轮设计文档，不修改现有 OpenSpec 主规格文档。

## 目标

本轮设计目标是为 `event_impact_analysis` 的首版真实执行链定义清晰的阶段职责和实现边界，重点包括：

- 明确四个 stage 的职责分工
- 明确三类检索能力在各 stage 中的使用关系
- 定义每个 stage 内部“调用几种、调用几次、失败如何处理”
- 引入 LLM 参与 `analyze_targets`，但保持结构化边界和可回归性
- 为后续 implementation plan 提供可直接落地的输入输出设计

## 非目标

- 不在本轮直接写实现代码
- 不重写现有 router、planner、retrieval 或 structured data 的 contract
- 不把 `event_impact_analysis` 做成全开放 agent 循环
- 不在首版引入复杂跨 stage 回跳
- 不让 LLM 成为事件分析链中的唯一事实来源

## 当前问题定义

`event_impact_analysis` 当前缺的不是意图识别或计划生成，而是执行面缺少两个关键生产阶段：

1. `collect_event_context`
2. `analyze_targets`

而后两个阶段已经具备部分基础：

3. `retrieve_evidence`
4. `synthesize_report`

因此首版正确方向不是重拆 plan，而是在保持既有四阶段骨架不变的前提下，补齐前两阶段的真实 runner，并让后两阶段消费它们的标准化输出。

## 四个 Stage 的职责定义

### 1. `collect_event_context`

职责：先把“事件背景”讲清楚。

它回答的问题是：

- 事件是什么
- 涉及哪些主题或行业
- 当前时间范围是什么
- 有没有足够的初步背景证据支持继续分析

它的核心任务是“找材料、压上下文”，而不是直接判断哪些公司受益。

### 2. `analyze_targets`

职责：基于事件上下文，判断哪些目标更可能受影响。

它回答的问题是：

- 哪些公司或板块值得优先关注
- 是受益、受损还是待验证
- 哪些对象优先级更高
- 还存在哪些关键不确定点

它的核心任务是“做判断、产结构”，而不是重新做大范围检索。

### 3. `retrieve_evidence`

职责：围绕已分析出的目标，补强论据。

它回答的问题是：

- 对前一阶段选出的目标，有没有更直接的支撑证据
- 哪些财报、公告、段落、表格、外部材料可以支撑最终报告

它的核心任务是“围绕目标验证结论”，而不是再做事件背景收集。

### 4. `synthesize_report`

职责：将事件背景、目标分析和证据结果组织成最终报告。

它回答的问题是：

- 最终如何向用户表达本轮分析
- 哪些对象值得关注
- 核心依据是什么
- 哪些判断仍然存在不确定性

它不直接检索，只消费前三个阶段的结果。

## 三类检索能力

本轮将检索能力分为三类：

### 1. 结构化数据检索

用于查询：

- 指标值
- 报告期数值
- 可标准化的财务事实

当前对应能力：

- `StructuredDataService`

### 2. RAG 混合检索

用于查询：

- 本地公告
- 财报段落
- 表格上下文
- 已解析文档中的证据片段

当前对应能力：

- `RetrievalFacade.retrieve_evidence(...)`

### 3. 外部工具检索

用于查询：

- 本地语料缺失的近期事件
- 外部公开信息
- 时效性较强的新闻或披露线索

首版设计中将其抽象为外部检索 provider / tool adapter，不在本轮规定具体供应商实现。

## 方案对比

### 方案 A：纯规则候选分析

做法：

- `collect_event_context` 用检索拿背景
- `analyze_targets` 只用规则把 theme 映射成公司或板块

优点：

- 最稳定
- 最容易测试

缺点：

- 语义理解弱
- 对复杂事件会很僵硬

### 方案 B：LLM 完全主导前两阶段

做法：

- 前两阶段都大量依赖 LLM，自由生成目标和推理

优点：

- 语义能力最强

缺点：

- 不稳定
- 幻觉风险高
- 很难做回归

### 方案 C：结构化骨架 + 受约束 LLM 分析

做法：

- `collect_event_context` 先用检索建立结构化事件上下文
- `analyze_targets` 基于事件上下文和候选池，使用受约束 LLM 输出标准结构结果

优点：

- 比纯规则灵活
- 比全放开 LLM 稳定
- 最符合当前仓库的 contract 风格

缺点：

- 需要额外定义输入输出 schema
- prompt 和校验要更细

## 推荐方案

采用 **方案 C：结构化骨架 + 受约束 LLM 分析**。

决策理由：

1. 事件影响判断天然需要语义理解，不适合只靠规则
2. 当前系统已经在 session、router、planner、structured data 上建立了结构化 contract，LLM 更适合作为“受约束分析器”，而不是唯一真相源
3. 该方案能最大化复用现有 retrieval 与 structured data，又能避免把 `event_impact_analysis` 做成不可控的自由代理循环

## Stage 输入输出设计

### `collect_event_context` 输入

- `request.query`
- `router_result.entities.event`
- `router_result.entities.themes`
- `router_result.entities.time_scope`
- `stage_constraints.time_hint`
- `stage_constraints.retrieval_budget`

### `collect_event_context` 输出

```python
{
  "event_context": {
    "event": "红海局势升级",
    "themes": ["航运", "油运", "出海链"],
    "time_scope": "recent",
    "context_summary": "事件导致航线扰动与绕航预期上升，可能影响航运与港口链。",
    "supporting_points": [
      "航线风险上升导致运输路径调整预期增强",
      "运价波动可能影响航运细分板块盈利弹性"
    ],
    "evidence_refs": ["evd_001", "evd_002"]
  },
  "event_entities": {
    "event": "红海局势升级",
    "themes": ["航运", "油运", "出海链"],
    "time_scope": "recent"
  },
  "source_status": {
    "external": "success",
    "local_rag": "weak"
  }
}
```

### `analyze_targets` 输入

- `request.query`
- `router_result.entities`
- `collect_event_context.event_context`
- 可选 `session_context.active_candidates`
- 结构化候选池

### `analyze_targets` 输出

```python
{
  "target_scope": ["中远海能", "招商轮船", "宁波港"],
  "ranked_targets": [
    {
      "target": "中远海能",
      "impact_direction": "positive",
      "reasoning_summary": "若绕航和运价上行持续，油运相关标的可能受益。",
      "confidence": "medium"
    },
    {
      "target": "招商轮船",
      "impact_direction": "positive",
      "reasoning_summary": "与航运运价弹性相关，但仍需更多公司级证据验证。",
      "confidence": "medium"
    }
  ],
  "open_questions": [
    "运价波动是否已被近期回落抵消",
    "不同航运细分领域受影响是否一致"
  ],
  "analysis_mode": "llm_constrained"
}
```

### `retrieve_evidence` 输入

- `request.query`
- `collect_event_context.event_context`
- `analyze_targets.target_scope`
- `analyze_targets.ranked_targets`
- `stage_constraints.retrieval_budget`

### `retrieve_evidence` 输出

沿用现有：

- `retrieval_result`
- `evidence_refs`

同时建议补充：

- `target_coverage`
- `source_status`

### `synthesize_report` 输入

- `collect_event_context`
- `analyze_targets`
- `retrieve_evidence`

### `synthesize_report` 输出

沿用现有 `FinalResponse`，但首版应显式包含：

- `summary`
- `report_blocks`
- `uncertainty_notes`
- `next_actions`

## 每个 Stage 的内部调用策略

本设计不让每个 stage 把三种检索全打一遍，而是要求“按目标分工，有限调用，有限补救”。

### 统一状态语义

每次检索调用统一归为四种状态：

- `success`
- `weak`
- `empty`
- `error`

后续的补救、降级和继续执行逻辑只根据这四种状态判断。

### `collect_event_context` 的内部调用逻辑

目标：先获得足够清晰的事件上下文。

默认预算：最多 3 次检索动作。

推荐顺序：

1. 外部工具检索 1 次
2. 本地 RAG 检索 1 次
3. 自适应补 1 次

自适应补的规则：

- 如果外部工具结果为 `empty` 或 `weak`，补一次外部改写检索
- 如果本地 RAG 结果为 `empty` 或 `weak`，补一次本地 query rewrite 检索
- 如果两边都弱，只补优先级更高的一边，不同时补两边

成功条件：

- 合并后 `evidence_refs >= 2`
- 且能稳定提取 `event`、`themes`、`time_scope`、`context_summary`

降级规则：

- 外部为空、本地有结果：继续，标记 `freshness_low`
- 本地为空、外部有结果：继续，标记 `local_support_missing`
- 两边都弱：返回 `degraded`
- 两边都空且无法生成最小事件上下文：返回 `failed`

### `analyze_targets` 的内部调用逻辑

目标：基于事件上下文输出结构化目标判断。

默认预算：

- LLM 主调用 1 次
- schema 修复最多 1 次

它默认不进行重检索。

处理步骤：

1. 从 `collect_event_context`、router entities、session active candidates、主题映射候选中组装候选池
2. 以结构化输入调用 LLM
3. 检查输出 schema
4. 若 schema 不合法，仅允许 1 次修复调用

成功条件：

- `target_scope` 非空
- 至少有 1 个 `ranked_target`
- 每个目标至少有 `impact_direction`、`reasoning_summary`、`confidence`

降级规则：

- 候选池不足但主题明确：允许退化成板块/主题级 `target_scope`
- LLM 输出合法但信号不足：允许 `confidence=low`
- LLM 输出连续两次不合法：返回 `failed`

### `retrieve_evidence` 的内部调用逻辑

目标：围绕已分析出的目标，补公司级或板块级证据。

默认预算：最多 4 次检索动作。

推荐顺序：

1. 本地 RAG：top1 target
2. 本地 RAG：top2 target 或 query rewrite
3. 结构化数据检索 1 次
4. 外部工具兜底 1 次

说明：

- 本地 RAG 是主路径
- 结构化数据只做补强，不替代证据链
- 外部工具仅在本地证据明显不足时兜底

成功条件：

- top1 有至少 2 条较强 evidence，或
- top1/top2 合计至少 3 条可引用 evidence

降级规则：

- RAG 强、结构化空：继续
- RAG 弱、结构化有：只能 `degraded`
- 本地都弱、外部有：继续但标记 `external_support_used`
- 全部弱：`degraded` 或 `failed`

### `synthesize_report` 的内部调用逻辑

目标：把分析与证据组织成最终可读报告。

它不直接检索。

规则：

- 若 `retrieve_evidence` 为 `degraded`，报告中必须显式写入不确定性
- 若只有背景、没有足够目标级证据，可以输出方向性分析，但不能伪装成强结论

## 候选池设计

`analyze_targets` 不应凭空让 LLM 猜目标。

首版候选池建议来自以下来源：

1. router 的 `themes`
2. `collect_event_context` 证据中显式出现的公司、板块、行业词
3. `session_context.active_candidates`
4. 本地轻量主题映射表
5. 可选结构化数据线索

其中：

- 主题映射表用于提供最小候选集合
- LLM 用于在候选集合内排序和判断正负方向
- 不要求首版就构建完整概念股知识图谱

## LLM 约束原则

LLM 进入首版主链，但必须受约束：

1. 不允许脱离候选池自由发散到无限公司集合
2. 不允许忽略 `collect_event_context` 的事实底座
3. 输出必须符合固定 schema
4. 允许返回低置信度和待验证问题，而不是强行给出确定结论

换句话说，LLM 在本设计里扮演的是“结构化分析器”，不是“自由研究员”。

## 失败与降级语义

首版推荐统一语义：

- `success`：结果足以被下游稳定消费
- `partial`：结果可消费，但信息覆盖不完整
- `degraded`：结果可面向用户降级展示，但不足以支撑强结论
- `failed`：连最小可消费结构都无法产出

执行原则：

- 能产出最小结构就尽量 `degraded`
- 只有在完全产不出结构时才 `failed`
- 首版不做跨 stage 回跳，失败后直接按当前状态停下或生成降级结果

## 与现有 orchestrator 的衔接

当前 `retrieve_evidence` runner 已经会从 `execution_state` 读取：

- `collect_event_context`
- `analyze_targets`

因此首版实现不应改 plan 形状，而应遵守现有消费位点：

- `collect_event_context.output_payload.event_context`
- `collect_event_context.output_payload.event_entities`
- `analyze_targets.output_payload.target_scope`

必要时允许在 `analyze_targets` 中补充更多字段，但不能破坏既有关键消费键。

## 测试策略

首版测试应覆盖：

1. `collect_event_context` 在外部成功 / 本地弱时仍能产出最小上下文
2. `collect_event_context` 在两边都弱时返回 `degraded`
3. `analyze_targets` 能消费事件上下文并输出标准结构
4. `analyze_targets` 的 LLM 非法输出会触发一次 schema 修复
5. `retrieve_evidence` 能消费 `target_scope`
6. `event_impact_analysis` 从 `route -> plan -> orchestrate -> envelope` 可走通首版真实链路

首版不强求：

- 完整多轮 session 驱动的 event follow-up
- 复杂跨阶段回跳
- 大规模评测集

## 分阶段实施建议

### 第一阶段

补齐：

- `collect_event_context` runner
- `analyze_targets` runner
- 轻量外部检索 provider 抽象
- 受约束 LLM 输出 schema

### 第二阶段

补齐：

- `event_impact_analysis` 端到端测试
- degraded 结果的 reporting 展示
- 候选池映射增强

### 第三阶段

再考虑：

- 跨 stage 有限回跳
- 更复杂的行业/概念映射
- 更多结构化指标协同
- 评测样本与回归集

## 设计结论

`event_impact_analysis` 的首版真实执行链应保持现有四阶段骨架不变：

- `collect_event_context`
- `analyze_targets`
- `retrieve_evidence`
- `synthesize_report`

其中：

- `collect_event_context` 负责“事件背景检索与上下文压缩”
- `analyze_targets` 负责“基于事实底座的受约束 LLM 目标分析”
- `retrieve_evidence` 负责“围绕候选目标补强证据”
- `synthesize_report` 负责“最终报告组织与不确定性表达”

这是当前仓库状态下最平衡的方案：既能引入 LLM 的语义能力，又不会破坏现有结构化 contract 和可测试性边界。
