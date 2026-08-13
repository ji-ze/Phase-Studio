from __future__ import annotations


_SHARPED_QSS = """
QWidget {
    background-color: #ffffff;
    color: #001170;
    selection-background-color: #44b7ff;
    selection-color: #001170;
    font-family: "Segoe UI", "Arial";
    font-size: 10pt;
}
QMainWindow, QDialog, QSplashScreen {
    background-color: #ffffff;
}
QGroupBox {
    border: none;
    border-top: 1px solid #f2f4f9;
    border-radius: 0;
    margin-top: 1.25em;
    padding: 12px 8px 8px 8px;
    background-color: #ffffff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 0;
    padding: 0 8px 0 0;
    color: #001170;
    background-color: #ffffff;
    font-weight: 700;
}
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #ffffff;
    color: #001170;
    border: none;
    border-bottom: 1px solid #44b7ff;
    border-radius: 0;
    padding: 4px 6px;
    min-height: 22px;
    selection-background-color: #44b7ff;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: none;
    border-bottom: 2px solid #2264b8;
}
QSpinBox, QDoubleSpinBox {
    padding-right: 23px;
}
QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 20px;
    background-color: #f2f4f9;
    border: none;
    border-left: 1px solid #44b7ff;
    border-bottom: 1px solid #44b7ff;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 20px;
    background-color: #f2f4f9;
    border: none;
    border-left: 1px solid #44b7ff;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: #44b7ff;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow,
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    width: 10px;
    height: 7px;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    image: url("__PHASE_STUDIO_ARROW_UP_XPM__");
}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    image: url("__PHASE_STUDIO_ARROW_DOWN_XPM__");
}
QComboBox {
    padding-right: 25px;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 22px;
    background-color: #f2f4f9;
    border: none;
    border-left: 1px solid #44b7ff;
}
QComboBox::drop-down:hover {
    background-color: #44b7ff;
}
QComboBox::down-arrow {
    image: url("__PHASE_STUDIO_ARROW_DOWN_XPM__");
    width: 10px;
    height: 7px;
}
QPushButton {
    background-color: #ffffff;
    color: #001170;
    border: 1px solid #2264b8;
    border-radius: 0;
    padding: 5px 12px;
    min-height: 24px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #44b7ff;
    border-color: #2264b8;
}
QPushButton:pressed {
    background-color: #2264b8;
    color: #ffffff;
}
QPushButton:disabled {
    color: #44b7ff;
    background-color: #ffffff;
    border-color: #44b7ff;
}
QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled,
QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {
    color: #44b7ff;
    background-color: #f2f4f9;
    border-bottom-color: #44b7ff;
}
QLabel:disabled {
    color: #44b7ff;
}
QTabWidget::pane {
    border: none;
    border-radius: 0;
    background-color: #ffffff;
}
QTabBar::tab {
    background-color: #f2f4f9;
    color: #001170;
    border: none;
    border-bottom: 1px solid #44b7ff;
    padding: 6px 12px;
    margin-right: 1px;
    border-top-left-radius: 0;
    border-top-right-radius: 0;
}
QTabBar::tab:selected {
    background-color: #ffffff;
    color: #001170;
    border-bottom: 3px solid #2264b8;
    font-weight: 700;
}
#categoryTabs > QTabBar::tab {
    background-color: #f2f4f9;
    color: #001170;
    border: 1px solid #001170;
    padding: 7px 24px;
    font-weight: 700;
}
#categoryTabs > QTabBar::tab:selected {
    background-color: #001170;
    color: #ffffff;
    border: 1px solid #001170;
}
QHeaderView::section {
    background-color: #f2f4f9;
    color: #001170;
    border: 1px solid #44b7ff;
    padding: 7px;
    font-weight: 700;
}
QTableWidget, QTreeWidget, QListWidget {
    background-color: #ffffff;
    alternate-background-color: #ffffff;
    gridline-color: #44b7ff;
    border: 1px solid #44b7ff;
}
QToolTip {
    background-color: #f2f4f9;
    color: #001170;
    border: 1px solid #2264b8;
    padding: 4px;
}
QProgressBar {
    border: none;
    border-bottom: 1px solid #44b7ff;
    border-radius: 0;
    text-align: center;
    background-color: #f2f4f9;
    min-height: 14px;
    max-height: 18px;
    font-weight: 600;
}
QProgressBar::chunk {
    background-color: #2264b8;
    border-radius: 0;
}
QWidget#brandHeader {
    background-color: #f2f4f9;
    border: none;
    border-bottom: 2px solid #2264b8;
    border-radius: 0;
}
QLabel#brandTitle {
    background-color: #f2f4f9;
    color: #001170;
    font-size: 17pt;
    font-weight: 800;
    letter-spacing: 1px;
}
QLabel#brandSubtitle {
    background-color: #f2f4f9;
    color: #2264b8;
    font-size: 9pt;
    font-weight: 600;
}
QLabel#brandLogo {
    background-color: #f2f4f9;
}
QLabel#versionBadge {
    color: #ffffff;
    background-color: #2264b8;
    border-radius: 0;
    padding: 3px 8px;
    font-size: 9pt;
    font-weight: 700;
}
QWidget#dashboardHeader {
    background-color: #001170;
    border-radius: 0;
}
QLabel#dashboardTitle {
    background-color: #001170;
    color: #ffffff;
    font-size: 13pt;
    font-weight: 800;
    letter-spacing: 1px;
}
QLabel#dashboardSubtitle {
    background-color: #001170;
    color: #44b7ff;
    font-size: 9pt;
    font-weight: 600;
}
QLabel#statusBadge {
    color: #001170;
    background-color: #f2f4f9;
    border: 1px solid #44b7ff;
    border-radius: 0;
    padding: 3px 9px;
    font-size: 9pt;
    font-weight: 800;
}
QLabel#statusBadge[runState="running"] {
    color: #ffffff;
    background-color: #2264b8;
    border-color: #44b7ff;
}
QLabel#statusBadge[runState="stopping"] {
    color: #001170;
    background-color: #44b7ff;
    border-color: #ffffff;
}
QLabel#statusBadge[runState="complete"], QLabel#statusBadge[runState="transferred"] {
    color: #2264b8;
    background-color: #f2f4f9;
    border: 2px solid #2264b8;
}
QLabel#statusBadge[runState="error"], QLabel#statusBadge[runState="cancelled"] {
    color: #ffffff;
    background-color: #001170;
    border: 2px solid #44b7ff;
}
QLabel#sectionLabel {
    color: #2264b8;
    font-size: 9pt;
    font-weight: 800;
    letter-spacing: 1px;
    padding: 2px 0 1px 0;
}
QWidget#resultSection {
    border: none;
    background-color: #ffffff;
}
QWidget#metricsCanvas, QWidget#structureCanvas {
    border: none;
    border-radius: 0;
    background-color: #ffffff;
}
QTextEdit#executionLog {
    border: none;
    border-top: 1px solid #44b7ff;
    border-radius: 0;
    padding: 6px;
    background-color: #ffffff;
    color: #001170;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 9pt;
}
QPushButton#primaryButton {
    color: #ffffff;
    background-color: #001170;
    border: 1px solid #001170;
    min-height: 31px;
    font-size: 11pt;
}
QPushButton#primaryButton:hover {
    background-color: #2264b8;
    border-color: #2264b8;
}
QPushButton#handoffButton {
    color: #2264b8;
    background-color: #ffffff;
    border: 1px solid #2264b8;
    min-height: 31px;
}
QPushButton#handoffButton:hover {
    background-color: #44b7ff;
    color: #001170;
}
QPushButton#handoffButton:disabled {
    color: #44b7ff;
    background-color: #ffffff;
    border-color: #44b7ff;
}
QToolButton {
    background-color: #ffffff;
    border: 1px solid #44b7ff;
    border-radius: 0;
    padding: 2px;
}
QToolButton:hover {
    background-color: #44b7ff;
    border-color: #2264b8;
}
QScrollBar:vertical {
    background: #f2f4f9;
    width: 5px;
    margin: 1px;
}
QScrollBar::handle:vertical {
    background: #2264b8;
    border-radius: 0;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover {
    background: #44b7ff;
}
QScrollBar::handle:vertical:pressed { background: #001170; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
    border: none;
}
QScrollBar:horizontal {
    background: #f2f4f9;
    height: 5px;
    margin: 1px;
}
QScrollBar::handle:horizontal {
    background: #2264b8;
    border-radius: 0;
    min-width: 28px;
}
QScrollBar::handle:horizontal:hover {
    background: #44b7ff;
}
QScrollBar::handle:horizontal:pressed { background: #001170; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: none;
    border: none;
}
QTextEdit#executionLog QScrollBar::handle:horizontal {
    background: #ffffff;
    border: 1px solid #44b7ff;
}
QTextEdit#executionLog QScrollBar::handle:horizontal:hover {
    background: #44b7ff;
    border-color: #2264b8;
}
QTextEdit#executionLog QScrollBar::handle:horizontal:pressed {
    background: #2264b8;
    border-color: #001170;
}
QSplitter::handle {
    background-color: #2264b8;
}
QSplitter::handle:hover {
    background-color: #001170;
}
QScrollArea {
    border: none;
    background-color: #ffffff;
}
QCheckBox {
    spacing: 7px;
    padding: 2px 0;
}
QLabel#secondaryHelp {
    color: #2264b8;
    font-size: 9pt;
    padding: 2px 0 4px 0;
}
QTextEdit#helpBody {
    border: none;
    border-left: 2px solid #44b7ff;
    padding: 8px 10px;
    color: #001170;
}
QGroupBox#helpSection {
    border-top: 1px solid #44b7ff;
    margin-top: 1.55em;
    padding: 13px 8px 8px 8px;
}
QGroupBox#helpSection::title {
    color: #001170;
    font-size: 12pt;
    font-weight: 700;
    padding: 0 8px 2px 0;
}
QLabel#helpSectionBody {
    color: #001170;
    background-color: #ffffff;
    padding: 2px 4px 4px 4px;
    font-size: 10pt;
}
QLabel#helpCallout, QLabel#settingsCallout, QLabel#configurationLockHint {
    color: #001170;
    background-color: #f2f4f9;
    border: none;
    border-left: 3px solid #44b7ff;
    padding: 8px 10px;
}
QLabel#configurationLockHint {
    font-size: 9pt;
    padding: 5px 8px;
}
QLabel#inlineGroupTitle {
    color: #001170;
    font-weight: 700;
    background-color: #ffffff;
}
QLabel#helpContentsLabel {
    color: #001170;
    font-size: 9pt;
    font-weight: 800;
    padding: 4px 8px 4px 0;
}
QToolButton#helpNavLink, QToolButton#guideLink {
    color: #2264b8;
    background-color: #ffffff;
    border: none;
    border-bottom: 1px solid #f2f4f9;
    padding: 3px 6px;
    font-weight: 600;
}
QToolButton#externalLink {
    background-color: transparent;
    border: none;
    padding: 2px;
}
QToolButton#externalLink:hover {
    background-color: #f2f4f9;
    border: none;
}
QToolButton#externalLink:pressed {
    background-color: #44b7ff;
    border: none;
}
QToolButton#helpNavLink:hover, QToolButton#guideLink:hover {
    color: #001170;
    background-color: #f2f4f9;
    border-bottom: 1px solid #44b7ff;
}
a { color: #2264b8; }
"""


def apply_phase_studio_style(app: object) -> None:
    """Apply the SharpED logo palette and Phase Studio visual system."""
    try:
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtGui import QColor, QPolygon
        from PySide6.QtWidgets import QProxyStyle, QStyle, QStyleFactory

        class PhaseStudioStyle(QProxyStyle):
            """Keep Fusion behavior while drawing crisp, theme-independent arrows."""

            def drawPrimitive(self, element, option, painter, widget=None):  # type: ignore[override]
                up_elements = {QStyle.PE_IndicatorArrowUp, QStyle.PE_IndicatorSpinUp}
                down_elements = {QStyle.PE_IndicatorArrowDown, QStyle.PE_IndicatorSpinDown}
                if element in up_elements or element in down_elements:
                    rect = option.rect
                    center = rect.center()
                    half_width = 4
                    half_height = 3
                    if element in up_elements:
                        points = QPolygon([
                            QPoint(center.x() - half_width, center.y() + half_height // 2),
                            QPoint(center.x() + half_width, center.y() + half_height // 2),
                            QPoint(center.x(), center.y() - half_height),
                        ])
                    else:
                        points = QPolygon([
                            QPoint(center.x() - half_width, center.y() - half_height // 2),
                            QPoint(center.x() + half_width, center.y() - half_height // 2),
                            QPoint(center.x(), center.y() + half_height),
                        ])
                    enabled = bool(option.state & QStyle.State_Enabled)
                    hovered = bool(option.state & QStyle.State_MouseOver)
                    color = "#2264b8" if hovered else ("#001170" if enabled else "#44b7ff")
                    painter.save()
                    painter.setRenderHint(painter.Antialiasing, True)
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QColor(color))
                    painter.drawPolygon(points)
                    painter.restore()
                    return
                super().drawPrimitive(element, option, painter, widget)

        base_style = QStyleFactory.create("Fusion")
        if base_style is not None:
            app.setStyle(PhaseStudioStyle(base_style))
    except Exception:
        pass

    try:
        from pathlib import Path

        assets = Path(__file__).resolve().parent / "assets"
        qss = _SHARPED_QSS.replace(
            "__PHASE_STUDIO_ARROW_UP_XPM__", assets.joinpath("arrow_up.xpm").as_posix()
        ).replace(
            "__PHASE_STUDIO_ARROW_DOWN_XPM__", assets.joinpath("arrow_down.xpm").as_posix()
        )
    except Exception:
        qss = _SHARPED_QSS
    app.setStyleSheet(qss)
