# 双层事件上下文检索实现计划

日期：2026-07-02  
状态：已完成

## 目标

为 `event_impact_analysis` 接入首版真实外部检索能力，打通：

- `GDELT` 事件搜索
- `CNInfo + SSE` 官方披露搜索

并通过 `ContextRetrievalPlanner` 控制：

- `collect_event_context`
- 候选发现检索
- 本地 RAG 的条件补充

## 实际落地结果

### 已完成实现

- `RetrievalStrategyClassifier` 抽象与 `StubRetrievalStrategyClassifier`
- `ExternalContextResult` / `ContextRetrievalPlan` 等标准模型
- `ContextRetrievalPlanner`
- `GdeltEventSearchProvider`
- `CninfoContextSearchProvider`
- `SseContextSearchProvider`
- `OfficialDisclosureSearchProvider`
- `DualSourceExternalContextRetriever`
- `collect_event_context` 条件 RAG 改造
- `OrchestratorService` 默认装配 dual-source external retriever

### 已完成测试

- `tests/unit/test_external_context_retriever.py`
- `tests/unit/test_context_retrieval_planner.py`
- `tests/unit/test_gdelt_event_search.py`
- `tests/unit/test_official_disclosure_search.py`
- `tests/unit/test_orchestrator_stage_runners.py`
- `tests/unit/test_orchestrator_service.py`
- `tests/integration/test_event_impact_analysis_flow.py`

## 完成情况

| 任务 | 状态 | 说明 |
| --- | --- | --- |
| 分类器抽象与 fallback | 完成 | 主流程暂用 stub，不阻塞后续训练子项目 |
| 双层 provider 模型与 planner | 完成 | 已形成可复用的控制面检索计划 |
| GDELT 事件搜索 provider | 完成 | 已能标准化事件搜索结果 |
| CNInfo / SSE 官方披露搜索 | 完成 | 已能标准化运行时披露搜索结果 |
| DualSourceExternalContextRetriever | 完成 | 已能合并两类源结果 |
| `collect_event_context` 条件 RAG | 完成 | 外部结果足够时跳过本地 RAG |
| orchestrator 默认装配 | 完成 | 未注入时默认走真实 dual-source retriever |
| 单测 / 集成测试 | 完成 | 关键路径已回归通过 |
| 状态文档同步 | 完成 | 项目状态、控制面状态、数据与证据状态已更新 |

## 验证命令

```bash
python -m unittest tests.unit.test_external_context_retriever tests.unit.test_context_retrieval_planner tests.unit.test_gdelt_event_search tests.unit.test_official_disclosure_search tests.unit.test_orchestrator_stage_runners tests.unit.test_orchestrator_service tests.integration.test_event_impact_analysis_flow -v
```

结果：`33` 个测试全部通过。

## 后续不在本计划内

- `RetrievalStrategyClassifier` 训练与接入
- provider 级缓存、超时、熔断与更细粒度排序
- 事件分析评测样本与误判回放体系
