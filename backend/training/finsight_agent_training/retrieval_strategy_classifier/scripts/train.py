"""微调 StructBERT 中文 base 为三分类检索策略分类器。

训练流程（CPU 30 分钟内跑完 5 epoch）：
1. 读固化切分 ``data/splits/{train,val}.jsonl``
2. 用 ``build_input_text`` 模板 + StructBERT tokenizer 编码
3. ``AutoModelForSequenceClassification`` 微调，含 warmup + linear schedule
4. val accuracy 连续 2 epoch 不升 → 早停，回滚到最优 checkpoint
5. 写入 ``artifacts/classifier_v1/``：模型权重 + tokenizer + labels.json + training_meta.json
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

# 支持 ``python train.py`` 和 ``python -m ...scripts.train`` 两种入口：
# 在 __main__ 模式下相对 import 不可用，需把 package 父目录加到 sys.path
if __package__ in (None, ""):
    _HERE = Path(__file__).resolve()
    # scripts/train.py -> .../finsight_agent_training/retrieval_strategy_classifier/scripts/
    # parents[0]=scripts, [1]=retrieval_strategy_classifier, [2]=finsight_agent_training,
    # [3]=training  ← package parent，要加到 sys.path
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

DEFAULT_ARTIFACTS_SUBDIR = (
    "backend/training/finsight_agent_training/retrieval_strategy_classifier/"
    "artifacts/classifier_v1"
)
DEFAULT_MAX_LENGTH = 128
DEFAULT_EPOCHS = 5
DEFAULT_BATCH_SIZE = 16
DEFAULT_LEARNING_RATE = 2e-5
DEFAULT_WARMUP_RATIO = 0.1
DEFAULT_WEIGHT_DECAY = 0.01
DEFAULT_SEED = 42
EARLY_STOP_PATIENCE = 2


@dataclass(slots=True)
class TrainingArtifacts:
    model_dir: Path
    meta: dict[str, Any]


def _load_split_rows(split_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with split_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _encode_example(row: dict[str, Any], tokenizer: Any, max_length: int) -> dict[str, Any]:
    text = build_input_text(
        query=str(row.get("query", "")),
        intent=str(row.get("intent", "")),
        event=str(row.get("event", "") or ""),
        themes=list(row.get("themes", []) or []),
        target=str(row.get("target", "") or ""),
        time_scope=str(row.get("time_scope", "") or ""),
        session_topic=str(row.get("session_topic", "") or ""),
    )
    encoded = tokenizer(
        text,
        truncation=True,
        max_length=max_length,
        padding="max_length",
        return_tensors="pt",
    )
    label = LABEL_TO_INDEX[str(row["label"])]
    return {
        "input_ids": encoded["input_ids"][0],
        "attention_mask": encoded["attention_mask"][0],
        "labels": label,
    }


def save_training_meta(
    *,
    out_dir: Path,
    params: dict[str, Any],
    metrics: dict[str, Any],
    git_commit: str,
) -> Path:
    """把训练参数 + val 指标 + 时间戳 + commit 写到 ``out_dir/training_meta.json``。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        **params,
        **metrics,
        "git_commit": git_commit,
        "trained_at": datetime.now(tz=timezone.utc).isoformat(),
        # JSON keys 必须是字符串；这是与运行时 ``labels.json`` 一致的约定
        "labels": {str(idx): label for idx, label in INDEX_TO_LABEL.items()},
    }
    out_path = out_dir / "training_meta.json"
    out_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def _current_git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return ""


def _evaluate(model: Any, loader: Any, device: Any) -> tuple[int, int]:
    """val accuracy 评估。返回 (correct, total)。"""
    model.eval()
    correct = 0
    total = 0
    # 本地导入 torch，避免冷启动开销
    with __import__("torch").no_grad():
        for batch in loader:
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["labels"].to(device)
            logits = model(input_ids=input_ids, attention_mask=attention_mask).logits
            preds = __import__("torch").argmax(logits, dim=-1)
            correct += int((preds == labels).sum())
            total += int(labels.size(0))
    return correct, total


def train(
    *,
    pretrained_dir: Path,
    splits_dir: Path,
    artifacts_dir: Path,
    epochs: int = DEFAULT_EPOCHS,
    batch_size: int = DEFAULT_BATCH_SIZE,
    learning_rate: float = DEFAULT_LEARNING_RATE,
    warmup_ratio: float = DEFAULT_WARMUP_RATIO,
    weight_decay: float = DEFAULT_WEIGHT_DECAY,
    seed: int = DEFAULT_SEED,
    max_length: int = DEFAULT_MAX_LENGTH,
) -> TrainingArtifacts:
    """离线微调 StructBERT 三分类，产出 ``artifacts_dir``。"""
    try:
        import torch  # type: ignore
        from torch.utils.data import DataLoader, Dataset  # type: ignore
        from transformers import (  # type: ignore
            AutoModelForSequenceClassification,
            AutoTokenizer,
            get_linear_schedule_with_warmup,
        )
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "transformers + torch required: pip install transformers torch"
        ) from exc

    torch.manual_seed(seed)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    tokenizer = AutoTokenizer.from_pretrained(str(pretrained_dir))
    model = AutoModelForSequenceClassification.from_pretrained(
        str(pretrained_dir),
        num_labels=len(LABEL_TO_INDEX),
    )
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)

    train_rows = _load_split_rows(splits_dir / "train.jsonl")
    val_rows = _load_split_rows(splits_dir / "val.jsonl")
    if not train_rows:
        raise RuntimeError(f"empty train split at {splits_dir / 'train.jsonl'}")
    if not val_rows:
        raise RuntimeError(f"empty val split at {splits_dir / 'val.jsonl'}")

    class _TrainDataset(Dataset):
        def __len__(self) -> int:
            return len(train_rows)

        def __getitem__(self, idx: int) -> dict[str, Any]:
            return _encode_example(train_rows[idx], tokenizer, max_length)

    class _ValDataset(Dataset):
        def __init__(self) -> None:
            self._rows = val_rows
            self._encoded = [_encode_example(row, tokenizer, max_length) for row in val_rows]

        def __len__(self) -> int:
            return len(self._encoded)

        def __getitem__(self, idx: int) -> dict[str, Any]:
            return self._encoded[idx]

    train_loader = DataLoader(_TrainDataset(), batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(_ValDataset(), batch_size=batch_size)

    optim = torch.optim.AdamW(
        model.parameters(), lr=learning_rate, weight_decay=weight_decay
    )
    total_steps = max(1, len(train_loader) * epochs)
    scheduler = get_linear_schedule_with_warmup(
        optim,
        num_warmup_steps=int(total_steps * warmup_ratio),
        num_training_steps=total_steps,
    )

    best_val_acc = -1.0
    best_epoch = -1
    patience = 0
    best_metrics: dict[str, Any] = {}

    for epoch in range(epochs):
        model.train()
        train_loss = 0.0
        for batch in train_loader:
            optim.zero_grad()
            outputs = model(
                input_ids=batch["input_ids"].to(device),
                attention_mask=batch["attention_mask"].to(device),
                labels=batch["labels"].to(device),
            )
            outputs.loss.backward()
            optim.step()
            scheduler.step()
            train_loss += float(outputs.loss.detach())

        correct, total = _evaluate(model, val_loader, device)
        val_acc = correct / total if total else 0.0
        train_loss /= max(1, len(train_loader))
        print(
            f"epoch {epoch + 1}/{epochs} train_loss={train_loss:.4f} "
            f"val_acc={val_acc:.4f}"
        )

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            best_epoch = epoch + 1
            patience = 0
            model.save_pretrained(str(artifacts_dir))
            tokenizer.save_pretrained(str(artifacts_dir))
            (artifacts_dir / "labels.json").write_text(
                json.dumps(INDEX_TO_LABEL, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            best_metrics = {"val_accuracy": val_acc, "epoch": epoch + 1}
        else:
            patience += 1
            if patience >= EARLY_STOP_PATIENCE:
                print("early stopping triggered")
                break

    if best_epoch < 0:
        raise RuntimeError("training produced no usable checkpoint")

    # 简单 macro F1 from val predictions
    # (在 best checkpoint 上重跑一次 val)
    # 注意：上面 _evaluate 只回 (correct, total)，避免在训练循环里算 F1 拖慢速度
    best_metrics["val_macro_f1"] = _compute_val_macro_f1(
        model, val_loader, device, len(LABEL_TO_INDEX)
    )

    meta_path = save_training_meta(
        out_dir=artifacts_dir,
        params={
            "epochs": epochs,
            "batch_size": batch_size,
            "lr": learning_rate,
            "warmup_ratio": warmup_ratio,
            "weight_decay": weight_decay,
            "seed": seed,
            "max_length": max_length,
            "device": str(device),
        },
        metrics=best_metrics,
        git_commit=_current_git_commit(),
    )

    return TrainingArtifacts(
        model_dir=artifacts_dir,
        meta=json.loads(meta_path.read_text(encoding="utf-8")),
    )


def _compute_val_macro_f1(model: Any, loader: Any, device: Any, n_labels: int) -> float:
    """在给定 loader 上跑一次推理，算 macro F1。"""
    import torch  # type: ignore

    model.eval()
    confusion = [[0 for _ in range(n_labels)] for _ in range(n_labels)]
    with torch.no_grad():
        for batch in loader:
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["labels"].to(device)
            logits = model(input_ids=input_ids, attention_mask=attention_mask).logits
            preds = torch.argmax(logits, dim=-1)
            for t, p in zip(labels.tolist(), preds.tolist()):
                confusion[t][p] += 1

    f1s: list[float] = []
    for i in range(n_labels):
        tp = confusion[i][i]
        fp = sum(confusion[r][i] for r in range(n_labels)) - tp
        fn = sum(confusion[i][c] for c in range(n_labels)) - tp
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        f1s.append(f1)
    return sum(f1s) / len(f1s) if f1s else 0.0


if __name__ == "__main__":
    import argparse

    # scripts/train.py -> .../finsight_agent_training/retrieval_strategy_classifier/scripts/
    # parents[0]=scripts, [1]=retrieval_strategy_classifier, [2]=finsight_agent_training,
    # [3]=training, [4]=backend, [5]=repo_root
    repo_root = Path(__file__).resolve().parents[5]
    parser = argparse.ArgumentParser(description="微调 StructBERT 检索策略分类器")
    parser.add_argument(
        "--pretrained-dir",
        default=str(repo_root / "var" / "models" / "pretrained" / "structbert-base-zh"),
    )
    parser.add_argument(
        "--splits-dir",
        default=str(
            repo_root
            / "backend"
            / "training"
            / "finsight_agent_training"
            / "retrieval_strategy_classifier"
            / "data"
            / "splits"
        ),
    )
    parser.add_argument("--artifacts-dir", default=str(repo_root / DEFAULT_ARTIFACTS_SUBDIR))
    parser.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--learning-rate", type=float, default=DEFAULT_LEARNING_RATE)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    result = train(
        pretrained_dir=Path(args.pretrained_dir),
        splits_dir=Path(args.splits_dir),
        artifacts_dir=Path(args.artifacts_dir),
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        seed=args.seed,
    )
    print(f"training complete -> {result.model_dir}")
