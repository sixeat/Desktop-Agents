import unittest
from pathlib import Path

from core.agent import Agent
from core.tooling import PermissionLevel, SandboxPolicy, ToolContext, ToolDefinition, ToolRegistry


class FakeToolClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def complete(self, messages, tools=None, tool_choice="auto", temperature=0.7):
        self.calls.append({"messages": messages, "tools": tools, "tool_choice": tool_choice})
        return self.responses.pop(0)

    async def chat(self, messages, temperature=0.7):
        raise AssertionError("tool-enabled agent should use complete")

    async def close(self):
        return None


class AgentToolsTest(unittest.IsolatedAsyncioTestCase):
    async def test_agent_executes_tool_call_and_returns_final_reply(self):
        tool = ToolDefinition(
            name="echo",
            description="echo",
            parameters={"type": "object"},
            permission_level=PermissionLevel.SAFE,
            handler=lambda args, ctx: {"value": args["value"]},
        )
        client = FakeToolClient([
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "echo", "arguments": '{"value": "hi"}'},
                }],
            },
            {"role": "assistant", "content": "工具结果是 hi"},
        ])
        agent = Agent(client=client, tools=ToolRegistry([tool]))
        context = ToolContext("agent", "Agent", SandboxPolicy((Path.cwd(),)))

        reply = await agent.chat("试试工具", history=[], tool_context=context)

        self.assertEqual(reply, "工具结果是 hi")
        self.assertEqual(client.calls[0]["tools"][0]["function"]["name"], "echo")
        sent_messages = client.calls[1]["messages"]
        self.assertEqual(sent_messages[-1]["role"], "tool")
        self.assertEqual(sent_messages[-1]["tool_call_id"], "call-1")
        self.assertIn("hi", sent_messages[-1]["content"])

    async def test_unknown_tool_returns_error_to_model(self):
        client = FakeToolClient([
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "missing", "arguments": "{}"},
                }],
            },
            {"role": "assistant", "content": "我不能使用这个工具。"},
        ])
        agent = Agent(client=client, tools=ToolRegistry([
            ToolDefinition("known", "known", {"type": "object"}, PermissionLevel.SAFE, lambda a, c: {})
        ]))

        reply = await agent.chat("试试", history=[])

        self.assertEqual(reply, "我不能使用这个工具。")
        self.assertIn("未知工具", client.calls[1]["messages"][-1]["content"])

    def test_agents_have_independent_tool_registries(self):
        first = Agent(tools=ToolRegistry())
        second = Agent(tools=ToolRegistry())
        first.tools.register(ToolDefinition("one", "one", {"type": "object"}, PermissionLevel.SAFE, lambda a, c: {}))

        self.assertEqual(len(first.tools), 1)
        self.assertEqual(len(second.tools), 0)


if __name__ == "__main__":
    unittest.main()
