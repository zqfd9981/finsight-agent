# FinSight V1 项目状态

日期：2026-07-02  
状态：控制面已接通 `event_impact_analysis` 首版四阶段真实执行链，项目进入“能力增强与覆盖扩展”阶段。

## 1. 总览

当前项目已经完成以下首版闭环：

- 共享 contracts、统一 API boundary、trace/envelope 已稳定落地
- `semantic-routing-and-planning` 已稳定输出 `RouterResult` 与 `Plan`
- retrieval facade 已稳定返回结构化 `RetrievalResult`
- `structured-market-data-support` 已完成本地指标库与外部 fallback 首版闭环
- orchestrator 已接通三条主路径：
  - `metric_lookup`
  - `evidence_lookup`
  - `event_impact_analysis`

## 2. 模块群状态

| 模块群 | 当前状态 | 当前里程碑 | 说明 |
| --- | --- | --- | --- |
| 控制面 | 进行中 | M6 Event Chain Ready | `event_impact_analysis` 四阶段首版真实接线已完成，后续重点转向能力增强与评测 |
| 数据与证据面 | 可联调 | M5 Data + Evidence Ready | retrieval 与 structured data 已可被统一控制面消费 |
| 呈现与评测面 | 进行中 | M4 Response Ready | response/trace 已稳定，评测集与工作台体验仍待增强 |

## 3. 关键 Spec 状态

| Spec | 当前状态 | 说明 |
| --- | --- | --- |
| `project-implementation-architecture` | 完成 | 工程结构与分层边界稳定 |
| `shared-analysis-contracts` | 完成 | `shared/contracts` 已稳定 |
| `workbench-backend-api-boundary` | 完成 | 统一 request / response boundary 已稳定 |
| `semantic-routing-and-planning` | 完成首版 | router / planner 已可稳定支撑真实执行链 |
| `conversation-session-state` | 完成首版 | `SessionContext` 与 rolling summary 已接入统一入口 |
| `event-analysis-orchestration` | 完成首版 | `metric_lookup` / `evidence_lookup` / `event_impact_analysis` 已接通真实执行链 |
| `structured-market-data-support` | 完成首版 | 本地财报表格指标库、本地优先查询与外部 fallback 已落地 |
| `evidence-retrieval-pipeline` | 完成首版 | retrieval 主链与结构化输出已稳定可消费 |
| `report-trace-and-evaluation` | 进行中 | response / trace 已接线，评测体系待补强 |
| `analysis-workbench` | 进行中 | API 主链已就绪，前端体验仍待增强 |

## 4. 当前里程碑

| 里程碑 | 状态 | 说明 |
| --- | --- | --- |
| M1 Contract Ready | 完成 | shared contracts 与 API boundary 已稳定 |
| M2 Semantic Routing Ready | 完成 | routing / planning 已可稳定输出 |
| M3 Retrieval Pipeline Ready | 完成 | retrieval 本地闭环已打通 |
| M4 Response Ready | 完成 | response / trace / envelope 已稳定 |
| M5 Structured Data Ready | 完成 | `metric_lookup` 已不再依赖 TODO 占位 |
| M6 Event Chain Ready | 完成 | `event_impact_analysis` 四阶段首版执行链已接通 |

## 5. 本轮新增成果

- 新增 `collect_event_context` 与 `analyze_targets` 两个真实 stage runner
- 新增外部上下文检索抽象与受约束 LLM 目标分析服务
- orchestrator 已可调度 `event_impact_analysis` 四阶段完整链路
- `synthesize_report` 已消费事件目标分析结果，并在摘要/不确定性/下一步建议中体现
- 新增 `event_impact_analysis` 端到端集成测试

## 6. 当前阻塞项

### Blocker 1：外部工具检索仍为抽象层

影响范围：

- `collect_event_context` 与候选发现检索目前已具备接入点，但默认仍依赖 stub / 空实现
- 近期事件的时效性覆盖能力仍受外部 provider 接入情况限制

解除条件：

- 选定并接入首个真实外部搜索 / 新闻 / 公告 provider

### Blocker 2：事件分析评测集仍待建立

影响范围：

- `event_impact_analysis` 的候选发现、目标排序与降级语义仍缺系统化回归样本

解除条件：

- 补齐首批事件分析 query 集、候选标的集与人工验收口径

## 7. 下一阶段建议

1. 为 `collect_event_context` 与候选发现检索接入真实外部工具 provider
2. 建立 `event_impact_analysis` 的首批评测样本与回归集
3. 继续扩展 `structured-market-data-support` 的指标、期间与公司覆盖范围
4. 评估是否为 `analyze_targets` 增加更细的结构化事实输入与 LLM 输出校验
