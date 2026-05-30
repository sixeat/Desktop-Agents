AC_STYLE = """
QDialog, QMainWindow {
    background: #f8f8f0;
    color: #725d42;
    font-family: "Microsoft YaHei", "Nunito", sans-serif;
}
QLabel {
    color: #794f27;
}
QLineEdit, QTextEdit, QComboBox {
    background: rgb(247, 243, 223);
    border: 3px solid #d4c9b4;
    border-radius: 16px;
    padding: 8px 14px;
    min-height: 30px;
    color: #725d42;
    selection-background-color: #e6f9f6;
    selection-color: #794f27;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus {
    border: 3px solid #ffcc00;
}
QComboBox::drop-down {
    border: none;
    width: 28px;
}
QComboBox QAbstractItemView {
    background: rgb(247, 243, 223);
    border: 3px solid #d4c9b4;
    border-radius: 14px;
    color: #725d42;
    selection-background-color: #e6f9f6;
    selection-color: #794f27;
}
QPushButton {
    background: #f8f8f0;
    border: 3px solid #bdaea0;
    border-radius: 20px;
    padding: 10px 22px;
    color: #794f27;
    font-weight: 700;
}
QPushButton:hover {
    background: #fffef5;
    border-color: #c9b8a8;
}
QPushButton:pressed {
    background: #ece8dc;
    border-color: #a89988;
}
QPushButton:disabled {
    background: #e8e4d8;
    color: #b0a898;
    border-color: #ccc4b8;
}
QPushButton#primaryButton {
    background: #19c8b9;
    color: #ffffff;
    border-color: #11a89b;
}
QPushButton#primaryButton:hover {
    background: #3dd4c6;
    border-color: #19c8b9;
}
QPushButton#primaryButton:pressed {
    background: #11a89b;
    border-color: #0e8f84;
}
QGroupBox {
    border: 3px solid #d4c9b4;
    border-radius: 20px;
    margin-top: 16px;
    padding: 18px 16px 14px 16px;
    background: rgb(247, 243, 223);
    color: #794f27;
    font-weight: 700;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 16px;
    padding: 0 10px;
    background: rgb(247, 243, 223);
}
QTableWidget {
    background: rgb(247, 243, 223);
    alternate-background-color: #f0ece0;
    border: 3px solid #d4c9b4;
    border-radius: 16px;
    gridline-color: #e0d8c8;
    color: #725d42;
    selection-background-color: #e6f9f6;
    selection-color: #794f27;
}
QHeaderView::section {
    background: #e6f9f6;
    border: none;
    border-right: 3px solid #d4c9b4;
    padding: 10px;
    color: #794f27;
    font-weight: 700;
}
QScrollArea {
    border: 3px solid #d4c9b4;
    border-radius: 16px;
    background: rgb(247, 243, 223);
}
QCheckBox {
    color: #794f27;
}
QTextEdit {
    background: rgb(247, 243, 223);
}
QMenu {
    background: rgb(247, 243, 223);
    border: 3px solid #d4c9b4;
    border-radius: 14px;
    padding: 8px;
}
QMenu::item {
    padding: 8px 22px;
    border-radius: 10px;
    color: #794f27;
}
QMenu::item:selected {
    background: #e6f9f6;
    color: #794f27;
}
QMenu::separator {
    height: 3px;
    background: #d4c9b4;
    margin: 8px 12px;
}
"""


def apply_cute_style(widget) -> None:
    widget.setStyleSheet(AC_STYLE)


def title_style() -> str:
    return "font-size: 20px; font-weight: 700; color: #794f27;"


def hint_style() -> str:
    return "font-size: 12px; color: #9f927d; line-height: 150%;"


def _rounded_pixmap(source: "QPixmap", size: int = 64, radius: int = 12) -> "QPixmap":
    from PyQt6.QtGui import QPixmap, QPainter, QPainterPath
    from PyQt6.QtCore import Qt

    scaled = source.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
    result = QPixmap(size, size)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, size, size, radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, scaled)
    painter.end()
    return result


def set_window_icon(window) -> None:
    from PyQt6.QtGui import QIcon, QPixmap
    from config import ICON_PATH

    if ICON_PATH.exists():
        pixmap = QPixmap(str(ICON_PATH))
        if not pixmap.isNull():
            window.setWindowIcon(QIcon(_rounded_pixmap(pixmap, 64, 14)))
