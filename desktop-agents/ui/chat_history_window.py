import time
from collections.abc import Iterable

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.agent_bus import BusMessage


class ChatHistoryWindow(QMainWindow):
    clear_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._message_count = 0
        self._setup_window()
        self._setup_ui()

    def _setup_window(self):
        self.setWindowTitle("聊天记录")
        self.resize(520, 680)

    def _setup_ui(self):
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("群聊记录", self)
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #202124;")
        subtitle = QLabel("最近消息", self)
        subtitle.setStyleSheet("font-size: 12px; color: #6B7280;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        clear_button = QPushButton("清空", self)
        clear_button.clicked.connect(self.clear_requested.emit)
        close_button = QPushButton("关闭", self)
        close_button.clicked.connect(self.hide)
        header.addLayout(title_box)
        header.addStretch(1)
        header.addWidget(clear_button)
        header.addWidget(close_button)
        root.addLayout(header)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: 1px solid #E5E7EB; background: #F5F7FA; }")

        self.message_container = QWidget(self.scroll_area)
        self.message_layout = QVBoxLayout(self.message_container)
        self.message_layout.setContentsMargins(12, 12, 12, 12)
        self.message_layout.setSpacing(10)
        self.message_layout.addStretch(1)
        self.scroll_area.setWidget(self.message_container)
        root.addWidget(self.scroll_area, 1)
        self.setCentralWidget(central)

    def load_messages(self, messages: Iterable[BusMessage]) -> None:
        self.clear_messages()
        for message in messages:
            self.append_message(message)

    def append_message(self, msg: BusMessage) -> None:
        row = self._create_message_row(msg)
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

    def message_count(self) -> int:
        return self._message_count

    def _create_message_row(self, msg: BusMessage) -> QWidget:
        is_user = msg.kind == "user"
        row = QWidget(self)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)

        bubble_box = QVBoxLayout()
        bubble_box.setSpacing(4)
        bubble_box.setContentsMargins(0, 0, 0, 0)

        timestamp = time.strftime("%H:%M:%S", time.localtime(msg.timestamp))
        meta = QLabel(f"{timestamp}  {msg.sender}", row)
        meta.setStyleSheet("font-size: 11px; color: #6B7280;")
        meta.setAlignment(Qt.AlignmentFlag.AlignRight if is_user else Qt.AlignmentFlag.AlignLeft)

        bubble = QLabel(msg.content, row)
        bubble.setWordWrap(True)
        bubble.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bubble.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        bubble.setMaximumWidth(360)
        if is_user:
            bubble.setStyleSheet(
                "QLabel { background: #95EC69; color: #111827; border-radius: 10px; padding: 8px 10px; font-size: 14px; }"
            )
        elif msg.kind == "system":
            bubble.setStyleSheet(
                "QLabel { background: #E5E7EB; color: #374151; border-radius: 10px; padding: 8px 10px; font-size: 13px; }"
            )
        else:
            bubble.setStyleSheet(
                "QLabel { background: #FFFFFF; color: #111827; border-radius: 10px; padding: 8px 10px; font-size: 14px; }"
            )

        bubble_box.addWidget(meta)
        bubble_box.addWidget(bubble)

        if is_user:
            row_layout.addStretch(1)
            row_layout.addLayout(bubble_box)
        else:
            row_layout.addLayout(bubble_box)
            row_layout.addStretch(1)
        return row

    def _scroll_to_bottom(self):
        bar = self.scroll_area.verticalScrollBar()
        bar.setValue(bar.maximum())
