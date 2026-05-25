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
    trust_env_values = []

    def __init__(self, *args, **kwargs):
        self.trust_env_values.append(kwargs.get("trust_env"))

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    def post(self, *args, **kwargs):
        return FakeResponse()


class LLMClientTest(unittest.IsolatedAsyncioTestCase):
    async def test_complete_uses_system_proxy_environment(self):
        FakeSession.trust_env_values = []
        client = OpenAICompatibleClient(
            api_key="key",
            base_url="https://api.example/v1",
            model="model",
            provider="provider",
        )

        with patch("core.llm_client.aiohttp.ClientSession", FakeSession):
            message = await client.complete([{"role": "user", "content": "hi"}])

        self.assertEqual(message["content"], "ok")
        self.assertEqual(FakeSession.trust_env_values, [True])


if __name__ == "__main__":
    unittest.main()
