from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .models import MetricQuery, MetricRecord


class MetricRepository:
    """基于本地 JSONL 的轻量指标仓储。"""

    def __init__(self, storage_dir: str | Path) -> None:
        self._storage_dir = Path(storage_dir)
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._records_path = self._storage_dir / "metric_records.jsonl"

    def save_records(self, records: list[MetricRecord]) -> None:
        with self._records_path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    def load_records(self) -> list[MetricRecord]:
        if not self._records_path.exists():
            return []

        records: list[MetricRecord] = []
        with self._records_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                records.append(MetricRecord(**json.loads(stripped)))
        return records

    def find_best_match(self, query: MetricQuery) -> MetricRecord | None:
        candidates = [
            record
            for record in self.load_records()
            if record.company_name == query.company_name
            and record.metric_name == query.metric_name
        ]
        if not candidates:
            return None

        if query.time_scope != "latest":
            for record in candidates:
                if record.time_scope == query.time_scope:
                    return record
            return None

        return sorted(candidates, key=lambda item: item.period_end, reverse=True)[0]
