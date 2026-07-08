from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from finsight_agent.infra.llm.client import LlmClient


logger = logging.getLogger(__name__)

DEFAULT_RERANK_MODEL_NAME = "BAAI/bge-reranker-v2-m3"
MODEL_DIR_ENV = "FINSIGHT_RERANK_MODEL_DIR"
MODEL_NAME_ENV = "FINSIGHT_RERANK_MODEL_NAME"
MODEL_ENABLED_ENV = "FINSIGHT_RERANK_ENABLED"
BACKEND_ENV = "FINSIGHT_RERANK_BACKEND"

_COMMON_QUERY_TERMS = {
    "哪些",
    "什么",
    "最近",
    "怎么",
    "如何",
    "到底",
    "还是",
    "影响",
    "方面",
    "产生",
    "意味着",
    "会对",
    "会",
    "对",
    "是否",
    "情况",
    "进展",
    "问题",
    "一个",
}
_SPLIT_MARKERS = (
    "到底",
    "意味着",
    "如何",
    "怎么",
    "哪些",
    "什么",
    "影响",
    "会",
    "对",
)


@dataclass(slots=True)
class RerankCandidate:
    id: str
    title: str
    text: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class RerankScore:
    id: str
    score: float
    keep: bool
    reason: str = ""


class _LazySequenceReranker:
    def __init__(self, model_dir: str | Path | None, model_name: str) -> None:
        self._model_dir = Path(model_dir) if model_dir else None
        self._model_name = model_name
        self._tokenizer: Any | None = None
        self._model: Any | None = None
        self._load_attempted = False
        self._available = False

    @property
    def available(self) -> bool:
        self._ensure_loaded()
        return self._available

    def _ensure_loaded(self) -> None:
        if self._load_attempted:
            return
        self._load_attempted = True
        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer  # type: ignore
        except Exception as exc:  # pragma: no cover
            logger.warning("rerank model import failed (%s); using lexical fallback", exc)
            return

        model_ref = str(self._model_dir) if self._model_dir is not None else self._model_name
        try:
            self._tokenizer = AutoTokenizer.from_pretrained(model_ref)
            self._model = AutoModelForSequenceClassification.from_pretrained(model_ref)
            self._model.eval()
            self._available = True
        except Exception as exc:  # pragma: no cover
            logger.warning("rerank model load failed (%s); using lexical fallback", exc)

    def score_pairs(self, query: str, texts: list[str]) -> list[float]:
        self._ensure_loaded()
        if not self._available or not texts:
            raise RuntimeError("rerank model unavailable")

        try:
            import torch  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("torch unavailable") from exc

        inputs = self._tokenizer(
            [query] * len(texts),
            texts,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )
        with torch.no_grad():
            logits = self._model(**inputs).logits

        if logits.ndim == 1:
            raw_scores = logits
        elif logits.shape[-1] == 1:
            raw_scores = logits[:, 0]
        else:
            raw_scores = logits[:, -1]
        scores = torch.sigmoid(raw_scores).tolist()
        return [float(score) for score in scores]


class _LlmJsonReranker:
    def __init__(self) -> None:
        self._client = LlmClient(timeout_seconds=120)

    @property
    def available(self) -> bool:
        return bool(self._client._api_key)

    def rerank(
        self,
        *,
        query: str,
        profile: str,
        candidates: list[RerankCandidate],
    ) -> list[dict[str, object]]:
        payload = self._client.complete_json(
            prompt_name="rerank_judge",
            variables={
                "system_prompt": _llm_system_prompt(profile),
                "query": query,
                "profile": profile,
                "results": [
                    {
                        "id": candidate.id,
                        "title": candidate.title,
                        "snippet": candidate.text,
                        "metadata": candidate.metadata,
                    }
                    for candidate in candidates
                ],
            },
        )
        ranked_results = payload.get("ranked_results")
        if not isinstance(ranked_results, list):
            raise ValueError("rerank_judge response missing ranked_results")

        normalized_results: list[dict[str, object]] = []
        for item in ranked_results:
            if not isinstance(item, dict):
                continue
            candidate_id = str(item.get("id", "")).strip()
            if not candidate_id:
                continue
            normalized_results.append(
                {
                    "id": candidate_id,
                    "score": max(0.0, min(1.0, float(item.get("score") or 0.0))),
                    "reason": str(item.get("reason") or "gpt4o_reranker"),
                }
            )
        if not normalized_results:
            raise ValueError("rerank_judge returned no usable results")
        return normalized_results


class RelevanceReranker:
    def __init__(
        self,
        *,
        model_dir: str | Path | None = None,
        model_name: str | None = None,
        model_enabled: bool | None = None,
    ) -> None:
        explicit_model_name = model_name or os.getenv(MODEL_NAME_ENV)
        resolved_enabled = (
            model_enabled
            if model_enabled is not None
            else os.getenv(MODEL_ENABLED_ENV, "1") != "0"
        )
        self._backend_preference = os.getenv(BACKEND_ENV, "llm").strip().lower() or "llm"
        resolved_model_name = explicit_model_name or DEFAULT_RERANK_MODEL_NAME
        resolved_model_dir = model_dir or os.getenv(MODEL_DIR_ENV)
        self._model_enabled = bool(
            resolved_enabled and (resolved_model_dir is not None or explicit_model_name)
        )
        self._llm_enabled = bool(resolved_enabled)
        self._llm = _LlmJsonReranker()
        self._model = _LazySequenceReranker(
            model_dir=resolved_model_dir,
            model_name=resolved_model_name,
        )

    @property
    def backend_name(self) -> str:
        if self._backend_preference == "llm" and self._llm_enabled and self._llm.available:
            return "gpt4o_reranker"
        if self._model_enabled and self._model.available:
            return "transformers_reranker"
        return "lexical_fallback"

    def rerank(
        self,
        *,
        query: str,
        profile: str,
        candidates: list[RerankCandidate],
        top_n: int | None = None,
    ) -> list[RerankScore]:
        normalized_query = query.strip()
        if not normalized_query or not candidates:
            return []

        lexical_scores = [
            self._lexical_score(normalized_query, candidate)
            for candidate in candidates
        ]

        llm_scores: dict[str, dict[str, object]] | None = None
        if self._backend_preference == "llm" and self._llm_enabled and self._llm.available:
            try:
                llm_ranked = self._llm.rerank(
                    query=normalized_query,
                    profile=profile,
                    candidates=candidates,
                )
                llm_scores = {
                    str(item["id"]): item
                    for item in llm_ranked
                }
            except Exception as exc:
                logger.warning("llm rerank failed (%s); falling back", exc)

        model_scores: list[float] | None = None
        if llm_scores is None and self._model_enabled:
            try:
                model_scores = self._model.score_pairs(
                    normalized_query,
                    [self._compose_text(candidate) for candidate in candidates],
                )
            except Exception:
                model_scores = None

        results: list[RerankScore] = []
        for index, candidate in enumerate(candidates):
            lexical_score = lexical_scores[index]
            if llm_scores is not None:
                score_entry = llm_scores.get(candidate.id)
                final_score = float(score_entry["score"]) if score_entry is not None else lexical_score
                reason = str(score_entry["reason"]) if score_entry is not None else "gpt4o_reranker_missing_id"
            elif model_scores is None:
                final_score = lexical_score
                reason = "lexical_fallback"
            else:
                final_score = min(1.0, (0.2 * lexical_score) + (0.8 * model_scores[index]))
                reason = "transformers_reranker"

            results.append(
                RerankScore(
                    id=candidate.id,
                    score=final_score,
                    keep=final_score >= self._threshold_for(profile),
                    reason=reason,
                )
            )

        results.sort(key=lambda item: item.score, reverse=True)
        if top_n is not None:
            results = results[:top_n]
        return results

    def _lexical_score(self, query: str, candidate: RerankCandidate) -> float:
        query_ngrams = _extract_ngrams(query)
        if not query_ngrams:
            return 0.0

        candidate_title = candidate.title.strip()
        candidate_text = self._compose_text(candidate)
        title_ngrams = _extract_ngrams(candidate_title)
        body_ngrams = _extract_ngrams(candidate_text)
        combined = title_ngrams | body_ngrams
        overlap_score = len(query_ngrams & combined) / len(query_ngrams)

        anchors = _extract_primary_anchors(query)
        anchor_hits = [anchor for anchor in anchors if anchor and anchor in candidate_text]
        anchor_score = (len(anchor_hits) / len(anchors)) if anchors else overlap_score

        title_overlap = len(query_ngrams & title_ngrams) / len(query_ngrams) if title_ngrams else 0.0
        return min(1.0, (0.45 * overlap_score) + (0.40 * anchor_score) + (0.15 * title_overlap))

    @staticmethod
    def _compose_text(candidate: RerankCandidate) -> str:
        return " ".join(part for part in (candidate.title.strip(), candidate.text.strip()) if part).strip()

    @staticmethod
    def _threshold_for(profile: str) -> float:
        if profile == "external_news":
            return 0.18
        return 0.12


_DEFAULT_RERANKER: RelevanceReranker | None = None


def build_default_reranker() -> RelevanceReranker:
    global _DEFAULT_RERANKER
    if _DEFAULT_RERANKER is None:
        _DEFAULT_RERANKER = RelevanceReranker()
    return _DEFAULT_RERANKER


def _llm_system_prompt(profile: str) -> str:
    profile_hint = (
        "候选是外部新闻标题和摘要。"
        if profile == "external_news"
        else "候选是内部RAG检索片段。"
    )
    return (
        "你是一个中文金融检索重排评测器。\n\n"
        f"{profile_hint}\n\n"
        "你的任务：\n"
        "1. 读取用户给出的 query 和候选 results。\n"
        "2. 判断每条 result 是否真正贴合 query。\n"
        "3. 对候选按相关性从高到低排序。\n\n"
        "强规则：\n"
        "- 只根据候选标题、摘要和元数据判断，不要假设你看过正文。\n"
        "- 必须严格区分“同一主题”和“共享泛词但不同产业/对象”的结果。\n"
        "- 明显广告、导流、软件下载、开户、股吧灌水、教程页应大幅降权。\n"
        "- 如果 query 是某个行业、事件、公司或公告，不能因为共享一个泛词就把别的行业或对象排前面。\n"
        "- 重点关注题材一致性、对象一致性、问题类型一致性。\n"
        "- 对明显串题或广告内容，score 应接近 0。\n"
        "- 对直接回答 query 主体的内容，score 应明显高于弱相关内容，不要把所有候选打成接近分数。\n"
        "- reason 必须使用中文。\n\n"
        "输出要求：\n"
        "- 只返回一个 JSON 对象。\n"
        "- 必须覆盖所有候选 id。\n"
        "- 格式必须是："
        "{\"ranked_results\":[{\"id\":\"候选ID\",\"score\":0.0,\"label\":\"high|medium|low|reject\",\"reason\":\"一句中文理由\"}],\"summary\":\"一句中文总结\"}\n"
        "- score 范围 0 到 1，按从高到低排序。"
    )


def _extract_primary_anchors(query: str) -> list[str]:
    normalized = _normalize_text(query)
    if not normalized:
        return []

    segment = normalized
    for marker in _SPLIT_MARKERS:
        position = segment.find(marker)
        if position > 0:
            segment = segment[:position]
            break

    compact = re.sub(r"[^\u4e00-\u9fffa-z0-9]", "", segment)
    for term in _COMMON_QUERY_TERMS:
        compact = compact.replace(term, "")
    compact = compact.strip()
    if len(compact) < 2:
        return []

    anchors: list[str] = []
    for size in range(min(4, len(compact)), 1, -1):
        candidate = compact[:size]
        if candidate and candidate not in anchors:
            anchors.append(candidate)
    if compact not in anchors and len(compact) <= 8:
        anchors.append(compact)
    return anchors


def _extract_ngrams(text: str) -> set[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return set()

    grams: set[str] = set()
    for token in re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", normalized):
        if token in _COMMON_QUERY_TERMS:
            continue
        if re.fullmatch(r"[a-z0-9]+", token):
            if len(token) >= 2:
                grams.add(token)
            continue
        limited = token[:12]
        for size in range(2, min(4, len(limited)) + 1):
            for index in range(0, len(limited) - size + 1):
                grams.add(limited[index : index + size])
    return grams


def _normalize_text(text: str) -> str:
    normalized = text.lower()
    normalized = normalized.replace("a股", "a股")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()
