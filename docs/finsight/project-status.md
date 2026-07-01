# FinSight V1 项目状态文档

日期：2026-07-01
状态：数据与证据链路已形成首版可检索闭环，准备进入 orchestrator 接线阶段

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
| 控制面 | routing/planning、session、orchestration | 待分配 | 进行中 | shared contracts、API boundary | orchestrator 与 session 真实链路尚未实现 | Control Plane Semantic Routing Ready | `RouterResult`、`Plan` 已可稳定产出，并可被统一 API 边界消费 |
| 数据与证据面 | structured market data、retrieval | 待分配 | 可联调 | shared contracts、控制面输入、PDF 语料 | 结构化指标链路与 orchestrator 尚未接入 | Retrieval Pipeline Ready | 本地 PDF 采集、解析、切块、sparse/dense/hybrid retrieval 已可产出结构化 `RetrievalResult` |
| 呈现与评测面 | response/evaluation、workbench | 待分配 | 进行中 | shared contracts、API boundary、retrieval result | workbench 页面展示仍是骨架，未接 orchestrator 真链路 | Response Ready | `FinalResponse`、`TraceBlock`、API envelope 已冻结且可通过骨架测试验证 |

## 3. 各 Spec 当前状态

| Spec | 所属模块群 | Owner | 当前状态 | 上游依赖 | Blocker | 下一里程碑 | DoD |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `project-implementation-architecture` | 全局底座 | 待分配 | 完成 | 无 | 无 | Architecture Ready | `frontend + backend + shared` 骨架已落地并通过测试 |
| `shared-analysis-contracts` | 全局底座 | 待分配 | 完成 | 无 | 无 | Contract Ready | 顶层 `shared/contracts`、fixtures 与中文字段注释已落地 |
| `workbench-backend-api-boundary` | 全局底座 | 待分配 | 完成 | shared contracts | 无 | API Boundary Ready | 统一请求/响应 contract、后端入口壳、前端 client 骨架已落地 |
| `semantic-routing-and-planning` | 控制面 | 待分配 | 进行中 | `SessionContext`、shared contracts、API boundary | 真实 session context 仍未接入，follow-up 仍基于轻量规则 | Control Plane Semantic Routing Ready | 能输出稳定 `RouterResult` 和 `Plan`，并作为首条快路径入口 |
| `conversation-session-state` | 控制面 | 待分配 | 未开始 | shared contracts | 会话持久化与压缩逻辑尚未实现 | Control Plane Mock Ready | 能输出压缩后的 `SessionContext` mock |
| `event-analysis-orchestration` | 控制面 | 待分配 | 未开始 | `Plan`、retrieval output、response assembly | 控制面与 retrieval 现已具备输入输出基础，但 orchestrator 本体未开工 | Orchestrator Ready | 能消费 `Plan` 并产出真实 `StageObservation` |
| `structured-market-data-support` | 数据与证据面 | 待分配 | 进行中 | router/planner 输出 | 当前未接真实结构化指标数据源 | Evidence Ready | 能返回首条 `metric_lookup` 快路径所需的稳定结构化结果 |
| `evidence-retrieval-pipeline` | 数据与证据面 | 待分配 | 进行中 | 本地 PDF 语料、shared contracts | orchestrator、评测集、在线模型增强尚未接入 | Retrieval Pipeline Ready | 本地 PDF 采集、解析、切块、sparse/dense/hybrid retrieval 与输出组装均已打通 |
| `report-trace-and-evaluation` | 呈现与评测面 | 待分配 | 进行中 | routing/planning、retrieval result | 页面级 trace 展示和评测口径尚未接 retrieval 真实输出 | Response Ready | 能输出 success / degraded / guardrail 三类响应骨架并封装到 API envelope |
| `analysis-workbench` | 呈现与评测面 | 待分配 | 进行中 | `FinalResponse`、API boundary | 页面交互与真实调用链路尚未实现 | Workbench Ready | 能通过 `WorkbenchApiClient` 消费统一 API boundary，并进入结果展示阶段 |

## 4. 当前全局 Blocker

### Blocker 1：模块 owner 尚未正式指派

影响范围：

- 所有模块群

解除条件：

- 项目负责人完成第一轮 owner 分配

### Blocker 2：真实 orchestrator 尚未接 retrieval / response 主链路

影响范围：

- 控制面
- 数据与证据面
- 呈现与评测面

解除条件：

- `event-analysis-orchestration` 开始消费 `RouterResult`、`Plan` 与统一 `RetrievalResult`

### Blocker 3：结构化指标数据源与评测集尚未接入

影响范围：

- 数据与证据面
- 呈现与评测面

解除条件：

- `structured-market-data-support` 接入真实数据
- retrieval 增补首批 query/evidence 评测集

## 5. 当前里程碑

| 里程碑 | 目标 | 判定条件 |
| --- | --- | --- |
| M1 Contract Ready | 共享对象定义稳定 | 已完成：shared contracts、fixtures、字段注释和 API boundary contract 已落地 |
| M2 Control Plane Semantic Routing Ready | 控制面具备稳定规则输出 | 已完成：router/planner 已覆盖长短路径与 follow-up 规则 |
| M3 Retrieval Pipeline Ready | 证据链路具备真实本地闭环 | 已完成：PDF acquisition、parsing、chunking、sparse、dense、fusion、rerank、retrieval output assembly 已打通 |
| M4 Response Ready | 响应层 contract 稳定 | 已完成：`FinalResponse`、`TraceBlock`、guardrail response 与 envelope 骨架可用 |
| M5 Orchestrator Ready | 检索能力接入主执行链 | 进行中：下一步应由 orchestrator 消费 retrieval facade 与统一 `RetrievalResult` |

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

## 8. 当前落地说明

- 已完成的底座：
  - 工程结构已切换到 `frontend/ + backend/ + shared/`
  - `shared-analysis-contracts` 已落地到顶层 `shared/contracts`
  - `workbench-backend-api-boundary` 已落地为统一 request/response 骨架
- 已完成的控制面能力：
  - `semantic-routing-and-planning` 已实现 `metric_lookup`、`event_impact_analysis`、`evidence_lookup`、`out_of_scope`
  - follow-up 已实现 `none`、`drilldown`、`compare`、`redirect`
- 已完成的数据与证据链路：
  - 本地 PDF 采集链路已打通
  - parsing + chunking 已产出 `parents.jsonl` / `children.jsonl`
  - SQLite FTS5 sparse retrieval 已可用
  - 本地 Qdrant + 本地 embedding dense retrieval 已可用
  - RRF fusion、child rerank、retrieval facade、retrieval trace、parent expand 已落地
- 尚未开始或尚未接线的部分：
  - session 持久化
  - orchestrator 主链路
  - structure market data 真实数据源
  - workbench 页面级交互与 trace 展示
