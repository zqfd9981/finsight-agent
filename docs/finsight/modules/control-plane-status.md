# 控制面状态

日期：2026-07-02  
当前状态：进行中  
当前负责人：待分配

## 1. 模块范围

- `conversation-session-state`
- `semantic-routing-and-planning`
- `event-analysis-orchestration`

## 2. 当前里程碑

- `semantic-routing-and-planning` 首版完成
- `conversation-session-state` 首版完成
- `event-analysis-orchestration` 首版四阶段事件主链完成

## 3. 当前阶段结论

控制面目前已经不再只是“短路径接线”，而是具备了三类真实执行链：

- `metric_lookup`
  - `query_structured_data`
  - `synthesize_brief_answer`
- `evidence_lookup`
  - `retrieve_evidence`
  - `synthesize_report`
- `event_impact_analysis`
  - `collect_event_context`
  - `analyze_targets`
  - `retrieve_evidence`
  - `synthesize_report`

其中 `event_impact_analysis` 的新增能力包括：

- 外部上下文检索抽象
- 受约束 LLM 目标分析服务
- 候选池不足时的一次有界候选发现检索
- 候选仍不足时的诚实降级，不伪造股票池

## 4. 当前输出

### semantic routing / planning

- `RouterService` 已稳定输出：
  - `metric_lookup`
  - `event_impact_analysis`
  - `evidence_lookup`
  - `out_of_scope`
- `PlannerService` 已稳定输出：
  - `metric_lookup` 两阶段计划
  - `evidence_lookup` 两阶段计划
  - `event_impact_analysis` 四阶段计划

### event-analysis-orchestration

- `OrchestratorService` 已支持真实执行：
  - `collect_event_context`
  - `analyze_targets`
  - `query_structured_data`
  - `synthesize_brief_answer`
  - `retrieve_evidence`
  - `synthesize_report`
- 已支持：
  - `out_of_scope` 短路
  - execution trace
  - `StageObservation`
  - retrieval facade 懒加载与执行后关闭

### 统一入口接线

- `WorkbenchBackendApiService` 已走真实链路：
  - `route -> plan -> orchestrate -> envelope`
- `SessionContext` 已在统一入口真实加载与保存
- `event_impact_analysis` 已有端到端集成测试覆盖

## 5. 活跃任务状态

- 任务：`semantic-routing-and-planning` 首版规则实现  
  状态：已完成  
  说明：已稳定支撑最小真实链路

- 任务：`SessionContext` 首版真实接线  
  状态：已完成  
  说明：已支持 follow-up 读取压缩上下文与 rolling summary

- 任务：`event_impact_analysis` 首版四阶段接线  
  状态：已完成  
  说明：事件背景收集、目标分析、证据补强、报告生成已可真实串联

- 任务：真实外部工具 provider 接入  
  状态：未开始  
  说明：当前仅完成抽象层与 stub 级接线

- 任务：事件分析评测与回归集  
  状态：未开始  
  说明：当前以单测和集成测试为主

## 6. 当前风险与卡点

- 外部工具检索尚未接入真实 provider，近期事件的时效性仍有限
- `analyze_targets` 已接入受约束 LLM，但仍缺系统化评测样本
- 事件分析结果目前更偏“首版可运行链”，精细排序和覆盖度仍需迭代

## 7. 不要改什么

- 不要在 orchestrator 中重新定义 router / planner / retrieval 的 contract 主权
- 不要让 `analyze_targets` 在候选池为空时直接自由生成股票列表
- 不要让 report 层私自扩展新的 block contract，而绕过 shared contract 演进

## 8. 下一次阶段检查

1. 检查是否选定并接入第一个真实外部检索 provider
2. 检查事件分析评测样本是否开始沉淀
3. 检查 `analyze_targets` 的结构化输入是否需要补充更多事实底座

## 9. 完成定义

控制面下一阶段可视为“进一步完成”的条件：

- 外部工具检索已具备真实线上 provider
- `event_impact_analysis` 建立起首批评测与回归集
- 事件分析链路在更多 query 上具备稳定降级与可解释行为
