# Streamlit 调试评测工作台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 Streamlit 骨架上补一套内部工作台，支持单条分析运行、执行链调试查看，以及事件评测样本 replay 与结果对照。

**Architecture:** 保持 `POST /api/v1/analysis/turns` 作为单条分析与调试共用入口，仅新增两个轻量 eval 接口承载 case 列表与 replay。前端采用多页面 Streamlit 结构，并将页面逻辑拆成“纯函数 view model + 薄渲染层”，让大部分行为可以用 `unittest` 在无浏览器环境下稳定测试。

**Tech Stack:** Python 3、Streamlit、`unittest`、现有 `WorkbenchBackendApiService`、`finsight_agent.evaluation.event_eval`、shared contracts。

---

## 文件结构

### 新增文件

- `backend/apps/api/event_eval.py`
  - 事件评测接口入口，提供 `GET /api/v1/eval/event-cases` 和 `POST /api/v1/eval/event-replay`
- `frontend/streamlit_app/components/analysis_run_form.py`
  - 统一 query/session/trace 运行表单
- `frontend/streamlit_app/components/response_summary_card.py`
  - 最终回答摘要与降级标签展示
- `frontend/streamlit_app/components/trace_block_viewer.py`
  - route / plan / execution trace 展示
- `frontend/streamlit_app/components/stage_observation_card.py`
  - 单个 stage 的状态和关键输出展示
- `frontend/streamlit_app/components/eval_case_table.py`
  - 评测 case 列表和筛选
- `frontend/streamlit_app/components/eval_result_detail.py`
  - 单条 replay 结果与 checks 详情
- `frontend/streamlit_app/pages/analysis_view.py`
  - 分析视图页面
- `frontend/streamlit_app/pages/debug_view.py`
  - 调试视图页面
- `frontend/streamlit_app/pages/eval_view.py`
  - 评测视图页面
- `frontend/streamlit_app/state/models.py`
  - 前端消费的 eval view models
- `frontend/streamlit_app/state/workbench_state.py`
  - 最近一次分析结果、当前筛选条件、当前选中 case 的状态助手
- `tests/unit/test_event_eval_api.py`
  - eval API 路由与 handler 测试
- `tests/unit/test_streamlit_api_client.py`
  - 前端 API client 与 replay payload 解析测试
- `tests/unit/test_streamlit_workbench_state.py`
  - 共享状态读写测试
- `tests/unit/test_streamlit_analysis_view.py`
  - 分析视图 view model 测试
- `tests/unit/test_streamlit_debug_view.py`
  - 调试视图 view model 测试
- `tests/unit/test_streamlit_eval_view.py`
  - 评测视图 view model 测试
- `tests/integration/test_streamlit_workbench_smoke.py`
  - 前端工作台最小 smoke 测试

### 修改文件

- `backend/apps/api/main.py`
  - 增加 eval 路由元数据
- `frontend/streamlit_app/app.py`
  - 从单入口骨架改成多页面工作台入口
- `frontend/streamlit_app/api_client.py`
  - 新增 eval case/replay API 构建与解析能力
- `frontend/streamlit_app/components/__init__.py`
  - 导出新组件
- `frontend/streamlit_app/pages/__init__.py`
  - 导出新页面
- `frontend/streamlit_app/state/__init__.py`
  - 导出状态助手
- `docs/finsight/project-status.md`
  - 同步工作台实现状态
- `docs/finsight/modules/control-plane-status.md`
  - 同步调试工作台与评测入口状态
- `docs/finsight/modules/data-evidence-status.md`
  - 同步 replay/eval 可视化支持状态

---

### Task 1: 增加事件评测 API 入口

**Files:**
- Create: `backend/apps/api/event_eval.py`
- Modify: `backend/apps/api/main.py`
- Test: `tests/unit/test_event_eval_api.py`

- [ ] **Step 1: 先写失败测试，钉住 eval 路由元数据和 handler 输出结构**

```python
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.apps.api import event_eval


class EventEvalApiTest(unittest.TestCase):
    def test_build_eval_route_metadata_returns_two_routes(self) -> None:
        routes = event_eval.build_eval_route_metadata()

        self.assertEqual(
            [route["path"] for route in routes],
            ["/api/v1/eval/event-cases", "/api/v1/eval/event-replay"],
        )

    def test_handle_event_cases_returns_fixture_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture_path = Path(temp_dir) / "cases.jsonl"
            fixture_path.write_text(
                json.dumps(
                    {
                        "case_id": "dual_001",
                        "query": "红海局势升级利好哪些A股航运股？",
                        "expected_intent": "event_impact_analysis",
                        "expected_strategy": "dual_primary",
                        "allow_degraded": True,
                        "min_target_count": 1,
                        "expected_target_keywords": ["中远海能"],
                        "notes": "双主源事件样本",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            original = event_eval.DEFAULT_EVENT_FIXTURE_PATH
            event_eval.DEFAULT_EVENT_FIXTURE_PATH = fixture_path
            try:
                payload = event_eval.handle_event_cases()
            finally:
                event_eval.DEFAULT_EVENT_FIXTURE_PATH = original

        self.assertEqual(len(payload["cases"]), 1)
        self.assertEqual(payload["cases"][0]["case_id"], "dual_001")

    def test_handle_event_replay_runs_selected_cases(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture_path = Path(temp_dir) / "cases.jsonl"
            fixture_path.write_text(
                json.dumps(
                    {
                        "case_id": "dual_001",
                        "query": "红海局势升级利好哪些A股航运股？",
                        "expected_intent": "event_impact_analysis",
                        "expected_strategy": "dual_primary",
                        "allow_degraded": True,
                        "min_target_count": 1,
                        "expected_target_keywords": ["中远海能"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            def _fake_replay_event_cases(*, fixture_path: Path, case_ids=None, service=None, include_trace=True):
                self.assertEqual(case_ids, ["dual_001"])
                return [
                    {
                        "case": {"case_id": "dual_001", "query": "红海局势升级利好哪些A股航运股？"},
                        "result": {
                            "case_id": "dual_001",
                            "actual_intent": "event_impact_analysis",
                            "actual_strategy": "dual_primary",
                            "response_type": "success",
                            "degraded": False,
                            "target_count": 2,
                            "evidence_ref_count": 3,
                            "summary": "中远海能等标的受益于运价弹性。",
                            "failure_reason": None,
                            "target_keywords": ["中远海能", "招商轮船"],
                        },
                        "checks": [{"check_name": "intent_match", "status": "pass", "message": "ok"}],
                    }
                ]

            original_fixture_path = event_eval.DEFAULT_EVENT_FIXTURE_PATH
            original_replay = event_eval.replay_event_cases
            event_eval.DEFAULT_EVENT_FIXTURE_PATH = fixture_path
            event_eval.replay_event_cases = _fake_replay_event_cases
            try:
                payload = event_eval.handle_event_replay({"case_ids": ["dual_001"]})
            finally:
                event_eval.DEFAULT_EVENT_FIXTURE_PATH = original_fixture_path
                event_eval.replay_event_cases = original_replay

        self.assertEqual(payload["summary"]["total"], 1)
        self.assertEqual(payload["summary"]["pass"], 1)
        self.assertEqual(payload["records"][0]["result"]["actual_strategy"], "dual_primary")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试，确认当前失败**

Run:

```bash
python -m unittest tests.unit.test_event_eval_api -v
```

Expected:

- FAIL，提示 `backend.apps.api.event_eval` 模块不存在，或相关方法未定义

- [ ] **Step 3: 写最小 API 实现与路由元数据**

`backend/apps/api/event_eval.py`

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from finsight_agent.evaluation.event_eval.fixture_loader import load_event_eval_cases
from finsight_agent.evaluation.event_eval.replay import replay_event_cases


EVENT_CASES_PATH = "/api/v1/eval/event-cases"
EVENT_REPLAY_PATH = "/api/v1/eval/event-replay"
DEFAULT_EVENT_FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "finsight_agent"
    / "evaluation"
    / "event_eval"
    / "fixtures"
    / "event_cases_v1.jsonl"
)


def build_eval_route_metadata() -> list[dict[str, str]]:
    return [
        {"method": "GET", "path": EVENT_CASES_PATH, "handler": "handle_event_cases"},
        {"method": "POST", "path": EVENT_REPLAY_PATH, "handler": "handle_event_replay"},
    ]


def handle_event_cases() -> dict[str, Any]:
    cases = load_event_eval_cases(DEFAULT_EVENT_FIXTURE_PATH)
    return {"cases": [case.__dict__ for case in cases]}


def handle_event_replay(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    request_payload = payload or {}
    case_ids = request_payload.get("case_ids")
    records = replay_event_cases(
        fixture_path=DEFAULT_EVENT_FIXTURE_PATH,
        case_ids=case_ids,
        include_trace=True,
    )
    serialized_records = []
    summary = {"total": len(records), "pass": 0, "warn": 0, "fail": 0}
    for record in records:
        if isinstance(record, dict):
            serialized_records.append(record)
            check_statuses = [item["status"] for item in record["checks"]]
        else:
            serialized = record.to_dict()
            serialized_records.append(serialized)
            check_statuses = [item.status for item in record.checks]
        if "fail" in check_statuses:
            summary["fail"] += 1
        elif "warn" in check_statuses:
            summary["warn"] += 1
        else:
            summary["pass"] += 1
    return {"records": serialized_records, "summary": summary}
```

`backend/apps/api/main.py`

```python
from backend.apps.api.analysis_turns import build_route_metadata
from backend.apps.api.event_eval import build_eval_route_metadata


def main() -> dict[str, object]:
    return {
        "description": APP_ENTRY_DESCRIPTION,
        "routes": [build_route_metadata(), *build_eval_route_metadata()],
    }
```

- [ ] **Step 4: 重新运行测试，确认通过**

Run:

```bash
python -m unittest tests.unit.test_event_eval_api -v
```

Expected:

- PASS，三个 API 入口测试全部通过

- [ ] **Step 5: 提交这一小步**

```bash
git add backend/apps/api/main.py backend/apps/api/event_eval.py tests/unit/test_event_eval_api.py
git commit -m "feat: 增加事件评测接口入口"
```

---

### Task 2: 扩展前端 API client 与共享状态

**Files:**
- Modify: `frontend/streamlit_app/api_client.py`
- Create: `frontend/streamlit_app/state/models.py`
- Create: `frontend/streamlit_app/state/workbench_state.py`
- Modify: `frontend/streamlit_app/state/__init__.py`
- Test: `tests/unit/test_streamlit_api_client.py`
- Test: `tests/unit/test_streamlit_workbench_state.py`

- [ ] **Step 1: 先写失败测试，钉住 eval payload 解析和共享状态读写**

```python
from __future__ import annotations

import unittest

from frontend.streamlit_app.api_client import WorkbenchApiClient
from frontend.streamlit_app.state.workbench_state import (
    get_last_analysis_result,
    get_selected_eval_case_id,
    set_last_analysis_result,
    set_selected_eval_case_id,
)
from shared.contracts.analysis_response_envelope import AnalysisResponseEnvelope


class StreamlitApiClientTest(unittest.TestCase):
    def test_parse_event_cases_returns_view_models(self) -> None:
        client = WorkbenchApiClient()

        payload = {
            "cases": [
                {
                    "case_id": "dual_001",
                    "query": "红海局势升级利好哪些A股航运股？",
                    "expected_intent": "event_impact_analysis",
                    "expected_strategy": "dual_primary",
                    "allow_degraded": True,
                    "min_target_count": 1,
                    "expected_target_keywords": ["中远海能"],
                    "notes": "双主源事件样本",
                }
            ]
        }

        cases = client.parse_event_cases(payload)

        self.assertEqual(cases[0].case_id, "dual_001")
        self.assertEqual(cases[0].expected_strategy, "dual_primary")

    def test_parse_event_replay_returns_summary_and_records(self) -> None:
        client = WorkbenchApiClient()

        payload = {
            "summary": {"total": 1, "pass": 1, "warn": 0, "fail": 0},
            "records": [
                {
                    "case": {"case_id": "dual_001", "query": "红海局势升级利好哪些A股航运股？"},
                    "result": {
                        "case_id": "dual_001",
                        "query": "红海局势升级利好哪些A股航运股？",
                        "actual_intent": "event_impact_analysis",
                        "actual_strategy": "dual_primary",
                        "response_type": "success",
                        "degraded": False,
                        "target_count": 2,
                        "evidence_ref_count": 3,
                        "summary": "中远海能等标的受益于运价弹性。",
                        "failure_reason": None,
                        "target_keywords": ["中远海能", "招商轮船"],
                    },
                    "checks": [{"check_name": "intent_match", "status": "pass", "message": "ok"}],
                }
            ],
        }

        replay = client.parse_event_replay(payload)

        self.assertEqual(replay.summary.total, 1)
        self.assertEqual(replay.records[0].result.actual_strategy, "dual_primary")


class StreamlitWorkbenchStateTest(unittest.TestCase):
    def test_state_helpers_store_last_analysis_result_and_selected_case(self) -> None:
        bucket: dict[str, object] = {}
        envelope = AnalysisResponseEnvelope(session_id="sess_demo")

        set_last_analysis_result(bucket, envelope)
        set_selected_eval_case_id(bucket, "dual_001")

        self.assertEqual(get_last_analysis_result(bucket).session_id, "sess_demo")
        self.assertEqual(get_selected_eval_case_id(bucket), "dual_001")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试，确认失败**

Run:

```bash
python -m unittest tests.unit.test_streamlit_api_client tests.unit.test_streamlit_workbench_state -v
```

Expected:

- FAIL，提示 `parse_event_cases`、`parse_event_replay`、状态助手或 view model 未定义

- [ ] **Step 3: 写最小 view model 和状态助手实现**

`frontend/streamlit_app/state/models.py`

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class EventEvalCaseView:
    case_id: str
    query: str
    expected_intent: str
    expected_strategy: str
    allow_degraded: bool
    min_target_count: int
    expected_target_keywords: list[str] = field(default_factory=list)
    notes: str | None = None


@dataclass(slots=True)
class EventReplayResultView:
    case_id: str
    query: str
    actual_intent: str
    actual_strategy: str
    response_type: str
    degraded: bool
    target_count: int
    evidence_ref_count: int
    summary: str
    failure_reason: str | None
    target_keywords: list[str] = field(default_factory=list)


@dataclass(slots=True)
class EventReplayRecordView:
    case_id: str
    query: str
    result: EventReplayResultView
    checks: list[dict[str, str]]


@dataclass(slots=True)
class EventReplaySummaryView:
    total: int
    pass_count: int
    warn_count: int
    fail_count: int


@dataclass(slots=True)
class EventReplayRunView:
    summary: EventReplaySummaryView
    records: list[EventReplayRecordView]
```

`frontend/streamlit_app/state/workbench_state.py`

```python
from __future__ import annotations

from collections.abc import MutableMapping

from shared.contracts.analysis_response_envelope import AnalysisResponseEnvelope


LAST_ANALYSIS_RESULT_KEY = "last_analysis_result"
SELECTED_EVAL_CASE_ID_KEY = "selected_eval_case_id"


def get_last_analysis_result(
    bucket: MutableMapping[str, object],
) -> AnalysisResponseEnvelope | None:
    payload = bucket.get(LAST_ANALYSIS_RESULT_KEY)
    return payload if isinstance(payload, AnalysisResponseEnvelope) else None


def set_last_analysis_result(
    bucket: MutableMapping[str, object],
    envelope: AnalysisResponseEnvelope,
) -> None:
    bucket[LAST_ANALYSIS_RESULT_KEY] = envelope


def get_selected_eval_case_id(bucket: MutableMapping[str, object]) -> str | None:
    payload = bucket.get(SELECTED_EVAL_CASE_ID_KEY)
    return payload if isinstance(payload, str) and payload else None


def set_selected_eval_case_id(bucket: MutableMapping[str, object], case_id: str | None) -> None:
    if case_id:
        bucket[SELECTED_EVAL_CASE_ID_KEY] = case_id
    else:
        bucket.pop(SELECTED_EVAL_CASE_ID_KEY, None)
```

`frontend/streamlit_app/api_client.py`

```python
from frontend.streamlit_app.state.models import (
    EventEvalCaseView,
    EventReplayRecordView,
    EventReplayResultView,
    EventReplayRunView,
    EventReplaySummaryView,
)


class WorkbenchApiClient:
    def __init__(
        self,
        endpoint_path: str = "/api/v1/analysis/turns",
        event_cases_path: str = "/api/v1/eval/event-cases",
        event_replay_path: str = "/api/v1/eval/event-replay",
    ) -> None:
        self.endpoint_path = endpoint_path
        self.event_cases_path = event_cases_path
        self.event_replay_path = event_replay_path

    def parse_event_cases(self, payload: dict) -> list[EventEvalCaseView]:
        return [
            EventEvalCaseView(
                case_id=item["case_id"],
                query=item["query"],
                expected_intent=item["expected_intent"],
                expected_strategy=item["expected_strategy"],
                allow_degraded=item["allow_degraded"],
                min_target_count=item.get("min_target_count", 0),
                expected_target_keywords=item.get("expected_target_keywords", []),
                notes=item.get("notes"),
            )
            for item in payload.get("cases", [])
        ]

    def parse_event_replay(self, payload: dict) -> EventReplayRunView:
        summary_payload = payload["summary"]
        records = []
        for item in payload.get("records", []):
            result_payload = item["result"]
            records.append(
                EventReplayRecordView(
                    case_id=item["case"]["case_id"],
                    query=item["case"]["query"],
                    result=EventReplayResultView(
                        case_id=result_payload["case_id"],
                        query=result_payload["query"],
                        actual_intent=result_payload["actual_intent"],
                        actual_strategy=result_payload["actual_strategy"],
                        response_type=result_payload["response_type"],
                        degraded=result_payload["degraded"],
                        target_count=result_payload["target_count"],
                        evidence_ref_count=result_payload["evidence_ref_count"],
                        summary=result_payload["summary"],
                        failure_reason=result_payload.get("failure_reason"),
                        target_keywords=result_payload.get("target_keywords", []),
                    ),
                    checks=item.get("checks", []),
                )
            )
        return EventReplayRunView(
            summary=EventReplaySummaryView(
                total=summary_payload["total"],
                pass_count=summary_payload["pass"],
                warn_count=summary_payload["warn"],
                fail_count=summary_payload["fail"],
            ),
            records=records,
        )
```

`frontend/streamlit_app/state/__init__.py`

```python
from .workbench_state import (
    get_last_analysis_result,
    get_selected_eval_case_id,
    set_last_analysis_result,
    set_selected_eval_case_id,
)
```

- [ ] **Step 4: 重新运行测试，确认通过**

Run:

```bash
python -m unittest tests.unit.test_streamlit_api_client tests.unit.test_streamlit_workbench_state -v
```

Expected:

- PASS，API payload 解析与共享状态读写测试通过

- [ ] **Step 5: 提交这一小步**

```bash
git add frontend/streamlit_app/api_client.py frontend/streamlit_app/state tests/unit/test_streamlit_api_client.py tests/unit/test_streamlit_workbench_state.py
git commit -m "feat: 增加前端工作台共享状态与评测解析"
```

---

### Task 3: 搭好多页面骨架并实现分析视图

**Files:**
- Create: `frontend/streamlit_app/components/analysis_run_form.py`
- Create: `frontend/streamlit_app/components/response_summary_card.py`
- Create: `frontend/streamlit_app/pages/analysis_view.py`
- Modify: `frontend/streamlit_app/components/__init__.py`
- Modify: `frontend/streamlit_app/pages/__init__.py`
- Modify: `frontend/streamlit_app/app.py`
- Test: `tests/unit/test_streamlit_analysis_view.py`

- [ ] **Step 1: 先写失败测试，钉住分析视图的 view model 组装逻辑**

```python
from __future__ import annotations

import unittest

from frontend.streamlit_app.pages.analysis_view import build_analysis_view_model
from shared.contracts.analysis_response_envelope import AnalysisResponseEnvelope
from shared.contracts.final_response import FinalResponse
from shared.contracts.trace_block import TraceBlock


class StreamlitAnalysisViewTest(unittest.TestCase):
    def test_build_analysis_view_model_extracts_core_fields(self) -> None:
        envelope = AnalysisResponseEnvelope(
            session_id="sess_demo",
            response=FinalResponse(
                response_type="success",
                session_id="sess_demo",
                summary="中远海能等标的受益于运价弹性。",
                report_blocks=[],
            ),
            trace_blocks=[
                TraceBlock(
                    block_type="routing",
                    title="Routing",
                    status="success",
                    payload_summary={"intent": "event_impact_analysis"},
                ),
                TraceBlock(
                    block_type="execution",
                    title="Execution",
                    status="success",
                    payload_summary={
                        "stage_observations": [
                            {
                                "stage_name": "collect_event_context",
                                "key_outputs": {"strategy": "dual_primary"},
                            },
                            {
                                "stage_name": "retrieve_evidence",
                                "key_outputs": {"evidence_ref_count": 3},
                            },
                        ]
                    },
                ),
            ],
        )

        model = build_analysis_view_model(envelope)

        self.assertEqual(model["summary"], "中远海能等标的受益于运价弹性。")
        self.assertEqual(model["intent"], "event_impact_analysis")
        self.assertEqual(model["strategy"], "dual_primary")
        self.assertEqual(model["evidence_ref_count"], 3)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试，确认当前失败**

Run:

```bash
python -m unittest tests.unit.test_streamlit_analysis_view -v
```

Expected:

- FAIL，提示 `analysis_view` 模块或 `build_analysis_view_model` 未定义

- [ ] **Step 3: 写最小页面骨架和分析视图实现**

`frontend/streamlit_app/components/analysis_run_form.py`

```python
from __future__ import annotations

from typing import Any


def build_analysis_run_form_defaults() -> dict[str, Any]:
    return {
        "query": "",
        "session_id": "",
        "include_trace": True,
        "query_mode": "first_turn",
    }
```

`frontend/streamlit_app/components/response_summary_card.py`

```python
from __future__ import annotations

from shared.contracts.analysis_response_envelope import AnalysisResponseEnvelope


def build_response_summary_card_data(envelope: AnalysisResponseEnvelope) -> dict[str, object]:
    return {
        "response_type": envelope.response.response_type,
        "summary": getattr(envelope.response, "summary", ""),
        "session_id": envelope.session_id,
    }
```

`frontend/streamlit_app/pages/analysis_view.py`

```python
from __future__ import annotations

from shared.contracts.analysis_response_envelope import AnalysisResponseEnvelope


def build_analysis_view_model(envelope: AnalysisResponseEnvelope) -> dict[str, object]:
    intent = ""
    strategy = ""
    evidence_ref_count = 0
    for block in envelope.trace_blocks:
        if block.block_type == "routing":
            intent = str(block.payload_summary.get("intent") or "")
        if block.block_type == "execution":
            observations = block.payload_summary.get("stage_observations", [])
            for item in observations:
                stage_name = item.get("stage_name", "")
                key_outputs = item.get("key_outputs", {})
                if stage_name == "collect_event_context":
                    strategy = str(key_outputs.get("strategy") or "")
                if stage_name == "retrieve_evidence":
                    evidence_ref_count = int(key_outputs.get("evidence_ref_count") or 0)
    return {
        "summary": getattr(envelope.response, "summary", ""),
        "response_type": envelope.response.response_type,
        "intent": intent,
        "strategy": strategy,
        "degraded": envelope.response.response_type != "success",
        "evidence_ref_count": evidence_ref_count,
        "session_id": envelope.session_id,
    }
```

`frontend/streamlit_app/app.py`

```python
from frontend.streamlit_app.api_client import WorkbenchApiClient


APP_ENTRY_DESCRIPTION = "Streamlit debug/eval workbench for FinSight Agent V1."


def get_registered_pages() -> list[str]:
    return ["分析视图", "调试视图", "评测视图"]


def main() -> dict[str, object]:
    client = WorkbenchApiClient()
    request = client.build_request(query="宁德时代 2024 年净利润是多少？")
    return {
        "description": APP_ENTRY_DESCRIPTION,
        "endpoint_path": client.endpoint_path,
        "default_query_mode": request.query_mode,
        "pages": get_registered_pages(),
    }
```

`frontend/streamlit_app/components/__init__.py`

```python
from .analysis_run_form import build_analysis_run_form_defaults
from .response_summary_card import build_response_summary_card_data
```

`frontend/streamlit_app/pages/__init__.py`

```python
from .analysis_view import build_analysis_view_model
```

- [ ] **Step 4: 重新运行测试，确认通过**

Run:

```bash
python -m unittest tests.unit.test_streamlit_analysis_view -v
```

Expected:

- PASS，分析视图能稳定抽取 summary、intent、strategy 与证据数量

- [ ] **Step 5: 提交这一小步**

```bash
git add frontend/streamlit_app/app.py frontend/streamlit_app/components frontend/streamlit_app/pages tests/unit/test_streamlit_analysis_view.py
git commit -m "feat: 增加工作台分析视图骨架"
```

---

### Task 4: 实现调试视图与 trace/stage 组件

**Files:**
- Create: `frontend/streamlit_app/components/trace_block_viewer.py`
- Create: `frontend/streamlit_app/components/stage_observation_card.py`
- Create: `frontend/streamlit_app/pages/debug_view.py`
- Modify: `frontend/streamlit_app/components/__init__.py`
- Modify: `frontend/streamlit_app/pages/__init__.py`
- Test: `tests/unit/test_streamlit_debug_view.py`

- [ ] **Step 1: 先写失败测试，钉住调试视图对 trace 的分段与 stage 抽取**

```python
from __future__ import annotations

import unittest

from frontend.streamlit_app.pages.debug_view import build_debug_view_model
from shared.contracts.analysis_response_envelope import AnalysisResponseEnvelope
from shared.contracts.final_response import FinalResponse
from shared.contracts.trace_block import TraceBlock


class StreamlitDebugViewTest(unittest.TestCase):
    def test_build_debug_view_model_groups_trace_blocks(self) -> None:
        envelope = AnalysisResponseEnvelope(
            response=FinalResponse(response_type="success", summary="ok"),
            trace_blocks=[
                TraceBlock(block_type="routing", title="Routing", status="success", payload_summary={"intent": "event_impact_analysis"}),
                TraceBlock(block_type="planning", title="Planning", status="success", payload_summary={"stages": ["collect_event_context", "analyze_targets"]}),
                TraceBlock(
                    block_type="execution",
                    title="Execution",
                    status="degraded",
                    payload_summary={
                        "stage_statuses": {"collect_event_context": "success", "analyze_targets": "degraded"},
                        "stage_observations": [
                            {"stage_name": "collect_event_context", "status": "success", "key_outputs": {"strategy": "dual_primary"}},
                            {"stage_name": "analyze_targets", "status": "degraded", "key_outputs": {"target_scope": []}},
                        ],
                    },
                ),
            ],
        )

        model = build_debug_view_model(envelope)

        self.assertEqual(model["routing"]["intent"], "event_impact_analysis")
        self.assertEqual(model["planning"]["stages"][0], "collect_event_context")
        self.assertEqual(model["execution"]["stage_statuses"]["analyze_targets"], "degraded")
        self.assertEqual(model["stages"][1]["stage_name"], "analyze_targets")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试，确认当前失败**

Run:

```bash
python -m unittest tests.unit.test_streamlit_debug_view -v
```

Expected:

- FAIL，提示 `debug_view` 或 trace/stage 组件未定义

- [ ] **Step 3: 写最小 trace 视图实现**

`frontend/streamlit_app/components/trace_block_viewer.py`

```python
from __future__ import annotations

from shared.contracts.trace_block import TraceBlock


def build_trace_block_data(block: TraceBlock) -> dict[str, object]:
    return {
        "block_type": block.block_type,
        "title": block.title,
        "status": block.status,
        "payload_summary": dict(block.payload_summary),
        "raw_refs": list(block.raw_refs),
    }
```

`frontend/streamlit_app/components/stage_observation_card.py`

```python
from __future__ import annotations


def build_stage_observation_card_data(payload: dict[str, object]) -> dict[str, object]:
    return {
        "stage_name": payload.get("stage_name", ""),
        "status": payload.get("status", "degraded"),
        "key_outputs": payload.get("key_outputs", {}),
        "user_summary": payload.get("user_summary"),
    }
```

`frontend/streamlit_app/pages/debug_view.py`

```python
from __future__ import annotations

from shared.contracts.analysis_response_envelope import AnalysisResponseEnvelope


def build_debug_view_model(envelope: AnalysisResponseEnvelope) -> dict[str, object]:
    routing: dict[str, object] = {}
    planning: dict[str, object] = {}
    execution: dict[str, object] = {"stage_statuses": {}, "stage_observations": []}
    for block in envelope.trace_blocks:
        if block.block_type == "routing":
            routing = dict(block.payload_summary)
        elif block.block_type == "planning":
            planning = dict(block.payload_summary)
        elif block.block_type == "execution":
            execution = dict(block.payload_summary)
    stages = list(execution.get("stage_observations", []))
    return {
        "routing": routing,
        "planning": planning,
        "execution": execution,
        "stages": stages,
        "response_type": envelope.response.response_type,
    }
```

`frontend/streamlit_app/components/__init__.py`

```python
from .analysis_run_form import build_analysis_run_form_defaults
from .response_summary_card import build_response_summary_card_data
from .trace_block_viewer import build_trace_block_data
from .stage_observation_card import build_stage_observation_card_data
```

`frontend/streamlit_app/pages/__init__.py`

```python
from .analysis_view import build_analysis_view_model
from .debug_view import build_debug_view_model
```

- [ ] **Step 4: 重新运行测试，确认通过**

Run:

```bash
python -m unittest tests.unit.test_streamlit_debug_view -v
```

Expected:

- PASS，调试视图能正确分离 route / plan / execution，并抽取 stage 列表

- [ ] **Step 5: 提交这一小步**

```bash
git add frontend/streamlit_app/components frontend/streamlit_app/pages tests/unit/test_streamlit_debug_view.py
git commit -m "feat: 增加工作台调试视图"
```

---

### Task 5: 实现评测视图、工作台 smoke 测试与状态文档同步

**Files:**
- Create: `frontend/streamlit_app/components/eval_case_table.py`
- Create: `frontend/streamlit_app/components/eval_result_detail.py`
- Create: `frontend/streamlit_app/pages/eval_view.py`
- Modify: `frontend/streamlit_app/components/__init__.py`
- Modify: `frontend/streamlit_app/pages/__init__.py`
- Modify: `docs/finsight/project-status.md`
- Modify: `docs/finsight/modules/control-plane-status.md`
- Modify: `docs/finsight/modules/data-evidence-status.md`
- Test: `tests/unit/test_streamlit_eval_view.py`
- Test: `tests/integration/test_streamlit_workbench_smoke.py`

- [ ] **Step 1: 先写失败测试，钉住评测视图的筛选与详情对照逻辑**

```python
from __future__ import annotations

import unittest

from frontend.streamlit_app.pages.eval_view import build_eval_view_model
from frontend.streamlit_app.state.models import (
    EventEvalCaseView,
    EventReplayRecordView,
    EventReplayResultView,
    EventReplayRunView,
    EventReplaySummaryView,
)


class StreamlitEvalViewTest(unittest.TestCase):
    def test_build_eval_view_model_filters_failed_records(self) -> None:
        replay = EventReplayRunView(
            summary=EventReplaySummaryView(total=2, pass_count=1, warn_count=0, fail_count=1),
            records=[
                EventReplayRecordView(
                    case_id="dual_001",
                    query="红海局势升级利好哪些A股航运股？",
                    result=EventReplayResultView(
                        case_id="dual_001",
                        query="红海局势升级利好哪些A股航运股？",
                        actual_intent="event_impact_analysis",
                        actual_strategy="dual_primary",
                        response_type="success",
                        degraded=False,
                        target_count=2,
                        evidence_ref_count=3,
                        summary="ok",
                        failure_reason=None,
                        target_keywords=["中远海能"],
                    ),
                    checks=[{"check_name": "intent_match", "status": "pass", "message": "ok"}],
                ),
                EventReplayRecordView(
                    case_id="event_weak_001",
                    query="最近这个事件利好谁？",
                    result=EventReplayResultView(
                        case_id="event_weak_001",
                        query="最近这个事件利好谁？",
                        actual_intent="event_impact_analysis",
                        actual_strategy="event_primary",
                        response_type="degraded",
                        degraded=True,
                        target_count=0,
                        evidence_ref_count=0,
                        summary="当前只能确认事件背景。",
                        failure_reason=None,
                        target_keywords=[],
                    ),
                    checks=[{"check_name": "target_count", "status": "fail", "message": "target_count < 1"}],
                ),
            ],
        )

        model = build_eval_view_model(replay, status_filter="fail")

        self.assertEqual(model["summary"]["fail"], 1)
        self.assertEqual(len(model["records"]), 1)
        self.assertEqual(model["records"][0]["case_id"], "event_weak_001")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 写最小 smoke 测试，钉住工作台入口能暴露三页**

```python
from __future__ import annotations

import unittest

from frontend.streamlit_app.app import main


class StreamlitWorkbenchSmokeTest(unittest.TestCase):
    def test_app_main_exposes_three_workbench_pages(self) -> None:
        payload = main()

        self.assertEqual(
            payload["pages"],
            ["分析视图", "调试视图", "评测视图"],
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: 运行测试，确认当前失败**

Run:

```bash
python -m unittest tests.unit.test_streamlit_eval_view tests.integration.test_streamlit_workbench_smoke -v
```

Expected:

- FAIL，提示 `eval_view` 或相关组件未定义

- [ ] **Step 4: 写最小评测视图实现**

`frontend/streamlit_app/components/eval_case_table.py`

```python
from __future__ import annotations

from frontend.streamlit_app.state.models import EventEvalCaseView


def build_eval_case_table_rows(cases: list[EventEvalCaseView]) -> list[dict[str, object]]:
    return [
        {
            "case_id": case.case_id,
            "query": case.query,
            "expected_strategy": case.expected_strategy,
            "allow_degraded": case.allow_degraded,
        }
        for case in cases
    ]
```

`frontend/streamlit_app/components/eval_result_detail.py`

```python
from __future__ import annotations

from frontend.streamlit_app.state.models import EventReplayRecordView


def build_eval_result_detail_data(record: EventReplayRecordView) -> dict[str, object]:
    return {
        "case_id": record.case_id,
        "query": record.query,
        "actual_strategy": record.result.actual_strategy,
        "degraded": record.result.degraded,
        "target_count": record.result.target_count,
        "summary": record.result.summary,
        "checks": list(record.checks),
    }
```

`frontend/streamlit_app/pages/eval_view.py`

```python
from __future__ import annotations

from frontend.streamlit_app.state.models import EventReplayRunView


def build_eval_view_model(
    replay_run: EventReplayRunView,
    *,
    status_filter: str = "all",
) -> dict[str, object]:
    records = []
    for record in replay_run.records:
        statuses = [item["status"] for item in record.checks]
        derived_status = "fail" if "fail" in statuses else "warn" if "warn" in statuses else "pass"
        if status_filter != "all" and derived_status != status_filter:
            continue
        records.append(
            {
                "case_id": record.case_id,
                "query": record.query,
                "status": derived_status,
                "actual_strategy": record.result.actual_strategy,
                "degraded": record.result.degraded,
                "target_count": record.result.target_count,
            }
        )
    return {
        "summary": {
            "total": replay_run.summary.total,
            "pass": replay_run.summary.pass_count,
            "warn": replay_run.summary.warn_count,
            "fail": replay_run.summary.fail_count,
        },
        "records": records,
    }
```

`frontend/streamlit_app/components/__init__.py`

```python
from .analysis_run_form import build_analysis_run_form_defaults
from .response_summary_card import build_response_summary_card_data
from .trace_block_viewer import build_trace_block_data
from .stage_observation_card import build_stage_observation_card_data
from .eval_case_table import build_eval_case_table_rows
from .eval_result_detail import build_eval_result_detail_data
```

`frontend/streamlit_app/pages/__init__.py`

```python
from .analysis_view import build_analysis_view_model
from .debug_view import build_debug_view_model
from .eval_view import build_eval_view_model
```

- [ ] **Step 5: 重新运行测试，确认通过**

Run:

```bash
python -m unittest tests.unit.test_streamlit_eval_view tests.integration.test_streamlit_workbench_smoke -v
```

Expected:

- PASS，评测视图筛选逻辑与工作台入口 smoke 测试通过

- [ ] **Step 6: 跑这一轮完整回归**

Run:

```bash
python -m unittest tests.unit.test_event_eval_api tests.unit.test_streamlit_api_client tests.unit.test_streamlit_workbench_state tests.unit.test_streamlit_analysis_view tests.unit.test_streamlit_debug_view tests.unit.test_streamlit_eval_view tests.integration.test_streamlit_workbench_smoke -v
```

Expected:

- PASS，工作台相关单测与 smoke 测试全部通过

- [ ] **Step 7: 同步状态文档**

更新以下文档中的状态描述：

- `docs/finsight/project-status.md`
- `docs/finsight/modules/control-plane-status.md`
- `docs/finsight/modules/data-evidence-status.md`

新增或调整的描述应明确：

- Streamlit 工作台已具备分析、调试、评测三类视图
- eval replay 已具备前端可视化入口
- 当前仍属于内部工作台，不是正式产品前端

- [ ] **Step 8: 提交这一小步**

```bash
git add frontend/streamlit_app/components frontend/streamlit_app/pages docs/finsight/project-status.md docs/finsight/modules/control-plane-status.md docs/finsight/modules/data-evidence-status.md tests/unit/test_streamlit_eval_view.py tests/integration/test_streamlit_workbench_smoke.py
git commit -m "feat: 增加工作台评测视图"
```

---

## 自检

### Spec coverage

- 三个页面：Task 3、Task 4、Task 5 覆盖
- 复用分析接口：Task 2、Task 3、Task 4 覆盖
- 新增 eval 接口：Task 1 覆盖
- 共享最近一次运行结果：Task 2 状态助手、Task 3/4 页面逻辑覆盖
- 评测 replay 结果可视化：Task 5 覆盖

### Placeholder scan

- 计划中未使用 `TODO`、`TBD`、`later`
- 每个任务都包含具体测试代码、运行命令、最小实现片段、提交命令

### Type consistency

- eval 前端 view models 集中定义在 `frontend/streamlit_app/state/models.py`
- 页面函数统一命名为 `build_*_view_model`
- 状态助手统一使用 `MutableMapping[str, object]`，方便 `st.session_state` 与测试字典共用

