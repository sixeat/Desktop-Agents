CLEAN_STYLE = """
QDialog, QMainWindow {
    background: #FFFFFF;
    color: #111111;
    font-family: "Microsoft YaHei";
}
QLabel {
    color: #111111;
}
QLineEdit, QTextEdit, QComboBox {
    background: #FFFFFF;
    border: 1px solid #D0D5DD;
    border-radius: 6px;
    padding: 7px 10px;
    color: #111111;
    selection-background-color: #DDEBFF;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus {
    border: 1px solid #111111;
}
QPushButton {
    background: #FFFFFF;
    border: 1px solid #B8BEC8;
    border-radius: 6px;
    padding: 7px 14px;
    color: #111111;
}
QPushButton:hover {
    background: #F5F5F5;
}
QPushButton:pressed {
    background: #EAEAEA;
}
QPushButton:disabled {
    background: #F5F5F5;
    color: #9AA0A6;
    border-color: #DADCE0;
}
QPushButton#primaryButton {
    background: #111111;
    color: #FFFFFF;
    border-color: #111111;
}
QPushButton#primaryButton:hover {
    background: #333333;
}
QGroupBox {
    border: 1px solid #DADCE0;
    border-radius: 8px;
    margin-top: 12px;
    padding: 14px 10px 10px 10px;
    background: #FFFFFF;
    color: #111111;
    font-weight: 700;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    background: #FFFFFF;
}
QTableWidget {
    background: #FFFFFF;
    alternate-background-color: #FAFAFA;
    border: 1px solid #DADCE0;
    border-radius: 6px;
    gridline-color: #EAECF0;
    color: #111111;
}
QHeaderView::section {
    background: #F5F5F5;
    border: none;
    border-right: 1px solid #DADCE0;
    padding: 7px;
    color: #111111;
    font-weight: 700;
}
QScrollArea {
    border: 1px solid #DADCE0;
    border-radius: 6px;
    background: #FFFFFF;
}
QCheckBox {
    color: #111111;
}
"""


def apply_cute_style(widget) -> None:
    widget.setStyleSheet(CLEAN_STYLE)


def title_style() -> str:
    return "font-size: 20px; font-weight: 700; color: #111111;"


def hint_style() -> str:
    return "font-size: 12px; color: #555555; line-height: 150%;"
