from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any

import requests

_logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LlmRequest:
    prompt_name: str
    system_prompt: str
    user_prompt: str


class LlmClient:
    """基于 AGICTO (OpenAI 兼容) 的结构化 JSON LLM 适配器。

    通过 https://api.agicto.cn/v1/chat/completions 调用，
    使用 response_format=json_object 强制 JSON 输出。
    内置重试以应对临时性错误（429/5xx/网络抖动）。

    保留 legacy fixture 机制以支持无网络的单元测试：
      FINSIGHT_<PROMPT_NAME>_JSON 环境变量存在时直接返回该 JSON。
    """

    _API_BASE = "https://api.agicto.cn/v1"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        max_retries: int | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self._api_key = (
            api_key
            or os.getenv("AGICTO_API_KEY")
            or os.getenv("FINSIGHT_LLM_API_KEY")
            or None
        )
        self._model = model or os.getenv("FINSIGHT_LLM_MODEL") or "deepseek-v4-flash"
        self._max_tokens = max_tokens or int(
            os.getenv("FINSIGHT_LLM_MAX_TOKENS", "4096")
        )
        self._max_retries = max_retries or int(
            os.getenv("FINSIGHT_LLM_MAX_RETRIES", "3")
        )
        # 30s 硬约束：前端 read timeout=120s，单次 LLM 最坏 30+1.5+30+3+30=94.5s
        # 留出 ~25s 给其他 stage 串行执行。原默认 60s 违反 project_memory 硬约束。
        self._timeout_seconds = timeout_seconds or float(
            os.getenv("FINSIGHT_LLM_TIMEOUT_SECONDS", "30")
        )

    def complete_json(
        self,
        *,
        prompt_name: str,
        variables: dict[str, object],
    ) -> dict[str, Any]:
        # legacy fixture：无网络测试场景
        raw = os.getenv(_legacy_response_env(prompt_name))
        if raw:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("llm response must be a JSON object")
            return payload

        if not self._api_key:
            raise RuntimeError(
                "missing llm api key: set AGICTO_API_KEY"
            )

        request = self._build_request(prompt_name=prompt_name, variables=variables)
        url = f"{self._API_BASE}/chat/completions"
        body = self._build_openai_body(request)

        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                response = requests.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                    timeout=self._timeout_seconds,
                )
                # 429/5xx 视为可重试
                if response.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(
                        f"agicto returned {response.status_code}",
                        response=response,
                    )
                response.raise_for_status()
                text = _extract_content_text(response.json())
                payload = _parse_json_payload(text)
                if not isinstance(payload, dict):
                    raise ValueError("llm response must be a JSON object")
                return payload
            except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
                last_error = e
                if attempt < self._max_retries:
                    time.sleep(1.5 * attempt)
                    continue
                raise

        raise last_error or RuntimeError("llm call failed after retries")

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

    def _build_openai_body(self, request: LlmRequest) -> dict[str, Any]:
        return {
            "model": self._model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "temperature": 0,
            "max_tokens": self._max_tokens,
            "response_format": {"type": "json_object"},
        }


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


def _extract_content_text(response_payload: dict[str, Any]) -> str:
    """从 OpenAI 兼容响应中提取文本内容。"""
    choices = response_payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("llm response missing choices")

    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ValueError("llm response missing message")

    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("llm response missing content text")

    return content


def _parse_json_payload(text: str) -> dict[str, Any]:
    """从 LLM 响应文本中解析 JSON 对象。

    response_format=json_object 下通常返回纯 JSON，
    但偶发会带前后空白或多余文本，这里先尝试直接解析，失败则用正则提取第一个 {} 块。
    LLM 偶发会返回字符串值含未转义引号或内部逗号缺失的非法 JSON，
    此时记录原始返回用于诊断，并抛出 ValueError 让上层决定降级策略。
    """
    text = text.strip()
    if not text:
        raise ValueError("llm response is empty")

    # 尝试 1：直接解析
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    # 尝试 2：提取第一个 {...} 块（非贪婪，避免多块场景误匹配）
    match = re.search(r"\{[\s\S]*?\}", text)
    if match:
        try:
            payload = json.loads(match.group(0))
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass  # 继续尝试下面

    # 尝试 3：去掉可能的 markdown 代码块标记后重试
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    if cleaned != text:
        try:
            payload = json.loads(cleaned)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass

    # 全部失败：记录原始返回用于诊断
    _logger.warning(
        "llm response is not valid JSON (len=%d, first 300 chars): %r",
        len(text),
        text[:300],
    )
    raise ValueError(f"llm response is not valid JSON: {text[:200]!r}")


def _json_default(value: object) -> str:
    return str(value)
