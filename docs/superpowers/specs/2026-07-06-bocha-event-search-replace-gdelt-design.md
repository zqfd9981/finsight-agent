# Bocha Event Search Provider Replace GDELT Design

日期：2026-07-06
状态：设计稿，待用户审阅

## 背景

截至 2026-07-06，FinSight 在 `event_impact_analysis` 链路中已具备首版双源外部上下文检索能力：

- `GdeltEventSearchProvider` —— 对接 GDELT 公共事件搜索 API（`https://api.gdeltproject.org/api/v2/doc/doc`）
- `OfficialDisclosureSearchProvider` —— 对接巨潮与上交所披露站
- `DualSourceExternalContextRetriever` —— 把两类源按 `RetrievalStrategyClassifier` 与 `ContextRetrievalPlanner` 输出合并

但在真实运行中，`GdeltEventSearchProvider` 出现两类不可接受的失败：

1. **频率限制**：`test_gedlt.py` 与 `make-workbench-runnable` 归档 change 的"已知风险"段落都明确记录"真实 `event_impact_analysis` 查询会触发 GDELT 429"
2. **结果分布偏英文**：GDELT 是英文全球新闻流，对中文 A 股场景（公告、行业术语、中文站点）的覆盖密度不够

因此本次设计的目标是把事件搜索 provider 从 GDELT 整体替换为博查（Bocha）Web Search API，同时把 `EventSearchProvider` 抽成 Protocol，让未来再加新源不必再改动 orchestrator。

## 目标

- 把 `GdeltEventSearchProvider` 替换为 `BochaEventSearchProvider`
- 引入 `EventSearchProvider` Protocol 作为事件搜索层的抽象边界
- `OrchestratorService` 默认装配改为 Bocha 实现
- 让 `DualSourceExternalContextRetriever` 的合并语义、stage runner 调用形态、结果契约保持不变
- 删除 GDELT 相关源码、测试与根目录 ad-hoc 脚本，让仓库中不再残留被默认装配路径触发的 GDELT 引用
- 同步更新工作台 runbook、项目状态文档、控制面状态文档、数据与证据状态文档，把"GDELT 走不通 → 切到 Bocha"的事实写进运维与项目叙事

## 非目标

- 本轮不替换 `OfficialDisclosureSearchProvider`（巨潮 + 上交所）
- 不重写 `DualSourceExternalContextRetriever`、`RetrievalStrategyClassifier`、`ContextRetrievalPlanner`
- 不引入 Bocha 重试、熔断、缓存、可观测性埋点
- 不为 `EventSearchProvider` 增加新方法（仅暴露现有 `search_event_context` 契约）
- 不加 env-gated 真活 Bocha 集成测试进 CI
- 不在首版让 `time_scope` 影响 Bocha `freshness`（统一固定 `oneWeek`）
- 不重写 `openspec/changes/archive/**` 已归档 change 中关于 GDELT 的历史叙述

## 现状判断

### GDELT 当前实现位置

| 文件 | 角色 |
| --- | --- |
| `backend/src/finsight_agent/infra/external/gdelt_event_search.py` | `GdeltEventSearchProvider` + `GdeltHttpFetcher`，被 `OrchestratorService._build_default_external_context_retriever` 默认装配 |
| `backend/src/finsight_agent/control_plane/orchestrator/service.py:161` | `event_search_provider=GdeltEventSearchProvider()` |
| `tests/unit/test_gdelt_event_search.py` | 单测，使用 stub fetcher |
| `tests/unit/test_external_context_retriever.py` | 协议契约测试，硬编码 `evidence_refs=["gdelt:1"]` 等字符串 |
| `tests/unit/test_orchestrator_stage_runners.py:282,308` | 端到端 fixture，硬编码 `"gdelt:001"` |
| `test_gedlt.py`（仓库根） | ad-hoc 冒烟脚本，未被仓库根 README 引用 |
| `test.py`（仓库根） | ad-hoc BigQuery 脚本，查询 `gdelt-bq.gdeltv2.events_partitioned` 公开数据集 |

### GDELT 已记录的失败点

- `docs/finsight/operations/workbench-runbook.md:126-135` 整段 5.2 故障排查专门处理"GDELT 429"
- `openspec/changes/archive/2026-07-06-make-workbench-runnable/proposal.md` 风险项明文写"真实 event_impact_analysis 查询会触发 GDELT 429"
- `test_gedlt.py` 直接复现 429 + 打印 `Retry-After`

### 项目已有的外部 provider 范式（可继承）

- 协议层：`backend/src/finsight_agent/control_plane/orchestrator/context_retriever.py` 已经为 `ExternalContextRetriever` 定义 Protocol
- 抽象边界：provider 类只暴露单一 `search_event_context` 方法，返回标准 `ExternalContextResult`
- 网络层：所有外部请求都用 `urllib.request`（GDELT、Guardian、CNInfo、SSE 全部一致），不引入 `requests`
- 配置：API key 一律走环境变量（如 `GUARDIAN_API_KEY`），不写 YAML
- 失败语义：HTTP 异常翻译为空 result + `source_status`，不抛出

## 设计原则

### 1. 抽象与实现分离

`EventSearchProvider` Protocol 与 `BochaEventSearchProvider` 分文件存在；orchestrator 只依赖 Protocol；具体 provider 可以零成本替换或扩展。

### 2. 失败不阻塞主链路

Bocha 任何异常（HTTP / 网络 / 解析 / 空响应）一律翻译成空 `ExternalContextResult` + `source_status.error` 标签，让 `DualSourceExternalContextRetriever` 合并逻辑与现有 GDELT 路径行为等价，由 `disclosure_search` / `local_rag` 自然兜底。

### 3. 最小资源消耗

首版不重试、不缓存、不熔断、不埋点，只保证"用最少的代码把 Bocha 接进来"。

### 4. 测试零网络依赖

所有单测用 stub fetcher；端到端契约测试用 stub provider；真实 Bocha 调用只通过仓库根 ad-hoc 脚本手动触发，不进 CI。

### 5. 协议一致性与证据前缀治理

`evidence_refs` 前缀随 provider 命名空间迁移（`gdelt:item_001` → `bocha:item_001`），所有硬编码该前缀的测试断言同步更新；新增 `test_no_gdelt_references_in_production.py` 作为长期护栏。

## 方案对比

### 方案 A：抽 EventSearchProvider 协议 + 仅保留 Bocha 实现（彻底替换）

**做法**

- 新建 `EventSearchProvider` Protocol
- 新建 `BochaEventSearchProvider`（默认装配）
- 删除 `GdeltEventSearchProvider`、`gdelt_event_search.py`、对应单测、根目录 ad-hoc 脚本
- 测试中所有 `gdelt:` 证据前缀同步改为 `bocha:`
- 文档中所有 GDELT 描述同步改为 Bocha

**优点**

- 与"GDELT 走不通"的事实彻底切割，不留历史包袱
- 默认装配路径上不可能再出现 GDELT
- 节省约 90 行未走通代码 + 一个 unit test

**缺点**

- 无 fallback：若 Bocha 后续也限流，需要重新实现 provider
- 需同步更新 4 份 doc、2 份根目录脚本、3 份测试的 GDELT 字面量

### 方案 B：抽 EventSearchProvider 协议 + Bocha 为默认 + GDELT 降级为可选

**做法**

- 与 A 同样抽协议、新增 Bocha
- 保留 `GdeltEventSearchProvider` 作为可选实现，通过工厂 + 环境变量切换
- 默认装配走 Bocha

**优点**

- 切换 / 回滚成本极低
- 离线 CI / fixture 场景仍可用 GDELT 路径

**缺点**

- 多保留约 90 行未走通代码
- 增加了"是否有人会用 GDELT 默认路径"的额外心智负担

### 方案 C：抽 EventSearchProvider 协议 + Bocha 为默认 + GDELT 仅作测试 fixture

- 与 B 类似，把 GDELT 实现下沉到 `tests/unit/_fixtures/`
- 收益不大、增加 fixture 与实现分离的认知成本

### 推荐：方案 A

**理由**：

1. 用户在 `EventSearchProvider 协议 + Bocha 实现` 边界选择时，明确选择"抽协议 + Bocha 实现"，并要求"GDELT 整体下线以免误用"
2. Bocha Web Search API 在中文覆盖、稳定性、合规性上已经优于 GDELT；GDELT 留在代码里只会成为后续维护者的认知负担
3. `EventSearchProvider` Protocol 已经为未来再加 provider 留出干净边界，不需要靠"保留 GDELT 实现"来演示可替换性
4. 删除 + 同步测试 / 文档的清理动作是一次性成本；保留 GDELT 是持续性成本

## 目标架构

```text
                query + router_result
                          |
                          v
            RetrievalStrategyClassifier
                          |
                          v
              ContextRetrievalPlanner
                          |
                          v
             collect_event_context
                /        |        \
               v         v         v
     EventSearchProvider DisclosureSearchProvider   Local RAG (optional)
       (Bocha, default)   (CNInfo + SSE)
```

**新增**
- `backend/src/finsight_agent/control_plane/orchestrator/event_search_provider.py`：Protocol 定义（与现有 `ExternalContextRetriever` Protocol 同侧，符合 consumer-owned 风格）
- `backend/src/finsight_agent/infra/external/bocha_event_search.py`：`BochaEventSearchProvider` + `BochaHttpFetcher`
- `tests/unit/test_bocha_event_search.py`：单测
- `tests/unit/test_no_gdelt_references_in_production.py`：护栏测试
- `test_bocha.py`（仓库根）：ad-hoc 冒烟脚本

**修改**
- `backend/src/finsight_agent/control_plane/orchestrator/service.py`：默认装配改为 Bocha
- `tests/unit/test_external_context_retriever.py`：协议契约测试字符串 `gdelt:` → `bocha:`
- `tests/unit/test_orchestrator_stage_runners.py`：fixture 字符串 `gdelt:001` → `bocha:001`
- `tests/unit/test_project_skeleton.py`：在 `test_minimal_fast_path_files_exist` 的 `required_files` 列表追加 `bocha_event_search.py`、`event_search_provider.py`（路径已修正为 `control_plane/orchestrator/`）、`test_bocha_event_search.py`（不删除现有条目；GDELT 文件本来未在该列表中）
- `docs/finsight/operations/workbench-runbook.md`：删除 §5.2"GDELT 429"故障排查，替换为 "Bocha 调用失败"诊断
- `docs/finsight/project-status.md`：line 19、47、84 的 GDELT 描述替换为 Bocha
- `docs/finsight/modules/control-plane-status.md`：line 93 表格行替换
- `docs/finsight/modules/data-evidence-status.md`：line 41、70、83 替换

**删除**
- `backend/src/finsight_agent/infra/external/gdelt_event_search.py`
- `tests/unit/test_gdelt_event_search.py`
- `test_gedlt.py`（仓库根）
- `test.py`（仓库根，GDELT BigQuery ad-hoc）

## 组件设计

### 1. `EventSearchProvider` Protocol

文件：`backend/src/finsight_agent/control_plane/orchestrator/event_search_provider.py`

**放置位置说明**：项目现有 Protocol（`ExternalContextRetriever`）定义在 `control_plane/orchestrator/context_retriever.py`（消费方一侧）。`EventSearchProvider` 同样作为 control plane 视角下的契约，应与现有 Protocol 同位置、同风格，便于 orchestrator 一并导入。

```python
class EventSearchProvider(Protocol):
    def search_event_context(
        self,
        *,
        query: str,
        event: str,
        themes: list[str],
        time_scope: str,
        limit: int,
    ) -> ExternalContextResult: ...
```

签名与现有 `DualSourceExternalContextRetriever._execute_step` 调用点（`dual_source_context_retriever.py:126-132`）严格一致；调用方契约就是返回 `ExternalContextResult`。

### 2. `BochaEventSearchProvider`

文件：`backend/src/finsight_agent/infra/external/bocha_event_search.py`

**常量**

```python
BOCHA_WEB_SEARCH_URL = "https://api.bochaai.com/v1/web-search"
BOCHA_FRESHNESS = "oneWeek"
BOCHA_USER_AGENT = "finsight-bocha-search/1.0"
```

**构造**

```python
class BochaEventSearchProvider:
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
```

**核心方法**

```python
def search_event_context(self, *, query, event, themes, time_scope, limit):
    composed_query = " ".join(part for part in (query, event, *themes) if part).strip()
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
        payload = self._fetcher.post_json(BOCHA_WEB_SEARCH_URL, headers=headers, body=body)
    except urllib.error.HTTPError as e:
        _logger.warning("bocha search failed: error=%s query_len=%d", f"http_{e.code}", len(composed_query))
        return self._empty_result(themes, time_scope, error=f"http_{e.code}")
    except urllib.error.URLError:
        _logger.warning("bocha search failed: error=timeout query_len=%d", len(composed_query))
        return self._empty_result(themes, time_scope, error="timeout")
    except json.JSONDecodeError:
        _logger.warning("bocha search failed: error=invalid_json query_len=%d", len(composed_query))
        return self._empty_result(themes, time_scope, error="invalid_json")
    except Exception:
        _logger.warning("bocha search failed: error=unknown query_len=%d", len(composed_query))
        return self._empty_result(themes, time_scope, error="unknown")

    value_list = (payload.get("data") or {}).get("webPages", {}).get("value") or []
    if not value_list:
        return self._empty_result(themes, time_scope, error="empty_response")

    items = self._map_items(value_list[:limit], themes)
    return ExternalContextResult(
        items=items,
        summary_hint=items[0].title if items else "",
        supporting_points=[(i.snippet or i.title) for i in items[:2]],
        evidence_refs=[f"bocha:item_{idx:03d}" for idx in range(1, len(items) + 1)],
        candidate_hints=list(themes),
        source_status={
            "bocha_used": True,
            "freshness": BOCHA_FRESHNESS,
            "time_scope": time_scope,
        },
    )
```

**字段映射**

| 目标 `ExternalContextItem` 字段 | 来源 | 兜底 |
| --- | --- | --- |
| `title` | `value[].name` | — |
| `url` | `value[].url` | 空字符串 |
| `publish_date` | `value[].datePublished` | 原样透传 |
| `snippet` | `value[].summary` | `value[].snippet` → `value[].name` → `""` |
| `source` | 常量 `"bocha"` | — |
| `themes` | 入参 `themes` | 原样回写 |

**`_empty_result`**

```python
def _empty_result(self, themes, time_scope, *, error):
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

### 3. `BochaHttpFetcher`

同文件 `bocha_event_search.py`，与现有 `GdeltHttpFetcher` 风格一致：

```python
@dataclass(slots=True)
class BochaHttpFetcher:
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
```

- 仅依赖 `urllib` + `json`，不引入 `requests`
- 30 秒 timeout，与 `GdeltHttpFetcher` 对齐
- 透传 `HTTPError` / `URLError` / `JSONDecodeError`，由 provider 翻译

### 4. 默认装配

修改 `backend/src/finsight_agent/control_plane/orchestrator/service.py:155-163`：

```python
def _build_default_external_context_retriever() -> DualSourceExternalContextRetriever:
    return DualSourceExternalContextRetriever(
        classifier=StubRetrievalStrategyClassifier(),
        planner=ContextRetrievalPlanner(),
        event_search_provider=BochaEventSearchProvider(),
        disclosure_search_provider=OfficialDisclosureSearchProvider(),
    )
```

`BochaEventSearchProvider()` 无参构造：key 必须由 `BOCHA_API_KEY` 环境变量提供，缺失即抛 `RuntimeError`（构造期而非首次查询期失败，便于启动期立即暴露配置问题）。

### 5. 协议契约测试字符串迁移

`tests/unit/test_external_context_retriever.py` 中的字面量调整（仅改字符串）：

| 位置 | 现状 | 改后 |
| --- | --- | --- |
| `ContextRetrievalModelsTest` 第 1 处 | `ExternalContextItem(source="gdelt", ...)` | `source="bocha"` |
| `ContextRetrievalModelsTest` 第 2 处 | `source_status={"gdelt_used": True}` | `source_status={"bocha_used": True}` |
| `DualSourceExternalContextRetrieverTest.test_retrieve_event_context_merges_planned_sources` | `evidence_refs=["gdelt:1"]` | `evidence_refs=["bocha:1"]` |

`tests/unit/test_orchestrator_stage_runners.py:282,308`：

```python
"evidence_refs": ["gdelt:001", "cninfo:001"]  # → ["bocha:001", "cninfo:001"]
```

### 6. 护栏测试

新增 `tests/unit/test_no_gdelt_references_in_production.py`：

- 遍历 `backend/src/finsight_agent/`（不含 `__pycache__`）的 `.py` 文件
- 断言 `gdelt` / `Gdelt` / `GDELT` 出现次数 == 0
- 失败时给出文件 + 行号
- 不覆盖 `docs/`、`openspec/changes/archive/`、本测试自身

## 配置

| 环境变量 | 必填 | 说明 |
| --- | --- | --- |
| `BOCHA_API_KEY` | 是 | 博查开放平台 API key，格式 `sk-...` |

- **缺失行为**：`BochaEventSearchProvider.__init__` 抛 `RuntimeError("BOCHA_API_KEY is required: pass api_key=... or set BOCHA_API_KEY env")`
- **不写 YAML**：与 `GUARDIAN_API_KEY` 风格保持一致
- **不传明文进代码**：单测用 `BochaEventSearchProvider(api_key="test-key", fetcher=stub)` 显式注入

## 错误处理与可观测性

### 失败语义总表

| 异常 | 返回 |
| --- | --- |
| `urllib.error.HTTPError` 401/403 | `ExternalContextResult(items=[], source_status={"bocha_used": False, "freshness": "oneWeek", "time_scope": ..., "error": "http_401"})` |
| `HTTPError` 429 | 同上，`error="http_429"` |
| `HTTPError` 其它 4xx/5xx | 同上，`error` 由 `f"http_{e.code}"` 动态构造（如 503 → `"http_503"`） |
| `urllib.error.URLError`（含 timeout） | `error="timeout"` |
| `json.JSONDecodeError` | `error="invalid_json"` |
| 其它 `Exception` | `error="unknown"` |
| payload 缺 `data.webPages.value` 或为空 | `error="empty_response"` |
| 入参 `composed_query` 为空 | `error="empty_query"` |

### 日志

- 统一在 `WARNING` 级别打 1 行：`bocha search failed: error=<tag> query_len=<int>`
- **不打印**：query 原文、API key、完整 payload
- 日志器名：`logging.getLogger(__name__)`（`finsight_agent.infra.external.bocha_event_search`）

### 显式不做

- 重试 / 指数退避
- 内存缓存 / TTL
- 熔断 / 短路
- OpenTelemetry / Prometheus metrics
- trace / observation 字段扩展

未来需要在 `BochaHttpFetcher` 上加装饰器即可，对 provider 与上层透明。

## 测试策略

### 新增单测：`tests/unit/test_bocha_event_search.py`

镜像 `tests/unit/test_gdelt_event_search.py` 的零网络依赖形态（frozen unittest + stub fetcher）：

| 用例 | 覆盖 |
| --- | --- |
| `test_search_returns_standardized_context_result` | happy path 3 条 items，断言 `source=="bocha"`、非空 `summary_hint`、`evidence_refs` 长度 |
| `test_snippet_prefers_summary_then_snippet_then_name` | snippet 三级兜底 |
| `test_publish_date_passed_through_as_is` | ISO 字符串不被二次格式化 |
| `test_themes_passed_through_into_items` | themes 回写 |
| `test_candidate_hints_are_input_themes` | candidate_hints 等于输入 themes |
| `test_evidence_refs_use_bocha_prefix` | `bocha:item_001` … `bocha:item_NNN` |
| `test_evidence_refs_match_item_count` | `len(evidence_refs) == len(items)` |
| `test_handles_empty_webpages_value` | `value == []` → 空 result + `bocha_used=False` |
| `test_handles_missing_webpages_field` | payload 无 `data.webPages` → 空 result |
| `test_handles_missing_data_field` | payload 无 `data` → 空 result |
| `test_handles_http_error_401` | `HTTPError(401)` → empty + `error="http_401"` |
| `test_handles_http_error_429` | `HTTPError(429)` → empty + `error="http_429"` |
| `test_handles_urlerror_timeout` | `URLError` → empty + `error="timeout"` |
| `test_handles_json_decode_error` | `JSONDecodeError` → empty + `error="invalid_json"` |
| `test_limit_truncates_items` | Bocha 返回 5 条、limit=3 → items 长度 = 3 |
| `test_constructor_raises_without_api_key` | 无 env + 无显式注入 → `RuntimeError` |
| `test_summary_hint_uses_first_item_title` | `summary_hint == items[0].title` |
| `test_supporting_points_take_first_two` | `supporting_points` 长度 ≤ 2 |
| `test_request_body_uses_one_week_freshness` | 验证 `fetcher.calls[0]["body"]["freshness"] == "oneWeek"` |
| `test_request_body_passes_count_as_limit` | 验证 `body["count"] == limit` |
| `test_request_body_sets_summary_true` | 验证 `body["summary"] is True` |
| `test_request_headers_include_bearer_token` | 验证 `headers["Authorization"].startswith("Bearer ")` |
| `test_empty_query_returns_empty_result` | 入参全空 → empty + `error="empty_query"`，**不**调 fetcher |

Stub 形态（参考 `_StubGdeltFetcher`）：

```python
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
```

### 协议契约测试更新

- `tests/unit/test_external_context_retriever.py`：见上文 §5.5
- `tests/unit/test_orchestrator_stage_runners.py:282,308`：`gdelt:001` → `bocha:001`

### 集成测试

`tests/integration/test_event_impact_analysis_flow.py` 与 `tests/unit/test_orchestrator_service.py` 在设计阶段已 Grep 验证无 GDELT 字面量残留，逻辑零改动；唯一含 GDELT 字面量的非外部 search provider 测试是 `test_orchestrator_stage_runners.py`（已在 §5.5 覆盖）。

### 护栏测试

`tests/unit/test_no_gdelt_references_in_production.py`：

- 遍历 `backend/src/finsight_agent/` 下 `.py` 文件（排除 `__pycache__`）
- 用正则匹配 `gdelt|Gdelt|GDELT`
- 任何命中即测试失败，错误信息含 `path:line:column` 与原文片段

### 新增 ad-hoc 冒烟脚本

`test_bocha.py`（仓库根），镜像 `test_guardian_open_platform.py` 形态：

- argparse：`--api-key` / `--query` / `--limit` / `--freshness`
- 默认 query = "红海局势升级 航运"；默认 limit = 3；默认 freshness = "oneWeek"
- 默认 api_key 读 `BOCHA_API_KEY` env
- 命中后打印每条结果的 title / url / datePublished / snippet（截断到 200 字）
- 失败按 HTTP code 给原因提示
- **不进 CI**

### 显式不做

- env-gated 真活集成测试（不进 CI，避免网络/限流耦合）
- 模糊匹配 / 主题抽取（首版不调 Bocha AI Search）
- 中文 token 计数 / 成本埋点

## 文档清理清单

### `docs/finsight/operations/workbench-runbook.md`

- line 126 `### 5.2 真实 event_impact_analysis 查询失败 / GDELT 429` 整段（126-135）替换为"Bocha 调用失败排查"，提示：
  - 检查 `BOCHA_API_KEY` 是否设置
  - 检查博查平台配额
  - 触发 `RuntimeError` 时查启动日志
  - 触发 429 时切换到 `disclosure_search` + `local_rag` 兜底（已有，无需新代码）

### `docs/finsight/project-status.md`

- line 19：`- GDELT 事件搜索` → `- Bocha 事件搜索`
- line 47：`- GdeltEventSearchProvider` → `- BochaEventSearchProvider`
- line 84：`- GDELT 与官方披露站检索已能被控制面消费` → `- Bocha 与官方披露站检索已能被控制面消费`

### `docs/finsight/modules/control-plane-status.md`

- line 93：表格行 `双层外部上下文检索接入 | 已完成首版 | 已接入 GDELT + 官方披露搜索` → `已接入 Bocha + 官方披露搜索`

### `docs/finsight/modules/data-evidence-status.md`

- line 41：`- GdeltEventSearchProvider` → `- BochaEventSearchProvider`
- line 70：表格行替换
- line 83：`- 扩展 GDELT + 官方披露` → `- 扩展 Bocha + 官方披露`

### 不动的文档

- `docs/superpowers/specs/2026-07-02-dual-source-event-context-retrieval-design.md`：历史设计，GDELT 是当时决策的合理选择，不重写
- `docs/superpowers/plans/2026-07-02-dual-source-event-context-retrieval.md`：已完成 plan，不重写
- `openspec/changes/archive/2026-07-06-make-workbench-runnable/`：归档 change，GDELT 429 是当时真实存在的风险项，不重写

## 范围外（明确不做）

- 不替换 `OfficialDisclosureSearchProvider`
- 不重写 `DualSourceExternalContextRetriever` 合并语义
- 不做 Bocha 重试 / 缓存 / 熔断
- 不接 Bocha AI Search（结构化模态卡）
- 不让 `time_scope` 影响 `freshness`
- 不做 OpenTelemetry / metrics
- 不加 env-gated 真活集成测试进 CI
- 不写 Bocha MCP server
- 不变更 `EventSearchProvider` Protocol 的方法签名（保持单一 `search_event_context`）

## 后续可演进方向（不在本 change）

- `time_scope` → `freshness` 智能映射（recent→oneDay / current→oneWeek / long_term→oneMonth）
- `EventSearchProvider` 增加 `search_with_filters(query, *, include_domains, exclude_domains)` 用于白名单财经站点
- 在 `BochaHttpFetcher` 上加重试装饰器（指数退避，限流感知）
- 在 `BochaEventSearchProvider` 上加内存 LRU 缓存（TTL 5 分钟，按 query hash 索引）
- 用 Bocha Semantic Reranker 对结果二次排序
- 评测样本体系：固化 10-20 个真实金融 query，比对 Bocha vs 旧 GDELT fixture 在 `event_search.status` 上的分布

## 设计结论

本 change 是 `event_impact_analysis` 链路的一次"事件搜索源替换 + 抽象化"，不是新能力引入：

- 用 `EventSearchProvider` Protocol 把事件搜索从 orchestrator 视野里抽离
- 用 `BochaEventSearchProvider` 作为首版默认实现，覆盖中文金融场景
- 用 `BochaHttpFetcher` 把网络层与业务层解耦，让单测零网络依赖
- 用"失败一律空 result + `source_status.error`"的语义让 Bocha 故障不阻塞主链路
- 用"删除 GDELT + 护栏测试 + 文档同步"保证方案 A 的承诺落地

相比"继续在 GDELT 上加超时/重试/cache"的路径，本方案更彻底：
- 直接解决"GDELT 走不通"的根因（不是限流问题，是源选错）
- 同步完成 EventSearchProvider 抽象化（之前只有 DisclosureSearchProvider 一侧有协议边界，事件搜索一侧是裸类，结构不一致）
- 一次性清理约 90 行未走通代码 + 1 份 unit test + 1 份根目录 ad-hoc 脚本

落地后 `collect_event_context` 链路行为对上层保持透明：调用方代码、stage runner、orchestrator 都不感知具体 provider；trace / observation 里只会看到 `source_status.event_search` 的值从老的 GDELT 状态字段切换为 `bocha_used / error`。