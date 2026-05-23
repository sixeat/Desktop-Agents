import json
from typing import Any

from core.builtin_tools import default_sandbox
from core.llm_client import OpenAICompatibleClient
from core.personality import Personality, load_personality
from core.tooling import ToolContext, ToolExecutor, ToolRegistry


class Agent:
    def __init__(
        self,
        persona_name: str = "default",
        client: OpenAICompatibleClient | None = None,
        tools: ToolRegistry | None = None,
    ):
        self.client = client or OpenAICompatibleClient()
        self.tools = tools or ToolRegistry()
        self.tool_executor = ToolExecutor(self.tools)
        self.max_tool_iterations = 4
        self.history: list[dict[str, str]] = []
        self.load_persona(persona_name)

    def load_persona(self, persona_name: str) -> None:
        self.persona_name = persona_name
        self.personality: Personality = load_personality(persona_name)
        self.name = self.personality.name
        self.description = self.personality.description
        self.style = self.personality.style
        self.topics = self.personality.topics
        self.reply_speed = self.personality.reply_speed
        self.emoji_frequency = self.personality.emoji_frequency
        self.tone = self.personality.tone
        self.avatar = self.personality.avatar
        self.system_prompt = self.personality.build_system_prompt()

    def switch_persona(self, persona_name: str, clear_history: bool = True) -> None:
        self.load_persona(persona_name)
        if clear_history:
            self.history.clear()

    async def chat(
        self,
        user_input: str,
        history: list[dict[str, str]] | None = None,
        tool_context: ToolContext | None = None,
    ) -> str:
        active_history = self.history if history is None else history
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            *active_history,
            {"role": "user", "content": user_input},
        ]
        if not self.tools:
            reply = await self.client.chat(messages)
        else:
            reply = await self._chat_with_tools(messages, tool_context)
        if history is None:
            self.history.append({"role": "user", "content": user_input})
            self.history.append({"role": "assistant", "content": reply})
        return reply

    async def _chat_with_tools(self, messages: list[dict[str, Any]], tool_context: ToolContext | None) -> str:
        if tool_context is None:
            tool_context = ToolContext(
                agent_id=self.persona_name,
                agent_name=self.name,
                sandbox=default_sandbox(),
            )

        for _ in range(self.max_tool_iterations):
            message = await self.client.complete(
                messages,
                tools=self.tools.to_deepseek_tools(),
                tool_choice="auto",
            )
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                return str(message.get("content") or "")

            messages.append(message)
            for tool_call in tool_calls:
                function = tool_call.get("function") or {}
                name = function.get("name") or ""
                arguments = function.get("arguments") or "{}"
                tool_call_id = tool_call.get("id")
                result = await self.tool_executor.execute(name, arguments, tool_context, tool_call_id)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "name": name,
                    "content": result.to_message_content(),
                })

        return json.dumps({"ok": False, "error": "工具调用次数过多，已停止。"}, ensure_ascii=False)

    async def close(self):
        await self.client.close()
