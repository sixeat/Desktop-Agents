import os
import unittest
from unittest.mock import patch

from core import llm_settings
from core.llm_settings import DEFAULT_BASE_URL, DEFAULT_MODEL, DEFAULT_PROVIDER, LLMSettings


class FakeQSettings:
    store = {}

    def __init__(self, *args):
        pass

    def value(self, key, default=None):
        return self.store.get(key, default)

    def setValue(self, key, value):
        self.store[key] = value

    def sync(self):
        return None


class FakeKeyring:
    password = ""
    fail_set = False

    @classmethod
    def get_password(cls, service, username):
        return cls.password

    @classmethod
    def set_password(cls, service, username, password):
        if cls.fail_set:
            raise RuntimeError("keyring unavailable")
        cls.password = password


class LLMSettingsTest(unittest.TestCase):
    def setUp(self):
        FakeQSettings.store = {}
        FakeKeyring.password = ""
        FakeKeyring.fail_set = False
        self.env_patch = patch.dict(os.environ, {}, clear=True)
        self.env_patch.start()
        self.qsettings_patch = patch("core.llm_settings.QSettings", FakeQSettings)
        self.keyring_patch = patch.object(llm_settings, "keyring", FakeKeyring)
        self.qsettings_patch.start()
        self.keyring_patch.start()

    def tearDown(self):
        self.keyring_patch.stop()
        self.qsettings_patch.stop()
        self.env_patch.stop()

    def test_loads_from_llm_api_key_env(self):
        os.environ["LLM_API_KEY"] = "env-key"
        os.environ["LLM_MODEL"] = "model-x"

        settings = llm_settings.load_llm_settings()

        self.assertEqual(settings.api_key, "env-key")
        self.assertEqual(settings.model, "model-x")
        self.assertEqual(settings.source, "env")

    def test_falls_back_to_deepseek_api_key_env(self):
        os.environ["DEEPSEEK_API_KEY"] = "deepseek-key"

        settings = llm_settings.load_llm_settings()

        self.assertEqual(settings.api_key, "deepseek-key")
        self.assertEqual(settings.provider, DEFAULT_PROVIDER)
        self.assertEqual(settings.base_url, DEFAULT_BASE_URL)
        self.assertEqual(settings.model, DEFAULT_MODEL)

    def test_save_and_reload_uses_qsettings_and_keyring(self):
        llm_settings.save_llm_settings(LLMSettings(
            provider="openai",
            api_key="saved-key",
            base_url="https://api.example/v1",
            model="gpt-test",
        ))

        settings = llm_settings.load_llm_settings()

        self.assertEqual(settings.provider, "openai")
        self.assertEqual(settings.api_key, "saved-key")
        self.assertEqual(settings.base_url, "https://api.example/v1")
        self.assertEqual(settings.model, "gpt-test")
        self.assertTrue(llm_settings.has_api_key())

    def test_falls_back_to_qsettings_when_keyring_unavailable(self):
        FakeKeyring.fail_set = True

        llm_settings.save_llm_settings(LLMSettings(api_key="fallback-key"))
        settings = llm_settings.load_llm_settings()

        self.assertEqual(settings.api_key, "fallback-key")
        self.assertEqual(settings.source, "settings")

    def test_missing_key_reports_false(self):
        self.assertFalse(llm_settings.has_api_key())


if __name__ == "__main__":
    unittest.main()
