"""Profile-aware result-selection dialog presentation."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, Sequence

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel,
    QPushButton, QSizePolicy, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from phase_studio.map_quality import (
    ResultCandidate, ResultRecommendation, ValidationProfile,
    ValidationProfileDefinition,
)
from phase_studio.ui_branding import (
    apply_safe_dialog_geometry, create_phase_studio_brand_header,
    create_phase_studio_context_banner,
)


def create_result_preview_host(renderer: object, cell: object, elev: float, azim: float) -> object:
    """Create isolated view state while reusing the established structure renderer."""
    renderer_type = type(renderer)

    class _PreviewHost:
        _structure_cartesian_geometry = renderer_type._structure_cartesian_geometry
        _element_color = renderer_type._element_color
        _plot_structure_atoms = renderer_type._plot_structure_atoms
        _update_structure_depth_artist = renderer_type._update_structure_depth_artist
        _update_structure_depth_cue = renderer_type._update_structure_depth_cue
        _structure_axis_limits = staticmethod(renderer_type._structure_axis_limits)
        _apply_structure_axis_limits = staticmethod(renderer_type._apply_structure_axis_limits)
        _begin_structure_view_drag = renderer_type._begin_structure_view_drag
        _apply_structure_view = renderer_type._apply_structure_view
        _sync_structure_view_from_event = renderer_type._sync_structure_view_from_event
        _finish_structure_view_drag = renderer_type._finish_structure_view_drag

        def __init__(self) -> None:
            self.structure_cell = cell
            self.structure_elev = elev
            self.structure_azim = azim
            self._structure_depth_artists = []
            self.structure_axes = []
            self._structure_interactive_axes = []
            self.structure_view_base_limits = None
            self.structure_view_limits = None
            self._structure_view_drag_source = None
            self.structure_canvas = None

    return _PreviewHost()


class ResultSelectionDialog(QDialog):
    """Render candidates and return one selection without owning its effects."""

    def __init__(
        self,
        parent: QWidget,
        candidates: Sequence[ResultCandidate],
        profile: ValidationProfile,
        definition: ValidationProfileDefinition,
        recommendation: ResultRecommendation,
        *,
        jana_context: bool,
        preview_host: object,
        parse_structure: Callable[[Path], Sequence[object]],
        reference_atoms: Sequence[object],
        source_title: Callable[[str], str],
    ) -> None:
        super().__init__(parent)
        self._ordered = sorted(candidates, key=lambda candidate: (
            int(candidate.cycle), 0 if candidate.source == "superflip" else 1,
            candidate.source,
        ))
        self._selected = recommendation.selected_candidate or self._ordered[0]
        self._jana_context = jana_context
        self._preview_host = preview_host
        self._parse_structure = parse_structure
        self._reference_atoms = reference_atoms
        self._source_title = source_title
        self._reference_available = profile in {
            ValidationProfile.REFERENCE_AND_HOLDOUT, ValidationProfile.REFERENCE_ONLY,
        }

        self.setObjectName("resultSelectionDialog")
        self.setProperty("resultContext", "JANA2020" if jana_context else "STANDALONE")
        self.setWindowTitle("Jana2020 result selection" if jana_context else "Save map and model")
        apply_safe_dialog_geometry(self, 1400, 800)
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        outer_layout.addWidget(create_phase_studio_brand_header())
        outer_layout.addWidget(create_phase_studio_context_banner(
            "JANA2020 RESULT SELECTION" if jana_context else "RESULT SELECTION",
            "Compare completed maps and select the result to pass to Jana2020"
            if jana_context else "Compare completed maps and select the result to save",
        ))

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(14, 10, 14, 14)
        content_layout.setSpacing(9)
        outer_layout.addWidget(content, 1)
        summary_form = QFormLayout()
        summary_form.setHorizontalSpacing(18)
        summary_form.setVerticalSpacing(2)
        free_count = max((candidate.metrics.n_free_reflections for candidate in candidates), default=0)
        summary_values = (
            ("Assessment", definition.assessment_label),
            ("Completed cycles", str(len({candidate.cycle for candidate in candidates}))),
            ("Recommended result", recommendation.recommended_candidate.label
             if recommendation.recommended_candidate else "Unavailable"),
            ("Reference", "Available" if self._reference_available else "Not available"),
            ("Holdout", f"5% · {free_count} reflections" if free_count else "Not enabled"),
        )
        for label_text, value_text in summary_values:
            value_label = QLabel(value_text)
            font = value_label.font(); font.setBold(True); value_label.setFont(font)
            summary_form.addRow(label_text, value_label)
        content_layout.addLayout(summary_form)
        reason_label = QLabel(recommendation.reason)
        reason_label.setObjectName("recommendationReason")
        reason_label.setWordWrap(True)
        reason_label.setStyleSheet("color: #52658b;")
        content_layout.addWidget(reason_label)
        table_section_label = QLabel("RESULT CANDIDATES")
        table_section_label.setObjectName("sectionLabel")
        content_layout.addWidget(table_section_label)

        headers = ["Recommended", "Cycle", "Source"] + [
            metric.arrow_label for metric in definition.primary_metrics
        ]
        table = QTableWidget(len(self._ordered), len(headers))
        table.setObjectName("diagnosticTable")
        table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        selected_row = 0
        for row, candidate in enumerate(self._ordered):
            values = [
                "Recommended" if candidate == recommendation.recommended_candidate else "",
                str(candidate.cycle),
                source_title(candidate.source)
                + (" (map only)" if not candidate.usable_structure else ""),
            ] + [
                "n/a" if (value := candidate.metrics.value(metric.key)) is None
                else f"{float(value):.3f}"
                for metric in definition.primary_metrics
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(
                    (Qt.AlignLeft if column in (0, 2) else Qt.AlignRight) | Qt.AlignVCenter
                )
                item.setData(Qt.UserRole, row)
                table.setItem(row, column, item)
            if candidate == self._selected:
                selected_row = row
        self._table = table

        self._preview_figure = Figure(figsize=(6.0, 3.4), dpi=100)
        preview_canvas = FigureCanvas(self._preview_figure)
        preview_canvas.setObjectName("resultPreviewCanvas")
        preview_canvas.setMinimumHeight(260)
        preview_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        preview_host.structure_canvas = preview_canvas
        preview_canvas.mpl_connect("button_press_event", preview_host._begin_structure_view_drag)
        preview_canvas.mpl_connect("motion_notify_event", preview_host._sync_structure_view_from_event)
        preview_canvas.mpl_connect("button_release_event", preview_host._finish_structure_view_drag)
        self._preview_canvas = preview_canvas

        action_button = QPushButton("Pass to Jana2020" if jana_context else "Save map and model")
        action_button.setObjectName("primaryButton")
        self._action_button = action_button
        table.itemSelectionChanged.connect(self._selection_changed)
        table.selectRow(selected_row)
        self._render_preview(self._selected)

        preview_section = QWidget()
        preview_layout = QVBoxLayout(preview_section)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_label = QLabel(
            "STRUCTURE COMPARISON" if self._reference_available else "STRUCTURE PREVIEW"
        )
        preview_label.setObjectName("sectionLabel")
        preview_layout.addWidget(preview_label)
        preview_layout.addWidget(preview_canvas, 1)
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(table)
        splitter.addWidget(preview_section)
        splitter.setSizes([760, 640])
        content_layout.addWidget(splitter, 1)

        button_row = QHBoxLayout()
        close_button = QPushButton("Return to Phase Studio")
        button_row.addWidget(close_button)
        button_row.addStretch(1)
        button_row.addWidget(action_button)
        content_layout.addLayout(button_row)
        close_button.clicked.connect(self.reject)
        action_button.clicked.connect(self.accept)

    @property
    def selected_candidate(self) -> ResultCandidate:
        return self._selected

    def _selection_changed(self) -> None:
        row = self._table.currentRow()
        if 0 <= row < len(self._ordered):
            self._render_preview(self._ordered[row])

    def _render_preview(self, candidate: ResultCandidate) -> None:
        self._selected = candidate
        figure = self._preview_figure
        figure.clear()
        figure.patch.set_facecolor("#ffffff")
        host = self._preview_host
        host.structure_axes = []
        host._structure_interactive_axes = []
        host._structure_depth_artists = []
        atoms = self._parse_structure(Path(candidate.structure_path)) if candidate.usable_structure else []
        panels = [(candidate.label, atoms, "Structure model unavailable · map remains usable")]
        if self._reference_available:
            panels.append(("Reference", self._reference_atoms, "Reference structure unavailable"))
        count = len(panels)
        positions = (0.5,) if count == 1 else (0.25, 0.75)
        metadata = []
        for index, (_title, panel_atoms, empty_text) in enumerate(panels, start=1):
            axis = figure.add_subplot(1, count, index, projection="3d")
            host.structure_axes.append(axis)
            metadata.append(host._plot_structure_atoms(axis, panel_atoms, empty_text))
        for position, (title, _atoms, _empty) in zip(positions, panels):
            figure.text(
                position, 0.96, title, ha="center", va="center", fontsize=10,
                fontweight="bold", color="#001170",
            )
        for position, details in zip(positions, metadata):
            figure.text(
                position, 0.03, details, ha="center", va="center", fontsize=7.5,
                color="#52658b",
            )
        if count > 1:
            figure.add_artist(Line2D(
                [0.5, 0.5], [0.08, 0.90], transform=figure.transFigure,
                color="#cbd7ea", linewidth=0.45, alpha=0.62,
            ))
        figure.subplots_adjust(left=0.01, right=0.99, bottom=0.09, top=0.90, wspace=0.04)
        self._preview_canvas.draw_idle()
        self._action_button.setText(
            "Pass to Jana2020" if self._jana_context else
            ("Save map and model" if candidate.usable_structure else "Save available result")
        )
