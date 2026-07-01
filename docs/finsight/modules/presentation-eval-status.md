# 呈现与评测面状态

日期：2026-07-01
当前状态：进行中
当前负责人：待分配

## 1. 模块范围

- `report-trace-and-evaluation`
- `analysis-workbench`

## 2. 当前里程碑

- Response Ready

## 3. 本轮目标

- 保持 `FinalResponse`、`TraceBlock` 和 guardrail 响应骨架稳定
- 让后续页面和 orchestrator 可以消费新的 `retrieval_trace`
- 继续把真实 UI 与评测工作后置到 retrieval / orchestrator 接线之后

## 4. 已冻结输入

- 共享接口：`FinalResponse`、`TraceBlock`、`GuardrailOrErrorResponse`
- 参考文档：`docs/finsight/shared-contracts-v1.md`
- 当前依赖：
  - 统一 API boundary
  - retrieval facade / retrieval output assembly

## 5. 本轮输出

- `FinalResponse` 骨架
- `TraceBlock` 骨架
- `AnalysisResponseEnvelope` 与 workbench client 骨架

## 6. 活跃任务

- 任务：`FinalResponse` success 渲染
  状态：部分完成
  窗口：主控窗口
  说明：后端 `FinalResponse` 骨架已稳定，页面端尚未接 retrieval 真结果
- 任务：`TraceBlock` 面板
  状态：部分完成
  窗口：主控窗口
  说明：routing / planning 占位 trace 已有，retrieval trace 刚在后端落地，前端尚未接线
- 任务：guardrail 展示
  状态：未开始
  窗口：待分配
  说明：仍需把停住原因和下一步建议做成清晰页面反馈
- 任务：workbench API client 骨架
  状态：已完成
  窗口：主控窗口
  说明：已落地统一 request/envelope 的前端 client

## 7. 当前卡点

- retrieval trace 虽已在后端落地，但页面侧还没消费
- orchestrator 还没接 retrieval 主链路，导致页面无法展示真实完整分析
- 评测层还没引入 retrieval 质量评测样例

## 8. 不要改什么

- 不改控制面的接口定义
- 不改 `EvidenceBundle` 的必填字段
- 不提前绑定真实 orchestrator 的运行行为

## 9. 下一次阶段检查

- 检查 workbench 是否开始消费 retrieval trace
- 检查评测层是否接入首批 retrieval 样例

## 10. 完成定义

- `FinalResponse`、`TraceBlock`、guardrail response 的 contract 与骨架已稳定
- retrieval 真实输出已经可供页面消费
- 下一轮只需补真实页面交互、retrieval trace 展示与评测，而不是回头修改 retrieval contract
