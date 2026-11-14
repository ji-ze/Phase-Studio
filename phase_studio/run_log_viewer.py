"""Non-modal access to persisted execution history, shared by review hosts."""
import json
from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
    QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
    QPushButton, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QStackedWidget)
from .run_review import PersistedRunReview, workflow_status_text
from .ui_branding import apply_safe_dialog_geometry


class RunLogViewer(QDialog):
    def __init__(self, parent, directory):
        super().__init__(parent)
        from .ui_style import apply_standard_dialog_style
        apply_standard_dialog_style(self)
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
        for title, key in [('All events', 'all'), ('Important events', 'important'), ('Scientific results only', 'scientific'), ('Warnings and errors', 'warnings')]:
            self.kind.addItem(title, key)
        self.kind.setAccessibleName('Execution log category')
        self.cycle_filter = QCheckBox('Selected cycle')
        self.family_filter = QCheckBox('Selected result family')
        for widget in (self.kind, self.cycle_filter, self.family_filter):
            filters.addWidget(widget)
        layout.addLayout(filters)
        self.component = QComboBox()
        self.component.addItem('All components', None)
        self.component.setAccessibleName('Filter execution component')
        self.raw_view = QCheckBox('Full structured details')
        extra = QHBoxLayout();extra.addWidget(self.component);extra.addStretch(1);extra.addWidget(self.raw_view)
        layout.addLayout(extra)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search persisted events')
        self.search.setAccessibleName('Search execution log')
        layout.addWidget(self.search)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.text.setAccessibleName('Persisted execution events')
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(['Time', 'Severity', 'Component', 'Cycle', 'Event', 'Message'])
        self.table.verticalHeader().hide()
        self.table.setWordWrap(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.table.horizontalHeader().setMaximumSectionSize(240)
        self.views = QStackedWidget()
        self.views.addWidget(self.table);self.views.addWidget(self.text)
        layout.addWidget(self.views, 1)
        self.raw_view.toggled.connect(lambda checked:self.views.setCurrentWidget(self.text if checked or self._legacy else self.table))
        self._legacy = False
        self._rendered = None
        actions = QHBoxLayout()
        for title, callback in [('Copy', lambda: QApplication.clipboard().setText(self.text.toPlainText())),
                                ('Export sanitized…', self.export),
                                ('Original log', self.open_original),
                                ('Close', self.close)]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)
        self.kind.currentIndexChanged.connect(self.render)
        self.cycle_filter.toggled.connect(self.render)
        self.family_filter.toggled.connect(self.render)
        self.search.textChanged.connect(self.render)
        self.component.currentIndexChanged.connect(self.render)
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
        selected = self.component.currentData()
        components = sorted({str(event.get('component','')) for event in self.review.records if event.get('component')})
        self.component.blockSignals(True)
        self.component.clear();self.component.addItem('All components',None)
        for name in components:self.component.addItem(name,name)
        self.component.setCurrentIndex(max(0,self.component.findData(selected)))
        self.component.blockSignals(False)
        self.render()

    def render(self, *_args):
        from .run_provenance import safe
        note=f' {self.review.incomplete_records} incomplete/malformed event line(s) omitted; original history preserved.' if self.review.incomplete_records else ''
        if self.family_filter.isChecked():note+=' Turn off the family filter to include unassigned or run-wide historical events.'
        self.status.setText(workflow_status_text(self.review.manifest)+note)
        events = self.review.events(cycle=self.cycle if self.cycle_filter.isChecked() else None,
            family=self.family if self.family_filter.isChecked() else None,
            kind=self.kind.currentData(), search=self.search.text())
        if self.component.currentData():
            events = [event for event in events if event.get('component')==self.component.currentData()]
        signature = json.dumps(safe(events),sort_keys=True,ensure_ascii=False)
        if signature != self._rendered:
            selected = self.table.item(self.table.currentRow(),0)
            selected_key = selected.data(Qt.UserRole) if selected else None
            scroll = self.table.verticalScrollBar().value()
            self.table.setRowCount(len(events))
            for row,event in enumerate(events):
                payload = safe(event.get('payload') or {})
                key = (event.get('session_id'),event.get('session_sequence'),event.get('timestamp'),event.get('event_type'))
                message = payload.get('message') or '; '.join(f'{name}: {payload[name]}' for name in ('stage','status','source') if name in payload) or 'Full event payload available in structured details'
                values = (event.get('timestamp',''),event.get('severity','INFO'),event.get('component',''),
                    str(event['cycle']) if event.get('cycle') is not None else 'Global',str(event.get('event_type','')).replace('_',' '),str(message))
                for column,value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    item.setData(Qt.UserRole,key)
                    from .ui_branding import bounded_tooltip
                    item.setToolTip(bounded_tooltip(str(value)[:512] + ('… Open full structured details for the complete event.' if len(str(value))>512 else '')))
                    self.table.setItem(row,column,item)
                if key==selected_key:self.table.selectRow(row)
            self.table.verticalScrollBar().setValue(scroll)
            self._rendered = signature
        lines = []
        for event in events:
            lines.append(json.dumps(safe(event),ensure_ascii=False,sort_keys=True,indent=2))
        self._legacy = False
        if not self.review.records:
            path = self.review.original_log()
            if path and self.kind.currentData() == 'all' and not self.cycle_filter.isChecked() and not self.family_filter.isChecked():
                lines = ['Structured history unavailable. Showing the persisted original text log.', safe(path.read_text(encoding='utf8', errors='replace'))]
                self._legacy = True
        text = '\n'.join(lines) or 'No persisted events match these filters. Unknown historical cycle/family associations are not inferred.'
        if not events and not self._legacy:
            self.status.setText(self.status.text()+' No persisted events match these filters.')
        if text != self.text.toPlainText():
            position = self.text.verticalScrollBar().value()
            self.text.setPlainText(text)
            self.text.verticalScrollBar().setValue(position)
        self.views.setCurrentWidget(self.text if self.raw_view.isChecked() or self._legacy else self.table)

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
