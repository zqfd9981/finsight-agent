## 1. 共享 Contract 基础

- [x] 1.1 编写 canonical shared-contract 文档，覆盖 `RouterResult`、`Plan`、`SessionContext`、`StageObservation`、`EvidenceBundle`、`FinalResponse`、`TraceBlock` 以及 guardrail / error response
- [x] 1.2 为每个共享对象补充 owner、producer、consumer、必填字段和 degraded semantics
- [x] 1.3 为每个共享对象补充 mock payload 或等价示例，供下游模块并行开发使用

## 2. 并行交付治理

- [x] 2.1 明确 7 个现有 spec 的 3 个模块群，并整理依赖关系图
- [x] 2.2 创建统一的项目状态文档模板，包含 owner、状态、依赖、blocker、里程碑和完成定义
- [x] 2.3 填充首版项目状态文档，记录当前各 spec 或模块群的初始推进状态

## 3. 联调准备

- [x] 3.1 定义第一批以 contract ready 为前提的联调检查点，而不是等待所有上游逻辑全部完成
- [x] 3.2 明确哪些下游模块可以在 shared contract 和 mock payload 就绪后先行开发
- [x] 3.3 按依赖顺序进入 `/opsx:apply`：先落 shared contracts，再落 delivery governance，最后推进实现与联调
