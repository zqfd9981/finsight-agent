# 本地 PDF 语料采集实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 为半导体样本股池建立首版可运行的本地 PDF 语料采集链路，覆盖 manifest 读取、按数据源发现披露列表、文档筛选、PDF 下载，以及试点公司覆盖率输出。

**架构：** 在 `capabilities/retrieval` 下新增一层聚焦“语料采集”的实现：读取 YAML 样本股池，按市场选择对应 adapter，将不同来源的披露元数据统一成同一种内部记录结构，筛选年报、半年报和三类重要公告，下载到约定目录，并写出采集状态供后续 retrieval ingestion 使用。要把 source adapter、筛选规则、文件存储、覆盖率汇总拆开，避免后面调 `CNInfo/SSE` 时污染上层流程。

**技术栈：** Python 3、`unittest`、标准库 `urllib` 优先、现有 YAML 配置加载、基于文件系统的 manifest / 状态快照；SQLite 状态落盘放到试点下载跑通之后再接。

---

## 文件结构

### 新增文件
- `backend/src/finsight_agent/capabilities/retrieval/acquisition_models.py`
  定义 manifest 记录、披露文档记录、筛选结果、下载结果、覆盖率摘要等对象。
- `backend/src/finsight_agent/capabilities/retrieval/corpus_manifest.py`
  负责读取 `semiconductor_sample_universe.yaml`、校验必填字段、支持按公司子集选择。
- `backend/src/finsight_agent/capabilities/retrieval/filing_filters.py`
  编码年报、半年报、重要公告三类筛选规则。
- `backend/src/finsight_agent/capabilities/retrieval/storage.py`
  负责输出目录解析、规范文件名生成、PDF 原子写入、JSON 状态快照写入。
- `backend/src/finsight_agent/capabilities/retrieval/acquisition_service.py`
  编排 manifest 读取、adapter 分发、筛选、下载执行、覆盖率汇总。
- `backend/src/finsight_agent/infra/external/sse_filings.py`
  实现 `SSE` 列表发现 adapter，并把返回结果标准化成内部 `FilingRecord`。
- `backend/src/finsight_agent/infra/external/cninfo_filings.py`
  实现 `CNInfo` 列表发现 adapter，并把返回结果标准化成内部 `FilingRecord`。
- `tests/unit/test_pdf_corpus_manifest.py`
  覆盖 manifest 解析和样本公司选择。
- `tests/unit/test_filing_filters.py`
  覆盖年报 / 半年报 / 公告筛选规则。
- `tests/unit/test_pdf_corpus_acquisition_service.py`
  覆盖采集服务编排行为，使用 fake adapter 和 fake downloader。
- `tests/integration/test_pdf_corpus_storage_layout.py`
  覆盖真实输出路径、命名规则和状态快照文件。

### 修改文件
- `backend/src/finsight_agent/capabilities/retrieval/service.py`
  暴露一个很薄的公开入口，用于构造采集服务，但不把它和 retrieval 主执行逻辑混在一起。
- `backend/src/finsight_agent/capabilities/retrieval/models.py`
  如果当前包已有统一导出习惯，则补充导出 acquisition 模型；如果没有，就保持兼容薄层。
- `config/app.yaml`
  增加 retrieval 语料采集相关路径和试点默认值，不改现有 control-plane 配置。
- `backend/src/finsight_agent/config/settings.py`
  增加 retrieval acquisition 配置加载和类型化封装。

### 实现前需要阅读的现有文件
- `docs/superpowers/specs/2026-06-30-pdf-corpus-acquisition-design.md`
- `docs/superpowers/specs/2026-06-30-local-pdf-rag-design.md`
- `var/data/corpus_manifests/semiconductor_sample_universe.yaml`
- `shared/contracts/evidence_bundle.py`
- `shared/contracts/stage_observation.py`

---

### 任务 1：补充采集配置与公共数据模型

**文件：**
- Create: `backend/src/finsight_agent/capabilities/retrieval/acquisition_models.py`
- Modify: `backend/src/finsight_agent/config/settings.py`
- Modify: `config/app.yaml`
- Test: `tests/unit/test_pdf_corpus_manifest.py`

- [ ] **步骤 1：先写失败的配置与模型测试**

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

from finsight_agent.config.settings import load_settings


class PdfCorpusSettingsTest(unittest.TestCase):
    def test_load_settings_exposes_retrieval_acquisition_paths(self) -> None:
        settings = load_settings()

        self.assertTrue(settings.retrieval.manifest_path.name.endswith(".yaml"))
        self.assertEqual(settings.retrieval.raw_filings_root.name, "raw_filings")
        self.assertEqual(settings.retrieval.status_root.name, "corpus_status")
        self.assertGreaterEqual(settings.retrieval.default_pilot_company_count, 8)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **步骤 2：运行测试，确认当前会失败**

运行：`python -m unittest tests.unit.test_pdf_corpus_manifest -v`  
预期：出现 `AttributeError` 或 `ImportError`，因为 retrieval acquisition 配置还不存在。

- [ ] **步骤 3：补最小配置类型和基础模型**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class RetrievalSettings:
    manifest_path: Path
    raw_filings_root: Path
    status_root: Path
    default_pilot_company_count: int = 10


@dataclass(slots=True)
class SampleCompany:
    company_code: str
    company_name: str
    segment: str
    subsegment: str
    priority: str
    theme_tags: list[str] = field(default_factory=list)
    notes: str | None = None
```

```yaml
app:
  name: finsight-agent
  version: v1
  mode: skeleton
  control_plane:
    root: backend/src/finsight_agent/control_plane
    prompts:
      router_system_prompt_path: router/prompts/system.txt
      planner_system_prompt_path: planner/prompts/system.txt
  retrieval:
    manifest_path: var/data/corpus_manifests/semiconductor_sample_universe.yaml
    raw_filings_root: var/data/raw_filings
    status_root: var/data/corpus_status
    default_pilot_company_count: 10
```

- [ ] **步骤 4：再次运行测试，确认通过**

运行：`python -m unittest tests.unit.test_pdf_corpus_manifest -v`  
预期：PASS

- [ ] **步骤 5：提交**

```bash
git add config/app.yaml backend/src/finsight_agent/config/settings.py backend/src/finsight_agent/capabilities/retrieval/acquisition_models.py tests/unit/test_pdf_corpus_manifest.py
git commit -m "feat: 增加语料采集配置与基础模型"
```

### 任务 2：实现 YAML 样本股池读取与公司选择

**文件：**
- Create: `backend/src/finsight_agent/capabilities/retrieval/corpus_manifest.py`
- Test: `tests/unit/test_pdf_corpus_manifest.py`

- [ ] **步骤 1：扩展失败测试，明确 manifest 行为**

```python
from finsight_agent.capabilities.retrieval.corpus_manifest import load_sample_universe


class PdfCorpusManifestLoaderTest(unittest.TestCase):
    def test_load_sample_universe_reads_companies_and_targets(self) -> None:
        manifest = load_sample_universe(load_settings().retrieval.manifest_path)

        self.assertEqual(manifest.theme, "semiconductor")
        self.assertEqual(len(manifest.companies), 50)
        self.assertEqual(manifest.segment_targets["equipment"], 12)

    def test_select_companies_prefers_high_priority_for_pilot(self) -> None:
        manifest = load_sample_universe(load_settings().retrieval.manifest_path)

        pilot = manifest.select_companies(limit=10)

        self.assertEqual(len(pilot), 10)
        self.assertTrue(all(company.priority in {"high", "medium"} for company in pilot))
```

- [ ] **步骤 2：运行测试，确认失败**

运行：`python -m unittest tests.unit.test_pdf_corpus_manifest -v`  
预期：FAIL，因为 `load_sample_universe` 还不存在。

- [ ] **步骤 3：实现 manifest loader 和选择逻辑**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .acquisition_models import SampleCompany


@dataclass(slots=True)
class SampleUniverse:
    theme: str
    segment_targets: dict[str, int]
    companies: list[SampleCompany] = field(default_factory=list)

    def select_companies(self, limit: int, company_codes: list[str] | None = None) -> list[SampleCompany]:
        if company_codes:
            code_set = set(company_codes)
            return [company for company in self.companies if company.company_code in code_set][:limit]

        priority_rank = {"high": 0, "medium": 1, "low": 2}
        return sorted(
            self.companies,
            key=lambda company: (priority_rank.get(company.priority, 9), company.company_code),
        )[:limit]


def load_sample_universe(manifest_path: Path) -> SampleUniverse:
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    companies = [
        SampleCompany(
            company_code=str(item["company_code"]),
            company_name=str(item["company_name"]),
            segment=str(item["segment"]),
            subsegment=str(item.get("subsegment", "")),
            priority=str(item.get("priority", "medium")),
            theme_tags=list(item.get("theme_tags", [])),
            notes=item.get("notes"),
        )
        for item in payload["companies"]
    ]
    return SampleUniverse(
        theme=str(payload["theme"]),
        segment_targets={str(k): int(v) for k, v in payload["segment_targets"].items()},
        companies=companies,
    )
```

- [ ] **步骤 4：再次运行测试，确认通过**

运行：`python -m unittest tests.unit.test_pdf_corpus_manifest -v`  
预期：PASS

- [ ] **步骤 5：提交**

```bash
git add backend/src/finsight_agent/capabilities/retrieval/corpus_manifest.py tests/unit/test_pdf_corpus_manifest.py
git commit -m "feat: 实现半导体样本股池读取"
```

### 任务 3：实现披露文档筛选规则

**文件：**
- Create: `backend/src/finsight_agent/capabilities/retrieval/filing_filters.py`
- Test: `tests/unit/test_filing_filters.py`

- [ ] **步骤 1：先写失败的筛选规则测试**

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

from finsight_agent.capabilities.retrieval.acquisition_models import FilingRecord
from finsight_agent.capabilities.retrieval.filing_filters import classify_filing


class FilingFiltersTest(unittest.TestCase):
    def test_classify_annual_report_excludes_summary(self) -> None:
        record = FilingRecord(
            source_name="sse",
            market="sse",
            company_code="688981",
            company_name="中芯国际",
            title="2024年年度报告摘要",
            publish_date="2025-03-29",
            source_doc_type="regular",
            pdf_url="https://example.test/a.pdf",
        )

        self.assertIsNone(classify_filing(record))

    def test_classify_major_announcement_matches_capacity_expansion(self) -> None:
        record = FilingRecord(
            source_name="cninfo",
            market="szse",
            company_code="002371",
            company_name="北方华创",
            title="关于投资建设半导体装备产能扩张项目的公告",
            publish_date="2025-04-18",
            source_doc_type="announcement",
            pdf_url="https://example.test/b.pdf",
        )

        result = classify_filing(record)

        self.assertIsNotNone(result)
        self.assertEqual(result.normalized_doc_type, "major_announcement")
        self.assertEqual(result.announcement_type, "capacity_expansion")
```

- [ ] **步骤 2：运行测试，确认失败**

运行：`python -m unittest tests.unit.test_filing_filters -v`  
预期：FAIL，因为 `FilingRecord` 和 `classify_filing` 还不存在。

- [ ] **步骤 3：实现文档记录和筛选规则**

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class FilingRecord:
    source_name: str
    market: str
    company_code: str
    company_name: str
    title: str
    publish_date: str
    source_doc_type: str
    pdf_url: str
    announcement_id: str | None = None


@dataclass(slots=True)
class ClassifiedFiling:
    normalized_doc_type: str
    announcement_type: str | None = None
    report_year: int | None = None


def classify_filing(record: FilingRecord) -> ClassifiedFiling | None:
    title = record.title
    if "摘要" in title or "英文" in title or "取消" in title:
        return None
    if "年度报告" in title or title.endswith("年报"):
        return ClassifiedFiling(normalized_doc_type="annual_report")
    if "半年度报告" in title or "半年报" in title:
        return ClassifiedFiling(normalized_doc_type="semiannual_report")
    if "业绩预告" in title or "业绩快报" in title:
        return ClassifiedFiling(normalized_doc_type="major_announcement", announcement_type="earnings_update")
    if "产能扩张" in title or "投资建设" in title or "重大合同" in title:
        return ClassifiedFiling(normalized_doc_type="major_announcement", announcement_type="capacity_expansion")
    if "并购" in title or "重组" in title or "股权激励" in title or "减值" in title:
        return ClassifiedFiling(normalized_doc_type="major_announcement", announcement_type="major_corporate_action")
    return None
```

- [ ] **步骤 4：再次运行测试，确认通过**

运行：`python -m unittest tests.unit.test_filing_filters -v`  
预期：PASS

- [ ] **步骤 5：提交**

```bash
git add backend/src/finsight_agent/capabilities/retrieval/acquisition_models.py backend/src/finsight_agent/capabilities/retrieval/filing_filters.py tests/unit/test_filing_filters.py
git commit -m "feat: 增加披露文档筛选规则"
```

### 任务 4：实现目录布局与规范命名

**文件：**
- Create: `backend/src/finsight_agent/capabilities/retrieval/storage.py`
- Test: `tests/integration/test_pdf_corpus_storage_layout.py`

- [ ] **步骤 1：先写失败的存储布局测试**

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

from finsight_agent.capabilities.retrieval.acquisition_models import FilingRecord
from finsight_agent.capabilities.retrieval.storage import build_output_path, write_status_snapshot


class PdfCorpusStorageLayoutTest(unittest.TestCase):
    def test_build_output_path_uses_company_doc_type_and_year(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            record = FilingRecord(
                source_name="sse",
                market="sse",
                company_code="688981",
                company_name="中芯国际",
                title="2024年年度报告",
                publish_date="2025-03-29",
                source_doc_type="regular",
                pdf_url="https://example.test/a.pdf",
            )

            output_path = build_output_path(
                root=Path(temp_dir),
                record=record,
                normalized_doc_type="annual_report",
                report_year=2024,
            )

            self.assertIn("688981_中芯国际", str(output_path))
            self.assertIn("annual", str(output_path))
            self.assertTrue(str(output_path).endswith(".pdf"))

    def test_write_status_snapshot_persists_json_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_status_snapshot(
                status_root=Path(temp_dir),
                snapshot_name="pilot_download_status",
                payload={"downloaded": 3, "failed": 1},
            )

            self.assertTrue(path.exists())
            self.assertIn("pilot_download_status", path.name)
```

- [ ] **步骤 2：运行测试，确认失败**

运行：`python -m unittest tests.integration.test_pdf_corpus_storage_layout -v`  
预期：FAIL，因为存储辅助函数还不存在。

- [ ] **步骤 3：实现输出路径和状态快照写入**

```python
from __future__ import annotations

import json
from pathlib import Path

from .acquisition_models import FilingRecord


DOC_TYPE_DIRS = {
    "annual_report": "annual",
    "semiannual_report": "semiannual",
    "major_announcement": "announcements",
}


def build_output_path(root: Path, record: FilingRecord, normalized_doc_type: str, report_year: int | None) -> Path:
    company_dir = f"{record.company_code}_{record.company_name}"
    year_dir = str(report_year or record.publish_date[:4])
    filename = f"{record.company_code}_{record.company_name}_{normalized_doc_type}_{year_dir}_{record.publish_date.replace('-', '')}.pdf"
    return root / company_dir / DOC_TYPE_DIRS[normalized_doc_type] / year_dir / filename


def write_status_snapshot(status_root: Path, snapshot_name: str, payload: dict[str, object]) -> Path:
    status_root.mkdir(parents=True, exist_ok=True)
    path = status_root / f"{snapshot_name}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
```

- [ ] **步骤 4：再次运行测试，确认通过**

运行：`python -m unittest tests.integration.test_pdf_corpus_storage_layout -v`  
预期：PASS

- [ ] **步骤 5：提交**

```bash
git add backend/src/finsight_agent/capabilities/retrieval/storage.py tests/integration/test_pdf_corpus_storage_layout.py
git commit -m "feat: 增加语料采集目录与命名辅助"
```

### 任务 5：实现 SSE 列表发现适配器

**文件：**
- Create: `backend/src/finsight_agent/infra/external/sse_filings.py`
- Test: `tests/unit/test_pdf_corpus_acquisition_service.py`

- [ ] **步骤 1：先写失败的 SSE 标准化测试**

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

from finsight_agent.infra.external.sse_filings import normalize_sse_record


class SseAdapterNormalizationTest(unittest.TestCase):
    def test_normalize_sse_record_maps_fields_to_internal_shape(self) -> None:
        raw_item = {
            "BULLETIN_TYPE": "L012",
            "SECURITY_CODE": "688981",
            "TITLE": "2024年年度报告",
            "SSEDATE": "2025-03-29",
            "URL": "/disclosure/listedinfo/announcement/c/new/2025-03-29/123.pdf",
        }

        record = normalize_sse_record(raw_item, company_name="中芯国际")

        self.assertEqual(record.source_name, "sse")
        self.assertEqual(record.company_code, "688981")
        self.assertEqual(record.company_name, "中芯国际")
        self.assertEqual(record.publish_date, "2025-03-29")
        self.assertTrue(record.pdf_url.startswith("https://"))
```

- [ ] **步骤 2：运行测试，确认失败**

运行：`python -m unittest tests.unit.test_pdf_corpus_acquisition_service -v`  
预期：FAIL，因为 `normalize_sse_record` 还不存在。

- [ ] **步骤 3：实现 SSE 标准化与 adapter 骨架**

```python
from __future__ import annotations

from urllib.parse import urljoin

from finsight_agent.capabilities.retrieval.acquisition_models import FilingRecord


SSE_BASE_URL = "https://www.sse.com.cn"


def normalize_sse_record(raw_item: dict[str, object], company_name: str) -> FilingRecord:
    pdf_url = str(raw_item["URL"])
    return FilingRecord(
        source_name="sse",
        market="sse",
        company_code=str(raw_item["SECURITY_CODE"]),
        company_name=company_name,
        title=str(raw_item["TITLE"]),
        publish_date=str(raw_item["SSEDATE"]),
        source_doc_type=str(raw_item.get("BULLETIN_TYPE", "unknown")),
        pdf_url=urljoin(SSE_BASE_URL, pdf_url),
        announcement_id=str(raw_item.get("BULLETIN_ID", "")) or None,
    )
```

- [ ] **步骤 4：再次运行测试，确认通过**

运行：`python -m unittest tests.unit.test_pdf_corpus_acquisition_service -v`  
预期：SSE 标准化测试 PASS

- [ ] **步骤 5：提交**

```bash
git add backend/src/finsight_agent/infra/external/sse_filings.py tests/unit/test_pdf_corpus_acquisition_service.py
git commit -m "feat: 增加 SSE 披露列表标准化"
```

### 任务 6：实现 CNInfo 列表发现适配器

**文件：**
- Create: `backend/src/finsight_agent/infra/external/cninfo_filings.py`
- Test: `tests/unit/test_pdf_corpus_acquisition_service.py`

- [ ] **步骤 1：扩展失败测试，加入 CNInfo 标准化断言**

```python
from finsight_agent.infra.external.cninfo_filings import normalize_cninfo_record


class CninfoAdapterNormalizationTest(unittest.TestCase):
    def test_normalize_cninfo_record_maps_fields_to_internal_shape(self) -> None:
        raw_item = {
            "secCode": "002371",
            "secName": "北方华创",
            "announcementTitle": "关于签订重大合同的公告",
            "announcementTime": 1744905600000,
            "adjunctUrl": "finalpage/2025-04-18/PDF.pdf",
            "announcementId": "1234567890",
        }

        record = normalize_cninfo_record(raw_item)

        self.assertEqual(record.source_name, "cninfo")
        self.assertEqual(record.market, "szse")
        self.assertEqual(record.company_code, "002371")
        self.assertEqual(record.company_name, "北方华创")
        self.assertEqual(record.announcement_id, "1234567890")
```

- [ ] **步骤 2：运行测试，确认失败**

运行：`python -m unittest tests.unit.test_pdf_corpus_acquisition_service -v`  
预期：FAIL，因为 `normalize_cninfo_record` 还不存在。

- [ ] **步骤 3：实现 CNInfo 标准化与 adapter 骨架**

```python
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urljoin

from finsight_agent.capabilities.retrieval.acquisition_models import FilingRecord


CNINFO_BASE_URL = "https://static.cninfo.com.cn/"


def normalize_cninfo_record(raw_item: dict[str, object]) -> FilingRecord:
    timestamp_ms = int(raw_item["announcementTime"])
    publish_date = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    return FilingRecord(
        source_name="cninfo",
        market="szse",
        company_code=str(raw_item["secCode"]),
        company_name=str(raw_item["secName"]),
        title=str(raw_item["announcementTitle"]),
        publish_date=publish_date,
        source_doc_type="announcement",
        pdf_url=urljoin(CNINFO_BASE_URL, str(raw_item["adjunctUrl"])),
        announcement_id=str(raw_item["announcementId"]),
    )
```

- [ ] **步骤 4：再次运行测试，确认通过**

运行：`python -m unittest tests.unit.test_pdf_corpus_acquisition_service -v`  
预期：CNInfo 标准化测试 PASS

- [ ] **步骤 5：提交**

```bash
git add backend/src/finsight_agent/infra/external/cninfo_filings.py tests/unit/test_pdf_corpus_acquisition_service.py
git commit -m "feat: 增加 CNInfo 披露列表标准化"
```

### 任务 7：实现采集服务编排

**文件：**
- Create: `backend/src/finsight_agent/capabilities/retrieval/acquisition_service.py`
- Modify: `backend/src/finsight_agent/capabilities/retrieval/service.py`
- Test: `tests/unit/test_pdf_corpus_acquisition_service.py`

- [ ] **步骤 1：先写失败的编排测试**

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

from finsight_agent.capabilities.retrieval.acquisition_models import FilingRecord, SampleCompany
from finsight_agent.capabilities.retrieval.acquisition_service import PdfCorpusAcquisitionService


class FakeAdapter:
    def __init__(self, records):
        self.records = records

    def list_filings(self, company, start_date, end_date):
        return list(self.records)


class PdfCorpusAcquisitionServiceTest(unittest.TestCase):
    def test_collect_filing_index_filters_only_supported_documents(self) -> None:
        company = SampleCompany(
            company_code="688981",
            company_name="中芯国际",
            segment="manufacturing_idm",
            subsegment="foundry",
            priority="high",
        )
        records = [
            FilingRecord(
                source_name="sse",
                market="sse",
                company_code="688981",
                company_name="中芯国际",
                title="2024年年度报告",
                publish_date="2025-03-29",
                source_doc_type="regular",
                pdf_url="https://example.test/a.pdf",
            ),
            FilingRecord(
                source_name="sse",
                market="sse",
                company_code="688981",
                company_name="中芯国际",
                title="关于召开股东大会的通知",
                publish_date="2025-03-20",
                source_doc_type="announcement",
                pdf_url="https://example.test/b.pdf",
            ),
        ]

        service = PdfCorpusAcquisitionService(
            sse_adapter=FakeAdapter(records),
            cninfo_adapter=FakeAdapter([]),
        )

        result = service.collect_filing_index(
            companies=[company],
            start_date="2021-01-01",
            end_date="2026-06-30",
        )

        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0].title, "2024年年度报告")
```

- [ ] **步骤 2：运行测试，确认失败**

运行：`python -m unittest tests.unit.test_pdf_corpus_acquisition_service -v`  
预期：FAIL，因为 `PdfCorpusAcquisitionService` 还不存在。

- [ ] **步骤 3：实现最小编排服务**

```python
from __future__ import annotations

from dataclasses import dataclass, field

from .acquisition_models import FilingRecord, SampleCompany
from .filing_filters import classify_filing


@dataclass(slots=True)
class FilingIndexResult:
    records: list[FilingRecord] = field(default_factory=list)


class PdfCorpusAcquisitionService:
    def __init__(self, sse_adapter, cninfo_adapter) -> None:
        self._sse_adapter = sse_adapter
        self._cninfo_adapter = cninfo_adapter

    def collect_filing_index(self, companies: list[SampleCompany], start_date: str, end_date: str) -> FilingIndexResult:
        accepted: list[FilingRecord] = []
        for company in companies:
            adapter = self._sse_adapter if company.company_code.startswith(("6", "688")) else self._cninfo_adapter
            for record in adapter.list_filings(company=company, start_date=start_date, end_date=end_date):
                if classify_filing(record) is not None:
                    accepted.append(record)
        return FilingIndexResult(records=accepted)
```

- [ ] **步骤 4：再次运行测试，确认通过**

运行：`python -m unittest tests.unit.test_pdf_corpus_acquisition_service -v`  
预期：PASS

- [ ] **步骤 5：提交**

```bash
git add backend/src/finsight_agent/capabilities/retrieval/acquisition_service.py backend/src/finsight_agent/capabilities/retrieval/service.py tests/unit/test_pdf_corpus_acquisition_service.py
git commit -m "feat: 增加语料采集编排服务"
```

### 任务 8：实现下载执行与覆盖率状态快照

**文件：**
- Modify: `backend/src/finsight_agent/capabilities/retrieval/acquisition_service.py`
- Modify: `backend/src/finsight_agent/capabilities/retrieval/storage.py`
- Test: `tests/unit/test_pdf_corpus_acquisition_service.py`

- [ ] **步骤 1：扩展失败测试，加入下载执行断言**

```python
class FakeDownloader:
    def __init__(self):
        self.downloads = []

    def download(self, url, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"%PDF-1.4\\n")
        self.downloads.append((url, destination))
        return destination


class PdfCorpusAcquisitionServiceDownloadTest(unittest.TestCase):
    def test_download_filings_writes_pdf_and_status_snapshot(self) -> None:
        company = SampleCompany(
            company_code="688981",
            company_name="中芯国际",
            segment="manufacturing_idm",
            subsegment="foundry",
            priority="high",
        )
        record = FilingRecord(
            source_name="sse",
            market="sse",
            company_code="688981",
            company_name="中芯国际",
            title="2024年年度报告",
            publish_date="2025-03-29",
            source_doc_type="regular",
            pdf_url="https://example.test/a.pdf",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            downloader = FakeDownloader()
            service = PdfCorpusAcquisitionService(
                sse_adapter=FakeAdapter([record]),
                cninfo_adapter=FakeAdapter([]),
                downloader=downloader,
                raw_filings_root=Path(temp_dir) / "raw_filings",
                status_root=Path(temp_dir) / "corpus_status",
            )

            result = service.download_filings(companies=[company], start_date="2021-01-01", end_date="2026-06-30")

            self.assertEqual(result.downloaded_count, 1)
            self.assertEqual(len(downloader.downloads), 1)
            self.assertTrue(result.status_snapshot_path.exists())
```

- [ ] **步骤 2：运行测试，确认失败**

运行：`python -m unittest tests.unit.test_pdf_corpus_acquisition_service -v`  
预期：FAIL，因为下载编排还没实现。

- [ ] **步骤 3：实现下载执行和状态快照写入**

```python
from dataclasses import dataclass
from pathlib import Path

from .storage import build_output_path, write_status_snapshot


@dataclass(slots=True)
class DownloadResult:
    downloaded_count: int
    failed_count: int
    status_snapshot_path: Path


class DefaultDownloader:
    def download(self, url: str, destination: Path) -> Path:
        import urllib.request

        destination.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, destination)
        return destination
```

```python
def download_filings(self, companies: list[SampleCompany], start_date: str, end_date: str) -> DownloadResult:
    filing_index = self.collect_filing_index(companies=companies, start_date=start_date, end_date=end_date)
    downloaded_count = 0
    failed_count = 0
    for record in filing_index.records:
        classified = classify_filing(record)
        if classified is None:
            continue
        destination = build_output_path(
            root=self._raw_filings_root,
            record=record,
            normalized_doc_type=classified.normalized_doc_type,
            report_year=classified.report_year,
        )
        try:
            self._downloader.download(record.pdf_url, destination)
            downloaded_count += 1
        except Exception:
            failed_count += 1
    snapshot_path = write_status_snapshot(
        status_root=self._status_root,
        snapshot_name="pilot_download_status",
        payload={"downloaded": downloaded_count, "failed": failed_count},
    )
    return DownloadResult(
        downloaded_count=downloaded_count,
        failed_count=failed_count,
        status_snapshot_path=snapshot_path,
    )
```

- [ ] **步骤 4：再次运行测试，确认通过**

运行：`python -m unittest tests.unit.test_pdf_corpus_acquisition_service -v`  
预期：PASS

- [ ] **步骤 5：提交**

```bash
git add backend/src/finsight_agent/capabilities/retrieval/acquisition_service.py backend/src/finsight_agent/capabilities/retrieval/storage.py tests/unit/test_pdf_corpus_acquisition_service.py
git commit -m "feat: 增加语料下载与状态快照"
```

### 任务 9：接入基于 settings 的默认服务构造与全量验证

**文件：**
- Modify: `backend/src/finsight_agent/capabilities/retrieval/service.py`
- Modify: `tests/unit/test_pdf_corpus_acquisition_service.py`
- Modify: `tests/integration/test_pdf_corpus_storage_layout.py`

- [ ] **步骤 1：先写失败的 facade 测试**

```python
from finsight_agent.capabilities.retrieval.service import build_pdf_corpus_acquisition_service


class RetrievalFacadeTest(unittest.TestCase):
    def test_build_pdf_corpus_acquisition_service_uses_repository_settings(self) -> None:
        service = build_pdf_corpus_acquisition_service()

        self.assertIsNotNone(service)
        self.assertTrue(hasattr(service, "download_filings"))
```

- [ ] **步骤 2：运行测试，确认失败**

运行：`python -m unittest tests.unit.test_pdf_corpus_acquisition_service -v`  
预期：FAIL，因为 facade 还不存在。

- [ ] **步骤 3：实现基于 settings 的默认服务构造**

```python
from __future__ import annotations

from finsight_agent.capabilities.retrieval.acquisition_service import DefaultDownloader, PdfCorpusAcquisitionService
from finsight_agent.config.settings import load_settings
from finsight_agent.infra.external.cninfo_filings import CninfoFilingsAdapter
from finsight_agent.infra.external.sse_filings import SseFilingsAdapter


def build_pdf_corpus_acquisition_service() -> PdfCorpusAcquisitionService:
    settings = load_settings()
    return PdfCorpusAcquisitionService(
        sse_adapter=SseFilingsAdapter(),
        cninfo_adapter=CninfoFilingsAdapter(),
        downloader=DefaultDownloader(),
        raw_filings_root=settings.retrieval.raw_filings_root,
        status_root=settings.retrieval.status_root,
    )
```

- [ ] **步骤 4：运行定向测试和全量测试**

运行：`python -m unittest tests.unit.test_pdf_corpus_manifest tests.unit.test_filing_filters tests.unit.test_pdf_corpus_acquisition_service tests.integration.test_pdf_corpus_storage_layout -v`  
预期：PASS

运行：`python -m unittest discover -s tests -p 'test*.py'`  
预期：PASS

- [ ] **步骤 5：提交**

```bash
git add backend/src/finsight_agent/capabilities/retrieval/service.py tests/unit/test_pdf_corpus_acquisition_service.py tests/integration/test_pdf_corpus_storage_layout.py
git commit -m "feat: 接入默认 PDF 语料采集服务"
```

## 自查

### 规格覆盖检查
- 数据源分工：`SSE` 主抓沪市、`CNInfo` 主抓深市、`SZSE` 仅校验，这部分由任务 5、6、7 覆盖。
- manifest 驱动和试点公司选择，由任务 1、2 覆盖。
- 年报 / 半年报 / 三类重要公告筛选，由任务 3 覆盖。
- 目录结构、文件命名和状态快照，由任务 4 覆盖。
- 下载执行和试点覆盖率输出，由任务 8 覆盖。
- 对外服务入口和仓库级验证，由任务 9 覆盖。

### 占位符扫描
- 没有保留 `TODO`、`TBD` 或“同上类似”这类无效计划语句。
- 所有命令都明确写出，并沿用了仓库现有 `unittest` 风格。

### 类型一致性检查
- `SampleCompany`、`FilingRecord`、`ClassifiedFiling`、`FilingIndexResult`、`DownloadResult` 都在后续步骤使用前定义。
- 配置字段统一使用 `settings.retrieval.*`。
- facade 名称统一使用 `build_pdf_corpus_acquisition_service`。

## 执行交接

计划已保存到 `docs/superpowers/plans/2026-06-30-pdf-corpus-acquisition.md`。接下来有两种执行方式：

**1. 子代理分任务执行（推荐）**  
我按任务逐项派发、审查和收口，推进会更快。

**2. 当前会话内直接执行**  
我就在这个会话里按计划逐项实现。

你选一个，我就继续。  
