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
    """返回事件评测接口的路由元数据。"""

    return [
        {"method": "GET", "path": EVENT_CASES_PATH, "handler": "handle_event_cases"},
        {"method": "POST", "path": EVENT_REPLAY_PATH, "handler": "handle_event_replay"},
    ]


def handle_event_cases() -> dict[str, Any]:
    """返回事件评测样本列表。"""

    cases = load_event_eval_cases(DEFAULT_EVENT_FIXTURE_PATH)
    return {"cases": [case.to_dict() for case in cases]}


def handle_event_replay(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """运行指定事件评测样本的 replay。"""

    request_payload = payload or {}
    case_ids = request_payload.get("case_ids")
    records = replay_event_cases(
        fixture_path=DEFAULT_EVENT_FIXTURE_PATH,
        case_ids=case_ids,
        include_trace=True,
    )

    summary = {"total": len(records), "pass": 0, "warn": 0, "fail": 0}
    serialized_records = []
    for record in records:
        if isinstance(record, dict):
            serialized_records.append(record)
            check_statuses = [str(item["status"]) for item in record.get("checks", [])]
        else:
            serialized_records.append(record.to_dict())
            check_statuses = [item.status for item in record.checks]
        if "fail" in check_statuses:
            summary["fail"] += 1
        elif "warn" in check_statuses:
            summary["warn"] += 1
        else:
            summary["pass"] += 1

    return {"records": serialized_records, "summary": summary}
