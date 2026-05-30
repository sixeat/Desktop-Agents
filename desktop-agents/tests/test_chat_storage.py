import tempfile
import unittest
from pathlib import Path

from core.agent_bus import BusMessage
from core.chat_storage import ChatStorage


class ChatStorageTest(unittest.TestCase):
    def make_storage(self, temp_dir: str) -> ChatStorage:
        return ChatStorage(Path(temp_dir) / "chat.sqlite3")

    def test_add_and_load_direct_messages(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = self.make_storage(temp_dir)
            storage.add_message("direct", BusMessage(sender="你", content="你好", kind="user", anchor_agent_id="agent-1", timestamp=1.0))
            storage.add_message("direct", BusMessage(sender="奶糖", content="我在", kind="agent", agent_id="agent-1", anchor_agent_id="agent-1", timestamp=2.0))

            messages = storage.load_recent_messages("direct", "agent-1")

        self.assertEqual([message.content for message in messages], ["你好", "我在"])
        self.assertEqual(messages[0].kind, "user")
        self.assertEqual(messages[1].agent_id, "agent-1")
        self.assertEqual(messages[1].anchor_agent_id, "agent-1")

    def test_group_and_direct_messages_are_separate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = self.make_storage(temp_dir)
            storage.add_message("group", BusMessage(sender="奶糖", content="群聊", kind="agent", agent_id="agent-1", timestamp=1.0))
            storage.add_message("direct", BusMessage(sender="你", content="单聊", kind="user", anchor_agent_id="agent-1", timestamp=2.0))

            group_messages = storage.load_recent_messages("group")
            direct_messages = storage.load_recent_messages("direct", "agent-1")

        self.assertEqual([message.content for message in group_messages], ["群聊"])
        self.assertEqual([message.content for message in direct_messages], ["单聊"])

    def test_direct_messages_are_isolated_by_anchor_agent_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = self.make_storage(temp_dir)
            storage.add_message("direct", BusMessage(sender="你", content="给一号", kind="user", anchor_agent_id="agent-1", timestamp=1.0))
            storage.add_message("direct", BusMessage(sender="你", content="给二号", kind="user", anchor_agent_id="agent-2", timestamp=2.0))

            first = storage.load_recent_messages("direct", "agent-1")
            second = storage.load_recent_messages("direct", "agent-2")

        self.assertEqual([message.content for message in first], ["给一号"])
        self.assertEqual([message.content for message in second], ["给二号"])

    def test_load_recent_messages_returns_latest_in_chronological_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = self.make_storage(temp_dir)
            for index in range(5):
                storage.add_message("direct", BusMessage(sender="你", content=str(index), kind="user", anchor_agent_id="agent-1", timestamp=float(index)))

            messages = storage.load_recent_messages("direct", "agent-1", limit=3)

        self.assertEqual([message.content for message in messages], ["2", "3", "4"])

    def test_clear_direct_does_not_clear_group(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = self.make_storage(temp_dir)
            storage.add_message("group", BusMessage(sender="奶糖", content="群聊", kind="agent", timestamp=1.0))
            storage.add_message("direct", BusMessage(sender="你", content="单聊", kind="user", anchor_agent_id="agent-1", timestamp=2.0))

            storage.clear_conversation("direct", "agent-1")

            group_messages = storage.load_recent_messages("group")
            direct_messages = storage.load_recent_messages("direct", "agent-1")

        self.assertEqual([message.content for message in group_messages], ["群聊"])
        self.assertEqual(direct_messages, [])

    def test_clear_group_does_not_clear_direct(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = self.make_storage(temp_dir)
            storage.add_message("group", BusMessage(sender="奶糖", content="群聊", kind="agent", timestamp=1.0))
            storage.add_message("direct", BusMessage(sender="你", content="单聊", kind="user", anchor_agent_id="agent-1", timestamp=2.0))

            storage.clear_conversation("group")

            group_messages = storage.load_recent_messages("group")
            direct_messages = storage.load_recent_messages("direct", "agent-1")

        self.assertEqual(group_messages, [])
        self.assertEqual([message.content for message in direct_messages], ["单聊"])


if __name__ == "__main__":
    unittest.main()
