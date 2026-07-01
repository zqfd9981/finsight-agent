# 数据与证据面状态

日期：2026-07-01  
当前状态：可联调  
当前负责人：待分配

## 1. 模块范围

- `structured-market-data-support`
- `evidence-retrieval-pipeline`

## 2. 当前里程碑

- `Retrieval Pipeline Ready`

## 3. 当前阶段结论

retrieval 主链已经不是“准备接线”状态，而是“已被 orchestrator 消费”的状态：

- 本地 PDF acquisition、parsing、chunking 已稳定
- sparse / dense / fusion / rerank / output assembly 已稳定
- retrieval facade 已能返回结构化 `RetrievalResult`
- `evidence_lookup` 路径已经通过 orchestrator 与统一 API 真实接线

结构化市场数据能力已进入“真实数据首版闭环”阶段：

- 已完成本地指标库、本地优先查询与外部 fallback 接口
- `metric_lookup` 已可返回真实结构化数值，不再依赖 `TODO`
- 当前仍未覆盖更多公司、更多指标和更多期间类型

## 4. 当前输出

### retrieval 已完成能力

- 本地 PDF acquisition
- parsing + chunking
- SQLite FTS5 sparse retrieval
- 本地 Qdrant + 本地 embedding dense retrieval
- RRF fusion
- rerank
- evidence output assembly
- `RetrievalResult`
- retrieval trace
- parent context expand

### 本轮新增稳定性增强

- retrieval 已被 orchestrator 首版真实消费
- evidence 路径执行后会关闭 orchestrator 自建 retrieval facade
- 本地 Qdrant 路径的 collection 重建前会先关闭旧 collection
- 本地 Qdrant 初始化已跳过会留下告警的临时 `:memory:` SQLite 探测连接

## 5. 活跃任务状态

- 任务：本地 PDF 语料采集
  状态：已完成
  说明：双源采集链路已可稳定运行

- 任务：PDF parsing + parent/child chunking
  状态：已完成
  说明：已稳定产出 `parents.jsonl` / `children.jsonl`

- 任务：sparse retrieval
  状态：已完成
  说明：SQLite FTS5 检索链可用

- 任务：dense retrieval
  状态：已完成
  说明：本地 embedding + Qdrant 已可用

- 任务：retrieval output assembly
  状态：已完成
  说明：`EvidenceItem`、`RetrievalResult`、retrieval trace 已稳定

- 任务：orchestrator 消费 retrieval facade
  状态：已完成
  说明：`evidence_lookup` 已从统一入口走真实 retrieval

- 任务：structured market data 真实数据源
  状态：进行中
  说明：已完成本地财报表格 -> 内部指标库 -> 本地优先查询闭环，并预留外部 fallback

- 任务：评测样本补齐
  状态：未开始
  说明：还缺首批 query / evidence 评测集

## 6. 当前风险与卡点

- `structured-market-data-support` 已接入首版真实指标源，但仍处于有限覆盖阶段
- retrieval 评测样本仍不足，回归主要依赖单测与集成测试

## 7. 不要改什么

- 不要把 retrieval 内部中间态直接暴露给控制面以上层
- 不要在 retrieval 模块中承担 session / orchestrator 的职责
- 不要为了 UI 展示去污染 `RetrievalResult` 的边界定义

## 8. 下一次阶段检查

1. 检查结构化指标数据是否开始扩展更多公司、指标和期间类型
2. 检查 retrieval 是否补齐首批评测样本
3. 检查 evidence follow-up 是否在统一 API 路径下形成真实闭环

## 9. 完成定义

数据与证据面进入下一阶段的条件：

- retrieval 继续保持稳定可消费
- `structured-market-data-support` 已具备可持续扩展的真实指标来源体系
- 补齐首批评测样本与回归验证入口
