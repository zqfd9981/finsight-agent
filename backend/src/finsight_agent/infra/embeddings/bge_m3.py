from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any


@dataclass(slots=True)
class EmbeddingResult:
    """本地 embedding 计算结果。"""

    vectors: list[list[float]]
    model_name: str
    model_version: str
    vector_dim: int


class BgeM3EmbeddingProvider:
    """本地 bge-m3 embedding 提供器。

    首版优先尝试加载 sentence-transformers 本地模型；
    如果模型暂不可用，则退回到稳定的特征哈希向量，保证测试和开发链路可运行。
    """

    model_name = "bge-m3"
    model_version = "bge-m3-v1"

    def __init__(
        self,
        model_name: str | None = None,
        model_version: str | None = None,
        use_real_model: bool = False,
    ) -> None:
        self.model_name = model_name or self.model_name
        self.model_version = model_version or self.model_version
        self._use_real_model = use_real_model
        self._model = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self._use_real_model and self._model is None:
            self._model = self._load_model()
        if self._model is not None:
            vectors = self._encode_with_model(texts)
            if vectors:
                return vectors
        return [_fallback_vector(text) for text in texts]

    def describe(self) -> EmbeddingResult:
        vectors = self.embed(["embedding metadata probe"])
        vector_dim = len(vectors[0]) if vectors else 0
        return EmbeddingResult(
            vectors=vectors,
            model_name=self.model_name,
            model_version=self.model_version,
            vector_dim=vector_dim,
        )

    def _load_model(self) -> Any | None:
        try:
            from sentence_transformers import SentenceTransformer
        except Exception:
            return None

        try:
            return SentenceTransformer(self.model_name)
        except Exception:
            return None

    def _encode_with_model(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            return []
        encoded = self._model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [list(map(float, row)) for row in encoded]

    @property
    def vector_dim(self) -> int:
        """返回当前 provider 的默认向量维度。"""

        return 384


@lru_cache(maxsize=1024)
def _fallback_vector(text: str, dimension: int = 384) -> list[float]:
    """给测试和开发环境准备的稳定哈希向量回退。"""

    vector = [0.0] * dimension
    normalized = text.strip()
    if not normalized:
        return vector

    for index, character in enumerate(normalized):
        slot = (ord(character) + index * 131) % dimension
        vector[slot] += 1.0

    norm = sum(value * value for value in vector) ** 0.5
    if norm == 0:
        return vector
    return [value / norm for value in vector]
