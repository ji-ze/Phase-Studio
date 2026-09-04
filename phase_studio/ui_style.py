from __future__ import annotations


CONTROL_ARROW_BUTTON_WIDTH = 26
CONTROL_ARROW_WIDTH = 8.0
CONTROL_ARROW_HEIGHT = 4.0
CONTROL_ARROW_STROKE_WIDTH = 1.5


_SHARPED_QSS = """
QWidget {
    background-color: #ffffff;
    color: #14204a;
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
    border-top: 1px solid #dce5f2;
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
    font-size: 10pt;
    font-weight: 600;
}
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #ffffff;
    color: #14204a;
    border: none;
    border-bottom: 1px solid #cbd7ea;
    border-radius: 0;
    padding: 4px 6px;
    min-height: 22px;
    selection-background-color: #44b7ff;
}
QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover,
QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {
    border-bottom-color: #8fb6da;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: none;
    border-bottom: 2px solid #2264b8;
}
QSpinBox, QDoubleSpinBox {
    padding-right: 29px;
}
QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 25px;
    background-color: #f2f4f9;
    border: none;
    border-left: 1px solid #cbd7ea;
    border-bottom: 1px solid #cbd7ea;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 25px;
    background-color: #f2f4f9;
    border: none;
    border-left: 1px solid #cbd7ea;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: #e2f4ff;
}
QSpinBox::up-button:pressed, QSpinBox::down-button:pressed,
QDoubleSpinBox::up-button:pressed, QDoubleSpinBox::down-button:pressed {
    background-color: #c8eaff;
}
QComboBox {
    padding-right: 29px;
}
QComboBox::drop-down {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 25px;
    background-color: #f2f4f9;
    border: none;
    border-left: 1px solid #cbd7ea;
}
QComboBox::drop-down:hover {
    background-color: #e2f4ff;
}
QComboBox::drop-down:pressed, QComboBox::drop-down:on {
    background-color: #c8eaff;
}
QWidget#phaseStudioArrowOverlay {
    background-color: transparent;
    border: none;
}
QWidget#settingsPage QLineEdit,
QWidget#settingsPage QSpinBox,
QWidget#settingsPage QDoubleSpinBox,
QWidget#settingsPage QComboBox {
    min-height: 21px;
    padding-top: 3px;
    padding-bottom: 3px;
}
QWidget#settingsPage QLineEdit[metadataInvalid="true"] {
    border-bottom: 2px solid #001170;
    background-color: #e2f4ff;
}
QWidget#settingsPage QSpinBox,
QWidget#settingsPage QDoubleSpinBox {
    min-height: 22px;
    max-height: 22px;
    padding-top: 2px;
    padding-bottom: 3px;
    padding-right: 29px;
}
QWidget#settingsPage QComboBox {
    padding-right: 29px;
}
QWidget#settingsPage QPushButton {
    min-height: 21px;
    padding: 3px 10px;
}
QPushButton#pathBrowseButton {
    min-height: 21px;
    padding: 3px 0;
    color: #001170;
    background-color: #f2f4f9;
    border: none;
    border-left: 1px solid #cbd7ea;
    border-bottom: 1px solid #cbd7ea;
}
QPushButton#pathBrowseButton:hover {
    color: #2264b8;
    background-color: #e2f4ff;
    border-left-color: #cbd7ea;
    border-bottom-color: #8fb6da;
}
QPushButton#pathBrowseButton:pressed {
    color: #001170;
    background-color: #c8eaff;
}
QPushButton#pathBrowseButton:disabled {
    color: #8794ad;
    background-color: #e7ecf3;
    border-left-color: #cbd7ea;
    border-bottom-color: #cbd7ea;
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
    color: #7183a6;
    background-color: #f5f7fa;
    border-color: #cbd7ea;
}
QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled,
QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {
    color: #8794ad;
    background-color: #f1f4f8;
    border-bottom-color: #cbd7ea;
}
QLabel:disabled, QCheckBox:disabled {
    color: #8794ad;
}
QLineEdit[configurationLocked="true"]:disabled,
QTextEdit[configurationLocked="true"]:disabled,
QPlainTextEdit[configurationLocked="true"]:disabled,
QSpinBox[configurationLocked="true"]:disabled,
QDoubleSpinBox[configurationLocked="true"]:disabled,
QComboBox[configurationLocked="true"]:disabled {
    /* A locked-during-RUNNING value must stay comfortably readable -- this
       is the configuration actively being used, not a genuinely irrelevant
       field -- while remaining clearly lower-contrast than an enabled
       control. Medium-muted navy rather than the near-invisible gray a
       plain :disabled state would give it. */
    color: #3d4d73;
    background-color: #edf2f8;
    border-bottom-color: #aebdd2;
}
QLabel[configurationLocked="true"]:disabled,
QCheckBox[configurationLocked="true"]:disabled {
    color: #4f5f87;
}
QSpinBox:disabled::up-button, QSpinBox:disabled::down-button,
QDoubleSpinBox:disabled::up-button, QDoubleSpinBox:disabled::down-button,
QComboBox:disabled::drop-down {
    background-color: #e7ecf3;
    border-left-color: #cbd7ea;
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
    border-bottom: 1px solid #cbd7ea;
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
#sectionTabs > QTabBar::tab {
    padding: 3px 12px;
}
#categoryTabs > QTabBar::tab {
    background-color: #f7f9fc;
    color: #14204a;
    border: 1px solid #cbd7ea;
    padding: 7px 24px;
    font-weight: 700;
}
#categoryTabs > QTabBar::tab:selected {
    background-color: #001170;
    color: #ffffff;
    border: 1px solid #001170;
}
QGroupBox#settingsGroup {
    border-top: 1px solid #dce5f2;
    margin-top: 1.05em;
    padding: 8px 8px 6px 8px;
}
QGroupBox#guidedSettingsGroup {
    border-top: 1px solid #dce5f2;
    margin-top: 0;
    padding: 6px 8px 6px 8px;
}
QGroupBox#settingsGroup[tightTop="true"] {
    margin-top: 0.6em;
}
QHeaderView::section {
    background-color: #f2f4f9;
    color: #001170;
    border: 1px solid #cbd7ea;
    padding: 7px;
    font-weight: 700;
}
QTableWidget, QTreeWidget, QListWidget {
    background-color: #ffffff;
    alternate-background-color: #ffffff;
    gridline-color: #dce5f2;
    border: 1px solid #cbd7ea;
}
QToolTip {
    background-color: #f2f4f9;
    color: #001170;
    border: 1px solid #2264b8;
    padding: 4px;
}
QProgressBar {
    border: none;
    border-bottom: 1px solid #cbd7ea;
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
QLabel#progressSectionLabel {
    color: #14204a;
    font-size: 8.5pt;
    font-weight: 600;
    letter-spacing: 0;
    padding: 0;
}
QLabel#progressStageCounter {
    color: #52658b;
    font-size: 8pt;
    font-weight: 700;
}
QLabel#currentCycleDetail {
    color: #52658b;
    background-color: transparent;
    border: none;
    padding: 1px 0;
    font-size: 8.5pt;
    font-weight: 600;
}
QProgressBar#currentCycleProgress {
    min-height: 7px;
    max-height: 7px;
    border: none;
    background-color: #f2f4f9;
}
QProgressBar#currentCycleProgress::chunk {
    background-color: #44b7ff;
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
    color: #52658b;
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
    border: 1px solid #8fb6da;
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
QLabel#structureRotationHint {
    color: #7183a6;
    font-size: 8pt;
    padding: 0 3px 0 0;
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
    border-top: 1px solid #cbd7ea;
    border-radius: 0;
    padding: 5px 9px;
    background-color: #ffffff;
    color: #14204a;
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
    color: #8794ad;
    background-color: #f7f9fc;
    border-color: #cbd7ea;
}
QPushButton#continueButton {
    color: #2264b8;
    background-color: #ffffff;
    border: 1px solid #2264b8;
    min-height: 31px;
}
QPushButton#continueButton:hover {
    background-color: #44b7ff;
    color: #001170;
}
QPushButton#continueButton:disabled {
    color: #8794ad;
    background-color: #f7f9fc;
    border-color: #cbd7ea;
}
QPushButton#stopAfterButton {
    color: #52658b;
    background-color: #ffffff;
    border-color: #aebdd2;
    font-weight: 600;
}
QPushButton#stopAfterButton:hover {
    color: #001170;
    background-color: #f2f4f9;
    border-color: #8fb6da;
}
QPushButton#stopNowButton:enabled {
    color: #001170;
    background-color: #edf3fa;
    border-color: #2264b8;
    font-weight: 700;
}
QPushButton#stopNowButton:enabled:hover {
    color: #ffffff;
    background-color: #2264b8;
}
QPushButton#clearButton {
    color: #7183a6;
    background-color: #ffffff;
    border-color: #cbd7ea;
    font-weight: 500;
}
QPushButton#clearButton:hover {
    color: #14204a;
    background-color: #f7f9fc;
    border-color: #8fb6da;
}
QWidget#runStatusPanel {
    background-color: #f8fafc;
    border: 1px solid #dce5f2;
}
QWidget#runStatusPanel QLabel {
    background-color: transparent;
}
QWidget#runStatusPanel QProgressBar {
    background-color: #edf2f8;
}
QLabel#runStatusTitle {
    color: #001170;
    background-color: transparent;
    font-size: 8.5pt;
    font-weight: 800;
    letter-spacing: 1px;
}
QToolButton {
    background-color: #ffffff;
    border: 1px solid #cbd7ea;
    border-radius: 0;
    padding: 2px;
}
QToolButton:hover {
    background-color: #44b7ff;
    border-color: #2264b8;
}
QToolButton#disclosureToggle {
    background-color: #ffffff;
    border: 1px solid #cbd7ea;
    padding: 4px 8px;
    color: #001170;
    font-weight: 600;
    text-align: left;
}
QToolButton#disclosureToggle:hover {
    background-color: #f2f4f9;
    border-color: #2264b8;
}
QToolButton#disclosureToggle:checked {
    background-color: #edf3fa;
    border-color: #2264b8;
}
QFrame#workflowCard {
    background-color: #ffffff;
    border: 1px solid #cbd7ea;
    border-radius: 3px;
}
QFrame#workflowCard:hover {
    background-color: #f5f9ff;
}
QFrame#workflowCard[selected="true"] {
    background-color: #edf3fa;
    border: 1px solid #2264b8;
}
QFrame#workflowCard[selected="true"]:hover {
    background-color: #edf3fa;
}
QFrame#workflowCard QLabel {
    background-color: transparent;
}
QLabel#workflowCardDescription {
    color: #52658b;
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
    border: 1px solid #cbd7ea;
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
    background-color: #cbd7ea;
}
QSplitter::handle:hover {
    background-color: #8fb6da;
}
QSplitter#mainSplitter::handle {
    background-color: #cbd7ea;
}
QSplitter#mainSplitter::handle:hover {
    background-color: #8fb6da;
}
QScrollArea {
    border: none;
    background-color: #ffffff;
}
QCheckBox {
    spacing: 7px;
    padding: 2px 0;
}
QWidget#settingsPage QCheckBox {
    padding: 1px 0;
}
QLabel#secondaryHelp {
    color: #52658b;
    font-size: 9pt;
    padding: 1px 0 2px 0;
}
QTextEdit#helpBody {
    border: none;
    border-left: 2px solid #cbd7ea;
    padding: 8px 10px;
    color: #14204a;
}
QGroupBox#helpSection {
    border-top: 1px solid #cbd7ea;
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
    color: #14204a;
    background-color: #ffffff;
    padding: 2px 4px 4px 4px;
    font-size: 10pt;
}
QLabel#helpCallout, QLabel#settingsCallout, QLabel#configurationLockHint {
    color: #14204a;
    background-color: #f2f4f9;
    border: none;
    border-left: 3px solid #8fb6da;
    padding: 8px 10px;
}
QLabel#helpCallout[calloutKind="warning"], QLabel#settingsCallout[calloutKind="warning"] {
    background-color: #e7f0fb;
    border-left: 4px solid #2264b8;
}
QLabel#helpCallout[calloutKind="tip"], QLabel#settingsCallout[calloutKind="tip"] {
    background-color: #f7f9fc;
    border-left: 2px solid #b7cbe8;
}
QWidget#metadataErrorPanel {
    background-color: #f7f9fc;
    border: none;
    border-left: 3px solid #8fb6da;
}
QLabel#metadataErrorText {
    color: #14204a;
    background-color: transparent;
    font-size: 9pt;
}
QToolButton#metadataErrorDetails {
    color: #2264b8;
    background-color: transparent;
    border: none;
    border-bottom: 1px solid #cbd7ea;
    padding: 1px 3px;
}
QLabel#settingsCallout {
    padding: 6px 8px;
}
QLabel#settingsCallout[compactPadding="true"] {
    padding: 3px 8px;
}
QLabel#configurationLockHint {
    font-size: 9pt;
    padding: 5px 8px;
}
QLabel#pageHeading {
    color: #001170;
    font-size: 12pt;
    font-weight: 700;
    background-color: #ffffff;
}
QFrame#pageHeadingRule {
    background-color: #2264b8;
    border: none;
}
QLabel#inlineGroupTitle {
    color: #001170;
    font-size: 10pt;
    font-weight: 600;
    background-color: #ffffff;
}
QLabel#helpContentsLabel {
    color: #001170;
    font-size: 9pt;
    font-weight: 800;
    padding: 2px 8px 2px 0;
}
QToolButton#helpNavLink, QToolButton#guideLink, QToolButton#settingsNavLink {
    color: #2264b8;
    background-color: #ffffff;
    border: none;
    border-bottom: 1px solid #f2f4f9;
    padding: 2px 6px;
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
    background-color: #e2f4ff;
    border: none;
}
QToolButton#helpNavLink:hover, QToolButton#guideLink:hover, QToolButton#settingsNavLink:hover {
    color: #001170;
    background-color: #f2f4f9;
    border-bottom: 1px solid #44b7ff;
}
QWidget#diagnosticHeader {
    background-color: #001170;
    border: none;
    border-bottom: 1px solid #8fb6da;
}
QLabel#diagnosticTitle {
    color: #ffffff;
    background-color: #001170;
    font-size: 13pt;
    font-weight: 800;
    letter-spacing: 1px;
}
QLabel#diagnosticSubtitle {
    color: #b9dcf3;
    background-color: #001170;
    font-size: 9pt;
    font-weight: 600;
}
QLabel#diagnosticStatus {
    color: #001170;
    background-color: #f2f4f9;
    border: 1px solid #8fb6da;
    padding: 4px 10px;
    min-width: 58px;
    font-size: 9pt;
    font-weight: 800;
}
QGroupBox#diagnosticSection {
    border-top: 1px solid #cbd7ea;
    margin-top: 1.25em;
    padding: 10px 6px 5px 6px;
}
QGroupBox#diagnosticSection[summaryDensity="compact"] {
    margin-top: 1.05em;
    padding: 3px 4px 1px 4px;
}
QGroupBox#diagnosticSection::title,
QLabel#diagnosticSectionTitle {
    color: #2264b8;
    background-color: #ffffff;
    font-size: 9pt;
    font-weight: 800;
    letter-spacing: 1px;
}
QLabel#diagnosticSummaryValue {
    color: #001170;
    background-color: #ffffff;
}
QToolButton#diagnosticTextAction {
    color: #2264b8;
    background-color: transparent;
    border: none;
    border-bottom: 1px solid #f2f4f9;
    padding: 2px 4px;
    font-size: 9pt;
}
QToolButton#diagnosticTextAction:hover {
    color: #001170;
    background-color: #f2f4f9;
    border-bottom: 1px solid #44b7ff;
}
QWidget#diagnosticMetric {
    background-color: #f7f9fc;
    border: none;
    border-top: 1px solid #8fb6da;
}
QLabel#diagnosticMetricValue {
    color: #001170;
    background-color: #f7f9fc;
    font-size: 12pt;
    font-weight: 800;
}
QLabel#diagnosticMetricLabel {
    color: #52658b;
    background-color: #f7f9fc;
    font-size: 8.5pt;
    font-weight: 600;
}
QWidget#diagnosticMetric[metricDensity="compact"] {
    background-color: #fbfcfe;
    border-top: 1px solid #cbd7ea;
}
QWidget#diagnosticMetric[metricDensity="compact"] QLabel#diagnosticMetricValue {
    background-color: #fbfcfe;
    font-size: 11pt;
}
QWidget#diagnosticMetric[metricDensity="compact"] QLabel#diagnosticMetricLabel {
    background-color: #fbfcfe;
    color: #52658b;
    font-size: 8pt;
}
QLabel#diagnosticMeta {
    color: #52658b;
    font-size: 8.5pt;
}
QTableWidget#diagnosticTable {
    border: 1px solid #f2f4f9;
    gridline-color: #f2f4f9;
    alternate-background-color: #f7f9fc;
    selection-background-color: #44b7ff;
    selection-color: #001170;
}
QTableWidget#diagnosticTable QHeaderView::section {
    background-color: #f2f4f9;
    color: #001170;
    border: none;
    border-bottom: 1px solid #cbd7ea;
    padding: 6px;
}
QPushButton#diagnosticSecondaryButton {
    background-color: #ffffff;
    color: #2264b8;
    border-color: #8fb6da;
    font-weight: 600;
}
QPushButton#diagnosticSecondaryButton:hover {
    background-color: #f2f4f9;
    color: #001170;
}
QPushButton#metricsControlButton {
    background-color: #ffffff;
    color: #2264b8;
    border: 1px solid #cbd7ea;
    border-radius: 0;
    padding: 1px 8px;
    min-height: 17px;
    font-size: 7.7pt;
    font-weight: 600;
}
QPushButton#metricsControlButton:hover {
    background-color: #f2f4f9;
    border-color: #2264b8;
    color: #001170;
}
QPushButton#metricsViewToggle {
    background-color: #ffffff;
    color: #52658b;
    border: 1px solid #cbd7ea;
    border-radius: 0;
    padding: 1px 8px;
    min-height: 17px;
    font-size: 7.7pt;
    font-weight: 600;
}
QPushButton#metricsViewToggle:hover {
    border-color: #2264b8;
    color: #001170;
}
QPushButton#metricsViewToggle:checked {
    background-color: #edf3fa;
    border-color: #2264b8;
    color: #001170;
}
QPushButton#metricsViewToggle:disabled {
    color: #b7c2d9;
    border-color: #e3e9f3;
    background-color: #f7f9fc;
}
QLabel#metricsHintLabel {
    color: #9aa8c2;
    font-size: 7.3pt;
    font-style: italic;
}
QSplitter#diagnosticSplitter::handle {
    background-color: #cbd7ea;
}
QDialog#phaseStudioErrorDialog {
    background-color: #ffffff;
}
QWidget#errorDialogHeader {
    background-color: #001170;
    border-bottom: 1px solid #8fb6da;
}
QLabel#errorDialogEyebrow {
    color: #b9dcf3;
    background-color: #001170;
    font-size: 8pt;
    font-weight: 700;
    letter-spacing: 1px;
}
QLabel#errorDialogTitle {
    color: #ffffff;
    background-color: #001170;
    font-size: 13pt;
    font-weight: 800;
}
QWidget#errorDialogBody {
    background-color: #ffffff;
}
QLabel#errorDialogSectionLabel {
    color: #52658b;
    background-color: transparent;
    font-size: 8pt;
    font-weight: 800;
    letter-spacing: 1px;
}
QLabel#errorDialogSummary, QLabel#errorDialogGuidance {
    color: #14204a;
    background-color: transparent;
}
QPlainTextEdit#errorDialogDetails {
    color: #14204a;
    background-color: #f7f9fc;
    border: 1px solid #cbd7ea;
    padding: 7px;
    font-size: 8.5pt;
}
QPushButton#errorPrimaryAction {
    color: #ffffff;
    background-color: #001170;
    border-color: #001170;
}
QPushButton#errorAction, QPushButton#errorDetailsButton,
QPushButton#errorCopyButton, QPushButton#errorCloseButton {
    color: #52658b;
    background-color: #ffffff;
    border-color: #cbd7ea;
    font-weight: 600;
}
QSplashScreen#phaseStudioSplash {
    background-color: #ffffff;
    border: 1px solid #cbd7ea;
    border-radius: 4px;
}
QLabel#splashTitle {
    color: #001170;
    background-color: transparent;
    font-size: 19pt;
    font-weight: 800;
}
QLabel#splashSubtitle {
    color: #52658b;
    background-color: transparent;
    font-size: 9.5pt;
    font-weight: 600;
}
QLabel#splashStatus {
    color: #14204a;
    background-color: transparent;
    font-size: 9.5pt;
}
QLabel#splashFooter {
    color: #8794ad;
    background-color: transparent;
    font-size: 8.5pt;
}
QLabel#splashLogo {
    background-color: transparent;
}
QProgressBar#splashProgress {
    min-height: 4px;
    max-height: 4px;
    background-color: #edf2f8;
    border: none;
}
QProgressBar#splashProgress::chunk {
    background-color: #2264b8;
}
a { color: #2264b8; }
"""


_TOOLTIP_WRAP_PREFIX = '<div style="max-width:'


def _wrap_tooltip_html(text: str, max_width: int = 380) -> str:
    """Cap a tooltip's rendered width. A plain-text QToolTip never wraps, so
    a single long sentence can otherwise span most of the screen; wrapping
    it as rich text inside a width-capped div fixes that regardless of how
    long the underlying sentence is. Blank-line-separated parts (e.g. a
    PathRow's description plus its live "Path: ..." line) become separate
    paragraphs; ordinary internal whitespace/newlines within each part
    collapse to a single space, matching plain-text tooltip conventions.
    Already-wrapped text (e.g. a tooltip copied from one widget to another
    via .toolTip()) is returned unchanged rather than wrapped again."""
    if text.startswith(_TOOLTIP_WRAP_PREFIX):
        return text
    import html as _html
    parts = [part.strip() for part in text.split("\n\n") if part.strip()]
    if not parts:
        return ""
    body = "<br><br>".join(_html.escape(" ".join(part.split())) for part in parts)
    return f'{_TOOLTIP_WRAP_PREFIX}{max_width}px;">{body}</div>'


def _install_tooltip_width_cap(app: object) -> None:
    """Monkey-patch QWidget.setToolTip once per process so every tooltip set
    anywhere in the app -- present call sites and any added later -- is
    automatically capped to a readable width, instead of auditing and
    wrapping each call site by hand. Idempotent: safe if
    apply_phase_studio_style() runs more than once in the same process."""
    from PySide6.QtWidgets import QWidget

    if getattr(QWidget.setToolTip, "_phase_studio_wraps_tooltips", False):
        return
    original_set_tooltip = QWidget.setToolTip

    def _phase_studio_set_tooltip(self, text=""):
        original_set_tooltip(self, _wrap_tooltip_html(str(text or "")))

    _phase_studio_set_tooltip._phase_studio_wraps_tooltips = True
    QWidget.setToolTip = _phase_studio_set_tooltip


def apply_phase_studio_style(app: object) -> None:
    """Apply the SharpED logo palette and Phase Studio visual system."""
    try:
        _install_tooltip_width_cap(app)
    except Exception:
        pass
    try:
        from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, Qt
        from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
        from PySide6.QtWidgets import QAbstractSpinBox, QComboBox, QProxyStyle, QStyle, QStyleFactory, QWidget

        class PhaseStudioStyle(QProxyStyle):
            """Keep Fusion behavior while drawing crisp, theme-independent arrows."""

            @staticmethod
            def _draw_chevron(painter, rect, *, up: bool, enabled: bool, hovered: bool, pressed: bool) -> None:
                logical_rect = QRectF(rect)
                center = logical_rect.center()
                half_width = CONTROL_ARROW_WIDTH / 2.0
                half_height = CONTROL_ARROW_HEIGHT / 2.0
                path = QPainterPath()
                if up:
                    path.moveTo(QPointF(center.x() - half_width, center.y() + half_height))
                    path.lineTo(QPointF(center.x(), center.y() - half_height))
                    path.lineTo(QPointF(center.x() + half_width, center.y() + half_height))
                else:
                    path.moveTo(QPointF(center.x() - half_width, center.y() - half_height))
                    path.lineTo(QPointF(center.x(), center.y() + half_height))
                    path.lineTo(QPointF(center.x() + half_width, center.y() - half_height))
                color = "#8794ad" if not enabled else ("#001170" if pressed else ("#2264b8" if hovered else "#001170"))
                pen = QPen(QColor(color), CONTROL_ARROW_STROKE_WIDTH)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.save()
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(path)
                painter.restore()

            def drawPrimitive(self, element, option, painter, widget=None):  # type: ignore[override]
                up_elements = {QStyle.PE_IndicatorArrowUp, QStyle.PE_IndicatorSpinUp}
                down_elements = {QStyle.PE_IndicatorArrowDown, QStyle.PE_IndicatorSpinDown}
                if element in up_elements or element in down_elements:
                    enabled = bool(option.state & QStyle.State_Enabled)
                    hovered = bool(option.state & QStyle.State_MouseOver)
                    pressed = bool(option.state & (QStyle.State_Sunken | QStyle.State_On))
                    self._draw_chevron(
                        painter,
                        QRectF(option.rect),
                        up=element in up_elements,
                        enabled=enabled,
                        hovered=hovered,
                        pressed=pressed,
                    )
                    return
                super().drawPrimitive(element, option, painter, widget)

        base_style = QStyleFactory.create("Fusion")
        if base_style is not None:
            app.setStyle(PhaseStudioStyle(base_style))

        class ControlArrowOverlay(QWidget):
            """Paint one canonical vector chevron family above styled Qt subcontrols."""

            def __init__(self, owner) -> None:
                super().__init__(owner)
                self.owner = owner
                self.hovered_part = ""
                self.pressed_part = ""
                self.setObjectName("phaseStudioArrowOverlay")
                self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
                self.setAutoFillBackground(False)

            def arrow_rects(self):
                full_rect = QRectF(0.0, 0.0, float(self.width()), float(self.height()))
                if isinstance(self.owner, QComboBox):
                    return (("down", full_rect, False),)
                half_height = full_rect.height() / 2.0
                return (
                    ("up", QRectF(0.0, 0.0, full_rect.width(), half_height), True),
                    ("down", QRectF(0.0, half_height, full_rect.width(), half_height), False),
                )

            def _background_for(self, part: str, enabled: bool) -> str:
                if not enabled:
                    return "#e7ecf3"
                if self.pressed_part == part:
                    return "#c8eaff"
                if self.hovered_part == part:
                    return "#e2f4ff"
                return "#f2f4f9"

            def paintEvent(self, event) -> None:  # type: ignore[override]
                del event
                painter = QPainter(self)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                enabled = self.owner.isEnabled()
                parts = self.arrow_rects()
                for part, rect, _up in parts:
                    painter.fillRect(rect, QColor(self._background_for(part, enabled)))
                separator_pen = QPen(QColor("#cbd7ea"), 1.0)
                painter.setPen(separator_pen)
                painter.drawLine(QPointF(0.5, 0.0), QPointF(0.5, float(self.height())))
                if len(parts) == 2:
                    midpoint = float(self.height()) / 2.0
                    painter.drawLine(QPointF(0.5, midpoint), QPointF(float(self.width()), midpoint))
                bottom_color = "#2264b8" if self.owner.hasFocus() else ("#8fb6da" if self.owner.underMouse() else "#cbd7ea")
                bottom_width = 2.0 if self.owner.hasFocus() else 1.0
                bottom_pen = QPen(QColor(bottom_color), bottom_width)
                painter.setPen(bottom_pen)
                painter.drawLine(
                    QPointF(0.0, float(self.height()) - bottom_width / 2.0),
                    QPointF(float(self.width()), float(self.height()) - bottom_width / 2.0),
                )
                for part, rect, up in parts:
                    PhaseStudioStyle._draw_chevron(
                        painter,
                        rect,
                        up=up,
                        enabled=enabled,
                        hovered=self.hovered_part == part,
                        pressed=self.pressed_part == part,
                    )

        class ControlArrowFilter(QObject):
            """Attach and synchronize transparent arrow overlays application-wide."""

            @staticmethod
            def _is_control(widget) -> bool:
                return isinstance(widget, (QComboBox, QAbstractSpinBox))

            def _ensure_overlay(self, owner):
                overlay = getattr(owner, "_phase_studio_arrow_overlay", None)
                if overlay is None or not hasattr(overlay, "hovered_part"):
                    overlay = ControlArrowOverlay(owner)
                    owner._phase_studio_arrow_overlay = overlay
                    owner.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
                    owner.setMouseTracking(True)
                button_width = min(CONTROL_ARROW_BUTTON_WIDTH, owner.width())
                overlay.setGeometry(owner.width() - button_width, 0, button_width, owner.height())
                overlay.setVisible(owner.isVisible())
                overlay.raise_()
                return overlay

            @staticmethod
            def _part_at(owner, position) -> str:
                if position.x() < owner.width() - CONTROL_ARROW_BUTTON_WIDTH:
                    return ""
                if isinstance(owner, QComboBox):
                    return "down"
                return "up" if position.y() < owner.height() / 2.0 else "down"

            def eventFilter(self, watched, event):  # type: ignore[override]
                if not self._is_control(watched):
                    return False
                event_type = event.type()
                if event_type in {
                    QEvent.Type.Polish,
                    QEvent.Type.Show,
                    QEvent.Type.Resize,
                    QEvent.Type.EnabledChange,
                    QEvent.Type.StyleChange,
                }:
                    self._ensure_overlay(watched).update()
                elif event_type in {QEvent.Type.HoverMove, QEvent.Type.MouseMove}:
                    overlay = self._ensure_overlay(watched)
                    position = event.position()
                    part = self._part_at(watched, position)
                    if overlay.hovered_part != part:
                        overlay.hovered_part = part
                        overlay.update()
                elif event_type == QEvent.Type.MouseButtonPress:
                    overlay = self._ensure_overlay(watched)
                    overlay.pressed_part = self._part_at(watched, event.position())
                    overlay.update()
                elif event_type == QEvent.Type.MouseButtonRelease:
                    overlay = self._ensure_overlay(watched)
                    overlay.pressed_part = ""
                    overlay.hovered_part = self._part_at(watched, event.position())
                    overlay.update()
                elif event_type in {QEvent.Type.Leave, QEvent.Type.Hide}:
                    overlay = self._ensure_overlay(watched)
                    overlay.hovered_part = ""
                    overlay.pressed_part = ""
                    overlay.update()
                return False

        previous_filter = getattr(app, "_phase_studio_control_arrow_filter", None)
        if previous_filter is not None:
            app.removeEventFilter(previous_filter)
        arrow_filter = ControlArrowFilter(app)
        app._phase_studio_control_arrow_filter = arrow_filter
        app.installEventFilter(arrow_filter)
        for existing_widget in app.allWidgets():
            if arrow_filter._is_control(existing_widget):
                arrow_filter._ensure_overlay(existing_widget)
    except Exception:
        pass

    app.setStyleSheet(_SHARPED_QSS)
