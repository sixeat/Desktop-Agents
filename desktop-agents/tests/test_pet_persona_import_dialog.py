import os
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from core.personality_trainer import PersonalityProfile
from ui.pet_persona_import_dialog import PetPersonaImportDialog

_app = QApplication.instance() or QApplication([])


class FakeResult:
    def __init__(self, profile):
        self.profile = profile
        self.message_count = 2
        self.target_message_count = 2
        self.used_fallback_messages = False


class PetPersonaImportDialogTest(unittest.TestCase):
    def test_custom_agent_name_is_separate_from_target_name(self):
        captured = {}

        def fake_load(path, target_name, pet_name, pet_type):
            captured.update(path=path, target_name=target_name, pet_name=pet_name, pet_type=pet_type)
            return FakeResult(PersonalityProfile(
                name=pet_name,
                pet_type=pet_type,
                personality_tag="活泼",
                catchphrases=["哈哈"],
                sentence_patterns=[],
                emoji_habits=["[旺柴]"],
                topics=["日常"],
                avg_sentence_length=5.0,
                greeting_style="直接开聊",
                system_prompt="你是自定义名。",
            ))

        dialog = PetPersonaImportDialog("奶糖", "cat")
        dialog.selected_path = Path("chat.txt")
        dialog.target_input.setText("张斌")
        dialog.name_input.setText("篮球搭子")

        with patch("ui.pet_persona_import_dialog.load_profile_from_export", side_effect=fake_load):
            dialog.analyze_file()

        self.assertEqual(captured["target_name"], "张斌")
        self.assertEqual(captured["pet_name"], "篮球搭子")
        self.assertEqual(dialog.profile.name, "篮球搭子")
        self.assertIn("人格名称：篮球搭子", dialog.preview.toPlainText())
        dialog.close()


if __name__ == "__main__":
    unittest.main()
