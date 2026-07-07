from __future__ import annotations

import importlib
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


class StreamlitEntrySmokeTest(unittest.TestCase):
    def test_streamlit_entry_module_imports_without_runtime(self) -> None:
        # Streamlit 入口在 import 期会调 ``bootstrap_streamlit_app``，
        # 后者包含 ``st.set_page_config`` 等需要 Streamlit runtime 的调用。
        # 实现必须用 try/except 容忍非 runtime 场景，让本测试不依赖 Streamlit 服务。
        mod = importlib.import_module("frontend.streamlit_app.streamlit_entry")

        self.assertTrue(hasattr(mod, "bootstrap_streamlit_app"))
        self.assertTrue(callable(getattr(mod, "bootstrap_streamlit_app")))

    def test_streamlit_entry_exposes_page_constants(self) -> None:
        mod = importlib.import_module("frontend.streamlit_app.streamlit_entry")

        self.assertEqual(getattr(mod, "PAGE_ANALYSIS", None), "分析视图")
        self.assertEqual(getattr(mod, "PAGE_DEBUG", None), "调试视图")
        self.assertEqual(getattr(mod, "PAGE_EVAL", None), "评测视图")


class StreamlitRenderShellTest(unittest.TestCase):
    def test_each_page_exposes_render_function(self) -> None:
        from frontend.streamlit_app.pages import analysis_view, debug_view, eval_view

        self.assertTrue(callable(getattr(analysis_view, "render_analysis_view", None)))
        self.assertTrue(callable(getattr(debug_view, "render_debug_view", None)))
        self.assertTrue(callable(getattr(eval_view, "render_eval_view", None)))


if __name__ == "__main__":
    unittest.main()
