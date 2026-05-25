import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from config import CHAT_UI_HISTORY_LIMIT
from core.agent_bus import BusMessage
from core.pet import PetConfig, PetMood
from core.pet_companion import PetResponse
from core.personality_trainer import PersonalityProfile
from ui.pet_manager import PetManager

_app = QApplication.instance() or QApplication([])


class FakePersonaDialog:
    class DialogCode:
        Accepted = 1

    profile = None
    exec_result = 1

    def __init__(self, pet_name: str, pet_type: str):
        self.pet_name = pet_name
        self.pet_type = pet_type

    def exec(self):
        return self.exec_result


class FakeBatchPersonaDialog:
    created_with = None
    exec_called = False

    def __init__(self, output_dir):
        self.output_dir = output_dir
        FakeBatchPersonaDialog.created_with = output_dir

    def exec(self):
        FakeBatchPersonaDialog.exec_called = True
        return 0


class PetManagerTest(unittest.TestCase):
    def make_pets(self) -> list[PetConfig]:
        return [
            PetConfig("cat", "小猫", "奶糖", (255, 141, 161)),
            PetConfig("dog", "小狗", "布丁", (255, 190, 105)),
            PetConfig("rabbit", "兔兔", "棉花", (168, 143, 255)),
        ]

    def test_create_widgets_creates_three_widgets(self):
        manager = PetManager(self.make_pets())

        manager.create_widgets()

        self.assertEqual(len(manager.widgets), 3)
        self.assertEqual(len(manager.companions), 3)
        self.assertTrue(all(widget.pet_config.agent_id for widget in manager.widgets))
        manager.close()

    def test_add_pet_creates_widget_companion_and_history(self):
        manager = PetManager([])
        config = PetConfig("cat", "小猫", "奶糖", (255, 141, 161), agent_id="agent-1")

        with patch("ui.pet_manager.save_pet_configs") as save_configs:
            widget = manager.add_pet(config)

        self.assertIn(widget, manager.widgets)
        self.assertIn(widget, manager.companions)
        self.assertIn(widget, manager.direct_histories)
        save_configs.assert_called_once()
        manager.close()

    def test_remove_pet_cleans_state(self):
        manager = PetManager([PetConfig("cat", "小猫", "奶糖", (255, 141, 161), agent_id="agent-1")])
        manager.create_widgets()
        widget = manager.widgets[0]
        manager.show_pet_chat_window(widget)

        with patch("ui.pet_manager.save_pet_configs"):
            manager.remove_pet("agent-1")

        self.assertEqual(manager.widgets, [])
        self.assertEqual(manager.companions, {})
        self.assertEqual(manager.direct_histories, {})
        self.assertEqual(manager.direct_chat_windows, {})
        manager.close()

    def test_same_type_agents_use_agent_id_in_messages(self):
        manager = PetManager([
            PetConfig("cat", "小猫", "奶糖", (255, 141, 161), agent_id="agent-1"),
            PetConfig("cat", "小猫", "泡芙", (255, 141, 161), agent_id="agent-2"),
        ])
        manager.create_widgets()
        first = manager.widgets[0]

        manager._append_direct_message(first, BusMessage(sender="你", content="hi", kind="user", anchor_agent_id=first.pet_config.identity))
        manager._show_chat_response(first, PetResponse("在", PetMood.HAPPY, "local", "test"), "direct")

        self.assertEqual(manager.direct_histories[first][0].anchor_agent_id, "agent-1")
        self.assertEqual(manager.direct_histories[first][1].agent_id, "agent-1")
        manager.close()

    def test_positions_do_not_all_overlap(self):
        manager = PetManager(self.make_pets())

        manager.create_widgets()
        positions = [widget.pos() for widget in manager.widgets]

        self.assertGreater(len(set((pos.x(), pos.y()) for pos in positions)), 1)
        manager.close()

    def test_show_all_and_close(self):
        manager = PetManager(self.make_pets())
        manager.create_widgets()

        manager.show_all()
        manager.close()

        self.assertEqual(manager.widgets, [])
        self.assertEqual(manager.companions, {})

    def test_click_pet_shows_local_reply(self):
        manager = PetManager(self.make_pets())
        manager.create_widgets()
        widget = manager.widgets[0]

        manager._on_pet_clicked(widget)

        self.assertEqual(len(widget._bubbles), 1)
        self.assertIsNot(manager.companions[widget], manager.companions[manager.widgets[1]])
        manager.close()

    def test_chat_request_updates_emotion_and_bubble(self):
        manager = PetManager(self.make_pets())
        manager.create_widgets()
        widget = manager.widgets[0]

        manager._on_pet_chat_requested(widget, "好开心")

        self.assertEqual(widget.mood, PetMood.HAPPY)
        self.assertEqual(len(widget._bubbles), 1)
        manager._on_pet_chat_requested(widget, "好困")
        self.assertEqual(widget.mood, PetMood.SLEEPY)
        manager.close()

    def test_auto_chat_creates_speech_and_propagates_emotion(self):
        manager = PetManager(self.make_pets())
        manager.create_widgets()
        speaker = manager.widgets[0]
        listener = manager.widgets[1]

        with patch("ui.pet_manager.has_api_key", return_value=False):
            manager.run_auto_chat_once()
        listener_response = manager._propagate_emotion(listener, manager.companions[speaker].handle_interaction("group_chat", "测试"))

        self.assertEqual(len(speaker._bubbles), 1)
        self.assertTrue(listener_response.text)
        self.assertNotEqual(manager.companions[listener].emotion_state.reason, "初始状态")
        manager.close()

    def test_chat_request_uses_llm_when_key_exists(self):
        manager = PetManager(self.make_pets())
        manager.create_widgets()
        widget = manager.widgets[0]
        calls = []

        def fake_chat(current_widget, text, show_thinking=True, channel="direct"):
            calls.append((current_widget, text, show_thinking, channel))
            manager.chat_reply_ready.emit(current_widget, PetResponse("智能回复", PetMood.HAPPY, "llm", "test"), channel)

        with patch("ui.pet_manager.has_api_key", return_value=True):
            with patch.object(manager, "_chat_with_llm", side_effect=fake_chat):
                manager._on_pet_chat_requested(widget, "你好")

        self.assertEqual(calls, [(widget, "你好", True, "direct")])
        self.assertEqual(widget._bubbles[-1].content, "智能回复")
        manager.close()

    def test_auto_chat_uses_llm_when_key_exists(self):
        manager = PetManager(self.make_pets())
        manager.create_widgets()
        calls = []

        def fake_chat(current_widget, text, show_thinking=True, channel="direct"):
            calls.append((current_widget, text, show_thinking, channel))

        with patch("ui.pet_manager.has_api_key", return_value=True):
            with patch.object(manager, "_chat_with_llm", side_effect=fake_chat):
                manager.run_auto_chat_once()

        self.assertEqual(len(calls), 1)
        self.assertFalse(calls[0][2])
        self.assertEqual(calls[0][3], "group")
        self.assertIn("当前要接话的人是", calls[0][1])
        self.assertIn("优先自然接上上一句", calls[0][1])
        manager.close()

    def test_direct_chat_history_is_separate_per_pet(self):
        manager = PetManager(self.make_pets())
        manager.create_widgets()
        first = manager.widgets[0]
        second = manager.widgets[1]

        with patch("ui.pet_manager.has_api_key", return_value=False):
            manager._on_pet_chat_requested(first, "你好")

        self.assertEqual([message.sender for message in manager.direct_histories[first]], ["你", first.pet_config.name])
        self.assertEqual(len(manager.direct_histories[second]), 0)
        self.assertEqual(len(manager.group_history), 0)
        manager.close()

    def test_auto_chat_history_only_goes_to_group(self):
        manager = PetManager(self.make_pets())
        manager.create_widgets()

        with patch("ui.pet_manager.has_api_key", return_value=False):
            manager.run_auto_chat_once()

        self.assertEqual(len(manager.group_history), 1)
        self.assertTrue(all(len(history) == 0 for history in manager.direct_histories.values()))
        manager.close()

    def test_group_prompt_includes_recent_transcript(self):
        manager = PetManager(self.make_pets())
        manager.create_widgets()
        manager.group_history.append(BusMessage(sender="张小斌", content="今天先把饭定了", kind="agent"))
        manager.group_history.append(BusMessage(sender="奶糖", content="我觉得可以点外卖", kind="agent"))
        speaker = manager.widgets[0]
        listener = manager.widgets[1]

        prompt = manager._group_chat_prompt(speaker, listener)

        self.assertIn("张小斌: 今天先把饭定了", prompt)
        self.assertIn("奶糖: 我觉得可以点外卖", prompt)
        self.assertIn("当前要接话的人是", prompt)
        manager.close()

    def test_chat_histories_keep_latest_50_messages(self):
        manager = PetManager(self.make_pets())
        manager.create_widgets()
        widget = manager.widgets[0]

        for index in range(CHAT_UI_HISTORY_LIMIT + 5):
            manager._append_direct_message(widget, BusMessage(sender="你", content=str(index), kind="user"))

        self.assertEqual(len(manager.direct_histories[widget]), CHAT_UI_HISTORY_LIMIT)
        self.assertEqual(manager.direct_histories[widget][0].content, "5")
        manager.close()

    def test_llm_reply_channel_controls_history_target(self):
        manager = PetManager(self.make_pets())
        manager.create_widgets()
        widget = manager.widgets[0]

        manager._show_chat_response(widget, PetResponse("单聊回复", PetMood.HAPPY, "llm", "test"), "direct")
        manager._show_chat_response(widget, PetResponse("群聊回复", PetMood.HAPPY, "llm", "test"), "group")

        self.assertEqual(manager.direct_histories[widget][-1].content, "单聊回复")
        self.assertEqual(manager.group_history[-1].content, "群聊回复")
        manager.close()

    def test_import_personas_from_folder_opens_batch_dialog(self):
        FakeBatchPersonaDialog.created_with = None
        FakeBatchPersonaDialog.exec_called = False
        manager = PetManager(self.make_pets())
        manager.create_widgets()

        with patch("ui.pet_manager.BatchPersonaImportDialog", FakeBatchPersonaDialog):
            with patch("ui.pet_manager.PET_PERSONAS_DIR", Path("personas")):
                manager.import_personas_from_folder()

        self.assertEqual(FakeBatchPersonaDialog.created_with, Path("personas"))
        self.assertTrue(FakeBatchPersonaDialog.exec_called)
        manager.close()

    def test_import_persona_preserves_avatar_and_records_persona_path(self):
        profile = PersonalityProfile(
            name="朋友",
            pet_type="cat",
            personality_tag="沉稳",
            catchphrases=["收到"],
            sentence_patterns=[],
            emoji_habits=[],
            topics=["工作"],
            avg_sentence_length=4.0,
            greeting_style="直接问候",
            system_prompt="你是沉稳的朋友。",
        )
        FakePersonaDialog.profile = profile
        FakePersonaDialog.exec_result = FakePersonaDialog.DialogCode.Accepted
        pets = self.make_pets()
        pets[0] = PetConfig("cat", "小猫", "奶糖", (255, 141, 161), avatar_path="normal.png", mood_avatar_paths={"normal": "normal.png"})
        manager = PetManager(pets)
        manager.create_widgets()
        first = manager.widgets[0]
        second = manager.widgets[1]

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("ui.pet_manager.PetPersonaImportDialog", FakePersonaDialog):
                with patch("ui.pet_manager.PET_PERSONAS_DIR", Path(temp_dir)):
                    with patch("ui.pet_manager.save_pet_configs"):
                        manager.import_persona_for_pet(first)
                    saved_path = Path(temp_dir) / profile.name / "persona.json"
                    saved_exists = saved_path.exists()

        self.assertEqual(first.pet_config.name, "朋友")
        self.assertEqual(manager.companions[first].pet_config.name, "朋友")
        self.assertEqual(manager.companions[first].profile.personality_tag, "沉稳")
        self.assertNotEqual(manager.companions[second].profile.personality_tag, "沉稳")
        self.assertTrue(saved_exists)
        self.assertEqual(first.pet_config.persona_path, str(saved_path))
        self.assertEqual(first.pet_config.avatar_path, "normal.png")
        self.assertEqual(first.pet_config.mood_avatar_paths["normal"], "normal.png")
        self.assertEqual(first.pet_config.personality_tag, "沉稳")
        self.assertEqual(manager.direct_histories[first][-1].sender, first.pet_config.name)
        self.assertEqual(len(manager.direct_histories[second]), 0)
        self.assertEqual(len(manager.group_history), 0)
        manager.close()

    def test_chat_window_send_uses_direct_chat_history(self):
        manager = PetManager(self.make_pets())
        manager.create_widgets()
        widget = manager.widgets[0]

        with patch("ui.pet_manager.has_api_key", return_value=False):
            manager.show_pet_chat_window(widget)
            window = manager.direct_chat_windows[widget]
            window.message_submitted.emit("你好")

        self.assertEqual([message.sender for message in manager.direct_histories[widget]], ["你", widget.pet_config.name])
        self.assertEqual(len(manager.group_history), 0)
        self.assertEqual(window.message_count(), 2)
        manager.close()


if __name__ == "__main__":
    unittest.main()
