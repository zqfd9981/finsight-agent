# FinSight 正式 Spec 修订建议：`frontend/backend` 工程层方案

日期：2026-06-27  
状态：建议稿，未生效

## 1. 目的

这份文档用于把已有的：

- `docs/finsight/frontend-backend-directory-proposal.md`

进一步收敛成一份**可执行的正式 spec 修订建议**。

这里的重点不是重复解释“为什么想做前后端分离”，而是回答下面 3 个问题：

1. 如果项目要正式接受 `frontend/ + backend/ + shared/` 的工程层方案，哪些 spec 必须改
2. 每份 spec 应该改到什么程度
3. 哪些地方现在不该改，避免为目录重写过多业务语义

## 2. 建议结论

建议采用下面这条正式路线：

- V1 仍然保持单仓开发
- V1 的前端工作台仍然使用 `Streamlit`
- 但正式目录组织升级为：
  - `frontend/`
  - `backend/`
  - `shared/`
- 后端内部继续保留现有分层：
  - `control_plane/`
  - `capabilities/`
  - `infra/`
  - `config/`

换句话说：

- 要改的是**工程层组织方式**
- 不该推翻的是**后端内部职责分层方式**

## 3. 建议影响范围

### 3.1 必改

- `openspec/specs/project-implementation-architecture/spec.md`
- `项目框架结构约定.md`

### 3.2 建议改

- `openspec/specs/analysis-workbench/spec.md`
- `docs/superpowers/specs/2026-06-23-finsight-agent-design.md`

### 3.3 可不改或仅补充说明

- `openspec/specs/shared-analysis-contracts/spec.md`
- `docs/finsight/shared-contracts-v1.md`
- `openspec/specs/report-trace-and-evaluation/spec.md`

原因是：

- `project-implementation-architecture` 直接约束顶层目录与依赖方向，所以必须改
- `analysis-workbench` 直接涉及前端工作台归属，所以建议同步改
- shared contracts 与 response 相关 spec 的核心语义并没有变，更多是路径归属与工程边界变化

## 4. 推荐正式结构

如果吸收该方案，推荐正式目录结构改为：

```text
.
├─ frontend/
│  └─ streamlit_app/
├─ backend/
│  ├─ apps/
│  │  └─ api/
│  ├─ src/
│  │  └─ finsight_agent/
│  │     ├─ control_plane/
│  │     ├─ capabilities/
│  │     ├─ infra/
│  │     └─ config/
│  └─ tests/
├─ shared/
│  ├─ contracts/
│  ├─ enums/
│  └─ fixtures/
├─ config/
├─ fixtures/
├─ tests/
├─ scripts/
├─ var/
├─ docs/
└─ openspec/
```

这里有 3 个核心原则：

1. `frontend/` 和 `backend/` 是工程层，不是业务层
2. `backend/` 内部继续保留原来的职责分层
3. `shared/` 提升为前后端共同遵守的稳定边界

## 5. 对 `project-implementation-architecture/spec.md` 的修订建议

这是最关键的一份正式 spec。

### 5.1 建议改写顶层目录要求

当前正式 spec 里，顶层目录明确要求至少包含：

- `apps/`
- `src/`
- `config/`
- `fixtures/`
- `tests/`
- `scripts/`
- `var/`
- `docs/`
- `openspec/`

如果正式采用前后端工程层方案，建议改成：

- `frontend/`
- `backend/`
- `shared/`
- `config/`
- `fixtures/`
- `tests/`
- `scripts/`
- `var/`
- `docs/`
- `openspec/`

### 5.2 建议新增一条“工程层与实现层分离” requirement

建议新增一个 requirement，表达下面这个意思：

- 项目顶层可以按 `frontend/`、`backend/`、`shared/` 组织为工程层
- 后端内部实现仍需按共享层、控制面、能力层和基础设施层进行分层

建议条文草案：

> 项目 MUST 将仓库顶层的工程组织方式与后端内部的实现分层区分开。  
> 在采用前后端工程层方案时，顶层 SHOULD 使用 `frontend/`、`backend/` 与 `shared/` 表达工程边界，而 `backend/src/` 下仍 MUST 按共享层、控制面、能力层与基础设施层组织核心实现。

### 5.3 建议改写“技术入口与业务实现分离”场景

当前表达更偏：

- `apps/` 放入口
- `src/` 放核心逻辑

建议改成更明确的前后端表达：

- `backend/apps/api/` 放 FastAPI 后端入口
- `frontend/streamlit_app/` 放 V1 工作台入口
- `backend/src/` 放核心业务逻辑

建议条文草案：

> **WHEN** 项目创建 FastAPI 后端入口和 V1 工作台入口  
> **THEN** 后端启动代码 MUST 放在 `backend/apps/api/` 或等价后端入口层，V1 工作台入口 MUST 放在 `frontend/streamlit_app/` 或等价前端入口层，核心业务逻辑 MUST 放在 `backend/src/` 下的可复用模块中。

### 5.4 建议新增“前端不得直连后端内部模块”的 requirement

这是这个方案能否以后平滑升级成独立 Web 前端的关键。

建议条文草案：

> 项目 MUST 禁止前端工程直接依赖后端内部实现模块。  
> `frontend/` 只允许通过稳定 API、共享 contract 或等价适配层消费后端能力，而不应直接 import `backend/src/` 下的控制面、能力层或基础设施层实现。

### 5.5 建议改写共享对象归属条文

当前 spec 只要求 shared contracts 与 entities 分开，但没有正式表达它们在前后端工程层方案下的归属位置。

建议补充：

- canonical contracts 与稳定 enums 进入顶层 `shared/`
- 仅后端内部复用的领域对象仍留在 `backend/src/`

建议条文草案：

> **WHEN** 某个对象会被前端与后端共同作为稳定接口或展示协议消费  
> **THEN** 该对象 MUST 放在顶层 `shared/contracts/`、`shared/enums/` 或等价跨工程共享目录中，而不应继续作为后端内部模块私有实现存在。

### 5.6 建议改写依赖方向规则

正式 spec 里目前的依赖方向更偏单仓内部模块关系。

建议改成两层表达：

第一层：工程层

- `frontend -> shared / backend API`
- `backend -> shared`
- `shared -> 不依赖 frontend/backend`

第二层：后端内部实现层

- `control_plane -> shared / infra`
- `capabilities -> shared / infra`

建议条文草案：

> 在采用前后端工程层方案时，项目 MUST 同时维护工程层依赖方向与后端内部实现层依赖方向。  
> `frontend/` MUST 不直接依赖 `backend/src/` 内部实现；`backend/` MAY 依赖顶层 `shared/`；`shared/` MUST 不反向依赖 `frontend/` 或 `backend/`。

## 6. 对 `analysis-workbench/spec.md` 的修订建议

这份 spec 的核心交互语义基本不用推翻，但建议改两处。

### 6.1 建议明确 `frontend/` 归属

当前表述是：

- 提供一个基于 Streamlit 的 V1 分析工作台

建议改成：

- V1 前端工作台以 `Streamlit` 实现
- 工作台属于 `frontend/` 工程
- 后续允许升级为独立 Web 前端，但不改变交互 contract

建议条文草案：

> 系统 MUST 提供一个位于 `frontend/` 工程中的 V1 分析工作台。  
> 在 V1 阶段，该工作台 MAY 以 Streamlit 实现；后续版本 MAY 升级为独立 Web 前端，但必须继续遵守统一 response、trace 与 session continuity 的交互边界。

### 6.2 建议明确工作台消费边界

当前 workbench spec 已经强调：

- workbench 消费统一 response、trace、session 标识

建议再明确一点：

- workbench 不直接消费后端内部 service
- workbench 只消费 API 或稳定 contract

建议条文草案：

> **WHEN** 工作台发起分析请求、展示结果或继续追问  
> **THEN** 工作台 MUST 通过后端统一接口或稳定共享 contract 消费能力结果，而不应直接依赖后端内部控制面、检索或报告实现模块。

## 7. 对 `shared-analysis-contracts/spec.md` 的修订建议

这份 spec 的核心语义其实不需要大改。

更准确地说：

- 它定义的是 canonical object
- 不是目录搬家本身

所以这里建议做的是**轻量补充说明**，而不是重写 requirement。

### 7.1 建议新增一个实现归属说明

建议加一段说明：

- 在前后端工程层方案下
- canonical contracts 的推荐代码落点是 `shared/contracts/`
- 但该 spec 的语义重点仍然是对象本身，而不是工具链实现细节

建议条文草案：

> 在采用前后端工程层组织方式时，shared contract 目录 SHOULD 以顶层 `shared/contracts/`、`shared/enums/` 或等价跨工程共享目录落地，以便前端与后端共同消费同一套 canonical object 定义。

## 8. 对 `项目框架结构约定.md` 的修订建议

这份文件虽然不是正式 spec，但它是当前最强的人话版说明书，所以必须同步更新。

建议改动范围：

- 第 2 节技术基线下的工程组织认知
- 第 4 节顶层目录结构
- 第 5 节内部结构描述
- 第 15 节依赖方向
- 第 16 节 spec 到目录映射
- 第 17 节第一批必须先搭哪些文件

### 8.1 建议统一改写顶层目录说明

应把“推荐第一版顶层目录如下”改成：

- `frontend/`
- `backend/`
- `shared/`
- 其余顶层目录保持不变

### 8.2 建议把原来的 `apps/workbench/` 映射改成 `frontend/streamlit_app/`

这是与用户心智最直接相关的一步。

### 8.3 建议把原来的 `src/finsight_agent/shared/*` 改成双层解释

需要明确区分：

- 顶层 `shared/`：跨工程共享边界
- 后端内部 `backend/src/finsight_agent/...`：后端实现层

## 9. 建议暂不修改的内容

为了避免因为目录调整引发过度 spec 重写，下面这些内容现在建议先不改：

### 9.1 不改业务链路定义

比如：

- `metric_lookup`
- `event_impact_analysis`
- `retrieve_evidence`
- `synthesize_report`

这些属于能力链路，不属于工程层目录调整。

### 9.2 不改 response 与 trace 的核心语义

比如：

- `FinalResponse`
- `TraceBlock`
- `GuardrailOrErrorResponse`

这些对象会继续存在，只是工程归属更偏顶层 `shared/`。

### 9.3 不改 V1 的前端技术基线

建议不要在这一次 spec 修订里直接把：

- `Streamlit`

改成：

- `React`
- `Vue`
- `Next.js`

因为这会把“目录工程层调整”和“前端技术栈升级”两个问题绑死在一起。

## 10. 推荐的正式修订顺序

如果后面要把这套方案真正纳入正式 spec，建议按下面顺序推进：

1. 先修订 `project-implementation-architecture/spec.md`
2. 再修订 `analysis-workbench/spec.md`
3. 再同步更新 `项目框架结构约定.md`
4. 最后再决定是否创建工程迁移变更并调整现有代码骨架

这样做的原因是：

- 先定顶层工程边界
- 再定前端工作台归属
- 最后再动代码

## 11. 一句话判断标准

如果未来正式采纳这套方案，判断 spec 是否改对了，可以只看一句话：

**顶层按 `frontend/ + backend/ + shared/` 组织工程，后端内部仍按 `shared / control_plane / capabilities / infra` 组织实现，前端只通过稳定接口消费后端结果。**

只要这句话在各份正式 spec 里能自洽落地，这次修订方向就是对的。
