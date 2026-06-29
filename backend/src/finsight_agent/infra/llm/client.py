from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class LlmRequest:
    prompt_name: str
    system_prompt: str
    user_prompt: str


class LlmClient:
    """最小 LLM JSON 输出适配器。

    当前默认从环境变量读取预置 JSON，便于在骨架阶段验证主链路；
    后续可在不改 router/planner 接口的前提下替换为真实模型调用。
    """

    def complete_json(self, *, prompt_name: str, variables: dict[str, object]) -> dict[str, Any]:
        response_env = f"FINSIGHT_{prompt_name.upper()}_JSON"
        raw = os.getenv(response_env)
        if not raw:
            raise RuntimeError(f"missing llm response env: {response_env}")

        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("llm response must be a JSON object")
        return payload
