import unittest

from config import PET_CHAT_HISTORY_LIMIT
from core.pet import PetConfig, PetMood
from core.pet_companion import PetCompanion
from core.personality_trainer import PersonalityProfile


class FakeClient:
    def __init__(self, reply="我听见啦！"):
        self.reply = reply
        self.messages = None

    async def chat(self, messages, temperature=0.7):
        self.messages = messages
        return self.reply


class FailingClient:
    async def chat(self, messages, temperature=0.7):
        raise RuntimeError("boom")


class PetCompanionTest(unittest.IsolatedAsyncioTestCase):
    def make_companion(self, personality_tag="活泼"):
        return PetCompanion(PetConfig("cat", "小猫", "奶糖", (255, 141, 161), personality_tag))

    def test_default_profile_uses_pet_config(self):
        companion = self.make_companion("温柔")

        self.assertEqual(companion.profile.name, "奶糖")
        self.assertEqual(companion.profile.pet_type, "cat")
        self.assertEqual(companion.profile.personality_tag, "温柔")

    def test_explicit_profile_preserves_system_prompt(self):
        profile = PersonalityProfile(
            name="朋友",
            pet_type="cat",
            personality_tag="沉稳",
            catchphrases=["收到"],
            sentence_patterns=[],
            emoji_habits=[],
            topics=["工作"],
            avg_sentence_length=5.0,
            greeting_style="直接问候",
            system_prompt="只保留导入人格提示。",
        )
        companion = PetCompanion(PetConfig("cat", "小猫", "奶糖", (255, 141, 161), "活泼"), profile=profile)

        self.assertIs(companion.profile, profile)
        self.assertEqual(companion.profile.personality_tag, "沉稳")
        self.assertEqual(companion.profile.system_prompt, "只保留导入人格提示。")

    def test_click_returns_happy_local_reply(self):
        response = self.make_companion().handle_interaction("click")

        self.assertEqual(response.mood, PetMood.HAPPY)
        self.assertEqual(response.source, "local")
        self.assertTrue(response.text)

    async def test_chat_without_client_uses_local_reply(self):
        response = await self.make_companion().chat("谢谢你，真可爱")

        self.assertEqual(response.source, "local")
        self.assertEqual(response.mood, PetMood.HAPPY)

    async def test_chat_with_fake_client_builds_messages(self):
        companion = self.make_companion()
        client = FakeClient("喵，我在呢！")

        response = await companion.chat("你好呀", client=client)

        self.assertEqual(response.source, "llm")
        self.assertEqual(response.text, "喵，我在呢！")
        self.assertIsNotNone(client.messages)
        joined = "\n".join(message["content"] for message in client.messages)
        self.assertIn("当前情绪", joined)
        self.assertIn("你好呀", joined)

    async def test_failing_client_falls_back_to_local(self):
        response = await self.make_companion().chat("哇？！", client=FailingClient())

        self.assertEqual(response.source, "local")
        self.assertEqual(response.mood, PetMood.SURPRISED)

    async def test_chat_with_memory_context_builds_messages(self):
        companion = self.make_companion()
        client = FakeClient("记得啦")

        await companion.chat("我喜欢什么", client=client, memory_context="- 偏好：喜欢猫")

        joined = "\n".join(message["content"] for message in client.messages)
        self.assertIn("已知用户记忆", joined)
        self.assertIn("喜欢猫", joined)

    def test_build_messages_omits_empty_memory_context(self):
        messages = self.make_companion().build_messages("你好", PetMood.NORMAL, "")

        self.assertNotIn("已知用户记忆", messages[0]["content"])

    def test_group_reply_uses_recent_context(self):
        companion = self.make_companion("沉稳")
        reply = companion.group_reply("你现在是 奶糖，正在和桌面小组里的其他 Agent 聊天。\n当前要接话的人是 张斌。\n最近的群聊记录：\n张斌: 今天的晚饭还没定\n奶糖: 我觉得可以先点外卖\n要求：\n- 优先自然接上上一句，但如果不合适，也可以轻轻换一个相关话题\n- 可以承接最近的话题，或者顺着气氛补一句\n- 只输出你的发言内容，不要加姓名前缀\n- 1到2句话，中文")

        self.assertTrue(reply)
        self.assertIn("奶糖", companion.profile.name)

    async def test_history_is_limited(self):
        companion = self.make_companion()
        for index in range(10):
            await companion.chat(f"消息{index}")

        self.assertLessEqual(len(companion.history), PET_CHAT_HISTORY_LIMIT)

    def test_remember_exchange_records_complete_turn(self):
        companion = self.make_companion()

        companion.remember_exchange("你好", "我在")

        self.assertEqual(companion.history, [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "我在"},
        ])

    def test_same_text_has_different_replies_by_mood(self):
        companion = self.make_companion("活泼")

        happy_reply = companion.local_reply("嗯", PetMood.HAPPY)
        sad_reply = companion.local_reply("嗯", PetMood.SAD)

        self.assertNotEqual(happy_reply, sad_reply)
        self.assertIn("开心", happy_reply)
        self.assertIn("难过", sad_reply)

    def test_apply_profile_replaces_profile_and_clears_history(self):
        companion = self.make_companion()
        companion.history.append({"role": "user", "content": "旧消息"})
        profile = PersonalityProfile(
            name="朋友",
            pet_type="cat",
            personality_tag="沉稳",
            catchphrases=["收到"],
            sentence_patterns=["短句"],
            emoji_habits=[],
            topics=["项目"],
            avg_sentence_length=6.0,
            greeting_style="直接问候",
            system_prompt="你是沉稳的朋友。",
        )

        companion.apply_profile(profile)

        self.assertIs(companion.profile, profile)
        self.assertEqual(companion.history, [])
        self.assertEqual(companion.emotion_state.mood, PetMood.NORMAL)

    def test_local_reply_uses_profile_emoji_habit(self):
        companion = self.make_companion()
        profile = PersonalityProfile(
            name="朋友",
            pet_type="cat",
            personality_tag="活泼",
            catchphrases=["哈哈哈"],
            sentence_patterns=[],
            emoji_habits=["[旺柴]"],
            topics=[],
            avg_sentence_length=5.0,
            greeting_style="直接开聊",
            system_prompt="你是朋友。",
        )

        companion.apply_profile(profile)
        reply = companion.local_reply("你好", PetMood.NORMAL)

        self.assertIn("[旺柴]", reply)

    def test_build_messages_includes_personality_reply_length_limit(self):
        messages = self.make_companion("毒舌").build_messages("你好", PetMood.NORMAL)

        self.assertIn("不超过 25 个中文字符", messages[0]["content"])

    def test_build_messages_uses_applied_profile_prompt(self):
        companion = self.make_companion()
        profile = PersonalityProfile(
            name="朋友",
            pet_type="dog",
            personality_tag="温柔",
            catchphrases=["好呀"],
            sentence_patterns=[],
            emoji_habits=[],
            topics=[],
            avg_sentence_length=5.0,
            greeting_style="温柔问候",
            system_prompt="只使用新人格系统提示。",
        )

        companion.apply_profile(profile, clear_history=False)
        messages = companion.build_messages("你好", PetMood.HAPPY)

        self.assertIn("只使用新人格系统提示", messages[0]["content"])
        self.assertIn("当前情绪", messages[0]["content"])


if __name__ == "__main__":
    unittest.main()
