import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from core.pet import PetConfig, default_pet_definition
from ui.agent_edit_dialog import AgentEditDialog

_app = QApplication.instance() or QApplication([])


class AgentEditDialogTest(unittest.TestCase):
    def test_new_agent_returns_config(self):
        dialog = AgentEditDialog()
        dialog.name_input.setText("张斌")
        dialog.mood_inputs[next(iter(dialog.mood_inputs))].setText("normal.png")

        dialog.accept()

        self.assertEqual(dialog.config.name, "张斌")
        self.assertEqual(dialog.config.type_id, default_pet_definition().type_id)
        self.assertTrue(dialog.config.agent_id)
        self.assertEqual(dialog.config.avatar_path, "normal.png")
        dialog.close()

    def test_empty_name_is_rejected(self):
        dialog = AgentEditDialog()
        dialog.name_input.setText("  ")

        with patch("ui.agent_edit_dialog.QMessageBox.warning") as warning:
            dialog.accept()

        warning.assert_called_once()
        self.assertIsNone(dialog.config)
        dialog.close()

    def test_edit_mode_preserves_identity_and_persona(self):
        original = PetConfig("cat", "小猫", "奶糖", (1, 2, 3), agent_id="agent-1", persona_path="persona.json")
        dialog = AgentEditDialog(original)
        dialog.name_input.setText("泡芙")
        dialog.mood_inputs[next(iter(dialog.mood_inputs))].setText("new-normal.png")

        dialog.accept()

        self.assertEqual(dialog.config.agent_id, "agent-1")
        self.assertEqual(dialog.config.persona_path, "persona.json")
        self.assertEqual(dialog.config.name, "泡芙")
        self.assertEqual(dialog.config.type_id, "cat")
        self.assertEqual(dialog.config.avatar_path, "new-normal.png")
        dialog.close()


if __name__ == "__main__":
    unittest.main()
