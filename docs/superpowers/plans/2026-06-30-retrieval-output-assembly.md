# Retrieval Output Assembly Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为现有 retrieval facade 增加真实 parent expand、结构化 retrieval trace，以及职责清晰的 EvidenceItem 组装层。

**Architecture:** 保持现有 sparse / dense / fusion / rerank 主链路不变，把结果输出层拆成 `parent_context_loader.py`、`evidence_assembly.py`、`trace_builder.py` 三个辅助模块，由 `service.py` 继续做薄编排。`RetrievalResult` 新增轻量 `retrieval_trace`，`EvidenceItem.parent_context` 改为优先使用真实 `parent chunk`。

**Tech Stack:** Python 3、`dataclasses`、本地 `jsonl` chunk 产物、`unittest`

---

## File Structure

### Create

- `backend/src/finsight_agent/capabilities/retrieval/parent_context_loader.py`
  - 从 `chunked_filings/<document_id>/parents.jsonl` 回填真实 parent context
- `backend/src/finsight_agent/capabilities/retrieval/evidence_assembly.py`
  - 负责从 `RerankedHit` 组装 `EvidenceItem`
- `backend/src/finsight_agent/capabilities/retrieval/trace_builder.py`
  - 负责构造 `retrieval_trace` 和 `retrieval_notes`
- `tests/unit/test_parent_context_loader.py`
  - 覆盖 parent 加载和 fallback 输入
- `tests/unit/test_evidence_assembly.py`
  - 覆盖 `EvidenceItem` 组装与 `support_strength`
- `tests/unit/test_trace_builder.py`
  - 覆盖结构化 trace 和 notes

### Modify

- `backend/src/finsight_agent/capabilities/retrieval/models.py`
  - 新增 `RetrievalTrace` 并把它接入 `RetrievalResult`
- `backend/src/finsight_agent/capabilities/retrieval/citation_builder.py`
  - 保留 citation builder，同时让 child 摘要 fallback 逻辑作为公共工具继续可复用
- `backend/src/finsight_agent/capabilities/retrieval/service.py`
  - 改成 orchestration only，调用新模块
- `tests/unit/test_dense_retrieval_facade.py`
  - 断言 facade 返回真实 `retrieval_trace` 和真实 parent context

## Task 1: 扩展 Retrieval 模型

**Files:**
- Modify: `backend/src/finsight_agent/capabilities/retrieval/models.py`
- Test: `tests/unit/test_trace_builder.py`

- [ ] **Step 1: 写失败测试，先约束 `RetrievalTrace` 和 `RetrievalResult` 结构**

```python
from finsight_agent.capabilities.retrieval.models import RetrievalResult, RetrievalTrace


def test_retrieval_result_accepts_structured_trace() -> None:
    trace = RetrievalTrace(
        original_query="归母净利润增长原因",
        normalized_query="归母净利润增长原因",
        rewrite_queries=["归属于上市公司股东的净利润 增长 原因"],
        sparse_hit_count=3,
        dense_hit_count=4,
        fused_hit_count=5,
        reranked_hit_count=5,
        final_evidence_count=3,
        sparse_rewrite_triggered=True,
        dense_rewrite_triggered=False,
        parent_expand_attempted=True,
        parent_expand_fallback_count=1,
    )

    result = RetrievalResult(
        request_id="req-001",
        normalized_claim="归母净利润增长原因",
        retrieval_trace=trace,
    )

    assert result.retrieval_trace is trace
    assert result.retrieval_trace.final_evidence_count == 3
```

- [ ] **Step 2: 运行测试，确认当前失败**

Run:

```powershell
python -m unittest tests.unit.test_trace_builder -v
```

Expected: FAIL，提示 `RetrievalTrace` 未定义或 `RetrievalResult` 不接受该字段。

- [ ] **Step 3: 在 `models.py` 中最小实现 `RetrievalTrace` 并接到 `RetrievalResult`**

```python
@dataclass(slots=True)
class RetrievalTrace:
    """结构化 retrieval 过程摘要。"""

    original_query: str
    normalized_query: str
    rewrite_queries: list[str] = field(default_factory=list)
    sparse_hit_count: int = 0
    dense_hit_count: int = 0
    fused_hit_count: int = 0
    reranked_hit_count: int = 0
    final_evidence_count: int = 0
    sparse_rewrite_triggered: bool = False
    dense_rewrite_triggered: bool = False
    parent_expand_attempted: bool = False
    parent_expand_fallback_count: int = 0


@dataclass(slots=True)
class RetrievalResult:
    """统一 retrieval facade 输出。"""

    request_id: str
    normalized_claim: str
    evidence_items: list[EvidenceItem] = field(default_factory=list)
    retrieval_notes: list[str] = field(default_factory=list)
    retrieval_trace: RetrievalTrace | None = None
```

- [ ] **Step 4: 运行测试，确认通过**

Run:

```powershell
python -m unittest tests.unit.test_trace_builder -v
```

Expected: PASS，且 `RetrievalResult` 支持结构化 trace。

- [ ] **Step 5: 提交**

```powershell
git add backend/src/finsight_agent/capabilities/retrieval/models.py tests/unit/test_trace_builder.py
git commit -m "feat: add structured retrieval trace model"
```

## Task 2: 实现 Parent Context Loader

**Files:**
- Create: `backend/src/finsight_agent/capabilities/retrieval/parent_context_loader.py`
- Modify: `backend/src/finsight_agent/capabilities/retrieval/citation_builder.py`
- Test: `tests/unit/test_parent_context_loader.py`

- [ ] **Step 1: 写失败测试，约束真实 parent 读取和缺失 fallback 输入**

```python
from pathlib import Path
import tempfile

from finsight_agent.capabilities.retrieval.parent_context_loader import ParentContextLoader


def test_parent_context_loader_reads_parent_chunk_text() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        document_dir = root / "doc_001"
        document_dir.mkdir(parents=True, exist_ok=True)
        (document_dir / "parents.jsonl").write_text(
            '{"chunk_id":"parent_001","chunk_text":"这是完整 parent 上下文","page_start":12,"page_end":15,"section_path":["管理层讨论与分析"]}\\n',
            encoding="utf-8",
        )

        loader = ParentContextLoader(root)
        record = loader.load_parent("doc_001", "parent_001")

        assert record is not None
        assert record.chunk_id == "parent_001"
        assert record.chunk_text == "这是完整 parent 上下文"


def test_parent_context_loader_returns_none_when_parent_missing() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        loader = ParentContextLoader(Path(temp_dir))
        record = loader.load_parent("doc_missing", "parent_missing")

        assert record is None
```

- [ ] **Step 2: 运行测试，确认当前失败**

Run:

```powershell
python -m unittest tests.unit.test_parent_context_loader -v
```

Expected: FAIL，提示模块或类不存在。

- [ ] **Step 3: 实现最小 `ParentContextLoader` 和 parent 记录对象**

```python
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path


@dataclass(slots=True)
class ParentChunkRecord:
    """从 parents.jsonl 读取的最小 parent 记录。"""

    chunk_id: str
    chunk_text: str
    page_start: int
    page_end: int
    section_path: list[str] = field(default_factory=list)


class ParentContextLoader:
    """从本地 chunk 产物中回填真实 parent context。"""

    def __init__(self, chunked_filings_root: Path) -> None:
        self._chunked_filings_root = chunked_filings_root
        self._cache: dict[str, dict[str, ParentChunkRecord]] = {}

    def load_parent(self, document_id: str, parent_id: str | None) -> ParentChunkRecord | None:
        if not parent_id:
            return None
        document_parents = self._cache.setdefault(
            document_id,
            self._load_document_parents(document_id),
        )
        return document_parents.get(parent_id)

    def _load_document_parents(self, document_id: str) -> dict[str, ParentChunkRecord]:
        parents_path = self._chunked_filings_root / document_id / "parents.jsonl"
        if not parents_path.exists():
            return {}

        result: dict[str, ParentChunkRecord] = {}
        with parents_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                payload = json.loads(line)
                result[payload["chunk_id"]] = ParentChunkRecord(
                    chunk_id=payload["chunk_id"],
                    chunk_text=payload["chunk_text"],
                    page_start=payload["page_start"],
                    page_end=payload["page_end"],
                    section_path=list(payload.get("section_path", [])),
                )
        return result
```

- [ ] **Step 4: 保留 child 摘要 fallback 工具**

在 `citation_builder.py` 中保留：

```python
def build_parent_context(chunk_text: str, max_chars: int = 180) -> str:
    """在真实 parent 缺失时，使用 child 摘要模拟 parent context。"""

    normalized = chunk_text.strip()
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[:max_chars].rstrip()}..."
```

- [ ] **Step 5: 运行测试，确认通过**

Run:

```powershell
python -m unittest tests.unit.test_parent_context_loader -v
```

Expected: PASS，能读到真实 parent，缺失时返回 `None`。

- [ ] **Step 6: 提交**

```powershell
git add backend/src/finsight_agent/capabilities/retrieval/parent_context_loader.py backend/src/finsight_agent/capabilities/retrieval/citation_builder.py tests/unit/test_parent_context_loader.py
git commit -m "feat: add parent context loader for retrieval output"
```

## Task 3: 实现 Evidence Assembly

**Files:**
- Create: `backend/src/finsight_agent/capabilities/retrieval/evidence_assembly.py`
- Test: `tests/unit/test_evidence_assembly.py`

- [ ] **Step 1: 写失败测试，约束真实 parent 优先和 fallback 行为**

```python
from finsight_agent.capabilities.retrieval.evidence_assembly import assemble_evidence_item
from finsight_agent.capabilities.retrieval.models import RerankedHit
from finsight_agent.capabilities.retrieval.parent_context_loader import ParentChunkRecord


def test_assemble_evidence_item_prefers_real_parent_context() -> None:
    hit = RerankedHit(
        chunk_id="child_001",
        document_id="doc_001",
        parent_id="parent_001",
        company_code="002371",
        company_name="北方华创",
        doc_type="annual_report",
        report_year="2025",
        publish_date="2025-04-25",
        page_start=42,
        page_end=42,
        page_anchor=42,
        section_path=["管理层讨论与分析"],
        chunk_text="净利润同比增长主要来自刻蚀设备收入提升。",
        sparse_score=8.2,
        dense_score=0.77,
        rrf_score=0.15,
        rerank_score=0.92,
    )
    parent = ParentChunkRecord(
        chunk_id="parent_001",
        chunk_text="这是完整 parent 上下文。",
        page_start=40,
        page_end=45,
        section_path=["管理层讨论与分析"],
    )

    item, used_fallback = assemble_evidence_item(rank=1, hit=hit, parent_record=parent)

    assert item.parent_context == "这是完整 parent 上下文。"
    assert used_fallback is False
    assert item.support_strength == "strong"


def test_assemble_evidence_item_falls_back_when_parent_missing() -> None:
    hit = RerankedHit(
        chunk_id="child_001",
        document_id="doc_001",
        parent_id="parent_missing",
        company_code="002371",
        company_name="北方华创",
        doc_type="annual_report",
        report_year="2025",
        publish_date="2025-04-25",
        page_start=42,
        page_end=42,
        page_anchor=42,
        section_path=["管理层讨论与分析"],
        chunk_text="净利润同比增长主要来自刻蚀设备收入提升。",
        sparse_score=8.2,
        dense_score=0.77,
        rrf_score=0.15,
        rerank_score=0.40,
    )

    item, used_fallback = assemble_evidence_item(rank=1, hit=hit, parent_record=None)

    assert item.parent_context.startswith("净利润同比增长")
    assert used_fallback is True
    assert item.support_strength == "weak"
```

- [ ] **Step 2: 运行测试，确认当前失败**

Run:

```powershell
python -m unittest tests.unit.test_evidence_assembly -v
```

Expected: FAIL，提示 assembly 模块或函数不存在。

- [ ] **Step 3: 最小实现 `assemble_evidence_item()` 和支持度策略**

```python
from __future__ import annotations

from .citation_builder import build_citation_record, build_parent_context
from .models import EvidenceItem, RetrievalScoreBreakdown, RerankedHit
from .parent_context_loader import ParentChunkRecord


def assemble_evidence_item(
    rank: int,
    hit: RerankedHit,
    parent_record: ParentChunkRecord | None,
) -> tuple[EvidenceItem, bool]:
    """把 reranked hit 组装成对外 EvidenceItem。"""

    parent_fallback_used = parent_record is None
    parent_context = (
        parent_record.chunk_text.strip()
        if parent_record is not None
        else build_parent_context(hit.chunk_text)
    )

    item = EvidenceItem(
        evidence_id=f"evidence_{rank:04d}",
        rank=rank,
        support_strength=classify_support_strength(hit),
        matched_chunk_id=hit.chunk_id,
        matched_parent_id=hit.parent_id,
        excerpt=" ".join(hit.chunk_text.split()),
        parent_context=parent_context,
        citation=build_citation_record(
            document_id=hit.document_id,
            page_start=hit.page_start,
            page_end=hit.page_end,
            page_anchor=hit.page_anchor,
        ),
        retrieval_scores=RetrievalScoreBreakdown(
            sparse_score=hit.sparse_score,
            dense_score=hit.dense_score,
            rrf_score=hit.rrf_score,
            rerank_score=hit.rerank_score,
        ),
        company_code=hit.company_code,
        company_name=hit.company_name,
        doc_type=hit.doc_type,
        section_path=list(hit.section_path),
    )
    return item, parent_fallback_used


def classify_support_strength(hit: RerankedHit) -> str:
    """显式支持度分类策略。"""

    rerank_score = hit.rerank_score
    has_supporting_channel = hit.sparse_score is not None or hit.dense_score is not None
    if rerank_score >= 0.8 and has_supporting_channel:
        return "strong"
    if rerank_score >= 0.5:
        return "partial"
    if rerank_score > 0:
        return "weak"
    return "unsupported"
```

- [ ] **Step 4: 运行测试，确认通过**

Run:

```powershell
python -m unittest tests.unit.test_evidence_assembly -v
```

Expected: PASS，真实 parent 优先，缺失时使用 fallback。

- [ ] **Step 5: 提交**

```powershell
git add backend/src/finsight_agent/capabilities/retrieval/evidence_assembly.py tests/unit/test_evidence_assembly.py
git commit -m "feat: add evidence assembly for retrieval result"
```

## Task 4: 实现 Trace Builder

**Files:**
- Create: `backend/src/finsight_agent/capabilities/retrieval/trace_builder.py`
- Test: `tests/unit/test_trace_builder.py`

- [ ] **Step 1: 写失败测试，约束结构化 trace 和 notes**

```python
from finsight_agent.capabilities.retrieval.trace_builder import build_retrieval_trace_and_notes


def test_build_retrieval_trace_and_notes() -> None:
    trace, notes = build_retrieval_trace_and_notes(
        original_query="归母净利润增长原因",
        normalized_query="归母净利润增长原因",
        sparse_hit_count=3,
        dense_hit_count=4,
        fused_hit_count=5,
        reranked_hit_count=5,
        final_evidence_count=3,
        sparse_rewrite_queries=["归属于上市公司股东的净利润"],
        dense_rewrite_queries=[],
        parent_expand_attempted=True,
        parent_expand_fallback_count=1,
    )

    assert trace.sparse_rewrite_triggered is True
    assert trace.dense_rewrite_triggered is False
    assert trace.parent_expand_fallback_count == 1
    assert "sparse rewrite triggered" in notes[0]
    assert "parent expand fallback used" in notes[-1]
```

- [ ] **Step 2: 运行测试，确认当前失败**

Run:

```powershell
python -m unittest tests.unit.test_trace_builder -v
```

Expected: FAIL，提示 trace builder 不存在。

- [ ] **Step 3: 实现最小 `build_retrieval_trace_and_notes()`**

```python
from __future__ import annotations

from .models import RetrievalTrace


def build_retrieval_trace_and_notes(
    *,
    original_query: str,
    normalized_query: str,
    sparse_hit_count: int,
    dense_hit_count: int,
    fused_hit_count: int,
    reranked_hit_count: int,
    final_evidence_count: int,
    sparse_rewrite_queries: list[str],
    dense_rewrite_queries: list[str],
    parent_expand_attempted: bool,
    parent_expand_fallback_count: int,
) -> tuple[RetrievalTrace, list[str]]:
    """构造结构化 retrieval trace 和面向人类的摘要 notes。"""

    rewrite_queries = list(sparse_rewrite_queries) + [
        query for query in dense_rewrite_queries if query not in sparse_rewrite_queries
    ]
    trace = RetrievalTrace(
        original_query=original_query,
        normalized_query=normalized_query,
        rewrite_queries=rewrite_queries,
        sparse_hit_count=sparse_hit_count,
        dense_hit_count=dense_hit_count,
        fused_hit_count=fused_hit_count,
        reranked_hit_count=reranked_hit_count,
        final_evidence_count=final_evidence_count,
        sparse_rewrite_triggered=bool(sparse_rewrite_queries),
        dense_rewrite_triggered=bool(dense_rewrite_queries),
        parent_expand_attempted=parent_expand_attempted,
        parent_expand_fallback_count=parent_expand_fallback_count,
    )

    notes: list[str] = []
    if sparse_rewrite_queries:
        notes.append(f"sparse rewrite triggered: {', '.join(sparse_rewrite_queries)}")
    if dense_rewrite_queries:
        notes.append(f"dense rewrite triggered: {', '.join(dense_rewrite_queries)}")
    if parent_expand_fallback_count:
        notes.append(
            f"parent expand fallback used for {parent_expand_fallback_count} evidence item"
        )
    return trace, notes
```

- [ ] **Step 4: 运行测试，确认通过**

Run:

```powershell
python -m unittest tests.unit.test_trace_builder -v
```

Expected: PASS，trace 和 notes 都符合预期。

- [ ] **Step 5: 提交**

```powershell
git add backend/src/finsight_agent/capabilities/retrieval/trace_builder.py tests/unit/test_trace_builder.py backend/src/finsight_agent/capabilities/retrieval/models.py
git commit -m "feat: add retrieval trace builder"
```

## Task 5: 收敛 Retrieval Facade 编排层

**Files:**
- Modify: `backend/src/finsight_agent/capabilities/retrieval/service.py`
- Test: `tests/unit/test_dense_retrieval_facade.py`

- [ ] **Step 1: 写失败测试，断言 facade 返回真实 parent context 和 structured trace**

```python
from finsight_agent.capabilities.retrieval.parsing_models import ChunkRecord
from finsight_agent.capabilities.retrieval.parsed_storage import write_chunk_artifact
from finsight_agent.capabilities.retrieval.service import DenseRetrievalFacade, RetrievalFacade, SparseRetrievalFacade
from finsight_agent.infra.embeddings.bge_m3 import BgeM3EmbeddingProvider


def test_facade_returns_real_parent_context_and_trace() -> None:
    # 在临时目录下写 1 个 parent 和 1 个 child
    write_chunk_artifact(
        root=chunk_root,
        document_id="doc_001",
        parents=[
            ChunkRecord(
                chunk_id="parent_001",
                document_id="doc_001",
                chunk_level="parent",
                parent_id=None,
                chunk_text="这是完整 parent 上下文。",
                page_start=40,
                page_end=45,
                page_anchor=40,
                section_path=["管理层讨论与分析"],
                element_ids=["p1"],
                order_in_document=1,
                source_parser="pdfplumber",
                created_from_parser_version="pdfplumber_v1",
            )
        ],
        children=[
            ChunkRecord(
                chunk_id="child_001",
                document_id="doc_001",
                chunk_level="child",
                parent_id="parent_001",
                chunk_text="净利润同比增长主要来自刻蚀设备收入提升。",
                page_start=42,
                page_end=42,
                page_anchor=42,
                section_path=["管理层讨论与分析"],
                element_ids=["c1"],
                order_in_document=2,
                source_parser="pdfplumber",
                created_from_parser_version="pdfplumber_v1",
            )
        ],
        chunk_report={"document_id": "doc_001", "parent_count": 1, "child_count": 1},
    )

    result = facade.retrieve_evidence("净利润增长", limit=3, company_code="002371")

    assert result.retrieval_trace is not None
    assert result.retrieval_trace.final_evidence_count >= 1
    assert result.evidence_items[0].parent_context == "这是完整 parent 上下文。"
```

- [ ] **Step 2: 运行测试，确认当前失败**

Run:

```powershell
python -m unittest tests.unit.test_dense_retrieval_facade -v
```

Expected: FAIL，因为当前 `parent_context` 仍来自 child 摘要，且没有 `retrieval_trace`。

- [ ] **Step 3: 在 `service.py` 中接入新模块，保持 facade 薄编排**

把当前 `retrieve_evidence()` 中直接构造 `EvidenceItem` 的逻辑替换成：

```python
parent_loader = ParentContextLoader(self.sparse_facade._chunked_filings_root)
evidence_items: list[EvidenceItem] = []
parent_expand_fallback_count = 0

for rank, hit in enumerate(reranked_hits[:limit], start=1):
    parent_record = parent_loader.load_parent(hit.document_id, hit.parent_id)
    item, used_fallback = assemble_evidence_item(
        rank=rank,
        hit=hit,
        parent_record=parent_record,
    )
    evidence_items.append(item)
    if used_fallback:
        parent_expand_fallback_count += 1

retrieval_trace, retrieval_notes = build_retrieval_trace_and_notes(
    original_query=raw_query,
    normalized_query=raw_query.strip(),
    sparse_hit_count=len(sparse_result.hits),
    dense_hit_count=len(dense_result.hits),
    fused_hit_count=len(fused_hits),
    reranked_hit_count=len(reranked_hits),
    final_evidence_count=len(evidence_items),
    sparse_rewrite_queries=sparse_result.triggered_rewrite_queries,
    dense_rewrite_queries=dense_result.rewrite_queries,
    parent_expand_attempted=bool(evidence_items),
    parent_expand_fallback_count=parent_expand_fallback_count,
)

return RetrievalResult(
    request_id=str(uuid.uuid4()),
    normalized_claim=raw_query.strip(),
    evidence_items=evidence_items,
    retrieval_notes=retrieval_notes,
    retrieval_trace=retrieval_trace,
)
```

同时删除 `service.py` 内部直接构造 `CitationRecord`、`RetrievalScoreBreakdown`、`EvidenceItem` 的散落逻辑。

- [ ] **Step 4: 运行定向测试，确认通过**

Run:

```powershell
python -m unittest tests.unit.test_dense_retrieval_facade -v
```

Expected: PASS，`parent_context` 来自真实 parent，且结果带 `retrieval_trace`。

- [ ] **Step 5: 运行相关回归**

Run:

```powershell
python -m unittest tests.unit.test_parent_context_loader tests.unit.test_evidence_assembly tests.unit.test_trace_builder tests.unit.test_sparse_retrieval_facade tests.unit.test_dense_retrieval_facade -v
```

Expected: PASS，所有 retrieval 输出层相关测试通过。

- [ ] **Step 6: 提交**

```powershell
git add backend/src/finsight_agent/capabilities/retrieval/service.py backend/src/finsight_agent/capabilities/retrieval/parent_context_loader.py backend/src/finsight_agent/capabilities/retrieval/evidence_assembly.py backend/src/finsight_agent/capabilities/retrieval/trace_builder.py backend/src/finsight_agent/capabilities/retrieval/models.py tests/unit/test_parent_context_loader.py tests/unit/test_evidence_assembly.py tests/unit/test_trace_builder.py tests/unit/test_dense_retrieval_facade.py
git commit -m "feat: assemble retrieval output with parent expand and trace"
```

## Task 6: 全量验证与收尾

**Files:**
- Modify: 无新增功能文件，必要时只修测试或类型问题
- Test: `tests/unit/test_dense_retrieval_facade.py`, `tests/unit/test_sparse_retrieval_facade.py`, 全量 `tests`

- [ ] **Step 1: 跑全量测试**

Run:

```powershell
python -m unittest discover -s tests -p 'test*.py'
```

Expected: 全部 PASS，不引入新的 warning 或资源泄露。

- [ ] **Step 2: 如果失败，只做最小修复并复跑**

若有类型或字段名不一致，优先检查：

- `RetrievalTrace` 字段名是否和 `trace_builder.py` 一致
- `RetrievalResult` 新字段是否影响现有测试构造
- `service.py` 是否仍保留了旧组装逻辑

- [ ] **Step 3: 检查工作区状态**

Run:

```powershell
git status --short
```

Expected: 只剩本轮实现相关文件变更。

- [ ] **Step 4: 最终提交**

```powershell
git add backend/src/finsight_agent/capabilities/retrieval docs/superpowers/specs/2026-06-30-retrieval-output-assembly-design.md docs/superpowers/plans/2026-06-30-retrieval-output-assembly.md tests/unit
git commit -m "feat: refine retrieval output assembly and trace"
```

## Self-Review

### Spec Coverage

- `retrieval_trace` 结构化输出：Task 1、Task 4、Task 5
- 真实 parent expand：Task 2、Task 5
- `EvidenceItem` 正式组装：Task 3、Task 5
- `retrieval_notes` 与 trace 分层：Task 4、Task 5
- facade 保持薄编排：Task 5

### Placeholder Scan

已检查计划中不存在：

- `TODO`
- `TBD`
- “实现后续逻辑”
- “类似 Task N”

所有代码步骤均给出明确示例和命令。

### Type Consistency

- `RetrievalTrace` 在 Task 1 定义，并在 Task 4、Task 5 中复用
- `ParentChunkRecord` 在 Task 2 定义，并在 Task 3、Task 5 中复用
- `assemble_evidence_item()` 在 Task 3 定义，并在 Task 5 调用
- `build_retrieval_trace_and_notes()` 在 Task 4 定义，并在 Task 5 调用
