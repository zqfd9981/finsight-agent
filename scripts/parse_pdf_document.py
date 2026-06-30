from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.retrieval.chunking import build_chunks
from finsight_agent.capabilities.retrieval.parsed_storage import (
    write_chunk_artifact,
    write_parsed_artifact,
)
from finsight_agent.capabilities.retrieval.parsing_service import build_parsing_service
from finsight_agent.config.settings import load_settings


def run_parse_document(argv: list[str] | None = None) -> int:
    """执行单份 PDF 的解析与切块，并输出摘要 JSON。"""

    parser = argparse.ArgumentParser(description="Parse a local PDF and emit parsed/chunked artifacts.")
    parser.add_argument("--pdf-path", required=True, help="待解析 PDF 的本地路径")
    args = parser.parse_args(argv)

    settings = load_settings()
    parsing_service = build_parsing_service()
    pdf_path = Path(args.pdf_path)

    artifact = parsing_service.parse_document(pdf_path)
    parsed_output_dir = write_parsed_artifact(settings.retrieval.parsed_filings_root, artifact)
    parser_version = (
        artifact.parse_report.parser_version if artifact.parse_report is not None else "unknown"
    )
    chunking_result = build_chunks(
        document_id=str(artifact.document["document_id"]),
        elements=artifact.elements,
        parser_version=parser_version,
        parent_target_chars=settings.retrieval.parent_target_chars,
        child_target_chars=settings.retrieval.child_target_chars,
    )
    chunk_output_dir = write_chunk_artifact(
        root=settings.retrieval.chunked_filings_root,
        document_id=str(artifact.document["document_id"]),
        parents=chunking_result.parents,
        children=chunking_result.children,
        chunk_report={
            "document_id": artifact.document["document_id"],
            "chunker_version": "chunker_v1",
            "parent_count": len(chunking_result.parents),
            "child_count": len(chunking_result.children),
            "warnings": [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    print(
        json.dumps(
            {
                "document_id": artifact.document["document_id"],
                "parsed_output_dir": str(parsed_output_dir),
                "chunk_output_dir": str(chunk_output_dir),
                "parent_count": len(chunking_result.parents),
                "child_count": len(chunking_result.children),
            },
            ensure_ascii=False,
        )
    )
    return 0


def main() -> int:
    return run_parse_document()


if __name__ == "__main__":
    raise SystemExit(main())
