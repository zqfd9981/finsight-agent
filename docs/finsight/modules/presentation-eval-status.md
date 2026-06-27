# 呈现与评测面状态

日期：2026-06-27
当前状态：进行中
当前负责人：待分配

## 1. 模块范围

- `report-trace-and-evaluation`
- `analysis-workbench`

## 2. 当前里程碑

- Response Ready

## 3. 本轮目标

- 保持 `FinalResponse`、`TraceBlock` 和 guardrail 响应骨架稳定
- 已接上统一 API boundary 的 envelope，不再只停留在孤立 mock
- 页面展示仍保持后置，不着急接真实复杂后端

## 4. 已冻结输入

- 共享接口：`FinalResponse`、`TraceBlock`、`GuardrailOrErrorResponse`
- 参考文档：`docs/finsight/shared-contracts-v1.md`
- 当前依赖：统一 API boundary 已冻结，可先基于 response envelope 推进

## 5. 本轮输出

- `FinalResponse` 骨架
- `TraceBlock` 骨架
- `AnalysisResponseEnvelope` 与 workbench client 骨架

## 6. 活跃任务

- 任务：`FinalResponse` success 渲染
  状态：部分完成
  窗口：主控窗口
  说明：后端 `FinalResponse` 骨架已可稳定产出，页面渲染仍待继续
- 任务：`TraceBlock` 面板
  状态：部分完成
  窗口：主控窗口
  说明：已接入 routing trace 占位块，planning/retrieval 面板仍未实现
- 任务：guardrail 展示
  状态：未开始
  窗口：待分配
  说明：先保证用户能看懂为什么停住、下一步怎么办
- 任务：workbench API client 骨架
  状态：已完成
  窗口：主控窗口
  说明：已落地统一 request/envelope 的前端 client，占位消费 API boundary

## 7. 当前卡点

- 页面级 workbench 交互仍未实现
- planning / retrieval trace 仍未接入
- 真实 orchestrator 没接入前，仍只能先验证骨架展示链路

## 8. 不要改什么

- 不改控制面的接口定义
- 不改 `EvidenceBundle` 的必填字段
- 不提前绑定真实 orchestrator 的运行行为

## 9. 下一次阶段检查

- 检查 workbench 是否进入首条真实 API 调用与结果展示实现

## 10. 完成定义

- `FinalResponse`、`TraceBlock`、guardrail response 的 contract 与骨架已稳定
- workbench 能通过统一 API boundary client 接入后端
- 下一轮只需补真实页面交互与结果展示，而不是重做接口边界
