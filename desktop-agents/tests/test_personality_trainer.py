import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.personality import Personality
from core.personality_trainer import PersonalityTrainer


class PersonalityTrainerTest(unittest.TestCase):
    def test_empty_messages_returns_default_profile(self):
        profile = PersonalityTrainer().analyze([], pet_name="奶糖", pet_type="cat")

        self.assertEqual(profile.name, "奶糖")
        self.assertEqual(profile.pet_type, "cat")
        self.assertEqual(profile.personality_tag, "活泼")
        self.assertIn("奶糖", profile.system_prompt)

    def test_default_profile_uses_builtin_template(self):
        profile = PersonalityTrainer().analyze([], pet_name="布丁", pet_type="dog")

        self.assertEqual(profile.personality_tag, "温柔")
        self.assertEqual(profile.catchphrases, ["汪汪", "慢慢来"])
        self.assertEqual(profile.topics, ["鼓励", "休息", "散步"])

    def test_analyze_extracts_style_features(self):
        messages = ["早呀哈哈，好耶！", "今天真的开心😊", "谢谢你抱抱", "晚安啦"]
        profile = PersonalityTrainer().analyze(messages, pet_name="布丁", pet_type="dog")

        self.assertEqual(profile.personality_tag, "活泼")
        self.assertTrue(profile.catchphrases)
        self.assertIn("感叹句", profile.sentence_patterns)
        self.assertIn("😊", profile.emoji_habits)
        self.assertEqual(profile.greeting_style, "早安问候")
        self.assertGreater(profile.avg_sentence_length, 0)
        self.assertIn("参考授权聊天风格生成", profile.system_prompt)
        self.assertIn("不是聊天记录中的真人", profile.system_prompt)

    def test_analyze_keeps_wechat_text_emoji_habits(self):
        messages = ["哈哈哈你是真的离谱[旺柴]", "我服了[偷笑]", "可以啊😂", "我发了[位置]和[链接]"]

        profile = PersonalityTrainer().analyze(messages, pet_name="张斌", pet_type="cat")

        self.assertIn("[旺柴]", profile.emoji_habits)
        self.assertIn("[偷笑]", profile.emoji_habits)
        self.assertIn("😂", profile.emoji_habits)
        self.assertNotIn("[位置]", profile.emoji_habits)
        self.assertNotIn("[链接]", profile.emoji_habits)
        self.assertIn("常用表情/表情词", profile.system_prompt)
        self.assertIn("[旺柴]", profile.system_prompt)

    def test_save_load_and_personality_dict(self):
        trainer = PersonalityTrainer()
        profile = trainer.analyze(["好的，收到，我认为按计划来。"], pet_name="可可", pet_type="bear")

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.json"
            trainer.save(profile, path)
            loaded = PersonalityTrainer.load(path)
            persona_path = Path(tmp) / "pet.json"
            persona_path.write_text(json.dumps(loaded.to_personality_dict(), ensure_ascii=False), encoding="utf-8")
            personality = Personality.from_json(persona_path)

        self.assertEqual(loaded.name, "可可")
        self.assertEqual(personality.name, "可可")
        self.assertTrue(personality.system_prompt)


if __name__ == "__main__":
    unittest.main()
