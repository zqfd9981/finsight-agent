## Why

当前 `openspec/specs` 下的 7 个 V1 spec 已经完成了能力拆分，整体方向是合理的，但还不足以支撑低摩擦的并行开发。现在模块边界已经有了，真正缺的是跨模块共享 contract、职责归属和项目交付节奏的统一约定。

之所以现在就要做这件事，是因为项目已经从“能力划分”进入“准备实现”的阶段。如果继续在没有统一 contract 和交付治理的前提下并行开发，后续最容易出问题的不是功能遗漏，而是 payload 结构漂移、职责理解不一致，以及联调顺序混乱。

## What Changes

- 新增一层共享 contract 定义，用来统一 routing、planning、session、orchestration、retrieval、report、UI 之间的核心对象。
- 新增一层并行交付治理定义，用来整理现有 7 个 spec 的模块分组、依赖关系和联调顺序。
- 定义统一的项目进度文档格式，用于记录 owner、状态、依赖、blocker、里程碑和完成定义。
- 产出按依赖顺序排列的 implementation tasks，先完成 contract 和治理，再进入模块实现与联调。

## Capabilities

### New Capabilities
- `shared-analysis-contracts`：定义 V1 并行开发所需的跨模块共享对象 contract，包括 `RouterResult`、`Plan`、`SessionContext`、`StageObservation`、`EvidenceBundle`、`FinalResponse`、`TraceBlock` 以及 guardrail / error response。
- `parallel-delivery-governance`：定义 7 个现有 spec 的并行开发分组、依赖关系、项目进度跟踪方式和联调就绪检查点。

### Modified Capabilities
<!-- 本次 change 先补齐并行开发基础，不直接改动现有 7 个 capability 的 requirement。后续如需把共享 contract 正式收敛进各 capability，再由对应 change 单独修改。 -->

## Impact

- 影响 `openspec/changes/define-v1-shared-contracts-and-delivery-plan/` 下的 planning artifacts。
- 为现有 7 个 spec 增加一层共享 contract 和项目交付治理约定，但不直接改变 V1 的产品功能范围。
- 为后续多人并行开发提供统一接口口径和项目推进方式，降低联调歧义和协作成本。
