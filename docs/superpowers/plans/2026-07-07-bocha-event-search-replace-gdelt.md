# Bocha Event Search Provider Replace GDELT Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `event_impact_analysis` 链路中的事件搜索 provider 从 GDELT 整体替换为博查（Bocha）Web Search API，并引入 `EventSearchProvider` Protocol 作为事件搜索层的抽象边界。

**Architecture:** 新建 `EventSearchProvider` Protocol（与现有 `ExternalContextRetriever` Protocol 同侧），新建 `BochaEventSearchProvider` 作为首版默认实现，`OrchestratorService` 默认装配改为 Bocha；GDELT 相关源码、测试、根目录 ad-hoc 脚本、docs 中 GDELT 描述全部下线或更新；新增"无 GDELT 残留"护栏测试防止误回潮。

**Tech Stack:** Python 3.x + `urllib.request`（沿用项目所有外部请求的统一栈）+ `dataclasses` + 标准 `unittest`（项目统一测试框架）；不引入新依赖。

**Spec:** `docs/superpowers/specs/2026-07-06-bocha-event-search-replace-gdelt-design.md`（baseline）。本计划是 spec 的可执行版本。

---

## Global Constraints

1. **网络栈**：所有外部 HTTP 请求使用 `urllib.request`，**不引入 `requests`**。与 GDELT / Guardian / CNInfo / SSE 现有 provider 保持一致。
2. **失败语义**：Bocha 任何异常（HTTP / 网络 / 解析 / 空响应 / 入参空）一律翻译成 `ExternalContextResult(items=[], source_status={"bocha_used": False, ..., "error": "<tag>"})`，**绝不向上抛**。
3. **日志**：仅在 `WARNING` 级别打 1 行，格式 `bocha search failed: error=<tag> query_len=<int>`。**不打印** query 原文 / API key / payload。
4. **配置**：API key 走环境变量 `BOCHA_API_KEY`，**不写 YAML**；构造期缺失即抛 `RuntimeError("BOCHA_API_KEY is required: pass api_key=... or set BOCHA_API_KEY env")`。
5. **零网络依赖**：所有单测使用 stub fetcher，不发起任何真实 HTTP 请求；真实 Bocha 调用只通过根目录 `test_bocha.py` 手动触发，不进 CI。
6. **证据引用前缀**：从 `gdelt:item_001` 改为 `bocha:item_001`（3 位零填充）；现有 `gdelt:` 字面量同步迁移。
7. **TDD 节奏**：每个任务遵循"写失败测试 → 跑确认红 → 实现 → 跑确认绿 → commit"的 5 步节拍；简单 string 迁移类任务可以省略步骤 1-2 但保留 commit。
8. **commit message**：使用约定式（`feat:` / `fix:` / `test:` / `docs:` / `chore:` 开头），单文件/单职责 commit；不批量。
9. **分支**：当前在 `feat/phase1-project-runnable`，本计划在该分支上线性提交；不创建新分支、不开 worktree。
10. **不要触碰**：`OfficialDisclosureSearchProvider`（巨潮 + 上交所）、`DualSourceExternalContextRetriever` 合并逻辑、`RetrievalStrategyClassifier`、`ContextRetrievalPlanner`、Local RAG、structured data 链路。

---

## Task 1: Add `EventSearchProvider` Protocol

**Files:**
- Create: `backend/src/finsight_agent/control_plane/orchestrator/event_search_provider.py`
- Test: `tests/unit/test_event_search_provider_contract.py`（新建，契约测试）

**Interfaces:**
- Consumes: `finsight_agent.control_plane.orchestrator.context_retrieval_models.ExternalContextResult`（已存在）
- Produces: `EventSearchProvider` Protocol，方法签名 `search_event_context(*, query: str, event: str, themes: list[str], time_scope: str, limit: int) -> ExternalContextResult`

**位置说明**：与现有 `ExternalContextRetriever` Protocol 同放在 `control_plane/orchestrator/`（consumer-owned 风格），便于 orchestrator 一并导入。

- [ ] **Step 1: 写失败测试**

新建文件 `tests/unit/test_event_search_provider_contract.py`：

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


class EventSearchProviderProtocolContractTest(unittest.TestCase):
    def test_protocol_can_be_imported_and_exposes_search_event_context(self) -> None:
        from finsight_agent.control_plane.orchestrator.event_search_provider import (
            EventSearchProvider,
        )

        # Protocol 本身只要求属性/方法存在；具体实现由后续 task 给出
        self.assertTrue(hasattr(EventSearchProvider, "search_event_context"))

    def test_protocol_signature_matches_existing_call_site(self) -> None:
        """验证 Protocol 方法签名与 dual_source_context_retriever.py:126 调用点一致。"""
        import inspect

        from finsight_agent.control_plane.orchestrator.event_search_provider import (
            EventSearchProvider,
        )

        sig = inspect.signature(EventSearchProvider.search_event_context)
        params = list(sig.parameters.keys())
        # 调用方传的关键字：query, event, themes, time_scope, limit
        for required in ("query", "event", "themes", "time_scope", "limit"):
            self.assertIn(required, params, f"missing param: {required}")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认红**

Run: `cd "c:\D\大模型课程\openspec测试项目" && python -m unittest tests.unit.test_event_search_provider_contract -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'finsight_agent.control_plane.orchestrator.event_search_provider'`（或类似 ImportError）

- [ ] **Step 3: 实现 Protocol**

新建文件 `backend/src/finsight_agent/control_plane/orchestrator/event_search_provider.py`：

```python
from __future__ import annotations

from typing import Protocol

from finsight_agent.control_plane.orchestrator.context_retrieval_models import (
    ExternalContextResult,
)


class EventSearchProvider(Protocol):
    """事件搜索 provider 协议。

    orchestrator 只依赖这层抽象，避免直接绑定具体事件搜索服务（GDELT / Bocha / 未来其他）。
    与 DisclosureSearchProvider 不同：本协议由事件搜索 consumer 拥有，
    因此与 ExternalContextRetriever Protocol 同侧放在 control_plane/orchestrator/。
    """

    def search_event_context(
        self,
        *,
        query: str,
        event: str,
        themes: list[str],
        time_scope: str,
        limit: int,
    ) -> ExternalContextResult:
        """检索事件背景材料，并返回标准化上下文片段。"""
```

- [ ] **Step 4: 跑测试确认绿**

Run: `cd "c:\D\大模型课程\openspec测试项目" && python -m unittest tests.unit.test_event_search_provider_contract -v`
Expected: PASS, 2 个用例全过

- [ ] **Step 5: Commit**

```bash
cd "c:\D\大模型课程\openspec测试项目"
git add backend/src/finsight_agent/control_plane/orchestrator/event_search_provider.py tests/unit/test_event_search_provider_contract.py
git commit -m "feat(orchestrator): add EventSearchProvider protocol"
```

---

## Task 2: Add `BochaEventSearchProvider` + `BochaHttpFetcher`

**Files:**
- Create: `backend/src/finsight_agent/infra/external/bocha_event_search.py`
- Test: `tests/unit/test_bocha_event_search.py`（新建，23 个用例）

**Interfaces:**
- Consumes: `EventSearchProvider` Protocol（Task 1）；`ExternalContextItem` / `ExternalContextResult`（已存在）；环境变量 `BOCHA_API_KEY`；stub fetcher（测试）
- Produces: `BochaEventSearchProvider`（实现 Protocol）、`BochaHttpFetcher`（urllib POST 封装）

**常量定义**：
- `BOCHA_WEB_SEARCH_URL = "https://api.bochaai.com/v1/web-search"`
- `BOCHA_FRESHNESS = "oneWeek"`（固定写死，不走 time_scope 映射）
- `BOCHA_USER_AGENT = "finsight-bocha-search/1.0"`

- [ ] **Step 1: 写失败测试骨架（happy path + 关键映射）**

新建 `tests/unit/test_bocha_event_search.py`：

```python
from __future__ import annotations

import json
import sys
import unittest
import urllib.error
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


class _StubBochaFetcher:
    def __init__(self, payload=None, side_effect=None):
        self._payload = payload
        self._side_effect = side_effect
        self.calls = []

    def post_json(self, url, *, headers, body):
        self.calls.append({"url": url, "headers": headers, "body": body})
        if self._side_effect is not None:
            raise self._side_effect
        return self._payload or {"data": {"webPages": {"value": []}}}


_FULL_PAYLOAD = {
    "data": {
        "webPages": {
            "value": [
                {
                    "id": "https://example.com/a",
                    "name": "红海航运受阻 油运价格连涨三周",
                    "url": "https://example.com/a",
                    "siteName": "财联社",
                    "datePublished": "2026-07-04T10:23:00",
                    "snippet": "受红海局势持续升级影响，全球航运受阻。",
                    "summary": "红海局势升级导致苏伊士航线绕行成本上升，国际油运价格连续三周上涨。国内中远海能、招商轮船等航运企业近期订单及运价数据均出现显著回升。",
                },
                {
                    "name": "A股航运板块走强",
                    "url": "https://example.com/b",
                    "datePublished": "2026-07-03T09:00:00",
                    "snippet": "中远海能、招商轮船领涨。",
                    "summary": "受地缘冲突影响，A股航运板块今日普遍走强。",
                },
                {
                    "name": "油运价格周报",
                    "url": "https://example.com/c",
                    "datePublished": "2026-07-02T08:00:00",
                    "snippet": "本周油运价格继续上行。",
                    "summary": "",
                },
            ]
        }
    }
}


class BochaEventSearchProviderTest(unittest.TestCase):
    def test_search_returns_standardized_context_result(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        provider = BochaEventSearchProvider(
            api_key="test-key", fetcher=_StubBochaFetcher(payload=_FULL_PAYLOAD)
        )
        result = provider.search_event_context(
            query="红海局势升级利好哪些A股航运股？",
            event="红海局势升级",
            themes=["航运", "油运"],
            time_scope="recent",
            limit=3,
        )

        self.assertEqual(len(result.items), 3)
        self.assertEqual(result.items[0].source, "bocha")
        self.assertEqual(result.items[0].title, "红海航运受阻 油运价格连涨三周")
        self.assertEqual(result.items[0].publish_date, "2026-07-04T10:23:00")
        self.assertEqual(result.items[0].url, "https://example.com/a")
        self.assertEqual(result.items[0].themes, ["航运", "油运"])
        # snippet 优先 summary；第 3 条 summary 空则回退 snippet
        self.assertIn("苏伊士航线绕行成本上升", result.items[0].snippet)
        self.assertEqual(result.items[2].snippet, "本周油运价格继续上行。")
        # summary_hint / supporting_points
        self.assertEqual(result.summary_hint, "红海航运受阻 油运价格连涨三周")
        self.assertEqual(len(result.supporting_points), 2)
        # evidence_refs 形如 bocha:item_001
        self.assertEqual(
            result.evidence_refs, ["bocha:item_001", "bocha:item_002", "bocha:item_003"]
        )
        # candidate_hints == themes
        self.assertEqual(result.candidate_hints, ["航运", "油运"])
        # source_status
        self.assertTrue(result.source_status["bocha_used"])
        self.assertEqual(result.source_status["freshness"], "oneWeek")
        self.assertEqual(result.source_status["time_scope"], "recent")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认红**

Run: `cd "c:\D\大模型课程\openspec测试项目" && python -m unittest tests.unit.test_bocha_event_search -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'finsight_agent.infra.external.bocha_event_search'`

- [ ] **Step 3: 实现 `BochaEventSearchProvider` + `BochaHttpFetcher`**

新建 `backend/src/finsight_agent/infra/external/bocha_event_search.py`：

```python
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from finsight_agent.control_plane.orchestrator.context_retrieval_models import (
    ExternalContextItem,
    ExternalContextResult,
)


_logger = logging.getLogger(__name__)

BOCHA_WEB_SEARCH_URL = "https://api.bochaai.com/v1/web-search"
BOCHA_FRESHNESS = "oneWeek"
BOCHA_USER_AGENT = "finsight-bocha-search/1.0"


@dataclass(slots=True)
class BochaHttpFetcher:
    """Bocha HTTP 客户端：仅负责发 POST + 解 JSON，不做错误翻译。"""

    timeout_seconds: float = 30.0

    def post_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        body: dict[str, object],
    ) -> dict[str, object]:
        data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(url, data=data, method="POST")
        for key, value in headers.items():
            request.add_header(key, value)
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))


class BochaEventSearchProvider:
    """Bocha 事件搜索 provider（首版默认事件搜索实现）。"""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        fetcher: BochaHttpFetcher | None = None,
    ) -> None:
        resolved_key = api_key if api_key is not None else os.environ.get("BOCHA_API_KEY")
        if not resolved_key:
            raise RuntimeError(
                "BOCHA_API_KEY is required: pass api_key=... or set BOCHA_API_KEY env"
            )
        self._api_key = resolved_key
        self._fetcher = fetcher or BochaHttpFetcher()

    def search_event_context(
        self,
        *,
        query: str,
        event: str,
        themes: list[str],
        time_scope: str,
        limit: int,
    ) -> ExternalContextResult:
        composed_query = " ".join(
            part for part in (query, event, *themes) if part
        ).strip()
        if not composed_query:
            return self._empty_result(themes, time_scope, error="empty_query")

        body = {
            "query": composed_query,
            "freshness": BOCHA_FRESHNESS,
            "summary": True,
            "count": limit,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "User-Agent": BOCHA_USER_AGENT,
        }

        try:
            payload = self._fetcher.post_json(
                BOCHA_WEB_SEARCH_URL, headers=headers, body=body
            )
        except urllib.error.HTTPError as exc:
            tag = f"http_{exc.code}"
            _logger.warning(
                "bocha search failed: error=%s query_len=%d", tag, len(composed_query)
            )
            return self._empty_result(themes, time_scope, error=tag)
        except urllib.error.URLError:
            _logger.warning(
                "bocha search failed: error=timeout query_len=%d", len(composed_query)
            )
            return self._empty_result(themes, time_scope, error="timeout")
        except json.JSONDecodeError:
            _logger.warning(
                "bocha search failed: error=invalid_json query_len=%d",
                len(composed_query),
            )
            return self._empty_result(themes, time_scope, error="invalid_json")
        except Exception:
            _logger.warning(
                "bocha search failed: error=unknown query_len=%d", len(composed_query)
            )
            return self._empty_result(themes, time_scope, error="unknown")

        value_list = (
            (payload.get("data") or {}).get("webPages", {}).get("value") or []
        )
        if not value_list:
            return self._empty_result(themes, time_scope, error="empty_response")

        items = self._map_items(value_list[:limit], themes)
        return ExternalContextResult(
            items=items,
            summary_hint=items[0].title if items else "",
            supporting_points=[(item.snippet or item.title) for item in items[:2]],
            evidence_refs=[
                f"bocha:item_{idx:03d}" for idx in range(1, len(items) + 1)
            ],
            candidate_hints=list(themes),
            source_status={
                "bocha_used": True,
                "freshness": BOCHA_FRESHNESS,
                "time_scope": time_scope,
            },
        )

    @staticmethod
    def _map_items(value_list: list[dict[str, object]], themes: list[str]) -> list[ExternalContextItem]:
        items: list[ExternalContextItem] = []
        for entry in value_list:
            title = str(entry.get("name") or "").strip()
            url = str(entry.get("url") or "").strip()
            publish_date = str(entry.get("datePublished") or "").strip()
            # snippet 三级兜底：summary → snippet → name
            snippet = (
                str(entry.get("summary") or "").strip()
                or str(entry.get("snippet") or "").strip()
                or title
            )
            items.append(
                ExternalContextItem(
                    title=title,
                    source="bocha",
                    publish_date=publish_date,
                    url=url,
                    snippet=snippet,
                    themes=list(themes),
                )
            )
        return items

    @staticmethod
    def _empty_result(
        themes: list[str], time_scope: str, *, error: str
    ) -> ExternalContextResult:
        return ExternalContextResult(
            items=[],
            summary_hint="",
            supporting_points=[],
            evidence_refs=[],
            candidate_hints=list(themes),
            source_status={
                "bocha_used": False,
                "freshness": BOCHA_FRESHNESS,
                "time_scope": time_scope,
                "error": error,
            },
        )
```

- [ ] **Step 4: 跑测试确认绿（happy path）**

Run: `cd "c:\D\大模型课程\openspec测试项目" && python -m unittest tests.unit.test_bocha_event_search.BochaEventSearchProviderTest.test_search_returns_standardized_context_result -v`
Expected: PASS

- [ ] **Step 5: 追加其余 22 个用例**

在同一个 `tests/unit/test_bocha_event_search.py` 文件中追加以下测试方法（保持 `BochaEventSearchProviderTest` 类内），每个方法独立可跑：

```python
    def test_snippet_prefers_summary_then_snippet_then_name(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        payload = {
            "data": {
                "webPages": {
                    "value": [
                        {"name": "n1", "url": "u1", "snippet": "s1", "summary": "sum1"},
                        {"name": "n2", "url": "u2", "snippet": "s2"},  # 无 summary
                        {"name": "n3", "url": "u3"},  # 都无
                    ]
                }
            }
        }
        provider = BochaEventSearchProvider(
            api_key="test-key", fetcher=_StubBochaFetcher(payload=payload)
        )
        result = provider.search_event_context(
            query="q", event="e", themes=[], time_scope="recent", limit=3
        )
        self.assertEqual(result.items[0].snippet, "sum1")
        self.assertEqual(result.items[1].snippet, "s2")
        self.assertEqual(result.items[2].snippet, "n3")

    def test_publish_date_passed_through_as_is(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        payload = {
            "data": {
                "webPages": {
                    "value": [
                        {
                            "name": "n",
                            "url": "u",
                            "datePublished": "2026-07-04T10:23:00",
                            "summary": "s",
                        }
                    ]
                }
            }
        }
        provider = BochaEventSearchProvider(
            api_key="test-key", fetcher=_StubBochaFetcher(payload=payload)
        )
        result = provider.search_event_context(
            query="q", event="e", themes=[], time_scope="recent", limit=1
        )
        self.assertEqual(result.items[0].publish_date, "2026-07-04T10:23:00")

    def test_themes_passed_through_into_items(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        payload = {
            "data": {
                "webPages": {
                    "value": [{"name": "n", "url": "u", "summary": "s"}]
                }
            }
        }
        provider = BochaEventSearchProvider(
            api_key="test-key", fetcher=_StubBochaFetcher(payload=payload)
        )
        result = provider.search_event_context(
            query="q",
            event="e",
            themes=["航运", "油运"],
            time_scope="recent",
            limit=1,
        )
        self.assertEqual(result.items[0].themes, ["航运", "油运"])

    def test_candidate_hints_are_input_themes(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        payload = {
            "data": {
                "webPages": {
                    "value": [{"name": "n", "url": "u", "summary": "s"}]
                }
            }
        }
        provider = BochaEventSearchProvider(
            api_key="test-key", fetcher=_StubBochaFetcher(payload=payload)
        )
        result = provider.search_event_context(
            query="q",
            event="e",
            themes=["航运"],
            time_scope="recent",
            limit=1,
        )
        self.assertEqual(result.candidate_hints, ["航运"])

    def test_evidence_refs_use_bocha_prefix(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        provider = BochaEventSearchProvider(
            api_key="test-key", fetcher=_StubBochaFetcher(payload=_FULL_PAYLOAD)
        )
        result = provider.search_event_context(
            query="q", event="e", themes=[], time_scope="recent", limit=3
        )
        self.assertEqual(
            result.evidence_refs,
            ["bocha:item_001", "bocha:item_002", "bocha:item_003"],
        )

    def test_evidence_refs_match_item_count(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        provider = BochaEventSearchProvider(
            api_key="test-key", fetcher=_StubBochaFetcher(payload=_FULL_PAYLOAD)
        )
        result = provider.search_event_context(
            query="q", event="e", themes=[], time_scope="recent", limit=3
        )
        self.assertEqual(len(result.evidence_refs), len(result.items))

    def test_handles_empty_webpages_value(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        provider = BochaEventSearchProvider(
            api_key="test-key",
            fetcher=_StubBochaFetcher(payload={"data": {"webPages": {"value": []}}}),
        )
        result = provider.search_event_context(
            query="q", event="e", themes=["t"], time_scope="recent", limit=3
        )
        self.assertEqual(result.items, [])
        self.assertEqual(result.evidence_refs, [])
        self.assertFalse(result.source_status["bocha_used"])
        self.assertEqual(result.source_status["error"], "empty_response")

    def test_handles_missing_webpages_field(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        provider = BochaEventSearchProvider(
            api_key="test-key",
            fetcher=_StubBochaFetcher(payload={"data": {}}),
        )
        result = provider.search_event_context(
            query="q", event="e", themes=["t"], time_scope="recent", limit=3
        )
        self.assertEqual(result.source_status["error"], "empty_response")

    def test_handles_missing_data_field(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        provider = BochaEventSearchProvider(
            api_key="test-key", fetcher=_StubBochaFetcher(payload={"other": "stuff"})
        )
        result = provider.search_event_context(
            query="q", event="e", themes=["t"], time_scope="recent", limit=3
        )
        self.assertEqual(result.source_status["error"], "empty_response")

    def test_handles_http_error_401(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        provider = BochaEventSearchProvider(
            api_key="test-key",
            fetcher=_StubBochaFetcher(side_effect=urllib.error.HTTPError(
                url="http://x", code=401, msg="Unauthorized", hdrs=None, fp=None
            )),
        )
        result = provider.search_event_context(
            query="q", event="e", themes=["t"], time_scope="recent", limit=3
        )
        self.assertEqual(result.source_status["error"], "http_401")
        self.assertFalse(result.source_status["bocha_used"])

    def test_handles_http_error_429(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        provider = BochaEventSearchProvider(
            api_key="test-key",
            fetcher=_StubBochaFetcher(side_effect=urllib.error.HTTPError(
                url="http://x", code=429, msg="Too Many", hdrs=None, fp=None
            )),
        )
        result = provider.search_event_context(
            query="q", event="e", themes=["t"], time_scope="recent", limit=3
        )
        self.assertEqual(result.source_status["error"], "http_429")

    def test_handles_urlerror_timeout(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        provider = BochaEventSearchProvider(
            api_key="test-key",
            fetcher=_StubBochaFetcher(side_effect=urllib.error.URLError("timeout")),
        )
        result = provider.search_event_context(
            query="q", event="e", themes=["t"], time_scope="recent", limit=3
        )
        self.assertEqual(result.source_status["error"], "timeout")

    def test_handles_json_decode_error(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        class _BadJsonFetcher:
            def post_json(self, url, *, headers, body):
                raise json.JSONDecodeError("bad", "", 0)

        provider = BochaEventSearchProvider(
            api_key="test-key", fetcher=_BadJsonFetcher()
        )
        result = provider.search_event_context(
            query="q", event="e", themes=["t"], time_scope="recent", limit=3
        )
        self.assertEqual(result.source_status["error"], "invalid_json")

    def test_limit_truncates_items(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        # Bocha 返回 5 条，limit=3
        big_payload = {
            "data": {
                "webPages": {
                    "value": [
                        {"name": f"n{i}", "url": f"u{i}", "summary": f"s{i}"}
                        for i in range(5)
                    ]
                }
            }
        }
        provider = BochaEventSearchProvider(
            api_key="test-key", fetcher=_StubBochaFetcher(payload=big_payload)
        )
        result = provider.search_event_context(
            query="q", event="e", themes=[], time_scope="recent", limit=3
        )
        self.assertEqual(len(result.items), 3)
        self.assertEqual(len(result.evidence_refs), 3)

    def test_constructor_raises_without_api_key(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        # 确保 env 也没设置
        import os

        old = os.environ.pop("BOCHA_API_KEY", None)
        try:
            with self.assertRaises(RuntimeError) as ctx:
                BochaEventSearchProvider()
            self.assertIn("BOCHA_API_KEY", str(ctx.exception))
        finally:
            if old is not None:
                os.environ["BOCHA_API_KEY"] = old

    def test_summary_hint_uses_first_item_title(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        provider = BochaEventSearchProvider(
            api_key="test-key", fetcher=_StubBochaFetcher(payload=_FULL_PAYLOAD)
        )
        result = provider.search_event_context(
            query="q", event="e", themes=[], time_scope="recent", limit=3
        )
        self.assertEqual(result.summary_hint, result.items[0].title)
        self.assertEqual(result.summary_hint, "红海航运受阻 油运价格连涨三周")

    def test_supporting_points_take_first_two(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        provider = BochaEventSearchProvider(
            api_key="test-key", fetcher=_StubBochaFetcher(payload=_FULL_PAYLOAD)
        )
        result = provider.search_event_context(
            query="q", event="e", themes=[], time_scope="recent", limit=3
        )
        self.assertLessEqual(len(result.supporting_points), 2)
        self.assertEqual(result.supporting_points[0], result.items[0].snippet)

    def test_request_body_uses_one_week_freshness(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BOCHA_FRESHNESS,
            BochaEventSearchProvider,
        )

        fetcher = _StubBochaFetcher(payload=_FULL_PAYLOAD)
        provider = BochaEventSearchProvider(api_key="test-key", fetcher=fetcher)
        provider.search_event_context(
            query="q", event="e", themes=[], time_scope="recent", limit=3
        )
        self.assertEqual(fetcher.calls[0]["body"]["freshness"], BOCHA_FRESHNESS)
        self.assertEqual(fetcher.calls[0]["body"]["freshness"], "oneWeek")

    def test_request_body_passes_count_as_limit(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        fetcher = _StubBochaFetcher(payload=_FULL_PAYLOAD)
        provider = BochaEventSearchProvider(api_key="test-key", fetcher=fetcher)
        provider.search_event_context(
            query="q", event="e", themes=[], time_scope="recent", limit=7
        )
        self.assertEqual(fetcher.calls[0]["body"]["count"], 7)

    def test_request_body_sets_summary_true(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        fetcher = _StubBochaFetcher(payload=_FULL_PAYLOAD)
        provider = BochaEventSearchProvider(api_key="test-key", fetcher=fetcher)
        provider.search_event_context(
            query="q", event="e", themes=[], time_scope="recent", limit=3
        )
        self.assertIs(fetcher.calls[0]["body"]["summary"], True)

    def test_request_headers_include_bearer_token(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        fetcher = _StubBochaFetcher(payload=_FULL_PAYLOAD)
        provider = BochaEventSearchProvider(api_key="my-secret-key", fetcher=fetcher)
        provider.search_event_context(
            query="q", event="e", themes=[], time_scope="recent", limit=3
        )
        auth = fetcher.calls[0]["headers"]["Authorization"]
        self.assertTrue(auth.startswith("Bearer "))
        self.assertIn("my-secret-key", auth)

    def test_empty_query_returns_empty_result(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        fetcher = _StubBochaFetcher(payload=_FULL_PAYLOAD)
        provider = BochaEventSearchProvider(api_key="test-key", fetcher=fetcher)
        result = provider.search_event_context(
            query="", event="", themes=[], time_scope="recent", limit=3
        )
        self.assertEqual(result.items, [])
        self.assertEqual(result.source_status["error"], "empty_query")
        # 不调 fetcher
        self.assertEqual(fetcher.calls, [])
```

- [ ] **Step 6: 跑全部新测试确认全绿**

Run: `cd "c:\D\大模型课程\openspec测试项目" && python -m unittest tests.unit.test_bocha_event_search -v`
Expected: 23 个用例全过（1 happy path + 22 边界/错误/请求体）

- [ ] **Step 7: Commit**

```bash
cd "c:\D\大模型课程\openspec测试项目"
git add backend/src/finsight_agent/infra/external/bocha_event_search.py tests/unit/test_bocha_event_search.py
git commit -m "feat(infra): add BochaEventSearchProvider and BochaHttpFetcher with 23 unit tests"
```

---

## Task 3: Wire Bocha as Default `event_search_provider`

**Files:**
- Modify: `backend/src/finsight_agent/control_plane/orchestrator/service.py`（line 17 import、line 155-163 函数体）

**Interfaces:**
- Consumes: `BochaEventSearchProvider`（Task 2）
- Produces: `OrchestratorService` 默认装配走 Bocha；旧 `GdeltEventSearchProvider` 仍可作为可选注入保留（仅本任务改默认装配，不删除旧 import；删除留给 Task 7）

- [ ] **Step 1: 改 import 与默认装配**

编辑 `backend/src/finsight_agent/control_plane/orchestrator/service.py`：

- 第 17 行：将 `from finsight_agent.infra.external.gdelt_event_search import GdeltEventSearchProvider` 替换为：
  ```python
  from finsight_agent.infra.external.bocha_event_search import BochaEventSearchProvider
  ```
- 第 155-163 行：将 `_build_default_external_context_retriever` 改为：
  ```python
  def _build_default_external_context_retriever() -> DualSourceExternalContextRetriever:
      """默认装配免费的双源外部上下文检索链路。"""

      return DualSourceExternalContextRetriever(
          classifier=StubRetrievalStrategyClassifier(),
          planner=ContextRetrievalPlanner(),
          event_search_provider=BochaEventSearchProvider(),
          disclosure_search_provider=OfficialDisclosureSearchProvider(),
      )
  ```

- [ ] **Step 2: 跑既有 orchestrator 单测确认绿（注意：此时 `BOCHA_API_KEY` 未设置会抛 `RuntimeError`）**

环境变量临时设置后跑：

```bash
cd "c:\D\大模型课程\openspec测试项目" && BOCHA_API_KEY=test-key python -m unittest tests.unit.test_orchestrator_service tests.unit.test_orchestrator_stage_runners tests.unit.test_external_context_retriever -v
```

Expected: PASS（这些测试用 stub provider / stub classifier，不会真的构造 `BochaEventSearchProvider()`）

- [ ] **Step 3: 验证 `_build_default_external_context_retriever` 在没有 env 时会抛（这是预期行为，不是 bug）**

Run: `cd "c:\D\大模型课程\openspec测试项目" && python -c "from finsight_agent.control_plane.orchestrator.service import _build_default_external_context_retriever; _build_default_external_context_retriever()"`
Expected: 抛 `RuntimeError("BOCHA_API_KEY is required: ...")`
说明：这是 spec 设计决策，构造期失败优于首次查询期失败。CI/启动脚本需要确保 `BOCHA_API_KEY` 已设置；这一点在 Task 10 同步到 workbench-runbook。

- [ ] **Step 4: Commit**

```bash
cd "c:\D\大模型课程\openspec测试项目"
git add backend/src/finsight_agent/control_plane/orchestrator/service.py
git commit -m "feat(orchestrator): default event_search_provider to BochaEventSearchProvider"
```

---

## Task 4: Migrate Protocol Contract Test Strings

**Files:**
- Modify: `tests/unit/test_external_context_retriever.py`（3 处字面量）

- [ ] **Step 1: 替换 `ContextRetrievalModelsTest` 第 1 处**

打开 `tests/unit/test_external_context_retriever.py`，在 `ContextRetrievalModelsTest` 类的 `test_context_result_and_plan_hold_structured_fields` 方法里：

- `source="gdelt"` → `source="bocha"`

- [ ] **Step 2: 替换 `ContextRetrievalModelsTest` 第 2 处**

同方法内：

- `source_status={"gdelt_used": True}` → `source_status={"bocha_used": True}`

- [ ] **Step 3: 替换 `DualSourceExternalContextRetrieverTest.test_retrieve_event_context_merges_planned_sources` 第 1 处**

在该方法的 `_StubEventProvider(... ExternalContextResult(... evidence_refs=["gdelt:1"], ...))` 调用里：

- `"gdelt:1"` → `"bocha:1"`

- [ ] **Step 4: 跑测试确认绿**

Run: `cd "c:\D\大模型课程\openspec测试项目" && python -m unittest tests.unit.test_external_context_retriever -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd "c:\D\大模型课程\openspec测试项目"
git add tests/unit/test_external_context_retriever.py
git commit -m "test(orchestrator): migrate protocol contract test to bocha prefix"
```

---

## Task 5: Migrate Stage Runner Fixture Strings

**Files:**
- Modify: `tests/unit/test_orchestrator_stage_runners.py`（line 282 与 line 308 各 1 处）

- [ ] **Step 1: 替换 line 282 的 `gdelt:001`**

打开 `tests/unit/test_orchestrator_stage_runners.py`，line 282：

- `"evidence_refs": ["gdelt:001", "cninfo:001"]` → `"evidence_refs": ["bocha:001", "cninfo:001"]`

- [ ] **Step 2: 替换 line 308 的 `gdelt:001`**

同文件 line 308 的断言：

- `self.assertEqual(result.evidence_refs, ["gdelt:001", "cninfo:001"])` → `self.assertEqual(result.evidence_refs, ["bocha:001", "cninfo:001"])`

- [ ] **Step 3: 跑测试确认绿**

Run: `cd "c:\D\大模型课程\openspec测试项目" && BOCHA_API_KEY=test-key python -m unittest tests.unit.test_orchestrator_stage_runners -v`
Expected: PASS（环境变量设 `BOCHA_API_KEY=test-key` 是因为该测试通过 service.py 间接构造默认 retriever；即便用 stub，导入路径仍可能触发 `RuntimeError`）

- [ ] **Step 4: Commit**

```bash
cd "c:\D\大模型课程\openspec测试项目"
git add tests/unit/test_orchestrator_stage_runners.py
git commit -m "test(orchestrator): migrate stage runner fixture to bocha prefix"
```

---

## Task 6: Pin New Files in `test_project_skeleton.py`

**Files:**
- Modify: `tests/unit/test_project_skeleton.py`（line 71-115 `test_minimal_fast_path_files_exist` 的 `required_files` 列表）

**说明**：`test_workbench_runnable_artifacts_exist` 与 `test_minimal_fast_path_files_exist` 当前均未 pin GDELT 文件，所以本次变更只追加、不删除。

- [ ] **Step 1: 在 `required_files` 列表追加 3 项**

打开 `tests/unit/test_project_skeleton.py`，在 `test_minimal_fast_path_files_exist` 方法的 `required_files` 列表末尾（line 114 `"scripts/run_workbench_backend.sh",` 之后）追加：

```python
            "backend/src/finsight_agent/control_plane/orchestrator/event_search_provider.py",
            "backend/src/finsight_agent/infra/external/bocha_event_search.py",
            "tests/unit/test_bocha_event_search.py",
```

注意：保留所有原有条目不动；这三项只是新增。

- [ ] **Step 2: 跑测试确认绿**

Run: `cd "c:\D\大模型课程\openspec测试项目" && python -m unittest tests.unit.test_project_skeleton -v`
Expected: PASS（含 `test_minimal_fast_path_files_exist`）

- [ ] **Step 3: Commit**

```bash
cd "c:\D\大模型课程\openspec测试项目"
git add tests/unit/test_project_skeleton.py
git commit -m "test(skeleton): pin bocha event search artifacts in fast path file list"
```

---

## Task 7: Delete GDELT Files

**Files:**
- Delete: `backend/src/finsight_agent/infra/external/gdelt_event_search.py`
- Delete: `tests/unit/test_gdelt_event_search.py`
- Delete: `test_gedlt.py`（仓库根）
- Delete: `test.py`（仓库根，GDELT BigQuery ad-hoc）

**前置条件**：Task 4-6 已完成，旧 GDELT 文件已无被测试代码引用。

- [ ] **Step 1: 删除 4 个文件**

```bash
cd "c:\D\大模型课程\openspec测试项目"
git rm backend/src/finsight_agent/infra/external/gdelt_event_search.py
git rm tests/unit/test_gdelt_event_search.py
git rm test_gedlt.py
git rm test.py
```

- [ ] **Step 2: 跑既有测试确认无回归（GDELT 文件被删后，曾 import 它们的地方必须已迁移完毕）**

```bash
cd "c:\D\大模型课程\openspec测试项目" && BOCHA_API_KEY=test-key python -m unittest discover -s tests/unit -v 2>&1 | tail -30
```

Expected: PASS；任何 `ImportError: GdeltEventSearchProvider` 出现都说明有遗漏。

- [ ] **Step 3: 跑 integration 测试**

```bash
cd "c:\D\大模型课程\openspec测试项目" && BOCHA_API_KEY=test-key python -m unittest discover -s tests/integration -v 2>&1 | tail -30
```

Expected: PASS；`test_event_impact_analysis_flow` 是关键回归。

- [ ] **Step 4: Commit**

```bash
cd "c:\D\大模型课程\openspec测试项目"
git commit -m "chore: remove gdelt event search and related ad-hoc scripts"
```

---

## Task 8: Add "No GDELT References in Production" Guard Test

**Files:**
- Create: `tests/unit/test_no_gdelt_references_in_production.py`

**扫描范围**：`backend/src/finsight_agent/`（不含 `__pycache__`）的所有 `.py` 文件。
**匹配模式**：`gdelt` / `Gdelt` / `GDELT`（大小写任一）。
**不覆盖**：`docs/`、`openspec/changes/archive/`、本测试自身（避免循环）。

- [ ] **Step 1: 写护栏测试**

新建 `tests/unit/test_no_gdelt_references_in_production.py`：

```python
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_ROOT = REPO_ROOT / "backend" / "src" / "finsight_agent"

_GDELT_PATTERN = re.compile(r"gdelt|Gdelt|GDELT")


class NoGdeltReferencesInProductionTest(unittest.TestCase):
    """方案 A 长期护栏：保证 backend/src/finsight_agent/ 不再出现 GDELT 字面量。"""

    def test_no_gdelt_references_in_backend_src(self):
        offenders: list[str] = []
        for py_file in PRODUCTION_ROOT.rglob("*.py"):
            # 排除 __pycache__ 与自身
            if "__pycache__" in py_file.parts:
                continue
            if py_file.name == "test_no_gdelt_references_in_production.py":
                continue
            text = py_file.read_text(encoding="utf-8")
            for line_no, line in enumerate(text.splitlines(), start=1):
                if _GDELT_PATTERN.search(line):
                    offenders.append(
                        f"{py_file.relative_to(REPO_ROOT)}:{line_no}: {line.strip()}"
                    )
        self.assertEqual(
            offenders,
            [],
            "GDELT references found in production code:\n" + "\n".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认绿**

Run: `cd "c:\D\大模型课程\openspec测试项目" && python -m unittest tests.unit.test_no_gdelt_references_in_production -v`
Expected: PASS

（如果失败，说明 Task 7 漏删或别处有遗漏，先补完再回本任务。）

- [ ] **Step 3: 反向验证：故意加一行 `gdelt = 1` 到某个 production 文件，确认测试会红**

临时 sanity check（不要 commit）：

```bash
cd "c:\D\大模型课程\openspec测试项目" && echo "gdelt_marker = 1" >> backend/src/finsight_agent/control_plane/orchestrator/__init__.py
python -m unittest tests.unit.test_no_gdelt_references_in_production -v
```

Expected: FAIL（报 `__init__.py` 末尾命中）

然后撤销：

```bash
cd "c:\D\大模型课程\openspec测试项目"
# 撤销追加的最后一行
git checkout -- backend/src/finsight_agent/control_plane/orchestrator/__init__.py
```

- [ ] **Step 4: 跑全套单测确认绿**

Run: `cd "c:\D\大模型课程\openspec测试项目" && BOCHA_API_KEY=test-key python -m unittest discover -s tests/unit -v 2>&1 | tail -10`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd "c:\D\大模型课程\openspec测试项目"
git add tests/unit/test_no_gdelt_references_in_production.py
git commit -m "test(guard): add no-gdelt-references-in-production guard test"
```

---

## Task 9: Add Ad-Hoc Bocha Smoke Script at Repo Root

**Files:**
- Create: `test_bocha.py`（仓库根）

**用途**：本地手动触发真实 Bocha API，验证 key 与连接性；**不进 CI**。

- [ ] **Step 1: 写脚本**

新建 `test_bocha.py`（仓库根）：

```python
from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
import urllib.error
import urllib.request
from dataclasses import dataclass


BOCHA_WEB_SEARCH_URL = "https://api.bochaai.com/v1/web-search"


@dataclass(slots=True)
class BochaSmokeResult:
    total: int
    items: list[dict[str, str]]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="测试博查（Bocha）Web Search API 是否可用。",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("BOCHA_API_KEY") or "",
        help=(
            "博查 API key。默认读取环境变量 BOCHA_API_KEY；未设置则报错退出。"
        ),
    )
    parser.add_argument(
        "--query", default="红海局势升级 航运", help="搜索关键词。"
    )
    parser.add_argument("--limit", type=int, default=3, help="返回结果条数。")
    parser.add_argument(
        "--freshness",
        default="oneWeek",
        choices=("noLimit", "oneDay", "oneWeek", "oneMonth", "oneYear"),
        help="时间窗口。默认 oneWeek。",
    )
    return parser


def _fetch_bocha(
    *, api_key: str, query: str, limit: int, freshness: str
) -> BochaSmokeResult:
    body = {
        "query": query,
        "freshness": freshness,
        "summary": True,
        "count": limit,
    }
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(BOCHA_WEB_SEARCH_URL, data=data, method="POST")
    request.add_header("Authorization", f"Bearer {api_key}")
    request.add_header("Content-Type", "application/json")
    request.add_header("User-Agent", "finsight-bocha-smoke-test/1.0")
    with urllib.request.urlopen(request, timeout=30.0) as response:
        payload = json.loads(response.read().decode("utf-8"))
    web_pages = (payload.get("data") or {}).get("webPages", {})
    value = web_pages.get("value") or []
    items: list[dict[str, str]] = []
    for entry in value:
        items.append(
            {
                "name": str(entry.get("name") or "").strip(),
                "url": str(entry.get("url") or "").strip(),
                "datePublished": str(entry.get("datePublished") or "").strip(),
                "snippet": (
                    str(entry.get("summary") or "").strip()
                    or str(entry.get("snippet") or "").strip()
                ),
            }
        )
    return BochaSmokeResult(total=len(items), items=items)


def _print_success(query: str, freshness: str, result: BochaSmokeResult) -> None:
    print("Bocha Web Search 测试成功")
    print(f"query={query}")
    print(f"freshness={freshness}")
    print(f"total={result.total}")
    print()
    if not result.items:
        print("未返回结果，但接口已正常响应。")
        return
    print("前几条结果：")
    for idx, item in enumerate(result.items, start=1):
        print(f"[{idx}] {item['name']}")
        if item["datePublished"]:
            print(f"    published: {item['datePublished']}")
        if item["url"]:
            print(f"    url: {item['url']}")
        if item["snippet"]:
            wrapped = textwrap.fill(
                item["snippet"][:200],
                width=80,
                initial_indent="    snippet: ",
                subsequent_indent="             ",
            )
            print(wrapped)
        print()


def _print_http_error(error: urllib.error.HTTPError) -> None:
    print("Bocha Web Search 测试失败", file=sys.stderr)
    print(f"http_status={error.code}", file=sys.stderr)
    try:
        payload = error.read().decode("utf-8", errors="replace")
    except Exception:
        payload = ""
    if error.code == 401:
        print("原因：API key 无效或缺失。", file=sys.stderr)
    elif error.code == 403:
        print("原因：当前 key 没有访问权限。", file=sys.stderr)
    elif error.code == 429:
        print("原因：触发 Bocha API 限流。", file=sys.stderr)
    else:
        print("原因：Bocha API 返回了非预期 HTTP 错误。", file=sys.stderr)
    if payload:
        print("response_body=", file=sys.stderr)
        print(payload, file=sys.stderr)


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if not args.api_key:
        print("缺少 BOCHA_API_KEY：请传 --api-key 或设置环境变量 BOCHA_API_KEY。", file=sys.stderr)
        return 2

    try:
        result = _fetch_bocha(
            api_key=args.api_key,
            query=args.query,
            limit=args.limit,
            freshness=args.freshness,
        )
    except urllib.error.HTTPError as error:
        _print_http_error(error)
        return 1
    except urllib.error.URLError as error:
        print("Bocha Web Search 测试失败", file=sys.stderr)
        print(f"network_error={error}", file=sys.stderr)
        return 2
    except Exception as error:  # pragma: no cover - smoke 兜底
        print("Bocha Web Search 测试失败", file=sys.stderr)
        print(f"unexpected_error={error}", file=sys.stderr)
        return 3

    _print_success(args.query, args.freshness, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: 语法 + 模块可导入 smoke（不真打网络）**

Run: `cd "c:\D\大模型课程\openspec测试项目" && python -c "import ast; ast.parse(open('test_bocha.py', encoding='utf-8').read()); print('OK')"`
Expected: 打印 `OK`

- [ ] **Step 3: 手动跑一次（仅在有真实 key 的环境执行；本步骤 CI 可跳过）**

```bash
cd "c:\D\大模型课程\openspec测试项目" && BOCHA_API_KEY=<真实key> python test_bocha.py --query "红海局势升级 航运" --limit 3
```

Expected: 打印 `Bocha Web Search 测试成功` + 前几条结果（手工检查标题 / URL / 日期合理）
说明：若本地无 key，可跳过本步骤，提交不影响。

- [ ] **Step 4: Commit**

```bash
cd "c:\D\大模型课程\openspec测试项目"
git add test_bocha.py
git commit -m "chore: add ad-hoc bocha web search smoke script"
```

---

## Task 10: Sync Docs (Runbook + 3 Status Files)

**Files:**
- Modify: `docs/finsight/operations/workbench-runbook.md`（line 126-135 §5.2 整段）
- Modify: `docs/finsight/project-status.md`（line 19, 47, 84）
- Modify: `docs/finsight/modules/control-plane-status.md`（line 93 表格行）
- Modify: `docs/finsight/modules/data-evidence-status.md`（line 41, 70, 83）

**说明**：每份 doc 的精确改动都在 spec §15 "文档清理清单" 中列出，行号已对齐；本任务按 spec 逐文件改。

- [ ] **Step 1: 改 `workbench-runbook.md` §5.2**

打开 `docs/finsight/operations/workbench-runbook.md`，定位 line 126：

```markdown
### 5.2 真实 event_impact_analysis 查询失败 / GDELT 429
```

整段（line 126 至 line 135）替换为：

```markdown
### 5.2 真实 event_impact_analysis 查询失败 / Bocha 调用异常

**症状**：工作台分析页报错或 `source_status.event_search` 显示 `bocha_used: false`。

**原因**：博查（Bocha）Web Search API 调用失败，可能由 key 缺失、配额耗尽、429 限流、网络超时等触发。

**排查步骤**：

1. 确认 `BOCHA_API_KEY` 环境变量已设置（启动期 `RuntimeError("BOCHA_API_KEY is required: ...")` 多半是这个原因）
2. 登录博查开放平台确认 key 有效、账户配额未耗尽
3. 触发 429 时无需手动干预：实现层已把 Bocha 失败翻译成空 result，`DualSourceExternalContextRetriever` 会自动切到 `disclosure_search`（巨潮 + 上交所），再不足则触发本地 RAG 兜底
4. 持续异常时手动跑根目录 `test_bocha.py` 做连通性 smoke：
   ```bash
   BOCHA_API_KEY=<key> python test_bocha.py --query "红海局势升级 航运" --limit 3
   ```

**后续可演进**：本 change 不做 Bocha 重试 / 缓存 / 熔断；如限流频繁，下一份 change 可在 `BochaHttpFetcher` 上加指数退避装饰器。
```

- [ ] **Step 2: 改 `project-status.md`**

打开 `docs/finsight/project-status.md`：

- line 19：`- GDELT 事件搜索` → `- Bocha 事件搜索`
- line 47：`- GdeltEventSearchProvider` → `- BochaEventSearchProvider`
- line 84：`- GDELT 与官方披露站检索已能被控制面消费` → `- Bocha 与官方披露站检索已能被控制面消费`

- [ ] **Step 3: 改 `control-plane-status.md`**

打开 `docs/finsight/modules/control-plane-status.md`，line 93 表格行：

- `已完成首版 | 已接入 GDELT + 官方披露搜索` → `已完成首版 | 已接入 Bocha + 官方披露搜索`

- [ ] **Step 4: 改 `data-evidence-status.md`**

打开 `docs/finsight/modules/data-evidence-status.md`：

- line 41：`- GdeltEventSearchProvider` → `- BochaEventSearchProvider`
- line 70：表格行的 `GDELT + 官方披露搜索` → `Bocha + 官方披露搜索`
- line 83：`- 扩展 GDELT + 官方披露` → `- 扩展 Bocha + 官方披露`

- [ ] **Step 5: 用 Grep 反向验证 docs 中无残留 GDELT**

```bash
cd "c:\D\大模型课程\openspec测试项目" && grep -nE "GDELT|Gdelt|gdelt" docs/finsight/operations/workbench-runbook.md docs/finsight/project-status.md docs/finsight/modules/control-plane-status.md docs/finsight/modules/data-evidence-status.md
```

Expected: 无输出（4 份 doc 已无 GDELT 字面量）

- [ ] **Step 6: Commit**

```bash
cd "c:\D\大模型课程\openspec测试项目"
git add docs/finsight/operations/workbench-runbook.md docs/finsight/project-status.md docs/finsight/modules/control-plane-status.md docs/finsight/modules/data-evidence-status.md
git commit -m "docs(finsight): sync gdelt-to-bocha migration across runbook and status docs"
```

---

## Task 11: Final Verification

**Files:** 无新增 / 修改；只跑测试。

- [ ] **Step 1: 跑全套 unit 测试**

```bash
cd "c:\D\大模型课程\openspec测试项目" && BOCHA_API_KEY=test-key python -m unittest discover -s tests/unit -v 2>&1 | tail -20
```

Expected: PASS，所有用例绿。

- [ ] **Step 2: 跑全套 integration 测试**

```bash
cd "c:\D\大模型课程\openspec测试项目" && BOCHA_API_KEY=test-key python -m unittest discover -s tests/integration -v 2>&1 | tail -20
```

Expected: PASS，所有用例绿。

- [ ] **Step 3: 跑护栏测试**

```bash
cd "c:\D\大模型课程\openspec测试项目" && python -m unittest tests.unit.test_no_gdelt_references_in_production -v
```

Expected: PASS

- [ ] **Step 4: 验证默认装配在 env 缺失时抛 `RuntimeError`**

```bash
cd "c:\D\大模型课程\openspec测试项目" && unset BOCHA_API_KEY && python -c "from finsight_agent.control_plane.orchestrator.service import _build_default_external_context_retriever; _build_default_external_context_retriever()"
```

（Windows cmd 下用 `set BOCHA_API_KEY=` 替代 `unset`）

Expected: 抛 `RuntimeError`，提示 BOCHA_API_KEY 缺失

- [ ] **Step 5: 验证默认装配在 env 设置时不抛**

```bash
cd "c:\D\大模型课程\openspec测试项目" && BOCHA_API_KEY=test-key python -c "from finsight_agent.control_plane.orchestrator.service import _build_default_external_context_retriever; retriever = _build_default_external_context_retriever(); print(type(retriever).__name__)"
```

Expected: 打印 `DualSourceExternalContextRetriever`

- [ ] **Step 6: 验证 git 状态干净**

```bash
cd "c:\D\大模型课程\openspec测试项目" && git status --short
```

Expected: 仅剩 `??` 标记的无关文件（根目录 .lnk / .html 等），与本 change 无关；无未提交修改

---

## Self-Review Checklist（plan 作者自查）

✅ **Spec 覆盖**：
- §"目标架构 + 新增/修改/删除清单" → Task 1-7 覆盖新增 Protocol / Provider / 修改 service.py / 删除 GDELT
- §"测试策略" 23 个用例 → Task 2 Step 5 完整覆盖
- §"协议契约测试字符串迁移" → Task 4 + Task 5 覆盖
- §"文档清理清单" → Task 10 覆盖
- §"护栏测试" → Task 8 覆盖
- §"ad-hoc 冒烟脚本" → Task 9 覆盖
- §"默认装配" → Task 3 覆盖

✅ **占位符扫描**：plan 中无 "TBD" / "TODO" / "类似 Task N" / "稍后补充" 等占位符。

✅ **类型一致性**：
- `EventSearchProvider.search_event_context` 签名在 Task 1、Task 2、Task 3、Task 4 一致
- `BochaHttpFetcher.post_json(url, *, headers, body)` 在 Task 2 stub 与实现中签名一致
- `source_status` 字段集合在 Task 2 实现、Task 2 测试、Task 4 契约测试、Task 5 stage runner fixture 中保持一致（`bocha_used` / `freshness` / `time_scope` / `error`）
- `evidence_refs` 格式 `bocha:item_NNN`（3 位零填充）在 Task 2 测试、Task 4 契约测试、Task 5 stage runner fixture 一致

✅ **分支**：不创建新分支、不开 worktree；11 个 commit 全部线性追加到当前 `feat/phase1-project-runnable`。

✅ **commit 粒度**：每个 task 1 个 commit；Task 2 因为含 23 个测试可能稍大但属同职责（Provider + tests）可接受；Task 10 把 4 份 doc 合并为 1 个 commit（docs 同步属同职责）。