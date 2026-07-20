"""LLM 驱动的检索策略分类器（默认主路径）。

与 Trained 分类器不同，它直接消费上游路由已抽出的 ``entities.company``，
因此对「具体公司 + 事件影响」这类查询鲁棒，且不依赖训练数据覆盖（解决了
Trained 模型 OOD + 实体盲的问题）。失败时回退到 fallback（通常是 Trained + Stub）。
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from finsight_agent.infra.llm import LlmClient
from finsight_agent.infra.llm.prompt_registry import get_prompt

from .retrieval_strategy_classifier import (
    DEFAULT_RETRIEVAL_STRATEGY,
    RETRIEVAL_STRATEGIES,
    RetrievalStrategyClassifier,
    StubRetrievalStrategyClassifier,
)

logger = logging.getLogger(__name__)

_PROMPT_NAME = "strategy"
_SYSTEM_PROMPT_NAME = "strategy.system"
_EVENT_IMPACT_INTENT = "event_impact_analysis"


def _extract_company_name(entities: object) -> str | None:
    """从上游路由抽出的 entities 中取出公司名（兼容 dict / str / None）。

    entities.company 可能是：
      - str：直接是公司名
      - dict：{raw, standard_name, stock_code}，优先取 standard_name
    """
    if not isinstance(entities, Mapping):
        return None
    company = entities.get("company")
    if company is None:
        return None
    if isinstance(company, str):
        return company.strip() or None
    if isinstance(company, Mapping):
        name = company.get("standard_name") or company.get("raw")
        if isinstance(name, str):
            return name.strip() or None
    return None


class LlmRetrievalStrategyClassifier:
    """LLM 判断优先的检索策略分类器，实现 ``RetrievalStrategyClassifier`` 接口。

    调用 ``LlmClient.complete_json`` 获取结构化策略判定；任何异常或非法输出
    都回退到 fallback。额外加一层确定性安全网：当实体已明确抽出具体公司且意图为
    事件影响、但 LLM 仍判 event_primary 时，按既定规则强制 dual_primary，
    避免回归（如「红海局势会对隆基绿能产生什么影响」）。
    """

    def __init__(
        self,
        *,
        llm_client: LlmClient,
        fallback: RetrievalStrategyClassifier | None = None,
        prompt_name: str = _PROMPT_NAME,
        system_prompt: str | None = None,
    ) -> None:
        self._llm_client = llm_client
        self._fallback: RetrievalStrategyClassifier = (
            fallback if fallback is not None else StubRetrievalStrategyClassifier()
        )
        self._prompt_name = prompt_name
        self._system_prompt = system_prompt or get_prompt(_SYSTEM_PROMPT_NAME).text

    def classify(
        self,
        *,
        query: str,
        router_payload: dict[str, object],
        session_topic: str,
    ) -> dict[str, str]:
        entities = router_payload.get("entities") or {}
        intent = router_payload.get("intent") or ""
        company = _extract_company_name(entities)

        try:
            payload = self._llm_client.complete_json(
                prompt_name=self._prompt_name,
                variables={
                    "system_prompt": self._system_prompt,
                    "query": query,
                    "intent": intent,
                    "entities": entities,
                    "session_topic": session_topic or "",
                },
            )
        except Exception as exc:
            logger.warning("llm strategy classifier failed (%r) — fallback", exc)
            return self._fallback.classify(
                query=query, router_payload=router_payload, session_topic=session_topic
            )

        strategy = payload.get("strategy")
        if strategy not in RETRIEVAL_STRATEGIES:
            logger.warning(
                "llm strategy returned invalid %r — fallback", strategy
            )
            return self._fallback.classify(
                query=query, router_payload=router_payload, session_topic=session_topic
            )

        reason = str(payload.get("reason") or "")
        confidence = str(payload.get("confidence") or "medium")

        # 安全网：实体已明确抽出具体公司 + 事件影响意图，但 LLM 仍判 event_primary
        # → 按既定规则强制 dual_primary，避免回归。若你信任提示词已足够，可删除此段。
        if (
            strategy == "event_primary"
            and company
            and str(intent) == _EVENT_IMPACT_INTENT
        ):
            logger.info(
                "entity safety-net: company=%s + event_impact → force dual_primary",
                company,
            )
            strategy = "dual_primary"
            reason = (
                f"entity_override: company={company} + event_impact → dual_primary; "
                f"llm_reason={reason}"
            )

        return {
            "strategy": strategy,
            "confidence": confidence,
            "reason": reason,
        }
