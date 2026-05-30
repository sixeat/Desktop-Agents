import unittest

from core.pet import PetConfig
from core.pet_companion import PetCompanion, PetResponse
from core.llm_settings import ROUTE_MODE_CLOUD_WHEN_KEY, ROUTE_MODE_LOCAL_ONLY
from core.reply_router import CloudReplyBackend, LocalReplyBackend, ReplyRequest, ReplyRouter, is_deep_topic


class FakeClient:
    def __init__(self):
        self.messages = None
        self.closed = False

    async def chat(self, messages, temperature=0.7):
        self.messages = messages
        return "云端回复"

    async def chat_stream(self, messages, temperature=0.7):
        self.messages = messages
        yield "云"
        yield "端回复"

    async def close(self):
        self.closed = True


class ReplyRouterTest(unittest.IsolatedAsyncioTestCase):
    def make_request(self, memory_context: str = "") -> ReplyRequest:
        companion = PetCompanion(PetConfig("cat", "小猫", "奶糖", (255, 141, 161)))
        return ReplyRequest(
            text="你好",
            channel="direct",
            event_type="chat",
            companion=companion,
            memory_context=memory_context,
        )

    def test_routes_local_without_api_key(self):
        router = ReplyRouter(api_key_available=lambda: False)

        decision = router.decide(self.make_request())

        self.assertEqual(decision.route, "local")
        self.assertEqual(decision.reason, "missing_api_key")
        self.assertFalse(decision.has_api_key)

    def test_routes_cloud_with_api_key_in_compat_mode(self):
        router = ReplyRouter(api_key_available=lambda: True, route_mode_provider=lambda: ROUTE_MODE_CLOUD_WHEN_KEY)

        decision = router.decide(self.make_request())

        self.assertEqual(decision.route, "cloud")
        self.assertEqual(decision.reason, "api_key_available_current_compat")
        self.assertTrue(decision.has_api_key)

    def test_force_route_overrides_default_decision(self):
        router = ReplyRouter(api_key_available=lambda: True, route_mode_provider=lambda: ROUTE_MODE_LOCAL_ONLY)
        request = ReplyRequest(
            text="你好",
            channel="direct",
            event_type="chat",
            companion=PetCompanion(PetConfig("cat", "小猫", "奶糖", (255, 141, 161))),
            force_route="cloud",
        )

        decision = router.decide(request)

        self.assertEqual(decision.route, "cloud")
        self.assertEqual(decision.reason, "forced_cloud")

    def test_local_only_mode_routes_local_even_with_api_key(self):
        router = ReplyRouter(api_key_available=lambda: True, route_mode_provider=lambda: ROUTE_MODE_LOCAL_ONLY)

        decision = router.decide(self.make_request())

        self.assertEqual(decision.route, "local")
        self.assertEqual(decision.reason, "mode_local_only")
        self.assertTrue(decision.has_api_key)

    def test_deep_topic_helper_classifies_obvious_deep_prompt(self):
        self.assertTrue(is_deep_topic("请分析一下这个方案为什么会失败，并给出解决计划"))
        self.assertFalse(is_deep_topic("摸摸头"))

    async def test_local_backend_delegates_to_existing_companion(self):
        request = self.make_request()

        response = await LocalReplyBackend().reply(request)

        self.assertIsInstance(response, PetResponse)
        self.assertEqual(response.source, "local")
        self.assertTrue(response.text)
        self.assertTrue(request.companion.history)

    async def test_cloud_backend_uses_existing_client_contract_and_memory_context(self):
        client = FakeClient()
        request = self.make_request(memory_context="用户喜欢猫")

        response = await CloudReplyBackend(client_factory=lambda: client).reply(request)

        self.assertEqual(response.text, "云端回复")
        self.assertEqual(response.source, "llm")
        self.assertTrue(client.closed)
        self.assertIn("用户喜欢猫", client.messages[0]["content"])

    async def test_cloud_backend_streams_partials_and_remembers_final_only(self):
        client = FakeClient()
        request = self.make_request(memory_context="用户喜欢猫")
        events = []

        async for event in CloudReplyBackend(client_factory=lambda: client).reply_stream(request):
            events.append(event)

        self.assertEqual(events[0], ("partial", "云"))
        self.assertEqual(events[1], ("partial", "云端回复"))
        self.assertEqual(events[2][0], "final")
        self.assertEqual(events[2][1].text, "云端回复")
        self.assertTrue(client.closed)
        self.assertEqual(request.companion.history[-2:], [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "云端回复"},
        ])


if __name__ == "__main__":
    unittest.main()
