import json
import tempfile
import unittest
from pathlib import Path

from core.personality import Personality, list_personalities


class PersonalityTest(unittest.TestCase):
    def write_persona(self, payload):
        temp_dir = tempfile.TemporaryDirectory()
        path = Path(temp_dir.name) / "tester.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        self.addCleanup(temp_dir.cleanup)
        return path

    def test_loads_rich_personality_fields(self):
        path = self.write_persona({
            "name": "测试员",
            "description": "一个认真测试的人",
            "style": ["严谨", "先复现"],
            "topics": ["测试", "质量"],
            "reply_speed": "slow",
            "emoji_frequency": "low",
            "tone": "严肃",
            "avatar": "assets/characters/tester.png",
        })

        personality = Personality.from_json(path)

        self.assertEqual(personality.persona_id, "tester")
        self.assertEqual(personality.name, "测试员")
        self.assertEqual(personality.topics, ["测试", "质量"])
        self.assertEqual(personality.avatar, "assets/characters/tester.png")

    def test_build_system_prompt_contains_identity_style_and_safety_rules(self):
        path = self.write_persona({
            "name": "测试员",
            "description": "一个认真测试的人",
            "style": ["严谨"],
            "topics": ["测试"],
            "tone": "严肃",
        })

        prompt = Personality.from_json(path).build_system_prompt()

        self.assertIn("你叫测试员", prompt)
        self.assertIn("严谨", prompt)
        self.assertIn("测试", prompt)
        self.assertIn("不要说自己是AI", prompt)
        self.assertIn("1到2句话", prompt)
        self.assertIn("不要在回复前加自己的名字", prompt)

    def test_old_schema_remains_supported(self):
        path = self.write_persona({
            "name": "旧人格",
            "description": "旧格式",
            "style": ["简短"],
            "system_prompt": "你是{name}，风格是{style}。",
        })

        personality = Personality.from_json(path)
        prompt = personality.build_system_prompt()

        self.assertEqual(personality.name, "旧人格")
        self.assertIn("你是旧人格", prompt)
        self.assertIn("简短", prompt)
        self.assertIn("补充规则", prompt)

    def test_lists_available_personalities(self):
        personalities = list_personalities()

        self.assertGreaterEqual(len(personalities), 5)
        self.assertIn("xiaoming", personalities)
        self.assertIn("xiaolan", personalities)
        self.assertEqual(personalities["xiaoming"].name, "小明")


if __name__ == "__main__":
    unittest.main()
