# FinSight Agent 本地 PDF RAG 设计

日期：2026-06-30  
状态：讨论稿，待继续细化

## 1. 目标

这份设计文档用于收敛 FinSight Agent 在 `evidence-retrieval-pipeline` 模块中的首版本地 PDF RAG 方案。

本轮设计目标不是立刻实现所有检索细节，而是先把以下问题定清：

- 首批语料范围是什么
- 本地 PDF 语料如何组织
- Parent-Child Chunking 如何落地
- Hybrid Retrieval 的主流程如何定义
- 页码级 citation 如何设计
- `EvidenceBundle` 类输出需要保留哪些信息

这份文档服务于后续 `evidence-retrieval-pipeline` 的实现计划，不改变现有主 spec 和共享 contract。

## 2. 设计范围

### 2.1 本轮只做什么

本轮 RAG 设计只覆盖：

- 本地 PDF 语料
- 年报、半年报、重要公告
- 中文金融文本检索
- Hybrid Retrieval
- Parent-Child Chunking
- 页码级 citation metadata
- 检索结果向 `EvidenceBundle` 风格输出的组装

### 2.2 本轮不做什么

本轮不包含：

- 新闻检索
- 主题 / 公司映射
- 最终报告生成
- 会话状态管理
- Planner / Orchestrator 决策逻辑
- 全市场一次性深度覆盖
- 重型财务结构化引擎

## 3. 首批语料边界

### 3.1 主题范围

首批语料围绕半导体主线建设，不追求全行业泛化覆盖。

### 3.2 公司范围

首版目标覆盖约 `50` 家样本公司。

这里的 `50` 家不是为了直接上线，而是为了：

- 验证目录规范和导入流水线
- 验证 chunk 粒度和 metadata 设计
- 验证半导体主线下的真实 query 命中表现
- 在中等规模下暴露 Hybrid Retrieval 和 rerank 的质量问题

这批样本公司应优先覆盖：

- 上游设备 / 材料
- 晶圆制造 / IDM
- 封测
- 设计
- 先进封装与算力相关链条

### 3.3 时间范围

首版采用分层时间窗，而不是全部文档统一按 `5` 年覆盖：

- 年报：最近 `5` 年
- 半年报：最近 `3` 年
- 重要公告：最近 `2` 年，必要时可扩到 `3` 年

这样设计的原因是：

- 年报用于保留公司中长期业务脉络
- 半年报用于补足近年的经营变化
- 公告用于保留时效性更强的证据，同时控制噪声和建库规模

### 3.4 公告范围

首版“重要公告”只收敛到以下三类：

- 业绩预告 / 业绩快报
- 重大合同 / 产能扩张 / 投资建设
- 并购重组 / 股权激励 / 大额减值等重大事项

这样设计的原因是：

- 更贴近半导体主线的事件驱动分析场景
- 证据价值更高
- 更容易形成可评测 query 集
- 避免公告量在首版失控

## 4. 实现路线选择

首版采用“分层双索引路线”，而不是轻量单索引路线，也不直接把所有高级增强一次做满。

### 4.1 选定方案

采用以下主流程：

- 本地 PDF 解析
- Parent-Child Chunking
- SQLite FTS5 稀疏索引
- Qdrant dense 索引
- 原始 query + 有界 rewrite
- sparse / dense 双路召回
- RRF 融合
- child chunk rerank
- parent expand
- 页码级 citation 组装

### 4.2 不选轻量单索引路线的原因

不采用“只有 SQLite FTS5 + 简单摘录”的方案，原因是：

- 不符合现有 V1 设计稿对 Hybrid Retrieval 的要求
- 后续接 Qdrant 时容易推翻索引结构和结果组装方式
- 不足以验证 parent-child 和 citation 设计

### 4.3 不直接做满高级增强的原因

不把 HyDE / Query2Doc / 高级质量判别作为默认主链路，原因是：

- 首版更需要稳定基线，而不是最大化增强复杂度
- 高级增强更适合作为“条件触发路径”
- 先把 Hybrid Retrieval 的主干链路做稳，后续调优会更清晰

## 5. 模块职责拆分

建议在 `backend/src/finsight_agent/capabilities/retrieval/` 下按职责拆成 5 个子层。

### 5.1 ingest

负责：

- 本地 PDF 发现
- 文档清单登记
- 文档元数据标准化
- 解析结果持久化

输入：

- 本地 PDF 文件

输出：

- 标准化文档记录
- PDF 解析结果

### 5.2 chunking

负责：

- parent 生成
- child 生成
- parent-child 关系登记
- 页码、标题、文档类型等 metadata 写入

输入：

- 解析后的结构块

输出：

- parent records
- child records
- chunk 级 metadata

### 5.3 indexing

负责：

- SQLite FTS5 稀疏索引构建
- Qdrant dense 索引构建
- chunk metadata 与索引键的一致性管理

输入：

- child records
- 必要的 metadata

输出：

- sparse index
- dense index

### 5.4 retrieval

负责查询主流程：

- 原始 query
- query rewrite
- sparse recall
- dense recall
- RRF fusion
- child rerank
- parent expand

输入：

- claim / target / retrieval hints

输出：

- 排序后的 evidence candidates
- support strength signals

### 5.5 assembly

负责：

- 证据去重与收束
- citation metadata 组装
- parent context 回填
- `EvidenceBundle` 风格输出

输入：

- rerank 后的 top child
- expand 后的 parent context

输出：

- evidence bundle
- retrieval notes

## 6. 本地 PDF 数据组织

### 6.1 目录原则

目录组织必须同时满足：

- 人能直接看懂
- 能稳定批量导入
- 后续可扩展到更多公司和年份

建议语料目录按以下维度组织：

- 公司
- 文档类型
- 年份

建议目录形态示意：

```text
var/data/raw_filings/
  <company_code>_<company_name>/
    annual/
      2021/
      2022/
      2023/
      2024/
      2025/
    semiannual/
      2023/
      2024/
      2025/
    announcements/
      2024/
      2025/
```

这里不强制文件名完全统一，但要求导入阶段能抽取出稳定元数据。

### 6.2 文档元数据

每份 PDF 至少应具备以下字段：

- document_id
- company_code
- company_name
- doc_type
- report_year
- report_period
- publish_date
- source_path
- title
- language

其中：

- `doc_type` 建议至少区分：
  - annual_report
  - semiannual_report
  - major_announcement
- `report_period` 用于区分年报、半年报和特殊公告场景

建议补充以下辅助字段，以支撑后续过滤、评测和语料治理：

- announcement_type
- industry_theme
- is_sample_corpus
- ingest_batch_id
- checksum
- parser_version
- parse_status
- page_count

其中：

- `announcement_type` 仅对 `major_announcement` 生效，用于区分首版限定的三类公告
- `industry_theme` 首版可以先固定为半导体相关标签，后续扩展到多主题
- `is_sample_corpus` 用于标记是否属于首批 `50` 家样本股语料
- `ingest_batch_id` 用于追踪一次批量导入任务，方便重跑和审计
- `checksum` 用于发现重复文件和脏数据
- `parser_version` 用于标记文档是由哪个解析版本生成
- `parse_status` 用于记录是否解析成功、部分成功或失败
- `page_count` 用于 citation 质量检查和页码边界校验

### 6.3 `document_record` 模型

建议将每份 PDF 登记为一条 `document_record`，作为后续 chunk、索引、citation 的上游主记录。

推荐字段如下：

```json
{
  "document_id": "688981_annual_report_2024_20250329",
  "company_code": "688981",
  "company_name": "中芯国际",
  "doc_type": "annual_report",
  "announcement_type": null,
  "report_year": 2024,
  "report_period": "FY",
  "publish_date": "2025-03-29",
  "title": "中芯国际 2024 年年度报告",
  "language": "zh-CN",
  "industry_theme": ["semiconductor"],
  "is_sample_corpus": true,
  "source_path": "var/data/raw_filings/688981_中芯国际/annual/2024/688981_中芯国际_annual_report_2024_20250329.pdf",
  "checksum": "sha256:...",
  "page_count": 312,
  "ingest_batch_id": "ingest_20260630_01",
  "parser_version": "mineru_pdfplumber_v1",
  "parse_status": "parsed"
}
```

字段约束建议如下：

- `document_id` 为全局唯一主键
- `doc_type` 枚举值固定为 `annual_report`、`semiannual_report`、`major_announcement`
- `announcement_type` 仅在 `doc_type=major_announcement` 时填写，其他情况为 `null`
- `report_year` 表示文档归属年份，不等于发布日期年份时仍按业务归属填写
- `report_period` 首版建议使用 `FY`、`H1`，公告可使用 `ANNOUNCEMENT`
- `source_path` 必须指向原始 PDF，而不是解析产物
- `parse_status` 首版建议至少支持 `parsed`、`partial`、`failed`

### 6.4 文档唯一标识

建议 `document_id` 采用稳定可读格式，例如：

```text
<company_code>_<doc_type>_<report_year>_<publish_date>
```

这样做的目的是：

- 便于调试
- 便于 trace 回看
- 便于后续索引重建和去重

如果遇到同一公司、同一文档类型、同一归属年份下存在多份补充版本，建议在导入层补一个有界后缀，而不是直接改写已有 `document_id` 规则，例如：

```text
<company_code>_<doc_type>_<report_year>_<publish_date>_v2
```

这样可以保留主键可读性，同时避免覆盖旧版本记录。

### 6.5 `chunk_record` 模型

建议将 parent 和 child 统一抽象为 `chunk_record`，通过 `chunk_level` 区分层级，而不是拆成两套完全不同的表结构。这样索引、检索和 citation 组装时更容易共用字段。

推荐字段如下：

```json
{
  "chunk_id": "688981_annual_report_2024_20250329_parent_000123",
  "document_id": "688981_annual_report_2024_20250329",
  "chunk_level": "parent",
  "parent_id": null,
  "company_code": "688981",
  "doc_type": "annual_report",
  "report_year": 2024,
  "section_path": ["第三节", "管理层讨论与分析", "主营业务分析"],
  "page_start": 87,
  "page_end": 89,
  "page_anchor": 88,
  "char_count": 1420,
  "token_estimate": 970,
  "content_text": "...",
  "content_hash": "sha256:...",
  "table_presence": true,
  "created_from_parser_version": "mineru_pdfplumber_v1"
}
```

对应 child 记录建议如下：

```json
{
  "chunk_id": "688981_annual_report_2024_20250329_child_000123_02",
  "document_id": "688981_annual_report_2024_20250329",
  "chunk_level": "child",
  "parent_id": "688981_annual_report_2024_20250329_parent_000123",
  "company_code": "688981",
  "doc_type": "annual_report",
  "report_year": 2024,
  "section_path": ["第三节", "管理层讨论与分析", "主营业务分析"],
  "page_start": 88,
  "page_end": 88,
  "page_anchor": 88,
  "char_count": 356,
  "token_estimate": 248,
  "content_text": "...",
  "content_hash": "sha256:...",
  "table_presence": false,
  "created_from_parser_version": "mineru_pdfplumber_v1"
}
```

字段含义建议如下：

- `chunk_level` 只允许 `parent` 或 `child`
- `parent_id` 在 parent 记录中为 `null`，在 child 记录中必须指向所属 parent
- `section_path` 用于保留章节语义路径，便于 rerank 和 citation 展示
- `page_start` / `page_end` 用于覆盖跨页文本块
- `page_anchor` 用于最终页码级 citation 展示，首版可取主命中页或起始页
- `content_hash` 用于 chunk 去重和索引一致性校验
- `table_presence` 用于标记该 chunk 是否包含表格或表格邻接解释

### 6.6 `chunk_id` 规则

建议 `chunk_id` 在 `document_id` 基础上派生，保持可读且稳定：

```text
<document_id>_parent_<parent_seq>
<document_id>_child_<parent_seq>_<child_seq>
```

例如：

```text
688981_annual_report_2024_20250329_parent_000123
688981_annual_report_2024_20250329_child_000123_02
```

这样做的好处是：

- 人工排查时能快速看出 chunk 归属
- parent expand 不需要额外复杂映射
- retrieval trace 和 citation 可以直接回溯到文档主记录

## 7. PDF 解析与 Parent-Child Chunking

### 7.1 解析目标

解析层的目标不是完美还原 PDF 版面，而是为了后续检索和 citation 提供稳定的结构基础。

首版建议采用“结构化解析优先”的路线：

- 主解析器：`MinerU`
- fallback：`pdfplumber`

这里的重点不是自己重造 PDF parser，而是：

- 由第三方 parser 负责把 PDF 解析成原始结构结果
- 由项目内部的 normalizer 负责把不同 parser 的输出统一成同一种中间产物
- 由后续 chunking 层负责唯一一次真正的检索切分

也就是说，首版不会设计两套复杂切分系统：

- 解析层只产出结构化元素
- chunking 层才负责 parent / child 的生成

### 7.2 解析层架构

首版建议按以下 3 层实现：

1. `raw parser`
   - `MinerU` 作为主解析器
   - `pdfplumber` 作为整份文档级 fallback
2. `normalizer`
   - 这是项目内部实现的标准化适配层
   - 负责把 `MinerU / pdfplumber` 的输出映射成统一 schema
3. `chunking`
   - 消费标准化后的结构元素
   - 生成最终索引使用的 parent / child chunks

对外建议暴露统一解析接口，而不是直接把第三方 parser 暴露给下游：

```python
class ParsedDocument:
    document: dict[str, object]
    elements: list[dict[str, object]]
    tables: list[dict[str, object]]
    parse_report: dict[str, object]


class DocumentParser:
    def parse(self, pdf_path: Path) -> ParsedDocument:
        ...
```

在实现层可分别对应：

- `MineruDocumentParser`
- `FallbackDocumentParser`
- `ParsingService`

### 7.3 解析产物落盘方式

首版不建议把所有解析结果塞进一个大 JSON，而建议“每个 PDF 一个目录，按职责拆文件”：

```text
var/data/parsed_filings/
  <document_id>/
    document.json
    elements.jsonl
    tables.jsonl
    parse_report.json
```

这样做的原因是：

- 方便人工排查单份文档
- 方便 chunking 流式消费 `elements.jsonl`
- 方便单独重跑表格提取或只查看解析报告
- 便于后续把不同产物分别导入 SQLite / Qdrant / 评测流程

### 7.4 `document.json`

`document.json` 只承载文档级元数据，不承载大量正文内容。

建议字段至少包含：

- `document_id`
- `company_code`
- `company_name`
- `doc_type`
- `report_year`
- `report_period`
- `publish_date`
- `title`
- `source_path`
- `page_count`
- `language`
- `industry_theme`
- `parser_name`
- `parser_version`
- `fallback_used`
- `parse_status`

其中：

- `document_id` 仍由项目内部规则生成，不依赖 parser 原始主键
- `source_path` 必须指向 `raw_filings` 下的原始 PDF
- `fallback_used` 用于标记该文档是否整份退回到 fallback parser

### 7.5 `elements.jsonl`

`elements.jsonl` 是解析层最核心的中间产物。这里的 `element` 是“结构元素”，不是最终 retrieval chunk。

建议每行一个 element，并且只保留结构化消费真正需要的字段：

- `element_id`
- `document_id`
- `element_type`
- `page_start`
- `page_end`
- `order_in_document`
- `section_path`
- `text`
- `parser_source`
- `confidence`
- `bbox`
- `related_table_id`

首版 `element_type` 建议限制为：

- `title`
- `paragraph`
- `list_item`
- `table_caption`
- `figure_caption`
- `page_header`
- `page_footer`

其中：

- `page_header` / `page_footer` 可以保留在解析产物里，但默认不进入 chunking 主链路
- `text` 应该已经完成视觉换行合并，不保留 PDF 原始碎行
- `section_path` 能给则给，fallback 场景允许为空或较浅

### 7.6 `tables.jsonl`

`tables.jsonl` 是表格专用产物，不与普通文本 element 混存。

建议每行一张表，字段至少包含：

- `table_id`
- `document_id`
- `page_start`
- `page_end`
- `order_in_document`
- `section_path`
- `caption_text`
- `table_text`
- `table_markdown`
- `parser_source`
- `confidence`
- `bbox`
- `table_type_hint`
- `related_metric_hints`

其中：

- `table_text` 用于后续检索或抽取的纯文本展开版
- `table_markdown` 用于保留更可读的结构表达
- `table_type_hint` 首版可做弱分类，例如：
  - `financial_statement`
  - `segment_breakdown`
  - `capacity_plan`
  - `shareholding_change`
- `related_metric_hints` 首版允许为空，但预留未来结构化指标抽取扩展点

这里的设计原则是：

- 首版 table 首先是“证据资产”
- 未来可进一步演进成“结构化数据资产”

### 7.7 `parse_report.json`

`parse_report.json` 用于记录解析过程和质量信息，不直接参与检索。

建议字段至少包含：

- `document_id`
- `status`
- `primary_parser`
- `parser_version`
- `fallback_used`
- `fallback_parser`
- `page_count`
- `parsed_element_count`
- `parsed_table_count`
- `warnings`
- `duration_ms`

建议 `warnings` 记录这类信息：

- `fallback_parser_used`
- `section_path_missing_page_12`
- `low_confidence_table_page_47`
- `header_footer_filter_uncertain_page_3`

### 7.8 Normalizer 职责

首版 normalizer 只做以下最小职责，不承担检索切分职责：

- 统一 element 类型枚举
- 合并视觉换行
- 清理明显空白字符噪声
- 维护 `order_in_document`
- 维护 `section_path`
- 关联 `table_caption` 和 `table`
- 过滤明显页眉页脚
- 生成 4 份标准解析产物

不建议放在 normalizer 的内容包括：

- parent / child chunk 生成
- 按检索窗口长度切分文本
- query aware 处理
- rerank 或 retrieval 相关字段

### 7.9 `section_path` 维护规则

`section_path` 是后续 parent 生成的关键结构字段。

建议规则如下：

- 如果 `MinerU` 能识别标题层级，则维护一个“当前标题栈”
- 正文 element 继承最近稳定的标题栈作为 `section_path`
- 遇到新的同级或更高层标题时，更新标题栈
- 如果当前页没有可靠标题层级，可沿用最近稳定路径
- fallback 场景下允许 `section_path` 为空或只有一层

例如：

```json
["管理层讨论与分析", "主营业务分析"]
```

### 7.10 Fallback 策略

首版 fallback 明确采用“整份文档级 fallback”，不做复杂按页 fallback。

执行规则如下：

- `MinerU` 成功：整份文档使用 `MinerU`
- `MinerU` 失败：整份文档退回 `pdfplumber`
- `pdfplumber` 也失败：
  - 仍写出最小 `document.json`
  - `parse_report.json` 标记为 `failed`
  - 不产出 `elements.jsonl / tables.jsonl`
  - 该文档不进入 chunking

fallback 只要求最小能力：

- 按页提取文本
- 合并明显视觉换行
- 启发式识别少量 `title / paragraph / table_caption`
- 不强求完整 `section_path`
- `tables.jsonl` 可为空

### 7.11 Parent 定义
Parent 是“受控大小的完整语义单元”，不是整章。

首版生成规则建议是：

- 忽略 `page_header` / `page_footer`
- 按 `order_in_document` 顺序扫描
- 同一 `section_path` 下的连续元素优先归到同一个 parent
- 遇到新的同级或更高层标题时结束当前 parent
- 若同一 section 太长，再按段落边界做软拆分

Parent 不是按固定字数硬切，但需要长度约束辅助。首版建议：

- 目标长度：`1500 - 3000` 中文字符
- 硬上限：`4000` 中文字符左右

超过阈值时，优先在以下边界拆分：

- 子标题边界
- 段落边界
- 列表边界

### 7.12 Child 定义

Child 是主要召回与 rerank 单元。

建议在每个 parent 内继续按 element 顺序生成 child：

- 以 `paragraph / list_item / table_caption / figure_caption` 为主拼接单元
- `title` 不单独作为 child，但可以作为 chunk 的上下文前缀
- 不按页切
- 不按视觉换行切
- 只在语义边界和长度边界切

首版 child 阈值建议：

- 目标长度：`300 - 700` 中文字符
- 硬上限：`900` 中文字符

同时建议：

- 过短的相邻 element 允许合并
- overlap 不做字符级滑窗，而采用轻量 element 级上下文继承

这一套规则可以概括为：

- 结构优先
- 长度约束辅助
- 不是固定长度硬切

### 7.13 Table 在 Chunking 中的角色

首版 table 的处理建议如下：

- `table` 本体单独保存在 `tables.jsonl`
- 不直接把整张表混入普通 `child chunk`
- `table_caption` 和表后解释文字允许进入 child
- 通过 `related_table_id / table_id` 与表格本体关联

这样做的原因是：

- 大表格直接混入普通 text chunk 容易稀释语义
- 首版先把文本检索链路做稳
- 同时保留表格证据和未来结构化指标抽取的可能

也就是说：

- 首版 table 不属于普通 text retrieval 主链路
- 但不是“解析出来不用”
- 而是“先结构化保存、先挂好关联、后续再扩 table-aware retrieval 或结构化指标链路”

### 7.14 Chunk 元数据

每个 parent / child 至少应具备：

- chunk_id
- document_id
- company_code
- company_name
- doc_type
- report_year
- publish_date
- page_start
- page_end
- page_anchor
- section_path
- content_text
- parent_id

其中页码字段是首版 citation 的关键基础。

另外建议补充：

- `element_ids`
- `source_parser`
- `created_from_parser_version`

这样后续可以稳定追踪：

- 这个 chunk 由哪些结构元素组合而来
- 它来自哪一个解析器
- 它使用了哪一版 chunking / parser 产物

### 7.15 Chunk 产物落盘方式

建议与解析产物分开，按“每个文档一个目录”的方式落到 `chunked_filings/` 下：

```text
var/data/chunked_filings/
  <document_id>/
    parents.jsonl
    children.jsonl
    chunk_report.json
```

其中：

- `parents.jsonl`
  - 一行一个 parent chunk
- `children.jsonl`
  - 一行一个 child chunk
- `chunk_report.json`
  - 记录 chunker 版本、阈值、parent / child 数量、是否出现超长 section 等信息

### 7.16 重跑与幂等策略

首版建议：

- 以 `document_id` 作为解析与 chunk 的主键
- 同一个 `document_id` 重跑时直接覆盖该目录下的解析产物和 chunk 产物
- `parse_report.json / chunk_report.json` 里记录：
  - `parser_version`
  - `chunker_version`
  - `fallback_used`
  - `generated_at`

首版不建议保留同一文档的多版本目录，而是采用“覆盖 + 版本记录”的简单策略。

### 7.17 首版验收口径

首版 parsing + chunking 的完成标准建议是：

- 能稳定消费当前已下载的本地 PDF 语料
- 每份 PDF 至少能稳定产出：
  - `document.json`
  - `elements.jsonl`
  - `parse_report.json`
- 大部分文档能产出 `tables.jsonl`
- chunking 能稳定产出：
  - `parents.jsonl`
  - `children.jsonl`
  - `chunk_report.json`
- `parent / child` 的页码、`section_path`、`element_ids` 可追溯
- 至少对试点公司的真实 PDF 做人工 spot check：
  - 标题路径是否合理
  - child 是否没有明显过碎或过粗
  - citation 页码是否基本对得上

## 8. 索引与检索流程

### 8.1 Sparse Retrieval

稀疏检索采用 SQLite FTS5。

理由：

- 与项目现有 SQLite 技术栈一致
- 本地单机可复现
- 足够支撑首版金融文本关键词检索

### 8.2 Dense Retrieval

dense retrieval 采用 Qdrant。

embedding 模型沿用总设计稿建议：

- BGE-M3

### 8.2.1 SQLite FTS5 落盘建议

首版建议将 sparse index 建在本地 SQLite 中，并围绕 child chunk 建主索引表。原因是 child 是主召回与 rerank 单元，sparse 先对 child 做命中最直接。

建议最小表结构包含：

- `documents`
- `chunks`
- `chunk_fts`

推荐形态如下：

```sql
CREATE TABLE documents (
  document_id TEXT PRIMARY KEY,
  company_code TEXT NOT NULL,
  company_name TEXT NOT NULL,
  doc_type TEXT NOT NULL,
  announcement_type TEXT,
  report_year INTEGER NOT NULL,
  report_period TEXT,
  publish_date TEXT NOT NULL,
  title TEXT NOT NULL,
  source_path TEXT NOT NULL,
  checksum TEXT,
  page_count INTEGER,
  parse_status TEXT NOT NULL
);

CREATE TABLE chunks (
  chunk_id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL,
  chunk_level TEXT NOT NULL,
  parent_id TEXT,
  company_code TEXT NOT NULL,
  doc_type TEXT NOT NULL,
  report_year INTEGER NOT NULL,
  page_start INTEGER NOT NULL,
  page_end INTEGER NOT NULL,
  page_anchor INTEGER NOT NULL,
  section_path TEXT,
  content_text TEXT NOT NULL,
  content_hash TEXT,
  table_presence INTEGER NOT NULL DEFAULT 0
);

CREATE VIRTUAL TABLE chunk_fts USING fts5(
  chunk_id UNINDEXED,
  company_code,
  company_name,
  title,
  section_path,
  content_text,
  tokenize = 'unicode61'
);
```

设计约束建议如下：

- `documents` 负责存放 document 级主记录，不直接参与全文召回
- `chunks` 存放 parent / child 的结构化元数据，但 FTS 主链路优先只索引 child
- `chunk_fts` 与 `chunks` 通过 `chunk_id` 关联
- `section_path` 可序列化为字符串写入 SQLite，便于首版工程落地
- `company_name` 与 `title` 一并进入 FTS，便于公告类 query 提升命中

### 8.2.2 Qdrant Collection 建议

首版 dense index 建议同样以 child chunk 为主索引粒度，parent 不直接作为默认 dense 检索对象。

建议 collection payload 至少包含：

- `chunk_id`
- `document_id`
- `parent_id`
- `chunk_level`
- `company_code`
- `company_name`
- `doc_type`
- `announcement_type`
- `report_year`
- `publish_date`
- `page_start`
- `page_end`
- `page_anchor`
- `section_path`
- `table_presence`

向量内容默认来自 `content_text`，并保留与 SQLite 一致的主键字段，以便 sparse / dense 结果在 RRF 前直接对齐。

Qdrant 层建议遵循以下原则：

- 首版只维护一个主 collection，用 payload 过滤公司、年份和文档类型
- 不在首版拆多 collection，避免增加导入与查询复杂度
- embedding 重建必须可重放，因此需要保留 `embedding_model_version`
- 如果后续要接多向量或 query-specific 向量，应作为第二阶段增强，而不是首版默认项

### 8.3 Query 输入

检索入口建议接受以下结构：

- raw_query
- claim
- target_company or target_topic
- retrieval_hints

这里不把所有执行上下文塞进 retrieval 模块，而是只接收检索真正需要的最小字段。

建议将检索请求统一抽象为 `RetrievalRequest`：

```json
{
  "request_id": "retrieval_20260630_0001",
  "raw_query": "中芯国际这两年有没有明显扩产计划？",
  "claim": "查询中芯国际近两年与扩产、资本开支或产能建设相关的证据",
  "target_company_codes": ["688981"],
  "target_company_names": ["中芯国际"],
  "target_topic": "semiconductor_capacity_expansion",
  "doc_type_filters": ["annual_report", "semiannual_report", "major_announcement"],
  "announcement_type_filters": ["major_contract_or_capacity_expansion_or_investment_construction"],
  "report_year_range": [2023, 2025],
  "top_k": 12,
  "retrieval_hints": {
    "prefer_recent_documents": true,
    "prefer_announcements": true,
    "allow_query_rewrite": true,
    "allow_hyde": false,
    "must_keep_original_query": true
  }
}
```

字段语义建议如下：

- `request_id` 用于 trace 关联和评测样本登记
- `raw_query` 保留用户原始表达，不做规范化覆盖
- `claim` 是更适合检索的任务化表述，可由上游 planner 或 orchestrator 生成
- `target_company_codes` 和 `target_company_names` 可同时存在，检索时优先以代码过滤
- `target_topic` 用于补足半导体主线下的术语召回，不替代公司过滤
- `doc_type_filters` 和 `announcement_type_filters` 是硬过滤条件，不属于软提示
- `report_year_range` 用于和首版语料窗口做交集过滤
- `top_k` 是最终 evidence item 上限，而不是单路召回上限
- `retrieval_hints` 只表达检索偏好，不承载业务决策

为了保持模块边界清晰，`RetrievalRequest` 首版不接收以下内容：

- 整个 `SessionContext`
- 上游完整 `Plan`
- 最终回答风格要求
- 多轮工具执行历史

### 8.4 Query Rewrite

默认启用轻量 rewrite，但必须保留原始 query。

首版要求：

- 原始 query 必须参与检索
- rewrite query 数量必须有上限
- rewrite 主要服务于口语化 claim、公告术语映射和半导体产业术语补全

### 8.5 HyDE / Query2Doc

HyDE / Query2Doc 在首版中不作为默认主链路，只作为条件触发增强。

可触发条件包括：

- query 很短且指代强
- 初始召回明显偏弱
- follow-up 场景省略严重
- claim 口语化严重且缺少检索术语

### 8.6 Fusion

sparse 与 dense 结果通过 RRF 融合。

首版不采用复杂加权融合作为默认主方案。

### 8.7 Rerank

Rerank 放在 RRF 之后，并且只针对 child chunks 做精排。

推荐模型：

- bge-reranker

这样做的目标是：

- 在统一候选池上做更可靠排序
- 保留 child 级细粒度相关性
- 把 parent expand 留到排序之后

### 8.8 Parent Expand

对 top child 做 parent expand 时：

- 只回填对应 parent
- 对重复 parent 去重
- 控制最终 parent 数量

首版不允许“命中 child 后回填整章”。

### 8.9 检索阶段输出

为了让 retrieval 各子层边界稳定，建议在内部明确几种中间结果对象：

- `SparseHit`
- `DenseHit`
- `FusedHit`
- `RerankedHit`
- `ExpandedEvidence`

最小字段建议如下：

- `SparseHit` / `DenseHit`
  - `chunk_id`
  - `document_id`
  - `parent_id`
  - `raw_score`
- `FusedHit`
  - `chunk_id`
  - `document_id`
  - `parent_id`
  - `rrf_score`
  - `sparse_rank`
  - `dense_rank`
- `RerankedHit`
  - `chunk_id`
  - `document_id`
  - `parent_id`
  - `rerank_score`
  - `rrf_score`
- `ExpandedEvidence`
  - `chunk_id`
  - `parent_id`
  - `excerpt`
  - `parent_context`
  - `citation_payload`

这样做的目的不是把所有中间对象都暴露到共享 contract，而是避免在一个函数里同时揉 sparse / dense / rerank / expand 的不同字段。

## 9. Citation 与 Evidence 输出

### 9.1 首版引用粒度

首版采用页码级引用。

每条引用至少应包含：

- document_id
- company_name
- doc_type
- title
- page_anchor 或 page_start/page_end
- excerpt
- parent_id
- child_id

### 9.2 选择页码级而不是 chunk 级的原因

页码级引用在首版是性价比最高的平衡点：

- 比纯 chunk_id 更适合人读和 trace 展示
- 比段落坐标级实现成本低
- 便于和 PDF 原文回查对齐

### 9.3 Support Strength

首版 retrieval 输出必须保留支撑强度。

建议最小分级为：

- strong
- partial
- weak
- unsupported

其中：

- `partial` 表示证据能支撑部分结论，但不足以支撑完整 claim
- `weak` 表示存在相关线索，但证据链薄弱

### 9.4 EvidenceBundle 风格输出

虽然当前共享 contract 已冻结，但 retrieval 内部输出应提前围绕以下内容组织：

- evidence items
- citation metadata
- parent context
- support strength
- retrieval notes

这样后续接 `EvidenceBundle` 时不会推翻内部结构。

建议将 retrieval 返回统一抽象为 `RetrievalResult`：

```json
{
  "request_id": "retrieval_20260630_0001",
  "normalized_claim": "查询中芯国际近两年与扩产、资本开支或产能建设相关的证据",
  "evidence_items": [
    {
      "evidence_id": "ev_0001",
      "rank": 1,
      "support_strength": "strong",
      "matched_chunk_id": "688981_major_announcement_2024_20240418_child_000021_01",
      "matched_parent_id": "688981_major_announcement_2024_20240418_parent_000021",
      "excerpt": "公司拟投资建设12英寸晶圆产线扩产项目……",
      "parent_context": "该公告说明了项目背景、投资金额与建设周期……",
      "citation": {
        "document_id": "688981_major_announcement_2024_20240418",
        "company_code": "688981",
        "company_name": "中芯国际",
        "doc_type": "major_announcement",
        "title": "关于投资建设产线项目的公告",
        "page_anchor": 3,
        "page_start": 3,
        "page_end": 4
      },
      "retrieval_scores": {
        "sparse_score": 18.2,
        "dense_score": 0.81,
        "rerank_score": 0.93,
        "rrf_score": 0.041
      }
    }
  ],
  "retrieval_notes": {
    "used_original_query": true,
    "rewrite_queries": ["中芯国际 扩产 产能建设 资本开支 公告"],
    "hyde_used": false,
    "candidate_counts": {
      "sparse": 40,
      "dense": 40,
      "fused": 26,
      "reranked": 12
    }
  }
}
```

输出约束建议如下：

- `request_id` 必须原样回传，便于上游聚合 trace
- `normalized_claim` 用于记录实际检索时使用的主任务表述
- `evidence_items` 必须按最终使用顺序排序
- `evidence_items` 中每一项都必须同时携带 `matched_chunk_id` 和 `matched_parent_id`
- `excerpt` 是 child 级命中文本，`parent_context` 是 parent expand 后的可读上下文
- `citation` 必须足以让上游在不重新查索引的情况下展示页码级来源
- `retrieval_scores` 首版可保留为内部调试字段，对外暴露时可裁剪
- `retrieval_notes` 用于解释本次检索是否使用 rewrite / HyDE 以及候选收缩过程

### 9.5 `support_strength` 语义

为了避免上游把 `support_strength` 当成模糊标签使用，首版建议明确语义边界：

- `strong`
  证据直接陈述 claim 的核心事实，且页码与上下文一致
- `partial`
  证据支持 claim 的一部分，但仍缺少关键限定条件、时间范围或主体信息
- `weak`
  证据只有相关线索，不能单独支撑主要结论
- `unsupported`
  候选与 claim 基本无关，或只能作为失败诊断保留，不应进入默认 top results

### 9.6 Citation 组装约束

页码级 citation 首版建议满足以下约束：

- 每个 evidence item 必须指向唯一 `document_id`
- `page_anchor` 必须落在 `page_start` 与 `page_end` 范围内
- `excerpt` 默认来自命中的 child，而不是整段 parent
- 如果 child 跨页，citation 展示优先显示 `page_start-page_end`
- 同一 parent 下多个 child 同时命中时，允许在 assembly 层做有限合并，但不能丢失原始 child 命中信息

## 10. 模块目录与服务边界

结合当前仓库已有骨架，建议 `backend/src/finsight_agent/capabilities/retrieval/` 维持一个薄 service 入口，其余逻辑按职责拆开，而不是继续堆在单一 `service.py`。

建议目录如下：

```text
backend/src/finsight_agent/capabilities/retrieval/
  service.py
  models.py
  query_rewrite.py
  rerank.py
  citation_builder.py
  ingest.py
  chunking.py
  sparse_index.py
  dense_index.py
  fusion.py
  prompts/
    .gitkeep
```

各文件职责建议如下：

- `service.py`
  对外统一入口，接收 `RetrievalRequest`，串起 rewrite、recall、fusion、rerank、expand、citation
- `models.py`
  放 `RetrievalRequest`、`RetrievalResult`、中间命中对象、citation 对象等内部模型
- `query_rewrite.py`
  负责 query rewrite 与条件 HyDE 触发策略
- `rerank.py`
  负责 child 级 rerank 调用与阈值控制
- `citation_builder.py`
  负责 evidence item 与页码级 citation 组装
- `ingest.py`
  负责本地 PDF 扫描、文档登记、checksum 计算、导入批次记录
- `chunking.py`
  负责 parent-child chunk 生成与 chunk metadata 产出
- `sparse_index.py`
  负责 SQLite 建表、写入、查询
- `dense_index.py`
  负责 Qdrant collection 建立、向量写入、payload 检索
- `fusion.py`
  负责 sparse / dense 结果的 RRF 融合与去重

### 10.1 `service.py` 入口建议

`service.py` 首版应尽量保持薄，只承担以下职责：

- 参数校验
- 调用 query rewrite
- 调用 sparse / dense recall
- 调用 fusion
- 调用 rerank
- 调用 parent expand
- 调用 citation builder
- 返回 `RetrievalResult`

不建议放进 `service.py` 的内容包括：

- SQLite SQL 细节
- Qdrant payload 构造细节
- chunking 规则实现
- support strength 的最终阈值硬编码

### 10.2 索引构建与查询接口建议

为了避免索引构建和在线查询耦合过紧，建议首版至少区分两类接口：

- 离线接口
  - `ingest_documents(...)`
  - `parse_documents(...)`
  - `build_chunks(...)`
  - `build_sparse_index(...)`
  - `build_dense_index(...)`
- 在线接口
  - `retrieve_evidence(request: RetrievalRequest) -> RetrievalResult`

这样后续 orchestrator 接 retrieval 时，只依赖一个在线接口，而不必感知 PDF 导入和索引重建过程。

## 11. 质量与评测

首版评测应聚焦检索与引用质量，而不是一开始就评价完整报告生成。

优先评测维度：

- 是否召回了正确公司材料
- 是否召回了正确页码附近的证据
- rerank 后 top 结果是否真正支撑 claim
- parent expand 后上下文是否可读
- support strength 标注是否合理

首批 query 集建议围绕半导体主线构建，并优先覆盖：

- 业绩变化解释
- 产能扩张 / 资本开支
- 大客户 / 大订单 / 合同
- 并购重组 / 激励 / 减值

## 12. 风险与控制

### 12.1 语料规模风险

`50` 家公司加分层时间窗后，PDF 数量已经不小。

控制方式：

- 先设计完整目录和 schema
- 再分批导入公司
- 先压通端到端样本，再放量

### 12.2 解析质量风险

PDF 结构质量不稳定，特别是表格、目录、页眉页脚和公告格式差异。

控制方式：

- Parent 以“受控语义单元”为目标，而不是强依赖章节树
- 保留整份文档级 parser fallback 策略

### 12.3 检索漂移风险

如果一开始把增强策略做太重，容易把问题藏进复杂流程里。

控制方式：

- 原始 query 必须保留
- HyDE / Query2Doc 只做条件触发
- 先用 RRF + child rerank 作为稳定基线

## 13. 后续需要继续明确的问题

- FTS5 中文检索增强是否需要额外分词支持
- Qdrant collection schema 和 metadata filter 细节
- retrieval service 的输入输出 Python 接口
- `EvidenceBundle` 内部字段与页码级 citation 的最终映射

## 14. 样本股 Manifest 与 SQLite 映射设计

为了兼顾“可 review 的 source of truth”和“可查询的工作库”，首版建议：

- `yaml manifest` 作为样本股池的主来源
- `SQLite` 作为导入、筛选、覆盖率统计和后续 ingestion 的工作库

这样做的原因是：

- `yaml` 更适合人工 review 和 git diff
- `SQLite` 更适合按 segment、priority、theme tag 和覆盖状态做查询
- 后续如果样本股池扩到不止半导体，也不需要推翻现有结构

### 14.1 不推荐的方案

首版不推荐把样本股池只存成单表字符串堆叠，例如：

- 把 `theme_tags` 直接拼成逗号字符串后只放一列
- 不区分 manifest 元信息和 company 明细
- 不保留导入来源路径与更新时间

这种方案虽然快，但后续一旦要做：

- 多个 manifest 并存
- 按 tag 过滤
- 按批次同步
- 样本池版本比较

就会很快变得难维护。

### 14.2 推荐表结构

首版建议至少拆成 4 张表：

- `corpus_manifests`
- `corpus_manifest_segment_targets`
- `corpus_manifest_companies`
- `corpus_manifest_company_tags`

如果后续需要跟踪 PDF 覆盖率或导入状态，再追加状态表，而不是把状态字段提前全部塞进主表。

### 14.3 `corpus_manifests`

这张表存放 manifest 本身的元信息，一份 yaml 对应一条主记录。

推荐字段：

```sql
CREATE TABLE corpus_manifests (
  manifest_id TEXT PRIMARY KEY,
  manifest_name TEXT NOT NULL,
  version INTEGER NOT NULL,
  theme TEXT NOT NULL,
  selection_strategy TEXT NOT NULL,
  target_company_count INTEGER NOT NULL,
  source_path TEXT NOT NULL,
  created_at TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1
);
```

字段说明：

- `manifest_id`
  建议使用稳定可读主键，例如 `semiconductor_sample_universe_v1`
- `manifest_name`
  用于展示名称，便于后续并存多个样本池
- `version`
  与 yaml 中的 `version` 对齐
- `theme`
  首版为 `semiconductor`
- `selection_strategy`
  保留选股策略文本，便于后续回溯为什么这样配样本
- `source_path`
  指向 repo 中的 yaml 路径
- `is_active`
  允许后续同时保留旧 manifest，但只标记一个当前生效版本

### 14.4 `corpus_manifest_segment_targets`

这张表存放每个 segment 的目标配额，便于后续检查样本池是否偏离初始设计。

```sql
CREATE TABLE corpus_manifest_segment_targets (
  manifest_id TEXT NOT NULL,
  segment TEXT NOT NULL,
  target_count INTEGER NOT NULL,
  PRIMARY KEY (manifest_id, segment),
  FOREIGN KEY (manifest_id) REFERENCES corpus_manifests(manifest_id)
);
```

首版 `segment` 建议直接沿用 manifest 中的枚举：

- `equipment`
- `materials`
- `manufacturing_idm`
- `packaging_testing`
- `design`
- `support_infra`

### 14.5 `corpus_manifest_companies`

这张表是样本股池的主体，一家公司在同一个 manifest 下对应一条记录。

```sql
CREATE TABLE corpus_manifest_companies (
  manifest_id TEXT NOT NULL,
  company_code TEXT NOT NULL,
  company_name TEXT NOT NULL,
  segment TEXT NOT NULL,
  subsegment TEXT NOT NULL,
  priority TEXT NOT NULL,
  notes TEXT,
  row_order INTEGER NOT NULL,
  is_enabled INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (manifest_id, company_code),
  FOREIGN KEY (manifest_id) REFERENCES corpus_manifests(manifest_id)
);
```

字段说明：

- `row_order`
  保留 yaml 中的顺序，便于回显和 diff
- `is_enabled`
  允许暂时停用某只样本股，而不必删除整条记录
- `priority`
  首版建议枚举为 `high`、`medium`、`low`

首版建议给这张表补以下索引：

```sql
CREATE INDEX idx_manifest_companies_segment
  ON corpus_manifest_companies(manifest_id, segment);

CREATE INDEX idx_manifest_companies_priority
  ON corpus_manifest_companies(manifest_id, priority);
```

### 14.6 `corpus_manifest_company_tags`

`theme_tags` 不建议直接只存在 JSON 字符串里，首版就应该做规范化表，方便后续筛选和统计。

```sql
CREATE TABLE corpus_manifest_company_tags (
  manifest_id TEXT NOT NULL,
  company_code TEXT NOT NULL,
  tag TEXT NOT NULL,
  PRIMARY KEY (manifest_id, company_code, tag),
  FOREIGN KEY (manifest_id, company_code)
    REFERENCES corpus_manifest_companies(manifest_id, company_code)
);
```

建议补索引：

```sql
CREATE INDEX idx_manifest_company_tags_tag
  ON corpus_manifest_company_tags(manifest_id, tag);
```

### 14.7 与 YAML 的同步规则

首版建议采用“yaml 主、SQLite 从”的同步规则：

- yaml 是 source of truth
- SQLite 由导入脚本全量重建或幂等 upsert
- 不允许人工直接改 SQLite 再反向覆盖 yaml

推荐同步步骤：

1. 读取 yaml manifest
2. 写入或更新 `corpus_manifests`
3. 覆盖写入 `corpus_manifest_segment_targets`
4. 覆盖写入 `corpus_manifest_companies`
5. 覆盖写入 `corpus_manifest_company_tags`

这样做的好处是：

- 逻辑简单
- 结果可重放
- 不会出现“数据库状态比文件更新但没人知道”的漂移

### 14.8 后续状态表建议

与 PDF 覆盖率、导入状态相关的信息，不建议现在提前塞进 `corpus_manifest_companies`。如果后续需要，建议单独新增状态表，例如：

```sql
CREATE TABLE corpus_company_ingestion_status (
  manifest_id TEXT NOT NULL,
  company_code TEXT NOT NULL,
  annual_report_count INTEGER NOT NULL DEFAULT 0,
  semiannual_report_count INTEGER NOT NULL DEFAULT 0,
  major_announcement_count INTEGER NOT NULL DEFAULT 0,
  last_ingested_at TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  PRIMARY KEY (manifest_id, company_code),
  FOREIGN KEY (manifest_id, company_code)
    REFERENCES corpus_manifest_companies(manifest_id, company_code)
);
```

这样可以把“样本池定义”和“数据落地进度”解耦，避免一张表既当配置，又当运行状态。
