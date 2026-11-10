"""Compact read-only presentation of the authoritative recommendation."""
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QHeaderView)
from .map_quality import profile_definition
from .run_review import recommendation_details
from .ui_branding import fit_dialog_to_available_screen
from .ui_style import apply_standard_dialog_style


class RecommendationDialog(QDialog):
    def __init__(self, parent, recommendation):
        super().__init__(parent)
        self.setWindowTitle('Why this cycle?')
        self.setObjectName('recommendationExplanation')
        apply_standard_dialog_style(self)
        layout = QVBoxLayout(self)
        title = QLabel('Why this cycle was recommended')
        title.setObjectName('sectionLabel')
        layout.addWidget(title)
        candidate = recommendation.recommended_candidate
        reason = QLabel((f'Cycle {candidate.cycle}. ' if candidate else '') + recommendation.reason)
        reason.setWordWrap(True)
        layout.addWidget(reason)
        definition = profile_definition(recommendation.profile)
        self.criteria = QTableWidget(len(definition.primary_metrics), 3)
        self.criteria.setHorizontalHeaderLabels(['Criterion, in priority order', 'Recommended cycle', 'Preferred direction'])
        self.criteria.verticalHeader().hide()
        self.criteria.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        from .result_selection import format_result_metric
        for row, metric in enumerate(definition.primary_metrics):
            value = candidate.metrics.value(metric.key) if candidate else None
            shown = format_result_metric(value) + (' Å' if value is not None and 'rmsd' in metric.key else '')
            for column, text in enumerate((metric.label, shown, 'Higher' if metric.higher_is_better else 'Lower')):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                item.setToolTip('Unavailable' if value is None else repr(value))
                self.criteria.setItem(row, column, item)
        self.criteria.resizeColumnsToContents()
        self.criteria.setMaximumHeight(self.criteria.horizontalHeader().height() + sum(self.criteria.rowHeight(i) for i in range(self.criteria.rowCount())) + 6)
        layout.addWidget(self.criteria)
        self.exact_text = recommendation_details(recommendation)
        policy = QLabel('\n'.join(line for line in self.exact_text.splitlines() if line.startswith(('Later metrics', 'Reference-dependent'))))
        policy.setWordWrap(True)
        layout.addWidget(policy)
        self.details = QPlainTextEdit(self.exact_text)
        self.details.setReadOnly(True)
        self.details.hide()
        layout.addWidget(self.details)
        actions = QHBoxLayout()
        toggle = QPushButton('Technical details')
        toggle.setCheckable(True)
        toggle.toggled.connect(self.details.setVisible)
        copy = QPushButton('Copy full precision')
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self.exact_text))
        close = QPushButton('Close')
        close.clicked.connect(self.close)
        actions.addWidget(toggle);actions.addWidget(copy);actions.addStretch(1);actions.addWidget(close)
        layout.addLayout(actions)
        fit_dialog_to_available_screen(self, QSize(660, min(480, layout.sizeHint().height()+24)))
