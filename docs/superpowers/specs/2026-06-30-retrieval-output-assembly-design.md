# Retrieval Output Assembly Design

## 背景

当前本地 PDF retrieval 主链路已经具备以下能力：

- `SQLite FTS5` 稀疏检索
- 本地 `Qdrant` dense retrieval
- 保守 query rewrite
- `RRF` 融合
- child 级 rerank
- 统一 retrieval facade

现阶段 retrieval 已经能稳定返回 `EvidenceItem`，但输出层仍然偏原型态，主要有三处不足：

1. `parent_context` 仍然来自命中 child 的截断摘要，不是真实 `parent chunk` 回填。
2. `EvidenceItem` 的组装逻辑散落在 facade 中，`support_strength` 与 citation 规则仍偏隐式。
3. `retrieval_notes` 主要是给人读的字符串，缺少程序可稳定消费的结构化 trace。

本设计只聚焦 retrieval 结果收口层，不改 sparse / dense / fusion / rerank 的主检索行为。

## 目标

本轮目标是把 retrieval 从“能搜到结果”提升到“能被上游正式消费”：

- 使用真实 `parent chunk` 回填 `parent_context`
- 将 `EvidenceItem` 组装职责从 facade 中抽离
- 为 `RetrievalResult` 增加轻量结构化 `retrieval_trace`
- 保留给人快速阅读的 `retrieval_notes`
- 保持 retrieval facade 对外接口稳定

## 非目标

本轮不包含以下内容：

- 不改 sparse query rewrite 策略
- 不改 dense embedding / Qdrant schema
- 不引入新的 rerank 模型
- 不实现评测平台或 report generation
- 不改 orchestrator 调用方式

## 方案对比

### 方案一：继续扩 `service.py`

把 `parent expand`、`EvidenceItem` 组装和 trace 逻辑都继续堆在现有 retrieval facade 中。

优点：

- 改动文件数最少
- 能最快产出结果

缺点：

- `service.py` 会继续膨胀
- 逻辑边界变差，不利于测试
- 后面 orchestrator 接入时更难维护

### 方案二：新增输出层辅助模块

保留 `service.py` 作为编排入口，同时新增：

- `parent_context_loader.py`
- `evidence_assembly.py`
- `trace_builder.py`

优点：

- 边界清楚，便于测试
- facade 保持薄入口
- 后续扩 parent expand / trace 更稳

缺点：

- 文件数会增加
- 需要一次性把职责拆清楚

### 方案三：一步到位做 summary + detailed trace 双层结构

除轻量 trace 外，再同时引入详细候选级 trace。

优点：

- 评测和诊断信息最完整

缺点：

- 当前阶段过重
- 返回体和实现复杂度都会明显上升

## 推荐方案

采用 **方案二**。

原因：

- 当前 retrieval 主链路已经稳定，接下来最重要的是把结果层职责拆清楚，而不是继续在 facade 中堆实现。
- `parent_context`、`EvidenceItem`、`trace` 这三层天然是不同职责，拆开后更利于后续 orchestrator、trace 评测和结果调试。
- 方案二能在不过度增加复杂度的前提下，把 retrieval 输出层整理成正式模块。

## 总体设计

retrieval 输出层保持现有主流程不变：

1. query rewrite
2. sparse recall
3. dense recall
4. RRF fusion
5. rerank
6. parent expand
7. evidence assembly
8. trace / notes 组装

其中 1 到 5 继续沿用现有实现；本轮新增 6 到 8 的明确职责边界。

### 模块拆分

#### `service.py`

继续作为 retrieval facade 的统一入口，只负责：

- 组织 sparse / dense / fusion / rerank 调用
- 调用 parent context loader
- 调用 evidence assembly
- 调用 trace builder
- 返回统一 `RetrievalResult`

`service.py` 不再直接构造 `EvidenceItem`，也不自己拼装 trace 字段。

#### `parent_context_loader.py`

职责：

- 根据 `document_id + parent_id` 读取 `chunked_filings/<document_id>/parents.jsonl`
- 找到真实 `parent chunk`
- 返回 parent 的文本和必要元数据

特点：

- 只做本地文件加载，不参与排序
- 允许内部做文档级缓存
- 找不到 parent 时返回 `None`

#### `evidence_assembly.py`

职责：

- 接收 `RerankedHit`
- 结合真实 parent context 与 citation
- 组装 `EvidenceItem`

内部会统一处理：

- `excerpt` 清洗
- `parent_context` 回填
- `support_strength` 分类
- `retrieval_scores` 复制

#### `trace_builder.py`

职责：

- 构造结构化 `retrieval_trace`
- 生成简洁 `retrieval_notes`

trace 面向程序消费，notes 面向人快速阅读。

## 数据结构设计

### `RetrievalTrace`

为 `RetrievalResult` 新增一个轻量结构化字段：

- `original_query`
- `normalized_query`
- `rewrite_queries`
- `sparse_hit_count`
- `dense_hit_count`
- `fused_hit_count`
- `reranked_hit_count`
- `final_evidence_count`
- `sparse_rewrite_triggered`
- `dense_rewrite_triggered`
- `parent_expand_attempted`
- `parent_expand_fallback_count`

设计原则：

- 默认只返回轻量摘要
- 不返回全量候选列表
- 不把内部每轮排序明细暴露给上游

### `RetrievalResult`

保留现有字段：

- `request_id`
- `normalized_claim`
- `evidence_items`
- `retrieval_notes`

新增：

- `retrieval_trace`

这样结果层会同时具备：

- 结构化过程摘要
- 面向人类的简洁 notes

## Parent Expand 设计

### 行为定义

`parent expand` 不是新一轮召回，而是在 child 命中后：

1. 读取 child 的 `document_id`
2. 读取 child 的 `parent_id`
3. 从对应 `parents.jsonl` 找回真实 parent
4. 用 parent 的 `chunk_text` 回填 `EvidenceItem.parent_context`

### 输入来源

使用现有 chunk 产物：

- `chunked_filings/<document_id>/parents.jsonl`
- child 上已有的 `parent_id`

### 失败回退

若 parent 找不到或文件缺失：

- 使用现有 child 摘要逻辑生成 `parent_context`
- 记录一次 `parent expand fallback`

这里的 fallback 是降级，不是错误中断。retrieval 结果仍然可以正常返回。

## Evidence Assembly 设计

### `EvidenceItem` 填充规则

- `excerpt`
  - 来自命中 child chunk
  - 做轻量空白规整
- `parent_context`
  - 优先使用真实 parent chunk
  - fallback 时使用 child 摘要
- `citation`
  - 继续使用页码级 citation
- `retrieval_scores`
  - 保留 sparse / dense / rrf / rerank
- `section_path`
  - 沿用命中 child 的结构路径

### `support_strength`

继续使用四档：

- `strong`
- `partial`
- `weak`
- `unsupported`

但逻辑改成一个显式策略函数，而不是散落在 facade 中。

首版策略保持简单：

- 高 rerank 分数，且至少在 sparse 或 dense 一路表现较强：`strong`
- rerank 中等：`partial`
- 有命中但证据边缘：`weak`
- 无有效结果或分数极低：`unsupported`

这里不做复杂规则树，只把当前隐式行为转成单独函数，便于后续调参。

## Retrieval Notes 设计

`retrieval_notes` 仍然保留，但角色变轻。

它只承担“让人快速看懂”的职责，不替代结构化 trace。

首版 notes 只记录这种信息：

- 是否触发 sparse rewrite
- 是否触发 dense rewrite
- 是否发生 parent expand fallback

例如：

- `sparse rewrite triggered: 归属于上市公司股东的净利润`
- `dense rewrite triggered: 营业收入`
- `parent expand fallback used for 1 evidence item`

## 错误处理

### parent context 加载失败

- 不抛出致命错误
- 退回 child 摘要
- 在 `retrieval_trace.parent_expand_fallback_count` 中计数
- 在 `retrieval_notes` 中补一条说明

### evidence assembly 异常

如果单条证据组装异常：

- 跳过当前证据项不合适，因为会导致排序结果和 evidence 数量失真
- 首版建议只允许 parent expand fallback，不让常规 assembly 失败
- 若真的遇到无法组装的异常，应让 retrieval 调用失败并暴露错误

这符合当前阶段“结果质量优先”的原则。

## 测试策略

新增和更新的测试应覆盖：

1. `parent_context_loader`
   - 能从 `parents.jsonl` 正确命中 parent
   - 缺失 parent 时返回 `None`
2. `evidence_assembly`
   - 能优先使用真实 parent context
   - fallback 时仍能生成 `EvidenceItem`
   - `support_strength` 分类稳定
3. `trace_builder`
   - 结构化 trace 字段完整
   - notes 与 rewrite / fallback 行为一致
4. `RetrievalFacade`
   - 返回的 `RetrievalResult` 含 `retrieval_trace`
   - `parent_context` 为真实 parent，而非 child 摘要

## 兼容性

本轮保持 retrieval facade 对外方法签名不变：

- `retrieve_evidence(...) -> RetrievalResult`

变化只体现在：

- `RetrievalResult` 新增 `retrieval_trace`
- `EvidenceItem.parent_context` 更真实

这意味着上层如果只消费 `evidence_items`，不会因为本轮调整而中断。

## 实现顺序建议

1. 为 `models.py` 增加 `RetrievalTrace`
2. 新增 `parent_context_loader.py`
3. 新增 `evidence_assembly.py`
4. 新增 `trace_builder.py`
5. 收敛 `service.py` 中的组装逻辑
6. 更新 retrieval facade 相关测试

## 成功标准

完成后应满足：

- `RetrievalResult` 默认携带结构化 `retrieval_trace`
- `EvidenceItem.parent_context` 默认来自真实 parent chunk
- parent 缺失时能稳定 fallback
- `retrieval_notes` 与 trace 各司其职
- `service.py` 保持薄编排层
- 全量测试保持通过
