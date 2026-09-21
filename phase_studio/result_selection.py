"""Profile-aware result-selection dialog presentation.

Superflip and SharpED are independent candidate sets here: each gets its own
ordered table, its own recommendation (computed by the caller via two calls
to map_quality.recommend_best_result -- one per source), and its own tracked
selection. Switching the source switch never recomputes a ranking and never
silently changes which candidate a caller-facing action will use; it only
changes which existing _SourceView is visible.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, Sequence

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QDialog, QFormLayout, QHBoxLayout,
    QHeaderView, QLabel, QPushButton, QSizePolicy, QSplitter, QStackedWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from phase_studio.map_quality import (
    ResultCandidate, ResultRecommendation, ValidationProfile,
    ValidationProfileDefinition,
)
from phase_studio.ui_branding import (
    apply_safe_dialog_geometry, create_callout_label,
    create_phase_studio_brand_header, create_phase_studio_context_banner,
)


_COMPACT_METRIC_COLUMNS = {
    "reference_f05": ("F0.5 ↑", "Reference F0.5"),
    "reference_rmsd": ("RMSD (Å) ↓", "Matched-peak RMSD"),
    "reference_phase_agreement": ("Phase agreement ↑", "Reference phase agreement"),
    "r_free": ("R_free ↓", "R_free"),
    "cc_free": ("CC_free ↑", "CC_free"),
    "omit_map_correlation": ("OMIT CC ↑", "OMIT map correlation"),
    "amplitude_rf": ("R factor ↓", "Amplitude agreement R factor"),
    "amplitude_cc": ("Amplitude CC ↑", "Amplitude CC"),
    "triplet_c3": ("C3 ↑", "Weighted triplet C3"),
}

_MAP_FEEDBACK_COLUMN_LABEL = "Map Feedback Δ (%)"
_MAP_FEEDBACK_COLUMN_TOOLTIP = (
    "Average reflection-intensity change applied by Map Feedback intensity "
    "correction feeding into this cycle. Diagnostic only -- not used for "
    "the automatic recommendation."
)


def result_selection_metric_columns(
    definition: ValidationProfileDefinition,
) -> tuple[tuple[str, str, str], ...]:
    """Return compact heading, full accessible name, and metric key."""
    return tuple(
        (*_COMPACT_METRIC_COLUMNS[metric.key], metric.key)
        for metric in definition.primary_metrics
    )


def format_result_metric(value: Optional[float]) -> str:
    """Format candidate metrics consistently without changing their values."""
    return "n/a" if value is None else f"{float(value):.3f}"


def format_map_feedback_change_column(value: Optional[float]) -> str:
    """Format the restored Map Feedback diagnostic; unavailable stays "—",
    never a fabricated 0%."""
    return "—" if value is None else f"{float(value):+.1f}%"


def result_warning_callout_text(source: str, map_feedback_intensity_enabled: bool) -> Optional[str]:
    """Compact validation-warning text for the active source table, or None
    when no warning applies (plain Superflip with Map Feedback off)."""
    sharped = source == "deblurred"
    if sharped and map_feedback_intensity_enabled:
        return (
            "SharpED processes the electron-density map with a neural-network model, and Map "
            "Feedback may modify reflection data used by subsequent cycles. Validate the selected "
            "result against the original measured diffraction data and an independent "
            "crystallographic refinement."
        )
    if sharped:
        return (
            "SharpED uses a neural-network model for electron-density map processing. The selected "
            "result should be validated against the original measured diffraction data and an "
            "independent crystallographic refinement."
        )
    if map_feedback_intensity_enabled:
        return (
            "Map Feedback modified the reflection data supplied to subsequent cycles. The selected "
            "result should therefore be validated against the original measured diffraction data."
        )
    return None


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


def _build_candidate_table(
    ordered: Sequence[ResultCandidate],
    recommendation: ResultRecommendation,
    metric_columns: tuple[tuple[str, str, str], ...],
    show_feedback_column: bool,
) -> QTableWidget:
    headers = ["Recommended", "Cycle"] + [compact for compact, _full, _key in metric_columns]
    if show_feedback_column:
        headers.append(_MAP_FEEDBACK_COLUMN_LABEL)
    table = QTableWidget(len(ordered), len(headers))
    table.setObjectName("diagnosticTable")
    table.setHorizontalHeaderLabels(headers)
    table.setAlternatingRowColors(True)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.verticalHeader().setVisible(False)
    header = table.horizontalHeader()
    header.setMinimumSectionSize(58)
    header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
    header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
    metric_start = 2
    metric_end = metric_start + len(metric_columns)
    for column in range(metric_start, len(headers)):
        header.setSectionResizeMode(column, QHeaderView.Stretch)
        item = table.horizontalHeaderItem(column)
        full_name = (
            metric_columns[column - metric_start][1]
            if column < metric_end else _MAP_FEEDBACK_COLUMN_TOOLTIP
        )
        item.setToolTip(full_name)
        item.setData(Qt.AccessibleDescriptionRole, full_name)
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    for row, candidate in enumerate(ordered):
        cycle_text = str(candidate.cycle) + (" (map only)" if not candidate.usable_structure else "")
        values = [
            "★ Recommended" if candidate == recommendation.recommended_candidate else "",
            cycle_text,
        ] + [
            format_result_metric(candidate.metrics.value(key)) for _compact, _full, key in metric_columns
        ]
        if show_feedback_column:
            values.append(format_map_feedback_change_column(candidate.map_feedback_change_percent))
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setTextAlignment(
                (Qt.AlignLeft if column in (0, 1) else Qt.AlignRight) | Qt.AlignVCenter
            )
            item.setData(Qt.UserRole, row)
            table.setItem(row, column, item)
    visible_rows = min(8, max(6, len(ordered)))
    table.setMaximumHeight(
        header.sizeHint().height()
        + visible_rows * table.verticalHeader().defaultSectionSize()
        + 2 * table.frameWidth()
    )
    return table


class _SourceView:
    """Owns one source's ordered candidates, its recommendation, its table
    widget, and its current selection. Built once per dialog; switching the
    source switch never rebuilds it -- it only changes which view's
    container is the QStackedWidget's current widget."""

    def __init__(
        self,
        source: str,
        candidates: Sequence[ResultCandidate],
        recommendation: ResultRecommendation,
        metric_columns: tuple[tuple[str, str, str], ...],
        show_feedback_column: bool,
        table_title: str,
    ) -> None:
        self.source = source
        self.ordered: list[ResultCandidate] = sorted(candidates, key=lambda c: int(c.cycle))
        self.recommendation = recommendation
        self.selected: Optional[ResultCandidate] = (
            recommendation.selected_candidate
            if recommendation.selected_candidate in self.ordered
            else (self.ordered[0] if self.ordered else None)
        )
        self.table = _build_candidate_table(self.ordered, recommendation, metric_columns, show_feedback_column)
        if self.selected is not None:
            self.table.selectRow(self.ordered.index(self.selected))

        self.container = QWidget()
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(6)
        title_label = QLabel(table_title)
        title_label.setObjectName("sectionLabel")
        container_layout.addWidget(title_label)
        container_layout.addWidget(self.table)
        container_layout.addStretch(1)

    def current_row_candidate(self) -> Optional[ResultCandidate]:
        row = self.table.currentRow()
        if 0 <= row < len(self.ordered):
            return self.ordered[row]
        return None


class ResultSelectionDialog(QDialog):
    """Render independent Superflip/SharpED candidate sets and return the
    candidate currently selected in whichever source is active, without
    owning its effects."""

    def __init__(
        self,
        parent: QWidget,
        superflip_candidates: Sequence[ResultCandidate],
        sharped_candidates: Sequence[ResultCandidate],
        profile: ValidationProfile,
        definition: ValidationProfileDefinition,
        superflip_recommendation: ResultRecommendation,
        sharped_recommendation: ResultRecommendation,
        *,
        superflip_tab_available: bool,
        sharped_tab_available: bool,
        initial_source: str,
        map_feedback_intensity_enabled: bool,
        jana_context: bool,
        preview_host: object,
        parse_structure: Callable[[Path], Sequence[object]],
        reference_atoms: Sequence[object],
        source_title: Callable[[str], str],
    ) -> None:
        super().__init__(parent)
        self._jana_context = jana_context
        self._preview_host = preview_host
        self._parse_structure = parse_structure
        self._reference_atoms = reference_atoms
        self._source_title = source_title
        self._map_feedback_intensity_enabled = bool(map_feedback_intensity_enabled)
        self._definition = definition
        self._reference_available = profile in {
            ValidationProfile.REFERENCE_AND_HOLDOUT, ValidationProfile.REFERENCE_ONLY,
        }

        self.setObjectName("resultSelectionDialog")
        self.setProperty("resultContext", "JANA2020" if jana_context else "STANDALONE")
        self.setWindowTitle("Jana2020 result selection" if jana_context else "Save map and model")
        apply_safe_dialog_geometry(self, 1280, 760)
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

        metric_columns = result_selection_metric_columns(definition)
        show_feedback_column = self._map_feedback_intensity_enabled

        # --- Compact segmented source switch, shown only when there is a
        # genuine choice to make; a single-source workflow opens directly on
        # its one available table with no switch at all. ---
        self._superflip_btn: Optional[QPushButton] = None
        self._sharped_btn: Optional[QPushButton] = None
        if superflip_tab_available and sharped_tab_available:
            switch_row = QHBoxLayout()
            switch_row.setSpacing(6)
            switch_row.addWidget(QLabel("Result source"))
            superflip_btn = QPushButton(source_title("superflip"))
            sharped_btn = QPushButton(source_title("deblurred"))
            for btn in (superflip_btn, sharped_btn):
                btn.setObjectName("metricsViewToggle")
                btn.setCheckable(True)
                btn.setCursor(Qt.PointingHandCursor)
            switch_group = QButtonGroup(self)
            switch_group.setExclusive(True)
            switch_group.addButton(superflip_btn)
            switch_group.addButton(sharped_btn)
            switch_row.addWidget(superflip_btn)
            switch_row.addWidget(sharped_btn)
            switch_row.addStretch(1)
            content_layout.addLayout(switch_row)
            self._superflip_btn = superflip_btn
            self._sharped_btn = sharped_btn
            superflip_btn.toggled.connect(lambda checked: checked and self._apply_source("superflip"))
            sharped_btn.toggled.connect(lambda checked: checked and self._apply_source("deblurred"))

        summary_form = QFormLayout()
        summary_form.setHorizontalSpacing(18)
        summary_form.setVerticalSpacing(2)
        content_layout.addLayout(summary_form)
        self._summary_value_labels: dict[str, QLabel] = {}
        for label_text in ("Assessment", "Source", "Completed cycles", "Recommended cycle", "Reference", "Holdout"):
            value_label = QLabel("")
            font = value_label.font()
            font.setBold(True)
            value_label.setFont(font)
            summary_form.addRow(label_text, value_label)
            self._summary_value_labels[label_text] = value_label

        self._warning_callout = create_callout_label("Validation needed", "", "warning", compact=True)
        self._warning_callout.setVisible(False)
        content_layout.addWidget(self._warning_callout)

        reason_label = QLabel("")
        reason_label.setObjectName("recommendationReason")
        reason_label.setWordWrap(True)
        reason_label.setStyleSheet("color: #52658b;")
        content_layout.addWidget(reason_label)
        self._reason_label = reason_label

        self._stack = QStackedWidget()
        self._views: dict[str, _SourceView] = {}
        if superflip_tab_available:
            view = _SourceView(
                "superflip", superflip_candidates, superflip_recommendation,
                metric_columns, show_feedback_column,
                f"{source_title('superflip').upper()} CANDIDATES",
            )
            self._views["superflip"] = view
            self._stack.addWidget(view.container)
        if sharped_tab_available:
            view = _SourceView(
                "deblurred", sharped_candidates, sharped_recommendation,
                metric_columns, show_feedback_column,
                f"{source_title('deblurred').upper()} CANDIDATES",
            )
            self._views["deblurred"] = view
            self._stack.addWidget(view.container)
        for view in self._views.values():
            view.table.itemSelectionChanged.connect(
                lambda source=view.source: self._on_source_table_selection_changed(source)
            )

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
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._stack)
        splitter.addWidget(preview_section)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        content_layout.addWidget(splitter, 1)
        self._splitter = splitter
        QTimer.singleShot(0, self._set_initial_splitter_sizes)

        button_row = QHBoxLayout()
        close_button = QPushButton("Return to Phase Studio")
        button_row.addWidget(close_button)
        button_row.addStretch(1)
        button_row.addWidget(action_button)
        content_layout.addLayout(button_row)
        close_button.clicked.connect(self.reject)
        action_button.clicked.connect(self.accept)

        self._active_source = initial_source if initial_source in self._views else next(iter(self._views))
        if self._superflip_btn is not None:
            (self._superflip_btn if self._active_source == "superflip" else self._sharped_btn).setChecked(True)
        else:
            self._apply_source(self._active_source)

    def _set_initial_splitter_sizes(self) -> None:
        """Allocate enough table width for headings, then give preview the rest."""
        view = self._views.get(self._active_source)
        if view is None:
            return
        table = view.table
        header = table.horizontalHeader()
        table_width = sum(
            max(table.sizeHintForColumn(column), header.sectionSizeHint(column))
            for column in range(table.columnCount())
        ) + table.frameWidth() * 2 + 8
        available = max(1, self._splitter.width() - self._splitter.handleWidth())
        minimum_preview = max(420, int(available * 0.38))
        table_width = min(table_width, max(1, available - minimum_preview))
        self._splitter.setSizes([table_width, max(1, available - table_width)])

    @property
    def selected_candidate(self) -> Optional[ResultCandidate]:
        view = self._views.get(self._active_source)
        return view.selected if view is not None else None

    @property
    def active_source(self) -> str:
        return self._active_source

    @property
    def active_recommendation(self) -> Optional[ResultRecommendation]:
        view = self._views.get(self._active_source)
        return view.recommendation if view is not None else None

    def _apply_source(self, source: str) -> None:
        """Switch which source's table/summary/warning/preview is visible.
        Called only from the switch buttons' own toggled signal (or once,
        directly, when there is only one source and no switch at all) --
        never implicitly, so the active source only ever changes on an
        explicit user action."""
        view = self._views.get(source)
        if view is None:
            return
        self._active_source = source
        self._stack.setCurrentWidget(view.container)
        self._summary_value_labels["Assessment"].setText(self._definition.assessment_label)
        self._summary_value_labels["Source"].setText(self._source_title(source))
        self._summary_value_labels["Completed cycles"].setText(str(len(view.ordered)))
        recommended = view.recommendation.recommended_candidate
        self._summary_value_labels["Recommended cycle"].setText(
            str(recommended.cycle) if recommended is not None else "Unavailable"
        )
        self._summary_value_labels["Reference"].setText(
            "Available" if self._reference_available else "Not available"
        )
        free_count = max((candidate.metrics.n_free_reflections for candidate in view.ordered), default=0)
        self._summary_value_labels["Holdout"].setText(
            f"5% · {free_count} reflections" if free_count else "Not enabled"
        )
        self._reason_label.setText(view.recommendation.reason)
        warning_text = result_warning_callout_text(source, self._map_feedback_intensity_enabled)
        self._warning_callout.setVisible(warning_text is not None)
        if warning_text is not None:
            self._warning_callout.setText(f"<b>Validation needed</b><br>{warning_text}")
        if view.selected is not None:
            self._render_preview(view.selected)
        self._sync_action_button()

    def _on_source_table_selection_changed(self, source: str) -> None:
        view = self._views.get(source)
        if view is None:
            return
        candidate = view.current_row_candidate()
        if candidate is None:
            return
        view.selected = candidate
        if source != self._active_source:
            # A background table's selection changing must never touch the
            # preview or action button of whichever source is on screen.
            return
        self._render_preview(candidate)
        self._sync_action_button()

    def _sync_action_button(self) -> None:
        candidate = self.selected_candidate
        usable_structure = candidate.usable_structure if candidate is not None else True
        self._action_button.setText(
            "Pass to Jana2020" if self._jana_context else
            ("Save map and model" if usable_structure else "Save available result")
        )

    def _render_preview(self, candidate: ResultCandidate) -> None:
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
