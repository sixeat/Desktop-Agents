from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from core.personality_trainer import PersonalityProfile
from core.pet_persona_importer import PetPersonaImportResult, load_profile_from_export
from ui.theme import apply_cute_style, hint_style, title_style


class PetPersonaImportDialog(QDialog):
    def __init__(self, pet_name: str, pet_type: str = "cat", parent=None):
        super().__init__(parent)
        self.pet_name = pet_name
        self.pet_type = pet_type
        self.selected_path: Path | None = None
        self.result: PetPersonaImportResult | None = None
        self._setup_ui()

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

        analyze_button = QPushButton("开始分析", self)
        analyze_button.setObjectName("primaryButton")
        analyze_button.clicked.connect(self.analyze_file)
        root.addWidget(analyze_button, alignment=Qt.AlignmentFlag.AlignRight)

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

    def analyze_file(self) -> None:
        if self.selected_path is None:
            QMessageBox.warning(self, "请选择文件", "请先选择聊天记录导出文件。")
            return
        target_name = self.target_input.text().strip() or self.selected_path.stem
        persona_name = self.name_input.text().strip() or target_name
        try:
            self.result = load_profile_from_export(
                self.selected_path,
                target_name=target_name,
                pet_name=persona_name,
                pet_type=self.pet_type,
            )
        except Exception as exc:
            QMessageBox.warning(self, "分析失败", f"无法分析该文件：{exc}")
            return

        self.preview.setPlainText(self._format_preview(self.result))
        self.import_button.setEnabled(True)

    def _format_preview(self, result: PetPersonaImportResult) -> str:
        profile = result.profile
        warning = "\n提示：目标消息较少，已使用可读取的全部文本辅助分析。\n" if result.used_fallback_messages else ""
        return "\n".join([
            f"人格名称：{profile.name}",
            f"性格：{profile.personality_tag}",
            f"口头禅：{', '.join(profile.catchphrases) if profile.catchphrases else '无'}",
            f"常聊话题：{', '.join(profile.topics) if profile.topics else '无'}",
            f"句式：{', '.join(profile.sentence_patterns) if profile.sentence_patterns else '无'}",
            f"Emoji：{', '.join(profile.emoji_habits) if profile.emoji_habits else '无'}",
            f"平均句长：{profile.avg_sentence_length:.1f}",
            f"用于分析消息数：{result.message_count}",
            f"目标消息数：{result.target_message_count}",
            warning.strip(),
        ]).strip()
