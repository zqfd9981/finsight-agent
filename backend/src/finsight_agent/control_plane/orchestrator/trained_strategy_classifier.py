from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Mapping

from .retrieval_strategy_classifier import (
    DEFAULT_RETRIEVAL_STRATEGY,
    RETRIEVAL_STRATEGIES,
    RetrievalStrategyClassifier,
    StubRetrievalStrategyClassifier,
)

logger = logging.getLogger(__name__)

DEFAULT_RUNTIME_MODEL_SUBDIR = "var/models/retrieval_strategy_classifier/v1"
ENV_VAR = "RETRIEVAL_STRATEGY_MODEL_DIR"
INFERENCE_TIMEOUT_SECONDS = 0.5
DEFAULT_MARGIN_HIGH = 0.40
DEFAULT_MARGIN_LOW = 0.15

_SERIALIZATION_TEMPLATE_KEYS = ("query",)


def _resolve_model_dir(model_dir: str | Path | None) -> Path:
    """Resolve the runtime model directory."""
    if model_dir is not None:
        return Path(model_dir)
    override = os.environ.get(ENV_VAR)
    if override:
        return Path(override)
    repo_root = Path(__file__).resolve().parents[5]
    return repo_root / DEFAULT_RUNTIME_MODEL_SUBDIR


class _LazyTransformer:
    """Lazy transformer loader to keep import costs off the hot path."""

    @classmethod
    def from_pretrained(cls, model_dir: str | Path):  # pragma: no cover
        from transformers import AutoModelForSequenceClassification, AutoTokenizer  # type: ignore

        tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
        model = AutoModelForSequenceClassification.from_pretrained(str(model_dir))
        return tokenizer, model


def _build_serialized_text(
    *,
    query: str,
) -> str:
    """Serialize query-only classifier input."""
    return f"[QUERY] {query}"


def _map_margin_to_confidence(
    margin: float, *, margin_high: float, margin_low: float
) -> str:
    if margin >= margin_high:
        return "high"
    if margin >= margin_low:
        return "medium"
    return "low"


class TrainedRetrievalStrategyClassifier:
    """Runtime classifier with lazy model loading and stub fallback."""

    def __init__(
        self,
        *,
        model_dir: str | Path | None = None,
        confidence_margin_high: float = DEFAULT_MARGIN_HIGH,
        confidence_margin_low: float = DEFAULT_MARGIN_LOW,
        fallback: RetrievalStrategyClassifier | None = None,
    ) -> None:
        self._model_dir = _resolve_model_dir(model_dir)
        self._confidence_margin_high = float(confidence_margin_high)
        self._confidence_margin_low = float(confidence_margin_low)
        self._fallback: RetrievalStrategyClassifier = (
            fallback if fallback is not None else StubRetrievalStrategyClassifier()
        )
        self._tokenizer: Any | None = None
        self._model: Any | None = None
        self._index_to_label: dict[int, str] | None = None
        self._degraded: bool = False
        self._model_loaded: bool = False

    @property
    def _is_degraded(self) -> bool:
        return self._degraded

    def _ensure_loaded(self) -> None:
        if self._model_loaded:
            return
        self._model_loaded = True

        if not self._model_dir.is_dir():
            logger.warning(
                "strategy classifier model dir missing: %s — falling back to stub",
                self._model_dir,
            )
            self._degraded = True
            return

        try:
            tokenizer, model = _LazyTransformer.from_pretrained(self._model_dir)
        except Exception as exc:
            logger.warning(
                "strategy classifier model load failed (%s) — falling back to stub",
                exc,
            )
            self._degraded = True
            return

        labels_path = self._model_dir / "labels.json"
        if labels_path.is_file():
            try:
                payload = json.loads(labels_path.read_text(encoding="utf-8"))
                self._index_to_label = {int(k): str(v) for k, v in payload.items()}
            except Exception as exc:
                logger.warning("labels.json unreadable (%s) — falling back to stub", exc)
                self._degraded = True
                return
        else:
            self._index_to_label = {
                0: "event_primary",
                1: "disclosure_primary",
                2: "dual_primary",
            }

        if set(self._index_to_label.values()) != set(RETRIEVAL_STRATEGIES):
            logger.warning(
                "labels.json does not match RETRIEVAL_STRATEGIES — falling back to stub"
            )
            self._degraded = True
            return

        self._tokenizer = tokenizer
        self._model = model
        try:
            self._model.eval()
        except Exception:  # pragma: no cover
            pass

    def _build_input(
        self,
        *,
        query: str,
        router_payload: Mapping[str, object],
        session_topic: str,
    ) -> str:
        del router_payload, session_topic
        return _build_serialized_text(query=query)

    def _fallback_payload(self) -> dict[str, str]:
        try:
            return self._fallback.classify(
                query="", router_payload={}, session_topic=""
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("fallback classifier itself failed (%s)", exc)
            return {
                "strategy": DEFAULT_RETRIEVAL_STRATEGY,
                "confidence": "low",
                "reason": "stub_fallback",
            }

    def classify(
        self,
        *,
        query: str,
        router_payload: dict[str, object],
        session_topic: str,
    ) -> dict[str, str]:
        try:
            self._ensure_loaded()
        except Exception as exc:
            logger.warning("ensure_loaded unexpectedly raised (%s) — falling back", exc)
            return self._fallback_payload()

        if self._degraded:
            return self._fallback_payload()

        try:
            import torch  # type: ignore
        except ImportError:
            logger.warning("torch not installed — falling back to stub")
            self._degraded = True
            return self._fallback_payload()

        try:
            text = self._build_input(
                query=query,
                router_payload=router_payload,
                session_topic=session_topic,
            )
            inputs = self._tokenizer(
                text,
                truncation=True,
                max_length=128,
                return_tensors="pt",
            )
            with torch.no_grad():
                logits = self._model(**inputs).logits
            probs = torch.softmax(logits, dim=-1)[0]
            sorted_probs, sorted_idxs = torch.sort(probs, descending=True)
            top1_idx = int(sorted_idxs[0].item())
            top1_prob = float(sorted_probs[0].item())
            top2_prob = float(sorted_probs[1].item()) if len(sorted_probs) > 1 else 0.0
            margin = top1_prob - top2_prob
        except Exception as exc:
            logger.warning("inference failed (%s) — falling back to stub", exc)
            self._degraded = True
            return self._fallback_payload()

        index_to_label = self._index_to_label or {
            0: "event_primary",
            1: "disclosure_primary",
            2: "dual_primary",
        }
        label = index_to_label.get(top1_idx, DEFAULT_RETRIEVAL_STRATEGY)
        if label not in RETRIEVAL_STRATEGIES:
            logger.warning("model returned unknown label %s — falling back", label)
            return self._fallback_payload()

        confidence = _map_margin_to_confidence(
            margin,
            margin_high=self._confidence_margin_high,
            margin_low=self._confidence_margin_low,
        )
        top1_label = index_to_label.get(int(sorted_idxs[0].item()), "?")
        top2_label = (
            index_to_label.get(int(sorted_idxs[1].item()), "?")
            if len(sorted_idxs) > 1
            else "?"
        )
        reason = f"structbert:margin={margin:.3f};top1={top1_label};top2={top2_label}"
        return {
            "strategy": label,
            "confidence": confidence,
            "reason": reason,
        }
