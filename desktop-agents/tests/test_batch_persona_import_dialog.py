import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from ui.batch_persona_import_dialog import BatchPersonaImportDialog

_app = QApplication.instance() or QApplication([])


class BatchPersonaImportDialogTest(unittest.TestCase):
    def test_scan_folder_loads_senders_and_builds_merge_plan(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir) / "exports"
            folder.mkdir()
            (folder / "群聊_AAA.txt").write_text(
                "2024-01-01 10:00:00 '张斌'\n到了吗\n\n"
                "2024-01-01 10:01:00 '张斌'\n我快到了\n\n"
                "2024-01-01 10:02:00 '斌哥'\n哈哈我也快到了\n\n"
                "2024-01-01 10:03:00 '斌哥'\n别急\n",
                encoding="utf-8",
            )
            dialog = BatchPersonaImportDialog(Path(temp_dir) / "personas")
            dialog.selected_dir = folder
            dialog.consent_checkbox.setChecked(True)

            dialog.scan_folder()
            for row in range(dialog.table.rowCount()):
                if dialog.table.item(row, 1).text() == "斌哥":
                    dialog.table.item(row, 3).setText("张斌")

            plans = dialog._build_plans()

        self.assertEqual(dialog.table.rowCount(), 2)
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0].persona_name, "张斌")
        self.assertEqual(set(plans[0].source_names), {"张斌", "斌哥"})
        dialog.close()

    def test_generate_personas_saves_results(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir) / "exports"
            folder.mkdir()
            output_dir = Path(temp_dir) / "personas"
            (folder / "私聊_老猪.txt").write_text(
                "2024-01-01 10:00:00 '老猪'\n快了快了\n\n"
                "2024-01-01 10:01:00 '老猪'\n别催\n",
                encoding="utf-8",
            )
            dialog = BatchPersonaImportDialog(output_dir)
            dialog.selected_dir = folder
            dialog.consent_checkbox.setChecked(True)
            dialog.scan_folder()

            dialog.generate_personas()

            self.assertEqual(len(dialog.results), 1)
            self.assertTrue((output_dir / "老猪" / "persona.json").exists())
            dialog.close()

    def test_scan_requires_consent(self):
        dialog = BatchPersonaImportDialog(Path("personas"))
        dialog.selected_dir = Path("exports")

        with patch("ui.batch_persona_import_dialog.QMessageBox.warning") as warning, \
                patch("ui.batch_persona_import_dialog.scan_persona_sources") as scan_sources:
            dialog.scan_folder()

        warning.assert_called_once()
        scan_sources.assert_not_called()
        dialog.close()

    def test_generate_requires_consent(self):
        dialog = BatchPersonaImportDialog(Path("personas"))
        dialog.sources = []

        with patch("ui.batch_persona_import_dialog.QMessageBox.warning") as warning, \
                patch("ui.batch_persona_import_dialog.build_batch_personas") as build_personas:
            dialog.generate_personas()

        warning.assert_called_once()
        build_personas.assert_not_called()
        dialog.close()

    def test_preview_includes_privacy_copy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir) / "exports"
            folder.mkdir()
            (folder / "私聊_老猪.txt").write_text(
                "2024-01-01 10:00:00 '老猪'\n快了快了\n\n"
                "2024-01-01 10:01:00 '老猪'\n别催\n",
                encoding="utf-8",
            )
            dialog = BatchPersonaImportDialog(Path(temp_dir) / "personas")
            dialog.selected_dir = folder
            dialog.consent_checkbox.setChecked(True)

            dialog.scan_folder()
            preview = dialog.preview.toPlainText()

        self.assertIn("原始聊天记录不会复制到人格目录", preview)
        self.assertIn("manifest/persona/style/examples/system_prompt/eval", preview)
        dialog.close()

    def test_scan_without_folder_warns(self):
        dialog = BatchPersonaImportDialog(Path("personas"))

        with patch("ui.batch_persona_import_dialog.QMessageBox.warning") as warning:
            dialog.scan_folder()

        warning.assert_called_once()
        dialog.close()


if __name__ == "__main__":
    unittest.main()
