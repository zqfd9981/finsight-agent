# 年报结构化数据提取 — 独立项目现状快照

> 生成时间：2026-07-14
> 目的：评估"年报结构化数据提取"模块从 finsight_agent 中独立出来的可行性，并固化现状方便后续独立。

---

## 1. 是否值得独立？— 值得

**复杂度已足够高**：核心代码 ~3400 行（不含脚本），是一个完整的"PDF → 结构化指标库"子系统。

**耦合度低**：与 finsight_agent 其他部分（RAG 检索、LLM 问答、前端服务）的唯一耦合点是查询时的 `StructuredDataService → MetricRepository.find_best_match` 调用，可以轻松用接口隔离。

**独立化收益**：
- 单独迭代节奏（结构化提取的 bug 修复不应触发 RAG/前端的全量测试）
- 单独部署（提取流水线是离线 batch 作业，查询是在线服务，混在一起不合理）
- 可复用（其他项目可直接接入这套年报提取能力）

---

## 2. 项目定位与边界

**做什么**：
- 输入：A 股上市公司年报 PDF
- 输出：SQLite 结构化指标库（三表 + 权益变动表 + 注释区 LLM 筛选明细表）

**不做什么**：
- 不做 RAG 向量检索（那是 finsight_agent 的事）
- 不做 LLM 问答（那是 finsight_agent 的事）
- 不做行情/实时数据（预留了 `ExternalMetricProvider` 接口）

**数据流全景**：
```
PDF 下载 → page_filter(LLM/rule 配页码) → MinerU 解析 → 跨页修复
  → TableExtractor(pandas→正则→LLM 三级提取) → MetricNormalizer(归一化)
  → MetricRepository(写 SQLite)
```

---

## 3. 代码资产清单

### 3.1 核心模块（~3400 行）

| 模块 | 路径 | 行数 | 职责 |
|---|---|---|---|
| **TableExtractor** | `backend/src/finsight_agent/capabilities/structured_data/table_extractor.py` | 1097 | 表格提取核心：pandas.read_html 优先→正则解析 markdown→LLM 回退；注释区 LLM 决策 keep/skip |
| **MineruParser** | `backend/src/finsight_agent/infra/document_parsers/mineru_parser.py` | 586 | MinerU API v4 主解析器：上传→轮询→下载 zip→转 ParsedDocumentArtifact；title 提升；单位解析 |
| **CrossPageRepair** | `backend/src/finsight_agent/capabilities/structured_data/cross_page_repair.py` | 368 | 跨页表格修复：检测缺失汇总行→拼接 PDF→重解析→验证补齐 |
| **MetricRepository** | `backend/src/finsight_agent/capabilities/structured_data/repository.py` | 317 | SQLite 仓储：建表/索引/迁移(幂等)、按公司 upsert、3 层匹配查询、合并口径优先 |
| **MetricNormalizer** | `backend/src/finsight_agent/capabilities/structured_data/metric_normalizer.py` | 294 | 中文指标名→标准英文 key 归一化：3 层匹配 + LLM 批量生成映射表 |
| **PdfplumberParser** | `backend/src/finsight_agent/infra/document_parsers/pdfplumber_parser.py` | 319 | pdfplumber 轻量 fallback 解析器 |
| **Models** | `backend/src/finsight_agent/capabilities/structured_data/models.py` | 80 | MetricRecord(16 字段) / MetricQuery / MetricLookupResult |
| **Service** | `backend/src/finsight_agent/capabilities/structured_data/service.py` | 125 | 查询门面：归一化→查库→未命中走外部 provider→degraded 兜底 |
| **Providers** | `backend/src/finsight_agent/capabilities/structured_data/providers.py` | 26 | 外部指标接口（预留） |

### 3.2 脚本（~5000 行）

| 脚本 | 行数 | 职责 |
|---|---|---|
| `build_page_filter.py` | 761 | 扫描 PDF 目录/书签，LLM 决策 rag/structured 页码分流 |
| `parse_filtered_pages.py` | 567 | 按 processing_type 分流入库：rag→切块→索引，structured→提取→SQLite |
| `rebuild_from_cache.py` | 491 | 从 MinerU 缓存零成本重载（不调 API） |
| `build_corpus_pipeline.py` | 335 | 一键全流程（下载→解析→索引），仅 RAG 路径 |
| `pilot_rebuild_html.py` | 414 | HTML 路线提取质量对比试点 |
| `migrate_metrics_to_sqlite.py` | 75 | JSONL→SQLite 一次性迁移 |
| `rebuild_metric_aliases.py` | 80 | LLM 归一化补救 |
| `repair_dedup_metrics.py` | 56 | 去重修复 |

### 3.3 验证脚本（已验证的公司基准）

| 脚本 | 公司 | 结果 |
|---|---|---|
| `_verify_byd.py` + `_verify_byd_html.py` | 002594 比亚迪 | 30/30 查询 + 7/7 值对账 + 跨表差异=0 |
| `_verify_yonyou.py` + `_verify_yonyou_html.py` | 600588 用友网络 | 30/30 查询 + 7/7 值对账 + 跨表差异=0 |
| `_verify_two_html.py` | 600031 三一重工 + 600690 海尔智家 | 三一 5/5 值对账通过；海尔 3/3 通过但缺合并利润表/现金流+注释区未入库 |

---

## 4. 数据资产

### 4.1 SQLite 指标库

- 路径：`var/data/structured_data/metrics.db`
- Schema：`metric_records` 表，16 字段 + 自增主键
- 关键字段：`metric_label`(中文原文) / `metric_name`(英文 key) / `time_scope` / `value`(原始字符串) / `statement_type`(consolidated/parent_only) / `source_section`(balance_sheet/income_statement/cash_flow_statement/equity_statement/notes)
- 索引：4 个（company+metric+time_scope / company / statement 优先级 / source_section 过滤）

### 4.2 解析产物

- 路径：`var/data/parsed_filings/<document_id>/`
- 内容：`document.json` + `elements.jsonl`(title/paragraph/table) + `tables.jsonl`(含 table_html) + `parse_report.json`
- document_id 约定：`{company_code}_{name}__{doc_type}__{year}__{stem}__structured`（或 `__rag`）

### 4.3 配置与缓存

| 文件 | 路径 | 说明 |
|---|---|---|
| 页码配置 | `var/data/page_filter/annual_2025_pages.json` | LLM/rule 决策的 rag/structured 页码分流 |
| 归一化映射 | `var/data/structured_data/metric_aliases.json` | 中文→英文 key 映射表 |
| 注释决策缓存 | `var/data/notes_section_decisions/{company_code}.json` | LLM 决策注释章节 keep/skip |
| MinerU 缓存 | `var/data/_mineru_cache/` | content_list.json 等原始解析结果 |

---

## 5. 外部依赖

| 依赖 | 用途 | 必需性 |
|---|---|---|
| **MinerU API** | PDF 结构化解析（表格 HTML 输出） | 必需（无替代品能达到同等质量） |
| **AGICTO LLM API** | 注释章节决策 + 指标名归一化 + 复杂表 fallback | 必需（deepseek-v4-flash 模型） |
| **pandas** | HTML 表格解析（自动展开合并单元格） | 必需 |
| **PyMuPDF (fitz)** | PDF 页数检测 + 物理拆分 + 跨页拼接 | 必需 |
| **pypdf** | 跨页表格修复时的 PDF 拼接 | 可选（PyMuPDF 可替代） |
| **pdfplumber** | 轻量 fallback 解析器 | 可选（质量差，仅调试用） |
| **SQLite** | 指标存储 | 必需（Python 内置） |

---

## 6. 与 finsight_agent 的耦合点

只有 **1 个运行时耦合点**：

```
finsight_agent 的 ReportingService
  → StructuredDataService.query_metric_lookup()
    → MetricNormalizer.normalize()
    → MetricRepository.find_best_match()
    → 返回 MetricLookupResult
```

独立化时只需：
1. 把 `capabilities/structured_data/` + `infra/document_parsers/` 整体搬走
2. 在 finsight_agent 侧留一个 `StructuredDataClient` 接口（HTTP/gRPC/直接 import 均可）
3. 提取流水线（scripts/）作为独立项目的 batch 作业

---

## 7. 已知问题与待改进项

### 7.1 structured_pages 配置是最脆弱的环节

三一重工缺注释区、海尔智家缺合并利润表/现金流 + 注释区未入库，**根因都是 structured_pages 页码配置错误**（LLM page_filter 或人工配页码出错）。

**建议**：入库后加"三表完整性校验"——检查 8 类报表（合并/母公司 × 4 类）是否齐全 + 注释区起点标题是否存在。不齐全时标记为 `degraded` 并告警。

### 7.2 注释区识别依赖起点标题页

`_build_statement_type_map` 需要"七、合并财务报表项目附注"这样的注释区起点标题来激活 `in_notes_region`。如果 structured_pages 跳过了这个标题所在页（如海尔智家 p128→p166 空白 38 页），注释区全部丢失。

**建议**：增加兜底逻辑——如果 structured 目录中有 `1、货币资金` 这类注释章节标题但没有注释区起点标题，自动从第一个注释章节标题开始激活 `in_notes_region`。

### 7.3 值单位不一致

三一重工值是整数（`20383175`，万元），海尔智家值有小数（`55583842589.70`，元）。当前 `unit` 字段都标"元"，但实际单位取决于年报声明。MinerU 解析器已实现单位检测（`_detect_table_unit`），但部分公司可能漏检。

### 7.4 注释表 LLM 决策缓存覆盖不足

目前只有 3 家公司有决策缓存（002594/600519/600588）。新公司首次提取时需要调 LLM，每家约 60-80 个注释章节，耗时约 2-3 分钟。

---

## 8. 独立化步骤建议

1. **新建仓库** `annual-report-structured-extraction`
2. **搬运代码**：
   - `capabilities/structured_data/` → `src/extraction/`
   - `infra/document_parsers/` → `src/parsers/`
   - `scripts/build_page_filter.py` + `parse_filtered_pages.py` + `rebuild_from_cache.py` → `scripts/`
3. **解耦**：移除对 `finsight_agent.capabilities.retrieval` 的依赖（parsing_models/parsing_service/parsed_storage 需要搬走或简化）
4. **接口化**：暴露 2 个入口：
   - `extract_company(pdf_path, company_code) → SQLite`（batch 作业）
   - `query_metric(company_code, metric_label) → MetricRecord`（在线查询）
5. **配置独立**：app.yaml 中的 `structured_data` 段独立成 config.yaml
6. **测试迁移**：搬运 `_verify_byd.py` / `_verify_yonyou.py` 作为回归测试基准
