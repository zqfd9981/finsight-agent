from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.infra.vector_store.qdrant_store import QdrantStore


class _ClosableCollection:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _StubClient:
    def __init__(self) -> None:
        self.collection = _ClosableCollection()
        self.collections = {"finsight_pdf_chunks_v1": self.collection}
        self._client = self
        self.deleted: list[str] = []
        self.created: list[tuple[str, int]] = []

    def collection_exists(self, collection_name: str) -> bool:
        return collection_name in self.collections

    def delete_collection(self, collection_name: str) -> None:
        self.deleted.append(collection_name)
        self.collections.pop(collection_name, None)

    def create_collection(self, collection_name: str, vectors_config) -> None:
        self.created.append((collection_name, vectors_config.size))
        self.collections[collection_name] = _ClosableCollection()


class QdrantStoreTest(unittest.TestCase):
    def test_recreate_collection_closes_existing_local_collection_before_delete(self) -> None:
        store = object.__new__(QdrantStore)
        store._client = _StubClient()

        store.recreate_collection("finsight_pdf_chunks_v1", vector_dim=1024)

        self.assertTrue(store._client.collection.closed)
        self.assertEqual(store._client.deleted, ["finsight_pdf_chunks_v1"])
        self.assertEqual(store._client.created, [("finsight_pdf_chunks_v1", 1024)])


if __name__ == "__main__":
    unittest.main()
