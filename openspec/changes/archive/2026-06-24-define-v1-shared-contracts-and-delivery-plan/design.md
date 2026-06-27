## Context

FinSight Agent V1 目前已经有 7 个 capability spec，分别覆盖 routing / planning、session、orchestration、structured market data、evidence retrieval、report / trace / evaluation，以及 Streamlit workbench。这个拆分已经足够支撑产品范围定义，但还不够支撑多人低摩擦并行开发，因为模块之间传递的核心对象仍然是分散隐含在各自 spec 里的。

当前最大的风险不是“少了某个功能”，而是“接口口径漂移”。不同小组可能都会给出局部上合理的 `Plan`、`SessionContext`、`EvidenceBundle` 或 `FinalResponse` 结构，但如果没有一个统一 contract 文档、明确的 ownership 规则以及项目推进方式，这些定义在实现阶段很容易慢慢偏掉。

同时，项目还缺少一个面向实施的进度视图。现有 7 个 spec 回答的是“系统应该做什么”，但并行开发还需要回答“谁负责什么、哪些可以独立做、哪些会卡在联调边界上、目前卡点在哪里”。

## Goals / Non-Goals

**Goals:**
- 为多个 capability 复用的共享对象建立单一事实来源。
- 给每一个共享对象指定唯一 owner，同时允许多个生产方和消费方存在。
- 保留现有 7 个 spec 的能力拆分，不推倒重来，只在其上增加更清晰的并行开发分组。
- 定义统一的项目进度文档，支持 owner、依赖、blocker、里程碑和完成定义的持续跟踪。
- 让下游模块在上游逻辑未完全实现前，也能基于稳定 contract 和 mock 数据先行开发。

**Non-Goals:**
- 不重新定义 V1 的产品范围。
- 不把现有 7 个 spec 合并成 3 个更大的 capability spec。
- 不用实现任务清单取代 capability spec。
- 不把所有内部对象都强行抽成共享 contract，只处理真正跨模块复用的对象。
- 不在这次 planning change 中直接确定代码级 schema library 或运行时校验方案。

## Decisions

### 1. 新增独立的共享 contract capability，而不是把 contract 定义散落在各个现有 spec 中

本次 change 引入 `shared-analysis-contracts`，专门负责沉淀 V1 并行开发真正共享的对象。它不取代业务语义 owner，而是统一记录这些对象的字段、字段语义、生产方、消费方、降级语义以及示例 payload。

这样做优于继续把 contract 描述埋在现有 spec 里，因为一旦多人并行修改多个模块，重复的 contract 文字几乎一定会逐渐漂移。

备选方案：
- 把 contract 继续分别写在各 capability spec 里。放弃，因为接口定义会碎片化，联调时不容易对齐。
- 直接让某个实现模块成为唯一 contract 源。放弃，因为当前还在 planning 阶段，应该先把 contract 稳定下来，再进入实现归属。

### 2. 保留现有 7 个 spec，不重拆，只增加一层并行交付分组

项目继续保留当前 7 个 spec，因为它们对应的是比较自然的能力边界。并行开发层面则额外整理为 3 个模块群：

- 控制面：`semantic-routing-and-planning`、`conversation-session-state`、`event-analysis-orchestration`
- 数据与证据面：`structured-market-data-support`、`evidence-retrieval-pipeline`
- 呈现与评测面：`report-trace-and-evaluation`、`analysis-workbench`

这样做优于把 7 个 spec 硬合并成 3 个大 spec，因为当前的问题不是 capability 划分错了，而是缺少并行开发视角下的协同层。

备选方案：
- 直接把 7 个 spec 合并成 3 个 umbrella spec。放弃，因为 requirement 粒度会变粗，边界反而更难讲清。
- 完全按 7 个独立 spec 各自推进，不再额外分组。放弃，因为这会掩盖控制面内部更强的耦合关系。

### 3. 共享 contract 文档负责统一定义，但 owner 仍归现有业务 capability

共享 contract 文档负责沉淀 canonical object，但每个对象仍然需要一个明确的语义 owner，例如：

- `semantic-routing-and-planning` 拥有 `RouterResult` 与 `Plan`
- `conversation-session-state` 拥有 `SessionContext`
- `event-analysis-orchestration` 拥有 `StageObservation`
- `evidence-retrieval-pipeline` 拥有 `EvidenceBundle`
- `report-trace-and-evaluation` 拥有 `FinalResponse`、`TraceBlock` 和 guardrail / error response

这样做优于把所有共享对象都视为 `shared-analysis-contracts` 的业务归属，因为 contract 文档适合做“统一定义”，但不适合吞掉所有对象本身的领域语义主权。

备选方案：
- 让 `shared-analysis-contracts` 成为所有共享对象的唯一 owner。放弃，因为会把语义 ownership 从真正理解业务的 capability 中抽离出去。
- 一个对象允许多个 owner。放弃，因为并行开发时需要唯一决策点，否则 required fields 和 degraded semantics 很难收敛。

### 4. 后端响应 contract 以 response 层为准，UI 只消费不再二次定义

`report-trace-and-evaluation` 负责后端最终的 `FinalResponse`、`TraceBlock` 和 guardrail / error envelope；`analysis-workbench` 作为严格的消费方，只负责渲染和交互，不再自行扩写响应语义。

这样做优于让 workbench 自己“顺手定义”一套响应结构，因为那样会制造第二套 contract 源，最终导致 runtime behavior、evaluation fixture 和 UI 预期逐渐分叉。

备选方案：
- 让 UI 按渲染需求主导 response shape。放弃，因为 response 不只是 UI 在消费，评测和联调同样依赖它。
- 让 orchestration 拥有最终 response。放弃，因为 orchestration 更适合拥有执行流和 observation，而不是面向展示和评测的最终 envelope。

### 5. 项目进度使用一份统一文档，并支持模块群汇总

项目维护一份统一的状态文档，同时兼顾按 spec 细看和按模块群汇总。文档中至少包含 owner、当前状态、依赖、blocker、里程碑和完成定义。

这样做优于让每个小组各自维护一份私有进度，因为当前最需要解决的是跨组可见性，而不是组内私有管理。

备选方案：
- 每个 spec 一份独立进度文档。放弃，因为更新入口太多，跨 spec blocker 很难一眼看出来。
- 完全用 `tasks.md` 充当项目进度面板。放弃，因为 `tasks.md` 更适合作为 change 的计划清单，不适合作为长期交付看板。

## Risks / Trade-offs

- [共享 contract 文档写得过抽象] -> 缓解：只覆盖当前 7 个 spec 已明确出现的共享对象，并配示例 payload。
- [团队对 owner 归属理解不一致] -> 缓解：在 contract 文档里显式写出语义 owner、producer、consumer。
- [项目状态文档容易过时] -> 缓解：把更新动作绑定到 owner 例会和联调检查点，而不是依赖临时补记。
- [正式开发前增加了额外治理成本] -> 缓解：只补最直接影响并行开发的 contract 和交付文档，不扩展到所有内部细节。
- [第一版 shared contracts 覆盖不完整] -> 缓解：先覆盖最关键的对象，后续按真正出现的跨模块复用再迭代扩充。

## Migration Plan

1. 产出共享 contract 文档，定义第一批 canonical objects。
2. 产出并行交付治理文档，整理 7 个 spec 的模块群和依赖关系。
3. 产出统一项目状态文档模板，并填入当前初始状态。
4. 基于 canonical contracts 生成 mock payload 或示例数据，允许下游先开发。
5. 后续实现阶段再由具体 change 决定是否需要回写修改现有 capability spec。

这次 change 主要是 planning change，回滚成本很低。如果需要收缩范围，也可以只保留 shared contracts 和 project status 两份关键产物，但“先定义统一 contract 再并行开发”这个判断应保持不变。

## Open Questions

- 正式进入实现后，项目状态文档最终应该放在 `openspec/`、`docs/` 还是单独的 delivery 目录下？
- contract 一致性在第一阶段是靠人工 review，还是要尽快补轻量 schema fixture？
- 第一批联调检查点更适合按模块群划，还是按共享对象 contract 划？
