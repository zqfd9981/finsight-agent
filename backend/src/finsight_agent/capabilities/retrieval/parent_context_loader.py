from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class ParentChunkRecord:
    """从 `parents.jsonl` 读取的最小 parent 记录。"""

    chunk_id: str
    chunk_text: str
    page_start: int
    page_end: int
    section_path: list[str] = field(default_factory=list)


class ParentContextLoader:
    """从本地 chunk 产物中按需回填真实 parent context。"""

    def __init__(self, chunked_filings_root: Path) -> None:
        self._chunked_filings_root = chunked_filings_root
        self._cache: dict[str, dict[str, ParentChunkRecord]] = {}

    def load_parent(
        self,
        document_id: str,
        parent_id: str | None,
    ) -> ParentChunkRecord | None:
        if not parent_id:
            return None

        records = self._load_document_parents(document_id)
        return records.get(parent_id)

    def _load_document_parents(self, document_id: str) -> dict[str, ParentChunkRecord]:
        cached = self._cache.get(document_id)
        if cached is not None:
            return cached

        parents_path = self._chunked_filings_root / document_id / "parents.jsonl"
        if not parents_path.exists():
            self._cache[document_id] = {}
            return self._cache[document_id]

        records: dict[str, ParentChunkRecord] = {}
        with parents_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue

                payload = json.loads(line)
                record = ParentChunkRecord(
                    chunk_id=str(payload.get("chunk_id", "")),
                    chunk_text=str(payload.get("chunk_text", "")),
                    page_start=int(payload.get("page_start", 0)),
                    page_end=int(payload.get("page_end", 0)),
                    section_path=list(payload.get("section_path", []) or []),
                )
                if record.chunk_id:
                    records[record.chunk_id] = record

        # 按文档缓存 parent，避免重复读取 JSONL。
        self._cache[document_id] = records
        return records
