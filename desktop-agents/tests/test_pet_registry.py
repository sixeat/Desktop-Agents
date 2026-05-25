import json
import tempfile
import unittest
from pathlib import Path

from core.pet import PetConfig
from core.pet_registry import load_pet_configs, normalize_pet_config, save_pet_configs


class PetRegistryTest(unittest.TestCase):
    def test_missing_file_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertEqual(load_pet_configs(Path(temp_dir) / "missing.json"), [])

    def test_save_and_load_roundtrip(self):
        config = PetConfig(
            "cat",
            "小猫",
            "奶糖",
            (255, 141, 161),
            agent_id="agent-1",
            avatar_path="normal.png",
            persona_path="persona.json",
            mood_avatar_paths={"happy": "happy.png"},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "agents.json"
            save_pet_configs([config], path)
            loaded = load_pet_configs(path)

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].agent_id, "agent-1")
        self.assertEqual(loaded[0].color, (255, 141, 161))
        self.assertEqual(loaded[0].mood_avatar_paths["happy"], "happy.png")

    def test_load_converts_color_list_and_adds_agent_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "agents.json"
            path.write_text(json.dumps({"agents": [{"type_id": "dog", "type_name": "小狗", "name": "布丁", "color": [1, 2, 3]}]}), encoding="utf-8")
            loaded = load_pet_configs(path)

        self.assertEqual(loaded[0].color, (1, 2, 3))
        self.assertTrue(loaded[0].agent_id)
        self.assertEqual(loaded[0].personality_tag, "活泼")

    def test_normalize_uses_normal_mood_avatar_as_avatar_path(self):
        config = normalize_pet_config(PetConfig("cat", "小猫", "奶糖", (1, 2, 3), mood_avatar_paths={"normal": "n.png"}))

        self.assertEqual(config.avatar_path, "n.png")
        self.assertTrue(config.agent_id)


if __name__ == "__main__":
    unittest.main()
