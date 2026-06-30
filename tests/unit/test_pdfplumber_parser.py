from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.infra.document_parsers.pdfplumber_parser import PdfplumberDocumentParser


class _FakePage:
    def __init__(self, text: str, tables: list[list[list[str]]] | None = None) -> None:
        self._text = text
        self._tables = tables or []

    def extract_text(self) -> str:
        return self._text

    def extract_tables(self) -> list[list[list[str]]]:
        return self._tables


class _FakePdf:
    def __init__(self, pages: list[_FakePage]) -> None:
        self.pages = pages

    def __enter__(self) -> _FakePdf:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class PdfplumberDocumentParserTest(unittest.TestCase):
    def test_parse_builds_minimal_standardized_artifact(self) -> None:
        parser = PdfplumberDocumentParser()
        fake_pdf = _FakePdf(
            [
                _FakePage("2025年半年度报告\n\n管理层讨论与分析"),
                _FakePage("表1：主要财务数据\n\n报告期内公司业务继续增长。"),
            ]
        )

        with patch(
            "finsight_agent.infra.document_parsers.pdfplumber_parser.pdfplumber.open",
            return_value=fake_pdf,
        ):
            artifact = parser.parse(Path("sample.pdf"))

        self.assertEqual(artifact.document["document_id"], "sample")
        self.assertEqual(artifact.document["page_count"], 2)
        self.assertEqual(len(artifact.elements), 4)
        self.assertEqual(artifact.elements[0].element_type, "title")
        self.assertEqual(artifact.elements[2].element_type, "table_caption")
        self.assertEqual(artifact.elements[-1].text, "报告期内公司业务继续增长。")
        self.assertEqual(artifact.tables, [])
        self.assertIsNotNone(artifact.parse_report)
        self.assertEqual(artifact.parse_report.primary_parser, "pdfplumber")
        self.assertEqual(artifact.parse_report.parser_version, "pdfplumber_v1")
        self.assertEqual(artifact.parse_report.parsed_element_count, 4)

    def test_parse_marks_chapter_like_line_as_title_and_updates_section_path(self) -> None:
        parser = PdfplumberDocumentParser()
        fake_pdf = _FakePdf(
            [
                _FakePage("第一节 重要提示、目录和释义\n\n公司董事会保证年度报告内容真实。"),
                _FakePage("第二节 公司简介和主要财务指标\n\n公司股票简称：北方华创"),
            ]
        )

        with patch(
            "finsight_agent.infra.document_parsers.pdfplumber_parser.pdfplumber.open",
            return_value=fake_pdf,
        ):
            artifact = parser.parse(Path("sample.pdf"))

        self.assertEqual(artifact.elements[0].element_type, "title")
        self.assertEqual(artifact.elements[0].section_path, ["第一节 重要提示、目录和释义"])
        self.assertEqual(artifact.elements[1].section_path, ["第一节 重要提示、目录和释义"])
        self.assertEqual(artifact.elements[2].element_type, "title")
        self.assertEqual(artifact.elements[3].section_path, ["第二节 公司简介和主要财务指标"])

    def test_parse_recognizes_numeric_chapter_titles(self) -> None:
        parser = PdfplumberDocumentParser()
        fake_pdf = _FakePdf(
            [
                _FakePage("一、管理层讨论与分析\n\n报告期内公司收入稳步增长。"),
                _FakePage("（一）主营业务分析\n\n刻蚀设备业务继续扩张。"),
            ]
        )

        with patch(
            "finsight_agent.infra.document_parsers.pdfplumber_parser.pdfplumber.open",
            return_value=fake_pdf,
        ):
            artifact = parser.parse(Path("sample.pdf"))

        self.assertEqual(artifact.elements[0].element_type, "title")
        self.assertEqual(artifact.elements[0].section_path, ["一、管理层讨论与分析"])
        self.assertEqual(artifact.elements[2].element_type, "title")
        self.assertEqual(artifact.elements[3].section_path, ["（一）主营业务分析"])

    def test_parse_extracts_basic_tables_into_table_artifacts(self) -> None:
        parser = PdfplumberDocumentParser()
        fake_pdf = _FakePdf(
            [
                _FakePage(
                    "表1：主要财务数据\n\n详见下表。",
                    tables=[
                        [
                            ["指标", "本期"],
                            ["营业收入", "100"],
                            ["净利润", "50"],
                        ]
                    ],
                )
            ]
        )

        with patch(
            "finsight_agent.infra.document_parsers.pdfplumber_parser.pdfplumber.open",
            return_value=fake_pdf,
        ):
            artifact = parser.parse(Path("sample.pdf"))

        self.assertEqual(len(artifact.tables), 1)
        self.assertEqual(artifact.tables[0].caption_text, "表1：主要财务数据")
        self.assertIn("营业收入", artifact.tables[0].table_text)
        self.assertIn("| 指标 | 本期 |", artifact.tables[0].table_markdown)
        self.assertEqual(artifact.parse_report.parsed_table_count, 1)

    def test_parse_does_not_treat_catalog_lines_as_section_titles(self) -> None:
        parser = PdfplumberDocumentParser()
        fake_pdf = _FakePdf(
            [
                _FakePage(
                    "目录\n\n第一节重要提示、目录和释义........................4\n第二节公司简介和主要财务指标........................9"
                )
            ]
        )

        with patch(
            "finsight_agent.infra.document_parsers.pdfplumber_parser.pdfplumber.open",
            return_value=fake_pdf,
        ):
            artifact = parser.parse(Path("sample.pdf"))

        self.assertEqual(artifact.elements, [])

    def test_parse_filters_page_number_only_fragments(self) -> None:
        parser = PdfplumberDocumentParser()
        fake_pdf = _FakePdf(
            [
                _FakePage("2024年年度报告\n\n1\n\n管理层讨论与分析\n\n报告期内公司业务继续增长。")
            ]
        )

        with patch(
            "finsight_agent.infra.document_parsers.pdfplumber_parser.pdfplumber.open",
            return_value=fake_pdf,
        ):
            artifact = parser.parse(Path("sample.pdf"))

        self.assertTrue(all(element.text != "1" for element in artifact.elements))
        self.assertTrue(any(element.text == "报告期内公司业务继续增长。" for element in artifact.elements))

    def test_parse_skips_catalog_only_pages(self) -> None:
        parser = PdfplumberDocumentParser()
        fake_pdf = _FakePdf(
            [
                _FakePage(
                    "目录\n\n第一节重要提示、目录和释义........................4\n第二节公司简介和主要财务指标........................9"
                ),
                _FakePage("第一节 重要提示、目录和释义\n\n公司董事会保证年度报告内容真实。"),
            ]
        )

        with patch(
            "finsight_agent.infra.document_parsers.pdfplumber_parser.pdfplumber.open",
            return_value=fake_pdf,
        ):
            artifact = parser.parse(Path("sample.pdf"))

        self.assertTrue(all(element.page_start != 1 for element in artifact.elements))
        self.assertEqual(artifact.elements[0].element_type, "title")
        self.assertEqual(artifact.elements[0].text, "第一节 重要提示、目录和释义")

    def test_parse_skips_catalog_page_even_with_report_header(self) -> None:
        parser = PdfplumberDocumentParser()
        fake_pdf = _FakePdf(
            [
                _FakePage(
                    "北方华创科技集团股份有限公司2024年年度报告全文\n\n"
                    "目录\n\n"
                    "第一节重要提示、目录和释义........................4\n"
                    "第二节公司简介和主要财务指标........................9"
                ),
                _FakePage("第二节 公司简介和主要财务指标\n\n公司股票简称：北方华创"),
            ]
        )

        with patch(
            "finsight_agent.infra.document_parsers.pdfplumber_parser.pdfplumber.open",
            return_value=fake_pdf,
        ):
            artifact = parser.parse(Path("sample.pdf"))

        self.assertTrue(all(element.page_start != 1 for element in artifact.elements))
        self.assertEqual(artifact.elements[0].text, "第二节 公司简介和主要财务指标")

    def test_parse_skips_appendix_inventory_page(self) -> None:
        parser = PdfplumberDocumentParser()
        fake_pdf = _FakePdf(
            [
                _FakePage(
                    "备查文件目录\n\n"
                    "（一）载有公司法定代表人签名的2024年年度报告原件。\n"
                    "（二）载有公司法定代表人、总裁、财务负责人签名并盖章的财务报表。"
                ),
                _FakePage("第一节 重要提示、目录和释义\n\n公司董事会保证年度报告内容真实。"),
            ]
        )

        with patch(
            "finsight_agent.infra.document_parsers.pdfplumber_parser.pdfplumber.open",
            return_value=fake_pdf,
        ):
            artifact = parser.parse(Path("sample.pdf"))

        self.assertTrue(all(element.page_start != 1 for element in artifact.elements))
        self.assertEqual(artifact.elements[0].text, "第一节 重要提示、目录和释义")

    def test_parse_skips_glossary_only_page(self) -> None:
        parser = PdfplumberDocumentParser()
        fake_pdf = _FakePdf(
            [
                _FakePage(
                    "释义\n\n"
                    "释义项 指 释义内容\n"
                    "公司、本公司 指 北方华创科技集团股份有限公司\n"
                    "中国证监会 指 中国证券监督管理委员会"
                ),
                _FakePage("一、管理层讨论与分析\n\n报告期内公司收入稳步增长。"),
            ]
        )

        with patch(
            "finsight_agent.infra.document_parsers.pdfplumber_parser.pdfplumber.open",
            return_value=fake_pdf,
        ):
            artifact = parser.parse(Path("sample.pdf"))

        self.assertTrue(all(element.page_start != 1 for element in artifact.elements))
        self.assertEqual(artifact.elements[0].text, "一、管理层讨论与分析")

    def test_parse_filters_repeated_report_header_line(self) -> None:
        parser = PdfplumberDocumentParser()
        fake_pdf = _FakePdf(
            [
                _FakePage(
                    "北方华创科技集团股份有限公司2024年年度报告全文\n\n"
                    "第二节 公司简介和主要财务指标\n\n"
                    "公司股票简称：北方华创"
                )
            ]
        )

        with patch(
            "finsight_agent.infra.document_parsers.pdfplumber_parser.pdfplumber.open",
            return_value=fake_pdf,
        ):
            artifact = parser.parse(Path("sample.pdf"))

        self.assertTrue(all("全文" not in element.text for element in artifact.elements))
        self.assertEqual(artifact.elements[0].text, "第二节 公司简介和主要财务指标")


if __name__ == "__main__":
    unittest.main()
