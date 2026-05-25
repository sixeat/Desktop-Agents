from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QAbstractItemView, QDialog, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout

from core.pet import PetConfig
from ui.theme import apply_cute_style, hint_style, title_style


class AgentManagementDialog(QDialog):
    add_requested = pyqtSignal()
    edit_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(str)
    import_requested = pyqtSignal(str)
    avatar_requested = pyqtSignal(str)
    chat_requested = pyqtSignal(str)

    def __init__(self, configs: list[PetConfig], parent=None):
        super().__init__(parent)
        self.configs = configs
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
        hint = QLabel("在这里新建 Agent、换情绪形象、导入朋友人格，或者直接打开聊天。", self)
        hint.setStyleSheet(hint_style())
        root.addWidget(hint)
        self.table = QTableWidget(0, 5, self)
        self.table.setHorizontalHeaderLabels(["名称", "性格", "形象", "人格", "ID"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setColumnHidden(4, True)
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
        self.avatar_button = QPushButton("更换形象", self)
        self.chat_button = QPushButton("打开聊天", self)
        for button in [self.add_button, self.edit_button, self.delete_button, self.import_button, self.avatar_button, self.chat_button]:
            buttons.addWidget(button)
        root.addLayout(buttons)

        self.add_button.clicked.connect(self.add_requested.emit)
        self.edit_button.clicked.connect(lambda: self._emit_selected(self.edit_requested))
        self.delete_button.clicked.connect(lambda: self._emit_selected(self.delete_requested))
        self.import_button.clicked.connect(lambda: self._emit_selected(self.import_requested))
        self.avatar_button.clicked.connect(lambda: self._emit_selected(self.avatar_requested))
        self.chat_button.clicked.connect(lambda: self._emit_selected(self.chat_requested))

    def load_configs(self, configs: list[PetConfig]) -> None:
        self.configs = configs
        self.table.setRowCount(0)
        for config in configs:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(config.name))
            self.table.setItem(row, 1, QTableWidgetItem(config.personality_tag))
            self.table.setItem(row, 2, QTableWidgetItem("已设置" if config.avatar_path or config.mood_avatar_paths else "默认"))
            self.table.setItem(row, 3, QTableWidgetItem("已导入" if config.persona_path else "默认"))
            self.table.setItem(row, 4, QTableWidgetItem(config.identity))
        if self.table.rowCount() > 0 and not self.table.selectedItems():
            self.table.selectRow(0)
        self.table.resizeColumnsToContents()

    def selected_agent_id(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 4)
        return item.text() if item else None

    def _emit_selected(self, signal) -> None:
        agent_id = self.selected_agent_id()
        if agent_id:
            signal.emit(agent_id)
