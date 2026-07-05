# 控制面状态

日期：2026-07-05  
当前状态：进行中  
阶段结论：控制面已完成三类主链的首版真实编排，并已具备事件样本回放能力，当前重点从“主链接线”转向“检索质量、分类器与评测增强”。

## 模块范围

- `semantic-routing-and-planning`
- `conversation-session-state`
- `event-analysis-orchestration`

## 当前能力

### 1. Router / Planner

- `RouterService` 已稳定输出：
  - `metric_lookup`
  - `evidence_lookup`
  - `event_impact_analysis`
  - `out_of_scope`
- `PlannerService` 已稳定输出：
  - `metric_lookup` 两阶段计划
  - `evidence_lookup` 两阶段计划
  - `event_impact_analysis` 四阶段计划

### 2. Orchestrator

- `OrchestratorService` 已稳定执行：
  - `query_structured_data`
  - `synthesize_brief_answer`
  - `collect_event_context`
  - `analyze_targets`
  - `retrieve_evidence`
  - `synthesize_report`
- 已支持：
  - `out_of_scope` 短路
  - `StageObservation`
  - execution trace
  - retrieval facade 懒加载与生命周期关闭

### 3. Session

- `SessionContext` 已接入统一入口
- 已支持：
  - snapshot 持久化
  - follow-up 上下文加载
  - rolling summary

### 4. 事件主链新增能力

- `event_impact_analysis` 已具备完整四阶段执行链
- `collect_event_context` 已改为：
  - 双层外部检索优先
  - 本地 RAG 条件补充
- `analyze_targets` 已支持：
  - 候选池不足时补 1 轮候选发现检索
  - 仍不足时诚实降级，不伪造股票池

### 5. Streamlit 内部工作台

- 已具备三类视图骨架：
  - `分析视图`
  - `调试视图`
  - `评测视图`
- `分析视图` / `调试视图` 复用统一 `analysis/turns` 入口
- `评测视图` 复用 `event_eval` fixtures、replay 与 checks

## 本轮新增

- 新增 `RetrievalStrategyClassifier` 抽象与 stub/fallback
- 新增 `ContextRetrievalPlanner`
- 新增 `DualSourceExternalContextRetriever`
- `OrchestratorService` 默认装配真实 dual-source external retriever
- 新增 `event_impact_analysis` replay 回放框架，可批量观察策略、降级与候选结果

## 活跃任务状态

| 任务 | 状态 | 说明 |
| --- | --- | --- |
| `semantic-routing-and-planning` 首版规则实现 | 已完成 | 已稳定驱动真实主链 |
| `SessionContext` 首版真实接线 | 已完成 | follow-up 已可真实续接 |
| `event_impact_analysis` 首版四阶段接线 | 已完成 | 事件链可真实执行 |
| 双层外部上下文检索接入 | 已完成首版 | 已接入 GDELT + 官方披露搜索 |
| 事件分析评测样本与回放 | 已完成首版 | 可批量回放事件 query，并观测策略与降级结果 |
| Streamlit 调试/评测工作台 | 已完成首版 | 已具备分析、调试、评测三视图骨架 |
| 检索策略分类器训练 | 未开始实现 | 已单独拆成训练子项目，不阻塞主链 |
| 事件分析评测集扩展 | 进行中 | 已有首版基线，后续继续补样本与误判场景 |

## 当前风险

1. `RetrievalStrategyClassifier` 仍是 stub/fallback，真实小模型分类尚未接入主流程。
2. 双层外部检索虽然已建立 replay 基线，但样本规模和弱结果覆盖仍不足。
3. `analyze_targets` 已可批量回放，但目标发现质量仍需更多真实事件样本观察。

## 下一步建议

1. 扩展 `event_impact_analysis` 评测样本与误判回放集
2. 按独立计划推进分类器训练与离线评测
3. 评估是否需要缓存、超时控制与 provider 级别熔断
