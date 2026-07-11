## MODIFIED Requirements

### Requirement: Orchestrator 每轮执行单一主计划
系统 MUST 为每个用户轮次执行一个主计划，并且在 V1 分析过程中避免无界的整轮重规划。

#### Scenario: 首轮计划端到端执行
- **WHEN** stage_planner 解析出一个受支持的多阶段分析计划
- **THEN** orchestrator 必须按顺序执行这些阶段，并收集 stage observation 供下游模块消费

#### Scenario: 简单结构化查询走短路径执行
- **WHEN** stage_planner 解析出一个面向 `metric_lookup` 的短计划
- **THEN** orchestrator 必须只执行计划中出现的阶段，直接完成结构化数据查询与简短回答综合，而不是强行进入事件分析主链路

#### Scenario: 返回超范围路由结果
- **WHEN** router 将该轮标记为超范围
- **THEN** orchestrator 必须停止常规执行，并直接转交给受约束响应生成逻辑

### Requirement: Orchestrator 支持有限的步骤级回退
系统 MUST 只在后续阶段发现前置条件缺失且仍可在有界范围内修复时，才允许回退到前一个关键步骤。

#### Scenario: 证据阶段暴露目标收敛不足
- **WHEN** `retrieve_evidence` 发现当前目标候选范围过宽，无法检索到可靠证据
- **THEN** orchestrator 必须能够先回到 `analyze_targets` 执行一次有界优化，再继续后续步骤

#### Scenario: 综合阶段发现引用缺失
- **WHEN** `synthesize_answer` 因引用不完整而无法支撑某个关键结论
- **THEN** orchestrator 必须能够请求对 `retrieve_evidence` 进行一次有界重试，而不是丢弃整轮分析
