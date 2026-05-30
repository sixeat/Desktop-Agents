from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from config import PET_PERSONAS_DIR
from core.pet_persona_importer import delete_persona_package, list_persona_packages
from ui.theme import apply_cute_style, hint_style, title_style, set_window_icon


class PersonaLibraryDialog(QDialog):
    bind_requested = pyqtSignal(str)
    batch_import_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._packages: list = []
        set_window_icon(self)
        self._setup_ui()
        self._refresh()

    def _setup_ui(self) -> None:
        self.setWindowTitle("人格库")
        self.resize(720, 460)
        apply_cute_style(self)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel("已生成的人格包", self)
        title.setStyleSheet(title_style())
        root.addWidget(title)

        hint = QLabel("这里列出所有从聊天记录导入或批量生成的人格包。可以删除，也可以绑定到 Agent。", self)
        hint.setStyleSheet(hint_style())
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.table = QTableWidget(0, 5, self)
        self.table.setHorizontalHeaderLabels(["名称", "性格", "消息数", "创建时间", "路径"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        self.batch_button = QPushButton("批量导入", self)
        self.refresh_button = QPushButton("刷新", self)
        self.bind_button = QPushButton("绑定到 Agent", self)
        self.bind_button.setObjectName("primaryButton")
        self.delete_button = QPushButton("删除", self)
        buttons.addWidget(self.batch_button)
        buttons.addWidget(self.refresh_button)
        buttons.addWidget(self.bind_button)
        buttons.addWidget(self.delete_button)
        buttons.addStretch(1)
        root.addLayout(buttons)

        self.batch_button.clicked.connect(self.batch_import_requested.emit)
        self.refresh_button.clicked.connect(self._refresh)
        self.bind_button.clicked.connect(self._on_bind)
        self.delete_button.clicked.connect(self._on_delete)

    def _refresh(self) -> None:
        self._packages = list_persona_packages(PET_PERSONAS_DIR)
        self.table.setRowCount(len(self._packages))
        for row, pkg in enumerate(self._packages):
            self.table.setItem(row, 0, QTableWidgetItem(pkg.name))
            self.table.setItem(row, 1, QTableWidgetItem(pkg.personality_tag))
            self.table.setItem(row, 2, QTableWidgetItem(f"{pkg.message_count} / {pkg.target_message_count}"))
            self.table.setItem(row, 3, QTableWidgetItem(pkg.created_at[:19].replace("T", " ") if pkg.created_at else ""))
            self.table.setItem(row, 4, QTableWidgetItem(str(pkg.package_dir)))
        self.table.resizeColumnsToContents()
        if self.table.rowCount() > 0:
            self.table.selectRow(0)

    def selected_package_path(self) -> str | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._packages):
            return None
        return str(self._packages[row].persona_path)

    def selected_package_name(self) -> str | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._packages):
            return None
        return self._packages[row].name

    def _on_bind(self) -> None:
        path = self.selected_package_path()
        if not path:
            QMessageBox.information(self, "提示", "请先选中一个人格包。")
            return
        self.bind_requested.emit(path)

    def _on_delete(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._packages):
            QMessageBox.information(self, "提示", "请先选中一个人格包。")
            return
        pkg = self._packages[row]
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除人格包“{pkg.name}”吗？\n路径：{pkg.package_dir}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if delete_persona_package(pkg.package_dir):
            self._refresh()
        else:
            QMessageBox.warning(self, "删除失败", "无法删除该人格包，请检查文件权限。")
