from dataclasses import replace
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.pet import PERSONALITY_TAGS, PetConfig, PetMood, default_pet_definition, default_personality_for_type
from core.pet_registry import new_agent_id, normalize_pet_config
from ui.theme import apply_cute_style, hint_style, title_style


MOOD_IMAGE_LABELS = {
    PetMood.NORMAL: "正常",
    PetMood.HAPPY: "开心",
    PetMood.SAD: "难过",
    PetMood.SLEEPY: "困",
    PetMood.SURPRISED: "惊讶",
    PetMood.ANGRY: "生气",
}

IMAGE_FILTER = "图片 (*.png *.jpg *.jpeg *.webp *.bmp *.gif);;PNG (*.png);;所有文件 (*)"


class AgentEditDialog(QDialog):
    def __init__(self, config: PetConfig | None = None, parent=None):
        super().__init__(parent)
        self.original_config = config
        self.config: PetConfig | None = None
        self.import_after_create = False
        self.mood_inputs: dict[PetMood, QLineEdit] = {}
        self._setup_ui()
        self._load_config(config)

    def _setup_ui(self) -> None:
        self.setWindowTitle("编辑 Agent" if self.original_config else "新建 Agent")
        self.resize(680, 600)
        apply_cute_style(self)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel("给 Agent 换上专属小形象" if self.original_config else "创建一个新的桌面 Agent", self)
        title.setStyleSheet(title_style())
        root.addWidget(title)
        intro = QLabel("设置名字、默认人格和 6 张情绪 PNG。静态图片会自动加呼吸、弹跳和情绪动作。", self)
        intro.setWordWrap(True)
        intro.setStyleSheet(hint_style())
        root.addWidget(intro)

        basic_group = QGroupBox("基础信息", self)
        form = QFormLayout(basic_group)
        self.name_input = QLineEdit(self)
        self.name_input.setPlaceholderText("比如：张斌、奶糖、篮球搭子")
        self.personality_input = QComboBox(self)
        self.personality_input.addItems(PERSONALITY_TAGS)
        form.addRow("Agent 名称", self.name_input)
        form.addRow("默认人格", self.personality_input)
        root.addWidget(basic_group)

        image_group = QGroupBox("情绪形象", self)
        mood_grid = QGridLayout(image_group)
        mood_grid.setColumnStretch(1, 1)
        for row, (mood, label) in enumerate(MOOD_IMAGE_LABELS.items()):
            input_box = QLineEdit(self)
            input_box.setPlaceholderText("可留空，留空时复用正常图")
            choose_button = QPushButton("选择", self)
            clear_button = QPushButton("清除", self)
            choose_button.clicked.connect(lambda checked=False, current_mood=mood: self._choose_image(current_mood))
            clear_button.clicked.connect(lambda checked=False, current_mood=mood: self.mood_inputs[current_mood].clear())
            self.mood_inputs[mood] = input_box
            mood_grid.addWidget(QLabel(f"{label} PNG", self), row, 0)
            mood_grid.addWidget(input_box, row, 1)
            mood_grid.addWidget(choose_button, row, 2)
            mood_grid.addWidget(clear_button, row, 3)
        root.addWidget(image_group)

        helper = QLabel("只填“正常”也可以，其他情绪会共用正常图；头像白底会自动尝试抠透明。", self)
        helper.setWordWrap(True)
        helper.setStyleSheet(hint_style())
        root.addWidget(helper)

        self.import_checkbox = QCheckBox("创建后立即导入人格", self)
        root.addWidget(self.import_checkbox)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        ok_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setText("保存 Agent")
            ok_button.setObjectName("primaryButton")
        cancel_button = self.buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setText("取消")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

    def _load_config(self, config: PetConfig | None) -> None:
        if config is None:
            definition = default_pet_definition()
            self.name_input.setText(definition.default_name)
            self._set_combo_text(self.personality_input, default_personality_for_type(definition.type_id))
            return
        self.name_input.setText(config.name)
        self._set_combo_text(self.personality_input, config.personality_tag)
        paths = dict(config.mood_avatar_paths or {})
        if config.avatar_path and PetMood.NORMAL.value not in paths:
            paths[PetMood.NORMAL.value] = config.avatar_path
        for mood, input_box in self.mood_inputs.items():
            input_box.setText(paths.get(mood.value, ""))
        self.import_checkbox.setVisible(False)

    def _choose_image(self, mood: PetMood) -> None:
        path, _ = QFileDialog.getOpenFileName(self, f"选择{MOOD_IMAGE_LABELS[mood]}形象", "", IMAGE_FILTER)
        if path:
            self.mood_inputs[mood].setText(path)

    def accept(self) -> None:
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "名称不能为空", "请填写 Agent 名称。")
            return
        definition = default_pet_definition()
        mood_paths = {mood.value: input_box.text().strip() for mood, input_box in self.mood_inputs.items() if input_box.text().strip()}
        if self.original_config is None:
            base = PetConfig(
                type_id=definition.type_id,
                type_name=definition.display_name,
                name=name,
                color=definition.color,
                personality_tag=self.personality_input.currentText(),
                agent_id=new_agent_id(),
            )
        else:
            base = self.original_config
        self.config = normalize_pet_config(replace(
            base,
            name=name,
            personality_tag=self.personality_input.currentText(),
            avatar_path=mood_paths.get(PetMood.NORMAL.value, base.avatar_path),
            mood_avatar_paths=mood_paths,
        ))
        self.import_after_create = self.import_checkbox.isChecked()
        super().accept()

    def _set_combo_value(self, combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _set_combo_text(self, combo: QComboBox, text: str) -> None:
        index = combo.findText(text)
        if index >= 0:
            combo.setCurrentIndex(index)
