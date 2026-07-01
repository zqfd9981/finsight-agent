# Event Analysis Orchestrator Implementation Plan

日期：2026-07-01  
状态：已完成

## 1. 目标

基于方案 A 落地 orchestrator 首版最小可运行链路：

- 打通 `metric_lookup` 短路径
- 打通 `evidence_lookup` 路径
- 让统一后端入口走真实 `route -> plan -> orchestrate -> envelope`
- 输出标准化 `StageObservation` 与 execution trace

## 2. 执行结果摘要

本计划已经全部完成，实际落地结果如下：

- 已新增 orchestrator 设计文档
- 已实现 `OrchestratorService` 首版真实执行流
- 已实现四个首版 stage runner
- 已接入 `StageObservation`
- 已接入 execution trace
- 已将 `WorkbenchBackendApiService` 与 API handler 从 stub 切到真实链路
- 已增加 unsupported stage 的失败保护
- 已修复 retrieval 本地 Qdrant 路径的资源生命周期问题

## 3. 任务完成状态

- [x] Task 1：建立 orchestrator 内部结果对象与 observation builder
- [x] Task 2：实现首版 stage runners
- [x] Task 3：实现 `OrchestratorService` 主执行流、停止策略与 execution trace
- [x] Task 4：将 `WorkbenchBackendApiService` 从 stub 接到真实 orchestrator
- [x] Task 5：补充失败保护、导入级验证与额外覆盖
- [x] Task 6：完成回归验证并整理交付说明

## 4. 实际交付内容

### 控制面

- `OrchestratorService`
- `StageExecutionResult`
- `OrchestrationResult`
- `build_stage_observation(...)`
- `build_execution_trace_block(...)`

### stage runners

- `query_structured_data`
- `synthesize_brief_answer`
- `retrieve_evidence`
- `synthesize_report`

### 统一入口接线

- `WorkbenchBackendApiService.build_response(...)`
- `backend/apps/api/analysis_turns.py`

### 稳定性增强

- unsupported stage 显式失败
- retrieval 懒加载
- orchestrator 自建 retrieval facade 执行后自动关闭
- 本地 Qdrant collection 重建前显式关闭旧 collection
- 本地 Qdrant 初始化跳过会留下告警的临时 `:memory:` SQLite 探测连接

## 5. 验证结果

已通过的关键验证命令：

- `python -m unittest tests.unit.test_orchestrator_service -v`
- `python -m unittest tests.unit.test_qdrant_store tests.unit.test_qdrant_store_resource_lifecycle tests.unit.test_dense_retrieval_facade tests.integration.test_metric_lookup_placeholder -v`
- `python -m unittest tests.unit.test_semantic_routing_and_planning tests.unit.test_orchestrator_service tests.unit.test_orchestrator_stage_runners tests.unit.test_project_skeleton tests.unit.test_qdrant_store tests.unit.test_qdrant_store_resource_lifecycle tests.unit.test_trace_builder tests.unit.test_dense_retrieval_facade tests.integration.test_metric_lookup_placeholder -v`

最终结果：

- 53 个相关测试全部通过
- evidence 集成测试中的 `ResourceWarning` 已清除

## 6. 后续建议

下一阶段优先级建议如下：

1. 把 `SessionContext` 真正接入 `WorkbenchBackendApiService`
2. 让 evidence follow-up 在线上真实 API 路径下工作
3. 推进 `structured-market-data-support` 的真实数据源接入
4. 为 orchestrator / retrieval / response 补齐首批评测样本
