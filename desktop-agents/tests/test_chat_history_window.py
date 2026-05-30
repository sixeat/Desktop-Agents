import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from core.agent import Agent
from core.agent_bus import AgentBus, BusMessage
from ui.agent_manager import AgentManager
from ui.chat_history_window import ChatHistoryWindow


class ChatHistoryWindowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        self.app.processEvents()

    def test_custom_title_and_subtitle_can_be_set(self):
        window = ChatHistoryWindow("单聊记录", "最近 50 条")

        self.assertEqual(window.windowTitle(), "单聊记录")
        window.close()

    def test_load_messages_shows_existing_history(self):
        window = ChatHistoryWindow()
        messages = [
            BusMessage(sender="小明", content="先看日志", kind="agent", timestamp=1),
            BusMessage(sender="你", content="好", kind="user", timestamp=2),
        ]

        window.load_messages(messages)

        self.assertEqual(window.message_count(), 2)
        window.close()

    def test_append_message_adds_live_message(self):
        window = ChatHistoryWindow()

        window.append_message(BusMessage(sender="小红", content="我整理一下", kind="agent"))

        self.assertEqual(window.message_count(), 1)
        window.close()

    def test_clear_messages_resets_count(self):
        window = ChatHistoryWindow()
        window.append_message(BusMessage(sender="大哥", content="先控风险", kind="agent"))

        window.clear_messages()

        self.assertEqual(window.message_count(), 0)
        window.close()

    def test_input_is_disabled_by_default(self):
        window = ChatHistoryWindow()

        self.assertIsNone(window.input_box)
        window.close()

    def test_enabled_input_emits_message_and_clears_box(self):
        window = ChatHistoryWindow(input_enabled=True)
        submitted = []
        window.message_submitted.connect(submitted.append)
        window.input_box.setText("  大家怎么看？  ")

        window._submit_input()

        self.assertEqual(submitted, ["大家怎么看？"])
        self.assertEqual(window.input_box.text(), "")
        window.close()

    def test_empty_input_is_ignored(self):
        window = ChatHistoryWindow(input_enabled=True)
        submitted = []
        window.message_submitted.connect(submitted.append)
        window.input_box.setText("   ")

        window._submit_input()

        self.assertEqual(submitted, [])
        window.close()

    def test_partial_message_updates_without_counting_as_history(self):
        window = ChatHistoryWindow()

        window.show_partial_message(BusMessage(sender="奶糖", content="你", kind="agent"))
        window.update_partial_message("你好")

        self.assertEqual(window.message_count(), 0)
        self.assertIsNotNone(window._partial_row)
        self.assertEqual(window._partial_bubble.text(), "你好")
        window.clear_partial_message()
        self.assertIsNone(window._partial_row)
        window.append_message(BusMessage(sender="奶糖", content="你好", kind="agent"))
        self.assertEqual(window.message_count(), 1)
        window.close()

    def test_agent_manager_imports_wechat_persona_from_export(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir) / "export"
            persona_dir = Path(temp_dir) / "personas"
            export_dir.mkdir()
            persona_dir.mkdir()
            (export_dir / "张斌.txt").write_text(
                "2024-01-01 10:00:00 张斌 [文字] 今晚打球吗\n"
                "2024-01-01 10:01:00 槐 [文字] 可以啊\n"
                "2024-01-01 10:02:00 张斌 [文字] 那我晚点到\n",
                encoding="utf-8",
            )

            import core.personality as personality_module
            import ui.agent_manager as agent_manager_module
            original_manager_personas_dir = agent_manager_module.PERSONAS_DIR
            original_core_personas_dir = personality_module.PERSONAS_DIR
            agent_manager_module.PERSONAS_DIR = persona_dir
            personality_module.PERSONAS_DIR = persona_dir
            try:
                bus = AgentBus()
                agents = {"xiaoming": Agent("xiaoming")}
                bus.register("xiaoming", agents["xiaoming"])
                manager = AgentManager(bus, agents)
                manager.create_widgets()

                persona_id = manager.import_wechat_persona_from_export(export_dir, "张斌", "张斌")

                self.assertEqual(persona_id, "张斌".lower())
                self.assertTrue((persona_dir / "张斌.json").exists())
                self.assertIn(persona_id, manager.personas)
                manager.close()
            finally:
                agent_manager_module.PERSONAS_DIR = original_manager_personas_dir
                personality_module.PERSONAS_DIR = original_core_personas_dir

    def test_agent_manager_delivers_bus_messages_to_history_window(self):
        bus = AgentBus()
        agents = {"xiaoming": Agent("xiaoming")}
        bus.register("xiaoming", agents["xiaoming"])
        manager = AgentManager(bus, agents)
        manager.create_widgets()

        manager.bus_message_received.emit(BusMessage(sender="小明", content="记录一下", kind="agent", agent_id="xiaoming"))
        self.app.processEvents()

        self.assertEqual(manager.chat_history_window.message_count(), 1)
        manager.close()


if __name__ == "__main__":
    unittest.main()
