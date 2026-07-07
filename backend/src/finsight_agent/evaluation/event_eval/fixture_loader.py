from __future__ import annotations

import json
from pathlib import Path

from .models import EventEvalCase


def load_event_eval_cases(path: Path) -> list[EventEvalCase]:
    """从 JSONL fixture 读取事件评测样本。"""

    cases: list[EventEvalCase] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        cases.append(EventEvalCase.from_dict(payload))
    return cases
