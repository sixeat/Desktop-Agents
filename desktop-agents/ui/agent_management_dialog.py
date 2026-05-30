from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QAbstractItemView, QDialog, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout

from config import MAX_DESKTOP_AGENTS, MIN_DESKTOP_AGENTS
from core.pet import PetConfig
from ui.theme import apply_cute_style, hint_style, title_style, set_window_icon


class AgentManagementDialog(QDialog):
    add_requested = pyqtSignal()
    edit_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(str)
    import_requested = pyqtSignal(str)
    reset_persona_requested = pyqtSignal(str)
    avatar_requested = pyqtSignal(str)
    chat_requested = pyqtSignal(str)
    persona_library_requested = pyqtSignal()
    deployed_changed = pyqtSignal(str, bool)

    def __init__(self, configs: list[PetConfig], parent=None):
        super().__init__(parent)
        self.configs = configs
        self._loading = False
        set_window_icon(self)
        self._setup_ui()
        self.load_configs(configs)

    def _setup_ui(self) -> None:
        self.setWindowTitle("Agent 管理")
        self.resize(820, 500)
        apply_cute_style(self)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)
        title = QLabel("管理你的桌面 Agent 小队", self)
        title.setStyleSheet(title_style())
        root.addWidget(title)
        hint = QLabel(f"在这里新建 Agent、换情绪形象、导入朋友人格，或者直接打开聊天。勾选“出战”决定谁出现在桌面，同时支持 {MIN_DESKTOP_AGENTS}-{MAX_DESKTOP_AGENTS} 个出战 Agent。", self)
        hint.setStyleSheet(hint_style())
        root.addWidget(hint)
        self.table = QTableWidget(0, 6, self)
        self.table.setHorizontalHeaderLabels(["出战", "名称", "性格", "形象", "人格", "ID"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setColumnHidden(5, True)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        self.add_button = QPushButton("新建 Agent", self)
        self.add_button.setObjectName("primaryButton")
        self.edit_button = QPushButton("编辑", self)
        self.delete_button = QPushButton("删除", self)
        self.import_button = QPushButton("导入人格", self)
        self.reset_persona_button = QPushButton("重置人格", self)
        self.avatar_button = QPushButton("更换形象", self)
        self.chat_button = QPushButton("打开聊天", self)
        self.library_button = QPushButton("人格库", self)
        for button in [self.add_button, self.edit_button, self.delete_button, self.import_button, self.reset_persona_button, self.avatar_button, self.chat_button, self.library_button]:
            buttons.addWidget(button)
        root.addLayout(buttons)

        self.add_button.clicked.connect(self.add_requested.emit)
        self.edit_button.clicked.connect(lambda: self._emit_selected(self.edit_requested))
        self.delete_button.clicked.connect(lambda: self._emit_selected(self.delete_requested))
        self.import_button.clicked.connect(lambda: self._emit_selected(self.import_requested))
        self.reset_persona_button.clicked.connect(lambda: self._emit_selected(self.reset_persona_requested))
        self.avatar_button.clicked.connect(lambda: self._emit_selected(self.avatar_requested))
        self.chat_button.clicked.connect(lambda: self._emit_selected(self.chat_requested))
        self.library_button.clicked.connect(self.persona_library_requested.emit)
        self.table.itemChanged.connect(self._on_item_changed)

    def load_configs(self, configs: list[PetConfig]) -> None:
        self.configs = configs
        self._loading = True
        self.table.setRowCount(0)
        for config in configs:
            row = self.table.rowCount()
            self.table.insertRow(row)
            deploy_item = QTableWidgetItem()
            deploy_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            deploy_item.setCheckState(Qt.CheckState.Checked if config.deployed else Qt.CheckState.Unchecked)
            self.table.setItem(row, 0, deploy_item)
            self.table.setItem(row, 1, QTableWidgetItem(config.name))
            self.table.setItem(row, 2, QTableWidgetItem(config.personality_tag))
            self.table.setItem(row, 3, QTableWidgetItem("已设置" if config.avatar_path or config.mood_avatar_paths else "默认"))
            self.table.setItem(row, 4, QTableWidgetItem("已导入" if config.persona_path else "默认"))
            self.table.setItem(row, 5, QTableWidgetItem(config.identity))
        self._loading = False
        if self.table.rowCount() > 0 and not self.table.selectedItems():
            self.table.selectRow(0)
        self.add_button.setEnabled(True)
        self.delete_button.setEnabled(len(configs) > MIN_DESKTOP_AGENTS)
        self.table.resizeColumnsToContents()

    def selected_agent_id(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 5)
        return item.text() if item else None

    def _emit_selected(self, signal) -> None:
        agent_id = self.selected_agent_id()
        if agent_id:
            signal.emit(agent_id)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading or item.column() != 0:
            return
        agent_id_item = self.table.item(item.row(), 5)
        if agent_id_item is None:
            return
        self.deployed_changed.emit(agent_id_item.text(), item.checkState() == Qt.CheckState.Checked)
