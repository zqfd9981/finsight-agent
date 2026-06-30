from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.retrieval.chunking import build_chunks
from finsight_agent.capabilities.retrieval.parsing_models import ParsedElement


class PdfChunkingTest(unittest.TestCase):
    def test_build_chunks_groups_elements_by_section_and_emits_parent_and_child(self) -> None:
        elements = [
            ParsedElement(
                element_id="e1",
                document_id="doc_1",
                element_type="title",
                page_start=3,
                page_end=3,
                order_in_document=1,
                section_path=["管理层讨论与分析"],
                text="管理层讨论与分析",
                parser_source="mineru",
            ),
            ParsedElement(
                element_id="e2",
                document_id="doc_1",
                element_type="paragraph",
                page_start=4,
                page_end=4,
                order_in_document=2,
                section_path=["管理层讨论与分析"],
                text="报告期内公司刻蚀设备业务继续增长。",
                parser_source="mineru",
            ),
            ParsedElement(
                element_id="e3",
                document_id="doc_1",
                element_type="paragraph",
                page_start=4,
                page_end=4,
                order_in_document=3,
                section_path=["管理层讨论与分析"],
                text="毛利率提升主要来自产品结构优化。",
                parser_source="mineru",
            ),
            ParsedElement(
                element_id="e4",
                document_id="doc_1",
                element_type="title",
                page_start=10,
                page_end=10,
                order_in_document=4,
                section_path=["主要会计数据"],
                text="主要会计数据",
                parser_source="mineru",
            ),
            ParsedElement(
                element_id="e5",
                document_id="doc_1",
                element_type="paragraph",
                page_start=11,
                page_end=11,
                order_in_document=5,
                section_path=["主要会计数据"],
                text="公司营业收入和净利润均实现同比增长。",
                parser_source="mineru",
            ),
        ]

        result = build_chunks(
            document_id="doc_1",
            elements=elements,
            parser_version="mineru_v1",
            parent_target_chars=2000,
            child_target_chars=500,
        )

        self.assertEqual(len(result.parents), 2)
        self.assertEqual(len(result.children), 2)
        self.assertEqual(result.parents[0].section_path, ["管理层讨论与分析"])
        self.assertEqual(result.parents[1].section_path, ["主要会计数据"])
        self.assertIn("刻蚀设备业务继续增长", result.children[0].chunk_text)
        self.assertIn("净利润均实现同比增长", result.children[1].chunk_text)

    def test_build_chunks_does_not_put_table_body_into_normal_child(self) -> None:
        elements = [
            ParsedElement(
                element_id="e1",
                document_id="doc_2",
                element_type="title",
                page_start=20,
                page_end=20,
                order_in_document=1,
                section_path=["主要会计数据"],
                text="主要会计数据",
                parser_source="mineru",
            ),
            ParsedElement(
                element_id="e2",
                document_id="doc_2",
                element_type="table_caption",
                page_start=20,
                page_end=20,
                order_in_document=2,
                section_path=["主要会计数据"],
                text="表1：主要财务数据",
                parser_source="mineru",
                related_table_id="t1",
            ),
            ParsedElement(
                element_id="e3",
                document_id="doc_2",
                element_type="table",
                page_start=20,
                page_end=21,
                order_in_document=3,
                section_path=["主要会计数据"],
                text="营业收入 100 净利润 50",
                parser_source="mineru",
                related_table_id="t1",
            ),
            ParsedElement(
                element_id="e4",
                document_id="doc_2",
                element_type="paragraph",
                page_start=21,
                page_end=21,
                order_in_document=4,
                section_path=["主要会计数据"],
                text="从表1可以看出，公司营业收入和净利润均实现增长。",
                parser_source="mineru",
                related_table_id="t1",
            ),
        ]

        result = build_chunks(
            document_id="doc_2",
            elements=elements,
            parser_version="mineru_v1",
            parent_target_chars=2000,
            child_target_chars=500,
        )

        self.assertEqual(len(result.children), 1)
        self.assertIn("表1：主要财务数据", result.children[0].chunk_text)
        self.assertIn("公司营业收入和净利润均实现增长", result.children[0].chunk_text)
        self.assertNotIn("营业收入 100 净利润 50", result.children[0].chunk_text)

    def test_build_chunks_splits_long_section_into_multiple_children(self) -> None:
        elements = [
            ParsedElement(
                element_id="e1",
                document_id="doc_3",
                element_type="title",
                page_start=1,
                page_end=1,
                order_in_document=1,
                section_path=["管理层讨论与分析"],
                text="管理层讨论与分析",
                parser_source="mineru",
            ),
            ParsedElement(
                element_id="e2",
                document_id="doc_3",
                element_type="paragraph",
                page_start=1,
                page_end=1,
                order_in_document=2,
                section_path=["管理层讨论与分析"],
                text="A" * 180,
                parser_source="mineru",
            ),
            ParsedElement(
                element_id="e3",
                document_id="doc_3",
                element_type="paragraph",
                page_start=1,
                page_end=1,
                order_in_document=3,
                section_path=["管理层讨论与分析"],
                text="B" * 180,
                parser_source="mineru",
            ),
            ParsedElement(
                element_id="e4",
                document_id="doc_3",
                element_type="paragraph",
                page_start=2,
                page_end=2,
                order_in_document=4,
                section_path=["管理层讨论与分析"],
                text="C" * 180,
                parser_source="mineru",
            ),
        ]

        result = build_chunks(
            document_id="doc_3",
            elements=elements,
            parser_version="mineru_v1",
            parent_target_chars=1000,
            child_target_chars=250,
        )

        self.assertEqual(len(result.parents), 1)
        self.assertGreaterEqual(len(result.children), 2)
        self.assertTrue(all(child.parent_id == result.parents[0].chunk_id for child in result.children))

    def test_build_chunks_splits_long_section_into_multiple_parents(self) -> None:
        elements = [
            ParsedElement(
                element_id="e1",
                document_id="doc_4",
                element_type="title",
                page_start=1,
                page_end=1,
                order_in_document=1,
                section_path=["管理层讨论与分析"],
                text="管理层讨论与分析",
                parser_source="mineru",
            ),
            ParsedElement(
                element_id="e2",
                document_id="doc_4",
                element_type="paragraph",
                page_start=1,
                page_end=1,
                order_in_document=2,
                section_path=["管理层讨论与分析"],
                text="A" * 140,
                parser_source="mineru",
            ),
            ParsedElement(
                element_id="e3",
                document_id="doc_4",
                element_type="paragraph",
                page_start=2,
                page_end=2,
                order_in_document=3,
                section_path=["管理层讨论与分析"],
                text="B" * 140,
                parser_source="mineru",
            ),
            ParsedElement(
                element_id="e4",
                document_id="doc_4",
                element_type="paragraph",
                page_start=3,
                page_end=3,
                order_in_document=4,
                section_path=["管理层讨论与分析"],
                text="C" * 140,
                parser_source="mineru",
            ),
        ]

        result = build_chunks(
            document_id="doc_4",
            elements=elements,
            parser_version="mineru_v1",
            parent_target_chars=220,
            child_target_chars=500,
        )

        self.assertGreaterEqual(len(result.parents), 2)
        self.assertEqual(result.parents[0].section_path, ["管理层讨论与分析"])
        self.assertEqual(result.parents[1].section_path, ["管理层讨论与分析"])

    def test_build_chunks_skips_front_matter_without_section_path(self) -> None:
        elements = [
            ParsedElement(
                element_id="e1",
                document_id="doc_5",
                element_type="paragraph",
                page_start=1,
                page_end=1,
                order_in_document=1,
                section_path=[],
                text="2024年年度报告",
                parser_source="pdfplumber",
            ),
            ParsedElement(
                element_id="e2",
                document_id="doc_5",
                element_type="paragraph",
                page_start=2,
                page_end=2,
                order_in_document=2,
                section_path=[],
                text="致股东",
                parser_source="pdfplumber",
            ),
            ParsedElement(
                element_id="e3",
                document_id="doc_5",
                element_type="title",
                page_start=4,
                page_end=4,
                order_in_document=3,
                section_path=["第一节 重要提示、目录和释义"],
                text="第一节 重要提示、目录和释义",
                parser_source="pdfplumber",
            ),
            ParsedElement(
                element_id="e4",
                document_id="doc_5",
                element_type="paragraph",
                page_start=4,
                page_end=4,
                order_in_document=4,
                section_path=["第一节 重要提示、目录和释义"],
                text="公司董事会保证年度报告内容真实。",
                parser_source="pdfplumber",
            ),
        ]

        result = build_chunks(
            document_id="doc_5",
            elements=elements,
            parser_version="pdfplumber_v1",
            parent_target_chars=2000,
            child_target_chars=500,
        )

        self.assertEqual(len(result.parents), 1)
        self.assertEqual(result.parents[0].page_start, 4)
        self.assertNotIn("致股东", result.parents[0].chunk_text)

    def test_build_chunks_skips_appendix_and_glossary_sections(self) -> None:
        elements = [
            ParsedElement(
                element_id="e1",
                document_id="doc_6",
                element_type="title",
                page_start=6,
                page_end=6,
                order_in_document=1,
                section_path=["（一）载有公司法定代表人签名的2024年年度报告原件。"],
                text="（一）载有公司法定代表人签名的2024年年度报告原件。",
                parser_source="pdfplumber",
            ),
            ParsedElement(
                element_id="e2",
                document_id="doc_6",
                element_type="paragraph",
                page_start=7,
                page_end=7,
                order_in_document=2,
                section_path=["（一）载有公司法定代表人签名的2024年年度报告原件。"],
                text="ERP 指 企业资源计划。",
                parser_source="pdfplumber",
            ),
            ParsedElement(
                element_id="e3",
                document_id="doc_6",
                element_type="title",
                page_start=9,
                page_end=9,
                order_in_document=3,
                section_path=["第二节 公司简介和主要财务指标"],
                text="第二节 公司简介和主要财务指标",
                parser_source="pdfplumber",
            ),
            ParsedElement(
                element_id="e4",
                document_id="doc_6",
                element_type="paragraph",
                page_start=9,
                page_end=9,
                order_in_document=4,
                section_path=["第二节 公司简介和主要财务指标"],
                text="公司股票简称：北方华创",
                parser_source="pdfplumber",
            ),
        ]

        result = build_chunks(
            document_id="doc_6",
            elements=elements,
            parser_version="pdfplumber_v1",
            parent_target_chars=2000,
            child_target_chars=500,
        )

        self.assertEqual(len(result.parents), 1)
        self.assertEqual(result.parents[0].section_path, ["第二节 公司简介和主要财务指标"])
        self.assertNotIn("ERP 指", result.parents[0].chunk_text)


if __name__ == "__main__":
    unittest.main()
