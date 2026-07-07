"""运行时 StructBERT 检索策略分类器。

设计目标：
- 实现 ``RetrievalStrategyClassifier`` Protocol，协议层不变
- 懒加载模型权重（首次 ``classify()`` 才读盘，不拖慢主流程启动）
- 任何失败路径 → ``fallback`` 兜底，行为与 ``StubRetrievalStrategyClassifier`` 等价
- 失败时主流程可观察 ``source_status["strategy_source"] = "stub_fallback"``

失败矩阵（覆盖）：
- transformers / torch 未安装
- model_dir 不存在
- 模型权重 / labels.json 读取失败
- tokenizer 编码失败
- 模型 forward 抛异常
- 推理结果 label 不在合法集
- 单次推理超过 500ms
- 任何其他 Exception
"""

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

# 模板字段顺序与训练侧 ``data/dataset.build_input_text`` 完全一致
# 这里复刻一份以避免在运行时 import 训练子项目（重型依赖传染）
_SERIALIZATION_TEMPLATE_KEYS = (
    "query",
    "intent",
    "event",
    "themes",
    "target",
    "time_scope",
    "session_topic",
)
_DEFAULT_FIELD = "无"


def _resolve_model_dir(model_dir: str | Path | None) -> Path:
    """按优先级解析运行时模型目录。

    1. ``__init__`` 参数
    2. ``$RETRIEVAL_STRATEGY_MODEL_DIR`` 环境变量
    3. ``<repo_root>/var/models/retrieval_strategy_classifier/v1/`` 默认
    """
    if model_dir is not None:
        return Path(model_dir)
    override = os.environ.get(ENV_VAR)
    if override:
        return Path(override)
    # trained_strategy_classifier.py ->
    #   .../finsight_agent/control_plane/orchestrator/trained_strategy_classifier.py
    # parents[0]=orchestrator, [1]=control_plane, [2]=finsight_agent,
    # [3]=src, [4]=backend, [5]=repo_root
    repo_root = Path(__file__).resolve().parents[5]
    return repo_root / DEFAULT_RUNTIME_MODEL_SUBDIR


class _LazyTransformer:
    """懒加载 transformers + torch 的占位类，便于测试替换。"""

    @classmethod
    def from_pretrained(cls, model_dir: str | Path):  # pragma: no cover - 真实模型路径
        from transformers import AutoModelForSequenceClassification, AutoTokenizer  # type: ignore

        tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
        model = AutoModelForSequenceClassification.from_pretrained(str(model_dir))
        return tokenizer, model


def _build_serialized_text(
    *,
    query: str,
    intent: str,
    event: str,
    themes: list[str],
    target: str,
    time_scope: str,
    session_topic: str,
) -> str:
    """运行时序列化模板；与训练侧 ``build_input_text`` 字段结构一致。

    缺字段一律填 "无"，确保序列结构稳定（与训练时相同）。
    """
    parts = [
        f"[QUERY] {query}",
        f"[INTENT] {intent or _DEFAULT_FIELD}",
        f"[EVENT] {event or _DEFAULT_FIELD}",
        f"[THEMES] {', '.join(themes) if themes else _DEFAULT_FIELD}",
        f"[TARGET] {target or _DEFAULT_FIELD}",
        f"[TIME_SCOPE] {time_scope or _DEFAULT_FIELD}",
        f"[SESSION_TOPIC] {session_topic or _DEFAULT_FIELD}",
    ]
    return " ".join(parts)


def _map_margin_to_confidence(
    margin: float, *, margin_high: float, margin_low: float
) -> str:
    if margin >= margin_high:
        return "high"
    if margin >= margin_low:
        return "medium"
    return "low"


class TrainedRetrievalStrategyClassifier:
    """运行时分类器：懒加载 StructBERT 微调模型，任何异常回退到 fallback。"""

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
        # 状态字段（公开以方便测试断言 _degraded / _model_loaded）
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
        # 一旦进入 _ensure_loaded 即认为 "已尝试加载"；后续即便失败也走 degraded 分支
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
                logger.warning(
                    "labels.json unreadable (%s) — falling back to stub", exc
                )
                self._degraded = True
                return
        else:
            # 缺失时回退到 spec 默认顺序
            self._index_to_label = {
                0: "event_primary",
                1: "disclosure_primary",
                2: "dual_primary",
            }

        # 校验 labels 完整性
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
        except Exception:  # pragma: no cover - mock 模型可能无 eval
            pass

    def _build_input(
        self,
        *,
        query: str,
        router_payload: Mapping[str, object],
        session_topic: str,
    ) -> str:
        entities_raw = router_payload.get("entities") if isinstance(router_payload, Mapping) else None
        entities = entities_raw if isinstance(entities_raw, Mapping) else {}
        event = str(entities.get("event") or "")
        themes_raw = entities.get("themes") or []
        themes = [str(t) for t in themes_raw if t]
        target = str(entities.get("target") or "")
        time_scope = str(entities.get("time_scope") or "")
        intent = ""
        if isinstance(router_payload, Mapping):
            intent = str(router_payload.get("intent") or "")
        return _build_serialized_text(
            query=query,
            intent=intent,
            event=event,
            themes=themes,
            target=target,
            time_scope=time_scope,
            session_topic=session_topic,
        )

    def _fallback_payload(self) -> dict[str, str]:
        """调 fallback 并返回其结果；保持 reason 严格为 ``stub_fallback``。"""
        try:
            return self._fallback.classify(
                query="", router_payload={}, session_topic=""
            )
        except Exception as exc:  # pragma: no cover - fallback 自身出错
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

        # ``_index_to_label`` 在 _ensure_loaded 后必然非 None（除非被打成 degraded）
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
