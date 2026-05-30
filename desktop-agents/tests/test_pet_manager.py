import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox

from config import CHAT_UI_HISTORY_LIMIT, MAX_DESKTOP_AGENTS
from core.agent_bus import BusMessage
from core.chat_storage import ChatStorage
from core.explicit_memory import ExplicitMemoryStore
from core.pet import PetConfig, PetMood
from core.pet_companion import PetResponse
from core.personality_trainer import PersonalityProfile, PersonalityTrainer
from core.reply_router import LocalReplyBackend, ReplyRouter
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


class RecordingLocalBackend(LocalReplyBackend):
    def __init__(self):
        super().__init__()
        self.requests = []

    async def reply(self, request):
        self.requests.append(request)
        return await super().reply(request)


class FakeStreamingCloudBackend:
    async def reply_stream(self, request):
        yield "partial", "你"
        yield "partial", "你好"
        request.companion.remember_exchange(request.text, "你好")
        yield "final", PetResponse("你好", PetMood.HAPPY, "llm", "stream_complete")


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

    def test_create_widgets_only_shows_deployed_agents(self):
        manager = PetManager([
            PetConfig("cat", "小猫", "奶糖", (255, 141, 161), agent_id="agent-1", deployed=True),
            PetConfig("dog", "小狗", "布丁", (255, 190, 105), agent_id="agent-2", deployed=False),
        ])

        manager.create_widgets()

        self.assertEqual([widget.pet_config.identity for widget in manager.widgets], ["agent-1"])
        self.assertEqual(len(manager.pets), 2)
        manager.close()

    def test_create_widgets_loads_existing_persona_path(self):
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
            system_prompt="只使用保存的人格提示。",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            persona_path = Path(temp_dir) / "persona.json"
            PersonalityTrainer().save(profile, persona_path)
            manager = PetManager([PetConfig("cat", "小猫", "奶糖", (255, 141, 161), personality_tag="活泼", persona_path=str(persona_path))])
            manager.create_widgets()
            companion = manager.companions[manager.widgets[0]]

            self.assertEqual(companion.profile.personality_tag, "沉稳")
            self.assertEqual(companion.profile.system_prompt, "只使用保存的人格提示。")
            manager.close()

    def test_create_widgets_falls_back_when_persona_path_is_invalid(self):
        manager = PetManager([PetConfig("cat", "小猫", "奶糖", (255, 141, 161), personality_tag="温柔", persona_path="missing-persona.json")])

        manager.create_widgets()
        companion = manager.companions[manager.widgets[0]]

        self.assertEqual(companion.profile.name, "奶糖")
        self.assertEqual(companion.profile.personality_tag, "温柔")
        manager.close()

    def test_set_agent_deployed_hides_widget_without_deleting_profile(self):
        manager = PetManager([
            PetConfig("cat", "小猫", "奶糖", (255, 141, 161), agent_id="agent-1"),
            PetConfig("dog", "小狗", "布丁", (255, 190, 105), agent_id="agent-2"),
        ])
        manager.create_widgets()
        hidden_widget = manager.widgets[1]

        with patch("ui.pet_manager.save_pet_configs"):
            manager.set_agent_deployed("agent-2", False)

        self.assertEqual([pet.identity for pet in manager.pets], ["agent-1", "agent-2"])
        self.assertFalse(manager.pets[1].deployed)
        self.assertEqual([widget.pet_config.identity for widget in manager.widgets], ["agent-1"])
        self.assertNotIn(hidden_widget, manager.companions)
        manager.close()

    def test_set_agent_deployed_shows_existing_profile(self):
        manager = PetManager([
            PetConfig("cat", "小猫", "奶糖", (255, 141, 161), agent_id="agent-1", deployed=True),
            PetConfig("dog", "小狗", "布丁", (255, 190, 105), agent_id="agent-2", deployed=False),
        ])
        manager.create_widgets()

        with patch("ui.pet_manager.save_pet_configs"):
            manager.set_agent_deployed("agent-2", True)

        self.assertTrue(manager.pets[1].deployed)
        self.assertEqual([widget.pet_config.identity for widget in manager.widgets], ["agent-1", "agent-2"])
        manager.close()

    def test_set_agent_deployed_refuses_to_hide_last_agent(self):
        manager = PetManager([PetConfig("cat", "小猫", "奶糖", (255, 141, 161), agent_id="agent-1")])
        manager.create_widgets()

        with patch("ui.pet_manager.QMessageBox.information"):
            manager.set_agent_deployed("agent-1", False)

        self.assertTrue(manager.pets[0].deployed)
        self.assertEqual(len(manager.widgets), 1)
        manager.close()

    def test_set_agent_deployed_refuses_more_than_six_visible_agents(self):
        pets = [PetConfig("cat", "小猫", f"Agent{i}", (255, 141, 161), agent_id=f"agent-{i}") for i in range(MAX_DESKTOP_AGENTS)]
        pets.append(PetConfig("dog", "小狗", "候补", (255, 190, 105), agent_id="agent-extra", deployed=False))
        manager = PetManager(pets)
        manager.create_widgets()

        with patch("ui.pet_manager.QMessageBox.information"):
            manager.set_agent_deployed("agent-extra", True)

        self.assertFalse(manager.pets[-1].deployed)
        self.assertEqual(len(manager.widgets), MAX_DESKTOP_AGENTS)
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

    def test_add_pet_keeps_extra_agent_undeployed_when_six_are_deployed(self):
        pets = [PetConfig("cat", "小猫", f"Agent{i}", (255, 141, 161), agent_id=f"agent-{i}") for i in range(MAX_DESKTOP_AGENTS)]
        manager = PetManager(pets)
        manager.create_widgets()

        with patch("ui.pet_manager.QMessageBox.information"):
            widget = manager.add_pet(PetConfig("cat", "小猫", "多余", (255, 141, 161), agent_id="extra"))

        self.assertIsNone(widget)
        self.assertEqual(len(manager.widgets), MAX_DESKTOP_AGENTS)
        self.assertEqual(len(manager.pets), MAX_DESKTOP_AGENTS + 1)
        self.assertFalse(manager.pets[-1].deployed)
        manager.close()

    def test_remove_pet_refuses_to_remove_last_agent(self):
        manager = PetManager([PetConfig("cat", "小猫", "奶糖", (255, 141, 161), agent_id="agent-1")])
        manager.create_widgets()

        with patch("ui.pet_manager.QMessageBox.information"):
            manager.remove_pet("agent-1")

        self.assertEqual(len(manager.widgets), 1)
        manager.close()

    def test_remove_pet_cleans_state(self):
        manager = PetManager([
            PetConfig("cat", "小猫", "奶糖", (255, 141, 161), agent_id="agent-1"),
            PetConfig("dog", "小狗", "布丁", (255, 190, 105), agent_id="agent-2"),
        ])
        manager.create_widgets()
        widget = manager.widgets[0]
        remaining = manager.widgets[1]
        manager.show_pet_chat_window(widget)

        with patch("ui.pet_manager.save_pet_configs"):
            manager.remove_pet("agent-1")

        self.assertEqual(manager.widgets, [remaining])
        self.assertNotIn(widget, manager.companions)
        self.assertNotIn(widget, manager.direct_histories)
        self.assertNotIn(widget, manager.direct_chat_windows)
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

        with patch("ui.pet_manager.has_api_key", return_value=False):
            manager._on_pet_chat_requested(widget, "好开心")

        self.assertEqual(widget.mood, PetMood.HAPPY)
        self.assertEqual(len(widget._bubbles), 1)
        with patch("ui.pet_manager.has_api_key", return_value=False):
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

        def fake_chat(current_widget, text, show_thinking=True, channel="direct", sleepy_at_night=False):
            calls.append((current_widget, text, show_thinking, channel, sleepy_at_night))
            manager.chat_reply_ready.emit(current_widget, PetResponse("智能回复", PetMood.HAPPY, "llm", "test"), channel)

        with patch("ui.pet_manager.has_api_key", return_value=True):
            with patch.object(manager, "_chat_with_llm", side_effect=fake_chat):
                manager._on_pet_chat_requested(widget, "你好")

        self.assertEqual(calls, [(widget, "你好", True, "direct", False)])
        self.assertEqual(widget._bubbles[-1].content, "智能回复")
        manager.close()

    def test_auto_chat_uses_llm_when_key_exists(self):
        manager = PetManager(self.make_pets())
        manager.create_widgets()
        calls = []

        def fake_chat(current_widget, text, show_thinking=True, channel="direct", sleepy_at_night=False):
            calls.append((current_widget, text, show_thinking, channel, sleepy_at_night))

        with patch("ui.pet_manager.has_api_key", return_value=True):
            with patch.object(manager, "_chat_with_llm", side_effect=fake_chat):
                manager.run_auto_chat_once()

        self.assertEqual(len(calls), 1)
        self.assertFalse(calls[0][2])
        self.assertEqual(calls[0][3], "group")
        self.assertTrue(calls[0][4])
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

    def test_group_history_window_submit_adds_user_message_and_agent_reply(self):
        manager = PetManager(self.make_pets())
        manager.create_widgets()

        with patch("ui.pet_manager.has_api_key", return_value=False):
            manager.group_history_window.message_submitted.emit("大家怎么看？")

        self.assertEqual(manager.group_history[0].sender, "你")
        self.assertEqual(manager.group_history[0].content, "大家怎么看？")
        self.assertEqual(manager.group_history[0].kind, "user")
        self.assertEqual(manager.group_history[1].kind, "agent")
        self.assertTrue(all(len(history) == 0 for history in manager.direct_histories.values()))
        manager.close()

    def test_group_chat_submit_uses_llm_when_key_exists(self):
        manager = PetManager(self.make_pets())
        manager.create_widgets()
        calls = []

        def fake_chat(current_widget, text, show_thinking=True, channel="direct", sleepy_at_night=False):
            calls.append((current_widget, text, show_thinking, channel, sleepy_at_night))

        with patch("ui.pet_manager.has_api_key", return_value=True):
            with patch.object(manager, "_chat_with_llm", side_effect=fake_chat):
                manager._on_group_chat_submitted("今晚吃什么？")

        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0][2])
        self.assertEqual(calls[0][3], "group")
        self.assertEqual(manager.group_history[0].content, "今晚吃什么？")
        manager.close()

    def test_group_chat_submit_persists_and_extracts_memory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "app.sqlite3"
            storage = ChatStorage(db_path)
            memory = ExplicitMemoryStore(db_path)
            manager = PetManager(self.make_pets(), chat_storage=storage, explicit_memory=memory)
            manager.create_widgets()

            with patch("ui.pet_manager.has_api_key", return_value=False):
                manager._on_group_chat_submitted("我喜欢猫")
            group_messages = storage.load_recent_messages("group")
            memories = memory.relevant_memories(limit=10)
            manager.close()

        self.assertEqual(group_messages[0].sender, "你")
        self.assertEqual(group_messages[0].content, "我喜欢猫")
        self.assertEqual(group_messages[0].kind, "user")
        self.assertEqual(group_messages[1].kind, "agent")
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0].category, "preference")
        self.assertIn("猫", memories[0].summary)

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
                    package_files = {path.name for path in saved_path.parent.iterdir()}
                    saved_exists = saved_path.exists()

        self.assertEqual(first.pet_config.name, "朋友")
        self.assertEqual(manager.companions[first].pet_config.name, "朋友")
        self.assertEqual(manager.companions[first].profile.personality_tag, "沉稳")
        self.assertNotEqual(manager.companions[second].profile.personality_tag, "沉稳")
        self.assertTrue(saved_exists)
        self.assertIn("manifest.json", package_files)
        self.assertIn("examples.jsonl", package_files)
        self.assertEqual(first.pet_config.persona_path, str(saved_path))
        self.assertEqual(first.pet_config.avatar_path, "normal.png")
        self.assertEqual(first.pet_config.mood_avatar_paths["normal"], "normal.png")
        self.assertEqual(first.pet_config.personality_tag, "沉稳")
        self.assertEqual(manager.direct_histories[first][-1].sender, first.pet_config.name)
        self.assertEqual(len(manager.direct_histories[second]), 0)
        self.assertEqual(len(manager.group_history), 0)
        manager.close()

    def test_reset_persona_clears_binding_and_preserves_agent_state(self):
        pets = self.make_pets()
        pets[0] = PetConfig(
            "cat",
            "小猫",
            "朋友",
            (255, 141, 161),
            personality_tag="沉稳",
            agent_id="agent-1",
            avatar_path="normal.png",
            persona_path="persona.json",
            mood_avatar_paths={"normal": "normal.png"},
        )
        manager = PetManager(pets)
        manager.create_widgets()
        widget = manager.widgets[0]
        manager.companions[widget].profile.system_prompt = "导入人格提示"

        with patch("ui.pet_manager.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes), \
                patch("ui.pet_manager.save_pet_configs"):
            manager.reset_persona_for_pet(widget)

        self.assertIsNone(widget.pet_config.persona_path)
        self.assertEqual(widget.pet_config.agent_id, "agent-1")
        self.assertEqual(widget.pet_config.avatar_path, "normal.png")
        self.assertEqual(widget.pet_config.mood_avatar_paths["normal"], "normal.png")
        self.assertEqual(manager.companions[widget].profile.personality_tag, "沉稳")
        self.assertNotEqual(manager.companions[widget].profile.system_prompt, "导入人格提示")
        self.assertIsNone(manager.pets[0].persona_path)
        manager.close()

    def test_reset_persona_updates_undeployed_agent_config(self):
        manager = PetManager([
            PetConfig("cat", "小猫", "奶糖", (255, 141, 161), agent_id="agent-1", deployed=True),
            PetConfig("dog", "小狗", "布丁", (255, 190, 105), agent_id="agent-2", deployed=False, persona_path="persona.json"),
        ])
        manager.create_widgets()

        with patch("ui.pet_manager.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes), \
                patch("ui.pet_manager.save_pet_configs"):
            manager.reset_persona_for_pet("agent-2")

        self.assertIsNone(manager.pets[1].persona_path)
        self.assertEqual([widget.pet_config.identity for widget in manager.widgets], ["agent-1"])
        manager.close()

    def test_reset_persona_noops_without_imported_persona(self):
        manager = PetManager([PetConfig("cat", "小猫", "奶糖", (255, 141, 161), agent_id="agent-1")])
        manager.create_widgets()

        with patch("ui.pet_manager.QMessageBox.information") as information, \
                patch("ui.pet_manager.save_pet_configs") as save_configs:
            manager.reset_persona_for_pet("agent-1")

        information.assert_called_once()
        save_configs.assert_not_called()
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

    def test_chat_storage_persists_and_restores_histories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = ChatStorage(Path(temp_dir) / "app.sqlite3")
            pets = [PetConfig("cat", "小猫", "奶糖", (255, 141, 161), agent_id="agent-1")]
            manager = PetManager(pets, chat_storage=storage)
            manager.create_widgets()
            widget = manager.widgets[0]
            manager._append_direct_message(widget, BusMessage(sender="你", content="你好", kind="user", anchor_agent_id="agent-1", timestamp=1.0))
            manager._show_chat_response(widget, PetResponse("我在", PetMood.NORMAL, "local", "test"), "direct")
            manager._append_group_message(BusMessage(sender="奶糖", content="群聊一句", kind="agent", agent_id="agent-1", timestamp=3.0))
            manager.close()

            restored = PetManager(pets, chat_storage=storage)
            restored.create_widgets()
            restored_widget = restored.widgets[0]

            self.assertEqual([message.content for message in restored.direct_histories[restored_widget]], ["你好", "我在"])
            self.assertEqual([message.content for message in restored.group_history], ["群聊一句"])
            self.assertEqual([message["content"] for message in restored.companions[restored_widget].history], ["你好", "我在"])
            restored.close()

    def test_clear_histories_also_clears_chat_storage(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = ChatStorage(Path(temp_dir) / "app.sqlite3")
            pets = [PetConfig("cat", "小猫", "奶糖", (255, 141, 161), agent_id="agent-1")]
            manager = PetManager(pets, chat_storage=storage)
            manager.create_widgets()
            widget = manager.widgets[0]
            manager._append_direct_message(widget, BusMessage(sender="你", content="单聊", kind="user", anchor_agent_id="agent-1"))
            manager._append_group_message(BusMessage(sender="奶糖", content="群聊", kind="agent"))

            manager._clear_direct_history(widget)
            direct_after_clear = storage.load_recent_messages("direct", "agent-1")
            group_after_direct_clear = storage.load_recent_messages("group")
            manager.clear_group_history()
            group_after_clear = storage.load_recent_messages("group")
            manager.close()

        self.assertEqual(direct_after_clear, [])
        self.assertEqual([message.content for message in group_after_direct_clear], ["群聊"])
        self.assertEqual(group_after_clear, [])

    def test_user_chat_creates_explicit_memory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            memory = ExplicitMemoryStore(Path(temp_dir) / "app.sqlite3")
            manager = PetManager([PetConfig("cat", "小猫", "奶糖", (255, 141, 161), agent_id="agent-1")], explicit_memory=memory)
            manager.create_widgets()
            widget = manager.widgets[0]

            with patch("ui.pet_manager.has_api_key", return_value=False):
                manager._on_pet_chat_requested(widget, "我喜欢猫")
            memories = memory.relevant_memories(limit=10)
            manager.close()

        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0].category, "preference")
        self.assertIn("猫", memories[0].summary)

    @patch("ui.pet_manager.get_thinking_time", return_value=0)
    def test_streaming_direct_reply_persists_one_final_agent_message(self, _thinking_time):
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = ChatStorage(Path(temp_dir) / "app.sqlite3")
            router = ReplyRouter(api_key_available=lambda: True, cloud_backend=FakeStreamingCloudBackend())
            manager = PetManager(
                [PetConfig("cat", "小猫", "奶糖", (255, 141, 161), agent_id="agent-1")],
                chat_storage=storage,
                reply_router=router,
            )
            manager.create_widgets()
            widget = manager.widgets[0]
            manager.show_pet_chat_window(widget)

            manager._on_pet_chat_requested(widget, "你好")
            QTest.qWait(180)
            stored_messages = storage.load_recent_messages("direct", "agent-1")
            manager.close()

        self.assertEqual([message.kind for message in stored_messages], ["user", "agent"])
        self.assertEqual(stored_messages[-1].content, "你好")
        self.assertEqual([message.content for message in manager.direct_histories.get(widget, [])], [])

    @patch("ui.pet_manager.get_thinking_time", return_value=0)
    def test_streaming_group_reply_persists_one_final_agent_message(self, _thinking_time):
        router = ReplyRouter(api_key_available=lambda: True, cloud_backend=FakeStreamingCloudBackend())
        manager = PetManager(self.make_pets(), reply_router=router)
        manager.create_widgets()
        manager.show_group_history()

        manager._on_group_chat_submitted("大家好")
        QTest.qWait(180)

        self.assertEqual([message.kind for message in manager.group_history], ["user", "agent"])
        self.assertEqual(manager.group_history[-1].content, "你好")
        self.assertEqual(manager.group_history_window.message_count(), 2)
        manager.close()

    @patch("ui.pet_manager.get_typing_delay", return_value=45)
    def test_typewriter_reveals_stream_text_one_character_at_a_time(self, _typing_delay):
        manager = PetManager([PetConfig("cat", "小猫", "奶糖", (255, 141, 161), personality_tag="温柔", agent_id="agent-1")])
        manager.create_widgets()
        widget = manager.widgets[0]

        manager._update_streaming_chat_response(widget, "你好", "direct")

        self.assertEqual(len(widget._bubbles), 0)
        QTest.qWait(60)
        self.assertEqual(widget._bubbles[-1].content, "你")
        self.assertEqual(len(manager.direct_histories[widget]), 0)
        QTest.qWait(60)
        self.assertEqual(widget._bubbles[-1].content, "你好")
        manager.close()

    @patch("ui.pet_manager.get_typing_delay", return_value=45)
    def test_typewriter_always_reveals_one_character_per_update(self, _typing_delay):
        manager = PetManager([PetConfig("cat", "小猫", "奶糖", (255, 141, 161), personality_tag="活泼", agent_id="agent-1")])
        manager.create_widgets()
        widget = manager.widgets[0]

        manager._update_streaming_chat_response(widget, "你好呀朋友", "direct")
        QTest.qWait(60)

        self.assertEqual(widget._bubbles[-1].content, "你")
        manager.close()

    def test_auto_chat_interval_uses_speaker_personality(self):
        manager = PetManager([PetConfig("rabbit", "兔兔", "棉花", (168, 143, 255), personality_tag="温柔", agent_id="agent-1"), PetConfig("cat", "小猫", "奶糖", (255, 141, 161), agent_id="agent-2")])
        manager.create_widgets()

        with patch.object(manager, "_is_nighttime", return_value=False):
            with patch("ui.pet_manager.get_chat_interval", return_value=23000) as chat_interval:
                manager.start_auto_chat()

        self.assertEqual(manager._auto_chat_timer.interval(), 23000)
        chat_interval.assert_called_with("温柔")
        manager.close()

    def test_pause_auto_chat_stops_timer_and_prevents_restart(self):
        manager = PetManager([PetConfig("cat", "小猫", "奶糖", (255, 141, 161), agent_id="agent-1")])
        manager.create_widgets()

        manager.pause_auto_chat()
        manager.add_pet(PetConfig("dog", "小狗", "布丁", (255, 190, 105), agent_id="agent-2"))

        self.assertTrue(manager._auto_chat_paused_by_user)
        self.assertFalse(manager._auto_chat_timer.isActive())
        self.assertEqual(len(manager.widgets), 2)
        manager.close()

    def test_resume_auto_chat_restarts_when_two_agents_visible(self):
        manager = PetManager([
            PetConfig("cat", "小猫", "奶糖", (255, 141, 161), agent_id="agent-1"),
            PetConfig("dog", "小狗", "布丁", (255, 190, 105), agent_id="agent-2"),
        ])
        manager.create_widgets()
        manager.pause_auto_chat()

        with patch.object(manager, "_is_nighttime", return_value=False):
            manager.resume_auto_chat()

        self.assertFalse(manager._auto_chat_paused_by_user)
        self.assertTrue(manager._auto_chat_timer.isActive())
        manager.close()

    def test_manual_auto_chat_interval_override_uses_selected_interval(self):
        manager = PetManager([
            PetConfig("cat", "小猫", "奶糖", (255, 141, 161), agent_id="agent-1"),
            PetConfig("dog", "小狗", "布丁", (255, 190, 105), agent_id="agent-2"),
        ])
        manager.create_widgets()
        manager.start_auto_chat()

        with patch.object(manager, "_is_nighttime", return_value=False):
            manager.set_auto_chat_interval_override(30_000)

        self.assertEqual(manager._auto_chat_interval_override_ms, 30_000)
        self.assertEqual(manager._auto_chat_timer.interval(), 30_000)
        manager.close()

    def test_nighttime_multiplies_auto_chat_interval(self):
        manager = PetManager(self.make_pets())

        with patch.object(manager, "_is_nighttime", return_value=True):
            self.assertEqual(manager._effective_auto_chat_interval(15_000), 45_000)
        with patch.object(manager, "_is_nighttime", return_value=False):
            self.assertEqual(manager._effective_auto_chat_interval(15_000), 15_000)
        manager.close()

    def test_nighttime_auto_group_chat_sets_sleepy_mood(self):
        manager = PetManager(self.make_pets())
        manager.create_widgets()
        speaker = manager.widgets[0]

        with patch.object(manager, "_is_nighttime", return_value=True):
            with patch("ui.pet_manager.has_api_key", return_value=False):
                manager.run_auto_chat_once()

        self.assertEqual(speaker.mood, PetMood.SLEEPY)
        self.assertEqual(manager.group_history[-1].kind, "agent")
        manager.close()

    def test_typewriter_finishes_before_persisting_stream_response(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = ChatStorage(Path(temp_dir) / "app.sqlite3")
            manager = PetManager(
                [PetConfig("cat", "小猫", "奶糖", (255, 141, 161), agent_id="agent-1")],
                chat_storage=storage,
            )
            manager.create_widgets()
            widget = manager.widgets[0]

            manager._finish_streaming_chat_response(widget, PetResponse("你好", PetMood.HAPPY, "llm", "stream_complete"), "direct")
            self.assertEqual(storage.load_recent_messages("direct", "agent-1"), [])
            QTest.qWait(180)
            stored_messages = storage.load_recent_messages("direct", "agent-1")
            manager.close()

        self.assertEqual([message.kind for message in stored_messages], ["agent"])
        self.assertEqual(stored_messages[-1].content, "你好")

    def test_reply_request_includes_explicit_memory_context(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            memory = ExplicitMemoryStore(Path(temp_dir) / "app.sqlite3")
            memory.remember_user_message("我喜欢猫")
            local_backend = RecordingLocalBackend()
            router = ReplyRouter(api_key_available=lambda: False, local_backend=local_backend)
            manager = PetManager(
                [PetConfig("cat", "小猫", "奶糖", (255, 141, 161), agent_id="agent-1")],
                explicit_memory=memory,
                reply_router=router,
            )
            manager.create_widgets()
            widget = manager.widgets[0]

            manager._on_pet_chat_requested(widget, "猫")
            manager.close()

        self.assertEqual(len(local_backend.requests), 1)
        self.assertIn("猫", local_backend.requests[0].memory_context)
        self.assertEqual(local_backend.requests[0].channel, "direct")
        self.assertEqual(local_backend.requests[0].event_type, "chat")

    def test_memory_recall_adds_direct_message_and_marks_mentioned(self):
        now = datetime.now()
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "app.sqlite3"
            storage = ChatStorage(db_path)
            memory = ExplicitMemoryStore(db_path)
            record = memory.remember_user_message("我明天要考试了", now=now - timedelta(days=2))[0]
            manager = PetManager(
                [PetConfig("cat", "小猫", "奶糖", (255, 141, 161), agent_id="agent-1")],
                chat_storage=storage,
                explicit_memory=memory,
            )
            manager.create_widgets()
            widget = manager.widgets[0]

            manager.run_memory_recall_once()
            due_after_recall = memory.due_memories()
            stored_messages = storage.load_recent_messages("direct", "agent-1")
            manager.close()

        self.assertEqual(due_after_recall, [])
        self.assertIn("考试", manager.direct_histories.get(widget, stored_messages)[-1].content if widget in manager.direct_histories else stored_messages[-1].content)
        self.assertEqual(stored_messages[-1].agent_id, "agent-1")
        self.assertEqual(stored_messages[-1].kind, "agent")
        self.assertTrue(record.id)


if __name__ == "__main__":
    unittest.main()
