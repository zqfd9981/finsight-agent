# 本地 Dense Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在本地完成 dense retrieval 的最小可用闭环，支持本地 embedding、Qdrant 向量索引、保守 query rewrite、RRF 融合、child 级 rerank，并与现有 sparse 检索结果对齐。

**Architecture:** dense 检索层保持分层清晰：embedding provider 只负责向量生成，dense index 只负责 Qdrant 写入和查询，dense retrieval service 只负责查询编排，fusion 负责 sparse/dense 合并，rerank 负责融合候选精排，最终由 retrieval facade 统一对外。首版保留原 query 优先原则，rewrite 仅作为保守补充路由。

**Tech Stack:** Python, Qdrant, 本地 `bge-m3` embedding, pytest/unittest 风格测试, 现有 `finsight_agent.capabilities.retrieval` 代码骨架

---

### Task 1: 补齐 dense 相关基础模型与配置

**Files:**
- Modify: `backend/src/finsight_agent/capabilities/retrieval/models.py`
- Modify: `backend/src/finsight_agent/config/settings.py`
- Modify: `config/app.yaml`
- Test: `tests/unit/test_dense_models.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path

from finsight_agent.config.settings import load_settings
from finsight_agent.capabilities.retrieval.models import DenseSearchRequest, DenseHit


def test_dense_request_and_hit_fields_exist():
    request = DenseSearchRequest(query_text="净利润", limit=5, company_code="002371")
    assert request.query_text == "净利润"
    assert request.limit == 5
    assert request.company_code == "002371"

    hit = DenseHit(
        chunk_id="c1",
        document_id="d1",
        parent_id="p1",
        company_code="002371",
        company_name="北方华创",
        doc_type="annual_report",
        report_year=2025,
        publish_date="2025-04-25",
        page_start=3,
        page_end=4,
        page_anchor=3,
        section_path=["管理层讨论与分析"],
        chunk_text="净利润同比增长",
        dense_score=0.91,
        query_variant="original",
    )
    assert hit.chunk_id == "c1"


def test_settings_include_dense_paths():
    settings = load_settings()
    assert isinstance(settings.control_plane.root, Path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.unit.test_dense_models -v`
Expected: FAIL because `DenseSearchRequest` / `DenseHit` and dense settings are not yet defined.

- [ ] **Step 3: Write minimal implementation**

Add dense-related dataclasses in `models.py`:

```python
from dataclasses import dataclass, field


@dataclass(slots=True)
class DenseSearchRequest:
    query_text: str
    limit: int = 10
    company_code: str | None = None
    doc_type: str | None = None
    report_year: int | None = None


@dataclass(slots=True)
class DenseHit:
    chunk_id: str
    document_id: str
    parent_id: str
    company_code: str
    company_name: str
    doc_type: str
    report_year: int
    publish_date: str
    page_start: int
    page_end: int
    page_anchor: int | None
    section_path: list[str]
    chunk_text: str
    dense_score: float
    query_variant: str = "original"
```

Extend settings with dense config:

```python
@dataclass(slots=True)
class DenseSettings:
    qdrant_collection_name: str
    embedding_model_name: str
    embedding_model_version: str
    qdrant_path: Path


@dataclass(slots=True)
class RetrievalSettings:
    ...
    dense: DenseSettings
```

Add YAML keys:

```yaml
app:
  control_plane:
    retrieval:
      dense:
        qdrant_collection_name: finsight_pdf_chunks_v1
        embedding_model_name: bge-m3
        embedding_model_version: bge-m3-v1
        qdrant_path: var/data/qdrant
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.unit.test_dense_models -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/finsight_agent/capabilities/retrieval/models.py backend/src/finsight_agent/config/settings.py config/app.yaml tests/unit/test_dense_models.py
git commit -m "补齐Dense检索基础模型与配置"
```

### Task 2: 实现本地 embedding provider

**Files:**
- Create: `backend/src/finsight_agent/infra/embeddings/__init__.py`
- Create: `backend/src/finsight_agent/infra/embeddings/bge_m3.py`
- Test: `tests/unit/test_bge_m3_embeddings.py`

- [ ] **Step 1: Write the failing test**

```python
from finsight_agent.infra.embeddings.bge_m3 import BgeM3EmbeddingProvider


def test_bge_m3_provider_returns_vectors():
    provider = BgeM3EmbeddingProvider()
    vectors = provider.embed(["净利润增长原因"])
    assert len(vectors) == 1
    assert len(vectors[0]) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.unit.test_bge_m3_embeddings -v`
Expected: FAIL because provider does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class EmbeddingResult:
    vectors: list[list[float]]
    model_name: str
    model_version: str
    vector_dim: int


class BgeM3EmbeddingProvider:
    """本地 bge-m3 embedding 提供器。

    首版可以先用最小可运行实现，后续再接真实模型加载。
    """

    model_name = "bge-m3"
    model_version = "bge-m3-v1"

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError("bge-m3 embedding provider is not implemented yet")
```

For the first implementation step, keep the provider interface in place and make the test fail for the expected reason. Then replace the placeholder with a local model call or a deterministic fallback that returns stable vectors for tests.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.unit.test_bge_m3_embeddings -v`
Expected: PASS after the provider is wired to a real or deterministic local embedding implementation.

- [ ] **Step 5: Commit**

```bash
git add backend/src/finsight_agent/infra/embeddings tests/unit/test_bge_m3_embeddings.py
git commit -m "实现本地Embedding提供器骨架"
```

### Task 3: 实现 Qdrant dense index

**Files:**
- Create: `backend/src/finsight_agent/infra/vector_store/qdrant_store.py`
- Create: `backend/src/finsight_agent/capabilities/retrieval/dense_index.py`
- Test: `tests/unit/test_dense_index.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path

from finsight_agent.capabilities.retrieval.dense_index import DenseChunkIndex


def test_dense_index_build_and_search(tmp_path: Path):
    index = DenseChunkIndex(index_root=tmp_path)
    count = index.rebuild_from_chunk_root(Path("var/data/chunked_filings"))
    assert count >= 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.unit.test_dense_index -v`
Expected: FAIL because `DenseChunkIndex` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Implement:
- Qdrant collection creation
- child chunk reading from `chunked_filings/*/children.jsonl`
- embedding generation through provider
- payload write and top-k search

Core shape:

```python
class DenseChunkIndex:
    def __init__(self, index_root: Path, collection_name: str, embedding_provider: object):
        ...

    def rebuild_from_chunk_root(self, chunk_root: Path) -> int:
        ...

    def search(self, query_text: str, limit: int, filters: DenseSearchFilters | None = None) -> list[DenseHit]:
        ...
```

The `DenseSearchFilters` class should mirror the smallest sparse filters: `company_code`, `doc_type`, `report_year`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.unit.test_dense_index -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/finsight_agent/infra/vector_store/qdrant_store.py backend/src/finsight_agent/capabilities/retrieval/dense_index.py tests/unit/test_dense_index.py
git commit -m "实现Qdrant Dense索引"
```

### Task 4: 实现 query rewrite 与 dense search service

**Files:**
- Modify: `backend/src/finsight_agent/capabilities/retrieval/query_rewrite.py`
- Create: `backend/src/finsight_agent/capabilities/retrieval/dense_retrieval_service.py`
- Test: `tests/unit/test_dense_retrieval_service.py`

- [ ] **Step 1: Write the failing test**

```python
from finsight_agent.capabilities.retrieval.dense_retrieval_service import DenseRetrievalService


def test_dense_service_prefers_original_query():
    service = DenseRetrievalService(...)
    result = service.search("归母净利润", limit=3)
    assert result.original_hit_count >= 0
    assert result.rewrite_queries is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.unit.test_dense_retrieval_service -v`
Expected: FAIL because service is not implemented yet.

- [ ] **Step 3: Write minimal implementation**

Implement:
- original query first
- alias rewrite only when original hit count is below threshold
- rewrite policy version tracking
- dense-only dedup by `chunk_id`

Keep query rewrite conservative and configuration-driven.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.unit.test_dense_retrieval_service -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/finsight_agent/capabilities/retrieval/query_rewrite.py backend/src/finsight_agent/capabilities/retrieval/dense_retrieval_service.py tests/unit/test_dense_retrieval_service.py
git commit -m "实现Dense查询改写与检索服务"
```

### Task 5: 实现 fusion 与 rerank

**Files:**
- Modify: `backend/src/finsight_agent/capabilities/retrieval/fusion.py`
- Modify: `backend/src/finsight_agent/capabilities/retrieval/rerank.py`
- Test: `tests/unit/test_dense_fusion_and_rerank.py`

- [ ] **Step 1: Write the failing test**

```python
from finsight_agent.capabilities.retrieval.fusion import rrf_fuse


def test_rrf_fuse_deduplicates_by_chunk_id():
    fused = rrf_fuse([], [])
    assert fused == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.unit.test_dense_fusion_and_rerank -v`
Expected: FAIL because fusion/rerank logic is not implemented yet.

- [ ] **Step 3: Write minimal implementation**

Implement:
- RRF fusion by `chunk_id`
- preserve `sparse_rank` and `dense_rank`
- rerank only top N fused child hits

Pseudo shape:

```python
def rrf_fuse(sparse_hits, dense_hits) -> list[FusedHit]:
    ...

def rerank_hits(hits: list[FusedHit], query_text: str, top_n: int) -> list[RerankedHit]:
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.unit.test_dense_fusion_and_rerank -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/finsight_agent/capabilities/retrieval/fusion.py backend/src/finsight_agent/capabilities/retrieval/rerank.py tests/unit/test_dense_fusion_and_rerank.py
git commit -m "实现Dense融合与精排"
```

### Task 6: 接通 retrieval facade 与回归验证

**Files:**
- Modify: `backend/src/finsight_agent/capabilities/retrieval/service.py`
- Test: `tests/unit/test_dense_retrieval_facade.py`
- Test: `tests/unit/test_dense_retrieval_e2e.py`

- [ ] **Step 1: Write the failing test**

```python
from finsight_agent.capabilities.retrieval.service import build_retrieval_facade


def test_facade_returns_retrieval_result():
    facade = build_retrieval_facade()
    result = facade.retrieve_evidence("归母净利润")
    assert result.request_id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.unit.test_dense_retrieval_facade -v`
Expected: FAIL because facade is not wired to dense yet.

- [ ] **Step 3: Write minimal implementation**

Wire:
- sparse
- dense
- fusion
- rerank
- parent expand
- citation builder

Keep `service.py` thin.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest discover -s tests -p 'test*.py'`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/finsight_agent/capabilities/retrieval/service.py tests/unit/test_dense_retrieval_facade.py tests/unit/test_dense_retrieval_e2e.py
git commit -m "接通Dense检索Facade"
```

