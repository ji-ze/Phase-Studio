"""Non-modal access to persisted execution history, shared by review hosts."""
import json
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
    QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
    QPushButton, QVBoxLayout)
from .run_review import PersistedRunReview, workflow_status_text
from .ui_branding import apply_safe_dialog_geometry


class RunLogViewer(QDialog):
    def __init__(self, parent, directory):
        super().__init__(parent)
        self.setObjectName('persistedExecutionLogViewer')
        self.setWindowTitle('Execution log')
        self.setModal(False)
        self.review = PersistedRunReview(directory)
        self.cycle = None
        self.family = None
        layout = QVBoxLayout(self)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        filters = QHBoxLayout()
        self.kind = QComboBox()
        for title, key in [('Full execution log', 'all'), ('Scientific results only', 'scientific'), ('Warnings and errors', 'warnings')]:
            self.kind.addItem(title, key)
        self.kind.setAccessibleName('Execution log category')
        self.cycle_filter = QCheckBox('Selected cycle')
        self.family_filter = QCheckBox('Selected result family')
        for widget in (self.kind, self.cycle_filter, self.family_filter):
            filters.addWidget(widget)
        layout.addLayout(filters)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search persisted events')
        self.search.setAccessibleName('Search execution log')
        layout.addWidget(self.search)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.text.setAccessibleName('Persisted execution events')
        layout.addWidget(self.text, 1)
        actions = QHBoxLayout()
        for title, callback in [('Copy', lambda: QApplication.clipboard().setText(self.text.toPlainText())),
                                ('Export sanitized diagnostics', self.export),
                                ('Open complete original log', self.open_original),
                                ('Close', self.close)]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)
        self.kind.currentIndexChanged.connect(self.render)
        self.cycle_filter.toggled.connect(self.render)
        self.family_filter.toggled.connect(self.render)
        self.search.textChanged.connect(self.render)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        apply_safe_dialog_geometry(self, 1050, 680)
        self.set_candidate(None)

    def showEvent(self,event):
        super().showEvent(event)
        self.timer.start();self.refresh()

    def hideEvent(self,event):
        self.timer.stop();super().hideEvent(event)

    def set_candidate(self, candidate):
        self.cycle = candidate.cycle if candidate else None
        self.family = candidate.source if candidate else None
        self.cycle_filter.setText(f'Selected cycle {self.cycle}' if self.cycle is not None else 'Selected cycle unavailable')
        self.family_filter.setText('Selected result family: '+str(self.family or 'unavailable'))
        self.cycle_filter.setEnabled(self.cycle is not None)
        self.family_filter.setEnabled(self.family is not None)
        self.render()

    def refresh(self):
        self.review.reload()
        self.render()

    def render(self, *_args):
        from .run_provenance import safe
        note=f' {self.review.incomplete_records} incomplete/malformed event line(s) omitted; original history preserved.' if self.review.incomplete_records else ''
        if self.family_filter.isChecked():note+=' Turn off the family filter to include unassigned or run-wide historical events.'
        self.status.setText(workflow_status_text(self.review.manifest)+note)
        events = self.review.events(cycle=self.cycle if self.cycle_filter.isChecked() else None,
            family=self.family if self.family_filter.isChecked() else None,
            kind=self.kind.currentData(), search=self.search.text())
        lines = []
        for event in events:
            payload = safe(event.get('payload') or {})
            message = payload.get('message') or json.dumps(payload, ensure_ascii=False, sort_keys=True)
            lines.append(f'{event.get("timestamp", "")} [{event.get("severity", "INFO")}][{event.get("component", "")}][{event.get("event_type", "")}] cycle {event.get("cycle")} {message}')
        if not self.review.records:
            path = self.review.original_log()
            if path and self.kind.currentData() == 'all' and not self.cycle_filter.isChecked() and not self.family_filter.isChecked():
                lines = ['Structured history unavailable. Showing the persisted original text log.', safe(path.read_text(encoding='utf8', errors='replace'))]
        text = '\n'.join(lines) or 'No persisted events match these filters. Unknown historical cycle/family associations are not inferred.'
        if text != self.text.toPlainText():
            position = self.text.verticalScrollBar().value()
            self.text.setPlainText(text)
            self.text.verticalScrollBar().setValue(position)

    def open_original(self):
        path = self.review.original_log()
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def export(self):
        name, _ = QFileDialog.getSaveFileName(self, 'Export sanitized diagnostics', '', 'ZIP (*.zip)')
        if name:
            try:
                self.review.export_sanitized(name)
            except (OSError, ValueError) as exc:
                from .error_reporting import sanitize_error_details
                QMessageBox.warning(self, 'Diagnostic export unavailable', sanitize_error_details(str(exc)))
