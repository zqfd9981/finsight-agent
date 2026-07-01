# FinSight V1 项目状态文档

日期：2026-07-01  
状态：控制面已打通 orchestrator 首版真实执行链，项目进入“session context 接线与后续能力扩展”阶段

## 1. 总览

当前项目已经完成三块基础能力的首版闭环：

- 共享 contracts 与统一 API boundary 已稳定落地
- semantic routing / planning 已能稳定输出 `RouterResult` 与 `Plan`
- retrieval facade 已能稳定返回结构化 `RetrievalResult`

在此基础上，`event-analysis-orchestration` 首版已经完成最小可运行接线：

- `metric_lookup` 短路径已可真实执行
- `evidence_lookup` 路径已可真实执行
- `WorkbenchBackendApiService` 已不再返回 stub，而是走 `route -> plan -> orchestrate -> envelope`
- execution trace 与 `StageObservation` 已接入统一响应链路

## 2. 模块群状态

| 模块群 | 当前状态 | 当前里程碑 | 说明 |
| --- | --- | --- | --- |
| 控制面 | 进行中 | M5 Orchestrator Ready | orchestrator 首版真实执行链已完成，session context 真实接线仍待推进 |
| 数据与证据面 | 可联调 | M3 Retrieval Pipeline Ready | retrieval 主链稳定可用，并已被 orchestrator 消费 |
| 呈现与评测面 | 进行中 | M4 Response Ready | API envelope、trace、response contract 已可用，workbench 展示层仍待继续接线 |

## 3. 关键 Spec 状态

| Spec | 当前状态 | 说明 |
| --- | --- | --- |
| `project-implementation-architecture` | 完成 | 工程结构与分层边界稳定 |
| `shared-analysis-contracts` | 完成 | `shared/contracts` 与 fixtures 已稳定 |
| `workbench-backend-api-boundary` | 完成 | 统一 request / response 边界已稳定 |
| `semantic-routing-and-planning` | 完成首版 | router / planner 已可稳定支撑真实链路 |
| `conversation-session-state` | 完成首版 | `SessionContext` 已真实接入统一入口，并支持 rolling summary 短期记忆 |
| `event-analysis-orchestration` | 完成首版最小路径 | `metric_lookup` / `evidence_lookup` 已真实接线 |
| `structured-market-data-support` | 进行中 | 已完成本地指标库、本地优先查询与外部 fallback 首版能力 |
| `evidence-retrieval-pipeline` | 完成首版 | retrieval 主链与结构化输出已可稳定消费 |
| `report-trace-and-evaluation` | 进行中 | response / trace 已接线，评测体系仍待补强 |
| `analysis-workbench` | 进行中 | 前端展示与真实 follow-up 体验仍待继续完善 |

## 4. 当前里程碑

| 里程碑 | 状态 | 说明 |
| --- | --- | --- |
| M1 Contract Ready | 完成 | shared contracts 与 API boundary 已稳定 |
| M2 Control Plane Semantic Routing Ready | 完成 | routing / planning 已可稳定输出 |
| M3 Retrieval Pipeline Ready | 完成 | retrieval 本地闭环已打通 |
| M4 Response Ready | 完成 | response / trace / envelope 已稳定 |
| M5 Orchestrator Ready | 完成 | orchestrator 首版最小运行链已真实接入 |

## 5. 本轮新增成果

- 新增 orchestrator 设计文档与 implementation plan
- 实现 `OrchestratorService` 首版真实执行流
- 实现 `query_structured_data`、`synthesize_brief_answer`、`retrieve_evidence`、`synthesize_report` 四个首版 stage runner
- 接入 `StageObservation` 与 execution trace 产出
- 打通统一后端入口到 orchestrator 的真实链路
- 增加 unsupported stage 的显式失败保护
- 修复 retrieval 本地 Qdrant 路径的资源生命周期问题，清理 evidence 集成测试中的 `ResourceWarning`

## 6. 当前阻塞项

### Blocker 1：`structured-market-data-support` 仍处于首版有限覆盖阶段

影响范围：

- `metric_lookup` 的真实覆盖范围仍受本地指标库与 fallback provider 数量限制
- 季报、更多公司和更多指标暂未进入首版能力范围

解除条件：

- 完成更多指标、期间类型与 provider 的扩展，并形成更稳定的构建入口

### Blocker 2：评测样本与验收口径仍待体系化

影响范围：

- retrieval / structured data / orchestrator / response 的持续回归能力

解除条件：

- 补充首批 query/evidence 评测样本，并形成持续验证入口

## 7. 下一阶段建议

1. 扩大 `structured-market-data-support` 的本地指标覆盖范围
2. 选定并接入首个真实外部指标 provider，替代当前 no-op fallback
3. 为 structured data / orchestrator / retrieval 建立更明确的评测样本与回归集
4. 继续推进 `event_impact_analysis` 的前两阶段真实 runner
