from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
# training 子项目下要 import finsight_agent_training 这个顶级包，
# 需要把 backend/training 加到 sys.path。
TRAINING_PARENT = REPO_ROOT / "backend" / "training"
for candidate in (REPO_ROOT, TRAINING_PARENT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


class ResolvePretrainedDirTest(unittest.TestCase):
    def test_default_path_under_var_models(self) -> None:
        from finsight_agent_training.retrieval_strategy_classifier.scripts.download_pretrained import (
            resolve_pretrained_dir,
        )

        path = resolve_pretrained_dir()
        expected = REPO_ROOT / "var" / "models" / "pretrained" / "structbert-base-zh"
        self.assertEqual(path, expected)
        self.assertTrue(str(path).startswith(str(REPO_ROOT)))

    def test_env_var_overrides_default(self) -> None:
        import os

        from finsight_agent_training.retrieval_strategy_classifier.scripts.download_pretrained import (
            resolve_pretrained_dir,
        )

        sentinel = str(REPO_ROOT / "var" / "models" / "custom_structbert")
        old_value = os.environ.get("STRUCTBERT_PRETRAINED_DIR")
        try:
            os.environ["STRUCTBERT_PRETRAINED_DIR"] = sentinel
            path = resolve_pretrained_dir()
        finally:
            if old_value is None:
                os.environ.pop("STRUCTBERT_PRETRAINED_DIR", None)
            else:
                os.environ["STRUCTBERT_PRETRAINED_DIR"] = old_value
        self.assertEqual(str(path), sentinel)
