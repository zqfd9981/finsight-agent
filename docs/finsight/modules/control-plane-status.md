# 控制面状态

日期：2026-06-29
当前状态：进行中
当前负责人：待分配

## 1. 模块范围

- `conversation-session-state`
- `semantic-routing-and-planning`
- `event-analysis-orchestration`

## 2. 当前里程碑

- Control Plane Semantic Routing Ready

## 3. 本轮目标

- 按既有设计完成 `semantic-routing-and-planning` 的首版规则实现
- 让统一 API boundary 消费真实 router / planner 输出，而不再只消费硬编码 stub
- 继续保持 session 和 orchestrator 的真实链路后置

## 4. 已冻结输入

- 共享接口：`RouterResult`、`Plan`、`SessionContext`、`StageObservation`
- 参考文档：`docs/finsight/shared-contracts-v1.md`
- 当前依赖：共享接口与 API boundary 已可视为首版稳定基线

## 5. 本轮输出

- 能稳定产出的 `RouterResult` 规则结果
- 能稳定产出的 `Plan` 长短路径骨架
- 供后端统一入口消费的 routing / planning trace

## 6. 活跃任务

- 任务：`RouterResult` 最小 mock
  状态：已完成
  窗口：主控窗口
  说明：已升级为规则路由，覆盖 `metric_lookup`、`event_impact_analysis`、`evidence_lookup` 与 `out_of_scope`
- 任务：`Plan` 四阶段骨架
  状态：已完成
  窗口：主控窗口
  说明：已落地 metric_lookup 两阶段、event analysis 四阶段、evidence lookup 缩减路径和 out-of-scope guardrail 计划
- 任务：统一 API 接入真实 router / planner
  状态：已完成
  窗口：主控窗口
  说明：`analysis_turns` 已通过 `WorkbenchBackendApiService` 消费真实 routing / planning 输出，并可返回 trace
- 任务：`SessionContext` 最小信息确认
  状态：未开始
  窗口：待分配
  说明：当前只通过 `session_id` 透传，尚未进入真实会话状态实现

## 7. 当前卡点

- `follow_up_type` 已有首版规则，但仍依赖轻量关键词与最小会话摘要
- `SessionContext` 仍未进入持久化或压缩实现
- orchestrator 仍适合后置，不宜和首条快路径混在同一轮推进

## 8. 不要改什么

- 不改 `EvidenceBundle`
- 不改 `FinalResponse`、`TraceBlock`
- 不直接扩写共享接口里的必填字段

## 9. 下一次阶段检查

- 检查当前 routing / planning 规则是否足够支撑首条 `metric_lookup` 真正接入结构化数据结果

## 10. 完成定义

- `RouterResult` 与 `Plan` 已能支撑统一 API boundary 的规则联调
- 首条 `metric_lookup` 实现可以直接复用当前 router / planner 骨架继续前进
- session 与 orchestrator 的真实实现明确后置，不阻塞首条快路径
