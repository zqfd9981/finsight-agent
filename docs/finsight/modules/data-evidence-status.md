# 数据与证据面状态

日期：2026-07-01
当前状态：可联调
当前负责人：待分配

## 1. 模块范围

- `structured-market-data-support`
- `evidence-retrieval-pipeline`

## 2. 当前里程碑

- Retrieval Pipeline Ready

## 3. 本轮目标

- 保持本地 PDF 语料采集、解析、切块和检索闭环稳定
- 让 retrieval 输出具备上游可消费的 `EvidenceItem`、`retrieval_trace` 与 `parent_context`
- 为 orchestrator 接线阶段准备稳定 retrieval facade

## 4. 已冻结输入

- 共享接口：`EvidenceBundle`、`RetrievalResult`
- 参考文档：`docs/finsight/shared-contracts-v1.md`
- 当前依赖：
  - 本地 PDF 样本语料
  - chunked filings 产物
  - shared contracts

## 5. 本轮输出

- 本地 PDF acquisition 链路
- parsing + chunking 产物
- SQLite FTS5 sparse retrieval
- 本地 Qdrant + 本地 embedding dense retrieval
- RRF fusion + child rerank
- retrieval facade + retrieval output assembly

## 6. 活跃任务

- 任务：本地 PDF 语料采集
  状态：已完成
  窗口：主控窗口
  说明：SSE / CNInfo 双源链路已可稳定下载、清理坏 PDF，并生成覆盖率快照
- 任务：PDF parsing + parent/child chunking
  状态：已完成
  窗口：主控窗口
  说明：已稳定产出 `parsed_filings/`、`chunked_filings/`、`parents.jsonl`、`children.jsonl`
- 任务：sparse retrieval
  状态：已完成
  窗口：主控窗口
  说明：SQLite FTS5 已支持 child chunk 索引与原 query 优先检索
- 任务：dense retrieval
  状态：已完成
  窗口：主控窗口
  说明：本地 embedding、Qdrant、RRF、rerank 与 facade 已落地
- 任务：retrieval output assembly
  状态：已完成
  窗口：主控窗口
  说明：已补齐真实 `parent expand`、`EvidenceItem` 组装、结构化 `retrieval_trace`
- 任务：structured market data 真实数据源
  状态：未开始
  窗口：待分配
  说明：当前仍未接入真实指标数据库或离线表

## 7. 当前卡点

- `structured-market-data-support` 仍未接入真实结构化指标源
- retrieval 还没有首批 query/evidence 评测集
- orchestrator 尚未消费统一 `RetrievalResult`

## 8. 不要改什么

- 不改 `RouterResult`、`Plan`、`SessionContext`
- 不把 retrieval 的内部中间态直接暴露给上游
- 不提前把 workbench UI 逻辑塞进 retrieval 模块

## 9. 下一次阶段检查

- 检查 orchestrator 是否开始消费 retrieval facade
- 检查 retrieval 是否补入第一批评测样例

## 10. 完成定义

- 本地 PDF acquisition、parsing、chunking、sparse、dense、fusion、rerank、output assembly 已全部可用
- retrieval facade 可稳定产出结构化 `RetrievalResult`
- 下一轮只需做 orchestrator 接线、评测与真实数据增强，而不是回头重做 retrieval 主链路
