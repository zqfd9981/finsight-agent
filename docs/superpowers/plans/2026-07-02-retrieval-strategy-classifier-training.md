# Retrieval Strategy Classifier Training Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个独立于主流程推进的 `RetrievalStrategyClassifier` 训练与评测闭环，产出可评测、可打包、可后续接入控制面的 `StructBERT` 三分类模型。

**Architecture:** 先建立稳定的数据 schema、标注规范和切分机制，再实现 `StructBERT` 单头三分类训练与离线评测，最后补可插拔线上推理适配。主流程继续保留 stub / fallback，本计划的训练产物只有在达到离线门槛后才进入接线阶段。

**Tech Stack:** Python、PyTorch、Transformers、JSONL 数据集、仓库现有 evaluation 目录、unittest/必要时轻量脚本测试

---

## 文件结构

本计划建议最终形成以下边界：

- `backend/src/finsight_agent/control_plane/orchestrator/retrieval_strategy_classifier.py`
  - 分类器线上接口与 stub/fallback
- `backend/src/finsight_agent/control_plane/orchestrator/retrieval_strategy_structbert.py`
  - `StructBERT` 推理适配器
- `backend/src/finsight_agent/evaluation/datasets/retrieval_strategy_samples.py`
  - 训练样本 schema、样本序列化模板、切分加载器
- `backend/src/finsight_agent/evaluation/runners/retrieval_strategy_eval.py`
  - 离线评测逻辑
- `backend/src/finsight_agent/evaluation/runners/retrieval_strategy_report.py`
  - 指标与误判报告导出
- `backend/src/finsight_agent/evaluation/datasets/retrieval_strategy/`
  - 原始样本、已标样本、split 元数据
- `backend/src/finsight_agent/evaluation/training/retrieval_strategy_train.py`
  - 训练入口
- `backend/src/finsight_agent/evaluation/training/retrieval_strategy_export.py`
  - 导出模型与元数据
- `tests/unit/test_retrieval_strategy_dataset.py`
- `tests/unit/test_retrieval_strategy_classifier.py`
- `tests/unit/test_retrieval_strategy_eval.py`
- `docs/superpowers/specs/2026-07-02-retrieval-strategy-classifier-training-design.md`
- `docs/superpowers/plans/2026-07-02-retrieval-strategy-classifier-training.md`

---

### Task 1: 定义分类器接口与标签常量

**Files:**
- Create: `backend/src/finsight_agent/control_plane/orchestrator/retrieval_strategy_classifier.py`
- Test: `tests/unit/test_retrieval_strategy_classifier.py`

- [ ] **Step 1: 写失败单测，固定标签集合与 fallback 行为**

```python
import unittest

from finsight_agent.control_plane.orchestrator.retrieval_strategy_classifier import (
    DEFAULT_RETRIEVAL_STRATEGY,
    RETRIEVAL_STRATEGIES,
    StubRetrievalStrategyClassifier,
)


class RetrievalStrategyClassifierTest(unittest.TestCase):
    def test_strategy_labels_are_stable(self) -> None:
        self.assertEqual(
            RETRIEVAL_STRATEGIES,
            ("event_primary", "disclosure_primary", "dual_primary"),
        )
        self.assertEqual(DEFAULT_RETRIEVAL_STRATEGY, "event_primary")

    def test_stub_classifier_returns_default_strategy(self) -> None:
        classifier = StubRetrievalStrategyClassifier()

        result = classifier.classify(
            query="红海局势升级利好哪些A股航运股？",
            router_payload={"intent": "event_impact_analysis", "entities": {}},
            session_topic="",
        )

        self.assertEqual(result["strategy"], "event_primary")
        self.assertEqual(result["confidence"], "low")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.unit.test_retrieval_strategy_classifier -v`

Expected: `ModuleNotFoundError` 或导入失败，因为目标文件尚不存在。

- [ ] **Step 3: 写最小实现，先稳定接口与默认值**

```python
from __future__ import annotations

from typing import Protocol


RETRIEVAL_STRATEGIES = (
    "event_primary",
    "disclosure_primary",
    "dual_primary",
)
DEFAULT_RETRIEVAL_STRATEGY = "event_primary"


class RetrievalStrategyClassifier(Protocol):
    """检索策略分类器协议。

    控制面只依赖这一层抽象，不直接依赖具体模型实现。
    """

    def classify(
        self,
        *,
        query: str,
        router_payload: dict[str, object],
        session_topic: str,
    ) -> dict[str, str]:
        """返回三分类策略标签及轻量调试信息。"""


class StubRetrievalStrategyClassifier:
    """默认占位实现，保证训练子项目未就绪时主流程仍可运行。"""

    def classify(
        self,
        *,
        query: str,
        router_payload: dict[str, object],
        session_topic: str,
    ) -> dict[str, str]:
        del query, router_payload, session_topic
        return {
            "strategy": DEFAULT_RETRIEVAL_STRATEGY,
            "confidence": "low",
            "reason": "stub_fallback",
        }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.unit.test_retrieval_strategy_classifier -v`

Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add backend/src/finsight_agent/control_plane/orchestrator/retrieval_strategy_classifier.py tests/unit/test_retrieval_strategy_classifier.py
git commit -m "feat: 增加检索策略分类器抽象"
```

### Task 2: 定义样本 schema 与输入模板

**Files:**
- Create: `backend/src/finsight_agent/evaluation/datasets/retrieval_strategy_samples.py`
- Test: `tests/unit/test_retrieval_strategy_dataset.py`

- [ ] **Step 1: 写失败单测，固定样本字段和序列化模板**

```python
import unittest

from finsight_agent.evaluation.datasets.retrieval_strategy_samples import (
    RetrievalStrategySample,
    render_classifier_input,
)


class RetrievalStrategyDatasetTest(unittest.TestCase):
    def test_render_classifier_input_uses_stable_template(self) -> None:
        sample = RetrievalStrategySample(
            sample_id="rsc_001",
            query="红海局势升级利好哪些A股航运股？",
            intent="event_impact_analysis",
            event="红海局势升级",
            themes=["航运", "油运"],
            target="A股航运股",
            time_scope="recent",
            session_topic="",
            label="dual_primary",
            label_source="human_reviewed",
            notes="",
        )

        rendered = render_classifier_input(sample)

        self.assertIn("[QUERY]", rendered)
        self.assertIn("[INTENT]", rendered)
        self.assertIn("[EVENT]", rendered)
        self.assertIn("[THEMES]", rendered)
        self.assertIn("[TARGET]", rendered)
        self.assertIn("[TIME_SCOPE]", rendered)
        self.assertIn("[SESSION_TOPIC]", rendered)
        self.assertIn("无", rendered)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.unit.test_retrieval_strategy_dataset -v`

Expected: 导入失败，因为样本 schema 文件尚不存在。

- [ ] **Step 3: 写最小实现，固定 dataclass 与输入模板**

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RetrievalStrategySample:
    sample_id: str
    query: str
    intent: str
    event: str
    themes: list[str]
    target: str
    time_scope: str
    session_topic: str
    label: str
    label_source: str
    notes: str


def _normalize_field(value: str) -> str:
    candidate = value.strip()
    return candidate or "无"


def render_classifier_input(sample: RetrievalStrategySample) -> str:
    return "\n".join(
        [
            "[QUERY]",
            _normalize_field(sample.query),
            "",
            "[INTENT]",
            _normalize_field(sample.intent),
            "",
            "[EVENT]",
            _normalize_field(sample.event),
            "",
            "[THEMES]",
            _normalize_field(", ".join(sample.themes)),
            "",
            "[TARGET]",
            _normalize_field(sample.target),
            "",
            "[TIME_SCOPE]",
            _normalize_field(sample.time_scope),
            "",
            "[SESSION_TOPIC]",
            _normalize_field(sample.session_topic),
        ]
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.unit.test_retrieval_strategy_dataset -v`

Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add backend/src/finsight_agent/evaluation/datasets/retrieval_strategy_samples.py tests/unit/test_retrieval_strategy_dataset.py
git commit -m "feat: 增加检索策略训练样本结构"
```

### Task 3: 增加 JSONL 数据集读取与 split 加载

**Files:**
- Modify: `backend/src/finsight_agent/evaluation/datasets/retrieval_strategy_samples.py`
- Test: `tests/unit/test_retrieval_strategy_dataset.py`

- [ ] **Step 1: 写失败单测，固定 JSONL 加载与 split 选择行为**

```python
import json
import tempfile
import unittest
from pathlib import Path

from finsight_agent.evaluation.datasets.retrieval_strategy_samples import (
    load_labeled_samples,
    load_split_ids,
)


class RetrievalStrategyDatasetLoaderTest(unittest.TestCase):
    def test_load_labeled_samples_and_split_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            labeled = root / "labeled.jsonl"
            split = root / "train.txt"

            labeled.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "sample_id": "rsc_001",
                                "query": "红海局势升级利好哪些A股航运股？",
                                "intent": "event_impact_analysis",
                                "event": "红海局势升级",
                                "themes": ["航运"],
                                "target": "A股航运股",
                                "time_scope": "recent",
                                "session_topic": "",
                                "label": "dual_primary",
                                "label_source": "human_reviewed",
                                "notes": "",
                            },
                            ensure_ascii=True,
                        )
                    ]
                ),
                encoding="utf-8",
            )
            split.write_text("rsc_001\n", encoding="utf-8")

            samples = load_labeled_samples(labeled)
            split_ids = load_split_ids(split)

            self.assertEqual(len(samples), 1)
            self.assertEqual(samples[0].label, "dual_primary")
            self.assertEqual(split_ids, ["rsc_001"])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.unit.test_retrieval_strategy_dataset -v`

Expected: `ImportError` 或属性不存在。

- [ ] **Step 3: 在数据模块中补充 JSONL / split 加载器**

```python
import json
from pathlib import Path


def load_labeled_samples(path: str | Path) -> list[RetrievalStrategySample]:
    raw = Path(path).read_text(encoding="utf-8").splitlines()
    samples: list[RetrievalStrategySample] = []
    for line in raw:
        if not line.strip():
            continue
        payload = json.loads(line)
        samples.append(
            RetrievalStrategySample(
                sample_id=str(payload["sample_id"]),
                query=str(payload["query"]),
                intent=str(payload["intent"]),
                event=str(payload.get("event", "")),
                themes=[str(item) for item in payload.get("themes", [])],
                target=str(payload.get("target", "")),
                time_scope=str(payload.get("time_scope", "")),
                session_topic=str(payload.get("session_topic", "")),
                label=str(payload["label"]),
                label_source=str(payload.get("label_source", "")),
                notes=str(payload.get("notes", "")),
            )
        )
    return samples


def load_split_ids(path: str | Path) -> list[str]:
    return [
        line.strip()
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.unit.test_retrieval_strategy_dataset -v`

Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add backend/src/finsight_agent/evaluation/datasets/retrieval_strategy_samples.py tests/unit/test_retrieval_strategy_dataset.py
git commit -m "feat: 增加检索策略数据集加载器"
```

### Task 4: 固定标注说明与样本目录骨架

**Files:**
- Create: `backend/src/finsight_agent/evaluation/datasets/retrieval_strategy/README.md`
- Create: `backend/src/finsight_agent/evaluation/datasets/retrieval_strategy/raw.jsonl`
- Create: `backend/src/finsight_agent/evaluation/datasets/retrieval_strategy/labeled.jsonl`
- Create: `backend/src/finsight_agent/evaluation/datasets/retrieval_strategy/train.txt`
- Create: `backend/src/finsight_agent/evaluation/datasets/retrieval_strategy/validation.txt`
- Create: `backend/src/finsight_agent/evaluation/datasets/retrieval_strategy/test.txt`

- [ ] **Step 1: 新建标注说明文档，写明三类标签判定规则**

```markdown
# Retrieval Strategy Dataset

## 标签

- `event_primary`
- `disclosure_primary`
- `dual_primary`

## 标注问题

标注员需要回答的问题是：

“为了高效建立 `collect_event_context`，首个必要检索动作应该优先查哪类源？”

## 规则

- 外部事件理解优先：`event_primary`
- 公司公告/财报/披露优先：`disclosure_primary`
- 事件背景与A股影响同等必要：`dual_primary`

## 文件

- `raw.jsonl`：待标样本
- `labeled.jsonl`：人工确认后的真标签样本
- `train.txt` / `validation.txt` / `test.txt`：按 `sample_id` 划分的 split 文件
```

- [ ] **Step 2: 初始化空数据文件**

```text
raw.jsonl           # 空文件
labeled.jsonl       # 空文件
train.txt           # 空文件
validation.txt      # 空文件
test.txt            # 空文件
```

- [ ] **Step 3: 手工检查目录结构**

Run: `Get-ChildItem -Recurse backend/src/finsight_agent/evaluation/datasets/retrieval_strategy`

Expected: 能看到 README 与 5 个数据文件。

- [ ] **Step 4: 提交**

```bash
git add backend/src/finsight_agent/evaluation/datasets/retrieval_strategy
git commit -m "docs: 增加检索策略数据标注骨架"
```

### Task 5: 增加数据质量校验脚本

**Files:**
- Create: `backend/src/finsight_agent/evaluation/datasets/retrieval_strategy_validate.py`
- Test: `tests/unit/test_retrieval_strategy_dataset.py`

- [ ] **Step 1: 写失败单测，固定最小校验规则**

```python
import tempfile
import unittest
from pathlib import Path

from finsight_agent.evaluation.datasets.retrieval_strategy_validate import (
    validate_dataset_directory,
)


class RetrievalStrategyDatasetValidationTest(unittest.TestCase):
    def test_validate_dataset_directory_detects_missing_split_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "labeled.jsonl").write_text("", encoding="utf-8")
            (root / "train.txt").write_text("missing_id\n", encoding="utf-8")
            (root / "validation.txt").write_text("", encoding="utf-8")
            (root / "test.txt").write_text("", encoding="utf-8")

            report = validate_dataset_directory(root)

            self.assertIn("missing_id", " ".join(report["errors"]))
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.unit.test_retrieval_strategy_dataset -v`

Expected: 模块不存在或函数不存在。

- [ ] **Step 3: 实现最小数据校验器**

```python
from __future__ import annotations

from pathlib import Path

from finsight_agent.evaluation.datasets.retrieval_strategy_samples import (
    load_labeled_samples,
    load_split_ids,
)


def validate_dataset_directory(root: str | Path) -> dict[str, list[str]]:
    root_path = Path(root)
    labeled = load_labeled_samples(root_path / "labeled.jsonl")
    known_ids = {sample.sample_id for sample in labeled}
    errors: list[str] = []

    for filename in ("train.txt", "validation.txt", "test.txt"):
        for sample_id in load_split_ids(root_path / filename):
            if sample_id not in known_ids:
                errors.append(f"{filename}: unknown sample_id {sample_id}")

    return {"errors": errors}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.unit.test_retrieval_strategy_dataset -v`

Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add backend/src/finsight_agent/evaluation/datasets/retrieval_strategy_validate.py tests/unit/test_retrieval_strategy_dataset.py
git commit -m "feat: 增加检索策略数据校验脚本"
```

### Task 6: 增加训练样本到模型输入的编码器

**Files:**
- Create: `backend/src/finsight_agent/evaluation/training/retrieval_strategy_features.py`
- Test: `tests/unit/test_retrieval_strategy_dataset.py`

- [ ] **Step 1: 写失败单测，固定标签映射与文本编码结果**

```python
import unittest

from finsight_agent.evaluation.datasets.retrieval_strategy_samples import RetrievalStrategySample
from finsight_agent.evaluation.training.retrieval_strategy_features import (
    LABEL_TO_ID,
    encode_sample,
)


class RetrievalStrategyFeatureEncodingTest(unittest.TestCase):
    def test_encode_sample_returns_text_and_label_id(self) -> None:
        sample = RetrievalStrategySample(
            sample_id="rsc_001",
            query="红海局势升级利好哪些A股航运股？",
            intent="event_impact_analysis",
            event="红海局势升级",
            themes=["航运"],
            target="A股航运股",
            time_scope="recent",
            session_topic="",
            label="dual_primary",
            label_source="human_reviewed",
            notes="",
        )

        encoded = encode_sample(sample)

        self.assertEqual(encoded["label_id"], LABEL_TO_ID["dual_primary"])
        self.assertIn("[QUERY]", encoded["text"])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.unit.test_retrieval_strategy_dataset -v`

Expected: 目标模块不存在。

- [ ] **Step 3: 实现标签映射与最小特征编码器**

```python
from __future__ import annotations

from finsight_agent.evaluation.datasets.retrieval_strategy_samples import (
    RetrievalStrategySample,
    render_classifier_input,
)


LABEL_TO_ID = {
    "event_primary": 0,
    "disclosure_primary": 1,
    "dual_primary": 2,
}
ID_TO_LABEL = {value: key for key, value in LABEL_TO_ID.items()}


def encode_sample(sample: RetrievalStrategySample) -> dict[str, object]:
    return {
        "sample_id": sample.sample_id,
        "text": render_classifier_input(sample),
        "label_id": LABEL_TO_ID[sample.label],
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.unit.test_retrieval_strategy_dataset -v`

Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add backend/src/finsight_agent/evaluation/training/retrieval_strategy_features.py tests/unit/test_retrieval_strategy_dataset.py
git commit -m "feat: 增加检索策略训练特征编码"
```

### Task 7: 增加 StructBERT 训练入口脚本

**Files:**
- Create: `backend/src/finsight_agent/evaluation/training/retrieval_strategy_train.py`
- Test: `tests/unit/test_retrieval_strategy_eval.py`

- [ ] **Step 1: 写失败单测，先固定训练入口参数解析**

```python
import unittest

from finsight_agent.evaluation.training.retrieval_strategy_train import (
    build_arg_parser,
)


class RetrievalStrategyTrainCliTest(unittest.TestCase):
    def test_build_arg_parser_accepts_dataset_and_output_dirs(self) -> None:
        parser = build_arg_parser()
        args = parser.parse_args(
            [
                "--dataset-dir",
                "backend/src/finsight_agent/evaluation/datasets/retrieval_strategy",
                "--output-dir",
                "runtime/models/retrieval_strategy_classifier",
            ]
        )

        self.assertTrue(str(args.dataset_dir).endswith("retrieval_strategy"))
        self.assertTrue(str(args.output_dir).endswith("retrieval_strategy_classifier"))
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.unit.test_retrieval_strategy_eval -v`

Expected: 导入失败，因为训练入口尚不存在。

- [ ] **Step 3: 实现最小训练入口骨架**

```python
from __future__ import annotations

import argparse
from pathlib import Path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="训练检索策略三分类模型")
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model-name", default="StructBERT")
    parser.add_argument("--epochs", type=int, default=5)
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    print(
        {
            "dataset_dir": str(args.dataset_dir),
            "output_dir": str(args.output_dir),
            "model_name": args.model_name,
            "epochs": args.epochs,
        }
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.unit.test_retrieval_strategy_eval -v`

Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add backend/src/finsight_agent/evaluation/training/retrieval_strategy_train.py tests/unit/test_retrieval_strategy_eval.py
git commit -m "feat: 增加检索策略训练入口骨架"
```

### Task 8: 增加离线评测器与核心指标

**Files:**
- Create: `backend/src/finsight_agent/evaluation/runners/retrieval_strategy_eval.py`
- Test: `tests/unit/test_retrieval_strategy_eval.py`

- [ ] **Step 1: 写失败单测，固定 metrics 输出字段**

```python
import unittest

from finsight_agent.evaluation.runners.retrieval_strategy_eval import (
    compute_classification_metrics,
)


class RetrievalStrategyEvalMetricsTest(unittest.TestCase):
    def test_compute_classification_metrics_returns_macro_f1(self) -> None:
        report = compute_classification_metrics(
            y_true=["event_primary", "dual_primary", "disclosure_primary"],
            y_pred=["event_primary", "event_primary", "disclosure_primary"],
        )

        self.assertIn("macro_f1", report)
        self.assertIn("per_class", report)
        self.assertIn("dual_primary_recall", report)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.unit.test_retrieval_strategy_eval -v`

Expected: 目标模块不存在。

- [ ] **Step 3: 实现最小评测器**

```python
from __future__ import annotations

from collections import Counter

from finsight_agent.control_plane.orchestrator.retrieval_strategy_classifier import (
    RETRIEVAL_STRATEGIES,
)


def compute_classification_metrics(
    *,
    y_true: list[str],
    y_pred: list[str],
) -> dict[str, object]:
    per_class: dict[str, dict[str, float]] = {}
    f1_scores: list[float] = []

    for label in RETRIEVAL_STRATEGIES:
        tp = sum(1 for truth, pred in zip(y_true, y_pred) if truth == label and pred == label)
        fp = sum(1 for truth, pred in zip(y_true, y_pred) if truth != label and pred == label)
        fn = sum(1 for truth, pred in zip(y_true, y_pred) if truth == label and pred != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
        per_class[label] = {"precision": precision, "recall": recall, "f1": f1}
        f1_scores.append(f1)

    macro_f1 = sum(f1_scores) / len(f1_scores)
    return {
        "macro_f1": macro_f1,
        "per_class": per_class,
        "dual_primary_recall": per_class["dual_primary"]["recall"],
        "support": dict(Counter(y_true)),
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.unit.test_retrieval_strategy_eval -v`

Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add backend/src/finsight_agent/evaluation/runners/retrieval_strategy_eval.py tests/unit/test_retrieval_strategy_eval.py
git commit -m "feat: 增加检索策略离线评测器"
```

### Task 9: 增加误判回放报告

**Files:**
- Create: `backend/src/finsight_agent/evaluation/runners/retrieval_strategy_report.py`
- Test: `tests/unit/test_retrieval_strategy_eval.py`

- [ ] **Step 1: 写失败单测，固定误判报告结构**

```python
import unittest

from finsight_agent.evaluation.runners.retrieval_strategy_report import (
    build_error_report,
)


class RetrievalStrategyErrorReportTest(unittest.TestCase):
    def test_build_error_report_collects_misrouted_samples(self) -> None:
        report = build_error_report(
            records=[
                {
                    "sample_id": "rsc_001",
                    "query": "红海局势升级利好哪些A股航运股？",
                    "y_true": "dual_primary",
                    "y_pred": "event_primary",
                }
            ]
        )

        self.assertEqual(report["total_errors"], 1)
        self.assertEqual(report["errors"][0]["sample_id"], "rsc_001")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.unit.test_retrieval_strategy_eval -v`

Expected: 模块不存在。

- [ ] **Step 3: 实现误判报告生成器**

```python
from __future__ import annotations


def build_error_report(*, records: list[dict[str, object]]) -> dict[str, object]:
    errors = [
        record
        for record in records
        if record.get("y_true") != record.get("y_pred")
    ]
    return {
        "total_errors": len(errors),
        "errors": errors,
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.unit.test_retrieval_strategy_eval -v`

Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add backend/src/finsight_agent/evaluation/runners/retrieval_strategy_report.py tests/unit/test_retrieval_strategy_eval.py
git commit -m "feat: 增加检索策略误判报告"
```

### Task 10: 增加模型导出与元数据打包

**Files:**
- Create: `backend/src/finsight_agent/evaluation/training/retrieval_strategy_export.py`
- Test: `tests/unit/test_retrieval_strategy_eval.py`

- [ ] **Step 1: 写失败单测，固定导出 metadata 结构**

```python
import unittest

from finsight_agent.evaluation.training.retrieval_strategy_export import (
    build_export_metadata,
)


class RetrievalStrategyExportTest(unittest.TestCase):
    def test_build_export_metadata_contains_required_fields(self) -> None:
        payload = build_export_metadata(
            model_name="StructBERT",
            dataset_version="v1",
            macro_f1=0.82,
        )

        self.assertEqual(payload["model_name"], "StructBERT")
        self.assertEqual(payload["dataset_version"], "v1")
        self.assertIn("label_to_id", payload)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.unit.test_retrieval_strategy_eval -v`

Expected: 模块不存在。

- [ ] **Step 3: 实现最小导出元数据函数**

```python
from __future__ import annotations

from finsight_agent.evaluation.training.retrieval_strategy_features import LABEL_TO_ID


def build_export_metadata(
    *,
    model_name: str,
    dataset_version: str,
    macro_f1: float,
) -> dict[str, object]:
    return {
        "model_name": model_name,
        "dataset_version": dataset_version,
        "macro_f1": macro_f1,
        "label_to_id": LABEL_TO_ID,
        "input_template_version": "v1",
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.unit.test_retrieval_strategy_eval -v`

Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add backend/src/finsight_agent/evaluation/training/retrieval_strategy_export.py tests/unit/test_retrieval_strategy_eval.py
git commit -m "feat: 增加检索策略模型导出元数据"
```

### Task 11: 增加 StructBERT 线上推理适配器

**Files:**
- Create: `backend/src/finsight_agent/control_plane/orchestrator/retrieval_strategy_structbert.py`
- Modify: `backend/src/finsight_agent/control_plane/orchestrator/retrieval_strategy_classifier.py`
- Test: `tests/unit/test_retrieval_strategy_classifier.py`

- [ ] **Step 1: 写失败单测，固定非法输出回退到默认策略**

```python
import unittest

from finsight_agent.control_plane.orchestrator.retrieval_strategy_structbert import (
    sanitize_strategy_output,
)


class RetrievalStrategyStructBertAdapterTest(unittest.TestCase):
    def test_sanitize_strategy_output_falls_back_for_invalid_label(self) -> None:
        payload = sanitize_strategy_output("not_a_label")
        self.assertEqual(payload["strategy"], "event_primary")
        self.assertEqual(payload["confidence"], "low")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.unit.test_retrieval_strategy_classifier -v`

Expected: 目标模块不存在。

- [ ] **Step 3: 实现最小推理适配器与标签清洗**

```python
from __future__ import annotations

from finsight_agent.control_plane.orchestrator.retrieval_strategy_classifier import (
    DEFAULT_RETRIEVAL_STRATEGY,
    RETRIEVAL_STRATEGIES,
)


def sanitize_strategy_output(label: str) -> dict[str, str]:
    candidate = label.strip()
    if candidate not in RETRIEVAL_STRATEGIES:
        return {
            "strategy": DEFAULT_RETRIEVAL_STRATEGY,
            "confidence": "low",
            "reason": "invalid_model_label",
        }
    return {
        "strategy": candidate,
        "confidence": "medium",
        "reason": "model_prediction",
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.unit.test_retrieval_strategy_classifier -v`

Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add backend/src/finsight_agent/control_plane/orchestrator/retrieval_strategy_structbert.py tests/unit/test_retrieval_strategy_classifier.py
git commit -m "feat: 增加StructBERT检索策略推理适配"
```

### Task 12: 接入 collect_event_context 前的集成门槛与切换开关

**Files:**
- Modify: `backend/src/finsight_agent/control_plane/orchestrator/context_retriever.py`
- Modify: `backend/src/finsight_agent/control_plane/orchestrator/stage_runners/collect_event_context.py`
- Test: `tests/unit/test_orchestrator_stage_runners.py`

- [ ] **Step 1: 写失败单测，固定分类器缺失时仍走原有 fallback**

```python
def test_collect_event_context_without_classifier_keeps_safe_fallback(self):
    result = run_collect_event_context_stage(
        request=self.request,
        router_result=self.router_result,
        stage_constraints={"retrieval_budget": 2},
        execution_state={},
        retrieval_facade=self.retrieval_facade,
        external_context_retriever=self.external_context_retriever,
    )

    self.assertIn(result.status, {"success", "degraded"})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.unit.test_orchestrator_stage_runners -v`

Expected: 因为签名或行为尚未扩展，新增测试不通过。

- [ ] **Step 3: 最小改造 stage，允许未来注入 classifier 但不强绑**

```python
# 这里只做最小接口预留：
# - 如果未显式传 classifier，继续沿用当前逻辑
# - 如果后续启用 classifier，再走 planner 分支
```

具体要求：

- 不改变当前默认行为
- 不要求本任务中真正启用训练好的模型
- 只为后续接线留扩展点

- [ ] **Step 4: 运行相关测试确认通过**

Run: `python -m unittest tests.unit.test_orchestrator_stage_runners tests.unit.test_retrieval_strategy_classifier -v`

Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add backend/src/finsight_agent/control_plane/orchestrator/context_retriever.py backend/src/finsight_agent/control_plane/orchestrator/stage_runners/collect_event_context.py tests/unit/test_orchestrator_stage_runners.py
git commit -m "feat: 预留检索策略分类器接线扩展点"
```

### Task 13: 补训练说明与运行命令

**Files:**
- Modify: `backend/src/finsight_agent/evaluation/datasets/retrieval_strategy/README.md`
- Modify: `docs/superpowers/specs/2026-07-02-retrieval-strategy-classifier-training-design.md`
- Modify: `docs/superpowers/plans/2026-07-02-retrieval-strategy-classifier-training.md`

- [ ] **Step 1: 在数据 README 中补充训练与评测命令**

```markdown
## 训练

```bash
python -m finsight_agent.evaluation.training.retrieval_strategy_train \
  --dataset-dir backend/src/finsight_agent/evaluation/datasets/retrieval_strategy \
  --output-dir runtime/models/retrieval_strategy_classifier
```

## 评测

```bash
python -m finsight_agent.evaluation.runners.retrieval_strategy_eval
```
```

- [ ] **Step 2: 手工检查文档与设计一致**

检查项：

- 标签名称是否一致
- 输入模板字段是否一致
- fallback 是否仍是 `event_primary`
- 评测门槛是否与设计一致

- [ ] **Step 3: 提交**

```bash
git add backend/src/finsight_agent/evaluation/datasets/retrieval_strategy/README.md docs/superpowers/specs/2026-07-02-retrieval-strategy-classifier-training-design.md docs/superpowers/plans/2026-07-02-retrieval-strategy-classifier-training.md
git commit -m "docs: 补充检索策略训练运行说明"
```

## Self-Review

### Spec coverage

- 训练任务边界：Task 1、Task 11、Task 12 覆盖
- 数据 schema 与模板：Task 2、Task 3 覆盖
- 标注与目录规范：Task 4、Task 5 覆盖
- StructBERT 单头训练骨架：Task 6、Task 7 覆盖
- 评测与误判回放：Task 8、Task 9 覆盖
- 模型导出与后续接线：Task 10、Task 11、Task 12 覆盖
- 文档与运行说明：Task 13 覆盖

### Placeholder scan

- 已避免使用 `TBD`、`TODO`、`implement later`
- 所有步骤都给出具体文件、测试、命令或最小代码骨架

### Type consistency

- 标签集合统一为：
  - `event_primary`
  - `disclosure_primary`
  - `dual_primary`
- fallback 统一为 `event_primary`
- 数据样本字段统一使用：
  - `sample_id`
  - `query`
  - `intent`
  - `event`
  - `themes`
  - `target`
  - `time_scope`
  - `session_topic`
  - `label`

