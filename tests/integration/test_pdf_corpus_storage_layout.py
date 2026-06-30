from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.retrieval.acquisition_models import FilingRecord
from finsight_agent.capabilities.retrieval.storage import (
    build_output_path,
    write_status_snapshot,
)


class PdfCorpusStorageLayoutTest(unittest.TestCase):
    def test_build_output_path_uses_company_doc_type_and_year(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            record = FilingRecord(
                source_name="sse",
                market="sse",
                company_code="688981",
                company_name="中芯国际",
                title="2024年年度报告",
                publish_date="2025-03-29",
                source_doc_type="regular",
                pdf_url="https://example.test/a.pdf",
            )

            output_path = build_output_path(
                root=Path(temp_dir),
                record=record,
                normalized_doc_type="annual_report",
                report_year=2024,
            )

            self.assertIn("688981_中芯国际", str(output_path))
            self.assertIn("annual", str(output_path))
            self.assertTrue(str(output_path).endswith(".pdf"))

    def test_write_status_snapshot_persists_json_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_status_snapshot(
                status_root=Path(temp_dir),
                snapshot_name="pilot_download_status",
                payload={"downloaded": 3, "failed": 1},
            )

            self.assertTrue(path.exists())
            self.assertIn("pilot_download_status", path.name)


if __name__ == "__main__":
    unittest.main()
