import asyncio
import threading
from pathlib import Path

from PyQt6.QtCore import Qt, QPoint, QRectF, pyqtSignal, QEasingCurve, QVariantAnimation
from PyQt6.QtGui import QAction, QColor, QPainter, QPainterPath, QPen, QPixmap, QBrush, QFont
from PyQt6.QtWidgets import QApplication, QInputDialog, QMenu, QSystemTrayIcon

from config import AGENT_SIZE, BREATHE_MIN_SCALE, BREATHE_MAX_SCALE, BREATHE_DURATION_MS, CHARACTERS_DIR, PROJECT_ROOT
from core.agent import Agent
from ui.bubble import ChatBubble
from ui.desktop_window import DesktopWindow


class AgentWidget(DesktopWindow):
    clicked = pyqtSignal()
    user_input_submitted = pyqtSignal(str)
    persona_switch_requested = pyqtSignal(str)
    history_requested = pyqtSignal()
    wechat_import_requested = pyqtSignal()
    api_key_settings_requested = pyqtSignal()
    chat_message_ready = pyqtSignal(str, str)
    chat_finished = pyqtSignal()

    def __init__(
        self,
        avatar_path: str | Path | None = None,
        agent: Agent | None = None,
        parent=None,
        direct_chat_enabled: bool = True,
        tray_enabled: bool = True,
    ):
        super().__init__(parent)
        self.avatar_path = avatar_path
        self.agent = agent or Agent()
        self.direct_chat_enabled = direct_chat_enabled
        self.tray_enabled = tray_enabled
        self._avatar_pixmap: QPixmap | None = None
        self._current_scale = 1.0
        self._drag_pos: QPoint | None = None
        self._press_global_pos: QPoint | None = None
        self._drag_moved = False
        self._breathe_forward = True
        self._is_chatting = False
        self._bubbles: list[ChatBubble] = []
        self.persona_options = {}

        self._setup_ui()
        self._load_avatar()
        self._start_breathe_animation()
        if self.tray_enabled:
            self._setup_tray_icon()
        else:
            self.tray_icon = None
        self.clicked.connect(self._on_clicked)
        self.chat_message_ready.connect(self._show_chat_bubble)
        self.chat_finished.connect(self._on_chat_finished)

    def _setup_ui(self):
        self.setFixedSize(AGENT_SIZE + 20, AGENT_SIZE + 20)
        self.setContentsMargins(10, 10, 10, 10)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def set_persona_options(self, personas):
        self.persona_options = personas

    def set_avatar_path(self, avatar_path: str | Path | None):
        self.avatar_path = avatar_path
        self._load_avatar()
        self.update()

    def apply_agent_personality(self):
        self.set_avatar_path(getattr(self.agent, "avatar", None))

    def _load_avatar(self):
        avatar_path = self._resolve_avatar_path(self.avatar_path)
        if avatar_path:
            self._avatar_pixmap = QPixmap(str(avatar_path))
        else:
            self._avatar_pixmap = self._create_default_avatar()
        if self._avatar_pixmap and not self._avatar_pixmap.isNull():
            self._avatar_pixmap = self._avatar_pixmap.scaled(
                AGENT_SIZE, AGENT_SIZE,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
        else:
            self._avatar_pixmap = self._create_default_avatar()

    def _resolve_avatar_path(self, avatar_path: str | Path | None) -> Path | None:
        if not avatar_path:
            return None
        path = Path(avatar_path)
        candidates = []
        if path.is_absolute():
            candidates.append(path)
        else:
            candidates.append(PROJECT_ROOT / path)
            candidates.append(CHARACTERS_DIR / path)
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _create_default_avatar(self) -> QPixmap:
        pixmap = QPixmap(AGENT_SIZE, AGENT_SIZE)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(100, 149, 237)))
        painter.drawEllipse(0, 0, AGENT_SIZE, AGENT_SIZE)
        painter.setPen(QPen(QColor(255, 255, 255)))
        painter.setFont(QFont("Microsoft YaHei", 20, QFont.Weight.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "AI")
        painter.end()
        return pixmap

    def _start_breathe_animation(self):
        self._breathe_anim = QVariantAnimation(self)
        self._breathe_anim.setStartValue(BREATHE_MIN_SCALE)
        self._breathe_anim.setEndValue(BREATHE_MAX_SCALE)
        self._breathe_anim.setDuration(BREATHE_DURATION_MS)
        self._breathe_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._breathe_anim.valueChanged.connect(self._on_breathe_value_changed)
        self._breathe_anim.finished.connect(self._toggle_breathe_direction)
        self._breathe_anim.start()

    def _toggle_breathe_direction(self):
        self._breathe_forward = not self._breathe_forward
        if self._breathe_forward:
            self._breathe_anim.setStartValue(BREATHE_MIN_SCALE)
            self._breathe_anim.setEndValue(BREATHE_MAX_SCALE)
        else:
            self._breathe_anim.setStartValue(BREATHE_MAX_SCALE)
            self._breathe_anim.setEndValue(BREATHE_MIN_SCALE)
        self._breathe_anim.start()

    def _on_breathe_value_changed(self, value):
        self._current_scale = float(value)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        center = self.rect().center()
        size = AGENT_SIZE * self._current_scale
        x = center.x() - size / 2
        y = center.y() - size / 2

        clip = QPainterPath()
        clip.addEllipse(QRectF(x, y, size, size))
        painter.setClipPath(clip)

        shadow_offset = 2
        shadow_rect = QRectF(x + shadow_offset, y + shadow_offset, size, size)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 60)))
        painter.drawEllipse(shadow_rect)

        if self._avatar_pixmap:
            src = QRectF(self._avatar_pixmap.rect())
            dst = QRectF(x, y, size, size)
            painter.drawPixmap(dst, self._avatar_pixmap, src)
        else:
            painter.setBrush(QBrush(QColor(100, 149, 237)))
            painter.drawEllipse(QRectF(x, y, size, size))

        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_global_pos = event.globalPosition().toPoint()
            self._drag_pos = self._press_global_pos - self.frameGeometry().topLeft()
            self._drag_moved = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self._drag_pos is not None:
            current_pos = event.globalPosition().toPoint()
            if self._press_global_pos:
                distance = (current_pos - self._press_global_pos).manhattanLength()
                if distance >= QApplication.startDragDistance():
                    self._drag_moved = True
            self.move(current_pos - self._drag_pos)
            self._reposition_bubbles()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            should_emit_click = not self._drag_moved
            self._drag_pos = None
            self._press_global_pos = None
            self._drag_moved = False
            if should_emit_click:
                self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _on_clicked(self):
        text, ok = QInputDialog.getText(None, f"和{self.agent.name}聊天", "你想说什么？")
        if not ok:
            return
        user_input = text.strip()
        if not user_input:
            return

        self.user_input_submitted.emit(user_input)
        if self.direct_chat_enabled:
            self.show_chat_bubble("你", user_input)
            self._start_chat(user_input)

    def _start_chat(self, user_input: str):
        if self._is_chatting:
            self.show_chat_bubble(self.agent.name, "我还在思考上一条消息，请稍等。")
            return

        self._is_chatting = True

        def runner():
            try:
                reply = asyncio.run(self.agent.chat(user_input))
                self.chat_message_ready.emit(self.agent.name, reply)
            except Exception:
                self.chat_message_ready.emit(self.agent.name, "聊天出错了，请稍后再试。")
            finally:
                self.chat_finished.emit()

        threading.Thread(target=runner, daemon=True).start()

    def show_chat_bubble(self, sender: str, content: str):
        self._show_chat_bubble(sender, content)

    def _show_chat_bubble(self, sender: str, content: str):
        bubble = ChatBubble(sender, content)
        self._bubbles.append(bubble)
        bubble.destroyed.connect(lambda _=None, item=bubble: self._remove_bubble(item))
        bubble.show_above(self)

    def _remove_bubble(self, bubble: ChatBubble):
        if bubble in self._bubbles:
            self._bubbles.remove(bubble)

    def _reposition_bubbles(self):
        for bubble in self._bubbles:
            if bubble.isVisible():
                bubble.show_above(self)

    def _on_chat_finished(self):
        self._is_chatting = False

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        if self.persona_options:
            switch_menu = menu.addMenu("切换人格")
            for persona_id, personality in self.persona_options.items():
                action = QAction(personality.name, self)
                action.setCheckable(True)
                action.setChecked(persona_id == self.agent.persona_name)
                action.setToolTip(personality.description)
                action.triggered.connect(
                    lambda checked=False, current_persona_id=persona_id: self.persona_switch_requested.emit(current_persona_id)
                )
                switch_menu.addAction(action)
            menu.addSeparator()

        history_action = QAction("聊天记录", self)
        import_wechat_action = QAction("导入聊天记录人格", self)
        api_key_action = QAction("API Key 设置", self)
        quit_action = QAction("退出", self)
        history_action.triggered.connect(self.history_requested.emit)
        import_wechat_action.triggered.connect(self.wechat_import_requested.emit)
        api_key_action.triggered.connect(self.api_key_settings_requested.emit)
        quit_action.triggered.connect(self._on_quit)
        menu.addAction(history_action)
        menu.addAction(import_wechat_action)
        menu.addAction(api_key_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        menu.exec(self.mapToGlobal(pos))

    def _on_quit(self):
        QApplication.instance().quit()

    def _setup_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        tray_pixmap = self._create_tray_pixmap()
        from PyQt6.QtGui import QIcon
        self.tray_icon.setIcon(QIcon(tray_pixmap))
        self.tray_icon.setToolTip("Desktop Agent")

        tray_menu = QMenu()
        show_action = QAction("显示", self)
        hide_action = QAction("隐藏", self)
        quit_action = QAction("退出", self)
        show_action.triggered.connect(self.show)
        hide_action.triggered.connect(self.hide)
        quit_action.triggered.connect(self._on_quit)
        tray_menu.addAction(show_action)
        tray_menu.addAction(hide_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _create_tray_pixmap(self) -> QPixmap:
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(100, 149, 237)))
        painter.drawEllipse(2, 2, 60, 60)
        painter.setPen(QPen(QColor(255, 255, 255)))
        painter.setFont(QFont("Microsoft YaHei", 16, QFont.Weight.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "AI")
        painter.end()
        return pixmap

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show()
