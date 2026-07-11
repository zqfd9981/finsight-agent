## REMOVED Requirements

- `Planner 输出稳定的 V1 计划骨架`
- `Planner 显式编码步骤约束`

## MODIFIED Requirements

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

#### Scenario: Router 处理泛财经常识问题
- **WHEN** 用户询问不属于结构化指标、事件影响或证据查找范畴的泛财经常识问题（例如降息对债市的机制性影响）
- **THEN** router 必须返回一个 `general_finance_qa` intent，并附带置信度和指向 LLM 直答的执行需求

#### Scenario: Router 处理超范围问题
- **WHEN** 用户请求投资建议、荐股或股价预测等 V1 范围外问题
- **THEN** router 必须返回一个 `out_of_scope` intent，并附带置信度和受约束的响应指令；泛财经问题不得被标记为 `out_of_scope`

### Requirement: Router 将追问类型作为独立维度处理
系统 MUST 将 follow-up 关系与 intent 分开判别，使同一个 intent 可以根据用户是在 drilldown、compare、expand 还是 redirect 而采用不同执行方式。

#### Scenario: Drilldown 保持相同核心任务
- **WHEN** 用户要求展开某个历史结论背后的更多证据
- **THEN** router 必须保留底层分析 intent，同时把 follow-up type 标记为 `drilldown`

#### Scenario: Redirect 触发重新规划
- **WHEN** 用户在同一会话中切换到一个实质不同的话题
- **THEN** router 必须把 follow-up type 标记为 `redirect`，并输出允许 orchestrator 重新解析 stage 列表的结果

## ADDED Requirements

### Requirement: Orchestrator 通过查表解析 stage 列表
系统 MUST 通过纯查表函数将 (intent, strategy) 映射为 (stages, stage_constraints, response_mode)，不调用 LLM。查表函数吸收原 planner 的 stage 编排职责，router 只做意图识别，classifier 只对 `event_impact_analysis` 做 strategy 三分类。

#### Scenario: metric_lookup 走快路径
- **WHEN** router 返回一个 `metric_lookup` intent 且无 strategy
- **THEN** 查表函数必须输出 `query_structured_data → synthesize_answer` 两个 stage，`response_mode` 为 `brief_answer`，不得进入事件上下文收集或目标分析阶段

#### Scenario: event_impact_analysis 按 strategy 分叉
- **WHEN** router 返回一个 `event_impact_analysis` intent 且 classifier 给出 strategy
- **THEN** 查表函数必须按 strategy 输出对应的 stage 列表：`event_primary` 走 `collect_event_context → synthesize_answer`（event_answer）；`disclosure_primary` 走 `collect_event_context → retrieve_evidence → synthesize_answer`（report）；`dual_primary` 走 `collect_event_context → analyze_targets → retrieve_evidence → synthesize_answer`（report）

#### Scenario: general_finance_qa 单 stage 直答
- **WHEN** router 返回一个 `general_finance_qa` intent
- **THEN** 查表函数必须只输出 `synthesize_answer` 单个 stage，`response_mode` 为 `direct`，不进入任何检索或结构化数据查询阶段

### Requirement: 泛财经常识问题走轻路径直答
系统 MUST 将不属于 metric/event/evidence 但属于金融领域的 query 识别为 `general_finance_qa`，走单 stage LLM 直答，不进入检索。该轻路径以 `response_mode=direct` 切换 prompt 模板。

#### Scenario: 宏观机制解释
- **WHEN** 用户询问降息对债市意味着什么这类宏观机制问题
- **THEN** 系统必须识别为 `general_finance_qa`，仅执行 `synthesize_answer` 单个 stage 并以 `direct` 模式生成回答，不调用检索或结构化数据查询

#### Scenario: 概念解释
- **WHEN** 用户询问某个金融概念的定义或含义
- **THEN** 系统必须识别为 `general_finance_qa`，仅执行 `synthesize_answer` 单个 stage 并以 `direct` 模式生成回答，不得被标记为 `out_of_scope`
