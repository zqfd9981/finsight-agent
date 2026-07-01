from __future__ import annotations

from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models


class QdrantStore:
    """本地 Qdrant 持久化存储适配层。"""

    def __init__(self, storage_path: Path | str) -> None:
        self._storage_path = storage_path
        if isinstance(storage_path, str) and storage_path == ":memory:":
            self._client = QdrantClient(path=":memory:")
        else:
            storage_root = Path(storage_path)
            storage_root.mkdir(parents=True, exist_ok=True)
            self._client = QdrantClient(path=str(storage_root))

    @property
    def client(self) -> QdrantClient:
        """返回底层 client，供上层索引逻辑复用。"""

        return self._client

    def close(self) -> None:
        """关闭底层本地 client，释放文件句柄。"""

        self._client.close()

    def recreate_collection(self, collection_name: str, vector_dim: int) -> None:
        """重建 child chunk dense collection。"""

        if self._client.collection_exists(collection_name=collection_name):
            self._client.delete_collection(collection_name=collection_name)
        self._client.create_collection(
            collection_name=collection_name,
            vectors_config=qdrant_models.VectorParams(
                size=vector_dim,
                distance=qdrant_models.Distance.COSINE,
            ),
        )
