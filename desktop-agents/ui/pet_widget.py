import math
from dataclasses import replace
from pathlib import Path

from PyQt6.QtCore import QPoint, QRectF, Qt, QEasingCurve, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QFont, QImage, QPainter, QPainterPath, QPen, QBrush, QPixmap
from PyQt6.QtWidgets import QApplication, QInputDialog, QMenu

from config import (
    PROJECT_ROOT,
    PET_BOUNCE_DURATION_MS,
    PET_BOUNCE_OFFSET,
    PET_BREATHE_DURATION_MS,
    PET_BREATHE_MAX_SCALE,
    PET_BREATHE_MIN_SCALE,
    PET_LABEL_HEIGHT,
    PET_SIZE,
    PET_WIDGET_MARGIN,
)
from core.pet import PetConfig, PetMood
from ui.bubble import ChatBubble
from ui.desktop_window import DesktopWindow


MOOD_LABELS = {
    PetMood.NORMAL: "普通",
    PetMood.HAPPY: "开心",
    PetMood.SAD: "难过",
    PetMood.SLEEPY: "困困",
    PetMood.ANGRY: "生气",
    PetMood.SURPRISED: "惊讶",
}


class PetWidget(DesktopWindow):
    clicked = pyqtSignal()
    mood_changed = pyqtSignal(str)
    speak_requested = pyqtSignal(str)
    chat_requested = pyqtSignal(str)
    history_requested = pyqtSignal()
    persona_import_requested = pyqtSignal()
    chat_window_requested = pyqtSignal()
    avatar_change_requested = pyqtSignal()

    def __init__(self, pet_config: PetConfig, parent=None):
        super().__init__(parent)
        self.pet_config = pet_config
        self.mood = PetMood.NORMAL
        self._current_scale = 1.0
        self._bounce_offset = 0.0
        self._motion_phase = 0.0
        self._drag_pos: QPoint | None = None
        self._press_global_pos: QPoint | None = None
        self._drag_moved = False
        self._breathe_forward = True
        self._bubbles: list[ChatBubble] = []
        self._avatar_pixmaps: dict[PetMood, QPixmap] = {}
        self._setup_ui()
        self._load_avatar_pixmaps()
        self._start_breathe_animation()

    def _setup_ui(self) -> None:
        width = PET_SIZE + PET_WIDGET_MARGIN * 2
        height = PET_SIZE + PET_LABEL_HEIGHT + PET_WIDGET_MARGIN * 2
        self.setFixedSize(width, height)
        self.setContentsMargins(PET_WIDGET_MARGIN, PET_WIDGET_MARGIN, PET_WIDGET_MARGIN, PET_WIDGET_MARGIN)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _start_breathe_animation(self) -> None:
        self._breathe_anim = QVariantAnimation(self)
        self._breathe_anim.setStartValue(PET_BREATHE_MIN_SCALE)
        self._breathe_anim.setEndValue(PET_BREATHE_MAX_SCALE)
        self._breathe_anim.setDuration(PET_BREATHE_DURATION_MS)
        self._breathe_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._breathe_anim.valueChanged.connect(self._on_breathe_value_changed)
        self._breathe_anim.finished.connect(self._toggle_breathe_direction)
        self._breathe_anim.start()
        self._motion_anim = QVariantAnimation(self)
        self._motion_anim.setStartValue(0.0)
        self._motion_anim.setEndValue(math.tau)
        self._motion_anim.setDuration(1800)
        self._motion_anim.setLoopCount(-1)
        self._motion_anim.valueChanged.connect(self._on_motion_value_changed)
        self._motion_anim.start()

    def _toggle_breathe_direction(self) -> None:
        self._breathe_forward = not self._breathe_forward
        if self._breathe_forward:
            self._breathe_anim.setStartValue(PET_BREATHE_MIN_SCALE)
            self._breathe_anim.setEndValue(PET_BREATHE_MAX_SCALE)
        else:
            self._breathe_anim.setStartValue(PET_BREATHE_MAX_SCALE)
            self._breathe_anim.setEndValue(PET_BREATHE_MIN_SCALE)
        self._breathe_anim.start()

    def _on_breathe_value_changed(self, value) -> None:
        self._current_scale = float(value)
        self.update()

    def _on_motion_value_changed(self, value) -> None:
        self._motion_phase = float(value)
        self.update()

    def _start_bounce_animation(self) -> None:
        if hasattr(self, "_bounce_anim") and self._bounce_anim.state() == QVariantAnimation.State.Running:
            self._bounce_anim.stop()
        self._bounce_anim = QVariantAnimation(self)
        self._bounce_anim.setStartValue(0.0)
        self._bounce_anim.setKeyValueAt(0.45, -float(PET_BOUNCE_OFFSET))
        self._bounce_anim.setEndValue(0.0)
        self._bounce_anim.setDuration(PET_BOUNCE_DURATION_MS)
        self._bounce_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._bounce_anim.valueChanged.connect(self._on_bounce_value_changed)
        self._bounce_anim.start()

    def _on_bounce_value_changed(self, value) -> None:
        self._bounce_offset = float(value)
        self.update()

    def set_mood(self, mood: PetMood | str, animate: bool = True) -> None:
        self.mood = PetMood(mood)
        self.mood_changed.emit(self.mood.value)
        if animate:
            self._start_bounce_animation()
        self.update()

    def set_avatar_path(self, path: str | Path | None) -> None:
        mood_paths = dict(self.pet_config.mood_avatar_paths)
        if path:
            mood_paths[PetMood.NORMAL.value] = str(path)
        else:
            mood_paths.pop(PetMood.NORMAL.value, None)
        self.pet_config = replace(self.pet_config, avatar_path=str(path) if path else None, mood_avatar_paths=mood_paths)
        self._load_avatar_pixmaps()
        self.update()

    def set_mood_avatar_paths(self, paths: dict[str, str]) -> None:
        cleaned = {PetMood(key).value: value for key, value in paths.items() if value}
        self.pet_config = replace(self.pet_config, avatar_path=cleaned.get(PetMood.NORMAL.value), mood_avatar_paths=cleaned)
        self._load_avatar_pixmaps()
        self.update()

    def show_speech(self, content: str) -> None:
        self.show_chat_bubble(self.pet_config.name, content)

    def show_chat_bubble(self, sender: str, content: str) -> None:
        bubble = ChatBubble(sender, content)
        self._bubbles.append(bubble)
        bubble.destroyed.connect(lambda _=None, item=bubble: self._remove_bubble(item))
        bubble.show_above(self)

    def _remove_bubble(self, bubble: ChatBubble) -> None:
        if bubble in self._bubbles:
            self._bubbles.remove(bubble)

    def _reposition_bubbles(self) -> None:
        for bubble in self._bubbles:
            if bubble.isVisible():
                bubble.show_above(self)

    def _load_avatar_pixmaps(self) -> None:
        self._avatar_pixmaps = {}
        paths = dict(self.pet_config.mood_avatar_paths or {})
        if self.pet_config.avatar_path and PetMood.NORMAL.value not in paths:
            paths[PetMood.NORMAL.value] = self.pet_config.avatar_path
        normal_pixmap = None
        for mood in PetMood:
            path = paths.get(mood.value)
            pixmap = self._load_pixmap(path)
            if pixmap is not None:
                self._avatar_pixmaps[mood] = pixmap
                if mood == PetMood.NORMAL:
                    normal_pixmap = pixmap
        if normal_pixmap is not None:
            for mood in PetMood:
                self._avatar_pixmaps.setdefault(mood, normal_pixmap)

    def _load_pixmap(self, path: str | Path | None) -> QPixmap | None:
        resolved = self._resolve_avatar_path(path)
        if resolved is None:
            return None
        pixmap = QPixmap(str(resolved))
        if pixmap.isNull():
            return None
        pixmap = self._make_edge_white_transparent(pixmap)
        return pixmap.scaled(
            PET_SIZE,
            PET_SIZE,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _make_edge_white_transparent(self, pixmap: QPixmap) -> QPixmap:
        image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        width = image.width()
        height = image.height()
        seen: set[tuple[int, int]] = set()
        stack = [(x, 0) for x in range(width)] + [(x, height - 1) for x in range(width)] + [(0, y) for y in range(height)] + [(width - 1, y) for y in range(height)]
        while stack:
            x, y = stack.pop()
            if (x, y) in seen or x < 0 or y < 0 or x >= width or y >= height:
                continue
            color = QColor(image.pixel(x, y))
            if not self._is_near_white(color):
                continue
            seen.add((x, y))
            color.setAlpha(0)
            image.setPixelColor(x, y, color)
            stack.extend([(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)])
        return QPixmap.fromImage(image)

    def _is_near_white(self, color: QColor) -> bool:
        return color.alpha() > 0 and color.red() >= 245 and color.green() >= 245 and color.blue() >= 245

    def _motion_transform(self) -> tuple[float, float, float]:
        wave = math.sin(self._motion_phase)
        if self.mood == PetMood.HAPPY:
            return 0.0, wave * 2.5, wave * 3.0
        if self.mood == PetMood.SAD:
            return 0.0, 3.0 + abs(wave) * 1.2, -2.0
        if self.mood == PetMood.SLEEPY:
            return wave * 1.2, 2.0, wave * 2.0
        if self.mood == PetMood.ANGRY:
            return math.sin(self._motion_phase * 4) * 2.0, 0.0, math.sin(self._motion_phase * 4) * 2.0
        if self.mood == PetMood.SURPRISED:
            return 0.0, -abs(wave) * 2.0, 0.0
        return 0.0, wave * 0.8, 0.0

    def _resolve_avatar_path(self, path: str | Path | None) -> Path | None:
        if not path:
            return None
        avatar_path = Path(path)
        candidates = [avatar_path] if avatar_path.is_absolute() else [PROJECT_ROOT / avatar_path, avatar_path]
        return next((candidate for candidate in candidates if candidate.exists()), None)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        color = QColor(*self.pet_config.color)
        size = PET_SIZE * self._current_scale
        motion_x, motion_y, rotation = self._motion_transform()
        circle_x = (self.width() - size) / 2 + motion_x
        circle_y = PET_WIDGET_MARGIN + (PET_SIZE - size) / 2 + self._bounce_offset + motion_y
        circle = QRectF(circle_x, circle_y, size, size)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 45)))
        painter.drawEllipse(circle.translated(2, 3))
        avatar = self._avatar_pixmaps.get(self.mood)
        if avatar is not None:
            clip = QPainterPath()
            clip.addEllipse(circle)
            painter.save()
            painter.translate(circle.center())
            painter.rotate(rotation)
            painter.translate(-circle.center())
            painter.setClipPath(clip)
            painter.drawPixmap(circle, avatar, QRectF(avatar.rect()))
            painter.restore()
        else:
            painter.save()
            painter.translate(circle.center())
            painter.rotate(rotation)
            painter.translate(-circle.center())
            painter.setBrush(QBrush(color))
            painter.drawEllipse(circle)
            self._draw_face(painter, circle)
            painter.restore()

        self._draw_name_label(painter)
        painter.end()

    def _draw_face(self, painter: QPainter, circle: QRectF) -> None:
        painter.setPen(QPen(QColor(50, 50, 60), max(2, int(PET_SIZE * 0.04))))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        cx = circle.center().x()
        cy = circle.center().y()
        eye_y = cy - circle.height() * 0.12
        left_x = cx - circle.width() * 0.18
        right_x = cx + circle.width() * 0.18

        if self.mood == PetMood.HAPPY:
            self._draw_arc_eye(painter, left_x, eye_y)
            self._draw_arc_eye(painter, right_x, eye_y)
            painter.drawArc(QRectF(cx - 14, cy - 3, 28, 22), 200 * 16, 140 * 16)
        elif self.mood == PetMood.SAD:
            painter.setBrush(QBrush(QColor(50, 50, 60)))
            painter.drawEllipse(QRectF(left_x - 4, eye_y - 2, 8, 8))
            painter.drawEllipse(QRectF(right_x - 4, eye_y - 2, 8, 8))
            painter.setBrush(QBrush(QColor(90, 170, 255)))
            painter.drawEllipse(QRectF(right_x + 5, eye_y + 5, 5, 8))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(QRectF(cx - 13, cy + 10, 26, 18), 25 * 16, 130 * 16)
        elif self.mood == PetMood.SLEEPY:
            painter.drawLine(int(left_x - 7), int(eye_y), int(left_x + 7), int(eye_y))
            painter.drawLine(int(right_x - 7), int(eye_y), int(right_x + 7), int(eye_y))
            painter.drawLine(int(cx - 6), int(cy + 13), int(cx + 6), int(cy + 13))
        elif self.mood == PetMood.ANGRY:
            painter.drawLine(int(left_x - 8), int(eye_y - 5), int(left_x + 7), int(eye_y + 4))
            painter.drawLine(int(right_x - 7), int(eye_y + 4), int(right_x + 8), int(eye_y - 5))
            painter.drawArc(QRectF(cx - 13, cy + 8, 26, 18), 25 * 16, 130 * 16)
        elif self.mood == PetMood.SURPRISED:
            painter.setBrush(QBrush(QColor(50, 50, 60)))
            painter.drawEllipse(QRectF(left_x - 4, eye_y - 4, 8, 8))
            painter.drawEllipse(QRectF(right_x - 4, eye_y - 4, 8, 8))
            painter.drawEllipse(QRectF(cx - 6, cy + 8, 12, 16))
            painter.setBrush(Qt.BrushStyle.NoBrush)
        else:
            painter.setBrush(QBrush(QColor(50, 50, 60)))
            painter.drawEllipse(QRectF(left_x - 4, eye_y - 4, 8, 8))
            painter.drawEllipse(QRectF(right_x - 4, eye_y - 4, 8, 8))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(QRectF(cx - 12, cy + 2, 24, 16), 200 * 16, 140 * 16)

    def _draw_arc_eye(self, painter: QPainter, x: float, y: float) -> None:
        painter.drawArc(QRectF(x - 8, y - 2, 16, 10), 0, 180 * 16)

    def _draw_name_label(self, painter: QPainter) -> None:
        label_rect = QRectF(0, PET_WIDGET_MARGIN + PET_SIZE + self._bounce_offset, self.width(), PET_LABEL_HEIGHT)
        path = QPainterPath()
        path.addRoundedRect(label_rect.adjusted(8, 2, -8, -2), 8, 8)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 255, 215)))
        painter.drawPath(path)
        painter.setPen(QPen(QColor(55, 55, 65)))
        painter.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        metrics = painter.fontMetrics()
        name = metrics.elidedText(self.pet_config.name, Qt.TextElideMode.ElideRight, int(label_rect.width()) - 18)
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, name)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_global_pos = event.globalPosition().toPoint()
            self._drag_pos = self._press_global_pos - self.frameGeometry().topLeft()
            self._drag_moved = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            if self._drag_pos is not None:
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

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = None
            self._press_global_pos = None
            self._drag_moved = True
            self.chat_window_requested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            should_click = not self._drag_moved
            self._drag_pos = None
            self._press_global_pos = None
            self._drag_moved = False
            if should_click:
                self.set_mood(PetMood.HAPPY)
                self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _show_context_menu(self, pos) -> None:
        menu = QMenu(self)
        greet_action = QAction("打个招呼", self)
        chat_action = QAction("和它说话", self)
        history_action = QAction("聊天记录", self)
        import_action = QAction("导入人格", self)
        avatar_action = QAction("更换形象", self)
        greet_action.triggered.connect(lambda: self.speak_requested.emit("greeting"))
        chat_action.triggered.connect(self._request_chat_input)
        history_action.triggered.connect(self.history_requested.emit)
        import_action.triggered.connect(self.persona_import_requested.emit)
        avatar_action.triggered.connect(self.avatar_change_requested.emit)
        menu.addAction(greet_action)
        menu.addAction(chat_action)
        menu.addAction(history_action)
        menu.addAction(import_action)
        menu.addAction(avatar_action)
        menu.addSeparator()

        mood_menu = menu.addMenu("切换情绪")
        for mood, label in MOOD_LABELS.items():
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(mood == self.mood)
            action.triggered.connect(lambda checked=False, current_mood=mood: self.set_mood(current_mood))
            mood_menu.addAction(action)
        menu.addSeparator()
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(quit_action)
        menu.exec(self.mapToGlobal(pos))

    def _request_chat_input(self) -> None:
        text, ok = QInputDialog.getText(None, f"和{self.pet_config.name}说话", "你想说什么？")
        if ok and text.strip():
            self.chat_requested.emit(text.strip())
