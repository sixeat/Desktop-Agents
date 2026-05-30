import asyncio
import threading

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from core.llm_client import LLMValidationResult, OpenAICompatibleClient
from core.llm_settings import DEFAULT_BASE_URL, DEFAULT_MODEL, DEFAULT_PROVIDER, LLMSettings, MASKED_KEY, ROUTE_MODE_CLOUD_WHEN_KEY, ROUTE_MODE_LOCAL_ONLY, load_llm_settings, save_llm_settings, settings_to_client_kwargs
from ui.theme import set_window_icon


class ApiKeyDialog(QDialog):
    validation_finished = pyqtSignal(object, str, object)
    def __init__(self, first_run: bool = False, parent=None):
        super().__init__(parent)
        self.first_run = first_run
        self.saved = False
        self._validating = False
        self.existing = load_llm_settings()
        self.validation_finished.connect(self._on_validation_finished)
        self.setWindowTitle("API Key 设置" if not first_run else "首次使用配置")
        self.setMinimumSize(480, 320)
        set_window_icon(self)
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

        self.privacy_notice = QLabel("隐私提示：云端增强会把当前对话、人格提示、最近聊天历史和相关记忆发送给配置的 API 服务商；导入人格时的原始聊天记录不会上传。选择“仅本地回复”后，运行时聊天不会发送到云端。")
        self.privacy_notice.setWordWrap(True)
        self.privacy_notice.setStyleSheet("background:#FFF7ED;color:#9A3412;padding:10px;border-radius:5px")
        layout.addWidget(self.privacy_notice)

        form = QFormLayout()
        self.provider_input = QLineEdit(self.existing.provider or DEFAULT_PROVIDER)
        self.base_url_input = QLineEdit(self.existing.base_url or DEFAULT_BASE_URL)
        self.model_input = QLineEdit(self.existing.model or DEFAULT_MODEL)
        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        if self.existing.api_key:
            self.key_input.setPlaceholderText(MASKED_KEY)
        self.route_mode_input = QComboBox(self)
        self.route_mode_input.addItem("有 API Key 时使用云端增强", ROUTE_MODE_CLOUD_WHEN_KEY)
        self.route_mode_input.addItem("仅本地回复，不发送聊天内容到云端", ROUTE_MODE_LOCAL_ONLY)
        index = self.route_mode_input.findData(self.existing.reply_route_mode)
        self.route_mode_input.setCurrentIndex(max(index, 0))
        self.show_key = QCheckBox("显示 API Key")
        self.show_key.stateChanged.connect(self._toggle_key_visible)

        form.addRow("Provider", self.provider_input)
        form.addRow("Base URL", self.base_url_input)
        form.addRow("Model", self.model_input)
        form.addRow("API Key", self.key_input)
        form.addRow("回复模式", self.route_mode_input)
        form.addRow("", self.show_key)
        layout.addLayout(form)

        self.status_label = QLabel("尚未验证")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color:#6B7280;")
        layout.addWidget(self.status_label)

        buttons = QDialogButtonBox()
        self.test_button = buttons.addButton("测试 Key", QDialogButtonBox.ButtonRole.ActionRole)
        self.save_button = buttons.addButton("保存", QDialogButtonBox.ButtonRole.AcceptRole)
        cancel_text = "退出" if self.first_run else "取消"
        self.cancel_button = buttons.addButton(cancel_text, QDialogButtonBox.ButtonRole.RejectRole)
        self.save_button.setDefault(True)
        self.test_button.clicked.connect(self.test_key)
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
            reply_route_mode=self.route_mode_input.currentData(),
        )

    def _validate_local_inputs(self, settings: LLMSettings) -> bool:
        if not settings.provider:
            QMessageBox.warning(self, "提示", "Provider 不能为空。")
            return False
        if not settings.base_url:
            QMessageBox.warning(self, "提示", "Base URL 不能为空。")
            return False
        if not settings.model:
            QMessageBox.warning(self, "提示", "Model 不能为空。")
            return False
        if settings.reply_route_mode == ROUTE_MODE_LOCAL_ONLY and not self.first_run:
            return True
        if self.first_run and not settings.api_key:
            QMessageBox.warning(self, "提示", "首次使用需要配置 API Key。")
            return False
        if not settings.api_key:
            QMessageBox.warning(self, "提示", "API Key 不能为空。")
            return False
        return True

    def test_key(self) -> None:
        settings = self.current_settings()
        if self._validate_local_inputs(settings):
            self._start_validation(settings, "test")

    def save(self) -> None:
        settings = self.current_settings()
        if not self._validate_local_inputs(settings):
            return
        if settings.reply_route_mode == ROUTE_MODE_LOCAL_ONLY and not settings.api_key and not self.first_run:
            save_llm_settings(settings, replace_key=False)
            self.saved = True
            self.accept()
            return
        self._start_validation(settings, "save")

    def _start_validation(self, settings: LLMSettings, intent: str) -> None:
        if self._validating:
            return
        self._set_busy(True)
        self._set_status("正在验证 API Key…", "#1565C0")

        def runner() -> None:
            try:
                client = OpenAICompatibleClient(**settings_to_client_kwargs(settings))
                result = asyncio.run(client.validate_api_key())
            except Exception as exc:
                result = LLMValidationResult(False, f"验证失败：{exc}")
            self.validation_finished.emit(result, intent, settings)

        threading.Thread(target=runner, daemon=True).start()

    def _on_validation_finished(self, result: LLMValidationResult, intent: str, settings: LLMSettings) -> None:
        self._set_busy(False)
        self._set_status(result.message, "#2E7D32" if result.ok else "#C62828")
        if not result.ok or intent != "save":
            return
        try:
            save_llm_settings(settings, replace_key=bool(self.key_input.text().strip()))
        except RuntimeError as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        self.saved = True
        self.accept()

    def _set_busy(self, busy: bool) -> None:
        self._validating = busy
        for widget in [self.provider_input, self.base_url_input, self.model_input, self.key_input, self.route_mode_input, self.show_key, self.test_button, self.save_button, self.cancel_button]:
            widget.setEnabled(not busy)

    def _set_status(self, text: str, color: str) -> None:
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color:{color};")
