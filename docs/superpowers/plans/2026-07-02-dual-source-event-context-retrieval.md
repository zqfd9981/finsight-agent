# Dual-Source Event Context Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `event_impact_analysis` 接入首版真实外部检索能力，打通 `GDELT 事件搜索 + 官方披露搜索` 的双层 provider，并通过 `ContextRetrievalPlanner` 控制 `collect_event_context` 与候选发现检索。

**Architecture:** 保持 orchestrator 只依赖 `ExternalContextRetriever` 抽象，在其下方新增 `RetrievalStrategyClassifier`、`ContextRetrievalPlanner`、`EventSearchProvider`、`DisclosureSearchProvider` 和组合实现 `DualSourceExternalContextRetriever`。首版主流程不依赖训练好的分类器，默认用 stub classifier/fallback；本地 RAG 从“固定必查”改为“条件补充”，由 planner 显式决定。

**Tech Stack:** Python、urllib 标准库 HTTP 请求、现有 CNInfo/SSE adapter 模式、unittest、现有 orchestrator/retrieval/reporting 代码

---

## 文件结构

本计划建议最终形成以下边界：

- `backend/src/finsight_agent/control_plane/orchestrator/context_retriever.py`
  - 保留上层协议，补充真实组合实现所需的标准结果模型
- `backend/src/finsight_agent/control_plane/orchestrator/retrieval_strategy_classifier.py`
  - 检索策略分类器接口与 stub/fallback
- `backend/src/finsight_agent/control_plane/orchestrator/context_retrieval_planner.py`
  - 把三类策略标签翻译成执行计划
- `backend/src/finsight_agent/control_plane/orchestrator/context_retrieval_models.py`
  - 外部上下文检索标准化结果与计划对象
- `backend/src/finsight_agent/control_plane/orchestrator/dual_source_context_retriever.py`
  - 组合实现 `ExternalContextRetriever`
- `backend/src/finsight_agent/infra/external/gdelt_event_search.py`
  - `GdeltEventSearchProvider`
- `backend/src/finsight_agent/infra/external/official_disclosure_search.py`
  - `OfficialDisclosureSearchProvider`
- `backend/src/finsight_agent/infra/external/cninfo_context_search.py`
  - CNInfo 运行时事件/披露搜索标准化
- `backend/src/finsight_agent/infra/external/sse_context_search.py`
  - SSE 运行时披露搜索标准化
- `backend/src/finsight_agent/control_plane/orchestrator/stage_runners/collect_event_context.py`
  - 从“固定外部+固定RAG”改成“planner 驱动 + 条件 RAG”
- `backend/src/finsight_agent/control_plane/orchestrator/stage_runners/analyze_targets.py`
  - 候选发现改为消费新的 `discover_candidates(...)` 标准结果
- `backend/src/finsight_agent/control_plane/orchestrator/service.py`
  - 注入新的组合 retriever 与 classifier/planner 依赖
- `tests/unit/test_external_context_retriever.py`
- `tests/unit/test_context_retrieval_planner.py`
- `tests/unit/test_gdelt_event_search.py`
- `tests/unit/test_official_disclosure_search.py`
- `tests/unit/test_orchestrator_stage_runners.py`
- `tests/integration/test_event_impact_analysis_flow.py`
- `docs/finsight/project-status.md`
- `docs/finsight/modules/control-plane-status.md`
- `docs/finsight/modules/data-evidence-status.md`

---

### Task 1: 固定检索策略分类器接口与 fallback

**Files:**
- Create: `backend/src/finsight_agent/control_plane/orchestrator/retrieval_strategy_classifier.py`
- Test: `tests/unit/test_external_context_retriever.py`

- [ ] **Step 1: 写失败单测，先固定三类策略标签与默认回退值**

```python
import unittest

from finsight_agent.control_plane.orchestrator.retrieval_strategy_classifier import (
    DEFAULT_RETRIEVAL_STRATEGY,
    RETRIEVAL_STRATEGIES,
    StubRetrievalStrategyClassifier,
)


class RetrievalStrategyClassifierContractTest(unittest.TestCase):
    def test_strategy_labels_and_default_are_stable(self) -> None:
        self.assertEqual(
            RETRIEVAL_STRATEGIES,
            ("event_primary", "disclosure_primary", "dual_primary"),
        )
        self.assertEqual(DEFAULT_RETRIEVAL_STRATEGY, "event_primary")

    def test_stub_classifier_returns_safe_fallback(self) -> None:
        classifier = StubRetrievalStrategyClassifier()

        payload = classifier.classify(
            query="红海局势升级利好哪些A股航运股？",
            router_payload={
                "intent": "event_impact_analysis",
                "entities": {"event": "红海局势升级"},
            },
            session_topic="",
        )

        self.assertEqual(payload["strategy"], "event_primary")
        self.assertEqual(payload["confidence"], "low")
        self.assertEqual(payload["reason"], "stub_fallback")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.unit.test_external_context_retriever -v`

Expected: `ModuleNotFoundError` 或导入失败，因为分类器文件尚不存在。

- [ ] **Step 3: 实现最小分类器接口与 stub**

```python
from __future__ import annotations

from typing import Protocol


RETRIEVAL_STRATEGIES = (
    "event_primary",
    "disclosure_primary",
    "dual_primary",
)
DEFAULT_RETRIEVAL_STRATEGY = "event_primary"


class RetrievalStrategyClassifier(Protocol):
    """检索策略分类器协议。

    首版主流程只依赖这层抽象，训练好的模型以后再按同一接口接入。
    """

    def classify(
        self,
        *,
        query: str,
        router_payload: dict[str, object],
        session_topic: str,
    ) -> dict[str, str]:
        """返回策略标签、置信度和调试原因。"""


class StubRetrievalStrategyClassifier:
    """训练分类器未就绪时的安全默认实现。"""

    def classify(
        self,
        *,
        query: str,
        router_payload: dict[str, object],
        session_topic: str,
    ) -> dict[str, str]:
        del query, router_payload, session_topic
        return {
            "strategy": DEFAULT_RETRIEVAL_STRATEGY,
            "confidence": "low",
            "reason": "stub_fallback",
        }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.unit.test_external_context_retriever -v`

Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add backend/src/finsight_agent/control_plane/orchestrator/retrieval_strategy_classifier.py tests/unit/test_external_context_retriever.py
git commit -m "feat: 增加检索策略分类器抽象"
```

### Task 2: 定义外部上下文标准结果与计划对象

**Files:**
- Create: `backend/src/finsight_agent/control_plane/orchestrator/context_retrieval_models.py`
- Test: `tests/unit/test_external_context_retriever.py`

- [ ] **Step 1: 写失败单测，固定标准化结果与 planner step 数据结构**

```python
import unittest

from finsight_agent.control_plane.orchestrator.context_retrieval_models import (
    ContextRetrievalPlan,
    ExternalContextItem,
    ExternalContextResult,
)


class ContextRetrievalModelsTest(unittest.TestCase):
    def test_context_result_and_plan_hold_structured_fields(self) -> None:
        item = ExternalContextItem(
            title="红海局势升级影响航线",
            source="gdelt",
            publish_date="2026-07-02",
            url="https://example.com/a",
            snippet="航线扰动加剧。",
            company_names=[],
            company_codes=[],
            themes=["航运"],
        )
        result = ExternalContextResult(
            items=[item],
            summary_hint="事件背景已提炼",
            supporting_points=["航线扰动加剧"],
            evidence_refs=["gdelt:item_001"],
            candidate_hints=["航运"],
            source_status={"gdelt_used": True},
        )
        plan = ContextRetrievalPlan(
            mode="event_primary",
            steps=[{"source": "event_search", "budget": 1}],
            allow_local_rag=False,
        )

        self.assertEqual(result.items[0].source, "gdelt")
        self.assertEqual(plan.mode, "event_primary")
        self.assertFalse(plan.allow_local_rag)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.unit.test_external_context_retriever -v`

Expected: 导入失败，因为模型文件尚不存在。

- [ ] **Step 3: 实现 dataclass 模型**

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ExternalContextItem:
    title: str
    source: str
    publish_date: str
    url: str
    snippet: str
    company_names: list[str] = field(default_factory=list)
    company_codes: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ExternalContextResult:
    items: list[ExternalContextItem] = field(default_factory=list)
    summary_hint: str = ""
    supporting_points: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    candidate_hints: list[str] = field(default_factory=list)
    source_status: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class ContextRetrievalPlan:
    mode: str
    steps: list[dict[str, object]]
    allow_local_rag: bool
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.unit.test_external_context_retriever -v`

Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add backend/src/finsight_agent/control_plane/orchestrator/context_retrieval_models.py tests/unit/test_external_context_retriever.py
git commit -m "feat: 增加外部上下文检索标准模型"
```

### Task 3: 实现 ContextRetrievalPlanner

**Files:**
- Create: `backend/src/finsight_agent/control_plane/orchestrator/context_retrieval_planner.py`
- Test: `tests/unit/test_context_retrieval_planner.py`

- [ ] **Step 1: 写失败单测，固定三类策略到检索计划的映射**

```python
import unittest

from finsight_agent.control_plane.orchestrator.context_retrieval_planner import (
    ContextRetrievalPlanner,
)


class ContextRetrievalPlannerTest(unittest.TestCase):
    def test_event_primary_plan_prefers_event_search_then_conditional_disclosure(self) -> None:
        planner = ContextRetrievalPlanner()

        plan = planner.build_plan(
            strategy_payload={"strategy": "event_primary", "confidence": "medium"},
            router_payload={
                "intent": "event_impact_analysis",
                "entities": {"event": "红海局势升级", "themes": ["航运"]},
            },
        )

        self.assertEqual(plan.mode, "event_primary")
        self.assertEqual(plan.steps[0]["source"], "event_search")
        self.assertEqual(plan.steps[1]["source"], "disclosure_search")
        self.assertFalse(plan.allow_local_rag)

    def test_dual_primary_plan_uses_two_primary_sources_without_default_rag(self) -> None:
        planner = ContextRetrievalPlanner()

        plan = planner.build_plan(
            strategy_payload={"strategy": "dual_primary", "confidence": "high"},
            router_payload={"intent": "event_impact_analysis", "entities": {}},
        )

        self.assertEqual(plan.mode, "dual_primary")
        self.assertEqual([step["source"] for step in plan.steps], ["event_search", "disclosure_search"])
        self.assertFalse(plan.allow_local_rag)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.unit.test_context_retrieval_planner -v`

Expected: `ModuleNotFoundError` 或导入失败。

- [ ] **Step 3: 实现最小 planner**

```python
from __future__ import annotations

from finsight_agent.control_plane.orchestrator.context_retrieval_models import (
    ContextRetrievalPlan,
)
from finsight_agent.control_plane.orchestrator.retrieval_strategy_classifier import (
    DEFAULT_RETRIEVAL_STRATEGY,
)


class ContextRetrievalPlanner:
    """把策略分类结果翻译成 collect_event_context 的执行计划。"""

    def build_plan(
        self,
        *,
        strategy_payload: dict[str, str],
        router_payload: dict[str, object],
    ) -> ContextRetrievalPlan:
        del router_payload
        strategy = strategy_payload.get("strategy") or DEFAULT_RETRIEVAL_STRATEGY

        if strategy == "disclosure_primary":
            return ContextRetrievalPlan(
                mode="disclosure_primary",
                steps=[
                    {"source": "disclosure_search", "budget": 1},
                    {"source": "event_search", "budget": 1, "when": "if_weak"},
                ],
                allow_local_rag=False,
            )
        if strategy == "dual_primary":
            return ContextRetrievalPlan(
                mode="dual_primary",
                steps=[
                    {"source": "event_search", "budget": 1},
                    {"source": "disclosure_search", "budget": 1},
                ],
                allow_local_rag=False,
            )
        return ContextRetrievalPlan(
            mode="event_primary",
            steps=[
                {"source": "event_search", "budget": 1},
                {"source": "disclosure_search", "budget": 1, "when": "if_weak"},
            ],
            allow_local_rag=False,
        )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.unit.test_context_retrieval_planner -v`

Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add backend/src/finsight_agent/control_plane/orchestrator/context_retrieval_planner.py tests/unit/test_context_retrieval_planner.py
git commit -m "feat: 增加事件上下文检索计划器"
```

### Task 4: 实现 GDELT 事件搜索 provider

**Files:**
- Create: `backend/src/finsight_agent/infra/external/gdelt_event_search.py`
- Test: `tests/unit/test_gdelt_event_search.py`

- [ ] **Step 1: 写失败单测，固定 GDELT 结果标准化**

```python
import unittest

from finsight_agent.infra.external.gdelt_event_search import (
    GdeltEventSearchProvider,
)


class _StubGdeltFetcher:
    def get_json(self, url: str, params: dict[str, object]) -> dict[str, object]:
        return {
            "articles": [
                {
                    "title": "Red Sea disruptions raise shipping concerns",
                    "url": "https://example.com/red-sea",
                    "seendate": "20260702T120000Z",
                    "domain": "example.com",
                    "socialimage": "",
                    "language": "English",
                    "sourcecountry": "US",
                }
            ]
        }


class GdeltEventSearchProviderTest(unittest.TestCase):
    def test_search_returns_standardized_context_result(self) -> None:
        provider = GdeltEventSearchProvider(fetcher=_StubGdeltFetcher())

        result = provider.search_event_context(
            query="红海局势升级利好哪些A股航运股？",
            event="红海局势升级",
            themes=["航运", "油运"],
            time_scope="recent",
            limit=3,
        )

        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].source, "gdelt")
        self.assertTrue(result.summary_hint)
        self.assertTrue(result.evidence_refs)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.unit.test_gdelt_event_search -v`

Expected: 模块不存在。

- [ ] **Step 3: 实现最小 GDELT provider**

```python
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime

from finsight_agent.control_plane.orchestrator.context_retrieval_models import (
    ExternalContextItem,
    ExternalContextResult,
)


GDELT_DOC_API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


@dataclass(slots=True)
class GdeltHttpFetcher:
    timeout_seconds: float = 30.0

    def get_json(self, url: str, params: dict[str, object]) -> dict[str, object]:
        query_string = urllib.parse.urlencode(params)
        with urllib.request.urlopen(f"{url}?{query_string}", timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))


class GdeltEventSearchProvider:
    def __init__(self, *, fetcher: GdeltHttpFetcher | None = None) -> None:
        self._fetcher = fetcher or GdeltHttpFetcher()

    def search_event_context(
        self,
        *,
        query: str,
        event: str,
        themes: list[str],
        time_scope: str,
        limit: int,
    ) -> ExternalContextResult:
        payload = self._fetcher.get_json(
            GDELT_DOC_API_URL,
            {
                "query": " ".join([query, event, *themes]).strip(),
                "mode": "ArtList",
                "maxrecords": str(limit),
                "format": "json",
            },
        )
        items: list[ExternalContextItem] = []
        evidence_refs: list[str] = []
        for index, article in enumerate(payload.get("articles", []) or [], start=1):
            title = str(article.get("title") or "").strip()
            url = str(article.get("url") or "").strip()
            publish_date = str(article.get("seendate") or "")[:8]
            normalized_date = (
                datetime.strptime(publish_date, "%Y%m%d").strftime("%Y-%m-%d")
                if publish_date
                else ""
            )
            items.append(
                ExternalContextItem(
                    title=title,
                    source="gdelt",
                    publish_date=normalized_date,
                    url=url,
                    snippet=title,
                    themes=list(themes),
                )
            )
            evidence_refs.append(f"gdelt:item_{index:03d}")
        summary_hint = items[0].title if items else ""
        return ExternalContextResult(
            items=items,
            summary_hint=summary_hint,
            supporting_points=[item.title for item in items[:2]],
            evidence_refs=evidence_refs,
            candidate_hints=list(themes),
            source_status={"gdelt_used": bool(items), "time_scope": time_scope},
        )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.unit.test_gdelt_event_search -v`

Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add backend/src/finsight_agent/infra/external/gdelt_event_search.py tests/unit/test_gdelt_event_search.py
git commit -m "feat: 增加GDELT事件搜索Provider"
```

### Task 5: 实现 CNInfo 运行时上下文搜索

**Files:**
- Create: `backend/src/finsight_agent/infra/external/cninfo_context_search.py`
- Test: `tests/unit/test_official_disclosure_search.py`

- [ ] **Step 1: 写失败单测，固定 CNInfo 披露结果标准化**

```python
import unittest

from finsight_agent.infra.external.cninfo_context_search import (
    CninfoContextSearchProvider,
)


class _StubCninfoContextFetcher:
    def get_json(self, url: str, params: dict[str, object], headers: dict[str, str]) -> dict[str, object]:
        return {
            "announcements": [
                {
                    "secCode": "000001",
                    "secName": "平安银行",
                    "announcementTitle": "关于航运链风险提示的公告",
                    "announcementTime": 1782960000000,
                    "adjunctUrl": "finalpage/2026-07-02/sample.PDF",
                    "announcementId": "ann_001",
                }
            ]
        }


class CninfoContextSearchProviderTest(unittest.TestCase):
    def test_search_returns_standardized_items(self) -> None:
        provider = CninfoContextSearchProvider(fetcher=_StubCninfoContextFetcher())

        result = provider.search(
            query="红海局势升级 航运",
            limit=3,
        )

        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].source, "cninfo")
        self.assertEqual(result.items[0].company_codes, ["000001"])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.unit.test_official_disclosure_search -v`

Expected: 导入失败，因为 provider 文件尚不存在。

- [ ] **Step 3: 实现最小 CNInfo 上下文搜索 provider**

```python
from __future__ import annotations

from finsight_agent.control_plane.orchestrator.context_retrieval_models import (
    ExternalContextItem,
    ExternalContextResult,
)
from finsight_agent.infra.external.cninfo_filings import (
    CNINFO_FULLTEXT_URL,
    CNINFO_SITE_BASE_URL,
    CninfoHttpFetcher,
    normalize_cninfo_record,
)


class CninfoContextSearchProvider:
    def __init__(self, *, fetcher: CninfoHttpFetcher | None = None) -> None:
        self._fetcher = fetcher or CninfoHttpFetcher()

    def search(self, *, query: str, limit: int) -> ExternalContextResult:
        payload = self._fetcher.get_json(
            url=CNINFO_FULLTEXT_URL,
            params={
                "searchkey": query,
                "sdate": "",
                "edate": "",
                "isfulltext": "false",
                "sortName": "pubdate",
                "sortType": "desc",
                "pageNum": "1",
                "pageSize": str(limit),
                "type": "",
            },
            headers={
                "Referer": f"{CNINFO_SITE_BASE_URL}/new/fulltextSearch?keyWord={query}",
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json, text/plain, */*",
            },
        )
        items: list[ExternalContextItem] = []
        evidence_refs: list[str] = []
        for index, raw in enumerate(payload.get("announcements", []) or [], start=1):
            record = normalize_cninfo_record(raw)
            items.append(
                ExternalContextItem(
                    title=record.title,
                    source="cninfo",
                    publish_date=record.publish_date,
                    url=record.pdf_url,
                    snippet=record.title,
                    company_names=[record.company_name],
                    company_codes=[record.company_code],
                    themes=[],
                )
            )
            evidence_refs.append(f"cninfo:{record.announcement_id or index}")
        return ExternalContextResult(
            items=items,
            summary_hint=items[0].title if items else "",
            supporting_points=[item.title for item in items[:2]],
            evidence_refs=evidence_refs,
            candidate_hints=[name for item in items for name in item.company_names],
            source_status={"cninfo_used": bool(items)},
        )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.unit.test_official_disclosure_search -v`

Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add backend/src/finsight_agent/infra/external/cninfo_context_search.py tests/unit/test_official_disclosure_search.py
git commit -m "feat: 增加CNInfo运行时上下文搜索"
```

### Task 6: 实现 SSE 运行时上下文搜索

**Files:**
- Create: `backend/src/finsight_agent/infra/external/sse_context_search.py`
- Test: `tests/unit/test_official_disclosure_search.py`

- [ ] **Step 1: 写失败单测，固定 SSE 披露结果标准化**

```python
import unittest

from finsight_agent.infra.external.sse_context_search import (
    SseContextSearchProvider,
)


class _StubSseContextFetcher:
    def get_json(self, url: str, params: dict[str, object], headers: dict[str, str]) -> dict[str, object]:
        return {
            "result": [
                {
                    "SECURITY_CODE": "600026",
                    "TITLE": "关于航运市场波动的公告",
                    "SSEDATE": "2026-07-02",
                    "URL": "/disclosure/listedinfo/announcement/c/new.pdf",
                    "BULLETIN_ID": "bulletin_001",
                }
            ]
        }


class SseContextSearchProviderTest(unittest.TestCase):
    def test_search_returns_standardized_items(self) -> None:
        provider = SseContextSearchProvider(fetcher=_StubSseContextFetcher())

        result = provider.search(
            query="红海局势升级 航运",
            limit=3,
        )

        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].source, "sse")
        self.assertEqual(result.items[0].company_codes, ["600026"])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.unit.test_official_disclosure_search -v`

Expected: 目标 provider 尚不存在。

- [ ] **Step 3: 实现最小 SSE 上下文搜索 provider**

```python
from __future__ import annotations

from finsight_agent.control_plane.orchestrator.context_retrieval_models import (
    ExternalContextItem,
    ExternalContextResult,
)
from finsight_agent.infra.external.sse_filings import (
    SSE_ANNOUNCEMENT_URL,
    SSE_BASE_URL,
    SseHttpFetcher,
)
from urllib.parse import urljoin


class SseContextSearchProvider:
    def __init__(self, *, fetcher: SseHttpFetcher | None = None) -> None:
        self._fetcher = fetcher or SseHttpFetcher()

    def search(self, *, query: str, limit: int) -> ExternalContextResult:
        payload = self._fetcher.get_json(
            url=SSE_ANNOUNCEMENT_URL,
            params={
                "isPagination": "true",
                "pageHelp.pageSize": str(limit),
                "pageHelp.pageNo": "1",
                "pageHelp.beginPage": "1",
                "pageHelp.cacheSize": "1",
                "pageHelp.endPage": "1",
                "title": query,
            },
            headers={
                "Referer": "https://www.sse.com.cn/disclosure/listedinfo/announcement/",
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json, text/javascript, */*; q=0.01",
            },
        )
        raw_items = payload.get("result") or []
        if isinstance(raw_items, dict):
            raw_items = [raw_items]
        items: list[ExternalContextItem] = []
        evidence_refs: list[str] = []
        for index, raw in enumerate(raw_items, start=1):
            if not isinstance(raw, dict):
                continue
            code = str(raw.get("SECURITY_CODE") or "").strip()
            title = str(raw.get("TITLE") or "").strip()
            url = urljoin(SSE_BASE_URL, str(raw.get("URL") or "").strip())
            bulletin_id = str(raw.get("BULLETIN_ID") or index)
            items.append(
                ExternalContextItem(
                    title=title,
                    source="sse",
                    publish_date=str(raw.get("SSEDATE") or "").strip(),
                    url=url,
                    snippet=title,
                    company_names=[],
                    company_codes=[code] if code else [],
                    themes=[],
                )
            )
            evidence_refs.append(f"sse:{bulletin_id}")
        return ExternalContextResult(
            items=items,
            summary_hint=items[0].title if items else "",
            supporting_points=[item.title for item in items[:2]],
            evidence_refs=evidence_refs,
            candidate_hints=[code for item in items for code in item.company_codes],
            source_status={"sse_used": bool(items)},
        )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.unit.test_official_disclosure_search -v`

Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add backend/src/finsight_agent/infra/external/sse_context_search.py tests/unit/test_official_disclosure_search.py
git commit -m "feat: 增加SSE运行时上下文搜索"
```

### Task 7: 实现官方披露组合 provider

**Files:**
- Create: `backend/src/finsight_agent/infra/external/official_disclosure_search.py`
- Test: `tests/unit/test_official_disclosure_search.py`

- [ ] **Step 1: 写失败单测，固定 CNInfo 主查、SSE 补查与去重合并**

```python
import unittest

from finsight_agent.control_plane.orchestrator.context_retrieval_models import (
    ExternalContextItem,
    ExternalContextResult,
)
from finsight_agent.infra.external.official_disclosure_search import (
    OfficialDisclosureSearchProvider,
)


class _StubDisclosureProvider:
    def __init__(self, result: ExternalContextResult) -> None:
        self.result = result
        self.calls = 0

    def search(self, *, query: str, limit: int) -> ExternalContextResult:
        del query, limit
        self.calls += 1
        return self.result


class OfficialDisclosureSearchProviderTest(unittest.TestCase):
    def test_search_merges_cninfo_and_sse_results(self) -> None:
        cninfo = _StubDisclosureProvider(
            ExternalContextResult(
                items=[
                    ExternalContextItem(
                        title="公告A",
                        source="cninfo",
                        publish_date="2026-07-02",
                        url="https://a",
                        snippet="公告A",
                        company_codes=["000001"],
                    )
                ],
                evidence_refs=["cninfo:a"],
                source_status={"cninfo_used": True},
            )
        )
        sse = _StubDisclosureProvider(
            ExternalContextResult(
                items=[
                    ExternalContextItem(
                        title="公告B",
                        source="sse",
                        publish_date="2026-07-02",
                        url="https://b",
                        snippet="公告B",
                        company_codes=["600026"],
                    )
                ],
                evidence_refs=["sse:b"],
                source_status={"sse_used": True},
            )
        )

        provider = OfficialDisclosureSearchProvider(
            cninfo_provider=cninfo,
            sse_provider=sse,
        )
        result = provider.search(query="红海局势升级 航运", limit=3)

        self.assertEqual(len(result.items), 2)
        self.assertEqual(result.evidence_refs, ["cninfo:a", "sse:b"])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.unit.test_official_disclosure_search -v`

Expected: 模块不存在。

- [ ] **Step 3: 实现组合 provider**

```python
from __future__ import annotations

from finsight_agent.control_plane.orchestrator.context_retrieval_models import (
    ExternalContextResult,
)
from finsight_agent.infra.external.cninfo_context_search import CninfoContextSearchProvider
from finsight_agent.infra.external.sse_context_search import SseContextSearchProvider


class OfficialDisclosureSearchProvider:
    def __init__(
        self,
        *,
        cninfo_provider: CninfoContextSearchProvider | None = None,
        sse_provider: SseContextSearchProvider | None = None,
    ) -> None:
        self._cninfo = cninfo_provider or CninfoContextSearchProvider()
        self._sse = sse_provider or SseContextSearchProvider()

    def search(self, *, query: str, limit: int) -> ExternalContextResult:
        primary = self._cninfo.search(query=query, limit=limit)
        secondary = self._sse.search(query=query, limit=limit)
        return ExternalContextResult(
            items=[*primary.items, *secondary.items],
            summary_hint=primary.summary_hint or secondary.summary_hint,
            supporting_points=[*primary.supporting_points, *secondary.supporting_points][:4],
            evidence_refs=[*primary.evidence_refs, *secondary.evidence_refs],
            candidate_hints=[*primary.candidate_hints, *secondary.candidate_hints],
            source_status={
                **primary.source_status,
                **secondary.source_status,
            },
        )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.unit.test_official_disclosure_search -v`

Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add backend/src/finsight_agent/infra/external/official_disclosure_search.py tests/unit/test_official_disclosure_search.py
git commit -m "feat: 增加官方披露组合搜索Provider"
```

### Task 8: 扩展 ExternalContextRetriever 协议与真实组合实现

**Files:**
- Modify: `backend/src/finsight_agent/control_plane/orchestrator/context_retriever.py`
- Create: `backend/src/finsight_agent/control_plane/orchestrator/dual_source_context_retriever.py`
- Test: `tests/unit/test_external_context_retriever.py`

- [ ] **Step 1: 写失败单测，固定双层 retriever 的 retrieve_event_context 与 discover_candidates 行为**

```python
import unittest

from finsight_agent.control_plane.orchestrator.context_retrieval_models import (
    ExternalContextResult,
)
from finsight_agent.control_plane.orchestrator.dual_source_context_retriever import (
    DualSourceExternalContextRetriever,
)


class _StubEventProvider:
    def __init__(self, result: ExternalContextResult) -> None:
        self.result = result

    def search_event_context(self, **kwargs):
        return self.result


class _StubDisclosureProvider:
    def __init__(self, result: ExternalContextResult) -> None:
        self.result = result

    def search(self, **kwargs):
        return self.result


class _StubPlanner:
    def build_plan(self, *, strategy_payload, router_payload):
        del strategy_payload, router_payload
        from finsight_agent.control_plane.orchestrator.context_retrieval_models import ContextRetrievalPlan
        return ContextRetrievalPlan(
            mode="dual_primary",
            steps=[
                {"source": "event_search", "budget": 1},
                {"source": "disclosure_search", "budget": 1},
            ],
            allow_local_rag=False,
        )


class _StubClassifier:
    def classify(self, *, query, router_payload, session_topic):
        del query, router_payload, session_topic
        return {"strategy": "dual_primary", "confidence": "high", "reason": "test"}


class DualSourceExternalContextRetrieverTest(unittest.TestCase):
    def test_retrieve_event_context_merges_planned_sources(self) -> None:
        retriever = DualSourceExternalContextRetriever(
            classifier=_StubClassifier(),
            planner=_StubPlanner(),
            event_search_provider=_StubEventProvider(ExternalContextResult(summary_hint="事件背景", evidence_refs=["gdelt:1"])),
            disclosure_search_provider=_StubDisclosureProvider(ExternalContextResult(summary_hint="公告背景", evidence_refs=["cninfo:1"])),
        )

        result = retriever.retrieve_event_context(
            query="红海局势升级利好哪些A股航运股？",
            event="红海局势升级",
            themes=["航运"],
            time_scope="recent",
            limit=3,
        )

        self.assertEqual(result["source_status"]["mode"], "dual_primary")
        self.assertEqual(result["evidence_refs"], ["gdelt:1", "cninfo:1"])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.unit.test_external_context_retriever -v`

Expected: 组合 retriever 尚不存在。

- [ ] **Step 3: 实现组合 retriever**

```python
from __future__ import annotations

from finsight_agent.control_plane.orchestrator.context_retrieval_models import (
    ExternalContextResult,
)
from finsight_agent.control_plane.orchestrator.context_retrieval_planner import (
    ContextRetrievalPlanner,
)
from finsight_agent.control_plane.orchestrator.retrieval_strategy_classifier import (
    StubRetrievalStrategyClassifier,
)


class DualSourceExternalContextRetriever:
    def __init__(
        self,
        *,
        classifier=None,
        planner: ContextRetrievalPlanner | None = None,
        event_search_provider=None,
        disclosure_search_provider=None,
    ) -> None:
        self._classifier = classifier or StubRetrievalStrategyClassifier()
        self._planner = planner or ContextRetrievalPlanner()
        self._event_search_provider = event_search_provider
        self._disclosure_search_provider = disclosure_search_provider

    def retrieve_event_context(
        self,
        *,
        query: str,
        event: str,
        themes: list[str],
        time_scope: str,
        limit: int,
    ) -> dict[str, object] | None:
        strategy_payload = self._classifier.classify(
            query=query,
            router_payload={
                "intent": "event_impact_analysis",
                "entities": {"event": event, "themes": themes, "time_scope": time_scope},
            },
            session_topic="",
        )
        plan = self._planner.build_plan(
            strategy_payload=strategy_payload,
            router_payload={"intent": "event_impact_analysis", "entities": {}},
        )
        merged = ExternalContextResult()
        for step in plan.steps:
            if step["source"] == "event_search" and self._event_search_provider is not None:
                payload = self._event_search_provider.search_event_context(
                    query=query,
                    event=event,
                    themes=themes,
                    time_scope=time_scope,
                    limit=int(step["budget"]),
                )
                merged.items.extend(payload.items)
                merged.supporting_points.extend(payload.supporting_points)
                merged.evidence_refs.extend(payload.evidence_refs)
                merged.candidate_hints.extend(payload.candidate_hints)
                merged.summary_hint = merged.summary_hint or payload.summary_hint
                merged.source_status.update(payload.source_status)
            if step["source"] == "disclosure_search" and self._disclosure_search_provider is not None:
                payload = self._disclosure_search_provider.search(
                    query=" ".join([query, event, *themes]).strip(),
                    limit=int(step["budget"]),
                )
                merged.items.extend(payload.items)
                merged.supporting_points.extend(payload.supporting_points)
                merged.evidence_refs.extend(payload.evidence_refs)
                merged.candidate_hints.extend(payload.candidate_hints)
                merged.summary_hint = merged.summary_hint or payload.summary_hint
                merged.source_status.update(payload.source_status)
        merged.source_status["mode"] = plan.mode
        return {
            "summary_hint": merged.summary_hint,
            "supporting_points": merged.supporting_points,
            "evidence_refs": merged.evidence_refs,
            "candidate_hints": merged.candidate_hints,
            "source_status": merged.source_status,
        }

    def discover_candidates(
        self,
        *,
        query: str,
        event_context: dict[str, object],
        limit: int,
    ) -> dict[str, object] | None:
        if self._disclosure_search_provider is None:
            return None
        payload = self._disclosure_search_provider.search(
            query=" ".join(
                [
                    query,
                    str(event_context.get("event") or "").strip(),
                    *[str(item).strip() for item in event_context.get("themes", []) or []],
                ]
            ).strip(),
            limit=limit,
        )
        return {
            "candidates": payload.candidate_hints,
            "evidence_refs": payload.evidence_refs,
            "source_status": payload.source_status,
        }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.unit.test_external_context_retriever -v`

Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add backend/src/finsight_agent/control_plane/orchestrator/context_retriever.py backend/src/finsight_agent/control_plane/orchestrator/dual_source_context_retriever.py tests/unit/test_external_context_retriever.py
git commit -m "feat: 增加双层外部上下文检索组合实现"
```

### Task 9: 改造 collect_event_context 为 planner 驱动 + 条件 RAG

**Files:**
- Modify: `backend/src/finsight_agent/control_plane/orchestrator/stage_runners/collect_event_context.py`
- Test: `tests/unit/test_orchestrator_stage_runners.py`

- [ ] **Step 1: 写失败单测，固定“默认不查本地 RAG”与“弱结果时再补一次”的行为**

```python
def test_collect_event_context_stage_skips_local_rag_when_external_context_is_sufficient(self) -> None:
    from finsight_agent.control_plane.orchestrator.stage_runners.collect_event_context import (
        run_collect_event_context_stage,
    )

    facade = _StubRetrievalFacade(_build_retrieval_result())
    external_retriever = _StubExternalContextRetriever(
        event_context_payload={
            "summary_hint": "外部事件背景已足够",
            "supporting_points": ["背景点1", "背景点2"],
            "evidence_refs": ["ext_001", "ext_002"],
            "source_status": {"mode": "dual_primary", "local_rag_needed": False},
        }
    )

    result = run_collect_event_context_stage(
        request=_build_request(query="红海局势升级利好哪些A股航运股？"),
        router_result=_build_router_result(
            intent="event_impact_analysis",
            entities={"event": "红海局势升级", "themes": ["航运"], "time_scope": "recent"},
        ),
        stage_constraints={"retrieval_budget": 3},
        execution_state={},
        retrieval_facade=facade,
        external_context_retriever=external_retriever,
    )

    self.assertEqual(result.status, "success")
    self.assertEqual(len(facade.calls), 0)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.unit.test_orchestrator_stage_runners -v`

Expected: 当前实现总会查本地 RAG，新增测试失败。

- [ ] **Step 3: 最小改造 runner，只在 source_status 指明需要时补本地 RAG**

```python
# 目标行为：
# 1. 先调 external_context_retriever.retrieve_event_context(...)
# 2. 读取返回里的 source_status.local_rag_needed
# 3. 只有为 True 或外部结果明显不足时，才调用 retrieval_facade.retrieve_evidence(...)
# 4. 若 dual_primary 命中已足够，不再默认查本地 RAG
```

具体要求：

- `external_payload` 足够时：
  - `local_evidence_count` 可以为 0
- 外部结果弱时：
  - 只补一次本地 RAG
- `source_status.mode` 需保留到 stage 输出里

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.unit.test_orchestrator_stage_runners -v`

Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add backend/src/finsight_agent/control_plane/orchestrator/stage_runners/collect_event_context.py tests/unit/test_orchestrator_stage_runners.py
git commit -m "feat: 改造事件上下文阶段为条件RAG"
```

### Task 10: 改造 analyze_targets 候选发现消费新的 discover_candidates 结果

**Files:**
- Modify: `backend/src/finsight_agent/control_plane/orchestrator/stage_runners/analyze_targets.py`
- Test: `tests/unit/test_orchestrator_stage_runners.py`

- [ ] **Step 1: 写失败单测，固定 candidate discovery 返回候选与 evidence refs 后可继续分析**

```python
def test_analyze_targets_stage_uses_discovered_candidates_from_dual_source_retriever(self) -> None:
    from finsight_agent.control_plane.orchestrator.stage_runners.analyze_targets import (
        run_analyze_targets_stage,
    )

    external_retriever = _StubExternalContextRetriever(
        candidate_discovery_payload={
            "candidates": ["中远海能", "招商轮船"],
            "evidence_refs": ["cninfo:1"],
        }
    )
    target_analysis_service = _StubTargetAnalysisService(
        {
            "target_scope": ["中远海能"],
            "ranked_targets": [
                {
                    "target": "中远海能",
                    "target_type": "company",
                    "impact_direction": "positive",
                    "reasoning_summary": "航运运价弹性相关。",
                    "confidence": "medium",
                }
            ],
            "open_questions": [],
            "confidence": "medium",
        }
    )

    execution_state = {
        "collect_event_context": StageExecutionResult(
            stage_name="collect_event_context",
            status="success",
            output_payload={"event_context": {"event": "红海局势升级", "themes": ["航运"]}},
        )
    }

    result = run_analyze_targets_stage(
        request=_build_request(query="红海局势升级利好哪些A股航运股？"),
        router_result=_build_router_result(
            intent="event_impact_analysis",
            entities={"event": "红海局势升级", "themes": ["航运"]},
        ),
        stage_constraints={"candidate_discovery_budget": 1},
        execution_state=execution_state,
        session_context=SessionContext(session_id="sess_001"),
        external_context_retriever=external_retriever,
        target_analysis_service=target_analysis_service,
    )

    self.assertEqual(result.status, "success")
    self.assertEqual(result.output_payload["target_scope"], ["中远海能"])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.unit.test_orchestrator_stage_runners -v`

Expected: 当前 discover_candidates 语义较弱或未覆盖新 payload，测试失败。

- [ ] **Step 3: 最小改造 analyze_targets**

```python
# 调整点：
# - discover_candidates 继续只补一轮
# - 优先消费 payload["candidates"]
# - 保留“找不到仍诚实降级”
# - 不因为 discover_candidates 返回辅助 evidence refs 就改变主流程语义
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.unit.test_orchestrator_stage_runners -v`

Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add backend/src/finsight_agent/control_plane/orchestrator/stage_runners/analyze_targets.py tests/unit/test_orchestrator_stage_runners.py
git commit -m "feat: 改造候选发现阶段消费双层检索结果"
```

### Task 11: 在 OrchestratorService 中装配真实 dual-source retriever

**Files:**
- Modify: `backend/src/finsight_agent/control_plane/orchestrator/service.py`
- Test: `tests/unit/test_orchestrator_service.py`

- [ ] **Step 1: 写失败单测，固定默认构造时不再是 NullExternalContextRetriever**

```python
def test_orchestrator_service_builds_real_external_context_retriever_by_default(self) -> None:
    service = OrchestratorService()
    self.assertNotEqual(
        service._external_context_retriever.__class__.__name__,
        "NullExternalContextRetriever",
    )
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.unit.test_orchestrator_service -v`

Expected: 当前默认仍是 `NullExternalContextRetriever`。

- [ ] **Step 3: 修改 service 默认装配**

```python
# 在 orchestrator service 中：
# - 若 external_context_retriever 未传入
# - 默认构造 DualSourceExternalContextRetriever
# - 默认注入：
#   - StubRetrievalStrategyClassifier
#   - ContextRetrievalPlanner
#   - GdeltEventSearchProvider
#   - OfficialDisclosureSearchProvider
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.unit.test_orchestrator_service -v`

Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add backend/src/finsight_agent/control_plane/orchestrator/service.py tests/unit/test_orchestrator_service.py
git commit -m "feat: 默认装配双层外部上下文检索器"
```

### Task 12: 补事件链端到端集成测试

**Files:**
- Modify: `tests/integration/test_event_impact_analysis_flow.py`

- [ ] **Step 1: 新增集成断言，固定 dual-source provider 结果会进入 execution trace 与最终 summary**

```python
def test_event_impact_analysis_records_dual_source_context_status(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        workbench_service = WorkbenchBackendApiService(
            router_service=_StubRouterService(),
            planner_service=_StubPlannerService(),
            orchestrator_service=OrchestratorService(
                retrieval_facade=_StubRetrievalFacade(),
                external_context_retriever=_StubExternalContextRetriever(),
                target_analysis_service=_StubTargetAnalysisService(),
            ),
            session_service=SessionService(
                repository=SessionRepository(storage_dir=Path(temp_dir) / "sessions")
            ),
        )

        envelope = workbench_service.build_response(
            AnalysisRequest(
                query="红海局势升级利好哪些A股航运公司？",
                include_trace=True,
            )
        )

    self.assertEqual(envelope.response.response_type, "success")
    self.assertTrue(envelope.trace_blocks)
```

- [ ] **Step 2: 运行测试确认当前覆盖不足或失败**

Run: `python -m unittest tests.integration.test_event_impact_analysis_flow -v`

Expected: 新增断言不通过或还未覆盖新 source status。

- [ ] **Step 3: 最小补充集成断言和 stub**

```python
# 保持已有 integration 风格：
# - 使用 stub provider，不访问真实网络
# - 断言双层 provider 的结果进入事件链
# - 不把集成测试绑到外网可用性
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.integration.test_event_impact_analysis_flow -v`

Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add tests/integration/test_event_impact_analysis_flow.py
git commit -m "test: 补充双层事件上下文检索集成覆盖"
```

### Task 13: 运行回归并同步状态文档

**Files:**
- Modify: `docs/finsight/project-status.md`
- Modify: `docs/finsight/modules/control-plane-status.md`
- Modify: `docs/finsight/modules/data-evidence-status.md`

- [ ] **Step 1: 跑关键单测和集成回归**

Run:

```bash
python -m unittest tests.unit.test_external_context_retriever tests.unit.test_context_retrieval_planner tests.unit.test_gdelt_event_search tests.unit.test_official_disclosure_search tests.unit.test_orchestrator_service tests.unit.test_orchestrator_stage_runners tests.integration.test_event_impact_analysis_flow -v
```

Expected: 全部通过。

- [ ] **Step 2: 同步状态文档**

文档中至少更新这些点：

- `event_impact_analysis` 外部工具检索已接入首版真实 provider
- 外部层已拆成：
  - `GDELT`
  - `CNInfo / SSE`
- `collect_event_context` 已改为自适应/条件 RAG
- 分类器训练仍是独立子项目，当前主流程使用 stub/fallback

- [ ] **Step 3: 提交**

```bash
git add docs/finsight/project-status.md docs/finsight/modules/control-plane-status.md docs/finsight/modules/data-evidence-status.md
git commit -m "docs: 同步双层事件上下文检索状态"
```

## Self-Review

### Spec coverage

- `EventSearchProvider`：Task 4 覆盖
- `DisclosureSearchProvider`：Task 5、Task 6、Task 7 覆盖
- `RetrievalStrategyClassifier`：Task 1 覆盖
- `ContextRetrievalPlanner`：Task 3 覆盖
- `DualSourceExternalContextRetriever`：Task 8 覆盖
- `collect_event_context` 条件 RAG：Task 9 覆盖
- 候选发现补搜索：Task 10 覆盖
- orchestrator 默认装配：Task 11 覆盖
- 集成与状态同步：Task 12、Task 13 覆盖

### Placeholder scan

- 未使用 `TBD`、`TODO`、`implement later`
- 每个任务都给出具体文件、测试、命令和最小代码骨架

### Type consistency

- 策略标签统一为：
  - `event_primary`
  - `disclosure_primary`
  - `dual_primary`
- GDELT provider 方法统一为：
  - `search_event_context(...)`
- 披露 provider 方法统一为：
  - `search(...)`
- 组合 retriever 协议仍维持：
  - `retrieve_event_context(...)`
  - `discover_candidates(...)`

