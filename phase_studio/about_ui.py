"""Compact owned About dialog and safe bundled-document viewer."""
from html import escape
from pathlib import Path
import re
import sys

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFontInfo, QTextBlockFormat, QTextCharFormat, QTextCursor, QTextDocument, QTextFormat
from PySide6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QDialog,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QSizePolicy, QStackedWidget, QStyle, QTextBrowser, QVBoxLayout, QWidget)

from phase_studio import version
from phase_studio.legal_content import legal_directory, source_text, citation_text
from phase_studio.ui_branding import (activate_owned_dialog, create_phase_studio_brand_header,
                                     fit_dialog_to_available_screen, standard_ui_font)

RELEASES_URL = 'https://github.com/ji-ze/Phase-Studio/releases'
REPOSITORY_URL = 'https://github.com/ji-ze/Phase-Studio'

CONTACTS_HTML = '''<h2>Phase Studio</h2>
<p><a href="mailto:zelenka@fzu.cz">Jiří Zelenka</a> — author and lead developer.</p>
<p><a href="https://github.com/ji-ze/Phase-Studio">GitHub repository</a> ·
<a href="https://sharped.fzu.cz/">SharpED website</a> ·
<a href="mailto:sharped@fzu.cz">sharped@fzu.cz</a></p>
<h3>SharpED development team</h3>
<p><a href="mailto:rohlicek@fzu.cz">Jan Rohlíček</a><br>
<a href="mailto:zelenka@fzu.cz">Jiří Zelenka</a><br>
<a href="mailto:kucerakova@fzu.cz">Monika Kučeráková</a><br>
<a href="mailto:buk@fzu.cz">Zdeněk Buk</a></p>
<h3>Scientific collaboration</h3>
<p>We welcome questions about the SharpED method, possible applications to
crystallographic data and opportunities for scientific collaboration.</p>
<p><a href="mailto:sharped@fzu.cz?subject=SharpED%20scientific%20collaboration">Contact us about a collaboration</a></p>
<h3>Institution</h3><p>Institute of Physics of the Czech Academy of Sciences<br>
Fyzikální ústav AV ČR, v. v. i.<br>Na Slovance 1999/2<br>
182 00 Prague 8<br>Czech Republic<br><a href="https://www.fzu.cz/en">www.fzu.cz/en</a></p>
<p>Use Original AUTHORS.md to read the complete original credits.
Copy original and Open original always use that unchanged source document.</p>'''

# Scoped to the two About surfaces. The wordmark is the only plain-text
# widget that requests the branding face; the SharpED subtitle retains its
# established, explicitly marked rich-text spans.
_STYLE = '''
QWidget { font-family:"@UI_FONT@"; font-size:10pt; color:#14204a; background:transparent; }
QDialog { background:#ffffff; }
QLabel#brandTitle { font-family:"Science Gothic"; font-size:18pt; font-weight:400; color:#001170; }
QLabel#brandSubtitle { font-size:8.5pt; }
QLabel#versionBadge { font-size:9pt; color:#60718b; font-weight:400; border:0; padding:0; }
QLabel#aboutDescription { color:#52617b; font-size:9pt; }
QPushButton { font-size:9pt; font-weight:400; background:#ffffff; color:#214b7e;
    border:1px solid #bdcce0; border-radius:4px; padding:3px 10px; min-height:18px; }
QPushButton:hover { background:#f0f6fc; border-color:#8baccd; }
QPushButton:pressed { background:#e4eef8; }
QPushButton:focus { border:1px dashed #596980; }
QPushButton:disabled { color:#76859b; background:#f5f7fa; border-color:#d8e1ec; }
QPushButton#documentLayoutButton { font-size:8.5pt; }
QPushButton#documentLayoutButton:checked { background:#eef6fc; border-color:#5293c0; }
QPushButton#aboutCard { background:#f8fafd; border:1px solid #d8e3ef; padding:0; border-radius:6px; min-height:44px; }
QPushButton#aboutCard:hover { background:#f1f6fc; border-color:#a7bfd8; }
QPushButton#aboutCard:checked { background:#eef6fc; border-color:#5293c0; }
QPushButton#aboutCard:focus { border:1px dashed #596980; }
QPushButton#aboutCard:pressed { background:#e5f0f9; }
QLabel#aboutCardTitle { color:#142d57; font-size:9.5pt; font-weight:600; }
QLabel#aboutCardSubtitle { color:#65748d; font-size:8.5pt; }
QScrollArea#aboutContent { border:1px solid #dce5ef; border-radius:6px; background:#f8fafd; }
QWidget#aboutPage { background:#f8fafd; }
QPushButton#aboutLink { color:#2c66a7; background:transparent; border:0; padding:2px 0; }
QPushButton#aboutLink:hover { text-decoration:underline; }
QPushButton#aboutLink:focus { border:1px dashed #596980; }
QLabel#documentTitle { font-size:12pt; font-weight:600; color:#142d57; }
QLabel#documentSource { font-size:8.5pt; color:#6b7890; }
QComboBox, QLineEdit { font-size:9.5pt; background:#ffffff; border:1px solid #cbd8e7;
    border-radius:3px; padding:4px 6px; min-height:18px; }
QTextBrowser { font-size:10.5pt; background:#ffffff; border:1px solid #dce5ef; padding:8px; }
QCheckBox { font-size:9pt; color:#5b6b82; }
'''


def _style(dialog):
    font = standard_ui_font()
    dialog.setFont(font)
    dialog.setStyleSheet(_STYLE.replace('@UI_FONT@', font.family()))


def _restore_focus(widget):
    if widget is not None:
        try:
            if widget.isVisible() and widget.isEnabled():
                widget.setFocus(Qt.OtherFocusReason)
        except RuntimeError:
            pass  # Owner may have been destroyed with the dialog.


class LegalBrowser(QTextBrowser):
    def loadResource(self, resource_type, url):
        # Neither Markdown nor rich text may fetch embedded local/remote data.
        return None

    def __init__(self):
        super().__init__()
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.anchorClicked.connect(self._open_link)

    def _open_link(self, url):
        if url.scheme().lower() in ('https', 'mailto'):
            QDesktopServices.openUrl(url)


def _document_title(path):
    originals = {'LICENSE': 'MIT License', 'AUTHORS.md': 'Authors and acknowledgements',
                 'THIRD_PARTY_NOTICES.md': 'Third-party notices', 'CITATION.cff': 'Citation metadata'}
    if path.name in originals and (path.parent == Path('.') or path.parent.resolve() == legal_directory().resolve()):
        return originals[path.name]
    known = {'GFDL-1.3.txt': 'GNU Free Documentation License 1.3',
             'LGPL-3.0.txt': 'GNU Lesser General Public License 3.0',
             'GPL-3.0.txt': 'GNU General Public License 3.0',
             'OFL-Science-Gothic.txt': 'Science Gothic — SIL Open Font License'}
    if path.name in known:
        return known[path.name]
    # Frozen metadata paths include actual distribution/version information.
    package = next((part.removesuffix('.dist-info') for part in path.parts if part.endswith('.dist-info')), '')
    if not package:
        package = path.parent.name if path.parent.name not in ('third_party_licenses', 'upstream', 'dependencies', 'licenses', 'license') else ''
    label = path.stem.replace('_', ' ').replace('LICENSE.', '').replace('LICENSE-', '')
    if label.upper() in ('LICENSE', 'COPYING', 'LICENCE'):
        label = 'License'
    return f'{package} · {label}' if package and package.lower() != label.lower() else label


class DocumentDialog(QDialog):
    """Display only enumerated bundled authorities; copy exact decoded source."""
    def __init__(self, parent, name, *, third_party=False, contacts=False):
        super().__init__(parent)
        if name not in {'AUTHORS.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'CITATION.cff'}:
            raise ValueError('Unknown bundled document')
        self.setObjectName('phaseStudioDocument')
        self.contacts = contacts and name == 'AUTHORS.md'
        _style(self)
        self.setWindowTitle('Third-party licenses' if third_party else _document_title(Path(name)))
        self.setWindowModality(Qt.WindowModal)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        title_row = QHBoxLayout()
        self.title_label = QLabel()
        self.title_label.setObjectName('documentTitle')
        self.title_label.setWordWrap(True)
        title_row.addWidget(self.title_label, 1)
        self.original_layout = QPushButton('Original layout')
        self.original_layout.setObjectName('documentLayoutButton')
        self.original_layout.setCheckable(True)
        self.original_layout.setToolTip('Show original line breaks. Copy original always copies the complete original source.')
        title_row.addWidget(self.original_layout)
        self.original_authors = QPushButton('Original AUTHORS.md')
        self.original_authors.setCheckable(True)
        self.original_authors.setVisible(self.contacts)
        self.original_authors.toggled.connect(self.render_document)
        title_row.addWidget(self.original_authors)
        layout.addLayout(title_row)
        self.paths = [legal_directory() / name]
        self.allowed_paths = [self.paths[0].resolve()]
        self.selector = QComboBox()
        self.selector.setAccessibleName('Choose dependency license')
        self.selector.addItem(_document_title(self.paths[0]))
        if third_party:
            self.selector.setEditable(True)
            self.selector.setInsertPolicy(QComboBox.NoInsert)
            self.selector.completer().setCaseSensitivity(Qt.CaseInsensitive)
            self.selector.completer().setFilterMode(Qt.MatchContains)
            roots = ([legal_directory() / 'dependencies', legal_directory() / 'upstream']
                     if getattr(sys, 'frozen', False) else [legal_directory() / 'third_party_licenses'])
            for root in roots:
                if root.is_dir():
                    for path in sorted(root.rglob('*')):
                        if path.is_file() and path.resolve().is_relative_to(root.resolve()):
                            self.paths.append(path)
                            self.allowed_paths.append(path.resolve())
                            self.selector.addItem(_document_title(path))
                            self.selector.setItemData(self.selector.count() - 1,
                                path.relative_to(legal_directory()).as_posix(), Qt.ToolTipRole)
            layout.addWidget(self.selector)
        self.source_label = QLabel()
        self.source_label.setObjectName('documentSource')
        self.source_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.source_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        layout.addWidget(self.source_label)
        self.browser = LegalBrowser()
        self.browser.setAccessibleName('Original license document')
        self.browser.setFont(standard_ui_font(10.5))
        self.browser.document().setDefaultFont(standard_ui_font(10.5))
        layout.addWidget(self.browser, 1)
        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('Find in document')
        self.search.setAccessibleName('Find in document')
        search_row.addWidget(self.search, 1)
        find = QPushButton('Find next')
        find.clicked.connect(self.find_next)
        self.search.returnPressed.connect(self.find_next)
        search_row.addWidget(find)
        layout.addLayout(search_row)
        tools = QHBoxLayout()
        self.copy_button = QPushButton('Copy original')
        self.copy_button.clicked.connect(lambda: QApplication.clipboard().setText(self.raw_text))
        tools.addWidget(self.copy_button)
        self.original_button = QPushButton('Open original')
        self.original_button.clicked.connect(self.open_original)
        tools.addWidget(self.original_button)
        tools.addStretch(1)
        self.close_button = QPushButton('Close')
        self.close_button.clicked.connect(self.reject)
        tools.addWidget(self.close_button)
        layout.addLayout(tools)
        self.selector.currentIndexChanged.connect(self.load_document)
        self.original_layout.toggled.connect(self.render_document)
        self.load_document()
        self.resize(760, 560)

    def _trusted(self):
        return (self.path is not None and self.path.resolve() == self.allowed_path
                and self.path.resolve().is_relative_to(legal_directory().resolve()))

    def load_document(self):
        index = self.selector.currentIndex()
        self.path = self.paths[index] if 0 <= index < len(self.paths) else None
        self.allowed_path = self.allowed_paths[index] if 0 <= index < len(self.allowed_paths) else None
        self.available = False
        try:
            if not self._trusted():
                raise OSError('Untrusted document path')
            self.raw_bytes = self.path.read_bytes()
            self.raw_text = self.raw_bytes.decode('utf8', errors='replace')
            self.available = True
        except (OSError, AttributeError):
            self.raw_bytes = b''
            self.raw_text = 'Bundled notice unavailable.'
        try:
            self.source = self.path.relative_to(legal_directory()).as_posix()
        except (ValueError, AttributeError):
            self.source = 'Unavailable'
        self.title_label.setText(_document_title(self.path) if self.path else 'Document unavailable')
        self.source_label.setToolTip('Original source: ' + self.source)
        self.source_label.setAccessibleDescription('Original source: ' + self.source)
        self._update_source_label()
        self.original_button.setEnabled(self.available)
        self.render_document()

    def _update_source_label(self):
        prefix = ('Contact summary · Original source: ' if self.contacts and
                  not self.original_authors.isChecked() else 'Original source: ')
        self.source_label.setText(self.source_label.fontMetrics().elidedText(
            prefix + self.source, Qt.ElideMiddle, max(80, self.source_label.width())))

    def render_document(self):
        original = self.original_layout.isChecked()
        # QTextEdit.setPlainText retains currentCharFormat. Clear a previous
        # Markdown heading before switching to a plain-text notice.
        self.browser.setCurrentCharFormat(QTextCharFormat())
        self.browser.document().setDefaultFont(standard_ui_font(10.5))
        self.original_layout.setEnabled(not (self.path and self.path.suffix.lower() == '.cff'))
        summary = self.contacts and not self.original_authors.isChecked()
        if summary:
            self.title_label.setText('Contacts and collaboration')
            self.original_layout.setEnabled(False)
            self.browser.setHtml(CONTACTS_HTML)
        elif self.path and self.path.suffix.lower() == '.md' and not original:
            self.title_label.setText(_document_title(self.path))
            self.browser.document().setMarkdown(self.raw_text,
                QTextDocument.MarkdownDialectGitHub | QTextDocument.MarkdownNoHTML)
        else:
            text = self.raw_text
            if not original and self.path and self.path.suffix.lower() != '.cff':
                # Reflow source-wrapped paragraphs for the reader. Every word
                # and paragraph remains; raw copy/open and Original layout
                # retain the untouched source bytes/line breaks.
                text = '\n\n'.join(re.sub(r'\s*\n\s*', ' ', paragraph).strip()
                                   for paragraph in re.split(r'\n\s*\n', text))
            self.browser.setPlainText(text)
            cursor = QTextCursor(self.browser.document())
            cursor.select(QTextCursor.Document)
            body_format = QTextCharFormat()
            body_format.setFont(standard_ui_font(10.5))
            cursor.setCharFormat(body_format)
        # Markdown headings and code spans must not inherit the branding font
        # when the offscreen font database starts with only Science Gothic.
        block = self.browser.document().begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid():
                    correction = QTextCharFormat(fragment.charFormat())
                    if QFontInfo(correction.font()).family() in ('', 'Science Gothic'):
                        correction.setFontFamilies([standard_ui_font().family()])
                    heading = block.blockFormat().headingLevel()
                    if heading:
                        correction.clearProperty(QTextFormat.FontSizeAdjustment)
                        correction.setFontPointSize(12 if heading == 1 else 11)
                    cursor = QTextCursor(self.browser.document())
                    cursor.setPosition(fragment.position())
                    cursor.setPosition(fragment.position() + fragment.length(), QTextCursor.KeepAnchor)
                    cursor.setCharFormat(correction)
                iterator += 1
            block = block.next()
        cursor = QTextCursor(self.browser.document())
        cursor.select(QTextCursor.Document)
        spacing = QTextBlockFormat()
        spacing.setLineHeight(120, QTextBlockFormat.ProportionalHeight.value)
        cursor.mergeBlockFormat(spacing)
        self.browser.moveCursor(QTextCursor.Start)
        self._update_source_label()

    def find_next(self):
        if not self.browser.find(self.search.text()):
            self.browser.moveCursor(QTextCursor.Start)
            self.browser.find(self.search.text())

    def open_original(self):
        if self.available and self._trusted() and self.path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.path)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'source'):
            self._update_source_label()

    def showEvent(self, event):
        super().showEvent(event)
        fit_dialog_to_available_screen(self, QSize(760, 560))
        # The common helper's large-dialog minimum is inappropriate here.
        self.setMinimumSize(min(420, self.width()), min(300, self.height()))
        self._update_source_label()


class _ContentPanel(QScrollArea):
    def sizeHint(self):
        height = self.widget().sizeHint().height() + 2 if self.widget() else 130
        return QSize(640, min(140, max(108, height)))

    def minimumSizeHint(self):
        return QSize(0, 76)


class AboutDialog(QDialog):
    def __init__(self, parent, *, jana: bool):
        super().__init__(parent)
        self.setObjectName('phaseStudioAbout')
        _style(self)
        self.setWindowTitle('About Phase Studio')
        self.setWindowModality(Qt.WindowModal)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)
        header = create_phase_studio_brand_header()
        header.layout().setContentsMargins(0, 0, 0, 0)
        logo = header.findChild(QLabel, 'brandLogo')
        logo.setPixmap(logo.pixmap().scaled(42, 42, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo.setFixedSize(42, 42)
        header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        badge = header.findChild(QLabel, 'versionBadge')
        badge.setText('v' + version.VERSION + '\nDevelopment')
        badge.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.version_label = badge
        layout.addWidget(header)
        profile = 'Jana2020 integration' if jana else 'Standalone application'
        description = QLabel('Crystallographic structure solution and electron-density processing. · ' + profile)
        description.setObjectName('aboutDescription')
        description.setWordWrap(True)
        description.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        description.setToolTip(profile)
        description.setAccessibleDescription(description.toolTip())
        self.mode_label = description
        layout.addWidget(description)
        navigation = QWidget()
        navigation.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        grid = QGridLayout(navigation)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self.cards = []
        self.card_group = QButtonGroup(self)
        self.card_group.setExclusive(True)
        entries = [('Authors & contacts', 'Credits and contacts'), ('License', 'MIT and copyright'),
                   ('Third-party licenses', 'Original notices'), ('Citation', 'Scientific citation')]
        icons = (QStyle.SP_FileDialogInfoView, QStyle.SP_FileDialogDetailedView,
                 QStyle.SP_FileDialogListView, QStyle.SP_FileIcon)
        for index, (title, subtitle) in enumerate(entries):
            card = QPushButton()
            card.setObjectName('aboutCard')
            card.setFocusPolicy(Qt.StrongFocus)
            card.setCheckable(True)
            card.setAccessibleName(title)
            card.setAccessibleDescription(subtitle)
            card.setMinimumHeight(44)
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            row = QHBoxLayout(card)
            row.setContentsMargins(10, 5, 10, 5)
            row.setSpacing(9)
            icon = QLabel()
            icon.setPixmap(self.style().standardIcon(icons[index]).pixmap(18, 18))
            icon.setFixedWidth(18)
            icon.setAttribute(Qt.WA_TransparentForMouseEvents)
            row.addWidget(icon)
            captions = QVBoxLayout()
            captions.setSpacing(1)
            for caption, object_name in ((title, 'aboutCardTitle'), (subtitle, 'aboutCardSubtitle')):
                label = QLabel(caption)
                label.setObjectName(object_name)
                label.setWordWrap(True)
                label.setAttribute(Qt.WA_TransparentForMouseEvents)
                captions.addWidget(label)
            row.addLayout(captions, 1)
            self.card_group.addButton(card, index)
            grid.addWidget(card, index // 2, index % 2)
            self.cards.append(card)
        layout.addWidget(navigation)
        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.stack.setMinimumHeight(76)
        self.stack.setMaximumHeight(140)
        layout.addWidget(self.stack)
        self._page('<p><b>Phase Studio</b><br>Jiří Zelenka — author and lead developer.<br>'
                   'Institute of Physics of the Czech Academy of Sciences · '
                   '<a href="mailto:zelenka@fzu.cz">zelenka@fzu.cz</a></p>'
                   '<p><b>SharpED development team</b><br>'
                   'Jiří Zelenka, Jan Rohlíček, Monika Kučeráková and Zdeněk Buk.</p>',
                   [('Contacts and credits', lambda: self.open_document('AUTHORS.md', contacts=True))])
        copyright_line = next((line for line in source_text('LICENSE').splitlines() if line.startswith('Copyright')), '').replace('(c)', '©')
        self._page('<p><b>MIT License</b></p><p>' + escape(copyright_line) + '</p>'
                   '<p>Permits use, modification and distribution under the terms of the license.</p>',
                   [('Read full license', lambda: self.open_document('LICENSE'))])
        self._page('<p><b>Third-party components</b></p>'
                   '<p>Bundled dependencies retain their own licenses. Complete original notices are available locally.</p>',
                   [('Browse licenses', lambda: self.open_document('THIRD_PARTY_NOTICES.md', third_party=True))])
        self.citation = citation_text(version.VERSION)
        self._page('<p><b>Citation</b></p><p>' + escape(self.citation) + '</p>',
                   [('Copy citation', lambda: QApplication.clipboard().setText(self.citation)),
                    ('View citation metadata', lambda: self.open_document('CITATION.cff'))])
        self.card_group.idClicked.connect(self.stack.setCurrentIndex)
        self.cards[0].setChecked(True)
        footer = QHBoxLayout()
        footer.setSpacing(16)
        for title, url in [('GitHub repository', REPOSITORY_URL), ('Official releases', RELEASES_URL)]:
            link = QPushButton(title)
            link.setObjectName('aboutLink')
            link.setFlat(True)
            link.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            link.setToolTip(url)
            link.clicked.connect(lambda checked=False, u=url: QDesktopServices.openUrl(QUrl(u)))
            footer.addWidget(link)
        footer.addStretch(1)
        self.close_button = QPushButton('Close')
        self.close_button.setMinimumWidth(72)
        self.close_button.clicked.connect(self.reject)
        footer.addWidget(self.close_button)
        layout.addLayout(footer)
        self.viewer = None
        self.resize(720, 420)

    def _page(self, text, actions):
        scroll = _ContentPanel()
        scroll.setObjectName('aboutContent')
        scroll.setWidgetResizable(True)
        body = QWidget()
        body.setObjectName('aboutPage')
        page_layout = QVBoxLayout(body)
        page_layout.setContentsMargins(12, 6, 12, 6)
        page_layout.setSpacing(4)
        page_layout.setAlignment(Qt.AlignTop)
        label = QLabel('<style>p { margin:0 0 5px 0; }</style>' + text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        label.setFocusPolicy(Qt.StrongFocus)
        label.linkActivated.connect(lambda link: QDesktopServices.openUrl(QUrl(link))
            if QUrl(link).scheme().lower() in ('https', 'mailto') else None)
        page_layout.addWidget(label)
        row = QHBoxLayout()
        for title, action in actions:
            button = QPushButton(title)
            button.clicked.connect(action)
            row.addWidget(button)
        row.addStretch(1)
        page_layout.addLayout(row)
        scroll.setWidget(body)
        self.stack.addWidget(scroll)

    def open_document(self, name, *, third_party=False, contacts=False):
        if self.viewer is not None and self.viewer.isVisible():
            activate_owned_dialog(self.viewer)
            return self.viewer
        if self.viewer is not None:
            self.viewer.deleteLater()
        previous = QApplication.focusWidget()
        self.viewer = DocumentDialog(self, name, third_party=third_party, contacts=contacts)
        self.viewer.finished.connect(lambda _result: _restore_focus(previous))
        self.viewer.open()
        return self.viewer

    def _fit(self):
        self.layout().activate()
        fit_dialog_to_available_screen(self, QSize(720, 420))
        self.setMinimumSize(min(430, self.width()), min(330, self.height()))

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
    previous = QApplication.focusWidget()
    dialog = AboutDialog(parent, jana=jana)
    parent._phase_studio_about = dialog
    def finished(_result):
        if parent.isVisible():
            activate_owned_dialog(parent)
            _restore_focus(previous)
    dialog.finished.connect(finished)
    dialog.open()
    return dialog
