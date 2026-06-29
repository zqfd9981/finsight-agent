from __future__ import annotations

import os


def llm_router_enabled() -> bool:
    """控制 router 是否优先走 LLM 结构化判别。"""
    return os.getenv("FINSIGHT_LLM_ROUTER_ENABLED", "1") == "1"


def llm_planner_enabled() -> bool:
    """控制 planner 是否优先走 LLM 结构化规划。"""
    return os.getenv("FINSIGHT_LLM_PLANNER_ENABLED", "1") == "1"
