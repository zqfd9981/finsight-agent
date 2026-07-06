# FinSight V1 项目状态

日期：2026-07-05  
状态：控制面、结构化数据、证据检索与事件主链均已形成首版可运行闭环，项目进入“能力增强、评测补强与稳定性优化”阶段。

## 总览

当前已经完成这些关键闭环：

- shared contracts、统一 API boundary、trace/envelope 已稳定落地
- `semantic-routing-and-planning` 已稳定输出 `RouterResult` 与 `Plan`
- retrieval facade 已稳定返回结构化 `RetrievalResult`
- `structured-market-data-support` 已完成“本地指标库 + 外部 fallback”首版闭环
- orchestrator 已接通三条真实执行链：
  - `metric_lookup`
  - `evidence_lookup`
  - `event_impact_analysis`
- `event_impact_analysis` 已接入首版真实双层外部检索：
  - `Bocha` 事件搜索
  - `CNInfo + SSE` 官方披露搜索
- `event_impact_analysis` 已新增首版评测样本与 replay 回放框架
- Streamlit 内部工作台已具备首版三视图骨架：
  - `分析视图`
  - `调试视图`
  - `评测视图`

## 里程碑

| 里程碑 | 状态 | 说明 |
| --- | --- | --- |
| M1 Contract Ready | 完成 | contracts 与 API boundary 已稳定 |
| M2 Semantic Routing Ready | 完成 | routing / planning 已能稳定驱动真实链路 |
| M3 Retrieval Pipeline Ready | 完成 | 本地 retrieval 闭环已稳定 |
| M4 Response Ready | 完成 | response / trace / envelope 已稳定 |
| M5 Structured Data Ready | 完成 | `metric_lookup` 已不再依赖占位结果 |
| M6 Event Chain Ready | 完成 | `event_impact_analysis` 四阶段主链已接通 |
| M7 External Context Ready | 完成首版 | 双层外部检索已接入事件链 |
| M8 Event Eval Ready | 完成首版 | 事件样本、回放与最小检查闭环已落地 |
| M9 Workbench Runnable | 完成首版 | 后端 FastAPI 入口 + Streamlit 工作台已可一键启动；见 [operations/workbench-runbook.md](operations/workbench-runbook.md) |

## 本轮新增成果

- 新增 `RetrievalStrategyClassifier` 抽象与 stub/fallback
- 新增 `ContextRetrievalPlanner`
- 新增双层外部检索组合器 `DualSourceExternalContextRetriever`
- 新增真实 provider：
  - `BochaEventSearchProvider`
  - `CninfoContextSearchProvider`
  - `SseContextSearchProvider`
  - `OfficialDisclosureSearchProvider`
- `collect_event_context` 从“固定外部 + 固定本地 RAG”改为“条件 RAG”
- `OrchestratorService` 默认装配真实 dual-source external retriever
- 新增 `event_eval` 模块：
  - fixture schema
  - replay result schema
  - replay runner
  - 确定性 checks
- 新增 Streamlit 工作台最小可视化骨架：
  - `分析视图` 复用统一 `analysis/turns` 入口
  - `调试视图` 可查看 route / plan / execution
  - `评测视图` 可查看 replay summary、records 与 checks
- 当前可批量观察：
  - `intent`
  - 检索策略
  - 是否降级
  - 候选数量
  - 证据引用数量

## 当前重点风险

### 1. 检索策略分类器仍为 stub/fallback

影响：
- `collect_event_context` 的主检索起手式目前仍使用安全默认值
- 真实分类器训练与离线评测尚未接入主流程

状态：
- 训练设计与计划已单独拆出
- 不阻塞当前事件主链继续演进

### 2. 真实外部检索已接入，首版评测基线已建立

影响：
- `Bocha` 与官方披露站检索已能被控制面消费
- 且现在已经可以用 replay 样本批量验证命中质量、弱结果降级与不同事件类型的稳定性

### 3. 事件评测仍处于首版基线阶段

影响：
- 当前已具备首批事件样本、回放入口与最小检查项
- 但样本量、弱结果覆盖、误判门槛和长期趋势分析仍需继续扩展

## 下一阶段建议

1. 扩展 `event_impact_analysis` 评测样本规模，补更多弱结果与误判场景
2. 独立推进 `RetrievalStrategyClassifier` 训练子项目
3. 为外部检索补缓存、超时与失败降级策略
4. 扩展结构化数据覆盖范围，补更多公司、指标与期间
