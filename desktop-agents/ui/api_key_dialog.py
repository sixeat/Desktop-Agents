from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from core.llm_settings import DEFAULT_BASE_URL, DEFAULT_MODEL, DEFAULT_PROVIDER, LLMSettings, MASKED_KEY, load_llm_settings, save_llm_settings


class ApiKeyDialog(QDialog):
    def __init__(self, first_run: bool = False, parent=None):
        super().__init__(parent)
        self.first_run = first_run
        self.saved = False
        self.existing = load_llm_settings()
        self.setWindowTitle("API Key 设置" if not first_run else "首次使用配置")
        self.setMinimumSize(480, 320)
        self._setup()

    def _setup(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("配置大模型 API Key" if self.first_run else "API Key 设置")
        title.setStyleSheet("font-size:16px;font-weight:bold")
        layout.addWidget(title)

        desc = QLabel("用于 Agent 聊天和工具调用。API Key 会优先保存到系统凭据管理器；不可用时保存到当前 Windows 用户配置，不写入项目文件。")
        desc.setWordWrap(True)
        desc.setStyleSheet("background:#E3F2FD;color:#1565C0;padding:10px;border-radius:5px")
        layout.addWidget(desc)

        form = QFormLayout()
        self.provider_input = QLineEdit(self.existing.provider or DEFAULT_PROVIDER)
        self.base_url_input = QLineEdit(self.existing.base_url or DEFAULT_BASE_URL)
        self.model_input = QLineEdit(self.existing.model or DEFAULT_MODEL)
        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        if self.existing.api_key:
            self.key_input.setPlaceholderText(MASKED_KEY)
        self.show_key = QCheckBox("显示 API Key")
        self.show_key.stateChanged.connect(self._toggle_key_visible)

        form.addRow("Provider", self.provider_input)
        form.addRow("Base URL", self.base_url_input)
        form.addRow("Model", self.model_input)
        form.addRow("API Key", self.key_input)
        form.addRow("", self.show_key)
        layout.addLayout(form)

        buttons = QDialogButtonBox()
        save = buttons.addButton("保存", QDialogButtonBox.ButtonRole.AcceptRole)
        cancel_text = "退出" if self.first_run else "取消"
        buttons.addButton(cancel_text, QDialogButtonBox.ButtonRole.RejectRole)
        save.setDefault(True)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons, alignment=Qt.AlignmentFlag.AlignRight)

    def _toggle_key_visible(self) -> None:
        mode = QLineEdit.EchoMode.Normal if self.show_key.isChecked() else QLineEdit.EchoMode.Password
        self.key_input.setEchoMode(mode)

    def current_settings(self) -> LLMSettings:
        new_key = self.key_input.text().strip()
        api_key = new_key or self.existing.api_key
        return LLMSettings(
            provider=self.provider_input.text().strip(),
            api_key=api_key,
            base_url=self.base_url_input.text().strip(),
            model=self.model_input.text().strip(),
            source="dialog",
        )

    def save(self) -> None:
        settings = self.current_settings()
        if not settings.provider:
            QMessageBox.warning(self, "提示", "Provider 不能为空。")
            return
        if not settings.base_url:
            QMessageBox.warning(self, "提示", "Base URL 不能为空。")
            return
        if not settings.model:
            QMessageBox.warning(self, "提示", "Model 不能为空。")
            return
        if self.first_run and not settings.api_key:
            QMessageBox.warning(self, "提示", "首次使用需要配置 API Key。")
            return
        try:
            save_llm_settings(settings, replace_key=bool(self.key_input.text().strip()))
        except RuntimeError as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        self.saved = True
        self.accept()
