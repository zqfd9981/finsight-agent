## Context

当前仓库已经按 `apps/ + src/` 建立了第一版单仓 Python 骨架，并把后端内部职责收敛为 `shared / control_plane / capabilities / infra / config` 等层次。这套结构符合当前正式 spec，但它和团队更直观的“前端工程 / 后端工程”认知存在偏差，也让 `Streamlit` 工作台看起来更像后端内部入口，而不是一个独立的前端工程。

当前约束和背景如下：

- V1 技术基线已明确为 `FastAPI + Streamlit + Python`
- 现有 spec 已经稳定表达了后端内部职责分层
- 团队希望目录上能一眼看到 `frontend/` 和 `backend/`
- 后续存在把工作台从 `Streamlit` 升级为独立 Web 前端的可能

因此，这次变化要解决的是**工程层组织方式**，而不是重写后端能力架构本身。

## Goals / Non-Goals

**Goals:**

- 在正式 spec 中引入 `frontend/ + backend/ + shared/` 的工程层组织方式
- 保留后端内部 `control_plane / capabilities / infra / config` 的现有分层
- 明确 V1 工作台仍然使用 `Streamlit`，但其工程归属是 `frontend/`
- 明确前端只能通过稳定接口或共享 contract 消费后端能力
- 为未来升级到独立 Web 前端保留迁移路径

**Non-Goals:**

- 不在这次变更中把 V1 前端技术栈改成 React、Vue 或 Next.js
- 不改变 `metric_lookup`、`event_impact_analysis` 等业务链路定义
- 不重写 shared contracts 的核心字段语义
- 不在这次变更中直接迁移现有代码骨架

## Decisions

### Decision 1：把 `frontend/`、`backend/`、`shared/` 定义为工程层

采用两层结构：

- 顶层工程层：`frontend/`、`backend/`、`shared/`
- 后端实现层：`backend/src/finsight_agent/...`

原因：

- 团队更容易理解“前端在哪、后端在哪”
- 可以把“工程分离”和“后端内部模块分层”拆开处理
- 不需要推翻现有 capability 到后端模块的映射方式

备选方案：

- 保持 `apps/ + src/` 不变
  - 优点：最贴近现有 spec 和当前骨架
  - 缺点：工程心智仍然不像前后端分离
- 直接改成独立 `frontend/web + backend/api`
  - 优点：边界最彻底
  - 缺点：对 V1 成本过高，也把工程层调整和前端技术栈升级绑死在一起

### Decision 2：V1 继续使用 `Streamlit`，但归属切换到 `frontend/`

V1 的工作台实现不变，仍使用 `Streamlit`，但正式归属从 `apps/workbench` 调整为 `frontend/streamlit_app/`。

原因：

- 这样能在不增加过多实现成本的情况下建立“前端工程”认知
- 当前工作台 spec 的交互边界保持稳定
- 后续升级成独立 Web 前端时，迁移点集中在 `frontend/`，而不是继续清理 `apps/` 与 `src/` 的耦合

备选方案：

- 继续保留 `apps/workbench`
  - 优点：最小改动
  - 缺点：继续弱化前端工程概念
- 现在直接改成 Web 前端
  - 优点：长期结构最纯粹
  - 缺点：超出当前 V1 范围

### Decision 3：把 stable contracts 与 enums 抬升到顶层 `shared/`

在前后端工程层方案下，真正跨前后端共享的 canonical contracts、稳定 enums 和联调 fixtures 推荐进入顶层 `shared/`。

原因：

- 这些对象的语义不应再被视为“后端内部模块”
- 这能为前后端共同消费同一套接口定义提供清晰归属
- 有助于后续独立 Web 前端复用稳定边界

备选方案：

- 继续把 shared contracts 放在 `backend/src/.../shared/`
  - 优点：迁移量更小
  - 缺点：语义上仍偏后端私有实现，前后端分离只是表面结构变化

### Decision 4：正式限制前端不得直连后端内部实现

前端工作台只能通过：

- 后端统一接口
- 稳定 response
- 顶层 `shared/` contract

消费后端结果，而不能直接 import `backend/src/` 下的控制面、能力层或基础设施层实现。

原因：

- 这是未来从 `Streamlit` 升级为独立 Web 前端的关键约束
- 没有这个约束，目录即使改成 `frontend/backend` 也只是名义分离

备选方案：

- 允许前端临时直连后端 service
  - 优点：短期实现简单
  - 缺点：后期前端独立化时迁移成本会快速放大

## Risks / Trade-offs

- [工程层与实现层同时存在，文档表述可能变复杂] → 在正式 spec 中显式区分“工程层”和“后端实现层”，避免把两者混写
- [shared 对象抬升后，现有代码和文档路径都会变化] → 先改 spec，再做分阶段代码迁移，不在一次变更里同时重写所有引用
- [V1 仍然使用 Streamlit，可能让人误以为不是真正前后端分离] → 在 spec 中明确 V1 是工程层分离、不是技术栈彻底分离，并写清 V2 升级路径
- [测试目录可能出现顶层 tests 与 backend/tests 双轨] → 在正式 spec 中单独约束工程层测试归属，避免后续自由扩散
- [如果前端仍偷偷直连后端实现，后续升级价值会被削弱] → 把“前端不得直连后端内部模块”升级为正式 requirement，并在迁移时加检查

## Migration Plan

1. 先修改 `project-implementation-architecture/spec.md`，正式引入 `frontend/ + backend/ + shared/` 的工程层表达
2. 再修改 `analysis-workbench/spec.md`，明确 V1 工作台属于 `frontend/` 且只能通过稳定接口消费后端结果
3. 同步更新 `项目框架结构约定.md`，统一人话版和正式 spec 的工程认知
4. 等文档确认后，再创建实现变更，把当前：
   - `apps/api/`
   - `apps/workbench/`
   - `src/finsight_agent/`
   分阶段迁移到：
   - `backend/apps/api/`
   - `frontend/streamlit_app/`
   - `backend/src/finsight_agent/`
5. 在实现变更中再决定是否把 stable contracts 从后端内部 `shared/` 迁移到顶层 `shared/`

回退策略：

- 如果正式 spec 评审未通过，可以保留当前 `apps/ + src/` 结构，不进行代码迁移
- 如果工程迁移开始后发现成本过高，可先只保留 spec 中的消费边界约束，延后目录级重组

## Open Questions

- 顶层 `tests/` 与 `backend/tests/` 的最终分工是否要在这次 spec 修订中一起定死
- 顶层 `shared/` 是否在首轮实现迁移中就包含全部 stable contracts，还是只先迁移前后端共同消费的那一部分
- `frontend/streamlit_app/` 在 V1 阶段是否需要一个轻量前端适配层，避免它直接感知后端 response 之外的实现细节
