from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from core.personality_trainer import PersonalityTrainer
from ui.theme import set_window_icon
from core.pet import PetConfig, PERSONALITY_TAGS, available_pet_definitions


class PetSelectorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pet_definitions = available_pet_definitions()
        self.name_inputs: list[QLineEdit] = []
        self.personality_inputs: list[QComboBox] = []
        self._selected_pets: list[PetConfig] = []
        self.setWindowTitle("选择桌面萌宠")
        self.setMinimumSize(420, 300)
        set_window_icon(self)
        self._setup()

    def _setup(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("选择 3 只桌面伙伴")
        title.setStyleSheet("font-size:16px;font-weight:bold")
        layout.addWidget(title)

        desc = QLabel("只填写名字和默认人格，形象会使用内置模板。")
        desc.setWordWrap(True)
        desc.setStyleSheet("background:#FFF8E1;color:#7A4F00;padding:10px;border-radius:5px")
        layout.addWidget(desc)

        form = QFormLayout()
        templates = PersonalityTrainer.DEFAULT_PROFILES
        for index in range(3):
            row = QWidget(self)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)

            definition = self.pet_definitions[index % len(self.pet_definitions)]
            template = templates[index % len(templates)]

            name_input = QLineEdit(row)
            name_input.setMaxLength(12)
            name_input.setText(definition.default_name)

            personality_input = QComboBox(row)
            personality_input.addItems(PERSONALITY_TAGS)
            personality_input.setCurrentText(template["personality_tag"])

            row_layout.addWidget(QLabel(f"内置形象 {index + 1}", row), 1)
            row_layout.addWidget(name_input, 1)
            row_layout.addWidget(personality_input, 1)
            form.addRow(f"Agent {index + 1}", row)

            self.name_inputs.append(name_input)
            self.personality_inputs.append(personality_input)

        layout.addLayout(form)

        buttons = QDialogButtonBox()
        confirm = buttons.addButton("召唤萌宠", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton("取消", QDialogButtonBox.ButtonRole.RejectRole)
        confirm.setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons, alignment=Qt.AlignmentFlag.AlignRight)

    def selected_pets(self) -> list[PetConfig]:
        return list(self._selected_pets)

    def accept(self) -> None:
        pets: list[PetConfig] = []
        for index, (definition, name_input) in enumerate(zip(self.pet_definitions, self.name_inputs), start=1):
            name = name_input.text().strip()
            if not name:
                QMessageBox.warning(self, "提示", f"萌宠 {index} 的名字不能为空。")
                return
            pets.append(PetConfig(
                type_id=definition.type_id,
                type_name=definition.display_name,
                name=name,
                color=definition.color,
                personality_tag=self.personality_inputs[index - 1].currentText(),
            ))

        if len(pets) != 3:
            QMessageBox.warning(self, "提示", "请选择 3 只萌宠。")
            return
        self._selected_pets = pets
        super().accept()
