## ADDED Requirements

### Requirement: 共享 contract 目录定义跨模块 canonical object
项目 MUST 维护一份统一的共享 contract 目录，用于定义 FinSight Agent V1 中被多个模块复用的核心对象，包括 `RouterResult`、`Plan`、`SessionContext`、`StageObservation`、`EvidenceBundle`、`FinalResponse`、`TraceBlock` 以及 guardrail / error response。

#### Scenario: 团队需要查询共享对象定义
- **WHEN** 任一模块团队需要生产或消费某个 V1 共享对象
- **THEN** 共享 contract 目录 MUST 提供该对象的必填字段、字段语义、producer、consumer 和 degraded-state 约定

### Requirement: 每个共享 contract 具有唯一语义 owner
每一个共享 contract MUST 指定且仅指定一个语义 owner capability，由它负责审批 required field 变更并维护对象语义边界。

#### Scenario: 有团队提出 required field 变更
- **WHEN** 某个团队提出新增、删除或重定义共享 contract 的 required field
- **THEN** 该变更 MUST 经过对应 owner capability 评审，并识别受影响的下游 consumer 之后才能接受

### Requirement: 共享 contract 提供并行开发示例
共享 contract 目录 MUST 为关键对象提供示例 payload 或等价 fixture，使下游团队在上游实现未完成前也能开展 mock-based 开发。

#### Scenario: 下游在上游实现完成前启动开发
- **WHEN** 某个消费方团队需要早于上游 producer 完成实现而开始开发
- **THEN** 共享 contract 目录 MUST 提供符合 canonical contract 的示例 payload，足以支持本地开发和联调准备
