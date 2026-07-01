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

from finsight_agent.control_plane.session.models import SessionSnapshot
from finsight_agent.control_plane.session.repository import SessionRepository
from shared.contracts.session_context import SessionContext


class SessionRepositoryTest(unittest.TestCase):
    def test_repository_returns_none_when_snapshot_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = SessionRepository(storage_dir=temp_dir)

            snapshot = repository.load("sess_missing")

        self.assertIsNone(snapshot)

    def test_repository_can_save_and_load_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = SessionRepository(storage_dir=temp_dir)
            snapshot = SessionSnapshot(
                session_id="sess_001",
                last_query="宁德时代 2024 年净利润是多少？",
                last_query_mode="first_turn",
                last_intent="metric_lookup",
                last_follow_up_type="none",
                last_plan_stages=[
                    "query_structured_data",
                    "synthesize_brief_answer",
                ],
                context=SessionContext(
                    session_id="sess_001",
                    active_topic="宁德时代 2024_annual net_profit",
                    active_candidates=["宁德时代"],
                    history_summary="上一轮已完成宁德时代 2024 年净利润查询。",
                    available_follow_ups=["drilldown", "expand"],
                ),
                updated_at="2026-07-01T12:00:00+08:00",
            )

            repository.save(snapshot)
            loaded = repository.load("sess_001")

        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.session_id, "sess_001")
        self.assertEqual(loaded.last_intent, "metric_lookup")
        self.assertEqual(loaded.last_plan_stages[0], "query_structured_data")
        self.assertEqual(loaded.context.active_topic, "宁德时代 2024_annual net_profit")
        self.assertEqual(loaded.context.active_candidates, ["宁德时代"])
        self.assertEqual(loaded.updated_at, "2026-07-01T12:00:00+08:00")

    def test_repository_overwrites_same_session_id_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = SessionRepository(storage_dir=temp_dir)
            first = SessionSnapshot(
                session_id="sess_same",
                last_query="宁德时代 2024 年净利润是多少？",
                last_query_mode="first_turn",
                last_intent="metric_lookup",
                last_follow_up_type="none",
                last_plan_stages=["query_structured_data"],
                context=SessionContext(
                    session_id="sess_same",
                    active_topic="宁德时代 2024_annual net_profit",
                    active_candidates=["宁德时代"],
                    history_summary="上一轮已完成指标查询。",
                    available_follow_ups=["drilldown"],
                ),
                updated_at="2026-07-01T12:00:00+08:00",
            )
            second = SessionSnapshot(
                session_id="sess_same",
                last_query="继续展开一下同比变化原因",
                last_query_mode="follow_up",
                last_intent="evidence_lookup",
                last_follow_up_type="drilldown",
                last_plan_stages=["retrieve_evidence", "synthesize_report"],
                context=SessionContext(
                    session_id="sess_same",
                    active_topic="宁德时代净利润同比变化原因",
                    active_candidates=["宁德时代"],
                    key_evidence_refs=["ev_001", "ev_002"],
                    history_summary="上一轮已补充证据引用。",
                    available_follow_ups=["drilldown", "expand"],
                ),
                updated_at="2026-07-01T12:05:00+08:00",
            )

            repository.save(first)
            repository.save(second)
            loaded = repository.load("sess_same")

        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.last_query_mode, "follow_up")
        self.assertEqual(loaded.last_intent, "evidence_lookup")
        self.assertEqual(loaded.context.key_evidence_refs, ["ev_001", "ev_002"])
        self.assertEqual(loaded.updated_at, "2026-07-01T12:05:00+08:00")


if __name__ == "__main__":
    unittest.main()
