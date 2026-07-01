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

from finsight_agent.capabilities.structured_data.models import MetricRecord
from finsight_agent.capabilities.structured_data.repository import MetricRepository
from finsight_agent.capabilities.structured_data.service import StructuredDataService
from finsight_agent.control_plane.orchestrator.service import OrchestratorService
from finsight_agent.control_plane.session.repository import SessionRepository
from finsight_agent.control_plane.session.service import SessionService
from finsight_agent.workbench_backend_api.service import WorkbenchBackendApiService
from shared.contracts.analysis_request import AnalysisRequest


class MetricLookupStructuredDataIntegrationTest(unittest.TestCase):
    def test_metric_lookup_returns_real_metric_value_instead_of_todo(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = MetricRepository(storage_dir=Path(temp_dir) / "metric_store")
            repository.save_records(
                [
                    MetricRecord(
                        company_name="宁德时代",
                        company_code="300750",
                        metric_name="net_profit",
                        metric_label="归母净利润",
                        time_scope="2024_annual",
                        period_end="2024-12-31",
                        value="507.45",
                        unit="亿元",
                        currency="CNY",
                        source_type="local_filing_table",
                        source_document_id="doc_001",
                        source_table_id="table_001",
                        source_caption="主要会计数据",
                        confidence="high",
                    )
                ]
            )
            structured_data_service = StructuredDataService(metric_repository=repository)
            orchestrator_service = OrchestratorService(
                structured_data_service=structured_data_service
            )
            workbench_service = WorkbenchBackendApiService(
                orchestrator_service=orchestrator_service,
                session_service=SessionService(
                    repository=SessionRepository(storage_dir=Path(temp_dir) / "sessions")
                ),
            )

            envelope = workbench_service.build_response(
                AnalysisRequest(query="宁德时代 2024 年净利润是多少？")
            )

        self.assertNotIn("TODO", envelope.response.summary)
        self.assertIn("507.45", envelope.response.summary)
        self.assertIn("亿元", envelope.response.summary)


if __name__ == "__main__":
    unittest.main()
