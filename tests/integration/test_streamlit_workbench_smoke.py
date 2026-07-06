from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from frontend.streamlit_app.app import main


class StreamlitWorkbenchSmokeTest(unittest.TestCase):
    def test_app_main_exposes_three_workbench_pages(self) -> None:
        payload = main()

        self.assertEqual(
            payload["pages"],
            ["分析视图", "调试视图", "评测视图"],
        )


if __name__ == "__main__":
    unittest.main()
