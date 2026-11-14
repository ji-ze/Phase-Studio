"""Explicit component selection; no inference that all components were used."""
from html import escape
from pathlib import Path
from PySide6.QtCore import Qt, QSize, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QFileDialog)
from .about_ui import LegalBrowser, DocumentDialog, _restore_focus
from .scientific_citations import references
from .ui_style import apply_standard_dialog_style
from .ui_branding import fit_dialog_to_available_screen, standard_ui_font, activate_owned_dialog
from .version import VERSION


class CitationDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        apply_standard_dialog_style(self)
        self.setWindowTitle('How to cite')
        self.setWindowModality(Qt.WindowModal)
        self.references = references(VERSION)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        guidance = QLabel('Cite the components actually used in your work. Check references to copy or export a selection.')
        guidance.setWordWrap(True)
        layout.addWidget(guidance)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Find a component, author or reference')
        self.search.setAccessibleName('Find citation')
        layout.addWidget(self.search)
        self.list = QListWidget()
        self.list.setAccessibleName('Software and journal references; check those actually used')
        for reference in self.references:
            item = QListWidgetItem(reference.name + ' — ' + reference.status)
            item.setCheckState(Qt.Unchecked)
            self.list.addItem(item)
        self.list.setMaximumHeight(100)
        self.list.setMinimumHeight(54)
        layout.addWidget(self.list)
        self.browser = LegalBrowser()
        self.browser.setFont(standard_ui_font(10.5))
        self.browser.document().setDefaultFont(standard_ui_font(10.5))
        layout.addWidget(self.browser, 1)
        current = QHBoxLayout()
        self.copy_button = QPushButton('Copy citation')
        self.copy_button.clicked.connect(lambda: QApplication.clipboard().setText(self.current().citation))
        current.addWidget(self.copy_button)
        self.source_button = QPushButton('Open source')
        self.source_button.setToolTip('Open the verified DOI or official software source')
        self.source_button.clicked.connect(self.open_source)
        current.addWidget(self.source_button)
        raw = QPushButton('CITATION.cff')
        raw.setToolTip('Read the complete original project citation metadata')
        raw.clicked.connect(self.open_original)
        current.addWidget(raw)
        current.addStretch()
        layout.addLayout(current)
        footer = QHBoxLayout()
        self.copy_selected = QPushButton('Copy checked')
        self.copy_selected.clicked.connect(lambda: QApplication.clipboard().setText('\n\n'.join(r.citation for r in self.selected())))
        footer.addWidget(self.copy_selected)
        self.export_button = QPushButton('Export BibTeX…')
        self.export_button.clicked.connect(self.export_bibtex)
        footer.addWidget(self.export_button)
        footer.addStretch()
        close = QPushButton('Close')
        close.clicked.connect(self.reject)
        footer.addWidget(close)
        layout.addLayout(footer)
        self.list.currentRowChanged.connect(self.display)
        self.list.itemChanged.connect(self.sync_selection)
        self.search.textChanged.connect(self.filter)
        self.list.setCurrentRow(0)
        self.sync_selection()
        self.original_viewer = None

    def current(self):
        return self.references[max(0, self.list.currentRow())]

    def selected(self):
        return [reference for i, reference in enumerate(self.references)
                if self.list.item(i).checkState() == Qt.Checked]

    def sync_selection(self):
        selected = self.selected()
        enabled = bool(selected)
        self.copy_selected.setEnabled(enabled)
        self.export_button.setEnabled(enabled)
        self.copy_selected.setText(f'Copy checked ({len(selected)})' if enabled else 'Copy checked')
        self.copy_selected.setToolTip(', '.join(reference.name for reference in selected) or 'Check the components actually used')

    def display(self, _row):
        reference = self.current()
        self.browser.setHtml('<h3>' + escape(reference.name) + '</h3><p>' + escape(reference.citation) +
                             '</p><p>' + escape(reference.status) + '</p>')

    def filter(self, value):
        matches = []
        for i, reference in enumerate(self.references):
            visible = value.casefold() in (reference.name + ' ' + reference.citation + ' ' + reference.status).casefold()
            self.list.item(i).setHidden(not visible)
            if visible:
                matches.append(i)
        self.browser.setVisible(bool(matches))
        self.copy_button.setEnabled(bool(matches))
        self.source_button.setEnabled(bool(matches))
        if matches:
            self.list.setCurrentRow(matches[0])

    def open_source(self):
        url = QUrl(self.current().url)
        if url.scheme() == 'https':
            QDesktopServices.openUrl(url)

    def open_original(self):
        if self.original_viewer is not None and self.original_viewer.isVisible():
            activate_owned_dialog(self.original_viewer)
            return
        previous = QApplication.focusWidget()
        self.original_viewer = DocumentDialog(self, 'CITATION.cff')
        self.original_viewer.finished.connect(lambda _result: (activate_owned_dialog(self), _restore_focus(previous)))
        self.original_viewer.open()

    def export_bibtex(self):
        selected = self.selected()
        if not selected:
            return
        filename, _ = QFileDialog.getSaveFileName(self, 'Export checked references', '', 'BibTeX (*.bib)')
        if filename:
            Path(filename).write_text('\n\n'.join(r.bibtex() for r in selected) + '\n', encoding='utf8')

    def showEvent(self, event):
        super().showEvent(event)
        fit_dialog_to_available_screen(self, QSize(720, 440))
        self.setMinimumSize(min(420, self.width()), min(320, self.height()))
