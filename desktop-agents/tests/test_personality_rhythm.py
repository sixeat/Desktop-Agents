import unittest
from unittest.mock import patch

from core.personality_rhythm import get_chat_interval, get_rhythm, get_thinking_time, get_typing_delay


class PersonalityRhythmTest(unittest.TestCase):
    def test_rhythm_table_contains_personality_parameters(self):
        active = get_rhythm("活泼")
        gentle = get_rhythm("温柔")
        calm = get_rhythm("沉稳")
        sharp = get_rhythm("毒舌")

        self.assertEqual(active.interval_ms, 35)
        self.assertEqual(active.chars_per_update, 1)
        self.assertEqual(active.max_reply_length, 30)
        self.assertEqual(gentle.interval_ms, 120)
        self.assertEqual(gentle.chars_per_update, 1)
        self.assertEqual(calm.chars_per_update, 1)
        self.assertEqual(calm.max_reply_length, 50)
        self.assertEqual(sharp.chars_per_update, 1)
        self.assertEqual(sharp.max_reply_length, 25)

    def test_unknown_personality_uses_active_defaults(self):
        self.assertEqual(get_rhythm("未知"), get_rhythm("活泼"))

    def test_typing_delay_applies_jitter(self):
        with patch("core.personality_rhythm.random.uniform", return_value=1.0):
            self.assertEqual(get_typing_delay("温柔"), 120)

    def test_chat_interval_uses_personality_range(self):
        with patch("core.personality_rhythm.random.randint", return_value=20000) as randint:
            interval = get_chat_interval("温柔")

        self.assertEqual(interval, 20000)
        randint.assert_called_once_with(20000, 50000)

    def test_thinking_time_uses_personality_range(self):
        with patch("core.personality_rhythm.random.randint", return_value=700) as randint:
            thinking = get_thinking_time("活泼")

        self.assertEqual(thinking, 700)
        randint.assert_called_once_with(250, 700)


if __name__ == "__main__":
    unittest.main()
