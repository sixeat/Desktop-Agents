import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from core.pet import PetConfig, PetMood
from ui.pet_widget import PetWidget

_app = QApplication.instance() or QApplication([])


class PetWidgetTest(unittest.TestCase):
    def make_widget(self) -> PetWidget:
        return PetWidget(PetConfig("cat", "小猫", "奶糖", (255, 141, 161)))

    def test_widget_starts_with_normal_mood(self):
        widget = self.make_widget()

        self.assertEqual(widget.mood, PetMood.NORMAL)
        widget.close()

    def test_set_mood_updates_state(self):
        widget = self.make_widget()

        widget.set_mood(PetMood.HAPPY, animate=False)

        self.assertEqual(widget.mood, PetMood.HAPPY)
        widget.close()

    def test_bounce_animation_can_start(self):
        widget = self.make_widget()

        widget.set_mood(PetMood.SURPRISED)

        self.assertTrue(hasattr(widget, "_bounce_anim"))
        widget.close()

    def test_left_click_sets_happy_and_emits_clicked(self):
        widget = self.make_widget()
        clicks = []
        widget.clicked.connect(lambda: clicks.append(True))
        widget.show()

        QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=QPoint(widget.width() // 2, widget.height() // 2))

        self.assertEqual(widget.mood, PetMood.HAPPY)
        self.assertEqual(clicks, [True])
        widget.close()

    def test_show_speech_creates_bubble(self):
        widget = self.make_widget()
        widget.show()

        widget.show_speech("我在呢")

        self.assertEqual(len(widget._bubbles), 1)
        widget.close()

    def test_stream_speech_updates_existing_bubble(self):
        widget = self.make_widget()
        widget.show()

        widget.show_or_update_stream_speech("你")
        widget.show_or_update_stream_speech("你好")

        self.assertEqual(len(widget._bubbles), 1)
        self.assertEqual(widget._bubbles[0].content, "你好")
        widget.finish_stream_speech("你好呀")
        self.assertEqual(len(widget._bubbles), 1)
        self.assertEqual(widget._bubbles[0].content, "你好呀")
        widget.close()

    def test_history_signal_can_be_emitted(self):
        widget = self.make_widget()
        requests = []
        widget.history_requested.connect(lambda: requests.append(True))

        widget.history_requested.emit()

        self.assertEqual(requests, [True])
        widget.close()

    def test_persona_import_signal_can_be_emitted(self):
        widget = self.make_widget()
        requests = []
        widget.persona_import_requested.connect(lambda: requests.append(True))

        widget.persona_import_requested.emit()

        self.assertEqual(requests, [True])
        widget.close()

    def test_chat_window_signal_can_be_emitted(self):
        widget = self.make_widget()
        requests = []
        widget.chat_window_requested.connect(lambda: requests.append(True))

        widget.chat_window_requested.emit()

        self.assertEqual(requests, [True])
        widget.close()

    def test_avatar_change_signal_can_be_emitted(self):
        widget = self.make_widget()
        requests = []
        widget.avatar_change_requested.connect(lambda: requests.append(True))

        widget.avatar_change_requested.emit()

        self.assertEqual(requests, [True])
        widget.close()

    def test_set_avatar_path_loads_normal_pixmap(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "normal.png"
            pixmap = QPixmap(16, 16)
            pixmap.fill(QColor("red"))
            pixmap.save(str(path))
            widget = self.make_widget()

            widget.set_avatar_path(path)

            self.assertEqual(widget.pet_config.avatar_path, str(path))
            self.assertIn(PetMood.NORMAL, widget._avatar_pixmaps)
            widget.close()

    def test_invalid_avatar_path_falls_back_without_pixmap(self):
        widget = PetWidget(PetConfig("cat", "小猫", "奶糖", (255, 141, 161), avatar_path="missing.png"))

        self.assertEqual(widget._avatar_pixmaps, {})
        widget.close()

    def test_mood_avatar_paths_are_loaded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            happy = Path(temp_dir) / "happy.png"
            pixmap = QPixmap(16, 16)
            pixmap.fill(QColor("yellow"))
            pixmap.save(str(happy))
            widget = PetWidget(PetConfig("cat", "小猫", "奶糖", (255, 141, 161), mood_avatar_paths={"happy": str(happy)}))

            self.assertIn(PetMood.HAPPY, widget._avatar_pixmaps)
            widget.set_mood(PetMood.HAPPY, animate=False)
            widget.close()

    def test_double_click_opens_chat_window_without_click_reply(self):
        widget = self.make_widget()
        clicks = []
        requests = []
        widget.clicked.connect(lambda: clicks.append(True))
        widget.chat_window_requested.connect(lambda: requests.append(True))
        widget.show()
        widget.set_mood(PetMood.NORMAL, animate=False)

        QTest.mouseDClick(widget, Qt.MouseButton.LeftButton, pos=QPoint(widget.width() // 2, widget.height() // 2))

        self.assertEqual(requests, [True])
        self.assertEqual(clicks, [])
        self.assertEqual(widget.mood, PetMood.NORMAL)
        widget.close()

    def test_drag_release_does_not_trigger_click(self):
        widget = self.make_widget()
        clicks = []
        widget.clicked.connect(lambda: clicks.append(True))
        widget.show()
        widget.set_mood(PetMood.NORMAL, animate=False)
        start = QPoint(widget.width() // 2, widget.height() // 2)
        end = start + QPoint(QApplication.startDragDistance() + 8, 0)

        QTest.mousePress(widget, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(widget, end)
        QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=end)

        self.assertEqual(widget.mood, PetMood.NORMAL)
        self.assertEqual(clicks, [])
        widget.close()


if __name__ == "__main__":
    unittest.main()
