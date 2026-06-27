## Purpose

定义 FinSight Agent V1 的任务理解能力，包括语义路由、追问类型判别、长短路径计划生成和步骤级约束表达。

## 重点关注

- 输入问题的 intent 判别、follow-up type 判别与 V1 长短路径 plan 骨架
- 步骤级约束如何被显式编码，而不是埋在自由文本里

## 非职责范围

- 不直接执行结构化数据查询与文档检索
- 不负责最终报告编写与前端展示

## 上下游关系

- 上游输入：query、`session_context`
- 下游输出：router result、follow-up type、plan skeleton、stage constraints

## Requirements

### Requirement: 语义路由输出结构化意图结果
系统 MUST 将每一个输入问题分类为结构化的 router 结果，并把 intent、语义对象和执行需求分层表达。

#### Scenario: Router 处理简单结构化查询问题
- **WHEN** 用户询问某个公司某一年的净利润、营收或其他单个结构化事实
- **THEN** router 必须返回一个 `metric_lookup` intent，并包含公司、指标、时间范围、置信度和执行需求

#### Scenario: Router 处理事件影响分析问题
- **WHEN** 用户询问某个国际事件可能利好哪些 A 股板块或公司
- **THEN** router 必须返回一个 `event_impact_analysis` intent，并包含提取出的实体、主题、时间范围、置信度和执行需求

#### Scenario: Router 处理证据查找问题
- **WHEN** 用户围绕某个已知公司、候选对象或结论要求补充支持证据
- **THEN** router 必须返回一个 `evidence_lookup` intent，并包含目标对象、待验证 claim、置信度和执行需求

#### Scenario: Router 处理超范围问题
- **WHEN** 用户请求 V1 范围外的短线股价预测或完整估值模型
- **THEN** router 必须返回一个 `out_of_scope` intent，并附带置信度和受约束的响应指令

### Requirement: Router 将追问类型作为独立维度处理
系统 MUST 将 follow-up 关系与 intent 分开判别，使同一个 intent 可以根据用户是在 drilldown、compare、expand 还是 redirect 而采用不同执行方式。

#### Scenario: Drilldown 保持相同核心任务
- **WHEN** 用户要求展开某个历史结论背后的更多证据
- **THEN** router 必须保留底层分析 intent，同时把 follow-up type 标记为 `drilldown`

#### Scenario: Redirect 触发重新规划
- **WHEN** 用户在同一会话中切换到一个实质不同的话题
- **THEN** router 必须把 follow-up type 标记为 `redirect`，并输出允许 planner 重建主计划的结果

### Requirement: Planner 输出稳定的 V1 计划骨架
系统 MUST 把受支持的 router 输出转换为一个受约束的 V1 plan。对于 `event_impact_analysis`，该 plan 由 `collect_event_context`、`analyze_targets`、`retrieve_evidence` 和 `synthesize_report` 组成；对于 `metric_lookup` 和 `evidence_lookup`，允许输出更短的阶段序列，但仍必须保持结构化计划。

#### Scenario: Planner 构建完整事件影响分析计划
- **WHEN** router 返回一个受支持的事件影响分析结果
- **THEN** planner 必须输出一个有序 plan，其中只包含必要的 V1 阶段以及各阶段所需的执行约束

#### Scenario: Planner 为 metric lookup 使用快路径
- **WHEN** router 识别出一个面向单个结构化事实的 `metric_lookup` 任务
- **THEN** planner 必须输出一个短计划，直接进入结构化数据查询和简短答案综合，不得强行进入事件上下文收集或目标分析阶段

#### Scenario: Planner 为 evidence lookup 缩减步骤
- **WHEN** router 识别出一个面向已选公司或 claim 的 `evidence_lookup` 任务
- **THEN** planner 必须输出一个缩减后的阶段序列，跳过不必要的目标分析，同时保留证据检索和报告综合步骤

### Requirement: Planner 显式编码步骤约束
系统 MUST 在 plan 中显式包含 time hint、retrieval budget 和 preferred output 等约束，而不是把这些信息隐含在自由文本 prompt 里。

#### Scenario: 时间敏感的事件上下文规划
- **WHEN** 用户明确提到近期或历史时间窗口
- **THEN** planner 必须为事件上下文收集阶段加入机器可读的 time hint

#### Scenario: 检索探索必须保持有界
- **WHEN** 某个阶段需要进行外部或本地检索
- **THEN** planner 必须编码有界的重试与 retrieval budget 约束，以限制该阶段的搜索循环
