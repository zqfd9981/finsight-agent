## Purpose

定义 FinSight Agent V1 的多轮会话状态能力，包括状态持久化、上下文压缩、追问继承和缺失状态下的降级处理。

## 重点关注

- 会话状态如何持久化、压缩与继承
- 追问时哪些历史信息应该进入当前轮次上下文

## 非职责范围

- 不负责 intent 判别与主计划生成
- 不负责 UI 展示和最终报告生成

## 上下游关系

- 上游输入：用户轮次、历史 observation、历史结论摘要
- 下游输出：压缩后的 `session_context`，供 router 与 planner 消费

## Requirements

### Requirement: 会话状态持久化分析上下文
系统 MUST 为每个分析会话持久化结构化的 session state，使后续轮次只复用 V1 事件影响分析所需的上下文。

#### Scenario: 首轮分析完成后创建会话状态
- **WHEN** 一次首轮分析成功完成
- **THEN** 系统必须持久化一条会话记录，至少包含当前 query、解析后的 intent、选中的主题、候选股票、检索到的证据、计划步骤、critic 备注以及最终报告摘要

#### Scenario: 追问轮次加载会话状态
- **WHEN** 一个携带已有 session 标识的追问到达系统
- **THEN** 系统必须加载已存储的会话状态，并向下游 routing 和 planning 阶段提供压缩后的 session context 对象

### Requirement: 会话状态区分相关上下文与完整历史
系统 MUST 提供压缩后的 session context 视图，而不是把完整原始对话逐轮传给每个 planning step。

#### Scenario: Planner 请求追问上下文
- **WHEN** planner 为一个已有会话启动新轮次
- **THEN** 系统必须提供一个摘要化上下文，其中包含与当前轮次相关的当前主题、活跃候选对象、关键证据引用和历史执行 trace 要点

#### Scenario: 会话中存在无关历史
- **WHEN** 历史轮次中包含已经失效或已经改道的分析路径
- **THEN** 系统必须在当前轮次使用的压缩上下文中排除这些无关的原始历史

### Requirement: 会话状态支持追问类型判别
系统 MUST 存储足够的轮次元数据，以便 router 将追问判别为 `none`、`drilldown`、`compare`、`expand` 或 `redirect`。

#### Scenario: 用户比较上一轮候选对象
- **WHEN** 用户要求比较上一轮产出的候选对象
- **THEN** 系统必须把上一轮候选对象标识和摘要结论作为 session context 暴露给 follow-up 分类逻辑

#### Scenario: 会话缺少可用的历史上下文
- **WHEN** 用户提交的问题携带 session 标识，但历史状态缺失或不完整
- **THEN** 系统必须将该轮视为一次新的分析或一次降级追问，而不能伪造继承上下文
