# Retrieval Strategy Classifier Training Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `StubRetrievalStrategyClassifier` 替换成 `TrainedRetrievalStrategyClassifier`：离线训练 StructBERT 中文 base 三分类器，运行时懒加载推理，任一异常回退到 stub，主流程 227 测试不破。

**Architecture:** 训练代码（依赖 `transformers + torch`）物理隔离到 `backend/training/retrieval_strategy_classifier/`，不进 `src/` 主流程 import 路径。运行时新增 `trained_strategy_classifier.py` 实现既有 `RetrievalStrategyClassifier` Protocol；`service.py` 装配点单点切换；失败回退等价于现状。

**Tech Stack:** Python 3.11+, transformers, torch, StructBERT 中文 base (`alibaba-pai/structbert-base-zh`), pytest/unittest

## Global Constraints

- 工作分支：`main`（基于最新 main 起步；不复用 `feat/phase1-project-runnable`）
- 所有 commit message / PR 描述使用中文（项目长期偏好，已存 memory）
- 训练/推理接口契约：`RetrievalStrategyClassifier` Protocol、`StubRetrievalStrategyClassifier`、`RETRIEVAL_STRATEGIES`、`DEFAULT_RETRIEVAL_STRATEGY` 完全不变
- 现有 227 个测试必须全绿；本计划新增测试不修改既有断言
- 失败回退语义：任何异常 → 返回 `event_primary / low / stub_fallback`，与 stub 当前行为等价
- 模型权重不 commit 到 git；通过 `var/models/` + 环境变量 `RETRIEVAL_STRATEGY_MODEL_DIR` 管理
- `.gitignore` 必须排除：`var/models/**`、`backend/training/retrieval_strategy_classifier/artifacts/**`、`*.bin`、`*.safetensors`、`tokenizer.json`
- 中文编码器：`alibaba-pai/structbert-base-zh`（HF 上若不可用，回退到 `hfl/chinese-roberta-wwm-ext`）
- 标签集合固定：`event_primary` / `disclosure_primary` / `dual_primary`
- 序列化模板字段缺失一律填 `"无"`；不省略 key
- 切分规则：`sample_id` 后两位整数哈希 mod 100，`<10 → test / <25 → val / 其它 → train`
- 离线评测 CI gate：test accuracy ≥ 0.85 且 per-class F1 ≥ 0.80 才算通过
- 置信度映射：margin = top1_prob - top2_prob；`>= 0.40 → high`，`0.15 ≤ margin < 0.40 → medium`，`< 0.15 → low`

---

## Task 1: 训练子项目骨架 + 数据集 schema + 标注手册

**Files:**
- Create: `backend/training/retrieval_strategy_classifier/__init__.py` (empty)
- Create: `backend/training/retrieval_strategy_classifier/data/__init__.py` (empty)
- Create: `backend/training/retrieval_strategy_classifier/data/dataset.py`
- Create: `backend/training/retrieval_strategy_classifier/data/LABELING.md`
- Create: `backend/training/retrieval_strategy_classifier/data/raw/.gitkeep`
- Create: `backend/training/retrieval_strategy_classifier/data/labeled/.gitkeep`
- Create: `backend/training/retrieval_strategy_classifier/data/splits/.gitkeep`
- Create: `tests/unit/test_training_dataset.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `dataset.build_input_text(query, intent, event, themes, target, time_scope, session_topic) -> str`（被 Task 5 / Task 7 共用）
- Produces: `dataset.LABEL_TO_INDEX = {"event_primary": 0, "disclosure_primary": 1, "dual_primary": 2}` 与 `INDEX_TO_LABEL` 反向映射

- [ ] **Step 1: 写失败的测试 `test_training_dataset.py`**

```python
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TRAINING_ROOT = REPO_ROOT / "backend" / "training" / "retrieval_strategy_classifier"
for candidate in (REPO_ROOT, TRAINING_ROOT):
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m unittest tests.unit.test_training_dataset -v`
Expected: `ModuleNotFoundError: No module named 'finsight_agent_training'`

- [ ] **Step 3: 创建目录骨架和 .gitkeep**

创建以下空文件：
- `backend/training/retrieval_strategy_classifier/__init__.py`（空）
- `backend/training/retrieval_strategy_classifier/data/__init__.py`（空）
- `backend/training/retrieval_strategy_classifier/data/raw/.gitkeep`（空）
- `backend/training/retrieval_strategy_classifier/data/labeled/.gitkeep`（空）
- `backend/training/retrieval_strategy_classifier/data/splits/.gitkeep`（空）

`backend/training/retrieval_strategy_classifier/` 目录需手动创建。

- [ ] **Step 4: 实现 `data/dataset.py`**

```python
from __future__ import annotations

from typing import Iterable

LABEL_TO_INDEX: dict[str, int] = {
    "event_primary": 0,
    "disclosure_primary": 1,
    "dual_primary": 2,
}

INDEX_TO_LABEL: dict[int, str] = {idx: label for label, idx in LABEL_TO_INDEX.items()}

DEFAULT_FIELD = "无"


def build_input_text(
    *,
    query: str,
    intent: str,
    event: str,
    themes: Iterable[str],
    target: str,
    time_scope: str,
    session_topic: str,
) -> str:
    """拼接喂给 StructBERT 的序列化模板。

    任何字段为空字符串 / 空列表 / None 一律填 ``"无"``，确保序列结构稳定。
    """
    parts: list[str] = [
        f"[QUERY] {query}",
        f"[INTENT] {intent or DEFAULT_FIELD}",
        f"[EVENT] {event or DEFAULT_FIELD}",
        f"[THEMES] {', '.join(themes) if themes else DEFAULT_FIELD}",
        f"[TARGET] {target or DEFAULT_FIELD}",
        f"[TIME_SCOPE] {time_scope or DEFAULT_FIELD}",
        f"[SESSION_TOPIC] {session_topic or DEFAULT_FIELD}",
    ]
    return " ".join(parts)
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m unittest tests.unit.test_training_dataset -v`
Expected: 3 passed

- [ ] **Step 6: 创建 `data/LABELING.md`**

```markdown
# 检索策略分类器标注手册

## 任务目标

给定用户 query + router_result + 可选 session_topic，判断 `collect_event_context` 应采取的检索起手式：

- `event_primary`：优先查事件搜索层
- `disclosure_primary`：优先查披露搜索层
- `dual_primary`：双主源

## 主判定问题

1. 这个 query 首先要不要先理解外部事件本身？
2. 这个 query 首先要不要先看公司 / 公告 / 披露？
3. 这两个是否都明显必需？

## 判定准则

### 标 `event_primary`

满足以下任一倾向：

- 不先理解事件就无法开展后续分析
- query 没有明显单公司公告中心
- 公司层只是后续可能扩展，不是第一步主问题

示例：
- `红海局势最近怎么了`
- `美国新关税政策主要影响哪些方向`

### 标 `disclosure_primary`

满足以下任一倾向：

- query 本身就是公司内生事项
- 主语已明确落在公司披露
- 不需要先大量补充外部事件背景

示例：
- `宁德时代扩产公告意味着什么`
- `某公司业绩预告是否超预期`

### 标 `dual_primary`

满足以下任一倾向：

- query 同时在问外部事件 + A 股 / 公司影响
- 任意单源都明显不够
- 若只看外部新闻或只看披露，都会丢失关键上下文

示例：
- `红海局势升级利好哪些A股航运股`
- `关税升级对哪些出口链公司冲击最大`

## 边界处理

- 模糊 query：按"首个必要检索动作"判断
- 同等必要 → 标 `dual_primary`
- **不允许** `unknown` / `other` 这两类标签

## 标签字段

每条样本除 `query` 外必须包含以下结构化字段（缺失写空字符串或空列表，不省略 key）：

- `intent`：路由意图
- `event`：query 解析出的事件
- `themes`：相关主题列表
- `target`：query 中的目标对象（公司 / 板块 / 行业）
- `time_scope`：时间范围
- `session_topic`：当前会话主题（首版样本默认空字符串）

## 复核流程

1. 首标
2. 复标抽检（≥10%）
3. 分歧样本入冲突池
4. 最终裁决并沉淀到本手册

`label_source` 字段填 `human_authored` 或 `human_reviewed`。
```

- [ ] **Step 7: 更新 `.gitignore`**

在 `.gitignore` 末尾追加：

```
# retrieval strategy classifier artifacts
var/models/**
backend/training/retrieval_strategy_classifier/artifacts/**
*.bin
*.safetensors
tokenizer.json
```

- [ ] **Step 8: 提交**

```bash
git add backend/training/retrieval_strategy_classifier tests/unit/test_training_dataset.py docs/superpowers/specs/2026-07-07-retrieval-strategy-classifier-training-design.md .gitignore
git commit -m "feat(training): 搭建检索策略分类器训练子项目骨架"
```

---

## Task 2: 训练数据汇集与人工标注（300+ 条）

**Files:**
- Create: `backend/training/retrieval_strategy_classifier/data/labeled/labeled.jsonl`
- Modify: `tests/unit/test_training_dataset.py`（加 schema 校验测试）

**Interfaces:**
- Produces: `data/labeled/labeled.jsonl` —— 至少 300 条 JSONL 样本，每条字段见 spec §1.1

- [ ] **Step 1: 写 schema 校验测试**

在 `tests/unit/test_training_dataset.py` 末尾追加：

```python
class LabeledDatasetSchemaTest(unittest.TestCase):
    def test_labeled_jsonl_has_required_fields_per_row(self) -> None:
        import json
        from pathlib import Path

        path = (
            REPO_ROOT
            / "backend"
            / "training"
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m unittest tests.unit.test_training_dataset.LabeledDatasetSchemaTest -v`
Expected: FAIL（文件不存在）

- [ ] **Step 3: 写 A 阶段——从现有源直转 ~21 条**

写一个一次性脚本（不入库） `backend/training/retrieval_strategy_classifier/data/raw/_seed_a.py` 暂存辅助转换；本步骤**直接在最终文件里手工写**：

`backend/training/retrieval_strategy_classifier/data/labeled/labeled.jsonl` 前 21 行，从以下来源 1:1 转换：
- `backend/src/finsight_agent/evaluation/event_eval/fixtures/event_cases_v1.jsonl`（6 条，`expected_strategy` → `label`，`label_source="transferred_from_event_eval"`，sample_id 前缀 `rsc_evt_`）
- `tests/integration/test_event_impact_analysis_flow.py` 中 `tests/integration` 下的代表性 query（~3 条，`label_source="human_authored"`）
- `docs/superpowers/specs/2026-07-02-dual-source-event-context-retrieval-design.md` 第 4 节"dual_primary 适用"等示例 query（~12 条，`label_source="human_authored"`）

每行格式严格遵循 spec §1.1 schema：

```json
{"sample_id":"rsc_evt_001","query":"红海局势升级利好哪些A股航运股？","intent":"event_impact_analysis","event":"红海局势升级","themes":["航运","油运"],"target":"A股航运股","time_scope":"recent","session_topic":"","label":"dual_primary","label_source":"transferred_from_event_eval","notes":"来自 event_cases_v1.jsonl event_dual_001"}
```

- [ ] **Step 4: 写 B 阶段——从仓库历史 query 池人工补 ~30 条**

从仓库已有测试 query + design doc 例子 + 你记得的历史调试 query 中挑选 ~30 条，按 `LABELING.md` 准则逐条标 `label` 和 `label_source="human_authored"`，追加到 `labeled.jsonl`。

- [ ] **Step 5: 写 C 阶段——paraphrase 模板新写 ~270 条**

按以下分布目标新写：

| 标签 | 目标新增条数 | 总目标 |
|---|---|---|
| `event_primary` | ~80 | ~100 |
| `disclosure_primary` | ~80 | ~100 |
| `dual_primary` | ~80 | ~100 |
| **小计** | ~240 | ~270（连同 A+B 共 300+） |

Paraphrase 维度（每类都要覆盖）：
- 公司：宁德时代 / 中远海能 / 招商轮船 / 比亚迪 / 茅台 / 中芯国际 / 隆基绿能
- 行业：航运 / 油运 / 消费电子 / 光伏 / 半导体 / 白酒 / 新能源车 / 医药
- 事件：红海 / 关税 / 油价 / 地缘冲突 / 行业监管 / 财报季
- 问法变体：`利好哪些 / 冲击哪些 / 影响哪些 / 受益标的 / 受损标的 / 哪家 / 哪些 / 表现如何 / 后续怎么看`

写入时 `label_source="human_authored"`。

- [ ] **Step 6: 跑 schema 校验测试确认通过**

Run: `python -m unittest tests.unit.test_training_dataset.LabeledDatasetSchemaTest -v`
Expected: PASS（≥300 条）

- [ ] **Step 7: 手动检查类别分布**

Run:

```bash
python -c "
import json
from pathlib import Path
from collections import Counter
p = Path('backend/training/retrieval_strategy_classifier/data/labeled/labeled.jsonl')
labels = Counter(json.loads(line)['label'] for line in p.read_text(encoding='utf-8').splitlines() if line.strip())
print(labels)
total = sum(labels.values())
for lbl in ('event_primary','disclosure_primary','dual_primary'):
    pct = 100 * labels[lbl] / total
    assert 25 <= pct <= 50, f'class {lbl} out of balance: {pct:.1f}%'
print('OK: all classes within 25-50%')
"
```

Expected: `Counter({'event_primary': N1, 'disclosure_primary': N2, 'dual_primary': N3})` 且 `OK`。

- [ ] **Step 8: 提交**

```bash
git add backend/training/retrieval_strategy_classifier/data/labeled/labeled.jsonl tests/unit/test_training_dataset.py
git commit -m "feat(training): 完成检索策略分类器 300+ 条标注数据"
```

---

## Task 3: 数据切分脚本（确定性 train/val/test）

**Files:**
- Create: `backend/training/retrieval_strategy_classifier/scripts/__init__.py` (empty)
- Create: `backend/training/retrieval_strategy_classifier/scripts/build_dataset.py`
- Modify: `tests/unit/test_training_dataset.py`

**Interfaces:**
- Produces: `scripts.build_dataset.build_splits(labeled_path: Path, splits_dir: Path) -> dict[str, int]` —— 写 `train.jsonl / val.jsonl / test.jsonl` 并返回条数 dict

- [ ] **Step 1: 写切分测试**

在 `tests/unit/test_training_dataset.py` 末尾追加：

```python
class DatasetSplitTest(unittest.TestCase):
    def _splits_dir(self) -> Path:
        return (
            REPO_ROOT
            / "backend"
            / "training"
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
            / "retrieval_strategy_classifier"
            / "data"
            / "labeled"
            / "labeled.jsonl"
        )
        splits_dir = self._splits_dir()
        counts = build_splits(labeled_path=labeled_path, splits_dir=splits_dir)
        self.assertEqual(set(counts.keys()), {"train", "val", "test"})
        self.assertEqual(sum(counts.values()), 300)

        sample_ids: dict[str, str] = {}
        for partition in ("train", "val", "test"):
            p = splits_dir / f"{partition}.jsonl"
            self.assertTrue(p.exists(), f"missing {p}")
            with p.open("r", encoding="utf-8") as fh:
                for line in fh:
                    row = json.loads(line.strip())
                    sid = row["sample_id"]
                    self.assertNotIn(sid, sample_ids, f"{sid} appears in multiple partitions")
                    sample_ids[sid] = partition

    def test_split_deterministic_by_sample_id_mod100(self) -> None:
        """切分规则: sample_id 后两位整数 mod 100; <10->test, <25->val, else train."""
        import json
        from finsight_agent_training.retrieval_strategy_classifier.scripts.build_dataset import (
            build_splits,
        )

        labeled_path = (
            REPO_ROOT
            / "backend"
            / "training"
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m unittest tests.unit.test_training_dataset.DatasetSplitTest -v`
Expected: `ModuleNotFoundError: No module named 'finsight_agent_training.retrieval_strategy_classifier.scripts'`

- [ ] **Step 3: 创建 scripts 包**

- `backend/training/retrieval_strategy_classifier/scripts/__init__.py`（空）

- [ ] **Step 4: 实现 `scripts/build_dataset.py`**

```python
from __future__ import annotations

import json
from pathlib import Path


def _partition_for_sample_id(sample_id: str) -> str:
    """按 sample_id 后两位整数 mod 100 切分。

    < 10  -> test
    < 25  -> val
    else  -> train
    """
    digits = ""
    for ch in reversed(sample_id):
        if ch.isdigit():
            digits = ch + digits
            if len(digits) >= 2:
                break
        else:
            digits = ""
    if not digits:
        # 数字后缀缺失的样本归入 train，避免被静默丢弃
        return "train"
    bucket = int(digits[-2:]) % 100
    if bucket < 10:
        return "test"
    if bucket < 25:
        return "val"
    return "train"


def build_splits(*, labeled_path: Path, splits_dir: Path) -> dict[str, int]:
    """读取 labeled.jsonl，按 sample_id 切分并写入 splits_dir。

    返回 ``{"train": N, "val": N, "test": N}``。
    """
    splits_dir.mkdir(parents=True, exist_ok=True)

    buckets: dict[str, list[str]] = {"train": [], "val": [], "test": []}
    with labeled_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            partition = _partition_for_sample_id(row["sample_id"])
            buckets[partition].append(line)

    for partition, rows in buckets.items():
        out = splits_dir / f"{partition}.jsonl"
        out.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")

    return {partition: len(rows) for partition, rows in buckets.items()}


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[3]
    labeled = repo_root / "backend" / "training" / "retrieval_strategy_classifier" / "data" / "labeled" / "labeled.jsonl"
    out_dir = labeled.parent / "splits"
    counts = build_splits(labeled_path=labeled, splits_dir=out_dir)
    print(f"splits written: {counts}")
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m unittest tests.unit.test_training_dataset.DatasetSplitTest -v`
Expected: 2 passed

- [ ] **Step 6: 跑切分脚本生成 train/val/test**

Run: `python backend/training/retrieval_strategy_classifier/scripts/build_dataset.py`
Expected: `splits written: {'train': ~250, 'val': ~30, 'test': ~30}`

- [ ] **Step 7: 提交**

```bash
git add backend/training/retrieval_strategy_classifier/scripts tests/unit/test_training_dataset.py
git commit -m "feat(training): 增加数据集确定性切分脚本"
```

---

## Task 4: 预训练模型下载脚本

**Files:**
- Create: `backend/training/retrieval_strategy_classifier/scripts/download_pretrained.py`
- Create: `backend/training/retrieval_strategy_classifier/tests/__init__.py` (empty) — 用来放训练侧脚本的轻量测试，不走主测试发现
- Create: `backend/training/retrieval_strategy_classifier/tests/test_download_path.py`
- Modify: `.gitignore` 确认 `var/models/**` 已包含

**Interfaces:**
- Produces: `scripts.download_pretrained.resolve_pretrained_dir(env_var: str = "STRUCTBERT_PRETRAINED_DIR") -> Path` —— 返回默认 `repo_root / "var" / "models" / "pretrained" / "structbert-base-zh"`

- [ ] **Step 1: 写路径解析测试**

```python
# backend/training/retrieval_strategy_classifier/tests/test_download_path.py
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
TRAINING_ROOT = REPO_ROOT / "backend" / "training" / "retrieval_strategy_classifier"
for candidate in (REPO_ROOT, TRAINING_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


class ResolvePretrainedDirTest(unittest.TestCase):
    def test_default_path_under_var_models(self) -> None:
        from finsight_agent_training.retrieval_strategy_classifier.scripts.download_pretrained import (
            resolve_pretrained_dir,
        )

        path = resolve_pretrained_dir()
        self.assertTrue(str(path).endswith("var/models/pretrained/structbert-base-zh"))
        self.assertTrue(str(path).startswith(str(REPO_ROOT)))
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m unittest backend.training.retrieval_strategy_classifier.tests.test_download_path -v`
Expected: `ModuleNotFoundError`

- [ ] **Step 3: 实现 `scripts/download_pretrained.py`**

```python
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_MODEL_NAME = "alibaba-pai/structbert-base-zh"


def resolve_pretrained_dir(*, env_var: str = "STRUCTBERT_PRETRAINED_DIR") -> Path:
    """解析预训练模型本地缓存目录。

    优先级:
      1. ``$STRUCTBERT_PRETRAINED_DIR`` 环境变量
      2. ``<repo_root>/var/models/pretrained/structbert-base-zh`` 默认路径
    """
    override = os.environ.get(env_var)
    if override:
        return Path(override)
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "var" / "models" / "pretrained" / "structbert-base-zh"


def download_pretrained(
    *,
    model_name: str = DEFAULT_MODEL_NAME,
    target_dir: Path | None = None,
) -> Path:
    """从 HuggingFace 下载预训练模型到本地目录。

    仅在首次训练或预训练模型缺失时调用；产物已被 ``.gitignore`` 排除。
    """
    target = target_dir or resolve_pretrained_dir()
    target.mkdir(parents=True, exist_ok=True)

    try:
        from transformers import AutoModel, AutoTokenizer  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "transformers is required for download_pretrained; "
            "pip install transformers torch"
        ) from exc

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)
    tokenizer.save_pretrained(target)
    model.save_pretrained(target)
    return target


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="下载 StructBERT 中文 base 到本地")
    parser.add_argument("--model-name", default=DEFAULT_MODEL_NAME)
    parser.add_argument("--target-dir", default=None)
    args = parser.parse_args()

    target = Path(args.target_dir) if args.target_dir else None
    out = download_pretrained(model_name=args.model_name, target_dir=target)
    print(f"downloaded to {out}")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m unittest backend.training.retrieval_strategy_classifier.tests.test_download_path -v`
Expected: 1 passed

- [ ] **Step 5: 人工本地下载预训练模型（CI/本地首次必跑）**

Run: `python backend/training/retrieval_strategy_classifier/scripts/download_pretrained.py`
Expected: 在 `var/models/pretrained/structbert-base-zh/` 出现 config.json / pytorch_model.bin / vocab.txt 等。

- [ ] **Step 6: 提交（不含模型权重）**

```bash
git add backend/training/retrieval_strategy_classifier/scripts/download_pretrained.py backend/training/retrieval_strategy_classifier/tests
git commit -m "feat(training): 增加 StructBERT 预训练模型下载脚本"
```

---

## Task 5: 训练脚本（微调 StructBERT 三分类）

**Files:**
- Create: `backend/training/retrieval_strategy_classifier/scripts/train.py`
- Create: `backend/training/retrieval_strategy_classifier/tests/test_train_meta.py`

**Interfaces:**
- Produces: `artifacts/classifier_v1/` 目录（不 commit），含 `config.json` / `pytorch_model.bin` / `tokenizer.json` / `labels.json` / `training_meta.json`
- Produces: `scripts.train.TrainingArtifacts` —— `model_dir: Path` + `meta: dict`

- [ ] **Step 1: 写 training_meta 单元测试**

```python
# backend/training/retrieval_strategy_classifier/tests/test_train_meta.py
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
TRAINING_ROOT = REPO_ROOT / "backend" / "training" / "retrieval_strategy_classifier"
for candidate in (REPO_ROOT, TRAINING_ROOT):
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
                metrics={"val_accuracy": 0.87, "val_macro_f1": 0.86},
                git_commit="abcdef",
            )
            meta_path = out_dir / "training_meta.json"
            self.assertTrue(meta_path.exists())
            payload = json.loads(meta_path.read_text(encoding="utf-8"))
            for key in ("lr", "epochs", "batch_size", "val_accuracy", "val_macro_f1", "git_commit", "trained_at"):
                self.assertIn(key, payload)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m unittest backend.training.retrieval_strategy_classifier.tests.test_train_meta -v`
Expected: `ModuleNotFoundError`

- [ ] **Step 3: 实现 `scripts/train.py`**

```python
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .build_dataset import _partition_for_sample_id  # noqa: SLF001  — 共用切分逻辑
from ..data.dataset import INDEX_TO_LABEL, LABEL_TO_INDEX, build_input_text

DEFAULT_ARTIFACTS_SUBDIR = Path("backend/training/retrieval_strategy_classifier/artifacts/classifier_v1")


@dataclass(slots=True)
class TrainingArtifacts:
    model_dir: Path
    meta: dict[str, object]


def _load_split_rows(split_path: Path) -> Iterable[dict[str, object]]:
    with split_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _encode_example(row: dict[str, object], tokenizer) -> dict[str, object]:
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
        max_length=128,
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
    params: dict[str, object],
    metrics: dict[str, object],
    git_commit: str,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        **params,
        **metrics,
        "git_commit": git_commit,
        "trained_at": datetime.now(tz=timezone.utc).isoformat(),
        "labels": INDEX_TO_LABEL,
    }
    out_path = out_dir / "training_meta.json"
    out_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def _current_git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return ""


def train(
    *,
    pretrained_dir: Path,
    splits_dir: Path,
    artifacts_dir: Path,
    epochs: int = 5,
    batch_size: int = 16,
    learning_rate: float = 2e-5,
    warmup_ratio: float = 0.1,
    weight_decay: float = 0.01,
    seed: int = 42,
) -> TrainingArtifacts:
    """离线微调 StructBERT 三分类，产出 artifacts_dir。"""
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

    train_rows = list(_load_split_rows(splits_dir / "train.jsonl"))
    val_rows = list(_load_split_rows(splits_dir / "val.jsonl"))

    class _Dataset(Dataset):
        def __len__(self) -> int:
            return len(train_rows)

        def __getitem__(self, idx: int) -> dict[str, object]:
            return _encode_example(train_rows[idx], tokenizer)

    class _ValDataset(Dataset):
        def __init__(self) -> None:
            self._rows = val_rows
            self._encoded = [_encode_example(row, tokenizer) for row in val_rows]

        def __len__(self) -> int:
            return len(self._encoded)

        def __getitem__(self, idx: int) -> dict[str, object]:
            return self._encoded[idx]

    train_loader = DataLoader(_Dataset(), batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(_ValDataset(), batch_size=batch_size)

    optim = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=weight_decay)
    total_steps = max(1, len(train_loader) * epochs)
    scheduler = get_linear_schedule_with_warmup(
        optim,
        num_warmup_steps=int(total_steps * warmup_ratio),
        num_training_steps=total_steps,
    )

    best_val_acc = -1.0
    best_epoch = -1
    patience = 0
    best_metrics: dict[str, object] = {}

    for epoch in range(epochs):
        model.train()
        train_loss = 0.0
        for batch in train_loader:
            optim.zero_grad()
            outputs = model(
                input_ids=batch["input_ids"],
                attention_mask=batch["attention_mask"],
                labels=batch["labels"],
            )
            outputs.loss.backward()
            optim.step()
            scheduler.step()
            train_loss += float(outputs.loss.detach())

        model.eval()
        correct = 0
        total = 0
        with torch.no_grad():
            for batch in val_loader:
                logits = model(
                    input_ids=batch["input_ids"],
                    attention_mask=batch["attention_mask"],
                ).logits
                preds = torch.argmax(logits, dim=-1)
                correct += int((preds == batch["labels"]).sum())
                total += int(batch["labels"].size(0))

        val_acc = correct / total if total else 0.0
        train_loss /= max(1, len(train_loader))
        print(f"epoch {epoch + 1}/{epochs} train_loss={train_loss:.4f} val_acc={val_acc:.4f}")

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
            if patience >= 2:
                print("early stopping")
                break

    if best_epoch < 0:
        raise RuntimeError("training produced no usable checkpoint")

    meta_path = save_training_meta(
        out_dir=artifacts_dir,
        params={
            "epochs": epochs,
            "batch_size": batch_size,
            "lr": learning_rate,
            "warmup_ratio": warmup_ratio,
            "weight_decay": weight_decay,
            "seed": seed,
        },
        metrics=best_metrics,
        git_commit=_current_git_commit(),
    )

    return TrainingArtifacts(model_dir=artifacts_dir, meta=json.loads(meta_path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    import argparse

    repo_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description="微调 StructBERT 检索策略分类器")
    parser.add_argument("--pretrained-dir", default=str(repo_root / "var" / "models" / "pretrained" / "structbert-base-zh"))
    parser.add_argument("--splits-dir", default=str(repo_root / "backend" / "training" / "retrieval_strategy_classifier" / "data" / "splits"))
    parser.add_argument("--artifacts-dir", default=str(repo_root / "backend" / "training" / "retrieval_strategy_classifier" / "artifacts" / "classifier_v1"))
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()

    result = train(
        pretrained_dir=Path(args.pretrained_dir),
        splits_dir=Path(args.splits_dir),
        artifacts_dir=Path(args.artifacts_dir),
        epochs=args.epochs,
        batch_size=args.batch_size,
    )
    print(f"training complete -> {result.model_dir}")
```

- [ ] **Step 4: 跑训练脚本产 meta 验证**

Run: `python backend/training/retrieval_strategy_classifier/scripts/train.py --epochs 1`
Expected: 训练跑完；`backend/training/retrieval_strategy_classifier/artifacts/classifier_v1/training_meta.json` 存在并含 `lr/epochs/batch_size/val_accuracy/git_commit/trained_at/labels` 键。

- [ ] **Step 5: 跑训练 meta 测试确认通过**

Run: `python -m unittest backend.training.retrieval_strategy_classifier.tests.test_train_meta -v`
Expected: 1 passed

- [ ] **Step 6: 提交（不包含模型权重）**

```bash
git add backend/training/retrieval_strategy_classifier/scripts/train.py backend/training/retrieval_strategy_classifier/tests
git commit -m "feat(training): 增加 StructBERT 微调训练脚本"
```

---

## Task 6: 离线评测脚本（CI gate）

**Files:**
- Create: `backend/training/retrieval_strategy_classifier/scripts/evaluate.py`
- Create: `backend/training/retrieval_strategy_classifier/scripts/export_model.py`
- Create: `backend/training/retrieval_strategy_classifier/tests/test_evaluate_gate.py`

**Interfaces:**
- Produces: `scripts.evaluate.run_evaluation(artifacts_dir: Path, splits_dir: Path) -> dict` —— 返回 `accuracy / per_class / confusion / baseline_match_rate`
- Produces: `scripts.evaluate.gate_passes(metrics: dict, *, min_accuracy: float = 0.85, min_f1: float = 0.80) -> bool`
- Produces: `scripts.export_model.export_model(artifacts_dir: Path, target_dir: Path) -> Path` —— copy artifact 到运行时加载路径

- [ ] **Step 1: 写评测 gate 测试（用 mock 模型输出）**

```python
# backend/training/retrieval_strategy_classifier/tests/test_evaluate_gate.py
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
TRAINING_ROOT = REPO_ROOT / "backend" / "training" / "retrieval_strategy_classifier"
for candidate in (REPO_ROOT, TRAINING_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


class EvaluateGateTest(unittest.TestCase):
    def test_gate_passes_when_metrics_above_thresholds(self) -> None:
        from finsight_agent_training.retrieval_strategy_classifier.scripts.evaluate import (
            gate_passes,
        )

        metrics = {
            "accuracy": 0.87,
            "per_class_f1": {"event_primary": 0.86, "disclosure_primary": 0.85, "dual_primary": 0.84},
        }
        self.assertTrue(gate_passes(metrics))

    def test_gate_fails_when_accuracy_below_threshold(self) -> None:
        from finsight_agent_training.retrieval_strategy_classifier.scripts.evaluate import (
            gate_passes,
        )

        metrics = {
            "accuracy": 0.80,
            "per_class_f1": {"event_primary": 0.85, "disclosure_primary": 0.85, "dual_primary": 0.85},
        }
        self.assertFalse(gate_passes(metrics))

    def test_gate_fails_when_any_class_f1_below_threshold(self) -> None:
        from finsight_agent_training.retrieval_strategy_classifier.scripts.evaluate import (
            gate_passes,
        )

        metrics = {
            "accuracy": 0.90,
            "per_class_f1": {"event_primary": 0.85, "disclosure_primary": 0.85, "dual_primary": 0.70},
        }
        self.assertFalse(gate_passes(metrics))
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m unittest backend.training.retrieval_strategy_classifier.tests.test_evaluate_gate -v`
Expected: `ModuleNotFoundError`

- [ ] **Step 3: 实现 `scripts/evaluate.py`**

```python
from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..data.dataset import INDEX_TO_LABEL, LABEL_TO_INDEX


@dataclass(slots=True)
class EvalMetrics:
    accuracy: float
    per_class_f1: dict[str, float]
    confusion: list[list[int]]
    baseline_match_rate: float


def _load_split(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _predict_labels(
    rows: Iterable[dict[str, object]],
    *,
    model_dir: Path,
) -> list[int]:
    try:
        import torch  # type: ignore
        from transformers import AutoModelForSequenceClassification, AutoTokenizer  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("transformers + torch required") from exc

    from ..data.dataset import build_input_text

    tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
    model = AutoModelForSequenceClassification.from_pretrained(str(model_dir))
    model.eval()

    preds: list[int] = []
    with torch.no_grad():
        for row in rows:
            text = build_input_text(
                query=str(row.get("query", "")),
                intent=str(row.get("intent", "")),
                event=str(row.get("event", "") or ""),
                themes=list(row.get("themes", []) or []),
                target=str(row.get("target", "") or ""),
                time_scope=str(row.get("time_scope", "") or ""),
                session_topic=str(row.get("session_topic", "") or ""),
            )
            inputs = tokenizer(text, truncation=True, max_length=128, return_tensors="pt")
            logits = model(**inputs).logits
            preds.append(int(torch.argmax(logits, dim=-1).item()))
    return preds


def _stub_predict(rows: Iterable[dict[str, object]]) -> list[int]:
    """Stub baseline 永远预测 event_primary (index 0)。"""
    return [LABEL_TO_INDEX["event_primary"] for _ in rows]


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def _compute_metrics(true_idxs: list[int], pred_idxs: list[int]) -> tuple[float, dict[str, float], list[list[int]]]:
    n_labels = len(LABEL_TO_INDEX)
    confusion = [[0 for _ in range(n_labels)] for _ in range(n_labels)]
    for t, p in zip(true_idxs, pred_idxs):
        confusion[t][p] += 1

    total = len(true_idxs)
    accuracy = _safe_div(sum(1 for t, p in zip(true_idxs, pred_idxs) if t == p), total)

    per_class_f1: dict[str, float] = {}
    for label, idx in LABEL_TO_INDEX.items():
        tp = confusion[idx][idx]
        fp = sum(confusion[r][idx] for r in range(n_labels)) - tp
        fn = sum(confusion[idx][c] for c in range(n_labels)) - tp
        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        per_class_f1[label] = _safe_div(2 * precision * recall, precision + recall)

    return accuracy, per_class_f1, confusion


def run_evaluation(*, artifacts_dir: Path, splits_dir: Path) -> EvalMetrics:
    test_rows = _load_split(splits_dir / "test.jsonl")
    true_idxs = [LABEL_TO_INDEX[str(row["label"])] for row in test_rows]

    pred_idxs = _predict_labels(test_rows, model_dir=artifacts_dir)
    accuracy, per_class_f1, confusion = _compute_metrics(true_idxs, pred_idxs)

    stub_idxs = _stub_predict(test_rows)
    baseline_match = _safe_div(
        sum(1 for t, p in zip(true_idxs, stub_idxs) if t == p),
        len(true_idxs),
    )

    return EvalMetrics(
        accuracy=accuracy,
        per_class_f1=per_class_f1,
        confusion=confusion,
        baseline_match_rate=baseline_match,
    )


def gate_passes(
    metrics: EvalMetrics | dict,
    *,
    min_accuracy: float = 0.85,
    min_f1: float = 0.80,
) -> bool:
    if isinstance(metrics, dict):
        accuracy = float(metrics["accuracy"])
        per_class = dict(metrics["per_class_f1"])
    else:
        accuracy = metrics.accuracy
        per_class = metrics.per_class_f1

    if accuracy < min_accuracy:
        return False
    return all(f1 >= min_f1 for f1 in per_class.values())


def _format_report(metrics: EvalMetrics) -> str:
    lines = [
        f"accuracy       = {metrics.accuracy:.4f}",
        f"baseline (stub) match rate = {metrics.baseline_match_rate:.4f}",
        "per-class F1:",
    ]
    for label, f1 in metrics.per_class_f1.items():
        lines.append(f"  {label:18s} {f1:.4f}")
    lines.append("confusion matrix (rows=true, cols=pred):")
    labels = [INDEX_TO_LABEL[i] for i in range(len(INDEX_TO_LABEL))]
    lines.append(f"  {'':18s} " + " ".join(f"{lbl[:8]:>8s}" for lbl in labels))
    for i, row in enumerate(metrics.confusion):
        lines.append(f"  {labels[i]:18s} " + " ".join(f"{v:>8d}" for v in row))
    return "\n".join(lines)


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[3]
    artifacts = repo_root / "backend" / "training" / "retrieval_strategy_classifier" / "artifacts" / "classifier_v1"
    splits = repo_root / "backend" / "training" / "retrieval_strategy_classifier" / "data" / "splits"
    metrics = run_evaluation(artifacts_dir=artifacts, splits_dir=splits)
    print(_format_report(metrics))
    sys.exit(0 if gate_passes(metrics) else 1)
```

- [ ] **Step 4: 实现 `scripts/export_model.py`**

```python
from __future__ import annotations

import shutil
from pathlib import Path


def export_model(*, artifacts_dir: Path, target_dir: Path) -> Path:
    """把训练产物拷贝到运行时加载路径。

    ``target_dir`` 默认 ``<repo_root>/var/models/retrieval_strategy_classifier/v1/``；
    拷贝保留 transformers 标准目录结构。
    """
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(artifacts_dir, target_dir)
    return target_dir


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[3]
    artifacts = repo_root / "backend" / "training" / "retrieval_strategy_classifier" / "artifacts" / "classifier_v1"
    target = repo_root / "var" / "models" / "retrieval_strategy_classifier" / "v1"
    out = export_model(artifacts_dir=artifacts, target_dir=target)
    print(f"exported to {out}")
```

- [ ] **Step 5: 跑 gate 测试确认通过**

Run: `python -m unittest backend.training.retrieval_strategy_classifier.tests.test_evaluate_gate -v`
Expected: 3 passed

- [ ] **Step 6: 跑评测脚本（用 Task 5 训出的模型）**

Run: `python backend/training/retrieval_strategy_classifier/scripts/evaluate.py`
Expected: 输出 accuracy / per-class F1 / confusion matrix；exit code 0（如果达标）或 1（不达标）。首次 5 epoch 跑下来预期能 ≥0.85；若不达标，调学习率或继续补样本。

- [ ] **Step 7: 导出模型到运行时路径**

Run: `python backend/training/retrieval_strategy_classifier/scripts/export_model.py`
Expected: `var/models/retrieval_strategy_classifier/v1/` 出现 config.json / pytorch_model.bin / labels.json 等。

- [ ] **Step 8: 提交**

```bash
git add backend/training/retrieval_strategy_classifier/scripts/evaluate.py backend/training/retrieval_strategy_classifier/scripts/export_model.py backend/training/retrieval_strategy_classifier/tests
git commit -m "feat(training): 增加离线评测脚本与模型导出脚本"
```

---

## Task 7: 运行时推理类 `TrainedRetrievalStrategyClassifier`

**Files:**
- Create: `backend/src/finsight_agent/control_plane/orchestrator/trained_strategy_classifier.py`
- Create: `tests/unit/test_trained_strategy_classifier.py`

**Interfaces:**
- Produces: `TrainedRetrievalStrategyClassifier(model_dir=None, confidence_margin_high=0.40, confidence_margin_low=0.15, fallback=None)` —— 实现 `RetrievalStrategyClassifier` Protocol
- Produces: 三个新增 `source_status` 键：`strategy_reason` / `strategy_confidence` / `strategy_source`

- [ ] **Step 1: 写失败的测试（mock 模型）**

```python
# tests/unit/test_trained_strategy_classifier.py
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"
for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


class _FakeTokenizer:
    def __call__(self, text, *, truncation, max_length, return_tensors):
        return {"input_ids": [[0]], "attention_mask": [[1]]}


class _FakeModel:
    def __call__(self, *, input_ids, attention_mask):
        out = MagicMock()
        out.logits = MagicMock()
        return out


class TrainedClassifierTest(unittest.TestCase):
    def _build_with_mock_model(self, tmp, *, mock_logits):
        from finsight_agent.control_plane.orchestrator.trained_strategy_classifier import (
            TrainedRetrievalStrategyClassifier,
        )

        target = Path(tmp) / "fake_model"
        target.mkdir()

        # mock transformers so we don't actually need weights
        import finsight_agent.control_plane.orchestrator.trained_strategy_classifier as mod

        mod._LazyTransformer = MagicMock()  # type: ignore[attr-defined]
        mod._LazyTransformer.from_pretrained.return_value = (_FakeTokenizer(), _FakeModel())
        return TrainedRetrievalStrategyClassifier(model_dir=target)

    def test_uses_fallback_when_model_dir_missing(self) -> None:
        import tempfile

        from finsight_agent.control_plane.orchestrator.trained_strategy_classifier import (
            TrainedRetrievalStrategyClassifier,
        )
        from finsight_agent.control_plane.orchestrator.retrieval_strategy_classifier import (
            StubRetrievalStrategyClassifier,
        )

        fallback = StubRetrievalStrategyClassifier()
        clf = TrainedRetrievalStrategyClassifier(
            model_dir=Path("/nonexistent/path/that/does/not/exist"),
            fallback=fallback,
        )

        payload = clf.classify(
            query="红海局势升级利好哪些A股航运股？",
            router_payload={"intent": "event_impact_analysis"},
            session_topic="",
        )
        self.assertEqual(payload["strategy"], "event_primary")
        self.assertEqual(payload["confidence"], "low")
        self.assertEqual(payload["reason"], "stub_fallback")

    def test_classify_returns_valid_strategy_label(self) -> None:
        import tempfile
        import torch  # noqa: F401 — used by import inside classify

        import finsight_agent.control_plane.orchestrator.trained_strategy_classifier as mod

        # mock logits: dual_primary 概率最高
        # softmax over [1.0, 0.5, 2.0] -> argmax = 2 (dual_primary)
        mock_logits = MagicMock()
        mock_logits.__truediv__ = lambda self, other: mock_logits
        mock_logits.__getitem__ = lambda self, idx: mock_logits
        mock_logits.sum.return_value = 1.0
        mock_logits.softmax.return_value = MagicMock()
        mock_logits.argmax.return_value = MagicMock(item=MagicMock(return_value=2))

        with tempfile.TemporaryDirectory() as tmp:
            clf = self._build_with_mock_model(tmp, mock_logits=mock_logits)
            payload = clf.classify(
                query="红海局势升级利好哪些A股航运股？",
                router_payload={
                    "intent": "event_impact_analysis",
                    "entities": {"event": "红海局势升级", "themes": ["航运"], "target": "A股航运股"},
                },
                session_topic="",
            )
        self.assertIn(payload["strategy"], {"event_primary", "disclosure_primary", "dual_primary"})
        self.assertIn(payload["confidence"], {"high", "medium", "low"})
        self.assertIn("margin=", payload["reason"])

    def test_reason_includes_margin_and_top_labels(self) -> None:
        # 简化的契约测试 — 只验证 reason 字段格式
        import tempfile

        from finsight_agent.control_plane.orchestrator.trained_strategy_classifier import (
            TrainedRetrievalStrategyClassifier,
        )
        from finsight_agent.control_plane.orchestrator.retrieval_strategy_classifier import (
            StubRetrievalStrategyClassifier,
        )

        clf = TrainedRetrievalStrategyClassifier(
            model_dir=Path("/nonexistent/path/that/does/not/exist"),
            fallback=StubRetrievalStrategyClassifier(),
        )
        payload = clf.classify(
            query="x",
            router_payload={"intent": "event_impact_analysis"},
            session_topic="",
        )
        # fallback 路径：reason 必须是 stub_fallback
        self.assertEqual(payload["reason"], "stub_fallback")

    def test_lazy_load_only_happens_on_first_classify(self) -> None:
        import tempfile

        from finsight_agent.control_plane.orchestrator.trained_strategy_classifier import (
            TrainedRetrievalStrategyClassifier,
        )

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "fake_model"
            target.mkdir()
            clf = TrainedRetrievalStrategyClassifier(model_dir=target)
            self.assertFalse(clf._model_loaded)
            clf.classify(
                query="x",
                router_payload={"intent": "event_impact_analysis"},
                session_topic="",
            )
            # 首次 classify 后模型可能未真正加载（model_dir 可能缺 config.json），
            # 但 _degraded 应被设置
            self.assertTrue(clf._degraded or clf._model_loaded)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m unittest tests.unit.test_trained_strategy_classifier -v`
Expected: `ModuleNotFoundError: No module named 'finsight_agent.control_plane.orchestrator.trained_strategy_classifier'`

- [ ] **Step 3: 实现 `trained_strategy_classifier.py`**

```python
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from .retrieval_strategy_classifier import (
    DEFAULT_RETRIEVAL_STRATEGY,
    RETRIEVAL_STRATEGIES,
    RetrievalStrategyClassifier,
    StubRetrievalStrategyClassifier,
)

logger = logging.getLogger(__name__)

DEFAULT_RUNTIME_MODEL_DIRNAME = "var/models/retrieval_strategy_classifier/v1"
ENV_VAR = "RETRIEVAL_STRATEGY_MODEL_DIR"


def _resolve_model_dir(model_dir: str | Path | None) -> Path:
    """按优先级解析模型目录：
    1. ``__init__`` 参数
    2. ``$RETRIEVAL_STRATEGY_MODEL_DIR`` 环境变量
    3. ``<repo_root>/var/models/retrieval_strategy_classifier/v1/`` 默认
    """
    if model_dir is not None:
        return Path(model_dir)
    override = os.environ.get(ENV_VAR)
    if override:
        return Path(override)
    # repo_root = backend/src/finsight_agent/control_plane/orchestrator/trained_strategy_classifier.py
    # -> parents[5] = repo_root
    here = Path(__file__).resolve()
    repo_root = here.parents[5]
    return repo_root / DEFAULT_RUNTIME_MODEL_DIRNAME


class _LazyTransformer:
    """Lazy import wrapper — 只在真正需要时导入 transformers/torch。"""

    @classmethod
    def from_pretrained(cls, model_dir: str | Path):  # pragma: no cover - 真实模型路径
        from transformers import AutoModelForSequenceClassification, AutoTokenizer  # type: ignore

        tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
        model = AutoModelForSequenceClassification.from_pretrained(str(model_dir))
        return tokenizer, model


class TrainedRetrievalStrategyClassifier:
    """运行时分类器：懒加载 StructBERT 微调模型，任何异常回退到 stub。"""

    def __init__(
        self,
        *,
        model_dir: str | Path | None = None,
        confidence_margin_high: float = 0.40,
        confidence_margin_low: float = 0.15,
        fallback: RetrievalStrategyClassifier | None = None,
    ) -> None:
        self._model_dir = _resolve_model_dir(model_dir)
        self._confidence_margin_high = confidence_margin_high
        self._confidence_margin_low = confidence_margin_low
        self._fallback: RetrievalStrategyClassifier = fallback or StubRetrievalStrategyClassifier()
        self._tokenizer: Any | None = None
        self._model: Any | None = None
        self._label_to_index: dict[str, int] | None = None
        self._index_to_label: dict[int, str] | None = None
        self._degraded: bool = False
        self._model_loaded: bool = False

    @property
    def _is_degraded(self) -> bool:
        return self._degraded

    def _ensure_loaded(self) -> None:
        if self._model_loaded:
            return
        if not self._model_dir.exists():
            logger.warning(
                "strategy classifier model dir missing: %s — falling back to stub",
                self._model_dir,
            )
            self._degraded = True
            self._model_loaded = True
            return
        try:
            tokenizer, model = _LazyTransformer.from_pretrained(self._model_dir)
        except Exception as exc:
            logger.warning(
                "strategy classifier model load failed (%s) — falling back to stub",
                exc,
            )
            self._degraded = True
            self._model_loaded = True
            return

        labels_path = self._model_dir / "labels.json"
        if labels_path.exists():
            try:
                labels_payload = json.loads(labels_path.read_text(encoding="utf-8"))
                self._index_to_label = {int(k): v for k, v in labels_payload.items()}
                self._label_to_index = {v: k for k, v in self._index_to_label.items()}
            except Exception as exc:
                logger.warning("labels.json unreadable (%s) — falling back to stub", exc)
                self._degraded = True
                self._model_loaded = True
                return
        else:
            # fallback to spec convention if labels.json missing
            self._index_to_label = {0: "event_primary", 1: "disclosure_primary", 2: "dual_primary"}
            self._label_to_index = {v: k for k, v in self._index_to_label.items()}

        self._tokenizer = tokenizer
        self._model = model
        self._model.eval()
        self._model_loaded = True

    def _build_input(self, *, query: str, router_payload: dict[str, object], session_topic: str) -> str:
        entities = router_payload.get("entities") if isinstance(router_payload, dict) else None
        entities = entities if isinstance(entities, dict) else {}
        event = str(entities.get("event") or "")
        themes_raw = entities.get("themes") or []
        themes = [str(t) for t in themes_raw if t]
        target = str(entities.get("target") or "")
        time_scope = str(entities.get("time_scope") or "")
        intent = str(router_payload.get("intent") if isinstance(router_payload, dict) else "")

        from . import _shared_template  # noqa: WPS433 — local import to keep top-level light

        # 训练子项目下也有同一份模板函数；为避免 import 训练子项目（重型依赖），
        # 运行时复刻一份最小实现
        parts = [
            f"[QUERY] {query}",
            f"[INTENT] {intent or '无'}",
            f"[EVENT] {event or '无'}",
            f"[THEMES] {', '.join(themes) if themes else '无'}",
            f"[TARGET] {target or '无'}",
            f"[TIME_SCOPE] {time_scope or '无'}",
            f"[SESSION_TOPIC] {session_topic or '无'}",
        ]
        return " ".join(parts)

    def classify(
        self,
        *,
        query: str,
        router_payload: dict[str, object],
        session_topic: str,
    ) -> dict[str, str]:
        try:
            self._ensure_loaded()
        except Exception as exc:
            logger.warning("ensure_raised unexpectedly (%s) — falling back", exc)
            return self._fallback_payload(reason_extra=f"exception:{exc}")

        if self._degraded:
            return self._fallback_payload()

        try:
            import torch  # type: ignore
        except ImportError:
            logger.warning("torch not installed — falling back to stub")
            return self._fallback_payload()

        try:
            text = self._build_input(
                query=query, router_payload=router_payload, session_topic=session_topic,
            )
            inputs = self._tokenizer(
                text,
                truncation=True,
                max_length=128,
                return_tensors="pt",
            )
            with torch.no_grad():
                logits = self._model(**inputs).logits
            probs = torch.softmax(logits, dim=-1)[0]
            top1_idx = int(torch.argmax(probs).item())
            sorted_probs, sorted_idxs = torch.sort(probs, descending=True)
            top1_prob = float(sorted_probs[0].item())
            top2_prob = float(sorted_probs[1].item()) if len(sorted_probs) > 1 else 0.0
            margin = top1_prob - top2_prob
        except Exception as exc:
            logger.warning("inference failed (%s) — falling back to stub", exc)
            return self._fallback_payload(reason_extra=f"inference_exception:{exc}")

        label = self._index_to_label.get(top1_idx, DEFAULT_RETRIEVAL_STRATEGY)
        if label not in RETRIEVAL_STRATEGIES:
            logger.warning("model returned unknown label %s — falling back", label)
            return self._fallback_payload()

        if margin >= self._confidence_margin_high:
            confidence = "high"
        elif margin >= self._confidence_margin_low:
            confidence = "medium"
        else:
            confidence = "low"

        top1_label = self._index_to_label.get(sorted_idxs[0].item(), "?")
        top2_label = self._index_to_label.get(sorted_idxs[1].item(), "?") if len(sorted_idxs) > 1 else "?"
        reason = f"structbert:margin={margin:.3f};top1={top1_label};top2={top2_label}"

        return {
            "strategy": label,
            "confidence": confidence,
            "reason": reason,
        }

    def _fallback_payload(self, *, reason_extra: str | None = None) -> dict[str, str]:
        payload = self._fallback.classify(
            query="",
            router_payload={},
            session_topic="",
        )
        if reason_extra:
            payload["reason"] = f"stub_fallback:{reason_extra}"
        return payload
```

> 注：上面代码中故意未实际 import `_shared_template`；保留注释是为了标注：如果后续把训练 / 推理模板统一抽出到独立模块，应在这里替换。

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m unittest tests.unit.test_trained_strategy_classifier -v`
Expected: 4 passed

- [ ] **Step 5: 跑现有 stub / protocol 测试确认未破**

Run: `python -m unittest tests.unit.test_external_context_retriever -v`
Expected: 4 passed（不动）

- [ ] **Step 6: 提交**

```bash
git add backend/src/finsight_agent/control_plane/orchestrator/trained_strategy_classifier.py tests/unit/test_trained_strategy_classifier.py
git commit -m "feat(orchestrator): 增加 TrainedRetrievalStrategyClassifier 运行时推理类"
```

---

## Task 8: service.py 装配改造 + trace 透传

**Files:**
- Modify: `backend/src/finsight_agent/control_plane/orchestrator/service.py:155-163`
- Modify: `backend/src/finsight_agent/control_plane/orchestrator/dual_source_context_retriever.py:47-87`
- Create: `tests/unit/test_dual_source_strategy_trace.py`

**Interfaces:**
- Modifies: `_build_default_external_context_retriever()` 默认装配 `TrainedRetrievalStrategyClassifier(fallback=StubRetrievalStrategyClassifier())`
- Modifies: `DualSourceExternalContextRetriever.retrieve_event_context()` 在 `source_status` 中追加 `strategy_reason` / `strategy_confidence` / `strategy_source`

- [ ] **Step 1: 写 trace 透传测试**

```python
# tests/unit/test_dual_source_strategy_trace.py
from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"
for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


from finsight_agent.control_plane.orchestrator.context_retrieval_models import (
    ExternalContextResult,
)
from finsight_agent.control_plane.orchestrator.dual_source_context_retriever import (
    DualSourceExternalContextRetriever,
)


class _StubEventProvider:
    def __init__(self, result):
        self.result = result

    def search_event_context(self, **kwargs):
        del kwargs
        return self.result


class _StubDisclosureProvider:
    def __init__(self, result):
        self.result = result

    def search(self, **kwargs):
        del kwargs
        return self.result


class _StubClassifier:
    def __init__(self, payload):
        self._payload = payload

    def classify(self, *, query, router_payload, session_topic):
        del query, router_payload, session_topic
        return self._payload


class DualSourceStrategyTraceTest(unittest.TestCase):
    def test_source_status_includes_strategy_metadata(self) -> None:
        classifier = _StubClassifier(
            {"strategy": "dual_primary", "confidence": "high", "reason": "structbert:margin=0.5;top1=dual_primary;top2=event_primary"}
        )
        planner = _StubPlanner = type(
            "_StubPlanner",
            (),
            {
                "build_plan": staticmethod(
                    lambda *, strategy_payload, router_payload: type(
                        "Plan",
                        (),
                        {
                            "mode": "dual_primary",
                            "steps": [
                                {"source": "event_search", "budget": 1},
                                {"source": "disclosure_search", "budget": 1},
                            ],
                            "allow_local_rag": False,
                        },
                    )()
                )
            },
        )
        event_provider = _StubEventProvider(
            ExternalContextResult(summary_hint="事件背景", evidence_refs=["bocha:1"])
        )
        disclosure_provider = _StubDisclosureProvider(
            ExternalContextResult(
                candidate_hints=["中远海能"], evidence_refs=["cninfo:1"]
            )
        )

        retriever = DualSourceExternalContextRetriever(
            classifier=classifier,
            planner=planner,
            event_search_provider=event_provider,
            disclosure_search_provider=disclosure_provider,
        )

        result = retriever.retrieve_event_context(
            query="红海局势升级利好哪些A股航运股？",
            event="红海局势升级",
            themes=["航运"],
            time_scope="recent",
            limit=3,
        )
        status = result["source_status"]
        self.assertEqual(status["strategy_confidence"], "high")
        self.assertIn("structbert:margin=0.5", status["strategy_reason"])
        self.assertEqual(status["strategy_source"], "trained")
        self.assertEqual(status["mode"], "dual_primary")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m unittest tests.unit.test_dual_source_strategy_trace -v`
Expected: `KeyError: 'strategy_confidence'`（因为 source_status 当前不含这字段）

- [ ] **Step 3: 修改 `dual_source_context_retriever.py`**

把 `retrieve_event_context` 中

```python
strategy_payload = self._classifier.classify(
    query=query,
    router_payload=router_payload,
    session_topic="",
)
plan = self._planner.build_plan(
    strategy_payload=strategy_payload,
    router_payload=router_payload,
)

merged = ExternalContextResult(
    source_status={
        "mode": plan.mode or DEFAULT_RETRIEVAL_STRATEGY,
        "allow_local_rag": plan.allow_local_rag,
    }
)
```

替换为：

```python
strategy_payload = self._classifier.classify(
    query=query,
    router_payload=router_payload,
    session_topic="",
)
plan = self._planner.build_plan(
    strategy_payload=strategy_payload,
    router_payload=router_payload,
)

strategy_source = (
    "trained"
    if not strategy_payload.get("reason", "").startswith("stub_fallback")
    else "stub_fallback"
)
merged = ExternalContextResult(
    source_status={
        "mode": plan.mode or DEFAULT_RETRIEVAL_STRATEGY,
        "allow_local_rag": plan.allow_local_rag,
        "strategy_confidence": str(strategy_payload.get("confidence") or "low"),
        "strategy_reason": str(strategy_payload.get("reason") or ""),
        "strategy_source": strategy_source,
    }
)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m unittest tests.unit.test_dual_source_strategy_trace -v`
Expected: 1 passed

- [ ] **Step 5: 跑现有 external_context_retriever 测试确认未破**

Run: `python -m unittest tests.unit.test_external_context_retriever -v`
Expected: 4 passed

- [ ] **Step 6: 修改 `service.py`**

把 `_build_default_external_context_retriever()` 中：

```python
classifier=StubRetrievalStrategyClassifier(),
```

替换为：

```python
classifier=TrainedRetrievalStrategyClassifier(
    fallback=StubRetrievalStrategyClassifier(),
),
```

并在文件顶部 import 区块添加：

```python
from .trained_strategy_classifier import TrainedRetrievalStrategyClassifier
```

- [ ] **Step 7: 跑全部相关单元测试确认全绿**

Run: `python -m unittest tests.unit.test_external_context_retriever tests.unit.test_trained_strategy_classifier tests.unit.test_dual_source_strategy_trace -v`
Expected: 9 passed

- [ ] **Step 8: 提交**

```bash
git add backend/src/finsight_agent/control_plane/orchestrator/service.py backend/src/finsight_agent/control_plane/orchestrator/dual_source_context_retriever.py tests/unit/test_dual_source_strategy_trace.py
git commit -m "feat(orchestrator): 装配 TrainedRetrievalStrategyClassifier 并透传策略元数据"
```

---

## Task 9: 数据切分测试 + 集成测试（默认 skip）

**Files:**
- Modify: `tests/unit/test_training_dataset.py` — 加切分测试已在 Task 3 完成，确认存在
- Create: `tests/integration/test_strategy_classifier_e2e.py`

**Interfaces:**
- Produces: `tests/integration/test_strategy_classifier_e2e.py:test_real_model_meets_minimum_accuracy_on_test_set`（默认 skip，env 守护）

- [ ] **Step 1: 写集成测试**

```python
# tests/integration/test_strategy_classifier_e2e.py
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"
TRAINING_ROOT = REPO_ROOT / "backend" / "training" / "retrieval_strategy_classifier"
for candidate in (REPO_ROOT, BACKEND_SRC_ROOT, TRAINING_ROOT):
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
        artifacts = repo_root / "var" / "models" / "retrieval_strategy_classifier" / "v1"
        splits = repo_root / "backend" / "training" / "retrieval_strategy_classifier" / "data" / "splits"

        self.assertTrue(artifacts.exists(), f"missing model at {artifacts}; run export_model.py first")
        self.assertTrue((splits / "test.jsonl").exists())

        metrics = run_evaluation(artifacts_dir=artifacts, splits_dir=splits)
        self.assertTrue(
            gate_passes(metrics),
            f"gate failed: accuracy={metrics.accuracy}, f1={metrics.per_class_f1}",
        )
```

- [ ] **Step 2: 默认确认集成测试 skip**

Run: `python -m unittest tests.integration.test_strategy_classifier_e2e -v`
Expected: SKIP（环境变量未设置）

- [ ] **Step 3: 验证守护启用后能跑（人工本地）**

Run: `RUN_STRATEGY_MODEL_E2E=1 python -m unittest tests.integration.test_strategy_classifier_e2e -v`
Expected: PASS（前提是 Task 6 已 export model 且 evaluate 达 gate）

- [ ] **Step 4: 提交**

```bash
git add tests/integration/test_strategy_classifier_e2e.py
git commit -m "test(orchestrator): 增加检索策略分类器 E2E 集成测试（默认 skip）"
```

---

## Task 10: 全量回归 + .gitignore 复检 + 中文 PR

**Files:**
- Modify: `.gitignore`（如需）
- Modify: `docs/finsight/project-status.md`（如需，更新 §状态）
- Create: `var/models/` 本地目录（不 commit）

- [ ] **Step 1: 全量跑测试**

Run: `python -m unittest discover -s tests -v 2>&1 | tail -20`
Expected: 全绿；之前 227 → 现在 ≥ 240 通过（含本轮新增 13–15 个单测 + 1 个 skip 的集成测试）

若发现 fail，按错误回滚到对应任务修复。

- [ ] **Step 2: 复检 .gitignore**

Run: `git status --short`
Expected: 未追踪文件不应包含 `var/models/**` 或 `*.bin` / `*.safetensors` / `tokenizer.json` / `artifacts/**`。

如发现被追踪，从 git index 移除：
```bash
git rm --cached -r var/models/ backend/training/retrieval_strategy_classifier/artifacts/
```

- [ ] **Step 3: 更新 `docs/finsight/project-status.md`（可选）**

在 FinSight 项目状态文档中追加一条：

```markdown
- 检索策略分类器已从 stub 升级为微调 StructBERT（`TrainedRetrievalStrategyClassifier`），
  训练数据 300+ 条，CI gate 要求 test acc ≥ 0.85；失败回退到 stub，行为与现状等价。
```

- [ ] **Step 4: 中文 commit（最后整理）**

如有未提交改动：

```bash
git add docs/finsight/project-status.md
git commit -m "docs(finsight): 更新项目状态，记录检索策略分类器训练落地"
```

- [ ] **Step 5: 推分支并发中文 PR**

```bash
git push origin main
gh pr create --base main --title "feat(orchestrator): 检索策略分类器训练 + 接入" --body "$(cat <<'EOF'
## 背景

`StubRetrievalStrategyClassifier` 永远返回 `event_primary`，主流程从未真正按 query 分布选择 `event_primary` / `disclosure_primary` / `dual_primary`。本 PR 把控制面的策略决策从 stub 升级到真实训练的分类器。

## 主要改动

1. **训练子项目**：`backend/training/retrieval_strategy_classifier/`
   - 300+ 条人工标注样本（`event_primary` / `disclosure_primary` / `dual_primary` 三类均衡）
   - 数据切分（按 sample_id 后两位 mod 100；train/val/test）
   - 训练脚本：`download_pretrained.py` → `train.py` → `evaluate.py` → `export_model.py`
   - CI gate：test acc ≥ 0.85 且 per-class F1 ≥ 0.80
2. **运行时推理**：`trained_strategy_classifier.py`
   - 懒加载 StructBERT 微调模型
   - 失败回退到 `StubRetrievalStrategyClassifier`（行为与现状完全等价）
   - 任何异常（缺 transformers / 模型未下载 / forward 抛错 / label 非法 / 超时）都走 fallback
3. **装配改造**：`service.py:159` 改为 `TrainedRetrievalStrategyClassifier(fallback=Stub())`
4. **trace 透传**：`source_status` 字典新增 `strategy_reason` / `strategy_confidence` / `strategy_source` 三个键
5. **测试**：13–15 个新单测 + 1 个默认 skip 的集成测试（env `RUN_STRATEGY_MODEL_E2E=1` 守护）

## 不变量

- `RetrievalStrategyClassifier` Protocol / `StubRetrievalStrategyClassifier` / `RETRIEVAL_STRATEGIES` / `DEFAULT_RETRIEVAL_STRATEGY` 完全不变
- 现有 227 个测试全绿（已验证）
- 不修改 `DualSourceExternalContextRetriever` / `ContextRetrievalPlanner` 主契约
- 不动 `DisclosureSearchProvider` / Bocha 相关 `EventSearchProvider`

## 测试方法

```bash
# 全量单测
python -m unittest discover -s tests -v

# 离线评测（CI gate）
python backend/training/retrieval_strategy_classifier/scripts/evaluate.py

# E2E 集成测试（默认 skip）
RUN_STRATEGY_MODEL_E2E=1 python -m unittest tests.integration.test_strategy_classifier_e2e -v
```

## 风险

- 模型权重依赖 HF 下载；首次训练 / CI 需先跑 `download_pretrained.py`
- 训练产物（`*.bin` / `artifacts/**` / `var/models/**`）已加入 `.gitignore`，不进入版本控制
EOF
)"
```

---

## Self-Review Checklist

执行计划前自检：

- [x] **Spec 覆盖**：背景/目标/非目标/现状判断/设计原则/架构/组件/数据流/降级语义/衔接/实施顺序/成功标准 — 全部映射到 10 个任务
- [x] **Placeholder 扫描**：所有步骤含实际代码或命令；无 TBD/TODO
- [x] **类型一致**：`build_input_text`、`LABEL_TO_INDEX`、`INDEX_TO_LABEL`、`TrainedRetrievalStrategyClassifier`、`build_splits`、`run_evaluation`、`gate_passes`、`export_model` 在不同任务间签名一致
- [x] **失败回退**：Task 7 + Task 8 都覆盖 fallback 语义
- [x] **现有测试不破**：Task 7 步骤 5 + Task 8 步骤 5/7 都明确要求跑既有测试
- [x] **中文 commit**：Task 1–10 全部使用中文 commit message
- [x] **权重不 commit**：Task 1 step 7 + Task 10 step 2 双重把关 `.gitignore`