import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from config import MAX_DESKTOP_AGENTS
from core.pet import PetConfig
from ui.agent_management_dialog import AgentManagementDialog

_app = QApplication.instance() or QApplication([])


class AgentManagementDialogTest(unittest.TestCase):
    def make_dialog(self):
        configs = [
            PetConfig("cat", "小猫", "奶糖", (1, 2, 3), agent_id="agent-1"),
            PetConfig("dog", "小狗", "布丁", (4, 5, 6), agent_id="agent-2", avatar_path="a.png", persona_path="p.json"),
        ]
        return AgentManagementDialog(configs)

    def test_loads_agent_rows(self):
        dialog = self.make_dialog()

        self.assertEqual(dialog.table.rowCount(), 2)
        self.assertEqual(dialog.table.item(0, 0).checkState(), Qt.CheckState.Checked)
        self.assertEqual(dialog.table.item(0, 1).text(), "奶糖")
        self.assertEqual(dialog.table.item(1, 3).text(), "已设置")
        dialog.close()

    def test_selected_agent_id(self):
        dialog = self.make_dialog()
        dialog.table.selectRow(1)

        self.assertEqual(dialog.selected_agent_id(), "agent-2")
        dialog.close()

    def test_keeps_add_enabled_when_deploy_limit_reached(self):
        configs = [PetConfig("cat", "小猫", f"Agent{i}", (1, 2, 3), agent_id=f"agent-{i}") for i in range(MAX_DESKTOP_AGENTS)]
        dialog = AgentManagementDialog(configs)

        self.assertTrue(dialog.add_button.isEnabled())
        self.assertTrue(dialog.delete_button.isEnabled())
        dialog.close()

    def test_disables_delete_when_only_one_agent_remains(self):
        dialog = AgentManagementDialog([PetConfig("cat", "小猫", "奶糖", (1, 2, 3), agent_id="agent-1")])

        self.assertTrue(dialog.add_button.isEnabled())
        self.assertFalse(dialog.delete_button.isEnabled())
        dialog.close()

    def test_buttons_emit_signals(self):
        dialog = self.make_dialog()
        emitted = []
        dialog.add_requested.connect(lambda: emitted.append("add"))
        dialog.edit_requested.connect(lambda agent_id: emitted.append(("edit", agent_id)))
        dialog.delete_requested.connect(lambda agent_id: emitted.append(("delete", agent_id)))
        dialog.import_requested.connect(lambda agent_id: emitted.append(("import", agent_id)))
        dialog.reset_persona_requested.connect(lambda agent_id: emitted.append(("reset", agent_id)))
        dialog.avatar_requested.connect(lambda agent_id: emitted.append(("avatar", agent_id)))
        dialog.chat_requested.connect(lambda agent_id: emitted.append(("chat", agent_id)))

        dialog.add_button.click()
        dialog.edit_button.click()
        dialog.delete_button.click()
        dialog.import_button.click()
        dialog.reset_persona_button.click()
        dialog.avatar_button.click()
        dialog.chat_button.click()

        self.assertIn("add", emitted)
        self.assertIn(("edit", "agent-1"), emitted)
        self.assertIn(("delete", "agent-1"), emitted)
        self.assertIn(("import", "agent-1"), emitted)
        self.assertIn(("reset", "agent-1"), emitted)
        self.assertIn(("avatar", "agent-1"), emitted)
        self.assertIn(("chat", "agent-1"), emitted)
        dialog.close()

    def test_deployed_checkbox_emits_signal(self):
        dialog = self.make_dialog()
        emitted = []
        dialog.deployed_changed.connect(lambda agent_id, deployed: emitted.append((agent_id, deployed)))

        dialog.table.item(1, 0).setCheckState(Qt.CheckState.Unchecked)

        self.assertEqual(emitted, [("agent-2", False)])
        dialog.close()


if __name__ == "__main__":
    unittest.main()
