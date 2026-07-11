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
    def test_init_ignores_devagi_key_as_fallback_source(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "AGICTO_API_KEY": "",
                "FINSIGHT_LLM_API_KEY": "",
                "DEVAGI_API_KEY": "legacy-devagi-key",
            },
            clear=False,
        ):
            client = LlmClient()

        self.assertIsNone(client._api_key)

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
        with patch.dict(
            "os.environ",
            {
                "FINSIGHT_ROUTER_JSON": "",
                "AGICTO_API_KEY": "",
                "FINSIGHT_LLM_API_KEY": "",
                "DEVAGI_API_KEY": "",
            },
            clear=False,
        ):
            client = LlmClient()
            with self.assertRaisesRegex(RuntimeError, "api key"):
                client.complete_json(
                    prompt_name="router",
                    variables={
                        "system_prompt": "Only output JSON",
                        "query": "宁德时代净利润",
                    },
                )

    @patch("finsight_agent.infra.llm.client.requests.post")
    def test_complete_json_calls_agicto_openai_compatible_api(self, post: Mock) -> None:
        response = Mock()
        response.status_code = 200
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
                "AGICTO_API_KEY": "test-key",
                "FINSIGHT_LLM_MODEL": "deepseek-v4-flash",
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
        args, kwargs = post.call_args
        # 验证 URL 指向 AGICTO OpenAI 兼容端点
        self.assertIn("api.agicto.cn", args[0])
        self.assertIn("/chat/completions", args[0])
        # 验证 API key 在 Authorization header 中
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-key")
        # 验证请求体格式
        body = kwargs["json"]
        self.assertEqual(body["model"], "deepseek-v4-flash")
        self.assertEqual(body["temperature"], 0)
        self.assertEqual(body["response_format"], {"type": "json_object"})
        # 验证 messages 结构
        self.assertEqual(body["messages"][0]["role"], "system")
        self.assertEqual(body["messages"][0]["content"], "Only output JSON")
        self.assertEqual(body["messages"][1]["role"], "user")


if __name__ == "__main__":
    unittest.main()
