# Structured Market Data Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `metric_lookup` 从本地财报表格和外部兜底来源返回真实结构化指标，而不再返回 `TODO`。

**Architecture:** 先在 `structured_data` 模块内部补齐统一数据模型、本地指标仓储、表格抽取器和离线构建器，形成“财报表格 -> 内部指标库 -> 查询 service”的本地闭环；再在 `StructuredDataService` 上叠加外部 provider 抽象与 fallback 语义，并同步补齐 brief answer 的降级输出与端到端测试。

**Tech Stack:** Python 3、`unittest`、标准库 `json` / `pathlib` / `dataclasses` / `tempfile`、现有 retrieval parsing models、现有 orchestrator / reporting service、可选 `akshare`

---

## 文件结构

### 新增文件

- `backend/src/finsight_agent/capabilities/structured_data/repository.py`
  负责本地指标记录的读写与最佳匹配查询。
- `backend/src/finsight_agent/capabilities/structured_data/normalizer.py`
  负责指标别名、期间、数值、单位的规则归一化。
- `backend/src/finsight_agent/capabilities/structured_data/extractor.py`
  负责从 `ParsedTable` 抽取 `MetricRecord`。
- `backend/src/finsight_agent/capabilities/structured_data/builder.py`
  负责扫描已解析财报产物并重建本地指标库。
- `backend/src/finsight_agent/capabilities/structured_data/providers.py`
  负责外部 provider 抽象与默认 no-op provider。
- `tests/unit/test_structured_data_models.py`
  覆盖内部模型默认值与来源字段。
- `tests/unit/test_metric_repository.py`
  覆盖本地指标仓储的读写、精确匹配、`latest` 匹配。
- `tests/unit/test_metric_extractor.py`
  覆盖表格指标抽取与规则归一化。
- `tests/unit/test_metric_builder.py`
  覆盖从解析产物目录重建本地指标库。
- `tests/unit/test_structured_data_service.py`
  覆盖本地优先、外部兜底、显式降级。
- `tests/integration/test_metric_lookup_structured_data.py`
  覆盖 `metric_lookup` 端到端真实数值返回。

### 修改文件

- `backend/src/finsight_agent/capabilities/structured_data/models.py`
  从占位文件改为真实数据模型。
- `backend/src/finsight_agent/capabilities/structured_data/service.py`
  从 `TODO` 占位实现改为本地优先 + 外部兜底查询。
- `backend/src/finsight_agent/control_plane/orchestrator/stage_runners/query_structured_data.py`
  继续沿用现有接口，但要允许透出更多结构化字段。
- `backend/src/finsight_agent/control_plane/orchestrator/stage_runners/synthesize_brief_answer.py`
  让成功态与降级态都能生成自然的简答。
- `tests/integration/test_metric_lookup_placeholder.py`
  迁移或替换为真实结构化数据集成测试。
- `docs/finsight/project-status.md`
  同步 `structured-market-data-support` 的阶段状态。
- `docs/finsight/modules/data-evidence-status.md`
  同步本地指标库与 external fallback 的进度。

## 任务 1：补齐结构化数据内部模型

**Files:**
- Modify: `backend/src/finsight_agent/capabilities/structured_data/models.py`
- Test: `tests/unit/test_structured_data_models.py`

- [ ] **Step 1: 先写失败测试，锁定模型字段与默认值**

```python
from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.structured_data.models import (
    MetricLookupResult,
    MetricQuery,
    MetricRecord,
)


class StructuredDataModelsTest(unittest.TestCase):
    def test_metric_query_defaults_to_allow_external_fallback(self) -> None:
        query = MetricQuery(
            company_name="宁德时代",
            metric_name="net_profit",
            time_scope="2024_annual",
        )

        self.assertEqual(query.company_name, "宁德时代")
        self.assertTrue(query.allow_external_fallback)

    def test_metric_record_keeps_source_trace_fields(self) -> None:
        record = MetricRecord(
            company_name="宁德时代",
            company_code="300750",
            metric_name="net_profit",
            metric_label="归属于上市公司股东的净利润",
            time_scope="2024_annual",
            period_end="2024-12-31",
            value="507.45",
            unit="亿元",
            currency="CNY",
            source_type="local_filing_table",
            source_document_id="300750_annual_report_2024_20250315",
            source_table_id="table_000001",
            source_caption="主要会计数据",
            confidence="high",
        )

        self.assertEqual(record.source_type, "local_filing_table")
        self.assertEqual(record.source_table_id, "table_000001")

    def test_metric_lookup_result_supports_degraded_response(self) -> None:
        result = MetricLookupResult.degraded(
            company_name="宁德时代",
            metric_name="revenue",
            time_scope="2025_annual",
            notes=["当前未找到对应期间数据"],
        )

        self.assertTrue(result.is_degraded)
        self.assertEqual(result.value, "")
        self.assertIn("当前未找到对应期间数据", result.notes)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试，确认当前失败**

Run: `python -m unittest tests.unit.test_structured_data_models -v`

Expected: FAIL，报 `ImportError` 或 `AttributeError`，因为 `models.py` 仍是占位文件。

- [ ] **Step 3: 写最小实现，定义内部查询 / 记录 / 结果模型**

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class MetricQuery:
    """结构化指标查询的内部标准对象。"""

    company_name: str
    metric_name: str
    time_scope: str
    allow_external_fallback: bool = True


@dataclass(slots=True)
class MetricRecord:
    """本地指标库中的标准记录。"""

    company_name: str
    company_code: str
    metric_name: str
    metric_label: str
    time_scope: str
    period_end: str
    value: str
    unit: str
    currency: str
    source_type: str
    source_document_id: str
    source_table_id: str
    source_caption: str
    confidence: str


@dataclass(slots=True)
class MetricLookupResult:
    """统一结构化指标查询结果。"""

    company_name: str
    metric_name: str
    time_scope: str
    value: str
    unit: str
    source_type: str
    source_summary: str
    matched_by: str
    confidence: str
    is_degraded: bool = False
    notes: list[str] = field(default_factory=list)

    @classmethod
    def degraded(
        cls,
        *,
        company_name: str,
        metric_name: str,
        time_scope: str,
        notes: list[str],
    ) -> "MetricLookupResult":
        return cls(
            company_name=company_name,
            metric_name=metric_name,
            time_scope=time_scope,
            value="",
            unit="",
            source_type="unavailable",
            source_summary="",
            matched_by="none",
            confidence="low",
            is_degraded=True,
            notes=notes,
        )
```

- [ ] **Step 4: 重新运行测试，确认通过**

Run: `python -m unittest tests.unit.test_structured_data_models -v`

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/src/finsight_agent/capabilities/structured_data/models.py tests/unit/test_structured_data_models.py
git commit -m "test: 补齐结构化数据内部模型"
```

## 任务 2：实现本地指标仓储与查询匹配

**Files:**
- Create: `backend/src/finsight_agent/capabilities/structured_data/repository.py`
- Test: `tests/unit/test_metric_repository.py`

- [ ] **Step 1: 先写失败测试，锁定本地仓储的查询行为**

```python
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.structured_data.models import MetricQuery, MetricRecord
from finsight_agent.capabilities.structured_data.repository import MetricRepository


class MetricRepositoryTest(unittest.TestCase):
    def test_find_exact_time_scope_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = MetricRepository(storage_dir=temp_dir)
            repository.save_records(
                [
                    MetricRecord(
                        company_name="宁德时代",
                        company_code="300750",
                        metric_name="net_profit",
                        metric_label="归母净利润",
                        time_scope="2024_annual",
                        period_end="2024-12-31",
                        value="507.45",
                        unit="亿元",
                        currency="CNY",
                        source_type="local_filing_table",
                        source_document_id="doc_001",
                        source_table_id="table_001",
                        source_caption="主要会计数据",
                        confidence="high",
                    )
                ]
            )

            result = repository.find_best_match(
                MetricQuery(
                    company_name="宁德时代",
                    metric_name="net_profit",
                    time_scope="2024_annual",
                )
            )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.value, "507.45")

    def test_find_latest_returns_latest_available_period(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = MetricRepository(storage_dir=temp_dir)
            repository.save_records(
                [
                    MetricRecord(
                        company_name="宁德时代",
                        company_code="300750",
                        metric_name="revenue",
                        metric_label="营业收入",
                        time_scope="2023_annual",
                        period_end="2023-12-31",
                        value="400.92",
                        unit="亿元",
                        currency="CNY",
                        source_type="local_filing_table",
                        source_document_id="doc_2023",
                        source_table_id="table_2023",
                        source_caption="主要会计数据",
                        confidence="high",
                    ),
                    MetricRecord(
                        company_name="宁德时代",
                        company_code="300750",
                        metric_name="revenue",
                        metric_label="营业收入",
                        time_scope="2024_annual",
                        period_end="2024-12-31",
                        value="512.30",
                        unit="亿元",
                        currency="CNY",
                        source_type="local_filing_table",
                        source_document_id="doc_2024",
                        source_table_id="table_2024",
                        source_caption="主要会计数据",
                        confidence="high",
                    ),
                ]
            )

            result = repository.find_best_match(
                MetricQuery(
                    company_name="宁德时代",
                    metric_name="revenue",
                    time_scope="latest",
                )
            )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.time_scope, "2024_annual")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m unittest tests.unit.test_metric_repository -v`

Expected: FAIL，报 `ModuleNotFoundError`，因为 `repository.py` 尚不存在。

- [ ] **Step 3: 实现文件型指标仓储**

```python
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .models import MetricQuery, MetricRecord


class MetricRepository:
    """基于本地 JSONL 的轻量指标仓储。"""

    def __init__(self, storage_dir: str | Path) -> None:
        self._storage_dir = Path(storage_dir)
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._records_path = self._storage_dir / "metric_records.jsonl"

    def save_records(self, records: list[MetricRecord]) -> None:
        with self._records_path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    def load_records(self) -> list[MetricRecord]:
        if not self._records_path.exists():
            return []
        records: list[MetricRecord] = []
        with self._records_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                records.append(MetricRecord(**json.loads(stripped)))
        return records

    def find_best_match(self, query: MetricQuery) -> MetricRecord | None:
        candidates = [
            record
            for record in self.load_records()
            if record.company_name == query.company_name and record.metric_name == query.metric_name
        ]
        if not candidates:
            return None
        if query.time_scope != "latest":
            for record in candidates:
                if record.time_scope == query.time_scope:
                    return record
            return None
        return sorted(candidates, key=lambda item: item.period_end, reverse=True)[0]
```

- [ ] **Step 4: 重新运行测试，确认通过**

Run: `python -m unittest tests.unit.test_metric_repository -v`

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/src/finsight_agent/capabilities/structured_data/repository.py tests/unit/test_metric_repository.py
git commit -m "feat: 增加本地结构化指标仓储"
```

## 任务 3：实现指标归一化与表格抽取器

**Files:**
- Create: `backend/src/finsight_agent/capabilities/structured_data/normalizer.py`
- Create: `backend/src/finsight_agent/capabilities/structured_data/extractor.py`
- Test: `tests/unit/test_metric_extractor.py`

- [ ] **Step 1: 先写失败测试，锁定从表格抽取核心指标的规则**

```python
from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.retrieval.parsing_models import ParsedTable
from finsight_agent.capabilities.structured_data.extractor import MetricExtractor


class MetricExtractorTest(unittest.TestCase):
    def test_extract_annual_revenue_and_net_profit_from_main_financial_table(self) -> None:
        table = ParsedTable(
            table_id="table_001",
            document_id="300750_annual_report_2024_20250315",
            page_start=12,
            page_end=12,
            order_in_document=1,
            section_path=["第二节 公司简介和主要财务指标"],
            caption_text="主要会计数据",
            table_text="营业收入 512.30 归属于上市公司股东的净利润 507.45",
            table_markdown=(
                "| 指标 | 2024年 | 2023年 |\n"
                "| 营业收入 | 512.30 | 400.92 |\n"
                "| 归属于上市公司股东的净利润 | 507.45 | 441.21 |"
            ),
            parser_source="pdfplumber",
        )

        records = MetricExtractor().extract_from_tables(
            company_name="宁德时代",
            company_code="300750",
            doc_type="annual_report",
            report_year=2024,
            tables=[table],
        )

        self.assertEqual({record.metric_name for record in records}, {"revenue", "net_profit"})
        self.assertEqual(records[0].time_scope, "2024_annual")
        revenue_record = next(record for record in records if record.metric_name == "revenue")
        self.assertEqual(revenue_record.value, "512.30")
        self.assertEqual(revenue_record.source_table_id, "table_001")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m unittest tests.unit.test_metric_extractor -v`

Expected: FAIL，报 `ModuleNotFoundError`，因为 `extractor.py` 和 `normalizer.py` 尚不存在。

- [ ] **Step 3: 实现指标别名、期间和值的规则归一化**

```python
from __future__ import annotations

from decimal import Decimal, InvalidOperation


_METRIC_ALIASES = {
    "营业收入": "revenue",
    "归属于上市公司股东的净利润": "net_profit",
    "归母净利润": "net_profit",
    "扣除非经常性损益后的净利润": "deducted_net_profit",
    "经营活动产生的现金流量净额": "operating_cash_flow",
}


def normalize_metric_name(label: str) -> str | None:
    return _METRIC_ALIASES.get(label.strip())


def normalize_time_scope(*, doc_type: str, report_year: int) -> str:
    if doc_type == "annual_report":
        return f"{report_year}_annual"
    if doc_type == "semiannual_report":
        return f"{report_year}_semiannual"
    return "latest"


def normalize_numeric_text(raw_value: str) -> str:
    cleaned = raw_value.strip().replace(",", "").replace(" ", "")
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = f"-{cleaned[1:-1]}"
    try:
        return format(Decimal(cleaned), "f")
    except InvalidOperation:
        return cleaned
```

- [ ] **Step 4: 实现从 `ParsedTable` 抽取 `MetricRecord`**

```python
from __future__ import annotations

from finsight_agent.capabilities.retrieval.parsing_models import ParsedTable

from .models import MetricRecord
from .normalizer import normalize_metric_name, normalize_numeric_text, normalize_time_scope


class MetricExtractor:
    """从财报表格中提取首版核心指标。"""

    def extract_from_tables(
        self,
        *,
        company_name: str,
        company_code: str,
        doc_type: str,
        report_year: int,
        tables: list[ParsedTable],
    ) -> list[MetricRecord]:
        time_scope = normalize_time_scope(doc_type=doc_type, report_year=report_year)
        records: list[MetricRecord] = []

        for table in tables:
            markdown_lines = [line.strip() for line in table.table_markdown.splitlines() if line.strip()]
            if len(markdown_lines) < 3:
                continue
            for line in markdown_lines[2:]:
                cells = [cell.strip() for cell in line.strip("|").split("|")]
                if len(cells) < 2:
                    continue
                metric_label = cells[0]
                metric_name = normalize_metric_name(metric_label)
                if metric_name is None:
                    continue
                value = normalize_numeric_text(cells[1])
                records.append(
                    MetricRecord(
                        company_name=company_name,
                        company_code=company_code,
                        metric_name=metric_name,
                        metric_label=metric_label,
                        time_scope=time_scope,
                        period_end=f"{report_year}-12-31" if doc_type == "annual_report" else f"{report_year}-06-30",
                        value=value,
                        unit="亿元",
                        currency="CNY",
                        source_type="local_filing_table",
                        source_document_id=table.document_id,
                        source_table_id=table.table_id,
                        source_caption=table.caption_text,
                        confidence="high",
                    )
                )
        return records
```

- [ ] **Step 5: 重新运行测试，确认通过**

Run: `python -m unittest tests.unit.test_metric_extractor -v`

Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add backend/src/finsight_agent/capabilities/structured_data/normalizer.py backend/src/finsight_agent/capabilities/structured_data/extractor.py tests/unit/test_metric_extractor.py
git commit -m "feat: 增加财报表格指标抽取器"
```

## 任务 4：实现离线指标库构建器

**Files:**
- Create: `backend/src/finsight_agent/capabilities/structured_data/builder.py`
- Test: `tests/unit/test_metric_builder.py`

- [ ] **Step 1: 先写失败测试，锁定从解析产物目录重建指标库的行为**

```python
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.structured_data.builder import StructuredMetricIndexBuilder
from finsight_agent.capabilities.structured_data.repository import MetricRepository


class MetricBuilderTest(unittest.TestCase):
    def test_rebuild_reads_tables_jsonl_and_writes_metric_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            parsed_root = Path(temp_dir) / "parsed"
            storage_root = Path(temp_dir) / "metric_store"
            filing_dir = parsed_root / "300750_宁德时代" / "annual" / "2024"
            filing_dir.mkdir(parents=True)

            (filing_dir / "document.json").write_text(
                json.dumps(
                    {
                        "document_id": "300750_annual_report_2024_20250315",
                        "company_name": "宁德时代",
                        "company_code": "300750",
                        "doc_type": "annual_report",
                        "report_year": 2024,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (filing_dir / "tables.jsonl").write_text(
                json.dumps(
                    {
                        "table_id": "table_001",
                        "document_id": "300750_annual_report_2024_20250315",
                        "page_start": 12,
                        "page_end": 12,
                        "order_in_document": 1,
                        "section_path": ["第二节 公司简介和主要财务指标"],
                        "caption_text": "主要会计数据",
                        "table_text": "营业收入 512.30",
                        "table_markdown": "| 指标 | 2024年 |\\n| --- | --- |\\n| 营业收入 | 512.30 |",
                        "parser_source": "pdfplumber",
                    },
                    ensure_ascii=False,
                ) + "\n",
                encoding="utf-8",
            )

            builder = StructuredMetricIndexBuilder(parsed_filings_root=parsed_root, storage_dir=storage_root)
            builder.rebuild()
            records = MetricRepository(storage_dir=storage_root).load_records()

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].metric_name, "revenue")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m unittest tests.unit.test_metric_builder -v`

Expected: FAIL，报 `ModuleNotFoundError`。

- [ ] **Step 3: 实现离线构建器**

```python
from __future__ import annotations

import json
from pathlib import Path

from finsight_agent.capabilities.retrieval.parsing_models import ParsedTable

from .extractor import MetricExtractor
from .repository import MetricRepository


class StructuredMetricIndexBuilder:
    """扫描已解析财报目录并重建本地指标库。"""

    def __init__(self, *, parsed_filings_root: str | Path, storage_dir: str | Path) -> None:
        self._parsed_filings_root = Path(parsed_filings_root)
        self._repository = MetricRepository(storage_dir=storage_dir)
        self._extractor = MetricExtractor()

    def rebuild(self) -> None:
        records = []
        for document_path in self._parsed_filings_root.rglob("document.json"):
            tables_path = document_path.with_name("tables.jsonl")
            if not tables_path.exists():
                continue
            document_payload = json.loads(document_path.read_text(encoding="utf-8"))
            tables: list[ParsedTable] = []
            for line in tables_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                tables.append(ParsedTable(**json.loads(line)))
            records.extend(
                self._extractor.extract_from_tables(
                    company_name=str(document_payload["company_name"]),
                    company_code=str(document_payload["company_code"]),
                    doc_type=str(document_payload["doc_type"]),
                    report_year=int(document_payload["report_year"]),
                    tables=tables,
                )
            )
        self._repository.save_records(records)
```

- [ ] **Step 4: 重新运行测试，确认通过**

Run: `python -m unittest tests.unit.test_metric_builder -v`

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/src/finsight_agent/capabilities/structured_data/builder.py tests/unit/test_metric_builder.py
git commit -m "feat: 增加本地指标库离线构建器"
```

## 任务 5：让 `StructuredDataService` 走通本地真实查询并改造简答输出

**Files:**
- Modify: `backend/src/finsight_agent/capabilities/structured_data/service.py`
- Modify: `backend/src/finsight_agent/control_plane/orchestrator/stage_runners/synthesize_brief_answer.py`
- Test: `tests/unit/test_structured_data_service.py`

- [ ] **Step 1: 先写失败测试，锁定本地命中与降级输出**

```python
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.structured_data.models import MetricRecord
from finsight_agent.capabilities.structured_data.repository import MetricRepository
from finsight_agent.capabilities.structured_data.service import StructuredDataService


class StructuredDataServiceTest(unittest.TestCase):
    def test_query_metric_lookup_reads_local_metric_record_first(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = MetricRepository(storage_dir=temp_dir)
            repository.save_records(
                [
                    MetricRecord(
                        company_name="宁德时代",
                        company_code="300750",
                        metric_name="net_profit",
                        metric_label="归母净利润",
                        time_scope="2024_annual",
                        period_end="2024-12-31",
                        value="507.45",
                        unit="亿元",
                        currency="CNY",
                        source_type="local_filing_table",
                        source_document_id="doc_001",
                        source_table_id="table_001",
                        source_caption="主要会计数据",
                        confidence="high",
                    )
                ]
            )
            service = StructuredDataService(metric_repository=repository)

            result = service.query_metric_lookup(
                company="宁德时代",
                metric="net_profit",
                time_scope="2024_annual",
            )

        self.assertEqual(result["value"], "507.45")
        self.assertEqual(result["source_type"], "local_filing_table")
        self.assertFalse(result["is_degraded"])

    def test_query_metric_lookup_returns_degraded_result_when_no_source_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = StructuredDataService(metric_repository=MetricRepository(storage_dir=temp_dir))
            result = service.query_metric_lookup(
                company="宁德时代",
                metric="operating_cash_flow",
                time_scope="2025_annual",
            )

        self.assertTrue(result["is_degraded"])
        self.assertEqual(result["value"], "")
        self.assertIn("当前未找到对应指标数据", result["notes"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m unittest tests.unit.test_structured_data_service -v`

Expected: FAIL，因为 `StructuredDataService` 还没有本地仓储与降级语义。

- [ ] **Step 3: 实现本地优先查询**

```python
from __future__ import annotations

from pathlib import Path

from shared.contracts.final_response import FinalResponse
from shared.enums.response_type import ResponseType

from .models import MetricLookupResult, MetricQuery
from .providers import ExternalMetricProvider, NullExternalMetricProvider
from .repository import MetricRepository


class StructuredDataService:
    """metric_lookup 使用的结构化指标查询能力。"""

    def __init__(
        self,
        *,
        metric_repository: MetricRepository | None = None,
        external_provider: ExternalMetricProvider | None = None,
        storage_dir: str | Path = "runtime/structured_data",
    ) -> None:
        self._repository = metric_repository or MetricRepository(storage_dir=storage_dir)
        self._external_provider = external_provider or NullExternalMetricProvider()

    def query_metric_lookup(self, company: str, metric: str, time_scope: str) -> dict[str, object]:
        query = MetricQuery(company_name=company, metric_name=metric, time_scope=time_scope)
        record = self._repository.find_best_match(query)
        if record is not None:
            result = MetricLookupResult(
                company_name=record.company_name,
                metric_name=record.metric_name,
                time_scope=record.time_scope,
                value=record.value,
                unit=record.unit,
                source_type=record.source_type,
                source_summary=f"{record.source_document_id} / {record.source_caption}",
                matched_by="local_repository",
                confidence=record.confidence,
            )
            return result.__dict__
        degraded = MetricLookupResult.degraded(
            company_name=company,
            metric_name=metric,
            time_scope=time_scope,
            notes=["当前未找到对应指标数据"],
        )
        return degraded.__dict__

    def to_brief_response(self, session_id: str, summary: str) -> FinalResponse:
        return FinalResponse(
            response_type=ResponseType.SUCCESS.value,
            session_id=session_id,
            summary=summary,
        )
```

- [ ] **Step 4: 改造 brief answer，让降级态不再拼出空值句子**

```python
structured_result = dict(stage_result.output_payload.get("structured_result", {}))

company = str(structured_result.get("company", "")).strip()
metric = str(structured_result.get("metric", "")).strip()
time_scope = str(structured_result.get("time_scope", "")).strip()
value = str(structured_result.get("value", "")).strip()
is_degraded = bool(structured_result.get("is_degraded", False))
notes = [str(item) for item in structured_result.get("notes", [])]

if is_degraded:
    note_text = "；".join(notes) if notes else "当前未找到对应指标数据。"
    summary = f"{company}{time_scope}{metric}暂未命中结构化数据。{note_text}"
else:
    unit = str(structured_result.get("unit", "")).strip()
    summary = f"{company}{time_scope}{metric}为{value}{unit}。"
```

- [ ] **Step 5: 重新运行测试，确认通过**

Run: `python -m unittest tests.unit.test_structured_data_service -v`

Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add backend/src/finsight_agent/capabilities/structured_data/service.py backend/src/finsight_agent/control_plane/orchestrator/stage_runners/synthesize_brief_answer.py tests/unit/test_structured_data_service.py
git commit -m "feat: 打通本地结构化指标查询路径"
```

## 任务 6：增加外部 provider 抽象与 fallback 行为

**Files:**
- Create: `backend/src/finsight_agent/capabilities/structured_data/providers.py`
- Modify: `backend/src/finsight_agent/capabilities/structured_data/service.py`
- Test: `tests/unit/test_structured_data_service.py`

- [ ] **Step 1: 先补失败测试，锁定本地未命中时的 external fallback**

```python
class _StubExternalMetricProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def lookup_metric(self, company_name: str, metric_name: str, time_scope: str) -> dict[str, object] | None:
        self.calls.append((company_name, metric_name, time_scope))
        return {
            "company_name": company_name,
            "metric_name": metric_name,
            "time_scope": time_scope,
            "value": "520.01",
            "unit": "亿元",
            "source_type": "external_api",
            "source_summary": "stub_external_provider",
            "matched_by": "external_provider",
            "confidence": "medium",
            "is_degraded": False,
            "notes": ["结果来自外部指标接口"],
        }


def test_query_metric_lookup_uses_external_provider_after_local_miss(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        provider = _StubExternalMetricProvider()
        service = StructuredDataService(
            metric_repository=MetricRepository(storage_dir=temp_dir),
            external_provider=provider,
        )

        result = service.query_metric_lookup(
            company="宁德时代",
            metric="revenue",
            time_scope="2025_annual",
        )

    self.assertEqual(result["source_type"], "external_api")
    self.assertEqual(provider.calls, [("宁德时代", "revenue", "2025_annual")])
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m unittest tests.unit.test_structured_data_service -v`

Expected: FAIL，因为 service 还不会回退外部 provider。

- [ ] **Step 3: 定义 provider 抽象与默认 no-op provider**

```python
from __future__ import annotations

from typing import Protocol


class ExternalMetricProvider(Protocol):
    def lookup_metric(
        self,
        company_name: str,
        metric_name: str,
        time_scope: str,
    ) -> dict[str, object] | None: ...


class NullExternalMetricProvider:
    """默认外部 provider，占位但不访问网络。"""

    def lookup_metric(
        self,
        company_name: str,
        metric_name: str,
        time_scope: str,
    ) -> dict[str, object] | None:
        return None
```

- [ ] **Step 4: 在 service 里加入外部兜底逻辑**

```python
record = self._repository.find_best_match(query)
if record is not None:
    ...

if query.allow_external_fallback:
    external_result = self._external_provider.lookup_metric(
        company_name=company,
        metric_name=metric,
        time_scope=time_scope,
    )
    if external_result is not None:
        external_result.setdefault("notes", [])
        external_result["notes"] = [
            str(item) for item in external_result.get("notes", [])
        ] + ["结果来自外部指标接口，非本地财报抽取"]
        return external_result
```

- [ ] **Step 5: 重新运行测试，确认通过**

Run: `python -m unittest tests.unit.test_structured_data_service -v`

Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add backend/src/finsight_agent/capabilities/structured_data/providers.py backend/src/finsight_agent/capabilities/structured_data/service.py tests/unit/test_structured_data_service.py
git commit -m "feat: 增加结构化指标外部兜底查询"
```

## 任务 7：补端到端集成测试并同步状态文档

**Files:**
- Create: `tests/integration/test_metric_lookup_structured_data.py`
- Modify: `tests/integration/test_metric_lookup_placeholder.py`
- Modify: `docs/finsight/project-status.md`
- Modify: `docs/finsight/modules/data-evidence-status.md`

- [ ] **Step 1: 先写失败测试，锁定 `metric_lookup` 不再返回 `TODO`**

```python
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.structured_data.models import MetricRecord
from finsight_agent.capabilities.structured_data.repository import MetricRepository
from finsight_agent.capabilities.structured_data.service import StructuredDataService
from finsight_agent.workbench_backend_api.service import WorkbenchBackendApiService
from shared.contracts.analysis_request import AnalysisRequest


class MetricLookupStructuredDataIntegrationTest(unittest.TestCase):
    def test_metric_lookup_returns_real_metric_value_instead_of_todo(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = MetricRepository(storage_dir=temp_dir)
            repository.save_records(
                [
                    MetricRecord(
                        company_name="宁德时代",
                        company_code="300750",
                        metric_name="net_profit",
                        metric_label="归母净利润",
                        time_scope="2024_annual",
                        period_end="2024-12-31",
                        value="507.45",
                        unit="亿元",
                        currency="CNY",
                        source_type="local_filing_table",
                        source_document_id="doc_001",
                        source_table_id="table_001",
                        source_caption="主要会计数据",
                        confidence="high",
                    )
                ]
            )
            service = WorkbenchBackendApiService(
                orchestrator_service=None,
                structured_data_service=StructuredDataService(metric_repository=repository),
            )

            envelope = service.build_response(
                AnalysisRequest(query="宁德时代 2024 年净利润是多少？")
            )

        self.assertNotIn("TODO", envelope.response.summary)
        self.assertIn("507.45", envelope.response.summary)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试，确认当前失败**

Run: `python -m unittest tests.integration.test_metric_lookup_structured_data -v`

Expected: FAIL，因为 `WorkbenchBackendApiService` 目前未必支持直接注入 `structured_data_service`，或者集成路径仍使用旧默认实现。

- [ ] **Step 3: 补齐入口接线或测试注入点，并更新状态文档**

```python
# WorkbenchBackendApiService.__init__(...)
self._orchestrator_service = orchestrator_service or OrchestratorService(
    structured_data_service=structured_data_service,
    ...
)
```

```markdown
| `structured-market-data-support` | 进行中 | 已完成本地指标库闭环，外部 fallback 首版接入 |
```

- [ ] **Step 4: 运行关键回归，确认通过**

Run: `python -m unittest tests.unit.test_structured_data_models tests.unit.test_metric_repository tests.unit.test_metric_extractor tests.unit.test_metric_builder tests.unit.test_structured_data_service tests.integration.test_metric_lookup_structured_data -v`

Expected: PASS

Run: `python -m unittest tests.unit.test_semantic_routing_and_planning tests.unit.test_orchestrator_service tests.unit.test_orchestrator_stage_runners tests.unit.test_trace_builder tests.unit.test_session_repository tests.unit.test_session_context_extractor tests.unit.test_workbench_session_flow tests.unit.test_project_skeleton tests.integration.test_metric_lookup_structured_data -v`

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tests/integration/test_metric_lookup_structured_data.py tests/integration/test_metric_lookup_placeholder.py docs/finsight/project-status.md docs/finsight/modules/data-evidence-status.md backend/src/finsight_agent/workbench_backend_api/service.py
git commit -m "feat: 打通结构化市场数据首版闭环"
```

## 自查清单

- [ ] `MetricLookupResult` 是否统一承载本地命中、外部命中和显式降级
- [ ] 本地仓储是否只承担存取和匹配，不混入抽取逻辑
- [ ] 表格抽取是否保持 deterministic，不引入 LLM
- [ ] `StructuredDataService` 是否做到本地优先，外部仅兜底
- [ ] brief answer 是否能正确表达降级态，而不是拼接出空值句子
- [ ] 集成测试是否验证“真实数值替代 TODO”
- [ ] 状态文档是否与实现进度同步

