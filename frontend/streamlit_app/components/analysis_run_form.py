from __future__ import annotations

from typing import Any


def build_analysis_run_form_defaults() -> dict[str, Any]:
    return {
        "query": "",
        "session_id": "",
        "include_trace": True,
        "query_mode": "first_turn",
    }
