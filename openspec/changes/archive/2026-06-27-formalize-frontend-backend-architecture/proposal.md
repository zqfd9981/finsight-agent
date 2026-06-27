## Why

当前工程骨架已经按单仓 Python 分层搭出了 `apps/ + src/` 结构，但它和团队更直观的“前端工程 / 后端工程”认知并不一致，也不利于后续把工作台从 `Streamlit` 平滑升级为独立 Web 前端。现在需要在不推翻现有后端内部职责分层的前提下，正式引入 `frontend/ + backend/ + shared/` 的工程层方案，并把相关约束收敛进正式 spec。

## What Changes

- 将顶层工程组织方式从 `apps/ + src/` 为主，调整为 `frontend/ + backend/ + shared/` 为主，同时保留 `config/`、`fixtures/`、`tests/`、`scripts/`、`var/`、`docs/`、`openspec/` 等顶层支撑目录。
- 明确“工程层”和“后端实现层”是两层不同的边界：`backend/` 内部继续保留 `control_plane/`、`capabilities/`、`infra/`、`config/` 等现有职责分层。
- 明确 V1 前端工作台仍以 `Streamlit` 实现，但其归属从 `apps/workbench` 调整为 `frontend/` 工程，并为后续升级到独立 Web 前端保留接口边界。
- 明确顶层 `shared/` 的归属语义，用于承接前后端共同消费的稳定 contracts、enums 和联调用 fixtures。
- **BREAKING**：正式 spec 中关于顶层目录、workbench 归属、shared contracts 代码落点和依赖方向的表述将发生变化，后续代码迁移需要同步调整 import 路径和目录映射。

## Capabilities

### New Capabilities
- 无

### Modified Capabilities
- `project-implementation-architecture`: 顶层工程结构、入口归属、shared 归属和依赖方向将从单仓内部目录表达升级为 `frontend/ + backend/ + shared/` 工程层表达。
- `analysis-workbench`: V1 工作台仍以 Streamlit 实现，但其工程归属、消费边界和后续升级路径需要正式写入 spec。

## Impact

- 受影响文档：
  - `openspec/specs/project-implementation-architecture/spec.md`
  - `openspec/specs/analysis-workbench/spec.md`
  - `项目框架结构约定.md`
- 受影响代码骨架：
  - `apps/api/`
  - `apps/workbench/`
  - `src/finsight_agent/shared/`
  - `src/finsight_agent/workbench/`
- 受影响系统边界：
  - 前端工作台与后端内部模块之间的依赖方式
  - shared contracts 的工程归属
  - 后续前端从 `Streamlit` 升级为独立 Web 工程时的迁移成本
