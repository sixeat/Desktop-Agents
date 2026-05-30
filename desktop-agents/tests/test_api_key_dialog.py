import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLineEdit

from core.llm_client import LLMValidationResult
from core.llm_settings import ROUTE_MODE_LOCAL_ONLY, LLMSettings
from ui.api_key_dialog import ApiKeyDialog

_app = QApplication.instance() or QApplication([])


class ApiKeyDialogTest(unittest.TestCase):
    def finish_validation(self, dialog: ApiKeyDialog, ok: bool, intent: str, settings: LLMSettings | None = None):
        dialog._on_validation_finished(
            LLMValidationResult(ok, "验证成功，API Key 可用。" if ok else "认证失败，请检查 API Key。", 200 if ok else 401),
            intent,
            settings or dialog.current_settings(),
        )

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

    def test_privacy_notice_is_visible(self):
        with patch("ui.api_key_dialog.load_llm_settings", return_value=LLMSettings()):
            dialog = ApiKeyDialog(first_run=False)

        self.assertIn("云端增强会把当前对话", dialog.privacy_notice.text())
        self.assertIn("原始聊天记录不会上传", dialog.privacy_notice.text())

    def test_route_mode_initializes_from_settings(self):
        with patch("ui.api_key_dialog.load_llm_settings", return_value=LLMSettings(reply_route_mode=ROUTE_MODE_LOCAL_ONLY)):
            dialog = ApiKeyDialog(first_run=False)

        self.assertEqual(dialog.route_mode_input.currentData(), ROUTE_MODE_LOCAL_ONLY)
        self.assertEqual(dialog.current_settings().reply_route_mode, ROUTE_MODE_LOCAL_ONLY)

    def test_local_only_mode_can_save_without_api_key_after_first_run(self):
        with patch("ui.api_key_dialog.load_llm_settings", return_value=LLMSettings(reply_route_mode=ROUTE_MODE_LOCAL_ONLY)):
            dialog = ApiKeyDialog(first_run=False)
        dialog.route_mode_input.setCurrentIndex(dialog.route_mode_input.findData(ROUTE_MODE_LOCAL_ONLY))

        with patch("ui.api_key_dialog.save_llm_settings") as save_settings, \
                patch.object(dialog, "_start_validation") as start_validation:
            dialog.save()

        save_settings.assert_called_once()
        start_validation.assert_not_called()
        self.assertTrue(dialog.saved)

    def test_test_key_success_updates_status_without_saving(self):
        with patch("ui.api_key_dialog.load_llm_settings", return_value=LLMSettings(api_key="secret-key")):
            dialog = ApiKeyDialog(first_run=False)

        with patch("ui.api_key_dialog.save_llm_settings") as save_settings:
            self.finish_validation(dialog, True, "test")

        save_settings.assert_not_called()
        self.assertIn("验证成功", dialog.status_label.text())
        self.assertFalse(dialog.saved)

    def test_save_success_after_validation_persists_and_accepts(self):
        settings = LLMSettings(provider="deepseek", api_key="new-key", base_url="https://api.example/v1", model="model")
        with patch("ui.api_key_dialog.load_llm_settings", return_value=LLMSettings()):
            dialog = ApiKeyDialog(first_run=False)
        dialog.key_input.setText("new-key")

        with patch("ui.api_key_dialog.save_llm_settings") as save_settings:
            self.finish_validation(dialog, True, "save", settings)

        save_settings.assert_called_once_with(settings, replace_key=True)
        self.assertTrue(dialog.saved)

    def test_save_failure_after_validation_does_not_persist(self):
        with patch("ui.api_key_dialog.load_llm_settings", return_value=LLMSettings(api_key="secret-key")):
            dialog = ApiKeyDialog(first_run=False)

        with patch("ui.api_key_dialog.save_llm_settings") as save_settings:
            self.finish_validation(dialog, False, "save")

        save_settings.assert_not_called()
        self.assertFalse(dialog.saved)
        self.assertIn("认证失败", dialog.status_label.text())

    def test_first_run_requires_api_key_before_validation(self):
        with patch("ui.api_key_dialog.load_llm_settings", return_value=LLMSettings()):
            dialog = ApiKeyDialog(first_run=True)

        with patch.object(dialog, "_start_validation") as start_validation:
            with patch("ui.api_key_dialog.QMessageBox.warning"):
                dialog.save()

        start_validation.assert_not_called()


if __name__ == "__main__":
    unittest.main()
