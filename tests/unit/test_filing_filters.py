from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.retrieval.acquisition_models import FilingRecord
from finsight_agent.capabilities.retrieval.filing_filters import classify_filing


class FilingFiltersTest(unittest.TestCase):
    def test_classify_annual_report_excludes_summary(self) -> None:
        record = FilingRecord(
            source_name="sse",
            market="sse",
            company_code="688981",
            company_name="中芯国际",
            title="2024年年度报告摘要",
            publish_date="2025-03-29",
            source_doc_type="regular",
            pdf_url="https://example.test/a.pdf",
        )

        self.assertIsNone(classify_filing(record))

    def test_classify_semiannual_report_before_annual_keyword(self) -> None:
        record = FilingRecord(
            source_name="sse",
            market="sse",
            company_code="688012",
            company_name="中微公司",
            title="2025年半年度报告",
            publish_date="2025-08-29",
            source_doc_type="regular",
            pdf_url="https://example.test/semiannual.pdf",
        )

        result = classify_filing(record)

        self.assertIsNotNone(result)
        self.assertEqual(result.normalized_doc_type, "semiannual_report")

    def test_classify_major_announcement_matches_capacity_expansion(self) -> None:
        record = FilingRecord(
            source_name="cninfo",
            market="szse",
            company_code="002371",
            company_name="北方华创",
            title="关于投资建设半导体装备产能扩张项目的公告",
            publish_date="2025-04-18",
            source_doc_type="announcement",
            pdf_url="https://example.test/b.pdf",
        )

        result = classify_filing(record)

        self.assertIsNotNone(result)
        self.assertEqual(result.normalized_doc_type, "major_announcement")
        self.assertEqual(result.announcement_type, "capacity_expansion")

    def test_classify_ignores_review_inquiry_reply_material(self) -> None:
        record = FilingRecord(
            source_name="sse",
            market="sse",
            company_code="688072",
            company_name="拓荆科技",
            title="关于拓荆科技股份有限公司向特定对象发行股票申请文件的审核问询函回复",
            publish_date="2025-12-30",
            source_doc_type="announcement",
            pdf_url="https://example.test/review.pdf",
        )

        self.assertIsNone(classify_filing(record))


if __name__ == "__main__":
    unittest.main()
