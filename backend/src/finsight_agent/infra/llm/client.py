from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import requests


@dataclass(slots=True)
class LlmRequest:
    prompt_name: str
    system_prompt: str
    user_prompt: str


class LlmClient:
    """Structured JSON LLM adapter with legacy fixture fallback."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self._base_url = (
            (base_url or os.getenv("FINSIGHT_LLM_BASE_URL") or "https://api.fe8.cn/v1")
            .rstrip("/")
        )
        self._api_key = (
            api_key
            or os.getenv("FINSIGHT_LLM_API_KEY")
            or os.getenv("DEVAGI_API_KEY")
        )
        self._model = model or os.getenv("FINSIGHT_LLM_MODEL") or "gpt-4o"
        self._timeout_seconds = timeout_seconds or float(
            os.getenv("FINSIGHT_LLM_TIMEOUT_SECONDS", "60")
        )

    def complete_json(
        self,
        *,
        prompt_name: str,
        variables: dict[str, object],
    ) -> dict[str, Any]:
        raw = os.getenv(_legacy_response_env(prompt_name))
        if raw:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("llm response must be a JSON object")
            return payload

        if not self._api_key:
            raise RuntimeError(
                "missing llm api key: set FINSIGHT_LLM_API_KEY or DEVAGI_API_KEY"
            )

        request = self._build_request(prompt_name=prompt_name, variables=variables)
        response = requests.post(
            f"{self._base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self._model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": request.system_prompt},
                    {"role": "user", "content": request.user_prompt},
                ],
            },
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()

        payload = _extract_json_payload(response.json())
        if not isinstance(payload, dict):
            raise ValueError("llm response must be a JSON object")
        return payload

    def _build_request(
        self,
        *,
        prompt_name: str,
        variables: dict[str, object],
    ) -> LlmRequest:
        system_prompt = variables.get("system_prompt")
        if isinstance(system_prompt, str) and system_prompt.strip():
            normalized_system_prompt = system_prompt.strip()
        else:
            normalized_system_prompt = _default_system_prompt(prompt_name)

        payload_variables = {
            key: value
            for key, value in variables.items()
            if key != "system_prompt"
        }
        user_prompt = (
            "Return exactly one JSON object that satisfies the requested schema.\n"
            f"prompt_name: {prompt_name}\n"
            "input_variables:\n"
            f"{json.dumps(payload_variables, ensure_ascii=False, indent=2, default=_json_default)}"
        )
        return LlmRequest(
            prompt_name=prompt_name,
            system_prompt=normalized_system_prompt,
            user_prompt=user_prompt,
        )


def _legacy_response_env(prompt_name: str) -> str:
    return f"FINSIGHT_{prompt_name.upper()}_JSON"


def _default_system_prompt(prompt_name: str) -> str:
    if prompt_name == "event_target_analysis":
        return (
            "You are FinSight Agent V1 target analysis planner. "
            "Return exactly one JSON object and no markdown. "
            "Required keys: target_scope, ranked_targets, open_questions, confidence, analysis_mode. "
            "target_scope must be a list of strings. "
            "ranked_targets must be a list of objects with keys "
            "target, target_type, impact_direction, reasoning_summary, confidence."
        )
    return (
        "You are a structured JSON assistant for FinSight Agent V1. "
        "Return exactly one valid JSON object and no markdown, prose, or code fences."
    )


def _extract_json_payload(response_payload: dict[str, Any]) -> dict[str, Any]:
    choices = response_payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("llm response missing choices")

    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ValueError("llm response missing message")

    content = message.get("content")
    normalized_content = _normalize_message_content(content)
    payload = json.loads(normalized_content)
    if not isinstance(payload, dict):
        raise ValueError("llm response must be a JSON object")
    return payload


def _normalize_message_content(content: object) -> str:
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text" and isinstance(item.get("text"), str):
                text_parts.append(item["text"])
        if text_parts:
            return "".join(text_parts)
    raise ValueError("llm response missing message content")


def _json_default(value: object) -> str:
    return str(value)
