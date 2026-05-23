import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLineEdit

from core.llm_settings import LLMSettings
from ui.api_key_dialog import ApiKeyDialog

_app = QApplication.instance() or QApplication([])


class ApiKeyDialogTest(unittest.TestCase):
    def test_key_field_uses_password_mode(self):
        with patch("ui.api_key_dialog.load_llm_settings", return_value=LLMSettings()):
            dialog = ApiKeyDialog(first_run=True)

        self.assertEqual(dialog.key_input.echoMode(), QLineEdit.EchoMode.Password)

    def test_existing_key_is_masked_as_placeholder(self):
        with patch("ui.api_key_dialog.load_llm_settings", return_value=LLMSettings(api_key="secret-key")):
            dialog = ApiKeyDialog(first_run=False)

        self.assertNotIn("secret-key", dialog.key_input.placeholderText())
        self.assertTrue(dialog.key_input.placeholderText())

    def test_current_settings_trims_values_and_preserves_existing_key(self):
        existing = LLMSettings(provider="deepseek", api_key="secret-key", base_url="https://old", model="old")
        with patch("ui.api_key_dialog.load_llm_settings", return_value=existing):
            dialog = ApiKeyDialog(first_run=False)
        dialog.provider_input.setText(" openai ")
        dialog.base_url_input.setText(" https://api.example/v1 ")
        dialog.model_input.setText(" gpt-test ")

        settings = dialog.current_settings()

        self.assertEqual(settings.provider, "openai")
        self.assertEqual(settings.api_key, "secret-key")
        self.assertEqual(settings.base_url, "https://api.example/v1")
        self.assertEqual(settings.model, "gpt-test")


if __name__ == "__main__":
    unittest.main()
