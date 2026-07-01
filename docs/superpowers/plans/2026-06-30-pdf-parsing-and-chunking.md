# 本地 PDF 解析与 Chunking 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 在已完成的本地 PDF 语料采集链路之上，实现首版 `parsing + chunking` 流程，能够把 `raw_filings` 下的真实 PDF 转换为标准解析产物和 `parent / child` chunk 产物，为后续 `SQLite FTS5 / Qdrant / citation` 打基础。

**架构：** 采用“结构化解析优先”的路线：`MinerU` 作为主解析器，`pdfplumber` 作为整份文档级 fallback。项目内部只实现 parser 抽象层、normalizer、解析产物落盘和 chunking 逻辑。解析层输出 `document.json / elements.jsonl / tables.jsonl / parse_report.json`，chunking 层消费这些结构化产物并生成 `parents.jsonl / children.jsonl / chunk_report.json`。真正的切分规则只存在于 chunking 层，`elements` 只是结构化输入。

**技术栈：** Python 3、`unittest`、标准库 `json` / `pathlib`、`pdfplumber`、可插拔 `MinerU` 适配层、现有 retrieval 目录结构、基于文件系统的中间产物落盘。

---

## 文件结构

### 新增文件
- `backend/src/finsight_agent/capabilities/retrieval/parsing_models.py`
  定义 `ParsedDocument`、`ParsedElement`、`ParsedTable`、`ParseReport`、`ChunkRecord`、`ChunkReport` 等内部模型。
- `backend/src/finsight_agent/capabilities/retrieval/parsing_service.py`
  负责 parser 调度、fallback、normalizer 和解析产物落盘。
- `backend/src/finsight_agent/capabilities/retrieval/chunking.py`
  负责从 `elements.jsonl / tables.jsonl` 生成 `parent / child` chunks。
- `backend/src/finsight_agent/capabilities/retrieval/parsed_storage.py`
  负责 `parsed_filings/` 和 `chunked_filings/` 下的目录构建、json/jsonl 写入和覆盖策略。
- `backend/src/finsight_agent/infra/document_parsers/mineru_parser.py`
  封装 `MinerU` 主解析器调用，返回统一 raw parse 结果。
- `backend/src/finsight_agent/infra/document_parsers/pdfplumber_parser.py`
  提供整份文档级 fallback 解析。
- `tests/unit/test_pdf_parsing_normalizer.py`
  覆盖 raw parse 到 `document/elements/tables/parse_report` 的标准化映射。
- `tests/unit/test_pdf_chunking.py`
  覆盖 `elements -> parent/child` 的切分规则、长度控制和 table 处理。
- `tests/integration/test_pdf_parsing_artifacts.py`
  覆盖解析产物落盘和 chunk 产物落盘目录结构。

### 修改文件
- `backend/src/finsight_agent/capabilities/retrieval/service.py`
  保持薄入口，新增构造 parsing / chunking service 的入口，但不和在线 retrieval 混在一起。
- `backend/src/finsight_agent/config/settings.py`
  增加 `parsed_filings_root`、`chunked_filings_root`、parser 版本与 chunking 阈值配置读取。
- `config/app.yaml`
  增加 parsing / chunking 相关配置。

### 实现前需要阅读的现有文件
- `docs/superpowers/specs/2026-06-30-local-pdf-rag-design.md`
- `docs/superpowers/specs/2026-06-30-pdf-corpus-acquisition-design.md`
- `backend/src/finsight_agent/capabilities/retrieval/acquisition_service.py`
- `backend/src/finsight_agent/capabilities/retrieval/storage.py`
- `var/data/raw_filings/`

---

## 任务 1：补充 parsing / chunking 配置与基础模型

**文件：**
- Create: `backend/src/finsight_agent/capabilities/retrieval/parsing_models.py`
- Modify: `backend/src/finsight_agent/config/settings.py`
- Modify: `config/app.yaml`
- Test: `tests/unit/test_pdf_parsing_normalizer.py`

- [ ] **步骤 1：先写失败测试，约束配置入口**

运行目标：
- `settings.retrieval.parsed_filings_root`
- `settings.retrieval.chunked_filings_root`
- `settings.retrieval.primary_parser_name`
- `settings.retrieval.parent_target_chars`
- `settings.retrieval.child_target_chars`

- [ ] **步骤 2：补最小配置和内部模型**

至少定义：
- `ParsedDocumentArtifact`
- `ParsedElement`
- `ParsedTable`
- `ParseReport`
- `ChunkRecord`
- `ChunkReport`

- [ ] **步骤 3：再次运行测试，确认通过**

运行：`python -m unittest tests.unit.test_pdf_parsing_normalizer -v`

### 任务 2：实现 parser 抽象层与整份文档级 fallback

**文件：**
- Create: `backend/src/finsight_agent/infra/document_parsers/mineru_parser.py`
- Create: `backend/src/finsight_agent/infra/document_parsers/pdfplumber_parser.py`
- Create: `backend/src/finsight_agent/capabilities/retrieval/parsing_service.py`
- Test: `tests/unit/test_pdf_parsing_normalizer.py`

- [ ] **步骤 1：先写失败测试，明确 parser 调度行为**

需要覆盖：
- `MinerU` 成功时不走 fallback
- `MinerU` 失败时整份文档切到 `pdfplumber`
- fallback 也失败时只写最小主记录和失败报告

- [ ] **步骤 2：实现统一解析接口**

建议接口：

```python
class DocumentParser:
    def parse(self, pdf_path: Path) -> ParsedDocumentArtifact:
        ...
```

- [ ] **步骤 3：在 `ParsingService` 里串起主解析器和 fallback**

约束：
- 不做按页 fallback
- `parse_report` 必须记录 `fallback_used`
- 不在这层做 chunking

- [ ] **步骤 4：运行测试，确认 parser 调度行为通过**

运行：`python -m unittest tests.unit.test_pdf_parsing_normalizer -v`

### 任务 3：实现 normalizer 与解析产物落盘

**文件：**
- Modify: `backend/src/finsight_agent/capabilities/retrieval/parsing_service.py`
- Create: `backend/src/finsight_agent/capabilities/retrieval/parsed_storage.py`
- Test: `tests/unit/test_pdf_parsing_normalizer.py`
- Test: `tests/integration/test_pdf_parsing_artifacts.py`

- [ ] **步骤 1：先写失败测试，明确 4 份产物的最小 schema**

需要覆盖：
- `document.json`
- `elements.jsonl`
- `tables.jsonl`
- `parse_report.json`

- [ ] **步骤 2：实现 normalizer**

只做这些职责：
- 统一 element type
- 合并视觉换行
- 清理空白噪声
- 维护 `order_in_document`
- 维护 `section_path`
- 关联 `table_caption` 和 `table`
- 过滤明显页眉页脚

- [ ] **步骤 3：实现 `parsed_filings/<document_id>/` 落盘**

约束：
- 每个 PDF 一个目录
- 覆盖写而不是保留多版本目录
- `parse_report` 里记录 `parser_version / generated_at`

- [ ] **步骤 4：运行测试，确认解析产物目录结构和内容通过**

运行：
- `python -m unittest tests.unit.test_pdf_parsing_normalizer -v`
- `python -m unittest tests.integration.test_pdf_parsing_artifacts -v`

### 任务 4：实现 `elements -> parent / child` 的唯一切分规则

**文件：**
- Create: `backend/src/finsight_agent/capabilities/retrieval/chunking.py`
- Test: `tests/unit/test_pdf_chunking.py`

- [ ] **步骤 1：先写失败测试，明确 parent / child 规则**

重点覆盖：
- parent 按 `section_path` 组织
- 同一 section 过长时在段落边界软拆分
- child 按语义元素拼接，不按固定页或视觉换行切
- child 目标长度 `300 - 700`，超长再切，过短可合并

- [ ] **步骤 2：实现 parent 生成**

约束：
- 忽略 `page_header / page_footer`
- 遇到新的同级或更高层标题结束当前 parent
- parent 目标长度 `1500 - 3000`

- [ ] **步骤 3：实现 child 生成**

约束：
- 主拼接单元：`paragraph / list_item / table_caption / figure_caption`
- `title` 只作为上下文前缀，不单独成为 child
- 轻量 element 级 overlap，避免字符级滑窗

- [ ] **步骤 4：运行测试，确认 chunk 规则通过**

运行：`python -m unittest tests.unit.test_pdf_chunking -v`

### 任务 5：明确 table 在 chunking 里的首版角色

**文件：**
- Modify: `backend/src/finsight_agent/capabilities/retrieval/chunking.py`
- Test: `tests/unit/test_pdf_chunking.py`

- [ ] **步骤 1：先写失败测试，明确 table 不直接进入普通 child**

需要覆盖：
- `table` 本体单独存在于 `tables.jsonl`
- `table_caption` 可以进入 child
- 相邻解释文字可以进入 child
- `related_table_id` 能保留回连关系

- [ ] **步骤 2：实现 table-aware 的最小 chunk 行为**

首版约束：
- 不把整张表文本直接塞进普通 `children.jsonl`
- 保留未来 `table-aware retrieval` 和结构化指标抽取扩展点

- [ ] **步骤 3：运行测试，确认通过**

运行：`python -m unittest tests.unit.test_pdf_chunking -v`

### 任务 6：实现 chunk 产物落盘与失败报告

**文件：**
- Modify: `backend/src/finsight_agent/capabilities/retrieval/parsed_storage.py`
- Modify: `backend/src/finsight_agent/capabilities/retrieval/chunking.py`
- Test: `tests/integration/test_pdf_parsing_artifacts.py`

- [ ] **步骤 1：先写失败测试，明确 `chunked_filings/` 目录结构**

需要覆盖：
- `parents.jsonl`
- `children.jsonl`
- `chunk_report.json`

- [ ] **步骤 2：实现落盘**

约束：
- 目录：`var/data/chunked_filings/<document_id>/`
- 同一文档重跑直接覆盖
- `chunk_report` 记录：
  - `chunker_version`
  - `parent_count`
  - `child_count`
  - `generated_at`
  - `warnings`

- [ ] **步骤 3：运行测试，确认通过**

运行：`python -m unittest tests.integration.test_pdf_parsing_artifacts -v`

### 任务 7：跑真实 PDF spot check 并完成首版验收

**文件：**
- 无新增文件要求，可在现有测试或脚本基础上补最小辅助代码

- [ ] **步骤 1：选择真实样本文档做 spot check**

建议至少覆盖：
- 一份年报
- 一份半年报
- 一份重要公告

- [ ] **步骤 2：跑通解析与 chunking**

验收项：
- `document.json / elements.jsonl / parse_report.json` 一定生成
- 大部分文档有 `tables.jsonl`
- `parents.jsonl / children.jsonl / chunk_report.json` 稳定生成

- [ ] **步骤 3：人工检查**

检查：
- 标题路径是否合理
- child 是否明显过碎或过粗
- 表题与表格关联是否保住
- citation 基础页码字段是否基本可追溯

- [ ] **步骤 4：全量测试**

运行：`python -m unittest discover -s tests -p 'test*.py'`

- [ ] **步骤 5：提交**

建议 commit message：

```bash
git commit -m "实现本地PDF解析与父子块切分骨架"
```

---

## 完成定义

本计划完成后，应满足：

- 已下载的本地 PDF 能稳定进入解析层
- 解析产物按统一 schema 落盘
- chunking 作为唯一切分层稳定生成 parent / child
- table 已被结构化保存，并与文本链路保持关联
- spot check 能验证结构和页码追溯性基本合理
- 全量测试通过
