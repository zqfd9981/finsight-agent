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
    def test_query_only_template_renders_single_segment(self) -> None:
        from finsight_agent_training.retrieval_strategy_classifier.data.dataset import (
            build_input_text,
        )

        text = build_input_text(query="红海局势最近怎么了？")
        self.assertEqual(text, "[QUERY] 红海局势最近怎么了？")

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

        required = {"sample_id", "query", "label", "label_source", "notes"}
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

    def test_reviewed_boundary_queries_follow_market_impact_policy(self) -> None:
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
        rows: dict[str, dict[str, str]] = {}
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                rows[str(row["sample_id"])] = row

        expected = {
            "rsc_ha_012": "event_primary",
            "rsc_gen_080": "event_primary",
            "rsc_gen_092": "event_primary",
            "rsc_gen_211": "event_primary",
            "rsc_gen_219": "event_primary",
            "rsc_gen_235": "event_primary",
            "rsc_gen_249": "event_primary",
            "rsc_gen_251": "event_primary",
            "rsc_gen_259": "event_primary",
            "rsc_gen_260": "event_primary",
            "rsc_gen_264": "event_primary",
            "rsc_gen_266": "event_primary",
            "rsc_gen_268": "event_primary",
            "rsc_gen_269": "event_primary",
            "rsc_gen_272": "event_primary",
            "rsc_gen_093": "dual_primary",
        }
        for sample_id, expected_label in expected.items():
            self.assertIn(sample_id, rows, f"missing reviewed sample: {sample_id}")
            self.assertEqual(
                rows[sample_id]["label"],
                expected_label,
                f"{sample_id} should follow the reviewed market-impact labeling policy",
            )


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
        counts_a = build_splits(labeled_path=labeled_path, splits_dir=splits_dir)
        counts_b = build_splits(labeled_path=labeled_path, splits_dir=splits_dir)
        self.assertEqual(counts_a, counts_b)

    def test_partition_function_follows_mod100_rule(self) -> None:
        from finsight_agent_training.retrieval_strategy_classifier.scripts.build_dataset import (
            _partition_for_sample_id,
        )

        self.assertEqual(_partition_for_sample_id("rsc_000009"), "test")
        self.assertEqual(_partition_for_sample_id("rsc_000010"), "val")
        self.assertEqual(_partition_for_sample_id("rsc_000024"), "val")
        self.assertEqual(_partition_for_sample_id("rsc_000025"), "train")
        self.assertEqual(_partition_for_sample_id("rsc_unknown"), "train")
