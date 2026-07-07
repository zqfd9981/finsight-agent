"""从 HuggingFace 拉取 StructBERT 中文 base 预训练模型到本地缓存目录。

训练和离线评测只读本地缓存；CI / 本地首次训练前需要先跑这个脚本。
所有产物（``*.bin``、``tokenizer.json``、``var/models/``）都已 ``.gitignore`` 排除。
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_MODEL_NAME = "alibaba-pai/structbert-base-zh"
FALLBACK_MODEL_NAME = "hfl/chinese-roberta-wwm-ext"
ENV_VAR = "STRUCTBERT_PRETRAINED_DIR"


def resolve_pretrained_dir(*, env_var: str = ENV_VAR) -> Path:
    """解析预训练模型本地缓存目录。

    优先级:
      1. ``$STRUCTBERT_PRETRAINED_DIR`` 环境变量
      2. ``<repo_root>/var/models/pretrained/structbert-base-zh`` 默认路径
    """
    override = os.environ.get(env_var)
    if override:
        return Path(override)
    # scripts/download_pretrained.py -> .../finsight_agent_training/retrieval_strategy_classifier/scripts/
    # parents[0]=scripts, [1]=retrieval_strategy_classifier, [2]=finsight_agent_training,
    # [3]=training, [4]=backend, [5]=repo_root
    repo_root = Path(__file__).resolve().parents[5]
    return repo_root / "var" / "models" / "pretrained" / "structbert-base-zh"


def _is_fully_downloaded(target: Path) -> bool:
    """粗粒度判断目录里至少存在 config.json + 权重文件 + tokenizer 文件。"""
    if not target.is_dir():
        return False
    has_config = (target / "config.json").is_file()
    has_weights = (target / "pytorch_model.bin").is_file() or any(
        target.glob("model.safetensors")
    )
    has_tokenizer = (target / "tokenizer.json").is_file() or (target / "vocab.txt").is_file()
    return has_config and has_weights and has_tokenizer


def download_pretrained(
    *,
    model_name: str = DEFAULT_MODEL_NAME,
    target_dir: Path | None = None,
    allow_fallback: bool = True,
) -> Path:
    """从 HuggingFace 下载预训练模型到本地目录。

    仅在首次训练或预训练模型缺失时调用；产物已被 ``.gitignore`` 排除。

    - ``model_name`` 优先尝试 StructBERT；若 HF 上不可达且 ``allow_fallback=True``，
      退回到 ``hfl/chinese-roberta-wwm-ext``（中文 wwm 替代方案）。
    - 目标目录已存在且完整时，跳过下载。
    """
    target = target_dir or resolve_pretrained_dir()
    target.mkdir(parents=True, exist_ok=True)

    if _is_fully_downloaded(target):
        return target

    try:
        from transformers import AutoModel, AutoTokenizer  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "transformers is required for download_pretrained; "
            "pip install transformers torch"
        ) from exc

    last_exc: Exception | None = None
    candidates = [model_name]
    if allow_fallback and model_name == DEFAULT_MODEL_NAME:
        candidates.append(FALLBACK_MODEL_NAME)

    for candidate_name in candidates:
        try:
            tokenizer = AutoTokenizer.from_pretrained(candidate_name)
            model = AutoModel.from_pretrained(candidate_name)
            tokenizer.save_pretrained(target)
            model.save_pretrained(target)
            return target
        except Exception as exc:  # pragma: no cover - 网络/HF 异常路径
            last_exc = exc
            continue

    raise RuntimeError(
        f"failed to download pretrained model: tried {candidates}; last error: {last_exc}"
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="下载 StructBERT 中文 base 到本地")
    parser.add_argument("--model-name", default=DEFAULT_MODEL_NAME)
    parser.add_argument("--target-dir", default=None)
    parser.add_argument(
        "--no-fallback",
        action="store_true",
        help="不允许回退到 hfl/chinese-roberta-wwm-ext",
    )
    args = parser.parse_args()

    target = Path(args.target_dir) if args.target_dir else None
    out = download_pretrained(
        model_name=args.model_name,
        target_dir=target,
        allow_fallback=not args.no_fallback,
    )
    print(f"downloaded to {out}")
