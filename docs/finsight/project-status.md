# FinSight V1 项目状态

日期：2026-07-02  
状态：控制面、结构化数据、证据检索与事件主链均已形成首版可运行闭环，项目进入“能力增强与评测补强”阶段。

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
  - `GDELT` 事件搜索
  - `CNInfo + SSE` 官方披露搜索

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

## 本轮新增成果

- 新增 `RetrievalStrategyClassifier` 抽象与 stub/fallback
- 新增 `ContextRetrievalPlanner`
- 新增双层外部检索组合器 `DualSourceExternalContextRetriever`
- 新增真实 provider：
  - `GdeltEventSearchProvider`
  - `CninfoContextSearchProvider`
  - `SseContextSearchProvider`
  - `OfficialDisclosureSearchProvider`
- `collect_event_context` 从“固定外部 + 固定本地 RAG”改为“条件 RAG”
- `OrchestratorService` 默认装配真实 dual-source external retriever

## 当前重点风险

### 1. 检索策略分类器仍为 stub/fallback

影响：
- `collect_event_context` 的主检索起手式目前仍使用安全默认值
- 真实分类器训练与离线评测尚未接入主流程

状态：
- 训练设计与计划已单独拆出
- 不阻塞当前事件主链继续演进

### 2. 真实外部检索已接入，但线上鲁棒性尚待评测

影响：
- `GDELT` 与官方披露站检索已能被控制面消费
- 但命中质量、弱结果降级与不同事件类型的稳定性仍需样本回放验证

### 3. 事件分析评测集仍需建立

影响：
- 目前已有单测与集成测试
- 但系统级事件样本、误判回放与质量门槛仍未形成正式评测体系

## 下一阶段建议

1. 建立 `event_impact_analysis` 首批评测样本与误判回放集
2. 独立推进 `RetrievalStrategyClassifier` 训练子项目
3. 扩展结构化数据覆盖范围，补更多公司、指标与期间
4. 评估是否为外部检索补更多 provider 或缓存策略
