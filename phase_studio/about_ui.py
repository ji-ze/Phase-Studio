"""Owned, branded application information with bundled legal authorities."""
from pathlib import Path
import sys

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QTextDocument
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QPushButton, QTextBrowser, QVBoxLayout,
    QTabWidget, QLineEdit, QHBoxLayout, QApplication, QWidget, QComboBox,
)

from phase_studio import version
from phase_studio.ui_branding import (
    activate_owned_dialog, create_phase_studio_brand_header, fit_dialog_to_available_screen,
)

from phase_studio.legal_content import legal_directory, source_text, overview_html, citation_text
RELEASES_URL = 'https://github.com/ji-ze/Phase-Studio/releases'


class LegalBrowser(QTextBrowser):
    def loadResource(self, resource_type, url):
        # Legal text may contain links, but never fetch embedded remote or local resources.
        return None

    def __init__(self):
        super().__init__()
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.anchorClicked.connect(self._open_link)

    def _open_link(self, url):
        if url.scheme().lower() in ('https', 'mailto'):
            QDesktopServices.openUrl(url)


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
        self.tabs = QTabWidget()
        self.tabs.setUsesScrollButtons(True)
        layout.addWidget(self.tabs, 1)
        self.documents = []
        def add(title, text, markdown=False, html=False):
            browser = LegalBrowser()
            if markdown:
                browser.document().setMarkdown(text, QTextDocument.MarkdownDialectGitHub | QTextDocument.MarkdownNoHTML)
            elif html:
                browser.setHtml(text)
            else:
                browser.setPlainText(text)
            self.documents.append(browser)
            self.tabs.addTab(browser, title)
            return browser
        add('About & Contacts', overview_html(version.VERSION), html=True)
        add('Authors & Acknowledgements', source_text('AUTHORS.md'), markdown=True)
        self.credits = add('License', source_text('LICENSE'))
        third_party = add('Third-party Licenses', source_text('THIRD_PARTY_NOTICES.md'), markdown=True)
        add('Citation', citation_text(version.VERSION) + '\n\nRaw CITATION.cff source:\n\n' + source_text('CITATION.cff'))
        notice_roots = ([legal_directory() / 'dependencies', legal_directory() / 'upstream']
                        if getattr(sys, 'frozen', False) else [legal_directory() / 'third_party_licenses'])
        notice_page = QWidget()
        notice_layout = QVBoxLayout(notice_page)
        self.notice_selector = QComboBox()
        self.notice_selector.addItem('Third-party overview', None)
        for notices in notice_roots:
            if notices.is_dir():
                for path in sorted(notices.rglob('*')):
                    if path.is_file():
                        self.notice_selector.addItem(path.relative_to(notices).as_posix(), str(path))
        notice_layout.addWidget(self.notice_selector)
        notice_layout.addWidget(third_party,1)
        self.tabs.removeTab(3)
        self.tabs.insertTab(3,notice_page,'Third-party Licenses')
        def select_notice():
            path = self.notice_selector.currentData()
            if path:
                third_party.setPlainText(Path(path).read_text(encoding='utf8',errors='replace'))
            else:
                third_party.document().setMarkdown(source_text('THIRD_PARTY_NOTICES.md'), QTextDocument.MarkdownDialectGitHub | QTextDocument.MarkdownNoHTML)
        self.notice_selector.currentIndexChanged.connect(select_notice)
        tools = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('Find in current document')
        tools.addWidget(self.search, 1)
        find = QPushButton('Find next')
        find.clicked.connect(self.find_next)
        self.search.returnPressed.connect(self.find_next)
        tools.addWidget(find)
        copy = QPushButton('Copy document')
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self.current_browser().toPlainText()))
        tools.addWidget(copy)
        original = QPushButton('Open original')
        def open_original():
            names = ('AUTHORS.md','AUTHORS.md','LICENSE','THIRD_PARTY_NOTICES.md','CITATION.cff')
            selected = self.notice_selector.currentData() if self.tabs.currentIndex()==3 else None
            path = Path(selected) if selected else legal_directory()/names[self.tabs.currentIndex()]
            if path.is_file(): QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        original.clicked.connect(open_original)
        tools.addWidget(original)
        layout.addLayout(tools)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def find_next(self):
        browser = self.current_browser()
        if not browser.find(self.search.text()):
            cursor = browser.textCursor()
            cursor.movePosition(cursor.Start)
            browser.setTextCursor(cursor)
            browser.find(self.search.text())

    def current_browser(self):
        return self.documents[self.tabs.currentIndex()]

    def _fit(self):
        self.layout().activate()
        fit_dialog_to_available_screen(self, QSize(860, 690))

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
