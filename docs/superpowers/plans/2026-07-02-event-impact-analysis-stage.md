# 2026-07-02 Event Impact Analysis Stage Implementation Plan

目标：为 `event_impact_analysis` 打通首版真实执行链，补齐 `collect_event_context` 与 `analyze_targets`，并让后续 `retrieve_evidence` / `synthesize_report` 真正消费它们的标准化输出。

架构结论：

- 保持现有四阶段 `Plan` 结构不变
- 新增外部上下文检索抽象 `ExternalContextRetriever`
- 新增受约束 LLM 目标分析服务 `TargetAnalysisService`
- `collect_event_context` 负责事件背景检索与上下文压缩
- `analyze_targets` 负责候选池构造、一次有界候选发现检索与结构化目标分析
- `retrieve_evidence` / `synthesize_report` 继续复用现有链路，但消费前两阶段输出

## 文件结构

### 新增文件

- `backend/src/finsight_agent/control_plane/orchestrator/context_retriever.py`
- `backend/src/finsight_agent/control_plane/orchestrator/target_analysis.py`
- `backend/src/finsight_agent/control_plane/orchestrator/stage_runners/collect_event_context.py`
- `backend/src/finsight_agent/control_plane/orchestrator/stage_runners/analyze_targets.py`
- `tests/integration/test_event_impact_analysis_flow.py`

### 修改文件

- `backend/src/finsight_agent/control_plane/orchestrator/service.py`
- `backend/src/finsight_agent/control_plane/orchestrator/stage_runners/__init__.py`
- `backend/src/finsight_agent/control_plane/orchestrator/stage_runners/synthesize_report.py`
- `tests/unit/test_orchestrator_stage_runners.py`
- `tests/unit/test_orchestrator_service.py`
- `docs/finsight/project-status.md`
- `docs/finsight/modules/control-plane-status.md`
- `docs/finsight/modules/data-evidence-status.md`

## 执行结果

- [x] Task 1：补外部上下文检索抽象与目标分析服务
- [x] Task 2：实现 `collect_event_context` runner
- [x] Task 3：实现 `analyze_targets` runner
- [x] Task 4：接入 orchestrator 主链并增强事件报告
- [x] Task 5：补端到端测试并同步状态文档

## 关键实现说明

- `collect_event_context` 同时消费外部上下文检索与本地 RAG，并输出：
  - `event_context`
  - `event_entities`
  - `source_status`
- `analyze_targets` 采用“结构化候选池 + 受约束 LLM”方案
- 当候选池不足时，`analyze_targets` 只允许做 1 轮候选发现检索
- 候选仍不足时返回 `degraded`，不伪造股票池
- `synthesize_report` 已开始消费目标分析结果，并在摘要、不确定性和下一步建议中体现

## 验证记录

已通过：

```bash
python -m unittest tests.unit.test_orchestrator_stage_runners tests.unit.test_orchestrator_service -v
python -m unittest tests.integration.test_event_impact_analysis_flow -v
python -m unittest tests.unit.test_semantic_routing_and_planning tests.unit.test_orchestrator_service tests.unit.test_orchestrator_stage_runners tests.unit.test_trace_builder tests.unit.test_session_repository tests.unit.test_session_context_extractor tests.unit.test_workbench_session_flow tests.unit.test_project_skeleton tests.integration.test_metric_lookup_placeholder tests.integration.test_metric_lookup_structured_data tests.integration.test_event_impact_analysis_flow -v
```

最终结果：`69` 个相关测试全部通过。

## 后续建议

1. 为 `ExternalContextRetriever` 接入真实外部 provider
2. 为事件分析建立首批评测集
3. 增强 `analyze_targets` 的事实底座与输出校验
