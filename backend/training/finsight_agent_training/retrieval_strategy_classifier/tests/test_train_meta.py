from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
# training 子项目下要 import finsight_agent_training 这个顶级包，
# 需要把 backend/training 加到 sys.path。
TRAINING_PARENT = REPO_ROOT / "backend" / "training"
for candidate in (REPO_ROOT, TRAINING_PARENT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


class TrainingMetaTest(unittest.TestCase):
    def test_training_meta_has_required_keys(self) -> None:
        from finsight_agent_training.retrieval_strategy_classifier.scripts.train import (
            save_training_meta,
        )

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "classifier_v1"
            out_dir.mkdir()
            save_training_meta(
                out_dir=out_dir,
                params={"lr": 2e-5, "epochs": 5, "batch_size": 16},
                metrics={"val_accuracy": 0.87, "val_macro_f1": 0.86, "epoch": 3},
                git_commit="abcdef",
            )
            meta_path = out_dir / "training_meta.json"
            self.assertTrue(meta_path.exists())
            payload = json.loads(meta_path.read_text(encoding="utf-8"))
            for key in (
                "lr",
                "epochs",
                "batch_size",
                "val_accuracy",
                "val_macro_f1",
                "git_commit",
                "trained_at",
                "labels",
            ):
                self.assertIn(key, payload)
            # labels 必须是训练时约定的反向索引映射
            self.assertEqual(
                payload["labels"],
                {"0": "event_primary", "1": "disclosure_primary", "2": "dual_primary"},
            )

    def test_training_meta_creates_out_dir(self) -> None:
        from finsight_agent_training.retrieval_strategy_classifier.scripts.train import (
            save_training_meta,
        )

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "nested" / "classifier_v1"
            save_training_meta(
                out_dir=out_dir,
                params={"lr": 1e-5, "epochs": 1, "batch_size": 8},
                metrics={"val_accuracy": 0.5, "val_macro_f1": 0.4, "epoch": 1},
                git_commit="",
            )
            self.assertTrue((out_dir / "training_meta.json").exists())
