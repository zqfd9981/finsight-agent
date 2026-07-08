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

from finsight_agent.capabilities.reporting.final_answer_writer import FinalAnswerWriter


class _RecordingLlmClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def complete_json(self, *, prompt_name: str, variables: dict[str, object]) -> dict[str, object]:
        self.calls.append(
            {
                "prompt_name": prompt_name,
                "variables": variables,
            }
        )
        return {
            "answer_markdown": "这是最终回答。",
            "answer_confidence": "high",
        }


class FinalAnswerWriterTest(unittest.TestCase):
    def test_writer_loads_system_prompt_from_external_file(self) -> None:
        llm_client = _RecordingLlmClient()
        with tempfile.TemporaryDirectory() as temp_dir:
            prompt_path = Path(temp_dir) / "system.txt"
            prompt_path.write_text(
                "你是中文金融分析助手。只输出 JSON。禁止编造输入中不存在的事实。",
                encoding="utf-8",
            )

            writer = FinalAnswerWriter(
                llm_client=llm_client,
                system_prompt_path=prompt_path,
            )

            draft = writer.write_answer(
                final_answer_context={
                    "query": "红海局势最近怎么了？",
                    "strategy": "event_primary",
                }
            )

        self.assertEqual(draft.answer_markdown, "这是最终回答。")
        self.assertEqual(len(llm_client.calls), 1)
        self.assertEqual(
            llm_client.calls[0]["variables"]["system_prompt"],
            "你是中文金融分析助手。只输出 JSON。禁止编造输入中不存在的事实。",
        )


if __name__ == "__main__":
    unittest.main()
