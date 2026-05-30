from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
)

from core.pet_persona_importer import BatchPersonaPlan, BatchPersonaResult, build_batch_personas, scan_persona_sources
from ui.theme import set_window_icon


class BatchPersonaImportDialog(QDialog):
    def __init__(self, output_dir: Path, parent=None):
        super().__init__(parent)
        self.output_dir = output_dir
        self.selected_dir: Path | None = None
        self.sources = []
        self.results: list[BatchPersonaResult] = []
        set_window_icon(self)
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setWindowTitle("批量导入人格")
        self.resize(760, 620)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        intro = QLabel("选择一个包含聊天记录导出文件的文件夹，程序会自动扫描里面的 .txt、.json、.csv 和 .db/.sqlite 文件，并按发送者生成人格；把多行的“人格名称”改成同一个名字即可合并同一个人。", self)
        intro.setWordWrap(True)
        root.addWidget(intro)

        self.consent_checkbox = QCheckBox("我已获得这些聊天记录的使用授权，并同意仅在本机扫描和生成人格包；原始聊天不会复制进人格目录。", self)
        root.addWidget(self.consent_checkbox)

        folder_row = QHBoxLayout()
        self.path_input = QLineEdit(self)
        self.path_input.setReadOnly(True)
        choose_button = QPushButton("选择文件夹", self)
        choose_button.clicked.connect(self.choose_folder)
        self.scan_button = QPushButton("扫描", self)
        self.scan_button.clicked.connect(self.scan_folder)
        folder_row.addWidget(self.path_input, 1)
        folder_row.addWidget(choose_button)
        folder_row.addWidget(self.scan_button)
        root.addLayout(folder_row)

        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(["导入", "发送者/别名", "消息数", "人格名称（同名会合并）"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemChanged.connect(self._refresh_preview)
        root.addWidget(self.table, 1)

        self.preview = QTextEdit(self)
        self.preview.setReadOnly(True)
        self.preview.setMaximumHeight(150)
        self.preview.setPlaceholderText("扫描结果和生成结果会显示在这里。")
        root.addWidget(self.preview)

        self.buttons = QDialogButtonBox(self)
        self.generate_button = self.buttons.addButton("生成并保存", QDialogButtonBox.ButtonRole.AcceptRole)
        self.generate_button.setEnabled(False)
        self.buttons.addButton("取消", QDialogButtonBox.ButtonRole.RejectRole)
        self.buttons.accepted.connect(self.generate_personas)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons, alignment=Qt.AlignmentFlag.AlignRight)

    def choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择聊天记录导出文件夹")
        if not folder:
            return
        self.selected_dir = Path(folder)
        self.path_input.setText(folder)
        self.sources = []
        self.results = []
        self.table.setRowCount(0)
        self.preview.clear()
        self.generate_button.setEnabled(False)

    def scan_folder(self) -> None:
        if self.selected_dir is None:
            QMessageBox.warning(self, "请选择文件夹", "请先选择聊天记录导出文件夹。")
            return
        if not self.consent_checkbox.isChecked():
            QMessageBox.warning(self, "需要授权", "请确认你已获得聊天记录使用授权，并同意仅在本机扫描和生成人格包。")
            return
        self.sources = scan_persona_sources(self.selected_dir)
        self._load_sources()
        self.generate_button.setEnabled(bool(self.sources))
        if not self.sources:
            self.preview.setPlainText("没有发现可用于生成人格的发送者。\n\n可能原因：\n1. 文件夹里没有支持的文件（.txt/.json/.csv/.db/.sqlite）\n2. txt 文件格式不符合（需要是 WeFlow 导出或带 [文字] 标签的格式）\n3. 所有发送者的消息都少于 2 条\n4. 有效消息都被过滤了（如 [图片] 占位、转账、空白行等）")

    def generate_personas(self) -> None:
        if not self.consent_checkbox.isChecked():
            QMessageBox.warning(self, "需要授权", "请确认你已获得聊天记录使用授权，并同意仅在本机生成人格包。")
            return
        plans = self._build_plans()
        if not plans:
            QMessageBox.warning(self, "没有可生成的人格", "请至少勾选一个发送者，并填写人格名称。")
            return
        self.results = build_batch_personas(self.sources, plans, output_dir=self.output_dir)
        self.preview.setPlainText("\n".join(
            f"已生成：{result.persona_name}（{result.message_count} 条，来源：{', '.join(result.source_names)}，保存到：{result.output_path}）"
            for result in self.results
        ))
        self.accept()

    def _load_sources(self) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.sources))
        for row, source in enumerate(self.sources):
            include = QTableWidgetItem()
            include.setFlags(include.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            include.setCheckState(Qt.CheckState.Checked)
            self.table.setItem(row, 0, include)
            name = QTableWidgetItem(source.name)
            name.setFlags(name.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 1, name)
            count = QTableWidgetItem(str(source.message_count))
            count.setFlags(count.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 2, count)
            self.table.setItem(row, 3, QTableWidgetItem(source.name))
        self.table.blockSignals(False)
        self._refresh_preview()

    def _build_plans(self) -> list[BatchPersonaPlan]:
        grouped: dict[str, list[str]] = {}
        for row, source in enumerate(self.sources):
            include = self.table.item(row, 0)
            if include is None or include.checkState() != Qt.CheckState.Checked:
                continue
            name_item = self.table.item(row, 3)
            persona_name = name_item.text().strip() if name_item else ""
            if not persona_name:
                continue
            grouped.setdefault(persona_name, []).append(source.name)
        return [BatchPersonaPlan(persona_name=name, source_names=source_names) for name, source_names in grouped.items()]

    def _refresh_preview(self) -> None:
        if not self.sources:
            return
        plans = self._build_plans()
        lines = [
            f"发现 {len(self.sources)} 个发送者，准备生成 {len(plans)} 个人格。",
            "隐私预览：扫描和生成仅在本机执行，原始聊天记录不会复制到人格目录。",
            "人格包将包含 manifest/persona/style/examples/system_prompt/eval 等派生文件。",
        ]
        for plan in plans:
            count = sum(source.message_count for source in self.sources if source.name in plan.source_names)
            merged = "、".join(plan.source_names)
            lines.append(f"- {plan.persona_name}: {count} 条，来源 {merged}")
        self.preview.setPlainText("\n".join(lines))
