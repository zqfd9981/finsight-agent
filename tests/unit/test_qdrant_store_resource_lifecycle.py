from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

from qdrant_client.local.persistence import CollectionPersistence


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.infra.vector_store.qdrant_store import QdrantStore


class QdrantStoreResourceLifecycleTest(unittest.TestCase):
    def test_persistent_store_does_not_probe_sqlite_memory_connection_when_constructed(self) -> None:
        original_connect = sqlite3.connect
        original_check_same_thread = CollectionPersistence.CHECK_SAME_THREAD
        connect_calls: list[tuple[object, ...]] = []

        def tracking_connect(*args, **kwargs):
            connect_calls.append(args)
            return original_connect(*args, **kwargs)

        sqlite3.connect = tracking_connect
        try:
            CollectionPersistence.CHECK_SAME_THREAD = None
            store = QdrantStore(storage_path=REPO_ROOT / "var" / "test_qdrant_store")
            store.recreate_collection("finsight_pdf_chunks_v1", vector_dim=8)
            store.close()
        finally:
            sqlite3.connect = original_connect
            CollectionPersistence.CHECK_SAME_THREAD = original_check_same_thread

        self.assertNotIn((":memory:",), connect_calls)


if __name__ == "__main__":
    unittest.main()
