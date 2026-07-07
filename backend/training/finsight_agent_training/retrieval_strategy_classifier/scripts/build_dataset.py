"""数据集构建与切分入口。

切分规则（确定性、可复现）：
- 提取 ``sample_id`` 末尾的数字后缀（最多 2 位），不足则补 ``00``；
- 不足 2 位的数字后缀等价于前导零，例如 ``rsc_000007`` 等价于 bucket ``7``；
- 若 sample_id 完全不含数字（如 ``rsc_unknown``），归入 ``train``，避免被静默丢弃；
- ``bucket = int(digits) % 100``，然后：
  - ``bucket < 10`` → ``test``
  - ``bucket < 25`` → ``val``
  - 其它 → ``train``
"""

from __future__ import annotations

import json
from pathlib import Path


def _partition_for_sample_id(sample_id: str) -> str:
    """按 sample_id 末两位数字 mod 100 切分。

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
    # scripts/build_dataset.py -> .../finsight_agent_training/retrieval_strategy_classifier/scripts/
    # parents[0]=scripts, [1]=retrieval_strategy_classifier, [2]=finsight_agent_training,
    # [3]=training, [4]=backend, [5]=repo_root
    repo_root = Path(__file__).resolve().parents[5]
    labeled = repo_root / "backend" / "training" / "finsight_agent_training" / "retrieval_strategy_classifier" / "data" / "labeled" / "labeled.jsonl"
    out_dir = labeled.parent / "splits"
    counts = build_splits(labeled_path=labeled, splits_dir=out_dir)
    print(f"splits written: {counts}")
