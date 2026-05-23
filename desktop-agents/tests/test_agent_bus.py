import random
import unittest

from core.agent import Agent
from core.agent_bus import AgentBus, BusMessage


class FakeClient:
    def __init__(self, reply):
        self.reply = reply
        self.messages = []

    async def chat(self, messages, temperature=0.7):
        self.messages.append(messages)
        return self.reply

    async def close(self):
        return None


class AgentBusTest(unittest.IsolatedAsyncioTestCase):
    def make_agent(self, persona_name, reply):
        return Agent(persona_name=persona_name, client=FakeClient(reply))

    def test_broadcast_notifies_subscribers_and_caps_history(self):
        bus = AgentBus(max_history=20)
        received = []
        bus.subscribe(received.append)

        for index in range(25):
            bus.broadcast(BusMessage(sender="tester", content=f"msg-{index}"))

        self.assertEqual(len(received), 25)
        self.assertEqual(len(bus.recent_history), 20)
        self.assertEqual(bus.recent_history[0].content, "msg-5")
        self.assertEqual(bus.recent_history[-1].content, "msg-24")

    async def test_speak_once_uses_shared_transcript_and_broadcasts_agent_message(self):
        agent = self.make_agent("xiaoming", "我来接一句。")
        bus = AgentBus()
        bus.register("xiaoming", agent)
        received = []
        bus.subscribe(received.append)
        bus.broadcast(BusMessage(sender="小红", content="我们先明确目标。", kind="agent", agent_id="xiaohong"))

        message = await bus.speak_once("xiaoming")

        self.assertIsNotNone(message)
        self.assertEqual(message.sender, "小明")
        self.assertEqual(message.agent_id, "xiaoming")
        self.assertEqual(received[-1].content, "我来接一句。")
        sent_messages = agent.client.messages[-1]
        self.assertEqual(sent_messages[0]["role"], "system")
        self.assertIn("小红: 我们先明确目标。", sent_messages[1]["content"])
        self.assertIn("请作为 小明", sent_messages[-1]["content"])

    async def test_user_interjection_broadcasts_user_and_agent_responses(self):
        bus = AgentBus(rng=random.Random(3))
        bus.register("xiaoming", self.make_agent("xiaoming", "我觉得可以先写个 demo。"))
        bus.register("xiaohong", self.make_agent("xiaohong", "我来整理一下需求。"))
        bus.register("dage", self.make_agent("dage", "先控风险。"))
        received = []
        bus.subscribe(received.append)

        await bus.handle_user_interjection("大家怎么看？", anchor_agent_id="xiaohong")

        self.assertEqual(received[0].kind, "user")
        self.assertEqual(received[0].sender, "你")
        self.assertEqual(received[0].anchor_agent_id, "xiaohong")
        self.assertGreaterEqual(len(received), 2)
        self.assertLessEqual(len(received), 3)
        self.assertTrue(any(msg.agent_id == "xiaohong" for msg in received[1:]))

    async def test_auto_turn_can_trigger_followups(self):
        bus = AgentBus(rng=random.Random(1), followup_probability=1.0)
        bus.register("xiaoming", self.make_agent("xiaoming", "我先开个话题。"))
        bus.register("xiaohong", self.make_agent("xiaohong", "我补充一下。"))
        bus.register("dage", self.make_agent("dage", "方向没问题。"))
        received = []
        bus.subscribe(received.append)

        await bus.run_auto_turn_once()

        self.assertGreaterEqual(len(received), 2)
        self.assertLessEqual(len(received), 3)
        self.assertTrue(all(msg.kind == "agent" for msg in received))
        self.assertEqual(len({msg.agent_id for msg in received}), len(received))

    async def test_speak_once_uses_switched_persona_name(self):
        agent = self.make_agent("xiaoming", "我换好啦。")
        bus = AgentBus()
        bus.register("slot-1", agent)
        agent.switch_persona("xiaolan")

        message = await bus.speak_once("slot-1")

        self.assertEqual(message.sender, "小蓝")
        self.assertIn("小蓝", agent.client.messages[-1][0]["content"])


if __name__ == "__main__":
    unittest.main()
