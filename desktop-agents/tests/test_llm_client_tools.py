import unittest
from unittest.mock import patch

from core.llm_client import OpenAICompatibleClient


class FakeResponse:
    status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def json(self):
        return {"choices": [{"message": {"role": "assistant", "content": "ok"}}]}


class FakeSession:
    last_payload = None
    last_endpoint = None

    def __init__(self, headers=None, timeout=None):
        self.headers = headers
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    def post(self, endpoint, json):
        FakeSession.last_endpoint = endpoint
        FakeSession.last_payload = json
        return FakeResponse()


class LLMClientToolsTest(unittest.IsolatedAsyncioTestCase):
    async def test_complete_sends_tools_and_tool_choice(self):
        client = OpenAICompatibleClient(
            api_key="key",
            base_url="https://example.test/v1",
            model="model-a",
            provider="test-provider",
        )
        tools = [{"type": "function", "function": {"name": "read_file", "parameters": {"type": "object"}}}]

        with patch("aiohttp.ClientSession", FakeSession):
            message = await client.complete([{"role": "user", "content": "hi"}], tools=tools)

        self.assertEqual(message["content"], "ok")
        self.assertEqual(FakeSession.last_endpoint, "https://example.test/v1/chat/completions")
        self.assertEqual(FakeSession.last_payload["model"], "model-a")
        self.assertEqual(FakeSession.last_payload["tools"], tools)
        self.assertEqual(FakeSession.last_payload["tool_choice"], "auto")

    async def test_missing_key_message_mentions_api_key_settings(self):
        client = OpenAICompatibleClient(api_key="", provider="test-provider")

        message = await client.complete([{"role": "user", "content": "hi"}])

        self.assertIn("API Key 设置", message["content"])
        self.assertNotIn("Authorization", message["content"])

    def test_constructor_can_load_runtime_settings(self):
        with patch("core.llm_client.load_llm_settings") as load_settings:
            load_settings.return_value.api_key = "runtime-key"
            load_settings.return_value.base_url = "https://runtime.example/v1"
            load_settings.return_value.model = "runtime-model"
            load_settings.return_value.provider = "runtime-provider"

            client = OpenAICompatibleClient()

        self.assertEqual(client.api_key, "runtime-key")
        self.assertEqual(client.base_url, "https://runtime.example/v1")
        self.assertEqual(client.model, "runtime-model")
        self.assertEqual(client.provider, "runtime-provider")


if __name__ == "__main__":
    unittest.main()
