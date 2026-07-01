from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from pathlib import Path

from .parsing_models import ChunkRecord, ParsedDocumentArtifact


def write_parsed_artifact(root: Path, artifact: ParsedDocumentArtifact) -> Path:
    """把单份文档的解析产物写入 `parsed_filings/<document_id>/`。"""

    document_id = str(artifact.document["document_id"])
    output_dir = root / document_id
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "document.json").write_text(
        json.dumps(artifact.document, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_jsonl(
        output_dir / "elements.jsonl",
        [asdict(element) for element in artifact.elements],
    )
    _write_jsonl(
        output_dir / "tables.jsonl",
        [asdict(table) for table in artifact.tables],
    )
    parse_report_payload = (
        asdict(artifact.parse_report) if artifact.parse_report is not None else {}
    )
    (output_dir / "parse_report.json").write_text(
        json.dumps(parse_report_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_dir


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    """按 JSONL 形式逐行写出记录。"""

    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


def write_chunk_artifact(
    root: Path,
    document_id: str,
    parents: list[ChunkRecord],
    children: list[ChunkRecord],
    chunk_report: dict[str, object],
) -> Path:
    """把单份文档的 chunk 产物写入 `chunked_filings/<document_id>/`。"""

    output_dir = root / document_id
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    _write_jsonl(output_dir / "parents.jsonl", [asdict(parent) for parent in parents])
    _write_jsonl(
        output_dir / "children.jsonl",
        [asdict(child) for child in children],
    )
    (output_dir / "chunk_report.json").write_text(
        json.dumps(chunk_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_dir
