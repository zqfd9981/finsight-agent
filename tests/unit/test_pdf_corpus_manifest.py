from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.config.settings import load_settings
from finsight_agent.capabilities.retrieval.corpus_manifest import load_sample_universe


class PdfCorpusSettingsTest(unittest.TestCase):
    def test_load_settings_exposes_retrieval_acquisition_paths(self) -> None:
        settings = load_settings()

        self.assertTrue(settings.retrieval.manifest_path.name.endswith(".yaml"))
        self.assertEqual(settings.retrieval.raw_filings_root.name, "raw_filings")
        self.assertEqual(settings.retrieval.status_root.name, "corpus_status")
        self.assertGreaterEqual(settings.retrieval.default_pilot_company_count, 8)


class PdfCorpusManifestLoaderTest(unittest.TestCase):
    def test_load_sample_universe_reads_companies_and_targets(self) -> None:
        manifest = load_sample_universe(load_settings().retrieval.manifest_path)

        self.assertEqual(manifest.theme, "semiconductor")
        self.assertEqual(len(manifest.companies), 50)
        self.assertEqual(manifest.segment_targets["equipment"], 12)

    def test_select_companies_prefers_high_priority_for_pilot(self) -> None:
        manifest = load_sample_universe(load_settings().retrieval.manifest_path)

        pilot = manifest.select_companies(limit=10)

        self.assertEqual(len(pilot), 10)
        self.assertTrue(all(company.priority in {"high", "medium"} for company in pilot))


if __name__ == "__main__":
    unittest.main()
