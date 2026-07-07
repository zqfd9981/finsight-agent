"""检索策略分类器 E2E 集成测试（默认 skip，需 env 守护启用）。

启用方式：

    RUN_STRATEGY_MODEL_E2E=1 python -m unittest \\
        tests.integration.test_strategy_classifier_e2e -v

依赖：``var/models/retrieval_strategy_classifier/v1/`` 已 export 出来。
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"
# 把 ``backend/training`` 加到 sys.path，让 ``finsight_agent_training`` 作为顶级包可导入
TRAINING_PARENT = REPO_ROOT / "backend" / "training"
for candidate in (REPO_ROOT, BACKEND_SRC_ROOT, TRAINING_PARENT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


@unittest.skipUnless(
    os.environ.get("RUN_STRATEGY_MODEL_E2E") == "1",
    "set RUN_STRATEGY_MODEL_E2E=1 to enable real-model end-to-end test",
)
class StrategyClassifierE2ETest(unittest.TestCase):
    def test_real_model_meets_minimum_accuracy_on_test_set(self) -> None:
        from finsight_agent_training.retrieval_strategy_classifier.scripts.evaluate import (
            gate_passes,
            run_evaluation,
        )

        repo_root = REPO_ROOT
        artifacts = (
            repo_root / "var" / "models" / "retrieval_strategy_classifier" / "v1"
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

        self.assertTrue(
            artifacts.exists(),
            f"missing exported model at {artifacts}; run export_model.py first",
        )
        self.assertTrue((splits / "test.jsonl").exists())

        metrics = run_evaluation(artifacts_dir=artifacts, splits_dir=splits)
        self.assertTrue(
            gate_passes(metrics),
            f"gate failed: accuracy={metrics.accuracy}, "
            f"per_class_f1={metrics.per_class_f1}",
        )
