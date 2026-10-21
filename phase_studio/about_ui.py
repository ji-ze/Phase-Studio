"""Owned, branded application information with bundled legal authorities."""
from pathlib import Path
import sys

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QPushButton, QTextBrowser, QVBoxLayout,
)

from phase_studio import version
from phase_studio.ui_branding import (
    activate_owned_dialog, create_phase_studio_brand_header, fit_dialog_to_available_screen,
)

RELEASES_URL = 'https://github.com/ji-ze/Phase-Studio/releases'


def legal_directory() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / 'PhaseStudioLegal'
    return Path(__file__).resolve().parents[1]


class AboutDialog(QDialog):
    def __init__(self, parent, *, jana: bool):
        super().__init__(parent)
        self.setObjectName('phaseStudioAbout')
        self.setWindowTitle('About Phase Studio')
        self.setWindowModality(Qt.WindowModal)
        self.setStyleSheet('QDialog#phaseStudioAbout {background:white;}')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)
        header = create_phase_studio_brand_header()
        header.findChild(QLabel, 'versionBadge').hide()
        layout.addWidget(header)
        self.version_label = QLabel('Version ' + version.VERSION)
        layout.addWidget(self.version_label)
        description = QLabel('Crystallographic structure solution and electron-density processing '
                             'with Superflip, SharpED and EDMA.')
        description.setWordWrap(True)
        layout.addWidget(description)
        self.mode_label = QLabel('Jana2020 integration' if jana else 'Standalone application')
        layout.addWidget(self.mode_label)
        releases = QPushButton('Official GitHub Releases')
        releases.setToolTip(RELEASES_URL)
        releases.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(RELEASES_URL)))
        layout.addWidget(releases)
        self.credits_button = QPushButton('Licenses and credits')
        self.credits_button.setCheckable(True)
        layout.addWidget(self.credits_button)
        self.credits = QTextBrowser()
        self.credits.setMinimumHeight(120)
        self.credits.setOpenExternalLinks(False)
        # Read the existing notices verbatim; do not maintain a second set of
        # authors, license terms or bibliographic assertions in the UI.
        notices = []
        for name in ('AUTHORS.md', 'LICENSE', 'CITATION.cff', 'THIRD_PARTY_NOTICES.md'):
            path = legal_directory() / name
            notices.append(name + '\n\n' + (path.read_text(encoding='utf8') if path.is_file()
                                           else 'Bundled notice unavailable: ' + name))
        self.credits.setPlainText('\n\n'.join(notices))
        self.credits.hide()
        layout.addWidget(self.credits)
        self.credits_button.toggled.connect(self._toggle_credits)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _toggle_credits(self, checked):
        self.credits.setVisible(checked)
        self._fit()

    def _fit(self):
        self.layout().activate()
        fit_dialog_to_available_screen(self, QSize(460, 510 if self.credits.isVisible() else 360))

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._fit)
        QTimer.singleShot(0, lambda: activate_owned_dialog(self))


def show_about_dialog(parent, *, jana: bool = False):
    """One modal child per owner; repeated actions raise the existing child."""
    dialog = getattr(parent, '_phase_studio_about', None)
    if dialog is not None and dialog.isVisible():
        activate_owned_dialog(dialog)
        return dialog
    if dialog is not None:
        dialog.deleteLater()
    dialog = AboutDialog(parent, jana=jana)
    parent._phase_studio_about = dialog
    dialog.finished.connect(lambda _result: activate_owned_dialog(parent) if parent.isVisible() else None)
    dialog.open()
    return dialog
