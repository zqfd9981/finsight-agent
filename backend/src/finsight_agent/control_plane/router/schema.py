from __future__ import annotations

from typing import Any

from shared.contracts.router_result import RouterResult
from shared.enums.follow_up_type import FollowUpType
from shared.enums.intent import Intent


def router_result_from_payload(payload: dict[str, Any]) -> RouterResult:
    required_keys = {
        "intent",
        "follow_up_type",
        "confidence",
        "entities",
        "needs",
        "constraints",
    }
    if not required_keys.issubset(payload):
        raise ValueError("router payload missing required keys")
    if payload["intent"] not in {item.value for item in Intent}:
        raise ValueError("invalid router intent")
    if payload["follow_up_type"] not in {item.value for item in FollowUpType}:
        raise ValueError("invalid follow_up_type")
    if not isinstance(payload["entities"], dict):
        raise ValueError("entities must be object")
    if not isinstance(payload["needs"], list):
        raise ValueError("needs must be list")
    if not isinstance(payload["constraints"], dict):
        raise ValueError("constraints must be object")

    return RouterResult(
        intent=payload["intent"],
        follow_up_type=payload["follow_up_type"],
        confidence=payload["confidence"],
        entities=payload["entities"],
        needs=payload["needs"],
        constraints=payload["constraints"],
    )
