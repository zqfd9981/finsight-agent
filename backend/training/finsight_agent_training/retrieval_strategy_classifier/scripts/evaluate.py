"""离线评测脚本（CI gate）。

输入：训练产物 ``artifacts_dir`` + 固化 test 集 ``splits_dir/test.jsonl``。
输出：accuracy / per-class precision / recall / F1 / confusion matrix / stub baseline 命中率。
退出码：accuracy ≥ 0.85 且 per-class F1 ≥ 0.80 → 0；否则 1。
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

# 兼容 ``python evaluate.py`` 和 ``python -m ...scripts.evaluate`` 两种入口
if __package__ in (None, ""):
    _HERE = Path(__file__).resolve()
    # scripts/evaluate.py -> parents[0]=scripts, [1]=retrieval_strategy_classifier,
    # [2]=finsight_agent_training, [3]=training  ← package parent
    _PKG_PARENT = _HERE.parents[3]
    if str(_PKG_PARENT) not in sys.path:
        sys.path.insert(0, str(_PKG_PARENT))
    from finsight_agent_training.retrieval_strategy_classifier.data.dataset import (  # type: ignore
        INDEX_TO_LABEL,
        LABEL_TO_INDEX,
        build_input_text,
    )
else:
    from ..data.dataset import (  # type: ignore
        INDEX_TO_LABEL,
        LABEL_TO_INDEX,
        build_input_text,
    )

MIN_ACCURACY = 0.85
MIN_PER_CLASS_F1 = 0.80


@dataclass(slots=True)
class EvalMetrics:
    accuracy: float
    per_class_f1: dict[str, float]
    confusion: list[list[int]]
    baseline_match_rate: float


def _load_split(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _predict_labels(
    rows: Iterable[dict[str, Any]],
    *,
    model_dir: Path,
) -> list[int]:
    try:
        import torch  # type: ignore
        from transformers import AutoModelForSequenceClassification, AutoTokenizer  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("transformers + torch required") from exc

    tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
    model = AutoModelForSequenceClassification.from_pretrained(str(model_dir))
    model.eval()

    preds: list[int] = []
    with torch.no_grad():
        for row in rows:
            text = build_input_text(
                query=str(row.get("query", "")),
                intent=str(row.get("intent", "")),
                event=str(row.get("event", "") or ""),
                themes=list(row.get("themes", []) or []),
                target=str(row.get("target", "") or ""),
                time_scope=str(row.get("time_scope", "") or ""),
                session_topic=str(row.get("session_topic", "") or ""),
            )
            inputs = tokenizer(text, truncation=True, max_length=128, return_tensors="pt")
            logits = model(**inputs).logits
            preds.append(int(torch.argmax(logits, dim=-1).item()))
    return preds


def _stub_predict(rows: Iterable[dict[str, Any]]) -> list[int]:
    """Stub baseline 永远预测 event_primary (index 0)。"""
    return [LABEL_TO_INDEX["event_primary"] for _ in rows]


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def _compute_metrics(
    true_idxs: list[int], pred_idxs: list[int]
) -> tuple[float, dict[str, float], list[list[int]]]:
    n_labels = len(LABEL_TO_INDEX)
    confusion = [[0 for _ in range(n_labels)] for _ in range(n_labels)]
    for t, p in zip(true_idxs, pred_idxs):
        confusion[t][p] += 1

    total = len(true_idxs)
    accuracy = _safe_div(
        sum(1 for t, p in zip(true_idxs, pred_idxs) if t == p), total
    )

    per_class_f1: dict[str, float] = {}
    per_class_precision: dict[str, float] = {}
    per_class_recall: dict[str, float] = {}
    for label, idx in LABEL_TO_INDEX.items():
        tp = confusion[idx][idx]
        fp = sum(confusion[r][idx] for r in range(n_labels)) - tp
        fn = sum(confusion[idx][c] for c in range(n_labels)) - tp
        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        per_class_precision[label] = precision
        per_class_recall[label] = recall
        per_class_f1[label] = _safe_div(2 * precision * recall, precision + recall)

    return accuracy, per_class_f1, confusion


def run_evaluation(*, artifacts_dir: Path, splits_dir: Path) -> EvalMetrics:
    test_rows = _load_split(splits_dir / "test.jsonl")
    true_idxs = [LABEL_TO_INDEX[str(row["label"])] for row in test_rows]

    pred_idxs = _predict_labels(test_rows, model_dir=artifacts_dir)
    accuracy, per_class_f1, confusion = _compute_metrics(true_idxs, pred_idxs)

    stub_idxs = _stub_predict(test_rows)
    baseline_match = _safe_div(
        sum(1 for t, p in zip(true_idxs, stub_idxs) if t == p),
        len(true_idxs),
    )

    return EvalMetrics(
        accuracy=accuracy,
        per_class_f1=per_class_f1,
        confusion=confusion,
        baseline_match_rate=baseline_match,
    )


def gate_passes(
    metrics: EvalMetrics | dict,
    *,
    min_accuracy: float = MIN_ACCURACY,
    min_f1: float = MIN_PER_CLASS_F1,
) -> bool:
    if isinstance(metrics, dict):
        accuracy = float(metrics["accuracy"])
        per_class = dict(metrics["per_class_f1"])
    else:
        accuracy = metrics.accuracy
        per_class = metrics.per_class_f1

    if accuracy < min_accuracy:
        return False
    return all(f1 >= min_f1 for f1 in per_class.values())


def _format_report(metrics: EvalMetrics) -> str:
    lines = [
        f"accuracy                 = {metrics.accuracy:.4f}",
        f"baseline (stub) match    = {metrics.baseline_match_rate:.4f}",
        "per-class F1:",
    ]
    for label, f1 in metrics.per_class_f1.items():
        lines.append(f"  {label:20s} {f1:.4f}")
    lines.append("confusion matrix (rows=true, cols=pred):")
    labels = [INDEX_TO_LABEL[i] for i in range(len(INDEX_TO_LABEL))]
    header = f"  {'':20s} " + " ".join(f"{lbl[:10]:>10s}" for lbl in labels)
    lines.append(header)
    for i, row in enumerate(metrics.confusion):
        lines.append(f"  {labels[i]:20s} " + " ".join(f"{v:>10d}" for v in row))
    return "\n".join(lines)


if __name__ == "__main__":
    # scripts/evaluate.py -> .../finsight_agent_training/retrieval_strategy_classifier/scripts/
    # parents[0]=scripts, [1]=retrieval_strategy_classifier, [2]=finsight_agent_training,
    # [3]=training, [4]=backend, [5]=repo_root
    repo_root = Path(__file__).resolve().parents[5]
    artifacts = (
        repo_root
        / "backend"
        / "training"
        / "finsight_agent_training"
        / "retrieval_strategy_classifier"
        / "artifacts"
        / "classifier_v1"
    )
    splits = (
        repo_root
        / "backend"
        / "training"
        / "finsight_agent_training"
        / "retrieval_strategy_classifier"
        / "data"
        / "splits"
    )
    metrics = run_evaluation(artifacts_dir=artifacts, splits_dir=splits)
    print(_format_report(metrics))
    sys.exit(0 if gate_passes(metrics) else 1)
