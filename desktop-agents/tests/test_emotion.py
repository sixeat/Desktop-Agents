import unittest

from core.emotion import EmotionEngine, EmotionSignal, EmotionState
from core.pet import PetMood


class EmotionEngineTest(unittest.TestCase):
    def setUp(self):
        self.engine = EmotionEngine()

    def test_happy_text(self):
        self.assertEqual(self.engine.mood_for_text("谢谢你，真可爱"), PetMood.HAPPY)

    def test_sleepy_text(self):
        self.assertEqual(self.engine.mood_for_text("晚安，好困"), PetMood.SLEEPY)

    def test_sad_text(self):
        self.assertEqual(self.engine.mood_for_text("我有点难过想哭"), PetMood.SAD)

    def test_angry_text(self):
        self.assertEqual(self.engine.mood_for_text("气死了，讨厌"), PetMood.ANGRY)

    def test_surprised_text(self):
        self.assertEqual(self.engine.mood_for_text("哇？！真的假的？？"), PetMood.SURPRISED)

    def test_plain_text_is_normal_without_current(self):
        state = self.engine.analyze(EmotionSignal("chat", "今天吃饭了"))

        self.assertEqual(state.mood, PetMood.NORMAL)

    def test_warm_personality_softens_angry(self):
        state = self.engine.analyze(EmotionSignal("chat", "讨厌，气死了"), personality_tag="温柔")

        self.assertNotEqual(state.mood, PetMood.ANGRY)

    def test_decay_returns_short_lived_moods_to_normal(self):
        state = self.engine.decay(EmotionState(PetMood.HAPPY, "test", {}))

        self.assertEqual(state.mood, PetMood.NORMAL)

    def test_mood_prompt_contains_personality_modifier(self):
        prompt = self.engine.mood_prompt(PetMood.ANGRY, "毒舌")

        self.assertIn("嘴硬", prompt)


if __name__ == "__main__":
    unittest.main()
