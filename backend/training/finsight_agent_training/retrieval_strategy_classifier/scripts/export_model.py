"""把训练产物拷贝到运行时加载路径。

默认源：``backend/training/finsight_agent_training/retrieval_strategy_classifier/artifacts/classifier_v1``
默认目标：``<repo_root>/var/models/retrieval_strategy_classifier/v1/``

目标目录已 ``.gitignore`` 排除；运行时类 ``TrainedRetrievalStrategyClassifier`` 通过
``RETRIEVAL_STRATEGY_MODEL_DIR`` 环境变量或默认路径加载。
"""

from __future__ import annotations

import shutil
from pathlib import Path

DEFAULT_ARTIFACTS_SUBDIR = (
    "backend/training/finsight_agent_training/retrieval_strategy_classifier/"
    "artifacts/classifier_v1"
)
DEFAULT_TARGET_SUBDIR = "var/models/retrieval_strategy_classifier/v1"


def export_model(*, artifacts_dir: Path, target_dir: Path) -> Path:
    """把训练产物拷贝到运行时加载路径。"""
    if not artifacts_dir.is_dir():
        raise FileNotFoundError(f"artifacts dir not found: {artifacts_dir}")
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(artifacts_dir, target_dir)
    return target_dir


if __name__ == "__main__":
    # scripts/export_model.py -> parents[5]=repo_root
    repo_root = Path(__file__).resolve().parents[5]
    artifacts = repo_root / DEFAULT_ARTIFACTS_SUBDIR
    target = repo_root / DEFAULT_TARGET_SUBDIR
    out = export_model(artifacts_dir=artifacts, target_dir=target)
    print(f"exported to {out}")
