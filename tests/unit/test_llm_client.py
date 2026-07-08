from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.infra.llm.client import LlmClient


class LlmClientTest(unittest.TestCase):
    def test_complete_json_returns_legacy_env_override_when_present(self) -> None:
        client = LlmClient()

        with patch.dict(
            "os.environ",
            {
                "FINSIGHT_ROUTER_JSON": json.dumps(
                    {"intent": "metric_lookup", "entities": {}}
                )
            },
            clear=False,
        ):
            payload = client.complete_json(
                prompt_name="router",
                variables={"query": "宁德时代净利润"},
            )

        self.assertEqual(payload["intent"], "metric_lookup")
        self.assertEqual(payload["entities"], {})

    def test_complete_json_raises_when_api_key_missing_and_no_legacy_override(self) -> None:
        client = LlmClient()

        with patch.dict(
            "os.environ",
            {
                "FINSIGHT_ROUTER_JSON": "",
                "DEVAGI_API_KEY": "",
                "FINSIGHT_LLM_API_KEY": "",
            },
            clear=False,
        ):
            with self.assertRaisesRegex(RuntimeError, "api key"):
                client.complete_json(
                    prompt_name="router",
                    variables={
                        "system_prompt": "Only output JSON",
                        "query": "宁德时代净利润",
                    },
                )

    @patch("finsight_agent.infra.llm.client.requests.post")
    def test_complete_json_calls_openai_compatible_endpoint(self, post: Mock) -> None:
        response = Mock()
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "intent": "metric_lookup",
                                "follow_up_type": "none",
                                "confidence": "high",
                                "entities": {
                                    "company": "宁德时代",
                                    "metric": "net_profit",
                                },
                                "needs": ["structured_data_query"],
                                "constraints": {
                                    "preferred_output": "brief_answer"
                                },
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        }
        response.raise_for_status.return_value = None
        post.return_value = response

        with patch.dict(
            "os.environ",
            {
                "DEVAGI_API_KEY": "test-key",
                "FINSIGHT_LLM_BASE_URL": "https://api.fe8.cn/v1",
                "FINSIGHT_LLM_MODEL": "gpt-4o-2024-08-06",
                "FINSIGHT_ROUTER_JSON": "",
            },
            clear=False,
        ):
            client = LlmClient()
            payload = client.complete_json(
                prompt_name="router",
                variables={
                    "system_prompt": "Only output JSON",
                    "query": "宁德时代净利润",
                    "session_context": None,
                },
            )

        self.assertEqual(payload["intent"], "metric_lookup")
        post.assert_called_once()
        _, kwargs = post.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(
            kwargs["json"]["model"],
            "gpt-4o-2024-08-06",
        )
        self.assertEqual(
            kwargs["json"]["response_format"],
            {"type": "json_object"},
        )
        self.assertEqual(
            kwargs["json"]["messages"][0]["content"],
            "Only output JSON",
        )


if __name__ == "__main__":
    unittest.main()
