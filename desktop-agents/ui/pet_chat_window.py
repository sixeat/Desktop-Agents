import time
from collections.abc import Iterable

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.agent_bus import BusMessage
from ui.theme import apply_cute_style, set_window_icon


class PetChatWindow(QMainWindow):
    message_submitted = pyqtSignal(str)

    def __init__(self, agent_name: str, parent=None):
        super().__init__(parent)
        self.agent_name = agent_name
        self._message_count = 0
        self._partial_row: QWidget | None = None
        self._partial_bubble: QLabel | None = None
        self._setup_window()
        self._setup_ui()

    def _setup_window(self) -> None:
        self.setWindowTitle(f"和{self.agent_name}聊天")
        self.resize(560, 700)
        set_window_icon(self)
        apply_cute_style(self)

    def _setup_ui(self) -> None:
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        self.title_label = QLabel(f"和{self.agent_name}聊天", self)
        self.title_label.setStyleSheet("font-size: 22px; font-weight: 700; color: #794f27;")
        root.addWidget(self.title_label)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: 3px solid #d4c9b4; border-radius: 16px; background: rgb(247, 243, 223); }")
        self.message_container = QWidget(self.scroll_area)
        self.message_layout = QVBoxLayout(self.message_container)
        self.message_layout.setContentsMargins(12, 12, 12, 12)
        self.message_layout.setSpacing(10)
        self.message_layout.addStretch(1)
        self.scroll_area.setWidget(self.message_container)
        root.addWidget(self.scroll_area, 1)

        input_row = QHBoxLayout()
        self.input = QLineEdit(self)
        self.input.setPlaceholderText("和它说点什么，回车发送")
        self.input.returnPressed.connect(self._submit_message)
        send_button = QPushButton("发送", self)
        send_button.clicked.connect(self._submit_message)
        input_row.addWidget(self.input, 1)
        input_row.addWidget(send_button)
        root.addLayout(input_row)
        self.setCentralWidget(central)

    def load_messages(self, messages: Iterable[BusMessage]) -> None:
        self.clear_messages()
        for message in messages:
            self.append_message(message)

    def append_message(self, message: BusMessage) -> None:
        row = self._create_message_row(message)
        self.message_layout.insertWidget(self.message_layout.count() - 1, row)
        self._message_count += 1
        QTimer.singleShot(0, self._scroll_to_bottom)

    def clear_messages(self) -> None:
        while self.message_layout.count() > 1:
            item = self.message_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._message_count = 0
        self._partial_row = None
        self._partial_bubble = None

    def show_partial_message(self, message: BusMessage) -> None:
        if self._partial_row is None:
            self._partial_row, self._partial_bubble = self._create_message_row(message, return_bubble=True)
            self.message_layout.insertWidget(self.message_layout.count() - 1, self._partial_row)
        self.update_partial_message(message.content)

    def update_partial_message(self, content: str) -> None:
        if self._partial_bubble is not None:
            self._partial_bubble.setText(content)
            QTimer.singleShot(0, self._scroll_to_bottom)

    def clear_partial_message(self) -> None:
        if self._partial_row is None:
            return
        self.message_layout.removeWidget(self._partial_row)
        self._partial_row.deleteLater()
        self._partial_row = None
        self._partial_bubble = None

    def message_count(self) -> int:
        return self._message_count

    def set_agent_name(self, agent_name: str) -> None:
        self.agent_name = agent_name
        self.setWindowTitle(f"和{self.agent_name}聊天")
        self.title_label.setText(f"和{self.agent_name}聊天")

    def _submit_message(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.message_submitted.emit(text)

    def _create_message_row(self, msg: BusMessage, return_bubble: bool = False):
        is_user = msg.kind == "user"
        row = QWidget(self)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        bubble_box = QVBoxLayout()
        bubble_box.setSpacing(4)
        bubble_box.setContentsMargins(0, 0, 0, 0)

        timestamp = time.strftime("%H:%M:%S", time.localtime(msg.timestamp))
        meta = QLabel(f"{timestamp}  {msg.sender}", row)
        meta.setStyleSheet("font-size: 11px; color: #9f927d;")
        meta.setAlignment(Qt.AlignmentFlag.AlignRight if is_user else Qt.AlignmentFlag.AlignLeft)

        bubble = QLabel(msg.content, row)
        bubble.setWordWrap(True)
        bubble.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bubble.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        bubble.setMaximumWidth(360)
        if is_user:
            bubble.setStyleSheet(
                "QLabel { background: #19c8b9; color: #ffffff; border-radius: 14px; padding: 9px 14px; font-size: 14px; }"
            )
        elif msg.kind == "system":
            bubble.setStyleSheet(
                "QLabel { background: #e8e4d8; color: #725d42; border-radius: 14px; padding: 8px 12px; font-size: 13px; }"
            )
        else:
            bubble.setStyleSheet(
                "QLabel { background: rgb(247, 243, 223); color: #794f27; border: 3px solid #d4c9b4; border-radius: 14px; padding: 9px 14px; font-size: 14px; }"
            )

        bubble_box.addWidget(meta)
        bubble_box.addWidget(bubble)
        if is_user:
            row_layout.addStretch(1)
            row_layout.addLayout(bubble_box)
        else:
            row_layout.addLayout(bubble_box)
            row_layout.addStretch(1)
        if return_bubble:
            return row, bubble
        return row

    def _scroll_to_bottom(self) -> None:
        bar = self.scroll_area.verticalScrollBar()
        bar.setValue(bar.maximum())
