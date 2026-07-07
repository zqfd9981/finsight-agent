from __future__ import annotations


def build_stage_observation_card_data(payload: dict[str, object]) -> dict[str, object]:
    return {
        "stage_name": payload.get("stage_name", ""),
        "status": payload.get("status", "degraded"),
        "key_outputs": payload.get("key_outputs", {}),
        "user_summary": payload.get("user_summary"),
    }
