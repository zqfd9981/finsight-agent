from __future__ import annotations

from pathlib import Path

from finsight_agent.capabilities.retrieval.parsing_models import (
    ParseReport,
    ParsedDocumentArtifact,
)


class MineruDocumentParser:
    """MinerU 主解析器占位实现。"""

    def parse(self, pdf_path: Path) -> ParsedDocumentArtifact:
        raise NotImplementedError("MinerU parser integration is not implemented yet")
