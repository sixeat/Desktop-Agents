import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from ui.pet_selector_dialog import PetSelectorDialog

_app = QApplication.instance() or QApplication([])


class PetSelectorDialogTest(unittest.TestCase):
    def test_default_selection_has_three_pets(self):
        dialog = PetSelectorDialog()
        dialog.accept()

        pets = dialog.selected_pets()

        self.assertEqual(len(pets), 3)
        self.assertEqual([pet.name for pet in pets], ["奶糖", "布丁", "棉花"])
        self.assertTrue(all(pet.personality_tag for pet in pets))

    def test_empty_name_is_rejected(self):
        dialog = PetSelectorDialog()
        dialog.name_inputs[0].setText("  ")

        with patch("ui.pet_selector_dialog.QMessageBox.warning") as warning:
            dialog.accept()

        warning.assert_called_once()
        self.assertEqual(dialog.selected_pets(), [])

    def test_custom_names_are_returned(self):
        dialog = PetSelectorDialog()
        dialog.name_inputs[0].setText("泡芙")
        dialog.name_inputs[1].setText("年糕")
        dialog.name_inputs[2].setText("豆豆")
        dialog.accept()

        self.assertEqual([pet.name for pet in dialog.selected_pets()], ["泡芙", "年糕", "豆豆"])


if __name__ == "__main__":
    unittest.main()
