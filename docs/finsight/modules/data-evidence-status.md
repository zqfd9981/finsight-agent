# 数据与证据面状态

日期：2026-06-27
当前状态：进行中
当前负责人：待分配

## 1. 模块范围

- `structured-market-data-support`
- `evidence-retrieval-pipeline`

## 2. 当前里程碑

- Evidence Ready

## 3. 本轮目标

- 先确保 `structured-market-data-support` 已能服务首条 `metric_lookup` 快路径
- `EvidenceBundle` 保持 contract ready，但暂不抢先进入真实 retrieval 实现
- 不急着做复杂检索优化

## 4. 已冻结输入

- 共享接口：`EvidenceBundle`
- 参考文档：`docs/finsight/shared-contracts-v1.md`
- 输入假设：`metric_lookup` 先走结构化数据占位查询，retrieval 后置

## 5. 本轮输出

- `metric_lookup` 结构化查询占位输出
- `EvidenceBundle` contract 与后续 retrieval 输入边界

## 6. 活跃任务

- 任务：`EvidenceBundle` 最小链路
  状态：未开始
  窗口：待分配
  说明：当前不是首条快路径优先项，保留到 retrieval 实现轮次
- 任务：候选对象最小输出
  状态：部分完成
  窗口：主控窗口
  说明：已落地 metric_lookup 结构化查询占位返回，未接真实候选映射与排序

## 7. 当前卡点

- `event_entities` 与 claim/target 的真实输入仍未固定
- `support_strength` 的判断口径还没有用真实样例压过一遍
- retrieval 何时启动，要看首条 `metric_lookup` 快路径是否先落地

## 8. 不要改什么

- 不改 `RouterResult`、`Plan`、`SessionContext`
- 不改 `FinalResponse`
- 不修改 UI 展示逻辑

## 9. 下一次阶段检查

- 检查结构化数据骨架是否已经足够让首条 `metric_lookup` 实现继续推进

## 10. 完成定义

- `structured-market-data-support` 已能提供首条快路径所需的占位结构
- `EvidenceBundle` contract 已冻结，可留待 retrieval 实现轮次直接消费
- 当前不要求 retrieval 真实产出即可继续推进首条快路径
