# 数据与证据面状态

日期：2026-07-05  
当前状态：可联调  
阶段结论：结构化数据、本地 RAG、首版外部上下文检索以及对应的 replay 评测基线都已经能被控制面统一消费。

## 模块范围

- `structured-market-data-support`
- `evidence-retrieval-pipeline`
- 事件外部上下文检索 provider

## 当前能力

### 1. Retrieval Pipeline

已完成：

- 本地 PDF acquisition
- parsing / chunking
- sparse retrieval
- dense retrieval
- fusion / rerank
- retrieval output assembly
- `RetrievalResult`
- retrieval trace

### 2. Structured Data

已完成：

- 财报表格指标抽取
- 本地指标库构建
- `StructuredDataService` 查询
- 本地优先、外部 fallback 的 `metric_lookup` 路径

### 3. 事件外部检索

本轮已新增：

- `GdeltEventSearchProvider`
  - 负责事件背景、近期资讯与 supporting points
- `CninfoContextSearchProvider`
  - 负责 CNInfo 运行时披露搜索
- `SseContextSearchProvider`
  - 负责 SSE 运行时披露搜索
- `OfficialDisclosureSearchProvider`
  - 负责组合 CNInfo + SSE 的官方披露结果
- `event_eval` replay 框架
  - 负责事件样本回放、最小字段抽取与确定性检查

## 控制面消费方式

- `collect_event_context`
  - 先消费外部上下文检索
  - 再按条件补本地 RAG
- `analyze_targets`
  - 候选池不足时触发 1 轮候选发现检索
- `retrieve_evidence`
  - 继续以本地 RAG 为主，消费上游事件上下文和目标范围

## 活跃任务状态

| 任务 | 状态 | 说明 |
| --- | --- | --- |
| retrieval 主链稳定化 | 已完成 | 已可稳定被 `evidence_lookup` / `event_impact_analysis` 消费 |
| structured market data 首版闭环 | 已完成 | `metric_lookup` 已接通真实结果 |
| 双层事件外部检索 provider | 已完成首版 | GDELT + 官方披露搜索已落地 |
| 外部检索质量回放 | 已完成首版 | 可用于观察 provider 命中、弱结果与候选发现行为 |
| structured data 覆盖扩展 | 未开始 | 后续补更多公司、指标、期间 |

## 当前风险

1. 外部 provider 已接入且已有 replay 基线，但真实网络返回的稳定性与去重质量仍需更多样本验证。
2. 事件候选发现质量仍需扩更多批量样本，不宜直接把当前行为视为最终版本。
3. 结构化数据覆盖仍有限，`metric_lookup` 的命中范围还需继续扩展。

## 下一步建议

1. 扩展 `GDELT + 官方披露` 的事件样本回放和弱结果评测
2. 为 provider 增加缓存、超时和失败降级策略
3. 持续扩展本地指标库覆盖范围
