from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from frontend.streamlit_app.state.workbench_state import (
    get_last_analysis_result,
    get_selected_eval_case_id,
    set_last_analysis_result,
    set_selected_eval_case_id,
)
from shared.contracts.analysis_response_envelope import AnalysisResponseEnvelope


class StreamlitWorkbenchStateTest(unittest.TestCase):
    def test_state_helpers_store_last_analysis_result_and_selected_case(self) -> None:
        bucket: dict[str, object] = {}
        envelope = AnalysisResponseEnvelope(session_id="sess_demo")

        set_last_analysis_result(bucket, envelope)
        set_selected_eval_case_id(bucket, "dual_001")

        self.assertEqual(get_last_analysis_result(bucket).session_id, "sess_demo")
        self.assertEqual(get_selected_eval_case_id(bucket), "dual_001")


if __name__ == "__main__":
    unittest.main()
