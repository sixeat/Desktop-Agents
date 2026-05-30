import threading
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QCheckBox,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from core.personality_trainer import PersonalityProfile
from core.pet_persona_importer import PetPersonaImportResult, build_persona_package_preview, load_profile_from_export
from ui.theme import apply_cute_style, hint_style, title_style, set_window_icon


class PetPersonaImportDialog(QDialog):
    analysis_finished = pyqtSignal(object, object)

    def __init__(self, pet_name: str, pet_type: str = "cat", parent=None):
        super().__init__(parent)
        self.pet_name = pet_name
        self.pet_type = pet_type
        self.selected_path: Path | None = None
        self.result: PetPersonaImportResult | None = None
        self._analyzing = False
        set_window_icon(self)
        self._setup_ui()
        self.analysis_finished.connect(self._on_analysis_finished)

    @property
    def profile(self) -> PersonalityProfile | None:
        return self.result.profile if self.result else None

    def _setup_ui(self) -> None:
        self.setWindowTitle(f"导入{self.pet_name}的人格")
        self.resize(600, 600)
        apply_cute_style(self)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel("从聊天记录蒸馏人格", self)
        title.setStyleSheet(title_style())
        root.addWidget(title)
        intro = QLabel("选择微信聊天记录导出文件，联系人用于定位发言者，Agent 名称用于导入后的桌面显示名。", self)
        intro.setWordWrap(True)
        intro.setStyleSheet(hint_style())
        root.addWidget(intro)

        self.consent_checkbox = QCheckBox("我已获得聊天记录使用授权，并同意仅在本机分析人格特征", self)
        self.consent_checkbox.stateChanged.connect(self._refresh_analyze_enabled)
        root.addWidget(self.consent_checkbox)

        file_row = QHBoxLayout()
        self.path_input = QLineEdit(self)
        self.path_input.setReadOnly(True)
        choose_button = QPushButton("选择聊天记录文件", self)
        choose_button.clicked.connect(self.choose_file)
        file_row.addWidget(self.path_input, 1)
        file_row.addWidget(choose_button)
        root.addLayout(file_row)

        form_group = QGroupBox("导入设置", self)
        form = QFormLayout(form_group)
        self.target_input = QLineEdit(self)
        self.target_input.setPlaceholderText("导出文件里的发送者名，比如：张斌")
        self.name_input = QLineEdit(self)
        self.name_input.setText(self.pet_name)
        self.name_input.setPlaceholderText("桌面上显示的名字，比如：篮球搭子")
        form.addRow("聊天记录里的联系人", self.target_input)
        form.addRow("导入后 Agent 名称", self.name_input)
        root.addWidget(form_group)

        self.analyze_button = QPushButton("开始分析", self)
        self.analyze_button.setObjectName("primaryButton")
        self.analyze_button.setEnabled(False)
        self.analyze_button.clicked.connect(self.analyze_file)
        root.addWidget(self.analyze_button, alignment=Qt.AlignmentFlag.AlignRight)

        self.preview = QTextEdit(self)
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("分析结果会显示在这里。")
        root.addWidget(self.preview, 1)

        self.buttons = QDialogButtonBox(self)
        self.import_button = self.buttons.addButton("确认导入", QDialogButtonBox.ButtonRole.AcceptRole)
        self.import_button.setObjectName("primaryButton")
        self.import_button.setEnabled(False)
        self.buttons.addButton("取消", QDialogButtonBox.ButtonRole.RejectRole)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

    def choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择聊天记录导出文件",
            "",
            "聊天记录 (*.json *.txt *.csv);;JSON (*.json);;文本 (*.txt);;CSV (*.csv)",
        )
        if not path:
            return
        self.selected_path = Path(path)
        self.path_input.setText(path)
        if not self.target_input.text().strip():
            self.target_input.setText(self.selected_path.stem)
        if not self.name_input.text().strip():
            self.name_input.setText(self.selected_path.stem)
        self.result = None
        self.import_button.setEnabled(False)
        self.preview.clear()
        self._refresh_analyze_enabled()

    def analyze_file(self) -> None:
        if self._analyzing:
            return
        if self.selected_path is None:
            QMessageBox.warning(self, "请选择文件", "请先选择聊天记录导出文件。")
            return
        if not self.consent_checkbox.isChecked():
            QMessageBox.warning(self, "需要授权", "请确认你已获得聊天记录使用授权，并同意在本机分析。")
            return
        path = self.selected_path
        target_name = self.target_input.text().strip() or path.stem
        persona_name = self.name_input.text().strip() or target_name
        self._set_analyzing(True)
        self.preview.setPlainText("正在分析聊天记录，请稍等……\n文件较大时可能需要几十秒，窗口不会再卡死。")

        def runner() -> None:
            try:
                result = load_profile_from_export(
                    path,
                    target_name=target_name,
                    pet_name=persona_name,
                    pet_type=self.pet_type,
                )
                self.analysis_finished.emit(result, None)
            except Exception as exc:
                self.analysis_finished.emit(None, exc)

        threading.Thread(target=runner, daemon=True).start()

    def _on_analysis_finished(self, result: PetPersonaImportResult | None, error: Exception | None) -> None:
        self._set_analyzing(False)
        if error is not None or result is None:
            self.preview.clear()
            QMessageBox.warning(self, "分析失败", f"无法分析该文件：{error}")
            return
        self.result = result
        self.preview.setPlainText(self._format_preview(result))
        self.import_button.setEnabled(True)

    def _refresh_analyze_enabled(self) -> None:
        self.analyze_button.setEnabled(
            not self._analyzing and self.selected_path is not None and self.consent_checkbox.isChecked()
        )

    def _set_analyzing(self, analyzing: bool) -> None:
        self._analyzing = analyzing
        self._refresh_analyze_enabled()
        self.import_button.setEnabled(False)
        self.target_input.setEnabled(not analyzing)
        self.name_input.setEnabled(not analyzing)
        self.consent_checkbox.setEnabled(not analyzing)

    def _format_preview(self, result: PetPersonaImportResult) -> str:
        profile = result.profile
        preview = build_persona_package_preview(profile, result)
        privacy = preview["manifest"]["privacy"]
        warning = "\n提示：目标消息较少，已使用可读取的全部文本辅助分析。\n" if result.used_fallback_messages else ""
        return "\n".join([
            "分析预览：确认导入后会保存人格包，原始聊天记录不会复制到人格目录。",
            f"人格名称：{profile.name}",
            f"性格：{profile.personality_tag}",
            f"口头禅：{', '.join(profile.catchphrases) if profile.catchphrases else '无'}",
            f"常聊话题：{', '.join(profile.topics) if profile.topics else '无'}",
            f"句式：{', '.join(profile.sentence_patterns) if profile.sentence_patterns else '无'}",
            f"Emoji：{', '.join(profile.emoji_habits) if profile.emoji_habits else '无'}",
            f"平均句长：{profile.avg_sentence_length:.1f}",
            f"用于分析消息数：{result.message_count}",
            f"目标消息数：{result.target_message_count}",
            "",
            "人格包 / 隐私预览：",
            f"- 将生成：{', '.join(preview['files'])}",
            f"- 原始聊天记录写入人格包：{'是' if privacy['raw_chat_included'] else '否'}",
            "- 导入分析默认仅在本机处理，不启用云端增强。",
            "- examples.jsonl 只保存匿名风格样本，用于之后在别的电脑重新学习风格。",
            f"- 脱敏次数：{privacy['redaction_count']}；敏感模式命中：{privacy['blocked_sensitive_patterns']}",
            warning.strip(),
        ]).strip()
