## 重点关注

- 四阶段主计划如何被执行
- 哪些局部重试、步骤回退和 observation 归一化在 V1 中被允许

## 非职责范围

- 不拥有 session、retrieval、structured data、report 的底层数据定义主权
- 不把所有下游能力吸纳成单体实现

## 上下游关系

- 上游输入：router result、plan、session context、structured data outputs、retrieval outputs
- 下游输出：标准化 stage observation、degraded observation、最终编排结果

## ADDED Requirements

### Requirement: Orchestrator 每轮执行单一主计划
系统 MUST 为每个用户轮次执行一个主计划，并且在 V1 分析过程中避免无界的整轮重规划。

#### Scenario: 首轮计划端到端执行
- **WHEN** planner 输出一个受支持的四阶段分析计划
- **THEN** orchestrator 必须按顺序执行这些阶段，并收集 stage observation 供下游模块消费

#### Scenario: 返回超范围路由结果
- **WHEN** router 或 planner 将该轮标记为超范围
- **THEN** orchestrator 必须停止常规执行，并直接转交给受约束响应生成逻辑

### Requirement: Orchestrator 支持有限的步骤内探索
系统 MUST 允许在不改变顶层计划的前提下，在单个 step 内进行有界重试、query rewrite 和局部搜索优化。

#### Scenario: 事件上下文检索需要追加搜索
- **WHEN** `collect_event_context` 在第一次尝试后未能收集到足够的新闻证据
- **THEN** orchestrator 必须允许在该步骤的配置 budget 内执行额外检索尝试

#### Scenario: 证据检索需要局部重跑
- **WHEN** evidence 阶段检测到低质量或弱对齐的检索结果
- **THEN** orchestrator 必须允许在现有 `retrieve_evidence` 阶段内执行有界的检索优化

### Requirement: Orchestrator 支持有限的步骤级回退
系统 MUST 只在后续阶段发现前置条件缺失且仍可在有界范围内修复时，才允许回退到前一个关键步骤。

#### Scenario: 证据阶段暴露目标收敛不足
- **WHEN** `retrieve_evidence` 发现当前目标候选范围过宽，无法检索到可靠证据
- **THEN** orchestrator 必须能够先回到 `analyze_targets` 执行一次有界优化，再继续后续步骤

#### Scenario: 综合阶段发现引用缺失
- **WHEN** `synthesize_report` 因引用不完整而无法支撑某个关键结论
- **THEN** orchestrator 必须能够请求对 `retrieve_evidence` 进行一次有界重试，而不是丢弃整轮分析

### Requirement: Orchestrator 记录标准化 observation
系统 MUST 把每个阶段的输出归一化为结构化 observation，以便 critic、报告生成、trace 渲染和评测共同消费。

#### Scenario: 阶段成功完成
- **WHEN** 某个阶段以可用输出结束
- **THEN** orchestrator 必须持久化一条 stage observation，其中包含阶段输入摘要、关键输出、置信度信号和证据引用

#### Scenario: 阶段降级或失败
- **WHEN** 某个阶段无法正常完成
- **THEN** orchestrator 必须持久化一条 degraded observation，记录阻塞原因、缓解路径和剩余可继续推进的选项
