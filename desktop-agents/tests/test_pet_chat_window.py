import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from core.agent_bus import BusMessage
from ui.pet_chat_window import PetChatWindow

_app = QApplication.instance() or QApplication([])


class PetChatWindowTest(unittest.TestCase):
    def test_window_title_uses_agent_name(self):
        window = PetChatWindow("奶糖")

        self.assertEqual(window.windowTitle(), "和奶糖聊天")
        window.close()

    def test_load_messages_shows_existing_history(self):
        window = PetChatWindow("奶糖")
        messages = [
            BusMessage(sender="你", content="你好", kind="user", timestamp=1),
            BusMessage(sender="奶糖", content="我在", kind="agent", timestamp=2),
        ]

        window.load_messages(messages)

        self.assertEqual(window.message_count(), 2)
        window.close()

    def test_submit_message_emits_signal_and_clears_input(self):
        window = PetChatWindow("奶糖")
        submitted = []
        window.message_submitted.connect(submitted.append)
        window.input.setText("  你好呀  ")

        QTest.keyClick(window.input, Qt.Key.Key_Return)

        self.assertEqual(submitted, ["你好呀"])
        self.assertEqual(window.input.text(), "")
        window.close()

    def test_clear_messages_resets_count(self):
        window = PetChatWindow("奶糖")
        window.append_message(BusMessage(sender="奶糖", content="我在", kind="agent"))

        window.clear_messages()

        self.assertEqual(window.message_count(), 0)
        window.close()

    def test_partial_message_updates_without_counting_as_history(self):
        window = PetChatWindow("奶糖")

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

    def test_set_agent_name_updates_title(self):
        window = PetChatWindow("奶糖")

        window.set_agent_name("张斌")

        self.assertEqual(window.windowTitle(), "和张斌聊天")
        self.assertEqual(window.title_label.text(), "和张斌聊天")
        window.close()


if __name__ == "__main__":
    unittest.main()
