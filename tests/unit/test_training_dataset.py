from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TRAINING_PARENT = REPO_ROOT / "backend" / "training"
for candidate in (REPO_ROOT, TRAINING_PARENT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


class BuildInputTextTest(unittest.TestCase):
    def test_full_fields_render_in_stable_order(self) -> None:
        from finsight_agent_training.retrieval_strategy_classifier.data.dataset import (
            build_input_text,
        )

        text = build_input_text(
            query="红海局势升级利好哪些A股航运股？",
            intent="event_impact_analysis",
            event="红海局势升级",
            themes=["航运", "油运"],
            target="A股航运股",
            time_scope="recent",
            session_topic="",
        )

        self.assertIn("[QUERY] 红海局势升级利好哪些A股航运股？", text)
        self.assertIn("[INTENT] event_impact_analysis", text)
        self.assertIn("[EVENT] 红海局势升级", text)
        self.assertIn("[THEMES] 航运, 油运", text)
        self.assertIn("[TARGET] A股航运股", text)
        self.assertIn("[TIME_SCOPE] recent", text)
        self.assertIn("[SESSION_TOPIC] 无", text)

    def test_missing_fields_fall_back_to_wu(self) -> None:
        from finsight_agent_training.retrieval_strategy_classifier.data.dataset import (
            build_input_text,
        )

        text = build_input_text(
            query="宁德时代扩产公告意味着什么？",
            intent="event_impact_analysis",
            event="",
            themes=[],
            target="",
            time_scope="",
            session_topic="",
        )

        self.assertIn("[EVENT] 无", text)
        self.assertIn("[THEMES] 无", text)
        self.assertIn("[TARGET] 无", text)
        self.assertIn("[TIME_SCOPE] 无", text)

    def test_label_index_mapping_is_bidirectional_and_complete(self) -> None:
        from finsight_agent_training.retrieval_strategy_classifier.data.dataset import (
            INDEX_TO_LABEL,
            LABEL_TO_INDEX,
        )

        expected = {"event_primary": 0, "disclosure_primary": 1, "dual_primary": 2}
        self.assertEqual(LABEL_TO_INDEX, expected)
        for label, idx in expected.items():
            self.assertEqual(INDEX_TO_LABEL[idx], label)


class LabeledDatasetSchemaTest(unittest.TestCase):
    def test_labeled_jsonl_has_required_fields_per_row(self) -> None:
        import json

        path = (
            REPO_ROOT
            / "backend"
            / "training"
            / "finsight_agent_training"
            / "retrieval_strategy_classifier"
            / "data"
            / "labeled"
            / "labeled.jsonl"
        )
        self.assertTrue(path.exists(), f"missing labeled dataset at {path}")

        required = {
            "sample_id", "query", "intent", "event", "themes",
            "target", "time_scope", "session_topic", "label",
            "label_source",
        }
        valid_labels = {"event_primary", "disclosure_primary", "dual_primary"}
        valid_sources = {"human_authored", "human_reviewed", "transferred_from_event_eval"}

        count = 0
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                missing = required - set(row.keys())
                self.assertFalse(missing, f"row missing fields: {missing} -> {row}")
                self.assertIn(row["label"], valid_labels)
                self.assertIn(row["label_source"], valid_sources)
                count += 1

        self.assertGreaterEqual(count, 300, f"need >= 300 labeled samples, got {count}")


class DatasetSplitTest(unittest.TestCase):
    def _splits_dir(self) -> Path:
        return (
            REPO_ROOT
            / "backend"
            / "training"
            / "finsight_agent_training"
            / "retrieval_strategy_classifier"
            / "data"
            / "splits"
        )

    def test_splits_three_partitions_disjoint_and_total_matches_labeled(self) -> None:
        import json
        from finsight_agent_training.retrieval_strategy_classifier.scripts.build_dataset import (
            build_splits,
        )

        labeled_path = (
            REPO_ROOT
            / "backend"
            / "training"
            / "finsight_agent_training"
            / "retrieval_strategy_classifier"
            / "data"
            / "labeled"
            / "labeled.jsonl"
        )
        splits_dir = self._splits_dir()
        counts = build_splits(labeled_path=labeled_path, splits_dir=splits_dir)
        self.assertEqual(set(counts.keys()), {"train", "val", "test"})
        # labeled.jsonl 真实总数（301），切分三方加起来必须等于它
        with labeled_path.open("r", encoding="utf-8") as fh:
            labeled_count = sum(1 for line in fh if line.strip())
        self.assertEqual(sum(counts.values()), labeled_count)

        sample_ids: dict[str, str] = {}
        for partition in ("train", "val", "test"):
            p = splits_dir / f"{partition}.jsonl"
            self.assertTrue(p.exists(), f"missing {p}")
            with p.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    sid = row["sample_id"]
                    self.assertNotIn(sid, sample_ids, f"{sid} appears in multiple partitions")
                    sample_ids[sid] = partition

    def test_split_deterministic_by_sample_id_mod100(self) -> None:
        """切分规则: sample_id 后两位整数 mod 100; <10->test, <25->val, else train."""
        from finsight_agent_training.retrieval_strategy_classifier.scripts.build_dataset import (
            build_splits,
        )

        labeled_path = (
            REPO_ROOT
            / "backend"
            / "training"
            / "finsight_agent_training"
            / "retrieval_strategy_classifier"
            / "data"
            / "labeled"
            / "labeled.jsonl"
        )
        splits_dir = self._splits_dir()
        # first call
        counts_a = build_splits(labeled_path=labeled_path, splits_dir=splits_dir)
        # second call must produce same counts
        counts_b = build_splits(labeled_path=labeled_path, splits_dir=splits_dir)
        self.assertEqual(counts_a, counts_b)

    def test_partition_function_follows_mod100_rule(self) -> None:
        """直接验证切分规则的边界值。"""
        from finsight_agent_training.retrieval_strategy_classifier.scripts.build_dataset import (
            _partition_for_sample_id,
        )

        # bucket < 10 -> test
        self.assertEqual(_partition_for_sample_id("rsc_000009"), "test")
        # bucket = 10 -> val (10 < 25)
        self.assertEqual(_partition_for_sample_id("rsc_000010"), "val")
        # bucket = 24 -> val
        self.assertEqual(_partition_for_sample_id("rsc_000024"), "val")
        # bucket = 25 -> train
        self.assertEqual(_partition_for_sample_id("rsc_000025"), "train")
        # 没有数字后缀 -> train（不静默丢弃）
        self.assertEqual(_partition_for_sample_id("rsc_unknown"), "train")