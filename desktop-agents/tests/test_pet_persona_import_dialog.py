import os
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtTest import QTest
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
        dialog.consent_checkbox.setChecked(True)
        dialog.target_input.setText("张斌")
        dialog.name_input.setText("篮球搭子")

        with patch("ui.pet_persona_import_dialog.load_profile_from_export", side_effect=fake_load):
            dialog.analyze_file()
            QTest.qWait(50)

        self.assertEqual(captured["target_name"], "张斌")
        self.assertEqual(captured["pet_name"], "篮球搭子")
        self.assertEqual(dialog.profile.name, "篮球搭子")
        preview = dialog.preview.toPlainText()
        self.assertIn("分析预览", preview)
        self.assertIn("原始聊天记录不会复制到人格目录", preview)
        self.assertIn("人格名称：篮球搭子", preview)
        self.assertIn("人格包 / 隐私预览", preview)
        self.assertIn("examples.jsonl", preview)
        self.assertIn("导入分析默认仅在本机处理", preview)
        dialog.close()

    def test_analyze_requires_consent(self):
        dialog = PetPersonaImportDialog("奶糖", "cat")
        dialog.selected_path = Path("chat.txt")

        with patch("ui.pet_persona_import_dialog.QMessageBox.warning") as warning, \
                patch("ui.pet_persona_import_dialog.load_profile_from_export") as load_profile:
            dialog.analyze_file()

        warning.assert_called_once()
        load_profile.assert_not_called()
        self.assertFalse(dialog._analyzing)
        dialog.close()

    def test_analyze_runs_in_background_and_disables_inputs(self):
        dialog = PetPersonaImportDialog("奶糖", "cat")
        dialog.selected_path = Path("chat.txt")
        dialog.consent_checkbox.setChecked(True)

        with patch("ui.pet_persona_import_dialog.threading.Thread") as thread_class:
            dialog.analyze_file()

        self.assertTrue(dialog._analyzing)
        self.assertFalse(dialog.analyze_button.isEnabled())
        self.assertFalse(dialog.import_button.isEnabled())
        thread_class.assert_called_once()
        dialog.close()


if __name__ == "__main__":
    unittest.main()
