from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

# 让测试同时可以导入后端包和顶层 shared 包。
for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


class ProjectSkeletonTest(unittest.TestCase):
    def test_required_top_level_directories_exist(self) -> None:
        """校验新 spec 要求的顶层工程目录已经落地。"""
        required_dirs = [
            "frontend",
            "backend",
            "shared",
            "config",
            "fixtures",
            "tests",
            "scripts",
            "var",
            "docs",
            "openspec",
        ]

        for directory in required_dirs:
            with self.subTest(directory=directory):
                self.assertTrue((REPO_ROOT / directory).is_dir())

    def test_legacy_top_level_directories_have_been_retired(self) -> None:
        """校验旧的主骨架目录已经不再作为当前实现入口存在。"""
        retired_dirs = [
            "apps",
            "src",
        ]

        for directory in retired_dirs:
            with self.subTest(directory=directory):
                self.assertFalse((REPO_ROOT / directory).exists())

    def test_minimal_fast_path_files_exist(self) -> None:
        """校验前后端分离后的第一版快路径骨架文件已经创建。"""
        required_files = [
            "backend/apps/api/main.py",
            "backend/apps/api/analysis_turns.py",
            "frontend/streamlit_app/app.py",
            "frontend/streamlit_app/api_client.py",
            "shared/contracts/router_result.py",
            "shared/contracts/plan.py",
            "shared/contracts/session_context.py",
            "shared/contracts/stage_observation.py",
            "shared/contracts/evidence_bundle.py",
            "shared/contracts/final_response.py",
            "shared/contracts/trace_block.py",
            "shared/contracts/guardrail_or_error_response.py",
            "shared/contracts/analysis_request.py",
            "shared/contracts/analysis_response_envelope.py",
            "shared/enums/intent.py",
            "shared/enums/stage_name.py",
            "backend/src/finsight_agent/control_plane/router/service.py",
            "backend/src/finsight_agent/control_plane/planner/service.py",
            "backend/src/finsight_agent/control_plane/session/models.py",
            "backend/src/finsight_agent/control_plane/session/repository.py",
            "backend/src/finsight_agent/control_plane/session/service.py",
            "backend/src/finsight_agent/control_plane/session/extractor.py",
            "backend/src/finsight_agent/capabilities/structured_data/service.py",
            "backend/src/finsight_agent/capabilities/reporting/service.py",
            "backend/src/finsight_agent/workbench_backend_api/service.py",
            "config/app.yaml",
            "config/logging.yaml",
            "config/retrieval.yaml",
            "fixtures/contracts/router_result.metric_lookup.json",
            "fixtures/contracts/plan.metric_lookup.json",
            "fixtures/contracts/final_response.success.json",
            "fixtures/contracts/analysis_request.first_turn.json",
            "fixtures/contracts/analysis_request.follow_up.json",
            "fixtures/contracts/analysis_response_envelope.success.json",
            "docs/finsight/api-boundary-deferred-fields.md",
            "openspec/specs/workbench-backend-api-boundary/spec.md",
        ]

        for file_path in required_files:
            with self.subTest(file_path=file_path):
                self.assertTrue((REPO_ROOT / file_path).is_file())

    def test_contract_and_backend_modules_can_be_imported(self) -> None:
        """校验共享 contract 与后端最小服务骨架可以被稳定导入。"""
        from finsight_agent.control_plane.router.service import RouterService
        from finsight_agent.control_plane.session.service import SessionService
        from finsight_agent.workbench_backend_api.service import WorkbenchBackendApiService
        from shared.contracts.analysis_request import AnalysisRequest
        from shared.contracts.analysis_response_envelope import AnalysisResponseEnvelope
        from shared.contracts.evidence_bundle import EvidenceBundle
        from shared.contracts.final_response import FinalResponse
        from shared.contracts.guardrail_or_error_response import (
            GuardrailOrErrorResponse,
        )
        from shared.contracts.plan import Plan
        from shared.contracts.router_result import RouterResult
        from shared.contracts.session_context import SessionContext
        from shared.contracts.stage_observation import StageObservation
        from shared.contracts.trace_block import TraceBlock
        from shared.enums.intent import Intent
        from shared.enums.stage_name import StageName

        self.assertEqual(RouterResult().version, "v1")
        self.assertEqual(Plan().version, "v1")
        self.assertEqual(SessionContext().version, "v1")
        self.assertEqual(StageObservation().version, "v1")
        self.assertEqual(EvidenceBundle().version, "v1")
        self.assertEqual(FinalResponse().version, "v1")
        self.assertEqual(TraceBlock().version, "v1")
        self.assertEqual(GuardrailOrErrorResponse().version, "v1")
        self.assertEqual(AnalysisRequest().version, "v1")
        self.assertEqual(AnalysisResponseEnvelope().version, "v1")
        self.assertEqual(Intent.METRIC_LOOKUP.value, "metric_lookup")
        self.assertEqual(StageName.QUERY_STRUCTURED_DATA.value, "query_structured_data")
        self.assertEqual(
            RouterService().build_metric_lookup_stub().intent,
            Intent.METRIC_LOOKUP.value,
        )
        self.assertTrue(
            WorkbenchBackendApiService().build_response(
                AnalysisRequest(query="宁德时代 2024 年净利润是多少？")
            ).response.session_id.startswith("sess_")
        )
        self.assertTrue(hasattr(SessionService(), "load_context"))

    def test_orchestrator_modules_can_be_imported(self) -> None:
        """校验 orchestrator 首版模块可以被稳定导入。"""
        import finsight_agent.control_plane.orchestrator.models as orchestrator_models
        import finsight_agent.control_plane.orchestrator.observation_builder as observation_builder
        import finsight_agent.control_plane.orchestrator.service as orchestrator_service

        self.assertTrue(hasattr(orchestrator_models, "OrchestrationResult"))
        self.assertTrue(hasattr(observation_builder, "build_stage_observation"))
        self.assertTrue(hasattr(orchestrator_service, "OrchestratorService"))

    def test_contract_fixture_is_valid_json(self) -> None:
        """校验 contract fixture 至少能被正常解析。"""
        fixture_path = REPO_ROOT / "fixtures/contracts/router_result.metric_lookup.json"
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["version"], "v1")
        self.assertEqual(payload["intent"], "metric_lookup")

    def test_api_boundary_fixtures_match_expected_shape(self) -> None:
        """校验 API boundary 的示例 fixture 与期望结构基本对齐。"""
        first_turn = json.loads(
            (REPO_ROOT / "fixtures/contracts/analysis_request.first_turn.json").read_text(
                encoding="utf-8"
            )
        )
        follow_up = json.loads(
            (REPO_ROOT / "fixtures/contracts/analysis_request.follow_up.json").read_text(
                encoding="utf-8"
            )
        )
        success_response = json.loads(
            (
                REPO_ROOT
                / "fixtures/contracts/analysis_response_envelope.success.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(first_turn["version"], "v1")
        self.assertEqual(first_turn["query_mode"], "first_turn")
        self.assertIsNone(first_turn["session_id"])
        self.assertEqual(follow_up["query_mode"], "follow_up")
        self.assertTrue(follow_up["session_id"])
        self.assertEqual(success_response["version"], "v1")
        self.assertIn("response", success_response)
        self.assertIn("trace_blocks", success_response)
        self.assertEqual(success_response["trace_blocks"][0]["block_type"], "routing")

    def test_frontend_does_not_import_backend_internal_modules(self) -> None:
        """校验前端入口没有直接依赖后端内部模块。"""
        frontend_entry = REPO_ROOT / "frontend/streamlit_app/app.py"
        source = frontend_entry.read_text(encoding="utf-8")

        forbidden_markers = [
            "finsight_agent.control_plane",
            "finsight_agent.capabilities",
            "finsight_agent.infra",
        ]

        for marker in forbidden_markers:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, source)

    def test_frontend_client_uses_boundary_objects_only(self) -> None:
        """校验前端 client 只依赖 shared contract，不直接引用后端实现。"""
        client_source = (REPO_ROOT / "frontend/streamlit_app/api_client.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("shared.contracts.analysis_request", client_source)
        self.assertIn("shared.contracts.analysis_response_envelope", client_source)
        self.assertNotIn("finsight_agent.", client_source)

    def test_backend_entry_exposes_minimal_analysis_turns_route_metadata(self) -> None:
        """校验后端入口已暴露分析轮次 API 元数据。"""
        from backend.apps.api.analysis_turns import ANALYSIS_TURNS_PATH, build_route_metadata

        route_metadata = build_route_metadata()

        self.assertEqual(ANALYSIS_TURNS_PATH, "/api/v1/analysis/turns")
        self.assertEqual(route_metadata["method"], "POST")
        self.assertEqual(route_metadata["path"], ANALYSIS_TURNS_PATH)


if __name__ == "__main__":
    unittest.main()
