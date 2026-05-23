import asyncio
import tempfile
import threading
from pathlib import Path

from PyQt6.QtCore import QObject, QPoint, QRect, pyqtSignal
from PyQt6.QtWidgets import QApplication

from config import AGENT_SIZE, DEFAULT_AGENT_X, DEFAULT_AGENT_Y, PERSONAS_DIR, PROJECT_ROOT
from core.agent import Agent
from core.agent_bus import AgentBus, BusMessage
from core.llm_client import OpenAICompatibleClient
from core.llm_settings import load_llm_settings, settings_to_client_kwargs
from core.personality import list_personalities
from tools.extract_wechat import write_persona_json
from tools.wechat.analyzer import build_personality, summarize_messages
from tools.wechat.parsers import load_export_dir
from ui.agent_widget import AgentWidget
from ui.api_key_dialog import ApiKeyDialog
from ui.chat_history_window import ChatHistoryWindow
from ui.import_dialog import WeChatImportDialog
from ui.tool_permission_dialog import ToolPermissionDialog


class AgentManager(QObject):
    bus_message_received = pyqtSignal(object)
    tool_permission_requested = pyqtSignal(object)
    screenshot_requested = pyqtSignal(object)

    def __init__(self, bus: AgentBus, agents: dict[str, Agent], parent=None):
        super().__init__(parent)
        self.bus = bus
        self.agents = agents
        self.personas = list_personalities()
        self.widgets: dict[str, AgentWidget] = {}
        self.chat_history_window = ChatHistoryWindow()
        self.import_dialog: WeChatImportDialog | None = None
        self._permission_requests: dict[int, tuple[threading.Event, dict]] = {}
        self._screenshot_requests: dict[int, tuple[threading.Event, dict]] = {}
        self._request_counter = 0
        self.chat_history_window.load_messages(list(self.bus.recent_history))
        self.chat_history_window.clear_requested.connect(self.clear_chat_history)
        self._unsubscribe = self.bus.subscribe(self._on_bus_message)
        self.bus_message_received.connect(self._display_bus_message)
        self.bus_message_received.connect(self.chat_history_window.append_message)
        self.tool_permission_requested.connect(self._show_tool_permission_dialog)
        self.screenshot_requested.connect(self._capture_screenshot)

    def create_widgets(self) -> None:
        for index, (agent_id, agent) in enumerate(self.agents.items()):
            widget = AgentWidget(
                agent=agent,
                avatar_path=getattr(agent, "avatar", None),
                direct_chat_enabled=False,
                tray_enabled=index == 0,
            )
            widget.set_persona_options(self.personas)
            widget.user_input_submitted.connect(
                lambda text, current_agent_id=agent_id: self.bus.post_user_message(
                    text,
                    anchor_agent_id=current_agent_id,
                )
            )
            widget.persona_switch_requested.connect(
                lambda persona_name, current_agent_id=agent_id: self.switch_agent_persona(
                    current_agent_id,
                    persona_name,
                )
            )
            widget.history_requested.connect(self.show_chat_history)
            widget.wechat_import_requested.connect(
                lambda current_agent_id=agent_id: self.import_wechat_persona(current_agent_id)
            )
            widget.api_key_settings_requested.connect(self.show_api_key_settings)
            widget.move(self._position_for_index(index))
            self.widgets[agent_id] = widget

    def show_all(self) -> None:
        for widget in self.widgets.values():
            widget.show()

    def close(self) -> None:
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None
        for widget in self.widgets.values():
            widget.close()
        if self.import_dialog is not None:
            self.import_dialog.close()
        self.chat_history_window.close()

    async def request_tool_permission(self, request) -> bool:
        request_id = self._next_request_id()
        event = threading.Event()
        state = {"allowed": False}
        self._permission_requests[request_id] = (event, state)
        self.tool_permission_requested.emit({"id": request_id, "request": request})
        await asyncio.to_thread(event.wait)
        self._permission_requests.pop(request_id, None)
        return bool(state.get("allowed"))

    async def request_screenshot(self, request) -> dict:
        request_id = self._next_request_id()
        event = threading.Event()
        state: dict = {}
        self._screenshot_requests[request_id] = (event, state)
        self.screenshot_requested.emit({"id": request_id, "request": request})
        await asyncio.to_thread(event.wait)
        self._screenshot_requests.pop(request_id, None)
        if state.get("error"):
            raise ValueError(state["error"])
        return state

    def _next_request_id(self) -> int:
        self._request_counter += 1
        return self._request_counter

    def _show_tool_permission_dialog(self, payload: dict) -> None:
        request_id = payload["id"]
        request = payload["request"]
        event, state = self._permission_requests.get(request_id, (None, None))
        if event is None:
            return
        dialog = ToolPermissionDialog(request)
        state["allowed"] = dialog.exec() == ToolPermissionDialog.DialogCode.Accepted
        event.set()

    def _capture_screenshot(self, payload: dict) -> None:
        request_id = payload["id"]
        event, state = self._screenshot_requests.get(request_id, (None, None))
        if event is None:
            return
        screen = QApplication.primaryScreen()
        if screen is None:
            state["error"] = "未找到可截图的屏幕。"
            event.set()
            return
        pixmap = screen.grabWindow(0)
        output = Path(tempfile.gettempdir()) / f"desktop_agents_screenshot_{request_id}.png"
        if not pixmap.save(str(output), "PNG"):
            state["error"] = "截图保存失败。"
            event.set()
            return
        state.update({
            "path": str(output),
            "width": pixmap.width(),
            "height": pixmap.height(),
        })
        event.set()

    def show_chat_history(self) -> None:
        self.chat_history_window.show()
        self.chat_history_window.raise_()
        self.chat_history_window.activateWindow()

    def clear_chat_history(self) -> None:
        self.bus.recent_history.clear()
        self.chat_history_window.clear_messages()

    def import_wechat_persona(self, agent_id: str) -> None:
        self.import_dialog = WeChatImportDialog(output_dir=PERSONAS_DIR)
        self.import_dialog.import_completed.connect(
            lambda persona_config, current_agent_id=agent_id: self.on_persona_imported(current_agent_id, persona_config)
        )
        self.import_dialog.exec()

    def show_api_key_settings(self) -> None:
        dialog = ApiKeyDialog(first_run=False)
        if dialog.exec() != ApiKeyDialog.DialogCode.Accepted:
            return
        settings = load_llm_settings()
        client_kwargs = settings_to_client_kwargs(settings)
        for agent in self.agents.values():
            agent.client = OpenAICompatibleClient(**client_kwargs)
        self.bus.broadcast(BusMessage(sender="系统", content="API Key 设置已更新。", kind="system"))

    def on_persona_imported(self, agent_id: str, persona_config: dict) -> None:
        persona_id = self._persona_id_from_name(str(persona_config.get("name") or "wechat_persona"))
        self.refresh_personas()
        self.switch_agent_persona(agent_id, persona_id)

    def import_wechat_persona_from_export(self, export_dir: Path, wxid: str, display_name: str | None = None) -> str:
        messages, report = load_export_dir(export_dir, wxid=wxid)
        if not messages:
            raise ValueError("未从导出目录读取到可分析的文字消息。请确认已用 WeChatMsg/MemoTrace 导出 CSV/TXT/JSON。")

        persona = build_personality(messages, wxid=wxid, display_name=display_name)
        persona_id = self._persona_id_from_name(display_name or wxid)
        output_path = PERSONAS_DIR / f"{persona_id}.json"
        write_persona_json(persona, output_path)
        self.refresh_personas()
        summary = summarize_messages(messages)
        self.bus.broadcast(BusMessage(
            sender="系统",
            content=f"已导入微信人格 {persona['name']}：{summary['target_messages']}/{summary['total_messages']} 条目标消息。",
            kind="system",
            anchor_agent_id=next(iter(self.widgets), None),
        ))
        return persona_id

    def refresh_personas(self) -> None:
        self.personas = list_personalities()
        for widget in self.widgets.values():
            widget.set_persona_options(self.personas)

    def _persona_id_from_name(self, value: str) -> str:
        safe = "".join(ch for ch in value.strip() if ch.isalnum() or ch in "_- ").strip().replace(" ", "_")
        return safe[:64] or "wechat_persona"

    def _on_bus_message(self, msg: BusMessage) -> None:
        self.bus_message_received.emit(msg)

    def _display_bus_message(self, msg: BusMessage) -> None:
        anchor_id = msg.anchor_agent_id or msg.agent_id
        widget = self.widgets.get(anchor_id)
        if widget is None and self.widgets:
            widget = next(iter(self.widgets.values()))
        if widget is not None:
            widget.show_chat_bubble(msg.sender, msg.content)

    def switch_agent_persona(self, agent_id: str, persona_name: str) -> None:
        agent = self.agents.get(agent_id)
        widget = self.widgets.get(agent_id)
        if agent is None or widget is None or persona_name not in self.personas:
            return

        agent.switch_persona(persona_name, clear_history=True)
        self.bus.register(agent_id, agent)
        widget.apply_agent_personality()
        widget.show_chat_bubble("系统", f"已切换人格：{agent.name}")

    def _position_for_index(self, index: int) -> QPoint:
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else QRect(0, 0, 1200, 800)
        widget_size = AGENT_SIZE + 20
        spacing = widget_size + 50
        start_x = max(available.left(), min(DEFAULT_AGENT_X, available.right() - widget_size))
        start_y = max(available.top(), min(DEFAULT_AGENT_Y, available.bottom() - widget_size))
        max_columns = max(1, (available.right() - start_x + 1) // spacing)

        row = index // max_columns
        col = index % max_columns
        x = start_x + col * spacing
        y = start_y + row * spacing

        if x + widget_size > available.right():
            x = max(available.left(), available.right() - widget_size)
        if y + widget_size > available.bottom():
            y = max(available.top(), available.bottom() - widget_size)
        return QPoint(x, y)
