from dataclasses import dataclass

from config import PET_CHAT_HISTORY_LIMIT
from core.emotion import EmotionEngine, EmotionSignal, EmotionState
from core.pet import PetConfig, PetMood
from core.personality_rhythm import get_rhythm
from core.personality_trainer import PersonalityProfile, PersonalityTrainer


@dataclass(frozen=True)
class PetResponse:
    text: str
    mood: PetMood
    source: str
    reason: str


class PetCompanion:
    def __init__(
        self,
        pet_config: PetConfig,
        profile: PersonalityProfile | None = None,
        emotion_engine: EmotionEngine | None = None,
    ):
        self.pet_config = pet_config
        self.profile = profile or PersonalityTrainer()._default_profile(pet_config.name, pet_config.type_id)
        if profile is None and self.profile.personality_tag != pet_config.personality_tag:
            self.profile.personality_tag = pet_config.personality_tag
            self.profile.system_prompt = PersonalityTrainer()._build_system_prompt(
                pet_config.name,
                pet_config.type_id,
                pet_config.personality_tag,
                self.profile.catchphrases,
                self.profile.emoji_habits,
                self.profile.topics,
                self.profile.greeting_style,
                self.profile.avg_sentence_length,
            )
        self.emotion_engine = emotion_engine or EmotionEngine()
        self.emotion_state = EmotionState(PetMood.NORMAL, "初始状态", {PetMood.NORMAL.value: 1.0})
        self.history: list[dict[str, str]] = []

    def apply_profile(self, profile: PersonalityProfile, clear_history: bool = True) -> None:
        self.profile = profile
        if clear_history:
            self.history.clear()
        self.emotion_state = EmotionState(PetMood.NORMAL, "人格已更新", {PetMood.NORMAL.value: 1.0})

    def handle_interaction(self, event_type: str, text: str = "") -> PetResponse:
        self.emotion_state = self.emotion_engine.analyze(
            EmotionSignal(event_type, text),
            self.emotion_state,
            self.profile.personality_tag,
        )
        reply = self.group_reply(text) if event_type == "group_chat" else self.local_reply(text, self.emotion_state.mood)
        self._remember(text or event_type, reply)
        return PetResponse(reply, self.emotion_state.mood, "local", self.emotion_state.reason)

    async def chat(self, user_input: str, client=None, memory_context: str | None = None) -> PetResponse:
        self.emotion_state = self.emotion_engine.analyze(
            EmotionSignal("chat", user_input),
            self.emotion_state,
            self.profile.personality_tag,
        )
        if client is None:
            reply = self.local_reply(user_input, self.emotion_state.mood)
            self._remember(user_input, reply)
            return PetResponse(reply, self.emotion_state.mood, "local", self.emotion_state.reason)

        try:
            reply = await client.chat(self.build_messages(user_input, self.emotion_state.mood, memory_context))
        except Exception:
            reply = self.local_reply(user_input, self.emotion_state.mood)
            self._remember(user_input, reply)
            return PetResponse(reply, self.emotion_state.mood, "local", "LLM失败，使用本地回复")

        clean_reply = str(reply).strip() or self.local_reply(user_input, self.emotion_state.mood)
        self._remember(user_input, clean_reply)
        return PetResponse(clean_reply, self.emotion_state.mood, "llm", self.emotion_state.reason)

    def build_messages(self, user_input: str, mood: PetMood, memory_context: str | None = None) -> list[dict[str, str]]:
        mood_prompt = self.emotion_engine.mood_prompt(mood, self.profile.personality_tag)
        rhythm = get_rhythm(self.profile.personality_tag)
        memory_section = ""
        if memory_context:
            memory_section = f"""

【已知用户记忆】
{memory_context}
使用规则：只在自然相关时使用这些记忆；不要机械复述；不要提数据库、记忆表或系统实现。"""
        system_prompt = f"""{self.profile.system_prompt}{memory_section}

【当前状态】
- 当前情绪：{mood.value}
- 情绪表达：{mood_prompt}
- 回复必须适合桌面气泡，1-2句话，不要输出名字前缀。
- 回复长度尽量不超过 {rhythm.max_reply_length} 个中文字符。""".strip()
        return [
            {"role": "system", "content": system_prompt},
            *self.history[-PET_CHAT_HISTORY_LIMIT:],
            {"role": "user", "content": user_input},
        ]

    def group_reply(self, text: str) -> str:
        phrase = self.profile.catchphrases[0] if self.profile.catchphrases else "嗯嗯"
        emoji = self._emoji_suffix()
        tag = self.profile.personality_tag
        recent_topic = self._extract_recent_topic(text)
        if tag == "温柔":
            return f"{phrase}，我也想顺着大家的话题聊一点。{emoji}"
        if tag in {"毒舌", "傲娇"}:
            return f"哼，这个话题我记住了，{phrase}。{emoji}"
        if tag == "沉稳":
            return f"{phrase}，我先顺着气氛补一句。{emoji}"
        return f"{phrase}，我来接一句。{emoji}"

    def local_reply(self, text: str, mood: PetMood) -> str:
        phrase = self.profile.catchphrases[0] if self.profile.catchphrases else "嗯嗯"
        emoji = self._emoji_suffix()
        tag = self.profile.personality_tag
        templates = {
            PetMood.NORMAL: f"{phrase}，我在这儿陪着你。{emoji}",
            PetMood.HAPPY: f"嘿嘿，我超开心！{phrase}{emoji}",
            PetMood.SAD: f"我有点难过，想靠近你一点点。{emoji}",
            PetMood.SLEEPY: f"有点困困的，但我还在听你说。{emoji}",
            PetMood.ANGRY: f"哼，我有一点点不高兴啦。{emoji}",
            PetMood.SURPRISED: f"诶？真的吗，我有点惊讶！{emoji}",
        }
        if tag == "温柔" and mood == PetMood.ANGRY:
            return f"我有点小难过，不过没关系，我还是会听你说。{emoji}"
        if tag in {"毒舌", "傲娇"} and mood == PetMood.HAPPY:
            return f"才、才没有很开心呢……{phrase}{emoji}"
        if tag == "沉稳" and mood == PetMood.SURPRISED:
            return f"这确实有点意外，我先冷静想想。{emoji}"
        return templates.get(mood, templates[PetMood.NORMAL])

    def _emoji_suffix(self) -> str:
        return self.profile.emoji_habits[0] if self.profile.emoji_habits else ""

    def _extract_recent_topic(self, text: str) -> str:
        if not text.strip():
            return "刚才的话题"
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for line in reversed(lines):
            if ": " in line:
                speaker, content = line.split(": ", 1)
                if speaker in {"你", "系统"}:
                    continue
                if content:
                    return content[:18]
        for line in reversed(lines):
            if line.startswith("要求") or line.startswith("-") or line.startswith("你现在是") or line.startswith("当前要接话的人"):
                continue
            return line[:18]
        return "刚才的话题"

    def remember_exchange(self, user_input: str, reply: str) -> None:
        self._remember(user_input, reply)

    def _remember(self, user_input: str, reply: str) -> None:
        if user_input:
            self.history.append({"role": "user", "content": user_input})
        self.history.append({"role": "assistant", "content": reply})
        overflow = len(self.history) - PET_CHAT_HISTORY_LIMIT
        if overflow > 0:
            del self.history[:overflow]
