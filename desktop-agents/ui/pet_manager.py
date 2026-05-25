import asyncio
import threading
from collections import deque
from dataclasses import replace

from PyQt6.QtCore import QObject, QPoint, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QPainter, QBrush, QColor, QPen
from PyQt6.QtWidgets import QApplication, QFileDialog, QMenu, QMessageBox, QSystemTrayIcon

from config import CHAT_UI_HISTORY_LIMIT, DEFAULT_AGENT_X, DEFAULT_AGENT_Y, PET_LABEL_HEIGHT, PET_PERSONAS_DIR, PET_SIZE, PET_WIDGET_MARGIN
from core.agent_bus import BusMessage
from core.emotion import EmotionSignal
from core.llm_client import OpenAICompatibleClient
from core.llm_settings import has_api_key, load_llm_settings, settings_to_client_kwargs
from core.pet import PetConfig
from core.pet_companion import PetCompanion, PetResponse
from core.pet import PetMood
from core.pet_persona_importer import safe_persona_slug, save_pet_persona
from core.pet_registry import normalize_pet_config, save_pet_configs
from ui.agent_edit_dialog import AgentEditDialog, IMAGE_FILTER
from ui.agent_management_dialog import AgentManagementDialog
from ui.api_key_dialog import ApiKeyDialog
from ui.batch_persona_import_dialog import BatchPersonaImportDialog
from ui.chat_history_window import ChatHistoryWindow
from ui.pet_chat_window import PetChatWindow
from ui.pet_persona_import_dialog import PetPersonaImportDialog
from ui.pet_widget import PetWidget


class PetManager(QObject):
    reply_ready = pyqtSignal(object, object)
    chat_reply_ready = pyqtSignal(object, object, str)

    def __init__(self, pets: list[PetConfig], parent=None):
        super().__init__(parent)
        self.pets = pets
        self.widgets: list[PetWidget] = []
        self.companions: dict[PetWidget, PetCompanion] = {}
        self.group_history: deque[BusMessage] = deque(maxlen=CHAT_UI_HISTORY_LIMIT)
        self.direct_histories: dict[PetWidget, deque[BusMessage]] = {}
        self.group_history_window = ChatHistoryWindow("群聊记录", "你和 Agent 们，最近 50 条")
        self.direct_history_windows: dict[PetWidget, ChatHistoryWindow] = {}
        self.direct_chat_windows: dict[PetWidget, PetChatWindow] = {}
        self.management_dialog: AgentManagementDialog | None = None
        self._auto_chat_index = 0
        self._auto_chat_timer = QTimer(self)
        self._auto_chat_timer.timeout.connect(self.run_auto_chat_once)
        self.tray_icon: QSystemTrayIcon | None = None
        self.reply_ready.connect(self._show_pet_response)
        self.chat_reply_ready.connect(self._show_chat_response)
        self.group_history_window.clear_requested.connect(self.clear_group_history)

    def create_widgets(self) -> None:
        self.pets = [normalize_pet_config(pet) for pet in self.pets]
        for index, pet in enumerate(self.pets):
            self._create_widget_for_config(pet, index)

    def _create_widget_for_config(self, config: PetConfig, index: int | None = None) -> PetWidget:
        config = normalize_pet_config(config)
        widget = PetWidget(config)
        widget.move(self._position_for_index(index if index is not None else len(self.widgets)))
        companion = PetCompanion(config)
        widget.clicked.connect(lambda current_widget=widget: self._on_pet_clicked(current_widget))
        widget.speak_requested.connect(lambda reason, current_widget=widget: self._on_pet_speak_requested(current_widget, reason))
        widget.chat_requested.connect(lambda text, current_widget=widget: self._on_pet_chat_requested(current_widget, text))
        widget.history_requested.connect(lambda current_widget=widget: self.show_direct_history(current_widget))
        widget.persona_import_requested.connect(lambda current_widget=widget: self.import_persona_for_pet(current_widget))
        widget.avatar_change_requested.connect(lambda current_widget=widget: self.change_avatar_for_pet(current_widget))
        widget.chat_window_requested.connect(lambda current_widget=widget: self.show_pet_chat_window(current_widget))
        self.widgets.append(widget)
        self.companions[widget] = companion
        self.direct_histories[widget] = deque(maxlen=CHAT_UI_HISTORY_LIMIT)
        return widget

    def show_all(self) -> None:
        for widget in self.widgets:
            widget.show()
        self._setup_tray_icon()
        self.start_auto_chat()

    def start_auto_chat(self, interval_ms: int = 8000) -> None:
        if len(self.widgets) >= 2:
            QTimer.singleShot(2500, self.run_auto_chat_once)
            self._auto_chat_timer.start(interval_ms)

    def stop_auto_chat(self) -> None:
        self._auto_chat_timer.stop()

    def run_auto_chat_once(self) -> None:
        if len(self.widgets) < 2:
            return
        speaker = self.widgets[self._auto_chat_index % len(self.widgets)]
        listener = self.widgets[(self._auto_chat_index + 1) % len(self.widgets)]
        self._auto_chat_index += 1
        prompt = self._group_chat_prompt(speaker, listener)
        if has_api_key():
            self._chat_with_llm(speaker, prompt, show_thinking=False, channel="group")
            return
        response = self.companions[speaker].handle_interaction("group_chat", prompt)
        self.chat_reply_ready.emit(speaker, response, "group")
        listener_response = self._propagate_emotion(listener, response)
        QTimer.singleShot(1200, lambda current_listener=listener, current_response=listener_response: self.chat_reply_ready.emit(current_listener, current_response, "group"))

    def close(self) -> None:
        self.stop_auto_chat()
        if self.tray_icon is not None:
            self.tray_icon.hide()
            self.tray_icon = None
        for widget in self.widgets:
            widget.close()
        self.group_history_window.close()
        for window in self.direct_history_windows.values():
            window.close()
        for window in self.direct_chat_windows.values():
            window.close()
        if self.management_dialog is not None:
            self.management_dialog.close()
            self.management_dialog = None
        self.widgets.clear()
        self.companions.clear()
        self.direct_histories.clear()
        self.direct_history_windows.clear()
        self.direct_chat_windows.clear()

    def _setup_tray_icon(self) -> None:
        if self.tray_icon is not None:
            return
        self.tray_icon = QSystemTrayIcon(QIcon(self._create_tray_pixmap()), self)
        self.tray_icon.setToolTip("桌面萌宠")
        menu = QMenu()
        api_key_action = QAction("API Key 设置", self)
        management_action = QAction("Agent 管理", self)
        history_action = QAction("群聊记录", self)
        batch_import_action = QAction("批量导入人格", self)
        show_action = QAction("显示萌宠", self)
        hide_action = QAction("隐藏萌宠", self)
        quit_action = QAction("退出", self)
        api_key_action.triggered.connect(self.show_api_key_settings)
        management_action.triggered.connect(self.show_agent_management)
        history_action.triggered.connect(self.show_group_history)
        batch_import_action.triggered.connect(self.import_personas_from_folder)
        show_action.triggered.connect(lambda: [widget.show() for widget in self.widgets])
        hide_action.triggered.connect(lambda: [widget.hide() for widget in self.widgets])
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(api_key_action)
        menu.addAction(management_action)
        menu.addAction(history_action)
        menu.addAction(batch_import_action)
        menu.addSeparator()
        menu.addAction(show_action)
        menu.addAction(hide_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()

    def _create_tray_pixmap(self):
        from PyQt6.QtGui import QPixmap
        pixmap = QPixmap(64, 64)
        pixmap.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(255, 141, 161)))
        painter.drawEllipse(4, 4, 56, 56)
        painter.setPen(QPen(QColor(255, 255, 255), 4))
        painter.drawArc(18, 22, 28, 22, 200 * 16, 140 * 16)
        painter.end()
        return pixmap

    def show_api_key_settings(self) -> None:
        dialog = ApiKeyDialog(first_run=False)
        dialog.exec()

    def import_personas_from_folder(self) -> None:
        dialog = BatchPersonaImportDialog(PET_PERSONAS_DIR)
        dialog.exec()

    def add_pet(self, config: PetConfig) -> PetWidget:
        config = normalize_pet_config(config)
        self.pets.append(config)
        widget = self._create_widget_for_config(config)
        widget.show()
        self.save_current_configs()
        self._refresh_management_dialog()
        if len(self.widgets) >= 2 and not self._auto_chat_timer.isActive():
            self.start_auto_chat()
        return widget

    def remove_pet(self, widget_or_agent_id) -> None:
        widget = self._widget_for(widget_or_agent_id)
        if widget is None:
            return
        self.pets = [pet for pet in self.pets if pet.identity != widget.pet_config.identity]
        self.widgets.remove(widget)
        self.companions.pop(widget, None)
        self.direct_histories.pop(widget, None)
        for mapping in [self.direct_history_windows, self.direct_chat_windows]:
            window = mapping.pop(widget, None)
            if window is not None:
                window.close()
        widget.close()
        if len(self.widgets) < 2:
            self.stop_auto_chat()
        self.save_current_configs()
        self._refresh_management_dialog()

    def update_pet_config(self, widget: PetWidget, config: PetConfig) -> None:
        if widget not in self.widgets:
            return
        config = normalize_pet_config(config)
        widget.pet_config = config
        widget._load_avatar_pixmaps()
        companion = self.companions[widget]
        companion.pet_config = config
        self.pets = [config if pet.identity == config.identity else pet for pet in self.pets]
        chat_window = self.direct_chat_windows.get(widget)
        if chat_window is not None:
            chat_window.set_agent_name(config.name)
        history_window = self.direct_history_windows.get(widget)
        if history_window is not None:
            history_window.setWindowTitle(f"和{config.name}的聊天记录")
        widget.update()
        self.save_current_configs()
        self._refresh_management_dialog()

    def save_current_configs(self) -> None:
        save_pet_configs([widget.pet_config for widget in self.widgets])

    def show_agent_management(self) -> None:
        if self.management_dialog is None:
            self.management_dialog = AgentManagementDialog([widget.pet_config for widget in self.widgets])
            self.management_dialog.add_requested.connect(self._add_agent_from_dialog)
            self.management_dialog.edit_requested.connect(self._edit_agent_from_dialog)
            self.management_dialog.delete_requested.connect(self._delete_agent_from_dialog)
            self.management_dialog.import_requested.connect(lambda agent_id: self.import_persona_for_pet(self._widget_for(agent_id)))
            self.management_dialog.avatar_requested.connect(lambda agent_id: self.change_avatar_for_pet(self._widget_for(agent_id)))
            self.management_dialog.chat_requested.connect(lambda agent_id: self.show_pet_chat_window(self._widget_for(agent_id)))
        self._refresh_management_dialog()
        self.management_dialog.show()
        self.management_dialog.raise_()
        self.management_dialog.activateWindow()

    def change_avatar_for_pet(self, widget: PetWidget | None) -> None:
        if widget is None or widget not in self.widgets:
            return
        path, _ = QFileDialog.getOpenFileName(None, f"更换{widget.pet_config.name}的正常形象", "", IMAGE_FILTER)
        if not path:
            return
        mood_paths = dict(widget.pet_config.mood_avatar_paths or {})
        mood_paths[PetMood.NORMAL.value] = path
        self.update_pet_config(widget, replace(widget.pet_config, avatar_path=path, mood_avatar_paths=mood_paths))

    def _add_agent_from_dialog(self) -> None:
        dialog = AgentEditDialog()
        if dialog.exec() != AgentEditDialog.DialogCode.Accepted or dialog.config is None:
            return
        widget = self.add_pet(dialog.config)
        if dialog.import_after_create:
            self.import_persona_for_pet(widget)

    def _edit_agent_from_dialog(self, agent_id: str) -> None:
        widget = self._widget_for(agent_id)
        if widget is None:
            return
        dialog = AgentEditDialog(widget.pet_config)
        if dialog.exec() == AgentEditDialog.DialogCode.Accepted and dialog.config is not None:
            self.update_pet_config(widget, dialog.config)

    def _delete_agent_from_dialog(self, agent_id: str) -> None:
        widget = self._widget_for(agent_id)
        if widget is None:
            return
        if QMessageBox.question(None, "删除 Agent", f"确定删除 {widget.pet_config.name} 吗？") != QMessageBox.StandardButton.Yes:
            return
        self.remove_pet(widget)

    def _refresh_management_dialog(self) -> None:
        if self.management_dialog is not None:
            self.management_dialog.load_configs([widget.pet_config for widget in self.widgets])

    def _widget_for(self, widget_or_agent_id) -> PetWidget | None:
        if isinstance(widget_or_agent_id, PetWidget):
            return widget_or_agent_id if widget_or_agent_id in self.widgets else None
        agent_id = str(widget_or_agent_id)
        return next((widget for widget in self.widgets if widget.pet_config.identity == agent_id), None)

    def import_persona_for_pet(self, widget: PetWidget | None) -> None:
        if widget is None or widget not in self.widgets:
            return
        dialog = PetPersonaImportDialog(widget.pet_config.name, widget.pet_config.type_id)
        if dialog.exec() != PetPersonaImportDialog.DialogCode.Accepted or dialog.profile is None:
            return
        profile = dialog.profile
        output_path = PET_PERSONAS_DIR / safe_persona_slug(profile.name or widget.pet_config.name) / "persona.json"
        saved_path = save_pet_persona(profile, output_path)
        companion = self.companions[widget]
        companion.apply_profile(profile)
        updated_config = replace(
            widget.pet_config,
            name=profile.name or widget.pet_config.name,
            personality_tag=profile.personality_tag,
            persona_path=str(saved_path),
        )
        self.update_pet_config(widget, updated_config)
        response = companion.handle_interaction("greeting")
        self._show_chat_response(widget, response, "direct")

    def _on_pet_clicked(self, widget: PetWidget) -> None:
        self._reply_locally(widget, "click", channel="direct")

    def _on_pet_speak_requested(self, widget: PetWidget, reason: str) -> None:
        self._reply_locally(widget, reason, channel="direct")

    def _on_pet_chat_requested(self, widget: PetWidget, text: str) -> None:
        self._append_direct_message(widget, BusMessage(sender="你", content=text, kind="user", anchor_agent_id=widget.pet_config.identity))
        if has_api_key():
            self._chat_with_llm(widget, text, channel="direct")
            return
        companion = self.companions[widget]
        self.chat_reply_ready.emit(widget, companion.handle_interaction("chat", text), "direct")

    def _reply_locally(self, widget: PetWidget, event_type: str, channel: str = "direct") -> None:
        companion = self.companions[widget]
        self.chat_reply_ready.emit(widget, companion.handle_interaction(event_type), channel)

    def _chat_with_llm(self, widget: PetWidget, text: str, show_thinking: bool = True, channel: str = "direct") -> None:
        companion = self.companions[widget]
        preview = companion.emotion_engine.analyze(
            signal=EmotionSignal("chat", text),
            current=companion.emotion_state,
            personality_tag=companion.profile.personality_tag,
        )
        companion.emotion_state = preview
        widget.set_mood(preview.mood)
        if show_thinking:
            widget.show_speech("我想想怎么说……")

        def runner() -> None:
            client = OpenAICompatibleClient(**settings_to_client_kwargs(load_llm_settings()))
            try:
                response = asyncio.run(companion.chat(text, client=client))
            finally:
                asyncio.run(client.close())
            self.chat_reply_ready.emit(widget, response, channel)

        threading.Thread(target=runner, daemon=True).start()

    def _show_pet_response(self, widget: PetWidget, response: PetResponse) -> None:
        if widget not in self.widgets:
            return
        widget.set_mood(response.mood)
        widget.show_speech(response.text)

    def _show_chat_response(self, widget: PetWidget, response: PetResponse, channel: str) -> None:
        if widget not in self.widgets:
            return
        self._show_pet_response(widget, response)
        message = BusMessage(sender=widget.pet_config.name, content=response.text, kind="agent", agent_id=widget.pet_config.identity, anchor_agent_id=widget.pet_config.identity)
        if channel == "group":
            self._append_group_message(message)
        else:
            self._append_direct_message(widget, message)

    def _append_group_message(self, message: BusMessage) -> None:
        self.group_history.append(message)
        if self.group_history_window.isVisible():
            self.group_history_window.load_messages(list(self.group_history))

    def _append_direct_message(self, widget: PetWidget, message: BusMessage) -> None:
        history = self.direct_histories.setdefault(widget, deque(maxlen=CHAT_UI_HISTORY_LIMIT))
        history.append(message)
        window = self.direct_history_windows.get(widget)
        if window is not None and window.isVisible():
            window.load_messages(list(history))
        chat_window = self.direct_chat_windows.get(widget)
        if chat_window is not None and chat_window.isVisible():
            chat_window.load_messages(list(history))

    def show_group_history(self) -> None:
        self.group_history_window.load_messages(list(self.group_history))
        self.group_history_window.show()
        self.group_history_window.raise_()
        self.group_history_window.activateWindow()

    def show_pet_chat_window(self, widget: PetWidget) -> None:
        window = self.direct_chat_windows.get(widget)
        if window is None:
            window = PetChatWindow(widget.pet_config.name)
            window.message_submitted.connect(lambda text, current_widget=widget: self._on_pet_chat_requested(current_widget, text))
            self.direct_chat_windows[widget] = window
        window.load_messages(list(self.direct_histories.get(widget, [])))
        window.show()
        window.raise_()
        window.activateWindow()

    def show_direct_history(self, widget: PetWidget) -> None:
        window = self.direct_history_windows.get(widget)
        if window is None:
            window = ChatHistoryWindow(f"和{widget.pet_config.name}的聊天记录", "你和这个 Agent，最近 50 条")
            window.clear_requested.connect(lambda current_widget=widget: self._clear_direct_history(current_widget))
            self.direct_history_windows[widget] = window
        window.load_messages(list(self.direct_histories.get(widget, [])))
        window.show()
        window.raise_()
        window.activateWindow()

    def clear_group_history(self) -> None:
        self.group_history.clear()
        self.group_history_window.clear_messages()

    def _clear_direct_history(self, widget: PetWidget) -> None:
        self.direct_histories.setdefault(widget, deque(maxlen=CHAT_UI_HISTORY_LIMIT)).clear()
        window = self.direct_history_windows.get(widget)
        if window is not None:
            window.clear_messages()

    def _propagate_emotion(self, widget: PetWidget, response: PetResponse) -> PetResponse:
        companion = self.companions[widget]
        propagated = companion.handle_interaction("chat", response.text)
        widget.set_mood(propagated.mood)
        return propagated

    def _group_chat_prompt(self, speaker: PetWidget, listener: PetWidget) -> str:
        transcript = self._format_group_transcript()
        speaker_name = speaker.pet_config.name
        listener_name = listener.pet_config.name
        base = [
            f"你现在是 {speaker_name}，正在和桌面小组里的其他 Agent 聊天。",
            f"当前要接话的人是 {listener_name}。",
        ]
        if transcript:
            base.append("最近的群聊记录：")
            base.append(transcript)
        base.extend([
            "要求：",
            "- 优先自然接上上一句，但如果不合适，也可以轻轻换一个相关话题",
            "- 可以承接最近的话题，或者顺着气氛补一句",
            "- 只输出你的发言内容，不要加姓名前缀",
            "- 1到2句话，中文",
        ])
        return "\n".join(base)

    def _format_group_transcript(self, limit: int = 6) -> str:
        messages = list(self.group_history)[-limit:]
        return "\n".join(f"{message.sender}: {message.content}" for message in messages)

    def _position_for_index(self, index: int) -> QPoint:
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else QRect(0, 0, 1200, 800)
        widget_width = PET_SIZE + PET_WIDGET_MARGIN * 2
        widget_height = PET_SIZE + PET_LABEL_HEIGHT + PET_WIDGET_MARGIN * 2
        spacing = widget_width + 50
        start_x = max(available.left(), min(DEFAULT_AGENT_X, available.right() - widget_width))
        start_y = max(available.top(), min(DEFAULT_AGENT_Y, available.bottom() - widget_height))
        max_columns = max(1, (available.right() - start_x + 1) // spacing)

        row = index // max_columns
        col = index % max_columns
        x = start_x + col * spacing
        y = start_y + row * spacing

        if x + widget_width > available.right():
            x = max(available.left(), available.right() - widget_width)
        if y + widget_height > available.bottom():
            y = max(available.top(), available.bottom() - widget_height)
        return QPoint(x, y)
