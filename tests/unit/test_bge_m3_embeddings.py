from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.infra.embeddings.bge_m3 import BgeM3EmbeddingProvider


class BgeM3EmbeddingProviderTest(unittest.TestCase):
    def test_provider_returns_vectors(self) -> None:
        provider = BgeM3EmbeddingProvider()
        vectors = provider.embed(["净利润增长原因"])
        self.assertEqual(len(vectors), 1)
        self.assertGreater(len(vectors[0]), 0)

    def test_provider_describe_returns_metadata(self) -> None:
        provider = BgeM3EmbeddingProvider()
        result = provider.describe()
        self.assertEqual(result.model_name, "bge-m3")
        self.assertEqual(result.model_version, "bge-m3-v1")
        self.assertGreater(result.vector_dim, 0)


if __name__ == "__main__":
    unittest.main()
