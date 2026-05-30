import asyncio
import threading
import time
from collections import deque
from dataclasses import replace
from datetime import datetime

from PyQt6.QtCore import QObject, QPoint, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup, QIcon, QPainter, QBrush, QColor, QPen
from PyQt6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMenu, QMessageBox, QSystemTrayIcon

from config import (
    CHAT_UI_HISTORY_LIMIT,
    DEFAULT_AGENT_X,
    DEFAULT_AGENT_Y,
    MAX_DESKTOP_AGENTS,
    MEMORY_RECALL_INTERVAL_MS,
    MEMORY_RECALL_STARTUP_DELAY_MS,
    MIN_DESKTOP_AGENTS,
    PET_CHAT_HISTORY_LIMIT,
    PET_LABEL_HEIGHT,
    PET_PERSONAS_DIR,
    PET_SIZE,
    PET_WIDGET_MARGIN,
)
from core.agent_bus import BusMessage
from core.chat_storage import ChatStorage
from core.emotion import EmotionSignal
from core.explicit_memory import ExplicitMemoryStore
from core.llm_settings import has_api_key
from core.pet import PetConfig
from core.pet_companion import PetCompanion, PetResponse
from core.pet import PetMood
from core.personality_rhythm import get_chat_interval, get_rhythm, get_thinking_time, get_typing_delay
from core.personality_trainer import PersonalityProfile, PersonalityTrainer
from core.reply_router import ReplyRequest, ReplyRouter
from core.pet_persona_importer import PersonaPackageMetadata, safe_persona_slug, save_pet_persona_package
from core.pet_registry import normalize_pet_config, save_pet_configs
from ui.agent_edit_dialog import AgentEditDialog, IMAGE_FILTER
from ui.agent_management_dialog import AgentManagementDialog
from ui.api_key_dialog import ApiKeyDialog
from ui.batch_persona_import_dialog import BatchPersonaImportDialog
from ui.chat_history_window import ChatHistoryWindow
from ui.pet_chat_window import PetChatWindow
from ui.pet_persona_import_dialog import PetPersonaImportDialog
from ui.pet_widget import PetWidget
from ui.persona_library_dialog import PersonaLibraryDialog


class PetManager(QObject):
    reply_ready = pyqtSignal(object, object)
    chat_reply_ready = pyqtSignal(object, object, str)
    chat_reply_stream_started = pyqtSignal(object, str)
    chat_reply_stream_delta = pyqtSignal(object, str, str)
    chat_reply_stream_finished = pyqtSignal(object, object, str)

    def __init__(self, pets: list[PetConfig], parent=None, chat_storage: ChatStorage | None = None, explicit_memory: ExplicitMemoryStore | None = None, reply_router: ReplyRouter | None = None):
        super().__init__(parent)
        self.pets = pets
        self.chat_storage = chat_storage
        self.explicit_memory = explicit_memory
        self.reply_router = reply_router or ReplyRouter(api_key_available=lambda: has_api_key())
        self.widgets: list[PetWidget] = []
        self.companions: dict[PetWidget, PetCompanion] = {}
        self.group_history: deque[BusMessage] = deque(maxlen=CHAT_UI_HISTORY_LIMIT)
        self.direct_histories: dict[PetWidget, deque[BusMessage]] = {}
        self.group_history_window = ChatHistoryWindow("群聊记录", "你和 Agent 们，最近 50 条", input_enabled=True, input_placeholder="加入群聊，说点什么...")
        self.direct_history_windows: dict[PetWidget, ChatHistoryWindow] = {}
        self.direct_chat_windows: dict[PetWidget, PetChatWindow] = {}
        self.management_dialog: AgentManagementDialog | None = None
        self._auto_chat_index = 0
        self._auto_chat_timer = QTimer(self)
        self._auto_chat_timer.timeout.connect(self.run_auto_chat_once)
        self._auto_chat_paused_by_user = False
        self._auto_chat_interval_override_ms: int | None = None
        self._auto_chat_pause_action: QAction | None = None
        self._auto_chat_interval_actions: dict[int | None, QAction] = {}
        self._memory_recall_index = 0
        self._memory_recall_timer = QTimer(self)
        self._memory_recall_timer.timeout.connect(self.run_memory_recall_once)
        self._typewriter_states: dict[tuple[PetWidget, str], dict] = {}
        self.tray_icon: QSystemTrayIcon | None = None
        self.reply_ready.connect(self._show_pet_response)
        self.chat_reply_ready.connect(self._show_chat_response)
        self.chat_reply_stream_started.connect(self._start_streaming_chat_response)
        self.chat_reply_stream_delta.connect(self._update_streaming_chat_response)
        self.chat_reply_stream_finished.connect(self._finish_streaming_chat_response)
        self.group_history_window.clear_requested.connect(self.clear_group_history)
        self.group_history_window.message_submitted.connect(self._on_group_chat_submitted)

    def create_widgets(self) -> None:
        self.pets = self._normalized_roster(self.pets)
        for index, pet in enumerate([pet for pet in self.pets if pet.deployed]):
            self._create_widget_for_config(pet, index)
        self._load_persisted_histories()

    def _normalized_roster(self, configs: list[PetConfig]) -> list[PetConfig]:
        normalized = [normalize_pet_config(pet) for pet in configs]
        deployed_count = 0
        roster = []
        for index, pet in enumerate(normalized):
            deployed = pet.deployed
            if index == 0 and not any(item.deployed for item in normalized):
                deployed = True
            if deployed and deployed_count >= MAX_DESKTOP_AGENTS:
                deployed = False
            if deployed:
                deployed_count += 1
            roster.append(replace(pet, deployed=deployed))
        return roster

    def _deployed_count(self) -> int:
        return sum(1 for pet in self.pets if pet.deployed)

    def _create_widget_for_config(self, config: PetConfig, index: int | None = None) -> PetWidget:
        config = normalize_pet_config(config)
        widget = PetWidget(config)
        widget.move(self._position_for_index(index if index is not None else len(self.widgets)))
        companion = PetCompanion(config, profile=self._load_persona_profile(config))
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

    def _load_persona_profile(self, config: PetConfig) -> PersonalityProfile | None:
        if not config.persona_path:
            return None
        try:
            return PersonalityTrainer.load(config.persona_path)
        except (OSError, ValueError, TypeError):
            return None

    def _load_persisted_histories(self) -> None:
        if self.chat_storage is None:
            return
        self.group_history.clear()
        self.group_history.extend(self.chat_storage.load_recent_messages("group", limit=CHAT_UI_HISTORY_LIMIT))
        for widget in self.widgets:
            self._load_persisted_direct_history(widget)

    def _load_persisted_direct_history(self, widget: PetWidget) -> None:
        if self.chat_storage is None:
            return
        history = self.direct_histories.setdefault(widget, deque(maxlen=CHAT_UI_HISTORY_LIMIT))
        history.clear()
        history.extend(self.chat_storage.load_recent_messages("direct", widget.pet_config.identity, limit=CHAT_UI_HISTORY_LIMIT))
        self._hydrate_companion_history(widget)

    def _hydrate_companion_history(self, widget: PetWidget) -> None:
        companion = self.companions.get(widget)
        if companion is None:
            return
        messages: list[dict[str, str]] = []
        for message in self.direct_histories.get(widget, []):
            if message.kind == "user":
                messages.append({"role": "user", "content": message.content})
            elif message.kind == "agent":
                messages.append({"role": "assistant", "content": message.content})
        companion.history = messages[-PET_CHAT_HISTORY_LIMIT:]

    def show_all(self) -> None:
        for widget in self.widgets:
            widget.show()
        self._setup_tray_icon()
        self.start_auto_chat()
        if self.explicit_memory is not None:
            QTimer.singleShot(MEMORY_RECALL_STARTUP_DELAY_MS, self.run_memory_recall_once)
            self._memory_recall_timer.start(MEMORY_RECALL_INTERVAL_MS)

    def start_auto_chat(self, interval_ms: int | None = None) -> None:
        if self._auto_chat_paused_by_user or len(self.widgets) < 2:
            return
        QTimer.singleShot(2500, self.run_auto_chat_once)
        self._auto_chat_timer.start(interval_ms or self._current_auto_chat_interval())
        self._refresh_auto_chat_tray_actions()

    def stop_auto_chat(self) -> None:
        self._auto_chat_timer.stop()
        self._refresh_auto_chat_tray_actions()

    def pause_auto_chat(self) -> None:
        self._auto_chat_paused_by_user = True
        self.stop_auto_chat()

    def resume_auto_chat(self) -> None:
        self._auto_chat_paused_by_user = False
        self.start_auto_chat()
        self._refresh_auto_chat_tray_actions()

    def _toggle_auto_chat_paused(self) -> None:
        if self._auto_chat_paused_by_user:
            self.resume_auto_chat()
        else:
            self.pause_auto_chat()

    def set_auto_chat_interval_override(self, interval_ms: int | None) -> None:
        self._auto_chat_interval_override_ms = interval_ms
        if not self._auto_chat_paused_by_user and len(self.widgets) >= 2:
            self._auto_chat_timer.start(self._current_auto_chat_interval())
        self._refresh_auto_chat_tray_actions()

    def _refresh_auto_chat_tray_actions(self) -> None:
        if self._auto_chat_pause_action is not None:
            self._auto_chat_pause_action.setText("恢复自动群聊" if self._auto_chat_paused_by_user else "暂停自动群聊")
        for interval_ms, action in self._auto_chat_interval_actions.items():
            action.setChecked(interval_ms == self._auto_chat_interval_override_ms)

    def _is_nighttime(self, now: datetime | None = None) -> bool:
        hour = (now or datetime.now()).hour
        return hour >= 22 or hour < 8

    def _effective_auto_chat_interval(self, base_ms: int) -> int:
        return base_ms * 3 if self._is_nighttime() else base_ms

    def _current_auto_chat_interval(self) -> int:
        base_ms = self._auto_chat_interval_override_ms or self._next_auto_chat_interval()
        return self._effective_auto_chat_interval(base_ms)

    def _next_auto_chat_interval(self) -> int:
        if not self.widgets:
            return get_chat_interval(None)
        speaker = self.widgets[self._auto_chat_index % len(self.widgets)]
        companion = self.companions.get(speaker)
        return get_chat_interval(companion.profile.personality_tag if companion is not None else None)

    def _nighttime_response(self, response: PetResponse) -> PetResponse:
        if not self._is_nighttime():
            return response
        return replace(response, mood=PetMood.SLEEPY)

    def run_auto_chat_once(self) -> None:
        if self._auto_chat_paused_by_user or len(self.widgets) < 2:
            return
        speaker = self.widgets[self._auto_chat_index % len(self.widgets)]
        listener = self.widgets[(self._auto_chat_index + 1) % len(self.widgets)]
        self._auto_chat_index += 1
        if self._auto_chat_timer.isActive():
            self._auto_chat_timer.setInterval(self._current_auto_chat_interval())
        prompt = self._group_chat_prompt(speaker, listener)
        request = self._reply_request(speaker, prompt, "group_chat", "group")
        if self.reply_router.decide(request).route == "cloud":
            self._chat_with_llm(speaker, prompt, show_thinking=False, channel="group", sleepy_at_night=True)
            return
        response = self._nighttime_response(asyncio.run(self.reply_router.local_backend.reply(request)))
        self.chat_reply_ready.emit(speaker, response, "group")
        listener_response = self._nighttime_response(self._propagate_emotion(listener, response))
        QTimer.singleShot(1200, lambda current_listener=listener, current_response=listener_response: self.chat_reply_ready.emit(current_listener, current_response, "group"))

    def close(self) -> None:
        self.stop_auto_chat()
        self._memory_recall_timer.stop()
        for state in self._typewriter_states.values():
            state["timer"].stop()
        self._typewriter_states.clear()
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
        self._auto_chat_pause_action = QAction("暂停自动群聊", self)
        interval_menu = QMenu("群聊间隔", menu)
        interval_group = QActionGroup(self)
        interval_group.setExclusive(True)
        self._auto_chat_interval_actions = {}
        for label, interval_ms in [("按 Agent 节奏", None), ("每 15 秒", 15_000), ("每 30 秒", 30_000), ("每 60 秒", 60_000)]:
            action = QAction(label, self)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, current_interval=interval_ms: self.set_auto_chat_interval_override(current_interval))
            interval_group.addAction(action)
            interval_menu.addAction(action)
            self._auto_chat_interval_actions[interval_ms] = action
        show_action = QAction("显示萌宠", self)
        hide_action = QAction("隐藏萌宠", self)
        quit_action = QAction("退出", self)
        library_action = QAction("人格库", self)
        library_action.triggered.connect(self.show_persona_library)
        api_key_action.triggered.connect(self.show_api_key_settings)
        management_action.triggered.connect(self.show_agent_management)
        history_action.triggered.connect(self.show_group_history)
        self._auto_chat_pause_action.triggered.connect(self._toggle_auto_chat_paused)
        show_action.triggered.connect(lambda: [widget.show() for widget in self.widgets])
        hide_action.triggered.connect(lambda: [widget.hide() for widget in self.widgets])
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(api_key_action)
        menu.addAction(management_action)
        menu.addAction(library_action)
        menu.addAction(history_action)
        menu.addSeparator()
        menu.addAction(self._auto_chat_pause_action)
        menu.addMenu(interval_menu)
        menu.addSeparator()
        menu.addAction(show_action)
        menu.addAction(hide_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self._refresh_auto_chat_tray_actions()
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()

    def _create_tray_pixmap(self):
        from PyQt6.QtGui import QPixmap
        from config import ICON_PATH
        from ui.theme import _rounded_pixmap

        if ICON_PATH.exists():
            pixmap = QPixmap(str(ICON_PATH))
            if not pixmap.isNull():
                return _rounded_pixmap(pixmap, 64, 14)
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

    def show_persona_library(self) -> None:
        dialog = PersonaLibraryDialog()
        dialog.bind_requested.connect(lambda path: self._bind_persona_from_library(path))
        dialog.batch_import_requested.connect(self._do_batch_import_from_library)
        dialog.exec()

    def _do_batch_import_from_library(self) -> None:
        batch_dialog = BatchPersonaImportDialog(PET_PERSONAS_DIR)
        batch_dialog.exec()
        self.show_persona_library()

    def _bind_persona_from_library(self, persona_path: str) -> None:
        if not self.pets:
            QMessageBox.information(None, "没有 Agent", "当前没有 Agent 可以绑定人格。")
            return
        names = [pet.name for pet in self.pets]
        name, ok = QInputDialog.getItem(None, "绑定人格", "选择要绑定的 Agent：", names, 0, False)
        if not ok or not name:
            return
        config = next((pet for pet in self.pets if pet.name == name), None)
        if config is None:
            return
        try:
            profile = PersonalityTrainer().load(persona_path)
        except (OSError, ValueError, TypeError):
            QMessageBox.warning(None, "加载失败", "无法加载该人格包。")
            return
        updated_config = replace(
            config,
            name=profile.name or config.name,
            personality_tag=profile.personality_tag or config.personality_tag,
            persona_path=persona_path,
        )
        self.update_pet_config(config.identity, updated_config)
        widget = self._widget_for(config.identity)
        if widget is not None:
            companion = self.companions[widget]
            companion.apply_profile(profile)
            response = companion.handle_interaction("greeting")
            self._show_chat_response(widget, response, "direct")
        self._refresh_management_dialog()
        QMessageBox.information(None, "绑定成功", f"已将人格“{profile.name}”绑定到 {updated_config.name}。")

    def reset_persona_for_pet(self, widget_or_agent_id) -> None:
        agent_id = self._agent_id_for(widget_or_agent_id)
        config = self._pet_config_for(agent_id)
        if config is None or not config.persona_path:
            QMessageBox.information(None, "无需重置", "这个 Agent 当前没有导入人格。")
            return
        if QMessageBox.question(None, "重置人格", f"确定解除 {config.name} 的导入人格绑定吗？人格包文件不会被删除。") != QMessageBox.StandardButton.Yes:
            return
        updated_config = replace(config, persona_path=None)
        self.update_pet_config(agent_id, updated_config)
        widget = self._widget_for(agent_id)
        if widget is not None:
            companion = self.companions[widget]
            default_profile = PersonalityTrainer()._default_profile(updated_config.name, updated_config.type_id)
            if default_profile.personality_tag != updated_config.personality_tag:
                default_profile.personality_tag = updated_config.personality_tag
                default_profile.system_prompt = PersonalityTrainer()._build_system_prompt(
                    updated_config.name,
                    updated_config.type_id,
                    updated_config.personality_tag,
                    default_profile.catchphrases,
                    default_profile.emoji_habits,
                    default_profile.topics,
                    default_profile.greeting_style,
                    default_profile.avg_sentence_length,
                )
            companion.apply_profile(default_profile)

    def add_pet(self, config: PetConfig) -> PetWidget | None:
        deployed = self._deployed_count() < MAX_DESKTOP_AGENTS
        config = normalize_pet_config(replace(config, deployed=deployed))
        self.pets.append(config)
        widget = None
        if config.deployed:
            widget = self._create_widget_for_config(config)
            self._load_persisted_direct_history(widget)
            widget.show()
        self.save_current_configs()
        self._refresh_management_dialog()
        if len(self.widgets) >= 2 and not self._auto_chat_timer.isActive():
            self.start_auto_chat()
        if not config.deployed:
            QMessageBox.information(None, "已加入候补", f"桌面最多同时出战 {MAX_DESKTOP_AGENTS} 个 Agent，新 Agent 已保存但未出现在桌面。")
        return widget

    def remove_pet(self, widget_or_agent_id) -> None:
        agent_id = self._agent_id_for(widget_or_agent_id)
        if agent_id is None:
            return
        if len(self.pets) <= MIN_DESKTOP_AGENTS:
            QMessageBox.information(None, "至少保留一个 Agent", f"Agent 档案至少需要保留 {MIN_DESKTOP_AGENTS} 个。")
            return
        self.pets = [pet for pet in self.pets if pet.identity != agent_id]
        widget = self._widget_for(agent_id)
        if widget is not None:
            self._remove_widget(widget)
        if self._deployed_count() == 0 and self.pets:
            self.pets[0] = replace(self.pets[0], deployed=True)
            self._create_widget_for_config(self.pets[0]).show()
        if len(self.widgets) < 2:
            self.stop_auto_chat()
        self.save_current_configs()
        self._refresh_management_dialog()

    def _remove_widget(self, widget: PetWidget) -> None:
        if widget in self.widgets:
            self.widgets.remove(widget)
        self.companions.pop(widget, None)
        self.direct_histories.pop(widget, None)
        for mapping in [self.direct_history_windows, self.direct_chat_windows]:
            window = mapping.pop(widget, None)
            if window is not None:
                window.close()
        widget.close()

    def update_pet_config(self, widget_or_agent_id, config: PetConfig) -> None:
        agent_id = self._agent_id_for(widget_or_agent_id)
        if agent_id is None:
            return
        existing = self._pet_config_for(agent_id)
        if existing is None:
            return
        config = normalize_pet_config(replace(config, agent_id=existing.identity, deployed=existing.deployed))
        self.pets = [config if pet.identity == agent_id else pet for pet in self.pets]
        widget = self._widget_for(agent_id)
        if widget is not None:
            widget.pet_config = config
            widget._load_avatar_pixmaps()
            companion = self.companions[widget]
            companion.pet_config = config
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
        save_pet_configs(self.pets)

    def show_agent_management(self) -> None:
        if self.management_dialog is None:
            self.management_dialog = AgentManagementDialog(self.pets)
            self.management_dialog.add_requested.connect(self._add_agent_from_dialog)
            self.management_dialog.edit_requested.connect(self._edit_agent_from_dialog)
            self.management_dialog.delete_requested.connect(self._delete_agent_from_dialog)
            self.management_dialog.import_requested.connect(self.import_persona_for_pet)
            self.management_dialog.reset_persona_requested.connect(self.reset_persona_for_pet)
            self.management_dialog.avatar_requested.connect(self.change_avatar_for_pet)
            self.management_dialog.chat_requested.connect(self._open_chat_from_management)
            self.management_dialog.deployed_changed.connect(self.set_agent_deployed)
            self.management_dialog.persona_library_requested.connect(self.show_persona_library)
        self._refresh_management_dialog()
        self.management_dialog.show()
        self.management_dialog.raise_()
        self.management_dialog.activateWindow()

    def change_avatar_for_pet(self, widget_or_agent_id) -> None:
        agent_id = self._agent_id_for(widget_or_agent_id)
        config = self._pet_config_for(agent_id) if agent_id is not None else None
        if config is None:
            return
        path, _ = QFileDialog.getOpenFileName(None, f"更换{config.name}的正常形象", "", IMAGE_FILTER)
        if not path:
            return
        mood_paths = dict(config.mood_avatar_paths or {})
        mood_paths[PetMood.NORMAL.value] = path
        self.update_pet_config(agent_id, replace(config, avatar_path=path, mood_avatar_paths=mood_paths))

    def _add_agent_from_dialog(self) -> None:
        dialog = AgentEditDialog()
        if dialog.exec() != AgentEditDialog.DialogCode.Accepted or dialog.config is None:
            return
        widget = self.add_pet(dialog.config)
        if widget is not None and dialog.import_after_create:
            self.import_persona_for_pet(widget)

    def _edit_agent_from_dialog(self, agent_id: str) -> None:
        config = self._pet_config_for(agent_id)
        if config is None:
            return
        dialog = AgentEditDialog(config)
        if dialog.exec() == AgentEditDialog.DialogCode.Accepted and dialog.config is not None:
            self.update_pet_config(agent_id, dialog.config)

    def _delete_agent_from_dialog(self, agent_id: str) -> None:
        config = self._pet_config_for(agent_id)
        if config is None:
            return
        if QMessageBox.question(None, "删除 Agent", f"确定删除 {config.name} 吗？") != QMessageBox.StandardButton.Yes:
            return
        self.remove_pet(agent_id)

    def _refresh_management_dialog(self) -> None:
        if self.management_dialog is not None:
            self.management_dialog.load_configs(self.pets)

    def _agent_id_for(self, widget_or_agent_id) -> str | None:
        if isinstance(widget_or_agent_id, PetWidget):
            return widget_or_agent_id.pet_config.identity if widget_or_agent_id in self.widgets else None
        if widget_or_agent_id is None:
            return None
        return str(widget_or_agent_id)

    def _pet_config_for(self, agent_id: str | None) -> PetConfig | None:
        if agent_id is None:
            return None
        return next((pet for pet in self.pets if pet.identity == agent_id), None)

    def _widget_for(self, widget_or_agent_id) -> PetWidget | None:
        if isinstance(widget_or_agent_id, PetWidget):
            return widget_or_agent_id if widget_or_agent_id in self.widgets else None
        agent_id = str(widget_or_agent_id)
        return next((widget for widget in self.widgets if widget.pet_config.identity == agent_id), None)

    def set_agent_deployed(self, agent_id: str, deployed: bool) -> None:
        config = self._pet_config_for(agent_id)
        if config is None or config.deployed == deployed:
            return
        if deployed and self._deployed_count() >= MAX_DESKTOP_AGENTS:
            QMessageBox.information(None, "出战数量已满", f"桌面最多同时出战 {MAX_DESKTOP_AGENTS} 个 Agent。")
            self._refresh_management_dialog()
            return
        if not deployed and self._deployed_count() <= MIN_DESKTOP_AGENTS:
            QMessageBox.information(None, "至少保留一个出战 Agent", f"至少需要 {MIN_DESKTOP_AGENTS} 个 Agent 出现在桌面。")
            self._refresh_management_dialog()
            return

        updated_config = replace(config, deployed=deployed)
        self.pets = [updated_config if pet.identity == agent_id else pet for pet in self.pets]
        if deployed:
            widget = self._widget_for(agent_id)
            if widget is None:
                widget = self._create_widget_for_config(updated_config)
                self._load_persisted_direct_history(widget)
            widget.show()
        else:
            widget = self._widget_for(agent_id)
            if widget is not None:
                self._remove_widget(widget)

        if len(self.widgets) >= 2 and not self._auto_chat_timer.isActive():
            self.start_auto_chat()
        elif len(self.widgets) < 2:
            self.stop_auto_chat()
        self.save_current_configs()
        self._refresh_management_dialog()

    def _open_chat_from_management(self, agent_id: str) -> None:
        widget = self._widget_for(agent_id)
        if widget is None:
            QMessageBox.information(None, "Agent 未出战", "请先勾选“出战”，再打开聊天窗口。")
            return
        self.show_pet_chat_window(widget)

    def import_persona_for_pet(self, widget_or_agent_id) -> None:
        agent_id = self._agent_id_for(widget_or_agent_id)
        config = self._pet_config_for(agent_id)
        if config is None:
            return
        dialog = PetPersonaImportDialog(config.name, config.type_id)
        if dialog.exec() != PetPersonaImportDialog.DialogCode.Accepted or dialog.profile is None:
            return
        profile = dialog.profile
        result = getattr(dialog, "result", None)
        metadata = PersonaPackageMetadata(
            message_count=result.message_count if result is not None else 0,
            target_message_count=result.target_message_count if result is not None else 0,
            used_fallback_messages=result.used_fallback_messages if result is not None else False,
        )
        saved_path = save_pet_persona_package(
            profile,
            PET_PERSONAS_DIR / safe_persona_slug(profile.name or config.name),
            metadata,
        )
        updated_config = replace(
            config,
            name=profile.name or config.name,
            personality_tag=profile.personality_tag,
            persona_path=str(saved_path),
        )
        self.update_pet_config(agent_id, updated_config)
        widget = self._widget_for(agent_id)
        if widget is not None:
            companion = self.companions[widget]
            companion.apply_profile(profile)
            response = companion.handle_interaction("greeting")
            self._show_chat_response(widget, response, "direct")

    def _on_pet_clicked(self, widget: PetWidget) -> None:
        self._reply_locally(widget, "click", channel="direct")

    def _on_pet_speak_requested(self, widget: PetWidget, reason: str) -> None:
        self._reply_locally(widget, reason, channel="direct")

    def _on_pet_chat_requested(self, widget: PetWidget, text: str) -> None:
        message_id = self._append_direct_message(widget, BusMessage(sender="你", content=text, kind="user", anchor_agent_id=widget.pet_config.identity))
        if self.explicit_memory is not None:
            self.explicit_memory.remember_user_message(text, source_message_id=message_id, channel="direct", anchor_agent_id=widget.pet_config.identity)
        request = self._reply_request(widget, text, "chat", "direct")
        if self.reply_router.decide(request).route == "cloud":
            self._chat_with_llm(widget, text, channel="direct")
            return
        response = asyncio.run(self.reply_router.local_backend.reply(request))
        self.chat_reply_ready.emit(widget, response, "direct")

    def _on_group_chat_submitted(self, text: str) -> None:
        message_id = self._append_group_message(BusMessage(sender="你", content=text, kind="user"))
        if self.explicit_memory is not None:
            self.explicit_memory.remember_user_message(text, source_message_id=message_id, channel="group")
        if not self.widgets:
            return
        speaker = self.widgets[self._auto_chat_index % len(self.widgets)]
        listener = self.widgets[(self._auto_chat_index + 1) % len(self.widgets)] if len(self.widgets) > 1 else speaker
        self._auto_chat_index += 1
        prompt = self._group_chat_prompt(speaker, listener)
        request = self._reply_request(speaker, prompt, "group_chat", "group")
        if self.reply_router.decide(request).route == "cloud":
            self._chat_with_llm(speaker, prompt, show_thinking=True, channel="group")
            return
        response = asyncio.run(self.reply_router.local_backend.reply(request))
        self.chat_reply_ready.emit(speaker, response, "group")

    def _reply_locally(self, widget: PetWidget, event_type: str, channel: str = "direct") -> None:
        companion = self.companions[widget]
        self.chat_reply_ready.emit(widget, companion.handle_interaction(event_type), channel)

    def _memory_context_for(self, text: str) -> str:
        if self.explicit_memory is None:
            return ""
        memories = self.explicit_memory.relevant_memories(text, limit=6)
        return self.explicit_memory.format_for_prompt(memories)

    def _reply_request(self, widget: PetWidget, text: str, event_type: str, channel: str) -> ReplyRequest:
        return ReplyRequest(
            text=text,
            channel=channel,
            event_type=event_type,
            companion=self.companions[widget],
            memory_context=self._memory_context_for(text),
        )

    def _chat_with_llm(self, widget: PetWidget, text: str, show_thinking: bool = True, channel: str = "direct", sleepy_at_night: bool = False) -> None:
        companion = self.companions[widget]
        preview = companion.emotion_engine.analyze(
            signal=EmotionSignal("chat", text),
            current=companion.emotion_state,
            personality_tag=companion.profile.personality_tag,
        )
        companion.emotion_state = preview
        widget.set_mood(preview.mood)
        if show_thinking:
            self.chat_reply_stream_started.emit(widget, channel)

        request = self._reply_request(widget, text, "group_chat" if channel == "group" else "chat", channel)

        async def run_stream() -> None:
            async for event_type, payload in self.reply_router.cloud_backend.reply_stream(request):
                if event_type == "partial":
                    self.chat_reply_stream_delta.emit(widget, str(payload), channel)
                else:
                    response = self._nighttime_response(payload) if sleepy_at_night else payload
                    self.chat_reply_stream_finished.emit(widget, response, channel)

        def runner() -> None:
            time.sleep(get_thinking_time(companion.profile.personality_tag) / 1000)
            asyncio.run(run_stream())

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
        self._persist_chat_response(widget, response, channel)

    def _persist_chat_response(self, widget: PetWidget, response: PetResponse, channel: str) -> None:
        message = BusMessage(sender=widget.pet_config.name, content=response.text, kind="agent", agent_id=widget.pet_config.identity, anchor_agent_id=widget.pet_config.identity)
        if channel == "group":
            self._append_group_message(message)
        else:
            self._append_direct_message(widget, message)

    def _stream_message(self, widget: PetWidget, content: str) -> BusMessage:
        return BusMessage(sender=widget.pet_config.name, content=content, kind="agent", agent_id=widget.pet_config.identity, anchor_agent_id=widget.pet_config.identity)

    def _start_streaming_chat_response(self, widget: PetWidget, channel: str) -> None:
        if widget not in self.widgets:
            return
        self._reset_typewriter_state(widget, channel)
        self._update_streaming_chat_response(widget, "我想想怎么说……", channel)

    def _update_streaming_chat_response(self, widget: PetWidget, text: str, channel: str) -> None:
        if widget not in self.widgets:
            return
        state = self._typewriter_state(widget, channel)
        self._set_typewriter_target(state, text)
        if not state["timer"].isActive():
            state["timer"].start(get_typing_delay(state["rhythm"].personality_tag))

    def _finish_streaming_chat_response(self, widget: PetWidget, response: PetResponse, channel: str) -> None:
        if widget not in self.widgets:
            return
        state = self._typewriter_state(widget, channel)
        self._set_typewriter_target(state, response.text)
        state["final_response"] = response
        if not state["timer"].isActive():
            state["timer"].start(get_typing_delay(state["rhythm"].personality_tag))

    def _typewriter_key(self, widget: PetWidget, channel: str) -> tuple[PetWidget, str]:
        return widget, channel

    def _typewriter_state(self, widget: PetWidget, channel: str) -> dict:
        key = self._typewriter_key(widget, channel)
        state = self._typewriter_states.get(key)
        if state is not None:
            return state
        timer = QTimer(self)
        timer.timeout.connect(lambda current_widget=widget, current_channel=channel: self._tick_typewriter(current_widget, current_channel))
        rhythm = get_rhythm(self.companions[widget].profile.personality_tag)
        state = {"target_text": "", "shown_text": "", "final_response": None, "timer": timer, "rhythm": rhythm}
        self._typewriter_states[key] = state
        return state

    def _reset_typewriter_state(self, widget: PetWidget, channel: str) -> None:
        key = self._typewriter_key(widget, channel)
        state = self._typewriter_states.pop(key, None)
        if state is not None:
            state["timer"].stop()

    def _set_typewriter_target(self, state: dict, text: str) -> None:
        shown_text = state["shown_text"]
        current_target = state["target_text"]
        if shown_text and not text.startswith(shown_text) and text != current_target:
            state["shown_text"] = ""
        state["target_text"] = text

    def _tick_typewriter(self, widget: PetWidget, channel: str) -> None:
        key = self._typewriter_key(widget, channel)
        state = self._typewriter_states.get(key)
        if state is None:
            return
        if widget not in self.widgets:
            state["timer"].stop()
            self._typewriter_states.pop(key, None)
            return
        target_text = state["target_text"]
        shown_text = state["shown_text"]
        if len(shown_text) < len(target_text):
            chars_per_update = state["rhythm"].chars_per_update
            shown_text = target_text[:len(shown_text) + chars_per_update]
            state["shown_text"] = shown_text
            self._render_streaming_chat_response(widget, shown_text, channel)
            state["timer"].start(get_typing_delay(state["rhythm"].personality_tag))
            return
        final_response = state.get("final_response")
        if final_response is None:
            state["timer"].stop()
            return
        state["timer"].stop()
        self._typewriter_states.pop(key, None)
        self._complete_streaming_chat_response(widget, final_response, channel)

    def _render_streaming_chat_response(self, widget: PetWidget, text: str, channel: str) -> None:
        widget.show_or_update_stream_speech(text)
        message = self._stream_message(widget, text)
        if channel == "group":
            if self.group_history_window.isVisible():
                self.group_history_window.show_partial_message(message)
            return
        for window in [self.direct_chat_windows.get(widget), self.direct_history_windows.get(widget)]:
            if window is not None and window.isVisible():
                window.show_partial_message(message)

    def _complete_streaming_chat_response(self, widget: PetWidget, response: PetResponse, channel: str) -> None:
        if widget not in self.widgets:
            return
        widget.set_mood(response.mood)
        widget.finish_stream_speech(response.text)
        if channel == "group":
            self.group_history_window.clear_partial_message()
        else:
            for window in [self.direct_chat_windows.get(widget), self.direct_history_windows.get(widget)]:
                if window is not None:
                    window.clear_partial_message()
        self._persist_chat_response(widget, response, channel)

    def _append_group_message(self, message: BusMessage) -> int | None:
        self.group_history.append(message)
        message_id = None
        if self.chat_storage is not None:
            message_id = self.chat_storage.add_message("group", message, conversation_title="群聊")
        if self.group_history_window.isVisible():
            self.group_history_window.load_messages(list(self.group_history))
        return message_id

    def _append_direct_message(self, widget: PetWidget, message: BusMessage) -> int | None:
        if message.anchor_agent_id is None:
            message.anchor_agent_id = widget.pet_config.identity
        history = self.direct_histories.setdefault(widget, deque(maxlen=CHAT_UI_HISTORY_LIMIT))
        history.append(message)
        message_id = None
        if self.chat_storage is not None:
            message_id = self.chat_storage.add_message("direct", message, conversation_title=f"和{widget.pet_config.name}聊天")
        window = self.direct_history_windows.get(widget)
        if window is not None and window.isVisible():
            window.load_messages(list(history))
        chat_window = self.direct_chat_windows.get(widget)
        if chat_window is not None and chat_window.isVisible():
            chat_window.load_messages(list(history))
        return message_id

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
        if self.chat_storage is not None:
            self.chat_storage.clear_conversation("group")
        self.group_history_window.clear_messages()

    def _clear_direct_history(self, widget: PetWidget) -> None:
        self.direct_histories.setdefault(widget, deque(maxlen=CHAT_UI_HISTORY_LIMIT)).clear()
        if self.chat_storage is not None:
            self.chat_storage.clear_conversation("direct", widget.pet_config.identity)
        window = self.direct_history_windows.get(widget)
        if window is not None:
            window.clear_messages()

    def run_memory_recall_once(self) -> None:
        if self.explicit_memory is None or not self.widgets:
            return
        memories = self.explicit_memory.due_memories(limit=1)
        if not memories:
            return
        memory = memories[0]
        widget = self.widgets[self._memory_recall_index % len(self.widgets)]
        self._memory_recall_index += 1
        response = PetResponse(
            text=self.explicit_memory.compose_followup(memory),
            mood=PetMood.NORMAL,
            source="memory",
            reason="timely explicit memory",
        )
        self._show_chat_response(widget, response, "direct")
        self.explicit_memory.mark_mentioned(memory.id)

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
