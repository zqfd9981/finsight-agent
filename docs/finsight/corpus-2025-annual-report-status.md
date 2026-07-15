# 2025 年报语料建设进度

> 本文档记录 2025 年度报告语料的处理状态、数据分布和存储细节。
> 更新时间：2026-07-13

## 一、总览

针对 2025 年 A 股年报，已完成 **PDF 提取 → 清洗 → 表格入 SQLite → 文本向量化入 Qdrant** 的全流程：

| 环节 | 状态 | 产物 |
|------|------|------|
| PDF 下载 | ✅ 完成 | `var/data/raw_filings/<公司>/<annual>/<2025>/<pdf>` |
| MinerU 解析 | ✅ 完成 | `var/data/parsed_filings/<doc_id>__rag/` |
| page_filter 清洗 | ✅ 完成 | LLM 标记 rag / structured 区间，剔除封面目录 |
| 切块（父子双层） | ✅ 完成 | `var/data/chunked_filings/<doc_id>__rag/{parents,children}.jsonl` |
| 表格入 SQLite | ✅ 完成 | `var/data/structured_data/metrics.db` |
| 文本向量化入 Qdrant | ✅ 完成 | `var/data/qdrant/` |
| Sparse 索引（BM25） | ✅ 完成 | `var/data/retrieval_index/sparse_chunks.db` |

**覆盖范围**：89 份 MinerU 解析的年报，88 家公司，10062 个 child chunk，parent chunk 未向量化（按需回表）。

## 二、数据范围说明

- **时间范围**：仅 2025 年报（披露日期 2025-01-01 ~ 2025-12-31）。
- **解析器**：仅 MinerU（`mineru_api_v4`）。pdfplumber 解析的 69 份年报未入向量库（质量差）。
- **已删除**：2023/2024 年的 chunks 和 parsed 文件已全部删除（pdfplumber 解析，质量不可靠）。
- **文档类型**：仅年报（annual）。半年报（67）、公告（383）未用 MinerU 切片，不入向量库。

### `__rag` 目录的来源

page_filter 用 LLM 分析 PDF 章节树，将页面标记为两类：
- `rag`：叙述性文本（管理层讨论、业务回顾、风险因素等）→ 切块入向量库
- `structured`：财务三表（资产负债表、利润表、现金流量表）→ 抽取入 SQLite

每个 `__rag` 目录是 page_filter 输出的、仅含 rag 类型页面的切片结果。

## 三、存储详情

### 1. SQLite 结构化指标（`var/data/structured_data/metrics.db`）

| 项目 | 值 |
|------|-----|
| 表名 | `metric_records` |
| 总行数 | 51625 |
| 覆盖公司 | 88 家 |
| Schema | EAV 长表，14 字段 + 自增主键 |
| period_end 分布 | `2024-12-31`（期末）、`2023-12-31`（期初）、其他对比期 |

**重要说明**：`period_end` 中的 `2024-12-31` 和 `2023-12-31` 是 **2025 年报里的对比期列**（期末/期初余额），并非独立解析 2023/2024 年报得到。所有数据均来自 2025 年报。

**字段双归一化**：`metric_label`（原始中文）+ `metric_name`（标准化英文 key），映射存于 `var/data/structured_data/metric_aliases.json`。

### 2. Qdrant 向量库（`var/data/qdrant/`）

| 项目 | 值 |
|------|-----|
| Collection | `finsight_pdf_chunks_v1` |
| Points | 10062（全部为 child chunk） |
| 向量维度 | 1024 |
| 距离度量 | Cosine |
| 模型 | `BAAI/bge-m3`（`bge-m3-v1`） |
| 入库方式 | GPU + batch_size=4 + 500 字截断，约 23 分钟 |

### 3. Chunk 文件（`var/data/chunked_filings/<doc_id>__rag/`）

| 文件 | 数量 | 是否向量化 | 用途 |
|------|------|-----------|------|
| `children.jsonl` | 10062 | ✅ 已入 Qdrant | 细粒度检索（约 400 字/chunk） |
| `parents.jsonl` | — | ❌ 未向量化 | 父级上下文回表（约 2000 字/chunk） |

### 4. Sparse 索引（`var/data/retrieval_index/sparse_chunks.db`）

- SQLite FTS5，trigram 分词，BM25 排序
- 索引了全部 72233 chunks（含非 `__rag` 目录，用于关键词检索）

## 四、父子 Chunk 设计

### 为什么 parents 不向量化？

父子双层 chunk 是 RAG 的标准实践：

- **child chunk**（细粒度，~400 字）：用于精确语义匹配，向量化入 Qdrant。
- **parent chunk**（粗粒度，~2000 字）：作为 child 的上下文容器，**不向量化**。

检索流程：
1. query → Qdrant 找 top-k child chunks
2. 通过 child 的 `parent_id` → `ParentContextLoader` 从 `parents.jsonl` 按需读取父级文本
3. 将 parent 文本作为上下文喂给 LLM

`ParentContextLoader`（[parent_context_loader.py](file:///c:/D/大模型课程/openspec测试项目/backend/src/finsight_agent/capabilities/retrieval/parent_context_loader.py)）按 `document_id` 缓存 parents，避免重复读 JSONL。

### Chunk 元数据字段

**children.jsonl** 每行字段：
```
chunk_id, document_id, chunk_level, parent_id, chunk_text,
page_start, page_end, page_anchor, section_path, element_ids,
order_in_document, source_parser, created_from_parser_version
```

**Qdrant payload**（`_normalize_chunk_row` 映射后）：
```
chunk_id, document_id, parent_id, company_code, company_name,
doc_type, report_year, publish_date, page_start, page_end,
page_anchor, section_path, chunk_text, embedding_model_version
```

`company_code`、`company_name`、`doc_type`、`report_year`、`publish_date` 通过 `_parse_document_id` 从 `document_id` 解析得到，支持 Qdrant filter 按公司/类型/年份过滤。

## 五、检索验证

入库后已验证 dense 检索正常工作：

| 查询 | Hits | Top Score | 命中公司 |
|------|------|-----------|---------|
| 平安银行营业收入 | 3 | 0.756 | 中国平安、平安银行 |
| 比亚迪新能源汽车销量 | 3 | 0.674 | 比亚迪、长城汽车 |

## 六、关键代码位置

| 功能 | 文件 |
|------|------|
| Embedding 模型加载 | [bge_m3.py](file:///c:/D/大模型课程/openspec测试项目/backend/src/finsight_agent/infra/embeddings/bge_m3.py) |
| Dense 索引构建 | [dense_index.py](file:///c:/D/大模型课程/openspec测试项目/backend/src/finsight_agent/capabilities/retrieval/dense_index.py) |
| Sparse 索引构建 | [sparse_index.py](file:///c:/D/大模型课程/openspec测试项目/backend/src/finsight_agent/capabilities/retrieval/sparse_index.py) |
| 父级上下文加载 | [parent_context_loader.py](file:///c:/D/大模型课程/openspec测试项目/backend/src/finsight_agent/capabilities/retrieval/parent_context_loader.py) |
| 检索 Facade 装配 | [service.py](file:///c:/D/大模型课程/openspec测试项目/backend/src/finsight_agent/capabilities/retrieval/service.py) |
| 全流程脚本 | [build_corpus_pipeline.py](file:///c:/D/大模型课程/openspec测试项目/scripts/build_corpus_pipeline.py) |
| 配置 | [app.yaml](file:///c:/D/大模型课程/openspec测试项目/config/app.yaml) |

## 七、已知问题与后续工作

### 已知问题

1. **半年报和公告未用 MinerU 切片**：67 份半年报和 383 份公告仍是 pdfplumber 解析，质量较低，未入向量库。

### 已修复问题（3 家公司覆盖差异）

曾存在 Qdrant/SQLite 公司覆盖差异（3 家），已全部修复：

| 公司 | 原根因 | 修复方式 | 修复结果 |
|------|--------|---------|---------|
| 600028 中国石化 | LLM 把三表标成 rag（无子章节树） | 手动拆 page_filter：从 rag p92-171 拆出 structured p98-106 | rag 235c + struct 413m |
| 601166 兴业银行 | LLM 漏标（PDF 无 outline，目录页码错乱） | 手动补 page_filter：structured p207-218 + rag p198-280 | rag 111c + struct 656m |
| 688599 天合光能 | MinerU 200 页限制导致 rag 失败 | 修复 MineruDocumentParser 支持分批解析 | rag 290c + struct 220m |

**MineruDocumentParser 分批解析**：MinerU API 限制单次 200 页（基于原始 PDF 页数，page_ranges 无效）。修改 [mineru_parser.py](file:///c:/D/大模型课程/openspec测试项目/backend/src/finsight_agent/infra/document_parsers/mineru_parser.py) 的 `parse` 方法，对 >200 页的 PDF 自动用 PyMuPDF 物理拆分成多份临时 PDF（每份 ≤200 页），分别调 API，按原始页码顺序合并 content_list。同时给 `_upload_pdf` 加了 3 次重试逻辑（10s/20s 间隔），处理 MinerU API 偶发 "operation failed" 错误。

**page_ranges 格式修复**：分批解析时 page_ranges 必须用压缩 range 格式（如 "92-200"），不能用逗号分隔的完整列表（如 "92,93,...,200"），否则 MinerU API 会报 "operation failed"。

### 后续可选工作

- 对剩余 10 家无指标公司排查 page_filter / structured 抽取失败原因
- V3 端到端查询验证（LLM + 检索 + 报告生成全链路）
- 评估是否对半年报/公告用 MinerU 重新解析
