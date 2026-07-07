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


import yaml  # noqa: E402

from frontend.streamlit_app.config_resolver import (  # noqa: E402
    DEFAULT_BACKEND_BASE_URL,
    DEFAULT_BACKEND_HOST,
    DEFAULT_BACKEND_PORT,
    DEFAULT_FRONTEND_HOST,
    DEFAULT_FRONTEND_PORT,
    resolve_workbench_config,
)


class StreamlitConfigResolverTest(unittest.TestCase):
    def test_resolve_workbench_config_returns_defaults_when_section_missing(self) -> None:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as handle:
            yaml.safe_dump({"app": {"name": "x"}}, handle, allow_unicode=True)
            tmp_path = Path(handle.name)

        try:
            cfg = resolve_workbench_config(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

        self.assertEqual(cfg["backend_host"], DEFAULT_BACKEND_HOST)
        self.assertEqual(cfg["backend_port"], DEFAULT_BACKEND_PORT)
        self.assertEqual(cfg["backend_base_url"], DEFAULT_BACKEND_BASE_URL)
        self.assertEqual(cfg["frontend_host"], DEFAULT_FRONTEND_HOST)
        self.assertEqual(cfg["frontend_port"], DEFAULT_FRONTEND_PORT)

    def test_resolve_workbench_config_reads_workbench_section(self) -> None:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as handle:
            yaml.safe_dump(
                {
                    "app": {
                        "workbench": {
                            "backend_base_url": "http://10.0.0.5:9000",
                            "backend_host": "10.0.0.5",
                            "backend_port": 9000,
                            "frontend_host": "0.0.0.0",
                            "frontend_port": 8601,
                        }
                    }
                },
                handle,
                allow_unicode=True,
            )
            tmp_path = Path(handle.name)

        try:
            cfg = resolve_workbench_config(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

        self.assertEqual(cfg["backend_host"], "10.0.0.5")
        self.assertEqual(cfg["backend_port"], 9000)
        self.assertEqual(cfg["backend_base_url"], "http://10.0.0.5:9000")
        self.assertEqual(cfg["frontend_host"], "0.0.0.0")
        self.assertEqual(cfg["frontend_port"], 8601)

    def test_resolve_workbench_config_handles_missing_file(self) -> None:
        nonexistent = Path(tempfile.gettempdir()) / "definitely-does-not-exist.yaml"
        if nonexistent.exists():
            nonexistent.unlink()

        cfg = resolve_workbench_config(nonexistent)

        self.assertEqual(cfg["backend_base_url"], DEFAULT_BACKEND_BASE_URL)


if __name__ == "__main__":
    unittest.main()
