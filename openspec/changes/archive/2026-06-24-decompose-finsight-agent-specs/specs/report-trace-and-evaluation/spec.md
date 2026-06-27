## 重点关注

- 最终报告结构、trace 输出、guardrail 降级结构与人工评测组织方式
- 如何让“可展示”和“可评测”共享同一套输出口径

## 非职责范围

- 不重新做路由和检索
- 不替代 orchestrator 做流程决策

## 上下游关系

- 上游输入：stage observations、evidence bundle、critic notes
- 下游输出：最终 response、trace blocks、golden query 评测材料

## ADDED Requirements

### Requirement: 最终报告使用稳定的分析结构
系统 MUST 生成结构稳定的 V1 分析报告，至少包含结论摘要、影响链条、候选对象、证据支撑和不确定性说明。

#### Scenario: 生成受支持的事件影响分析报告
- **WHEN** 一次事件影响分析在具备可用证据的前提下完成
- **THEN** 最终响应必须把答案组织为报告区块，覆盖结论、影响逻辑、候选板块或公司以及证据支撑

#### Scenario: 报告中存在未消除的不确定性
- **WHEN** 证据或映射结果仍然不完整
- **THEN** 报告必须显式说明不确定性，并且不能把未解决的问题写成已确认事实

### Requirement: Trace 输出暴露关键推理产物
系统 MUST 把 routing、planning、retrieval、rerank 和 critic verification 的 trace 数据作为结构化辅助输出暴露出来，以支持调试和评测。

#### Scenario: 成功运行时渲染 trace
- **WHEN** 某一轮成功完成
- **THEN** 系统必须提供 router 结果、计划步骤、检索证据、rerank 结果和 critic 备注等 trace 区块

#### Scenario: 降级运行时渲染 trace
- **WHEN** 某一轮因信息不足、映射失败或证据薄弱而降级
- **THEN** trace 必须包含降级原因以及正常流程停止的阶段

### Requirement: Guardrail 响应使用统一降级结构
系统 MUST 通过统一的响应结构表达降级结果，明确当前推进程度、阻塞原因和建议的下一步用户动作。

#### Scenario: 信息不足响应
- **WHEN** 工作流无法收集到可靠的外部事件上下文
- **THEN** 响应必须说明当前还能给出什么结论、为什么无法继续深入，以及补充哪些输入会有帮助

#### Scenario: 证据不足响应
- **WHEN** 工作流已经识别出目标对象，但无法用本地证据验证关键 claim
- **THEN** 响应必须把相关判断标记为暂定，并解释缺失证据的边界

### Requirement: 评测采用分桶的 Golden Query 机制
系统 MUST 定义一个基于分桶 golden query、逐题 rubric 和多维评分的 V1 评测方案。

#### Scenario: 为 V1 组织评测集
- **WHEN** 项目准备首批人工评测包
- **THEN** 评测集必须按首轮事件分析、证据 drilldown、对比分析以及 guardrail 或超范围场景进行分桶

#### Scenario: 人工评测者为 query 打分
- **WHEN** 评审者对某条 golden query 的结果进行评估
- **THEN** 系统必须提供带明确维度和 `0 / 1 / 2` 评分指引的 rubric，而不是依赖自由发挥的主观意见
