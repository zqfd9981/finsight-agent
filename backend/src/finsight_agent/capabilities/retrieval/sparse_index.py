from __future__ import annotations

from contextlib import closing
import json
import sqlite3
from pathlib import Path

from .models import SparseChunkHit, SparseSearchFilters


class SparseChunkIndex:
    """基于 SQLite FTS5 的本地 child chunk 稀疏索引。"""

    def __init__(self, index_path: Path) -> None:
        self._index_path = index_path

    def rebuild_from_chunk_root(self, chunk_root: Path) -> int:
        """从 `chunked_filings/*/children.jsonl` 全量重建稀疏索引。"""

        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self._index_path)) as connection:
            self._recreate_schema(connection)
            indexed_count = 0
            for children_path in sorted(chunk_root.glob("*/children.jsonl")):
                for row in self._read_jsonl(children_path):
                    payload = self._normalize_chunk_row(row)
                    self._insert_chunk(connection, payload)
                    indexed_count += 1
            connection.commit()
        return indexed_count

    def search(
        self,
        query_text: str,
        limit: int,
        filters: SparseSearchFilters | None = None,
    ) -> list[SparseChunkHit]:
        """执行关键词检索，并把命中 chunk 回表成标准结果。"""

        if not query_text.strip():
            return []

        effective_filters = filters or SparseSearchFilters()
        normalized_query = _normalize_match_query(query_text)
        sql = """
SELECT
  chunks.chunk_id,
  chunks.document_id,
  chunks.parent_id,
  chunks.company_code,
  chunks.company_name,
  chunks.doc_type,
  chunks.report_year,
  chunks.publish_date,
  chunks.page_start,
  chunks.page_end,
  chunks.page_anchor,
  chunks.section_path_json,
  chunks.chunk_text,
  bm25(chunk_fts) AS bm25_score
FROM chunk_fts
JOIN chunks ON chunks.chunk_id = chunk_fts.chunk_id
WHERE chunk_fts MATCH ?
"""
        parameters: list[object] = [normalized_query]

        if effective_filters.company_code:
            sql += " AND chunks.company_code = ?"
            parameters.append(effective_filters.company_code)
        if effective_filters.doc_type:
            sql += " AND chunks.doc_type = ?"
            parameters.append(effective_filters.doc_type)

        sql += " ORDER BY bm25_score LIMIT ?"
        parameters.append(limit)

        with closing(sqlite3.connect(self._index_path)) as connection:
            rows = connection.execute(sql, parameters).fetchall()

        return [
            SparseChunkHit(
                chunk_id=str(row[0]),
                document_id=str(row[1]),
                parent_id=str(row[2]) if row[2] is not None else None,
                company_code=str(row[3]),
                company_name=str(row[4]),
                doc_type=str(row[5]),
                report_year=str(row[6]),
                publish_date=str(row[7]),
                page_start=int(row[8]),
                page_end=int(row[9]),
                page_anchor=int(row[10]),
                section_path=json.loads(str(row[11])) if row[11] else [],
                chunk_text=str(row[12]),
                bm25_score=float(row[13]),
            )
            for row in rows
        ]

    def _recreate_schema(self, connection: sqlite3.Connection) -> None:
        """重建主表和 FTS5 虚表，保证每次导入都是干净状态。"""

        connection.executescript(
            """
DROP TABLE IF EXISTS chunk_fts;
DROP TABLE IF EXISTS chunks;

CREATE TABLE chunks (
  chunk_id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL,
  parent_id TEXT,
  company_code TEXT NOT NULL,
  company_name TEXT NOT NULL,
  doc_type TEXT NOT NULL,
  report_year TEXT NOT NULL,
  publish_date TEXT NOT NULL,
  page_start INTEGER NOT NULL,
  page_end INTEGER NOT NULL,
  page_anchor INTEGER NOT NULL,
  section_path_json TEXT NOT NULL,
  chunk_text TEXT NOT NULL
);

CREATE VIRTUAL TABLE chunk_fts USING fts5(
  chunk_id UNINDEXED,
  chunk_text,
  tokenize = 'trigram'
);
"""
        )

    def _insert_chunk(
        self,
        connection: sqlite3.Connection,
        payload: dict[str, object],
    ) -> None:
        """把单条 child chunk 同时写入主表和 FTS5 虚表。"""

        connection.execute(
            """
INSERT INTO chunks (
  chunk_id,
  document_id,
  parent_id,
  company_code,
  company_name,
  doc_type,
  report_year,
  publish_date,
  page_start,
  page_end,
  page_anchor,
  section_path_json,
  chunk_text
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""",
            (
                payload["chunk_id"],
                payload["document_id"],
                payload["parent_id"],
                payload["company_code"],
                payload["company_name"],
                payload["doc_type"],
                payload["report_year"],
                payload["publish_date"],
                payload["page_start"],
                payload["page_end"],
                payload["page_anchor"],
                payload["section_path_json"],
                payload["chunk_text"],
            ),
        )
        connection.execute(
            "INSERT INTO chunk_fts (chunk_id, chunk_text) VALUES (?, ?)",
            (payload["chunk_id"], payload["chunk_text"]),
        )

    def _normalize_chunk_row(self, row: dict[str, object]) -> dict[str, object]:
        """把 children.jsonl 中的原始行映射成索引层统一 payload。"""

        document_id = str(row.get("document_id", ""))
        company_code, company_name, doc_type, report_year, publish_date = _parse_document_id(
            document_id
        )
        return {
            "chunk_id": str(row.get("chunk_id", "")),
            "document_id": document_id,
            "parent_id": str(row.get("parent_id")) if row.get("parent_id") is not None else None,
            "company_code": company_code,
            "company_name": company_name,
            "doc_type": doc_type,
            "report_year": report_year,
            "publish_date": publish_date,
            "page_start": int(row.get("page_start", 0) or 0),
            "page_end": int(row.get("page_end", 0) or 0),
            "page_anchor": int(row.get("page_anchor", 0) or 0),
            "section_path_json": json.dumps(row.get("section_path", []) or [], ensure_ascii=False),
            "chunk_text": str(row.get("chunk_text", "")),
        }

    def _read_jsonl(self, path: Path) -> list[dict[str, object]]:
        """读取单个 JSONL 文件中的全部 child chunk 记录。"""

        rows: list[dict[str, object]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                if isinstance(payload, dict):
                    rows.append(payload)
        return rows


def _parse_document_id(document_id: str) -> tuple[str, str, str, str, str]:
    """从现有 document_id 中解析公司、文档类型和日期字段。"""

    parts = document_id.split("_")
    if len(parts) < 4:
        raise ValueError(f"invalid document_id: {document_id}")
    company_code = parts[0]

    report_year_index = len(parts) - 2
    for index in range(1, len(parts) - 1):
        if parts[index].isdigit() and len(parts[index]) == 4:
            report_year_index = index
            break

    report_year = parts[report_year_index]
    publish_date = parts[-1]

    middle_parts = parts[1:report_year_index]
    # 兼容两种 document_id：
    # 1. <code>_<name>_<doc_type>_<year>_<date>
    # 2. <code>_<doc_type>_<year>_<date>
    if len(middle_parts) >= 2 and _looks_like_company_name(middle_parts[0]):
        company_name = middle_parts[0]
        doc_type = "_".join(middle_parts[1:])
    else:
        company_name = ""
        doc_type = "_".join(middle_parts)
    return company_code, company_name, doc_type, report_year, publish_date


def _looks_like_company_name(value: str) -> bool:
    """用很轻的启发式判断 document_id 中是否显式带了公司名。"""

    return any("\u4e00" <= character <= "\u9fff" for character in value)


def _normalize_match_query(query_text: str) -> str:
    """把用户查询规整成首版 trigram FTS5 可接受的 MATCH 表达式。"""

    sanitized = query_text.strip().replace('"', " ").replace("'", " ")
    return f'"{sanitized}"'
