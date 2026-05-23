from typing import Any

from core.llm_client import OpenAICompatibleClient
from core.personality import Personality, load_personality


class Agent:
    def __init__(self, persona_name: str = "default", client: OpenAICompatibleClient | None = None):
        self.client = client or OpenAICompatibleClient()
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
    ) -> str:
        active_history = self.history if history is None else history
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            *active_history,
            {"role": "user", "content": user_input},
        ]
        reply = await self.client.chat(messages)
        if history is None:
            self.history.append({"role": "user", "content": user_input})
            self.history.append({"role": "assistant", "content": reply})
        return reply

    async def close(self):
        await self.client.close()
