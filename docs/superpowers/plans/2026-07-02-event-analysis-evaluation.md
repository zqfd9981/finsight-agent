# 事件分析评测与回放实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `event_impact_analysis` 建立首版可版本化的事件样本、离线回放入口和最小评测检查闭环，支撑 provider 调优、误判回放和后续分类器训练对比。

**Architecture:** 在现有 `WorkbenchBackendApiService` 之上新增一个轻量 `evaluation/event_eval` 目录，专门承载 fixture schema、replay result schema、批量回放入口和确定性检查逻辑。保留现有 `tests/integration` 作为主链回归，新增的 replay runner 负责批量观测事件链质量而不是替代主流程。

**Tech Stack:** Python 3、dataclass、JSONL fixtures、`unittest`、现有 `WorkbenchBackendApiService` / `OrchestratorService` / shared contracts。

---

## 文件结构

### 新增文件

- `backend/src/finsight_agent/evaluation/__init__.py`
  - 评测目录包初始化。
- `backend/src/finsight_agent/evaluation/event_eval/__init__.py`
  - 事件评测子包初始化。
- `backend/src/finsight_agent/evaluation/event_eval/models.py`
  - `EventEvalCase`、`ReplayResult`、`CheckResult` 等标准模型。
- `backend/src/finsight_agent/evaluation/event_eval/fixture_loader.py`
  - 读取和校验 JSONL fixture。
- `backend/src/finsight_agent/evaluation/event_eval/checks.py`
  - 确定性评测检查逻辑。
- `backend/src/finsight_agent/evaluation/event_eval/replay.py`
  - 批量回放入口、结果抽取和汇总输出。
- `backend/src/finsight_agent/evaluation/event_eval/fixtures/event_cases_v1.jsonl`
  - 首批事件样本。
- `tests/unit/test_event_eval_models.py`
  - fixture schema / result schema / loader 的结构测试。
- `tests/unit/test_event_eval_checks.py`
  - 评测检查逻辑测试。
- `tests/unit/test_event_eval_replay.py`
  - replay runner 结果抽取与汇总测试。
- `tests/integration/test_event_analysis_replay_smoke.py`
  - 用真实事件主链做最小 replay smoke test。

### 修改文件

- `docs/finsight/project-status.md`
  - 在实现完成后同步“评测样本与回放框架”的状态。
- `docs/finsight/modules/control-plane-status.md`
  - 在实现完成后同步控制面评测能力状态。
- `docs/finsight/modules/data-evidence-status.md`
  - 在实现完成后同步外部 provider 的评测支持状态。

---

### Task 1: 建立评测模型与 fixture loader

**Files:**
- Create: `backend/src/finsight_agent/evaluation/__init__.py`
- Create: `backend/src/finsight_agent/evaluation/event_eval/__init__.py`
- Create: `backend/src/finsight_agent/evaluation/event_eval/models.py`
- Create: `backend/src/finsight_agent/evaluation/event_eval/fixture_loader.py`
- Test: `tests/unit/test_event_eval_models.py`

- [ ] **Step 1: 先写失败测试，钉住样本与结果 schema**

```python
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from finsight_agent.evaluation.event_eval.fixture_loader import load_event_eval_cases
from finsight_agent.evaluation.event_eval.models import EventEvalCase, ReplayResult


class EventEvalModelsTest(unittest.TestCase):
    def test_load_event_eval_cases_parses_jsonl_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture_path = Path(temp_dir) / "cases.jsonl"
            fixture_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "case_id": "event_dual_001",
                                "query": "红海局势升级利好哪些A股航运股？",
                                "expected_intent": "event_impact_analysis",
                                "expected_strategy": "dual_primary",
                                "allow_degraded": True,
                                "min_target_count": 1,
                                "expected_target_keywords": ["中远海能"],
                                "notes": "双主源事件样本",
                            },
                            ensure_ascii=False,
                        )
                    ]
                ),
                encoding="utf-8",
            )

            cases = load_event_eval_cases(fixture_path)

        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0].case_id, "event_dual_001")
        self.assertEqual(cases[0].expected_strategy, "dual_primary")

    def test_replay_result_serializes_core_fields(self) -> None:
        result = ReplayResult(
            case_id="event_dual_001",
            query="红海局势升级利好哪些A股航运股？",
            actual_intent="event_impact_analysis",
            actual_strategy="dual_primary",
            response_type="success",
            degraded=False,
            target_count=2,
            evidence_ref_count=3,
            summary="中远海能等标的受益于运价弹性。",
            failure_reason=None,
            target_keywords=["中远海能", "招商轮船"],
        )

        payload = result.to_dict()

        self.assertEqual(payload["actual_strategy"], "dual_primary")
        self.assertEqual(payload["target_count"], 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试，确认当前失败**

Run:

```bash
python -m unittest tests.unit.test_event_eval_models -v
```

Expected:

- FAIL，提示 `finsight_agent.evaluation.event_eval` 模块或相关类型不存在。

- [ ] **Step 3: 写最小模型与 loader 实现**

`backend/src/finsight_agent/evaluation/event_eval/models.py`

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class EventEvalCase:
    """描述一条事件评测样本。"""

    case_id: str
    query: str
    expected_intent: str
    expected_strategy: str
    allow_degraded: bool
    min_target_count: int = 0
    expected_target_keywords: list[str] = field(default_factory=list)
    notes: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "EventEvalCase":
        return cls(
            case_id=str(payload["case_id"]),
            query=str(payload["query"]),
            expected_intent=str(payload["expected_intent"]),
            expected_strategy=str(payload["expected_strategy"]),
            allow_degraded=bool(payload["allow_degraded"]),
            min_target_count=int(payload.get("min_target_count") or 0),
            expected_target_keywords=[
                str(item).strip()
                for item in (payload.get("expected_target_keywords") or [])
                if str(item).strip()
            ],
            notes=str(payload.get("notes") or "").strip() or None,
        )


@dataclass(slots=True)
class ReplayResult:
    """描述一条事件样本回放后的标准化结果。"""

    case_id: str
    query: str
    actual_intent: str
    actual_strategy: str
    response_type: str
    degraded: bool
    target_count: int
    evidence_ref_count: int
    summary: str
    failure_reason: str | None = None
    target_keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "query": self.query,
            "actual_intent": self.actual_intent,
            "actual_strategy": self.actual_strategy,
            "response_type": self.response_type,
            "degraded": self.degraded,
            "target_count": self.target_count,
            "evidence_ref_count": self.evidence_ref_count,
            "summary": self.summary,
            "failure_reason": self.failure_reason,
            "target_keywords": list(self.target_keywords),
        }


@dataclass(slots=True)
class CheckResult:
    """描述单条样本在某个检查项上的评测结果。"""

    check_name: str
    status: str
    message: str
```

`backend/src/finsight_agent/evaluation/event_eval/fixture_loader.py`

```python
from __future__ import annotations

import json
from pathlib import Path

from .models import EventEvalCase


def load_event_eval_cases(path: Path) -> list[EventEvalCase]:
    cases: list[EventEvalCase] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        cases.append(EventEvalCase.from_dict(payload))
    return cases
```

`backend/src/finsight_agent/evaluation/__init__.py`

```python
"""评测相关子模块。"""
```

`backend/src/finsight_agent/evaluation/event_eval/__init__.py`

```python
"""事件分析评测与回放子模块。"""
```

- [ ] **Step 4: 重新运行模型测试，确认通过**

Run:

```bash
python -m unittest tests.unit.test_event_eval_models -v
```

Expected:

- PASS，`load_event_eval_cases` 和 `ReplayResult.to_dict()` 都通过。

- [ ] **Step 5: 提交这一小步**

```bash
git add backend/src/finsight_agent/evaluation tests/unit/test_event_eval_models.py
git commit -m "feat: 增加事件评测模型与样本加载器"
```

---

### Task 2: 落首批事件样本 fixture

**Files:**
- Create: `backend/src/finsight_agent/evaluation/event_eval/fixtures/event_cases_v1.jsonl`
- Modify: `tests/unit/test_event_eval_models.py`

- [ ] **Step 1: 先补失败测试，钉住默认 fixture 至少覆盖三类策略**

```python
from pathlib import Path

from finsight_agent.evaluation.event_eval.fixture_loader import load_event_eval_cases


def test_default_fixture_covers_three_strategies(self) -> None:
    fixture_path = (
        Path(__file__).resolve().parents[2]
        / "backend"
        / "src"
        / "finsight_agent"
        / "evaluation"
        / "event_eval"
        / "fixtures"
        / "event_cases_v1.jsonl"
    )

    cases = load_event_eval_cases(fixture_path)
    strategies = {case.expected_strategy for case in cases}

    self.assertIn("event_primary", strategies)
    self.assertIn("disclosure_primary", strategies)
    self.assertIn("dual_primary", strategies)
    self.assertGreaterEqual(len(cases), 6)
```

- [ ] **Step 2: 运行测试，确认当前因 fixture 缺失而失败**

Run:

```bash
python -m unittest tests.unit.test_event_eval_models -v
```

Expected:

- FAIL，提示 `event_cases_v1.jsonl` 不存在。

- [ ] **Step 3: 写第一批 JSONL 事件样本**

`backend/src/finsight_agent/evaluation/event_eval/fixtures/event_cases_v1.jsonl`

```json
{"case_id":"event_001","query":"红海局势最近怎么了？","expected_intent":"event_impact_analysis","expected_strategy":"event_primary","allow_degraded":true,"min_target_count":0,"expected_target_keywords":["红海","航线"],"notes":"纯事件背景问题"}
{"case_id":"event_002","query":"美国加征关税会影响哪些行业？","expected_intent":"event_impact_analysis","expected_strategy":"event_primary","allow_degraded":true,"min_target_count":0,"expected_target_keywords":["关税","行业"],"notes":"外部事件偏背景理解"}
{"case_id":"disclosure_001","query":"宁德时代扩产公告意味着什么？","expected_intent":"event_impact_analysis","expected_strategy":"disclosure_primary","allow_degraded":false,"min_target_count":0,"expected_target_keywords":["宁德时代","扩产"],"notes":"公司内生事件"}
{"case_id":"disclosure_002","query":"某公司业绩预告是否释放积极信号？","expected_intent":"event_impact_analysis","expected_strategy":"disclosure_primary","allow_degraded":true,"min_target_count":0,"expected_target_keywords":["业绩预告"],"notes":"披露优先问题"}
{"case_id":"dual_001","query":"红海局势升级利好哪些A股航运股？","expected_intent":"event_impact_analysis","expected_strategy":"dual_primary","allow_degraded":true,"min_target_count":1,"expected_target_keywords":["航运","中远海能"],"notes":"事件背景+A股标的影响"}
{"case_id":"dual_002","query":"关税升级对哪些消费电子公司冲击更大？","expected_intent":"event_impact_analysis","expected_strategy":"dual_primary","allow_degraded":true,"min_target_count":1,"expected_target_keywords":["消费电子"],"notes":"外部事件+公司影响判断"}
```

- [ ] **Step 4: 重新运行模型测试，确认 fixture 可用**

Run:

```bash
python -m unittest tests.unit.test_event_eval_models -v
```

Expected:

- PASS，默认 fixture 至少包含三类策略，且样本量达到最小门槛。

- [ ] **Step 5: 提交这一小步**

```bash
git add backend/src/finsight_agent/evaluation/event_eval/fixtures tests/unit/test_event_eval_models.py
git commit -m "feat: 增加首批事件评测样本"
```

---

### Task 3: 实现确定性评测检查

**Files:**
- Create: `backend/src/finsight_agent/evaluation/event_eval/checks.py`
- Create: `tests/unit/test_event_eval_checks.py`

- [ ] **Step 1: 先写失败测试，钉住 intent、strategy、降级、候选和响应成形检查**

```python
from __future__ import annotations

import unittest

from finsight_agent.evaluation.event_eval.checks import run_event_eval_checks
from finsight_agent.evaluation.event_eval.models import EventEvalCase, ReplayResult


class EventEvalChecksTest(unittest.TestCase):
    def test_checks_fail_when_strategy_mismatches(self) -> None:
        case = EventEvalCase(
            case_id="dual_001",
            query="红海局势升级利好哪些A股航运股？",
            expected_intent="event_impact_analysis",
            expected_strategy="dual_primary",
            allow_degraded=True,
            min_target_count=1,
            expected_target_keywords=["航运"],
        )
        result = ReplayResult(
            case_id="dual_001",
            query=case.query,
            actual_intent="event_impact_analysis",
            actual_strategy="event_primary",
            response_type="success",
            degraded=False,
            target_count=1,
            evidence_ref_count=2,
            summary="事件背景已经建立。",
            target_keywords=["航运"],
        )

        checks = run_event_eval_checks(case, result)

        strategy_check = next(item for item in checks if item.check_name == "strategy_match")
        self.assertEqual(strategy_check.status, "fail")

    def test_checks_warn_when_degraded_is_allowed(self) -> None:
        case = EventEvalCase(
            case_id="event_001",
            query="红海局势最近怎么了？",
            expected_intent="event_impact_analysis",
            expected_strategy="event_primary",
            allow_degraded=True,
            min_target_count=0,
        )
        result = ReplayResult(
            case_id="event_001",
            query=case.query,
            actual_intent="event_impact_analysis",
            actual_strategy="event_primary",
            response_type="degraded",
            degraded=True,
            target_count=0,
            evidence_ref_count=1,
            summary="已拿到有限事件背景。",
        )

        checks = run_event_eval_checks(case, result)

        degraded_check = next(item for item in checks if item.check_name == "degraded_policy")
        self.assertEqual(degraded_check.status, "warn")
```

- [ ] **Step 2: 运行测试，确认当前失败**

Run:

```bash
python -m unittest tests.unit.test_event_eval_checks -v
```

Expected:

- FAIL，提示 `run_event_eval_checks` 不存在。

- [ ] **Step 3: 写最小检查逻辑**

`backend/src/finsight_agent/evaluation/event_eval/checks.py`

```python
from __future__ import annotations

from .models import CheckResult, EventEvalCase, ReplayResult


def run_event_eval_checks(case: EventEvalCase, result: ReplayResult) -> list[CheckResult]:
    checks = [
        _check_intent(case, result),
        _check_strategy(case, result),
        _check_degraded(case, result),
        _check_target_count(case, result),
        _check_response_shape(result),
        _check_target_keywords(case, result),
    ]
    return checks


def _check_intent(case: EventEvalCase, result: ReplayResult) -> CheckResult:
    status = "pass" if case.expected_intent == result.actual_intent else "fail"
    return CheckResult("intent_match", status, f"expected={case.expected_intent} actual={result.actual_intent}")


def _check_strategy(case: EventEvalCase, result: ReplayResult) -> CheckResult:
    status = "pass" if case.expected_strategy == result.actual_strategy else "fail"
    return CheckResult("strategy_match", status, f"expected={case.expected_strategy} actual={result.actual_strategy}")


def _check_degraded(case: EventEvalCase, result: ReplayResult) -> CheckResult:
    if not result.degraded:
        return CheckResult("degraded_policy", "pass", "未发生降级")
    if case.allow_degraded:
        return CheckResult("degraded_policy", "warn", "样本允许降级，当前按告警处理")
    return CheckResult("degraded_policy", "fail", "样本不允许降级，但实际发生降级")


def _check_target_count(case: EventEvalCase, result: ReplayResult) -> CheckResult:
    if result.target_count >= case.min_target_count:
        return CheckResult("target_count", "pass", f"target_count={result.target_count}")
    return CheckResult(
        "target_count",
        "fail",
        f"target_count={result.target_count} < min_target_count={case.min_target_count}",
    )


def _check_response_shape(result: ReplayResult) -> CheckResult:
    has_summary = bool(result.summary.strip())
    status = "pass" if has_summary else "fail"
    return CheckResult("response_shape", status, "summary present" if has_summary else "summary missing")


def _check_target_keywords(case: EventEvalCase, result: ReplayResult) -> CheckResult:
    if not case.expected_target_keywords:
        return CheckResult("target_keywords", "warn", "未配置关键词检查")
    joined = " ".join(result.target_keywords + [result.summary])
    matched = [keyword for keyword in case.expected_target_keywords if keyword and keyword in joined]
    status = "pass" if matched else "warn"
    return CheckResult("target_keywords", status, f"matched={matched}")
```

- [ ] **Step 4: 重新运行检查测试，确认通过**

Run:

```bash
python -m unittest tests.unit.test_event_eval_checks -v
```

Expected:

- PASS，策略错位时失败，允许降级时返回 `warn`。

- [ ] **Step 5: 提交这一小步**

```bash
git add backend/src/finsight_agent/evaluation/event_eval/checks.py tests/unit/test_event_eval_checks.py
git commit -m "feat: 增加事件评测检查逻辑"
```

---

### Task 4: 实现 replay runner 与结果抽取

**Files:**
- Create: `backend/src/finsight_agent/evaluation/event_eval/replay.py`
- Create: `tests/unit/test_event_eval_replay.py`

- [ ] **Step 1: 先写失败测试，钉住 envelope 到 ReplayResult 的结果抽取**

```python
from __future__ import annotations

import unittest

from finsight_agent.evaluation.event_eval.replay import build_replay_result
from finsight_agent.evaluation.event_eval.models import EventEvalCase
from shared.contracts.analysis_response_envelope import AnalysisResponseEnvelope
from shared.contracts.final_response import FinalResponse
from shared.contracts.trace_block import TraceBlock


class EventEvalReplayTest(unittest.TestCase):
    def test_build_replay_result_extracts_strategy_and_targets(self) -> None:
        case = EventEvalCase(
            case_id="dual_001",
            query="红海局势升级利好哪些A股航运股？",
            expected_intent="event_impact_analysis",
            expected_strategy="dual_primary",
            allow_degraded=True,
            min_target_count=1,
        )
        envelope = AnalysisResponseEnvelope(
            session_id="sess_001",
            response=FinalResponse(
                response_type="success",
                summary="中远海能、招商轮船等标的可能受益。",
                report_blocks=[],
            ),
            trace_blocks=[
                TraceBlock(
                    block_type="routing",
                    title="路由结果",
                    status="success",
                    payload_summary={"intent": "event_impact_analysis"},
                ),
                TraceBlock(
                    block_type="execution",
                    title="执行结果",
                    status="success",
                    payload_summary={
                        "stage_statuses": {
                            "collect_event_context": "success",
                            "analyze_targets": "success",
                        },
                        "stage_observations": [
                            {
                                "stage_name": "collect_event_context",
                                "key_outputs": {"strategy": "dual_primary"},
                                "evidence_refs": ["ext_001"],
                            },
                            {
                                "stage_name": "analyze_targets",
                                "key_outputs": {"target_scope": ["中远海能", "招商轮船"]},
                                "evidence_refs": [],
                            },
                        ],
                    },
                ),
            ],
        )

        result = build_replay_result(case, envelope)

        self.assertEqual(result.actual_strategy, "dual_primary")
        self.assertEqual(result.target_count, 2)
        self.assertEqual(result.evidence_ref_count, 1)
```

- [ ] **Step 2: 运行测试，确认当前失败**

Run:

```bash
python -m unittest tests.unit.test_event_eval_replay -v
```

Expected:

- FAIL，提示 `build_replay_result` 不存在。

- [ ] **Step 3: 实现结果抽取与批量回放入口**

`backend/src/finsight_agent/evaluation/event_eval/replay.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from finsight_agent.workbench_backend_api.service import WorkbenchBackendApiService
from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.analysis_response_envelope import AnalysisResponseEnvelope

from .checks import run_event_eval_checks
from .fixture_loader import load_event_eval_cases
from .models import CheckResult, EventEvalCase, ReplayResult


@dataclass(slots=True)
class ReplayRunRecord:
    case: EventEvalCase
    result: ReplayResult
    checks: list[CheckResult]


def replay_event_cases(
    fixture_path: Path,
    *,
    service: WorkbenchBackendApiService | None = None,
    include_trace: bool = True,
) -> list[ReplayRunRecord]:
    workbench_service = service or WorkbenchBackendApiService()
    records: list[ReplayRunRecord] = []
    for case in load_event_eval_cases(fixture_path):
        envelope = workbench_service.build_response(
            AnalysisRequest(query=case.query, include_trace=include_trace)
        )
        result = build_replay_result(case, envelope)
        checks = run_event_eval_checks(case, result)
        records.append(ReplayRunRecord(case=case, result=result, checks=checks))
    return records


def build_replay_result(
    case: EventEvalCase,
    envelope: AnalysisResponseEnvelope,
) -> ReplayResult:
    actual_intent = ""
    actual_strategy = ""
    target_keywords: list[str] = []
    evidence_ref_count = 0

    for block in envelope.trace_blocks:
        if block.block_type == "routing":
            actual_intent = str(block.payload_summary.get("intent") or "")
        if block.block_type != "execution":
            continue
        observations = block.payload_summary.get("stage_observations") or []
        for observation in observations:
            if observation.get("stage_name") == "collect_event_context":
                key_outputs = observation.get("key_outputs") or {}
                actual_strategy = str(key_outputs.get("strategy") or actual_strategy)
                evidence_ref_count += len(observation.get("evidence_refs") or [])
            if observation.get("stage_name") == "analyze_targets":
                key_outputs = observation.get("key_outputs") or {}
                target_keywords.extend(
                    [str(item).strip() for item in (key_outputs.get("target_scope") or []) if str(item).strip()]
                )
                evidence_ref_count += len(observation.get("evidence_refs") or [])

    response = envelope.response
    summary = getattr(response, "summary", "") or ""
    response_type = getattr(response, "response_type", "degraded") or "degraded"
    degraded = response_type != "success"

    return ReplayResult(
        case_id=case.case_id,
        query=case.query,
        actual_intent=actual_intent,
        actual_strategy=actual_strategy,
        response_type=response_type,
        degraded=degraded,
        target_count=len(target_keywords),
        evidence_ref_count=evidence_ref_count,
        summary=summary,
        failure_reason=None if summary else "empty_summary",
        target_keywords=target_keywords,
    )
```

- [ ] **Step 4: 重新运行 replay 单测，确认通过**

Run:

```bash
python -m unittest tests.unit.test_event_eval_replay -v
```

Expected:

- PASS，`actual_strategy`、`target_count`、`evidence_ref_count` 都能被抽取。

- [ ] **Step 5: 提交这一小步**

```bash
git add backend/src/finsight_agent/evaluation/event_eval/replay.py tests/unit/test_event_eval_replay.py
git commit -m "feat: 增加事件评测回放入口"
```

---

### Task 5: 增加最小 replay smoke test，并同步状态文档

**Files:**
- Create: `tests/integration/test_event_analysis_replay_smoke.py`
- Modify: `docs/finsight/project-status.md`
- Modify: `docs/finsight/modules/control-plane-status.md`
- Modify: `docs/finsight/modules/data-evidence-status.md`

- [ ] **Step 1: 先写失败的 replay smoke test**

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

from finsight_agent.evaluation.event_eval.replay import replay_event_cases
from finsight_agent.control_plane.orchestrator.service import OrchestratorService
from finsight_agent.control_plane.session.repository import SessionRepository
from finsight_agent.control_plane.session.service import SessionService
from finsight_agent.workbench_backend_api.service import WorkbenchBackendApiService
from tests.integration.test_event_impact_analysis_flow import (
    _StubExternalContextRetriever,
    _StubPlannerService,
    _StubRetrievalFacade,
    _StubRouterService,
    _StubTargetAnalysisService,
)


class EventAnalysisReplaySmokeTest(unittest.TestCase):
    def test_replay_event_cases_returns_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture_path = Path(temp_dir) / "cases.jsonl"
            fixture_path.write_text(
                '{"case_id":"dual_001","query":"红海局势升级利好哪些A股航运股？","expected_intent":"event_impact_analysis","expected_strategy":"dual_primary","allow_degraded":true,"min_target_count":1,"expected_target_keywords":["中远海能"],"notes":"smoke"}\n',
                encoding="utf-8",
            )

            service = WorkbenchBackendApiService(
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

            records = replay_event_cases(fixture_path, service=service)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].result.actual_intent, "event_impact_analysis")
        self.assertTrue(records[0].checks)
```

- [ ] **Step 2: 运行测试，确认当前因 strategy 未写入 trace 或抽取不完整而失败**

Run:

```bash
python -m unittest tests.integration.test_event_analysis_replay_smoke -v
```

Expected:

- 初始可能 FAIL，暴露 replay 抽取字段和现有 trace 的不一致处。

- [ ] **Step 3: 按实际 trace 结构补齐最小可用实现，并同步状态文档**

如果现有 `execution` trace block 还没有足够的 `stage_observations` 摘要，请补最小必要信息，保证 replay 抽取稳定。补齐后同步 3 份状态文档，明确：

- 事件评测样本与回放框架已接入首版
- 可用于 provider 调优与分类器训练前后对比

状态文档建议补充的句式：

`docs/finsight/project-status.md`

```md
- 已新增 `event_impact_analysis` 评测样本与 replay 回放框架
- 当前可批量观察 intent、strategy、降级和候选发现结果
```

`docs/finsight/modules/control-plane-status.md`

```md
| 事件分析评测样本与回放 | 已完成首版 | 可批量回放事件 query，并观测策略与降级结果 |
```

`docs/finsight/modules/data-evidence-status.md`

```md
| 事件外部检索质量回放 | 已完成首版 | 可用于观察 provider 命中、弱结果与候选发现行为 |
```

- [ ] **Step 4: 跑完整验证**

Run:

```bash
python -m unittest tests.unit.test_event_eval_models tests.unit.test_event_eval_checks tests.unit.test_event_eval_replay tests.integration.test_event_analysis_replay_smoke tests.integration.test_event_impact_analysis_flow -v
```

Expected:

- PASS
- 至少能够看到：
  - fixture loader 通过
  - checks 通过
  - replay 抽取通过
  - replay smoke test 通过
  - 原有事件主链集成测试未退化

- [ ] **Step 5: 提交这一小步**

```bash
git add backend/src/finsight_agent/evaluation tests/integration/test_event_analysis_replay_smoke.py docs/finsight/project-status.md docs/finsight/modules/control-plane-status.md docs/finsight/modules/data-evidence-status.md
git commit -m "feat: 增加事件分析评测与回放框架"
```

---

## 自检要点

- 样本 schema、结果 schema、检查逻辑和 replay 抽取字段必须一致命名。
- 首版不要引入 LLM judge、复杂总分或前端面板。
- replay runner 必须走真实 `WorkbenchBackendApiService`，不要绕过主链。
- 如果现有 trace 不足以提取 `actual_strategy`，只补最小必要字段，不重构整条 trace 体系。

## 建议验证命令

```bash
python -m unittest tests.unit.test_event_eval_models tests.unit.test_event_eval_checks tests.unit.test_event_eval_replay tests.integration.test_event_analysis_replay_smoke tests.integration.test_event_impact_analysis_flow -v
```

## 后续不在本计划内

- `RetrievalStrategyClassifier` 真正训练与上线切换
- provider 级缓存、超时、熔断
- LLM judge 或更复杂质量评分
- Web UI / 可视化评测面板
