from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_ROOT = REPO_ROOT / "backend" / "src" / "finsight_agent"

_GDELT_PATTERN = re.compile(r"gdelt|Gdelt|GDELT")


class NoGdeltReferencesInProductionTest(unittest.TestCase):
    """方案 A 长期护栏：保证 backend/src/finsight_agent/ 不再出现 GDELT 字面量。"""

    def test_no_gdelt_references_in_backend_src(self):
        offenders: list[str] = []
        for py_file in PRODUCTION_ROOT.rglob("*.py"):
            # 排除 __pycache__ 与自身
            if "__pycache__" in py_file.parts:
                continue
            if py_file.name == "test_no_gdelt_references_in_production.py":
                continue
            text = py_file.read_text(encoding="utf-8")
            for line_no, line in enumerate(text.splitlines(), start=1):
                if _GDELT_PATTERN.search(line):
                    offenders.append(
                        f"{py_file.relative_to(REPO_ROOT)}:{line_no}: {line.strip()}"
                    )
        self.assertEqual(
            offenders,
            [],
            "GDELT references found in production code:\n" + "\n".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()