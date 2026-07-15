# 财务报表表格提取与验证流程指南

> 本文档描述从上市公司年报 PDF 提取财务三表 + 注释明细表并入库 SQLite 的完整流程，
> 以及对提取结果做"30 个查询验证"的方法论。文档自包含，可供其他平台/大模型
> 对其他公司复用此验证流程。

---

## 1. 整体架构与数据流

```
年报 PDF
   │
   ├─ MinerU API（vlm 模型，按 structured_pages 子集解析）
   │     ↓
   ├─ content_list.json（MinerU 缓存，按页组织元素：title/paragraph/table）
   │     ↓
   ├─ _build_artifact（finsight_agent/infra/document_parsers/mineru_parser.py）
   │     ↓
   ├─ parsed_filings/<doc_id>/tables.jsonl   ← 每行一张表，含 table_html/table_markdown
   ├─ parsed_filings/<doc_id>/elements.jsonl ← 标题/段落元素，用于识别章节边界
   │     ↓
   ├─ TableExtractor（capabilities/structured_data/table_extractor.py）
   │     ├─ 规则提取：is_metric_series_table + extract_metrics_by_rule（pandas 风格列对齐）
   │     └─ LLM 注释章节决策：notes_section_decisions/<code>.json（keep=1/0）
   │     ↓
   └─ SQLite: var/data/structured_data/metrics.db → metric_records 表（EAV 长表）
```

### 关键路径速查

| 角色 | 路径 |
|------|------|
| MinerU 缓存 | `var/data/_mineru_cache/<pdf_stem>/<uuid>_content_list.json` |
| 结构化页码配置 | `var/data/page_filter/annual_2025_pages.json` |
| 解析产物 | `var/data/parsed_filings/<doc_id>/{tables.jsonl, elements.jsonl}` |
| LLM 注释决策缓存 | `var/data/notes_section_decisions/<stock_code>.json` |
| 指标数据库 | `var/data/structured_data/metrics.db`（表名 `metric_records`） |
| 指标归一化映射 | `config/structured_data/metric_aliases.json`（中文 → 英文 key） |
| 验证脚本（参考实现） | `scripts/_verify_byd.py` |

---

## 2. 提取流程详解

### 2.1 structured_pages 的确定

`annual_2025_pages.json` 中每家公司有 `kept_ranges`，其中 `processing_type="structured"` 的区间
是三表 + 注释区所在页码。这些页交给 MinerU 做结构化解析（带 table_html），其余页走 `__rag`
路径只做叙述文本切片（存 Qdrant）。

**陷阱**：structured_pages 必须覆盖整张报表的所有跨页，否则 MinerU 会把跨页表截断。
project memory 建议给结构化页范围加 2 页 buffer。

### 2.2 MinerU → tables.jsonl

`_build_artifact` 遍历 content_list 每页元素：

- `type=title` → 更新 `current_section_path`，写入 elements.jsonl
- `type=paragraph` → 写入 elements.jsonl
- `type=table` → 写入 tables.jsonl，字段：
  - `table_id`（全局序号）、`page_start`/`page_end`、`order_in_document`
  - `caption_text`（报表标题，比亚迪 164 张表里几乎全空，靠 elements.jsonl 的 title 推断）
  - `table_markdown`（人类可读，列对齐用 `|`）
  - `table_html`（**pandas.read_html 的输入**，保留合并单元格结构）
  - `table_text`、`parser_source`、`table_type_hint`

**已知现象：table_html 不是 100%**
MinerU 对跨页表格会在续页留下"空占位 table 元素"（table_markdown 长度=0，body 为空）。
比亚迪 164 张表中有 3 张空占位（p144 资产负债表续页、p150 现金流量表续页、p156 权益变动表续页），
内容已在前面页完整输出。**这是正常现象，不是错误**，TableExtractor 会自动跳过空表。

### 2.3 TableExtractor 规则提取

`extract_metrics_by_rule` 对每张 A 类表（指标时间序列表）做：

1. **识别 A 类表头**（`is_metric_series_table`）：
   - 表头含期间关键词（期末余额/期初余额/本期金额/上期金额/2024年度/2024年12月31日 等）
   - 第一列不是维度词（账龄/单位名称/类别/客户/供应商/序号 等 → B 类明细表，跳过）

2. **列类型分类**（`_classify_header_columns`）：每列标记为 `metric`/`note`/`period`
   - period：匹配期间关键词
   - note：附注/注/Note/项目 等表头标识列
   - metric：项目/指标名列

3. **数据行列对齐**：按表头期间列下标取值，强制 `len(value_cells) == len(period_headers)`
   不一致则跳过该行（避免列错位）。

4. **time_scope 归一化**（`_normalize_time_scope`）：
   - `期末余额`/`期初余额` → 原样
   - `本期金额`/`本期发生额` → `本期`；`上期金额`/`上期发生额` → `上期`
   - `2024年度`/`2024 年度`/`2024年12月31日`/`2024年(经重述)` → **统一为 `2024年`**
     （去掉空格、"度"、完整日期、"(经重述)"标记，只保留 4 位年份 + "年"）

5. **metric_name 归一化**：`MetricNormalizer` 把中文原文映射成英文 key
   （如"货币资金"→`cash_and_equivalents`），映射表在 `metric_aliases.json`。
   未命中的指标 `metric_name = metric_label`（保留中文）。

6. **生成 MetricRecord**，关键字段：
   - `company_code`/`company_name`、`metric_label`（中文原文）/`metric_name`（英文 key）
   - `time_scope`（归一化后）、`period_end`（YYYY-MM-DD）、`value`（字符串，保留千分位/括号负数）
   - `unit="元"`（**注意：比亚迪年报实际单位是千元，但 unit 字段统一标"元"**，查询时需知道这一点）
   - `statement_type`：`consolidated`（合并）/`parent_only`（母公司）
   - `source_section`：`unknown`（三表区，未细分）/`notes`（注释区）/`cash_flow_statement`（部分现金流表）
   - `source_table_id`、`source_caption`、`confidence`

### 2.4 statement_type 判定

TableExtractor 根据表标题/section_path 判断：
- 标题含"合并"或无明确标识 → `consolidated`
- 标题含"公司"（如"公司资产负债表""公司利润表"，指母公司）→ `parent_only`

### 2.5 source_section 判定（已知局限）

当前 TableExtractor 对三表区**未细分**报表类型，统一标 `unknown`。
只有部分现金流量表被标为 `cash_flow_statement`（64 条）。
**查询三表数据时不要用 `source_section='balance_sheet'` 等精确值，要用 `source_section='unknown'`**。

---

## 3. LLM 注释章节保留流程

### 3.1 为什么需要 LLM 决策

注释区（如"七、合并财务报表主要项目注释"）有几十到上百张明细表，分两类：
- **A 类（值得保留）**：明细分类表、调节表、变动表，含可查询的指标值
  （如"14、固定资产"含原价/累计折旧/账面价值，"58、所得税费用"含当期/递延调节）
- **B 类（跳过）**：账龄分析维度表、披露性维度表、客户/供应商名单
  （如"3、应收账款"账龄分桶，无指标值只有占比）

B 类表与三表存在同名 key 碰撞（如"应收账款""长期借款""财务费用"），语义不同，
全部入库会污染查询结果。因此用 LLM 判断每个注释章节 keep=1/0。

### 3.2 LLM 决策流程

1. **收集注释章节标题**：遍历 elements.jsonl，在注释区（"财务报表主要项目注释"起点之后）
   收集所有 `数字、` 开头的 title（如"14、固定资产""44、营业收入和营业成本"）。

2. **LLM 判断**（`LlmClient.complete_json`）：
   - 输入：章节标题 + 该章节下第一张表的 markdown 采样
   - 输出：`{"keep": 1/0, "reason": "明细分类有指标值" / "账龄分析维度表" / ...}`
   - 缓存到 `var/data/notes_section_decisions/<stock_code>.json`，避免重复调用

3. **应用决策**：TableExtractor 遍历注释区表时，查 `decisions[nearest_section_title]`：
   - `keep=1` → 提取指标入库（source_section='notes'）
   - `keep=0` → 跳过，不入库

### 3.3 比亚迪决策结果（参考）

- 总章节：63
- keep=1：50（明细分类、调节表、变动表、费用明细、关键指标）
- keep=0：13（账龄分析、披露性维度表，如"3、应收账款"账龄表、"22、所有权或使用权受到限制的资产"）

**注释区指标名特征**：注释区表的第一列是明细项名称，**不是报表原词**。
例如"44、营业收入和营业成本"注释表的指标是"主营业务收入""其他业务收入"，
不是"营业收入"。"47、管理费用"注释表的指标是"职工福利费""社会保险费""折旧及摊销"，
不是"管理费用"。**查询注释区时要用明细项名称，不能用报表原词**。

### 3.4 LLM 配置（硬约束）

- API：AGICTO OpenAI 兼容（`https://api.agicto.cn/v1/chat/completions`）
- 模型：`deepseek-v4-flash`（可被 `FINSIGHT_LLM_MODEL` 覆盖）
- API Key 环境变量优先级：`AGICTO_API_KEY` → `FINSIGHT_LLM_API_KEY` → `DEVAGI_API_KEY`
- 超时 30s，重试 3 次（429/5xx/网络错误）
- `response_format={"type":"json_object"}` + 正则兜底解析
- 必须走系统代理（国内网络限制）

---

## 4. 验证方法论：30 个查询验证

### 4.1 验证目标

确认提取数据"没有错误"：表数正确、三表/注释表分类正确、指标值与原始 HTML 一致、
跨年度可比、母公司报表可查。

### 4.2 30 个查询的设计维度

| 维度 | 题号 | 数量 | 验证点 |
|------|------|------|--------|
| 三表-资产负债表（合并） | Q01-Q10 | 10 | 流动/非流动资产、流动/非流动负债、权益 |
| 三表-利润表（合并） | Q11-Q16 | 6 | 收入、成本、利润、每股收益、研发费用 |
| 三表-现金流量表（合并） | Q17-Q20 | 4 | 经营/投资/筹资活动净额、期末现金 |
| 注释区 LLM keep=1 | Q21-Q25 | 5 | 营收明细、管理费用明细、固定资产、所得税、递延所得税 |
| 跨年度对比 | Q26-Q28 | 3 | 同一指标 2024 vs 2023 |
| 母公司报表 | Q29-Q30 | 2 | 母公司净利润、营业收入 |

### 4.3 查询模板（SQL）

```sql
SELECT metric_name, metric_label, time_scope, value, period_end,
       source_section, statement_type
FROM metric_records
WHERE company_code = '<股票代码>'
  AND <where_clause>
ORDER BY time_scope, source_section;
```

### 4.4 关键字段值特征（**查询时必须注意**）

这些是比亚迪验证中踩过的坑，对其他公司同样适用：

1. **time_scope 全部归一化为 `YYYY年`**
   - `2024年度` → `2024年`
   - `2024年12月31日` → `2024年`
   - `2024年(经重述)` → `2024年`
   - 查询利润表/现金流量表时用 `time_scope='2024年'`，**不要用 `'2024年度'`**

2. **source_section 三表多为 `unknown`**
   - 不要用 `source_section='balance_sheet'/'income_statement'`
   - 三表区查询统一用 `source_section='unknown'`
   - 注释区查询用 `source_section='notes'`

3. **所有者权益合计的实际 label 因公司而异**
   - 比亚迪用"股东权益合计"（不是"所有者权益合计"）
   - 归母权益为"归属于母公司股东权益合计"（不是"归属于母公司所有者权益合计"）
   - 建议用 `LIKE '%股东权益合计%'` 或先查实际 label 再精确匹配

4. **营业成本带前缀**
   - 比亚迪利润表 label 为"减:营业成本"或"减：营业成本"（半角/全角冒号）
   - 建议用 `LIKE '%营业成本%'`

5. **现金流量表净额措辞不一**
   - 投资活动可能是"投资活动产生的现金流量净额"或"投资活动使用的现金流量净额"
   - 筹资活动可能是"筹资活动产生的现金流量净额"或"筹资活动(使用)/产生的现金流量净额"
   - 期末现金可能是"期末现金及现金等价物余额"或"六、年末现金及现金等价物余额"
   - 建议用 `LIKE '%投资活动%现金流量净额%'` 等模糊匹配

6. **注释区指标名是明细项，不是报表原词**
   - 查"营业收入明细"用 `metric_label IN ('主营业务收入','其他业务收入')`
   - 查"管理费用明细"用 `metric_label IN ('职工福利费','社会保险费','折旧及摊销')`
   - 不能用 `metric_label='营业收入' AND source_section='notes'`

7. **数值单位与公开数据对账**
   - 比亚迪年报数值单位是"千元"（777,102,455 千元 = 7771 亿元）
   - SQLite `unit` 字段统一标"元"（未区分千元/元）
   - 验证时需知道年报单位，与公开数据（如巨潮资讯、Wind）对账

8. **value 是字符串**
   - 保留千分位（`102,738,734`）和括号负数（`(129,082,282)`）
   - 比较数值时需 `CAST(REPLACE(REPLACE(value,',',''),'(','-') AS REAL)`（简化版，不处理括号闭合）
   - 验证"值正确"时直接字符串比对原始 HTML 即可

### 4.5 验证脚本结构（参考 `scripts/_verify_byd.py`）

```
[1] tables.jsonl 统计
    - 总表数、含 table_html 数
    - 三表区页码范围、注释区页码范围
    - 按报表类型分类（balance_sheet/income_statement/cash_flow_statement/equity_statement）
    - 注释区 keep=1/keep=0 表数

[2] LLM 注释章节决策
    - 总章节、keep=1、keep=0

[3] SQLite 数据分布
    - 总记录数
    - source_section 分布、statement_type 分布、time_scope 分布
    - 数据采样（source_section='unknown' 前 20 条、'notes' 前 10 条）

[4] 30 个查询验证
    - 按 4.2 的维度逐条查询
    - 输出通过/失败，失败时打印 0 条
    - 汇总：通过 X/30，失败 Y/30
```

### 4.6 报表标题识别（classify_stmt_title）

识别三表标题时需排除注释章节标题：

```python
def classify_stmt_title(text: str) -> str | None:
    t = text or ""
    if "注释" in t:        # 排除"60、现金流量表项目注释"
        return None
    if "补充资料" in t:    # 排除"61、现金流量表补充资料"
        return None
    if "资产负债表" in t: return "balance_sheet"
    if "利润表" in t:     return "income_statement"
    if "现金流量表" in t: return "cash_flow_statement"
    if "所有者权益变动表" in t or "股东权益变动表" in t: return "equity_statement"
    return None
```

### 4.7 章节边界（build_page_ranges）

每个报表标题只覆盖到"下一个章节边界"前，边界 = 报表标题页 ∪ 注释区起点页。
否则最后一个报表标题会越界覆盖整个注释区。

```python
boundary_pages = sorted(set([p for p,_,_ in stmt_titles] + list(notes_start_pages)))
for page, stmt_type, _ in stmt_titles:
    next_boundary = next((bp for bp in boundary_pages if bp > page), max_page+1)
    for p in range(page, next_boundary):
        if p in actual_pages:
            stmt_page_map[p] = stmt_type
```

注释区起点识别：含"财务报表主要项目注释"且含"七、"/"十九、"/"公司财务"的 title。
注释区 = 从最早注释起点到 elements 最大页，排除三表区。

---

## 5. 对其他公司复用此验证流程

### 5.1 准备工作

1. 确认该公司已走完提取流程：
   - `var/data/parsed_filings/<doc_id>/tables.jsonl` 存在
   - `var/data/parsed_filings/<doc_id>/elements.jsonl` 存在
   - `var/data/notes_section_decisions/<stock_code>.json` 存在
   - SQLite `metric_records` 表中有该 company_code 的记录

2. 获取 `doc_id`：
   ```
   <stock_code>_<公司名>__annual__<year>__<pdf_stem>__structured_v2
   ```
   例如 `002594_比亚迪__annual__2025__002594_比亚迪_annual_report_2025_20250325__structured_v2`

### 5.2 适配验证脚本

复制 `scripts/_verify_byd.py` 为 `scripts/_verify_<stock_code>.py`，修改：

```python
DOC_ID = "<目标公司的 doc_id>"
# 其余逻辑通用，无需修改
```

### 5.3 适配 30 个查询的 where_clause

针对目标公司的实际数据特征调整（见 4.4）：

1. 先跑 `[3] SQLite 数据分布` 部分，看实际 `metric_label`/`time_scope`/`source_section` 分布
2. 先跑 `数据采样`，看前 20 条数据长什么样
3. 针对实际 label 调整查询：
   - 所有者权益：先查 `SELECT DISTINCT metric_label FROM metric_records WHERE company_code=? AND metric_label LIKE '%权益合计%'`，再用精确值
   - 营业成本：用 `LIKE '%营业成本%'` 兼容"减:营业成本"/"减：营业成本"
   - 现金流量净额：用 `LIKE '%投资活动%现金流量净额%'` 兼容"产生"/"使用"
   - 注释区：先用 `SELECT DISTINCT metric_label FROM metric_records WHERE source_section='notes'` 看明细项名称

### 5.4 验证步骤

1. **统计层**（[1][2][3]）：
   - 表数是否合理（三表 8-16 张、权益变动表 2-6 张、注释区几十到上百张）
   - LLM 决策 keep/skip 比例（通常 keep > skip，比亚迪 50:13）
   - SQLite 记录数（三表区几百条、注释区几百到上千条）
   - time_scope 分布（2024年/2023年 应占多数）

2. **查询层**（[4] 30 个查询）：
   - 目标 30/30 全通过
   - 失败时按 4.4 的字段特征排查

3. **值对账层**（抽样核对）：
   - 从 tables.jsonl 取原始 table_markdown，找关键指标行
   - 与 SQLite value 字段字符串比对（注意千分位/括号负数）
   - 与公开数据（巨潮资讯年报、Wind/同花顺）对账数值量级
   - 注意单位：年报可能是"元"/"千元"/"万元"，SQLite unit 字段不一定准确

### 5.5 常见失败原因与修复

| 失败现象 | 可能原因 | 修复方法 |
|----------|----------|----------|
| 三表区表数=0 | caption_text 全空，靠 page_start 落入三表区识别；若 elements.jsonl 报表标题页码错则失败 | 检查 elements.jsonl 中"资产负债表"等标题的 page_start |
| 注释区表数=0 | notes_start_pages 未识别（注释区起点 title 措辞不同） | 扩展"财务报表主要项目注释"匹配条件 |
| Q09-Q10 权益失败 | label 是"股东权益合计"而非"所有者权益合计" | 用 LIKE 或先查实际 label |
| Q11-Q20 利润/现金流失败 | time_scope 用了"2024年度"但实际归一化为"2024年" | 改用 `time_scope='2024年'` |
| Q21-Q22 注释区失败 | 用了报表原词"营业收入"但注释区是"主营业务收入" | 用明细项名称或 LIKE |
| Q29-Q30 母公司失败 | statement_type 不是 'parent_only' | 先查 `SELECT DISTINCT statement_type` 看实际值 |
| 值差 1000 倍 | 年报单位是千元，公开数据是元 | 对账时统一单位 |

---

## 6. 比亚迪验证结果（2026-07-13，作为基准）

### 6.1 表格统计

- 总表数：164（含 table_html 161，空占位 3）
- 三表：16（资产负债表 11 + 利润表 3 + 现金流量表 2）
- 权益变动表：6
- 注释区：142（keep=1 章节 102 张 + keep=0 章节 40 张）
- LLM 决策：63 章节（keep=50 / skip=13）

### 6.2 SQLite 分布

- 总记录：1863（notes 1233 + unknown 566 + cash_flow_statement 64）
- statement_type：consolidated 1521 + parent_only 342
- time_scope：2024年 644 + 2023年 511 + 其他 708

### 6.3 30 查询：30/30 通过

### 6.4 值对账（原始 HTML vs SQLite vs 公开数据）

| 指标 | 原始 HTML | SQLite | 量级核对 |
|------|-----------|--------|----------|
| 货币资金 | 102,738,734 | 102738734 | ≈1027 亿元 ✓ |
| 资产总计 | 783,355,855 | 783355855 | ≈7834 亿元 ✓ |
| 负债合计 | 584,667,646 | 584667646 | ≈5847 亿元 ✓ |
| 股东权益合计 | 198,688,209 | 198688209 | ≈1987 亿元 ✓ |
| 营业收入 | 777,102,455 | 777102455 | ≈7771 亿元 ✓（比亚迪 2024 营收公开数据） |
| 净利润 | 41,587,940 | 41587940 | ≈416 亿元 ✓ |
| 研发费用 | 53,194,745 | 53194745 | ≈532 亿元 ✓ |
| 基本每股收益 | 13.84 | 13.84 | 元/股 ✓ |
| 经营活动现金流量净额 | 133,453,873 | 133453873 | ≈1335 亿元 ✓ |
| 母公司净利润 | 14,171,956 | 14171956 | ≈142 亿元 ✓ |

（年报单位为千元，公开数据通常为元，量级核对时注意换算）

---

## 7. 注意事项与已知局限

1. **table_html 非 100% 是正常的**：MinerU 跨页表格续页留空占位，内容已在前页完整输出。
   验证"含 table_html 数"时，空占位数应 ≤ 报表数（每个跨页报表最多 1 个空占位）。

2. **source_section 未细分三表**：当前 TableExtractor 只标 `unknown`/`notes`/`cash_flow_statement`。
   若需按 balance_sheet/income_statement 精确查询，需在 TableExtractor 中增加报表类型识别
   （基于 elements.jsonl 的报表标题页码 → stmt_page_map）。

3. **unit 字段不准确**：统一标"元"，实际可能是千元/万元。查询时不要依赖 unit，
   要从年报原文或量级核对确认单位。

4. **metric_name 部分未归一化**：未在 `metric_aliases.json` 中的指标，`metric_name = metric_label`（中文）。
   查询时优先用 `metric_label`（中文原文），`metric_name` 仅作辅助。

5. **注释区同名 key 碰撞**：注释区与三表存在同名指标（如"应收账款""长期借款"），
   语义不同。LLM keep/skip 决策已过滤大部分 B 类表，但查询时仍建议用
   `source_section` 区分三表（`unknown`）与注释（`notes`）。

6. **繁体年份**：港交所双语年报可能有"二零二四年"，`_normalize_time_scope` 保持原样，
   查询时需单独处理（比亚迪无此情况）。

7. **跨页表截断**：若 structured_pages 未覆盖整张报表，MinerU 会截断。
   症状：某报表只有部分指标入库。修复：扩展 structured_pages 范围（加 2 页 buffer）。

---

## 附录 A：验证脚本完整结构（`scripts/_verify_byd.py`）

```
模块级常量：DOC_ID, PARSED_DIR, TABLES_JSONL, ELEMENTS_JSONL, NOTES_DECISION_FILE, DB_PATH

函数：
  load_jsonl(path) → list[dict]
  classify_stmt_title(text) → str|None     # 识别报表标题，排除注释章节
  build_page_ranges(elements) → (stmt_page_map, notes_pages, notes_section_titles)
  find_nearest_notes_title(page, titles) → str|None

main():
  [1] tables.jsonl 统计（总表数、html数、三表/注释表分类）
  [2] LLM 注释章节决策分布
  [3] SQLite 数据分布（source_section/statement_type/time_scope + 采样）
  [4] 30 个查询验证（逐条 SQL，输出通过/失败）
```

## 附录 B：快速对账 SQL 模板

```sql
-- 查某指标的所有记录（跨年度/跨报表类型）
SELECT metric_label, time_scope, value, period_end, source_section, statement_type
FROM metric_records
WHERE company_code = '<code>' AND metric_label LIKE '%<关键词>%'
ORDER BY time_scope, statement_type;

-- 查所有者权益相关 label
SELECT DISTINCT metric_label, metric_name
FROM metric_records
WHERE company_code = '<code>' AND metric_label LIKE '%权益合计%';

-- 查注释区所有指标名（找明细项）
SELECT DISTINCT metric_label
FROM metric_records
WHERE company_code = '<code>' AND source_section = 'notes'
ORDER BY metric_label;

-- 跨年度对比某指标
SELECT metric_label, time_scope, value, statement_type
FROM metric_records
WHERE company_code = '<code>'
  AND metric_label = '<精确label>'
  AND time_scope IN ('2024年', '2023年')
  AND statement_type = 'consolidated'
ORDER BY time_scope;
```

## 附录 C：原始 HTML 值核对模板（Python）

```python
import json
from pathlib import Path

TABLES_JSONL = Path("var/data/parsed_filings/<doc_id>/tables.jsonl")
tables = [json.loads(l) for l in TABLES_JSONL.open(encoding="utf-8") if l.strip()]

# 找某页的表，核对某指标的值
for t in tables:
    if int(t.get("page_start") or 0) == <页码>:
        md = t.get("table_markdown") or ""
        for line in md.split("\n"):
            if "<指标关键词>" in line:
                print(line)  # 与 SQLite value 比对
                break
        break
```
