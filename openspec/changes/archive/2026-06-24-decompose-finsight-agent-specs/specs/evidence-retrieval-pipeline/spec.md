## 重点关注

- 混合检索、parent-child chunking、query 增强、rerank 与 citation 组装
- 证据支持强度如何被保留下来供报告与 trace 使用

## 非职责范围

- 不负责主题/公司映射
- 不负责会话状态管理和最终报告结构定义

## 上下游关系

- 上游输入：待验证 claim、candidate company/topic、retrieval hints
- 下游输出：evidence bundle、support strength、citation metadata、parent context

## ADDED Requirements

### Requirement: 检索流水线支持混合证据检索
系统 MUST 通过同时结合 dense retrieval 和 sparse retrieval 的混合流水线，从年报、半年报和重要公告中检索本地证据。

#### Scenario: Query 通过多种检索模式召回证据
- **WHEN** evidence 阶段接收到一个需要验证的公司或主题 claim
- **THEN** retrieval pipeline 必须先执行 dense retrieval、sparse retrieval 和 fusion，再返回排序后的 child chunk

#### Scenario: 不依赖纯向量检索也能工作
- **WHEN** dense retrieval 质量较弱或向量结果稀少
- **THEN** pipeline 仍然必须能够通过 sparse retrieval 路径返回候选证据

### Requirement: 检索流水线支持 Parent-Child Chunking
系统 MUST 以 parent-child chunk 关系索引本地文档，使最终证据同时具备检索精度和可读上下文。

#### Scenario: 先对 child chunk 进行排序
- **WHEN** pipeline 执行 rerank
- **THEN** 它必须把 child chunk 而不是整个 parent 文档作为主要相关性排序单元

#### Scenario: 最终证据需要可读上下文
- **WHEN** 顶部排序的 child chunk 被选中
- **THEN** pipeline 必须把它们扩展回对应的 parent 单元，并在生成前对重复的 parent 结果去重

### Requirement: 检索流水线组装可追踪引用
系统 MUST 返回保留源文档身份、chunk 关系和引用元数据的 evidence bundle，以满足报告和 trace 视图的需要。

#### Scenario: 报告生成器消费证据
- **WHEN** report generator 请求最终证据支持
- **THEN** pipeline 必须为每个被选中的 claim-supporting 结果返回源标识、可直接用于引用的摘录以及 parent 上下文引用

#### Scenario: 证据无法完全支撑 claim
- **WHEN** 检索结果只能部分支撑请求的结论
- **THEN** pipeline 必须把支撑强度标记为 partial 或 weak，而不能返回暗示“已完全验证”的引用元数据

### Requirement: 检索流水线支持条件式 Query 增强
系统 MUST 保留原始 query，同时允许在有界触发条件下进行有限 rewrite，以及可选启用 HyDE 或 Query2Doc 这类增强技术。

#### Scenario: Query rewrite 改善口语化检索
- **WHEN** 输入的 claim 或事件描述较口语化但仍在范围内
- **THEN** pipeline 必须允许在保留原始 query 的同时，增加少量面向检索的改写 query

#### Scenario: 条件触发高级增强
- **WHEN** 初始检索质量较弱且满足配置的触发条件
- **THEN** pipeline 必须能够把 HyDE 或 Query2Doc 作为次级增强路径启用，而不是默认作用于所有 query
