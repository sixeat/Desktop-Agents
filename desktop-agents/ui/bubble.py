from PyQt6.QtCore import QPoint, QRect, Qt, QPropertyAnimation, QTimer
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsOpacityEffect,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class ChatBubble(QWidget):
    TRIANGLE_HEIGHT = 10
    RADIUS = 14
    MAX_WIDTH = 320

    def __init__(self, sender: str, content: str, anchor_widget: QWidget | None = None, parent=None):
        super().__init__(parent)
        self.sender = sender
        self.content = content
        self._fade_animation: QPropertyAnimation | None = None
        self._fade_timer = QTimer(self)
        self._fade_timer.setSingleShot(True)
        self._fade_timer.timeout.connect(self._fade_out)
        self._setup_window()
        self._setup_ui()
        if anchor_widget:
            self.show_above(anchor_widget)
        self._fade_timer.start(6000)

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

    def _setup_ui(self):
        self.setMaximumWidth(self.MAX_WIDTH)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12 + self.TRIANGLE_HEIGHT)
        layout.setSpacing(4)

        sender_label = QLabel(self.sender, self)
        sender_label.setStyleSheet("color: #2B2B2B; font-weight: 700; font-size: 12px; background: transparent;")

        self.content_label = QLabel(self.content, self)
        self.content_label.setWordWrap(True)
        self.content_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.content_label.setStyleSheet("color: #222222; font-size: 14px; line-height: 1.35; background: transparent;")

        layout.addWidget(sender_label)
        layout.addWidget(self.content_label)
        self.adjustSize()

    def update_content(self, content: str) -> None:
        self.content = content
        self.content_label.setText(content)
        self.adjustSize()
        self._fade_timer.start(6000)

    def show_above(self, anchor_widget: QWidget):
        self.adjustSize()
        anchor_top_left = anchor_widget.mapToGlobal(QPoint(0, 0))
        anchor_rect = QRect(anchor_top_left, anchor_widget.size())
        x = anchor_rect.center().x() - self.width() // 2
        y = anchor_rect.top() - self.height() - 8

        screen = QApplication.screenAt(anchor_rect.center()) or QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            x = max(available.left(), min(x, available.right() - self.width()))
            y = max(available.top(), min(y, available.bottom() - self.height()))

        self.move(x, y)
        self.show()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        bubble_rect = self.rect().adjusted(2, 2, -2, -self.TRIANGLE_HEIGHT - 2)
        shadow_rect = bubble_rect.translated(0, 3)

        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(shadow_rect.toRectF(), self.RADIUS, self.RADIUS)
        painter.fillPath(shadow_path, QColor(180, 160, 130, 35))

        bubble_path = QPainterPath()
        bubble_path.addRoundedRect(bubble_rect.toRectF(), self.RADIUS, self.RADIUS)
        painter.fillPath(bubble_path, QColor(247, 243, 223, 245))

        triangle_center = self.width() // 2
        triangle = QPainterPath()
        triangle.moveTo(triangle_center - 9, bubble_rect.bottom())
        triangle.lineTo(triangle_center + 9, bubble_rect.bottom())
        triangle.lineTo(triangle_center, bubble_rect.bottom() + self.TRIANGLE_HEIGHT)
        triangle.closeSubpath()
        painter.fillPath(triangle, QColor(247, 243, 223, 245))

        painter.setPen(QPen(QColor(212, 201, 180, 140), 3))
        painter.drawPath(bubble_path)
        painter.end()

    def _fade_out(self):
        effect = self.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(self)
            self.setGraphicsEffect(effect)
        effect.setOpacity(1.0)

        self._fade_animation = QPropertyAnimation(effect, b"opacity", self)
        self._fade_animation.setDuration(500)
        self._fade_animation.setStartValue(1.0)
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.finished.connect(self.close)
        self._fade_animation.start()
