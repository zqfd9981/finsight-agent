from __future__ import annotations

from contextlib import closing
import json
import time
from pathlib import Path

from qdrant_client.http import models as qdrant_models

from finsight_agent.infra.embeddings.bge_m3 import BgeM3EmbeddingProvider
from finsight_agent.infra.vector_store.qdrant_store import QdrantStore

from .models import DenseHit, DenseSearchFilters


class DenseChunkIndex:
    """基于本地 Qdrant 的 child chunk dense 索引。"""

    def __init__(
        self,
        storage_path: Path | str,
        collection_name: str,
        embedding_provider: BgeM3EmbeddingProvider,
    ) -> None:
        self._store = QdrantStore(storage_path=storage_path)
        self._collection_name = collection_name
        self._embedding_provider = embedding_provider

    def rebuild_from_chunk_root(self, chunk_root: Path) -> int:
        """从 chunked_filings 全量重建 Qdrant dense 索引。

        只索引 ``__rag`` 后缀的目录：这些是 page_filter 产出的 MinerU 解析、
        叙述性文本切片（财务三表已进 SQLite，不重复入向量库）。
        """

        self._store.recreate_collection(
            collection_name=self._collection_name,
            vector_dim=self._embedding_provider.vector_dim,
        )

        indexed_count = 0
        point_id = 1
        t0 = time.time()
        all_files = sorted(chunk_root.glob("*/children.jsonl"))
        # 只保留 __rag 目录（MinerU 解析的 2025 年报叙述性切片）
        files = [f for f in all_files if f.parent.name.endswith("__rag")]
        total_files = len(files)
        skipped = len(all_files) - total_files
        print(
            f"  共 {len(all_files)} 个 children.jsonl，"
            f"筛选 __rag 目录: {total_files} 个，跳过 {skipped} 个",
            flush=True,
        )

        for file_idx, children_path in enumerate(files, 1):
            rows = self._read_jsonl(children_path)
            if not rows:
                continue
            payloads = [self._normalize_chunk_row(row) for row in rows]

            # 分批 embedding（CPU 模式，批大小 64 匹配模型内部 batch）
            batch_size = 64
            all_vectors: list[list[float]] = []
            for batch_start in range(0, len(payloads), batch_size):
                batch = payloads[batch_start:batch_start + batch_size]
                batch_vectors = self._embedding_provider.embed(
                    [str(p["chunk_text"]) for p in batch]
                )
                all_vectors.extend(batch_vectors)

            points: list[qdrant_models.PointStruct] = []
            for payload, vector in zip(payloads, all_vectors, strict=True):
                points.append(
                    qdrant_models.PointStruct(
                        id=point_id,
                        vector=vector,
                        payload=payload,
                    )
                )
                indexed_count += 1
                point_id += 1
            if points:
                self._store.client.upsert(
                    collection_name=self._collection_name,
                    points=points,
                    wait=True,
                )
            # 每 5 个文件打一次进度
            if file_idx % 5 == 0 or file_idx == total_files:
                elapsed = time.time() - t0
                speed = indexed_count / elapsed if elapsed > 0 else 0
                eta = (total_files - file_idx) * (elapsed / file_idx) if file_idx > 0 else 0
                print(
                    f"  [{file_idx}/{total_files}] {indexed_count} chunks, "
                    f"{speed:.0f} chunk/s, ETA {eta:.0f}s",
                    flush=True,
                )
        return indexed_count

    def search(
        self,
        query_text: str,
        limit: int,
        filters: DenseSearchFilters | None = None,
        query_variant: str = "original",
    ) -> list[DenseHit]:
        """执行 top-k dense 搜索，并回表成统一命中结构。"""

        stripped_query = query_text.strip()
        if not stripped_query:
            return []

        vector = self._embedding_provider.embed([stripped_query])[0]
        response = self._store.client.query_points(
            collection_name=self._collection_name,
            query=vector,
            query_filter=_build_filter(filters),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )

        hits: list[DenseHit] = []
        for point in response.points:
            payload = dict(point.payload or {})
            hits.append(
                DenseHit(
                    chunk_id=str(payload["chunk_id"]),
                    document_id=str(payload["document_id"]),
                    parent_id=str(payload["parent_id"]),
                    company_code=str(payload["company_code"]),
                    company_name=str(payload["company_name"]),
                    doc_type=str(payload["doc_type"]),
                    report_year=int(payload["report_year"]),
                    publish_date=str(payload["publish_date"]),
                    page_start=int(payload["page_start"]),
                    page_end=int(payload["page_end"]),
                    page_anchor=int(payload["page_anchor"])
                    if payload.get("page_anchor") is not None
                    else None,
                    section_path=list(payload.get("section_path", []) or []),
                    chunk_text=str(payload.get("chunk_text", "")),
                    dense_score=float(point.score or 0.0),
                    query_variant=query_variant,
                )
            )
        return hits

    def close(self) -> None:
        """关闭本地 Qdrant 连接，便于测试和临时目录清理。"""

        self._store.close()

    def _normalize_chunk_row(self, row: dict[str, object]) -> dict[str, object]:
        """把 children.jsonl 记录映射成 Qdrant payload。"""

        document_id = str(row.get("document_id", ""))
        company_code, company_name, doc_type, report_year, publish_date = _parse_document_id(
            document_id
        )
        return {
            "chunk_id": str(row.get("chunk_id", "")),
            "document_id": document_id,
            "parent_id": str(row.get("parent_id", "")),
            "company_code": company_code,
            "company_name": company_name,
            "doc_type": doc_type,
            "report_year": int(report_year) if str(report_year).isdigit() else 0,
            "publish_date": publish_date,
            "page_start": int(row.get("page_start", 0) or 0),
            "page_end": int(row.get("page_end", 0) or 0),
            "page_anchor": int(row.get("page_anchor", 0) or 0),
            "section_path": list(row.get("section_path", []) or []),
            "chunk_text": str(row.get("chunk_text", "")),
            "embedding_model_version": self._embedding_provider.model_version,
        }

    def _read_jsonl(self, path: Path) -> list[dict[str, object]]:
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


def _build_filter(filters: DenseSearchFilters | None) -> qdrant_models.Filter | None:
    """把最小 metadata 过滤条件映射成 Qdrant filter。"""

    if filters is None:
        return None

    conditions: list[qdrant_models.FieldCondition] = []
    if filters.company_code:
        conditions.append(
            qdrant_models.FieldCondition(
                key="company_code",
                match=qdrant_models.MatchValue(value=filters.company_code),
            )
        )
    if filters.doc_type:
        conditions.append(
            qdrant_models.FieldCondition(
                key="doc_type",
                match=qdrant_models.MatchValue(value=filters.doc_type),
            )
        )
    if filters.report_year is not None:
        conditions.append(
            qdrant_models.FieldCondition(
                key="report_year",
                match=qdrant_models.MatchValue(value=filters.report_year),
            )
        )
    if not conditions:
        return None
    return qdrant_models.Filter(must=conditions)


def _parse_document_id(document_id: str) -> tuple[str, str, str, str, str]:
    """从 document_id 中解析公司、文档类型和日期字段。"""

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
    if len(middle_parts) >= 2 and _looks_like_company_name(middle_parts[0]):
        company_name = middle_parts[0]
        doc_type = "_".join(middle_parts[1:])
    else:
        company_name = ""
        doc_type = "_".join(middle_parts)
    return company_code, company_name, doc_type, report_year, publish_date


def _looks_like_company_name(value: str) -> bool:
    """用轻量启发式判断 document_id 中是否显式带了公司名。"""

    return any("\u4e00" <= character <= "\u9fff" for character in value)
