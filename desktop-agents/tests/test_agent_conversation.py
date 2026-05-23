import unittest

from core.agent import Agent


class FakeClient:
    def __init__(self):
        self.messages = None

    async def chat(self, messages, temperature=0.7):
        self.messages = messages
        return "你好，我是小助手。"

    async def close(self):
        return None


class AgentConversationTest(unittest.IsolatedAsyncioTestCase):
    async def test_agent_builds_messages_and_returns_reply(self):
        client = FakeClient()
        agent = Agent(client=client)

        reply = await agent.chat("你好", history=[{"role": "assistant", "content": "欢迎！"}])

        self.assertEqual(reply, "你好，我是小助手。")
        self.assertEqual(client.messages[0]["role"], "system")
        self.assertIn("小助手", client.messages[0]["content"])
        self.assertEqual(client.messages[1], {"role": "assistant", "content": "欢迎！"})
        self.assertEqual(client.messages[-1], {"role": "user", "content": "你好"})

    async def test_agent_keeps_internal_history_when_history_is_not_provided(self):
        client = FakeClient()
        agent = Agent(client=client)

        await agent.chat("你好")

        self.assertEqual(agent.history[-2], {"role": "user", "content": "你好"})
        self.assertEqual(agent.history[-1], {"role": "assistant", "content": "你好，我是小助手。"})

    async def test_agent_can_switch_persona_and_clear_history(self):
        client = FakeClient()
        agent = Agent("xiaoming", client=client)
        await agent.chat("你好")

        agent.switch_persona("xiaohong")

        self.assertEqual(agent.name, "小红")
        self.assertEqual(agent.persona_name, "xiaohong")
        self.assertEqual(agent.history, [])
        self.assertIn("小红", agent.system_prompt)
        self.assertIn("不要说自己是AI", agent.system_prompt)


if __name__ == "__main__":
    unittest.main()
