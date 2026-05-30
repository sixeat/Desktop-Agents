import asyncio
import unittest
from unittest.mock import patch

import aiohttp

from core.llm_client import OpenAICompatibleClient


class FakeResponse:
    status = 200

    def __init__(self, status=200, data=None):
        self.status = status
        self.data = data or {"choices": [{"message": {"role": "assistant", "content": "ok"}}]}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def json(self):
        return self.data

    async def text(self):
        return "error"


class FakeSession:
    trust_env_values = []
    response = FakeResponse()
    exception = None

    def __init__(self, *args, **kwargs):
        self.trust_env_values.append(kwargs.get("trust_env"))

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    def post(self, *args, **kwargs):
        if self.exception:
            raise self.exception
        return self.response


class LLMClientTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        FakeSession.trust_env_values = []
        FakeSession.response = FakeResponse()
        FakeSession.exception = None

    def make_client(self):
        return OpenAICompatibleClient(
            api_key="key",
            base_url="https://api.example/v1",
            model="model",
            provider="provider",
        )

    async def test_complete_uses_system_proxy_environment(self):
        client = self.make_client()

        with patch("core.llm_client.aiohttp.ClientSession", FakeSession):
            message = await client.complete([{"role": "user", "content": "hi"}])

        self.assertEqual(message["content"], "ok")
        self.assertEqual(FakeSession.trust_env_values, [True])

    async def test_validate_api_key_success(self):
        client = self.make_client()

        with patch("core.llm_client.aiohttp.ClientSession", FakeSession):
            result = await client.validate_api_key()

        self.assertTrue(result.ok)
        self.assertIn("验证成功", result.message)
        self.assertEqual(FakeSession.trust_env_values, [True])

    async def test_validate_api_key_auth_failure(self):
        FakeSession.response = FakeResponse(status=401)
        client = self.make_client()

        with patch("core.llm_client.aiohttp.ClientSession", FakeSession):
            result = await client.validate_api_key()

        self.assertFalse(result.ok)
        self.assertIn("认证失败", result.message)
        self.assertEqual(result.status, 401)

    async def test_validate_api_key_timeout(self):
        FakeSession.exception = asyncio.TimeoutError()
        client = self.make_client()

        with patch("core.llm_client.aiohttp.ClientSession", FakeSession):
            result = await client.validate_api_key()

        self.assertFalse(result.ok)
        self.assertIn("超时", result.message)

    async def test_validate_api_key_network_error(self):
        FakeSession.exception = aiohttp.ClientError()
        client = self.make_client()

        with patch("core.llm_client.aiohttp.ClientSession", FakeSession):
            result = await client.validate_api_key()

        self.assertFalse(result.ok)
        self.assertIn("网络", result.message)


if __name__ == "__main__":
    unittest.main()
