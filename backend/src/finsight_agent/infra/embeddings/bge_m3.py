from __future__ import annotations

import os

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

# Windows 上 torch 自带的 Intel OpenMP(libiomp5md.dll) 与 sklearn/faiss 的
# MSVC OpenMP(vcomp140.dll) 同进程并存时，torch C 扩展初始化阶段会间歇性
# SIGSEGV。KMP_DUPLICATE_LIB_OK=TRUE 允许重复 OpenMP 运行时共存，消除崩溃。
# 必须在 import torch 之前设置，故放在模块加载处。
# 用强制赋值（非 setdefault）：若环境已存在 falsy 值，setdefault 不会覆盖会漏掉修复。
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"


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
        self._vector_dim: int | None = None
        if use_real_model:
            self._model = self._load_model()
            if self._model is None:
                raise RuntimeError(
                    f"无法加载 embedding 模型 {self.model_name}，请确认已下载到本地缓存"
                )

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
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

    def _resolve_local_snapshot_path(self) -> str | None:
        """离线定位本地完整 snapshot 目录，绕过可能失效的 hub repo-id 解析器。

        适用场景：本地 HF 缓存为非标准结构（如跨文件系统拷贝后 blobs/ 为空、
        snapshots/ 为普通副本）时，huggingface_hub 的离线解析会失败并回退联网。
        直接指向含 config.json + 权重的 snapshot 目录并用 local_files_only 加载，
        可完全离线使用本地模型。
        """
        from pathlib import Path

        hf_home = Path(os.environ.get("HF_HOME", str(Path.home() / ".cache" / "huggingface")))
        hub = hf_home / "hub"
        if not hub.exists():
            return None

        key = self.model_name.lower().replace("/", "--")
        candidates: list[Path] = []
        for model_dir in hub.glob("models--*"):
            if key not in model_dir.name.lower():
                continue
            for snap in sorted(model_dir.glob("snapshots/*")):
                if not snap.is_dir():
                    continue
                has_config = (snap / "config.json").exists()
                has_weights = (snap / "model.safetensors").exists() or (
                    snap / "pytorch_model.bin"
                ).exists()
                if has_config and has_weights:
                    candidates.append(snap)

        return str(candidates[-1]) if candidates else None

    def _load_model(self) -> Any | None:
        try:
            from sentence_transformers import SentenceTransformer
        except Exception:
            return None

        try:
            # GPU 优先：GTX 1650 4GB 显存 + batch_size=4 + 500 字截断可稳定运行（7 chunks/s）
            # CPU 模式仅 0.3 chunks/s，9706 chunks 需 9 小时，不可行
            import torch

            device = "cuda" if torch.cuda.is_available() else "cpu"

            # 优先离线直读本地 snapshot 目录，绕过 hub repo-id 解析器
            # （应对本地缓存非标准、离线解析失败的问题）。
            local_path = self._resolve_local_snapshot_path()
            if local_path is not None:
                os.environ.setdefault("HF_HUB_OFFLINE", "1")
                os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
                return SentenceTransformer(
                    local_path, local_files_only=True, device=device
                )

            # 回退：标准环境（缓存规范或联网可用）下用 repo-id 加载
            return SentenceTransformer(self.model_name, device=device)
        except Exception:
            return None

    def _encode_with_model(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            return []
        # 截断到 500 字符：99% 的 chunk 本就 <600 字，几乎无损；
        # 长文本在 GPU 上会 OOM、在 CPU 上极慢，截断后 GPU 7 chunks/s 稳定运行。
        truncated = [t[:500] if len(t) > 500 else t for t in texts]
        encoded = self._model.encode(
            truncated,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=4,
        )
        return [list(map(float, row)) for row in encoded]

    @property
    def vector_dim(self) -> int:
        """返回当前 provider 的向量维度，优先用模型实际维度。"""
        if self._vector_dim is not None:
            return self._vector_dim
        if self._model is not None:
            try:
                # 新版 sentence-transformers 改名了方法
                dim_fn = getattr(
                    self._model,
                    "get_embedding_dimension",
                    getattr(self._model, "get_sentence_embedding_dimension", None),
                )
                if dim_fn is not None:
                    self._vector_dim = dim_fn()
                    return self._vector_dim
            except Exception:
                pass
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
