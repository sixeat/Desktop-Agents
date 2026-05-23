import json

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QTextEdit, QVBoxLayout

from core.tooling import PermissionLevel, ToolCallRequest


class ToolPermissionDialog(QDialog):
    def __init__(self, request: ToolCallRequest, parent=None):
        super().__init__(parent)
        self.request = request
        self.setWindowTitle("工具执行确认")
        self.setMinimumSize(480, 360)
        self._setup()

    def _setup(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        level = "高危" if self.request.permission_level == PermissionLevel.DANGEROUS else "普通"
        title = QLabel(f"{self.request.agent_name} 请求使用工具：{self.request.tool_name}")
        title.setStyleSheet("font-size:16px;font-weight:bold")
        layout.addWidget(title)

        warning = QLabel(f"权限级别：{level}。请确认这是你允许 Agent 执行的操作。")
        warning.setWordWrap(True)
        if self.request.permission_level == PermissionLevel.DANGEROUS:
            warning.setStyleSheet("background:#FFEBEE;color:#B71C1C;padding:10px;border-radius:5px")
        else:
            warning.setStyleSheet("background:#E3F2FD;color:#1565C0;padding:10px;border-radius:5px")
        layout.addWidget(warning)

        args = QTextEdit()
        args.setReadOnly(True)
        args.setText(json.dumps(self.request.arguments, ensure_ascii=False, indent=2))
        args.setMinimumHeight(160)
        layout.addWidget(args)

        buttons = QDialogButtonBox()
        allow = buttons.addButton("允许一次", QDialogButtonBox.ButtonRole.AcceptRole)
        deny = buttons.addButton("拒绝", QDialogButtonBox.ButtonRole.RejectRole)
        allow.setDefault(False)
        deny.setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons, alignment=Qt.AlignmentFlag.AlignRight)
