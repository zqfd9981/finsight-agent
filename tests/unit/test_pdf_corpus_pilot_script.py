from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.retrieval.acquisition_service import DownloadResult
from finsight_agent.capabilities.retrieval.acquisition_models import SampleCompany
from finsight_agent.capabilities.retrieval.corpus_manifest import SampleUniverse
from finsight_agent.config.settings import RetrievalSettings

from scripts.download_pdf_corpus_pilot import run_pilot_download


class PdfCorpusPilotScriptTest(unittest.TestCase):
    def test_run_pilot_download_uses_settings_default_and_prints_json(self) -> None:
        sample_universe = SampleUniverse(
            theme="semiconductor",
            segment_targets={"equipment": 1},
            companies=[
                SampleCompany(
                    company_code="688981",
                    company_name="中芯国际",
                    segment="manufacturing_idm",
                    subsegment="foundry",
                    priority="high",
                )
            ],
        )

        class FakeService:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def download_pilot_filings(self, **kwargs):
                self.calls.append(dict(kwargs))
                return DownloadResult(
                    downloaded_count=2,
                    failed_count=1,
                    status_snapshot_path=Path("var/data/corpus_status/pilot_download_status.json"),
                )

        fake_service = FakeService()
        fake_settings = type(
            "FakeSettings",
            (),
            {
                "retrieval": RetrievalSettings(
                    manifest_path=Path("var/data/corpus_manifests/semiconductor_sample_universe.yaml"),
                    raw_filings_root=Path("var/data/raw_filings"),
                    status_root=Path("var/data/corpus_status"),
                    default_pilot_company_count=8,
                )
            },
        )()

        with (
            mock.patch(
                "scripts.download_pdf_corpus_pilot.load_settings",
                return_value=fake_settings,
            ),
            mock.patch(
                "scripts.download_pdf_corpus_pilot.load_sample_universe",
                return_value=sample_universe,
            ),
            mock.patch(
                "scripts.download_pdf_corpus_pilot.build_pdf_corpus_acquisition_service",
                return_value=fake_service,
            ),
            mock.patch("sys.stdout", new=io.StringIO()) as fake_stdout,
        ):
            exit_code = run_pilot_download(
                ["--start-date", "2024-01-01", "--end-date", "2025-12-31"]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(fake_service.calls), 1)
        self.assertEqual(fake_service.calls[0]["pilot_company_count"], 8)
        payload = json.loads(fake_stdout.getvalue())
        self.assertEqual(payload["downloaded_count"], 2)
        self.assertEqual(payload["failed_count"], 1)


if __name__ == "__main__":
    unittest.main()
