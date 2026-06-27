## ADDED Requirements

### Requirement: 并行交付治理定义模块分组与依赖图
项目 MUST 将现有 7 个 V1 spec 归入明确的并行交付模块群，并发布这些模块群之间的依赖关系，用于判断哪些工作可以独立推进、哪些需要协同检查点。

#### Scenario: 项目为并行实现分配 owner
- **WHEN** 项目开始为模块或团队分配 owner
- **THEN** 交付治理文档 MUST 标明每个 spec 所属的模块群，以及影响其联调顺序的上下游依赖

### Requirement: 项目状态文档跟踪真实交付状态
项目 MUST 维护一份统一的状态文档，记录按 spec 或按模块群的 owner、当前状态、依赖、blocker、里程碑和完成定义。

#### Scenario: 负责人查看当前推进状态
- **WHEN** 项目负责人或模块 owner 需要查看当前交付就绪度
- **THEN** 状态文档 MUST 直接展示各 spec 或模块群的当前进展与活跃 blocker，而不依赖各团队各自维护的私有笔记

### Requirement: 联调就绪检查点依赖 contract ready
项目 MUST 定义以 canonical contracts 和 mock payload 就绪为前提的联调检查点，使下游模块不必等待所有上游 live implementation 完成后才能启动。

#### Scenario: 下游模块在 live integration 前先行开发
- **WHEN** 某个下游团队已经拿到审批通过的共享 contract 和 mock payload
- **THEN** 交付治理文档 MUST 允许该团队先进入实现和本地验证，而不是等待上游 producer 的 live output 完全可用
