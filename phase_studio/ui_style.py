from __future__ import annotations


_FALLBACK_LIGHT_VS_QSS = """
QWidget {
    background-color: #ffffff;
    color: #1f1f1f;
    selection-background-color: #add6ff;
    selection-color: #000000;
    font-family: "Segoe UI", "Arial";
    font-size: 9pt;
}
QMainWindow, QDialog, QSplashScreen {
    background-color: #ffffff;
}
QGroupBox {
    border: 1px solid #d4d4d4;
    border-radius: 3px;
    margin-top: 0.8em;
    padding: 8px;
    background-color: #ffffff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    color: #1f1f1f;
    background-color: #ffffff;
}
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #ffffff;
    color: #1f1f1f;
    border: 1px solid #cecece;
    border-radius: 2px;
    padding: 3px 5px;
    selection-background-color: #add6ff;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #007acc;
}
QPushButton {
    background-color: #f3f3f3;
    color: #1f1f1f;
    border: 1px solid #cecece;
    border-radius: 2px;
    padding: 5px 12px;
}
QPushButton:hover {
    background-color: #e5f1fb;
    border-color: #007acc;
}
QPushButton:pressed {
    background-color: #cce4f7;
}
QPushButton:disabled {
    color: #a6a6a6;
    background-color: #f8f8f8;
    border-color: #dddddd;
}
QTabWidget::pane {
    border: 1px solid #d4d4d4;
    background-color: #ffffff;
}
QTabBar::tab {
    background-color: #f3f3f3;
    border: 1px solid #d4d4d4;
    padding: 5px 10px;
}
QTabBar::tab:selected {
    background-color: #ffffff;
    border-bottom-color: #ffffff;
}
QHeaderView::section {
    background-color: #f3f3f3;
    color: #1f1f1f;
    border: 1px solid #d4d4d4;
    padding: 4px;
}
QTableWidget, QTreeWidget, QListWidget {
    background-color: #ffffff;
    alternate-background-color: #f8f8f8;
    gridline-color: #e5e5e5;
    border: 1px solid #d4d4d4;
}
QToolTip {
    background-color: #ffffe1;
    color: #1f1f1f;
    border: 1px solid #c8c8c8;
    padding: 4px;
}
QProgressBar {
    border: 1px solid #d4d4d4;
    border-radius: 2px;
    text-align: center;
    background-color: #ffffff;
}
QProgressBar::chunk {
    background-color: #007acc;
}
"""


def apply_phase_studio_style(app: object) -> None:
    """Apply QtVSCodeStyle Light (Visual Studio) to every Phase Studio window.

    The preferred implementation uses the upstream ``qtvscodestyle`` package:
    ``qtvsc.load_stylesheet(qtvsc.Theme.LIGHT_VS)``.  A small local fallback is
    kept so the program remains usable during development if the optional
    dependency is not installed yet.
    """
    try:
        from PySide6.QtWidgets import QStyleFactory

        style = QStyleFactory.create("Fusion")
        if style is not None:
            app.setStyle(style)
    except Exception:
        pass

    try:
        import qtvscodestyle as qtvsc

        stylesheet = qtvsc.load_stylesheet(qtvsc.Theme.LIGHT_VS)
        app.setStyleSheet(stylesheet)
        return
    except Exception:
        app.setStyleSheet(_FALLBACK_LIGHT_VS_QSS)
