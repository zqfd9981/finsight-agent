from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.retrieval.parent_context_loader import ParentContextLoader


class ParentContextLoaderTest(unittest.TestCase):
    def test_load_parent_returns_record_from_parents_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            document_dir = root / "doc_1"
            document_dir.mkdir(parents=True, exist_ok=True)
            (document_dir / "parents.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "chunk_id": "doc_1_parent_000001",
                                "document_id": "doc_1",
                                "chunk_level": "parent",
                                "parent_id": None,
                                "chunk_text": "管理层讨论与分析全文",
                                "page_start": 5,
                                "page_end": 6,
                                "page_anchor": 5,
                                "section_path": ["管理层讨论与分析"],
                            },
                            ensure_ascii=False,
                        )
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            loader = ParentContextLoader(chunked_filings_root=root)

            record = loader.load_parent("doc_1", "doc_1_parent_000001")

            self.assertIsNotNone(record)
            self.assertIsInstance(record, object)
            self.assertEqual(record.chunk_id, "doc_1_parent_000001")
            self.assertEqual(record.chunk_text, "管理层讨论与分析全文")
            self.assertEqual(record.page_start, 5)
            self.assertEqual(record.page_end, 6)
            self.assertEqual(record.section_path, ["管理层讨论与分析"])

    def test_load_parent_returns_none_when_parent_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            document_dir = root / "doc_1"
            document_dir.mkdir(parents=True, exist_ok=True)
            (document_dir / "parents.jsonl").write_text(
                json.dumps(
                    {
                        "chunk_id": "doc_1_parent_000001",
                        "document_id": "doc_1",
                        "chunk_level": "parent",
                        "parent_id": None,
                        "chunk_text": "管理层讨论与分析全文",
                        "page_start": 5,
                        "page_end": 6,
                        "page_anchor": 5,
                        "section_path": ["管理层讨论与分析"],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            loader = ParentContextLoader(chunked_filings_root=root)

            self.assertIsNone(loader.load_parent("doc_1", "missing_parent"))
            self.assertIsNone(loader.load_parent("doc_1", None))
            self.assertIsNone(loader.load_parent("missing_doc", "doc_1_parent_000001"))

    def test_load_parent_uses_cached_record_after_source_file_removed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            document_dir = root / "doc_1"
            document_dir.mkdir(parents=True, exist_ok=True)
            parents_path = document_dir / "parents.jsonl"
            parents_path.write_text(
                json.dumps(
                    {
                        "chunk_id": "doc_1_parent_000001",
                        "document_id": "doc_1",
                        "chunk_level": "parent",
                        "parent_id": None,
                        "chunk_text": "缓存中的 parent 内容",
                        "page_start": 8,
                        "page_end": 9,
                        "page_anchor": 8,
                        "section_path": ["主营业务分析"],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            loader = ParentContextLoader(chunked_filings_root=root)

            first_record = loader.load_parent("doc_1", "doc_1_parent_000001")
            self.assertIsNotNone(first_record)

            parents_path.unlink()

            second_record = loader.load_parent("doc_1", "doc_1_parent_000001")

            self.assertIsNotNone(second_record)
            self.assertEqual(second_record, first_record)


if __name__ == "__main__":
    unittest.main()
