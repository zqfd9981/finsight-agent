# 控制面状态

日期：2026-06-27
当前状态：进行中
当前负责人：待分配

## 1. 模块范围

- `conversation-session-state`
- `semantic-routing-and-planning`
- `event-analysis-orchestration`

## 2. 当前里程碑

- Control Plane Mock Ready

## 3. 本轮目标

- 保持 `RouterResult` 和 `Plan` 的最小版本稳定可复用
- 让控制面骨架能被统一 API boundary 继续消费
- 暂时不急着把 session 和 orchestrator 真实链路串起来

## 4. 已冻结输入

- 共享接口：`RouterResult`、`Plan`、`SessionContext`、`StageObservation`
- 参考文档：`docs/finsight/shared-contracts-v1.md`
- 当前依赖：共享接口与 API boundary 已可视为首版稳定基线

## 5. 本轮输出

- 能稳定产出的 `RouterResult` mock
- 能稳定产出的 `Plan` mock
- 供后端统一入口消费的 metric_lookup 最小控制面骨架

## 6. 活跃任务

- 任务：`RouterResult` 最小 mock
  状态：已完成
  窗口：主控窗口
  说明：已落地 metric_lookup 快路径占位路由结果
- 任务：`Plan` 四阶段骨架
  状态：部分完成
  窗口：主控窗口
  说明：已落地 metric_lookup 两阶段骨架，事件分析四阶段仍待后续实现
- 任务：`SessionContext` 最小信息确认
  状态：未开始
  窗口：待分配
  说明：当前只通过 `session_id` 透传，尚未进入真实会话状态实现

## 7. 当前卡点

- `follow_up_type` 目前只有 API boundary 层的最小追问占位语义
- `SessionContext` 仍未进入持久化或压缩实现
- orchestrator 仍适合后置，不宜和首条快路径混在同一轮推进

## 8. 不要改什么

- 不改 `EvidenceBundle`
- 不改 `FinalResponse`、`TraceBlock`
- 不直接扩写共享接口里的必填字段

## 9. 下一次阶段检查

- 检查控制面骨架是否已经足够支撑首条 `metric_lookup` 真实实现 change

## 10. 完成定义

- `RouterResult` 与 `Plan` 已能支撑统一 API boundary 的骨架联调
- 首条 `metric_lookup` 实现可以直接复用当前 router/planner 骨架继续前进
- session 与 orchestrator 的真实实现明确后置，不阻塞首条快路径
