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
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

import html
import json
import math
import gemmi
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.colors import to_rgb
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from mpl_toolkits.mplot3d.art3d import Line3DCollection
from PySide6.QtCore import Qt, QTimer, QSettings, QEvent, QPoint
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView, QButtonGroup, QDialog, QFormLayout, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QPushButton, QSizePolicy, QSplitter, QStackedWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
    QToolButton, QToolTip, QMessageBox,
)

from phase_studio.map_quality import (
    ResultCandidate, ResultRecommendation, ValidationProfile,
    ValidationProfileDefinition,
    recommend_best_result,
)
from phase_studio.ui_branding import (
    apply_safe_dialog_geometry, clamp_window_to_available_screen, create_callout_label,
    create_phase_studio_brand_header, create_phase_studio_context_banner,
)
from phase_studio.fullscreen_viewer import show_detached_viewer
from phase_studio.structure_camera import (
    StructureCameraController, fit_projected_structure, set_structure_viewport_clip,
    structure_marker_sizes, camera_settings_button,
)


_COMPACT_METRIC_COLUMNS = {
    "reference_f05": ("F0.5 ↑", "Reference F0.5"),
    "reference_rmsd": ("RMSD (Å) ↓", "Matched-peak RMSD"),
    "reference_phase_agreement": ("Phase agreement ↑", "Reference phase agreement"),
    "r_free": ("R_free ↓", "R_free"),
    "cc_free": ("CC_free ↑", "CC_free"),
    "omit_map_correlation": ("OMIT CC ↑", "OMIT map correlation"),
    "amplitude_rf": ("R factor ↓", "Amplitude consistency with original measured reflections; not independent refinement R. Scale is fitted to map FFT amplitudes."),
    "amplitude_cc": ("Amplitude CC ↑", "Pearson correlation of original measured amplitudes and map FFT amplitudes; imposed input amplitudes can give unity without validating phases."),
    "triplet_c3": ("C3 ↑", "Weighted triplet C3"),
}


class _MetricHeader(QHeaderView):
    """Keep scientific hover help inside the supporting table's width."""
    def __init__(self, table):
        super().__init__(Qt.Horizontal, table)
        self.sectionDoubleClicked.connect(self._details)

    def _details(self, section):
        item = self.parentWidget().horizontalHeaderItem(section)
        if item is not None:
            text = item.data(Qt.AccessibleDescriptionRole) or item.toolTip()
            QMessageBox.information(self.window(), item.text(), str(text))

    def viewportEvent(self, event):
        if event.type() == QEvent.ToolTip:
            index = self.logicalIndexAt(event.pos())
            item = self.parentWidget().horizontalHeaderItem(index) if index >= 0 else None
            if item is not None:
                full = str(item.data(Qt.AccessibleDescriptionRole) or item.toolTip())
                brief = full.split('. ')[0]
                if len(brief)>140: brief=brief[:137]+'…'
                width = max(100,min(220,self.width()-16))
                text = f'<p style="width:{width}px">{html.escape(brief)}<br>Double-click header for details.</p>'
                QToolTip.showText(self.mapToGlobal(QPoint(4,self.height())),text,self)
                return True
            QToolTip.hideText()
            return True
        return super().viewportEvent(event)

_MAP_FEEDBACK_COLUMN_LABEL = "Feedback Δ"
_MAP_FEEDBACK_COLUMN_TOOLTIP = (
    "Average reflection-intensity change applied by Map Feedback intensity "
    "correction feeding into this cycle. Diagnostic only -- not used for "
    "the automatic recommendation."
)
CAMERA_HELP_TEXT = (
    "Left-drag: rotate · Right/Middle/Shift-left-drag: pan · "
    "Wheel: zoom · Double-click: fit"
)


@dataclass(frozen=True)
class CandidateSelection:
    """Completed immutable candidate plus current filesystem/readiness evidence."""
    candidate: Optional[ResultCandidate]
    ready: bool
    geometry: bool
    reason: str
    pending: bool = False

    @property
    def identity(self) -> tuple:
        c = self.candidate
        return () if c is None else (c.run_id, c.source, c.cycle, c.candidate_id,
            c.map_sha256, c.edma_sigma, c.structure_sha256, c.jana_model_sha256)


@dataclass(frozen=True)
class ResolvedCandidateSnapshot:
    """One sealed candidate and its immutable, representation-specific geometry."""
    selection: CandidateSelection
    representation: str
    atoms: tuple
    coordinates: tuple
    bonds: tuple
    composition: str
    detected_count: int
    cell_segments: tuple

    @property
    def identity(self):
        return self.selection.identity


def candidate_selection(candidate, *, jana=True, pending=False) -> CandidateSelection:
    """Inspect sealed artifacts, never generate, repair or substitute them."""
    if candidate is None:
        return CandidateSelection(None, False, False, "No candidate selected.")
    from phase_studio.app import candidate_artifact_sha256, parse_cif_atoms
    c = candidate
    def present(path):
        return bool(path) and Path(path).is_file() and Path(path).stat().st_size > 0
    try:
        if not c.usable_map or not present(c.map_path):
            return CandidateSelection(c, False, False, "Map unavailable; scientific metrics remain available.")
        if c.map_sha256 and candidate_artifact_sha256(Path(c.map_path)) != c.map_sha256:
            return CandidateSelection(c, False, False, "Source map identity changed.")
        geometry = c.usable_structure and present(c.structure_path)
        if geometry and c.structure_sha256 and candidate_artifact_sha256(Path(c.structure_path)) != c.structure_sha256:
            return CandidateSelection(c, False, False, "EDMA structure identity changed.")
        if geometry:
            geometry = c.detected_atom_count > 0 if c.detected_atom_count is not None else bool(parse_cif_atoms(Path(c.structure_path)))
        if pending:
            return CandidateSelection(c, False, geometry, "EDMA recalculation pending; last completed structure retained.", True)
        if jana and not (c.candidate_id and c.map_sha256):
            return CandidateSelection(c, False, geometry, "Candidate identity is not sealed for handoff.")
        if jana and c.edma_enabled:
            if not geometry:
                return CandidateSelection(c, False, False, "Completed EDMA structure unavailable.")
            if not c.jana_model_sha256 or not present(c.jana_model_path):
                return CandidateSelection(c, False, geometry, "Corresponding Jana model unavailable.")
            if candidate_artifact_sha256(Path(c.jana_model_path)) != c.jana_model_sha256:
                return CandidateSelection(c, False, geometry, "Jana model identity changed.")
            if c.jana_model_site_count is None or c.jana_model_site_count <= 0:
                return CandidateSelection(c, False, geometry, "Jana model contains no validated atomic sites.")
        return CandidateSelection(c, True, geometry, "Ready for handoff." if jana else "Ready for export.")
    except (OSError, ValueError, RuntimeError):
        return CandidateSelection(c, False, False, "Candidate artifacts could not be read.")


class ResultFamilySegment(QPushButton):
    """Single-line family choice with a full accessible source description."""

    def __init__(self, title: str, subtitle: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setText("")
        self.setObjectName("resultFamilySegment")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 7, 14, 7)
        layout.setSpacing(2)
        self.title_label = QLabel(title)
        self.subtitle_label = QLabel(subtitle)
        title_font = self.title_label.font()
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        for label in (self.title_label, self.subtitle_label):
            label.setAlignment(Qt.AlignCenter)
            label.setAttribute(Qt.WA_TransparentForMouseEvents)
            if label is self.title_label:
                layout.addWidget(label)
        self.subtitle_label.hide()
        self.setToolTip(subtitle)
        self.setAccessibleName(title)
        margins = layout.contentsMargins()
        self.setMinimumHeight(
            self.title_label.fontMetrics().lineSpacing()
            + margins.top() + margins.bottom() + layout.spacing()
        )
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.toggled.connect(self._sync_label_colors)
        self._sync_label_colors(False)

    def _sync_label_colors(self, checked: bool) -> None:
        color = "#ffffff" if checked else "#001170"
        for label in (self.title_label, self.subtitle_label):
            label.setStyleSheet(f"color:{color}; background:transparent;")


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
    return "n/a" if value is None or not math.isfinite(float(value)) else f"{float(value):.3f}"


def recorded_edma_site_lineage(candidate: ResultCandidate) -> dict:
    """Read only the matching completed export's diagnostic sidecar.

    Counts from another threshold or a different retained CIF are not evidence
    for this candidate. The Jana count remains the sealed m40 authority.
    """
    path = Path(candidate.structure_path)
    try:
        data = json.loads(path.with_name(path.stem + "_site_counts.json").read_text(encoding="utf-8"))
        if (float(data["threshold_sigma"]) != candidate.edma_sigma
                or int(data["cif_sites"]) != candidate.detected_atom_count):
            return {}
        counts = {key: int(data[key]) for key in ("raw_edma_sites", "cif_sites", "independent_asu_sites")}
        return counts if all(value >= 0 for value in counts.values()) else {}
    except (OSError, ValueError, TypeError, KeyError):
        return {}


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
            "Map Feedback modified reflection inputs. Validate SharpED neural-network predictions against "
            "original measured diffraction data and independent crystallographic refinement."
        )
    if sharped:
        return (
            "SharpED predictions must be validated against original measured diffraction data "
            "and independent crystallographic refinement."
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
    headers = ["★", "Cycle"] + [compact for compact, _full, _key in metric_columns]
    if show_feedback_column:
        headers.append(_MAP_FEEDBACK_COLUMN_LABEL)
    table = QTableWidget(len(ordered), len(headers))
    table.setHorizontalHeader(_MetricHeader(table))
    table.setObjectName("diagnosticTable")
    table.setHorizontalHeaderLabels(headers)
    table.setAlternatingRowColors(True)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    table.verticalHeader().setVisible(False)
    header = table.horizontalHeader()
    header.setStyleSheet("QHeaderView::section { padding:3px 4px; font-size:9pt; }")
    header_font = header.font()
    if header_font.pointSizeF() > 9.0:
        header_font.setPointSizeF(9.0)
        header.setFont(header_font)
    header.ensurePolished()
    header_metrics = header.fontMetrics()
    header.setMinimumSectionSize(35)
    header.setSectionResizeMode(0, QHeaderView.Fixed)
    header.setSectionResizeMode(1, QHeaderView.Interactive)
    header.resizeSection(0, 40)
    table.horizontalHeaderItem(0).setToolTip("Recommended candidate; the highlighted row is your selection.")
    longest_cycle = max((str(candidate.cycle) for candidate in ordered), key=len, default="1")
    header.resizeSection(
        1, max(header_metrics.horizontalAdvance("Cycle"),
               table.fontMetrics().horizontalAdvance(longest_cycle)) + 20,
    )
    metric_start = 2
    metric_end = metric_start + len(metric_columns)
    for column in range(metric_start, len(headers)):
        header.setSectionResizeMode(column, QHeaderView.Interactive)
        item = table.horizontalHeaderItem(column)
        full_name = (
            metric_columns[column - metric_start][1]
            if column < metric_end else _MAP_FEEDBACK_COLUMN_TOOLTIP
        )
        item.setToolTip(full_name)
        item.setData(Qt.AccessibleDescriptionRole, full_name)
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        key = metric_columns[column - metric_start][2] if column < metric_end else None
        values = [
            format_result_metric(candidate.metrics.value(key)) if key else
            format_map_feedback_change_column(candidate.map_feedback_change_percent)
            for candidate in ordered
        ]
        minimum = max(
            header_metrics.horizontalAdvance(item.text()) + 10,
            max((table.fontMetrics().horizontalAdvance(value) + 16 for value in values), default=0),
        )
        header.resizeSection(column, minimum)
    for row, candidate in enumerate(ordered):
        # The source is already stated in the table title and dynamic summary;
        # repeating it in every row consumed the table's 35–40% allocation.
        if not candidate.edma_enabled:
            cycle_suffix = " (EDMA disabled)"
        elif not candidate.usable_structure:
            cycle_suffix = " (map only)"
        else:
            cycle_suffix = ""
        cycle_text = f"{candidate.cycle}{cycle_suffix}"
        values = [
            "★" if candidate == recommendation.recommended_candidate else "",
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
            if column == 1:
                item.setToolTip(f"Cycle {cycle_text}")
            elif 2 <= column < 2 + len(metric_columns):
                _heading, definition, key = metric_columns[column - 2]
                raw = candidate.metrics.value(key)
                item.setToolTip("Unrounded value: " + (
                    f"{float(raw):.12g}" if raw is not None and math.isfinite(float(raw)) else "unavailable"))
            table.setItem(row, column, item)
    # One result must not reserve six empty table rows and starve the preview.
    # Two rows keeps the header/selection comfortable; additional cycles grow
    # naturally up to the established eight-row cap.
    visible_rows = min(8, max(2, len(ordered)))
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
        jana_context: bool = False,
    ) -> None:
        self.source = source
        self.ordered: list[ResultCandidate] = sorted(candidates, key=lambda c: int(c.cycle))
        self.recommendation = recommendation
        self.manually_selected = False
        self.table = _build_candidate_table(self.ordered, recommendation, metric_columns, show_feedback_column)
        ready = [c for c in self.ordered if candidate_selection(c, jana=jana_context).ready]
        best_ready = recommend_best_result(recommendation.profile, ready).selected_candidate
        self.selected = best_ready or recommendation.recommended_candidate or (self.ordered[0] if self.ordered else None)
        for row, candidate in enumerate(self.ordered):
            status = candidate_selection(candidate, jana=jana_context)
            self.table.item(row, 1).setToolTip(f"Cycle {candidate.cycle} · {status.reason}")

        self.container = QWidget()
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(6)
        title_label = QLabel(table_title)
        title_label.setObjectName("sectionLabel")
        title_label.setWordWrap(True)
        container_layout.addWidget(title_label)
        container_layout.addWidget(self.table)
        container_layout.addStretch(1)

    def current_row_candidate(self) -> Optional[ResultCandidate]:
        row = self.table.currentRow()
        if 0 <= row < len(self.ordered):
            return self.ordered[row]
        return None

    @property
    def selected(self) -> Optional[ResultCandidate]:
        return self.current_row_candidate()

    @selected.setter
    def selected(self, candidate) -> None:
        if candidate is None:
            self.table.clearSelection()
            self.table.setCurrentCell(-1, -1)
            return
        if candidate in self.ordered:
            row = self.ordered.index(candidate)
        else:
            key = lambda c: (c.run_id, c.source, c.cycle, c.map_sha256 or c.map_path)
            row = next((i for i, c in enumerate(self.ordered) if key(c) == key(candidate)), None)
            if row is None:
                return
            self.ordered[row] = candidate
        if self.table.currentRow() != row or not self.table.selectionModel().selectedRows():
            self.table.selectRow(row)


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
        authoritative_composition: str = "",
        authoritative_composition_label: str = "Composition",
        adjust_threshold: Optional[Callable[[ResultCandidate, bool], Optional[ResultCandidate]]] = None,
        adjust_threshold_async: Optional[Callable[[ResultCandidate, bool, Callable], object]] = None,
    ) -> None:
        super().__init__(parent)
        self._jana_context = jana_context
        self._preview_host = preview_host
        self._parse_structure = parse_structure
        self._reference_atoms = reference_atoms
        self._source_title = source_title
        self._authoritative_composition = str(authoritative_composition or "")
        self._authoritative_composition_label = str(
            authoritative_composition_label or "Composition"
        )
        self._adjust_threshold = adjust_threshold
        self._adjust_threshold_async = adjust_threshold_async
        self._closed = False
        self._pending_thresholds: dict[tuple, object] = {}
        self._map_feedback_intensity_enabled = bool(map_feedback_intensity_enabled)
        self._definition = definition
        self._reference_available = profile in {
            ValidationProfile.REFERENCE_AND_HOLDOUT, ValidationProfile.REFERENCE_ONLY,
        }
        self._view_mode = "molecule"
        self._auto_rotate_enabled = True
        self._current_candidate: Optional[ResultCandidate] = None
        self.preview_candidate_id = ""
        self.preview_structure_hash = ""
        self._current_formula = ""
        self._presentation_cache: dict = {}
        self._detached_viewer = None
        self._preview_user_interacted = False
        self._preview_fit_timer = QTimer(self)
        self._preview_fit_timer.setSingleShot(True)
        self._preview_fit_timer.setInterval(0)
        self._preview_fit_timer.timeout.connect(self._fit_preview)

        self.setObjectName("resultSelectionDialog")
        self.setProperty("resultContext", "JANA2020" if jana_context else "STANDALONE")
        self.setWindowTitle("Jana2020 result selection" if jana_context else "Save map and model")
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
        content_layout.setContentsMargins(14, 8, 14, 7)
        content_layout.setSpacing(5)
        outer_layout.addWidget(content, 1)

        metric_columns = result_selection_metric_columns(definition)
        show_feedback_column = self._map_feedback_intensity_enabled

        # --- Primary handoff decision, shown only when there is a
        # genuine choice to make; a single-source workflow opens directly on
        # its one available table with no switch at all. ---
        self._superflip_btn: Optional[QPushButton] = None
        self._sharped_btn: Optional[QPushButton] = None
        if superflip_tab_available and sharped_tab_available:
            switch_row = QHBoxLayout()
            switch_row.setSpacing(0)
            switch_label = QLabel("HANDOFF OUTPUT")
            switch_label.setObjectName("sectionLabel")
            content_layout.addWidget(switch_label)
            superflip_btn = ResultFamilySegment("CHARGE-FLIPPING SOLUTION", "Superflip phase solution")
            sharped_btn = ResultFamilySegment("STRUCTURE PREDICTION", "SharpED-processed map")
            for btn in (superflip_btn, sharped_btn):
                btn.setStyleSheet(
                    "QPushButton { background:#ffffff; color:#001170; border:1px solid #3158a6; "
                    "font-weight:600; text-align:center; }"
                    "QPushButton:checked { background:#001170; color:#ffffff; border-color:#001170; }"
                    "QPushButton:focus { border:2px solid #1fa5ff; }"
                    "QPushButton:hover:!checked { background:#eef4ff; }"
                )
            switch_group = QButtonGroup(self)
            switch_group.setExclusive(True)
            switch_group.addButton(superflip_btn)
            switch_group.addButton(sharped_btn)
            switch_row.addWidget(superflip_btn)
            switch_row.addWidget(sharped_btn)
            content_layout.addLayout(switch_row)
            self._output_description = QLabel("")
            self._output_description.setObjectName("resultOutputDescription")
            self._output_description.setWordWrap(True)
            self._output_description.setStyleSheet("color:#334766; padding:2px 4px;")
            self._output_description.setVisible(False)
            self._superflip_btn = superflip_btn
            self._sharped_btn = sharped_btn
            superflip_btn.toggled.connect(lambda checked: checked and self._apply_source("superflip"))
            sharped_btn.toggled.connect(lambda checked: checked and self._apply_source("deblurred"))

        summary_form = QGridLayout()
        summary_form.setHorizontalSpacing(12)
        summary_form.setVerticalSpacing(1)
        content_layout.addLayout(summary_form)
        self._summary_value_labels: dict[str, QLabel] = {}
        for index, label_text in enumerate(("Assessment", "Source", "Available cycles", "Recommended cycle", "Reference", "Holdout")):
            value_label = QLabel("")
            font = value_label.font()
            font.setBold(True)
            value_label.setFont(font)
            column = (index % 3) * 2
            row = index // 3
            heading = QLabel(label_text)
            if label_text not in {"Reference", "Holdout"} or (
                label_text == "Reference" and self._reference_available
            ) or (
                label_text == "Holdout" and profile in {
                    ValidationProfile.HOLDOUT_ONLY, ValidationProfile.REFERENCE_AND_HOLDOUT,
                }
            ):
                summary_form.addWidget(heading, row, column)
                summary_form.addWidget(value_label, row, column + 1)
            else:
                heading.hide(); value_label.hide()
            self._summary_value_labels[label_text] = value_label

        self._warning_callout = create_callout_label("Validation needed", "", "warning", compact=True)
        self._warning_callout.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._warning_callout.setStyleSheet("background:#f3f5f8; color:#334766; padding:4px 8px;")
        warning_policy = self._warning_callout.sizePolicy()
        warning_policy.setRetainSizeWhenHidden(False)
        self._warning_callout.setSizePolicy(warning_policy)
        self._warning_callout.setFixedHeight(self._warning_callout.fontMetrics().lineSpacing() * 2 + 8)
        self._warning_callout.setVisible(False)

        reason_label = QLabel("")
        reason_label.setObjectName("recommendationReason")
        reason_label.setWordWrap(True)
        reason_label.setStyleSheet("color: #52658b;")
        reason_label.setVisible(False)
        self._reason_label = reason_label

        self._stack = QStackedWidget()
        self._stack.setMinimumWidth(300)
        self._stack.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self._views: dict[str, _SourceView] = {}
        if superflip_tab_available:
            view = _SourceView(
                "superflip", superflip_candidates, superflip_recommendation,
                metric_columns, show_feedback_column,
                "CHARGE-FLIPPING SOLUTION CANDIDATES  ·  SOURCE: SUPERFLIP",
                jana_context=jana_context,
            )
            self._views["superflip"] = view
            self._stack.addWidget(view.container)
        if sharped_tab_available:
            view = _SourceView(
                "deblurred", sharped_candidates, sharped_recommendation,
                metric_columns, show_feedback_column,
                "STRUCTURE PREDICTION CANDIDATES  ·  SOURCE: SHARPED",
                jana_context=jana_context,
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
        preview_canvas.setFocusPolicy(Qt.StrongFocus)
        # This is the flexible region.  A large canvas minimum used to force
        # the native dialog taller after its pre-layout screen clamp, placing
        # the handoff actions below the Windows work area on short monitors.
        preview_canvas.setMinimumHeight(130)
        preview_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        preview_host.structure_canvas = preview_canvas
        self._preview_canvas = preview_canvas
        # Detaching reparents the canvas without resizing this dialog. Refit
        # against its actual viewport, unless the user has set their camera.
        preview_canvas.mpl_connect("resize_event", self._on_preview_resize)

        action_button = QPushButton("Pass to Jana2020" if jana_context else "Save map and model")
        action_button.setObjectName("primaryButton")
        self._action_button = action_button

        preview_section = QWidget()
        self._preview_section = preview_section
        preview_section.setStyleSheet("QToolButton:disabled { color:#8a96ac; background:#f4f6f9; border:1px solid #dde3ed; }")
        preview_section.setMinimumWidth(420)
        preview_section.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        preview_layout = QVBoxLayout(preview_section)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_label = QLabel("STRUCTURE PREVIEW")
        preview_label.setObjectName("sectionLabel")
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        toolbar.addWidget(preview_label)
        toolbar.addStretch(1)
        self._previous_cycle_button = QToolButton()
        self._previous_cycle_button.setText("◀")
        self._previous_cycle_button.setToolTip("Show the previous completed cycle for this output family.")
        self._next_cycle_button = QToolButton()
        self._next_cycle_button.setText("▶")
        self._next_cycle_button.setToolTip("Show the next completed cycle for this output family.")
        self._latest_cycle_button = QToolButton()
        self._latest_cycle_button.setText("Latest")
        self._latest_cycle_button.setToolTip("Show the latest completed cycle for this output family.")
        self._latest_cycle_button.setCheckable(True)
        self._fit_button = QToolButton()
        self._fit_button.setText("Fit")
        self._reset_button = QToolButton()
        self._reset_button.setText("Reset view")
        self._auto_rotate_button = QToolButton()
        self._auto_rotate_button.setText("Auto rotate: On")
        self._auto_rotate_button.setCheckable(True)
        self._auto_rotate_button.setChecked(True)
        self._fullscreen_button = QToolButton()
        self._fullscreen_button.setText("Fullscreen")
        self._fullscreen_button.setToolTip("Open this live result viewer fullscreen (F11; Esc closes).")
        self._add_atoms_button = QToolButton()
        self._add_atoms_button.setText("+ atoms")
        self._add_atoms_button.setToolTip("Lower only this candidate's EDMA threshold and recalculate its structure.")
        self._remove_atoms_button = QToolButton()
        self._remove_atoms_button.setText("- atoms")
        self._remove_atoms_button.setToolTip("Raise only this candidate's EDMA threshold and recalculate its structure.")
        self._threshold_status = QLabel("")
        self._threshold_status.setObjectName("autosolveReviewStatus")
        self._molecule_button = QToolButton()
        self._molecule_button.setText("Complete molecules")
        self._molecule_button.setCheckable(True)
        self._molecule_button.setChecked(True)
        self._cell_button = QToolButton()
        self._cell_button.setText("Full cell")
        self._cell_button.setCheckable(True)
        mode_group = QButtonGroup(self)
        mode_group.setExclusive(True)
        mode_group.addButton(self._molecule_button)
        mode_group.addButton(self._cell_button)
        for button in (self._previous_cycle_button, self._next_cycle_button, self._latest_cycle_button):
            button.setCursor(Qt.PointingHandCursor)
            toolbar.addWidget(button)
        toolbar.addSpacing(10)
        for button in (self._fit_button, self._fullscreen_button):
            button.setCursor(Qt.PointingHandCursor)
            toolbar.addWidget(button)
        preview_layout.addLayout(toolbar)
        view_toolbar = QHBoxLayout()
        view_toolbar.setSpacing(6)
        view_toolbar.addWidget(self._threshold_status)
        for button in (self._add_atoms_button, self._remove_atoms_button):
            button.setCursor(Qt.PointingHandCursor)
            view_toolbar.addWidget(button)
        view_toolbar.addStretch(1)
        view_toolbar.addWidget(camera_settings_button(self))
        view_toolbar.addWidget(QLabel("View:"))
        for button in (self._molecule_button, self._cell_button, self._auto_rotate_button):
            button.setCursor(Qt.PointingHandCursor)
            view_toolbar.addWidget(button)
        self._fullscreen_button.setCursor(Qt.PointingHandCursor)
        self._reset_button.setParent(self)
        self._reset_button.hide()  # Reset remains available through the canvas R key.
        self._fit_button.setToolTip("Fit visible geometry. Double-click to fit; press R to reset orientation.")
        preview_layout.addLayout(view_toolbar)
        camera_hint = QLabel(CAMERA_HELP_TEXT)
        camera_hint.setObjectName("structureInteractionHint")
        camera_hint.setAlignment(Qt.AlignRight)
        camera_hint.setToolTip(CAMERA_HELP_TEXT)
        hint_font = camera_hint.font()
        if hint_font.pointSizeF() > 8.0:
            hint_font.setPointSizeF(8.0)
            camera_hint.setFont(hint_font)
        preview_layout.addWidget(camera_hint)
        self._camera_hint = camera_hint
        camera_hint.setVisible(True)
        preview_canvas.setToolTip("")
        self._metadata_label = QLabel("")
        self._metadata_label.setObjectName("autosolveReviewDetail")
        self._metadata_label.setWordWrap(True)
        preview_layout.addWidget(self._metadata_label)
        self._element_legend = QLabel("")
        self._element_legend.setObjectName("elementLegend")
        self._element_legend.setTextFormat(Qt.RichText)
        self._element_legend.setWordWrap(True)
        self._element_legend.setVisible(False)
        preview_layout.addWidget(self._element_legend)
        preview_layout.addWidget(preview_canvas, 1)

        self._fit_button.clicked.connect(self._request_preview_fit)
        self._previous_cycle_button.clicked.connect(lambda: self._step_cycle(-1))
        self._next_cycle_button.clicked.connect(lambda: self._step_cycle(1))
        self._latest_cycle_button.clicked.connect(self._select_latest_cycle)
        self._reset_button.clicked.connect(self._reset_preview)
        self._auto_rotate_button.toggled.connect(self._toggle_auto_rotate)
        self._add_atoms_button.clicked.connect(lambda: self._change_threshold(True))
        self._remove_atoms_button.clicked.connect(lambda: self._change_threshold(False))
        self._fullscreen_button.clicked.connect(self._open_fullscreen)
        self._molecule_button.toggled.connect(
            lambda checked: checked and self._set_view_mode("molecule")
        )
        self._cell_button.toggled.connect(
            lambda checked: checked and self._set_view_mode("cell")
        )
        self._camera = StructureCameraController(
            preview_canvas,
            lambda: preview_host._structure_interactive_axes,
            fit=self._fit_preview,
            reset=self._reset_preview,
            orientation_changed=self._preview_orientation_changed,
            interaction=self._preview_camera_interaction,
            toggle_auto_rotate=lambda: self._auto_rotate_button.toggle(),
        )
        self._rotate_timer = QTimer(self)
        self._rotate_timer.timeout.connect(self._auto_rotate_tick)
        self._rotate_timer.start(60)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._stack)
        splitter.addWidget(preview_section)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        splitter.setMinimumHeight(150)
        content_layout.addWidget(splitter, 1)
        self._splitter = splitter
        self._splitter_user_resized = False
        self._setting_splitter_sizes = False
        splitter.splitterMoved.connect(self._on_splitter_moved)
        QTimer.singleShot(0, self._set_initial_splitter_sizes)

        self._selected_output_summary = QLabel("")
        self._selected_output_summary.setObjectName("selectedOutputSummary")
        self._selected_output_summary.setWordWrap(True)
        self._selected_output_summary.setMinimumHeight(55)
        self._selected_output_summary.setStyleSheet(
            "QLabel { background:#eef4ff; border:1px solid #b9cae8; border-radius:4px; "
            "padding:4px 10px; color:#142b55; }"
        )
        # One fixed footer owns both the selected-result statement and the
        # actions.  It sits outside the shrinking splitter/content region and
        # therefore always receives its complete sizeHint.
        footer = QWidget()
        footer.setObjectName("wizardFooter")
        footer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(14, 4, 14, 5)
        footer_layout.setSpacing(4)
        footer_layout.addWidget(self._warning_callout)
        footer_layout.addWidget(self._selected_output_summary)
        button_row = QHBoxLayout()
        close_button = QPushButton("Return to Phase Studio")
        button_row.addWidget(close_button)
        button_row.addStretch(1)
        button_row.addWidget(action_button)
        footer_layout.addLayout(button_row)
        outer_layout.addWidget(footer, 0)
        self._footer = footer
        self._close_button = close_button
        close_button.clicked.connect(self.reject)
        action_button.clicked.connect(self.accept)

        self._initializing_selection = True
        self._source_explicit = False
        self._active_source = initial_source if initial_source in self._views else next(iter(self._views))
        self._sharped_expected = sharped_tab_available
        self._automatic_fallback = False
        if jana_context and self._active_source == "deblurred":
            sharped_ready = any(candidate_selection(c).ready for c in self._views['deblurred'].ordered)
            superflip = self._views.get('superflip')
            if not sharped_ready and superflip and any(candidate_selection(c).ready for c in superflip.ordered):
                self._active_source = 'superflip'
                self._automatic_fallback = True
        if self._superflip_btn is not None:
            (self._superflip_btn if self._active_source == "superflip" else self._sharped_btn).setChecked(True)
        else:
            self._output_description = QLabel("")
            self._output_description.setVisible(False)
            self._apply_source(self._active_source)

        # Clamp only after every child and its minimumSizeHint exists.  Repeat
        # once after the window manager supplies the final native frame.
        self.layout().activate()
        self._apply_safe_initial_geometry()
        QTimer.singleShot(0, self._clamp_after_show)
        self._initializing_selection = False

    def _apply_safe_initial_geometry(self) -> None:
        apply_safe_dialog_geometry(
            self, 1180, 680, width_fraction=0.90, height_fraction=0.84,
        )
        # This is the measured practical minimum for the compact header,
        # toolbar, 150 px scientific canvas, and fixed handoff footer.  On a
        # shorter work area, retain the largest safe initial height instead.
        self.setMinimumHeight(min(670, self.height()))

    def _clamp_after_show(self) -> None:
        clamp_window_to_available_screen(
            self, width_fraction=0.90, height_fraction=0.84,
            center_if_resized=True,
        )

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        if hasattr(self, "_element_legend"):
            # Composition and EDMA state remain visible at every size; the
            # redundant color key yields first on short work areas.
            self._element_legend.setVisible(self.height() >= 700)
        if hasattr(self, "_camera_hint"):
            self._camera_hint.setVisible(self.height() >= 700)
        if hasattr(self, "_reason_label"):
            # The recommendation is already identified in the summary/table.
            # On short work areas, yield this duplicate prose row to the
            # scientific canvas while the fixed handoff footer stays visible.
            self._reason_label.setVisible(False)
        if hasattr(self, "_splitter") and not getattr(self, "_splitter_user_resized", False):
            QTimer.singleShot(0, self._set_initial_splitter_sizes)
        if hasattr(self, "_preview_fit_timer") and not self._preview_user_interacted:
            self._preview_fit_timer.start()

    def _open_fullscreen(self) -> None:
        family = "Charge-flipping solution" if self._active_source == "superflip" else "Structure prediction"
        self._fullscreen_button.setVisible(False)
        previous = self._detached_viewer
        self._detached_viewer = show_detached_viewer(
            self, self._preview_section, f"{family} — Cycle {self.selected_candidate.cycle}" if self.selected_candidate else family, self._detached_viewer,
        )
        if self._detached_viewer is not previous:
            self._detached_viewer.finished.connect(self._restore_fullscreen_action)
        self._sync_detached_identity(self.selected_candidate)
        # Detach the existing view without replacing its selected candidate,
        # threshold, representation or deliberately chosen camera.

    def _restore_fullscreen_action(self, _result: int = 0) -> None:
        self._fullscreen_button.setVisible(True)

    def _change_threshold(self, add_atoms: bool) -> None:
        candidate = self.selected_candidate
        if candidate is None:
            return
        if self._adjust_threshold_async is not None:
            def completed(updated, report, request) -> None:
                self._apply_async_threshold_result(candidate, updated, report, request)
            request = self._adjust_threshold_async(candidate, add_atoms, completed)
            if request is not None:
                self._pending_thresholds[self._threshold_key(candidate)] = request
                self._threshold_status.setText(
                    f"EDMA {float(request.threshold):.2f} σ · updating… "
                    f"Current handoff: EDMA {float(candidate.edma_sigma):.2f} σ"
                )
                self._sync_action_button()
            return
        if self._adjust_threshold is None:
            return
        updated = self._adjust_threshold(candidate, add_atoms)
        if updated is None:
            return
        view = self._views[self._active_source]
        try:
            index = view.ordered.index(candidate)
        except ValueError:
            return
        view.ordered[index] = updated
        view.selected = updated
        self._render_preview(updated)
        self._sync_action_button()

    def _apply_async_threshold_result(self, original, updated, report, request) -> None:
        if self._closed:
            return
        key = self._threshold_key(original)
        if self._pending_thresholds.get(key) is not request:
            return
        self._pending_thresholds.pop(key, None)
        if report is not None:
            if self.selected_candidate is not None and self._threshold_key(self.selected_candidate) == key:
                self._threshold_status.setText(
                    "EDMA threshold update failed. Previous completed structure retained."
                )
            self._sync_action_button()
            return
        if updated is None:
            self._sync_action_button()
            return
        if self._threshold_key(updated) != key:
            self._sync_action_button()
            return
        if updated.edma_sigma is None or not math.isclose(float(updated.edma_sigma), float(request.threshold), abs_tol=1e-9, rel_tol=0):
            self._threshold_status.setText("Discarded an EDMA completion for a different threshold. Previous completed structure retained.")
            self._sync_action_button()
            return
        view = self._views.get(original.source)
        if view is None:
            return
        index = next((
            i for i, item in enumerate(view.ordered)
            if item.cycle == original.cycle and item.map_sha256 == original.map_sha256
        ), None)
        if index is None:
            return
        if view.ordered[index] != original:
            self._sync_action_button()
            return  # An older completed generation cannot replace a newer one.
        was_selected = view.selected is not None and (
            view.selected.cycle == original.cycle
            and view.selected.map_sha256 == original.map_sha256
        )
        view.ordered[index] = updated
        if was_selected:
            view.selected = updated
        if was_selected and self._active_source == original.source:
            self._render_preview(updated)
        self._sync_action_button()

    @staticmethod
    def _threshold_key(candidate: ResultCandidate) -> tuple:
        return (candidate.run_id, candidate.source, candidate.cycle,
                candidate.map_sha256 or candidate.map_path)

    def done(self, result: int) -> None:
        self._closed = True
        detached = getattr(self,'_detached_viewer',None)
        if detached is not None and not detached._restored:
            detached.close()
        super().done(result)

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
        ) + table.frameWidth() * 2 + table.verticalScrollBar().sizeHint().width() + 8
        required_width = (
            sum(table.columnWidth(column) for column in range(table.columnCount()))
            + table.frameWidth() * 2 + table.verticalScrollBar().sizeHint().width() + 4
        )
        available = max(1, self._splitter.width() - self._splitter.handleWidth())
        minimum_preview = max(420, int(available * 0.55))
        # The candidate table is supporting evidence; the scientific viewer
        # remains the dominant 66-70% of the dialog while retaining enough room
        # for every compact heading.
        try:
            share = float(QSettings('PhaseStudio','PhaseStudio').value('viewer/resultSelectionTableShare', .28))
            share = max(.20,min(.50,share)) if math.isfinite(share) else .28
        except (ValueError,TypeError):
            share = .28
        table_width = int(available * share)
        table_width = max(table_width, required_width + 48)
        table_width = min(table_width, max(1, available - minimum_preview))
        self._setting_splitter_sizes = True
        try:
            self._splitter.setSizes([table_width, max(1, available - table_width)])
        finally:
            self._setting_splitter_sizes = False

    def _on_splitter_moved(self, *_args) -> None:
        if not self._setting_splitter_sizes:
            self._splitter_user_resized = True
            sizes = self._splitter.sizes()
            if sum(sizes)>0:
                settings = QSettings('PhaseStudio','PhaseStudio')
                settings.setValue('viewer/resultSelectionTableShare', sizes[0]/sum(sizes))
                settings.sync()

    @property
    def selected_candidate(self) -> Optional[ResultCandidate]:
        accepted = getattr(self, '_accepted_selection', None)
        if accepted is not None:
            return accepted.candidate
        view = self._views.get(self._active_source)
        return view.selected if view is not None else None

    @property
    def selection_snapshot(self) -> CandidateSelection:
        candidate = self.selected_candidate
        return candidate_selection(candidate, jana=self._jana_context,
            pending=candidate is not None and self._threshold_key(candidate) in self._pending_thresholds)

    def accept(self) -> None:
        snapshot = self.selection_snapshot
        rendered = getattr(self, '_resolved_preview', None)
        if not snapshot.ready:
            self._sync_action_button()
            return  # Keep the explanation visible; never substitute another row.
        if snapshot.geometry and (rendered is None or rendered.identity != snapshot.identity):
            self._selected_output_summary.setText('Selected scientific structure is inconsistent with the preview. Reselect the candidate before passing it to Jana2020.')
            self._action_button.setEnabled(False)
            return
        self._accepted_selection = snapshot
        super().accept()

    def selection_state(self) -> dict:
        return {"source": self._active_source if self._source_explicit else None, "mode": self._view_mode,
                "fallback_shown": self._automatic_fallback,
                "rotate": self._auto_rotate_enabled,
                "candidates": {source: self._threshold_key(view.selected)
                               for source, view in self._views.items() if view.selected and view.manually_selected}}

    def restore_selection(self, state: dict) -> None:
        self._automatic_fallback = False
        for source, identity in state.get("candidates", {}).items():
            view = self._views.get(source)
            if view is not None:
                for row, candidate in enumerate(view.ordered):
                    if self._threshold_key(candidate) == identity:
                        view.table.selectRow(row)
                        break
        self._auto_rotate_button.setChecked(state.get("rotate", True))
        mode = state.get("mode", "molecule")
        (self._cell_button if mode == "cell" else self._molecule_button).setChecked(True)
        source = state.get("source")
        if source in self._views:
            button = self._superflip_btn if source == "superflip" else self._sharped_btn
            if button is not None:
                button.setChecked(True)
            self._apply_source(source)
        self._automatic_fallback = False
        self._sync_action_button()

    def set_fallback_message(self, message: str) -> None:
        self._fallback_message = message
        self._warning_callout.setText(html.escape(message))
        self._warning_callout.show()

    def set_sharped_expected(self, *, automatic: bool) -> None:
        self._sharped_expected = True
        self._automatic_fallback = automatic and self.active_source == 'superflip'
        self._sync_action_button()

    def _show_empty_preview(self, candidate=None, reason="") -> None:
        self._current_candidate = candidate
        self._resolved_preview = None
        self._sync_detached_identity(candidate)
        self.preview_candidate_id = ""
        self.preview_structure_hash = ""
        self._preview_fit = None
        self._preview_host._structure_interactive_axes = []
        self._preview_figure.clear()
        self._preview_figure.text(.5, .5, "No completed structure is available for this selection.",
            ha="center", va="center", fontfamily="Segoe UI", wrap=True)
        self._metadata_label.setText(html.escape(reason))
        self._threshold_status.clear()
        self._element_legend.clear()
        self._preview_canvas.draw_idle()

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
        if not self._initializing_selection:
            self._automatic_fallback = False
            self._source_explicit = True
        self._active_source = source
        self._stack.setCurrentWidget(view.container)
        self._summary_value_labels["Assessment"].setText(self._definition.assessment_label)
        self._summary_value_labels["Source"].setText(self._source_title(source))
        self._summary_value_labels["Available cycles"].setText(str(sum(
            c.usable_map and Path(c.map_path).is_file() for c in view.ordered)))
        self._summary_value_labels["Available cycles"].setToolTip("Available completed source maps, not the overall workflow cycle count. Metrics-only rows remain available for inspection.")
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
        self._summary_value_labels["Assessment"].setToolTip(self._definition.description)
        family_explanation = (
            "Superflip phase solution from the selected completed cycle. "
            "The EDMA structure below is extracted from the corresponding Superflip map."
            if source == "superflip" else
            "SharpED-processed map and EDMA structure from the selected completed cycle."
        )
        self._output_description.setText(family_explanation)
        self._reason_label.setText(view.recommendation.reason)
        explanation = (view.recommendation.reason + " Compare within this family in order: "
            + " → ".join(metric.label for metric in self._definition.primary_metrics)
            + ". Each later metric breaks ties only (tolerance 1e-12). Missing tie-breakers are skipped. "
              "Remaining ties prefer a complete result, then the earliest cycle. Values shown are rounded; hover for precision.")
        self._summary_value_labels["Recommended cycle"].setToolTip(explanation)
        view.table.setToolTip("★ marks the recommendation; the highlighted row is selected. " + explanation)
        warning_text = result_warning_callout_text(source, self._map_feedback_intensity_enabled)
        self._warning_callout.setVisible(True)
        if warning_text is not None:
            self._warning_callout.setText(f"<b>Validation required</b> · {warning_text}")
        else:
            self._warning_callout.setText("<b>Phase assessment</b> · Imposed amplitude agreement does not independently validate phases. Inspect and refine against original measured data.")
        if view.selected is not None:
            self._render_preview(view.selected)
        else:
            self._show_empty_preview(reason="Select a completed candidate, or return to Phase Studio to review the run.")
        self._sync_action_button()

    def _on_source_table_selection_changed(self, source: str) -> None:
        if self._closed:
            return
        view = self._views.get(source)
        if view is None:
            return
        candidate = view.current_row_candidate()
        if candidate is None:
            return
        view.selected = candidate
        view.manually_selected = True
        if source != self._active_source:
            # A background table's selection changing must never touch the
            # preview or action button of whichever source is on screen.
            return
        self._render_preview(candidate)
        self._sync_action_button()

    def _sync_action_button(self) -> None:
        candidate = self.selected_candidate
        pending = candidate is not None and self._threshold_key(candidate) in self._pending_thresholds
        snapshot = self.selection_snapshot
        self._action_button.setEnabled(snapshot.ready)
        self._action_button.setToolTip(snapshot.reason)
        for button in (self._fit_button, self._fullscreen_button, self._reset_button,
                       self._molecule_button, self._cell_button, self._auto_rotate_button):
            button.setEnabled(snapshot.geometry)
        usable_structure = candidate.usable_structure if candidate is not None else True
        self._action_button.setText(
            "Pass to Jana2020" if self._jana_context else
            ("Save map and model" if usable_structure else "Save available result")
        )
        threshold_available = (
            snapshot.geometry and candidate is not None and candidate.edma_enabled and candidate.edma_sigma is not None
            and (self._adjust_threshold is not None or self._adjust_threshold_async is not None)
        )
        self._add_atoms_button.setEnabled(threshold_available and not pending)
        self._remove_atoms_button.setEnabled(threshold_available and not pending)
        if candidate is not None and (snapshot.ready or snapshot.pending):
            family = "Charge-flipping solution" if candidate.source == "superflip" else "Structure prediction"
            provenance = (
                f" · {html.escape(candidate.reflection_input_provenance)}"
                if candidate.reflection_input_provenance else ""
            )
            threshold = (
                f" · EDMA {candidate.edma_sigma:.2f} σ"
                if candidate.edma_enabled and candidate.edma_sigma is not None else ""
            )
            transfer = (
                "<br>Scientific map + corresponding Jana model will be passed to Jana2020."
                if self._jana_context and candidate.edma_enabled else
                "<br>EDMA disabled — Jana2020 will determine the structure from the map."
                if self._jana_context else ""
            )
            self._selected_output_summary.setText(
                f"<b>Selected for {'Jana2020' if self._jana_context else 'export'}:</b> "
                f"{family} · Cycle {candidate.cycle}{threshold}"
                f"{provenance} · Jana model: {candidate.jana_model_site_count if candidate.jana_model_site_count is not None else 'unavailable'} atomic sites{transfer}"
            )
        else:
            self._selected_output_summary.setText(
                "<b>No result is ready to pass to Jana2020.</b> " + html.escape(snapshot.reason)
                if self._jana_context else "No result is ready for export. " + html.escape(snapshot.reason))
        if candidate is not None:
            view = self._views[self._active_source]
            row = view.table.currentRow()
            if row >= 0:
                view.table.item(row, 1).setToolTip(f"Cycle {candidate.cycle} · {snapshot.reason}")
            if candidate.source == 'superflip' and snapshot.ready:
                sharped = self._views.get('deblurred')
                if self._sharped_expected and not any(candidate_selection(c, jana=self._jana_context).ready for c in (sharped.ordered if sharped else [])):
                    message = ("No completed SharpED structure is available. A completed charge-flipping solution has been selected instead."
                        if self._automatic_fallback else "No completed SharpED structure is available. The selected charge-flipping solution can be passed to Jana2020.")
                    self.set_fallback_message(message)
            recommended = view.recommendation.recommended_candidate
            if snapshot.ready and recommended is not None and candidate != recommended and not candidate_selection(recommended, jana=self._jana_context).ready:
                explanation = f"Scientific recommendation Cycle {recommended.cycle} is not handoff-ready. " + (
                    f"Selected the highest-ranked ready candidate, Cycle {candidate.cycle}."
                    if not view.manually_selected else f"Your selected Cycle {candidate.cycle} is ready.")
                self._selected_output_summary.setToolTip(explanation)
                self._selected_output_summary.setText(self._selected_output_summary.text() + "<br>" + explanation)
            else:
                self._selected_output_summary.setToolTip("The highlighted row is selected. The star indicates the independent scientific recommendation.")
        view = self._views.get(self._active_source)
        row = view.table.currentRow() if view is not None else -1
        count = len(view.ordered) if view is not None else 0
        self._previous_cycle_button.setEnabled(row > 0)
        self._next_cycle_button.setEnabled(0 <= row < count - 1)
        self._latest_cycle_button.setEnabled(count > 0 and row != count - 1)
        self._latest_cycle_button.setChecked(count > 0 and row == count - 1)

    def _step_cycle(self, direction: int) -> None:
        view = self._views.get(self._active_source)
        if view is None or not view.ordered:
            return
        row = view.table.currentRow()
        target = max(0, min(len(view.ordered) - 1, row + int(direction)))
        view.table.selectRow(target)

    def _select_latest_cycle(self) -> None:
        view = self._views.get(self._active_source)
        if view is not None and view.ordered:
            view.table.selectRow(len(view.ordered) - 1)

    def _set_view_mode(self, mode: str) -> None:
        self._view_mode = "cell" if mode == "cell" else "molecule"
        if self._current_candidate is not None:
            self._render_preview(self._current_candidate)

    def _request_preview_fit(self) -> None:
        self._preview_user_interacted = False
        self._fit_preview()

    def _schedule_preview_fit(self) -> None:
        """Fit after Qt resolves the canvas, coalescing resize bursts."""
        self._preview_fit_timer.start()

    def _on_preview_resize(self, _event) -> None:
        if not self._closed and not self._preview_user_interacted:
            self._schedule_preview_fit()

    def _fit_preview(self) -> None:
        if self._preview_user_interacted:
            return
        fit = getattr(self, "_preview_fit", None)
        if fit is None:
            return
        coords = getattr(self, "_preview_fit_coords", None)
        if coords is None:
            return
        for axis in self._preview_host._structure_interactive_axes:
            fit_projected_structure(axis, coords)
        self._preview_canvas.draw_idle()

    def _reset_preview(self) -> None:
        host = self._preview_host
        host.structure_elev, host.structure_azim = 20.0, 35.0
        for axis in host._structure_interactive_axes:
            axis.view_init(elev=host.structure_elev, azim=host.structure_azim, roll=0.)
        self._preview_user_interacted = False
        self._fit_preview()

    def _toggle_auto_rotate(self, enabled: bool) -> None:
        self._auto_rotate_enabled = bool(enabled)
        self._auto_rotate_button.setText("Auto rotate: On" if enabled else "Auto rotate: Off")

    def _preview_orientation_changed(self, elev: float, azim: float, _source_axis) -> None:
        host = self._preview_host
        host.structure_elev, host.structure_azim = float(elev), float(azim)
        for axis in host._structure_interactive_axes:
            axis.view_init(elev=elev, azim=azim)
        host._update_structure_depth_cue(elev, azim)

    def _preview_camera_interaction(self, kind: str) -> None:
        if kind in {"rotate", "pan", "zoom"}:
            self._preview_user_interacted = True

    def _auto_rotate_tick(self) -> None:
        host = self._preview_host
        if not self._auto_rotate_enabled or not host._structure_interactive_axes or not self._camera.allow_auto_rotation():
            return
        host.structure_azim = (float(host.structure_azim) + 0.4) % 360.0
        for axis in host._structure_interactive_axes:
            axis.view_init(elev=host.structure_elev, azim=host.structure_azim, roll=axis.roll)
        host._update_structure_depth_cue(host.structure_elev,host.structure_azim)
        self._rotation_fit_tick = getattr(self,'_rotation_fit_tick',0)+1
        if not self._preview_user_interacted and self._rotation_fit_tick % 8 == 0:
            # Refit only at a real clipping risk, rather than solve a fit every frame.
            from mpl_toolkits.mplot3d import proj3d
            points = getattr(self,'_preview_fit_coords',None)
            if points is not None and len(points):
                for axis in host._structure_interactive_axes:
                    x,y,_ = proj3d.proj_transform(*np.asarray(points).T,axis.get_proj())
                    pixels = axis.transData.transform(np.column_stack((x,y)))
                    box = axis.get_position(original=True).transformed(axis.figure.transFigure)
                    if (pixels[:,0].min()<box.x0+4 or pixels[:,0].max()>box.x1-4 or
                        pixels[:,1].min()<box.y0+4 or pixels[:,1].max()>box.y1-4):
                        self._fit_preview()
        self._preview_canvas.draw_idle()

    def _on_preview_scroll(self, event) -> None:
        axis = getattr(event, "inaxes", None)
        if axis not in self._preview_host._structure_interactive_axes:
            return
        scale = 0.88 if getattr(event, "button", "") == "up" else 1.14
        limits = []
        for low, high in (axis.get_xlim3d(), axis.get_ylim3d(), axis.get_zlim3d()):
            center = (float(low) + float(high)) / 2.0
            half = (float(high) - float(low)) * scale / 2.0
            limits.append((center - half, center + half))
        for other in self._preview_host._structure_interactive_axes:
            self._preview_host._apply_structure_axis_limits(other, tuple(limits))
        self._preview_canvas.draw_idle()

    def _candidate_presentation(self, candidate: ResultCandidate):
        from phase_studio.autosolve_window import prepare_structure_presentation

        path = Path(candidate.structure_path)
        stat = path.stat() if path.is_file() else None
        cache_key = (
            candidate.run_id, candidate.source, candidate.cycle, candidate.candidate_id,
            candidate.map_sha256, candidate.structure_sha256, candidate.edma_sigma,
            candidate.jana_model_sha256, candidate.unit_cell, candidate.space_group,
            str(path), getattr(stat, "st_mtime_ns", 0), getattr(stat, "st_size", 0),
            self._view_mode, candidate.edma_asu_composition,
        )
        if cache_key in self._presentation_cache:
            return self._presentation_cache[cache_key]
        composition_label = "EDMA asymmetric-unit composition"
        composition = candidate.edma_asu_composition
        data = prepare_structure_presentation(
            path if candidate.usable_structure else None, self._view_mode,
            composition, composition_label,
        )
        result = (
            data["atoms"], data["coords"], data["bonds"], data["composition"],
            data["detected"], data["fit"], data["cell_segments"],
        )
        self._presentation_cache[cache_key] = result
        return result

    def _sync_detached_identity(self, candidate):
        detached = getattr(self, '_detached_viewer', None)
        if detached is not None and not detached._restored:
            family = ('Charge-flipping solution' if candidate.source == 'superflip' else 'Structure prediction') if candidate else 'Structure unavailable'
            title = f'{family} — Cycle {candidate.cycle}' if candidate else family
            detached.setWindowTitle(title)
            detached.title_label.setText(title)
            detached.candidate_identity = CandidateSelection(candidate,False,False,'').identity

    def _render_preview(self, candidate: ResultCandidate) -> None:
        status = candidate_selection(candidate, jana=self._jana_context)
        if not status.geometry:
            self._show_empty_preview(candidate, status.reason)
            return
        previous = self._current_candidate
        palette=getattr(QApplication.instance(),'_phase_color_palette','phase')
        if (previous == candidate and getattr(self,'_rendered_view_mode',None)==self._view_mode
                and getattr(self,'_rendered_palette',None)==palette
                and getattr(self,'_resolved_preview',None) is not None):
            self._sync_detached_identity(candidate)
            return  # Identical immutable data: keep artists, camera and geometry.
        same_candidate = previous is not None and (
            previous.run_id, previous.source, previous.cycle, previous.map_sha256,
            self._view_mode
        ) == (
            candidate.run_id, candidate.source, candidate.cycle, candidate.map_sha256,
            getattr(self, "_rendered_view_mode", None)
        )
        old_axis = next(iter(self._preview_host._structure_interactive_axes), None)
        retained_camera = None
        if same_candidate and self._preview_user_interacted and old_axis is not None:
            retained_camera = (
                old_axis.get_xlim3d(), old_axis.get_ylim3d(), old_axis.get_zlim3d(),
                getattr(old_axis, "_phase_fit_zoom", 1.0),
            )
        if not same_candidate:
            self._preview_user_interacted = False
        self._rendered_view_mode = self._view_mode
        self._rendered_palette = palette
        self._current_candidate = candidate
        self._sync_detached_identity(candidate)
        self.preview_candidate_id = candidate.candidate_id
        self.preview_structure_hash = candidate.structure_sha256
        figure = self._preview_figure
        figure.clear()
        figure.patch.set_facecolor("#ffffff")
        host = self._preview_host
        host.structure_axes = []
        host._structure_interactive_axes = []
        host._structure_depth_artists = []
        try:
            atoms, coords, bonds, composition, detected_count, fit, cell_segments = self._candidate_presentation(candidate)
            self._resolved_preview = ResolvedCandidateSnapshot(status,self._view_mode,
                tuple((str(a.label),str(a.element),tuple(float(v) for v in a.frac)) for a in atoms),
                tuple(tuple(float(v) for v in row) for row in coords),tuple(tuple(b) for b in bonds),
                composition,int(detected_count),tuple(tuple(tuple(float(v) for v in row) for row in segment) for segment in cell_segments))
            composition_label = "EDMA asymmetric-unit composition"
        except Exception:
            self._resolved_preview = None
            atoms, coords, bonds, composition, detected_count, fit, cell_segments = [], np.zeros((0, 3)), [], "", 0, None, []
            composition_label = "Composition"
        self._current_formula = composition
        self._preview_fit = fit
        self._preview_fit_coords = (
            np.vstack([coords, *cell_segments]) if cell_segments else coords
        )
        axis = figure.add_subplot(1, 1, 1, projection="3d")
        host.structure_axes.append(axis)
        if not atoms:
            axis.set_axis_off()
            axis.text2D(
                0.5, 0.5, "Structure model unavailable · map remains usable",
                ha="center", va="center", transform=axis.transAxes,
            )
        else:
            axis.set_proj_type("ortho")
            axis.set_xticks([]); axis.set_yticks([]); axis.set_zticks([])
            axis.view_init(elev=host.structure_elev, azim=host.structure_azim,
                           roll=float(old_axis.roll) if old_axis is not None else 0.)
            colors = [host._element_color(atom.element) for atom in atoms]
            count_scale = max(0.30, min(1.0, (320.0 / max(1, len(atoms))) ** 0.32))
            sizes = structure_marker_sizes(len(atoms))
            axis.scatter(
                coords[:, 0], coords[:, 1], coords[:, 2], s=sizes, c=colors,
                edgecolors="#ffffff", linewidths=max(0.08, 0.18 * count_scale),
                depthshade=False,
            )
            if bonds:
                axis.add_collection3d(Line3DCollection(
                    [np.asarray([coords[i], coords[j]]) for i, j in bonds],
                    colors="#5d6b86", linewidths=max(0.35, 1.2 * count_scale),
                ))
            if cell_segments:
                axis.add_collection3d(Line3DCollection(
                    cell_segments, colors="#44b7ff", linewidths=0.75, alpha=0.72,
                ))
            host._structure_interactive_axes.append(axis)
            axis.set_axis_off()
        source = self._source_title(candidate.source)
        lineage = recorded_edma_site_lineage(candidate)
        raw_detail = (
            f" · Raw EDMA peaks: {lineage['raw_edma_sites']}"
            if lineage else ""
        )
        model = f" · {candidate.sharped_model}" if candidate.sharped_model else ""
        initialization = (
            f" · {candidate.superflip_initialization}"
            if candidate.source == "superflip" and candidate.superflip_initialization else ""
        )
        self._metadata_label.setText(
            f"{html.escape(source)} · Cycle {candidate.cycle}{html.escape(model)}{html.escape(initialization)}<br>"
            f"<b>{html.escape(composition_label)}:</b> {html.escape((composition or 'Unavailable').translate(str.maketrans('0123456789', '₀₁₂₃₄₅₆₇₈₉')))}"
            f"<br>EDMA candidate: {candidate.detected_atom_count if candidate.detected_atom_count is not None else detected_count} sites{raw_detail} · "
            + (f"Jana model: {candidate.jana_model_site_count} atomic sites"
               if candidate.jana_model_site_count is not None and candidate.jana_model_sha256
               else "Jana model: prepared during handoff")
        )
        self._metadata_label.setToolTip(self._metadata_label.text().replace("<br>", "\n")
            + f"\nRendered atoms: {len(atoms)}; candidate identity: {candidate.candidate_id}. "
            "Changing EDMA sites need not change the composition-constrained Jana model count.")
        self._metadata_label.setText(
            f"<b>ASU:</b> {html.escape((composition or 'Unavailable').translate(str.maketrans('0123456789', '₀₁₂₃₄₅₆₇₈₉')))}"
            f" · Jana model: {candidate.jana_model_site_count if candidate.jana_model_site_count is not None else 'unavailable'} atomic sites<br>"
            f"{html.escape(source)} · Cycle {candidate.cycle}{html.escape(model)}{html.escape(initialization)}"
        )
        self._threshold_status.setText(
            f"EDMA {candidate.edma_sigma:.2f} σ · {detected_count:,} EDMA sites"
            if candidate.edma_enabled and candidate.edma_sigma is not None else "EDMA disabled"
        )
        pending_request = self._pending_thresholds.get(self._threshold_key(candidate))
        if pending_request is not None:
            self._threshold_status.setText(
                f"EDMA {float(pending_request.threshold):.2f} σ · updating… "
                f"Current handoff: EDMA {float(candidate.edma_sigma):.2f} σ"
            )
        if candidate.edma_enabled:
            from phase_studio.app import edma_asu_atoms, parse_cif_atoms, parse_cif_cell_and_sg
            path = Path(candidate.structure_path)
            if path.is_file():
                cell, sg, _hm = parse_cif_cell_and_sg(path)
                independent = len(edma_asu_atoms(parse_cif_atoms(path), cell, sg))
                model_count = candidate.jana_model_site_count
                self._threshold_status.setToolTip(
                    f"CIF EDMA sites: {detected_count}; independent ASU sites: {independent}; "
                    f"displayed in {'Full cell' if self._view_mode == 'cell' else 'Complete molecules'}: {len(atoms)}; "
                    f"Jana m40 sites: {model_count if model_count is not None else 'unavailable'}. "
                    "Display expansion does not detect additional sites."
                )
        elements = sorted({str(atom.element) for atom in atoms})
        legend = "&nbsp;&nbsp;&nbsp; ".join(
            f'<span style="color:{host._element_color(element)}; font-size:12pt;">&#9679;</span>&nbsp;{html.escape(element)}'
            for element in elements
        )
        self._element_legend.setText(f"Elements:&nbsp;&nbsp; {legend}" if legend else "")
        # Source/cycle identity belongs to the compact metadata header.  The
        # scientific canvas contains geometry only and can use its full area.
        figure.subplots_adjust(left=0.005, right=0.995, bottom=0.005, top=0.995)
        if retained_camera is not None:
            xlim, ylim, zlim, zoom = retained_camera
            axis.set_xlim3d(xlim); axis.set_ylim3d(ylim); axis.set_zlim3d(zlim)
            axis.set_box_aspect((1, 1, 1), zoom=zoom)
            axis._phase_fit_zoom = zoom
            set_structure_viewport_clip(axis)
        self._camera.refresh_axes()
        self._preview_canvas.draw_idle()
        QTimer.singleShot(0, self._fit_preview)
        self._schedule_preview_fit()

    def _refresh_viewer_palette(self):
        if self._current_candidate is not None:
            self._render_preview(self._current_candidate)
