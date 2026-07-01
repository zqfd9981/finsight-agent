from __future__ import annotations

import json
from pathlib import Path

from finsight_agent.capabilities.retrieval.parsing_models import ParsedTable

from .extractor import MetricExtractor
from .repository import MetricRepository


class StructuredMetricIndexBuilder:
    """扫描已解析财报目录并重建本地指标库。"""

    def __init__(self, *, parsed_filings_root: str | Path, storage_dir: str | Path) -> None:
        self._parsed_filings_root = Path(parsed_filings_root)
        self._repository = MetricRepository(storage_dir=storage_dir)
        self._extractor = MetricExtractor()

    def rebuild(self) -> None:
        records = []
        for document_path in self._parsed_filings_root.rglob("document.json"):
            tables_path = document_path.with_name("tables.jsonl")
            if not tables_path.exists():
                continue

            document_payload = json.loads(document_path.read_text(encoding="utf-8"))
            tables: list[ParsedTable] = []
            for line in tables_path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                tables.append(ParsedTable(**json.loads(stripped)))

            records.extend(
                self._extractor.extract_from_tables(
                    company_name=str(document_payload["company_name"]),
                    company_code=str(document_payload["company_code"]),
                    doc_type=str(document_payload["doc_type"]),
                    report_year=int(document_payload["report_year"]),
                    tables=tables,
                )
            )

        self._repository.save_records(records)
