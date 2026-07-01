# 控制面状态

日期：2026-07-01  
当前状态：进行中  
当前负责人：待分配

## 1. 模块范围

- `conversation-session-state`
- `semantic-routing-and-planning`
- `event-analysis-orchestration`

## 2. 当前里程碑

- `semantic-routing-and-planning` 首版完成
- `event-analysis-orchestration` 首版最小运行链完成

## 3. 本轮目标完成情况

本轮原定目标已经基本完成：

- 已按既有设计落地 orchestrator 方案 A
- 已让统一 API boundary 消费真实 router / planner / orchestrator 输出
- 已打通 `metric_lookup` 与 `evidence_lookup` 两条首版真实链路
- 已补充 execution trace 与 `StageObservation`

仍未完成的部分：

- `SessionContext` 真实接线
- event 四阶段真实执行能力

## 4. 当前输出

### semantic routing / planning

- `RouterService` 已稳定输出：
  - `metric_lookup`
  - `event_impact_analysis`
  - `evidence_lookup`
  - `out_of_scope`
- `PlannerService` 已稳定输出：
  - `metric_lookup` 两阶段短路径
  - `evidence_lookup` 两阶段短路径
  - `event_impact_analysis` 四阶段计划骨架

### event-analysis-orchestration

- `OrchestratorService` 已实现真实执行流
- 已支持：
  - `query_structured_data`
  - `synthesize_brief_answer`
  - `retrieve_evidence`
  - `synthesize_report`
- 已支持：
  - `out_of_scope` 短路
  - execution trace
  - `StageObservation`
  - unsupported stage 显式失败
  - retrieval 懒加载与执行后资源关闭

### 统一入口接线

- `WorkbenchBackendApiService` 已走真实链路：
  - `route -> plan -> orchestrate -> envelope`
- `backend/apps/api/analysis_turns.py` 已不再返回 stub

## 5. 活跃任务状态

- 任务：`semantic-routing-and-planning` 首版规则实现
  状态：已完成
  说明：已稳定支撑最小真实链路

- 任务：`event-analysis-orchestration` 方案 A 落地
  状态：已完成首版
  说明：`metric_lookup` / `evidence_lookup` 已真实接线

- 任务：统一 API 接入真实 orchestrator
  状态：已完成
  说明：trace 与 response 已通过统一入口返回

- 任务：`SessionContext` 真实接线
  状态：未开始
  说明：当前后端入口仍只透传 `session_id`

- 任务：event 四阶段真实执行
  状态：未开始
  说明：当前只保留计划骨架与失败保护

## 6. 当前风险与卡点

- `SessionContext` 未接入会影响 evidence follow-up 的线上效果
- event 四阶段尚未有真实 runner，当前遇到未注册 stage 会显式失败
- `WorkbenchBackendApiService` 尚未消费真实会话上下文，compare / drilldown 线上行为仍受限

## 7. 不要改什么

- 不要在 orchestrator 中重新定义 router / planner / retrieval 的 contract 主权
- 不要把 retrieval 内部中间态直接暴露给 API boundary
- 不要在 session 能力未设计清楚前把会话状态逻辑硬塞进 orchestrator

## 8. 下一次阶段检查

1. 检查 `SessionContext` 是否开始进入统一后端入口
2. 检查 evidence follow-up 是否能在真实 API 路径下工作
3. 检查 event 四阶段中下一批 runner 的边界设计是否已明确

## 9. 完成定义

控制面下一阶段可视为“进一步完成”的条件：

- `SessionContext` 开始被真实消费
- evidence follow-up 能在统一入口下真实工作
- event 四阶段至少接通第一批真实执行能力
