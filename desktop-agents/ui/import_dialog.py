from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from core.importer.wechat_importer import WeChatImporter
from ui.theme import set_window_icon


class ImportThread(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    done = pyqtSignal(object)

    def __init__(self, importer: WeChatImporter, session: str, name: str):
        super().__init__()
        self.importer = importer
        self.session = session
        self.name = name

    def run(self):
        try:
            self.status.emit("提取消息...")
            self.progress.emit(30)
            result = self.importer.full_import(self.session, self.name)
            self.progress.emit(100)
            self.done.emit(result)
        except Exception as exc:
            self.status.emit(f"失败: {exc}")
            self.done.emit(None)


class FileImportThread(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    done = pyqtSignal(object)

    def __init__(self, importer: WeChatImporter, path: str, wxid: str, name: str):
        super().__init__()
        self.importer = importer
        self.path = path
        self.wxid = wxid
        self.name = name

    def run(self):
        try:
            self.status.emit("解析本地聊天记录...")
            self.progress.emit(30)
            result = self.importer.import_export_path(self.path, self.wxid, self.name)
            self.progress.emit(100)
            self.done.emit(result)
        except Exception as exc:
            self.status.emit(f"失败: {exc}")
            self.done.emit(None)


class WeChatImportDialog(QDialog):
    import_completed = pyqtSignal(dict)

    def __init__(self, parent=None, output_dir=None):
        super().__init__(parent)
        self.setWindowTitle("导入聊天记录人格")
        self.setMinimumSize(560, 520)
        set_window_icon(self)
        self.importer = WeChatImporter(output_dir=output_dir)
        self.worker: ImportThread | FileImportThread | None = None
        self.setup()

    def setup(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("导入聊天记录人格")
        font = QFont()
        font.setPointSize(15)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        self.st = QLabel()
        self.st.setStyleSheet("padding: 10px; border-radius: 5px;")
        self.st.setWordWrap(True)
        layout.addWidget(self.st)

        row = QHBoxLayout()
        self.btn_file = QPushButton("导入聊天记录文件")
        self.btn_file.clicked.connect(self.choose_file)
        row.addWidget(self.btn_file)
        self.btn_folder = QPushButton("批量导入")
        self.btn_folder.clicked.connect(self.choose_folder)
        row.addWidget(self.btn_folder)
        row.addStretch()
        layout.addLayout(row)

        self.list = QListWidget()
        self.list.setMaximumHeight(180)
        self.list.itemSelectionChanged.connect(lambda: self.btn_go.setEnabled(True))
        layout.addWidget(self.list)

        self.pre = QTextEdit()
        self.pre.setMaximumHeight(90)
        self.pre.setReadOnly(True)
        layout.addWidget(self.pre)

        self.prog = QProgressBar()
        self.prog.setVisible(False)
        layout.addWidget(self.prog)

        self.btn_go = QPushButton("导入并创建 Agent")
        self.btn_go.setStyleSheet("QPushButton{background:#07C160;color:white;padding:10px;font-weight:bold;border-radius:5px}QPushButton:hover{background:#06AD56}QPushButton:disabled{background:#ccc}")
        self.btn_go.clicked.connect(self.go)
        self.btn_go.setEnabled(False)
        layout.addWidget(self.btn_go)

        self.st.setText(
            "推荐：导入本地聊天记录文件，或批量导入包含聊天记录的文件夹（支持 txt/csv/json/sqlite）。\n"
            "如果不知道怎么导出聊天记录，请参考 https://github.com/r266-tech/wechat-local-mcp"
        )
        self.st.setStyleSheet("background:#E3F2FD;color:#1565C0;padding:10px;border-radius:5px")

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择聊天记录文件",
            "",
            "聊天记录 (*.txt *.csv *.json *.db *.sqlite *.sqlite3);;所有文件 (*.*)",
        )
        if path:
            self.import_local_path(path)

    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, "选择聊天记录文件夹")
        if path:
            self.import_local_path(path)

    def import_local_path(self, path: str):
        wxid, ok = QInputDialog.getText(self, "联系人标识", "输入要分析的微信号/昵称/文件名：")
        if not ok or not wxid.strip():
            return
        name, ok = QInputDialog.getText(self, "人格名称", "导入后 Agent 名称：", text=wxid.strip())
        if not ok:
            return
        self.prog.setVisible(True)
        self.btn_go.setEnabled(False)
        self.btn_file.setEnabled(False)
        self.btn_folder.setEnabled(False)
        self.worker = FileImportThread(self.importer, path, wxid.strip(), name.strip() or wxid.strip())
        self.worker.progress.connect(self.prog.setValue)
        self.worker.status.connect(self.pre.setText)
        self.worker.done.connect(self.on_done)
        self.worker.start()

    def load(self):
        self.btn.setEnabled(False)
        self.list.clear()
        contacts = self.importer.contacts()
        if not contacts:
            QMessageBox.information(self, "提示", "未获取到联系人。请确认微信已登录且有聊天记录。")
            self.btn.setEnabled(True)
            return
        self.st.setText(f"已获取 {len(contacts)} 个联系人")
        for contact in contacts[:60]:
            marker = "群" if contact["type"] == "group" else ""
            item = QListWidgetItem(f"{contact['name']} {marker} ({contact['msg_count']}条)")
            item.setData(Qt.ItemDataRole.UserRole, contact)
            self.list.addItem(item)
        self.btn.setText("刷新")
        self.btn.setProperty("a", "load")
        self.btn.setEnabled(True)

    def go(self):
        item = self.list.currentItem()
        if not item:
            return
        contact = item.data(Qt.ItemDataRole.UserRole)
        self.prog.setVisible(True)
        self.btn_go.setEnabled(False)
        self.worker = ImportThread(self.importer, contact["session_id"], contact["name"])
        self.worker.progress.connect(self.prog.setValue)
        self.worker.status.connect(self.pre.setText)
        self.worker.done.connect(self.on_done)
        self.worker.start()

    def on_done(self, result):
        if result:
            phrases = ", ".join([item[0] for item in result.top_phrases[:3]]) if result.top_phrases else "无"
            self.pre.setText(f"导入成功！\n联系人: {result.contact_name}\n消息数: {result.total_messages}\n口头禅: {phrases}")
            self.import_completed.emit(result.persona_config)
            QMessageBox.information(self, "完成", f"已导入 {result.contact_name} 的人格！")
            self.accept()
        else:
            QMessageBox.warning(self, "失败", "导入失败。请确认选择的记录里包含该微信号/昵称/文件名对应的文字消息。")
            self.btn_go.setEnabled(True)
        self.btn_file.setEnabled(True)
        self.btn_folder.setEnabled(True)
        self.prog.setVisible(False)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait(2000)
        super().closeEvent(event)
