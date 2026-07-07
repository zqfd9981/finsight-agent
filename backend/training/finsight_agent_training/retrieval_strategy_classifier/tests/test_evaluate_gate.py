from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
TRAINING_PARENT = REPO_ROOT / "backend" / "training"
for candidate in (REPO_ROOT, TRAINING_PARENT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


class EvaluateGateTest(unittest.TestCase):
    def test_gate_passes_when_metrics_above_thresholds(self) -> None:
        from finsight_agent_training.retrieval_strategy_classifier.scripts.evaluate import (
            gate_passes,
        )

        metrics = {
            "accuracy": 0.87,
            "per_class_f1": {
                "event_primary": 0.86,
                "disclosure_primary": 0.85,
                "dual_primary": 0.84,
            },
        }
        self.assertTrue(gate_passes(metrics))

    def test_gate_fails_when_accuracy_below_threshold(self) -> None:
        from finsight_agent_training.retrieval_strategy_classifier.scripts.evaluate import (
            gate_passes,
        )

        metrics = {
            "accuracy": 0.80,
            "per_class_f1": {
                "event_primary": 0.85,
                "disclosure_primary": 0.85,
                "dual_primary": 0.85,
            },
        }
        self.assertFalse(gate_passes(metrics))

    def test_gate_fails_when_any_class_f1_below_threshold(self) -> None:
        from finsight_agent_training.retrieval_strategy_classifier.scripts.evaluate import (
            gate_passes,
        )

        metrics = {
            "accuracy": 0.90,
            "per_class_f1": {
                "event_primary": 0.85,
                "disclosure_primary": 0.85,
                "dual_primary": 0.70,
            },
        }
        self.assertFalse(gate_passes(metrics))

    def test_gate_accepts_evalmetrics_dataclass(self) -> None:
        from finsight_agent_training.retrieval_strategy_classifier.scripts.evaluate import (
            EvalMetrics,
            gate_passes,
        )

        m = EvalMetrics(
            accuracy=0.86,
            per_class_f1={"event_primary": 0.81, "disclosure_primary": 0.82, "dual_primary": 0.83},
            confusion=[[10, 1, 1], [1, 10, 1], [1, 1, 10]],
            baseline_match_rate=0.33,
        )
        self.assertTrue(gate_passes(m))

    def test_confusion_matrix_shape(self) -> None:
        from finsight_agent_training.retrieval_strategy_classifier.scripts.evaluate import (
            _compute_metrics,
        )

        true_idxs = [0, 0, 1, 1, 2, 2]
        pred_idxs = [0, 1, 1, 2, 2, 0]
        accuracy, per_class_f1, confusion = _compute_metrics(true_idxs, pred_idxs)
        # 3x3 confusion matrix
        self.assertEqual(len(confusion), 3)
        for row in confusion:
            self.assertEqual(len(row), 3)
        # accuracy: 3 correct out of 6 = 0.5
        self.assertAlmostEqual(accuracy, 0.5)
        # per_class F1 must have all 3 labels
        self.assertEqual(set(per_class_f1.keys()), {"event_primary", "disclosure_primary", "dual_primary"})
