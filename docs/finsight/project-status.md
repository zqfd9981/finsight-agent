# FinSight V1 项目状态文档

日期：2026-06-29
状态：骨架已落地，准备进入首条业务快路径实现

## 1. 使用说明

这份文档同时承担两种用途：

- 作为统一项目状态模板
- 作为当前第一版真实状态快照

推荐状态值：

- `未开始`
- `进行中`
- `阻塞`
- `可联调`
- `完成`

## 2. 模块群状态总览

| 模块群 | 覆盖 spec | 当前 owner | 当前状态 | 主要依赖 | 当前 blocker | 当前里程碑 | 完成定义 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 控制面 | routing/planning、session、orchestration | 待分配 | 进行中 | shared contracts、API boundary | orchestrator 与 session 真实链路尚未实现 | Control Plane Semantic Routing Ready | `RouterResult`、`Plan` 已可按规则产出，且可被统一 API 边界消费 |
| 数据与证据面 | structured market data、retrieval | 待分配 | 进行中 | shared contracts、控制面输入 mock | 真实结构化数据源与 retrieval 链路尚未接入 | Evidence Ready | metric_lookup 占位查询可返回稳定结构，后续再接真实数据与证据 |
| 呈现与评测面 | response/evaluation、workbench | 待分配 | 进行中 | shared contracts、API boundary、response fixtures | workbench 页面展示仍是入口骨架，未进入真实交互实现 | Response Ready | `FinalResponse`、`TraceBlock`、API envelope 已冻结且可通过骨架测试验证 |

## 3. 各 Spec 当前状态

| Spec | 所属模块群 | Owner | 当前状态 | 上游依赖 | Blocker | 下一里程碑 | DoD |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `project-implementation-architecture` | 全局底座 | 待分配 | 完成 | 无 | 无 | Architecture Ready | `frontend + backend + shared` 骨架已落地并通过测试 |
| `shared-analysis-contracts` | 全局底座 | 待分配 | 完成 | 无 | 无 | Contract Ready | 顶层 `shared/contracts`、fixtures 与中文字段注释已落地 |
| `workbench-backend-api-boundary` | 全局底座 | 待分配 | 完成 | shared contracts | 无 | API Boundary Ready | 统一请求/响应 contract、后端入口壳、前端 client 骨架已落地 |
| `semantic-routing-and-planning` | 控制面 | 待分配 | 进行中 | `SessionContext`、shared contracts、API boundary | 真实 session context 仍未接入，当前 follow-up 仍基于轻量规则 | Control Plane Semantic Routing Ready | 能输出稳定 `RouterResult` 和 `Plan` 规则结果，并作为首条快路径入口 |
| `conversation-session-state` | 控制面 | 待分配 | 未开始 | shared contracts | 会话持久化与压缩逻辑尚未实现 | Control Plane Mock Ready | 能输出压缩后的 `SessionContext` mock |
| `event-analysis-orchestration` | 控制面 | 待分配 | 未开始 | `Plan`、structured output、retrieval output | 输入输出 contract 已冻结，但真实 orchestrator 未开工 | Control Plane Mock Ready | 能消费 mock `Plan` 并产出 mock `StageObservation` |
| `structured-market-data-support` | 数据与证据面 | 待分配 | 进行中 | router/planner 输出 | 当前仅有 metric_lookup 占位查询，未接真实数据源 | Evidence Ready | 能返回首条 metric_lookup 快路径所需的稳定结构化结果 |
| `evidence-retrieval-pipeline` | 数据与证据面 | 待分配 | 未开始 | claim / target mock | 首条 metric_lookup 快路径暂不依赖 retrieval | Evidence Ready | 能产出最小 `EvidenceBundle` |
| `report-trace-and-evaluation` | 呈现与评测面 | 待分配 | 进行中 | routing/planning mock、structured data 占位结果 | trace 仍是占位生成，未形成真实报告链路 | Response Ready | 能输出 success / degraded / guardrail 三类响应骨架并封装到 API envelope |
| `analysis-workbench` | 呈现与评测面 | 待分配 | 进行中 | `FinalResponse`、API boundary | 页面交互与真实调用链路尚未实现 | Workbench Ready | 能通过 `WorkbenchApiClient` 消费统一 API boundary，并进入结果展示阶段 |

## 4. 当前全局 Blocker

### Blocker 1：模块 owner 尚未正式指派

影响范围：

- 所有模块群

解除条件：

- 项目负责人完成第一轮 owner 分配

### Blocker 2：首条真实业务快路径尚未起新的实现 change

影响范围：

- 控制面
- 数据与证据面
- 呈现与评测面

解除条件：

- 新建并进入 `metric_lookup` 最小快路径实现 change

### Blocker 3：真实 session / orchestrator / retrieval 仍未接入

影响范围：

- 控制面
- 数据与证据面
- 呈现与评测面

解除条件：

- 首条快路径之外的复杂链路进入后续实现轮次

## 5. 第一批里程碑

| 里程碑 | 目标 | 判定条件 |
| --- | --- | --- |
| M1 Contract Ready | 共享对象定义稳定 | 已完成：shared contracts、fixtures、字段注释和 API boundary contract 已落地 |
| M2 Control Plane Mock Ready | 控制面可先行联调 | 已完成：`RouterResult`、`Plan` mock 与 API boundary 骨架可用 |
| M2.5 Control Plane Semantic Routing Ready | 控制面进入首版规则联调 | 已完成：router/planner 已覆盖长短路径与 follow-up 规则，并接入统一 API trace |
| M3 Evidence Ready | 数据与证据面产出可被消费 | 进行中：metric_lookup 占位查询可返回稳定结构，但 retrieval 未启动 |
| M4 Response Ready | 响应层 contract 稳定 | 已完成：`FinalResponse`、`TraceBlock`、guardrail response 与 envelope 骨架可用 |
| M5 Demo Ready | 首轮分析和一轮追问跑通 | 进行中：控制面已完成规则实现，待结构化数据与结果呈现继续接入 |

## 6. 更新规则

- 每周至少更新一次模块群状态
- 每次联调前后必须更新 blocker
- Owner 变更时必须同步更新本文件
- 如果某个 spec 已进入实现，状态不得继续保留为 `未开始`

## 7. 和模块进度文件怎么配合

这份文档负责记录全局视角，不负责展开每个模块这轮的细节。

对应的模块细节应该放在：

- `docs/finsight/modules/control-plane-status.md`
- `docs/finsight/modules/data-evidence-status.md`
- `docs/finsight/modules/presentation-eval-status.md`

更新分工建议如下：

- 主控窗口更新本文件，负责里程碑、全局 blocker、模块群总体状态
- 对应模块的负责人或主控窗口更新模块进度文件，负责本轮目标、活跃任务、卡点和下一次阶段检查
- 工作窗口不直接改本文件，只通过任务卡、同步卡、交接卡汇报局部进展

## 8. 当前落地说明

- 已完成的底座：
  - 工程结构已切换到 `frontend/ + backend/ + shared/`
  - `shared-analysis-contracts` 已落地到顶层 `shared/contracts`
  - `workbench-backend-api-boundary` 已落地为统一 request/response 骨架
- 已落地的骨架：
  - 后端统一分析入口：`backend/apps/api/analysis_turns.py`
  - 后端适配层：`backend/src/finsight_agent/workbench_backend_api/service.py`
  - 前端 API client：`frontend/streamlit_app/api_client.py`
  - API boundary fixtures 与测试已通过
- 已完成的新增进展：
  - `semantic-routing-and-planning` 已实现 `metric_lookup`、`event_impact_analysis`、`evidence_lookup`、`out_of_scope`
  - follow-up 已实现 `none`、`drilldown`、`compare`、`redirect` 的首版判别
  - planner 已实现 metric 快路径、event 四阶段长路径、evidence 缩减路径以及 guardrail 计划
- 尚未开始的真实业务实现：
  - session 持久化
  - orchestrator 主链路
  - retrieval / evidence 真实链路
  - workbench 页面级交互

这样可以避免：

- 多个窗口同时改同一份全局状态
- 模块细节把全局看板写得过重
- 全局状态和模块状态互相打架
