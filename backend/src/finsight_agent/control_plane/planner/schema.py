from __future__ import annotations

from typing import Any

from shared.contracts.plan import Plan
from shared.enums.intent import Intent
from shared.enums.response_mode import ResponseMode
from shared.enums.stage_name import StageName


def plan_from_payload(payload: dict[str, Any]) -> Plan:
    required_keys = {
        "plan_id",
        "intent",
        "stages",
        "stage_constraints",
        "response_mode",
    }
    if not required_keys.issubset(payload):
        raise ValueError("planner payload missing required keys")
    if payload["intent"] not in {item.value for item in Intent}:
        raise ValueError("invalid plan intent")
    if not isinstance(payload["stages"], list):
        raise ValueError("stages must be list")
    allowed_stages = {item.value for item in StageName}
    if any(stage not in allowed_stages for stage in payload["stages"]):
        raise ValueError("invalid stage in plan")
    if not isinstance(payload["stage_constraints"], dict):
        raise ValueError("stage_constraints must be object")
    if payload["response_mode"] not in {item.value for item in ResponseMode}:
        raise ValueError("invalid response_mode")

    return Plan(
        plan_id=payload["plan_id"],
        intent=payload["intent"],
        stages=payload["stages"],
        stage_constraints=payload["stage_constraints"],
        response_mode=payload["response_mode"],
    )
