#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase Studio Qt application.

Iterative Superflip -> optional SharpED server deblur -> EDMA reconstruction with
persistent settings and standardized metric plotting.

The selected metadata source supplies cell, symmetry and composition; a
reference structure can additionally supply atom sites and comparison metrics. Superflip
referencefile is written when the user explicitly selects an external reference file
(CIF/Jana/XPLOR/CCP4); otherwise, from the second cycle onward, it is filled in
automatically from the most recent previous-cycle EDMA CIF (or the previous-cycle
XPLOR map when EDMA produced no usable peaks) so Superflip keeps a fixed origin in
reciprocal space across cycles. The first Superflip run has no modelfile. Later cycles
can use EDMA CIF coordinates, raw Superflip XPLOR, or deblurred XPLOR as Superflip
modelfile.

Each cycle saves:
  cycle_NNN/cycle_NNN_superflip.xplor
  cycle_NNN/edma_superflip/cycle_NNN_superflip_edma.cif
  cycle_NNN/cycle_NNN_deblurred.xplor
  cycle_NNN/edma_deblurred/cycle_NNN_deblurred_edma.cif
  metrics.csv

External commands expected:
  superflip, EDMA
"""

from __future__ import annotations

import collections
import csv
import html
import math
import os
import queue
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, FrozenSet, Iterable, List, Optional, Sequence, Tuple

import numpy as np

try:
    from phase_studio.version import VERSION as __version__
except Exception:
    from version import VERSION as __version__

try:
    from phase_studio.error_reporting import (
        ErrorAction,
        ErrorReport,
        build_error_report,
        build_validation_report,
        sanitize_error_details,
        show_phase_studio_error,
    )
except Exception:
    from error_reporting import (
        ErrorAction,
        ErrorReport,
        build_error_report,
        build_validation_report,
        sanitize_error_details,
        show_phase_studio_error,
    )

try:
    from phase_studio.sharped_server_client import SharpEDServerClient
except Exception:
    from sharped_server_client import SharpEDServerClient

try:
    from phase_studio.process_utils import allow_external_process_foreground, text_encoding
except Exception:
    from process_utils import allow_external_process_foreground, text_encoding

try:
    import gemmi
except Exception as exc:
    raise RuntimeError(
        "Gemmi could not be loaded. Install it with: "
        "conda install -c conda-forge gemmi. "
        f"Original error: {exc}"
    ) from exc

# Import the selected Qt binding before Matplotlib's Qt backend.
# The application and the frozen executable use PySide6 exclusively.
try:
    from PySide6.QtCore import Qt, QTimer, QSettings, QUrl, QPoint, QRect, QRectF, QSize
    from PySide6.QtGui import QColor, QDesktopServices, QFont, QGuiApplication, QIcon, QKeySequence, QPainter, QPen, QPixmap, QShortcut, QTextBlockFormat, QTextCharFormat, QTextCursor
    from PySide6.QtWidgets import (
        QApplication, QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame,
        QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
        QDialog, QDialogButtonBox, QProgressBar, QPushButton, QScrollArea, QSizePolicy, QSpinBox, QSplitter, QSplashScreen, QToolButton,
        QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QTabWidget, QTextEdit, QVBoxLayout, QWidget
    )
except Exception as exc:
    raise RuntimeError(
        "PySide6 could not be loaded. Verify the PySide6 installation and "
        "Qt DLL dependencies. "
        f"Original error: {exc}"
    ) from exc

try:
    from phase_studio.ui_style import apply_phase_studio_style
except Exception:
    from ui_style import apply_phase_studio_style

try:
    import matplotlib

    matplotlib.use("QtAgg", force=True)
    matplotlib.rcParams.update(
        {
            "text.color": "#001170",
            "axes.labelcolor": "#001170",
            "axes.edgecolor": "#001170",
            "axes.titlecolor": "#001170",
            "xtick.color": "#001170",
            "ytick.color": "#001170",
            "grid.color": "#44b7ff",
            "figure.facecolor": "#ffffff",
            "axes.facecolor": "#ffffff",
            "savefig.facecolor": "#ffffff",
            "legend.labelcolor": "#001170",
        }
    )
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.colors import to_rgb
    from matplotlib.figure import Figure
    from matplotlib.lines import Line2D
    from matplotlib.ticker import MaxNLocator
    from mpl_toolkits.mplot3d.art3d import Line3DCollection
except Exception as exc:
    raise RuntimeError(
        "Matplotlib QtAgg backend could not be loaded. "
        f"Original error: {exc}"
    ) from exc

COMMENT_PREFIXES = ("#", "!", ";")
REFLECTION_DATA_MODE_SET_FROM_INFLIP = "set from inflip"
REFLECTION_DATA_MODE_INTENSITY = "hkl I sigma"
REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA = "hkl F sigma"
REFLECTION_DATA_MODE_INTENSITY_PHASE_SIGMA = "hkl I phase sigma"
REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA = "hkl F phase sigma"
REFLECTION_DATA_MODE_INTENSITY_FWHM = "hkl I fwhm"
REFLECTION_DATA_MODE_AMPLITUDE_FWHM = "hkl F fwhm"
# Compatibility name used by older settings and internal call sites.
REFLECTION_DATA_MODE_AUTO = REFLECTION_DATA_MODE_SET_FROM_INFLIP
ATOMIC_NUMBER_HINTS = {
    "H": 1, "B": 5, "C": 6, "N": 7, "O": 8, "F": 9,
    "Na": 11, "Mg": 12, "Al": 13, "Si": 14, "P": 15, "S": 16, "Cl": 17,
    "K": 19, "Ca": 20, "Mn": 25, "Fe": 26, "Co": 27, "Ni": 28,
    "Cu": 29, "Zn": 30, "Br": 35, "Ag": 47, "I": 53, "Au": 79,
    "Hg": 80, "Pb": 82,
}

@dataclass
class Reflection:
    h: int
    k: int
    l: int
    value: float
    sigma: Optional[float] = None
    phase: Optional[float] = None

@dataclass
class AtomSite:
    label: str
    element: str
    frac: np.ndarray
    density: float = 1.0


@dataclass
class StructureDepthArtists:
    scatter: object
    atom_coordinates: np.ndarray
    atom_base_colors: np.ndarray
    atom_sizes: np.ndarray
    atom_draw_order: np.ndarray
    cell_collection: object
    cell_midpoints: np.ndarray
    cell_corners: np.ndarray


def structure_camera_direction(elev: float, azim: float) -> np.ndarray:
    """Return the unit vector from the view centre toward the camera."""
    elevation = math.radians(float(elev))
    azimuth = math.radians(float(azim))
    return np.asarray(
        [
            math.cos(elevation) * math.cos(azimuth),
            math.cos(elevation) * math.sin(azimuth),
            math.sin(elevation),
        ],
        dtype=np.float64,
    )


def structure_camera_depth(points: np.ndarray, elev: float, azim: float) -> np.ndarray:
    """Project centered Cartesian coordinates onto the current camera direction."""
    point_array = np.asarray(points, dtype=np.float64).reshape((-1, 3))
    if point_array.size == 0:
        return np.asarray([], dtype=np.float64)
    centered = point_array - np.mean(point_array, axis=0, keepdims=True)
    return centered @ structure_camera_direction(elev, azim)


def structure_depth_fade(
    points: np.ndarray,
    bounds: np.ndarray,
    elev: float,
    azim: float,
    *,
    front_hold: float = 0.25,
    gamma: float = 1.25,
    maximum: float = 0.68,
) -> np.ndarray:
    """Map current camera depth to a monotonic blend amount toward white.

    ``bounds`` is the visible geometry used to normalize this individual
    structure.  The nearest quarter remains at its original color; only middle
    and rear geometry is progressively blended toward white.
    """
    point_array = np.asarray(points, dtype=np.float64).reshape((-1, 3))
    bound_array = np.asarray(bounds, dtype=np.float64).reshape((-1, 3))
    if point_array.size == 0:
        return np.asarray([], dtype=np.float64)
    center = np.mean(bound_array, axis=0, keepdims=True)
    direction = structure_camera_direction(elev, azim)
    projected_bounds = (bound_array - center) @ direction
    front = float(np.max(projected_bounds))
    back = float(np.min(projected_bounds))
    span = max(front - back, 1.0e-12)
    rear_depth = np.clip((front - (point_array - center) @ direction) / span, 0.0, 1.0)
    hold = max(0.0, min(0.45, float(front_hold)))
    normalized = np.clip((rear_depth - hold) / max(1.0e-12, 1.0 - hold), 0.0, 1.0)
    return np.clip(float(maximum), 0.0, 0.95) * np.power(normalized, max(0.2, float(gamma)))


def blend_structure_colors(base_colors: np.ndarray, fade: np.ndarray) -> np.ndarray:
    """Blend RGB colors toward the white Phase Studio structure background."""
    colors = np.asarray(base_colors, dtype=np.float64)
    if colors.ndim == 1:
        colors = np.repeat(colors.reshape((1, 3)), len(fade), axis=0)
    amounts = np.asarray(fade, dtype=np.float64).reshape((-1, 1))
    return np.clip(colors * (1.0 - amounts) + amounts, 0.0, 1.0)


def fitted_dialog_client_size(
    available_size: QSize,
    frame_extra: QSize = QSize(0, 0),
    preferred_size: QSize = QSize(1180, 835),
) -> QSize:
    """Return an initial client size whose complete frame fits the usable desktop."""
    max_outer_width = max(1, int(math.floor(available_size.width() * 0.95)))
    # On short high-DPI desktops, use the available work area rather than
    # sacrificing scientific plot height to a large decorative outer margin.
    # The native frame is still measured and kept wholly above the taskbar.
    max_outer_height = max(1, int(math.floor(available_size.height() * 0.97)))
    client_width = min(preferred_size.width(), max(1, max_outer_width - max(0, frame_extra.width())))
    client_height = min(preferred_size.height(), max(1, max_outer_height - max(0, frame_extra.height())))
    return QSize(client_width, client_height)


def fit_dialog_to_available_screen(
    dialog: QDialog,
    preferred_size: QSize = QSize(1180, 835),
) -> QRect:
    """Size and center a dialog inside its screen's availableGeometry()."""
    dialog.ensurePolished()
    dialog.winId()  # Ensure native frame margins are available before sizing.
    screen = dialog.screen() or QGuiApplication.primaryScreen()
    if screen is None:
        fallback = QRect(0, 0, preferred_size.width(), preferred_size.height())
        dialog.resize(preferred_size)
        return fallback

    available = screen.availableGeometry()
    frame = dialog.frameGeometry()
    client = dialog.geometry()
    frame_extra = QSize(
        max(0, frame.width() - client.width()),
        max(0, frame.height() - client.height()),
    )
    target = fitted_dialog_client_size(available.size(), frame_extra, preferred_size)
    dialog.setMinimumSize(min(760, target.width()), min(520, target.height()))
    dialog.resize(target)

    frame = dialog.frameGeometry()
    target_frame_top_left = QPoint(
        available.x() + max(0, (available.width() - frame.width()) // 2),
        available.y() + max(0, (available.height() - frame.height()) // 2),
    )
    dialog.move(dialog.pos() + target_frame_top_left - frame.topLeft())

    # A window manager may adjust frame margins after the first move. Clamp a
    # second time so the full native frame, including its title bar, stays in
    # the usable rectangle above the taskbar.
    frame = dialog.frameGeometry()
    dx = max(available.left() - frame.left(), 0) - max(frame.right() - available.right(), 0)
    dy = max(available.top() - frame.top(), 0) - max(frame.bottom() - available.bottom(), 0)
    if dx or dy:
        dialog.move(dialog.pos() + QPoint(dx, dy))

    dialog.available_geometry_at_open = QRect(available)  # type: ignore[attr-defined]
    dialog.initial_client_size = QSize(dialog.size())  # type: ignore[attr-defined]
    return available

@dataclass
class ReferenceContext:
    cif_path: Path
    work_ref_cif: Path
    cell: gemmi.UnitCell
    spacegroup: gemmi.SpaceGroup
    spacegroup_hm: str
    composition: str
    atoms: List[AtomSite]


@dataclass
class JanaWizardContext:
    """Distinguishes a normal standalone Phase Studio launch from the two
    Jana2020-Wizard-initiated launches that open this same main window. Both
    single-pass workflows (Superflip only, Superflip + SharpED) run through
    the original lightweight console/wrapper path and never construct this
    window or this context at all.

    The default (launch_mode="standalone") is a normal standalone launch: no
    field here may change behavior unless launched_from_jana_wizard is True."""

    launched_from_jana_wizard: bool = False
    # "standalone" | "full_configuration" | "phase_recycling" -- which of the
    # two Wizard launches (if any) opened this window. "full_configuration"
    # is Jana Wizard -> Open full configuration (the user drives the whole
    # workflow manually, then explicitly clicks Send to Jana2020, with a
    # Superflip/SharpED source switch in the result selector).
    # "phase_recycling" is Jana Wizard -> Phase recycling (auto-started, its
    # map source fixed to whatever was chosen in the Wizard, and its result
    # selector opens automatically on completion with no source switch).
    launch_mode: str = "standalone"
    wizard_map_source: str = ""  # "superflip" or "deblurred"; only meaningful when launch_mode == "phase_recycling"


# --- Shared canonical Superflip/SharpED display-name mapping (spec: create
# one shared user-facing source mapping, do not scatter conditional string
# literals like `"SharpED" if source == "deblurred" else "Superflip"`
# throughout the GUI). The internal token stays "superflip" / "deblurred" --
# only these three helpers translate it to what the user sees. ---

def result_source_title(source: str) -> str:
    """Canonical short display name for a result-source token."""
    return "Superflip" if str(source or "").strip().lower() == "superflip" else "SharpED"


def result_map_label(source: str) -> str:
    """Canonical "<Source> map" display label."""
    return f"{result_source_title(source)} map"


def result_structure_label(source: str) -> str:
    """Canonical "<Source> structure" display label."""
    return f"{result_source_title(source)} structure"


@dataclass(frozen=True)
class CrystalMetadata:
    """Validated crystallographic metadata selected for one pipeline run."""

    cell: gemmi.UnitCell
    spacegroup: gemmi.SpaceGroup
    spacegroup_hm: str
    composition: str
    source: str
    source_path: Optional[Path] = None

@dataclass
class SuperflipLogMetrics:
    saved_run: Optional[int] = None
    rvalue: Optional[float] = None
    peaks: Optional[float] = None
    symm: Optional[float] = None
    derived_sg: str = ""
    ref_match: Optional[float] = None
    fom: Optional[float] = None
    success_rate: Optional[float] = None
    mean_cycles: Optional[float] = None


LOG_LEVELS = {"INFO", "STEP", "SUCCESS", "WARNING", "ERROR", "COMMAND", "DETAIL"}
LOG_DETAIL_PREFIXES = (
    "edma plimit",
    "edma maxima",
    "sharped inference server",
    "sharped model",
    "sharped elements",
    "sharped maximum upload",
    "sharped server http timeout",
    "next-cycle modelfile",
    "xplor damping",
    "cif modelfiles",
    "superflip perform",
    "output formats",
    "superflip bestdensities",
    "superflip polish",
    "superflip hkl data mode",
    "superflip resolution cutoff",
    "optional functions",
    "map feedback",
    "prepared hkl",
    "standardized hkl export",
    "superflip map:",
    "sharped map:",
    "removed stale superflip",
    "xplor map normalized",
    "cif-only exclude settings",
    "superflip reads normalized xplor",
    "original/viewer xplor",
    "superflip modelfile is set",
    "superflip symmetry voxel grid",
    "tls fallback detail:",
    "sharped protocol detail:",
)


@dataclass(frozen=True)
class ExecutionLogRecord:
    text: str
    level: str = "INFO"
    subsystem: str = "Pipeline"


def redact_log_secrets(message: object) -> str:
    """Remove credentials and job-access tokens from user-visible diagnostics."""
    return sanitize_error_details(message)


def relative_log_paths(message: str, work_dir: Optional[Path]) -> str:
    """Make paths below the already-announced work directory concise."""
    text = str(message)
    if work_dir is None or re.match(r"^\s*work (?:dir|directory):", text, re.IGNORECASE):
        return text
    try:
        root = str(Path(work_dir).expanduser().resolve())
    except Exception:
        return text
    for separator in ("\\", "/"):
        variant = root.replace("\\", separator).replace("/", separator)
        text = text.replace(variant + separator, "")
    return text


def classify_log_record(
    message: object,
    *,
    level: str = "",
    subsystem: str = "",
    work_dir: Optional[Path] = None,
) -> ExecutionLogRecord:
    """Create a safe semantic log record without changing scientific content."""
    text = relative_log_paths(redact_log_secrets(message), work_dir)
    stripped = text.strip()
    lowered = stripped.lower()
    resolved_subsystem = str(subsystem or "").strip()
    if not resolved_subsystem:
        bracketed = re.match(r"^\[([^]]+)\]", stripped)
        if bracketed:
            resolved_subsystem = bracketed.group(1)
        elif "sharped" in lowered:
            resolved_subsystem = "SharpED"
        elif "superflip" in lowered:
            resolved_subsystem = "Superflip"
        elif "edma" in lowered:
            resolved_subsystem = "EDMA"
        elif "jana2020" in lowered or "jana .inflip" in lowered:
            resolved_subsystem = "Jana2020"
        else:
            resolved_subsystem = "Pipeline"

    resolved_level = str(level or "").strip().upper()
    if resolved_level not in LOG_LEVELS:
        if "error" in lowered or "failed" in lowered or "failure" in lowered:
            resolved_level = "ERROR"
        elif lowered.startswith(LOG_DETAIL_PREFIXES):
            resolved_level = "DETAIL"
        elif any(word in lowered for word in ("warning", "could not", "skipped", "omitted")):
            resolved_level = "WARNING"
        elif stripped.startswith("$") or stripped.startswith("$ ") or stripped.startswith("  $"):
            resolved_level = "DETAIL"
        elif stripped.startswith("===") or re.match(r"^cycle\s+\d+\s*/\s*\d+", lowered):
            resolved_level = "STEP"
        elif any(word in lowered for word in ("completed", " complete", "finished", "done.")):
            resolved_level = "SUCCESS"
        elif text.startswith(("  ", "\t")):
            resolved_level = "DETAIL"
        else:
            resolved_level = "INFO"
    return ExecutionLogRecord(text=text, level=resolved_level, subsystem=resolved_subsystem)


@dataclass
class CycleResult:
    cycle: int
    model_source: str
    model_in: Optional[Path]
    model_metric: Optional[float]
    superflip_map: Path
    superflip_edma_cif: Path
    superflip_metric: Optional[float]
    deblur_map: Path
    deblur_edma_cif: Path
    deblur_metric: Optional[float]
    superflip_saved_run: Optional[int] = None
    superflip_rvalue: Optional[float] = None
    superflip_peaks: Optional[float] = None
    superflip_symm: Optional[float] = None
    superflip_derived_sg: str = ""
    superflip_ref_match: Optional[float] = None
    superflip_fom: Optional[float] = None
    superflip_success_rate: Optional[float] = None
    superflip_mean_cycles: Optional[float] = None
    recycle_map_correlation: Optional[float] = None
    omit_superflip_correlation: Optional[float] = None
    omit_superflip_rfree: Optional[float] = None
    omit_deblur_correlation: Optional[float] = None
    omit_deblur_rfree: Optional[float] = None
    superflip_recall: Optional[float] = None
    superflip_precision: Optional[float] = None
    superflip_heavy_atom_count: Optional[float] = None
    deblur_recall: Optional[float] = None
    deblur_precision: Optional[float] = None
    deblur_heavy_atom_count: Optional[float] = None
    powder_repartition_avg_change_percent: Optional[float] = None
    intensity_correction_avg_change_percent: Optional[float] = None


INPUT_MODE_INFLIP = "jana_inflip"
INPUT_MODE_INFLIP_OVERRIDES = "jana_inflip_overrides"
INPUT_MODE_EXTERNAL = "external_hkl_cif"

INPUT_MODE_LABELS = {
    INPUT_MODE_INFLIP: "Jana2020 .inflip",
    INPUT_MODE_INFLIP_OVERRIDES: "Jana2020 .inflip with external HKL/reference overrides",
    INPUT_MODE_EXTERNAL: "External HKL + CIF reference",
}

METADATA_SOURCE_INFLIP = "jana_inflip"
METADATA_SOURCE_REFERENCE = "reference_file"
METADATA_SOURCE_MANUAL = "manual"

METADATA_SOURCE_LABELS = {
    METADATA_SOURCE_INFLIP: "Jana2020 .inflip",
    METADATA_SOURCE_REFERENCE: "Reference structure",
    METADATA_SOURCE_MANUAL: "Manual",
}


def normalize_metadata_source(value: str) -> str:
    text = str(value or "").strip().lower()
    if text in {METADATA_SOURCE_INFLIP, "inflip", "jana", "jana .inflip"}:
        return METADATA_SOURCE_INFLIP
    if text in {METADATA_SOURCE_REFERENCE, "reference", "reference file"}:
        return METADATA_SOURCE_REFERENCE
    if text in {METADATA_SOURCE_MANUAL, "manual input"}:
        return METADATA_SOURCE_MANUAL
    return METADATA_SOURCE_INFLIP

def normalize_input_source_mode(value: str) -> str:
    text = str(value or "").strip().lower()
    if text in {INPUT_MODE_INFLIP, "inflip", "jana", "jana .inflip"}:
        return INPUT_MODE_INFLIP
    if text in {INPUT_MODE_INFLIP_OVERRIDES, "inflip_overrides"} or ("inflip" in text and "override" in text):
        return INPUT_MODE_INFLIP_OVERRIDES
    if text in {INPUT_MODE_EXTERNAL, "external"} or text.startswith("external"):
        return INPUT_MODE_EXTERNAL
    return INPUT_MODE_INFLIP

@dataclass
class RunConfig:
    hkl: Path
    reference_cif: Path
    superflip_reference_xplor: Optional[Path]
    superflip_referencefile: Optional[Path]
    first_cycle_modelfile: Optional[Path]
    input_source_mode: str
    jana_inflip: Optional[Path]
    crystal_metadata: CrystalMetadata
    jana_return_to_jana: bool
    work_dir: Path
    cycles: int
    superflip_exe: str
    edma_exe: str
    composition_override: str
    plimit_superflip: float
    plimit_deblur: float
    merge_distance: float
    edma_maxima: str
    edma_fullcell: str
    edma_numberofatoms: str
    edma_centerofcharge: bool
    edma_chlimit: str
    edma_chlimlist: str
    extra_edma_keywords: str
    damping_factor: float
    modelfile_source: str
    reconstruction_mode: str
    run_edma_recycle_final: bool
    exclude_atoms: str
    perform_algorithm: str
    map_export_format: str
    structure_export_format: str
    referencefile_mode: str
    voxel: str
    bestdensities_count: int
    bestdensities_metric: str
    bestdensities_symmetry: bool
    polish: bool
    maxcycles: int
    repeatmode: int
    randomseed: str
    delta: str
    weakratio: str
    biso: str
    reflection_data_mode: str
    first_cycle_like_attachment: bool
    i_over_sigma_min: float
    resolution_d_min: float
    normalize: str
    nresshells: int
    missing: str
    searchsymmetry: str
    derivesymmetry: str
    electrons: str
    dataitemwidths: str
    extra_superflip_keywords: str
    map_feedback_missing_enabled: bool
    map_feedback_missing_from_cycle: int
    map_feedback_missing_percent_limit: float
    map_feedback_intensity_enabled: bool
    map_feedback_intensity_from_cycle: int
    map_feedback_intensity_damping: float
    map_feedback_intensity_max_i_over_sigma: float
    redistribute_overlaps: bool
    powder_redistribution_from_cycle: int
    powder_wavelength: float
    powder_separation_factor: float
    powder_redistribution_mix: float
    run_sharped: bool
    symmetrize_deblurred_map: bool
    run_edma_superflip: bool
    run_edma_deblurred: bool
    compute_omit_maps: bool
    compute_omit_rfree: bool
    sharped_base_url: str
    sharped_api_token: str
    sharped_model: str
    sharped_elements: str
    sharped_outres: float
    sharped_max_upload_mb: float
    sharped_timeout_seconds: int
    sharped_poll_seconds: int
    sharped_max_polls: int


@dataclass
class PipelineState:
    """Everything the cycle loop needs to resume exactly where it left off.

    Built once per fresh run and mutated cycle by cycle; kept around after a stop
    or a natural finish so Continue can pick the loop back up with the same
    metadata, reflections, model/reference feedback and accumulated results.
    """

    cfg: RunConfig
    ref_ctx: ReferenceContext
    observed_hkls: Dict[str, Path]
    configured_data_mode: str
    referencefile_mode: str
    explicit_superflip_referencefile: Optional[Path]
    modelfile_mode: str
    use_xplor_modelfile: bool
    use_cif_modelfile: bool
    use_superflip_xplor_modelfile: bool
    sharped_elements: str
    exclude_labels: List[str]
    progress_stages: List[str]
    current_reflections: List[Reflection]
    all_results: List[CycleResult] = field(default_factory=list)
    completed_cycles: int = 0
    current_model: Optional[Path] = None
    current_model_metric: Optional[float] = None
    auto_reference_cif: Optional[Path] = None
    auto_reference_xplor: Optional[Path] = None
    recycle_map: Optional[Path] = None
    omit_test_hkls: FrozenSet[Tuple[int, int, int]] = field(default_factory=frozenset)
    pending_powder_repartition_change_percent: Optional[float] = None
    pending_intensity_correction_change_percent: Optional[float] = None


@dataclass(frozen=True)
class CycleProgressState:
    cycle_index: int
    cycle_total: int
    stage_name: str
    stage_index: int
    stage_total: int
    sub_index: Optional[int] = None
    sub_total: Optional[int] = None
    detail: str = ""
    busy: bool = False
    complete: bool = False

    def display_text(self) -> str:
        # sub_index/sub_total (Superflip's internal repeat-pass counter) is
        # deliberately not shown here: it reads as developer/internal detail
        # in the compact primary status line and is already visible in the
        # pipeline's own settings-summary log lines.
        parts = [f"Cycle {self.cycle_index} of {self.cycle_total}", self.stage_name]
        if self.detail:
            # Call sites pass lowercase detail phrases ("running", "preparing
            # upload", ...); capitalize just the leading letter here, in one
            # place, for sentence-case display rather than editing every
            # _emit_cycle_progress() call site individually.
            parts.append(self.detail[:1].upper() + self.detail[1:])
        return " · ".join(part for part in parts if part)


@dataclass(frozen=True)
class SuperflipProgress:
    """One live progress observation parsed from Superflip's own stdout.

    repeat/repeat_total describe Superflip's internal repeatmode attempt
    counter -- NOT the Phase Studio workflow cycle ("Cycle N of M") and NOT
    the final "Saved run" selected-density index. phase is "running" while a
    repeat is in progress and "completed" once Superflip reports its last run
    finished."""

    repeat: Optional[int] = None
    repeat_total: Optional[int] = None
    phase: str = "running"


class SuperflipRepeatProgressParser:
    """Best-effort, defensive line-by-line parser for Superflip's repeatmode
    progress, e.g.:

        Starting iteration:                  (first repeat begins)
        Run number  1. Still  9 to go.       (repeat 1 finished, repeat 2 begins)
        ...
        Last run from 10 completed.          (final repeat finished)

    repeat_total is always the EFFECTIVE repeatmode Phase Studio itself wrote
    into the current .inflip (never parsed from the log), per the requirement
    that live progress describe the running calculation, not just the GUI
    setting. Unrecognized lines are ignored; this parser never raises."""

    _RUN_NUMBER_RE = re.compile(r"run\s+number\s+(\d+)\s*\.\s*still\s+(\d+)\s+to\s+go", re.IGNORECASE)
    _LAST_RUN_RE = re.compile(r"last\s+run\s+from\s+(\d+)\s+completed", re.IGNORECASE)

    def __init__(self, repeat_total: int) -> None:
        self.repeat_total = max(1, int(repeat_total))
        self.completed_runs = 0
        self.saw_progress = False

    def feed(self, line: str) -> Optional[SuperflipProgress]:
        try:
            text = str(line or "")
            if not text.strip():
                return None
            if "starting iteration:" in text.lower():
                self.saw_progress = True
                repeat = min(self.completed_runs + 1, self.repeat_total)
                return SuperflipProgress(repeat=repeat, repeat_total=self.repeat_total, phase="running")
            match = self._RUN_NUMBER_RE.search(text)
            if match:
                self.saw_progress = True
                self.completed_runs = int(match.group(1))
                repeat = min(self.completed_runs + 1, self.repeat_total)
                return SuperflipProgress(repeat=repeat, repeat_total=self.repeat_total, phase="running")
            match = self._LAST_RUN_RE.search(text)
            if match:
                self.saw_progress = True
                self.completed_runs = int(match.group(1))
                return SuperflipProgress(repeat=self.repeat_total, repeat_total=self.repeat_total, phase="completed")
        except Exception:
            return None
        return None


def cycle_progress_stages(cfg: object) -> List[str]:
    """Return only workflow stages that can actually execute for this run."""
    modelfile_mode = normalize_modelfile_source(str(getattr(cfg, "modelfile_source", "")))
    raw_superflip_cycling = modelfile_mode == "superflip_xplor"
    stages = ["Preparing cycle", "Superflip"]
    if bool(getattr(cfg, "run_edma_superflip", False)):
        stages.append("EDMA · Superflip map")
    if bool(getattr(cfg, "run_sharped", False)) and not raw_superflip_cycling:
        stages.append("SharpED")
    if bool(getattr(cfg, "symmetrize_deblurred_map", False)) and not raw_superflip_cycling:
        stages.append("Superflip symmetry averaging")
    if bool(getattr(cfg, "run_edma_deblurred", False)) and not raw_superflip_cycling:
        stages.append(f"EDMA · {result_map_label('deblurred')}")
    stages.append("Finalizing cycle")
    return stages


@dataclass
class XplorMap:
    title: str
    grid: Tuple[int, int, int, int, int, int, int, int, int]
    cell: Tuple[float, float, float, float, float, float]
    axis_order: str
    data: np.ndarray

@dataclass
class HklAnalysis:
    hkl_path: Path
    data_mode: str
    cell: gemmi.UnitCell
    spacegroup: gemmi.SpaceGroup
    spacegroup_hm: str
    reflections_raw: List[Reflection]
    reflections_unique: List[Reflection]
    d_min: float
    d_full_98: Optional[float]
    bins: List[Dict[str, float]]
    source_note: str

@dataclass
class HklAnalysisRequest:
    mode: str
    hkl_text: str
    jana_text: str
    ref_text: str
    work_text: str
    configured_mode: str
    metadata: Optional[CrystalMetadata] = None

@dataclass
class HklLoadResult:
    hkl_path: Path
    data_mode: str
    cell: gemmi.UnitCell
    spacegroup: gemmi.SpaceGroup
    spacegroup_hm: str
    source_note: str
    value_col: int
    sigma_col: Optional[int]
    include_000: bool
    reflections: List[Reflection]
    unique_reflections: List[Reflection]

REFERENCE_STRUCTURE_SUFFIXES = {".cif", ".ins", ".res"}
REFERENCE_DENSITY_SUFFIXES = {".xplor", ".ccp4", ".map", ".m80", ".m81", ".jana"}
REFERENCE_FILE_SUFFIXES = REFERENCE_STRUCTURE_SUFFIXES | REFERENCE_DENSITY_SUFFIXES

# -----------------------------------------------------------------------------
# CIF / crystallographic helpers
# -----------------------------------------------------------------------------

def clean_element_symbol(value: str) -> str:
    value = re.sub(r"[^A-Za-z]", "", str(value or "")).capitalize()
    if len(value) > 1:
        value = value[0] + value[1:].lower()
    return value or "X"

def normalize_atom_label(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()

def wrap_frac(frac: Sequence[float]) -> np.ndarray:
    arr = np.asarray(frac, dtype=np.float64)
    return arr - np.floor(arr)

def parse_triplet_for_superflip(triplet: str) -> str:
    parts = [p.strip() for p in triplet.split(",")]
    out: List[str] = []
    for p in parts:
        p = re.sub(r"(?<![A-Za-z0-9_])x(?![A-Za-z0-9_])", "x1", p)
        p = re.sub(r"(?<![A-Za-z0-9_])y(?![A-Za-z0-9_])", "x2", p)
        p = re.sub(r"(?<![A-Za-z0-9_])z(?![A-Za-z0-9_])", "x3", p)
        out.append(p)
    return " ".join(out)

def center_vector_to_float_string(v: Sequence[int]) -> str:
    vals = [float(x) / 24.0 for x in v]
    return "  " + "  ".join(f"{x:.6f}" for x in vals)

def apply_gemmi_op(op: gemmi.Op, frac: Sequence[float]) -> np.ndarray:
    res = op.apply_to_xyz([float(frac[0]), float(frac[1]), float(frac[2])])
    try:
        vals = [float(res[0]), float(res[1]), float(res[2])]
    except Exception:
        vals = [float(res.x), float(res.y), float(res.z)]
    return wrap_frac(vals)

def expand_atoms_by_symmetry(atoms: Sequence[AtomSite], sg: gemmi.SpaceGroup) -> List[AtomSite]:
    if not atoms:
        return []
    ops = full_spacegroup_ops(sg)
    if not ops:
        return list(atoms)
    expanded: List[AtomSite] = []
    seen = set()
    for atom in atoms:
        for op_idx, op in enumerate(ops):
            frac = apply_gemmi_op(op, atom.frac)
            key = (
                clean_element_symbol(atom.element),
                round(float(frac[0]), 4),
                round(float(frac[1]), 4),
                round(float(frac[2]), 4),
            )
            if key in seen:
                continue
            seen.add(key)
            expanded.append(AtomSite(label=f"{atom.label}_{op_idx+1}", element=atom.element, frac=frac, density=atom.density))
    return expanded

def full_spacegroup_ops(sg: gemmi.SpaceGroup) -> List[gemmi.Op]:
    try:
        group_ops = sg.operations()
        return [op.translated(cen) for op in group_ops.sym_ops for cen in group_ops.cen_ops]
    except Exception:
        return []

def frac_distance_angstrom(cell: gemmi.UnitCell, f1: Sequence[float], f2: Sequence[float]) -> float:
    d = np.asarray(f1, dtype=np.float64) - np.asarray(f2, dtype=np.float64)
    d -= np.round(d)
    pos = cell.orthogonalize(gemmi.Fractional(float(d[0]), float(d[1]), float(d[2])))
    return float(math.sqrt(pos.x * pos.x + pos.y * pos.y + pos.z * pos.z))

def spacegroup_name_candidates(name: str) -> List[str]:
    raw = str(name or "").strip().strip("'\"")
    if not raw:
        return ["P 1"]
    candidates = [raw]
    spaced = re.sub(r"\s+", " ", raw)
    compact = spaced.replace(" ", "")
    if spaced not in candidates:
        candidates.append(spaced)
    compact_low = compact.lower()
    if compact_low in {"p21/n", "p121/n1"}:
        candidates.extend(["P 21/n", "P 1 21/n 1", "P 21/c", "P 1 21/c 1"])
    elif compact_low in {"p21/c", "p121/c1"}:
        candidates.extend(["P 21/c", "P 1 21/c 1", "P 21/n", "P 1 21/n 1"])
    m = re.fullmatch(r"([A-Za-z])\s+1\s+(.+?)\s+1", spaced)
    if m:
        candidates.append(f"{m.group(1).upper()} {m.group(2)}")
    if compact not in candidates:
        candidates.append(compact)
    return candidates

def get_spacegroup_from_name(name: str) -> gemmi.SpaceGroup:
    candidates = spacegroup_name_candidates(name)
    for cand in candidates:
        try:
            return gemmi.SpaceGroup(cand)
        except Exception:
            continue
    return gemmi.SpaceGroup("P 1")


def resolve_spacegroup_symbol(name: str) -> Optional[gemmi.SpaceGroup]:
    """Resolve a user-entered symbol without silently falling back to P 1."""
    if not str(name or "").strip():
        return None
    for candidate in spacegroup_name_candidates(name):
        try:
            return gemmi.SpaceGroup(candidate)
        except Exception:
            continue
    return None

def get_spacegroup_from_number(number_text: str) -> Optional[gemmi.SpaceGroup]:
    parsed = parse_cif_number(number_text, math.nan) if str(number_text or "").strip() else math.nan
    number = int(parsed) if np.isfinite(parsed) else 0
    if number <= 0:
        return None
    for factory in (
        lambda n: gemmi.SpaceGroup(n),
        lambda n: gemmi.find_spacegroup_by_number(n),
    ):
        try:
            sg = factory(number)
            if sg is not None:
                return sg
        except Exception:
            continue
    return None


def compact_spacegroup_symbol(spacegroup: gemmi.SpaceGroup) -> str:
    try:
        return str(spacegroup.short_name()).strip()
    except Exception:
        return str(spacegroup.hm).strip()


def validate_composition_text(value: str) -> str:
    """Validate the existing whitespace-separated Superflip composition syntax."""
    text = str(value or "").strip()
    if not text:
        raise ValueError("Composition is missing.")
    tokens = [token for token in re.split(r"[\s,;]+", text) if token]
    awaiting_count = False
    saw_element = False
    for token in tokens:
        match = re.fullmatch(r"([A-Z][a-z]?|D)([0-9]+(?:\.[0-9]+)?)?", token)
        if match:
            symbol = "H" if match.group(1) == "D" else match.group(1)
            try:
                if gemmi.Element(symbol).atomic_number <= 0:
                    raise ValueError
            except Exception as exc:
                raise ValueError(f"Composition contains an unknown element: {match.group(1)}") from exc
            if match.group(2) is not None and float(match.group(2)) <= 0:
                raise ValueError(f"Composition count must be positive: {token}")
            awaiting_count = match.group(2) is None
            saw_element = True
            continue
        if awaiting_count and re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", token):
            if float(token) <= 0:
                raise ValueError(f"Composition count must be positive: {token}")
            awaiting_count = False
            continue
        raise ValueError(
            f"Invalid composition token '{token}'. Use the existing Superflip syntax, for example Ag196 S108 O40 B1000."
        )
    if not saw_element:
        raise ValueError("Composition is missing.")
    return text


def parse_composition_counts(composition: str) -> List[Tuple[str, int]]:
    """Parse the existing whitespace-separated Superflip composition syntax
    (e.g. "Zn8 I8 C8 H8 N8" or "Ag 196 S 108") into ordered (element, count)
    pairs, mirroring validate_composition_text()'s grammar. Used as a
    composition-driven fallback for EDMA peak element assignment when no
    reference-structure atom sites are available (see
    assign_elements_by_reference_composition())."""
    text = str(composition or "").strip()
    if not text:
        return []
    tokens = [token for token in re.split(r"[\s,;]+", text) if token]
    result: List[Tuple[str, int]] = []
    pending_symbol: Optional[str] = None
    for token in tokens:
        match = re.fullmatch(r"([A-Z][a-z]?|D)([0-9]+(?:\.[0-9]+)?)?", token)
        if match:
            if pending_symbol is not None:
                result.append((pending_symbol, 1))
            symbol = "H" if match.group(1) == "D" else match.group(1)
            if match.group(2) is not None:
                result.append((symbol, max(1, int(round(float(match.group(2)))))))
                pending_symbol = None
            else:
                pending_symbol = symbol
            continue
        if pending_symbol is not None and re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", token):
            result.append((pending_symbol, max(1, int(round(float(token))))))
            pending_symbol = None
            continue
        # Unrecognized token: ignore defensively here -- validate_composition_text()
        # is the authoritative validator and already runs earlier in the pipeline.
    if pending_symbol is not None:
        result.append((pending_symbol, 1))
    return result


def validate_crystal_cell(cell: gemmi.UnitCell) -> gemmi.UnitCell:
    values = (cell.a, cell.b, cell.c, cell.alpha, cell.beta, cell.gamma)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("Unit-cell parameters must be finite numbers.")
    if min(cell.a, cell.b, cell.c) <= 0.0:
        raise ValueError("Unit-cell lengths a, b and c must be greater than zero.")
    if not all(0.0 < angle < 180.0 for angle in (cell.alpha, cell.beta, cell.gamma)):
        raise ValueError("Unit-cell angles alpha, beta and gamma must be between 0 and 180 degrees.")
    if not math.isfinite(float(cell.volume)) or cell.volume <= 0.0:
        raise ValueError("The supplied unit cell has no physical positive volume.")
    return cell

def get_cif_blocks(cif_path: Path) -> List[gemmi.cif.Block]:
    doc = gemmi.cif.read_file(str(cif_path))
    if len(doc) == 0:
        raise ValueError(f"Empty CIF: {cif_path}")
    return [doc[i] for i in range(len(doc))]

def get_cif_block(cif_path: Path) -> gemmi.cif.Block:
    """Return the first block, kept for compatibility."""
    return get_cif_blocks(cif_path)[0]

def get_block_value(block: gemmi.cif.Block, keys: Sequence[str], default: str = "") -> str:
    """Case-tolerant block value lookup."""
    wanted = {str(k).lower() for k in keys}
    for k in keys:
        try:
            v = block.find_value(k)
            if v is not None and str(v).strip():
                return str(v).strip().strip("'\"")
        except Exception:
            pass
    # Some CIF readers are strict about item spelling/case.  Fall back to a
    # pair iterator over all items in the block.
    try:
        for item in block:
            try:
                key = str(item.pair[0])
                val = str(item.pair[1])
            except Exception:
                continue
            if key.lower() in wanted and val.strip():
                return val.strip().strip("'\"")
    except Exception:
        pass
    return default

def parse_cif_number(value: str, default: float) -> float:
    s = str(value).strip().strip("'\"")
    if not s or s in {".", "?"}:
        return default
    # CIF often stores standard uncertainties, e.g. 35.3409(2).
    s = re.sub(r"\([^)]+\)$", "", s)
    try:
        return float(s)
    except Exception:
        return default

def is_cif_placeholder(value: str) -> bool:
    return str(value or "").strip().strip("'\"") in {"", ".", "?"}

def manual_cif_value(cif_path: Path, keys: Sequence[str]) -> str:
    """Very robust last-resort lookup from raw CIF text.

    Handles values on the same line and values on the next line.  This is here
    because database CIFs can contain several data blocks, comments and quoted
    values, and we must never silently fall back to a 1 Å dummy cell.
    """
    wanted = {k.lower() for k in keys}
    lines = cif_path.read_text(encoding="utf-8", errors="replace").splitlines()
    for i, raw in enumerate(lines):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split(None, 1)
        if not parts:
            continue
        key = parts[0].lower()
        if key not in wanted:
            continue
        if len(parts) > 1 and parts[1].strip():
            return parts[1].strip().strip("'\"")
        # Value on next non-empty non-comment line.
        for j in range(i + 1, min(len(lines), i + 6)):
            nxt = lines[j].strip()
            if nxt and not nxt.startswith("#"):
                return nxt.strip("'\"")
    return ""

def raw_cif_value(cif_path: Path, keys: Sequence[str]) -> str:
    """Raw text CIF value lookup across all data blocks.

    This is deliberately independent of gemmi so database CIFs with global
    blocks, validation text and unusual loops cannot silently fall back to a
    1 Å dummy cell.
    """
    wanted = {k.lower() for k in keys}
    lines = cif_path.read_text(encoding="utf-8", errors="replace").splitlines()
    for i, raw in enumerate(lines):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith(";"):
            continue
        parts = stripped.split(None, 1)
        if not parts:
            continue
        key = parts[0].lower()
        if key not in wanted:
            continue
        if len(parts) > 1 and parts[1].strip():
            val = parts[1].strip()
            if "#" in val:
                val = val.split("#", 1)[0].strip()
            val = val.strip().strip("'\"")
            if not is_cif_placeholder(val):
                return val
            continue
        for j in range(i + 1, min(len(lines), i + 8)):
            nxt = lines[j].strip()
            if nxt and not nxt.startswith("#"):
                val = nxt.strip().strip("'\"")
                if not is_cif_placeholder(val):
                    return val
                break
    return ""


def composition_from_formula(formula: str) -> str:
    text = str(formula or "").strip().strip("'\"")
    if not text or text in {".", "?"}:
        return ""
    parts: List[str] = []
    for elem, count_text in re.findall(r"([A-Z][a-z]?|D)\s*([0-9]+(?:\.[0-9]+)?)?", text):
        elem = clean_element_symbol(elem)
        if elem in {"H", "D"}:
            continue
        count = float(count_text) if count_text else 1.0
        if abs(count - round(count)) < 1e-2:
            count_str = str(int(round(count)))
        else:
            count_str = f"{count:g}"
        parts.append(f"{elem}{count_str}")
    return " ".join(parts)


def parse_cif_cell_and_sg(cif_path: Path) -> Tuple[gemmi.UnitCell, gemmi.SpaceGroup, str]:
    cell_keys = [
        "_cell_length_a", "_cell_length_b", "_cell_length_c",
        "_cell_angle_alpha", "_cell_angle_beta", "_cell_angle_gamma",
    ]
    sg_keys = [
        "_space_group_name_H-M_alt", "_symmetry_space_group_name_H-M_alt",
        "_symmetry_space_group_name_H-M", "_space_group_name_h-m_alt",
        "_symmetry_space_group_name_h-m_alt", "_symmetry_space_group_name_h-m",
    ]
    sg_number_keys = [
        "_space_group_IT_number", "_symmetry_Int_Tables_number",
        "_space_group.it_number", "_symmetry_int_tables_number",
    ]

    # Raw text first. This handles Jana/database CIFs with data_global before
    # the real data block, e.g. _cell_length_a 24.3524(4).
    vals = [parse_cif_number(raw_cif_value(cif_path, [k]), math.nan) for k in cell_keys]
    has_lengths = all(np.isfinite(vals[i]) and vals[i] > 2.0 for i in range(3))
    has_angles = all(np.isfinite(vals[i]) and 20.0 < vals[i] < 170.0 for i in range(3, 6))
    hm = raw_cif_value(cif_path, sg_keys)
    sg_number = raw_cif_value(cif_path, sg_number_keys)

    if not (has_lengths and has_angles):
        # Secondary gemmi fallback.
        vals = [math.nan] * 6
        hm = ""
        sg_number = ""
        for block in get_cif_blocks(cif_path):
            tmp = [parse_cif_number(get_block_value(block, [k], ""), math.nan) for k in cell_keys]
            ok_len = all(np.isfinite(tmp[i]) and tmp[i] > 2.0 for i in range(3))
            ok_ang = all(np.isfinite(tmp[i]) and 20.0 < tmp[i] < 170.0 for i in range(3, 6))
            if ok_len and ok_ang:
                vals = tmp
                hm = get_block_value(block, sg_keys, "")
                sg_number = get_block_value(block, sg_number_keys, "")
                break

    has_lengths = all(np.isfinite(vals[i]) and vals[i] > 2.0 for i in range(3))
    has_angles = all(np.isfinite(vals[i]) and 20.0 < vals[i] < 170.0 for i in range(3, 6))
    if not (has_lengths and has_angles):
        raise ValueError(
            f"Could not read a physical unit cell from reference CIF: {cif_path}\n"
            f"Parsed values were: {vals}\n"
            "Expected _cell_length_a/b/c and _cell_angle_alpha/beta/gamma."
        )

    cell = gemmi.UnitCell(*[float(x) for x in vals])
    hm = (hm or "P 1").strip().strip("'\"")
    sg = get_spacegroup_from_number(hm) if re.fullmatch(r"\d+(?:\.0+)?", str(hm).strip()) else None
    if sg is None:
        sg = get_spacegroup_from_name(hm)
    if sg.number == 1 and hm.replace(" ", "").lower() not in {"p1", "p-1"}:
        sg_from_number = get_spacegroup_from_number(sg_number)
        if sg_from_number is not None:
            sg = sg_from_number
    low = hm.lower().replace("'", "").replace('"', "").strip()
    if low in {"p 1 21/n 1", "p21/n", "p 21/n"} or "21/n" in low:
        hm = "P 21/n"
    elif low in {"p 1 21/c 1", "p21/c", "p 21/c"} or "21/c" in low:
        hm = "P 21/c"
    elif sg.number != 1:
        try:
            hm = str(sg.hm).strip() or hm
        except Exception:
            pass
    return cell, sg, hm or sg.hm


def parse_cif_atoms(cif_path: Path) -> List[AtomSite]:
    atoms: List[AtomSite] = []
    lines = cif_path.read_text(encoding="utf-8", errors="replace").splitlines()
    i = 0
    while i < len(lines):
        if lines[i].strip().lower() != "loop_":
            i += 1
            continue
        i += 1
        headers: List[str] = []
        while i < len(lines) and lines[i].lstrip().startswith("_"):
            headers.append(lines[i].strip())
            i += 1
        lower = [h.lower() for h in headers]
        needed = {"_atom_site_label", "_atom_site_fract_x", "_atom_site_fract_y", "_atom_site_fract_z"}
        if not needed.issubset(set(lower)):
            while i < len(lines) and not lines[i].lstrip().startswith(("loop_", "_", "data_")):
                i += 1
            continue
        ilabel = lower.index("_atom_site_label")
        ix = lower.index("_atom_site_fract_x")
        iy = lower.index("_atom_site_fract_y")
        iz = lower.index("_atom_site_fract_z")
        ielem = lower.index("_atom_site_type_symbol") if "_atom_site_type_symbol" in lower else None
        while i < len(lines):
            raw = lines[i]
            stripped = raw.lstrip()
            if stripped.startswith("loop_") or stripped.startswith("_") or stripped.startswith("data_"):
                break
            if not raw.strip() or raw.strip().startswith("#"):
                i += 1
                continue
            parts = raw.split()
            if len(parts) > max(ilabel, ix, iy, iz):
                try:
                    label = parts[ilabel]
                    elem = clean_element_symbol(parts[ielem]) if ielem is not None and len(parts) > ielem else clean_element_symbol(label)
                    fx = parse_cif_number(parts[ix], math.nan)
                    fy = parse_cif_number(parts[iy], math.nan)
                    fz = parse_cif_number(parts[iz], math.nan)
                    if not (np.isfinite(fx) and np.isfinite(fy) and np.isfinite(fz)):
                        raise ValueError("bad fractional coordinate")
                    frac = wrap_frac([fx, fy, fz])
                    atoms.append(AtomSite(label=label, element=elem, frac=frac))
                except Exception:
                    pass
            i += 1
    if atoms:
        return atoms
    try:
        doc = gemmi.cif.read_file(str(cif_path))
        for block in doc:
            st = gemmi.make_small_structure_from_block(block)
            for site in st.sites:
                elem = clean_element_symbol(site.element.name if site.element.name else site.label)
                frac = wrap_frac([site.fract.x, site.fract.y, site.fract.z])
                atoms.append(AtomSite(label=site.label, element=elem, frac=frac))
            if atoms:
                return atoms
    except Exception:
        pass
    return atoms

def cif_has_readable_atoms(cif_path: Optional[Path]) -> bool:
    if cif_path is None or not cif_path.is_file():
        return False
    try:
        return bool(parse_cif_atoms(cif_path))
    except Exception:
        return False

def atom_element_counts(atoms: Sequence[AtomSite]) -> Tuple[Dict[str, int], List[str]]:
    counts: Dict[str, int] = collections.Counter()
    order: List[str] = []
    for a in atoms:
        elem = clean_element_symbol(a.element)
        if elem in {"H", "D"}:
            continue
        if elem not in counts:
            order.append(elem)
        counts[elem] += 1
    return counts, order

def composition_from_atoms(atoms: Sequence[AtomSite], elements: Optional[Sequence[str]] = None) -> str:
    counts, order = atom_element_counts(atoms)
    parts: List[str] = []
    if elements is not None:
        for elem in elements:
            ce = clean_element_symbol(elem)
            if counts.get(ce, 0) > 0:
                parts.append(f"{ce}{counts[ce]}")
    else:
        parts = [f"{elem}{counts[elem]}" for elem in order if counts.get(elem, 0) > 0]
    if parts:
        return " ".join(parts)
    return "C1"

def composition_from_full_cell_atoms(atoms: Sequence[AtomSite], cell: gemmi.UnitCell, sg: gemmi.SpaceGroup) -> str:
    if not atoms:
        return ""
    ops = full_spacegroup_ops(sg)
    if not ops:
        ops = list(sg.operations().sym_ops)
    expanded: List[AtomSite] = []
    for atom in atoms:
        elem = clean_element_symbol(atom.element)
        if elem in {"H", "D"}:
            continue
        for op in ops:
            frac = apply_gemmi_op(op, atom.frac)
            duplicate = False
            for old in expanded:
                if clean_element_symbol(old.element) == elem and frac_distance_angstrom(cell, frac, old.frac) < 0.25:
                    duplicate = True
                    break
            if not duplicate:
                expanded.append(AtomSite(label=atom.label, element=elem, frac=frac, density=atom.density))
    return composition_from_atoms(expanded) if expanded else ""


def read_reference_crystal_metadata(reference_file: Path) -> CrystalMetadata:
    """Read one complete metadata set from the selected structure reference."""
    path = Path(reference_file).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Reference metadata file not found: {path}")
    if path.suffix.lower() not in REFERENCE_STRUCTURE_SUFFIXES:
        raise ValueError("Reference metadata requires a CIF/INS/RES structure file.")

    cell, spacegroup, hm = parse_cif_cell_and_sg(path)
    validate_crystal_cell(cell)
    sg_symbol = raw_cif_value(
        path,
        [
            "_space_group_name_H-M_alt",
            "_symmetry_space_group_name_H-M_alt",
            "_symmetry_space_group_name_H-M",
        ],
    )
    sg_number = raw_cif_value(
        path,
        ["_space_group_IT_number", "_symmetry_Int_Tables_number", "_space_group.it_number"],
    )
    if path.suffix.lower() == ".cif" and not (sg_symbol or sg_number):
        raise ValueError("Reference file does not contain space-group metadata.")

    atoms = parse_cif_atoms(path)
    formula = composition_from_formula(
        raw_cif_value(path, ["_chemical_formula_sum", "_chemical_formula_moiety"])
    )
    composition = composition_from_full_cell_atoms(atoms, cell, spacegroup) or formula or composition_from_atoms(atoms)
    composition = validate_composition_text(composition)
    return CrystalMetadata(
        cell=cell,
        spacegroup=spacegroup,
        spacegroup_hm=str(hm or spacegroup.hm).strip(),
        composition=composition,
        source=METADATA_SOURCE_REFERENCE,
        source_path=path,
    )


def reference_context_from_metadata(
    metadata: CrystalMetadata,
    atom_source: Optional[Path],
    work_dir: Path,
) -> ReferenceContext:
    """Create the existing downstream context from one authoritative metadata set."""
    atoms: List[AtomSite] = []
    source_path = metadata.source_path or Path("phase_studio_manual_metadata")
    if atom_source is not None and Path(atom_source).is_file() and Path(atom_source).suffix.lower() in REFERENCE_STRUCTURE_SUFFIXES:
        source_path = Path(atom_source).resolve()
        atoms = parse_cif_atoms(source_path)
    work_ref = Path(work_dir) / "phase_studio_reference_for_metrics.cif"
    write_structure_cif(
        work_ref,
        metadata.cell,
        metadata.spacegroup,
        metadata.spacegroup_hm,
        atoms,
        metadata.composition,
    )
    return ReferenceContext(
        cif_path=Path(source_path),
        work_ref_cif=work_ref,
        cell=metadata.cell,
        spacegroup=metadata.spacegroup,
        spacegroup_hm=metadata.spacegroup_hm,
        composition=metadata.composition,
        atoms=atoms,
    )

def load_reference_context(reference_cif: Path, work_dir: Path, composition_override: str = "") -> ReferenceContext:
    metadata = read_reference_crystal_metadata(reference_cif)
    if composition_override.strip():
        metadata = CrystalMetadata(
            metadata.cell,
            metadata.spacegroup,
            metadata.spacegroup_hm,
            validate_composition_text(composition_override),
            metadata.source,
            metadata.source_path,
        )
    return reference_context_from_metadata(metadata, reference_cif, work_dir)



def reference_context_with_external_atom_sites(
    ref_ctx: ReferenceContext,
    external_cif: Optional[Path],
    work_dir: Path,
    composition_override: str = "",
    log: Optional[Callable[[str], None]] = None,
) -> ReferenceContext:
    """Use atom sites from an explicit reference CIF without replacing Jana HKL.

    In Jana2020 .inflip mode, Phase Studio can synthesize a metadata-only CIF from
    cell/spacegroup/composition.  That file is useful for setting up the run,
    but it has zero atom sites and is invalid as a Superflip reference density.
    When the user explicitly selects a real CIF as Superflip referencefile, keep
    Jana cell/spacegroup as the run metadata but use the selected CIF's atoms for
    metrics/EDMA reference handling.
    """
    if external_cif is None or Path(external_cif).suffix.lower() != ".cif":
        return ref_ctx
    try:
        atoms = parse_cif_atoms(Path(external_cif))
    except Exception:
        atoms = []
    if not atoms:
        return ref_ctx
    full_cell_comp = composition_from_full_cell_atoms(atoms, ref_ctx.cell, ref_ctx.spacegroup)
    comp = composition_override.strip() or full_cell_comp or composition_from_formula(
        raw_cif_value(Path(external_cif), ["_chemical_formula_sum", "_chemical_formula_moiety"])
    ) or composition_from_atoms(atoms) or ref_ctx.composition
    work_ref = work_dir / "phase_studio_reference_atoms_from_selected_cif.cif"
    write_structure_cif(work_ref, ref_ctx.cell, ref_ctx.spacegroup, ref_ctx.spacegroup_hm, atoms)
    if log is not None:
        log(f"Reference atom sites taken from selected Superflip reference CIF: {external_cif}")
        log(f"Working reference CIF with atom sites: {work_ref}")
    return ReferenceContext(
        cif_path=Path(external_cif),
        work_ref_cif=work_ref,
        cell=ref_ctx.cell,
        spacegroup=ref_ctx.spacegroup,
        spacegroup_hm=ref_ctx.spacegroup_hm,
        composition=comp,
        atoms=atoms,
    )


def expanded_unique_atoms(atoms: Sequence[AtomSite], cell: gemmi.UnitCell, sg: gemmi.SpaceGroup, merge_tol_a: float = 0.25) -> List[AtomSite]:
    ops = sg.operations().sym_ops
    out: List[AtomSite] = []
    for a in atoms:
        for op in ops:
            f = apply_gemmi_op(op, a.frac)
            duplicate = False
            for b in out:
                if clean_element_symbol(a.element) == clean_element_symbol(b.element) and frac_distance_angstrom(cell, f, b.frac) < merge_tol_a:
                    duplicate = True
                    break
            if not duplicate:
                out.append(AtomSite(label=a.label, element=a.element, frac=f, density=a.density))
    return out

def nearest_metric_to_reference(model_cif: Optional[Path], ref_ctx: ReferenceContext, same_element: bool = True) -> Optional[float]:
    if model_cif is None or not Path(model_cif).is_file():
        return None
    model_atoms = parse_cif_atoms(Path(model_cif))
    if not model_atoms or not ref_ctx.atoms:
        return None
    ref_full = expanded_unique_atoms(ref_ctx.atoms, ref_ctx.cell, ref_ctx.spacegroup)
    _, model_sg, _ = parse_cif_cell_and_sg(Path(model_cif))
    model_full = expanded_unique_atoms(model_atoms, ref_ctx.cell, model_sg)
    def distances(a_list: Sequence[AtomSite], b_list: Sequence[AtomSite]) -> List[float]:
        ds: List[float] = []
        for a in a_list:
            candidates = [b for b in b_list if (not same_element or clean_element_symbol(a.element) == clean_element_symbol(b.element))]
            if not candidates:
                candidates = list(b_list)
            if candidates:
                ds.append(min(frac_distance_angstrom(ref_ctx.cell, a.frac, b.frac) for b in candidates))
        return ds
    all_d = np.asarray(distances(model_full, ref_full) + distances(ref_full, model_full), dtype=np.float64)
    if len(all_d) == 0:
        return None
    return float(math.sqrt(np.mean(np.square(all_d))))

def atom_recall_precision(
    model_cif: Optional[Path], ref_ctx: ReferenceContext, merge_distance: float, same_element: bool = True,
) -> Optional[Tuple[Optional[float], Optional[float]]]:
    """Recall/precision of EDMA-found atoms against the reference: each atom is
    matched to its nearest same-element counterpart within merge_distance
    (independent nearest-neighbor lookup per atom, not a global bipartite
    assignment -- a lightweight per-cycle indicator, not a publication-grade
    validation metric). Hydrogen and helium are excluded from both sides before
    matching, since electron-density charge-flipping cannot resolve them (too
    few electrons); counting them would systematically and misleadingly depress
    recall for any hydrogen-containing structure regardless of reconstruction
    quality. Unlike nearest_metric_to_reference's RMSD, a reference atom with no
    same-element candidate within range counts as unmatched (no any-element
    fallback), since miscounting a wrong-element peak as "found" would
    misrepresent recall/precision. Returns None only when there are no heavy
    reference atoms to compare against; with a reference but an empty/missing
    model, returns (0.0, None) -- recall is 0, precision has no denominator
    (nothing was found to be right or wrong about)."""
    def heavy(atoms: Sequence[AtomSite]) -> List[AtomSite]:
        return [a for a in atoms if clean_element_symbol(a.element) not in {"H", "He"}]
    if not ref_ctx.atoms:
        return None
    ref_full = heavy(expanded_unique_atoms(heavy(ref_ctx.atoms), ref_ctx.cell, ref_ctx.spacegroup))
    if not ref_full:
        return None
    model_atoms = heavy(parse_cif_atoms(Path(model_cif))) if model_cif is not None and Path(model_cif).is_file() else []
    if not model_atoms:
        return (0.0, None)
    _, model_sg, _ = parse_cif_cell_and_sg(Path(model_cif))
    model_full = heavy(expanded_unique_atoms(model_atoms, ref_ctx.cell, model_sg))
    if not model_full:
        return (0.0, None)
    def nearest_distance(a: AtomSite, candidates: Sequence[AtomSite]) -> Optional[float]:
        same = [b for b in candidates if not same_element or clean_element_symbol(a.element) == clean_element_symbol(b.element)]
        if not same:
            return None
        return min(frac_distance_angstrom(ref_ctx.cell, a.frac, b.frac) for b in same)
    matched_ref = sum(1 for a in ref_full if (d := nearest_distance(a, model_full)) is not None and d <= merge_distance)
    matched_model = sum(1 for a in model_full if (d := nearest_distance(a, ref_full)) is not None and d <= merge_distance)
    recall = matched_ref / len(ref_full)
    precision = matched_model / len(model_full)
    return (recall, precision)

def count_heavy_atoms(model_cif: Optional[Path]) -> Optional[float]:
    """Number of non-hydrogen, non-helium atoms in an EDMA structure export --
    a reference-free fallback progress indicator (does the found atom count
    stabilize across cycles) for when no reference structure is available."""
    if model_cif is None or not Path(model_cif).is_file():
        return None
    atoms = parse_cif_atoms(Path(model_cif))
    if not atoms:
        return None
    return float(sum(1 for a in atoms if clean_element_symbol(a.element) not in {"H", "He"}))

# -----------------------------------------------------------------------------
# HKL / Superflip / SharpED / EDMA
# -----------------------------------------------------------------------------

def normalize_reflection_data_mode(value: str) -> str:
    # A combo item's own friendly display text (see REFLECTION_DATA_MODE_DISPLAY_LABELS,
    # used to populate the "HKL format" combo below) must normalize back to its
    # own internal token, exactly like input_source_mode/metadata_source already
    # do -- checked before the alias lowering, which would otherwise mangle the
    # "·"/"σ" characters into something no alias recognizes.
    raw = str(value or "")
    for token, label in REFLECTION_DATA_MODE_DISPLAY_LABELS.items():
        if raw == label:
            return token
    mode = raw.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "auto": REFLECTION_DATA_MODE_SET_FROM_INFLIP,
        "auto_detect": REFLECTION_DATA_MODE_AUTO,
        "detect": REFLECTION_DATA_MODE_AUTO,
        "set_from_inflip": REFLECTION_DATA_MODE_SET_FROM_INFLIP,
        "hkl_i_sigma": REFLECTION_DATA_MODE_INTENSITY,
        "hkl_f_sigma": REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA,
        "hkl_i_phase_sigma": REFLECTION_DATA_MODE_INTENSITY_PHASE_SIGMA,
        "hkl_f_phase_sigma": REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA,
        "i": REFLECTION_DATA_MODE_INTENSITY,
        "int": REFLECTION_DATA_MODE_INTENSITY,
        "intensities": REFLECTION_DATA_MODE_INTENSITY,
        "intensity_sigma": REFLECTION_DATA_MODE_INTENSITY,
        "f": REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA,
        "fobs": REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA,
        "fobs_sigma": REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA,
        "amplitude": REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA,
        "amplitudes": REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA,
        "amplitude_sigma": REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA,
        "amplitude_dummy_sigma": REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA,
        "fobs_phase_sigma": REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA,
        "fobs_zero_phase": REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA,
        "fobs_zero_phase_sigma": REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA,
        "intensity_phase_sigma": REFLECTION_DATA_MODE_INTENSITY_PHASE_SIGMA,
        "i_phase_sigma": REFLECTION_DATA_MODE_INTENSITY_PHASE_SIGMA,
        "hkl_i_fwhm": REFLECTION_DATA_MODE_INTENSITY_FWHM,
        "hkl_f_fwhm": REFLECTION_DATA_MODE_AMPLITUDE_FWHM,
        "i_fwhm": REFLECTION_DATA_MODE_INTENSITY_FWHM,
        "intensity_fwhm": REFLECTION_DATA_MODE_INTENSITY_FWHM,
        "f_fwhm": REFLECTION_DATA_MODE_AMPLITUDE_FWHM,
        "fobs_fwhm": REFLECTION_DATA_MODE_AMPLITUDE_FWHM,
        "amplitude_fwhm": REFLECTION_DATA_MODE_AMPLITUDE_FWHM,
    }
    mode = aliases.get(mode, mode)
    if mode == REFLECTION_DATA_MODE_AUTO:
        return REFLECTION_DATA_MODE_AUTO
    if mode in {
        REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA,
        REFLECTION_DATA_MODE_INTENSITY_PHASE_SIGMA,
        REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA,
        REFLECTION_DATA_MODE_INTENSITY_FWHM,
        REFLECTION_DATA_MODE_AMPLITUDE_FWHM,
    }:
        return mode
    return REFLECTION_DATA_MODE_INTENSITY


REFLECTION_DATA_MODE_DISPLAY_LABELS = {
    REFLECTION_DATA_MODE_SET_FROM_INFLIP: "Set from .inflip",
    REFLECTION_DATA_MODE_INTENSITY: "h k l · I · σ(I)",
    REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA: "h k l · F · σ(F)",
    REFLECTION_DATA_MODE_INTENSITY_PHASE_SIGMA: "h k l · I · phase · σ(I)",
    REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA: "h k l · F · phase · σ(F)",
    REFLECTION_DATA_MODE_INTENSITY_FWHM: "h k l · I · FWHM",
    REFLECTION_DATA_MODE_AMPLITUDE_FWHM: "h k l · F · FWHM",
}


def format_reflection_data_mode(value: str) -> str:
    """Human-readable column layout for a reflection-data-mode token, for
    read-only summaries and log lines. Never changes parser mode/columns --
    display only."""
    mode = normalize_reflection_data_mode(value)
    return REFLECTION_DATA_MODE_DISPLAY_LABELS.get(mode, str(value or ""))


def wrap_path_tooltip(path_text: str, width: int = 60) -> str:
    """Wrap a long file path across multiple tooltip lines instead of one
    huge horizontal line covering most of the window. Paths rarely contain
    the whitespace textwrap-style wrapping needs, so break after path
    separators instead."""
    text = str(path_text or "")
    if len(text) <= width:
        return text
    parts = re.split(r"([\\/])", text)
    lines: List[str] = []
    current = ""
    for part in parts:
        if current and len(current) + len(part) > width:
            lines.append(current)
            current = part
        else:
            current += part
    if current:
        lines.append(current)
    return "\n".join(lines)


def reflection_mode_is_amplitude(data_mode: str) -> bool:
    return normalize_reflection_data_mode(data_mode) in {
        REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA,
        REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA,
        REFLECTION_DATA_MODE_AMPLITUDE_FWHM,
    }


def reflection_mode_has_phase(data_mode: str) -> bool:
    return normalize_reflection_data_mode(data_mode) in {
        REFLECTION_DATA_MODE_INTENSITY_PHASE_SIGMA,
        REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA,
    }


def reflection_mode_has_fwhm(data_mode: str) -> bool:
    """True when the reflection file's second data column is a peak-shape FWHM
    (full width at half maximum, e.g. from a Le Bail powder extraction), not a
    genuine measurement uncertainty. FWHM is typically on a completely
    different scale than the intensity/amplitude it is paired with, so an
    I/FWHM or F/FWHM ratio is not a signal-to-noise ratio the way I/sigma(I)
    is, and must not be labeled or interpreted as one."""
    return normalize_reflection_data_mode(data_mode) in {
        REFLECTION_DATA_MODE_INTENSITY_FWHM,
        REFLECTION_DATA_MODE_AMPLITUDE_FWHM,
    }


def superflip_dataformat_for_mode(data_mode: str) -> str:
    quantity = "amplitude" if reflection_mode_is_amplitude(data_mode) else "intensity"
    if reflection_mode_has_phase(data_mode):
        return f"{quantity} phase dummy"
    if reflection_mode_has_fwhm(data_mode):
        return f"{quantity} fwhm"
    return f"{quantity} dummy"

def detect_reflection_data_mode_from_hkl(hkl_path: Path) -> str:
    name = hkl_path.name.lower()
    name_hint = REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA if "fobs" in name or "f_obs" in name else None
    try:
        with hkl_path.open("r", encoding="utf-8", errors="ignore") as f:
            for _ in range(80):
                line = f.readline()
                if not line:
                    break
                low = line.lower()
                if "fobs_zero_phase_sigma" in low:
                    return REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA
                if "intensity" in low and "phase" in low:
                    return REFLECTION_DATA_MODE_INTENSITY_PHASE_SIGMA
                if "fobs" in low and "phase" in low:
                    return REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA
                if "intensity" in low and "fwhm" in low:
                    return REFLECTION_DATA_MODE_INTENSITY_FWHM
                if ("fobs" in low or "amplitude" in low) and "fwhm" in low:
                    return REFLECTION_DATA_MODE_AMPLITUDE_FWHM
                if "fobs" in low and "sigma" in low:
                    return REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA
                if "intensity" in low:
                    return REFLECTION_DATA_MODE_INTENSITY
    except Exception:
        pass
    return name_hint or REFLECTION_DATA_MODE_INTENSITY

def resolve_reflection_data_mode(hkl_path: Path, configured_mode: str) -> str:
    mode = normalize_reflection_data_mode(configured_mode)
    if mode == REFLECTION_DATA_MODE_AUTO:
        return detect_reflection_data_mode_from_hkl(hkl_path)
    return mode

def parse_reflection_line(line: str, value_col: int, sigma_col: Optional[int]) -> Optional[Reflection]:
    stripped = line.strip()
    if not stripped or stripped.startswith(COMMENT_PREFIXES):
        return None
    parts = stripped.split()
    if len(parts) < max(3, value_col):
        return None
    try:
        h, k, l = int(float(parts[0])), int(float(parts[1])), int(float(parts[2]))
        value = float(parts[value_col - 1])
        sigma = None
        if sigma_col is not None and sigma_col > 0 and len(parts) >= sigma_col:
            sigma = float(parts[sigma_col - 1])
        phase = None
        if value_col == 4 and sigma_col == 6 and len(parts) >= 5:
            phase_token = parts[4].strip()
            if phase_token not in {"?", ".", "nan", "NaN"}:
                phase = float(phase_token)
        return Reflection(h, k, l, value, sigma, phase)
    except Exception:
        return None

def read_hkl(hkl_path: Path, value_col: int = 4, sigma_col: Optional[int] = 5, include_000: bool = False) -> List[Reflection]:
    reflections: List[Reflection] = []
    with hkl_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            r = parse_reflection_line(line, value_col=value_col, sigma_col=sigma_col)
            if r is None:
                continue
            if not include_000 and r.h == 0 and r.k == 0 and r.l == 0:
                continue
            reflections.append(r)
    if not reflections:
        raise ValueError(f"No reflections parsed from HKL file: {hkl_path}")
    return reflections

def reflection_columns_for_mode(data_mode: str) -> Tuple[int, Optional[int], bool]:
    mode = normalize_reflection_data_mode(data_mode)
    if reflection_mode_has_phase(mode):
        return 4, 6, True
    if mode == REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA:
        return 4, 5, False
    return 4, 5, False

def merge_duplicate_reflections(reflections: Sequence[Reflection]) -> List[Reflection]:
    buckets: Dict[Tuple[int, int, int], List[Reflection]] = collections.defaultdict(list)
    order: List[Tuple[int, int, int]] = []
    for r in reflections:
        key = (int(r.h), int(r.k), int(r.l))
        if key not in buckets:
            order.append(key)
        buckets[key].append(r)
    merged: List[Reflection] = []
    for h, k, l in order:
        items = buckets[(h, k, l)]
        if len(items) == 1:
            merged.append(items[0])
            continue
        vals = np.asarray([float(x.value) for x in items], dtype=np.float64)
        sigs = np.asarray([float(x.sigma) if x.sigma is not None else np.nan for x in items], dtype=np.float64)
        valid = np.isfinite(sigs) & (sigs > 0)
        if np.any(valid):
            w = np.zeros_like(vals)
            w[valid] = 1.0 / np.square(sigs[valid])
            value = float(np.sum(w * vals) / np.sum(w))
            sigma = float(math.sqrt(1.0 / np.sum(w)))
        else:
            value = float(np.mean(vals))
            sigma = None
        phases = np.asarray([float(x.phase) if x.phase is not None else np.nan for x in items], dtype=np.float64)
        phase: Optional[float] = None
        valid_phases = np.isfinite(phases)
        if np.any(valid_phases):
            angles = np.deg2rad(phases[valid_phases])
            phase = float(math.degrees(math.atan2(float(np.mean(np.sin(angles))), float(np.mean(np.cos(angles))))))
        merged.append(Reflection(h, k, l, value, sigma, phase))
    return merged

def observed_hkl_name_for_mode(data_mode: str) -> str:
    mode = normalize_reflection_data_mode(data_mode)
    if mode == REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA:
        return "observed_unique_amplitude_sigma_for_superflip.hkl"
    if mode == REFLECTION_DATA_MODE_INTENSITY_PHASE_SIGMA:
        return "observed_unique_intensity_phase_sigma_for_superflip.hkl"
    if mode == REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA:
        return "observed_unique_amplitude_phase_sigma_for_superflip.hkl"
    return "observed_unique_for_superflip.hkl"

def reflection_d_spacing(cell: gemmi.UnitCell, h: int, k: int, l: int) -> float:
    if h == 0 and k == 0 and l == 0:
        return math.inf
    a, b, c = float(cell.a), float(cell.b), float(cell.c)
    alpha, beta, gamma = math.radians(float(cell.alpha)), math.radians(float(cell.beta)), math.radians(float(cell.gamma))
    sin_alpha, sin_beta, sin_gamma = math.sin(alpha), math.sin(beta), math.sin(gamma)
    volume_factor = math.sqrt(
        max(
            0.0,
            1.0
            - math.cos(alpha) ** 2
            - math.cos(beta) ** 2
            - math.cos(gamma) ** 2
            + 2.0 * math.cos(alpha) * math.cos(beta) * math.cos(gamma),
        )
    )
    if min(a, b, c, sin_alpha, sin_beta, sin_gamma, volume_factor) <= 0:
        return math.inf
    volume = a * b * c * volume_factor
    astar = b * c * sin_alpha / volume
    bstar = a * c * sin_beta / volume
    cstar = a * b * sin_gamma / volume
    cos_alpha_star = (math.cos(beta) * math.cos(gamma) - math.cos(alpha)) / (sin_beta * sin_gamma)
    cos_beta_star = (math.cos(alpha) * math.cos(gamma) - math.cos(beta)) / (sin_alpha * sin_gamma)
    cos_gamma_star = (math.cos(alpha) * math.cos(beta) - math.cos(gamma)) / (sin_alpha * sin_beta)
    inv_d2 = (
        h * h * astar * astar
        + k * k * bstar * bstar
        + l * l * cstar * cstar
        + 2.0 * k * l * bstar * cstar * cos_alpha_star
        + 2.0 * h * l * astar * cstar * cos_beta_star
        + 2.0 * h * k * astar * bstar * cos_gamma_star
    )
    if inv_d2 <= 0:
        return math.inf
    return 1.0 / math.sqrt(inv_d2)

def reflection_sintheta_over_lambda(cell: gemmi.UnitCell, h: int, k: int, l: int) -> float:
    d = reflection_d_spacing(cell, h, k, l)
    if not math.isfinite(d) or d <= 0:
        return 0.0
    return 1.0 / (2.0 * d)

def _parse_triplet_translation(expr: str) -> float:
    text = re.sub(r"[+-]?(?:x|y|z)", "", str(expr or "").strip().lower().replace(" ", ""))
    if not text:
        return 0.0
    if text[0] not in "+-":
        text = "+" + text
    value = 0.0
    for sign, number in re.findall(r"([+-])(\d+(?:/\d+)?|\d*\.\d+)", text):
        if "/" in number:
            num, den = number.split("/", 1)
            term = float(num) / float(den)
        else:
            term = float(number)
        value += -term if sign == "-" else term
    return value

def direct_rotation_translation_from_triplet(triplet: str) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    rows: List[List[int]] = []
    translations: List[float] = []
    for expr in str(triplet or "").split(","):
        text = expr.strip().lower().replace(" ", "")
        coeffs = [0, 0, 0]
        for sign, axis in re.findall(r"([+-]?)(x|y|z)", text):
            idx = {"x": 0, "y": 1, "z": 2}[axis]
            coeffs[idx] += -1 if sign == "-" else 1
        rows.append(coeffs)
        translations.append(_parse_triplet_translation(text))
    if len(rows) != 3:
        return None
    matrix = np.asarray(rows, dtype=np.int64)
    det = round(float(np.linalg.det(matrix)))
    if abs(det) != 1:
        return None
    return matrix, np.asarray(translations, dtype=np.float64)

def direct_rotation_matrix_from_triplet(triplet: str) -> Optional[np.ndarray]:
    parsed = direct_rotation_translation_from_triplet(triplet)
    return None if parsed is None else parsed[0]

def transform_hkl_by_direct_rotation(rotation: np.ndarray, hkl: Tuple[int, int, int]) -> Tuple[int, int, int]:
    # Direct-space operation x' = R x transforms reciprocal indices as R^-T h.
    reciprocal = np.linalg.inv(np.asarray(rotation, dtype=np.float64)).T
    transformed = reciprocal @ np.asarray([int(hkl[0]), int(hkl[1]), int(hkl[2])], dtype=np.float64)
    rounded = np.rint(transformed).astype(int)
    return int(rounded[0]), int(rounded[1]), int(rounded[2])

def apply_symmetry_to_hkl(op: gemmi.Op, hkl: Tuple[int, int, int]) -> Optional[Tuple[int, int, int]]:
    h, k, l = hkl
    for attr in ("apply_to_hkl", "apply_to_miller"):
        fn = getattr(op, attr, None)
        if fn is None:
            continue
        try:
            out = fn([int(h), int(k), int(l)])
            return int(out[0]), int(out[1]), int(out[2])
        except Exception:
            pass
    try:
        rotation = direct_rotation_matrix_from_triplet(op.triplet())
        if rotation is not None:
            return transform_hkl_by_direct_rotation(rotation, hkl)
    except Exception:
        pass
    return None

def is_systematically_absent_hkl(hkl: Tuple[int, int, int], sg: gemmi.SpaceGroup) -> bool:
    try:
        ops = full_spacegroup_ops(sg)
    except Exception:
        ops = []
    for op in ops:
        try:
            transformed = apply_symmetry_to_hkl(op, hkl)
            if transformed != hkl:
                continue
            parsed = direct_rotation_translation_from_triplet(op.triplet())
            if parsed is None:
                continue
            _rotation, translation = parsed
            phase = int(hkl[0]) * float(translation[0]) + int(hkl[1]) * float(translation[1]) + int(hkl[2]) * float(translation[2])
            if abs(phase - round(phase)) > 1e-6:
                return True
        except Exception:
            continue
    return False

def reciprocal_metric_tensor(cell: gemmi.UnitCell) -> np.ndarray:
    alpha = math.radians(float(cell.alpha))
    beta = math.radians(float(cell.beta))
    gamma = math.radians(float(cell.gamma))
    direct = np.asarray(
        [
            [cell.a * cell.a, cell.a * cell.b * math.cos(gamma), cell.a * cell.c * math.cos(beta)],
            [cell.a * cell.b * math.cos(gamma), cell.b * cell.b, cell.b * cell.c * math.cos(alpha)],
            [cell.a * cell.c * math.cos(beta), cell.b * cell.c * math.cos(alpha), cell.c * cell.c],
        ],
        dtype=np.float64,
    )
    return np.linalg.inv(direct)

def hkl_q2_from_metric(gstar: np.ndarray, h: int, k: int, l: int) -> float:
    return (
        float(gstar[0, 0]) * h * h
        + 2.0 * float(gstar[0, 1]) * h * k
        + 2.0 * float(gstar[0, 2]) * h * l
        + float(gstar[1, 1]) * k * k
        + 2.0 * float(gstar[1, 2]) * k * l
        + float(gstar[2, 2]) * l * l
    )

def sintheta_over_lambda_from_metric(gstar: np.ndarray, h: int, k: int, l: int) -> float:
    q2 = hkl_q2_from_metric(gstar, h, k, l)
    return 0.5 * math.sqrt(q2) if q2 > 0.0 and math.isfinite(q2) else math.nan

def hkl_stl_array_from_metric(gstar: np.ndarray, hkls: np.ndarray) -> np.ndarray:
    arr = np.asarray(hkls, dtype=np.float64)
    if arr.size == 0:
        return np.asarray([], dtype=np.float64)
    h = arr[:, 0]
    k = arr[:, 1]
    l = arr[:, 2]
    q2 = (
        float(gstar[0, 0]) * h * h
        + 2.0 * float(gstar[0, 1]) * h * k
        + 2.0 * float(gstar[0, 2]) * h * l
        + float(gstar[1, 1]) * k * k
        + 2.0 * float(gstar[1, 2]) * k * l
        + float(gstar[2, 2]) * l * l
    )
    stl = np.full(q2.shape, np.nan, dtype=np.float64)
    valid = np.isfinite(q2) & (q2 > 0.0)
    stl[valid] = 0.5 * np.sqrt(q2[valid])
    return stl

def hkl_symmetry_cache(sg: Optional[gemmi.SpaceGroup]) -> Tuple[List[Tuple[Tuple[int, int, int], Tuple[int, int, int], Tuple[int, int, int]]], List[Tuple[Tuple[int, int, int], Tuple[float, float, float]]]]:
    matrices: List[Tuple[Tuple[int, int, int], Tuple[int, int, int], Tuple[int, int, int]]] = [
        ((1, 0, 0), (0, 1, 0), (0, 0, 1))
    ]
    absence_ops: List[Tuple[Tuple[Tuple[int, int, int], Tuple[int, int, int], Tuple[int, int, int]], Tuple[float, float, float]]] = []
    if sg is None:
        return matrices, absence_ops
    seen = {matrices[0]}
    try:
        ops = full_spacegroup_ops(sg)
    except Exception:
        ops = []
    for op in ops:
        parsed = direct_rotation_translation_from_triplet(op.triplet())
        if parsed is None:
            continue
        direct_rotation, translation = parsed
        try:
            reciprocal = np.linalg.inv(np.asarray(direct_rotation, dtype=np.float64)).T
        except Exception:
            continue
        rounded = np.rint(reciprocal).astype(int)
        if not np.allclose(reciprocal, rounded, atol=1e-8):
            continue
        matrix = tuple(tuple(int(v) for v in row) for row in rounded.tolist())  # type: ignore[assignment]
        if matrix not in seen:
            matrices.append(matrix)
            seen.add(matrix)
        absence_ops.append((matrix, (float(translation[0]), float(translation[1]), float(translation[2]))))
    return matrices, absence_ops

def apply_hkl_matrix(
    matrix: Tuple[Tuple[int, int, int], Tuple[int, int, int], Tuple[int, int, int]],
    h: int,
    k: int,
    l: int,
) -> Tuple[int, int, int]:
    return (
        matrix[0][0] * h + matrix[0][1] * k + matrix[0][2] * l,
        matrix[1][0] * h + matrix[1][1] * k + matrix[1][2] * l,
        matrix[2][0] * h + matrix[2][1] * k + matrix[2][2] * l,
    )

def is_systematically_absent_hkl_cached(
    h: int,
    k: int,
    l: int,
    absence_ops: Sequence[Tuple[Tuple[Tuple[int, int, int], Tuple[int, int, int], Tuple[int, int, int]], Tuple[float, float, float]]],
) -> bool:
    for matrix, translation in absence_ops:
        if apply_hkl_matrix(matrix, h, k, l) != (h, k, l):
            continue
        phase = h * translation[0] + k * translation[1] + l * translation[2]
        if abs(phase - round(phase)) > 1e-6:
            return True
    return False

def canonical_hkl_cached(
    h: int,
    k: int,
    l: int,
    matrices: Sequence[Tuple[Tuple[int, int, int], Tuple[int, int, int], Tuple[int, int, int]]],
) -> Tuple[int, int, int]:
    best = (int(h), int(k), int(l))
    inverted = (-best[0], -best[1], -best[2])
    if inverted < best:
        best = inverted
    for matrix in matrices:
        transformed = apply_hkl_matrix(matrix, h, k, l)
        if transformed < best:
            best = transformed
        inverted = (-transformed[0], -transformed[1], -transformed[2])
        if inverted < best:
            best = inverted
    return best

def canonical_hkl(hkl: Tuple[int, int, int], sg: Optional[gemmi.SpaceGroup] = None) -> Tuple[int, int, int]:
    equivalents = [tuple(int(x) for x in hkl), tuple(-int(x) for x in hkl)]
    if sg is not None:
        try:
            for op in full_spacegroup_ops(sg):
                transformed = apply_symmetry_to_hkl(op, hkl)
                if transformed is None:
                    continue
                equivalents.append(transformed)
                equivalents.append(tuple(-int(x) for x in transformed))
        except Exception:
            pass
    return min(equivalents)

def reflection_signal_to_noise(r: Reflection, data_mode: str) -> Optional[float]:
    if r.sigma is None:
        return None
    sigma = float(r.sigma)
    value = float(r.value)
    if sigma <= 0 or not math.isfinite(sigma) or not math.isfinite(value):
        return None
    if reflection_mode_is_amplitude(data_mode):
        amplitude = abs(value)
        if amplitude <= 0:
            return 0.0
        if reflection_mode_has_fwhm(data_mode):
            # The factor of 2 below propagates a genuine sigma(F) into an
            # intensity-domain uncertainty (I=F^2 => dI=2F.dF); FWHM is not an
            # uncertainty, so that propagation does not apply -- use F/FWHM directly.
            return amplitude / sigma
        return amplitude / (2.0 * sigma)
    return value / sigma

def reflection_amplitude_signal_to_noise(r: Reflection) -> Optional[float]:
    if r.sigma is None:
        return None
    sigma = float(r.sigma)
    value = float(r.value)
    if sigma <= 0 or not math.isfinite(sigma) or not math.isfinite(value):
        return None
    return value / sigma

def reflection_value_label(data_mode: str) -> str:
    if reflection_mode_is_amplitude(data_mode):
        return "Fobs"
    return "Iobs"

def reflection_sigma_label(data_mode: str) -> str:
    if reflection_mode_has_fwhm(data_mode):
        return "FWHM"
    return "σ(F)" if reflection_mode_is_amplitude(data_mode) else "σ(I)"

def reflection_primary_snr_label(data_mode: str) -> str:
    # FWHM is a peak-shape width, not an uncertainty (see
    # reflection_mode_has_fwhm's own docstring warning), so this ratio is
    # never a true signal-to-noise figure -- but it must at least name the
    # correct numerator: F/FWHM for amplitude data, I/FWHM for intensity
    # data (see reflection_signal_to_noise()'s amplitude branch, which
    # divides |F| by FWHM directly, never converting to the intensity
    # domain the way the non-FWHM amplitude branch below does).
    if reflection_mode_has_fwhm(data_mode):
        return "F/FWHM" if reflection_mode_is_amplitude(data_mode) else "I/FWHM"
    return "I/σ(I)"

def reflection_primary_signal_to_noise(r: Reflection, data_mode: str) -> Optional[float]:
    return reflection_signal_to_noise(r, data_mode)

def format_resolution_d(value: Optional[float], digits: int = 5) -> str:
    if value is None or not math.isfinite(float(value)) or float(value) <= 0:
        return "n/a"
    return f"{float(value):.{digits}g} A"

def referencefile_mode_for_path(reference_path: Optional[Path]) -> str:
    if reference_path is None:
        return "omit"
    suffix = reference_path.suffix.lower()
    if suffix in REFERENCE_STRUCTURE_SUFFIXES:
        return "reference_cif"
    if suffix in REFERENCE_DENSITY_SUFFIXES:
        return "reference_density"
    return "reference_density"

def theoretical_unique_hkl_stl_from_observed(
    reflections: Sequence[Reflection],
    cell: gemmi.UnitCell,
    sg: gemmi.SpaceGroup,
    d_min: float,
) -> Dict[Tuple[int, int, int], float]:
    if not reflections or not math.isfinite(d_min) or d_min <= 0:
        return {}
    gstar = reciprocal_metric_tensor(cell)
    try:
        miller = gemmi.make_miller_array(cell, sg, float(d_min), 0.0, True)
        miller = np.asarray(miller, dtype=np.int32)
        stls = hkl_stl_array_from_metric(gstar, miller)
        return {
            (int(row[0]), int(row[1]), int(row[2])): float(stl)
            for row, stl in zip(miller, stls)
            if math.isfinite(float(stl)) and float(stl) > 0.0
        }
    except Exception:
        pass
    qmax = 1.0 / (float(d_min) * float(d_min))
    hmax = int(math.ceil(float(cell.a) / float(d_min))) + 1
    kmax = int(math.ceil(float(cell.b) / float(d_min))) + 1
    matrices, absence_ops = hkl_symmetry_cache(sg)
    unique_stl: Dict[Tuple[int, int, int], float] = {}
    g00, g01, g02 = float(gstar[0, 0]), float(gstar[0, 1]), float(gstar[0, 2])
    g11, g12, g22 = float(gstar[1, 1]), float(gstar[1, 2]), float(gstar[2, 2])
    for h in range(-hmax, hmax + 1):
        h2 = h * h
        for k in range(-kmax, kmax + 1):
            base = g00 * h2 + 2.0 * g01 * h * k + g11 * k * k - qmax
            linear_l = 2.0 * (g02 * h + g12 * k)
            disc = linear_l * linear_l - 4.0 * g22 * base
            if disc < -1e-12:
                continue
            root = math.sqrt(max(0.0, disc))
            lo_l = int(math.ceil((-linear_l - root) / (2.0 * g22) - 1e-10))
            hi_l = int(math.floor((-linear_l + root) / (2.0 * g22) + 1e-10))
            for l in range(lo_l, hi_l + 1):
                if (h, k, l) == (0, 0, 0):
                    continue
                q2 = g00 * h2 + 2.0 * g01 * h * k + 2.0 * g02 * h * l + g11 * k * k + 2.0 * g12 * k * l + g22 * l * l
                if q2 <= 0.0 or q2 > qmax + 1e-9:
                    continue
                if is_systematically_absent_hkl_cached(h, k, l, absence_ops):
                    continue
                key = canonical_hkl_cached(h, k, l, matrices)
                stl = 0.5 * math.sqrt(q2)
                previous = unique_stl.get(key)
                if previous is None or stl < previous:
                    unique_stl[key] = stl
    return unique_stl

def theoretical_unique_hkls_from_observed(
    reflections: Sequence[Reflection],
    cell: gemmi.UnitCell,
    sg: gemmi.SpaceGroup,
    d_min: float,
) -> List[Tuple[int, int, int]]:
    return list(theoretical_unique_hkl_stl_from_observed(reflections, cell, sg, d_min).keys())

def analyze_hkl_data(
    hkl_path: Path,
    data_mode: str,
    cell: gemmi.UnitCell,
    sg: gemmi.SpaceGroup,
    sg_hm: str,
    source_note: str = "",
    bin_count: int = 12,
) -> HklAnalysis:
    mode = normalize_reflection_data_mode(data_mode)
    value_col, sigma_col, include_000 = reflection_columns_for_mode(mode)
    raw = read_hkl(hkl_path, value_col=value_col, sigma_col=sigma_col, include_000=include_000)
    unique = merge_duplicate_reflections(raw)
    gstar = reciprocal_metric_tensor(cell)
    unique_hkls = np.asarray([[int(r.h), int(r.k), int(r.l)] for r in unique], dtype=np.int32)
    unique_stls = hkl_stl_array_from_metric(gstar, unique_hkls)
    nonzero = np.any(unique_hkls != 0, axis=1) if unique_hkls.size else np.asarray([], dtype=bool)
    valid_stl = np.isfinite(unique_stls) & (unique_stls > 0.0) & nonzero
    ds = (1.0 / (2.0 * unique_stls[valid_stl])).astype(np.float64) if np.any(valid_stl) else np.asarray([], dtype=np.float64)
    if ds.size == 0:
        raise ValueError("No non-zero HKL reflections with finite d-spacing were found.")
    d_min = float(np.min(ds))
    theory_stl_by_key = theoretical_unique_hkl_stl_from_observed(unique, cell, sg, d_min)
    observed_asu = np.array(unique_hkls, copy=True)
    try:
        sg.switch_to_asu(observed_asu)
        observed_keys = [(int(row[0]), int(row[1]), int(row[2])) for row in observed_asu]
    except Exception:
        matrices, _absence_ops = hkl_symmetry_cache(sg)
        observed_keys = [canonical_hkl_cached(int(r.h), int(r.k), int(r.l), matrices) for r in unique]
    observed_records = [
        (key, float(stl), reflection_primary_signal_to_noise(r, mode))
        for key, stl, r in zip(observed_keys, unique_stls, unique)
    ]
    observed_records = [(key, stl, ios) for key, stl, ios in observed_records if math.isfinite(stl) and stl > 0]
    max_stl = max([stl for _, stl, _ in observed_records] or [0.0])
    if max_stl <= 0:
        raise ValueError("Could not calculate sin(theta)/lambda values for the HKL data.")
    bins: List[Dict[str, float]] = []
    edges = np.linspace(0.0, max_stl, max(2, int(bin_count)) + 1)
    bin_total = len(edges) - 1
    theory_counts = np.zeros(bin_total, dtype=np.int64)
    observed_counts = np.zeros(bin_total, dtype=np.int64)
    signal_sums = np.zeros(bin_total, dtype=np.float64)
    signal_counts = np.zeros(bin_total, dtype=np.int64)
    theory_stls = np.asarray([stl for stl in theory_stl_by_key.values() if math.isfinite(float(stl)) and float(stl) > 0], dtype=np.float64)
    if theory_stls.size:
        theory_bin_indices = np.searchsorted(edges, theory_stls, side="left") - 1
        theory_bin_indices = np.clip(theory_bin_indices, 0, bin_total - 1)
        theory_counts += np.bincount(theory_bin_indices, minlength=bin_total)[:bin_total]
    observed_stl_by_key: Dict[Tuple[int, int, int], float] = {}
    for key, stl, _ios in observed_records:
        if key in theory_stl_by_key:
            observed_stl_by_key[key] = min(stl, observed_stl_by_key.get(key, stl))
    observed_theory_stls = np.asarray([stl for stl in observed_stl_by_key.values() if math.isfinite(float(stl)) and float(stl) > 0], dtype=np.float64)
    if observed_theory_stls.size:
        observed_bin_indices = np.searchsorted(edges, observed_theory_stls, side="left") - 1
        observed_bin_indices = np.clip(observed_bin_indices, 0, bin_total - 1)
        observed_counts += np.bincount(observed_bin_indices, minlength=bin_total)[:bin_total]
    for _key, stl, ios in observed_records:
        if ios is None or not math.isfinite(float(ios)):
            continue
        bin_idx = int(np.searchsorted(edges, float(stl), side="left") - 1)
        if 0 <= bin_idx < bin_total:
            signal_sums[bin_idx] += float(ios)
            signal_counts[bin_idx] += 1
    for idx in range(bin_total):
        lo = float(edges[idx])
        hi = float(edges[idx + 1])
        completeness = 100.0 * float(observed_counts[idx]) / float(theory_counts[idx]) if theory_counts[idx] else 0.0
        mean_signal = float(signal_sums[idx] / signal_counts[idx]) if signal_counts[idx] else math.nan
        bins.append(
            {
                "lo": lo,
                "hi": hi,
                "center": 0.5 * (lo + hi),
                "theory": float(theory_counts[idx]),
                "observed": float(observed_counts[idx]),
                "completeness": completeness,
                "mean_i_over_sigma": mean_signal,
                "mean_signal_to_noise": mean_signal,
            }
        )
    theory_sorted = sorted((stl, key) for key, stl in theory_stl_by_key.items())
    d_full_98: Optional[float] = None
    theory_idx = 0
    theory_cum_count = 0
    observed_cum_count = 0
    while theory_idx < len(theory_sorted):
        edge = float(theory_sorted[theory_idx][0])
        while theory_idx < len(theory_sorted) and theory_sorted[theory_idx][0] <= edge + 1e-12:
            key = theory_sorted[theory_idx][1]
            theory_cum_count += 1
            observed_stl = observed_stl_by_key.get(key)
            if observed_stl is not None and observed_stl <= edge + 1e-12:
                observed_cum_count += 1
            theory_idx += 1
        if theory_cum_count and 100.0 * observed_cum_count / theory_cum_count >= 98.0:
            d_full_98 = 1.0 / (2.0 * edge) if edge > 0 else None
    return HklAnalysis(
        hkl_path=Path(hkl_path),
        data_mode=mode,
        cell=cell,
        spacegroup=sg,
        spacegroup_hm=sg_hm,
        reflections_raw=raw,
        reflections_unique=unique,
        d_min=d_min,
        d_full_98=d_full_98,
        bins=bins,
        source_note=source_note,
    )

def _phase_studio_float7(value: float) -> str:
    try:
        x = float(value)
        if not math.isfinite(x):
            x = 0.0
    except Exception:
        x = 0.0
    return f"{x:.7f}"


def calculate_superflip_dataitemwidths(records: Sequence[Tuple[int, int, int, float, float, float]]) -> Tuple[int, int, int]:
    """Return safe dataitemwidths for the exact Jana/Superflip fbegin records.

    Superflip's legacy fixed-width reader is sensitive to negative indices.
    Therefore the h/k/l field width is chosen large enough to keep at least
    one leading character before the longest signed index.  The floating-item
    width is chosen from the actual decimal strings that will be written.
    """
    if not records:
        return 4, 14, 14
    max_index_len = 1
    max_float_len = 1
    for h, k, l, value, phase, sigma in records:
        max_index_len = max(max_index_len, len(str(int(h))), len(str(int(k))), len(str(int(l))))
        max_float_len = max(
            max_float_len,
            len(_phase_studio_float7(value)),
            len(_phase_studio_float7(phase)),
            len(_phase_studio_float7(sigma)),
        )
    hkl_width = max(4, max_index_len + 1)
    item_width = max(14, max_float_len + 1)
    return hkl_width, item_width, item_width


def format_superflip_fixed_reflection(
    h: int,
    k: int,
    l: int,
    value: float,
    phase: float,
    sigma: float,
    widths: Tuple[int, int, int],
) -> str:
    hkl_width, value_width, sigma_width = widths
    # Use the same width for phase as for sigma; this matches the traditional
    # Jana/Superflip Fobs/phase/sigma layout while still allowing the width to
    # grow automatically for large values.
    phase_width = sigma_width
    return (
        f"{int(h):{hkl_width}d}"
        f"{int(k):{hkl_width}d}"
        f"{int(l):{hkl_width}d}"
        f"{float(value):{value_width}.7f}"
        f"{float(phase):{phase_width}.7f}"
        f"{float(sigma):{sigma_width}.7f}"
    )


def _passes_reflection_filters(
    r: Reflection,
    i_over_sigma_min: float,
    cell: Optional[gemmi.UnitCell],
    resolution_d_min: float,
) -> bool:
    if i_over_sigma_min > 0 and r.sigma is not None and r.sigma > 0:
        if float(r.value) / float(r.sigma) < i_over_sigma_min:
            return False
    d_min = max(0.0, float(resolution_d_min or 0.0))
    if d_min > 0 and cell is not None and reflection_d_spacing(cell, int(r.h), int(r.k), int(r.l)) < d_min:
        return False
    return True


def infer_dataitemwidths_from_hkl(hkl_path: Path, fallback: str = "4 14 14") -> str:
    """Infer Superflip dataitemwidths from the exact records to be copied into fbegin."""
    try:
        lines = Path(hkl_path).read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return fallback

    # Prefer the explicit Phase Studio header written by write_observed_reflections().
    for raw in lines[:20]:
        low = raw.lower()
        if "phase studio auto dataitemwidths:" in low:
            tail = raw.split(":", 1)[1].strip()
            parts = tail.split()
            if len(parts) >= 3 and all(part.lstrip("+-").isdigit() for part in parts[:3]):
                return " ".join(parts[:3])

    records: List[Tuple[int, int, int, float, float, float]] = []
    for raw in lines:
        if not raw.strip() or raw.lstrip().startswith(COMMENT_PREFIXES):
            continue
        parts = raw.split()
        if len(parts) < 4:
            continue
        try:
            h = int(float(parts[0]))
            k = int(float(parts[1]))
            l = int(float(parts[2]))
            value = float(parts[3])
            phase = float(parts[4]) if len(parts) >= 5 else 0.0
            sigma = float(parts[5]) if len(parts) >= 6 else 0.0
            records.append((h, k, l, value, phase, sigma))
        except Exception:
            continue
    if not records:
        return fallback
    return " ".join(str(x) for x in calculate_superflip_dataitemwidths(records))


def write_observed_reflections(out_hkl: Path, reflections: Sequence[Reflection], i_over_sigma_min: float = 0.0, data_mode: str = REFLECTION_DATA_MODE_INTENSITY, cell: Optional[gemmi.UnitCell] = None, resolution_d_min: float = 0.0) -> int:
    out_hkl.parent.mkdir(parents=True, exist_ok=True)
    mode = normalize_reflection_data_mode(data_mode)
    filtered = [
        r for r in reflections
        if _passes_reflection_filters(r, i_over_sigma_min, cell, resolution_d_min)
    ]
    with out_hkl.open("w", encoding="utf-8") as f:
        quantity = "Fobs" if reflection_mode_is_amplitude(mode) else "Iobs"
        sigma_name = "sigma(Fobs)" if reflection_mode_is_amplitude(mode) else "sigma(Iobs)"
        if reflection_mode_has_phase(mode):
            f.write(f"# h k l {quantity} phase(deg) {sigma_name}\n")
            f.write("# Phase is converted from degrees to turns for Superflip; sigma is ignored by Superflip.\n")
        else:
            f.write(f"# h k l {quantity} {sigma_name}\n")
            f.write("# Sigma is retained by Phase Studio and ignored by Superflip.\n")
        n = 0
        for r in filtered:
            value = max(0.0, float(r.value))
            sigma = 0.0 if r.sigma is None else max(0.0, float(r.sigma))
            if reflection_mode_has_phase(mode):
                phase_turns = (0.0 if r.phase is None else float(r.phase)) / 360.0
                f.write(f"{r.h:5d} {r.k:5d} {r.l:5d} {value:14.7f} {phase_turns:14.9f} {sigma:14.7f}\n")
            else:
                f.write(f"{r.h:5d} {r.k:5d} {r.l:5d} {value:14.7f} {sigma:14.7f}\n")
            n += 1
    return n

def write_standardized_hkl_with_phase(
    out_hkl: Path, reflections: Sequence[Reflection], i_over_sigma_min: float = 0.0,
    data_mode: str = REFLECTION_DATA_MODE_INTENSITY, cell: Optional[gemmi.UnitCell] = None,
    resolution_d_min: float = 0.0, calc_by_hkl: Optional[Dict[Tuple[int, int, int], Tuple[float, float]]] = None,
) -> int:
    """calc_by_hkl, when given, maps (h, k, l) -> (F_squared_calc, phase_calc_deg) read by
    FFT from a reconstructed XPLOR map (see xplor_fft_predictions); its phase is written
    instead of the reflection's own phase field, which is only ever the value supplied by
    the selected HKL mode (0.0 for most modes) and never reflects the reconstruction."""
    out_hkl.parent.mkdir(parents=True, exist_ok=True)
    mode = normalize_reflection_data_mode(data_mode)
    d_min = max(0.0, float(resolution_d_min or 0.0))
    n = 0
    with out_hkl.open("w", encoding="utf-8") as f:
        f.write("# h k l I sigma(I) phase(deg)\n")
        phase_note = "phase is calculated by FFT from the reconstructed map" if calc_by_hkl else "phase is 0.0 unless supplied by the selected HKL mode"
        f.write(f"# Phase Studio {__version__} standardized HKL export; {phase_note}.\n")
        for r in reflections:
            if i_over_sigma_min > 0 and r.sigma is not None and r.sigma > 0:
                if float(r.value) / float(r.sigma) < i_over_sigma_min:
                    continue
            if d_min > 0 and cell is not None and reflection_d_spacing(cell, int(r.h), int(r.k), int(r.l)) < d_min:
                continue
            value = max(0.0, float(r.value))
            if not reflection_mode_is_amplitude(mode):
                intensity = value
                sigma_i = 0.0 if r.sigma is None else max(0.0, float(r.sigma))
            else:
                intensity = value * value
                sigma_f = 0.0 if r.sigma is None else max(0.0, float(r.sigma))
                sigma_i = 2.0 * value * sigma_f
            calc = calc_by_hkl.get((int(r.h), int(r.k), int(r.l))) if calc_by_hkl else None
            phase = float(calc[1]) if calc is not None else (0.0 if r.phase is None else float(r.phase))
            f.write(f"{r.h:5d} {r.k:5d} {r.l:5d} {intensity:14.7f} {sigma_i:14.7f} {phase:12.6f}\n")
            n += 1
    return n

def write_shelx_fcf(
    out_fcf: Path, reflections: Sequence[Reflection], i_over_sigma_min: float = 0.0,
    data_mode: str = REFLECTION_DATA_MODE_INTENSITY, cell: Optional[gemmi.UnitCell] = None,
    resolution_d_min: float = 0.0, calc_by_hkl: Optional[Dict[Tuple[int, int, int], Tuple[float, float]]] = None,
) -> int:
    """ShelX/Jana-compatible .fcf reflection list (CIF loop, list format 4: h k l
    F_squared_meas sigma F_squared_calc phase_calc). calc_by_hkl, when given, maps
    (h, k, l) -> (F_squared_calc, phase_calc_deg) read by FFT from a reconstructed XPLOR
    map (see xplor_fft_predictions); without it, F_squared_calc is written equal to
    F_squared_meas and phase_calc to 0 as neutral placeholders (no reconstruction available)."""
    out_fcf.parent.mkdir(parents=True, exist_ok=True)
    mode = normalize_reflection_data_mode(data_mode)
    d_min = max(0.0, float(resolution_d_min or 0.0))
    n = 0
    with out_fcf.open("w", encoding="utf-8") as f:
        f.write(f"# Phase Studio {__version__} ShelX-compatible FCF export (list format 4).\n")
        if calc_by_hkl:
            f.write("# F_squared_calc and phase_calc are read by FFT from the reconstructed map.\n")
        else:
            f.write("# F_squared_calc is written equal to F_squared_meas and phase_calc to 0.0 as placeholders (no reconstruction available).\n")
        f.write("loop_\n")
        for tag in ("_refln_index_h", "_refln_index_k", "_refln_index_l", "_refln_F_squared_meas",
                    "_refln_F_squared_sigma", "_refln_F_squared_calc", "_refln_phase_calc"):
            f.write(f"{tag}\n")
        for r in reflections:
            if i_over_sigma_min > 0 and r.sigma is not None and r.sigma > 0:
                if float(r.value) / float(r.sigma) < i_over_sigma_min:
                    continue
            if d_min > 0 and cell is not None and reflection_d_spacing(cell, int(r.h), int(r.k), int(r.l)) < d_min:
                continue
            value = max(0.0, float(r.value))
            if not reflection_mode_is_amplitude(mode):
                intensity = value
                sigma_i = 0.0 if r.sigma is None else max(0.0, float(r.sigma))
            else:
                intensity = value * value
                sigma_f = 0.0 if r.sigma is None else max(0.0, float(r.sigma))
                sigma_i = 2.0 * value * sigma_f
            calc = calc_by_hkl.get((int(r.h), int(r.k), int(r.l))) if calc_by_hkl else None
            intensity_calc = float(calc[0]) if calc is not None else intensity
            phase = float(calc[1]) if calc is not None else 0.0
            f.write(f"{r.h:5d} {r.k:5d} {r.l:5d} {intensity:14.7f} {sigma_i:14.7f} {intensity_calc:14.7f} {phase:12.6f}\n")
            n += 1
    return n

def export_phased_reflections_from_map(
    map_export_format: str, out_path_base: Path, xplor_map: Path, reflections: Sequence[Reflection],
    i_over_sigma_min: float, data_mode: str, cell: gemmi.UnitCell, resolution_d_min: float,
    log: Callable[[str], None],
) -> Optional[Path]:
    """Map format's 'HKL reflections with phases' / 'ShelX (fcf)' options: read F_calc and
    phase_calc for every observed hkl by FFT from a just-reconstructed XPLOR map (the same
    technique the SharpED phase-recycling methods use), then write them alongside |Fobs|.
    Called once per Superflip map, exactly like the ccp4/jana extra-format options."""
    fmt = normalize_map_export_format(map_export_format)
    if fmt not in {"hkl_phases", "shelx_fcf"}:
        return None
    calc_by_hkl = xplor_fft_predictions(xplor_map, [(int(r.h), int(r.k), int(r.l)) for r in reflections])
    if fmt == "hkl_phases":
        out_path = out_path_base.with_name(out_path_base.name + "_phased.hkl")
        n = write_standardized_hkl_with_phase(out_path, reflections, i_over_sigma_min, data_mode, cell=cell, resolution_d_min=resolution_d_min, calc_by_hkl=calc_by_hkl)
        log(f"Phased HKL export (phases from {xplor_map.name}): {out_path} ({n} reflections)")
    else:
        out_path = out_path_base.with_name(out_path_base.name + ".fcf")
        n = write_shelx_fcf(out_path, reflections, i_over_sigma_min, data_mode, cell=cell, resolution_d_min=resolution_d_min, calc_by_hkl=calc_by_hkl)
        log(f"ShelX FCF export (phases from {xplor_map.name}): {out_path} ({n} reflections)")
    return out_path

def reflection_value_as_intensity(reflection: Reflection, data_mode: str) -> float:
    value = max(0.0, float(reflection.value))
    if reflection_mode_is_amplitude(data_mode):
        return value * value
    return value

def value_from_intensity(intensity: float, data_mode: str) -> float:
    intensity = max(0.0, float(intensity))
    if reflection_mode_is_amplitude(data_mode):
        return math.sqrt(intensity)
    return intensity

def estimate_sigma_for_reflection_value(reflections: Sequence[Reflection], value: float) -> Optional[float]:
    ratios: List[float] = []
    for r in reflections:
        if r.sigma is None:
            continue
        if r.value > 0 and r.sigma > 0:
            ratios.append(float(r.sigma) / float(r.value))
    if not ratios:
        return None
    return max(0.0, float(value) * float(np.median(np.asarray(ratios, dtype=np.float64))))

def xplor_fft_intensity_phase(xplor_map: Path, hkl: Tuple[int, int, int]) -> Tuple[float, float]:
    xmap = read_xplor_map(xplor_map)
    grid = tuple(int(v) for v in xmap.grid)
    nx, ny, nz = grid[0], grid[3], grid[6]
    data = np.asarray(xmap.data, dtype=np.float64).reshape((nz, ny, nx))
    coeffs = np.fft.fftn(data)
    h, k, l = hkl
    coeff = coeffs[int(l) % nz, int(k) % ny, int(h) % nx]
    intensity = float(abs(coeff) ** 2)
    phase = float(math.degrees(math.atan2(float(coeff.imag), float(coeff.real))))
    return intensity, phase

def xplor_fft_predictions(xplor_map: Path, hkls: Sequence[Tuple[int, int, int]]) -> Dict[Tuple[int, int, int], Tuple[float, float]]:
    xmap = read_xplor_map(xplor_map)
    grid = tuple(int(v) for v in xmap.grid)
    nx, ny, nz = grid[0], grid[3], grid[6]
    data = np.asarray(xmap.data, dtype=np.float64).reshape((nz, ny, nx))
    coeffs = np.fft.fftn(data)
    predictions: Dict[Tuple[int, int, int], Tuple[float, float]] = {}
    for h, k, l in hkls:
        coeff = coeffs[int(l) % nz, int(k) % ny, int(h) % nx]
        predictions[(int(h), int(k), int(l))] = (
            float(abs(coeff) ** 2),
            float(math.degrees(math.atan2(float(coeff.imag), float(coeff.real)))),
        )
    return predictions

def synthesize_xplor_map_from_phases(
    reflections: Sequence[Reflection],
    data_mode: str,
    grid: Tuple[int, int, int, int, int, int, int, int, int],
    cell: Tuple[float, float, float, float, float, float],
    axis_order: str,
    phases_by_hkl: Dict[Tuple[int, int, int], float],
    title: str,
    spacegroup: gemmi.SpaceGroup,
) -> Tuple[XplorMap, int]:
    """Fourier-synthesize a real map from |Fobs| (derived from `reflections`) combined
    with phases (degrees) from `phases_by_hkl`, for hkl present in both. Each measured
    hkl is expanded to every space-group-symmetry-equivalent reciprocal-lattice point
    (matching amplitude, phase-shifted per the operation) -- leaving only the measured
    asymmetric-unit point non-zero would discard most of the true signal and produce a
    heavily smeared map. Everything outside that expanded set is zero. Any Friedel mate
    still missing afterwards (non-centrosymmetric space groups) is filled by Hermitian
    symmetry so the resulting map is real."""
    nx, ny, nz = int(grid[0]), int(grid[3]), int(grid[6])
    coeffs = np.zeros((nz, ny, nx), dtype=np.complex128)
    direct: set = set()
    ops = full_spacegroup_ops(spacegroup) or [gemmi.Op("x,y,z")]
    used = 0
    for r in reflections:
        h, k, l = int(r.h), int(r.k), int(r.l)
        phase_deg = phases_by_hkl.get((h, k, l))
        if phase_deg is None:
            continue
        amplitude = math.sqrt(reflection_value_as_intensity(r, data_mode))
        if amplitude <= 0:
            continue
        base_phase = math.radians(float(phase_deg))
        for op in ops:
            eh, ek, el = op.apply_to_hkl((h, k, l))
            phase = base_phase + op.phase_shift((h, k, l))
            index = (int(el) % nz, int(ek) % ny, int(eh) % nx)
            coeffs[index] = complex(amplitude * math.cos(phase), amplitude * math.sin(phase))
            direct.add(index)
        used += 1
    for lz, ky, hx in list(direct):
        mate = ((-lz) % nz, (-ky) % ny, (-hx) % nx)
        if mate not in direct:
            coeffs[mate] = np.conj(coeffs[lz, ky, hx])
    data = np.fft.ifftn(coeffs).real
    return XplorMap(
        title=title,
        grid=tuple(int(v) for v in grid),
        cell=tuple(float(v) for v in cell),
        axis_order=axis_order or "ZYX",
        data=data.reshape(-1),
    ), used

def compose_fobs_phicalc_map(
    output_path: Path,
    reflections: Sequence[Reflection],
    data_mode: str,
    deblurred_map: Path,
    title: str,
    spacegroup: gemmi.SpaceGroup,
    log: Callable[[str], None],
) -> Path:
    """Recompose a map from the observed |Fobs| and phi_calc read (by FFT) from the
    supplied deblurred map, for every measured hkl. This is the map handed to
    SharpED in the next recycling cycle."""
    xmap = read_xplor_map(deblurred_map)
    hkls = [(int(r.h), int(r.k), int(r.l)) for r in reflections]
    predictions = xplor_fft_predictions(deblurred_map, hkls)
    phases_by_hkl = {hkl: phase for hkl, (_intensity, phase) in predictions.items()}
    new_xmap, used = synthesize_xplor_map_from_phases(
        reflections, data_mode, xmap.grid, xmap.cell, xmap.axis_order, phases_by_hkl, title, spacegroup
    )
    write_xplor_map(output_path, new_xmap)
    log(f"[Fobs+phi_calc] {used}/{len(reflections)} observed hkl used from {deblurred_map.name} -> {output_path.name}")
    return output_path

def compose_random_phase_map(
    output_path: Path,
    reflections: Sequence[Reflection],
    data_mode: str,
    cell: gemmi.UnitCell,
    spacegroup: gemmi.SpaceGroup,
    randomseed: str,
    title: str,
    log: Callable[[str], None],
) -> Path:
    """Extreme variant of the first recycling cycle: skip Superflip entirely and
    synthesize a map straight from |Fobs| with independent random phases."""
    nx, ny, nz = superflip_default_voxel_triplet(cell, 0.2)
    grid = (nx, 0, nx - 1, ny, 0, ny - 1, nz, 0, nz - 1)
    cell_tuple = (cell.a, cell.b, cell.c, cell.alpha, cell.beta, cell.gamma)
    seed_text = str(randomseed or "").strip()
    rng = np.random.default_rng(int(seed_text)) if seed_text.isdigit() else np.random.default_rng()
    phases_by_hkl = {
        (int(r.h), int(r.k), int(r.l)): float(rng.uniform(0.0, 360.0)) for r in reflections
    }
    new_xmap, used = synthesize_xplor_map_from_phases(
        reflections, data_mode, grid, cell_tuple, "ZYX", phases_by_hkl, title, spacegroup
    )
    write_xplor_map(output_path, new_xmap)
    log(f"[Random start] {used}/{len(reflections)} observed hkl given independent random phases on a {nx}x{ny}x{nz} grid -> {output_path.name}")
    return output_path

def xplor_map_correlation(map_a: Path, map_b: Path) -> Optional[float]:
    """Pearson correlation between two XPLOR density grids, used as a cheap,
    reference-free convergence proxy for the SharpED phase-recycling cycle loop
    (no EDMA/reference structure required, unlike the other per-cycle metrics)."""
    try:
        a = read_xplor_map(map_a).data.ravel()
        b = read_xplor_map(map_b).data.ravel()
        if a.shape != b.shape or a.size == 0:
            return None
        if np.std(a) < 1e-12 or np.std(b) < 1e-12:
            return None
        return float(np.corrcoef(a, b)[0, 1])
    except Exception:
        return None

def select_omit_test_set(reflections: Sequence[Reflection], seed_text: str, fraction: float = 0.05) -> FrozenSet[Tuple[int, int, int]]:
    """Pick a fixed random subset of hkl (default 5%) to exclude from omit-map
    Superflip/SharpED runs and to evaluate R_free against. Seeded from Superflip's
    own Random seed when it is a plain integer, otherwise from a fixed constant, so
    the same test set is reused for every cycle of a run (comparable cycle to cycle)
    regardless of how many times it is (re)selected."""
    hkls = sorted({(int(r.h), int(r.k), int(r.l)) for r in reflections})
    if not hkls:
        return frozenset()
    seed_text = str(seed_text or "").strip()
    seed = int(seed_text) if seed_text.isdigit() else 987654321
    rng = np.random.default_rng(seed)
    count = max(1, round(len(hkls) * max(0.0, min(1.0, fraction))))
    chosen = rng.choice(len(hkls), size=min(count, len(hkls)), replace=False)
    return frozenset(hkls[i] for i in chosen.tolist())

def compute_rfree(reflections: Sequence[Reflection], test_hkls: FrozenSet[Tuple[int, int, int]], data_mode: str, predictions: Dict[Tuple[int, int, int], Tuple[float, float]]) -> Optional[float]:
    """Crystallographic R_free: sum(|Fobs - k*Fcalc|) / sum(|Fobs|) over only the
    excluded test-set reflections, with k the least-squares scale factor between
    them. Fcalc/phase_calc come from `predictions` (see xplor_fft_predictions),
    read from a map that never saw the test set during reconstruction."""
    fobs: List[float] = []
    fcalc: List[float] = []
    for r in reflections:
        hkl = (int(r.h), int(r.k), int(r.l))
        if hkl not in test_hkls:
            continue
        prediction = predictions.get(hkl)
        if prediction is None:
            continue
        fobs.append(math.sqrt(reflection_value_as_intensity(r, data_mode)))
        fcalc.append(math.sqrt(max(0.0, prediction[0])))
    if len(fobs) < 3:
        return None
    fobs_arr = np.asarray(fobs, dtype=np.float64)
    fcalc_arr = np.asarray(fcalc, dtype=np.float64)
    denom = float(np.sum(fcalc_arr * fcalc_arr))
    if denom <= 1e-12:
        return None
    k = float(np.sum(fobs_arr * fcalc_arr)) / denom
    fobs_sum = float(np.sum(fobs_arr))
    if fobs_sum <= 1e-12:
        return None
    return float(np.sum(np.abs(fobs_arr - k * fcalc_arr)) / fobs_sum)

def candidate_missing_hkls_from_bounds(reflections: Sequence[Reflection], cell: gemmi.UnitCell, resolution_d_min: float) -> List[Tuple[int, int, int]]:
    if not reflections:
        return []
    existing = {(int(r.h), int(r.k), int(r.l)) for r in reflections}
    hmax = max(abs(int(r.h)) for r in reflections)
    kmax = max(abs(int(r.k)) for r in reflections)
    lmax = max(abs(int(r.l)) for r in reflections)
    if resolution_d_min > 0:
        d_min = float(resolution_d_min)
    else:
        ds = [reflection_d_spacing(cell, int(r.h), int(r.k), int(r.l)) for r in reflections if not (r.h == 0 and r.k == 0 and r.l == 0)]
        d_min = min(ds) if ds else 0.0
    candidates: List[Tuple[int, int, int]] = []
    for h in range(-hmax, hmax + 1):
        for k in range(-kmax, kmax + 1):
            for l in range(-lmax, lmax + 1):
                key = (h, k, l)
                if key in existing or key == (0, 0, 0):
                    continue
                if d_min > 0 and reflection_d_spacing(cell, h, k, l) < d_min:
                    continue
                candidates.append(key)
    return candidates

def apply_map_feedback_to_reflections(
    reflections: Sequence[Reflection],
    data_mode: str,
    feedback_map: Path,
    cell: gemmi.UnitCell,
    resolution_d_min: float,
    add_missing: bool,
    missing_percent_limit: float,
    correct_intensities: bool,
    intensity_damping: float,
    intensity_max_i_over_sigma: float,
    log: Callable[[str], None],
) -> Tuple[List[Reflection], Optional[float]]:
    """Returns (updated_reflections, intensity_correction_avg_change_percent),
    the latter being the mean, across reflections actually corrected this
    call, of |after - before| / before * 100 -- i.e. the average percent
    change in intensity from map-based correction alone (add_missing
    reflections are new, not changed, so they never contribute) -- or None
    when correct_intensities is off or nothing was corrected."""
    mode = normalize_reflection_data_mode(data_mode)
    current = [Reflection(int(r.h), int(r.k), int(r.l), float(r.value), r.sigma, r.phase) for r in reflections]
    if not current:
        return current, None
    existing_keys = [(int(r.h), int(r.k), int(r.l)) for r in current]
    predictions = xplor_fft_predictions(feedback_map, existing_keys)
    ratios: List[float] = []
    for r in current:
        raw_i, _ = predictions.get((int(r.h), int(r.k), int(r.l)), (0.0, 0.0))
        obs_i = reflection_value_as_intensity(r, mode)
        if raw_i > 0 and obs_i > 0:
            ratios.append(obs_i / raw_i)
    scale = float(np.median(np.asarray(ratios, dtype=np.float64))) if ratios else 1.0
    corrected = 0
    damping = max(0.0, min(1.0, float(intensity_damping or 0.0)))
    max_i_over_sigma = max(0.0, float(intensity_max_i_over_sigma or 0.0))
    change_percentages: List[float] = []
    if correct_intensities and damping > 0:
        corrected_reflections: List[Reflection] = []
        for r in current:
            key = (int(r.h), int(r.k), int(r.l))
            raw_i, map_phase = predictions.get(key, (0.0, 0.0))
            if max_i_over_sigma > 0:
                if r.value <= 0 or r.sigma is None or r.sigma <= 0 or (float(r.value) / float(r.sigma)) >= max_i_over_sigma:
                    corrected_reflections.append(r)
                    continue
            if raw_i > 0:
                obs_i = reflection_value_as_intensity(r, mode)
                map_i = raw_i * scale
                new_i = (1.0 - damping) * obs_i + damping * map_i
                value = value_from_intensity(new_i, mode)
                phase = r.phase if r.phase is not None else (map_phase if reflection_mode_has_phase(mode) else None)
                corrected_reflections.append(Reflection(r.h, r.k, r.l, value, r.sigma, phase))
                corrected += 1
                if obs_i > 1e-12:
                    change_percentages.append(abs(new_i - obs_i) / obs_i * 100.0)
            else:
                corrected_reflections.append(r)
        current = corrected_reflections
    avg_change_percent = sum(change_percentages) / len(change_percentages) if change_percentages else None
    added = 0
    if add_missing and missing_percent_limit > 0:
        max_add = int(math.floor(len(current) * max(0.0, float(missing_percent_limit)) / 100.0))
        if max_add > 0:
            candidates = candidate_missing_hkls_from_bounds(current, cell, resolution_d_min)
            candidate_predictions = xplor_fft_predictions(feedback_map, candidates)
            ranked = sorted(candidate_predictions.items(), key=lambda item: item[1][0], reverse=True)
            existing = {(int(r.h), int(r.k), int(r.l)) for r in current}
            new_reflections = list(current)
            for key, (raw_i, phase) in ranked:
                if added >= max_add:
                    break
                if key in existing or raw_i <= 0:
                    continue
                intensity = raw_i * scale
                value = value_from_intensity(intensity, mode)
                sigma = estimate_sigma_for_reflection_value(current, value)
                new_reflections.append(Reflection(key[0], key[1], key[2], value, sigma, phase if reflection_mode_has_phase(mode) else None))
                existing.add(key)
                added += 1
            current = new_reflections
    log(
        "Map feedback: "
        f"scale={scale:.6g}, corrected={corrected}, added_missing={added}, "
        f"intensity_max_i_over_sigma={max_i_over_sigma:g}, reflections={len(current)}, "
        f"avg_intensity_change={'n/a' if avg_change_percent is None else f'{avg_change_percent:.2f}%'}"
    )
    return current, avg_change_percent

def bragg_two_theta_deg(d_value: float, wavelength: float) -> Optional[float]:
    """Bragg angle 2theta in degrees; None (not raised) for a reflection that is
    geometrically inaccessible at this wavelength, so one bad hkl does not abort
    overlap grouping for the rest of the data set."""
    if wavelength <= 0 or not math.isfinite(wavelength) or d_value <= 0 or not math.isfinite(d_value):
        return None
    argument = wavelength / (2.0 * d_value)
    if argument > 1.0 + 1e-9:
        return None
    return float(math.degrees(2.0 * math.asin(min(1.0, argument))))

def assign_powder_overlap_groups(
    reflections: Sequence[Reflection], cell: gemmi.UnitCell, wavelength: float, separation_factor: float,
) -> Dict[Tuple[int, int, int], int]:
    """Group reflections whose Bragg peaks overlap in a powder pattern: sorted by
    2theta, neighbors are joined transitively into the same group while
    delta(2theta) < separation_factor * (FWHM1 + FWHM2) / 2, matching Superflip's
    own fwhmseparation convention. FWHM is read from each reflection's sigma
    field (that is where the 'hkl I/F fwhm' data modes store it). A reflection
    with no FWHM value or an inaccessible 2theta is left ungrouped (group 0).
    Returns hkl -> group id, 0 meaning "not part of any overlap group"."""
    entries: List[Tuple[Tuple[int, int, int], float, float]] = []
    for r in reflections:
        if r.sigma is None:
            continue
        d_value = reflection_d_spacing(cell, int(r.h), int(r.k), int(r.l))
        angle = bragg_two_theta_deg(d_value, wavelength)
        if angle is None:
            continue
        entries.append(((int(r.h), int(r.k), int(r.l)), angle, max(0.0, float(r.sigma))))
    groups: Dict[Tuple[int, int, int], int] = {}
    if len(entries) < 2:
        return groups
    entries.sort(key=lambda item: item[1])
    group_id = 0
    current_component: List[Tuple[Tuple[int, int, int], float, float]] = [entries[0]]
    for previous, current in zip(entries, entries[1:]):
        delta = current[1] - previous[1]
        threshold = separation_factor * (previous[2] + current[2]) / 2.0
        if delta < threshold:
            current_component.append(current)
        else:
            if len(current_component) > 1:
                group_id += 1
                for key, _angle, _fwhm in current_component:
                    groups[key] = group_id
            current_component = [current]
    if len(current_component) > 1:
        group_id += 1
        for key, _angle, _fwhm in current_component:
            groups[key] = group_id
    return groups

def write_powder_repartitioning_log(
    log_path: Path, cell: gemmi.UnitCell, mode: str, by_group: Dict[int, List[Reflection]],
    before: Sequence[Reflection], after: Sequence[Reflection], wavelength: float, separation_factor: float,
    mix: float, fallback_groups: int, feedback_map: Path, group_avg_change_percent: Dict[int, float],
    avg_change_percent: Optional[float],
) -> None:
    """Write a human-readable per-cycle log of powder overlap repartitioning:
    how many groups were considered, their average size, the average per-group
    intensity change, and the observed (before) vs. redistributed (after)
    values for the first 3 groups sorted by d-spacing, largest d (lowest
    2theta) first."""
    before_by_key = {(int(r.h), int(r.k), int(r.l)): r for r in before}
    after_by_key = {(int(r.h), int(r.k), int(r.l)): r for r in after}
    group_count = len(by_group)
    total_members = sum(len(members) for members in by_group.values())
    avg_size = total_members / group_count if group_count else 0.0

    def group_d(members: List[Reflection]) -> float:
        ds = [reflection_d_spacing(cell, int(r.h), int(r.k), int(r.l)) for r in members]
        ds = [d for d in ds if d and math.isfinite(d)]
        return sum(ds) / len(ds) if ds else 0.0

    ordered_groups = sorted(by_group.items(), key=lambda item: group_d(item[1]), reverse=True)
    avg_change_text = "n/a" if avg_change_percent is None else f"{avg_change_percent:.2f}%"
    lines: List[str] = [
        "Powder overlap repartitioning",
        f"feedback map: {feedback_map}",
        f"wavelength={wavelength:g} A  separation_factor={separation_factor:g}  mix={mix:g}",
        f"groups considered: {group_count}",
        f"average group size: {avg_size:.2f} reflections/group ({total_members} reflections total in groups)",
        f"average intensity change per group: {avg_change_text}",
        f"map-fallback groups (no usable map signal): {fallback_groups}",
        "",
        f"First {min(3, len(ordered_groups))} groups by d-spacing (largest d / lowest 2θ first):",
    ]
    for gid, members in ordered_groups[:3]:
        d_avg = group_d(members)
        change = group_avg_change_percent.get(gid)
        change_text = "n/a" if change is None else f"{change:.2f}%"
        lines.append(f"\nGroup {gid}  (avg d = {d_avg:.4f} A, {len(members)} reflections, avg intensity change = {change_text}):")
        lines.append(f"  {'h':>4} {'k':>4} {'l':>4} {'d (A)':>9} {'FWHM':>9} {'before':>14} {'after':>14} {'change':>9}")
        sorted_members = sorted(
            members, key=lambda r: reflection_d_spacing(cell, int(r.h), int(r.k), int(r.l)), reverse=True
        )
        for r in sorted_members:
            key = (int(r.h), int(r.k), int(r.l))
            d_value = reflection_d_spacing(cell, *key)
            before_r = before_by_key.get(key)
            after_r = after_by_key.get(key)
            fwhm_text = f"{before_r.sigma:.4f}" if before_r is not None and before_r.sigma is not None else "n/a"
            before_value = before_r.value if before_r is not None else float("nan")
            after_value = after_r.value if after_r is not None else float("nan")
            before_intensity = reflection_value_as_intensity(before_r, mode) if before_r is not None else 0.0
            after_intensity = reflection_value_as_intensity(after_r, mode) if after_r is not None else 0.0
            member_change_text = (
                f"{(after_intensity - before_intensity) / before_intensity * 100.0:.2f}%"
                if before_intensity > 1e-12 else "n/a"
            )
            lines.append(
                f"  {r.h:>4} {r.k:>4} {r.l:>4} {d_value:>9.4f} {fwhm_text:>9} {before_value:>14.4f} {after_value:>14.4f} {member_change_text:>9}"
            )
    try:
        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        pass

def redistribute_overlap_reflections(
    reflections: Sequence[Reflection], data_mode: str, feedback_map: Path, cell: gemmi.UnitCell,
    wavelength: float, separation_factor: float, mix: float, log: Callable[[str], None],
    log_path: Optional[Path] = None,
) -> Tuple[List[Reflection], Optional[float]]:
    """Powder overlap repartitioning: within each 2theta/FWHM overlap group (see
    assign_powder_overlap_groups), keep the observed group-total intensity fixed
    but replace each member's share of it with a blend of its own observed ratio
    and the ratio implied by intensities calculated by FFT from feedback_map
    (mix=0 keeps the observed split, mix=1 uses the map split entirely) --
    the same technique used to deblur overlapping reflections in Le Bail powder
    extractions before phase retrieval. Groups where the map has no usable
    signal for any member fall back to the observed split unchanged.

    When log_path is given, a detailed per-cycle log is written there: how many
    groups were considered, their average size, and the observed (before) vs.
    redistributed (after) values for the first 3 groups sorted by d-spacing.

    Returns (updated_reflections, avg_change_percent), where avg_change_percent
    is the mean, across groups, of each group's average member-wise absolute
    intensity change |after - before| / before * 100 -- i.e. the average
    percent change in intensity per overlap group -- or None if there were no
    overlap groups to redistribute."""
    mode = normalize_reflection_data_mode(data_mode)
    current = [Reflection(int(r.h), int(r.k), int(r.l), float(r.value), r.sigma, r.phase) for r in reflections]
    groups = assign_powder_overlap_groups(current, cell, wavelength, separation_factor)
    if not groups:
        log("Overlap repartitioning: no overlap groups found (need at least two reflections with FWHM and accessible 2θ).")
        if log_path is not None:
            try:
                log_path.write_text(
                    "Powder overlap repartitioning\n"
                    f"feedback map: {feedback_map}\n"
                    f"wavelength={wavelength:g} Å  separation_factor={separation_factor:g}  mix={mix:g}\n"
                    "No overlap groups found (need at least two reflections with FWHM and accessible 2θ).\n",
                    encoding="utf-8",
                )
            except OSError:
                pass
        return current, None
    by_group: Dict[int, List[Reflection]] = {}
    for r in current:
        gid = groups.get((int(r.h), int(r.k), int(r.l)), 0)
        if gid:
            by_group.setdefault(gid, []).append(r)
    all_keys = [(int(r.h), int(r.k), int(r.l)) for group in by_group.values() for r in group]
    predictions = xplor_fft_predictions(feedback_map, all_keys)
    mix = max(0.0, min(1.0, float(mix)))
    redistributed: Dict[Tuple[int, int, int], float] = {}
    fallback_groups = 0
    group_avg_change_percent: Dict[int, float] = {}
    for gid, members in by_group.items():
        observed = [reflection_value_as_intensity(r, mode) for r in members]
        target = float(sum(observed))
        map_intensities = [max(0.0, predictions.get((int(r.h), int(r.k), int(r.l)), (0.0, 0.0))[0]) for r in members]
        map_sum = float(sum(map_intensities))
        observed_ratios = [(value / target if target > 0 else 1.0 / len(members)) for value in observed]
        if map_sum <= 1e-30:
            fallback_groups += 1
            ratios = observed_ratios
        else:
            map_ratios = [value / map_sum for value in map_intensities]
            ratios = [(1.0 - mix) * o + mix * m for o, m in zip(observed_ratios, map_ratios)]
        member_changes: List[float] = []
        for r, ratio, before_intensity in zip(members, ratios, observed):
            new_intensity = target * ratio
            redistributed[(int(r.h), int(r.k), int(r.l))] = new_intensity
            if before_intensity > 1e-12:
                member_changes.append(abs(new_intensity - before_intensity) / before_intensity * 100.0)
        if member_changes:
            group_avg_change_percent[gid] = sum(member_changes) / len(member_changes)
    avg_change_percent = (
        sum(group_avg_change_percent.values()) / len(group_avg_change_percent) if group_avg_change_percent else None
    )
    updated: List[Reflection] = []
    for r in current:
        key = (int(r.h), int(r.k), int(r.l))
        if key in redistributed:
            updated.append(Reflection(r.h, r.k, r.l, value_from_intensity(redistributed[key], mode), r.sigma, r.phase))
        else:
            updated.append(r)
    log(
        "Overlap repartitioning: "
        f"groups={len(by_group)}, reflections_redistributed={len(redistributed)}, "
        f"map_fallback_groups={fallback_groups}, mix={mix:g}, wavelength={wavelength:g} A, "
        f"separation_factor={separation_factor:g}, "
        f"avg_intensity_change_per_group={'n/a' if avg_change_percent is None else f'{avg_change_percent:.2f}%'}"
    )
    if log_path is not None:
        write_powder_repartitioning_log(
            log_path, cell, mode, by_group, current, updated, wavelength, separation_factor, mix, fallback_groups,
            feedback_map, group_avg_change_percent, avg_change_percent,
        )
        log(f"Overlap repartitioning: detailed log written to {log_path}")
    return updated, avg_change_percent

def wants_xplor_modelfile(value: str) -> bool:
    return "xplor" in str(value or "").strip().lower()

def normalize_modelfile_source(value: str) -> str:
    text = str(value or "").strip().lower()
    if text in {"none", "omit", "no", "off"}:
        return "none"
    if text in {"superflip_xplor", "raw_superflip_xplor", "superflip", "raw_xplor"}:
        return "superflip_xplor"
    if text in {"deblurred_xplor", "deblur_xplor", "deblurred", "sharped_xplor"}:
        return "deblurred_xplor"
    if text in {"deblurred_edma_cif", "edma_cif", "cif"}:
        return "deblurred_edma_cif"
    if wants_xplor_modelfile(text):
        return "deblurred_xplor"
    return "deblurred_edma_cif"

def make_run_scoped_dedup_log(
    base_log: Callable[..., None],
    seen: set,
    dedupe_prefixes: Tuple[str, ...],
) -> Callable[..., None]:
    """Wrap a log callable so a message starting with one of dedupe_prefixes
    is logged at its normal level only the first time it is seen (per
    `seen`, a plain set the caller creates fresh once per workflow run);
    every later, byte-identical occurrence is demoted to DETAIL instead of
    repeating at full prominence once per cycle. Every other message, and
    every UNIQUE occurrence of a deduped one, passes through unchanged --
    nothing is ever suppressed, only its repeat prominence."""

    def wrapped(message: object, *args, **kwargs) -> None:
        text = str(message)
        if text.startswith(dedupe_prefixes):
            if text in seen:
                kwargs.setdefault("level", "DETAIL")
            else:
                seen.add(text)
        base_log(message, *args, **kwargs)

    return wrapped

def modelfile_source_display_label(value: str) -> str:
    """Canonical user-facing text for a Next-cycle model token -- the same
    labels the GUI combo itself shows (see _add_combo_with_values() call
    site), so a normal-facing log line never leaks the internal token."""
    token = normalize_modelfile_source(value)
    if token == "none":
        return "None"
    if token == "superflip_xplor":
        return f"{result_map_label('superflip')} (XPLOR)"
    if token == "deblurred_xplor":
        return f"{result_map_label('deblurred')} (XPLOR)"
    return f"{result_structure_label('deblurred')} (EDMA CIF)"

def normalize_reconstruction_mode(value: str) -> str:
    """Canonical internal code behind the "Phasing method" combo. "superflip" (GUI
    label "Superflip") is the default charge-flipping cycle, unchanged. The other two
    run Superflip at most once and instead recycle |Fobs| with phases calculated by
    FFT from the SharpED-deblurred map each cycle; "sharped_recycle" is the GUI's
    "1st Superflip, then SharpED (beta)"; "sharped_recycle_random" is the GUI's
    "SharpED (experimental)" and skips Superflip entirely, starting cycle 1 from
    random phases.

    Must be idempotent (normalize(normalize(x)) == normalize(x)): callers may pass
    either the raw combo text or an already-canonical code, sometimes more than
    once on the same value. The canonical code "sharped_recycle" itself contains
    "sharped" as a substring, so exact codes are matched before any fuzzy "sharped"
    substring check -- otherwise re-normalizing "sharped_recycle" would wrongly
    fall through to the random-start code."""
    text = str(value or "superflip").strip().lower()
    exact = {
        "superflip": "superflip",
        "sharped_recycle": "sharped_recycle",
        "recycle": "sharped_recycle",
        "fourier_recycle": "sharped_recycle",
        "sharped_recycle_superflip_start": "sharped_recycle",
        "1st superflip, then sharped": "sharped_recycle",
        "1st superflip, then sharped (beta)": "sharped_recycle",
        "sharped": "sharped_recycle_random",
        "sharped (beta)": "sharped_recycle_random",
        "sharped (experimental)": "sharped_recycle_random",
        "sharped_recycle_random": "sharped_recycle_random",
        "sharped_recycle_random_start": "sharped_recycle_random",
        "random_start": "sharped_recycle_random",
        "random": "sharped_recycle_random",
    }
    if text in exact:
        return exact[text]
    if "superflip" in text and "sharped" in text:
        return "sharped_recycle"
    if "sharped" in text:
        return "sharped_recycle_random"
    return "superflip"

def parse_atom_label_list(value: str) -> List[str]:
    value = str(value or "").strip()
    if not value or value.lower() in {"none", "off", "false", "0"}:
        return []
    if value.lower() in {"default", "legacy_default"}:
        return []
    labels: List[str] = []
    for tok in re.split(r"[\s,;]+", value):
        tok = tok.strip()
        if not tok:
            continue
        if re.fullmatch(r"\d+", tok):
            tok = "B" + tok
        labels.append(tok)
    return labels

def _xplor_numbers(line: str, cast: Callable[[str], object]) -> List[object]:
    return [cast(tok.replace("D", "E").replace("d", "e")) for tok in str(line or "").split()]

XPLOR_FLOAT_RE = re.compile(r"[+-]?(?:(?:\d+\.\d*)|(?:\.\d+)|(?:\d+))(?:[EeDd][+-]?\d+)?")

def _xplor_float_values(line: str) -> List[float]:
    text = str(line or "")
    values: List[float] = []
    for match in XPLOR_FLOAT_RE.finditer(text):
        token = match.group(0).replace("D", "E").replace("d", "E")
        values.append(float(token))
    return values

def read_xplor_map(path: Path) -> XplorMap:
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines):
        raise RuntimeError(f"XPLOR map is empty: {path}")
    try:
        ntitle = int(lines[i].strip().split()[0])
    except Exception as exc:
        raise RuntimeError(f"Cannot read XPLOR title count in {path}") from exc
    i += 1
    title_lines = lines[i:i + max(0, ntitle)]
    i += max(0, ntitle)
    title = title_lines[0].strip() if title_lines else Path(path).stem
    while i < len(lines) and not lines[i].strip():
        i += 1
    try:
        grid_vals = _xplor_numbers(lines[i], int)
    except Exception as exc:
        raise RuntimeError(f"Cannot read XPLOR grid in {path}") from exc
    if len(grid_vals) < 9:
        raise RuntimeError(f"XPLOR grid line has too few integers in {path}")
    grid = tuple(int(v) for v in grid_vals[:9])
    i += 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    try:
        cell_vals = _xplor_numbers(lines[i], float)
    except Exception as exc:
        raise RuntimeError(f"Cannot read XPLOR cell in {path}") from exc
    if len(cell_vals) < 6:
        raise RuntimeError(f"XPLOR cell line has too few numbers in {path}")
    cell = tuple(float(v) for v in cell_vals[:6])
    i += 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines):
        raise RuntimeError(f"Cannot read XPLOR axis order in {path}")
    axis_order = lines[i].strip() or "ZYX"
    i += 1

    nx = int(grid[0])
    ny = int(grid[3])
    nz = int(grid[6])
    layer_size = nx * ny
    if nx <= 0 or ny <= 0 or nz <= 0:
        raise RuntimeError(f"XPLOR grid dimensions must be positive in {path}")
    values: List[float] = []
    for layer in range(nz):
        layer_values: List[float] = []
        while i < len(lines) and not lines[i].strip():
            i += 1
        if i < len(lines):
            marker = lines[i].strip()
            if re.fullmatch(r"[+-]?\d+", marker) and int(marker) == layer:
                i += 1
        while len(layer_values) < layer_size:
            if i >= len(lines):
                raise RuntimeError(f"XPLOR map ended inside layer {layer} in {path}")
            raw = lines[i].strip()
            i += 1
            if not raw:
                continue
            try:
                layer_values.extend(_xplor_float_values(raw))
            except Exception as exc:
                raise RuntimeError(f"Cannot read XPLOR density values in {path}") from exc
        if len(layer_values) > layer_size:
            raise RuntimeError(f"XPLOR layer {layer} has too many density values in {path}")
        values.extend(layer_values)
    data = np.asarray(values, dtype=np.float64)
    expected = nx * ny * nz
    if data.size != expected:
        raise RuntimeError(f"XPLOR map {path} has {data.size} values, expected {expected}")
    return XplorMap(title=title, grid=grid, cell=cell, axis_order=axis_order, data=data)

def write_xplor_map(path: Path, xmap: XplorMap, title: Optional[str] = None, values_per_line: int = 6) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    grid = tuple(int(v) for v in xmap.grid)
    nx, ny, nz = grid[0], grid[3], grid[6]
    layer_size = nx * ny
    data = np.asarray(xmap.data, dtype=np.float64).reshape(-1)
    expected = nx * ny * nz
    if data.size != expected:
        raise RuntimeError(f"Cannot write XPLOR map {path}: {data.size} values, expected {expected}")
    map_title = (title or xmap.title or Path(path).stem).strip()
    with Path(path).open("w", encoding="utf-8", newline="\n") as f:
        f.write("\n")
        f.write(f"{1:8d}\n")
        f.write(map_title[:80] + "\n")
        f.write(
            f"{grid[0]:8d}{grid[1]:8d}{grid[2]:8d}"
            f"{grid[3]:8d}{grid[4]:8d}{grid[5]:8d}"
            f"{grid[6]:8d}{grid[7]:8d}{grid[8]:8d}\n"
        )
        c = xmap.cell
        f.write(f"{c[0]:12.5f}{c[1]:12.5f}{c[2]:12.5f}{c[3]:12.5f}{c[4]:12.5f}{c[5]:12.5f}\n")
        f.write((xmap.axis_order or "ZYX") + "\n")
        for layer in range(nz):
            f.write(f"{layer:8d}\n")
            start = layer * layer_size
            layer_data = data[start:start + layer_size]
            if values_per_line <= 1:
                for value in layer_data:
                    f.write(f"{float(value):12.5E}\n")
            else:
                ncols = max(1, int(values_per_line))
                for offset in range(0, layer_size, ncols):
                    row = layer_data[offset:offset + ncols]
                    f.write("".join(f"{float(value):12.5E}" for value in row) + "\n")
        f.write("-9999\n")
        f.write(f"{float(np.mean(data)):20.6E}{float(np.std(data)):20.6E}\n")

def normalize_xplor_for_strict_reader(xplor_map: Path, output_map: Path, log: Optional[Callable[[str], None]] = None) -> Path:
    xmap = read_xplor_map(xplor_map)
    write_xplor_map(output_map, xmap, title=xmap.title, values_per_line=1)
    if log:
        log(f"XPLOR map normalized for strict Superflip/EDMA reader: {output_map.name}")
    return output_map

def normalize_xplor_for_superflip_modelfile(xplor_map: Path, output_map: Path, log: Optional[Callable[[str], None]] = None) -> Path:
    # Superflip's ReadXPlor chooses E-format only when the first data row
    # contains an uppercase "E"; SharpED maps use lowercase "e".
    xmap = read_xplor_map(xplor_map)
    write_xplor_map(output_map, xmap, title=xmap.title, values_per_line=1)
    if log:
        log(f"XPLOR modelfile normalized for Superflip reader: {output_map.name}")
    return output_map

def normalize_xplor_for_edma(xplor_map: Path, output_map: Path, log: Optional[Callable[[str], None]] = None) -> Path:
    return normalize_xplor_for_strict_reader(xplor_map, output_map, log)

def xplor_grid_dimensions(xmap: XplorMap) -> Tuple[int, int, int]:
    grid = tuple(int(v) for v in xmap.grid)
    return int(grid[0]), int(grid[3]), int(grid[6])

def xplor_voxel_keyword_from_grid(xplor_map: Path) -> str:
    xmap = read_xplor_map(xplor_map)
    nx, ny, nz = xplor_grid_dimensions(xmap)
    return f"voxel {nx} {ny} {nz}"

def resample_density_axis(data: np.ndarray, new_len: int, axis: int) -> np.ndarray:
    arr = np.moveaxis(np.asarray(data, dtype=np.float64), axis, 0)
    old_len = int(arr.shape[0])
    new_len = int(new_len)
    if new_len == old_len:
        return np.moveaxis(arr, 0, axis)
    if old_len <= 1 or new_len <= 1:
        indices = np.zeros(max(1, new_len), dtype=np.int64)
        return np.moveaxis(arr[indices, ...], 0, axis)
    positions = np.linspace(0.0, float(old_len - 1), new_len, dtype=np.float64)
    lo = np.floor(positions).astype(np.int64)
    hi = np.minimum(lo + 1, old_len - 1)
    weights_shape = (new_len,) + (1,) * (arr.ndim - 1)
    weights = (positions - lo).reshape(weights_shape)
    out = (1.0 - weights) * arr[lo, ...] + weights * arr[hi, ...]
    return np.moveaxis(out, 0, axis)

def resample_xplor_map(xmap: XplorMap, nx: int, ny: int, nz: int, title: Optional[str] = None) -> XplorMap:
    old_nx, old_ny, old_nz = xplor_grid_dimensions(xmap)
    nx = max(2, int(nx))
    ny = max(2, int(ny))
    nz = max(2, int(nz))
    data = np.asarray(xmap.data, dtype=np.float64).reshape((old_nz, old_ny, old_nx))
    data = resample_density_axis(data, nz, axis=0)
    data = resample_density_axis(data, ny, axis=1)
    data = resample_density_axis(data, nx, axis=2)
    grid = tuple(int(v) for v in xmap.grid)
    new_grid = (
        nx, int(grid[1]), int(grid[1]) + nx - 1,
        ny, int(grid[4]), int(grid[4]) + ny - 1,
        nz, int(grid[7]), int(grid[7]) + nz - 1,
    )
    return XplorMap(
        title=title or xmap.title,
        grid=new_grid,
        cell=xmap.cell,
        axis_order=xmap.axis_order,
        data=data.reshape(-1),
    )

def prepare_xplor_for_sharped_upload(
    input_map: Path,
    output_dir: Path,
    max_upload_mb: float,
    log: Callable[[str], None],
) -> Path:
    limit_mb = float(max_upload_mb or 0.0)
    if limit_mb <= 0:
        return input_map
    limit_bytes = int(limit_mb * 1024.0 * 1024.0)
    try:
        current_bytes = int(Path(input_map).stat().st_size)
    except Exception:
        return input_map
    if current_bytes <= limit_bytes:
        return input_map
    raise RuntimeError(
        "The XPLOR map is still larger than the configured SharpED upload limit "
        f"({current_bytes / 1_000_000.0:.1f} MB > {limit_mb:g} MB). "
        "For Superflip-generated maps, leave the voxel field empty/omit so Phase Studio can ask Superflip "
        "to calculate a coarser SharpED-compatible grid directly. For external maps, generate a lower-grid "
        "XPLOR map before uploading."
    )

def xplor_tail_mean_sigma(xplor_map: Path) -> Tuple[Optional[float], Optional[float]]:
    try:
        lines = Path(xplor_map).read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return None, None
    for raw in reversed(lines):
        parts = raw.strip().replace("D", "E").replace("d", "e").split()
        if len(parts) < 2:
            continue
        try:
            return float(parts[0]), float(parts[1])
        except Exception:
            continue
    return None, None

def edma_absolute_plimit(xplor_map: Path, sigma_multiplier: float) -> Tuple[float, Optional[float]]:
    _, sigma = xplor_tail_mean_sigma(xplor_map)
    multiplier = max(0.0, float(sigma_multiplier))
    if sigma is None or not math.isfinite(float(sigma)) or float(sigma) <= 0:
        return multiplier, None
    return multiplier * float(sigma), float(sigma)

def blend_xplor_maps(previous_model: Path, deblurred_map: Path, output_map: Path, damping_factor: float, log: Optional[Callable[[str], None]] = None) -> Path:
    factor = max(1.0, float(damping_factor))
    if factor <= 1.0 + 1e-12:
        shutil.copy2(deblurred_map, output_map)
        return output_map
    old_map = read_xplor_map(previous_model)
    new_map = read_xplor_map(deblurred_map)
    if old_map.grid != new_map.grid or old_map.axis_order.strip().upper() != new_map.axis_order.strip().upper():
        raise RuntimeError(f"Cannot damp XPLOR modelfile: previous model and {result_map_label('deblurred').lower()} have different grids")
    if len(old_map.cell) != len(new_map.cell) or any(abs(a - b) > 1e-3 for a, b in zip(old_map.cell, new_map.cell)):
        raise RuntimeError(f"Cannot damp XPLOR modelfile: previous model and {result_map_label('deblurred').lower()} have different cells")
    blended = ((factor - 1.0) * old_map.data + new_map.data) / factor
    out = XplorMap(
        title=f"damped model factor {factor:g}",
        grid=old_map.grid,
        cell=old_map.cell,
        axis_order=old_map.axis_order,
        data=np.asarray(blended, dtype=np.float64),
    )
    write_xplor_map(output_map, out)
    if log:
        log(f"Damped XPLOR modelfile: {output_map} (factor {factor:g})")
    return output_map

def effective_xplor_damping_factor(inverse_value: float) -> float:
    inverse = max(0.001, min(1.0, float(inverse_value)))
    return max(1.0, 1.0 / inverse)

def clean_keyword_lines(value: str) -> List[str]:
    lines: List[str] = []
    for raw in str(value or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        lines.append(line)
    return lines


def clean_extra_superflip_keywords(value: str, log: Optional[Callable[[str], None]] = None) -> List[str]:
    """Return safe user/legacy extra Superflip keywords.

    The main writer owns structural keywords such as referencefile, modelfile,
    cell and outputfile.  If a stale keyword is left in the extra box or was
    parsed from an older .inflip, old Superflip builds may obey the later line
    and read referencefile.cif instead of the explicitly selected
    superflip_referencefile.cif.
    """
    blocked = {
        "title", "perform", "outputfile", "outputformat",
        "referencefile", "referenceformat",
        "modelfile", "modelformat",
        "dimension", "cell", "spacegroup", "centro",
        "centers", "endcenters", "symmetry", "endsymmetry",
        "composition", "repeatmode", "bestdensities", "maxcycles",
        "randomseed", "dataformat", "dataitemwidths", "fbegin", "endf",
    }
    safe: List[str] = []
    for line in clean_keyword_lines(value):
        parts = split_inflip_line(line)
        key = parts[0].lower() if parts else ""
        if key in blocked:
            if log is not None:
                log(f"  Ignored duplicate/managed Superflip keyword from Extra keywords: {key}")
            continue
        safe.append(line)
    return safe

def split_inflip_line(line: str) -> List[str]:
    text = str(line or "")
    for marker in ("#", "!", ";"):
        if marker in text:
            text = text.split(marker, 1)[0]
    text = text.strip()
    if not text:
        return []
    try:
        return shlex.split(text)
    except Exception:
        return text.split()

def inflip_first_token(line: str) -> str:
    parts = split_inflip_line(line)
    return parts[0].lower() if parts else ""


def insert_before_fbegin(lines: Sequence[str], new_line: str) -> List[str]:
    out: List[str] = []
    inserted = False
    for line in lines:
        if not inserted and inflip_first_token(line) == "fbegin":
            out.append(new_line)
            inserted = True
        out.append(line)
    if not inserted:
        out.append(new_line)
    return out


def without_inflip_keywords(lines: Sequence[str], keywords: Iterable[str]) -> List[str]:
    blocked = {str(k).lower() for k in keywords}
    return [line for line in lines if inflip_first_token(line) not in blocked]


def extract_embedded_hkl_from_inflip(inflip_path: Path, output_dir: Path) -> Path:
    lines = Path(inflip_path).read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    reflections: List[str] = []
    phase_is_superflip_turns = any(
        inflip_first_token(line) == "dataformat"
        and "phase" in {part.lower() for part in split_inflip_line(line)[1:]}
        for line in lines
    )
    in_block = False
    for line in lines:
        key = inflip_first_token(line)
        if key == "fbegin":
            in_block = True
            continue
        if in_block and key == "endf":
            break
        if in_block and line.strip() and not line.lstrip().startswith(COMMENT_PREFIXES):
            record = line.rstrip()
            if phase_is_superflip_turns:
                fields = record.split()
                if len(fields) >= 6:
                    try:
                        fields[4] = f"{float(fields[4]) * 360.0:.9f}"
                        record = " ".join(fields)
                    except ValueError:
                        pass
            reflections.append(record)
    if not reflections:
        raise ValueError(f"No fbegin/endf reflection block was found in Jana2020 .inflip: {inflip_path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"{Path(inflip_path).stem}_embedded_reflections.hkl"
    out.write_text(
        "# Reflections exported from the Jana2020 .inflip fbegin/endf block.\n"
        + ("# Input Superflip phase turns were converted to degrees by Phase Studio.\n" if phase_is_superflip_turns else "")
        + "\n".join(reflections)
        + "\n",
        encoding="utf-8",
    )
    return out


def inflip_declared_reference(inflip_path: Path) -> Optional[Path]:
    for raw in Path(inflip_path).read_text(encoding="utf-8", errors="replace").splitlines():
        parts = split_inflip_line(raw)
        if parts and parts[0].lower() == "referencefile" and len(parts) > 1:
            p = Path(parts[1].strip().strip('"'))
            if not p.is_absolute():
                p = Path(inflip_path).parent / p
            return p.resolve()
    return None




def parse_inflip_crystallography(inflip_path: Path) -> Tuple[gemmi.UnitCell, gemmi.SpaceGroup, str, str]:
    cell_values: Optional[List[float]] = None
    hm = ""
    composition = ""
    for raw in Path(inflip_path).read_text(encoding="utf-8", errors="replace").splitlines():
        parts = split_inflip_line(raw)
        if not parts:
            continue
        key = parts[0].lower()
        if key == "cell" and len(parts) >= 7:
            vals = []
            for item in parts[1:7]:
                vals.append(parse_cif_number(item, math.nan))
            if all(np.isfinite(vals)):
                cell_values = [float(v) for v in vals]
        elif key == "spacegroup" and len(parts) > 1:
            hm = " ".join(parts[1:]).strip().strip("'\"") or hm
        elif key == "composition" and len(parts) > 1:
            composition = " ".join(parts[1:]).strip() or composition
    if cell_values is None:
        raise ValueError(f"Jana2020 .inflip does not contain a readable cell keyword: {inflip_path}")
    if not hm:
        raise ValueError(f"Jana2020 .inflip does not contain a spacegroup keyword: {inflip_path}")
    if not composition:
        raise ValueError(f"Jana2020 .inflip does not contain a composition keyword: {inflip_path}")
    sg = get_spacegroup_from_number(hm) if re.fullmatch(r"\d+(?:\.0+)?", str(hm).strip()) else None
    if sg is None:
        sg = resolve_spacegroup_symbol(hm)
    if sg is None:
        raise ValueError(f"Jana2020 .inflip contains an unrecognized space group: {hm}")
    low = hm.lower().replace("'", "").replace('"', "").replace(" ", "")
    if "21/n" in low:
        hm_out = "P 21/n"
    elif "21/c" in low:
        hm_out = "P 21/c"
    else:
        try:
            hm_out = str(sg.hm).strip() or hm
        except Exception:
            hm_out = hm
    cell = validate_crystal_cell(gemmi.UnitCell(*cell_values))
    return cell, sg, hm_out, validate_composition_text(composition)


def resolve_crystal_metadata(
    source: str,
    *,
    jana_inflip: Optional[Path] = None,
    reference_file: Optional[Path] = None,
    manual_cell: Optional[Sequence[float]] = None,
    manual_spacegroup_number: int = 0,
    manual_spacegroup_symbol: str = "",
    manual_composition: str = "",
) -> CrystalMetadata:
    """Resolve exactly one selected metadata source into a validated object."""
    resolved_source = normalize_metadata_source(source)
    if resolved_source == METADATA_SOURCE_INFLIP:
        if jana_inflip is None or not Path(jana_inflip).is_file():
            raise ValueError("Crystal metadata is incomplete. Select a readable Jana2020 .inflip file.")
        path = Path(jana_inflip).expanduser().resolve()
        cell, spacegroup, hm, composition = parse_inflip_crystallography(path)
        return CrystalMetadata(cell, spacegroup, hm, composition, resolved_source, path)

    if resolved_source == METADATA_SOURCE_REFERENCE:
        if reference_file is None:
            raise ValueError("Crystal metadata is incomplete. Select a reference structure file.")
        return read_reference_crystal_metadata(Path(reference_file))

    values = list(manual_cell or [])
    if len(values) != 6 or any(not math.isfinite(float(value)) for value in values):
        raise ValueError("Crystal metadata is incomplete. Provide all six manual unit-cell parameters.")
    if any(float(value) <= 0.0 for value in values):
        raise ValueError("Manual unit-cell lengths and angles must all be set to positive values.")
    cell = validate_crystal_cell(gemmi.UnitCell(*[float(value) for value in values]))
    number = int(manual_spacegroup_number)
    if number < 1 or number > 230:
        raise ValueError("Manual space-group number must be between 1 and 230.")
    by_number = get_spacegroup_from_number(str(number))
    by_symbol = resolve_spacegroup_symbol(manual_spacegroup_symbol)
    if by_symbol is None:
        raise ValueError(f"Manual space-group symbol is not recognized: {manual_spacegroup_symbol or '(empty)'}")
    if by_number is None or by_number.number != by_symbol.number:
        raise ValueError(
            f"Manual space-group number and symbol contradict each other: #{number} versus {manual_spacegroup_symbol}."
        )
    composition = validate_composition_text(manual_composition)
    return CrystalMetadata(
        cell=cell,
        spacegroup=by_symbol,
        spacegroup_hm=str(by_symbol.hm).strip(),
        composition=composition,
        source=resolved_source,
        source_path=None,
    )

def reflection_data_mode_from_inflip(inflip_path: Optional[Path]) -> Optional[str]:
    if inflip_path is None or not Path(inflip_path).is_file():
        return None
    try:
        parsed = parse_inflip_settings(Path(inflip_path))
    except Exception:
        return None
    mode = parsed.get("reflection_data_mode", "")
    if not mode:
        return None
    return normalize_reflection_data_mode(mode)

def embedded_reflection_data_mode_from_inflip(inflip_path: Optional[Path]) -> Optional[str]:
    if inflip_path is None or not Path(inflip_path).is_file():
        return None
    saw_dataitemwidths = False
    saw_dataformat_amplitude = False
    saw_dataformat_intensity = False
    saw_dataformat_phase = False
    saw_dataformat_fwhm = False
    sample_widths: List[int] = []
    in_block = False
    try:
        for raw in Path(inflip_path).read_text(encoding="utf-8", errors="replace").splitlines():
            parts = split_inflip_line(raw)
            key = parts[0].strip().lower() if parts else ""
            if key == "dataitemwidths":
                saw_dataitemwidths = True
            elif key == "dataformat":
                items = {p.strip().lower() for p in parts[1:]}
                saw_dataformat_intensity = "intensity" in items
                saw_dataformat_amplitude = "amplitude" in items
                saw_dataformat_phase = "phase" in items
                saw_dataformat_fwhm = "fwhm" in items
            if key == "fbegin":
                in_block = True
                continue
            if in_block and key == "endf":
                break
            if in_block and raw.strip() and not raw.lstrip().startswith(COMMENT_PREFIXES):
                fields = raw.split()
                if len(fields) >= 4:
                    sample_widths.append(len(fields))
                    if len(sample_widths) >= 20:
                        break
    except Exception:
        return None
    if saw_dataformat_phase:
        return REFLECTION_DATA_MODE_INTENSITY_PHASE_SIGMA if saw_dataformat_intensity else REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA
    if saw_dataitemwidths and sample_widths and max(sample_widths) >= 6:
        return REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA
    if saw_dataformat_fwhm:
        return REFLECTION_DATA_MODE_INTENSITY_FWHM if saw_dataformat_intensity else REFLECTION_DATA_MODE_AMPLITUDE_FWHM
    if saw_dataformat_intensity:
        return REFLECTION_DATA_MODE_INTENSITY
    if saw_dataformat_amplitude:
        return REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA
    return None

def resolve_reflection_data_mode_from_sources(
    hkl_path: Path,
    configured_mode: str,
    inflip_path: Optional[Path] = None,
) -> str:
    mode = normalize_reflection_data_mode(configured_mode)
    if mode != REFLECTION_DATA_MODE_AUTO:
        return mode
    inflip_mode = reflection_data_mode_from_inflip(inflip_path)
    if inflip_mode and inflip_mode != REFLECTION_DATA_MODE_AUTO:
        return inflip_mode
    return resolve_reflection_data_mode(hkl_path, mode)


def resolve_hkl_analysis_inputs(request: HklAnalysisRequest) -> Tuple[Path, str, gemmi.UnitCell, gemmi.SpaceGroup, str, str]:
    """Resolve an HklAnalysisRequest into the concrete HKL file/cell/symmetry/
    data-mode a load or completeness analysis needs. Plain function operating
    only on its request argument (no QMainWindow/self needed) so any caller
    -- the main GUI's own Validate HKL/Analyze completeness, or the Jana
    Wizard's input summary/data-mode detection -- can call it directly."""
    work_dir = Path(request.work_text).expanduser().resolve() if request.work_text else Path.cwd()
    jana_path = Path(request.jana_text).expanduser().resolve() if request.jana_text else None
    use_inflip_hkl = request.mode == INPUT_MODE_INFLIP or (request.mode == INPUT_MODE_INFLIP_OVERRIDES and not request.hkl_text)
    if use_inflip_hkl:
        if jana_path is None or not jana_path.is_file():
            raise FileNotFoundError("Jana2020 .inflip is required to test or analyze embedded HKL data.")
        hkl_path = extract_embedded_hkl_from_inflip(jana_path, work_dir)
        source_note = f"HKL source: fbegin/endf block exported from {jana_path}"
    else:
        if not request.hkl_text:
            raise FileNotFoundError("Select an external HKL file or a Jana2020 .inflip with embedded reflections.")
        hkl_path = Path(request.hkl_text).expanduser().resolve()
        if not hkl_path.is_file():
            raise FileNotFoundError(f"HKL file not found: {hkl_path}")
        source_note = f"HKL source: {hkl_path}"
    metadata = request.metadata
    if metadata is None:
        raise ValueError("Crystal metadata is incomplete. Provide unit-cell, symmetry and composition information.")
    cell = metadata.cell
    sg = metadata.spacegroup
    hm = metadata.spacegroup_hm
    metadata_name = metadata.source_path if metadata.source_path is not None else "manual input"
    source_note += f"; cell/symmetry source: {metadata_name}"
    if use_inflip_hkl:
        data_mode = embedded_reflection_data_mode_from_inflip(jana_path) or resolve_reflection_data_mode_from_sources(hkl_path, request.configured_mode, jana_path)
    else:
        data_mode = resolve_reflection_data_mode_from_sources(hkl_path, request.configured_mode, jana_path)
    return hkl_path, data_mode, cell, sg, hm, source_note


def build_hkl_load_result(request: HklAnalysisRequest) -> HklLoadResult:
    """Plain-function equivalent of resolve_hkl_analysis_inputs() that also
    reads and merges the reflections -- see resolve_hkl_analysis_inputs()."""
    hkl_path, data_mode, cell, sg, hm, source_note = resolve_hkl_analysis_inputs(request)
    value_col, sigma_col, include_000 = reflection_columns_for_mode(data_mode)
    reflections = read_hkl(hkl_path, value_col=value_col, sigma_col=sigma_col, include_000=include_000)
    unique = merge_duplicate_reflections(reflections)
    return HklLoadResult(
        hkl_path=hkl_path,
        data_mode=data_mode,
        cell=cell,
        spacegroup=sg,
        spacegroup_hm=hm,
        source_note=source_note,
        value_col=value_col,
        sigma_col=sigma_col,
        include_000=include_000,
        reflections=reflections,
        unique_reflections=unique,
    )


def build_hkl_analysis_request_from_inflip(
    inflip_path: Path,
    reference_file: Optional[Path] = None,
    work_dir: Optional[Path] = None,
) -> HklAnalysisRequest:
    """Build the HklAnalysisRequest a Jana2020-.inflip-only caller (the Jana
    Wizard) needs, without requiring a full IterativeSuperflipPipelineQtGUI
    instance. Mirrors what the main GUI's _collect_hkl_analysis_request()
    computes for its own "Jana2020 .inflip" input mode: crystal metadata is
    always resolved from the .inflip itself (never manual entry or a
    reference-file override, since the Wizard has no such controls)."""
    metadata = resolve_crystal_metadata(METADATA_SOURCE_INFLIP, jana_inflip=inflip_path)
    return HklAnalysisRequest(
        INPUT_MODE_INFLIP,
        "",
        str(inflip_path),
        str(reference_file) if reference_file is not None else "",
        str(work_dir) if work_dir is not None else "",
        REFLECTION_DATA_MODE_AUTO,
        metadata,
    )


def write_reference_cif_from_inflip(inflip_path: Path, output_cif: Path) -> Path:
    cell, sg, hm, composition = parse_inflip_crystallography(inflip_path)
    output_cif.parent.mkdir(parents=True, exist_ok=True)
    write_structure_cif(output_cif, cell, sg, hm, [], composition)
    return output_cif


def inflip_header_for_m80(lines: Sequence[str]) -> List[str]:
    header: List[str] = []
    marker = "# Keywords for charge flipping"
    for line in lines:
        if marker in line:
            break
        if inflip_first_token(line) == "fbegin":
            break
        header.append(line)
    return header


def define_m80_inflip_from_model(header_lines: Sequence[str], base_name: str, model_name: str) -> List[str]:
    out: List[str] = []
    saw_perform = False
    saw_outputfile = False
    drop = {
        "modelfile", "modelformat", "repeatmode", "randomseed",
        "polish", "maxcycles", "searchsymmetry", "derivesymmetry", "voxel",
    }
    for line in header_lines:
        key = inflip_first_token(line)
        if key in drop:
            continue
        if key == "perform" and not saw_perform:
            out.append("perform symmetry")
            saw_perform = True
            continue
        if key == "outputfile" and not saw_outputfile:
            body = str(line).split("#", 1)[0].rstrip()
            ready = f'{base_name}-ready.xplor'
            if ready.lower() not in body.lower():
                spacer = "" if body.endswith((" ", "\t")) else " "
                body = f'{body}{spacer}"{ready}"'
            out.append(body)
            saw_outputfile = True
            continue
        out.append(line)
    if not saw_perform:
        out = insert_before_fbegin(out, "perform symmetry")
    if not saw_outputfile:
        out = insert_before_fbegin(out, f'outputfile "{base_name}-ready.xplor"')
    out.extend([
        "repeatmode 1",
        f'modelfile "{model_name}"',
        "polish no",
        "maxcycles 0",
        "searchsymmetry average",
        "derivesymmetry yes",
    ])
    return out


def write_text_lines_platform(path: Path, lines: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\r\n".join(str(line) for line in lines).rstrip("\r\n") + "\r\n"
    path.write_bytes(text.encode(text_encoding(), errors="replace"))


def return_phase_studio_result_to_jana(
    cfg: RunConfig,
    result: CycleResult,
    log: Callable[[str], None],
    stop_event: Optional[threading.Event] = None,
    map_source: str = "deblurred",
) -> None:
    if not cfg.jana_return_to_jana or cfg.jana_inflip is None:
        raise RuntimeError("Jana2020 handoff requires a Jana2020 .inflip primary input.")
    inflip_path = Path(cfg.jana_inflip)
    if not inflip_path.is_file():
        raise RuntimeError(f"Jana2020 .inflip no longer exists: {inflip_path}")
    jana_cwd = inflip_path.parent
    base_name = inflip_path.stem
    source_key = str(map_source or "deblurred").strip().lower()
    if source_key.startswith("super"):
        source_map = Path(result.superflip_map)
        target_map = jana_cwd / f"{base_name}-phase-studio-superflip-cycle_{int(result.cycle):03d}.xplor"
        source_label = result_map_label("superflip")
    else:
        source_map = Path(result.deblur_map)
        target_map = jana_cwd / f"{base_name}-deb.xplor"
        source_label = result_map_label("deblurred")
    if not source_map.is_file():
        raise RuntimeError(f"Selected Jana2020 handoff map not found: {source_map}")
    if source_map.resolve() != target_map.resolve():
        shutil.copy2(source_map, target_map)
    log(f"Jana2020 handoff source: cycle {int(result.cycle):03d}, {source_label}")
    log(f"Jana2020 handoff map: {target_map}")
    original = Path(str(cfg.superflip_exe)).expanduser()
    calc_dir = original.parent / "deblurrer"
    calc_inflip = calc_dir / "calc_m80.inflip"
    original_lines = inflip_path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    final_lines = define_m80_inflip_from_model(inflip_header_for_m80(original_lines), base_name, target_map.name)
    write_text_lines_platform(calc_inflip, final_lines)
    log(f"Jana2020 final Superflip input: {calc_inflip}")
    run_command(
        [str(original), str(calc_inflip)],
        cwd=jana_cwd,
        log_path=Path(cfg.work_dir) / "jana2020_return_superflip.log",
        log=log,
        stop_event=stop_event,
        allow_foreground=True,
    )
    log("Jana2020 final Superflip handoff completed.")



def perform_jana_handoff(
    cfg: RunConfig,
    result: CycleResult,
    map_source: str,
    log: Callable[[str], None],
    stop_event: Optional[threading.Event] = None,
) -> None:
    """Compatibility wrapper used by the full Phase Studio hand-off button.

    Earlier builds called perform_jana_handoff() from the GUI worker thread,
    while the actual implementation was renamed to return_phase_studio_result_to_jana().
    Keeping this small wrapper prevents a NameError and ensures both call paths use
    the same Jana2020 final hand-off implementation.
    """
    return_phase_studio_result_to_jana(
        cfg=cfg,
        result=result,
        log=log,
        stop_event=stop_event,
        map_source=map_source,
    )


def parse_inflip_settings(inflip_path: Path) -> Dict[str, str]:
    settings: Dict[str, str] = {}
    extra: List[str] = []
    skip_until = ""
    saw_reference_keyword = False
    saw_voxel_keyword = False
    skip_blocks = {
        "fbegin": "endf",
        "symmetry": "endsymmetry",
        "centers": "endcenters",
        "qvectors": "endqvectors",
        "histogram": "endhistogram",
        "referencesymmetry": "endreferencesymmetry",
    }
    ignored = {
        "title", "cell", "spacegroup", "centro", "dimension", "referencefile",
        "referenceformat", "modelformat", "dataformat",
        "inputfile", "outputbase", "m40forjana", "writem40", "maxima", "fullcell",
        "scale", "numberofatoms", "centerofcharge", "chlimit", "chlimlist",
    }
    direct_line_keys = {
        "perform": "perform_algorithm",
        "voxel": "voxel",
        "randomseed": "randomseed",
        "delta": "delta",
        "weakratio": "weakratio",
        "biso": "biso",
        "missing": "missing",
        "derivesymmetry": "derivesymmetry",
        "electrons": "electrons",
        "dataitemwidths": "dataitemwidths",
        "lambda": "powder_wavelength",
        "wavelength": "powder_wavelength",
        "fwhmseparation": "powder_separation_factor",
    }
    text = Path(inflip_path).read_text(encoding="utf-8", errors="replace")
    for raw in text.splitlines():
        parts = split_inflip_line(raw)
        if not parts:
            continue
        key = parts[0].strip().lower()
        if skip_until:
            if key == skip_until:
                skip_until = ""
            continue
        if key in skip_blocks:
            skip_until = skip_blocks[key]
            continue
        value = " ".join(parts[1:]).strip()
        if key == "composition":
            settings["composition_override"] = value
        elif key == "referencefile":
            saw_reference_keyword = True
            ref_name = parts[1].strip().strip('"') if len(parts) > 1 else ""
            if ref_name:
                settings["superflip_referencefile"] = ref_name
                settings["reference_cif"] = ref_name
            suffix = Path(ref_name).suffix.lower()
            if suffix in REFERENCE_DENSITY_SUFFIXES:
                settings["referencefile_mode"] = "reference_density"
            elif suffix in REFERENCE_STRUCTURE_SUFFIXES:
                settings["referencefile_mode"] = "reference_cif"
            elif ref_name:
                settings["referencefile_mode"] = "reference_density"
        elif key == "referenceformat":
            saw_reference_keyword = True
            fmt = parts[1].strip().lower() if len(parts) > 1 else ""
            if fmt in {"jana", "xplor", "ccp4"}:
                settings["referencefile_mode"] = "reference_density"
            elif fmt == "cif":
                settings["referencefile_mode"] = "reference_cif"
        elif key == "modelfile":
            model_name = parts[1].strip().strip('"') if len(parts) > 1 else ""
            if model_name:
                settings["first_cycle_modelfile"] = model_name
        elif key == "dataformat":
            items = [p.strip().lower() for p in parts[1:]]
            if "intensity" in items and "phase" in items:
                settings["reflection_data_mode"] = REFLECTION_DATA_MODE_INTENSITY_PHASE_SIGMA
            elif "amplitude" in items and "phase" in items:
                settings["reflection_data_mode"] = REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA
            elif "intensity" in items and "fwhm" in items:
                settings["reflection_data_mode"] = REFLECTION_DATA_MODE_INTENSITY_FWHM
            elif "amplitude" in items and "fwhm" in items:
                settings["reflection_data_mode"] = REFLECTION_DATA_MODE_AMPLITUDE_FWHM
            elif "intensity" in items:
                settings["reflection_data_mode"] = REFLECTION_DATA_MODE_INTENSITY
            elif "amplitude" in items and "dummy" in items:
                settings["reflection_data_mode"] = REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA
            elif "amplitude" in items:
                settings["reflection_data_mode"] = REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA
        elif key == "bestdensities":
            if len(parts) > 1:
                settings["bestdensities_count"] = parts[1]
            metric = parts[2].lower() if len(parts) > 2 else "rvalue"
            settings["bestdensities_metric"] = normalize_bestdensities_metric(metric)
            settings["bestdensities_symmetry"] = "true" if metric == "symmetry" else "false"
        elif key == "polish":
            settings["polish"] = "true" if value.lower().startswith("yes") else "false"
        elif key in {"maxcycles", "repeatmode", "nresshells"}:
            settings[key] = parts[1] if len(parts) > 1 else ""
        elif key == "normalize":
            settings["normalize"] = parts[1] if len(parts) > 1 else "none"
        elif key == "searchsymmetry":
            settings["searchsymmetry"] = parts[1] if len(parts) > 1 else "average"
        elif key == "plimit":
            if len(parts) > 1:
                settings["plimit_superflip"] = parts[1]
        elif key in direct_line_keys:
            if key == "voxel":
                saw_voxel_keyword = True
            settings[direct_line_keys[key]] = value
        elif key in ignored:
            continue
        else:
            extra.append(raw.strip())
    if not saw_reference_keyword:
        settings["referencefile_mode"] = "omit"
    if not saw_voxel_keyword:
        settings["voxel"] = "omit"
    if "dataitemwidths" in settings and "reflection_data_mode" not in settings:
        settings["reflection_data_mode"] = REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA
    if extra:
        settings["extra_superflip_keywords"] = "\n".join(extra)
    return settings

def resolve_powder_wavelength(
    manual_value: float, inflip_path: Optional[Path], reference_cif_path: Optional[Path],
) -> Tuple[float, str]:
    """Resolve the powder-repartitioning wavelength.

    Priority: a manually entered nonzero value wins outright; otherwise the Jana
    .inflip file's lambda/wavelength line; otherwise the reference file's
    _diffrn_radiation_wavelength CIF tag. Returns (value, source_description).
    """
    if manual_value > 0:
        return manual_value, "manual entry"
    if inflip_path is not None and inflip_path.is_file():
        try:
            settings = parse_inflip_settings(inflip_path)
        except Exception:
            settings = {}
        value = parse_cif_number(settings.get("powder_wavelength", ""), 0.0)
        if value > 0:
            return value, f".inflip file ({inflip_path.name})"
    if reference_cif_path is not None and reference_cif_path.is_file():
        try:
            raw = raw_cif_value(reference_cif_path, ["_diffrn_radiation_wavelength", "_diffrn_radiation.wavelength"])
        except Exception:
            raw = ""
        value = parse_cif_number(raw, 0.0)
        if value > 0:
            return value, f"reference file ({reference_cif_path.name})"
    return 0.0, "none"

def normalize_output_format(value: str) -> str:
    fmt = str(value or "xplor").strip().lower()
    if fmt in {"jana", "xplor", "ccp4", "m80"}:
        return fmt
    return "xplor"

def normalize_map_export_format(value: str) -> str:
    """XPLOR is always produced internally for EDMA/SharpED/Superflip; this picks one
    additional saved output on top of it: an extra density map format (ccp4/jana), or
    a reflection-file export in place of an extra density map (hkl_phases/shelx_fcf)."""
    fmt = str(value or "xplor").strip().lower()
    exact = {
        "xplor": "xplor",
        "ccp4": "ccp4",
        "jana": "jana",
        "hkl_phases": "hkl_phases",
        "hkl reflections with phases": "hkl_phases",
        "shelx_fcf": "shelx_fcf",
        "shelx (fcf)": "shelx_fcf",
        "fcf": "shelx_fcf",
    }
    return exact.get(fmt, "xplor")

def normalize_structure_export_format(value: str) -> str:
    """CIF is always produced internally as the EDMA structure/modelfile; this picks
    one additional saved structure format on top of it."""
    fmt = str(value or "cif").strip().lower()
    if fmt in {"cif", "xyz", "pdb"}:
        return fmt
    return "cif"

def normalize_bestdensities_metric(value: str) -> str:
    metric = str(value or "rvalue").strip().lower()
    if metric in {"rvalue", "peakiness", "symmetry", "reference"}:
        return metric
    return "rvalue"

def superflip_default_voxel_triplet(cell: gemmi.UnitCell, step_angstrom: float = 0.2) -> Tuple[int, int, int]:
    step = max(0.01, float(step_angstrom))
    dims = []
    for length in (cell.a, cell.b, cell.c):
        raw = max(1, int(math.ceil(float(length) / step)))
        dims.append(int(math.ceil(raw / 10.0) * 10))
    return int(dims[0]), int(dims[1]), int(dims[2])

def voxel_keyword_is_omitted(value: str) -> bool:
    text = str(value or "").strip().lower()
    return not text or text in {"none", "no", "off", "omit"}

def sharped_upload_limit_bytes(max_upload_mb: float) -> int:
    return int(max(0.0, float(max_upload_mb or 0.0)) * 1_000_000.0)

def estimate_xplor_text_bytes(nx: int, ny: int, nz: int) -> int:
    values = max(1, int(nx)) * max(1, int(ny)) * max(1, int(nz))
    # Jana/Superflip XPLOR maps are text maps.  The observed public-server
    # cases are about 12 bytes per density value; use a conservative margin.
    return int(values * 13.2 + max(1, int(nz)) * 16 + 4096)

def sharped_limited_superflip_voxel(
    voxel: str,
    cell: gemmi.UnitCell,
    max_upload_mb: float,
    log: Optional[Callable[[str], None]] = None,
) -> str:
    if max_upload_mb <= 0 or not voxel_keyword_is_omitted(voxel):
        return voxel
    limit_bytes = sharped_upload_limit_bytes(max_upload_mb)
    if limit_bytes <= 0:
        return voxel
    default_step = 0.2
    default_dims = superflip_default_voxel_triplet(cell, default_step)
    default_estimate = estimate_xplor_text_bytes(*default_dims)
    # Leave the keyword omitted if the normal Superflip grid should fit with
    # some room.  This preserves the historical default for ordinary cells.
    if default_estimate <= int(limit_bytes * 0.92):
        return voxel
    target_bytes = int(limit_bytes * 0.86)
    scale = max(0.2, min(0.98, (float(target_bytes) / float(default_estimate)) ** (1.0 / 3.0)))
    step = default_step / scale
    dims = superflip_default_voxel_triplet(cell, step)
    for _ in range(40):
        if estimate_xplor_text_bytes(*dims) <= target_bytes:
            break
        step *= 1.025
        dims = superflip_default_voxel_triplet(cell, step)
    if log is not None:
        log(
            "SharpED upload limit: Superflip voxel/finevoxel keywords added before map calculation "
            f"to avoid post-hoc XPLOR resampling: default estimate {default_dims[0]}x{default_dims[1]}x{default_dims[2]} "
            f"({default_estimate / 1_000_000.0:.1f} MB) -> voxel {dims[0]} {dims[1]} {dims[2]} "
            f"(estimated {estimate_xplor_text_bytes(*dims) / 1_000_000.0:.1f} MB; limit {max_upload_mb:g} MB)."
        )
    return f"{dims[0]} {dims[1]} {dims[2]}"

def append_superflip_keyword(extra_keywords: str, line: str) -> str:
    base = str(extra_keywords or "").strip()
    addition = str(line or "").strip()
    if not addition:
        return base
    if not base:
        return addition
    return base + "\n" + addition

def superflip_voxel_keyword_line(value: str, cell: gemmi.UnitCell, log: Optional[Callable[[str], None]] = None) -> str:
    text = str(value or "").strip()
    if voxel_keyword_is_omitted(text):
        return ""
    if text.lower() == "auto":
        dims = superflip_default_voxel_triplet(cell)
        return f"voxel {dims[0]} {dims[1]} {dims[2]}"
    parts = text.replace(",", " ").split()
    if len(parts) == 3 and all(re.fullmatch(r"[+-]?\d+", p) for p in parts):
        return "voxel " + " ".join(parts)
    if parts and re.fullmatch(r"\d+(?:\.\d+)?", parts[0]):
        step = float(parts[0])
        if step > 0:
            dims = superflip_default_voxel_triplet(cell, step)
            return f"voxel {dims[0]} {dims[1]} {dims[2]}"
    if log:
        log(f"Superflip voxel value {text!r} is not understood; using automatic 0.2 A grid.")
    dims = superflip_default_voxel_triplet(cell)
    return f"voxel {dims[0]} {dims[1]} {dims[2]}"

def superflip_normalize_keyword_lines(normalize: str, nresshells: int, log: Optional[Callable[[str], None]] = None) -> List[str]:
    mode = str(normalize or "").strip().lower()
    if not mode or mode in {"none", "no", "off", "omit", "local"}:
        return []
    if log:
        log(f"Superflip normalize value {normalize!r} may be unsupported by this executable; omitting normalize keyword.")
    return []

def write_structure_cif(
    output_cif: Path,
    cell: gemmi.UnitCell,
    sg: gemmi.SpaceGroup,
    sg_hm: str,
    atoms: Sequence[AtomSite],
    composition: str = "",
) -> None:
    output_cif.parent.mkdir(parents=True, exist_ok=True)
    group_ops = sg.operations()
    ops = [op.translated(cen) for op in group_ops.sym_ops for cen in group_ops.cen_ops]
    with output_cif.open("w", encoding="utf-8") as f:
        f.write("data_iterative_edma_prediction\n")
        f.write(f"_cell_length_a {cell.a:.5f}\n_cell_length_b {cell.b:.5f}\n_cell_length_c {cell.c:.5f}\n")
        f.write(f"_cell_angle_alpha {cell.alpha:.5f}\n_cell_angle_beta {cell.beta:.5f}\n_cell_angle_gamma {cell.gamma:.5f}\n")
        f.write(f"_symmetry_space_group_name_H-M '{sg_hm}'\n_space_group_name_H-M_alt '{sg_hm}'\n")
        try:
            f.write(f"_symmetry_Int_Tables_number {sg.number}\n_space_group_IT_number {sg.number}\n")
        except Exception:
            pass
        if str(composition or "").strip():
            f.write(f"_chemical_formula_sum '{str(composition).strip()}'\n")
        f.write("loop_\n_space_group_symop_operation_xyz\n")
        for op in ops:
            f.write(f"'{op.triplet()}'\n")
        if atoms:
            f.write("loop_\n_atom_site_label\n_atom_site_type_symbol\n_atom_site_fract_x\n_atom_site_fract_y\n_atom_site_fract_z\n")
            counts: Dict[str, int] = collections.Counter()
            for a in atoms:
                elem = clean_element_symbol(a.element)
                counts[elem] += 1
                f0 = wrap_frac(a.frac)
                f.write(f"{elem}{counts[elem]} {elem} {f0[0]:.6f} {f0[1]:.6f} {f0[2]:.6f}\n")


def fractional_to_cartesian(cell: gemmi.UnitCell, frac: Sequence[float]) -> Tuple[float, float, float]:
    x, y, z = [float(v) for v in wrap_frac(frac)]
    a, b, c = float(cell.a), float(cell.b), float(cell.c)
    alpha = math.radians(float(cell.alpha))
    beta = math.radians(float(cell.beta))
    gamma = math.radians(float(cell.gamma))
    cos_alpha, cos_beta, cos_gamma = math.cos(alpha), math.cos(beta), math.cos(gamma)
    sin_gamma = math.sin(gamma)
    if abs(sin_gamma) < 1e-12:
        return a * x, b * y, c * z
    volume_factor = math.sqrt(max(0.0, 1.0 - cos_alpha ** 2 - cos_beta ** 2 - cos_gamma ** 2 + 2.0 * cos_alpha * cos_beta * cos_gamma))
    cart_x = a * x + b * cos_gamma * y + c * cos_beta * z
    cart_y = b * sin_gamma * y + c * (cos_alpha - cos_beta * cos_gamma) / sin_gamma * z
    cart_z = c * volume_factor / sin_gamma * z
    return cart_x, cart_y, cart_z

def write_structure_xyz(output_xyz: Path, cell: gemmi.UnitCell, atoms: Sequence[AtomSite]) -> None:
    output_xyz.parent.mkdir(parents=True, exist_ok=True)
    with output_xyz.open("w", encoding="utf-8") as f:
        f.write(f"{len(atoms)}\n")
        f.write("Phase Studio EDMA Cartesian-coordinate export\n")
        for atom in atoms:
            elem = clean_element_symbol(atom.element)
            x, y, z = fractional_to_cartesian(cell, atom.frac)
            f.write(f"{elem} {x:.8f} {y:.8f} {z:.8f}\n")

def write_structure_pdb(output_pdb: Path, cell: gemmi.UnitCell, sg_hm: str, atoms: Sequence[AtomSite]) -> None:
    output_pdb.parent.mkdir(parents=True, exist_ok=True)
    with output_pdb.open("w", encoding="utf-8") as f:
        f.write(f"CRYST1{cell.a:9.3f}{cell.b:9.3f}{cell.c:9.3f}{cell.alpha:7.2f}{cell.beta:7.2f}{cell.gamma:7.2f} {sg_hm[:11]:<11}    1\n")
        for idx, atom in enumerate(atoms, start=1):
            elem = clean_element_symbol(atom.element)
            x, y, z = fractional_to_cartesian(cell, atom.frac)
            name = (atom.label or f"{elem}{idx}")[:4]
            f.write(
                f"HETATM{idx:5d} {name:<4} UNK A   1    "
                f"{x:8.3f}{y:8.3f}{z:8.3f}{1.00:6.2f}{0.00:6.2f}          {elem:>2}\n"
            )
        f.write("END\n")

def write_structure_bundle(output_cif: Path, cell: gemmi.UnitCell, sg: gemmi.SpaceGroup, sg_hm: str, atoms: Sequence[AtomSite], structure_format: str = "cif") -> None:
    """Write the CIF that EDMA/next-cycle modelfiles always need, plus one optional
    extra structure format (xyz or pdb) selected by the user."""
    write_structure_cif(output_cif, cell, sg, sg_hm, atoms)
    fmt = normalize_structure_export_format(structure_format)
    if fmt == "xyz":
        write_structure_xyz(output_cif.with_suffix(".xyz"), cell, atoms)
    elif fmt == "pdb":
        write_structure_pdb(output_cif.with_suffix(".pdb"), cell, sg_hm, atoms)

def write_filtered_cif(input_cif: Path, output_cif: Path, exclude_labels: Sequence[str]) -> Tuple[Path, int, int]:
    atoms = parse_cif_atoms(input_cif)
    cell, sg, hm = parse_cif_cell_and_sg(input_cif)
    exclude = {normalize_atom_label(x) for x in exclude_labels}
    kept: List[AtomSite] = []
    removed = 0
    for a in atoms:
        if normalize_atom_label(a.label) in exclude:
            removed += 1
            continue
        kept.append(AtomSite(label=a.label, element=a.element, frac=wrap_frac(a.frac), density=a.density))
    write_structure_cif(output_cif, cell, sg, hm, kept)
    return output_cif.resolve(), removed, len(kept)

def write_superflip_input(
    inp_path: Path,
    prefix: str,
    ref_ctx: ReferenceContext,
    observed_hkl: Path,
    output_xplor: str,
    model_file: Optional[Path],
    reference_file: Optional[Path],
    reference_format: str,
    perform_algorithm: str,
    output_format: str,
    write_auxiliary_outputs: bool,
    export_superflip_xplor: bool,
    export_superflip_ccp4: bool,
    export_superflip_jana: bool,
    voxel: str,
    bestdensities_count: int,
    bestdensities_metric: str,
    bestdensities_symmetry: bool,
    polish: bool,
    maxcycles: int,
    repeatmode: int,
    randomseed: str,
    delta: str,
    weakratio: str,
    biso: str,
    reflection_data_mode: str,
    normalize: str,
    nresshells: int,
    missing: str,
    searchsymmetry: str,
    derivesymmetry: str,
    electrons: str,
    dataitemwidths: str,
    extra_superflip_keywords: str,
    log: Optional[Callable[[str], None]] = None,
) -> None:
    inp_path.parent.mkdir(parents=True, exist_ok=True)
    ops = ref_ctx.spacegroup.operations()
    perform = str(perform_algorithm or "CF").strip().upper()
    perform_base = perform.split()[0].lower()
    if perform_base not in {"cf", "aar", "lde", "general", "fourier", "symmetry"}:
        perform = "CF"
    fmt = normalize_output_format(output_format)
    best_metric = "symmetry" if bestdensities_symmetry else normalize_bestdensities_metric(bestdensities_metric)
    effective_repeatmode = int(repeatmode)
    write_randomseed = True
    if model_file is not None:
        if effective_repeatmode != 1 and log is not None:
            log("  Superflip modelfile is set; using repeatmode 1 because repeated model-seeded runs are deterministic.")
        effective_repeatmode = 1
        write_randomseed = False
        if log is not None:
            log("  Superflip modelfile is set; randomseed keyword omitted.")
    bestdensities_line = f"bestdensities {max(1, int(bestdensities_count))} {best_metric}"
    data_mode = normalize_reflection_data_mode(reflection_data_mode)
    voxel_line = superflip_voxel_keyword_line(voxel, ref_ctx.cell, log)
    normalize_lines = superflip_normalize_keyword_lines(normalize, nresshells, log)
    delta_value = str(delta or "AUTO").strip() or "AUTO"
    weakratio_value = str(weakratio or "0.000").strip() or "0.000"
    biso_value = str(biso or "0.000").strip() or "0.000"
    derivesymmetry_value = str(derivesymmetry or "yes").strip() or "yes"
    searchsymmetry_value = str(searchsymmetry or "average").strip().lower() or "average"
    if searchsymmetry_value not in {"no", "shift", "average"}:
        searchsymmetry_value = "average"
    with inp_path.open("w", encoding="utf-8") as f:
        f.write(f"title {prefix}\nperform {perform}\n")
        output_files: List[str] = []
        if write_auxiliary_outputs or export_superflip_jana:
            output_files.extend([f"{prefix}.m81", f"{prefix}.m80"])
        if export_superflip_ccp4:
            output_files.append(f"{prefix}.ccp4")
        if export_superflip_xplor or output_xplor not in output_files:
            output_files.append(output_xplor)
        f.write("outputfile " + " ".join(output_files) + f"\noutputformat {fmt}\n")
        if reference_file is not None:
            f.write(f"referencefile {reference_file.name}\n")
        if model_file is not None:
            f.write(f"modelfile {model_file.name}\n")
        f.write("dimension  3\n")
        if voxel_line:
            f.write(voxel_line + "\n")
        c = ref_ctx.cell
        f.write(f"cell {c.a:.6f} {c.b:.6f} {c.c:.6f} {c.alpha:.4f} {c.beta:.4f} {c.gamma:.4f}\n")
        f.write(f"spacegroup {ref_ctx.spacegroup_hm}\n")
        f.write("centro yes\n" if ops.is_centrosymmetric() else "centro no\n")
        f.write("centers\n")
        for cen in ops.cen_ops:
            f.write(center_vector_to_float_string(cen) + "\n")
        f.write("endcenters\nsymmetry\n")
        for op in ops.sym_ops:
            f.write("  " + parse_triplet_for_superflip(op.triplet()) + "\n")
        f.write("endsymmetry\n")
        f.write(f"composition {ref_ctx.composition}\n\n")
        f.write("# Keywords for density modification\n")
        f.write(f"repeatmode {effective_repeatmode}\n{bestdensities_line}\nmaxcycles {int(maxcycles)}\n")
        f.write(f"delta {delta_value}\nweakratio {weakratio_value}\nBiso {biso_value}\n")
        if polish:
            f.write("polish yes\n")
        if write_randomseed:
            f.write(f"randomseed {randomseed}\n")
        for line in normalize_lines:
            f.write(line + "\n")
        if missing.strip():
            f.write(f"missing {missing.strip()}\n")
        f.write(f"searchsymmetry {searchsymmetry_value}\nderivesymmetry {derivesymmetry_value}\n")
        for line in clean_extra_superflip_keywords(extra_superflip_keywords, log):
            f.write(line + "\n")
        if str(electrons or "").strip():
            f.write(f"electrons {str(electrons).strip()}\n")
        f.write(f"dataformat {superflip_dataformat_for_mode(data_mode)}\n")
        f.write("fbegin\n")
        with observed_hkl.open("r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                # Preserve leading spaces in fixed-width Jana/Superflip reflection records.
                # With dataitemwidths 4 14 14, stripping a line such as
                # "  -9 -28   1 ..." turns it into "-9 -28   1 ...", and older
                # Superflip builds can read this as a broken "- 9" / "- 28" index.
                s = line.rstrip("\r\n")
                if s.strip() and not s.lstrip().startswith(COMMENT_PREFIXES):
                    f.write(s + "\n")
        f.write("endf\n")

def write_superflip_symmetry_input(
    inp_path: Path,
    prefix: str,
    ref_ctx: ReferenceContext,
    model_file: Path,
    output_xplor: str,
    output_format: str,
    voxel: str,
    searchsymmetry: str,
    derivesymmetry: str,
    log: Optional[Callable[[str], None]] = None,
) -> None:
    inp_path.parent.mkdir(parents=True, exist_ok=True)
    ops = ref_ctx.spacegroup.operations()
    voxel_line = superflip_voxel_keyword_line(voxel, ref_ctx.cell, log)
    if not voxel_line:
        voxel_line = xplor_voxel_keyword_from_grid(model_file)
        if log:
            log(f"  Superflip symmetry voxel grid taken from input XPLOR map: {voxel_line}")
    searchsymmetry_value = str(searchsymmetry or "average").strip().lower() or "average"
    if searchsymmetry_value not in {"no", "shift", "average"}:
        searchsymmetry_value = "average"
    derivesymmetry_value = str(derivesymmetry or "yes").strip() or "yes"
    # The symmetry-only post-processing result is consumed as a map by EDMA,
    # Jana export and later Superflip modelfiles, therefore it must be a real
    # XPLOR map even when the main Superflip run uses outputformat jana.
    fmt = "xplor"
    with inp_path.open("w", encoding="utf-8") as f:
        f.write(f"title {prefix}\n")
        f.write("perform symmetry\n")
        f.write(f'outputfile "{output_xplor}"\n')
        f.write(f"outputformat {fmt}\n")
        f.write(f"referencefile {model_file.name}\n")
        f.write("dimension  3\n")
        c = ref_ctx.cell
        f.write(f"cell {c.a:.6f} {c.b:.6f} {c.c:.6f} {c.alpha:.4f} {c.beta:.4f} {c.gamma:.4f}\n")
        f.write(f"spacegroup {ref_ctx.spacegroup_hm}\n")
        f.write("centro yes\n" if ops.is_centrosymmetric() else "centro no\n")
        f.write("centers\n")
        for cen in ops.cen_ops:
            f.write(center_vector_to_float_string(cen) + "\n")
        f.write("endcenters\nsymmetry\n")
        for op in ops.sym_ops:
            f.write("  " + parse_triplet_for_superflip(op.triplet()) + "\n")
        f.write("endsymmetry\n")
        f.write(f"composition {ref_ctx.composition}\n\n")
        f.write(f'modelfile "{model_file.name}"\n')
        f.write("polish no\n")
        f.write("maxcycles 0\n")
        f.write(f"searchsymmetry {searchsymmetry_value}\n")
        f.write(f"derivesymmetry {derivesymmetry_value}\n")
        if voxel_line:
            f.write(voxel_line + "\n")



def run_command(
    cmd: Sequence[str],
    cwd: Path,
    log_path: Path,
    log: Callable[[str], None],
    timeout: Optional[int] = None,
    stop_event: Optional[threading.Event] = None,
    allow_foreground: bool = False,
    on_output_line: Optional[Callable[[str], None]] = None,
) -> int:
    """Run an external command, writing its complete raw stdout/stderr to
    log_path unchanged, byte for byte (including any bare '\\r' console
    overwrite sequences some tools emit) -- this is a live-streaming reader,
    not a filter, and never alters what a diagnostic log-file comparison
    would see.

    on_output_line, when given, is called with each decoded line as it
    arrives WHILE the process is still running (best-effort progress
    observation only; a raised exception from it is swallowed so a parsing
    bug can never fail the run or block stop_event/timeout handling)."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    display_cmd = [Path(str(cmd[0])).name] if cmd else []
    for argument in cmd[1:]:
        text = str(argument)
        try:
            path = Path(text)
            display_cmd.append(path.name if path.is_absolute() and path.parent.resolve() == Path(cwd).resolve() else text)
        except Exception:
            display_cmd.append(text)
    log("  $ " + " ".join(display_cmd))
    with log_path.open("wb") as lf:
        def relay(raw_bytes: bytes) -> None:
            lf.write(raw_bytes)
            if on_output_line is not None:
                try:
                    on_output_line(raw_bytes.decode("utf-8", errors="replace"))
                except Exception:
                    pass

        try:
            proc = subprocess.Popen(list(cmd), cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            if allow_foreground:
                allow_external_process_foreground(proc.pid)
        except OSError as exc:
            exe = str(cmd[0]) if cmd else "<empty command>"
            if getattr(exc, "winerror", None) == 4551:
                message = (
                    f"Windows Application Control blocked this executable: {exe}\n"
                    "WinError 4551 is raised by Windows before the process starts. "
                    "This is not local SharpED inference; it means the selected Superflip/EDMA executable is not allowed by the current Windows Smart App Control, Code Integrity, WDAC, or AppLocker policy.\n"
                    "If Unblock-File does not help, the file is being blocked because it is unsigned or not trusted by policy. "
                    "Use an approved/signed Superflip/EDMA executable, select a policy-approved installed path, or ask the Windows administrator/security policy owner to allow this binary."
                )
            else:
                message = f"Could not start external command: {' '.join(str(x) for x in cmd)}\n{exc}"
            lf.write((message + "\n").encode("utf-8", errors="replace"))
            raise RuntimeError(message) from exc

        # A dedicated reader thread drains the pipe with blocking readline()
        # calls -- pipes/threads are used instead of select()/pty so this
        # works identically on a Windows PyInstaller build. The main loop
        # below never blocks on it (queue.get(timeout=...)), so stop_event
        # and the timeout deadline stay checked at the same ~0.2s cadence as
        # before, regardless of how much (or how little) output arrives.
        line_queue: "queue.Queue[Optional[bytes]]" = queue.Queue()

        def reader() -> None:
            try:
                stream = proc.stdout
                if stream is not None:
                    for raw_bytes in iter(stream.readline, b""):
                        line_queue.put(raw_bytes)
            except Exception:
                pass
            finally:
                line_queue.put(None)

        reader_thread = threading.Thread(target=reader, daemon=True)
        reader_thread.start()

        deadline = None if timeout is None else time.monotonic() + float(timeout)
        reader_done = False
        while proc.poll() is None:
            if stop_event is not None and stop_event.is_set():
                lf.write(b"\nImmediate stop requested by user.\n")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
                while True:
                    try:
                        raw_bytes = line_queue.get_nowait()
                    except queue.Empty:
                        break
                    if raw_bytes is None:
                        break
                    relay(raw_bytes)
                raise RuntimeError(f"Immediate stop requested; terminated command: {' '.join(str(x) for x in cmd)}")
            if deadline is not None and time.monotonic() > deadline:
                proc.kill()
                proc.wait(timeout=5)
                raise RuntimeError(f"Command timed out after {timeout} seconds: {' '.join(str(x) for x in cmd)}")
            drained_any = False
            while True:
                try:
                    raw_bytes = line_queue.get_nowait()
                except queue.Empty:
                    break
                if raw_bytes is None:
                    reader_done = True
                    break
                relay(raw_bytes)
                drained_any = True
            if not drained_any:
                time.sleep(0.2)
        # The process has exited; drain whatever the reader thread already
        # queued (or is about to finish queueing), bounded so a stalled
        # reader can never hang command completion.
        if not reader_done:
            drain_deadline = time.monotonic() + 5.0
            while time.monotonic() < drain_deadline:
                try:
                    raw_bytes = line_queue.get(timeout=0.2)
                except queue.Empty:
                    continue
                if raw_bytes is None:
                    break
                relay(raw_bytes)
        reader_thread.join(timeout=2.0)
    if proc.returncode != 0:
        tail = ""
        try:
            tail = "\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-80:])
        except Exception:
            pass
        raise RuntimeError(f"Command failed with code {proc.returncode}: {' '.join(str(x) for x in cmd)}\nLog: {log_path}\n{tail}")
    return proc.returncode

def resolve_executable_for_validation(exe: str) -> Optional[Path]:
    raw = str(exe or "").strip().strip('"')
    if not raw:
        return None
    p = Path(raw).expanduser()
    if p.is_file():
        return p.resolve()
    found = shutil.which(raw)
    return Path(found).resolve() if found else None

def warn_if_windows_unsigned_exe(exe: str, label: str) -> str:
    if sys.platform != "win32":
        return ""
    path = resolve_executable_for_validation(exe)
    if path is None:
        return f"{label} executable not found: {exe}"
    try:
        import subprocess as _subprocess
        ps = (
            "if ((Get-AuthenticodeSignature -LiteralPath $args[0]).Status -eq 'NotSigned') "
            "{ 'NotSigned' }"
        )
        proc = _subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps, str(path)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if "NotSigned" in (proc.stdout or ""):
            return (
                f"{label} executable is not digitally signed: {path}. "
                "Windows Smart App Control/WDAC may block it. Use a signed or policy-approved executable if the run fails with WinError 4551."
            )
    except Exception:
        pass
    return ""

def run_superflip_cycle(cycle_dir: Path, prefix: str, ref_ctx: ReferenceContext, observed_hkl: Path, model_file: Optional[Path], reference_file: Optional[Path], reference_format: str, superflip_exe: str, perform_algorithm: str, output_format: str, write_auxiliary_outputs: bool, export_superflip_xplor: bool, export_superflip_ccp4: bool, export_superflip_jana: bool, voxel: str, bestdensities_count: int, bestdensities_metric: str, bestdensities_symmetry: bool, polish: bool, maxcycles: int, repeatmode: int, randomseed: str, delta: str, weakratio: str, biso: str, reflection_data_mode: str, normalize: str, nresshells: int, missing: str, searchsymmetry: str, derivesymmetry: str, electrons: str, dataitemwidths: str, extra_superflip_keywords: str, log: Callable[[str], None], stop_event: Optional[threading.Event] = None, on_output_line: Optional[Callable[[str], None]] = None) -> Path:
    cycle_dir.mkdir(parents=True, exist_ok=True)
    output_name = f"{prefix}.xplor"
    inp = cycle_dir / f"{prefix}.inflip"
    log_path = cycle_dir / f"{prefix}.superflip.log"
    model_for_input: Optional[Path] = None
    if model_file is not None:
        repeatmode = 1
        suffix = model_file.suffix.lower() or ".dat"
        if suffix == ".xplor":
            viewer_model = cycle_dir / "current_modelfile.xplor"
            if model_file.resolve() != viewer_model.resolve():
                shutil.copy2(model_file, viewer_model)
            model_for_input = cycle_dir / "current_modelfile_for_superflip.xplor"
            normalize_xplor_for_superflip_modelfile(model_file, model_for_input, log)
            log(f"  Superflip reads normalized XPLOR modelfile: {model_for_input}")
            log(f"  Original/viewer XPLOR modelfile kept as: {viewer_model}")
        elif suffix == ".cif":
            model_for_input = cycle_dir / "current_modelfile.cif"
            if model_file.resolve() != model_for_input.resolve():
                shutil.copy2(model_file, model_for_input)
            log(f"  Superflip reads CIF modelfile by .cif extension, without an explicit CIF format keyword: {model_for_input}")
        elif suffix == ".ccp4":
            model_for_input = cycle_dir / "current_modelfile.ccp4"
            if model_file.resolve() != model_for_input.resolve():
                shutil.copy2(model_file, model_for_input)
            log(f"  Superflip reads CCP4 modelfile: {model_for_input}")
        else:
            raise ValueError(
                "Superflip modelfile must be an XPLOR/CCP4 density map or a CIF structure file. "
                f"Unsupported modelfile: {model_file}"
            )
    reference_for_input: Optional[Path] = None
    if reference_file is not None:
        suffix = ".xplor" if str(reference_format or "").strip().lower() == "xplor" else reference_file.suffix.lower()
        # Keep the Superflip referencefile separate from ref_ctx.work_ref_cif.
        # In Jana2020 .inflip mode ref_ctx.work_ref_cif can be a synthetic metadata-only CIF
        # named referencefile.cif with zero atoms.  Using the same filename would overwrite
        # the explicit user-selected Superflip reference CIF and Superflip would stop with
        # "no atoms found in the CIF file".
        reference_for_input = cycle_dir / f"superflip_referencefile{suffix or '.dat'}"
        if reference_file.resolve() != reference_for_input.resolve():
            shutil.copy2(reference_file, reference_for_input)
    work_ref_dst = cycle_dir / ref_ctx.work_ref_cif.name
    if reference_for_input is None or work_ref_dst.resolve() != reference_for_input.resolve():
        shutil.copy2(ref_ctx.work_ref_cif, work_ref_dst)
    write_superflip_input(inp, prefix, ref_ctx, observed_hkl, output_name, model_for_input, reference_for_input, reference_format, perform_algorithm, output_format, write_auxiliary_outputs, export_superflip_xplor, export_superflip_ccp4, export_superflip_jana, voxel, bestdensities_count, bestdensities_metric, bestdensities_symmetry, polish, maxcycles, repeatmode, randomseed, delta, weakratio, biso, reflection_data_mode, normalize, nresshells, missing, searchsymmetry, derivesymmetry, electrons, dataitemwidths, extra_superflip_keywords, log)
    log(f"[Superflip] Running {inp.name}")
    out = cycle_dir / output_name
    for stale in (out, cycle_dir / f"{prefix}.sflog"):
        try:
            if stale.is_file():
                stale.unlink()
                log(f"  Removed stale Superflip output before run: {stale.name}")
        except Exception as exc:
            log(f"  Could not remove stale Superflip output {stale}: {exc}")
    run_started_at = time.time()
    run_command(
        [superflip_exe, inp.name],
        cwd=cycle_dir,
        log_path=log_path,
        log=log,
        stop_event=stop_event,
        allow_foreground=True,
        on_output_line=on_output_line,
    )
    if not out.is_file() or out.stat().st_size == 0:
        tail = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-120:]
        raise RuntimeError(f"Superflip did not create expected XPLOR map: {out}\n" + "\n".join(tail))
    try:
        if out.stat().st_mtime < run_started_at - 1.0:
            tail = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-120:]
            raise RuntimeError(
                f"Superflip output map is older than the current run and was probably stale: {out}\n" + "\n".join(tail)
            )
    except RuntimeError:
        raise
    except Exception:
        pass
    log("[Superflip] Completed")
    return out

def run_superflip_symmetrize_map(
    cycle_dir: Path,
    prefix: str,
    ref_ctx: ReferenceContext,
    input_map: Path,
    superflip_exe: str,
    output_format: str,
    voxel: str,
    searchsymmetry: str,
    derivesymmetry: str,
    log: Callable[[str], None],
    stop_event: Optional[threading.Event] = None,
) -> Path:
    sym_dir = cycle_dir / "superflip_symmetrized_deblur"
    sym_dir.mkdir(parents=True, exist_ok=True)
    model_for_input = sym_dir / "deblurred_modelfile_for_symmetry.xplor"
    normalize_xplor_for_superflip_modelfile(input_map, model_for_input, log)
    output_name = f"{prefix}.xplor"
    inp = sym_dir / f"{prefix}.inflip"
    log_path = sym_dir / f"{prefix}.superflip.log"
    out = sym_dir / output_name
    write_superflip_symmetry_input(
        inp_path=inp,
        prefix=prefix,
        ref_ctx=ref_ctx,
        model_file=model_for_input,
        output_xplor=output_name,
        output_format=output_format,
        voxel=voxel,
        searchsymmetry=searchsymmetry,
        derivesymmetry=derivesymmetry,
        log=log,
    )
    log(f"[Superflip symmetry] Running {inp.name}")
    for stale in (out, sym_dir / f"{prefix}.sflog"):
        try:
            if stale.is_file():
                stale.unlink()
                log(f"  Removed stale Superflip symmetry output before run: {stale.name}")
        except Exception as exc:
            log(f"  Could not remove stale Superflip symmetry output {stale}: {exc}")
    run_started_at = time.time()
    run_command(
        [superflip_exe, inp.name],
        cwd=sym_dir,
        log_path=log_path,
        log=log,
        stop_event=stop_event,
        allow_foreground=True,
    )
    if not out.is_file() or out.stat().st_size == 0:
        tail = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-120:]
        raise RuntimeError(f"Superflip did not create expected symmetrized XPLOR map: {out}\n" + "\n".join(tail))
    try:
        if out.stat().st_mtime < run_started_at - 1.0:
            tail = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-120:]
            raise RuntimeError(
                f"Superflip symmetrized map is older than the current run and was probably stale: {out}\n" + "\n".join(tail)
            )
    except RuntimeError:
        raise
    except Exception:
        pass
    final_map = cycle_dir / f"{prefix}.xplor"
    if out.resolve() != final_map.resolve():
        shutil.copy2(out, final_map)
    log(f"[Superflip symmetry] Completed · {final_map.name}")
    return final_map

def sharped_elements_from_composition(composition: str) -> str:
    elements: List[str] = []
    for elem in re.findall(r"([A-Z][a-z]?|D)", str(composition or "")):
        elem = clean_element_symbol(elem)
        if elem in {"H", "D", "X"} or elem in elements:
            continue
        elements.append(elem)
    return " ".join(elements) or "C N O"

def run_sharped_deblur(
    input_map: Path,
    output_map: Path,
    base_url: str,
    api_token: str,
    model: str,
    elements: str,
    outres: float,
    max_upload_mb: float,
    timeout_seconds: int,
    poll_seconds: int,
    max_polls: int,
    log: Callable[[str], None],
    stop_event: Optional[threading.Event] = None,
    progress: Optional[Callable[[str], None]] = None,
) -> Path:
    output_map.parent.mkdir(parents=True, exist_ok=True)
    log_path = output_map.parent / f"{output_map.stem}.sharped.log"
    log_lines: List[str] = []

    def log_both(line: str) -> None:
        log_lines.append(line)
        if progress is not None:
            lowered = str(line).lower()
            if "uploading" in lowered:
                progress("uploading")
            elif "downloading" in lowered:
                progress("downloading")
            elif "server status:" in lowered:
                status = lowered.split("server status:", 1)[1].strip()
                progress("completed" if status in {"completed", "complete", "done", "ready", "finished", "success", "succeeded"} else "processing")
            elif "[sharped] processing" in lowered:
                progress("processing")
            elif "[sharped] completed" in lowered:
                progress("completed")
        try:
            log(line)
        finally:
            log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    timeout = max(600, int(timeout_seconds))
    log_both(f"SharpED server HTTP timeout: {timeout} seconds")
    if stop_event is not None and stop_event.is_set():
        raise RuntimeError("Immediate stop requested.")
    if max_upload_mb <= 0 and "jana.fzu.cz" in str(base_url).lower():
        input_bytes = int(Path(input_map).stat().st_size)
        public_limit_bytes = 100_000_000
        if input_bytes > public_limit_bytes:
            raise RuntimeError(
                "The selected XPLOR map is larger than the current public SharpED server upload limit "
                f"({input_bytes / 1_000_000:.1f} MB > 100 MB). Set 'Max upload size MB' to 100, "
                "or use a private SharpED endpoint with a higher upload limit."
            )
    upload_map = prepare_xplor_for_sharped_upload(input_map, output_map.parent, max_upload_mb, log_both)
    if upload_map != input_map:
        log_both(f"SharpED upload map: {upload_map}")
    client = SharpEDServerClient(base_url=base_url, timeout=float(timeout))
    selected_model = model.strip()
    if not selected_model or selected_model.lower() in {"default", "server default", "sharped default"}:
        models = client.get_models(log=log_both)
        selected_model = models.default_model or "SharpED latest"
        if models.models:
            log_both("SharpED server models: " + ", ".join(models.models))
        log_both(f"SharpED server default model: {selected_model}")

    client.execute(
        file_path=upload_map,
        bearer_token=api_token.strip(),
        out_path=output_map,
        elements=elements.strip() or "C N O",
        model=selected_model,
        outres=outres,
        poll_seconds=poll_seconds,
        max_polls=max_polls,
        log=log_both,
        stop_event=stop_event,
    )
    if not output_map.is_file() or output_map.stat().st_size == 0:
        raise RuntimeError(f"SharpED did not create output map: {output_map}")
    log_both(f"[SharpED] Downloaded {output_map.name}")
    return output_map

def parse_edma_coo(coo_file: Path) -> Tuple[np.ndarray, np.ndarray]:
    atoms: List[List[float]] = []
    densities: List[float] = []
    if not coo_file.exists():
        return np.empty((0, 3), dtype=np.float64), np.empty((0,), dtype=np.float64)
    with coo_file.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.strip().startswith("#") or not line.strip():
                continue
            try:
                vals = [float(p) for p in line.split()]
                if len(vals) < 4:
                    continue
                if vals[0] > 1 and float(vals[0]).is_integer() and len(vals) >= 5 and vals[1] < 1.5:
                    atoms.append([vals[1], vals[2], vals[3]])
                    densities.append(vals[4])
                else:
                    atoms.append([vals[0], vals[1], vals[2]])
                    densities.append(vals[3] if len(vals) > 3 else 1.0)
            except Exception:
                continue
    return np.asarray(atoms, dtype=np.float64), np.asarray(densities, dtype=np.float64)

def assign_elements_by_density(density: np.ndarray, heavy: str = "Ag", light: str = "B") -> List[str]:
    if density is None or len(density) == 0:
        return []
    vals = np.asarray(density, dtype=np.float64)
    vals = np.nan_to_num(vals, nan=0.0, posinf=0.0, neginf=0.0)
    if len(vals) == 1:
        return [heavy]
    shifted = vals - float(np.min(vals))
    x = np.log1p(np.maximum(shifted, 0.0))
    c1 = float(np.quantile(x, 0.25)); c2 = float(np.quantile(x, 0.75))
    if abs(c2 - c1) < 1e-12:
        high = x >= float(np.median(x))
    else:
        for _ in range(32):
            lab = np.abs(x - c2) < np.abs(x - c1)
            c1n = float(np.mean(x[~lab])) if np.any(~lab) else c1
            c2n = float(np.mean(x[lab])) if np.any(lab) else c2
            if abs(c1n - c1) < 1e-9 and abs(c2n - c2) < 1e-9:
                c1, c2 = c1n, c2n
                break
            c1, c2 = c1n, c2n
        if c1 > c2:
            c1, c2 = c2, c1
        high = x >= 0.5 * (c1 + c2)
    return [heavy if bool(h) else light for h in high]

def element_atomic_number(elem: str) -> int:
    elem = clean_element_symbol(elem)
    try:
        gemmi_elem = gemmi.Element(elem)
        z = int(getattr(gemmi_elem, "atomic_number", 0) or getattr(gemmi_elem, "ordinal", 0) or 0)
        if z > 0:
            return z
    except Exception:
        pass
    return int(ATOMIC_NUMBER_HINTS.get(elem, 0))

def scaled_element_quotas(target_counts: Sequence[Tuple[str, int]], n_items: int) -> Dict[str, int]:
    clean_targets = [(clean_element_symbol(e), int(c)) for e, c in target_counts if int(c) > 0 and clean_element_symbol(e) not in {"H", "D"}]
    if n_items <= 0 or not clean_targets:
        return {}
    total = sum(c for _, c in clean_targets)
    if total <= 0:
        return {}
    raw = [(elem, n_items * count / total) for elem, count in clean_targets]
    quotas = {elem: int(math.floor(value)) for elem, value in raw}
    remaining = n_items - sum(quotas.values())
    for elem, _ in sorted(raw, key=lambda item: item[1] - math.floor(item[1]), reverse=True):
        if remaining <= 0:
            break
        quotas[elem] += 1
        remaining -= 1
    if n_items >= len(clean_targets):
        for elem, _ in clean_targets:
            if quotas.get(elem, 0) > 0:
                continue
            donor = max((e for e in quotas if quotas[e] > 1), key=lambda e: quotas[e], default="")
            if donor:
                quotas[donor] -= 1
                quotas[elem] = 1
    return quotas

def assign_elements_by_reference_composition(
    density: np.ndarray, ref_atoms: Sequence[AtomSite], composition: str = ""
) -> List[str]:
    if density is None or len(density) == 0:
        return []
    counts, order = atom_element_counts(ref_atoms)
    target_counts = [(elem, counts[elem]) for elem in order if counts.get(elem, 0) > 0]
    if not target_counts:
        # No reference-structure atom sites to draw element counts from --
        # the common case when the run has no external reference file, just
        # an entered composition. Fall back to that composition itself
        # instead of dropping straight to the generic Ag/B density-threshold
        # placeholder below, so the written CIF's elements match what was
        # actually entered/declared, the same way EDMA's own m40 output
        # already does via its own "composition" keyword.
        target_counts = parse_composition_counts(composition)
    quotas = scaled_element_quotas(target_counts, len(density))
    if not quotas:
        return assign_elements_by_density(density, heavy="Ag", light="B")
    ranked = sorted(quotas, key=lambda elem: element_atomic_number(elem), reverse=True)
    labels_by_density: List[str] = []
    for elem in ranked:
        labels_by_density.extend([elem] * quotas.get(elem, 0))
    if len(labels_by_density) < len(density):
        labels_by_density.extend([ranked[-1]] * (len(density) - len(labels_by_density)))
    labels_by_density = labels_by_density[:len(density)]

    assigned = [""] * len(density)
    vals = np.nan_to_num(np.asarray(density, dtype=np.float64), nan=0.0, posinf=0.0, neginf=0.0)
    for peak_idx, elem in zip(np.argsort(vals)[::-1], labels_by_density):
        assigned[int(peak_idx)] = elem
    return assigned

def symmetry_merge_peaks(frac: np.ndarray, density: np.ndarray, ref_ctx: ReferenceContext, merge_distance_a: float) -> Tuple[np.ndarray, np.ndarray]:
    if len(frac) == 0:
        return frac, density
    order = np.argsort(density)[::-1]
    selected: List[np.ndarray] = []
    selected_d: List[float] = []
    selected_orbits: List[List[np.ndarray]] = []
    ops = full_spacegroup_ops(ref_ctx.spacegroup)
    if not ops:
        ops = list(ref_ctx.spacegroup.operations().sym_ops)
    for idx in order:
        f = wrap_frac(frac[idx])
        orbit = [apply_gemmi_op(op, f) for op in ops]
        duplicate = False
        for old_orbit in selected_orbits:
            min_orbit_distance = min(
                frac_distance_angstrom(ref_ctx.cell, new_pos, old_pos)
                for new_pos in orbit
                for old_pos in old_orbit
            )
            if min_orbit_distance < merge_distance_a:
                duplicate = True
                break
        if not duplicate:
            selected.append(f)
            selected_d.append(float(density[idx]))
            selected_orbits.append(orbit)
    return np.asarray(selected, dtype=np.float64), np.asarray(selected_d, dtype=np.float64)

def run_edma_on_xplor(
    xplor_map: Path,
    out_dir: Path,
    prefix: str,
    ref_ctx: ReferenceContext,
    plimit_sigma: float,
    merge_distance_a: float,
    edma_exe: str,
    log: Callable[[str], None],
    stop_event: Optional[threading.Event] = None,
    maxima: str = "all",
    fullcell: str = "no",
    numberofatoms: str = "composition",
    centerofcharge: bool = True,
    chlimit: str = "0.2500",
    chlimlist: str = "0.0057 relative",
    extra_edma_keywords: str = "",
    structure_format: str = "cif",
    write_m40: bool = True,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    inp = out_dir / f"{prefix}_edma.inp"
    outbase = f"{prefix}_edma"
    coo = out_dir / f"{outbase}.coo"
    edma_log = out_dir / f"{outbase}.log"
    cif = out_dir / f"{outbase}.cif"
    map_copy = out_dir / xplor_map.name
    normalize_xplor_for_edma(xplor_map, map_copy, log)
    absolute_plimit, map_sigma = edma_absolute_plimit(map_copy, plimit_sigma)
    c = ref_ctx.cell
    with inp.open("w", encoding="utf-8") as f:
        f.write(f"inputfile {map_copy.name}\noutputbase {outbase}\n")
        f.write(f"cell {c.a} {c.b} {c.c} {c.alpha} {c.beta} {c.gamma}\n")
        ops = ref_ctx.spacegroup.operations()
        f.write("centers\n")
        for cen in ops.cen_ops:
            f.write(center_vector_to_float_string(cen) + "\n")
        f.write("endcenters\nsymmetry\n")
        for op in ops.sym_ops:
            f.write("  " + parse_triplet_for_superflip(op.triplet()) + "\n")
        f.write("endsymmetry\n")
        maxima_value = str(maxima or "all").strip() or "all"
        fullcell_value = str(fullcell or "no").strip().lower() or "no"
        if fullcell_value not in {"yes", "no"}:
            fullcell_value = "no"
        f.write(f"scale fractional\nmaxima {maxima_value}\nfullcell {fullcell_value}\n")
        f.write(f"plimit {float(absolute_plimit):g}\n")
        f.write(f"composition {ref_ctx.composition}\n")
        if str(numberofatoms or "").strip():
            f.write(f"numberofatoms {str(numberofatoms).strip()}\n")
        f.write("centerofcharge yes\n" if centerofcharge else "centerofcharge no\n")
        if str(chlimit or "").strip():
            f.write(f"chlimit {str(chlimit).strip()}\n")
        if str(chlimlist or "").strip():
            f.write(f"chlimlist {str(chlimlist).strip()}\n")
        if write_m40:
            # Jana-format peaks (m40), requested only when this run could
            # actually be handed off to Jana2020 (a jana_inflip is
            # configured) -- otherwise it is just another per-cycle file
            # nothing will ever read.
            f.write("m40forjana yes\n")
            f.write(f"writem40 {outbase}.m40\n")
        for line in clean_keyword_lines(extra_edma_keywords):
            f.write(line + "\n")
    map_label = result_map_label("deblurred" if "deblur" in prefix.lower() else "superflip")
    log(f"[EDMA] {map_label} · threshold {plimit_sigma:g} σ")
    if map_sigma is None:
        log(f"  plimit={float(absolute_plimit):g}")
    else:
        log(f"  map σ={map_sigma:g} · plimit={float(absolute_plimit):g}")
    run_command([edma_exe, inp.name], cwd=out_dir, log_path=edma_log, log=log, stop_event=stop_event)
    log_text = edma_log.read_text(encoding="utf-8", errors="replace") if edma_log.is_file() else ""
    lower_log = log_text.lower()
    edma_failed = (
        "error reading keyword" in lower_log
        or ("there were" in lower_log and "errors in the input file" in lower_log)
        or "stop error" in lower_log
    )
    if edma_failed:
        tail = "\n".join(log_text.splitlines()[-80:])
        raise RuntimeError(f"EDMA failed for {xplor_map.name}.\nLog: {edma_log}\n{tail}")
    if not coo.is_file() or coo.stat().st_size == 0:
        tail = "\n".join(log_text.splitlines()[-80:])
        raise RuntimeError(f"EDMA did not create coordinate output: {coo}\nLog: {edma_log}\n{tail}")
    frac, dens = parse_edma_coo(coo)
    if len(frac) == 0:
        log(f"EDMA coordinate output contains no peaks above plimit for {xplor_map.name}; writing empty CIF.")
        write_structure_bundle(cif, ref_ctx.cell, ref_ctx.spacegroup, ref_ctx.spacegroup_hm, [], structure_format)
        return cif
    frac, dens = symmetry_merge_peaks(frac, dens, ref_ctx, merge_distance_a)
    elements = assign_elements_by_reference_composition(dens, ref_ctx.atoms, ref_ctx.composition)
    atoms = [AtomSite(label=f"{elements[i]}{i+1}", element=elements[i], frac=frac[i], density=float(dens[i])) for i in range(len(frac))]
    write_structure_bundle(cif, ref_ctx.cell, ref_ctx.spacegroup, ref_ctx.spacegroup_hm, atoms, structure_format)
    return cif

def parse_superflip_log_metrics(log_path: Path) -> SuperflipLogMetrics:
    """Extract the saved-density metrics from a Superflip log.

    Superflip can perform several repeatmode attempts in one .sflog.  The map
    that Jana/Phase Studio actually uses is described by the last printed
    "Properties of the saved density" table, not necessarily by attempt 1
    and not necessarily by the last attempted run.  This parser therefore keeps
    the last valid table row and records the saved run number together with
    Rvalue, Peaks, Symm. and Der.SG.
    """
    metrics = SuperflipLogMetrics()
    if not Path(log_path).is_file():
        return metrics

    text_log = Path(log_path).read_text(encoding="utf-8", errors="replace")
    lines = text_log.splitlines()

    def as_float(value: str) -> Optional[float]:
        try:
            return float(str(value).replace(",", "."))
        except Exception:
            return None

    def is_float_token(value: str) -> bool:
        return as_float(value) is not None

    # Parse all saved-density summary tables and keep the last valid row.
    in_saved_density_table = False
    for line in lines:
        if ("Run" in line and "Rvalue" in line and "Peaks" in line and "Symm" in line):
            in_saved_density_table = True
            continue
        if not in_saved_density_table:
            continue
        tokens = line.split()
        if not tokens:
            in_saved_density_table = False
            continue
        if len(tokens) < 4:
            continue
        try:
            saved_run = int(float(tokens[0]))
        except Exception:
            continue
        rvalue = as_float(tokens[1])
        peaks = as_float(tokens[2])
        symm = as_float(tokens[3])
        if rvalue is None or peaks is None or symm is None:
            continue
        metrics.saved_run = saved_run
        metrics.rvalue = rvalue
        metrics.peaks = peaks
        metrics.symm = symm
        # Standard Jana/Superflip table: Run Rvalue Peaks Symm. Der.SG
        if len(tokens) >= 5 and not is_float_token(tokens[4]):
            metrics.derived_sg = tokens[4]
        # Extended variants can contain Ref.match near the end.
        if len(tokens) >= 8 and all(is_float_token(t) for t in tokens[-4:]):
            try:
                metrics.ref_match = float(tokens[-4])
            except Exception:
                pass

    sr_re = re.compile(r"Success rate(?:\s*\(SR\))?\s*\[%\]\s*:\s*([-+]?\d+(?:\.\d+)?)", re.IGNORECASE)
    mean_re = re.compile(r"Mean cycles per convergence\(beta\)\s*:\s*([-+]?\d+(?:\.\d+)?)", re.IGNORECASE)
    score_re = re.compile(r"\bScore:\s*([-+]?\d+(?:\.\d+)?)")
    fom_re = re.compile(r"\bFOM\b[^-+0-9]*([-+]?\d+(?:\.\d+)?)", re.IGNORECASE)
    for line in lines:
        m = sr_re.search(line)
        if m:
            try:
                metrics.success_rate = float(m.group(1))
            except Exception:
                pass
        m = mean_re.search(line)
        if m:
            try:
                metrics.mean_cycles = float(m.group(1))
            except Exception:
                pass
        m = score_re.search(line)
        if m:
            try:
                metrics.fom = float(m.group(1))
            except Exception:
                pass
        m = fom_re.search(line)
        if m:
            try:
                metrics.fom = float(m.group(1))
            except Exception:
                pass

    return metrics

def parse_superflip_cycle_metrics(cycle_dir: Path, prefix: str) -> SuperflipLogMetrics:
    candidates = [
        Path(cycle_dir) / f"{prefix}.sflog",
        Path(cycle_dir) / f"{prefix}.superflip.log",
    ]
    # Some Superflip builds use the title/output base rather than the input stem.
    candidates.extend(sorted(Path(cycle_dir).glob("*.sflog"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True))
    seen = set()
    fallback = SuperflipLogMetrics()
    for candidate in candidates:
        key = str(candidate.resolve()) if candidate.exists() else str(candidate)
        if key in seen:
            continue
        seen.add(key)
        m = parse_superflip_log_metrics(candidate)
        if m.rvalue is not None or m.peaks is not None or m.symm is not None:
            return m
        fallback = m
    return fallback


def write_metrics_csv(path: Path, results: Sequence[CycleResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "cycle",
            "model_source",
            "model_in",
            "model_rmsd_A",
            "superflip_map",
            "superflip_edma_cif",
            "superflip_rmsd_A",
            "deblur_map",
            "deblur_edma_cif",
            "deblur_rmsd_A",
            "superflip_saved_run",
            "superflip_rvalue",
            "superflip_peaks",
            "superflip_symm",
            "superflip_derived_sg",
            "superflip_ref_match",
            "superflip_fom",
            "superflip_success_rate_percent",
            "superflip_mean_cycles",
            "recycle_map_correlation",
            "omit_superflip_correlation",
            "omit_superflip_rfree",
            "omit_deblur_correlation",
            "omit_deblur_rfree",
            "superflip_recall",
            "superflip_precision",
            "superflip_heavy_atom_count",
            "deblur_recall",
            "deblur_precision",
            "deblur_heavy_atom_count",
            "powder_repartition_avg_change_percent",
            "intensity_correction_avg_change_percent",
        ])
        for r in results:
            w.writerow([
                r.cycle,
                r.model_source,
                "" if r.model_in is None else r.model_in,
                "" if r.model_metric is None else r.model_metric,
                r.superflip_map,
                r.superflip_edma_cif,
                "" if r.superflip_metric is None else r.superflip_metric,
                r.deblur_map,
                r.deblur_edma_cif,
                "" if r.deblur_metric is None else r.deblur_metric,
                "" if r.superflip_saved_run is None else r.superflip_saved_run,
                "" if r.superflip_rvalue is None else r.superflip_rvalue,
                "" if r.superflip_peaks is None else r.superflip_peaks,
                "" if r.superflip_symm is None else r.superflip_symm,
                r.superflip_derived_sg or "",
                "" if r.superflip_ref_match is None else r.superflip_ref_match,
                "" if r.superflip_fom is None else r.superflip_fom,
                "" if r.superflip_success_rate is None else r.superflip_success_rate,
                "" if r.superflip_mean_cycles is None else r.superflip_mean_cycles,
                "" if r.recycle_map_correlation is None else r.recycle_map_correlation,
                "" if r.omit_superflip_correlation is None else r.omit_superflip_correlation,
                "" if r.omit_superflip_rfree is None else r.omit_superflip_rfree,
                "" if r.omit_deblur_correlation is None else r.omit_deblur_correlation,
                "" if r.omit_deblur_rfree is None else r.omit_deblur_rfree,
                "" if r.superflip_recall is None else r.superflip_recall,
                "" if r.superflip_precision is None else r.superflip_precision,
                "" if r.superflip_heavy_atom_count is None else r.superflip_heavy_atom_count,
                "" if r.deblur_recall is None else r.deblur_recall,
                "" if r.deblur_precision is None else r.deblur_precision,
                "" if r.deblur_heavy_atom_count is None else r.deblur_heavy_atom_count,
                "" if r.powder_repartition_avg_change_percent is None else r.powder_repartition_avg_change_percent,
                "" if r.intensity_correction_avg_change_percent is None else r.intensity_correction_avg_change_percent,
            ])


# -----------------------------------------------------------------------------
# Qt GUI
# -----------------------------------------------------------------------------

CONFIG_FORM_VERTICAL_SPACING = 5
CONFIG_FORM_HORIZONTAL_SPACING = 14
CONFIG_PAGE_MARGIN_HORIZONTAL = 10
CONFIG_PAGE_MARGIN_VERTICAL = 8
CONFIG_MAJOR_SECTION_SPACING = 10
CONFIG_GUIDED_GROUP_MARGINS = (8, 5, 8, 6)
CONFIG_GUIDED_GROUP_SPACING = 5
CONFIG_BROWSE_BUTTON_WIDTH = 28
CONFIG_CONTROL_VISIBLE_HEIGHT = 28


class MiddleElidedLabel(QLabel):
    """Single-line label that keeps its complete value in the tooltip."""

    def __init__(self, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._full_text = str(text)
        self.setToolTip(self._full_text)
        self.setMinimumWidth(1)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._update_elided_text()

    def _update_elided_text(self) -> None:
        available_width = max(1, self.contentsRect().width())
        QLabel.setText(
            self,
            self.fontMetrics().elidedText(self._full_text, Qt.ElideMiddle, available_width),
        )

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._update_elided_text()


class PathRow(QWidget):
    def __init__(self, label: str, default: str = "", mode: str = "file", file_filter: str = "All files (*)") -> None:
        super().__init__()
        self.mode = mode
        self.file_filter = file_filter
        self.on_change: Optional[Callable[[], None]] = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.label_text = str(label)
        self.form_label: Optional[QWidget] = None
        self._base_tooltip = ""
        self.edit = QLineEdit(default)
        self.button = QPushButton("…")
        self.button.setObjectName("pathBrowseButton")
        self.button.setFixedSize(CONFIG_BROWSE_BUTTON_WIDTH, CONFIG_CONTROL_VISIBLE_HEIGHT)
        layout.addWidget(self.edit, 1)
        layout.addWidget(self.button)
        self.button.clicked.connect(self.browse)
        self.edit.editingFinished.connect(self._notify_changed)
        self._refresh_path_tooltip()

    def browse(self) -> None:
        if self.mode == "dir":
            path = QFileDialog.getExistingDirectory(self, "Select directory", self.edit.text() or str(Path.cwd()))
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Select file", self.edit.text() or str(Path.cwd()), self.file_filter)
        if path:
            self.set_value(path)
            self._notify_changed()

    def _notify_changed(self) -> None:
        self.edit.setCursorPosition(0)
        self._refresh_path_tooltip()
        if self.on_change is not None:
            self.on_change()

    def value(self) -> str:
        return self.edit.text().strip()

    def set_value(self, value: str) -> None:
        self.edit.setText(str(value))
        self.edit.setCursorPosition(0)
        self._refresh_path_tooltip()

    def set_tooltip(self, tooltip: str) -> None:
        self._base_tooltip = str(tooltip).strip()
        self._refresh_path_tooltip()
        self.button.setToolTip("Browse for " + self.label_text)

    def set_form_label(self, label: Optional[QWidget]) -> None:
        self.form_label = label
        if label is not None:
            label.setEnabled(self.isEnabled())

    def setEnabled(self, enabled: bool) -> None:  # type: ignore[override]
        super().setEnabled(enabled)
        if self.form_label is not None:
            self.form_label.setEnabled(enabled)

    def _refresh_path_tooltip(self) -> None:
        path = self.edit.text().strip()
        parts = [part for part in (self._base_tooltip, f"Path: {path}" if path else "") if part]
        tooltip = "\n\n".join(parts)
        self.setToolTip(tooltip)
        self.edit.setToolTip(tooltip)

INPUT_TOOLTIPS = {
    "input_source_mode": "Choose whether reflections come from Jana2020 .inflip, selected overrides, or an external HKL file.",
    "jana_inflip": "Jana2020 Superflip input file. In Jana modes its fbegin/endf reflection block is the default HKL source, and its cell/space-group/composition keywords can provide the reference metadata.",
    "hkl": "External reflection file. In Jana override mode it replaces only the fbegin/endf reflection block; in external mode it is the required reflection source.",
    "metadata_source": "Authoritative source for unit cell, space group and composition.",
    "manual_cell_a": "Manual unit-cell length a in angstrom.",
    "manual_cell_b": "Manual unit-cell length b in angstrom.",
    "manual_cell_c": "Manual unit-cell length c in angstrom.",
    "manual_cell_alpha": "Manual unit-cell angle alpha in degrees.",
    "manual_cell_beta": "Manual unit-cell angle beta in degrees.",
    "manual_cell_gamma": "Manual unit-cell angle gamma in degrees.",
    "manual_spacegroup_number": "International Tables space-group number from 1 to 230.",
    "manual_spacegroup_symbol": "Recognized Hermann-Mauguin space-group symbol.",
    "manual_composition": "Composition in the existing Superflip syntax, for example Ag196 S108 O40 B1000.",
    "reference_cif": "Optional external reference. CIF/INS/RES files can provide metadata and atom sites; Jana/XPLOR/CCP4 maps can be Superflip reference densities.",
    "first_cycle_modelfile": "Optional external density or structure model for cycle 1. Supported Superflip modelfile inputs are XPLOR, CCP4 and CIF.",
    "work_dir": "Output directory for generated HKL files, Superflip inputs, maps, EDMA results, logs and metrics.",
    "superflip_exe": "Absolute path to the original Jana2020 Superflip executable. Default: C:\\Jana2020\\SUPERFLIP\\superflip_original.exe. Do not select the Phase Studio wrapper named superflip.exe.",
    "edma_exe": "Absolute path to the Jana2020 EDMA executable used for peak extraction and structure export from XPLOR density maps. Default: C:\\Jana2020\\SUPERFLIP\\EDMA.exe.",
    "workflow_preset": "Applies a bundle of starting values for a common crystallographic workflow. 'Recommended' is a general-purpose baseline (matches the built-in defaults); the others tune settings for a specific sample type. All values remain individually editable afterward, and 'Custom' leaves everything untouched.",
    "cycles": "Number of iterative Superflip → EDMA → SharpED → EDMA cycles to run.",
    "composition_override": "Optional Superflip composition string. Leave blank to derive composition from the reference CIF formula or atom list.",
    "plimit_superflip": "Peak threshold as a multiplier of the XPLOR map sigma. Phase Studio converts it to EDMA's absolute 'plimit <value>'.",
    "plimit_deblur": "Peak threshold as a multiplier of the XPLOR map sigma. Phase Studio converts it to EDMA's absolute 'plimit <value>'.",
    "merge_distance": "Distance tolerance in Angstrom for reducing EDMA maxima to one representative per full space-group orbit before writing the CIF asymmetric unit.",
    "edma_maxima": "EDMA maxima keyword. 'all' lists all density maxima above plimit; use more restrictive EDMA syntax only when you want to limit peak picking.",
    "edma_fullcell": "EDMA fullcell keyword. 'no' writes symmetry-independent maxima when the supplied space-group symmetry is correct; 'yes' lists the full unit cell.",
    "edma_numberofatoms": "EDMA numberofatoms keyword for structure export. 'composition' asks EDMA to export atom counts consistent with the chemical composition.",
    "edma_centerofcharge": "EDMA centerofcharge keyword. When enabled, EDMA refines peak positions to the center of charge of the atomic basin before export.",
    "edma_chlimit": "EDMA chlimit keyword. Minimum integrated charge for exported maxima; useful for suppressing noise peaks in rough or over-sharpened maps.",
    "edma_chlimlist": "EDMA chlimlist keyword. Charge-list threshold, for example '0.0057 relative', used together with numberofatoms and composition-based export.",
    "extra_edma_keywords": "Additional raw EDMA keyword lines appended to the generated EDMA input. Use this for documented EDMA options not exposed above.",
    "damping_factor": "Inverse XPLOR damping value 1/x. 1.0 means no damping; 0.5 is equivalent to the previous factor 2.0; 0.25 is equivalent to factor 4.0. Disabled/ignored for CIF or none.",
    "modelfile_source": "Authoritative source for cycle 2 and later. none forces the run to one cycle; superflip_xplor cycles without SharpED deblurring; deblurred_xplor uses the SharpED XPLOR map; deblurred_edma_cif ignores XPLOR damping.",
    "reconstruction_mode": "Superflip runs the standard charge-flipping cycle every cycle (unchanged default). '1st Superflip, then SharpED (beta)' runs Superflip only once, then each cycle deblurs with SharpED, reads phi_calc by FFT from that SharpED map for every measured hkl, and recomposes a map from |Fobs| + phi_calc for the next cycle; it does not work well with some models. 'SharpED (experimental)' skips Superflip entirely and starts cycle 1 from |Fobs| with independent random phases; it does not work yet and is intended for development, not production use. Hidden unless 'Show beta and experimental features' is enabled on Advanced -> Setup.",
    "run_edma_recycle_final": "Only used by the '1st Superflip, then SharpED (beta)' and 'SharpED (experimental)' phasing methods: run EDMA peak extraction and structure export once, on the final cycle's |Fobs|+phi_calc map.",
    "exclude_atoms": "Optional atom labels to remove from CIF modelfiles before the next Superflip cycle. Use comma, semicolon or whitespace separation.",
    "run_edma_superflip": "Run EDMA peak search on the Superflip XPLOR map and write CIF, XYZ and PDB structure exports.",
    "run_sharped": "Run SharpED server deblurring on the Superflip XPLOR map. If disabled, the SharpED map is a copy of the Superflip map.",
    "symmetrize_deblurred_map": "After SharpED deblurring, run Superflip in perform symmetry mode with the deblurred XPLOR as modelfile. No charge flipping is performed; the output map is averaged according to the supplied space-group symmetry and is then used for EDMA, Jana export, feedback and later-cycle XPLOR modelfiles.",
    "run_edma_deblurred": "Run EDMA peak search on the SharpED XPLOR map. Disable this when you only want map export or Superflip EDMA results.",
    "compute_omit_maps": "Each cycle, additionally run Superflip (and SharpED, if enabled) on a fixed random 5% of reflections excluded from the input, producing 'omit' maps used only for cross-validation. Enables the Superflip validation and SharpED validation tabs' omit-map correlation series (full map vs. omit map); together with R_free, this also feeds the phase-recycling result selector's Selection score, helping identify the most suitable map among the recycling cycles. Roughly doubles Superflip/SharpED time per cycle.",
    "compute_omit_rfree": "Also compute R_free from the excluded 5% holdout: the crystallographic R-factor between their observed |F| and |F| calculated by FFT from the omit map, which never saw them. Feeds the phase-recycling result selector's Selection score alongside OMIT correlation, helping rank cycles and choose the most suitable map. Requires 'Compute OMIT validation maps'.",
    "perform_algorithm": "Superflip perform keyword. Common values: CF, lde, general, fourier, symmetry; AAR is kept for executables that support it.",
    "map_export_format": "XPLOR is always produced internally (EDMA and SharpED require it). xplor keeps only that working map; ccp4 or jana additionally saves a CCP4 map or Jana m80/m81 density+reflection files. 'HKL reflections with phases' and 'ShelX (fcf)' instead save, for each cycle's Superflip map, the observed |Fobs|/intensity together with phases (and, for ShelX, calculated F squared) read by FFT from that map, in a standardized text file or a ShelX/Jana-compatible .fcf file.",
    "structure_export_format": "CIF is always produced internally (used for metrics and next-cycle modelfiles). xyz or pdb additionally saves that structure format alongside the CIF.",
    "referencefile_mode": "Internal automatic setting derived from External reference file. Phase Studio writes only referencefile and lets Superflip infer jana/xplor/ccp4/cif from the filename.",
    "voxel": "Superflip voxel grid. The default omit/blank skips the keyword. Use three integers, for example 180 80 160, or AUTO to compute a 0.2 A grid from the unit cell.",
    "bestdensities_count": "First argument of bestdensities: how many best density maps Superflip keeps.",
    "bestdensities_metric": "Second argument of bestdensities: rvalue, peakiness, symmetry or reference. 'symmetry' biases saved-density selection toward symmetry-consistent solutions.",
    "polish": "Adds 'polish yes' to the Superflip input, enabling Superflip's final polishing/refinement stage when supported by the executable.",
    "maxcycles": "Maximum number of Superflip iterations per run.",
    "repeatmode": "Superflip repeatmode parameter controlling repeated independent attempts and convergence sampling.",
    "randomseed": "Random seed passed to Superflip. Use a fixed value for reproducibility or Superflip-supported automatic syntax if desired.",
    "delta": "Superflip delta keyword. AUTO lets Superflip estimate the flip threshold.",
    "weakratio": "Superflip weakratio keyword.",
    "biso": "Overall isotropic B factor used to sharpen the map. Use 0.000 if no sharpening is wanted.",
    "reflection_data_mode": "Exact HKL column order. 'set from inflip' imports dataformat from Jana. hkl I sigma/hkl F sigma/hkl I phase sigma/hkl F phase sigma accept I or F followed by a genuine sigma, optionally with phase in degrees before sigma; Phase Studio converts phase to Superflip turns and retains sigma for diagnostics. hkl I fwhm/hkl F fwhm are for data whose second column is a peak-shape FWHM (e.g. Le Bail powder extraction), not a measurement uncertainty -- I/sigma(I)-style statistics are hidden or relabeled I/FWHM for these, since an I/FWHM ratio is not a signal-to-noise ratio.",
    "first_cycle_like_attachment": "Legacy option removed from the UI. Use Basic -> Workflow -> Next-cycle model instead.",
    "i_over_sigma_min": "Minimum value/sigma filter for observed reflections before writing the Superflip HKL block.",
    "resolution_d_min": "Optional resolution cutoff in Angstrom. 0 keeps all reflections; 1.2 keeps only reflections with d >= 1.2 A.",
    "normalize": "Optional Superflip reflection normalization keyword. For this Windows executable, none is the safest default and local is omitted.",
    "nresshells": "Number of resolution shells used only when a supported Superflip normalization keyword is written.",
    "missing": "Optional Superflip missing-data keyword line, for example bounds for missing reflections.",
    "searchsymmetry": "Superflip searchsymmetry keyword: no, shift or average.",
    "derivesymmetry": "Superflip derivesymmetry keyword. Common values are yes, no or use, depending on Superflip version.",
    "electrons": "Superflip electrons keyword. Leave blank to omit.",
    "dataitemwidths": "Not required for generated inputs because Phase Studio writes whitespace-separated fbegin records.",
    "extra_superflip_keywords": "Additional raw Superflip keyword lines inserted before fbegin. Use this for advanced/manual keywords not represented by a widget.",
    "map_feedback_missing_enabled": "Enables missing-reflection completion. When off, the fields below are ignored.",
    "map_feedback_missing_from_cycle": "First completed cycle whose map is used to add missing reflections for the next cycle.",
    "map_feedback_missing_percent_limit": "Maximum number of added missing reflections, expressed as a percent of the current HKL count. This prevents map feedback from overwhelming measured data.",
    "map_feedback_intensity_enabled": "Enables map-based intensity correction. When off, the fields below are ignored.",
    "map_feedback_intensity_from_cycle": "First completed cycle whose map is used to damp observed intensities for the next cycle.",
    "map_feedback_intensity_damping": "Damping factor for map-based intensity correction. 0 keeps observed data; 1 replaces them by scaled map-derived intensities.",
    "map_feedback_intensity_max_i_over_sigma": "Apply map-based intensity correction only to non-zero reflections with value/sigma below this limit. Use 0 to correct all non-zero reflections.",
    "redistribute_overlaps": "Enables powder overlap repartitioning: each cycle, redistribute the combined observed intensity of overlapping-reflection groups (hkl I/F fwhm data only) between their members, using intensities calculated by FFT from that cycle's processed map. When off, the fields below are ignored.",
    "powder_redistribution_from_cycle": "First completed cycle whose map is used to redistribute overlapping powder reflections for the next cycle.",
    "powder_wavelength": "Radiation wavelength in Å, required to compute 2θ for powder overlap repartitioning. If left at 0, it is auto-detected first from the .inflip file's lambda/wavelength line, then from the reference file's _diffrn_radiation_wavelength tag; enter it manually if neither source has it.",
    "powder_separation_factor": "Multiplier of the mean FWHM (in the same 2θ-like units as the data) used to decide whether two reflections' Bragg peaks overlap: delta(2θ) < separation_factor * (FWHM1 + FWHM2) / 2. Matches Superflip's own fwhmseparation keyword.",
    "powder_redistribution_mix": "Blend factor for powder overlap repartitioning: 0 keeps each reflection's observed share of its group's total intensity; 1 replaces it entirely with the share implied by intensities calculated from the processed map. The group total is always conserved regardless of this value.",
    "sharped_base_url": "SharpED inference server base URL. The C++ reference client uses https://jana.fzu.cz.",
    "sharped_api_token": "User API token sent as Authorization: Bearer during upload/status/download.",
    "show_beta_features": "When off (default), beta and experimental Phasing methods and the settings that only apply to them are hidden entirely from the Basic tabs, not just disabled. Enable to make them selectable.",
    "sharped_model": "SharpED server model name. Use default to query /sharp-ed/models and select the server default.",
    "sharped_elements": "Chemical elements sent to the SharpED server. Leave blank to derive unique non-H elements from the reference composition.",
    "sharped_outres": "Requested output sampling/resolution of the SharpED density map.",
    "sharped_max_upload_mb": "Maximum XPLOR map size uploaded to the SharpED server in megabytes. Use 100 MB for the current public server limit. If voxel is empty/omit, Phase Studio can add a coarser Superflip voxel keyword before map calculation so the native Superflip XPLOR fits. Set 0 to disable this check.",
    "sharped_timeout_seconds": "HTTP timeout in seconds for SharpED model query, upload, status and download requests. Phase Studio enforces at least 600 seconds for large XPLOR uploads.",
    "sharped_poll_seconds": "Seconds between status polling requests.",
    "sharped_max_polls": "Maximum number of status polls. Use -1 to wait without a fixed polling limit.",
}

SUPERFLIP_KEYWORD_REFERENCE = """Superflip keyword quick reference

Structure and symmetry, generated from Reference CIF:
  title, dimension, cell, spacegroup, centro, centers/endcenters,
  symmetry/endsymmetry, composition.

Input reflection data:
  fbegin/endf, dataformat, dataitemwidths, reflstartline, reflendline,
  resunits, lambda.

Output and model files:
  outputfile, outputformat, filebase, rewriteoutput, modelfile,
  commandfile, terminal, expandedlog, coverage.

Density modification and convergence:
  perform, maxcycles, repeatmode, bestdensities, delta, weakratio,
  Biso, randomseed, polish, addcycles, convergencemode, skipstart.

Normalization and missing reflections:
  normalize, nresshells, missing, electrons.

Symmetry/origin handling:
  searchsymmetry, derivesymmetry, referencesymmetry/endreferencesymmetry,
  usephases, viewprogress.

Grid and higher-dimensional options:
  voxel, finevoxel, realdimension, qvectors/endqvectors.

Histogram/powder-specific options:
  histogram/endhistogram, hmparameters, fwhmratio.

Use Extra Superflip keywords for any manual keyword not exposed as a widget,
for example:
  expandedlog yes
  coverage no
  addcycles 200
  convergencemode rvalue 30
  usephases firstcycle
"""


def create_phase_studio_logo_pixmap(width: int = 96) -> QPixmap:
    """Render the supplied Phase Studio monitor mark without an external asset dependency."""
    width = max(40, int(width))
    height = max(30, int(round(width * 255.0 / 339.0)))
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.Antialiasing, True)
        sx = width / 339.0
        sy = height / 255.0

        def rect(x: float, y: float, w: float, h: float, color: str, radius: float = 0.0) -> None:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(int(x * sx), int(y * sy), int(w * sx), int(h * sy), radius * sx, radius * sy)

        frame_pen = QPen(QColor("#001170"), max(2.0, 7.0 * sx))
        frame_pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(frame_pen)
        painter.setBrush(QColor("#F2F4F9"))
        painter.drawRoundedRect(int(19 * sx), int(11 * sy), int(286 * sx), int(177 * sy), 2.5 * sx, 2.5 * sy)
        painter.drawLine(int(159 * sx), int(188 * sy), int(159 * sx), int(238 * sy))
        painter.drawLine(int(82 * sx), int(239 * sy), int(237 * sx), int(239 * sy))

        rect(104, 49, 30, 17, "#001170", 5)
        rect(132, 69, 19, 16, "#001170", 5)
        rect(72, 87, 61, 13, "#001170", 6)
        rect(80, 106, 25, 21, "#001170", 5)
        rect(118, 109, 17, 42, "#001170", 5)
        rect(149, 107, 21, 22, "#001170", 5)
        rect(151, 47, 44, 20, "#1FA5FF", 5)
        rect(194, 69, 33, 16, "#1FA5FF", 7)
        rect(172, 87, 90, 13, "#44B7FF", 6)
        rect(190, 106, 42, 21, "#1FA5FF", 6)
        rect(146, 134, 64, 15, "#1FA5FF", 7)
    finally:
        painter.end()
    return pixmap


def create_phase_studio_app_icon(size: int = 64) -> QIcon:
    """Create a square, optically centered application/taskbar icon."""
    size = max(32, int(size))
    source = create_phase_studio_logo_pixmap(size)
    cropped = source.copy(
        int(source.width() * 0.04),
        int(source.height() * 0.025),
        int(source.width() * 0.88),
        int(source.height() * 0.95),
    )
    target = QPixmap(size, size)
    target.fill(Qt.transparent)
    scaled = cropped.scaled(
        int(size * 0.90), int(size * 0.90), Qt.KeepAspectRatio, Qt.SmoothTransformation
    )
    painter = QPainter(target)
    try:
        painter.drawPixmap((size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled)
    finally:
        painter.end()
    return QIcon(target)


def create_phase_studio_brand_header() -> QWidget:
    """The "PHASE STUDIO" branded header (logo, title, version badge,
    subtitle) -- shared by the main window and any other Phase Studio
    surface (the Jana2020 Wizard, its result selector, ...) that should
    visually read as the same application rather than a generic dialog."""
    brand_header = QWidget()
    brand_header.setObjectName("brandHeader")
    brand_layout = QHBoxLayout(brand_header)
    brand_layout.setContentsMargins(12, 6, 12, 7)
    brand_layout.setSpacing(10)
    brand_logo = QLabel()
    brand_logo.setObjectName("brandLogo")
    brand_logo_pixmap = create_phase_studio_logo_pixmap(58)
    brand_logo.setPixmap(brand_logo_pixmap)
    brand_logo.setFixedSize(brand_logo_pixmap.size())
    brand_logo.setToolTip("Phase Studio")
    brand_text_layout = QVBoxLayout()
    brand_text_layout.setContentsMargins(0, 0, 0, 0)
    brand_text_layout.setSpacing(1)
    brand_title_row = QHBoxLayout()
    brand_title_row.setSpacing(8)
    brand_title = QLabel("PHASE STUDIO")
    brand_title.setObjectName("brandTitle")
    version_badge = QLabel(__version__)
    version_badge.setObjectName("versionBadge")
    version_badge.setAlignment(Qt.AlignCenter)
    brand_title_row.addWidget(brand_title, 1)
    brand_title_row.addWidget(version_badge)
    brand_subtitle = QLabel("Superflip · SharpED · EDMA workflow")
    brand_subtitle.setObjectName("brandSubtitle")
    brand_subtitle.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    brand_text_layout.addLayout(brand_title_row)
    brand_text_layout.addWidget(brand_subtitle)
    brand_layout.addWidget(brand_logo, 0, Qt.AlignVCenter)
    brand_layout.addLayout(brand_text_layout, 1)
    return brand_header


def create_phase_studio_context_banner(title: str, subtitle: str, badge: Optional[QWidget] = None) -> QWidget:
    """A compact navy context banner using the same visual language as the
    main window's "RUN OVERVIEW" banner (#dashboardHeader/#dashboardTitle/
    #dashboardSubtitle in ui_style.py), reused for Jana2020 Wizard page
    context and the Jana2020 result selector so both read as the same
    application as the main window rather than an unrelated dialog."""
    banner = QWidget()
    banner.setObjectName("dashboardHeader")
    banner_layout = QHBoxLayout(banner)
    banner_layout.setContentsMargins(12, 5, 12, 5)
    banner_text = QVBoxLayout()
    banner_text.setSpacing(0)
    banner_title = QLabel(title)
    banner_title.setObjectName("dashboardTitle")
    banner_subtitle = QLabel(subtitle)
    banner_subtitle.setObjectName("dashboardSubtitle")
    banner_subtitle.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    banner_text.addWidget(banner_title)
    banner_text.addWidget(banner_subtitle)
    banner_layout.addLayout(banner_text, 1)
    if badge is not None:
        banner_layout.addWidget(badge)
    return banner


def apply_safe_dialog_geometry(dialog: QWidget, width: int, height: int) -> None:
    """Int-based convenience wrapper around the existing
    fit_dialog_to_available_screen() (frame-aware: measures the dialog's
    actual native frame, not an approximate margin, and double-clamps after
    the window manager settles) -- the one shared safe top-level-window
    geometry helper for the Jana2020 Wizard, the Jana2020 result selector,
    HKL Validation/Completeness, and any other Phase Studio dialog, rather
    than each maintaining its own hard-coded/partial sizing logic."""
    fit_dialog_to_available_screen(dialog, QSize(width, height))


class WorkflowDiagram(QWidget):
    """Compact native-Qt overview of the optional reconstruction branches."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(198)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setToolTip("Optional branches depend on the Workflow settings.")

    @staticmethod
    def _diagram_geometry(width: float) -> Tuple[List[QRectF], List[QRectF]]:
        width = max(240.0, float(width))
        margin = 8.0
        gap = max(7.0, min(16.0, width * 0.025))
        box_w = max(44.0, (width - 2.0 * margin - 3.0 * gap) / 4.0)
        box_h = 42.0
        make_row = lambda y: [
            QRectF(margin + index * (box_w + gap), y, box_w, box_h)
            for index in range(4)
        ]
        return make_row(22.0), make_row(104.0)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        super().paintEvent(event)
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            width = max(240.0, float(self.width()))
            margin = 8.0
            top_boxes, bottom_boxes = self._diagram_geometry(width)
            top_labels = ("Reflections", "Superflip", "XPLOR map", "SharpED")
            bottom_labels = ("EDMA", "SharpED map", "Next-cycle model", "Jana2020")
            diagram_font = painter.font()
            diagram_font.setPointSizeF(8.5)
            painter.setFont(diagram_font)

            def draw_row(labels: Sequence[str], boxes: Sequence[QRectF]) -> None:
                for label, box in zip(labels, boxes):
                    painter.setPen(QPen(QColor("#44b7ff"), 1.0))
                    painter.setBrush(QColor("#f2f4f9"))
                    painter.drawRect(box)
                    painter.setPen(QColor("#001170"))
                    painter.drawText(box.adjusted(4.0, 2.0, -4.0, -2.0), Qt.AlignCenter | Qt.TextWordWrap, label)

            draw_row(top_labels, top_boxes)
            draw_row(bottom_labels, bottom_boxes)

            def arrow(start_x: float, start_y: float, end_x: float, end_y: float) -> None:
                painter.setPen(QPen(QColor("#2264b8"), 1.35))
                painter.drawLine(int(start_x), int(start_y), int(end_x), int(end_y))
                angle = math.atan2(end_y - start_y, end_x - start_x)
                head = 6.0
                spread = 0.58
                for delta in (-spread, spread):
                    painter.drawLine(
                        int(end_x),
                        int(end_y),
                        int(end_x - head * math.cos(angle + delta)),
                        int(end_y - head * math.sin(angle + delta)),
                    )

            for first, second in zip(top_boxes, top_boxes[1:]):
                arrow(first.right() + 2.0, first.center().y(), second.left() - 2.0, second.center().y())

            # Optional scientific branches from the raw XPLOR map and SharpED.
            arrow(top_boxes[2].center().x(), top_boxes[2].bottom() + 2.0, bottom_boxes[0].center().x(), bottom_boxes[0].top() - 2.0)
            arrow(top_boxes[3].center().x(), top_boxes[3].bottom() + 2.0, bottom_boxes[1].center().x(), bottom_boxes[1].top() - 2.0)
            painter.setPen(QPen(QColor("#2264b8"), 1.35))
            route_y = 158.0
            painter.drawLine(int(bottom_boxes[0].center().x()), int(bottom_boxes[0].bottom() + 2.0), int(bottom_boxes[0].center().x()), int(route_y))
            painter.drawLine(int(bottom_boxes[0].center().x()), int(route_y), int(bottom_boxes[2].center().x()), int(route_y))
            arrow(bottom_boxes[2].center().x(), route_y, bottom_boxes[2].center().x(), bottom_boxes[2].bottom() + 2.0)
            arrow(bottom_boxes[1].right() + 2.0, bottom_boxes[1].center().y(), bottom_boxes[2].left() - 2.0, bottom_boxes[2].center().y())
            arrow(bottom_boxes[2].right() + 2.0, bottom_boxes[2].center().y(), bottom_boxes[3].left() - 2.0, bottom_boxes[3].center().y())

            painter.setPen(QColor("#2264b8"))
            painter.drawText(
                QRectF(margin, 170.0, width - 2.0 * margin, 20.0),
                Qt.AlignCenter,
                "Optional branches · selected result → Jana2020",
            )
        finally:
            painter.end()


def format_metric_hover_value(value: float) -> str:
    """Magnitude-adaptive display formatting for a hover-tooltip number.
    Display only -- never used for the stored/plotted metric value itself."""
    magnitude = abs(float(value))
    if magnitude >= 1000:
        return f"{value:,.0f}"
    if magnitude >= 100:
        return f"{value:.1f}"
    if magnitude >= 10:
        return f"{value:.2f}"
    return f"{value:.3f}"


def robust_detail_range(values: Sequence[Optional[float]], min_points: int = 4) -> Optional[Tuple[float, float]]:
    """Display-only robust y-range covering the main body of ``values`` (a
    padded IQR fence around the median), for a "Detail" viewport that stays
    readable when one extreme outlier would otherwise dominate the full
    autoscaled range. Never modifies, discards or recalculates any stored
    metric value -- points outside the returned range are simply outside the
    current viewport, exactly like an ordinary zoom. Returns None when there
    are too few finite points for a robust range to mean anything."""
    finite = np.asarray(
        [float(v) for v in values if v is not None and np.isfinite(float(v))], dtype=float
    )
    if finite.size < min_points:
        return None
    q1, q3 = np.percentile(finite, [25, 75])
    iqr = q3 - q1
    pad = iqr * 1.5 if iqr > 1e-9 else max(abs(float(np.median(finite))), 1.0) * 0.1
    lo, hi = q1 - pad, q3 + pad
    if hi - lo < 1e-9:
        hi = lo + max(abs(lo), 1.0) * 0.05
    return (float(lo), float(hi))


class MetricsPlotInteraction:
    """Reusable hover/zoom/pan/reset controller for one Reconstruction
    Metrics tab's Matplotlib canvas.

    _render_metrics_tab() tears down and rebuilds the tab's Axes on every
    refresh (figure.clear() + add_subplot), so this controller intentionally
    holds no reference to a specific Axes/artist across redraws -- it looks
    up the CURRENT Axes and CURRENT series data through the callables passed
    to __init__ every time an event fires, and notify_redraw_start() drops
    any hover state pointing at an Axes that is about to be destroyed.
    """

    HOVER_RADIUS_PX = 9.0
    ZOOM_FACTOR = 1.3
    AXIS_EDGE_PX = 22.0

    def __init__(
        self,
        key: str,
        canvas: "FigureCanvas",
        get_axes: Callable[[], object],
        get_series: Callable[[], List[Tuple[str, List[int], List[Optional[float]], List[Optional[float]], str]]],
        *,
        supports_detail: bool = False,
        on_state_changed: Optional[Callable[[str], None]] = None,
        request_rerender: Optional[Callable[[], None]] = None,
    ) -> None:
        self.key = key
        self.canvas = canvas
        self._get_axes = get_axes
        self._get_series = get_series
        self.supports_detail = supports_detail
        self.on_state_changed = on_state_changed
        self.request_rerender = request_rerender
        self.user_modified = False
        self.mode = "full"
        self.detail_available = False
        self._stored_xlim: Optional[Tuple[float, float]] = None
        self._stored_ylim: Optional[Tuple[float, float]] = None
        self._drag: Optional[dict] = None
        self._hover_annotation = None
        self._hover_ring = None
        self._hover_cycle: Optional[int] = None
        canvas.mpl_connect("scroll_event", self._on_scroll)
        canvas.mpl_connect("button_press_event", self._on_press)
        canvas.mpl_connect("motion_notify_event", self._on_motion)
        canvas.mpl_connect("button_release_event", self._on_release)
        canvas.mpl_connect("figure_leave_event", self._on_leave)

    # ----- external API used by _render_metrics_tab() and the control row -----

    def notify_redraw_start(self) -> None:
        """Call at the very top of each render pass, before figure.clear()."""
        self._hover_annotation = None
        self._hover_ring = None
        self._hover_cycle = None

    def apply_limits(
        self,
        ax,
        full_xlim: Tuple[float, float],
        full_ylim: Tuple[float, float],
        detail_ylim: Optional[Tuple[float, float]],
    ) -> str:
        """Set the Axes' x/y limits for this render pass, honoring a stored
        manual zoom/pan (section 16: live updates must not reset it) or an
        active Detail mode, falling back to the freshly computed full-range
        limits otherwise. Returns which view is actually in effect."""
        self.detail_available = detail_ylim is not None
        if not self.detail_available and self.mode == "detail":
            self.mode = "full"
        if self.user_modified and self._stored_xlim is not None and self._stored_ylim is not None:
            ax.set_xlim(self._stored_xlim)
            ax.set_ylim(self._stored_ylim)
            return "manual"
        if self.mode == "detail" and detail_ylim is not None:
            ax.set_xlim(full_xlim)
            ax.set_ylim(detail_ylim)
            return "detail"
        ax.set_xlim(full_xlim)
        ax.set_ylim(full_ylim)
        return "full"

    def reset_view(self) -> None:
        self.user_modified = False
        self.mode = "full"
        self._stored_xlim = None
        self._stored_ylim = None
        self._request_rerender()
        self._notify()

    def set_mode(self, mode: str) -> None:
        if mode == self.mode and not self.user_modified:
            return
        self.mode = mode
        self.user_modified = False
        self._stored_xlim = None
        self._stored_ylim = None
        self._request_rerender()
        self._notify()

    # ----- internal -----

    def _request_rerender(self) -> None:
        if self.request_rerender is not None:
            try:
                self.request_rerender()
            except Exception:
                pass

    def _notify(self) -> None:
        if self.on_state_changed is not None:
            try:
                self.on_state_changed(self.key)
            except Exception:
                pass

    def _mark_user_modified(self, ax) -> None:
        self.user_modified = True
        self._stored_xlim = tuple(ax.get_xlim())
        self._stored_ylim = tuple(ax.get_ylim())

    def _axis_targets(self, ax, event) -> Tuple[bool, bool]:
        # Cursor proximity to the axes edges (display/pixel space, so this is
        # DPI- and zoom-independent) decides whether to zoom one axis or both.
        try:
            bbox = ax.get_window_extent()
        except Exception:
            return True, True
        near_bottom = event.y is not None and (event.y - bbox.y0) <= self.AXIS_EDGE_PX
        near_left = event.x is not None and (event.x - bbox.x0) <= self.AXIS_EDGE_PX
        if near_bottom and not near_left:
            return True, False
        if near_left and not near_bottom:
            return False, True
        return True, True

    def _on_scroll(self, event) -> None:
        ax = self._get_axes()
        if ax is None or event.inaxes is not ax or event.xdata is None or event.ydata is None:
            return
        factor = (1.0 / self.ZOOM_FACTOR) if event.button == "up" else self.ZOOM_FACTOR
        zoom_x, zoom_y = self._axis_targets(ax, event)
        if zoom_x:
            xlim = ax.get_xlim()
            x = event.xdata
            ax.set_xlim(x - (x - xlim[0]) * factor, x + (xlim[1] - x) * factor)
        if zoom_y:
            ylim = ax.get_ylim()
            y = event.ydata
            ax.set_ylim(y - (y - ylim[0]) * factor, y + (ylim[1] - y) * factor)
        self._mark_user_modified(ax)
        self._hide_tooltip()
        self.canvas.draw_idle()
        self._notify()

    def _on_press(self, event) -> None:
        ax = self._get_axes()
        if ax is None or event.inaxes is not ax:
            return
        if event.dblclick:
            self.reset_view()
            return
        if event.button not in (1, 2):
            return
        self._drag = {
            "button": event.button,
            "x_px": event.x,
            "y_px": event.y,
            "xlim": ax.get_xlim(),
            "ylim": ax.get_ylim(),
        }
        self._hide_tooltip()
        try:
            self.canvas.setCursor(Qt.ClosedHandCursor)
        except Exception:
            pass

    def _on_motion(self, event) -> None:
        ax = self._get_axes()
        if ax is None:
            return
        if self._drag is not None:
            if event.button in (1, 2):
                self._do_pan(ax, event)
            else:
                self._end_drag()
            return
        if event.inaxes is not ax:
            self._hide_tooltip()
            return
        self._update_hover(ax, event)

    def _do_pan(self, ax, event) -> None:
        drag = self._drag
        if drag is None or event.x is None or event.y is None:
            return
        inv = ax.transData.inverted()
        x0_data, y0_data = inv.transform((drag["x_px"], drag["y_px"]))
        x1_data, y1_data = inv.transform((event.x, event.y))
        dx = x0_data - x1_data
        dy = y0_data - y1_data
        xlim = drag["xlim"]
        ylim = drag["ylim"]
        ax.set_xlim(xlim[0] + dx, xlim[1] + dx)
        ax.set_ylim(ylim[0] + dy, ylim[1] + dy)
        self._mark_user_modified(ax)
        self.canvas.draw_idle()

    def _on_release(self, event) -> None:
        self._end_drag()

    def _end_drag(self) -> None:
        if self._drag is not None:
            self._drag = None
            try:
                self.canvas.setCursor(Qt.ArrowCursor)
            except Exception:
                pass
            self._notify()

    def _on_leave(self, event) -> None:
        self._hide_tooltip()
        self._end_drag()

    # ----- hover tooltip -----

    def _update_hover(self, ax, event) -> None:
        if event.x is None or event.y is None:
            self._hide_tooltip()
            return
        cycle, best_dist, anchor = self._nearest_cycle(ax, event)
        if cycle is None or best_dist > self.HOVER_RADIUS_PX:
            self._hide_tooltip()
            return
        if cycle == self._hover_cycle and self._hover_annotation is not None:
            return
        self._show_tooltip(ax, cycle, anchor)

    def _nearest_cycle(self, ax, event) -> Tuple[Optional[int], float, Optional[Tuple[float, float]]]:
        # Hit-testing is done in DISPLAY (pixel) space against the actually
        # PLOTTED values (which for the normalized-score tabs is the 0-1
        # score, not the raw metric) so proximity behaves consistently after
        # zoom/pan and across DPI scales; the raw value used for the tooltip
        # TEXT is looked up separately in _show_tooltip(). ``anchor`` is the
        # exact (x, y) of the single closest marker, in data coordinates, for
        # both the tooltip anchor and the hover-highlight ring.
        best_cycle: Optional[int] = None
        best_dist = float("inf")
        best_anchor: Optional[Tuple[float, float]] = None
        for _label, cycles, plotted_values, _raw_values, _unit in self._get_series():
            xs: List[float] = []
            ys: List[float] = []
            for c, v in zip(cycles, plotted_values):
                if v is None:
                    continue
                fv = float(v)
                if not np.isfinite(fv):
                    continue
                xs.append(float(c))
                ys.append(fv)
            if not xs:
                continue
            disp = ax.transData.transform(np.column_stack([xs, ys]))
            dists = np.hypot(disp[:, 0] - event.x, disp[:, 1] - event.y)
            idx = int(np.argmin(dists))
            if dists[idx] < best_dist:
                best_dist = float(dists[idx])
                best_cycle = int(round(xs[idx]))
                best_anchor = (xs[idx], ys[idx])
        return best_cycle, best_dist, best_anchor

    def _tooltip_offset(self, ax, anchor_x: float, anchor_y: float) -> Tuple[float, float, str, str]:
        """Pick which corner the tooltip grows toward (offset direction plus
        matching text alignment) from how close the anchor point sits to each
        edge of the plotting area, in display/pixel space -- proximity-based
        rather than measuring the not-yet-rendered annotation's exact size,
        but enough to keep "Cycle N" and the rest of the box on screen for
        points near the top (y=Best) or right edge (near the legend)."""
        offset = 11.0
        try:
            bbox = ax.get_window_extent()
            disp = ax.transData.transform((anchor_x, anchor_y))
            fx = (disp[0] - bbox.x0) / max(1.0, bbox.width)
            fy = (disp[1] - bbox.y0) / max(1.0, bbox.height)
        except Exception:
            fx = fy = 0.0
        go_left = fx > 0.62
        go_down = fy > 0.68
        dx = -offset if go_left else offset
        dy = -offset if go_down else offset
        ha = "right" if go_left else "left"
        va = "top" if go_down else "bottom"
        return dx, dy, ha, va

    def _show_tooltip(self, ax, cycle: int, anchor: Optional[Tuple[float, float]]) -> None:
        if anchor is None:
            self._hide_tooltip()
            return
        lines = [f"Cycle {cycle}"]
        for label, cycles, _plotted_values, raw_values, unit in self._get_series():
            value = None
            for c, v in zip(cycles, raw_values):
                if c == cycle and v is not None and np.isfinite(float(v)):
                    value = float(v)
                    break
            if value is None:
                continue
            clean_label = label.replace("(%)", "").strip()
            lines.append(f"{clean_label}: {format_metric_hover_value(value)}{unit}")
        if len(lines) <= 1:
            self._hide_tooltip()
            return
        text = "\n".join(lines)
        anchor_x, anchor_y = anchor
        # Anchor to the data point itself (axes data coordinates); the offset
        # direction and text alignment flip based on how close the point is
        # to each edge of the plotting area (in display/pixel space, so it
        # works after zoom/pan and at any DPI), so the tooltip -- including
        # its "Cycle N" heading -- stays fully on screen instead of being
        # clipped near the top (e.g. a point at y=Best) or the right edge
        # (e.g. a point near the legend).
        dx, dy, ha, va = self._tooltip_offset(ax, anchor_x, anchor_y)
        if self._hover_annotation is None or self._hover_annotation.axes is not ax:
            self._hover_annotation = ax.annotate(
                text,
                xy=(anchor_x, anchor_y),
                xytext=(dx, dy),
                textcoords="offset points",
                ha=ha,
                va=va,
                fontsize=7.3,
                color="#14204a",
                linespacing=1.5,
                bbox=dict(boxstyle="square,pad=0.35", facecolor="#f5f9ff", edgecolor="#2264b8", linewidth=0.9),
                zorder=12,
                annotation_clip=False,
            )
        else:
            self._hover_annotation.set_text(text)
            self._hover_annotation.xy = (anchor_x, anchor_y)
            self._hover_annotation.set_position((dx, dy))
            self._hover_annotation.set_ha(ha)
            self._hover_annotation.set_va(va)
            self._hover_annotation.set_visible(True)
        # A restrained ring around just the hovered marker -- visual hierarchy
        # stays line < markers < hover-highlighted marker, no new permanent color.
        if self._hover_ring is None or self._hover_ring.axes is not ax:
            (self._hover_ring,) = ax.plot(
                [anchor_x],
                [anchor_y],
                marker="o",
                markersize=9.5,
                markerfacecolor="none",
                markeredgecolor="#001170",
                markeredgewidth=1.3,
                linestyle="none",
                zorder=11,
            )
        else:
            self._hover_ring.set_data([anchor_x], [anchor_y])
            self._hover_ring.set_visible(True)
        self._hover_cycle = cycle
        self.canvas.draw_idle()

    def _hide_tooltip(self) -> None:
        changed = False
        if self._hover_annotation is not None:
            try:
                self._hover_annotation.set_visible(False)
                changed = True
            except Exception:
                pass
        if self._hover_ring is not None:
            try:
                self._hover_ring.set_visible(False)
                changed = True
            except Exception:
                pass
        if changed:
            self.canvas.draw_idle()
        self._hover_cycle = None


class IterativeSuperflipPipelineQtGUI(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        # Standalone default; _sync_window_title() (called once jana_wizard_context
        # exists, below, mirroring _sync_jana_action_button()) sets the
        # Jana2020-launched title instead when that context applies.
        self.setWindowTitle(f"Phase Studio {__version__}")
        self.setWindowIcon(create_phase_studio_app_icon(64))
        self.resize(1420, 880)
        self.msg_queue: "queue.Queue[Tuple[str, object]]" = queue.Queue()
        self.worker: Optional[threading.Thread] = None
        self.hkl_task_worker: Optional[threading.Thread] = None
        self._hkl_task_generation = 0
        self._active_hkl_task_id: Optional[int] = None
        self._completed_hkl_task_ids: set[int] = set()
        self.stop_after_cycle = threading.Event()
        self.stop_now = threading.Event()
        self.results: List[CycleResult] = []
        self.last_run_config: Optional[RunConfig] = None
        self._resume_state: Optional[PipelineState] = None
        self.reference_atoms_for_plot: List[AtomSite] = []
        self.superflip_atoms_for_plot: List[AtomSite] = []
        self.deblur_atoms_for_plot: List[AtomSite] = []
        self.structure_cell: Optional[gemmi.UnitCell] = None
        self.structure_axes: List[object] = []
        self._structure_depth_artists: List[StructureDepthArtists] = []
        self.structure_elev = 20.0
        self.structure_azim = 35.0
        self._structure_rotation_source: Optional[object] = None
        self._configuration_locked = False
        self.jana_wizard_context = JanaWizardContext()
        self._run_status = "READY"
        self._cycle_progress_state: Optional[CycleProgressState] = None
        self._syncing_metadata_controls = False
        self._metadata_source_user_selected = False
        self._metadata_valid = False
        self._metadata_error_report: Optional[ErrorReport] = None
        self._structure_parse_errors: set[str] = set()
        self.inputs: Dict[str, object] = {}
        self.input_labels: Dict[str, QWidget] = {}
        self.settings = QSettings("PhaseStudio", "PhaseStudio")
        self._build_ui()
        self.help_shortcut = QShortcut(QKeySequence(Qt.Key_F1), self)
        self.help_shortcut.setContext(Qt.WindowShortcut)
        self.help_shortcut.activated.connect(self._open_context_help)
        self.load_settings()
        QTimer.singleShot(250, self.refresh_sharped_models)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll_queue)
        self.timer.start(200)

    def _configure_form(self, form: QFormLayout) -> QFormLayout:
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.DontWrapRows)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(CONFIG_FORM_HORIZONTAL_SPACING)
        form.setVerticalSpacing(CONFIG_FORM_VERTICAL_SPACING)
        form.setContentsMargins(0, 0, 0, 0)
        return form

    @staticmethod
    def _brief_tooltip(text: str) -> str:
        text = " ".join(str(text or "").split())
        match = re.match(r"^(.+?[.!?])(?:\s|$)", text)
        return match.group(1) if match else text

    def _secondary_help(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("secondaryHelp")
        label.setWordWrap(True)
        return label

    def _add_path(self, form: QFormLayout, key: str, label: str, default: str, mode: str = "file", file_filter: str = "All files (*)") -> None:
        row = PathRow(label, default, mode, file_filter)
        row.on_change = self.save_settings
        form.addRow(label, row)
        row.set_form_label(form.labelForField(row))
        self.inputs[key] = row
        self._apply_input_tooltip(key, row)
        self._apply_form_label_tooltip(form, row, key)

    def _add_text(self, form: QFormLayout, key: str, label: str, default: str = "") -> None:
        w = QLineEdit(default)
        form.addRow(label, w)
        self.inputs[key] = w
        self._apply_input_tooltip(key, w)
        self._apply_form_label_tooltip(form, w, key)

    def _add_multiline(self, form: QFormLayout, key: str, label: str, default: str = "", min_height: int = 90) -> None:
        w = QTextEdit()
        w.setAcceptRichText(False)
        w.setPlainText(default)
        w.setMinimumHeight(min_height)
        form.addRow(label, w)
        self.inputs[key] = w
        self._apply_input_tooltip(key, w)
        self._apply_form_label_tooltip(form, w, key)

    def _add_combo(self, form: QFormLayout, key: str, label: str, values: Sequence[str], default: str) -> None:
        w = QComboBox()
        w.addItems(list(values))
        w.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        w.setMinimumContentsLength(18)
        w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        # Editable-but-read-only so every dropdown's popup uses the same, more compact
        # row height as the SharpED model selector, instead of Qt's taller default for
        # non-editable combo boxes (was visibly inconsistent from one dropdown to another).
        w.setEditable(True)
        w.lineEdit().setReadOnly(True)
        w.lineEdit().setCursor(Qt.CursorShape.ArrowCursor)
        w.setInsertPolicy(QComboBox.NoInsert)
        idx = w.findText(default)
        if idx >= 0:
            w.setCurrentIndex(idx)
        form.addRow(label, w)
        self.inputs[key] = w
        self._apply_input_tooltip(key, w)
        self._apply_form_label_tooltip(form, w, key)

    def _add_combo_with_values(
        self,
        form: QFormLayout,
        key: str,
        label: str,
        items: Sequence[Tuple[str, str]],
        default_value: str,
    ) -> None:
        """Like _add_combo, but each item's user-facing text (items[i][1]) is
        independent of the internal token stored as its Qt userData
        (items[i][0]) -- _combo_value()/_set_widget_value_from_string() read
        and write that token via currentData()/findData(), never by parsing
        the display text. Use this instead of _add_combo whenever a combo's
        internal values are not already presentable as-is (e.g. raw file-role
        tokens like "deblurred_xplor")."""
        w = QComboBox()
        for value, text in items:
            w.addItem(text, value)
        w.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        w.setMinimumContentsLength(18)
        w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        w.setEditable(True)
        w.lineEdit().setReadOnly(True)
        w.lineEdit().setCursor(Qt.CursorShape.ArrowCursor)
        w.setInsertPolicy(QComboBox.NoInsert)
        idx = w.findData(default_value)
        if idx >= 0:
            w.setCurrentIndex(idx)
        form.addRow(label, w)
        self.inputs[key] = w
        self._apply_input_tooltip(key, w)
        self._apply_form_label_tooltip(form, w, key)

    def _add_checkbox(
        self,
        form: QFormLayout,
        key: str,
        label: str,
        default: bool = False,
        *,
        align_with_fields: bool = False,
    ) -> None:
        w = QCheckBox(label)
        w.setChecked(bool(default))
        if align_with_fields:
            form.addRow("", w)
        else:
            form.addRow(w)
        self.inputs[key] = w
        self._apply_input_tooltip(key, w)

    def _add_spin(self, form: QFormLayout, key: str, label: str, default: int, minimum: int = 0, maximum: int = 1000000, step: int = 1) -> None:
        w = QSpinBox()
        w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        w.setMinimumHeight(CONFIG_CONTROL_VISIBLE_HEIGHT)
        w.setRange(minimum, maximum)
        w.setSingleStep(step)
        w.setValue(default)
        form.addRow(label, w)
        self.inputs[key] = w
        self._apply_input_tooltip(key, w)
        self._apply_form_label_tooltip(form, w, key)

    def _add_dspin(self, form: QFormLayout, key: str, label: str, default: float, minimum: float = -1e9, maximum: float = 1e9, step: float = 0.1, decimals: int = 3) -> None:
        w = QDoubleSpinBox()
        w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        w.setMinimumHeight(CONFIG_CONTROL_VISIBLE_HEIGHT)
        w.setRange(minimum, maximum)
        w.setSingleStep(step)
        w.setDecimals(decimals)
        w.setValue(default)
        form.addRow(label, w)
        self.inputs[key] = w
        self._apply_input_tooltip(key, w)
        self._apply_form_label_tooltip(form, w, key)

    def _apply_input_tooltip(self, key: str, widget: object) -> None:
        tooltip = self._brief_tooltip(INPUT_TOOLTIPS.get(key, ""))
        if not tooltip:
            return
        if isinstance(widget, PathRow):
            widget.set_tooltip(tooltip)
        elif hasattr(widget, "setToolTip"):
            widget.setToolTip(tooltip)  # type: ignore[attr-defined]

    def _apply_form_label_tooltip(self, form: QFormLayout, widget: QWidget, key: str) -> None:
        tooltip = self._brief_tooltip(INPUT_TOOLTIPS.get(key, ""))
        label = form.labelForField(widget)
        if label is not None:
            self.input_labels[key] = label
            label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
            if tooltip:
                label.setToolTip(tooltip)

    def _open_help_section(self, anchor: str) -> None:
        if not hasattr(self, "category_tabs"):
            return
        is_advanced = self.help_section_advanced.get(str(anchor), False)
        tabs = self.advanced_tabs if is_advanced else self.basic_tabs
        scroll = getattr(self, "help_scroll_advanced" if is_advanced else "help_scroll_basic", None)
        if scroll is None:
            return
        self.category_tabs.setCurrentIndex(1 if is_advanced else 0)
        help_index = next(
            (index for index in range(tabs.count()) if tabs.tabText(index) == "Help"),
            -1,
        )
        if help_index < 0:
            return
        tabs.setCurrentIndex(help_index)
        target = self.help_sections.get(str(anchor))
        if target is None:
            scroll.verticalScrollBar().setValue(0)
            return
        QTimer.singleShot(0, lambda section=target, sc=scroll: sc.ensureWidgetVisible(section, 0, 8))

    def _context_help_anchor(self) -> Optional[str]:
        if not hasattr(self, "category_tabs"):
            return "setup"
        if self.category_tabs.currentIndex() == 0:
            name = self.basic_tabs.tabText(self.basic_tabs.currentIndex())
            return {
                "Input": "input",
                "Workflow": "workflow",
                "Output": "output",
                "Map feedback": "map_feedback",
                "Help": None,
            }.get(name, "setup")
        name = self.advanced_tabs.tabText(self.advanced_tabs.currentIndex())
        return {
            "Setup": "adv_setup",
            "Superflip": "superflip",
            "EDMA": "edma",
            "SharpED": "sharped",
            "Help": None,
        }.get(name, "adv_setup")

    def _open_context_help(self) -> None:
        anchor = self._context_help_anchor()
        if anchor is not None:
            self._open_help_section(anchor)

    def _external_link_icon(self, url: str, tooltip: str) -> QToolButton:
        def chain_pixmap(color: str) -> QPixmap:
            pixmap = QPixmap(16, 16)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            try:
                painter.setRenderHint(QPainter.Antialiasing, True)
                pen = QPen(QColor(color), 1.35)
                pen.setJoinStyle(Qt.RoundJoin)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.save()
                painter.translate(5.8, 9.4)
                painter.rotate(-38.0)
                painter.drawRoundedRect(QRectF(-4.4, -2.4, 8.0, 4.8), 2.4, 2.4)
                painter.restore()
                painter.save()
                painter.translate(10.2, 6.6)
                painter.rotate(-38.0)
                painter.drawRoundedRect(QRectF(-3.6, -2.4, 8.0, 4.8), 2.4, 2.4)
                painter.restore()
            finally:
                painter.end()
            return pixmap

        normal_pixmap = chain_pixmap("#7183a6")
        active_pixmap = chain_pixmap("#2264b8")
        icon = QIcon()
        icon.addPixmap(normal_pixmap, QIcon.Normal, QIcon.Off)
        icon.addPixmap(active_pixmap, QIcon.Active, QIcon.Off)
        link = QToolButton()
        link.setObjectName("externalLink")
        link.setIcon(icon)
        link.setIconSize(normal_pixmap.size())
        link.setAutoRaise(True)
        link.setCursor(Qt.PointingHandCursor)
        link.setToolTip(tooltip)
        link.setAccessibleName(tooltip)
        link.setFixedSize(20, 20)
        link.clicked.connect(lambda _checked=False, target=url: QDesktopServices.openUrl(QUrl(target)))
        return link

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)
        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setObjectName("mainSplitter")
        self.main_splitter.setHandleWidth(1)
        main_layout.addWidget(self.main_splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(6, 4, 8, 4)
        left_layout.setSpacing(8)
        self.main_splitter.addWidget(left)

        left_layout.addWidget(create_phase_studio_brand_header())

        category_tabs = QTabWidget()
        category_tabs.setObjectName("categoryTabs")
        basic_tabs = QTabWidget()
        basic_tabs.setObjectName("sectionTabs")
        advanced_tabs = QTabWidget()
        advanced_tabs.setObjectName("sectionTabs")
        category_tabs.addTab(basic_tabs, "Basic")
        category_tabs.addTab(advanced_tabs, "Advanced")
        self.category_tabs = category_tabs
        self.basic_tabs = basic_tabs
        self.advanced_tabs = advanced_tabs
        self.help_sections: Dict[str, QWidget] = {}
        self.help_section_advanced: Dict[str, bool] = {}
        left_layout.addWidget(category_tabs, 1)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 4, 6, 4)
        right_layout.setSpacing(6)
        self.main_splitter.addWidget(right)
        left.setMinimumWidth(400)
        right.setMinimumWidth(600)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setStretchFactor(0, 4)
        self.main_splitter.setStretchFactor(1, 7)
        self.main_splitter.setSizes([520, 900])

        self.status_badge = QLabel("READY")
        self.status_badge.setObjectName("statusBadge")
        self.status_badge.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(create_phase_studio_context_banner(
            "RUN OVERVIEW", "Phasing progress and results", badge=self.status_badge
        ))

        # Basic / Input
        self._build_input_tab()
        # Basic / Workflow
        self._build_workflow_tab()

        # Basic / Output
        self._build_output_tab()

        # Basic / Map feedback
        self._build_map_feedback_tab()

        # Basic / Help
        self._build_basic_help_tab()

        self._build_advanced_setup_tab()
        self._build_advanced_superflip_tab()
        self._build_advanced_edma_tab()
        self._build_advanced_sharped_tab()
        self._build_advanced_help_tab()

        # Persistent actions
        self._build_run_controls(left_layout)

        # Right-side resizable scientific dashboard
        self.result_splitter = QSplitter(Qt.Vertical)
        self.result_splitter.setObjectName("resultSplitter")
        self.result_splitter.setHandleWidth(3)
        self.result_splitter.setChildrenCollapsible(False)
        right_layout.addWidget(self.result_splitter, 1)

        self._build_metrics_section()
        self._build_structure_comparison_section()
        self._build_execution_log_section()
        self._last_log_record: Optional[ExecutionLogRecord] = None
        self._append_execution_log("Ready. Select an input to begin.")
        self._update_action_states()
        self._update_plot()
        self._update_structure_views()
        self._sync_input_source_mode_widgets()
        self._sync_workflow_widgets()
        self._sync_map_feedback_widgets()
        self._sync_normalization_widgets()

    def _build_basic_help_tab(self) -> None:
        basic_help_tab = self._add_settings_tab("Help")
        basic_contents_row = QHBoxLayout()
        basic_contents_row.setSpacing(4)
        basic_contents_label = QLabel("CONTENTS")
        basic_contents_label.setObjectName("helpContentsLabel")
        basic_contents_row.addWidget(basic_contents_label)
        for link_text, anchor in (
            ("Setup", "setup"), ("Input", "input"), ("Workflow", "workflow"),
            ("Output", "output"), ("Feedback", "map_feedback"), ("Jana2020", "jana_integration"), ("About", "about"),
        ):
            link = QToolButton()
            link.setObjectName("helpNavLink")
            link.setText(link_text)
            link.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            link.setCursor(Qt.PointingHandCursor)
            link.clicked.connect(lambda _checked=False, target=anchor: self._open_help_section(target))
            basic_contents_row.addWidget(link)
        basic_contents_row.addStretch(1)
        basic_help_tab.addLayout(basic_contents_row)
        setup_help_layout = self._add_help_section(basic_help_tab, "setup", "Systematic setup guide", """
            <h3>1. Select the input</h3>
            <p>Phase Studio can use a Jana2020 <b>.inflip</b> file, a Jana2020 .inflip file with selected external overrides, or an external HKL file.</p>
            <p><b>Crystal metadata</b> independently selects the authoritative unit cell, space group and composition: Jana2020 .inflip, the selected reference structure, or validated manual input. External HKL data therefore do not require a CIF when complete manual metadata are supplied.</p>
            <p>For external reflections, select the exact HKL column order first. Use <b>Validate HKL</b> to verify how columns were parsed and <b>Analyze completeness</b> to inspect completeness and data quality before reconstruction.</p>
            <h3>2. Choose a reconstruction preset</h3>
            <p><b>Workflow preset</b> (Basic &rarr; Workflow) applies a bundle of starting values in one step; every value stays individually editable afterward. Use it as a starting point, then adjust parameters only when necessary.</p>
            <ul><li><b>Recommended</b> (default): a general-purpose baseline that matches the built-in defaults.</li>
            <li><b>small molecule:</b> settings intended as a starting point for small-molecule data.</li>
            <li><b>inorganic:</b> settings intended as a starting point for inorganic materials.</li>
            <li><b>MOF atomic resolution:</b> settings intended as a starting point for atomic-resolution framework data.</li>
            <li><b>MOF medium resolution:</b> settings intended as a starting point for medium-resolution framework data.</li>
            <li><b>Custom:</b> applies nothing; a placeholder for manually configured values.</li></ul>
            <p>Applying a preset changes multiple controls. Review the resulting values and adapt them to the dataset; a preset is not a universal scientific recommendation.</p>
            <p><b>Phasing method</b> defaults to the standard Superflip cycle. Two SharpED phase-recycling methods, one beta and one experimental, are hidden by default; enable <b>Show beta and experimental features</b> on Advanced &rarr; Setup to make them selectable.</p>
            <h3>3. Configure the iterative workflow</h3>
            <p><b>observed reflections &rarr; Superflip &rarr; XPLOR map &rarr; EDMA and/or SharpED &rarr; deblurred XPLOR &rarr; EDMA &rarr; next-cycle model</b></p>
            <p>The exact branches depend on <b>Basic &rarr; Workflow &rarr; Optional processing</b>. The next-cycle source can be Superflip XPLOR, SharpED/deblurred XPLOR, deblurred EDMA CIF, or <b>none</b>. Selecting none forces a one-cycle run.</p>
            <h3>4. Inspect each cycle</h3>
            <p>Review convergence metrics, structure previews, detected atom/peak counts, reference agreement when available, Superflip versus SharpED results, and the execution log. Phase Studio does not replace final crystallographic refinement.</p>
            <h3>5. Return the selected result to Jana2020</h3>
            <p>After a successful run, <b>Send to Jana2020</b> lets you select a completed cycle and map source. Final interpretation and refinement remain in Jana2020.</p>
        """)
        setup_help_layout.insertWidget(1, WorkflowDiagram())
        self._add_help_callout(setup_help_layout, "Tip", "Validate the reflection interpretation and review the selected preset values before starting a run.")
        self._add_back_to_contents(setup_help_layout)
        input_help_layout = self._add_help_section(basic_help_tab, "input", "Input reference", """
            <h3>Data input</h3>
            <p><b>Input mode</b> chooses the reflection source: <b>Jana2020 .inflip</b>, <b>Jana2020 .inflip with overrides</b>, or <b>External HKL</b>. In Jana modes, the .inflip file's fbegin/endf block is the default HKL source and its cell/space-group/composition keywords can provide crystallographic metadata; External mode uses reflection data loaded independently of Jana2020 and requires metadata from another source.</p>
            <p><b>Jana2020 .inflip file</b> is the Superflip input file used by the two Jana input modes.</p>
            <p><b>External HKL file</b> replaces only the fbegin/endf block in override mode, or is the required reflection source in external mode.</p>
            <p><b>HKL format</b> is the exact column order of the reflection data. <code>set from inflip</code> imports the format from Jana, including a <code>dataformat ... fwhm</code> line; the other modes accept intensity or amplitude followed by sigma, optionally with a phase column in degrees before sigma. <b>hkl I fwhm</b> and <b>hkl F fwhm</b> are for data whose second column is a peak-shape FWHM (e.g. from a Le Bail powder extraction) rather than a genuine uncertainty -- Validate HKL and Analyze completeness relabel sigma-based columns and statistics accordingly (I/FWHM instead of I/&sigma;(I)) and hide the I/&sigma;(I)=3 significance threshold, which does not apply to FWHM data.</p>
            <p><b>Validate HKL</b> parses the selected HKL or .inflip reflection block and shows which h, k, l, value, sigma and phase fields were read. <b>Analyze completeness</b> opens completeness and data-statistics plots (d<sub>min</sub>, resolution-dependent completeness, mean I/&sigma;(I)) for the selected data.</p>
            <h3>Crystal metadata</h3>
            <p><b>Metadata source</b> is the authoritative source for unit cell, space group and composition: <b>Jana2020 .inflip</b>, the selected <b>Reference file</b>, or <b>Manual</b> entry. Phase Studio does not silently combine metadata from more than one source.</p>
            <p>When <b>Manual</b> is selected: <b>a, b, c</b> (&Aring;) and <b>alpha, beta, gamma</b> (&deg;) are the unit-cell parameters; <b>Number</b> (1-230) or <b>Symbol</b> identifies the space group; <b>Composition</b> uses Superflip syntax, for example <code>Ag196 S108 O40 B1000</code>.</p>
            <h3>Reference and initial model</h3>
            <p><b>Reference file</b> is an optional external reference: CIF/INS/RES files can supply metadata and atom sites used for comparison metrics; Jana/XPLOR/CCP4 maps can serve as a Superflip reference density (referencefile keyword), which also anchors the reciprocal-space origin from cycle 2 onward when no explicit reference is chosen.</p>
            <p><b>Initial model (cycle 1)</b> is an optional external density or structure model that seeds the first Superflip cycle. Supported inputs are XPLOR, CCP4 and CIF.</p>
        """)
        self._add_back_to_contents(input_help_layout)
        workflow_help_layout = self._add_help_section(basic_help_tab, "workflow", "Workflow reference", """
            <h3>Reconstruction</h3>
            <p><b>Workflow preset</b> applies a bundle of starting values in one step; every value stays individually editable afterward. <b>Recommended</b> (default) is a general-purpose baseline matching the built-in defaults; the MOF/small-molecule/inorganic presets tune values for a specific sample type; <b>Custom</b> applies nothing.</p>
            <p><b>Cycles</b> is the number of iterative Superflip &rarr; EDMA &rarr; SharpED &rarr; EDMA cycles to run. The effective count is forced to 1 when Next-cycle model is <code>none</code>.</p>
            <p><b>Phasing method</b> chooses the reconstruction algorithm:</p>
            <ul>
                <li><b>Superflip</b> (default) &mdash; the standard charge-flipping cycle: Superflip runs every cycle, seeded by Next-cycle model.</li>
                <li><b>1st Superflip, then SharpED (beta)</b> &mdash; Superflip runs only once, on cycle 1. Every following cycle deblurs the previous map with SharpED, calculates phases by FFT from that deblurred map for every measured reflection (expanded over the full space-group symmetry), and recomposes a map from |Fobs| with those phases for the next cycle. Does not work well with some models.</li>
                <li><b>SharpED (experimental)</b> &mdash; the same recycling loop, but skips Superflip entirely: cycle 1 starts from a map synthesized directly from |Fobs| with independent random phases. Not production-ready; can take hundreds of cycles to converge, if it converges at all.</li>
            </ul>
            <p>Both recycling methods are hidden unless <b>Show beta and experimental features</b> is checked on Advanced &rarr; Setup. Selecting one disables Next-cycle model, XPLOR damping, Symmetrize SharpED map and the per-cycle EDMA checkboxes below it, since the method defines its own next-cycle map; use <b>Run EDMA on final map</b> (Optional processing) instead. The convergence graph adds a <b>Map correlation</b> series for these methods (each cycle's recomposed map compared with the previous cycle's).</p>
            <p><b>Next-cycle model</b> (Superflip phasing method only) is the authoritative source for cycle 2 onward: <b>None</b> forces a one-cycle run; <b>Superflip map (XPLOR)</b> cycles without SharpED processing; <b>SharpED map (XPLOR)</b> uses the SharpED-processed XPLOR map; <b>SharpED structure (EDMA CIF)</b> uses the EDMA structure extracted from the SharpED map and ignores XPLOR damping.</p>
            <p><b>XPLOR damping (1/x)</b> (Superflip phasing method, XPLOR next-cycle models only) is the inverse damping factor: 1.0 means no damping, 0.5 is equivalent to the previous factor 2.0, 0.25 to factor 4.0.</p>
            <p><b>Excluded atoms</b> removes selected atom labels from CIF modelfiles before the next Superflip cycle (comma/semicolon/whitespace-separated); it does not apply to XPLOR-only model paths.</p>
            <h3>SharpED model</h3>
            <p><b>Model</b> is the SharpED server model name sent with every deblurring request; <b>Refresh models</b> fetches the current list from the configured server and updates this selector. Server URL and API token are on Advanced &rarr; Setup; elements, output resolution and network/upload settings are on Advanced &rarr; SharpED.</p>
            <h3>Optional processing</h3>
            <p>Under <b>Superflip cycle</b> (used when Phasing method is Superflip):</p>
            <ul>
                <li><b>Run EDMA on Superflip map</b> &mdash; peak-search the Superflip XPLOR map and export CIF/XYZ/PDB.</li>
                <li><b>Run SharpED</b> &mdash; process the Superflip map with the SharpED server. If disabled, the SharpED map used downstream is just a copy of the Superflip map.</li>
                <li><b>Symmetrize SharpED map with Superflip (beta)</b> &mdash; after SharpED processing, run Superflip in symmetry mode (no charge flipping) with the SharpED map as modelfile, averaging it according to the supplied space-group symmetry. Hidden unless beta/experimental features are enabled.</li>
                <li><b>Run EDMA on SharpED map</b> &mdash; peak-search the SharpED (or symmetrized) XPLOR map and export CIF/XYZ/PDB.</li>
                <li><b>Compute OMIT validation maps (5% holdout)</b> &mdash; each cycle, additionally run Superflip (and SharpED, if enabled) on a fixed random 5% of reflections excluded from the input, purely for cross-validation. Populates the omit-map correlation series on the <b>Superflip validation</b> and <b>SharpED validation</b> tabs. Roughly doubles Superflip/SharpED time per cycle.</li>
                <li><b>Calculate R_free on the 5% holdout</b> &mdash; requires the option above; also computes R_free (the crystallographic R-factor between the excluded reflections' observed |F| and |F| calculated by FFT from the omit map) for both the omit-map series.</li>
            </ul>
            <p>Under <b>Phase-recycling methods</b> (used by the two beta/experimental Phasing methods):</p>
            <ul><li><b>Run EDMA on final map</b> &mdash; run EDMA once, on the last cycle's recomposed |Fobs|+phi_calc map.</li></ul>
        """)
        self._add_back_to_contents(workflow_help_layout)
        output_help_layout = self._add_help_section(basic_help_tab, "output", "Output reference", """
            <h3>Output</h3>
            <p><b>Working directory</b> is where Phase Studio writes generated HKL files, Superflip inputs, maps, EDMA results, logs and metrics. Use a dedicated directory per run when reproducibility matters.</p>
            <p><b>Map format</b> adds one extra saved output on top of the XPLOR map that is always kept internally for EDMA, SharpED and Superflip: <code>ccp4</code> or <code>jana</code> save an extra CCP4 map or Jana m80/m81 density+reflection files; <b>HKL reflections with phases</b> and <b>ShelX (fcf)</b> instead save, for each cycle's Superflip map, the observed reflections (h k l, intensity/F&sup2;, sigma) together with phases &mdash; and, for ShelX, calculated F&sup2; &mdash; read by FFT from that map, as a standardized text file or a ShelX/Jana-compatible .fcf file, in place of an extra density map.</p>
            <p><b>Structure format</b> adds one extra saved structure format on top of the CIF that is always kept internally for metrics and next-cycle modelfiles: <code>xyz</code> or <code>pdb</code>.</p>
        """)
        self._add_back_to_contents(output_help_layout)
        map_feedback_layout = self._add_help_section(basic_help_tab, "map_feedback", "Map feedback reference", """
            <p>Each of the three mechanisms below has its own <b>Enable</b> checkbox at the top of its group; unchecking it grays out the rest of that group and skips the mechanism entirely. <b>Start after cycle</b> keeps its own 1-999 range regardless of the current <b>Cycles</b> value (Basic &rarr; Workflow), so it can be set up ahead of raising Cycles; the fields below it stay grayed out with a hint whenever the current Cycles value cannot reach the configured starting cycle.</p>
            <h3>Missing-reflection completion</h3>
            <p><b>Start after cycle</b> is the first completed cycle whose map is used to add missing reflections for the next cycle. <b>Maximum added reflections (%)</b> caps generated missing reflections as a percent of the current reflection count, preventing feedback from overwhelming measured data.</p>
            <h3>Intensity correction</h3>
            <p><b>Start after cycle</b> is the first completed cycle whose map is used to damp observed intensities for the next cycle. <b>Correction damping</b> ranges from 0 (keeps observed values) to 1 (replaces them with scaled map-derived values). <b>Apply when value/&sigma; &lt;</b> limits correction to weak non-zero reflections below this value/&sigma;; 0 applies it to all non-zero reflections. The average intensity change across corrected reflections is plotted on the <b>Intensity correction</b> convergence tab (lower is better).</p>
            <h3>Powder overlap repartitioning</h3>
            <p>Only applies to reflections carrying an FWHM value (the <code>hkl I fwhm</code>/<code>hkl F fwhm</code> HKL formats). <b>Start after cycle</b> is the first completed cycle whose map is used to redistribute overlapping reflections for the next cycle. Reflections whose Bragg peaks overlap in a powder pattern -- delta(2θ) below <b>Separation factor</b> times the mean of their FWHM, Superflip's own <code>fwhmseparation</code> convention -- have their combined observed intensity redistributed between them using intensities calculated by FFT from that cycle's map (the SharpED map when SharpED deblurring is enabled, otherwise a copy of the Superflip map), blended by <b>Map ratio mix</b> (0 keeps the observed split, 1 uses the map split fully; default 1). The group total is always conserved. <b>Wavelength</b> is required to compute 2θ; if left at 0 it is auto-detected first from the loaded <code>.inflip</code> file's <code>lambda</code>/<code>wavelength</code> line, then from the reference file's <code>_diffrn_radiation_wavelength</code> tag -- enter it manually if neither source has it. Each time it runs, a <code>cycle_NNN_powder_repartitioning.log</code> file is written with the number of overlap groups considered, their average size, their average intensity change, and the before/after intensities for every reflection in the 3 groups with the largest d-spacing. The average intensity change per group is also plotted on the <b>Powder repartitioning</b> convergence tab (lower is better).</p>
        """)
        self._add_help_callout(map_feedback_layout, "Warning", "Missing-reflection completion and intensity correction rewrite the observed HKL data fed into later cycles, not just the model. Review the reconstruction carefully before trusting downstream cycles.")
        self._add_back_to_contents(map_feedback_layout)
        jana_integration_layout = self._add_help_section(basic_help_tab, "jana_integration", "Jana2020 integration", """
            <p>Phase Studio can install itself as Jana2020's active Superflip launcher, so that Jana2020's own
            "Superflip" action opens the Phase Studio Jana2020 Wizard instead of running Superflip directly.
            This is entirely optional and separate from using Phase Studio as a standalone application.</p>
            <h3>Install to Jana2020</h3>
            <p>When Phase Studio is launched normally (not from the Jana2020 Wizard), the third main-window button
            reads <b>Install to Jana2020</b> and opens the Jana2020 integration dialog. It detects an existing
            Jana2020 installation (starting with <code>C:\\Jana2020</code>), or a folder can be selected manually.
            Installing:</p>
            <ul>
                <li>preserves Jana2020's existing Superflip executable as <code>superflip_original.exe</code>,</li>
                <li>installs the Phase Studio Jana2020 launcher as <code>superflip.exe</code> in its place, together with its required runtime files,</li>
                <li>leaves <code>EDMA.exe</code> and all Jana2020 crystallographic project data unchanged.</li>
            </ul>
            <p>Nothing is modified merely by opening the dialog; only pressing <b>Install integration</b> (or
            <b>Update integration</b>/<b>Repair</b> once already installed) changes anything on disk, and only inside
            the selected Jana2020 <code>SUPERFLIP</code> folder.</p>
            <h3>Reversibility</h3>
            <p><b>Remove integration</b>, inside the same dialog, restores the preserved <code>superflip_original.exe</code>
            back to <code>superflip.exe</code> and removes the Phase Studio-owned launcher and its runtime files.
            Jana2020 then runs its own original Superflip exactly as before Phase Studio was ever installed.</p>
            <h3>Send to Jana2020</h3>
            <p>When Phase Studio is instead launched <i>from</i> the Jana2020 Wizard (via the installed launcher, or
            "Open full configuration"), the same button reads <b>Send to Jana2020</b> and opens the existing
            Superflip/SharpED cycle-result selection and handoff dialog described above -- unrelated to installing
            or removing the integration itself.</p>
        """)
        self._add_help_callout(jana_integration_layout, "Note", "Installing or removing the Jana2020 integration only manages the superflip.exe launcher inside the selected Jana2020 SUPERFLIP folder. It never modifies crystallographic project data, and a completed Phase Studio run is never required to install, update, repair or remove it.")
        self._add_back_to_contents(jana_integration_layout)
        about_layout = self._add_help_section(basic_help_tab, "about", "About Phase Studio", """
            <h2>Phase Studio</h2>
            <p>Phase Studio is a crystallographic reconstruction workflow integrating Superflip, SharpED and EDMA with Jana2020-oriented workflows.</p>
            <h3>Developed at</h3>
            <p>Department of Structure Analysis<br>Institute of Physics of the Czech Academy of Sciences</p>
            <h3>Authors and contacts</h3>
            <p><b>Jiří Zelenka</b><br><a href="mailto:zelenka@fzu.cz">zelenka@fzu.cz</a></p>
            <p><b>Jan Rohlíček</b><br><a href="mailto:rohlicek@fzu.cz">rohlicek@fzu.cz</a></p>
            <p><b>Monika Kučeráková</b></p><p><b>Zdeněk Buk</b></p>
            <p><b>General contact</b><br><a href="mailto:sharped@fzu.cz">sharped@fzu.cz</a></p>
            <h3>Project resources</h3>
        """)
        for resource_name, resource_url, resource_tip in (
            ("Department of Structure Analysis", "https://www.fzu.cz/en/research/divisions-and-departments/division-3/department-19", "Open the department website"),
            ("SharpED project and API token", "https://sharped.fzu.cz/", "Open the SharpED project and API-token page"),
            ("Phase Studio source code", "https://github.com/ji-ze/Phase-Studio", "Open the Phase Studio source repository"),
        ):
            resource_row = QHBoxLayout()
            resource_row.addWidget(QLabel(resource_name))
            resource_row.addWidget(self._external_link_icon(resource_url, resource_tip))
            resource_row.addStretch(1)
            about_layout.addLayout(resource_row)
        self._add_back_to_contents(about_layout)
        basic_help_tab.addSpacing(CONFIG_MAJOR_SECTION_SPACING)
        basic_help_tab.addStretch(1)

    def _build_advanced_setup_tab(self) -> None:
        setup_tab = self._add_settings_tab("Setup", advanced=True)
        programs_form = self._add_form_group(setup_tab, "External programs")
        self._add_path(programs_form, "superflip_exe", "Superflip executable", r"C:\Jana2020\SUPERFLIP\superflip_original.exe", "file", "Executables (*.exe);;All files (*)")
        self._add_path(programs_form, "edma_exe", "EDMA executable", r"C:\Jana2020\SUPERFLIP\EDMA.exe", "file", "Executables (*.exe);;All files (*)")
        program_links = QVBoxLayout()
        program_links.setSpacing(3)
        for program_name, tooltip in (
            ("Superflip website", "Open the official Superflip website"),
            ("EDMA website", "Open the official EDMA website"),
        ):
            program_row = QHBoxLayout()
            program_row.addWidget(QLabel(program_name))
            program_row.addWidget(self._external_link_icon("https://superflip.fzu.cz/", tooltip))
            program_row.addStretch(1)
            program_links.addLayout(program_row)
        programs_form.addRow("Downloads", program_links)

        sharped_api_form = self._add_form_group(setup_tab, "SharpED connection")
        self._add_text(sharped_api_form, "sharped_base_url", "Server URL", "https://jana.fzu.cz")
        self._add_text(sharped_api_form, "sharped_api_token", "API token", os.environ.get("SHARPED_API_TOKEN", ""))
        try:
            self.inputs["sharped_api_token"].setEchoMode(QLineEdit.Password)  # type: ignore[attr-defined]
        except Exception:
            pass
        token_link_row = QHBoxLayout()
        token_link_row.addWidget(QLabel("Get SharpED token"))
        token_link_row.addWidget(self._external_link_icon("https://sharped.fzu.cz/", "Open the SharpED project and API-token page"))
        token_link_row.addStretch(1)
        sharped_api_form.addRow("", token_link_row)

        interface_form = self._add_form_group(setup_tab, "Interface")
        self._add_checkbox(interface_form, "show_beta_features", "Show beta and experimental features", False, align_with_fields=True)
        try:
            self.inputs["show_beta_features"].toggled.connect(self._sync_workflow_widgets)  # type: ignore[attr-defined]
        except Exception:
            pass
        interface_form.addRow("", self._secondary_help(
            "Off by default. Enable this option to expose experimental phasing methods and their "
            "method-specific settings, hidden entirely rather than just disabled while it is off."
        ))
        setup_tab.addSpacing(CONFIG_MAJOR_SECTION_SPACING)
        setup_tab.addStretch(1)

    def _build_advanced_superflip_tab(self) -> None:
        superflip_tab = self._add_settings_tab("Superflip", advanced=True)
        calculation_form = self._add_form_group(superflip_tab, "Calculation", "superflip")
        self._add_combo(calculation_form, "perform_algorithm", "Algorithm", ["CF", "AAR", "lde", "general", "fourier", "symmetry"], "CF")
        self.inputs["perform_algorithm"].setToolTip(
            INPUT_TOOLTIPS["perform_algorithm"]
        )  # type: ignore[attr-defined]
        self._add_spin(calculation_form, "maxcycles", "Maximum iterations", 2000, 1, 100000, 100)
        self._add_spin(calculation_form, "repeatmode", "Repeat mode", 10, 1, 10000, 1)
        self._add_text(calculation_form, "randomseed", "Random seed", "AUTO")
        self._add_text(calculation_form, "delta", "Delta", "AUTO")
        self._add_text(calculation_form, "weakratio", "Weak ratio", "0.000")
        self._add_text(calculation_form, "biso", "Biso", "0.000")
        self._add_checkbox(calculation_form, "polish", "Enable final polish", True, align_with_fields=True)

        density_form = self._add_form_group(superflip_tab, "Density / solution selection")
        self._add_text(density_form, "voxel", "Voxel grid", "")
        self._add_spin(density_form, "bestdensities_count", "Stored best densities", 1, 1, 100, 1)
        self._add_combo(density_form, "bestdensities_metric", "Density selection metric", ["rvalue", "peakiness", "symmetry", "reference"], "symmetry")
        self._add_combo(density_form, "searchsymmetry", "Search symmetry", ["average", "shift", "no"], "average")
        self._add_text(density_form, "derivesymmetry", "Derive symmetry", "yes")

        reflection_form = self._add_form_group(superflip_tab, "Reflection handling")
        self._add_dspin(reflection_form, "i_over_sigma_min", "Minimum observed value/σ", 2.0, 0.0, 100.0, 0.5, 3)
        self._add_dspin(reflection_form, "resolution_d_min", "High-resolution cutoff dmin (Å)", 0.0, 0.0, 20.0, 0.1, 3)
        self._add_combo(reflection_form, "normalize", "Normalization", ["none", "local", "atoms", "wilson"], "atoms")
        try:
            self.inputs["normalize"].currentTextChanged.connect(self._sync_normalization_widgets)  # type: ignore[attr-defined]
        except Exception:
            pass
        self._add_spin(reflection_form, "nresshells", "Resolution shells", 100, 0, 100000, 10)
        self._add_text(reflection_form, "missing", "Missing reflections", "bound 0.5 2.5")
        self._add_text(reflection_form, "electrons", "Electrons", "")

        reference_density_form = self._add_form_group(superflip_tab, "Reference density")
        reference_density_form.addRow(self._secondary_help(
            "The referencefile keyword is automatic: it is written only when a reference file is selected on Model, or "
            "from cycle 2 onward when none is selected, using the previous cycle's EDMA CIF (or its XPLOR map if EDMA "
            "produced no usable peaks) so Superflip keeps a fixed origin in reciprocal space between cycles."
        ))
        reference_density_form.addRow(self._secondary_help(
            "dataitemwidths is unnecessary because Phase Studio writes whitespace-separated fbegin/endf records."
        ))

        additional_sf_form = self._add_form_group(superflip_tab, "Additional keywords")
        self._add_multiline(additional_sf_form, "extra_superflip_keywords", "Extra Superflip keywords", "", 110)
        self.load_inflip_btn = QPushButton("Load settings from .inflip")
        self.load_inflip_btn.setToolTip("Read Superflip keyword settings from an existing .inflip file. Reflection data blocks are ignored.")
        self.load_inflip_btn.clicked.connect(self.load_inflip_settings_dialog)
        additional_sf_form.addRow("", self.load_inflip_btn)
        superflip_tab.addSpacing(CONFIG_MAJOR_SECTION_SPACING)
        superflip_tab.addStretch(1)

    def _build_advanced_edma_tab(self) -> None:
        edma_tab = self._add_settings_tab("EDMA", advanced=True)
        peak_form = self._add_form_group(edma_tab, "Peak extraction", "edma")
        self._add_dspin(peak_form, "plimit_superflip", "Superflip threshold", 0.5, 0.0, 100.0, 0.1, 3)
        self._add_dspin(peak_form, "plimit_deblur", "SharpED threshold (σ)", 0.5, 0.0, 100.0, 0.1, 3)
        self._add_text(peak_form, "edma_maxima", "Maxima selection", "all")
        self._add_text(peak_form, "edma_numberofatoms", "Atom-count mode", "composition")

        symmetry_form = self._add_form_group(edma_tab, "Symmetry and peak positions")
        self._add_dspin(symmetry_form, "merge_distance", "Merge distance (Å)", 0.75, 0.0, 10.0, 0.05, 3)
        self._add_combo(symmetry_form, "edma_fullcell", "Full-cell", ["no", "yes"], "no")
        self._add_checkbox(symmetry_form, "edma_centerofcharge", "Use center of charge", True, align_with_fields=True)

        chemical_form = self._add_form_group(edma_tab, "Chemical filtering")
        self._add_text(chemical_form, "edma_chlimit", "Charge limit", "0.2500")
        self._add_text(chemical_form, "edma_chlimlist", "Charge-list threshold", "0.0057 relative")

        edma_extra_form = self._add_form_group(edma_tab, "Additional keywords")
        self._add_multiline(edma_extra_form, "extra_edma_keywords", "Extra EDMA keywords", "", 110)
        edma_tab.addSpacing(CONFIG_MAJOR_SECTION_SPACING)
        edma_tab.addStretch(1)

    def _build_advanced_sharped_tab(self) -> None:
        sharped_advanced_tab = self._add_settings_tab("SharpED", advanced=True)
        inference_form = self._add_form_group(sharped_advanced_tab, "Inference")
        self._add_text(inference_form, "sharped_elements", "Elements", "")
        self.inputs["sharped_elements"].setPlaceholderText("Auto from composition")  # type: ignore[attr-defined]
        self._add_dspin(inference_form, "sharped_outres", "Output resolution (Å)", 0.2, 0.001, 10.0, 0.05, 4)

        network_form = self._add_form_group(sharped_advanced_tab, "Transfer and network")
        self._add_dspin(network_form, "sharped_max_upload_mb", "Upload limit (MB)", 100.0, 0.0, 100000.0, 10.0, 1)
        self._add_spin(network_form, "sharped_timeout_seconds", "HTTP timeout (s)", 600, 600, 7200, 60)
        self._add_spin(network_form, "sharped_poll_seconds", "Polling interval (s)", 2, 1, 3600, 1)
        self._add_spin(network_form, "sharped_max_polls", "Maximum polls", -1, -1, 1000000, 1)
        max_polls_widget = self.inputs.get("sharped_max_polls")
        if isinstance(max_polls_widget, QSpinBox):
            max_polls_widget.setSpecialValueText("Unlimited")
        sharped_advanced_tab.addSpacing(CONFIG_MAJOR_SECTION_SPACING)
        sharped_advanced_tab.addStretch(1)

    def _build_advanced_help_tab(self) -> None:
        advanced_help_tab = self._add_settings_tab("Help", advanced=True)
        advanced_contents_row = QHBoxLayout()
        advanced_contents_row.setSpacing(4)
        advanced_contents_label = QLabel("CONTENTS")
        advanced_contents_label.setObjectName("helpContentsLabel")
        advanced_contents_row.addWidget(advanced_contents_label)
        for link_text, anchor in (
            ("Setup", "adv_setup"), ("Superflip", "superflip"), ("EDMA", "edma"),
            ("SharpED", "sharped"), ("Keywords", "keyword_reference"),
        ):
            link = QToolButton()
            link.setObjectName("helpNavLink")
            link.setText(link_text)
            link.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            link.setCursor(Qt.PointingHandCursor)
            link.clicked.connect(lambda _checked=False, target=anchor: self._open_help_section(target))
            advanced_contents_row.addWidget(link)
        advanced_contents_row.addStretch(1)
        advanced_help_tab.addLayout(advanced_contents_row)
        adv_setup_help_layout = self._add_help_section(advanced_help_tab, "adv_setup", "Setup reference", """
            <h3>External programs</h3>
            <p><b>Superflip executable</b> is the absolute path to the original Jana2020 Superflip executable (default <code>C:\\Jana2020\\SUPERFLIP\\superflip_original.exe</code>). Do not select the Phase Studio wrapper named superflip.exe.</p>
            <p><b>EDMA executable</b> is the absolute path to the Jana2020 EDMA executable used for peak extraction and structure export from XPLOR density maps (default <code>C:\\Jana2020\\SUPERFLIP\\EDMA.exe</code>).</p>
            <h3>SharpED connection</h3>
            <p><b>Server URL</b> is the SharpED inference-server base URL; the reference client uses <code>https://jana.fzu.cz</code>. <b>API token</b> authorizes upload/status/download requests and is never written to logs or error messages.</p>
            <h3>Interface</h3>
            <p><b>Show beta and experimental features</b> is unchecked by default. While off, the beta/experimental Phasing methods and Symmetrize SharpED map with Superflip (beta) are removed from the Basic tabs entirely, not just disabled. Enable it to make them selectable; turning it off again while one is active falls back to standard Superflip.</p>
        """, advanced=True)
        self._add_back_to_contents(adv_setup_help_layout, advanced=True)
        superflip_help_layout = self._add_help_section(advanced_help_tab, "superflip", "Superflip guide", """
            <h3>What Superflip does</h3>
            <p>Superflip is the density-reconstruction and phase-retrieval stage. Phase Studio prepares reflections, crystallographic metadata and input, executes Superflip, then uses its density map for direct inspection, EDMA peak extraction, SharpED processing and iterative feedback.</p>
            <h3>Calculation</h3>
            <p><b>Algorithm</b> maps to Superflip's <code>perform</code> keyword; common values are <code>CF</code> (normal charge-flipping, used by the presets), <code>lde</code>, <code>general</code>, <code>fourier</code> and <code>symmetry</code>; <code>AAR</code> is kept for executables that support it.</p>
            <p><b>Maximum iterations</b> limits one Superflip run. <b>Repeat mode</b> controls repeated independent attempts and convergence sampling. <b>Random seed</b> initializes random numbers; use a fixed value for reproducibility or Superflip's automatic syntax. <b>Delta</b> (<code>AUTO</code> lets Superflip estimate the flip threshold), <b>Weak ratio</b> and <b>Biso</b> (overall isotropic B-factor used to sharpen the map; 0.000 disables sharpening) are advanced parameters normally left at preset/default values. <b>Enable final polish</b> adds <code>polish yes</code>, activating Superflip's final polishing stage when supported.</p>
            <h3>Density / solution selection</h3>
            <p><b>Voxel grid</b> is the Superflip <code>voxel</code> keyword: blank omits it; three integers set an explicit grid; <code>AUTO</code> computes a 0.2 &Aring; grid from the unit cell.</p>
            <p><b>Stored best densities</b> and <b>Density selection metric</b> are the two arguments of <code>bestdensities</code> &mdash; how many best density maps Superflip keeps, and whether it selects by rvalue, peakiness, symmetry or reference agreement. Selecting <b>symmetry</b> biases selection toward symmetry-consistent solutions.</p>
            <p><b>Search symmetry</b> maps to <code>searchsymmetry</code> (<code>no</code>, <code>shift</code> or <code>average</code>). <b>Derive symmetry</b> maps to <code>derivesymmetry</code> (commonly <code>yes</code>, <code>no</code> or <code>use</code>, depending on the Superflip version).</p>
            <h3>Reflection handling</h3>
            <p><b>Minimum observed value/&sigma;</b> filters weak observed reflections before writing the Superflip HKL block. <b>High-resolution cutoff d<sub>min</sub> (&Aring;)</b> is an optional resolution cutoff; 0 keeps all reflections. <b>Normalization</b> is an optional reflection-normalization keyword (<code>none</code> is the safest default for the Windows executable). <b>Resolution shells</b> is used only when a supported normalization keyword is written. <b>Missing reflections</b> supplies Superflip's <code>missing</code> line, for example bounds for missing reflections. <b>Electrons</b> is Superflip's <code>electrons</code> keyword; leave blank to omit it.</p>
            <h3>Reference density</h3>
            <p>The <code>referencefile</code> keyword is written automatically: from the selected Reference file when one is chosen on Basic &rarr; Input, or from cycle 2 onward when none is selected, using the previous cycle's EDMA CIF (or its XPLOR map if EDMA produced no usable peaks). This keeps Superflip's origin fixed in reciprocal space between cycles. <code>dataitemwidths</code> is unnecessary and not exposed, because Phase Studio always writes whitespace-separated fbegin/endf records.</p>
            <h3>Additional keywords</h3>
            <p><b>Extra Superflip keywords</b> lets expert users append documented keyword lines, inserted before <code>fbegin</code>, that are not represented by a dedicated control. <b>Load settings from .inflip</b> reads Superflip keyword settings from an existing .inflip file (reflection data blocks are ignored).</p>
            <h3>Output</h3>
            <p>XPLOR (map) and CIF (structure) are always produced internally because EDMA, SharpED and later-cycle modelfiles consume them; the <b>Map format</b> and <b>Structure format</b> choices on Basic &rarr; Output add one extra saved format on top for external inspection, molecular-graphics viewers or Jana2020.</p>
        """, advanced=True)
        self._add_help_callout(superflip_help_layout, "Starting point", "CF and the supplied preset values are initial settings only; choose parameters appropriate for the dataset and intended method.")
        self._add_back_to_contents(superflip_help_layout, advanced=True)
        edma_help_layout = self._add_help_section(advanced_help_tab, "edma", "EDMA guide", """
            <h3>What EDMA does in Phase Studio</h3>
            <p>EDMA extracts density maxima from an XPLOR map. Phase Studio uses these maxima to create structural models and exports, independently for the Superflip map and the SharpED map when enabled.</p>
            <h3>Peak extraction</h3>
            <p><b>Superflip threshold</b> and <b>SharpED threshold (&sigma;)</b> are multipliers of the corresponding map sigma; Phase Studio converts each multiplier to EDMA's absolute <code>plimit</code> for that map. A higher threshold is stricter; a lower threshold includes more maxima &mdash; there is no universal correct value. <b>Maxima selection = all</b> requests all maxima above plimit; advanced users may enter more restrictive documented EDMA syntax. <b>Atom-count mode = composition</b> requests atom counts consistent with the chemical composition.</p>
            <h3>Symmetry and peak positions</h3>
            <p><b>Merge distance</b> is the tolerance (&Aring;) used when reducing maxima to one representative per full space-group orbit for the CIF asymmetric unit. <b>Full-cell = no</b> requests symmetry-independent maxima when the supplied symmetry is correct; <code>yes</code> lists the full unit cell. <b>Use center of charge</b> refines peak positions to the center of charge of each density basin before export.</p>
            <h3>Chemical filtering</h3>
            <p><b>Charge limit</b> is the minimum integrated charge for exported maxima; useful for suppressing noise peaks in rough or over-sharpened maps. <b>Charge-list threshold</b> supplies EDMA's <code>chlimlist</code> setting, for example <code>0.0057 relative</code>, used together with atom-count/composition-based export.</p>
            <h3>Additional keywords</h3>
            <p><b>Extra EDMA keywords</b> appends documented EDMA options not represented by a dedicated control.</p>
        """, advanced=True)
        self._add_help_callout(edma_help_layout, "Important", "Select each EDMA threshold for its map and assess the resulting peaks; there is no universal threshold.")
        self._add_back_to_contents(edma_help_layout, advanced=True)
        sharped_help_layout = self._add_help_section(advanced_help_tab, "sharped", "SharpED guide", """
            <h3>What SharpED does</h3>
            <p>SharpED processes and deblurs the XPLOR density map from Superflip. After EDMA extraction the result can be inspected in Structure Comparison, used for EDMA, optionally symmetrized, used as a next-cycle XPLOR model, or handed to Jana2020. If server processing is disabled, the workflow continues without a genuinely processed SharpED result.</p>
            <p><b>Model</b> selection is on Basic &rarr; Workflow. Server connection is on Advanced &rarr; Setup (server URL/API token); elements, output resolution and upload/network settings are on Advanced &rarr; SharpED (everything else below).</p>
            <h3>1. Server connection</h3>
            <p><b>Server URL</b> is the inference-server address. <b>API token</b> authenticates server requests. Obtain a token from the SharpED project and API-token page.</p>
            <h3>2. Model and elements</h3>
            <p><b>Model</b> (Basic &rarr; Workflow) is sent to the server; <b>Refresh models</b> updates the selector; <code>default</code> uses the server default. <b>Elements</b> are sent to SharpED; when blank, Phase Studio derives unique non-hydrogen elements from the reference composition.</p>
            <h3>3. Output resolution</h3>
            <p><b>Output resolution (&Aring;)</b> is the requested sampling/resolution of the SharpED density map.</p>
            <h3>4. Upload and network</h3>
            <p><b>Upload limit</b> checks XPLOR size locally; its application default is 100 MB and 0 disables this local check (confirm the actual limit with the configured service). If Voxel grid is empty/omit, Phase Studio can add a coarser Superflip voxel keyword before map calculation so the native Superflip XPLOR fits under this limit. <b>HTTP timeout</b> covers model queries, upload, status and download requests and is enforced at 600 seconds minimum. <b>Polling interval</b> sets the delay between status checks. <b>Maximum polls</b> limits those checks; <b>-1</b> means no fixed polling limit.</p>
            <h3>5. SharpED in iterative workflows</h3>
            <p><b>Run SharpED</b> (Basic &rarr; Workflow &rarr; Optional processing) enables server processing; if disabled, the SharpED map used downstream is a copy of the Superflip map. <b>Symmetrize SharpED map with Superflip (beta)</b> performs symmetry averaging, not another charge-flipping reconstruction. Next-cycle model's <b>SharpED map (XPLOR)</b> option feeds the SharpED map into the next cycle; <b>SharpED structure (EDMA CIF)</b> feeds its EDMA structure instead.</p>
            <h3>6. Phase-recycling methods (beta/experimental)</h3>
            <p><b>1st Superflip, then SharpED (beta)</b> and <b>SharpED (experimental)</b> use SharpED for phase recycling instead of iterative Superflip cycling. They are hidden from the Phasing method list by default; check <b>Show beta and experimental features</b> (Advanced &rarr; Setup) to select them. Neither is production-ready.</p>
        """, advanced=True)
        sharped_link_row = QHBoxLayout()
        sharped_link_row.addWidget(QLabel("SharpED project and API token"))
        sharped_link_row.addWidget(self._external_link_icon("https://sharped.fzu.cz/", "Open the SharpED project and API-token page"))
        sharped_link_row.addStretch(1)
        sharped_help_layout.addLayout(sharped_link_row)
        self._add_help_callout(sharped_help_layout, "Important", "SharpED processing requires a valid API token and network access.")
        self._add_back_to_contents(sharped_help_layout, advanced=True)
        keyword_html = html.escape(SUPERFLIP_KEYWORD_REFERENCE).replace("\n", "<br>")
        keyword_help_layout = self._add_help_section(
            advanced_help_tab,
            "keyword_reference",
            "Advanced Superflip keyword reference",
            f'<p style="font-family: Cascadia Mono, Consolas, monospace; color: #2264b8;">{keyword_html}</p>',
            advanced=True,
        )
        self._add_back_to_contents(keyword_help_layout, advanced=True)
        advanced_help_tab.addSpacing(CONFIG_MAJOR_SECTION_SPACING)
        advanced_help_tab.addStretch(1)

    def _build_run_controls(self, left_layout: QVBoxLayout) -> None:
        primary_buttons = QHBoxLayout()
        primary_buttons.setSpacing(8)
        secondary_buttons = QHBoxLayout()
        secondary_buttons.setSpacing(8)
        self.run_btn = QPushButton("Run phasing")
        self.continue_btn = QPushButton("Continue run")
        self.stop_btn = QPushButton("Stop after current cycle")
        self.stop_now_btn = QPushButton("Stop immediately")
        self.clear_btn = QPushButton("Clear results")
        # Third primary action is context-sensitive: "Send to Jana2020" (a
        # result-hand-off action) when launched from the Jana2020 Wizard,
        # "Install to Jana2020" (an application-integration action, no run
        # required) for a normal standalone launch. handoff_btn is kept as a
        # compatibility alias -- existing call sites that disable it during
        # an active run (start_run/continue_run/error/cancel) stay correct
        # unchanged in both contexts, since "disable while running" applies
        # to either meaning of the button.
        self.jana_action_btn = QPushButton("Install to Jana2020")
        self.handoff_btn = self.jana_action_btn
        self.run_btn.setObjectName("primaryButton")
        self.continue_btn.setObjectName("continueButton")
        self.jana_action_btn.setObjectName("handoffButton")
        self.stop_btn.setObjectName("stopAfterButton")
        self.stop_now_btn.setObjectName("stopNowButton")
        self.clear_btn.setObjectName("clearButton")
        for action_button in (self.run_btn, self.continue_btn, self.stop_btn, self.stop_now_btn, self.clear_btn, self.jana_action_btn):
            action_button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.continue_btn.setEnabled(False)
        self.run_btn.setToolTip("Start the complete iterative crystallographic reconstruction workflow.")
        self.continue_btn.setToolTip(
            "Resume the previous run exactly where it stopped or finished, reusing the same metadata, "
            "reflections and cycle feedback. If it already reached the configured cycle count, increase "
            "Cycles above the completed count first."
        )
        self.stop_btn.setToolTip("Request a graceful stop after the currently running cycle has completed.")
        self.stop_now_btn.setToolTip("Terminate the currently running external Superflip/EDMA process and stop the pipeline as soon as possible.")
        self.clear_btn.setToolTip("Clear the log panel and reset the plotted metrics for the current GUI session.")
        self.run_btn.clicked.connect(self.start_run)
        self.continue_btn.clicked.connect(self.continue_run)
        self.stop_btn.clicked.connect(self.request_stop_after_cycle)
        self.stop_now_btn.clicked.connect(self.request_immediate_stop)
        self.clear_btn.clicked.connect(self.clear_log_plot)
        self.jana_action_btn.clicked.connect(self._on_jana_action_clicked)
        primary_buttons.addWidget(self.run_btn, 1)
        primary_buttons.addWidget(self.continue_btn, 1)
        primary_buttons.addWidget(self.jana_action_btn, 1)
        secondary_buttons.addWidget(self.stop_btn, 2)
        secondary_buttons.addWidget(self.stop_now_btn, 1)
        secondary_buttons.addWidget(self.clear_btn, 1)
        left_layout.addLayout(primary_buttons)
        left_layout.addLayout(secondary_buttons)
        # jana_wizard_context is still its standalone default at this point
        # in construction (a Wizard launch sets it right after this window
        # is constructed, then calls _sync_jana_action_button() again itself
        # -- see launch_phase_studio_from_jana()'s build_window()), so this
        # call establishes the correct standalone label/state immediately
        # for every OTHER launch path.
        self._sync_jana_action_button()
        self._sync_window_title()

        self.run_status_panel = QWidget()
        self.run_status_panel.setObjectName("runStatusPanel")
        run_status_layout = QVBoxLayout(self.run_status_panel)
        run_status_layout.setContentsMargins(8, 6, 8, 7)
        run_status_layout.setSpacing(3)
        run_status_title = QLabel("RUN STATUS")
        run_status_title.setObjectName("runStatusTitle")
        run_status_layout.addWidget(run_status_title)
        overall_progress_header = QHBoxLayout()
        self.overall_progress_label = QLabel("Overall")
        self.overall_progress_label.setObjectName("progressSectionLabel")
        self.overall_progress_value = QLabel("Idle")
        self.overall_progress_value.setObjectName("progressStageCounter")
        self.overall_progress_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        overall_progress_header.addWidget(self.overall_progress_label)
        overall_progress_header.addStretch(1)
        overall_progress_header.addWidget(self.overall_progress_value)
        run_status_layout.addLayout(overall_progress_header)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFormat("Idle")
        self.progress_bar.setToolTip("Cycle-level progress indicator for the iterative pipeline.")
        run_status_layout.addWidget(self.progress_bar)
        current_cycle_header = QHBoxLayout()
        current_cycle_label = QLabel("Current cycle")
        current_cycle_label.setObjectName("progressSectionLabel")
        self.current_cycle_stage_counter = QLabel("Idle")
        self.current_cycle_stage_counter.setObjectName("progressStageCounter")
        self.current_cycle_stage_counter.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        current_cycle_header.addWidget(current_cycle_label)
        current_cycle_header.addStretch(1)
        current_cycle_header.addWidget(self.current_cycle_stage_counter)
        run_status_layout.addLayout(current_cycle_header)
        self.current_cycle_detail = QLabel("Idle")
        self.current_cycle_detail.setObjectName("currentCycleDetail")
        self.current_cycle_detail.setWordWrap(True)
        run_status_layout.addWidget(self.current_cycle_detail)
        # Secondary, subordinate line for Superflip's own live repeatmode
        # progress (e.g. "Superflip repeat 17 of 50"). Hidden whenever there
        # is nothing live to show: repeatmode==1, a non-Superflip stage, or
        # between cycles -- see _apply_cycle_progress_state().
        self.superflip_repeat_detail = QLabel("")
        self.superflip_repeat_detail.setObjectName("superflipRepeatDetail")
        self.superflip_repeat_detail.setWordWrap(True)
        self.superflip_repeat_detail.setVisible(False)
        run_status_layout.addWidget(self.superflip_repeat_detail)
        self.superflip_repeat_progress = QProgressBar()
        self.superflip_repeat_progress.setObjectName("superflipRepeatProgress")
        self.superflip_repeat_progress.setRange(0, 1)
        self.superflip_repeat_progress.setValue(0)
        self.superflip_repeat_progress.setTextVisible(False)
        self.superflip_repeat_progress.setFixedHeight(6)
        self.superflip_repeat_progress.setToolTip("Superflip's own repeatmode attempt counter for the running Superflip stage -- subordinate to the stage progress above.")
        self.superflip_repeat_progress.setVisible(False)
        run_status_layout.addWidget(self.superflip_repeat_progress)
        self.current_cycle_progress = QProgressBar()
        self.current_cycle_progress.setObjectName("currentCycleProgress")
        self.current_cycle_progress.setRange(0, 1)
        self.current_cycle_progress.setValue(0)
        self.current_cycle_progress.setTextVisible(False)
        self.current_cycle_progress.setToolTip("Stage-based progress for the active cycle; this is not an elapsed-time estimate.")
        run_status_layout.addWidget(self.current_cycle_progress)
        self.configuration_lock_hint = QLabel("Configuration locked while the calculation is running.")
        self.configuration_lock_hint.setObjectName("configurationLockHint")
        self.configuration_lock_hint.setVisible(False)
        run_status_layout.addWidget(self.configuration_lock_hint)
        left_layout.addWidget(self.run_status_panel)
        self._set_run_status("Ready")

    def _build_metrics_section(self) -> None:
        metrics_section, metrics_layout = self._make_result_section("WORKFLOW METRICS")
        self.metrics_tabs = QTabWidget()
        self.metrics_tabs.setObjectName("metricsTabs")
        self.metrics_figures: Dict[str, Figure] = {}
        self.metrics_axes: Dict[str, object] = {}
        self.metrics_canvases: Dict[str, FigureCanvas] = {}
        self.metrics_interactions: Dict[str, MetricsPlotInteraction] = {}
        self._metrics_hover_series: Dict[str, list] = {}
        self._metrics_last_render_args: Dict[str, dict] = {}
        self._metrics_tab_keys: List[str] = []
        metrics_tab_tooltips = {
            "superflip": (
                "Reference match, SF RMSD, Recall and Precision compare directly against a supplied reference "
                "structure (Recall/Precision: heavy, i.e. non-H/He, atoms matched within EDMA's Merge distance), so "
                "they only appear when one is provided. Without a reference, Heavy atoms found (a simple count) "
                "appears instead as a fallback progress indicator."
            ),
            "deblur": (
                "SharpED RMSD, Recall and Precision compare directly against a supplied reference structure (Recall/"
                "Precision: heavy, i.e. non-H/He, atoms matched within EDMA's Merge distance), so they only appear "
                "when one is provided. Without a reference, Heavy atoms found appears instead as a fallback progress "
                "indicator. Map correlation only appears for the SharpED phase-recycling phasing methods."
            ),
            "powder_repartition": (
                "Average, across overlap groups, of each group's mean member-wise intensity change caused by that "
                "cycle's powder overlap repartitioning (Basic -> Map feedback). Only appears when repartitioning is "
                "enabled; lower is better, since it should shrink toward 0% as the map increasingly agrees with the "
                "observed data. Each cycle's point reflects the repartitioning that fed its input, so it lags one "
                "cycle behind the repartitioning run itself."
            ),
            "intensity_correction": (
                "Average, across corrected reflections, of the intensity change caused by that cycle's map-based "
                "intensity correction (Basic -> Map feedback -> Intensity correction). Only appears when intensity "
                "correction is enabled; lower is better, since it should shrink toward 0% as the map increasingly "
                "agrees with the observed data. Each cycle's point reflects the correction that fed its input, so it "
                "lags one cycle behind the correction run itself."
            ),
            "superflip_omit": "OMIT maps + R_free cross-validation for the Superflip map.",
            "deblur_omit": "OMIT maps + R_free cross-validation for the SharpED map.",
        }
        self._metrics_detail_supported_keys = {"powder_repartition", "intensity_correction"}
        for key, title in (
            ("superflip", "Superflip"),
            ("deblur", "SharpED"),
            ("superflip_omit", "Superflip validation"),
            ("deblur_omit", "SharpED validation"),
            ("powder_repartition", "Powder repartitioning"),
            ("intensity_correction", "Intensity correction"),
        ):
            # Each page is now JUST the canvas -- the interaction controls
            # (hint / Full range / Detail / Reset view) live once in the
            # QTabWidget's own corner, not a second per-tab toolbar row, so
            # every pixel of page height goes to the plot itself.
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, 0, 0, 0)
            page_layout.setSpacing(0)

            figure = Figure(figsize=(7.5, 3.5), dpi=100)
            canvas = FigureCanvas(figure)
            canvas.setObjectName("metricsCanvas")
            canvas.setMinimumHeight(140)
            canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            canvas.mpl_connect("resize_event", lambda _event, k=key: self._layout_metrics_figure(k))
            canvas.setToolTip("")
            canvas.setFocusPolicy(Qt.ClickFocus)
            page_layout.addWidget(canvas, 1)
            tab_index = self.metrics_tabs.addTab(page, title)
            if key in metrics_tab_tooltips:
                self.metrics_tabs.setTabToolTip(tab_index, metrics_tab_tooltips[key])
            self._metrics_tab_keys.append(key)
            self.metrics_figures[key] = figure
            self.metrics_axes[key] = figure.add_subplot(111)
            self.metrics_canvases[key] = canvas
            self.metrics_interactions[key] = MetricsPlotInteraction(
                key,
                canvas,
                get_axes=(lambda k=key: self.metrics_axes.get(k)),
                get_series=(lambda k=key: self._metrics_hover_series.get(k, [])),
                supports_detail=(key in self._metrics_detail_supported_keys),
                on_state_changed=self._on_metrics_view_changed,
                request_rerender=(lambda k=key: self._replay_metrics_tab(k)),
            )
        metrics_layout.addWidget(self.metrics_tabs, 1)

        # ----- Shared interaction control strip: lives in the tab bar's own
        # corner (same horizontal strip as the Superflip/SharpED/... tabs, not
        # a second row that eats into the plot) and always acts on whichever
        # tab is currently selected. -----
        metrics_corner = QWidget()
        metrics_corner_layout = QHBoxLayout(metrics_corner)
        metrics_corner_layout.setContentsMargins(6, 0, 4, 0)
        metrics_corner_layout.setSpacing(6)
        self.metrics_hint_label = QLabel("Wheel zoom · Drag pan · Double-click reset")
        self.metrics_hint_label.setObjectName("metricsHintLabel")
        metrics_corner_layout.addWidget(self.metrics_hint_label)
        self.metrics_full_range_btn = QPushButton("Full range")
        self.metrics_detail_btn = QPushButton("Detail")
        for btn in (self.metrics_full_range_btn, self.metrics_detail_btn):
            btn.setObjectName("metricsViewToggle")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
        metrics_mode_group = QButtonGroup(metrics_corner)
        metrics_mode_group.setExclusive(True)
        metrics_mode_group.addButton(self.metrics_full_range_btn)
        metrics_mode_group.addButton(self.metrics_detail_btn)
        self.metrics_full_range_btn.setChecked(True)
        self.metrics_full_range_btn.setToolTip("Show every value using the normal full y range.")
        self.metrics_detail_btn.setToolTip(
            "Focus the y range on the main body of values (robust to a single outlying cycle). "
            "Points outside the current view are not deleted -- they are simply off-screen."
        )
        self.metrics_full_range_btn.clicked.connect(lambda _checked=False: self._set_metrics_view_mode(self._current_metrics_key(), "full"))
        self.metrics_detail_btn.clicked.connect(lambda _checked=False: self._set_metrics_view_mode(self._current_metrics_key(), "detail"))
        metrics_corner_layout.addWidget(self.metrics_full_range_btn)
        metrics_corner_layout.addWidget(self.metrics_detail_btn)
        self.metrics_reset_btn = QPushButton("Reset view")
        self.metrics_reset_btn.setObjectName("metricsControlButton")
        self.metrics_reset_btn.setCursor(Qt.PointingHandCursor)
        self.metrics_reset_btn.setToolTip("Return to the automatically calculated full-data view.")
        self.metrics_reset_btn.setEnabled(False)
        self.metrics_reset_btn.clicked.connect(lambda _checked=False: self._reset_metrics_view(self._current_metrics_key()))
        metrics_corner_layout.addWidget(self.metrics_reset_btn)
        self.metrics_tabs.setCornerWidget(metrics_corner, Qt.TopRightCorner)
        self.metrics_tabs.currentChanged.connect(self._on_metrics_tab_changed)
        self._on_metrics_tab_changed(self.metrics_tabs.currentIndex())
        self.result_splitter.addWidget(metrics_section)

    def _build_structure_comparison_section(self) -> None:
        structure_section, structure_layout = self._make_result_section("STRUCTURE COMPARISON")
        self.structure_rotation_hint = QLabel("Drag to rotate all views · Hydrogen and helium atoms hidden")
        self.structure_rotation_hint.setObjectName("structureRotationHint")
        self.structure_rotation_hint.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.structure_rotation_hint.setVisible(False)
        structure_layout.addWidget(self.structure_rotation_hint)
        self.structure_figure = Figure(figsize=(7.5, 3.0), dpi=100)
        self.structure_canvas = FigureCanvas(self.structure_figure)
        self.structure_canvas.setObjectName("structureCanvas")
        self.structure_canvas.setMinimumHeight(260)
        self.structure_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.structure_canvas.setToolTip("")
        self.structure_canvas.mpl_connect("button_press_event", self._begin_structure_rotation)
        self.structure_canvas.mpl_connect("motion_notify_event", self._sync_structure_view_from_event)
        self.structure_canvas.mpl_connect("button_release_event", self._finish_structure_rotation)
        self.structure_canvas.mpl_connect("resize_event", lambda _event: self._layout_structure_figure())
        structure_layout.addWidget(self.structure_canvas, 1)
        self.result_splitter.addWidget(structure_section)

    def _build_execution_log_section(self) -> None:
        log_section, log_layout = self._make_result_section("EXECUTION LOG")
        self.log_text = QTextEdit()
        self.log_text.setObjectName("executionLog")
        self.log_text.setReadOnly(True)
        self.log_text.setLineWrapMode(QTextEdit.NoWrap)
        self.log_text.setMinimumHeight(100)
        self.log_text.setToolTip("")
        log_layout.addWidget(self.log_text, 1)
        self.result_splitter.addWidget(log_section)
        self.result_splitter.setStretchFactor(0, 2)
        self.result_splitter.setStretchFactor(1, 6)
        self.result_splitter.setStretchFactor(2, 2)
        self.result_splitter.setSizes([155, 425, 120])

    # ----- Basic-tab builders, one per tab, called in order from _build_ui.
    # Each assigns the same self.* attributes, connects the same signals, and
    # keeps the same widget defaults/tooltips/object names as before this
    # extraction (2026 maintainability refactor) -- purely a code-motion out
    # of _build_ui's own body, no behavior change. -----

    def _build_input_tab(self) -> None:
        input_tab = self._add_settings_tab("Input")
        data_input_form = self._add_form_group(input_tab, "Data input")
        self._add_combo(
            data_input_form,
            "input_source_mode",
            "Input mode",
            [
                INPUT_MODE_LABELS[INPUT_MODE_INFLIP],
                INPUT_MODE_LABELS[INPUT_MODE_INFLIP_OVERRIDES],
                INPUT_MODE_LABELS[INPUT_MODE_EXTERNAL],
            ],
            INPUT_MODE_LABELS[INPUT_MODE_INFLIP],
        )
        try:
            self.inputs["input_source_mode"].currentTextChanged.connect(self._sync_input_source_mode_widgets)  # type: ignore[attr-defined]
            self.inputs["input_source_mode"].activated.connect(self._input_mode_user_changed)  # type: ignore[attr-defined]
        except Exception:
            pass
        self._add_path(data_input_form, "jana_inflip", "Jana2020 .inflip file", "", "file", "Superflip input (*.inflip *.inp);;All files (*)")
        self._add_path(data_input_form, "hkl", "External HKL file", "", "file", "HKL files (*.hkl);;All files (*)")
        self._add_combo(
            data_input_form,
            "reflection_data_mode",
            "HKL format",
            [
                format_reflection_data_mode(REFLECTION_DATA_MODE_SET_FROM_INFLIP),
                format_reflection_data_mode(REFLECTION_DATA_MODE_INTENSITY),
                format_reflection_data_mode(REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA),
                format_reflection_data_mode(REFLECTION_DATA_MODE_INTENSITY_PHASE_SIGMA),
                format_reflection_data_mode(REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA),
                format_reflection_data_mode(REFLECTION_DATA_MODE_INTENSITY_FWHM),
                format_reflection_data_mode(REFLECTION_DATA_MODE_AMPLITUDE_FWHM),
            ],
            format_reflection_data_mode(REFLECTION_DATA_MODE_SET_FROM_INFLIP),
        )
        try:
            self.inputs["reflection_data_mode"].currentTextChanged.connect(self._sync_map_feedback_widgets)  # type: ignore[attr-defined]
        except Exception:
            pass
        # jana_inflip already gets a dedicated on_change handler
        # (_jana_inflip_path_changed, assigned further below) which also
        # refreshes map-feedback gating; hkl has no such handler of its own,
        # so give it one here rather than silently overwriting whichever of
        # the two assignments runs last.
        hkl_row = self.inputs.get("hkl")
        if hasattr(hkl_row, "on_change"):
            hkl_row.on_change = self._hkl_path_changed
        hkl_button_row = QHBoxLayout()
        self.test_hkl_btn = QPushButton("Validate HKL")
        self.analyze_hkl_btn = QPushButton("Analyze completeness")
        self.test_hkl_btn.setToolTip("Parse the selected HKL or Jana2020 .inflip reflection block and show which h, k, l, value, sigma and phase fields were read.")
        self.analyze_hkl_btn.setToolTip("Open completeness and data-statistics plots for the selected HKL data.")
        self.test_hkl_btn.clicked.connect(self.test_hkl_load_dialog)
        self.analyze_hkl_btn.clicked.connect(self.open_hkl_completeness_dialog)
        hkl_button_row.addWidget(self.test_hkl_btn)
        hkl_button_row.addWidget(self.analyze_hkl_btn)
        data_input_form.addRow("", hkl_button_row)

        metadata_form = self._add_form_group(input_tab, "Crystal metadata")
        self._add_combo(
            metadata_form,
            "metadata_source",
            "Metadata source",
            [
                METADATA_SOURCE_LABELS[METADATA_SOURCE_INFLIP],
                METADATA_SOURCE_LABELS[METADATA_SOURCE_REFERENCE],
                METADATA_SOURCE_LABELS[METADATA_SOURCE_MANUAL],
            ],
            METADATA_SOURCE_LABELS[METADATA_SOURCE_INFLIP],
        )
        self.inputs["metadata_source"].currentTextChanged.connect(self._sync_metadata_source_widgets)  # type: ignore[attr-defined]
        self.inputs["metadata_source"].activated.connect(self._metadata_source_activated)  # type: ignore[attr-defined]

        self.metadata_summary_panel = QWidget()
        self.metadata_summary_panel.setObjectName("metadataSummaryPanel")
        metadata_summary_layout = self._configure_form(QFormLayout(self.metadata_summary_panel))
        self.metadata_cell_summary = QLabel("No metadata loaded.")
        self.metadata_cell_summary.setWordWrap(True)
        self.metadata_cell_angles_summary = QLabel("")
        self.metadata_cell_angles_summary.setWordWrap(True)
        self.metadata_spacegroup_summary = QLabel("")
        self.metadata_spacegroup_summary.setWordWrap(True)
        self.metadata_composition_summary = QLabel("")
        self.metadata_composition_summary.setWordWrap(True)
        metadata_summary_layout.addRow("Cell lengths", self.metadata_cell_summary)
        metadata_summary_layout.addRow("Cell angles", self.metadata_cell_angles_summary)
        metadata_summary_layout.addRow("Space group", self.metadata_spacegroup_summary)
        metadata_summary_layout.addRow("Composition", self.metadata_composition_summary)
        metadata_form.addRow("", self.metadata_summary_panel)

        self.manual_metadata_panel = QWidget()
        self.manual_metadata_panel.setObjectName("manualMetadataPanel")
        manual_layout = QGridLayout(self.manual_metadata_panel)
        manual_layout.setContentsMargins(0, 0, 0, 0)
        manual_layout.setHorizontalSpacing(8)
        manual_layout.setVerticalSpacing(CONFIG_FORM_VERTICAL_SPACING)

        unit_cell_heading = QLabel("Unit cell")
        unit_cell_heading.setObjectName("inlineGroupTitle")
        manual_layout.addWidget(unit_cell_heading, 0, 0, 1, 6)

        def add_manual_cell_control(key: str, row: int, column: int, label_text: str, unit: str) -> None:
            label = QLabel(label_text)
            control = QDoubleSpinBox()
            control.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            control.setFixedHeight(CONFIG_CONTROL_VISIBLE_HEIGHT)
            control.setRange(0.0, 10000.0 if "cell_" in key and not key.endswith(("alpha", "beta", "gamma")) else 179.99999)
            control.setDecimals(5)
            control.setSingleStep(0.1)
            control.setSpecialValueText("Not set")
            control.setValue(0.0)
            manual_layout.addWidget(label, row, column)
            manual_layout.addWidget(control, row, column + 1)
            manual_layout.addWidget(QLabel(unit), row, column + 2)
            self.inputs[key] = control
            self.input_labels[key] = label
            self._apply_input_tooltip(key, control)
            if control.toolTip():
                label.setToolTip(control.toolTip())
            control.valueChanged.connect(self._manual_metadata_value_changed)

        for row, (length_key, length_label, angle_key, angle_label) in enumerate(
            (
                ("manual_cell_a", "a", "manual_cell_alpha", "alpha"),
                ("manual_cell_b", "b", "manual_cell_beta", "beta"),
                ("manual_cell_c", "c", "manual_cell_gamma", "gamma"),
            ),
            start=1,
        ):
            add_manual_cell_control(length_key, row, 0, length_label, "Å")
            add_manual_cell_control(angle_key, row, 3, angle_label, "°")

        symmetry_heading = QLabel("Symmetry")
        symmetry_heading.setObjectName("inlineGroupTitle")
        manual_layout.addWidget(symmetry_heading, 4, 0, 1, 6)
        number_label = QLabel("Number")
        number_control = QSpinBox()
        number_control.setRange(0, 230)
        number_control.setSpecialValueText("Not set")
        number_control.setFixedHeight(CONFIG_CONTROL_VISIBLE_HEIGHT)
        symbol_label = QLabel("Symbol")
        symbol_control = QLineEdit()
        symbol_control.setFixedHeight(CONFIG_CONTROL_VISIBLE_HEIGHT)
        manual_layout.addWidget(number_label, 5, 0)
        manual_layout.addWidget(number_control, 5, 1, 1, 2)
        manual_layout.addWidget(symbol_label, 5, 3)
        manual_layout.addWidget(symbol_control, 5, 4, 1, 2)
        self.inputs["manual_spacegroup_number"] = number_control
        self.inputs["manual_spacegroup_symbol"] = symbol_control
        self.input_labels["manual_spacegroup_number"] = number_label
        self.input_labels["manual_spacegroup_symbol"] = symbol_label
        self._apply_input_tooltip("manual_spacegroup_number", number_control)
        self._apply_input_tooltip("manual_spacegroup_symbol", symbol_control)
        number_control.valueChanged.connect(self._manual_spacegroup_number_changed)
        symbol_control.editingFinished.connect(self._manual_spacegroup_symbol_changed)

        composition_heading = QLabel("Composition")
        composition_heading.setObjectName("inlineGroupTitle")
        composition_control = QLineEdit()
        composition_control.setFixedHeight(CONFIG_CONTROL_VISIBLE_HEIGHT)
        composition_control.setPlaceholderText("Ag196 S108 O40 B1000")
        manual_layout.addWidget(composition_heading, 6, 0, 1, 6)
        manual_layout.addWidget(composition_control, 7, 0, 1, 6)
        self.inputs["manual_composition"] = composition_control
        self.input_labels["manual_composition"] = composition_heading
        self._apply_input_tooltip("manual_composition", composition_control)
        composition_control.editingFinished.connect(self._manual_metadata_value_changed)

        self.manual_metadata_status = QLabel("")
        self.manual_metadata_status.setObjectName("secondaryHelp")
        self.manual_metadata_status.setWordWrap(True)
        manual_layout.addWidget(self.manual_metadata_status, 8, 0, 1, 6)
        metadata_form.addRow("", self.manual_metadata_panel)

        self.metadata_error_panel = QWidget()
        self.metadata_error_panel.setObjectName("metadataErrorPanel")
        metadata_error_layout = QHBoxLayout(self.metadata_error_panel)
        metadata_error_layout.setContentsMargins(9, 7, 7, 7)
        metadata_error_layout.setSpacing(8)
        self.metadata_error_text = QLabel("")
        self.metadata_error_text.setObjectName("metadataErrorText")
        self.metadata_error_text.setWordWrap(True)
        self.metadata_error_details_btn = QToolButton()
        self.metadata_error_details_btn.setObjectName("metadataErrorDetails")
        self.metadata_error_details_btn.setText("Details")
        self.metadata_error_details_btn.clicked.connect(self._show_metadata_error_details)
        metadata_error_layout.addWidget(self.metadata_error_text, 1)
        metadata_error_layout.addWidget(self.metadata_error_details_btn, 0, Qt.AlignTop)
        self.metadata_error_panel.setVisible(False)
        metadata_form.addRow("", self.metadata_error_panel)

        reference_form = self._add_form_group(input_tab, "Reference and initial model")
        self._add_path(reference_form, "reference_cif", "Reference structure", "", "file", "Reference files (*.cif *.ins *.res *.m80 *.m81 *.jana *.xplor *.ccp4 *.map);;CIF structures (*.cif *.ins *.res);;Jana density maps (*.m80 *.m81 *.jana);;XPLOR maps (*.xplor);;CCP4 maps (*.ccp4 *.map);;All files (*)")
        self.inputs["jana_inflip"].on_change = self._jana_inflip_path_changed  # type: ignore[attr-defined]
        self.inputs["reference_cif"].on_change = self._reference_path_changed  # type: ignore[attr-defined]
        self._add_path(reference_form, "first_cycle_modelfile", "Initial model (cycle 1)", "", "file", "Model/map files (*.xplor *.ccp4 *.cif);;All files (*)")
        input_tab.addSpacing(CONFIG_MAJOR_SECTION_SPACING)
        input_tab.addStretch(1)

    def _build_workflow_tab(self) -> None:
        workflow_tab = self._add_settings_tab("Workflow")
        workflow_form = self._add_form_group(workflow_tab, "Reconstruction", "setup")
        self._workflow_form = workflow_form
        self._add_combo(workflow_form, "workflow_preset", "Workflow preset", ["Recommended", "Custom", "MOF atomic resolution", "MOF medium resolution", "small molecule", "inorganic"], "Recommended")
        try:
            self.inputs["workflow_preset"].currentTextChanged.connect(self._apply_workflow_preset)  # type: ignore[attr-defined]
        except Exception:
            pass
        self._add_spin(workflow_form, "cycles", "Cycles", 5, 1, 999, 1)
        self.inputs["cycles"].valueChanged.connect(self._update_plot)  # type: ignore[attr-defined]
        self.inputs["cycles"].valueChanged.connect(self._sync_map_feedback_widgets)  # type: ignore[attr-defined]
        self.inputs["cycles"].valueChanged.connect(self._sync_workflow_widgets)  # type: ignore[attr-defined]
        self._add_combo(workflow_form, "reconstruction_mode", "Phasing method", ["Superflip", "1st Superflip, then SharpED (beta)", "SharpED (experimental)"], "Superflip")
        try:
            self.inputs["reconstruction_mode"].currentTextChanged.connect(self._sync_workflow_widgets)  # type: ignore[attr-defined]
        except Exception:
            pass
        self.reconstruction_mode_warning = self._settings_callout("", "")
        self.reconstruction_mode_warning.setVisible(False)
        workflow_form.addRow("", self.reconstruction_mode_warning)
        self.single_cycle_note = self._settings_callout("Single-cycle run", "Next-cycle settings are inactive.")
        self.single_cycle_note.setVisible(False)
        workflow_form.addRow("", self.single_cycle_note)
        self._add_combo_with_values(
            workflow_form,
            "modelfile_source",
            "Next-cycle model",
            [
                ("superflip_xplor", f"{result_map_label('superflip')} (XPLOR)"),
                ("deblurred_xplor", f"{result_map_label('deblurred')} (XPLOR)"),
                ("deblurred_edma_cif", f"{result_structure_label('deblurred')} (EDMA CIF)"),
                ("none", "None"),
            ],
            "deblurred_xplor",
        )
        try:
            self.inputs["modelfile_source"].currentTextChanged.connect(self._sync_workflow_widgets)  # type: ignore[attr-defined]
        except Exception:
            pass
        self._add_dspin(workflow_form, "damping_factor", "XPLOR damping (1/x)", 0.3, 0.001, 1.0, 0.05, 3)
        self._add_text(workflow_form, "exclude_atoms", "Excluded atoms", "none")
        workflow_note = self._settings_callout(
            "Note",
            "Next-cycle model controls how subsequent reconstruction cycles are initialized. Selecting None "
            "limits the workflow to a single cycle. XPLOR damping applies only to XPLOR-based recycling. "
            "Method-specific recycling settings take precedence when Phasing method is not Superflip."
        )
        workflow_form.addRow("", workflow_note)
        self.recycle_note = self._settings_callout(
            "Phasing method",
            "Superflip is the standard iterative charge-flipping cycle (unchanged). "
            "1st Superflip, then SharpED (beta) runs Superflip only once, then each cycle deblurs the previous map with "
            "SharpED, calculates phi_calc by FFT from that SharpED map for every measured hkl, and recomposes a map "
            "from |Fobs| + phi_calc for the next cycle's SharpED input. "
            "SharpED (experimental) skips Superflip entirely: cycle 1 starts from |Fobs| with independent random phases instead."
        )
        workflow_form.addRow("", self.recycle_note)

        model_form = self._add_form_group(workflow_tab, "SharpED model", "sharped")
        self._add_combo(model_form, "sharped_model", "Model", ["koala 2.0"], "koala 2.0")
        try:
            self.inputs["sharped_model"].lineEdit().setReadOnly(False)  # type: ignore[attr-defined]
            self.inputs["sharped_model"].lineEdit().setCursor(Qt.CursorShape.IBeamCursor)  # type: ignore[attr-defined]
        except Exception:
            pass
        self.refresh_models_btn = QPushButton("Refresh models")
        self.refresh_models_btn.setToolTip("Fetch the current list of SharpED server models and update the model selector.")
        self.refresh_models_btn.clicked.connect(self.refresh_sharped_models)
        model_form.addRow("", self.refresh_models_btn)
        model_form.addRow("", self._secondary_help(
            "Connection: Advanced → Setup\nInference and transfer: Advanced → SharpED"
        ))

        optional_form = self._add_form_group(workflow_tab, "Optional processing")
        self._optional_form = optional_form
        superflip_stages_label = QLabel("Superflip cycle")
        superflip_stages_label.setObjectName("inlineGroupTitle")
        optional_form.addRow(superflip_stages_label)
        self._add_checkbox(optional_form, "run_edma_superflip", "Run EDMA on Superflip map", True, align_with_fields=True)
        self._add_checkbox(optional_form, "run_sharped", "Run SharpED", True, align_with_fields=True)
        self._add_checkbox(optional_form, "symmetrize_deblurred_map", "Symmetrize SharpED map with Superflip (beta)", False, align_with_fields=True)
        self._add_checkbox(optional_form, "run_edma_deblurred", "Run EDMA on SharpED map", True, align_with_fields=True)
        self._add_checkbox(optional_form, "compute_omit_maps", "Compute OMIT validation maps (5% holdout)", False, align_with_fields=True)
        self._add_checkbox(optional_form, "compute_omit_rfree", "Calculate R_free on the 5% holdout", False, align_with_fields=True)
        try:
            self.inputs["compute_omit_maps"].toggled.connect(self._sync_workflow_widgets)  # type: ignore[attr-defined]
        except Exception:
            pass
        self.recycle_stages_label = QLabel("Phase-recycling methods")
        self.recycle_stages_label.setObjectName("inlineGroupTitle")
        optional_form.addRow(self.recycle_stages_label)
        self._add_checkbox(optional_form, "run_edma_recycle_final", "Run EDMA on final map", False, align_with_fields=True)
        workflow_tab.addSpacing(CONFIG_MAJOR_SECTION_SPACING)
        workflow_tab.addStretch(1)

    def _build_output_tab(self) -> None:
        # A fresh Path.cwd() here (rather than a value threaded in from
        # _build_ui) is equivalent: it is only ever read once, during
        # construction, to seed the default working-directory text.
        cwd = Path.cwd()
        output_tab = self._add_settings_tab("Output")
        output_form = self._add_form_group(output_tab, "Output")
        self._add_path(output_form, "work_dir", "Working directory", str(cwd / "iterative_superflip_qt_run"), "dir")
        self._add_combo(output_form, "map_export_format", "Map format", ["xplor", "ccp4", "jana", "HKL reflections with phases", "ShelX (fcf)"], "xplor")
        self._add_combo(output_form, "structure_export_format", "Structure format", ["cif", "xyz", "pdb"], "cif")
        output_form.addRow("", self._secondary_help(
            "Internal processing: XPLOR and CIF are always kept internally for EDMA, SharpED and next-cycle "
            "modelfiles, regardless of the formats selected below."
        ))
        output_form.addRow("", self._secondary_help(
            "Export behavior: ccp4/jana additionally save one extra density map for external use or Jana2020, "
            "while HKL reflections with phases and ShelX (fcf) instead save, for each cycle's Superflip map, the "
            "observed reflections together with phases read by FFT from that map, in place of an extra density map."
        ))
        output_tab.addSpacing(CONFIG_MAJOR_SECTION_SPACING)
        output_tab.addStretch(1)

    def _build_map_feedback_tab(self) -> None:
        feedback_tab = self._add_settings_tab("Map feedback")
        # Every other page's first section is a QGroupBox, which carries its
        # own ~1.25em top margin from the shared QGroupBox QSS -- this page's
        # Warning callout has no such margin of its own, so without an
        # explicit spacer here it sits noticeably closer to the sub-tab row
        # than any other page's first section does.
        feedback_tab.addSpacing(CONFIG_MAJOR_SECTION_SPACING)
        feedback_tab.addWidget(self._settings_callout(
            "Warning",
            "The operations on this page modify the reflection data supplied to subsequent cycles. "
            "Results from these cycles should therefore be validated against the original measured data.",
        ))
        missing_feedback_form = self._add_form_group(feedback_tab, "Missing-reflection completion", "map_feedback")
        self._add_checkbox(missing_feedback_form, "map_feedback_missing_enabled", "Enable missing-reflection completion", False, align_with_fields=True)
        self._add_spin(missing_feedback_form, "map_feedback_missing_from_cycle", "Start after cycle", 1, 1, 999, 1)
        self._add_dspin(missing_feedback_form, "map_feedback_missing_percent_limit", "Maximum added reflections (%)", 0.0, 0.0, 100.0, 1.0, 3)

        intensity_feedback_form = self._add_form_group(feedback_tab, "Intensity correction")
        self._add_checkbox(intensity_feedback_form, "map_feedback_intensity_enabled", "Enable intensity correction", False, align_with_fields=True)
        self._add_spin(intensity_feedback_form, "map_feedback_intensity_from_cycle", "Start after cycle", 1, 1, 999, 1)
        self._add_dspin(intensity_feedback_form, "map_feedback_intensity_damping", "Correction damping", 0.0, 0.0, 1.0, 0.05, 3)
        self._add_dspin(intensity_feedback_form, "map_feedback_intensity_max_i_over_sigma", "Apply when value/σ <", 0.0, 0.0, 1000.0, 0.5, 3)
        intensity_feedback_form.addRow("", self._settings_callout("Note", "Value/σ = 0 applies correction to all non-zero reflections."))

        powder_feedback_form = self._add_form_group(feedback_tab, "Powder overlap repartitioning")
        self._add_checkbox(powder_feedback_form, "redistribute_overlaps", "Enable powder overlap repartitioning (FWHM data)", False, align_with_fields=True)
        self._add_spin(powder_feedback_form, "powder_redistribution_from_cycle", "Start after cycle", 1, 1, 999, 1)
        self._add_dspin(powder_feedback_form, "powder_wavelength", "Wavelength (Å)", 0.0, 0.0, 10.0, 0.01, 5)
        self._add_dspin(powder_feedback_form, "powder_separation_factor", "Separation factor", 0.2, 0.001, 100.0, 0.05, 3)
        self._add_dspin(powder_feedback_form, "powder_redistribution_mix", "Map ratio mix", 1.0, 0.0, 1.0, 0.05, 3)
        powder_feedback_form.addRow("", self._settings_callout(
            "Note",
            "Only applies to reflections with an FWHM value (hkl I/F fwhm data). Wavelength is auto-detected -- if "
            "left at 0 -- from the Jana2020 .inflip file (dataformat's lambda/wavelength line), or otherwise from the "
            "reference file's _diffrn_radiation_wavelength; enter it manually if neither is available. Reflections "
            "whose Bragg peaks overlap -- delta(2θ) below Separation factor times the mean of their FWHM -- "
            "have their combined observed intensity redistributed between them using intensities calculated by FFT "
            "from that cycle's processed map, blended by Map ratio mix (0 keeps the observed split, 1 uses the map "
            "split fully); the group total is always conserved.",
        ))
        for key in ("map_feedback_missing_enabled", "map_feedback_intensity_enabled", "redistribute_overlaps"):
            try:
                self.inputs[key].toggled.connect(self._sync_map_feedback_widgets)  # type: ignore[attr-defined]
            except Exception:
                pass
        for key in ("map_feedback_missing_from_cycle", "map_feedback_intensity_from_cycle", "powder_redistribution_from_cycle"):
            try:
                self.inputs[key].valueChanged.connect(self._sync_map_feedback_widgets)  # type: ignore[attr-defined]
            except Exception:
                pass
        feedback_tab.addSpacing(CONFIG_MAJOR_SECTION_SPACING)
        feedback_tab.addStretch(1)

    # ----- Shared UI-construction helpers used across _build_ui's tab/section
    # builder methods below. Extracted from local closures that used to live
    # inline in _build_ui (2026 maintainability refactor); behavior is
    # unchanged, they are just callable as self._X() from more than one
    # builder method now instead of only within one giant function's scope. -----

    def _add_settings_tab(self, name: str, advanced: bool = False) -> QVBoxLayout:
        scroll = QScrollArea()
        scroll.setObjectName("settingsScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        if advanced:
            scroll.setViewportMargins(0, 2, 0, 0)
        page = QWidget()
        page.setObjectName("settingsPage")
        page.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(
            CONFIG_PAGE_MARGIN_HORIZONTAL,
            CONFIG_PAGE_MARGIN_VERTICAL + (2 if advanced else 0),
            CONFIG_PAGE_MARGIN_HORIZONTAL,
            CONFIG_PAGE_MARGIN_VERTICAL,
        )
        layout.setSpacing(CONFIG_MAJOR_SECTION_SPACING)
        scroll.setWidget(page)
        (self.advanced_tabs if advanced else self.basic_tabs).addTab(scroll, name)
        if name == "Help":
            if advanced:
                self.help_scroll_advanced = scroll
                self.help_page_advanced = page
            else:
                self.help_scroll_basic = scroll
                self.help_page_basic = page
        return layout

    def _add_form_group(self, page_layout: QVBoxLayout, title: str, guide_anchor: Optional[str] = None) -> QFormLayout:
        if guide_anchor:
            box = QGroupBox()
            box.setObjectName("guidedSettingsGroup")
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(*CONFIG_GUIDED_GROUP_MARGINS)
            box_layout.setSpacing(CONFIG_GUIDED_GROUP_SPACING)
            heading_row = QHBoxLayout()
            heading = QLabel(title)
            heading.setObjectName("inlineGroupTitle")
            guide = QToolButton()
            guide.setObjectName("guideLink")
            guide.setText("Open guide")
            guide.setCursor(Qt.PointingHandCursor)
            guide.setToolTip("Open the relevant section in Help (F1).")
            guide.clicked.connect(lambda _checked=False, target=guide_anchor: self._open_help_section(target))
            heading_row.addWidget(heading, 1)
            heading_row.addWidget(guide)
            form_widget = QWidget()
            form = self._configure_form(QFormLayout(form_widget))
            box_layout.addLayout(heading_row)
            box_layout.addWidget(form_widget)
            page_layout.addWidget(box)
            return form
        box = QGroupBox(title)
        box.setObjectName("settingsGroup")
        form = self._configure_form(QFormLayout(box))
        page_layout.addWidget(box)
        return form

    def _settings_callout(self, title: str, text: str) -> QLabel:
        label = QLabel(f"<b>{title}</b><br>{text}")
        label.setObjectName("settingsCallout")
        label.setTextFormat(Qt.RichText)
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        return label

    def _make_result_section(self, title: str) -> Tuple[QWidget, QVBoxLayout]:
        section = QWidget()
        section.setObjectName("resultSection")
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(4, 4, 4, 4)
        section_layout.setSpacing(3)
        label = QLabel(title)
        label.setObjectName("sectionLabel")
        section_layout.addWidget(label)
        return section, section_layout

    def _add_help_section(self, page_layout: QVBoxLayout, anchor: str, title: str, body_html: str, *, advanced: bool = False) -> QVBoxLayout:
        box = QGroupBox(title)
        box.setObjectName("helpSection")
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(10, 12, 10, 8)
        body = QLabel(body_html)
        body.setObjectName("helpSectionBody")
        body.setTextFormat(Qt.RichText)
        body.setWordWrap(True)
        body.setOpenExternalLinks(True)
        body.setTextInteractionFlags(Qt.TextBrowserInteraction)
        body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        box_layout.addWidget(body)
        page_layout.addWidget(box)
        self.help_sections[anchor] = box
        self.help_section_advanced[anchor] = advanced
        return box_layout

    def _add_help_callout(self, section_layout: QVBoxLayout, label: str, text: str) -> None:
        callout = QLabel(f"<b>{label}</b><br>{text}")
        callout.setObjectName("helpCallout")
        callout.setTextFormat(Qt.RichText)
        callout.setWordWrap(True)
        section_layout.addWidget(callout)

    def _add_back_to_contents(self, section_layout: QVBoxLayout, *, advanced: bool = False) -> None:
        row = QHBoxLayout()
        row.addStretch(1)
        link = QToolButton()
        link.setObjectName("helpNavLink")
        link.setText("↑ Contents")
        link.setCursor(Qt.PointingHandCursor)
        scroll_attr = "help_scroll_advanced" if advanced else "help_scroll_basic"
        link.clicked.connect(lambda: getattr(self, scroll_attr).verticalScrollBar().setValue(0))
        row.addWidget(link)
        section_layout.addLayout(row)

    def _metadata_source_value(self) -> str:
        return normalize_metadata_source(
            self._combo_value("metadata_source") if "metadata_source" in self.inputs else ""
        )

    def _set_metadata_source(self, source: str) -> None:
        widget = self.inputs.get("metadata_source")
        if not isinstance(widget, QComboBox):
            return
        label = METADATA_SOURCE_LABELS[normalize_metadata_source(source)]
        index = widget.findText(label)
        if index >= 0 and index != widget.currentIndex():
            widget.setCurrentIndex(index)
        else:
            self._sync_metadata_source_widgets()

    def _default_metadata_source_for_input(self) -> str:
        mode = normalize_input_source_mode(
            self._combo_value("input_source_mode") if "input_source_mode" in self.inputs else ""
        )
        if mode in {INPUT_MODE_INFLIP, INPUT_MODE_INFLIP_OVERRIDES}:
            return METADATA_SOURCE_INFLIP
        reference_text = self._path_value("reference_cif").strip() if "reference_cif" in self.inputs else ""
        if reference_text:
            path = Path(reference_text).expanduser()
            if path.is_file() and path.suffix.lower() in REFERENCE_STRUCTURE_SUFFIXES:
                return METADATA_SOURCE_REFERENCE
        return METADATA_SOURCE_MANUAL

    def _input_mode_user_changed(self, _index: int = -1) -> None:
        self._metadata_source_user_selected = False
        self._set_metadata_source(self._default_metadata_source_for_input())
        self._sync_input_source_mode_widgets()

    def _metadata_source_activated(self, _index: int = -1) -> None:
        self._metadata_source_user_selected = True
        self._sync_metadata_source_widgets()
        self._sync_input_source_mode_widgets()

    def _jana_inflip_path_changed(self) -> None:
        mode = normalize_input_source_mode(self._combo_value("input_source_mode"))
        if mode in {INPUT_MODE_INFLIP, INPUT_MODE_INFLIP_OVERRIDES} and not self._metadata_source_user_selected:
            self._metadata_source_user_selected = False
            self._set_metadata_source(METADATA_SOURCE_INFLIP)
        self._sync_metadata_source_widgets()
        # A different .inflip file can declare a different embedded dataformat
        # (e.g. FWHM vs. plain intensity), which gates powder overlap
        # repartitioning -- refresh that alongside the metadata sync above.
        self._sync_map_feedback_widgets()
        self.save_settings()

    def _hkl_path_changed(self) -> None:
        # Mirrors _jana_inflip_path_changed()'s map-feedback refresh: an
        # external HKL file's detected format also gates powder overlap
        # repartitioning (FWHM-carrying data only).
        self._sync_map_feedback_widgets()
        self.save_settings()

    def _reference_path_changed(self) -> None:
        reference_text = self._path_value("reference_cif").strip()
        reference_path = Path(reference_text).expanduser() if reference_text else None
        mode = normalize_input_source_mode(self._combo_value("input_source_mode"))
        if (
            not self._metadata_source_user_selected
            and mode == INPUT_MODE_EXTERNAL
            and reference_path is not None
            and reference_path.is_file()
            and reference_path.suffix.lower() in REFERENCE_STRUCTURE_SUFFIXES
        ):
            self._metadata_source_user_selected = False
            self._set_metadata_source(METADATA_SOURCE_REFERENCE)
        self._sync_metadata_source_widgets()
        self.save_settings()

    def _manual_spacegroup_number_changed(self, number: int) -> None:
        if self._syncing_metadata_controls:
            return
        self._syncing_metadata_controls = True
        try:
            symbol_widget = self.inputs.get("manual_spacegroup_symbol")
            if isinstance(symbol_widget, QLineEdit):
                spacegroup = get_spacegroup_from_number(str(number)) if number else None
                symbol_widget.setText(compact_spacegroup_symbol(spacegroup) if spacegroup is not None else "")
                symbol_widget.setProperty("metadataInvalid", False)
                symbol_widget.style().unpolish(symbol_widget)
                symbol_widget.style().polish(symbol_widget)
        finally:
            self._syncing_metadata_controls = False
        self._manual_metadata_value_changed()

    def _manual_spacegroup_symbol_changed(self) -> None:
        if self._syncing_metadata_controls:
            return
        symbol_widget = self.inputs.get("manual_spacegroup_symbol")
        number_widget = self.inputs.get("manual_spacegroup_number")
        if not isinstance(symbol_widget, QLineEdit) or not isinstance(number_widget, QSpinBox):
            return
        spacegroup = resolve_spacegroup_symbol(symbol_widget.text())
        invalid = spacegroup is None
        symbol_widget.setProperty("metadataInvalid", invalid)
        symbol_widget.style().unpolish(symbol_widget)
        symbol_widget.style().polish(symbol_widget)
        if spacegroup is not None:
            self._syncing_metadata_controls = True
            try:
                number_widget.setValue(int(spacegroup.number))
                symbol_widget.setText(compact_spacegroup_symbol(spacegroup))
            finally:
                self._syncing_metadata_controls = False
        self._manual_metadata_value_changed()

    def _manual_metadata_values(self) -> Tuple[List[float], int, str, str]:
        cell = [
            self._dspin_value(key)
            for key in (
                "manual_cell_a",
                "manual_cell_b",
                "manual_cell_c",
                "manual_cell_alpha",
                "manual_cell_beta",
                "manual_cell_gamma",
            )
        ]
        return (
            cell,
            self._spin_value("manual_spacegroup_number"),
            self._line_value("manual_spacegroup_symbol"),
            self._line_value("manual_composition"),
        )

    def _resolve_crystal_metadata_from_inputs(self) -> CrystalMetadata:
        jana_text = self._path_value("jana_inflip").strip() if "jana_inflip" in self.inputs else ""
        reference_text = self._path_value("reference_cif").strip() if "reference_cif" in self.inputs else ""
        manual_cell, manual_number, manual_symbol, manual_composition = self._manual_metadata_values()
        return resolve_crystal_metadata(
            self._metadata_source_value(),
            jana_inflip=Path(jana_text).expanduser().resolve() if jana_text else None,
            reference_file=Path(reference_text).expanduser().resolve() if reference_text else None,
            manual_cell=manual_cell,
            manual_spacegroup_number=manual_number,
            manual_spacegroup_symbol=manual_symbol,
            manual_composition=manual_composition,
        )

    @staticmethod
    def _metadata_summary_values(metadata: CrystalMetadata) -> Tuple[str, str, str, str]:
        cell = metadata.cell
        # Lengths and angles are split into their own rows (rather than one long
        # line) so the summary does not wrap awkwardly at typical panel widths.
        lengths_text = f"{cell.a:.5f} × {cell.b:.5f} × {cell.c:.5f} Å"
        angles_text = f"α {cell.alpha:.3f}° × β {cell.beta:.3f}° × γ {cell.gamma:.3f}°"
        group_text = f"{compact_spacegroup_symbol(metadata.spacegroup)} (#{metadata.spacegroup.number})"
        return lengths_text, angles_text, group_text, metadata.composition

    def _manual_metadata_value_changed(self, *_args) -> None:
        if self._syncing_metadata_controls or self._metadata_source_value() != METADATA_SOURCE_MANUAL:
            return
        try:
            metadata = self._resolve_crystal_metadata_from_inputs()
            self.manual_metadata_status.setText(
                f"Valid · {compact_spacegroup_symbol(metadata.spacegroup)} (#{metadata.spacegroup.number})"
            )
            self._clear_metadata_error()
        except Exception as exc:
            self.manual_metadata_status.setText("")
            self._set_metadata_error(exc)

    def _set_metadata_error(self, error: object) -> None:
        # Run stays clickable even with invalid metadata: start_run()'s own
        # get_config() call raises the same underlying error, reported
        # through the normal error dialog on click -- instead of a silently
        # inert button that gives the user no indication of what to fix.
        report = build_error_report(error, subsystem="Crystal metadata", operation="Resolve crystal metadata")
        self._metadata_valid = False
        self._metadata_error_report = report
        if hasattr(self, "metadata_error_text"):
            self.metadata_error_text.setText(f"{report.title}\n{report.guidance}")
            self.metadata_error_panel.setVisible(True)

    def _clear_metadata_error(self) -> None:
        self._metadata_valid = True
        self._metadata_error_report = None
        if hasattr(self, "metadata_error_panel"):
            self.metadata_error_panel.setVisible(False)

    def _show_metadata_error_details(self) -> None:
        report = self._metadata_error_report
        if report is not None:
            self._show_error_report(report)

    def _sync_metadata_source_widgets(self, *_args) -> None:
        if not hasattr(self, "manual_metadata_panel"):
            return
        source = self._metadata_source_value()
        manual = source == METADATA_SOURCE_MANUAL
        self.manual_metadata_panel.setVisible(manual)
        self.metadata_summary_panel.setVisible(not manual)
        if manual:
            self._manual_metadata_value_changed()
            return
        try:
            metadata = self._resolve_crystal_metadata_from_inputs()
            lengths_text, angles_text, group_text, composition = self._metadata_summary_values(metadata)
            self.metadata_cell_summary.setText(lengths_text)
            self.metadata_cell_angles_summary.setText(angles_text)
            self.metadata_spacegroup_summary.setText(group_text)
            self.metadata_composition_summary.setText(composition)
            self.metadata_summary_panel.setVisible(True)
            self._clear_metadata_error()
        except Exception as exc:
            self.metadata_cell_summary.setText("")
            self.metadata_cell_angles_summary.setText("")
            self.metadata_spacegroup_summary.setText("")
            self.metadata_composition_summary.setText("")
            self.metadata_summary_panel.setVisible(False)
            self._set_metadata_error(exc)

    def _apply_beta_feature_visibility(self) -> None:
        """Beta/experimental Phasing method options are hidden entirely (not just
        disabled) unless 'Show beta and experimental features' is checked on
        Advanced -> Setup, per the user's request that they not appear at all by default."""
        show_beta = self._check_value("show_beta_features") if "show_beta_features" in self.inputs else False
        combo = self.inputs.get("reconstruction_mode")
        if isinstance(combo, QComboBox):
            full_items = ["Superflip", "1st Superflip, then SharpED (beta)", "SharpED (experimental)"]
            allowed = full_items if show_beta else full_items[:1]
            existing = [combo.itemText(i) for i in range(combo.count())]
            if existing != allowed:
                current = combo.currentText()
                combo.blockSignals(True)
                combo.clear()
                combo.addItems(allowed)
                combo.setCurrentText(current if current in allowed else "Superflip")
                combo.blockSignals(False)
        symmetrize_widget = self.inputs.get("symmetrize_deblurred_map")
        if isinstance(symmetrize_widget, QCheckBox):
            if hasattr(self, "_optional_form"):
                try:
                    self._optional_form.setRowVisible(symmetrize_widget, show_beta)
                except Exception:
                    symmetrize_widget.setVisible(show_beta)
            else:
                symmetrize_widget.setVisible(show_beta)
            if not show_beta and symmetrize_widget.isChecked():
                symmetrize_widget.setChecked(False)
        # The "Phasing method" note only has something to explain once another
        # method besides Superflip can actually be picked; and the
        # "Phase-recycling methods" group (Run EDMA on final map) only applies
        # to those same beta/experimental methods -- hide both, not just
        # disable them, right alongside the combo items themselves.
        recycle_note_widget = getattr(self, "recycle_note", None)
        if recycle_note_widget is not None:
            recycle_note_widget.setVisible(show_beta)
            if hasattr(self, "_workflow_form"):
                try:
                    self._workflow_form.setRowVisible(recycle_note_widget, show_beta)
                except Exception:
                    pass
        recycle_stages_label_widget = getattr(self, "recycle_stages_label", None)
        if recycle_stages_label_widget is not None:
            recycle_stages_label_widget.setVisible(show_beta)
            if hasattr(self, "_optional_form"):
                try:
                    self._optional_form.setRowVisible(recycle_stages_label_widget, show_beta)
                except Exception:
                    pass
        recycle_final_widget = self.inputs.get("run_edma_recycle_final")
        if isinstance(recycle_final_widget, QCheckBox):
            if hasattr(self, "_optional_form"):
                try:
                    self._optional_form.setRowVisible(recycle_final_widget, show_beta)
                except Exception:
                    recycle_final_widget.setVisible(show_beta)
            else:
                recycle_final_widget.setVisible(show_beta)
            if not show_beta and recycle_final_widget.isChecked():
                recycle_final_widget.setChecked(False)

    def _sync_normalization_widgets(self, *_args) -> None:
        # nresshells (Resolution shells) is only meaningful for "local" normalization.
        mode = str(self._combo_value("normalize") if "normalize" in self.inputs else "").strip().lower()
        is_local = mode == "local"
        widget = self.inputs.get("nresshells")
        if hasattr(widget, "setEnabled"):
            widget.setEnabled(is_local)  # type: ignore[attr-defined]
        if hasattr(widget, "setToolTip"):
            widget.setToolTip(  # type: ignore[attr-defined]
                INPUT_TOOLTIPS.get("nresshells", "") if is_local
                else "Ignored: Resolution shells is used only when Normalization is 'local'."
            )
        label = self.input_labels.get("nresshells")
        if label is not None:
            label.setEnabled(is_local)

    def _sync_workflow_widgets(self) -> None:
        if self._configuration_locked:
            return
        self._apply_beta_feature_visibility()
        reconstruction_mode = normalize_reconstruction_mode(self._combo_value("reconstruction_mode") if "reconstruction_mode" in self.inputs else "")
        is_recycling = reconstruction_mode != "superflip"
        for key, tooltip_when_disabled in (
            ("modelfile_source", "Ignored: the selected Phasing method defines its own next-cycle map instead of Next-cycle model."),
            ("damping_factor", "Ignored: XPLOR damping applies only to the Superflip phasing method's next-cycle model."),
            ("symmetrize_deblurred_map", "Ignored: symmetry averaging is not part of the selected Phasing method."),
            ("run_edma_superflip", "Ignored: EDMA after the Superflip map is not part of the selected Phasing method."),
            ("run_sharped", "Ignored: the selected Phasing method always deblurs with SharpED every cycle."),
            ("run_edma_deblurred", "Ignored: EDMA after the SharpED map is not part of the selected Phasing method; use Run EDMA on final map instead."),
            ("compute_omit_maps", "Ignored: omit maps are only computed for the standard Superflip cycle."),
        ):
            widget = self.inputs.get(key)
            if hasattr(widget, "setEnabled"):
                widget.setEnabled(not is_recycling)  # type: ignore[attr-defined]
            label = self.input_labels.get(key)
            if label is not None:
                label.setEnabled(not is_recycling)
            if hasattr(widget, "setToolTip"):
                widget.setToolTip(tooltip_when_disabled if is_recycling else INPUT_TOOLTIPS.get(key, ""))  # type: ignore[attr-defined]
        omit_rfree_widget = self.inputs.get("compute_omit_rfree")
        omit_maps_enabled = not is_recycling and self._check_value("compute_omit_maps")
        if isinstance(omit_rfree_widget, QCheckBox):
            omit_rfree_widget.setEnabled(omit_maps_enabled)
            omit_rfree_widget.setToolTip(
                INPUT_TOOLTIPS.get("compute_omit_rfree", "") if omit_maps_enabled
                else "Ignored: requires 'Compute omit maps' to be enabled."
            )
            if not omit_maps_enabled and omit_rfree_widget.isChecked():
                omit_rfree_widget.setChecked(False)
        recycle_final_widget = self.inputs.get("run_edma_recycle_final")
        if hasattr(recycle_final_widget, "setEnabled"):
            recycle_final_widget.setEnabled(is_recycling)  # type: ignore[attr-defined]
        if hasattr(recycle_final_widget, "setToolTip"):
            recycle_final_widget.setToolTip(  # type: ignore[attr-defined]
                INPUT_TOOLTIPS.get("run_edma_recycle_final", "") if is_recycling
                else "Ignored: only used by the '1st Superflip, then SharpED' and 'SharpED' phasing methods."
            )
        recycle_final_label = self.input_labels.get("run_edma_recycle_final")
        if recycle_final_label is not None:
            recycle_final_label.setEnabled(is_recycling)
        warning_widget = getattr(self, "reconstruction_mode_warning", None)
        if warning_widget is not None:
            if reconstruction_mode == "sharped_recycle":
                warning_widget.setText(
                    "<b>Beta feature</b><br>1st Superflip, then SharpED does not work well with some models."
                )
                show_warning = True
            elif reconstruction_mode == "sharped_recycle_random":
                warning_widget.setText(
                    "<b>Experimental feature</b><br>SharpED (random-phase start) does not work well yet and is "
                    "intended for development, not production use. It can take extremely long to converge, even "
                    "for simple structures (hundreds of cycles), and convergence is not guaranteed."
                )
                show_warning = True
            else:
                show_warning = False
            warning_widget.setVisible(show_warning)
            if hasattr(self, "_workflow_form"):
                try:
                    self._workflow_form.setRowVisible(warning_widget, show_warning)
                except Exception:
                    pass
        if is_recycling:
            note_widget = getattr(self, "single_cycle_note", None)
            if note_widget is not None:
                note_widget.setVisible(False)
                if hasattr(self, "_workflow_form"):
                    try:
                        self._workflow_form.setRowVisible(note_widget, False)
                    except Exception:
                        pass
            self._update_plot()
            return
        mode = normalize_modelfile_source(self._combo_value("modelfile_source") if "modelfile_source" in self.inputs else "")
        cycles_widget = self.inputs.get("cycles")
        damping_widget = self.inputs.get("damping_factor")
        symmetrize_widget = self.inputs.get("symmetrize_deblurred_map")
        if isinstance(cycles_widget, QSpinBox):
            if mode == "none":
                if cycles_widget.value() != 1:
                    cycles_widget.setValue(1)
                cycles_widget.setEnabled(False)
                cycles_widget.setToolTip("Next-cycle model is none, so there is no feedback model for later cycles. The run is therefore forced to one cycle.")
            else:
                cycles_widget.setEnabled(True)
                cycles_widget.setToolTip(INPUT_TOOLTIPS.get("cycles", ""))
            cycles_label = self.input_labels.get("cycles")
            if cycles_label is not None:
                cycles_label.setEnabled(mode != "none")
        single_cycle = mode != "none" and max(1, self._spin_value("cycles") if "cycles" in self.inputs else 1) <= 1
        single_cycle_tooltip = "Used only when more than one reconstruction cycle is requested."
        note_widget = getattr(self, "single_cycle_note", None)
        if note_widget is not None:
            note_widget.setVisible(single_cycle)
            if hasattr(self, "_workflow_form"):
                try:
                    self._workflow_form.setRowVisible(note_widget, single_cycle)
                except Exception:
                    pass
        modelfile_widget = self.inputs.get("modelfile_source")
        # Next-cycle model stays editable even at Cycles=1 when it is itself the
        # reason the run is forced to one cycle (mode == "none"), so the user can
        # always change away from "none" to re-enable multi-cycle runs.
        if hasattr(modelfile_widget, "setEnabled"):
            modelfile_widget.setEnabled(not single_cycle)  # type: ignore[attr-defined]
        modelfile_label = self.input_labels.get("modelfile_source")
        if modelfile_label is not None:
            modelfile_label.setEnabled(not single_cycle)
        if hasattr(modelfile_widget, "setToolTip"):
            modelfile_widget.setToolTip(  # type: ignore[attr-defined]
                single_cycle_tooltip if single_cycle else INPUT_TOOLTIPS.get("modelfile_source", "")
            )
        if isinstance(damping_widget, QDoubleSpinBox):
            damping_mode_ok = mode in {"superflip_xplor", "deblurred_xplor"}
            damping_widget.setEnabled(damping_mode_ok and not single_cycle)
            damping_label = self.input_labels.get("damping_factor")
            if damping_label is not None:
                damping_label.setEnabled(damping_mode_ok and not single_cycle)
            if not damping_mode_ok:
                damping_widget.setToolTip("XPLOR damping is used only when Next-cycle model is superflip_xplor or deblurred_xplor.")
            elif single_cycle:
                damping_widget.setToolTip(single_cycle_tooltip)
            else:
                damping_widget.setToolTip(INPUT_TOOLTIPS.get("damping_factor", ""))
        if isinstance(symmetrize_widget, QCheckBox):
            symmetrize_widget.setEnabled(mode != "superflip_xplor")
            symmetrize_label = self.input_labels.get("symmetrize_deblurred_map")
            if symmetrize_label is not None:
                symmetrize_label.setEnabled(mode != "superflip_xplor")
            if mode == "superflip_xplor":
                symmetrize_widget.setToolTip("Raw Superflip XPLOR cycling skips the deblurred-map branch, so post-deblur symmetry averaging is not used.")
            else:
                symmetrize_widget.setToolTip(INPUT_TOOLTIPS.get("symmetrize_deblurred_map", ""))
        self._update_plot()

    def _sync_map_feedback_widgets(self) -> None:
        if self._configuration_locked:
            return
        groups = (
            ("map_feedback_missing_enabled", "Enable missing-reflection completion",
             "map_feedback_missing_from_cycle", ("map_feedback_missing_percent_limit",)),
            ("map_feedback_intensity_enabled", "Enable intensity correction",
             "map_feedback_intensity_from_cycle", (
                 "map_feedback_intensity_damping", "map_feedback_intensity_max_i_over_sigma",
             )),
            ("redistribute_overlaps", "Enable powder overlap repartitioning",
             "powder_redistribution_from_cycle", (
                 "powder_wavelength", "powder_separation_factor", "powder_redistribution_mix",
             )),
        )
        # "Start after cycle" fields deliberately keep their own full range
        # (1-999) regardless of the current Cycles value: Cycles is often
        # still at its default of 1 while the user is setting these up ahead
        # of increasing it, and clamping the spin box's maximum to the
        # current Cycles value made it un-editable (min==max==1) in exactly
        # that common case. The pipeline itself already tolerates a
        # start-after-cycle beyond the actual run length as a harmless no-op.
        cycles_value = max(1, self._spin_value("cycles")) if "cycles" in self.inputs else 1
        # Powder overlap repartitioning only makes sense for FWHM-carrying
        # reflection data (hkl I fwhm / hkl F fwhm); gate the checkbox itself
        # on that, on top of (not instead of) its own checked state below.
        # A disabled-but-still-checked box reads as "queued but blocked" and
        # is confusing/misleading, so it is force-unchecked (not just grayed)
        # the moment it becomes unavailable -- an unavailable feature must
        # look and behave exactly like "off", never "on but you can't touch
        # it". _validate_run_config() still blocks Run if it is somehow
        # checked against non-FWHM data (e.g. a stale saved setting), as a
        # last-resort safety net, not the primary mechanism.
        redistribute_checkbox = self.inputs.get("redistribute_overlaps")
        if isinstance(redistribute_checkbox, QCheckBox):
            has_fwhm_data = reflection_mode_has_fwhm(self._resolve_configured_data_mode_for_ui())
            if not has_fwhm_data and redistribute_checkbox.isChecked():
                redistribute_checkbox.setChecked(False)
            redistribute_checkbox.setEnabled(has_fwhm_data)
            redistribute_label = self.input_labels.get("redistribute_overlaps")
            if redistribute_label is not None:
                redistribute_label.setEnabled(has_fwhm_data)
            redistribute_checkbox.setToolTip(
                INPUT_TOOLTIPS.get("redistribute_overlaps", "") if has_fwhm_data
                else "Requires FWHM-carrying reflection data (hkl I fwhm / hkl F fwhm); no FWHM format is currently detected for the configured HKL source."
            )
        else:
            has_fwhm_data = True
        for checkbox_key, checkbox_label, from_cycle_key, other_field_keys in groups:
            checkbox = self.inputs.get(checkbox_key)
            checkbox_enabled = bool(checkbox.isChecked()) if isinstance(checkbox, QCheckBox) else True
            if checkbox_key == "redistribute_overlaps":
                checkbox_enabled = checkbox_enabled and has_fwhm_data
            from_cycle_widget = self.inputs.get(from_cycle_key)
            if hasattr(from_cycle_widget, "setEnabled"):
                from_cycle_widget.setEnabled(checkbox_enabled)  # type: ignore[attr-defined]
            from_cycle_label = self.input_labels.get(from_cycle_key)
            if from_cycle_label is not None:
                from_cycle_label.setEnabled(checkbox_enabled)
            if hasattr(from_cycle_widget, "setToolTip"):
                from_cycle_widget.setToolTip(  # type: ignore[attr-defined]
                    INPUT_TOOLTIPS.get(from_cycle_key, "") if checkbox_enabled
                    else f"Ignored: requires '{checkbox_label}' to be enabled."
                )
            # Feedback starting at cycle N is first applied to the reflections
            # used for cycle N+1 -- so the mechanism can only ever act while
            # Cycles allows at least one cycle from that starting point onward.
            from_cycle_value = int(from_cycle_widget.value()) if isinstance(from_cycle_widget, QSpinBox) else 1
            reachable = cycles_value >= from_cycle_value
            fields_active = checkbox_enabled and reachable
            for field_key in other_field_keys:
                widget = self.inputs.get(field_key)
                if hasattr(widget, "setEnabled"):
                    widget.setEnabled(fields_active)  # type: ignore[attr-defined]
                label = self.input_labels.get(field_key)
                if label is not None:
                    label.setEnabled(fields_active)
                if hasattr(widget, "setToolTip"):
                    if not checkbox_enabled:
                        tooltip = f"Ignored: requires '{checkbox_label}' to be enabled."
                    elif not reachable:
                        tooltip = "Requires a subsequent reconstruction cycle."
                    else:
                        tooltip = INPUT_TOOLTIPS.get(field_key, "")
                    widget.setToolTip(tooltip)  # type: ignore[attr-defined]

    def _sync_input_source_mode_widgets(self) -> None:
        if self._configuration_locked:
            return
        mode = normalize_input_source_mode(self._combo_value("input_source_mode") if "input_source_mode" in self.inputs else "")
        jana_enabled = mode in {INPUT_MODE_INFLIP, INPUT_MODE_INFLIP_OVERRIDES} or self._metadata_source_value() == METADATA_SOURCE_INFLIP
        override_enabled = mode == INPUT_MODE_INFLIP_OVERRIDES
        external_enabled = mode == INPUT_MODE_EXTERNAL
        reflection_data_mode_enabled = mode != INPUT_MODE_INFLIP
        for key, enabled in (
            ("jana_inflip", jana_enabled),
            ("hkl", override_enabled or external_enabled),
            ("reference_cif", True),
            ("reflection_data_mode", reflection_data_mode_enabled),
        ):
            widget = self.inputs.get(key)
            if hasattr(widget, "setEnabled"):
                widget.setEnabled(bool(enabled))  # type: ignore[attr-defined]
            label = self.input_labels.get(key)
            if label is not None:
                label.setEnabled(bool(enabled))
        reflection_data_mode_widget = self.inputs.get("reflection_data_mode")
        if hasattr(reflection_data_mode_widget, "setToolTip"):
            reflection_data_mode_widget.setToolTip(  # type: ignore[attr-defined]
                "Ignored: the dataformat keyword is read directly from the Jana2020 .inflip file."
                if not reflection_data_mode_enabled else INPUT_TOOLTIPS.get("reflection_data_mode", "")
            )
        jana_inflip_widget = self.inputs.get("jana_inflip")
        if isinstance(jana_inflip_widget, PathRow):
            jana_inflip_widget.set_tooltip(
                INPUT_TOOLTIPS.get("jana_inflip", "") if jana_enabled
                else "Not used in External HKL mode."
            )
        hkl_widget = self.inputs.get("hkl")
        if isinstance(hkl_widget, PathRow):
            hkl_widget.set_tooltip(
                INPUT_TOOLTIPS.get("hkl", "") if (override_enabled or external_enabled)
                else "Not used with the Jana2020 .inflip input mode; reflections come from the .inflip file."
            )
        self._sync_metadata_source_widgets()
        self._sync_map_feedback_widgets()

    def _set_configuration_locked(self, locked: bool) -> None:
        locked = bool(locked)
        was_locked = self._configuration_locked
        self._configuration_locked = locked
        for key, widget in self.inputs.items():
            styled_widgets = [widget]
            if isinstance(widget, QWidget):
                styled_widgets.extend(widget.findChildren(QWidget))
            for styled_widget in styled_widgets:
                styled_widget.setProperty("configurationLocked", locked)
            if hasattr(widget, "setEnabled"):
                widget.setEnabled(not locked)  # type: ignore[attr-defined]
            label = self.input_labels.get(key)
            if label is not None:
                label.setProperty("configurationLocked", locked)
                label.setEnabled(not locked)
        for name in ("test_hkl_btn", "analyze_hkl_btn", "refresh_models_btn", "load_inflip_btn"):
            action = getattr(self, name, None)
            if action is not None:
                action.setEnabled(not locked)
        if hasattr(self, "configuration_lock_hint"):
            self.configuration_lock_hint.setVisible(locked)
        if was_locked and not locked:
            self._sync_input_source_mode_widgets()
            self._sync_metadata_source_widgets()
            self._sync_workflow_widgets()

    def _widget_value_as_string(self, widget: object) -> str:
        if isinstance(widget, PathRow):
            return widget.value()
        if isinstance(widget, QLineEdit):
            return widget.text()
        if isinstance(widget, QTextEdit):
            return widget.toPlainText()
        if isinstance(widget, QComboBox):
            # Internal-token combos (e.g. Next-cycle model) store the saved
            # token as Qt item data, distinct from the display text shown to
            # the user -- see _add_combo_with_values(). Combos whose items
            # are their own value simply have no data on the current item
            # and fall through to the display text as before.
            data = widget.currentData()
            return str(data) if data is not None else widget.currentText()
        if isinstance(widget, QCheckBox):
            return "true" if widget.isChecked() else "false"
        if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
            return str(widget.value())
        return ""

    def _set_widget_value_from_string(self, widget: object, value: str) -> None:
        value = "" if value is None else str(value)
        try:
            if isinstance(widget, PathRow):
                widget.set_value(value)
            elif isinstance(widget, QLineEdit):
                widget.setText(value)
            elif isinstance(widget, QTextEdit):
                widget.setPlainText(value)
            elif isinstance(widget, QComboBox):
                # Internal-token combos (userData != display text, e.g. the
                # Next-cycle model combo) are matched by data first; combos
                # whose items are their own value (the common case) simply
                # have no data to match and fall through to findText().
                idx = widget.findData(value)
                if idx < 0:
                    idx = widget.findText(value)
                if idx < 0:
                    # Case-insensitive fallback so a saved value survives a
                    # display-only capitalization change to a combo item
                    # (e.g. an old "custom" setting still matches "Custom").
                    idx = widget.findText(value, Qt.MatchFixedString)
                if idx >= 0:
                    widget.setCurrentIndex(idx)
                elif hasattr(widget, "setCurrentText"):
                    widget.setCurrentText(value)
            elif isinstance(widget, QCheckBox):
                widget.setChecked(value.strip().lower() in {"1", "true", "yes", "on"})
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(float(value)))
            elif isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(value.replace(",", ".")))
        except Exception:
            # Ignore stale/incompatible saved values.
            pass

    def load_settings(self) -> None:
        saved_metadata_source = self.settings.value("inputs/metadata_source", None)
        for key, widget in self.inputs.items():
            value = self.settings.value(f"inputs/{key}", None)
            if value is not None:
                if key == "reflection_data_mode":
                    # The combo's items are the human-readable display labels
                    # (see REFLECTION_DATA_MODE_DISPLAY_LABELS), not the raw
                    # internal tokens, so a saved value -- whether an old raw
                    # token from before that change or a display label saved
                    # since -- must be normalized then re-formatted to match
                    # an actual item, or findText() below fails to locate it
                    # and the saved HKL format selection is silently lost.
                    value = format_reflection_data_mode(normalize_reflection_data_mode(str(value)))
                self._set_widget_value_from_string(widget, str(value))

        # Migrate legacy generic executable names to the Jana2020 installation
        # defaults while preserving any explicit custom absolute path.
        executable_defaults = {
            "superflip_exe": r"C:\Jana2020\SUPERFLIP\superflip_original.exe",
            "edma_exe": r"C:\Jana2020\SUPERFLIP\EDMA.exe",
        }
        generic_values = {
            "superflip_exe": {"", "superflip", "superflip.exe"},
            "edma_exe": {"", "edma", "edma.exe"},
        }
        for key, default_path in executable_defaults.items():
            widget = self.inputs.get(key)
            if widget is None:
                continue
            current = self._widget_value_as_string(widget).strip()
            if current.lower() in generic_values[key]:
                self._set_widget_value_from_string(widget, default_path)
        # Backward compatibility with older GUI versions that had a separate
        # "Use symmetry for best densities" checkbox instead of "symmetry"
        # being a normal Density selection metric option.
        legacy_bestdensities_symmetry = str(self.settings.value("inputs/bestdensities_symmetry", "")).strip().lower() in {"1", "true", "yes", "on"}
        if legacy_bestdensities_symmetry and "bestdensities_metric" in self.inputs:
            self._set_widget_value_from_string(self.inputs["bestdensities_metric"], "symmetry")
        # Backward compatibility with older GUI versions that had one common
        # EDMA plimit field named "plimit".
        old_plimit = self.settings.value("inputs/plimit", None)
        if old_plimit is not None:
            if self.settings.value("inputs/plimit_superflip", None) is None and "plimit_superflip" in self.inputs:
                self._set_widget_value_from_string(self.inputs["plimit_superflip"], str(old_plimit))
            if self.settings.value("inputs/plimit_deblur", None) is None and "plimit_deblur" in self.inputs:
                self._set_widget_value_from_string(self.inputs["plimit_deblur"], str(old_plimit))
        # Backward compatibility with older GUI versions that had separate
        # export_superflip_ccp4/export_superflip_jana checkboxes instead of one
        # Map format choice.
        if self.settings.value("inputs/map_export_format", None) is None:
            legacy_jana = str(self.settings.value("inputs/export_superflip_jana", "")).strip().lower() in {"1", "true", "yes", "on"}
            legacy_ccp4 = str(self.settings.value("inputs/export_superflip_ccp4", "")).strip().lower() in {"1", "true", "yes", "on"}
            legacy_standard_hkl = str(self.settings.value("inputs/export_standard_hkl", "")).strip().lower() in {"1", "true", "yes", "on"}
            map_format_widget = self.inputs.get("map_export_format")
            if map_format_widget is not None and (legacy_jana or legacy_ccp4 or legacy_standard_hkl):
                self._set_widget_value_from_string(
                    map_format_widget,
                    "jana" if legacy_jana else ("ccp4" if legacy_ccp4 else "HKL reflections with phases"),
                )
        legacy_reference_xplor = self.settings.value("inputs/superflip_reference_xplor", None)
        legacy_superflip_referencefile = self.settings.value("inputs/superflip_referencefile", None)
        referencefile_widget = self.inputs.get("reference_cif")
        if referencefile_widget is not None and not self._widget_value_as_string(referencefile_widget).strip():
            legacy_reference = legacy_superflip_referencefile or legacy_reference_xplor
            if legacy_reference:
                self._set_widget_value_from_string(referencefile_widget, str(legacy_reference))
        if saved_metadata_source is None:
            self._set_metadata_source(self._default_metadata_source_for_input())
        self._sync_input_source_mode_widgets()
        self._sync_metadata_source_widgets()
        geom = self.settings.value("window/geometry", None)
        if geom is not None:
            try:
                self.restoreGeometry(geom)
            except Exception:
                pass
        for setting_key, splitter in (
            ("window/main_splitter", getattr(self, "main_splitter", None)),
            ("window/result_splitter", getattr(self, "result_splitter", None)),
        ):
            state = self.settings.value(setting_key, None)
            if state is not None and isinstance(splitter, QSplitter):
                try:
                    splitter.restoreState(state)
                except Exception:
                    pass

    def load_inflip_settings_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load Superflip settings", self._path_value("work_dir") or str(Path.cwd()), "Superflip input (*.inflip *.inp);;All files (*)")
        if not path:
            return
        try:
            parsed = parse_inflip_settings(Path(path))
            if "superflip_reference_xplor" in parsed and "superflip_referencefile" not in parsed:
                parsed["superflip_referencefile"] = parsed["superflip_reference_xplor"]
            if "superflip_referencefile" in parsed and "reference_cif" not in parsed:
                parsed["reference_cif"] = parsed["superflip_referencefile"]
            applied = 0
            for key, value in parsed.items():
                widget = self.inputs.get(key)
                if widget is None:
                    continue
                self._set_widget_value_from_string(widget, value)
                applied += 1
            self._append_execution_log(
                f"Loaded {applied} GUI settings from {path}",
                level="SUCCESS",
                subsystem="Jana2020",
            )
            self._append_execution_log(
                "HKL data format was imported when dataformat/dataitemwidths were present; "
                "reflection records and crystallographic blocks were not copied into editable fields.",
                level="DETAIL",
                subsystem="Jana2020",
            )
        except Exception as exc:
            self._show_error_report(
                build_error_report(exc, subsystem="Jana2020", operation="Load .inflip settings", paths=(path,))
            )

    def _collect_hkl_analysis_request(self) -> HklAnalysisRequest:
        mode = normalize_input_source_mode(self._combo_value("input_source_mode") if "input_source_mode" in self.inputs else "")
        hkl_text = self._path_value("hkl").strip() if "hkl" in self.inputs else ""
        jana_text = self._path_value("jana_inflip").strip() if "jana_inflip" in self.inputs else ""
        ref_text = self._path_value("reference_cif").strip() if "reference_cif" in self.inputs else ""
        work_text = self._path_value("work_dir").strip() if "work_dir" in self.inputs else ""
        configured_mode = self._combo_value("reflection_data_mode") if "reflection_data_mode" in self.inputs else REFLECTION_DATA_MODE_AUTO
        metadata = self._resolve_crystal_metadata_from_inputs()
        return HklAnalysisRequest(mode, hkl_text, jana_text, ref_text, work_text, configured_mode, metadata)

    def _set_hkl_task_running(self, running: bool) -> None:
        for button_name in ("test_hkl_btn", "analyze_hkl_btn"):
            button = getattr(self, button_name, None)
            if isinstance(button, QPushButton):
                button.setEnabled(not running and not self._configuration_locked)
        pipeline_active = self.worker is not None and self.worker.is_alive()
        run_is_idle = str(getattr(self, "_run_status", "READY")).upper() == "READY"
        if running and not pipeline_active and run_is_idle:
            self.progress_bar.setRange(0, 0)
            self._set_overall_progress_text("HKL analysis…")
        elif not running and not pipeline_active and run_is_idle:
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(0)
            self._set_overall_progress_text("Idle")

    def _start_hkl_background_task(self, label: str, worker_fn: Callable[[], object], done_kind: str) -> None:
        if self.hkl_task_worker is not None and self.hkl_task_worker.is_alive():
            self._append_execution_log(
                "HKL analysis is already running; wait for it to finish before starting another analysis.",
                level="WARNING",
                subsystem="HKL",
            )
            return
        self._set_hkl_task_running(True)
        self._hkl_task_generation += 1
        task_id = self._hkl_task_generation
        self._active_hkl_task_id = task_id

        def worker() -> None:
            try:
                result = worker_fn()
                self.msg_queue.put((done_kind, (task_id, result)))
            except Exception as exc:
                report = build_error_report(
                    exc,
                    subsystem="HKL",
                    operation=label,
                    extra_details=traceback.format_exc(),
                )
                self.msg_queue.put(("hkl_task_error", (task_id, report)))
            finally:
                self.msg_queue.put(("hkl_task_finished", (task_id, None)))

        self.hkl_task_worker = threading.Thread(target=worker, daemon=True)
        self.hkl_task_worker.start()

    def test_hkl_load_dialog(self) -> None:
        try:
            request = self._collect_hkl_analysis_request()
        except Exception as exc:
            self._show_error_report(build_error_report(exc, subsystem="HKL", operation="HKL validation"))
            return

        def worker() -> object:
            return build_hkl_load_result(request)

        self._start_hkl_background_task("HKL validation", worker, "hkl_load_result")

    def _diagnostic_header(
        self,
        title: str,
        subtitle: str,
        status: Optional[str] = None,
        *,
        compact: bool = False,
    ) -> QWidget:
        header = QWidget()
        header.setObjectName("diagnosticHeader")
        header.setProperty("headerDensity", "compact" if compact else "standard")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 5 if compact else 10, 14, 5 if compact else 10)
        text_layout = QVBoxLayout()
        text_layout.setSpacing(1)
        title_label = QLabel(title)
        title_label.setObjectName("diagnosticTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("diagnosticSubtitle")
        text_layout.addWidget(title_label)
        text_layout.addWidget(subtitle_label)
        header_layout.addLayout(text_layout, 1)
        if status:
            badge = QLabel(status)
            badge.setObjectName("diagnosticStatus")
            badge.setAlignment(Qt.AlignCenter)
            badge.setToolTip("Technical reflection input parsed successfully.")
            header_layout.addWidget(badge)
        return header

    def _diagnostic_input_summary(
        self,
        hkl_path: Path,
        data_mode: str,
        cell: gemmi.UnitCell,
        spacegroup_hm: str,
        source_note: str,
        extra_rows: Sequence[Tuple[str, str]] = (),
        compact: bool = False,
    ) -> QGroupBox:
        box = QGroupBox("INPUT SUMMARY")
        box.setObjectName("diagnosticSection")
        box.setProperty("summaryDensity", "compact" if compact else "standard")

        if compact and not extra_rows:
            grid = QGridLayout(box)
            grid.setContentsMargins(8, 1, 8, 1)
            grid.setHorizontalSpacing(12)
            grid.setVerticalSpacing(2)

            source_row = QWidget()
            source_layout = QHBoxLayout(source_row)
            source_layout.setContentsMargins(0, 0, 0, 0)
            source_layout.setSpacing(5)
            source_value = MiddleElidedLabel(hkl_path.name)
            source_value.setObjectName("diagnosticSummaryValue")
            source_value.setToolTip(wrap_path_tooltip(str(hkl_path)))
            source_layout.addWidget(source_value, 1)
            copy_path = QToolButton()
            copy_path.setObjectName("diagnosticTextAction")
            copy_path.setText("Copy path")
            copy_path.setToolTip("Copy the full reflection-source path.")
            copy_path.clicked.connect(lambda: QApplication.clipboard().setText(str(hkl_path)))
            source_layout.addWidget(copy_path)

            values = (
                ("Source", source_row),
                ("Format", QLabel(format_reflection_data_mode(data_mode))),
                ("Unit cell", QLabel(
                    f"{cell.a:.5g} × {cell.b:.5g} × {cell.c:.5g} Å · "
                    f"{cell.alpha:.4g}° × {cell.beta:.4g}° × {cell.gamma:.4g}°"
                )),
                ("Space group", QLabel(spacegroup_hm)),
            )
            for index, (label_text, value_widget) in enumerate(values):
                row, pair = divmod(index, 2)
                label = QLabel(label_text)
                label.setObjectName("diagnosticSummaryLabel")
                if isinstance(value_widget, QLabel):
                    value_widget.setObjectName("diagnosticSummaryValue")
                    value_widget.setTextInteractionFlags(Qt.TextSelectableByMouse)
                    value_widget.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
                grid.addWidget(label, row, pair * 2)
                grid.addWidget(value_widget, row, pair * 2 + 1)
            grid.setColumnStretch(1, 3)
            grid.setColumnStretch(3, 2)
            box.setToolTip(source_note)
            return box

        form = QFormLayout(box)
        form.setContentsMargins(10, 8 if compact else 12, 10, 4 if compact else 8)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(3 if compact else 5)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        source_row = QWidget()
        source_layout = QHBoxLayout(source_row)
        source_layout.setContentsMargins(0, 0, 0, 0)
        source_layout.setSpacing(7)
        source_value = QLabel(hkl_path.name)
        source_value.setObjectName("diagnosticSummaryValue")
        source_value.setToolTip(wrap_path_tooltip(str(hkl_path)))
        source_layout.addWidget(source_value)
        copy_path = QToolButton()
        copy_path.setObjectName("diagnosticTextAction")
        copy_path.setText("Copy path")
        copy_path.setToolTip("Copy the full reflection-source path.")
        copy_path.clicked.connect(lambda: QApplication.clipboard().setText(str(hkl_path)))
        source_layout.addWidget(copy_path)
        source_layout.addStretch(1)
        form.addRow("Source", source_row)

        rows = [
            ("Format", format_reflection_data_mode(data_mode)),
            ("Unit cell", f"{cell.a:.5g} × {cell.b:.5g} × {cell.c:.5g} Å · {cell.alpha:.4g}° × {cell.beta:.4g}° × {cell.gamma:.4g}°"),
            ("Space group", spacegroup_hm),
        ]
        rows.extend(extra_rows)
        for label_text, value_text in rows:
            value = QLabel(value_text)
            value.setObjectName("diagnosticSummaryValue")
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            form.addRow(label_text, value)
        box.setToolTip(source_note)
        return box

    def _diagnostic_metric_grid(
        self,
        metrics: Sequence[Tuple[str, str]],
        compact: bool = False,
        row_columns: Sequence[int] = (),
    ) -> QWidget:
        panel = QWidget()
        panel.setObjectName("diagnosticMetrics")
        cards: List[QWidget] = []
        for value_text, label_text in metrics:
            card = QWidget()
            card.setObjectName("diagnosticMetric")
            card.setProperty("metricDensity", "compact" if compact else "standard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(6 if compact else 8, 0 if compact else 7, 6 if compact else 8, 0 if compact else 7)
            card_layout.setSpacing(0)
            value = QLabel(value_text)
            value.setObjectName("diagnosticMetricValue")
            value.setAlignment(Qt.AlignCenter)
            label = QLabel(label_text)
            label.setObjectName("diagnosticMetricLabel")
            label.setAlignment(Qt.AlignCenter)
            label.setWordWrap(True)
            card_layout.addWidget(value)
            card_layout.addWidget(label)
            cards.append(card)

        requested_rows = tuple(int(count) for count in row_columns if int(count) > 0)
        if requested_rows and sum(requested_rows) == len(cards):
            rows_layout = QVBoxLayout(panel)
            rows_layout.setContentsMargins(0, 0, 0, 0)
            rows_layout.setSpacing(6)
            offset = 0
            for count in requested_rows:
                row_widget = QWidget()
                row_widget.setObjectName("diagnosticMetricRow")
                row_widget.setProperty("metricColumns", count)
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(6)
                for card in cards[offset:offset + count]:
                    card.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
                    row_layout.addWidget(card, 1)
                rows_layout.addWidget(row_widget)
                offset += count
        else:
            grid = QGridLayout(panel)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(6)
            grid.setVerticalSpacing(6)
            columns = min(4, max(1, len(metrics)))
            for index, card in enumerate(cards):
                grid.addWidget(card, index // columns, index % columns)
            for column in range(columns):
                grid.setColumnStretch(column, 1)
        return panel

    @staticmethod
    def _configure_diagnostic_table(table: QTableWidget) -> None:
        table.setObjectName("diagnosticTable")
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setHighlightSections(False)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)

    def _build_hkl_validation_dialog(self, result: HklLoadResult) -> QDialog:
        hkl_path = result.hkl_path
        data_mode = result.data_mode
        cell = result.cell
        hm = result.spacegroup_hm
        source_note = result.source_note
        value_col = result.value_col
        sigma_col = result.sigma_col
        include_000 = result.include_000
        reflections = result.reflections
        unique = result.unique_reflections
        sigma_count = sum(1 for reflection in reflections if reflection.sigma is not None)
        phase_count = sum(1 for reflection in reflections if reflection.phase is not None)
        value_label = reflection_value_label(data_mode)
        sigma_label = reflection_sigma_label(data_mode)
        snr_label = reflection_primary_snr_label(data_mode)
        is_fwhm_mode = reflection_mode_has_fwhm(data_mode)
        derived_ios_label = "Derived I/FWHM" if is_fwhm_mode else "Derived I/σ"

        dialog = QDialog(self)
        dialog.setObjectName("hklValidationDialog")
        dialog.setWindowTitle("HKL Validation")
        dialog.resize(1060, 680)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(9)
        layout.addWidget(self._diagnostic_header("HKL VALIDATION", "Reflection parsing and input diagnostics", "VALID"))
        column_summary = (
            f"{value_label}: column {value_col} · {sigma_label}: column "
            f"{sigma_col if sigma_col is not None else 'none'} · "
            f"(0 0 0): {'included' if include_000 else 'excluded'}"
        )
        layout.addWidget(self._diagnostic_input_summary(
            hkl_path,
            data_mode,
            cell,
            f"{compact_spacegroup_symbol(result.spacegroup)} (#{result.spacegroup.number})",
            source_note,
            (("Columns", column_summary),),
        ))
        layout.addWidget(self._diagnostic_metric_grid((
            (f"{len(reflections):,}", "Parsed"),
            (f"{len(unique):,}", "Unique"),
            (f"{sigma_count:,} / {len(reflections):,}", f"{sigma_label} coverage"),
            (f"{phase_count:,} / {len(reflections):,}", "Phase coverage"),
        )))

        sample_header = QHBoxLayout()
        sample_title = QLabel("REFLECTION SAMPLE")
        sample_title.setObjectName("diagnosticSectionTitle")
        sample_header.addWidget(sample_title)
        sample_header.addStretch(1)
        rows = min(50, len(reflections))
        sample_count = QLabel(f"First {rows:,} of {len(reflections):,} parsed reflections")
        sample_count.setObjectName("diagnosticMeta")
        sample_header.addWidget(sample_count)
        layout.addLayout(sample_header)

        # "Derived I/sigma" is categorically not applicable to FWHM data (every
        # row would read n/a, since FWHM is not a genuine sigma to propagate
        # error from) -- hide the column entirely rather than fill it with dashes.
        headers = ["h", "k", "l", value_label, sigma_label, "Phase (°)", snr_label]
        if not is_fwhm_mode:
            headers.append(derived_ios_label)
        headers.extend(["d (Å)", "sinθ/λ"])
        sigma_column_index = headers.index(sigma_label)
        table = QTableWidget(rows, len(headers))
        self._configure_diagnostic_table(table)
        table.setHorizontalHeaderLabels(headers)
        if not is_fwhm_mode:
            sigma_header_item = table.horizontalHeaderItem(sigma_column_index)
            if sigma_header_item is not None:
                sigma_header_item.setToolTip(
                    "~value marks a theoretical estimate (Poisson counting statistics, "
                    "σ ≈ √value) shown only because no measured uncertainty was parsed "
                    "for that reflection; it is not measured data."
                )
        for column in range(3):
            table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeToContents)
        for column in range(3, len(headers)):
            table.horizontalHeader().setSectionResizeMode(column, QHeaderView.Stretch)
        estimated_sigma_color = QColor("#7183a6")
        for row, reflection in enumerate(reflections[:rows]):
            d_spacing = reflection_d_spacing(cell, int(reflection.h), int(reflection.k), int(reflection.l))
            stl = reflection_sintheta_over_lambda(cell, int(reflection.h), int(reflection.k), int(reflection.l))
            primary_snr = reflection_primary_signal_to_noise(reflection, data_mode)

            sigma_is_estimated = False
            if reflection.sigma is not None:
                sigma_text = f"{float(reflection.sigma):.7g}"
            elif is_fwhm_mode:
                sigma_text = "—"
            else:
                # No measured uncertainty was parsed for this reflection: show a
                # theoretical Poisson counting-statistics estimate (sigma ~= sqrt
                # of the observed intensity/amplitude) instead of leaving it blank,
                # clearly marked with "~" so it is never mistaken for measured data.
                theoretical_sigma = math.sqrt(abs(float(reflection.value)))
                sigma_text = f"~{theoretical_sigma:.7g}"
                sigma_is_estimated = True

            row_values: List[Tuple[str, bool]] = [
                (str(int(reflection.h)), False),
                (str(int(reflection.k)), False),
                (str(int(reflection.l)), False),
                (f"{float(reflection.value):.7g}", False),
                (sigma_text, sigma_is_estimated),
                ("—" if reflection.phase is None else f"{float(reflection.phase):.7g}", False),
                ("—" if primary_snr is None else f"{float(primary_snr):.7g}", False),
            ]
            if not is_fwhm_mode:
                derived_ios = reflection_signal_to_noise(reflection, data_mode)
                row_values.append(("—" if derived_ios is None else f"{float(derived_ios):.7g}", False))
            row_values.append(("—" if not math.isfinite(d_spacing) else f"{d_spacing:.5g}", False))
            row_values.append((f"{stl:.5g}", False))

            for column, (text_value, is_estimate) in enumerate(row_values):
                item = QTableWidgetItem(text_value)
                item.setTextAlignment(Qt.AlignCenter if column < 3 else Qt.AlignRight | Qt.AlignVCenter)
                if is_estimate:
                    font = item.font()
                    font.setItalic(True)
                    item.setFont(font)
                    item.setForeground(estimated_sigma_color)
                    item.setToolTip(
                        "Theoretical estimate (σ ≈ √value, Poisson counting statistics) -- "
                        "no measured uncertainty was parsed for this reflection."
                    )
                table.setItem(row, column, item)
        layout.addWidget(table, 1)

        summary_text = (
            "HKL VALIDATION\n"
            f"Source: {hkl_path}\nFormat: {format_reflection_data_mode(data_mode)}\n"
            f"Unit cell: {cell.a:.5g} × {cell.b:.5g} × {cell.c:.5g} Å · "
            f"{cell.alpha:.4g}° × {cell.beta:.4g}° × {cell.gamma:.4g}°\n"
            f"Space group: {hm}\nParsed: {len(reflections):,}\nUnique: {len(unique):,}\n"
            f"{sigma_label} coverage: {sigma_count:,}/{len(reflections):,}\n"
            f"Phase coverage: {phase_count:,}/{len(reflections):,}"
        )
        footer = QHBoxLayout()
        copy_summary = QPushButton("Copy summary")
        copy_summary.setObjectName("diagnosticSecondaryButton")
        copy_summary.clicked.connect(lambda: QApplication.clipboard().setText(summary_text))
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        footer.addWidget(copy_summary)
        footer.addStretch(1)
        footer.addWidget(close_button)
        layout.addLayout(footer)
        dialog.hkl_table = table  # type: ignore[attr-defined]
        dialog.summary_text = summary_text  # type: ignore[attr-defined]
        dialog.full_source_path = str(hkl_path)  # type: ignore[attr-defined]
        fit_dialog_to_available_screen(dialog, QSize(1060, 680))
        return dialog

    def _show_hkl_load_result_dialog(self, payload: object) -> None:
        dialog = self._build_hkl_validation_dialog(payload)  # type: ignore[arg-type]
        # A second, deferred fit once the native window is fully realized
        # (matches _show_hkl_completeness_dialog): the first fit's frame
        # measurement can be inaccurate before the window manager settles.
        QTimer.singleShot(0, lambda: fit_dialog_to_available_screen(dialog, QSize(1060, 680)))
        dialog.exec()

    def open_hkl_completeness_dialog(self) -> None:
        try:
            request = self._collect_hkl_analysis_request()
        except Exception as exc:
            self._show_error_report(build_error_report(exc, subsystem="HKL", operation="HKL completeness analysis"))
            return

        def worker() -> object:
            hkl_path, data_mode, cell, sg, hm, source_note = resolve_hkl_analysis_inputs(request)
            analysis = analyze_hkl_data(hkl_path, data_mode, cell, sg, hm, source_note)
            return analysis

        self._start_hkl_background_task("HKL completeness analysis", worker, "hkl_completeness_result")

    def _build_hkl_completeness_dialog(self, analysis: HklAnalysis) -> QDialog:
        dialog = QDialog(self)
        dialog.setObjectName("hklCompletenessDialog")
        dialog.setWindowTitle("HKL Completeness")
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(9, 8, 9, 8)
        layout.setSpacing(4)
        layout.addWidget(self._diagnostic_header(
            "HKL COMPLETENESS",
            "Resolution-dependent completeness and intensity statistics",
            compact=True,
        ))
        d_min_text = format_resolution_d(analysis.d_min)
        d_full = format_resolution_d(analysis.d_full_98)
        sigma_label = reflection_sigma_label(analysis.data_mode)
        signal_label = reflection_primary_snr_label(analysis.data_mode)
        is_fwhm_mode = reflection_mode_has_fwhm(analysis.data_mode)
        raw_sigma_count = sum(1 for r in analysis.reflections_raw if r.sigma is not None)
        unique_sigma_count = sum(1 for r in analysis.reflections_unique if r.sigma is not None)
        phase_count = sum(1 for r in analysis.reflections_raw if r.phase is not None)
        primary_snr_values = [reflection_primary_signal_to_noise(r, analysis.data_mode) for r in analysis.reflections_unique]
        primary_snr_values = [float(v) for v in primary_snr_values if v is not None and math.isfinite(float(v))]
        median_signal = "n/a" if not primary_snr_values else f"{float(np.median(np.asarray(primary_snr_values, dtype=np.float64))):.3g}"
        signal_threshold = 3.0
        threshold_stl: Optional[float] = None
        threshold_d: Optional[float] = None
        signal_points = [
            (float(b["center"]), float(b["mean_signal_to_noise"]))
            for b in analysis.bins
            if math.isfinite(float(b["center"])) and math.isfinite(float(b["mean_signal_to_noise"]))
        ]
        # The I/sigma(I) = 3 significance convention does not apply to FWHM data:
        # FWHM is a peak-shape parameter (e.g. from a Le Bail powder extraction),
        # not a measurement uncertainty, so an I/FWHM ratio is not comparable in
        # scale or meaning to a genuine signal-to-noise ratio. Skip the threshold
        # entirely rather than presenting a number that looks like one but isn't.
        if not is_fwhm_mode:
            for idx, (stl, signal) in enumerate(signal_points):
                if signal >= signal_threshold:
                    continue
                if idx > 0:
                    prev_stl, prev_signal = signal_points[idx - 1]
                    if prev_signal >= signal_threshold and stl > prev_stl and not math.isclose(signal, prev_signal):
                        fraction = (signal_threshold - prev_signal) / (signal - prev_signal)
                        threshold_stl = prev_stl + fraction * (stl - prev_stl)
                    else:
                        threshold_stl = stl
                else:
                    threshold_stl = stl
                break
            if threshold_stl is not None and threshold_stl > 0:
                threshold_d = 1.0 / (2.0 * threshold_stl)
        threshold_d_text = "n/a (not meaningful for FWHM)" if is_fwhm_mode else format_resolution_d(threshold_d)
        input_summary = self._diagnostic_input_summary(
            analysis.hkl_path,
            analysis.data_mode,
            analysis.cell,
            f"{compact_spacegroup_symbol(analysis.spacegroup)} (#{analysis.spacegroup.number})",
            analysis.source_note,
            compact=True,
        )
        layout.addWidget(input_summary)
        if is_fwhm_mode:
            fwhm_note = QLabel(
                "<b>FWHM data</b><br>FWHM is a peak-shape parameter, not a measurement uncertainty. "
                "I/FWHM is shown only as a descriptive intensity-to-width measure; I/&sigma;(I)-based "
                "significance thresholds do not apply and are omitted below."
            )
            fwhm_note.setObjectName("helpCallout")
            fwhm_note.setTextFormat(Qt.RichText)
            fwhm_note.setWordWrap(True)
            layout.addWidget(fwhm_note)
        metric_cards = [
            (f"{len(analysis.reflections_unique):,}", "Unique reflections"),
            (d_min_text, "d_min"),
            (d_full, "d at 98% cumulative completeness"),
            (median_signal, f"Median {signal_label}"),
        ]
        if not is_fwhm_mode:
            # A significance threshold on I/FWHM would misrepresent it as a
            # conventional I/sigma(I)-style signal-to-noise ratio; omit the
            # card entirely rather than show a prose fallback as a metric value.
            metric_cards.append((threshold_d_text, f"d where mean {signal_label} < {signal_threshold:.1f}"))
        metric_cards.extend([
            (f"{phase_count:,} / {len(analysis.reflections_raw):,}", "Phase-value coverage"),
            (f"{raw_sigma_count:,} / {len(analysis.reflections_raw):,}", f"{sigma_label} coverage"),
        ])
        metrics_panel = self._diagnostic_metric_grid(
            metric_cards, compact=True, row_columns=(len(metric_cards),)
        )
        layout.addWidget(metrics_panel)

        content_splitter = QSplitter(Qt.Vertical)
        content_splitter.setObjectName("diagnosticSplitter")
        content_splitter.setChildrenCollapsible(False)
        plot_panel = QWidget()
        plot_panel.setMinimumHeight(300)
        plot_layout = QVBoxLayout(plot_panel)
        plot_layout.setContentsMargins(0, 0, 0, 0)
        plot_layout.setSpacing(3)
        plot_title = QLabel("COMPLETENESS AND SIGNAL VS RESOLUTION")
        plot_title.setObjectName("diagnosticSectionTitle")
        plot_layout.addWidget(plot_title)
        figure = Figure(figsize=(8.4, 6.4), dpi=100)
        canvas = FigureCanvas(figure)
        canvas.setObjectName("hklCompletenessCanvas")
        canvas.setMinimumHeight(280)
        canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        plot_grid = figure.add_gridspec(
            2,
            2,
            # The nested first row becomes two equal 1.15-height axes; the
            # histogram remains the deliberately secondary 0.65-height panel.
            height_ratios=(2.30, 0.65),
            width_ratios=(0.82, 0.18),
            hspace=0.64,
            wspace=0.04,
            left=0.095,
            right=0.985,
            bottom=0.14,
            top=0.942,
        )

        resize_hooks: Dict[str, Callable[[], None]] = {}

        def adjust_plot_bottom_margin(event) -> None:
            # Preserve a readable, unclipped histogram xlabel when the splitter
            # compresses the canvas: Matplotlib margins are fractional, while
            # the label needs approximately the same physical pixel clearance.
            canvas_height = max(1.0, float(event.height))
            responsive_bottom = min(0.21, max(0.14, 52.0 / canvas_height))
            responsive_hspace = min(0.86, max(0.64, 0.64 + (340.0 - canvas_height) / 420.0))
            responsive_top = min(0.942, 1.0 - 21.0 / canvas_height)
            responsive_ylabel_size = 6.0 if canvas_height < 320.0 else (8.0 if canvas_height < 360.0 else 9.0)
            if (
                not math.isclose(float(plot_grid.bottom), responsive_bottom, abs_tol=0.001)
                or not math.isclose(float(plot_grid.hspace), responsive_hspace, abs_tol=0.001)
                or not math.isclose(float(plot_grid.top), responsive_top, abs_tol=0.001)
            ):
                plot_grid.update(bottom=responsive_bottom, hspace=responsive_hspace, top=responsive_top)
                for plot_axis in figure.axes:
                    subplot_spec = plot_axis.get_subplotspec()
                    if subplot_spec is not None:
                        plot_axis.set_position(subplot_spec.get_position(figure))
                for resolution_axis in figure.axes[:2]:
                    resolution_axis.yaxis.label.set_fontsize(responsive_ylabel_size)
                if figure.legends:
                    responsive_legend_column = plot_grid[0, 1].get_position(figure)
                    figure.legends[0].set_bbox_to_anchor(
                        (
                            responsive_legend_column.x0 + 0.008,
                            (responsive_legend_column.y0 + responsive_legend_column.y1) / 2.0,
                        ),
                        transform=figure.transFigure,
                    )
                canvas.draw_idle()
            # Re-evaluate d_min/d_98 label placement for the new canvas size:
            # their screen-space separation (not their scientific values)
            # determines whether the labels can be shown side by side.
            relayout_guides = resize_hooks.get("relayout_guides")
            if relayout_guides is not None:
                relayout_guides()

        layout_resize_cid = canvas.mpl_connect("resize_event", adjust_plot_bottom_margin)
        resolution_grid = plot_grid[0, 0].subgridspec(
            2,
            1,
            height_ratios=(1.0, 1.0),
            hspace=0.15,
        )
        ax_completeness = figure.add_subplot(resolution_grid[0, 0])
        ax_signal = figure.add_subplot(resolution_grid[1, 0], sharex=ax_completeness)
        ax_histogram = figure.add_subplot(plot_grid[1, 0])
        centers = [float(b["center"]) for b in analysis.bins]
        widths = [max(0.0001, float(b["hi"]) - float(b["lo"])) for b in analysis.bins]
        completeness = [float(b["completeness"]) for b in analysis.bins]
        mean_signal = [float(b["mean_signal_to_noise"]) if math.isfinite(float(b["mean_signal_to_noise"])) else np.nan for b in analysis.bins]
        signal_values = [reflection_primary_signal_to_noise(r, analysis.data_mode) for r in analysis.reflections_unique]
        signal_values = [float(v) for v in signal_values if v is not None and math.isfinite(float(v))]
        if is_fwhm_mode:
            fwhm_numerator = "F" if reflection_mode_is_amplitude(analysis.data_mode) else "I"
            signal_math_label = rf"${fwhm_numerator}/\mathrm{{FWHM}}$"
            mean_signal_math_label = rf"Mean ${fwhm_numerator}/\mathrm{{FWHM}}$"
            threshold_math_label = None
        else:
            signal_math_label = r"$I/\sigma(I)$"
            mean_signal_math_label = r"Mean $I/\sigma(I)$"
            threshold_math_label = rf"$I/\sigma(I) = {signal_threshold:.1f}$"
        resolution_math_label = r"$\sin\theta/\lambda$"
        d_min_stl = 1.0 / (2.0 * analysis.d_min) if analysis.d_min > 0 else None
        d_full_stl = 1.0 / (2.0 * analysis.d_full_98) if analysis.d_full_98 is not None and analysis.d_full_98 > 0 else None
        d_min_plot_text = rf"{analysis.d_min:.5g} $\AA$" if d_min_stl is not None else "n/a"
        d_full_plot_text = rf"{analysis.d_full_98:.5g} $\AA$" if d_full_stl is not None else "n/a"
        figure.patch.set_facecolor("#ffffff")
        for axis in (ax_completeness, ax_signal, ax_histogram):
            axis.set_facecolor("#ffffff")
        completeness_artist = ax_completeness.bar(
            centers,
            completeness,
            width=widths,
            align="center",
            color="#2264b8",
            alpha=0.60,
            edgecolor="none",
            zorder=2,
            label="Completeness",
        )
        ax_completeness.step(
            centers,
            completeness,
            where="mid",
            color="#2264b8",
            linewidth=1.3,
            zorder=3,
        )
        ax_completeness.axhline(98.0, color="#001170", linewidth=1.0, linestyle="--", zorder=3)
        d_min_label = r"$d_{\mathrm{min}}$"
        d_98_label = r"$d_{98}$"
        d_min_artist = None
        d_full_artist = None
        if d_min_stl is not None:
            d_min_artist = ax_completeness.axvline(
                d_min_stl, color="#001170", linewidth=1.1, linestyle="-", label=d_min_label
            )
            ax_signal.axvline(d_min_stl, color="#001170", linewidth=1.1, linestyle="-")
        if d_full_stl is not None:
            d_full_artist = ax_completeness.axvline(
                d_full_stl, color="#44b7ff", linewidth=1.1, linestyle=":", label=d_98_label
            )
            ax_signal.axvline(d_full_stl, color="#44b7ff", linewidth=1.1, linestyle=":")
        ax_completeness.set_ylabel("Completeness (%)", labelpad=8, fontsize=9)
        shared_ylabel_x = -0.075
        ax_completeness.yaxis.set_label_coords(shared_ylabel_x, 0.5)
        ax_completeness.set_ylim(0, 102)
        ax_completeness.set_yticks((0, 50, 100))
        ax_completeness.tick_params(axis="x", which="both", bottom=False, labelbottom=False)
        ax_completeness.grid(True, axis="y", color="#cbd7ea", linewidth=0.45, alpha=0.42)
        mean_artist, = ax_signal.plot(
            centers,
            mean_signal,
            marker="o",
            color="#001170",
            linewidth=1.9,
            markersize=4.5,
            zorder=3,
            label=mean_signal_math_label,
        )
        threshold_artist = None
        if not is_fwhm_mode:
            threshold_artist = ax_signal.axhline(
                signal_threshold,
                color="#2264b8",
                linewidth=1.0,
                linestyle="--",
                zorder=2,
                label=threshold_math_label,
            )
        ax_signal.set_ylabel(mean_signal_math_label, labelpad=8, fontsize=9)
        ax_signal.yaxis.set_label_coords(shared_ylabel_x, 0.5)
        ax_signal.set_xlabel(resolution_math_label, labelpad=2)
        ax_signal.yaxis.set_major_locator(MaxNLocator(nbins=4, min_n_ticks=3))
        ax_signal.margins(y=0.08)
        ax_signal.grid(True, axis="y", color="#cbd7ea", linewidth=0.45, alpha=0.42)
        if threshold_stl is not None:
            ax_signal.axvline(threshold_stl, color="#2264b8", linewidth=1.1, linestyle="-.")
            threshold_plot_text = rf"{threshold_d:.5g} $\AA$" if threshold_d is not None else ""
            threshold_label = (
                rf"$I/\sigma(I)=3$ · {threshold_plot_text}"
                if threshold_plot_text
                else r"$I/\sigma(I)=3$"
            )
            ax_signal.annotate(
                threshold_label,
                xy=(threshold_stl, signal_threshold),
                xytext=(4, 5),
                textcoords="offset points",
                ha="left",
                va="bottom",
                color="#52658b",
                fontsize=7.0,
            )
        guide_annotation_artists: List[object] = []

        def place_resolution_guide_annotations() -> None:
            """Place the d_min/d_98 labels, avoiding overlap regardless of the
            current canvas size. The scientific values (d_min_plot_text,
            d_full_plot_text) are never altered here -- only where and how the
            two labels are drawn depends on their current screen-space gap."""
            for artist in guide_annotation_artists:
                try:
                    artist.remove()
                except Exception:
                    pass
            guide_annotation_artists.clear()

            entries: List[Tuple[float, str, str]] = []
            if d_min_stl is not None:
                entries.append((d_min_stl, d_min_label, d_min_plot_text))
            if d_full_stl is not None:
                entries.append((d_full_stl, d_98_label, d_full_plot_text))
            if not entries:
                return

            def annotate_one(x: float, text: str, ha: str, dx: float) -> None:
                guide_annotation_artists.append(
                    ax_completeness.annotate(
                        text,
                        xy=(x, 0.99),
                        xycoords=ax_completeness.get_xaxis_transform(),
                        xytext=(dx, -1.0),
                        textcoords="offset points",
                        ha=ha,
                        va="top",
                        color="#14204a",
                        fontsize=7.2,
                        bbox={"boxstyle": "square,pad=0.16", "facecolor": "#ffffff", "edgecolor": "none", "alpha": 0.88},
                        annotation_clip=False,
                    )
                )

            if len(entries) == 1:
                x, short_label, value_text = entries[0]
                annotate_one(x, f"{short_label}\n{value_text}", "center", 0.0)
                return

            entries.sort(key=lambda item: item[0])
            (x_left, label_left, text_left), (x_right, label_right, text_right) = entries
            # A real draw is needed so transData reflects the canvas size the
            # labels will actually be rendered at (including after a resize).
            try:
                figure.canvas.draw()
            except Exception:
                pass
            px_left = ax_completeness.transData.transform((x_left, 0.0))[0]
            px_right = ax_completeness.transData.transform((x_right, 0.0))[0]
            pixel_gap = abs(px_right - px_left)
            merge_threshold_px = 10.0
            collision_threshold_px = 62.0
            if pixel_gap < merge_threshold_px:
                # Case C: the two guide positions are visually indistinguishable
                # at this plot width. Report both scientific values together in
                # one box rather than drawing two illegibly close labels; the
                # values themselves are unchanged and still shown independently
                # in the summary cards and CSV export.
                x_mid = (x_left + x_right) / 2.0
                annotate_one(
                    x_mid,
                    f"{label_left} = {text_left}\n{label_right} = {text_right}",
                    "center",
                    0.0,
                )
            elif pixel_gap < collision_threshold_px:
                # Case B: close but distinguishable -- push the two labels apart
                # so their boxes clear each other while each stays visually
                # anchored (via the small xytext offset) to its own guide line.
                annotate_one(x_left, f"{label_left}\n{text_left}", "right", -8.0)
                annotate_one(x_right, f"{label_right}\n{text_right}", "left", 8.0)
            else:
                # Case A: well separated -- centered placement, as before.
                for x, label, text in entries:
                    annotate_one(x, f"{label}\n{text}", "center", 0.0)

        place_resolution_guide_annotations()
        resize_hooks["relayout_guides"] = place_resolution_guide_annotations

        legend_handles = [completeness_artist, mean_artist]
        legend_labels = ["Completeness", mean_signal_math_label]
        if threshold_artist is not None:
            legend_handles.append(threshold_artist)
            legend_labels.append(threshold_math_label)
        if d_full_artist is not None:
            legend_handles.append(d_full_artist)
            legend_labels.append(d_98_label)
        if d_min_artist is not None:
            legend_handles.append(d_min_artist)
            legend_labels.append(d_min_label)
        legend_column = plot_grid[0, 1].get_position(figure)
        legend_anchor = (
            legend_column.x0 + 0.008,
            (legend_column.y0 + legend_column.y1) / 2.0,
        )
        figure.legend(
            legend_handles,
            legend_labels,
            loc="center left",
            bbox_to_anchor=legend_anchor,
            bbox_transform=figure.transFigure,
            ncol=1,
            frameon=False,
            fontsize=8.0,
            handlelength=1.10,
            handletextpad=0.30,
            labelspacing=0.26,
            borderaxespad=0.0,
        )
        histogram_denominator = max(1, len(analysis.reflections_unique))
        if signal_values:
            histogram_bins = np.arange(0.0, 16.0, 1.0)
            histogram_weights = np.full(len(signal_values), 100.0 / float(histogram_denominator), dtype=np.float64)
            ax_histogram.hist(signal_values, bins=histogram_bins, weights=histogram_weights, color="#44b7ff", alpha=0.82)
        else:
            no_signal_text = (
                f"No {reflection_primary_snr_label(analysis.data_mode)} values available"
                if is_fwhm_mode else "No sigma values available"
            )
            ax_histogram.text(0.5, 0.5, no_signal_text, transform=ax_histogram.transAxes, ha="center", va="center")
        histogram_title_artist = ax_histogram.set_title(
            "REFLECTION DISTRIBUTION",
            loc="left",
            pad=9,
            color="#001170",
            fontsize=9,
            fontweight="bold",
        )
        ax_histogram.set_xlabel(signal_math_label, labelpad=4)
        ax_histogram.set_ylabel("Reflections (%)", labelpad=8, fontsize=9)
        ax_histogram.set_xlim(0.0, 15.0)
        ax_histogram.set_xticks(np.arange(0.0, 16.0, 1.0))
        ax_histogram.grid(True, axis="y", color="#cbd7ea", linewidth=0.45, alpha=0.42)
        for axis in (ax_completeness, ax_signal, ax_histogram):
            axis.tick_params(colors="#14204a")
            axis.xaxis.label.set_color("#14204a")
            axis.yaxis.label.set_color("#14204a")
            for spine in ("top", "right"):
                axis.spines[spine].set_visible(False)
        plot_layout.addWidget(canvas, 1)
        content_splitter.addWidget(plot_panel)

        bins_panel = QWidget()
        bins_panel.setMinimumHeight(94)
        bins_layout = QVBoxLayout(bins_panel)
        bins_layout.setContentsMargins(0, 0, 0, 0)
        bins_layout.setSpacing(3)
        bins_title = QLabel("RESOLUTION BINS")
        bins_title.setObjectName("diagnosticSectionTitle")
        bins_layout.addWidget(bins_title)
        headers = ["sinθ/λ range", "Observed", "Theoretical", "Completeness (%)", f"Mean {signal_label}"]
        table = QTableWidget(len(analysis.bins), len(headers))
        table.setMinimumHeight(68)
        self._configure_diagnostic_table(table)
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for row, item in enumerate(analysis.bins):
            theory_count = int(item["theory"])
            values = [
                f"{float(item['lo']):.4g} - {float(item['hi']):.4g}",
                str(int(item["observed"])),
                str(theory_count),
                # Completeness is undefined with no theoretical reflections in the shell.
                "—" if theory_count == 0 else f"{float(item['completeness']):.2f}",
                "n/a" if not math.isfinite(float(item["mean_signal_to_noise"])) else f"{float(item['mean_signal_to_noise']):.3g}",
            ]
            for column, text_value in enumerate(values):
                cell_item = QTableWidgetItem(text_value)
                cell_item.setTextAlignment(Qt.AlignCenter if column == 0 else Qt.AlignRight | Qt.AlignVCenter)
                table.setItem(row, column, cell_item)
        bins_layout.addWidget(table, 1)
        content_splitter.addWidget(bins_panel)
        # Give the scientific plots the reclaimed height while retaining a
        # fully visible, independently scrollable resolution-bin table.
        content_splitter.setSizes([450, 100])
        content_splitter.setStretchFactor(0, 5)
        content_splitter.setStretchFactor(1, 1)
        layout.addWidget(content_splitter, 1)

        summary_text = (
            "HKL COMPLETENESS\n"
            f"Source: {analysis.hkl_path}\nFormat: {format_reflection_data_mode(analysis.data_mode)}\n"
            f"Unit cell: {analysis.cell.a:.5g} {analysis.cell.b:.5g} {analysis.cell.c:.5g} {analysis.cell.alpha:.4g} {analysis.cell.beta:.4g} {analysis.cell.gamma:.4g}\n"
            f"Space group: {compact_spacegroup_symbol(analysis.spacegroup)} (#{analysis.spacegroup.number})\nParsed / unique: {len(analysis.reflections_raw):,} / {len(analysis.reflections_unique):,}\n"
            f"{sigma_label} coverage: {raw_sigma_count:,}/{len(analysis.reflections_raw):,} raw; {unique_sigma_count:,}/{len(analysis.reflections_unique):,} unique\n"
            f"Phase values: {phase_count:,}/{len(analysis.reflections_raw):,}\n"
            f"d_min: {d_min_text}\nd at 98% cumulative completeness: {d_full}\n"
            f"Median {signal_label}: {median_signal}\nd where mean {signal_label} falls below {signal_threshold:.1f}: {threshold_d_text}"
        )

        def export_csv() -> None:
            file_name, _ = QFileDialog.getSaveFileName(dialog, "Export resolution bins", "hkl_completeness.csv", "CSV files (*.csv)")
            if not file_name:
                return
            with Path(file_name).open("w", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream)
                writer.writerow(headers)
                for bin_item in analysis.bins:
                    writer.writerow([
                        f"{float(bin_item['lo']):.8g} - {float(bin_item['hi']):.8g}",
                        int(bin_item["observed"]),
                        int(bin_item["theory"]),
                        float(bin_item["completeness"]),
                        "" if not math.isfinite(float(bin_item["mean_signal_to_noise"])) else float(bin_item["mean_signal_to_noise"]),
                    ])

        def export_plot() -> None:
            file_name, _ = QFileDialog.getSaveFileName(dialog, "Export completeness plot", "hkl_completeness.png", "PNG image (*.png);;PDF document (*.pdf);;SVG image (*.svg)")
            if file_name:
                figure.savefig(file_name, dpi=200, bbox_inches="tight")

        footer = QHBoxLayout()
        copy_summary = QPushButton("Copy summary")
        copy_summary.setObjectName("diagnosticSecondaryButton")
        copy_summary.clicked.connect(lambda: QApplication.clipboard().setText(summary_text))
        export_csv_button = QPushButton("Export CSV")
        export_csv_button.setObjectName("diagnosticSecondaryButton")
        export_csv_button.clicked.connect(export_csv)
        export_plot_button = QPushButton("Export plot")
        export_plot_button.setObjectName("diagnosticSecondaryButton")
        export_plot_button.clicked.connect(export_plot)
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        footer.addWidget(copy_summary)
        footer.addWidget(export_csv_button)
        footer.addWidget(export_plot_button)
        footer.addStretch(1)
        footer.addWidget(close_button)
        layout.addLayout(footer)
        dialog.hkl_bins_table = table  # type: ignore[attr-defined]
        dialog.hkl_input_summary = input_summary  # type: ignore[attr-defined]
        dialog.hkl_metrics_panel = metrics_panel  # type: ignore[attr-defined]
        dialog.hkl_plot_panel = plot_panel  # type: ignore[attr-defined]
        dialog.hkl_figure = figure  # type: ignore[attr-defined]
        dialog.hkl_canvas = canvas  # type: ignore[attr-defined]
        dialog.hkl_resolution_axes = (ax_completeness, ax_signal)  # type: ignore[attr-defined]
        dialog.hkl_histogram_axis = ax_histogram  # type: ignore[attr-defined]
        dialog.hkl_histogram_title_artist = histogram_title_artist  # type: ignore[attr-defined]
        dialog.hkl_bins_title = bins_title  # type: ignore[attr-defined]
        dialog.hkl_plot_grid = plot_grid  # type: ignore[attr-defined]
        dialog.hkl_resolution_grid = resolution_grid  # type: ignore[attr-defined]
        dialog.hkl_legend_column_bounds = legend_column  # type: ignore[attr-defined]
        dialog.hkl_layout_resize_cid = layout_resize_cid  # type: ignore[attr-defined]
        dialog.hkl_content_splitter = content_splitter  # type: ignore[attr-defined]
        dialog.summary_text = summary_text  # type: ignore[attr-defined]
        dialog.full_source_path = str(analysis.hkl_path)  # type: ignore[attr-defined]
        fit_dialog_to_available_screen(dialog)
        return dialog

    def _show_hkl_completeness_dialog(self, analysis: HklAnalysis) -> None:
        dialog = self._build_hkl_completeness_dialog(analysis)
        QTimer.singleShot(0, lambda: fit_dialog_to_available_screen(dialog))
        dialog.exec()

    def save_settings(self) -> None:
        for key, widget in self.inputs.items():
            self.settings.setValue(f"inputs/{key}", self._widget_value_as_string(widget))
        self.settings.setValue("window/geometry", self.saveGeometry())
        if hasattr(self, "main_splitter"):
            self.settings.setValue("window/main_splitter", self.main_splitter.saveState())
        if hasattr(self, "result_splitter"):
            self.settings.setValue("window/result_splitter", self.result_splitter.saveState())
        self.settings.sync()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.save_settings()
        super().closeEvent(event)

    def _path_value(self, key: str) -> str:
        return self.inputs[key].value()  # type: ignore[attr-defined]

    def _line_value(self, key: str) -> str:
        widget = self.inputs.get(key)
        if widget is None or not hasattr(widget, "text"):
            return ""
        return widget.text().strip()  # type: ignore[attr-defined]

    def _multiline_value(self, key: str) -> str:
        widget = self.inputs.get(key)
        if widget is None or not hasattr(widget, "toPlainText"):
            return ""
        return widget.toPlainText().strip()  # type: ignore[attr-defined]

    def _combo_value(self, key: str) -> str:
        widget = self.inputs.get(key)
        if widget is None or not hasattr(widget, "currentText"):
            return ""
        if hasattr(widget, "currentData"):
            data = widget.currentData()  # type: ignore[attr-defined]
            if data is not None:
                return str(data)
        return widget.currentText().strip()  # type: ignore[attr-defined]

    def _check_value(self, key: str) -> bool:
        widget = self.inputs.get(key)
        if widget is None or not hasattr(widget, "isChecked"):
            return False
        return bool(widget.isChecked())  # type: ignore[attr-defined]

    def _spin_value(self, key: str) -> int:
        widget = self.inputs.get(key)
        if widget is None or not hasattr(widget, "value"):
            return 0
        return int(widget.value())  # type: ignore[attr-defined]

    def _dspin_value(self, key: str) -> float:
        widget = self.inputs.get(key)
        if widget is None or not hasattr(widget, "value"):
            return 0.0
        return float(widget.value())  # type: ignore[attr-defined]

    def _set_overall_progress_text(self, text: str) -> None:
        display = str(text)
        self.progress_bar.setFormat(display)
        if hasattr(self, "overall_progress_value"):
            self.overall_progress_value.setText(display)

    def clear_log_plot(self) -> None:
        self.log_text.clear()
        self.log_text.horizontalScrollBar().setValue(0)
        self._last_log_record = None
        self.results.clear()
        self.reference_atoms_for_plot.clear()
        self.superflip_atoms_for_plot.clear()
        self.deblur_atoms_for_plot.clear()
        self.structure_cell = None
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self._set_overall_progress_text("Idle")
        self._cycle_progress_state = None
        self.current_cycle_detail.setText("Idle")
        self.current_cycle_stage_counter.setText("Idle")
        self.current_cycle_progress.setRange(0, 1)
        self.current_cycle_progress.setValue(0)
        self._apply_superflip_repeat_state(None)
        self._set_run_status("Ready")
        self._sync_jana_action_button()
        self.last_run_config = None
        self._update_plot()
        self._update_structure_views()

    def _append_execution_log(
        self,
        payload: object,
        *,
        level: str = "",
        subsystem: str = "",
    ) -> bool:
        work_dir = self.last_run_config.work_dir if self.last_run_config is not None else None
        record = payload if isinstance(payload, ExecutionLogRecord) else classify_log_record(
            payload,
            level=level,
            subsystem=subsystem,
            work_dir=work_dir,
        )
        repeatable_status = bool(
            record.subsystem.lower() == "sharped"
            and re.search(r"(?:server status:|\]\s*(?:processing|completed|uploading|downloading))", record.text, re.IGNORECASE)
        )
        # Consecutive, byte-identical INFO/SUCCESS/DETAIL lines are almost always
        # presentation noise (e.g. a settings-loading step logged from more than
        # one code path with the same summary), not new information. WARNING,
        # ERROR and STEP lines are never suppressed this way, even if repeated,
        # since a recurring warning is meaningful on every cycle it appears.
        duplicate_informational = record.level.upper() in {"INFO", "SUCCESS", "DETAIL"}
        if (repeatable_status or duplicate_informational) and self._last_log_record == record:
            return False

        scroll_bar = self.log_text.verticalScrollBar()
        was_following = scroll_bar.maximum() - scroll_bar.value() <= max(4, scroll_bar.pageStep() // 20)
        cursor = QTextCursor(self.log_text.document())
        cursor.movePosition(QTextCursor.End)
        if self.log_text.document().characterCount() > 1:
            cursor.insertBlock()
        block_format = cursor.blockFormat()
        block_format.setLineHeight(112.0, QTextBlockFormat.ProportionalHeight.value)
        cursor.setBlockFormat(block_format)
        text_format = QTextCharFormat()
        colors = {
            "INFO": "#14204a",
            "STEP": "#001170",
            "SUCCESS": "#2264b8",
            "WARNING": "#8a5a00",
            "ERROR": "#b42318",
            "COMMAND": "#52658b",
            "DETAIL": "#7183a6",
        }
        text_format.setForeground(QColor(colors.get(record.level, "#001170")))
        workflow_subsystem = record.subsystem.casefold() in {"superflip", "sharped", "edma"}
        workflow_heading = (
            record.level not in {"DETAIL", "COMMAND"}
            and (
                workflow_subsystem
                or record.level in {"STEP", "SUCCESS", "ERROR"}
                or bool(re.match(r"^(?:===\s*)?cycle\s+\d+", record.text.strip(), re.IGNORECASE))
            )
        )
        text_format.setFontWeight(QFont.DemiBold if workflow_heading else QFont.Normal)
        text_format.setFontFixedPitch(True)
        cursor.insertText(record.text, text_format)
        if was_following:
            scroll_bar.setValue(scroll_bar.maximum())
        self._last_log_record = record
        return True

    def log(self, message: str, *, level: str = "", subsystem: str = "") -> None:
        work_dir = self.last_run_config.work_dir if self.last_run_config is not None else None
        self.msg_queue.put(("log", classify_log_record(
            message,
            level=level,
            subsystem=subsystem,
            work_dir=work_dir,
        )))

    def _emit_cycle_progress(
        self,
        cycle_index: int,
        cycle_total: int,
        stages: Sequence[str],
        stage_name: str,
        *,
        sub_index: Optional[int] = None,
        sub_total: Optional[int] = None,
        detail: str = "",
        busy: bool = False,
        complete: bool = False,
    ) -> None:
        try:
            stage_index = list(stages).index(stage_name) + 1
        except ValueError:
            stage_index = max(1, len(stages))
        self.msg_queue.put(("cycle_progress", CycleProgressState(
            cycle_index=max(1, int(cycle_index)),
            cycle_total=max(1, int(cycle_total)),
            stage_name=str(stage_name),
            stage_index=stage_index,
            stage_total=max(1, len(stages)),
            sub_index=sub_index,
            sub_total=sub_total,
            detail=str(detail),
            busy=bool(busy),
            complete=bool(complete),
        )))

    def _apply_cycle_progress_state(self, state: CycleProgressState) -> None:
        self._cycle_progress_state = state
        stage_total = max(1, int(state.stage_total))
        self.current_cycle_progress.setRange(0, stage_total)
        completed_stages = stage_total if state.complete else max(0, min(stage_total, int(state.stage_index) - 1))
        self.current_cycle_progress.setValue(completed_stages)
        display_text = state.display_text()
        if self.stop_after_cycle.is_set():
            stop_detail = "Stopping immediately…" if self.stop_now.is_set() else "Stopping after current cycle…"
            display_text = f"{display_text} · {stop_detail}"
        self.current_cycle_detail.setText(display_text)
        self.current_cycle_stage_counter.setText(
            "Completed" if state.complete else f"Stage {state.stage_index} of {stage_total}"
        )
        self._apply_superflip_repeat_state(state)

    def _apply_superflip_repeat_state(self, state: Optional[CycleProgressState]) -> None:
        sub_total = None if state is None else state.sub_total
        sub_index = None if state is None else state.sub_index
        if state is None or state.complete or sub_total is None or sub_index is None or int(sub_total) <= 1:
            self.superflip_repeat_detail.setVisible(False)
            self.superflip_repeat_progress.setVisible(False)
            return
        sub_total = int(sub_total)
        sub_index = max(1, min(int(sub_index), sub_total))
        self.superflip_repeat_detail.setText(f"Superflip repeat {sub_index} of {sub_total}")
        self.superflip_repeat_detail.setVisible(True)
        self.superflip_repeat_progress.setRange(0, sub_total)
        self.superflip_repeat_progress.setValue(sub_index)
        self.superflip_repeat_progress.setVisible(True)

    def _annotate_cycle_progress(self, detail: str) -> None:
        state = self._cycle_progress_state
        if state is None:
            self.current_cycle_detail.setText(str(detail))
            return
        text = state.display_text()
        self.current_cycle_detail.setText(f"{text} · {detail}" if detail else text)

    def _set_terminal_cycle_state(self, terminal: str) -> None:
        """Preserve the last reached stage without retaining active-state wording."""
        state = self._cycle_progress_state
        self._apply_superflip_repeat_state(None)
        if state is None:
            self.current_cycle_progress.setRange(0, 1)
            self.current_cycle_progress.setValue(0)
            self.current_cycle_stage_counter.setText(terminal)
            self.current_cycle_detail.setText("Stopped by user" if terminal == "Stopped" else terminal)
            return

        stage_total = max(1, int(state.stage_total))
        stage_index = max(1, min(stage_total, int(state.stage_index)))
        self.current_cycle_progress.setRange(0, stage_total)
        self.current_cycle_progress.setValue(max(self.current_cycle_progress.value(), stage_index))
        self.current_cycle_stage_counter.setText(f"{terminal} at stage {stage_index} of {stage_total}")
        parts = [f"Cycle {state.cycle_index} of {state.cycle_total}", state.stage_name]
        parts.append("stopped by user" if terminal == "Stopped" else terminal.lower())
        self.current_cycle_detail.setText(" · ".join(parts))

    def _finish_cancelled_run(self) -> None:
        """Apply the single user-facing terminal state for either stop action."""
        self.worker = None
        completed_cycles = max(len(self.results), self.progress_bar.value() if self.progress_bar.maximum() > 0 else 0)
        total_cycles = max(1, int(getattr(self.last_run_config, "cycles", 1)), completed_cycles)
        self.progress_bar.setRange(0, total_cycles)
        self.progress_bar.setValue(min(completed_cycles, total_cycles))
        self._set_overall_progress_text("Cancelled")
        self._set_terminal_cycle_state("Stopped")
        self.stop_after_cycle.clear()
        self.stop_now.clear()
        self._set_run_status("Cancelled")
        self.run_btn.setText("Run phasing")
        self._update_action_states()
        self._append_execution_log("Pipeline cancelled by the user.", level="WARNING", subsystem="Pipeline")

    def _set_run_status(self, status: str) -> None:
        normalized = str(status).strip().upper() or "READY"
        normalized = {
            "IDLE": "READY",
            "DONE": "COMPLETE",
            "COMPLETED": "COMPLETE",
            "FAILED": "ERROR",
            "CANCELED": "CANCELLED",
            # The pipeline is still RUNNING for button-enablement purposes while a
            # stop is pending; the "stopping" badge is shown separately via
            # _show_stopping_badge() without changing the stored _run_status.
            "STOPPING": "RUNNING",
        }.get(normalized, normalized)
        self._run_status = normalized
        if hasattr(self, "status_badge"):
            self.status_badge.setText(normalized)
            self.status_badge.setProperty("runState", normalized.lower())
            self.status_badge.style().unpolish(self.status_badge)
            self.status_badge.style().polish(self.status_badge)
        self._update_action_states()
        # Refreshes only the metrics tabs' state-aware empty-state text (never
        # overwrites real plotted data, since it's gated on there being no
        # results yet); this was previously dead code checking a
        # self.canvas attribute that is never actually set anywhere.
        if hasattr(self, "metrics_canvases") and not getattr(self, "results", []):
            self._update_plot()
        if hasattr(self, "structure_canvas"):
            self._update_structure_views()

    def _update_action_states(self) -> None:
        status = str(getattr(self, "_run_status", "READY")).upper()
        active = status == "RUNNING"
        self._set_configuration_locked(active)
        if hasattr(self, "run_btn"):
            # Invalid crystal metadata does not disable Run: start_run()'s
            # own get_config() call raises the same underlying error, which
            # is already reported through the normal error dialog on click.
            self.run_btn.setEnabled(not active)
        if hasattr(self, "continue_btn"):
            self.continue_btn.setEnabled(not active and getattr(self, "_resume_state", None) is not None)
        if hasattr(self, "stop_btn"):
            self.stop_btn.setEnabled(status == "RUNNING" and not self.stop_after_cycle.is_set())
        if hasattr(self, "stop_now_btn"):
            self.stop_now_btn.setEnabled(status == "RUNNING" and not self.stop_now.is_set())
        if hasattr(self, "clear_btn"):
            has_results = bool(getattr(self, "results", []))
            has_log = bool(hasattr(self, "log_text") and self.log_text.toPlainText().strip())
            self.clear_btn.setEnabled(not active and (has_results or has_log))
        self._sync_jana_action_button()

    def _jana_wizard_handoff_available(self) -> bool:
        """Whether a Jana2020 Wizard hand-off/result-selector action is
        currently meaningful: only for a session actually launched from the
        Wizard (Full configuration or Phase recycling), with a completed run
        whose results came from a Jana2020 .inflip. A standalone session that
        happens to load a .inflip manually must never satisfy this."""
        return bool(
            self.results
            and self.last_run_config
            and self.last_run_config.jana_inflip is not None
            and self.jana_wizard_context.launched_from_jana_wizard
            and self.jana_wizard_context.launch_mode in ("full_configuration", "phase_recycling")
        )

    def _sync_window_title(self) -> None:
        """Single source of truth for the window title, driven entirely by
        launch context (jana_wizard_context.launched_from_jana_wizard) --
        never inferred from whether a .inflip happens to be loaded. Mirrors
        _sync_jana_action_button()'s "Install to Jana2020" / "Send to
        Jana2020" pattern."""
        if self.jana_wizard_context.launched_from_jana_wizard:
            self.setWindowTitle(f"Phase Studio {__version__} for Jana2020")
        else:
            self.setWindowTitle(f"Phase Studio {__version__}")

    def _sync_jana_action_button(self) -> None:
        """Single source of truth for the third primary action button's
        label/tooltip/enabled state, driven entirely by launch context
        (jana_wizard_context.launched_from_jana_wizard) -- never inferred
        from whether a .inflip happens to be loaded."""
        if not hasattr(self, "jana_action_btn"):
            return
        active = str(getattr(self, "_run_status", "READY")).upper() == "RUNNING"
        if self.jana_wizard_context.launched_from_jana_wizard:
            self.jana_action_btn.setText("Send to Jana2020")
            self.jana_action_btn.setToolTip(
                "After a run launched from the Jana2020 Wizard completes, select a cycle and either its "
                "Superflip or SharpED result for handoff back to Jana2020."
            )
            self.jana_action_btn.setEnabled((not active) and self._jana_wizard_handoff_available())
        else:
            self.jana_action_btn.setText("Install to Jana2020")
            self.jana_action_btn.setToolTip(
                "Install, update, repair or remove the Phase Studio Jana2020 launcher inside a Jana2020 "
                "installation (Jana2020\\SUPERFLIP). Available at any time; no completed run is required."
            )
            # An application-integration action, not a result action (spec
            # section 3): enabled in normal READY state, disabled only while
            # a calculation is actively running, so files used by Jana/
            # Superflip are not modified during an active Phase Studio run.
            self.jana_action_btn.setEnabled(not active)

    def _on_jana_action_clicked(self) -> None:
        """Dispatches the third primary action according to launch context:
        the existing Jana2020 result hand-off for a Wizard-launched session,
        or the Jana2020 integration management dialog for a standalone one."""
        if self.jana_wizard_context.launched_from_jana_wizard:
            self.open_jana_handoff_dialog()
        else:
            self.open_install_to_jana_dialog()

    def _show_stopping_badge(self) -> None:
        # Cosmetic only: the pipeline is still RUNNING for _update_action_states()
        # purposes (stop/stop-now button enablement, configuration lock) until the
        # worker actually exits, but the visible status badge should reflect that a
        # stop was requested rather than sitting on "RUNNING" with no feedback.
        if hasattr(self, "status_badge"):
            self.status_badge.setText("STOPPING")
            self.status_badge.setProperty("runState", "stopping")
            self.status_badge.style().unpolish(self.status_badge)
            self.status_badge.style().polish(self.status_badge)

    def request_stop_after_cycle(self) -> None:
        self.stop_after_cycle.set()
        self._annotate_cycle_progress("Stopping after current cycle…")
        self._update_action_states()
        self._show_stopping_badge()
        self.log("Stop after current cycle requested.", level="DETAIL")

    def request_immediate_stop(self) -> None:
        self.stop_after_cycle.set()
        self.stop_now.set()
        self._annotate_cycle_progress("Stopping immediately…")
        self._update_action_states()
        self._show_stopping_badge()
        self.log("Immediate stop requested.", level="DETAIL")

    def refresh_sharped_models(self) -> None:
        base_widget = self.inputs.get("sharped_base_url")
        timeout_widget = self.inputs.get("sharped_timeout_seconds")
        base_url = base_widget.text().strip() if isinstance(base_widget, QLineEdit) else "https://jana.fzu.cz"
        timeout = 20
        if isinstance(timeout_widget, QSpinBox):
            timeout = max(5, min(60, int(timeout_widget.value())))

        def worker() -> None:
            try:
                client = SharpEDServerClient(base_url=base_url or "https://jana.fzu.cz", timeout=float(timeout))
                models = client.get_models()
                self.msg_queue.put(("sharped_models", (models.default_model, models.models)))
            except Exception as exc:
                self.msg_queue.put(("log", f"SharpED model refresh failed: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_workflow_preset(self, preset: str) -> None:
        name = str(preset or "").strip().lower()
        if name == "custom":
            return

        def set_value(key: str, value: str) -> None:
            widget = self.inputs.get(key)
            if widget is not None:
                self._set_widget_value_from_string(widget, value)

        if "recommended" in name:
            set_value("cycles", "5")
            set_value("reconstruction_mode", "Superflip")
            set_value("modelfile_source", "deblurred_xplor")
            set_value("damping_factor", "0.3")
            set_value("exclude_atoms", "none")
            set_value("run_edma_superflip", "true")
            set_value("run_sharped", "true")
            set_value("symmetrize_deblurred_map", "false")
            set_value("run_edma_deblurred", "true")
            set_value("run_edma_recycle_final", "false")
            set_value("compute_omit_maps", "false")
            set_value("compute_omit_rfree", "false")
            set_value("map_feedback_missing_enabled", "false")
            set_value("map_feedback_missing_from_cycle", "1")
            set_value("map_feedback_intensity_enabled", "false")
            set_value("map_feedback_intensity_from_cycle", "1")
            set_value("redistribute_overlaps", "false")
            set_value("powder_redistribution_from_cycle", "1")
            set_value("powder_wavelength", "0.0")
            set_value("powder_separation_factor", "0.2")
            set_value("powder_redistribution_mix", "1.0")
            set_value("sharped_model", "koala 2.0")
            set_value("perform_algorithm", "CF")
            set_value("maxcycles", "2000")
            set_value("repeatmode", "10")
            set_value("randomseed", "AUTO")
            set_value("delta", "AUTO")
            set_value("weakratio", "0.000")
            set_value("biso", "0.000")
            set_value("polish", "true")
            set_value("voxel", "")
            set_value("bestdensities_count", "1")
            set_value("bestdensities_metric", "symmetry")
            set_value("searchsymmetry", "average")
            set_value("derivesymmetry", "yes")
            set_value("resolution_d_min", "0.0")
            set_value("normalize", "atoms")
            set_value("nresshells", "100")
            set_value("missing", "bound 0.5 2.5")
            set_value("electrons", "")
            set_value("plimit_superflip", "0.5")
            set_value("plimit_deblur", "0.5")
            set_value("map_export_format", "xplor")
        elif "atomic" in name:
            set_value("reflection_data_mode", format_reflection_data_mode(REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA))
            set_value("modelfile_source", "deblurred_xplor")
            set_value("plimit_superflip", "3.0")
            set_value("plimit_deblur", "3.0")
            set_value("resolution_d_min", "0.9")
            set_value("bestdensities_metric", "symmetry")
            set_value("map_export_format", "jana")
        elif "medium" in name:
            set_value("reflection_data_mode", format_reflection_data_mode(REFLECTION_DATA_MODE_AUTO))
            set_value("modelfile_source", "deblurred_edma_cif")
            set_value("plimit_superflip", "0.5")
            set_value("plimit_deblur", "0.5")
            set_value("resolution_d_min", "0.0")
        elif "small" in name:
            set_value("reflection_data_mode", format_reflection_data_mode(REFLECTION_DATA_MODE_INTENSITY))
            set_value("modelfile_source", "deblurred_edma_cif")
            set_value("plimit_superflip", "0.5")
            set_value("plimit_deblur", "0.5")
            set_value("bestdensities_metric", "rvalue")
        elif "inorganic" in name:
            set_value("reflection_data_mode", format_reflection_data_mode(REFLECTION_DATA_MODE_AUTO))
            set_value("modelfile_source", "deblurred_edma_cif")
            set_value("plimit_superflip", "1.0")
            set_value("plimit_deblur", "1.0")
            set_value("bestdensities_metric", "symmetry")
        self._sync_workflow_widgets()
        self._sync_map_feedback_widgets()
        self._sync_normalization_widgets()

    def _open_configuration_page(self, name: str, *, advanced: bool = False) -> None:
        self.category_tabs.setCurrentIndex(1 if advanced else 0)
        tabs = self.advanced_tabs if advanced else self.basic_tabs
        for index in range(tabs.count()):
            if tabs.tabText(index) == name:
                tabs.setCurrentIndex(index)
                break

    def _error_actions(self, report: ErrorReport) -> List[ErrorAction]:
        category = report.category
        if category == "reference_missing":
            row = self.inputs.get("reference_cif")
            actions: List[ErrorAction] = []
            if isinstance(row, PathRow):
                actions.append(ErrorAction("Select file…", row.browse, True))
            actions.append(ErrorAction("Use Manual metadata", lambda: self._set_metadata_source(METADATA_SOURCE_MANUAL)))
            return actions
        if category == "hkl_missing":
            row = self.inputs.get("hkl")
            return [ErrorAction("Select HKL…", row.browse, True)] if isinstance(row, PathRow) else []
        if category == "superflip_missing":
            row = self.inputs.get("superflip_exe")
            return [ErrorAction("Locate Superflip…", row.browse, True)] if isinstance(row, PathRow) else []
        if category == "edma_missing":
            row = self.inputs.get("edma_exe")
            return [ErrorAction("Locate EDMA…", row.browse, True)] if isinstance(row, PathRow) else []
        if category in {"file_permission", "file_write"}:
            row = self.inputs.get("work_dir")
            return [ErrorAction("Choose folder…", row.browse, True)] if isinstance(row, PathRow) else []
        if category == "sharped_authentication":
            return [ErrorAction("Open SharpED settings", lambda: self._open_configuration_page("Setup", advanced=True), True)]
        if category.startswith("sharped_"):
            return [ErrorAction("Open SharpED settings", lambda: self._open_configuration_page("SharpED", advanced=True), True)]
        if category == "input_validation":
            actions = [ErrorAction("Open Input", lambda: self._open_configuration_page("Input"), True)]
            if "SharpED" in report.summary:
                actions.append(ErrorAction("Open SharpED settings", lambda: self._open_configuration_page("Setup", advanced=True)))
            return actions
        if category in {"hkl_invalid", "metadata", "unit_cell", "space_group", "composition", "inflip"}:
            return [ErrorAction("Open Input", lambda: self._open_configuration_page("Input"), True)]
        return []

    def _show_error_report(self, report: ErrorReport, *, write_log: bool = True) -> str:
        if write_log and hasattr(self, "log_text"):
            # The concise line is enough for the normal workflow log; the full
            # diagnostic (including any traceback) is not duplicated here -- it
            # stays fully available via the error dialog's "Show details".
            self._append_execution_log(report.title + ".", level="ERROR", subsystem=report.subsystem)
        return show_phase_studio_error(self, report, self._error_actions(report))

    def _handle_pipeline_error(self, report: ErrorReport) -> None:
        cancelled = report.category == "cancelled"
        if cancelled:
            self._finish_cancelled_run()
            return
        self.worker = None
        self.stop_after_cycle.clear()
        self.stop_now.clear()
        self._set_run_status("Error")
        if self.progress_bar.minimum() == 0 and self.progress_bar.maximum() == 0:
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(0)
        self._set_overall_progress_text("Error")
        self._set_terminal_cycle_state("Error")
        self.run_btn.setText("Run phasing")
        self._update_action_states()
        self._show_error_report(report)

    def _poll_queue(self) -> None:
        try:
            processed = 0
            while processed < 250:
                kind, payload = self.msg_queue.get_nowait()
                processed += 1
                hkl_task_id: Optional[int] = None
                if kind.startswith("hkl_") and isinstance(payload, tuple) and len(payload) == 2 and isinstance(payload[0], int):
                    hkl_task_id, payload = payload
                    if hkl_task_id != self._active_hkl_task_id:
                        continue
                    if kind != "hkl_task_finished":
                        if hkl_task_id in self._completed_hkl_task_ids:
                            continue
                        self._completed_hkl_task_ids.add(hkl_task_id)
                if kind == "log":
                    self._append_execution_log(payload)
                    self._update_action_states()
                elif kind == "result":
                    result = payload  # type: ignore[assignment]
                    self.results.append(result)  # type: ignore[arg-type]
                    self.superflip_atoms_for_plot = self._safe_parse_structure(result.superflip_edma_cif)  # type: ignore[attr-defined]
                    self.deblur_atoms_for_plot = self._safe_parse_structure(result.deblur_edma_cif)  # type: ignore[attr-defined]
                    self._update_plot()
                    self._update_structure_views()
                elif kind == "structure_update":
                    panel, cif_path = payload  # type: ignore[misc]
                    atoms = self._safe_parse_structure(Path(cif_path))
                    if str(panel) == "superflip":
                        self.superflip_atoms_for_plot = atoms
                    elif str(panel) == "deblur":
                        self.deblur_atoms_for_plot = atoms
                    self._update_structure_views()
                elif kind == "reference_atoms":
                    self.reference_atoms_for_plot = list(payload)  # type: ignore[arg-type]
                    self._update_structure_views()
                elif kind == "structure_cell":
                    values = tuple(float(value) for value in payload)  # type: ignore[arg-type]
                    if len(values) == 6 and min(values[:3]) > 0:
                        self.structure_cell = gemmi.UnitCell(*values)
                        self._update_structure_views()
                elif kind == "sharped_models":
                    default_model, models = payload  # type: ignore[misc]
                    widget = self.inputs.get("sharped_model")
                    if isinstance(widget, QComboBox):
                        current = widget.currentText().strip() or "default"
                        widget.blockSignals(True)
                        widget.clear()
                        values = ["default"]
                        if default_model:
                            values.append(str(default_model))
                        for model in list(models):
                            if model not in values:
                                values.append(model)
                        widget.addItems(values)
                        idx = widget.findText(current)
                        widget.setCurrentIndex(idx if idx >= 0 else 0)
                        widget.blockSignals(False)
                    self._append_execution_log("[SharpED] Models refreshed.", level="SUCCESS", subsystem="SharpED")
                elif kind == "hkl_load_result":
                    parsed_count = len(payload.reflections) if isinstance(payload, HklLoadResult) else 0
                    unique_count = len(payload.unique_reflections) if isinstance(payload, HklLoadResult) else 0
                    self._append_execution_log(
                        f"[HKL] Validation completed · {parsed_count:,} parsed / {unique_count:,} unique",
                        level="SUCCESS",
                        subsystem="HKL",
                    )
                    self._set_hkl_task_running(False)
                    self._show_hkl_load_result_dialog(payload)
                elif kind == "hkl_completeness_result":
                    resolution = format_resolution_d(payload.d_min) if isinstance(payload, HklAnalysis) else "n/a"
                    self._append_execution_log(
                        f"[HKL] Completeness analysis completed · d_min {resolution}",
                        level="SUCCESS",
                        subsystem="HKL",
                    )
                    self._set_hkl_task_running(False)
                    self._show_hkl_completeness_dialog(payload)  # type: ignore[arg-type]
                elif kind == "hkl_task_error":
                    self._set_hkl_task_running(False)
                    report = payload if isinstance(payload, ErrorReport) else build_error_report(payload, subsystem="HKL", operation="HKL analysis")
                    self._show_error_report(report)
                elif kind == "hkl_task_finished":
                    if hkl_task_id is not None:
                        self._active_hkl_task_id = None
                        self.hkl_task_worker = None
                    self._set_hkl_task_running(False)
                elif kind == "handoff_done":
                    self._set_run_status("Transferred")
                    self._append_execution_log(
                        "Jana2020 handoff completed. Phase Studio will close automatically.",
                        level="SUCCESS",
                        subsystem="Jana2020",
                    )
                    self.handoff_btn.setEnabled(False)
                    QTimer.singleShot(400, QApplication.instance().quit)
                elif kind == "handoff_error":
                    self._set_run_status("Error")
                    report = payload if isinstance(payload, ErrorReport) else build_error_report(payload, subsystem="Jana2020", operation="Jana2020 handoff")
                    self._show_error_report(report)
                    self.handoff_btn.setEnabled(bool(self.results and self.last_run_config and self.last_run_config.jana_inflip is not None))
                elif kind == "progress_setup":
                    self._set_run_status("Running")
                    total = max(1, int(payload))
                    self.progress_bar.setRange(0, total)
                    self.progress_bar.setValue(0)
                    self._set_overall_progress_text("Running")
                    self.current_cycle_progress.setRange(0, 0)
                    self.current_cycle_detail.setText(f"Cycle 1 of {total} · Preparing cycle")
                    self.current_cycle_stage_counter.setText("Preparing")
                    self._apply_superflip_repeat_state(None)
                elif kind == "cycle_progress":
                    self._apply_cycle_progress_state(payload)  # type: ignore[arg-type]
                elif kind == "progress":
                    value = int(payload)
                    self.progress_bar.setValue(value)
                    self._set_overall_progress_text("Running")
                elif kind == "error":
                    report = payload if isinstance(payload, ErrorReport) else build_error_report(payload, operation="Run pipeline")
                    self._handle_pipeline_error(report)
                elif kind == "error_report":
                    report = payload if isinstance(payload, ErrorReport) else build_error_report(payload, operation="Run pipeline")
                    self._handle_pipeline_error(report)
                elif kind == "cancelled":
                    self._finish_cancelled_run()
                elif kind == "done":
                    self.worker = None
                    self.stop_after_cycle.clear()
                    self.stop_now.clear()
                    self._set_run_status("Complete")
                    self._append_execution_log("=== Pipeline complete ===", level="SUCCESS")
                    if payload is not None:
                        self.progress_bar.setValue(int(payload))
                    self._set_overall_progress_text("Complete")
                    if self._cycle_progress_state is None:
                        self.current_cycle_detail.setText("Pipeline complete")
                        self.current_cycle_stage_counter.setText("Completed")
                    self.run_btn.setEnabled(True)
                    self.run_btn.setText("Run phasing")
                    self._sync_jana_action_button()
                    # Auto-opening the result selector is Jana-Wizard-owned
                    # functionality: a standalone session that happens to
                    # load a Jana2020 .inflip manually must never trigger it
                    # (spec: only a session actually launched from the
                    # Wizard -- either Full configuration or Phase recycling
                    # -- is eligible).
                    if self._jana_wizard_handoff_available():
                        if self.jana_wizard_context.launch_mode == "phase_recycling":
                            self._append_execution_log(
                                "Phase recycling complete. Opening the Jana2020 result selector automatically.",
                                subsystem="Jana2020",
                            )
                            self.open_jana_result_selector(
                                source_mode="locked",
                                initial_source=self.jana_wizard_context.wizard_map_source or "deblurred",
                            )
                        else:
                            self._append_execution_log(
                                "[Jana2020] Hand-off ready · select Superflip or SharpED result",
                                subsystem="Jana2020",
                            )
        except queue.Empty:
            pass

    def _source_map_path(self, result: CycleResult, source: str) -> Path:
        return Path(result.superflip_map) if source == "superflip" else Path(result.deblur_map)

    def _source_structure_path(self, result: CycleResult, source: str) -> Path:
        return Path(result.superflip_edma_cif) if source == "superflip" else Path(result.deblur_edma_cif)

    def _source_available_for_results(self, source: str) -> bool:
        return any(self._source_map_path(r, source).is_file() for r in self.results)

    def _default_handoff_source(self) -> str:
        # No Wizard choice exists for a Full-configuration hand-off -- default
        # to SharpED (typically the more refined final result) when it was
        # actually produced, else Superflip (always present in the standard
        # workflow).
        if self._source_available_for_results("deblurred"):
            return "deblurred"
        return "superflip"

    def open_jana_result_selector(self, source_mode: str, initial_source: str) -> None:
        """One shared Jana2020 result selector reused by both Jana-Wizard
        launch contexts that reach this main window:

        - source_mode="locked": Wizard Phase recycling. The map source was
          already chosen in the Wizard (jana_wizard_context.wizard_map_source)
          and is shown read-only, with no switch offered.
        - source_mode="switchable": Wizard "Open full configuration". The
          user interactively switches between Superflip and SharpED.
          Switching is presentation only: it never reruns Superflip, SharpED,
          EDMA, FFT, OMIT, R_free, RMSD or any other metric -- it only
          changes which existing CycleResult fields are displayed and which
          map/structure paths are used for the preview and hand-off.

        Both modes hand off through the exact same perform_jana_handoff()
        used before; this method only changes presentation."""
        cfg = self.last_run_config
        if cfg is None or cfg.jana_inflip is None:
            self._show_error_report(
                build_error_report(
                    RuntimeError("Jana2020 handoff requires a run started from a Jana2020 .inflip file."),
                    subsystem="Jana2020",
                    operation="Jana2020 handoff",
                    severity="warning",
                )
            )
            return
        if not self.results:
            self._show_error_report(
                build_error_report(
                    RuntimeError("No completed cycle is available for Jana2020 handoff."),
                    subsystem="Jana2020",
                    operation="Jana2020 handoff",
                    severity="warning",
                )
            )
            return

        switchable = source_mode == "switchable"
        superflip_ok = self._source_available_for_results("superflip")
        sharped_ok = self._source_available_for_results("deblurred")
        wants_superflip = str(initial_source or "").strip().lower() == "superflip"
        if wants_superflip and not superflip_ok and sharped_ok:
            initial_source = "deblurred"
        elif not wants_superflip and not sharped_ok and superflip_ok:
            initial_source = "superflip"
        state: Dict[str, object] = {"source": initial_source, "cycle": None}

        def fmt(value: object) -> str:
            if value is None:
                return "n/a"
            try:
                value_f = float(value)
                if not np.isfinite(value_f):
                    return "n/a"
                return f"{value_f:.3f}"
            except Exception:
                return str(value) if str(value) else "n/a"

        def fmt_count(value: object) -> str:
            if value is None:
                return "n/a"
            try:
                return f"{int(round(float(value))):,}"
            except (TypeError, ValueError):
                return "n/a"

        def col_available(getter) -> bool:
            return any(getter(r) not in (None, "") for r in self.results)

        class _PreviewHost:
            """Reuses IterativeSuperflipPipelineQtGUI's own atom/cell/depth-cue
            rendering and rotation-drag methods -- unchanged, on a disposable
            object -- so this preview looks and behaves exactly like the main
            Structure Comparison view without touching the main window's own
            rendering state. Created once for the whole dialog (not per
            source-switch rebuild) so rotation survives a source switch."""

            _structure_cartesian_geometry = IterativeSuperflipPipelineQtGUI._structure_cartesian_geometry
            _element_color = IterativeSuperflipPipelineQtGUI._element_color
            _plot_structure_atoms = IterativeSuperflipPipelineQtGUI._plot_structure_atoms
            _update_structure_depth_artist = IterativeSuperflipPipelineQtGUI._update_structure_depth_artist
            _update_structure_depth_cue = IterativeSuperflipPipelineQtGUI._update_structure_depth_cue
            _begin_structure_rotation = IterativeSuperflipPipelineQtGUI._begin_structure_rotation
            _apply_structure_rotation = IterativeSuperflipPipelineQtGUI._apply_structure_rotation
            _sync_structure_view_from_event = IterativeSuperflipPipelineQtGUI._sync_structure_view_from_event
            _finish_structure_rotation = IterativeSuperflipPipelineQtGUI._finish_structure_rotation

            def __init__(self, cell, elev: float, azim: float) -> None:
                self.structure_cell = cell
                self.structure_elev = elev
                self.structure_azim = azim
                self._structure_depth_artists: List[StructureDepthArtists] = []
                self.structure_axes: List[object] = []
                self._structure_rotation_source = None
                self.structure_canvas = None

        preview_host = _PreviewHost(self.structure_cell, self.structure_elev, self.structure_azim)

        dialog = QDialog(self)
        dialog.setWindowTitle("Jana2020 result selection")
        # Content-aware target size, capped to the available screen: a
        # single-cycle, no-reference run doesn't need the same window as a
        # multi-cycle, fully-ranked, reference-compared one. Computed once
        # up front rather than per source-switch -- switching source changes
        # column count modestly but not enough to justify visibly resizing
        # an already-open dialog under the user's cursor.
        reference_available_hint = bool(self.reference_atoms_for_plot)
        if len(self.results) <= 1 and not reference_available_hint:
            preferred_width, preferred_height = 1150, 680
        else:
            preferred_width, preferred_height = 1400, 800
        preferred_height = min(preferred_height + max(0, len(self.results) - 5) * 12, preferred_height + 150)
        apply_safe_dialog_geometry(dialog, preferred_width, preferred_height)
        outer_layout = QVBoxLayout(dialog)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Same branded header + navy context banner as the main window and the
        # Jana2020 Wizard, so this reads as the same application rather than a
        # generic Qt dialog -- identical for both source_mode values.
        outer_layout.addWidget(create_phase_studio_brand_header())
        outer_layout.addWidget(create_phase_studio_context_banner(
            "JANA2020 RESULT SELECTION", "Compare completed cycles and select a map for handoff"
        ))

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(14, 10, 14, 14)
        content_layout.setSpacing(10)
        outer_layout.addWidget(content, 1)

        # --- Result source: a switchable Superflip/SharpED segmented control
        # for Full configuration, or a read-only label for the Wizard's own
        # Phase-recycling choice (spec sections 14-16, 34-35). ---
        source_row = QHBoxLayout()
        source_row.setSpacing(8)
        source_heading = QLabel("Result source")
        source_row.addWidget(source_heading)
        superflip_btn: Optional[QPushButton] = None
        sharped_btn: Optional[QPushButton] = None
        locked_source_value_label: Optional[QLabel] = None
        if switchable:
            superflip_btn = QPushButton("Superflip")
            sharped_btn = QPushButton("SharpED")
            for btn in (superflip_btn, sharped_btn):
                btn.setObjectName("metricsViewToggle")
                btn.setCheckable(True)
                btn.setCursor(Qt.PointingHandCursor)
            source_group = QButtonGroup(dialog)
            source_group.setExclusive(True)
            source_group.addButton(superflip_btn)
            source_group.addButton(sharped_btn)
            superflip_btn.setEnabled(superflip_ok)
            sharped_btn.setEnabled(sharped_ok)
            if not superflip_ok:
                superflip_btn.setToolTip("No Superflip map is available for the completed cycles.")
            if not sharped_ok:
                sharped_btn.setToolTip("No SharpED map is available for the completed cycles.")
            source_row.addWidget(superflip_btn)
            source_row.addWidget(sharped_btn)
        else:
            locked_source_value_label = QLabel(result_map_label(str(state["source"])))
            locked_font = locked_source_value_label.font()
            locked_font.setBold(True)
            locked_source_value_label.setFont(locked_font)
            source_row.addWidget(locked_source_value_label)
        source_row.addStretch(1)
        content_layout.addLayout(source_row)
        if not switchable:
            wizard_note = QLabel("Result source was selected in the Jana2020 Wizard.")
            wizard_note.setStyleSheet("color: #7183a6; font-style: italic;")
            content_layout.addWidget(wizard_note)

        summary_form = QFormLayout()
        summary_form.setContentsMargins(0, 0, 0, 0)
        summary_form.setHorizontalSpacing(18)
        summary_form.setVerticalSpacing(2)
        summary_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        content_layout.addLayout(summary_form)

        content_layout.addWidget(QLabel("Select a completed cycle for Jana2020 handoff."))

        availability_note = QLabel("")
        availability_note.setObjectName("janaSourceAvailabilityNote")
        availability_note.setStyleSheet("color: #b3261e; font-weight: 600;")
        availability_note.setWordWrap(True)
        availability_note.setVisible(False)
        content_layout.addWidget(availability_note)

        table_section_label = QLabel("CANDIDATE CYCLES")
        table_section_label.setObjectName("sectionLabel")
        content_layout.addWidget(table_section_label)

        body_holder = QWidget()
        body_layout = QVBoxLayout(body_holder)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(6)
        content_layout.addWidget(body_holder, 1)

        button_row = QHBoxLayout()
        close_btn = QPushButton("Return to Phase Studio")
        send_btn = QPushButton("Send to Jana2020")
        send_btn.setObjectName("primaryButton")
        button_row.addWidget(close_btn)
        button_row.addStretch(1)
        button_row.addWidget(send_btn)
        content_layout.addLayout(button_row)
        close_btn.clicked.connect(dialog.reject)
        send_btn.clicked.connect(dialog.accept)

        current_result_ref: Dict[str, Optional[CycleResult]] = {"result": None}

        def rebuild(map_source: str) -> None:
            state["source"] = map_source
            if switchable:
                superflip_btn.setChecked(map_source == "superflip")
                sharped_btn.setChecked(map_source != "superflip")
            else:
                locked_source_value_label.setText(result_map_label(map_source))

            while body_layout.count():
                child = body_layout.takeAt(0)
                widget = child.widget()
                if widget is not None:
                    # Detach immediately (not just deleteLater) so a stray
                    # findChild(QTableWidget) mid-switch -- in tests or any
                    # other introspection -- can never see the outgoing table.
                    widget.setParent(None)
                    widget.deleteLater()

            source_title = result_source_title(map_source)

            if map_source == "superflip":
                candidate_columns = [
                    ("Saved run", lambda r: r.superflip_saved_run, lambda v: "n/a" if v is None else str(int(v))),
                    ("R value", lambda r: r.superflip_rvalue, fmt),
                    ("Peakiness", lambda r: r.superflip_peaks, fmt),
                    ("Symmetry", lambda r: r.superflip_symm, fmt),
                    ("Derived SG", lambda r: (r.superflip_derived_sg or None), lambda v: v or "n/a"),
                    ("Ref. match", lambda r: r.superflip_ref_match, fmt),
                    ("FoM / Score", lambda r: r.superflip_fom, fmt),
                    ("Success rate %", lambda r: r.superflip_success_rate, fmt),
                    ("Mean cycles", lambda r: r.superflip_mean_cycles, fmt),
                    ("Recall", lambda r: r.superflip_recall, fmt),
                    ("Precision", lambda r: r.superflip_precision, fmt),
                    ("Heavy atoms", lambda r: r.superflip_heavy_atom_count, fmt_count),
                ]
                rfree_getter = lambda r: r.omit_superflip_rfree
                omit_getter = lambda r: r.omit_superflip_correlation
                rmsd_getter = lambda r: r.superflip_metric
            else:
                # Deliberately excludes Superflip-only fields (R value,
                # Peakiness, Symmetry, Derived SG) -- they describe the
                # Superflip map, not the SharpED-processed one this table
                # represents.
                candidate_columns = [
                    ("Recall", lambda r: r.deblur_recall, fmt),
                    ("Precision", lambda r: r.deblur_precision, fmt),
                    ("Heavy atoms", lambda r: r.deblur_heavy_atom_count, fmt_count),
                    ("Map correlation", lambda r: r.recycle_map_correlation, fmt),
                ]
                rfree_getter = lambda r: r.omit_deblur_rfree
                omit_getter = lambda r: r.omit_deblur_correlation
                rmsd_getter = lambda r: r.deblur_metric

            # --- Selection score: rank-based normalization of whichever of
            # R_free (lower better), OMIT correlation (higher better) and
            # RMSD (lower better) are actually populated for THIS source.
            # UI sorting aid only -- never written back into any CycleResult,
            # metrics.csv or hand-off, and switching source recomputes this
            # display-only ranking from the existing values, never a metric.
            def rank_normalize(values: List[Optional[float]], higher_is_better: bool) -> List[Optional[float]]:
                pairs = [(i, float(v)) for i, v in enumerate(values) if v is not None and np.isfinite(float(v))]
                normalized: List[Optional[float]] = [None] * len(values)
                if not pairs:
                    return normalized
                if len(pairs) == 1:
                    normalized[pairs[0][0]] = 0.0
                    return normalized
                ordered = sorted(pairs, key=lambda p: p[1], reverse=higher_is_better)
                n = len(ordered)
                i = 0
                while i < n:
                    j = i
                    while j + 1 < n and ordered[j + 1][1] == ordered[i][1]:
                        j += 1
                    average_rank = (i + j) / 2.0
                    for k in range(i, j + 1):
                        normalized[ordered[k][0]] = average_rank / (n - 1)
                    i = j + 1
                return normalized

            rfree_values = [rfree_getter(r) for r in self.results]
            omit_values = [omit_getter(r) for r in self.results]
            rmsd_values = [rmsd_getter(r) for r in self.results]
            rfree_available = any(v is not None for v in rfree_values)
            omit_available = any(v is not None for v in omit_values)
            rmsd_available = any(v is not None for v in rmsd_values)

            ranking_columns = []
            normalized_dims: List[Tuple[str, List[Optional[float]]]] = []
            if rfree_available:
                ranking_columns.append(("R_free", rfree_getter, fmt))
                normalized_dims.append(("R_free", rank_normalize(rfree_values, higher_is_better=False)))
            if omit_available:
                ranking_columns.append(("OMIT correlation", omit_getter, fmt))
                normalized_dims.append(("OMIT correlation", rank_normalize(omit_values, higher_is_better=True)))
            if rmsd_available:
                ranking_columns.append(("RMSD (Å)", rmsd_getter, fmt))
                normalized_dims.append(("RMSD", rank_normalize(rmsd_values, higher_is_better=False)))

            scores: List[Optional[float]] = []
            for idx in range(len(self.results)):
                valid = [normalized[idx] for _name, normalized in normalized_dims if normalized[idx] is not None]
                scores.append(sum(valid) / len(valid) if valid else None)
            ranking_active = any(s is not None for s in scores)

            if ranking_active:
                order = sorted(
                    range(len(self.results)),
                    key=lambda i: (scores[i] is None, scores[i] if scores[i] is not None else 0.0, i),
                )
                # Standard competition ranking: equal scores share the same
                # Rank (1, 1, 3 -- not 1, 1, 2).
                rank_numbers: dict = {}
                position = 0
                previous_score: Optional[float] = None
                current_rank = 0
                for i in order:
                    if scores[i] is None:
                        continue
                    position += 1
                    if previous_score is None or scores[i] != previous_score:
                        current_rank = position
                        previous_score = scores[i]
                    rank_numbers[i] = current_rank
            else:
                order = list(range(len(self.results)))
                rank_numbers = {}

            columns = [(h, g, f) for (h, g, f) in candidate_columns if col_available(g)]
            headers: List[str] = (["Rank", "Cycle", "Selection score"] if ranking_active else ["Cycle"])
            headers += [h for h, _g, _f in ranking_columns]
            headers += [h for h, _g, _f in columns]
            cycle_col_index = headers.index("Cycle")
            reference_available = bool(self.reference_atoms_for_plot)

            if normalized_dims:
                ranking_summary = " + ".join(name for name, _values in normalized_dims)
                if not rmsd_available and (rfree_available or omit_available):
                    ranking_summary += " (reference RMSD unavailable)"
            elif len(self.results) <= 1:
                ranking_summary = "Not applicable"
            else:
                ranking_summary = "Not available"

            while summary_form.rowCount():
                summary_form.removeRow(0)
            for label_text, value_text in (
                ("Completed cycles", str(len(self.results))),
                ("Ranking", ranking_summary),
                ("Reference", "Available" if reference_available else "Not available"),
            ):
                value_label = QLabel(value_text)
                value_font = value_label.font()
                value_font.setBold(True)
                value_label.setFont(value_font)
                summary_form.addRow(label_text, value_label)

            table = QTableWidget(len(self.results), len(headers))
            table.setObjectName("diagnosticTable")
            table.setHorizontalHeaderLabels(headers)
            table.setAlternatingRowColors(True)
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectRows)
            table.setSelectionMode(QAbstractItemView.SingleSelection)
            table.verticalHeader().setVisible(False)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
            table.horizontalHeader().setStretchLastSection(len(headers) <= 3)

            class _NumericTableWidgetItem(QTableWidgetItem):
                """Sorts by an explicit numeric/string key instead of Qt's
                default lexicographic text compare, so header-click sorting
                is correct for this table."""

                def __init__(self, text: str, sort_value: object) -> None:
                    super().__init__(text)
                    self._sort_value = sort_value

                def __lt__(self, other: object) -> bool:  # noqa: N802 - Qt override
                    other_value = getattr(other, "_sort_value", None)
                    if self._sort_value is None:
                        return False
                    if other_value is None:
                        return True
                    try:
                        return float(self._sort_value) < float(other_value)
                    except (TypeError, ValueError):
                        return str(self._sort_value) < str(other_value)

            def add_cell(display_row: int, col: int, text: str, sort_value: object, left_align: bool = False) -> "_NumericTableWidgetItem":
                item = _NumericTableWidgetItem(text, sort_value)
                item.setTextAlignment((Qt.AlignLeft if left_align else Qt.AlignRight) | Qt.AlignVCenter)
                table.setItem(display_row, col, item)
                return item

            # Without a validation ranking metric, no cycle is scientifically
            # "recommended" -- the first (chronologically earliest) cycle is
            # selected purely so a preview is shown, with no best/preferred
            # framing.
            initial_result_idx = order[0] if order else 0
            preserved_cycle = state.get("cycle")
            preserved_result_idx = None
            if preserved_cycle is not None:
                for idx, r in enumerate(self.results):
                    if int(r.cycle) == preserved_cycle:
                        preserved_result_idx = idx
                        break
            select_result_idx = preserved_result_idx if preserved_result_idx is not None else initial_result_idx

            for display_row, result_idx in enumerate(order):
                result = self.results[result_idx]
                col = 0
                if ranking_active:
                    rank = rank_numbers.get(result_idx)
                    add_cell(display_row, col, "n/a" if rank is None else str(rank), rank)
                    col += 1
                cycle_item = add_cell(display_row, col, str(int(result.cycle)), int(result.cycle))
                cycle_item.setData(Qt.UserRole, int(result.cycle))
                if ranking_active and result_idx == initial_result_idx:
                    cycle_item.setToolTip("Best-ranked cycle (lowest Selection score).")
                col += 1
                if ranking_active:
                    score = scores[result_idx]
                    add_cell(display_row, col, fmt(score), score)
                    col += 1
                for _header, getter, formatter in ranking_columns:
                    value = getter(result)
                    add_cell(display_row, col, formatter(value), value)
                    col += 1
                for header, getter, formatter in columns:
                    value = getter(result)
                    add_cell(display_row, col, formatter(value), value, left_align=(header == "Derived SG"))
                    col += 1

            def result_for_table_row(row: int) -> Optional[CycleResult]:
                if row < 0:
                    return None
                item = table.item(row, cycle_col_index)
                if item is None:
                    return None
                cycle_id = item.data(Qt.UserRole)
                if cycle_id is None:
                    return None
                return next((r for r in self.results if int(r.cycle) == int(cycle_id)), None)

            preview_figure = Figure(figsize=(6.0, 3.4), dpi=100)
            preview_canvas = FigureCanvas(preview_figure)
            preview_canvas.setObjectName("janaResultPreviewCanvas")
            preview_canvas.setMinimumHeight(260)
            preview_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            preview_canvas.setToolTip("")
            preview_host.structure_canvas = preview_canvas

            def preview_atoms_for(result: CycleResult) -> List[AtomSite]:
                return self._safe_parse_structure(self._source_structure_path(result, map_source))

            def render_preview(result: CycleResult) -> None:
                current_result_ref["result"] = result
                state["cycle"] = int(result.cycle)
                has_map = self._source_map_path(result, map_source).is_file()
                if has_map:
                    availability_note.setVisible(False)
                else:
                    extra = " Choose another cycle, or switch source." if switchable else " Choose another cycle."
                    availability_note.setText(f"No {source_title} map is available for cycle {int(result.cycle)}.{extra}")
                    availability_note.setVisible(True)
                send_btn.setEnabled(has_map)

                preview_figure.clear()
                preview_figure.patch.set_facecolor("#ffffff")
                preview_host.structure_axes = []
                preview_host._structure_depth_artists = []
                panels = [(
                    f"{source_title} · Cycle {int(result.cycle)}",
                    preview_atoms_for(result),
                    "Structure preview unavailable for this cycle",
                )]
                if reference_available:
                    panels.append(("Reference", self.reference_atoms_for_plot, "Reference structure unavailable"))
                # With no atomic reference, a full second pane would just show
                # "Reference structure unavailable" -- give the selected
                # result the whole viewer instead of wasting half of it.
                column_count = len(panels)
                x_positions = (0.5,) if column_count == 1 else (0.25, 0.75)
                metadata = []
                for idx, (_title, atoms, empty_text) in enumerate(panels, start=1):
                    ax = preview_figure.add_subplot(1, column_count, idx, projection="3d")
                    preview_host.structure_axes.append(ax)
                    metadata.append(preview_host._plot_structure_atoms(ax, atoms, empty_text))
                for x_position, (title, _atoms, _empty_text) in zip(x_positions, panels):
                    preview_figure.text(
                        x_position, 0.96, title, ha="center", va="center",
                        fontsize=10, fontweight="bold", color="#001170",
                    )
                for x_position, meta in zip(x_positions, metadata):
                    preview_figure.text(x_position, 0.03, meta, ha="center", va="center", fontsize=7.5, color="#52658b")
                if column_count > 1:
                    preview_figure.add_artist(Line2D(
                        [0.5, 0.5], [0.08, 0.90], transform=preview_figure.transFigure,
                        color="#cbd7ea", linewidth=0.45, alpha=0.62,
                    ))
                preview_figure.subplots_adjust(left=0.01, right=0.99, bottom=0.09, top=0.90, wspace=0.04)
                preview_canvas.draw_idle()

            preview_canvas.mpl_connect("button_press_event", preview_host._begin_structure_rotation)
            preview_canvas.mpl_connect("motion_notify_event", preview_host._sync_structure_view_from_event)
            preview_canvas.mpl_connect("button_release_event", preview_host._finish_structure_rotation)

            def on_selection_changed() -> None:
                result = result_for_table_row(table.currentRow())
                if result is not None:
                    render_preview(result)

            table.itemSelectionChanged.connect(on_selection_changed)
            # Populate rows first, THEN enable sorting -- enabling it before
            # setItem() calls would let each insertion re-sort mid-population.
            # Cycle identity is resolved via Qt.UserRole (result_for_table_row),
            # never the visible row index, so header-click sorting stays correct.
            table.setSortingEnabled(True)
            # setSortingEnabled(True) itself immediately re-sorts existing rows
            # (descending, by column 0, by default) -- force a deterministic
            # ascending sort by column 0 (Rank when ranked, else Cycle) so the
            # already-built `order` sequence (best-first / chronological) is
            # what actually ends up on screen, not an arbitrary Qt default.
            table.sortItems(0, Qt.AscendingOrder)
            select_display_row = order.index(select_result_idx) if select_result_idx in order else 0
            table.selectRow(select_display_row)
            # selectRow() doesn't reliably fire itemSelectionChanged the very
            # first time a freshly (re)built table is populated -- render
            # explicitly so the preview is never blank after a rebuild.
            initial_result = result_for_table_row(select_display_row)
            if initial_result is not None:
                render_preview(initial_result)

            viewer_section = QWidget()
            viewer_section_layout = QVBoxLayout(viewer_section)
            viewer_section_layout.setContentsMargins(0, 0, 0, 0)
            viewer_section_layout.setSpacing(3)
            viewer_section_label = QLabel("STRUCTURE COMPARISON")
            viewer_section_label.setObjectName("sectionLabel")
            viewer_section_layout.addWidget(viewer_section_label)
            viewer_section_layout.addWidget(preview_canvas, 1)

            splitter = QSplitter(Qt.Horizontal)
            splitter.addWidget(table)
            splitter.addWidget(viewer_section)
            # A handful of columns doesn't need half the dialog; give the
            # table only as much width as its content plausibly needs and let
            # the structure viewer take the rest.
            table_share = 0.32 if len(headers) <= 3 else 0.55
            splitter_total = 1260
            splitter.setSizes([
                int(splitter_total * table_share), int(splitter_total * (1.0 - table_share))
            ])
            body_layout.addWidget(splitter, 1)

            if ranking_active:
                note_text = (
                    "Selection score combines available validation ranks -- R_free and OMIT correlation "
                    "(from the 5% reflection holdout) and RMSD (vs. a reference structure, if provided); "
                    "lower is better."
                )
            else:
                note_text = "No validation metric is available for ranking. Select a cycle manually."
            note = QLabel(note_text)
            note.setStyleSheet("color: #52658b;")
            note.setWordWrap(True)
            body_layout.addWidget(note)

        if switchable:
            superflip_btn.clicked.connect(lambda _checked=False: rebuild("superflip"))
            sharped_btn.clicked.connect(lambda _checked=False: rebuild("deblurred"))

        rebuild(str(state["source"]))

        if dialog.exec() != QDialog.Accepted:
            # Closing without sending keeps the main window and its completed
            # results exactly as they are; "Send to Jana2020" reopens this
            # same selector.
            return

        selected_result = current_result_ref["result"]
        if selected_result is None:
            return
        final_source = str(state["source"])
        if not self._source_map_path(selected_result, final_source).is_file():
            # Defensive: Send is disabled whenever this is true, but never
            # silently hand off the wrong source if it is somehow reached.
            return

        self.handoff_btn.setEnabled(False)
        self._append_execution_log(
            f"[Jana2020] Hand-off source · Cycle {int(selected_result.cycle):03d} · {result_map_label(final_source)}",
            level="STEP",
            subsystem="Jana2020",
        )

        def worker() -> None:
            try:
                perform_jana_handoff(cfg, selected_result, final_source, log=self.log)
                self.msg_queue.put(("handoff_done", None))
            except Exception as exc:
                self.msg_queue.put((
                    "handoff_error",
                    build_error_report(
                        exc,
                        subsystem="Jana2020",
                        operation="Jana2020 handoff",
                        extra_details=traceback.format_exc(),
                    ),
                ))

        threading.Thread(target=worker, daemon=True).start()

    def open_jana_handoff_dialog(self) -> None:
        """Entry point for the main window's "Send to Jana2020" button.
        Dispatches to the one shared open_jana_result_selector(): locked to
        the Wizard's own choice for a Phase-recycling session, switchable
        between Superflip/SharpED for a Full-configuration session."""
        if self.jana_wizard_context.launch_mode == "phase_recycling":
            self.open_jana_result_selector(
                source_mode="locked",
                initial_source=self.jana_wizard_context.wizard_map_source or "deblurred",
            )
            return
        self.open_jana_result_selector(source_mode="switchable", initial_source=self._default_handoff_source())

    def open_install_to_jana_dialog(self) -> None:
        """Entry point for the main window's "Install to Jana2020" button
        (standalone launch only -- see _on_jana_action_clicked()).

        Manages the Phase Studio -> Jana2020\\SUPERFLIP integration: detect,
        install, update, repair, remove. Every file operation is delegated
        to phase_studio.jana_integration (transactional, independently
        tested); this method is presentation only and never modifies
        anything just by being opened -- only the explicit "Install
        integration"/"Update integration"/"Repair"/"Remove integration"
        buttons do."""
        from phase_studio import jana_integration as ji

        dialog = QDialog(self)
        dialog.setWindowTitle("Jana2020 Integration")
        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(create_phase_studio_brand_header())
        outer.addWidget(create_phase_studio_context_banner(
            "JANA2020 INTEGRATION",
            "Install the Phase Studio workflow launcher into Jana2020",
        ))

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(14, 10, 14, 10)
        content_layout.setSpacing(10)
        scroll_area.setWidget(content)
        outer.addWidget(scroll_area, 1)

        path_group = QGroupBox("Jana2020 Installation")
        path_group_layout = QVBoxLayout(path_group)
        path_row = QHBoxLayout()
        path_edit = QLineEdit()
        path_edit.setPlaceholderText(r"C:\Jana2020")
        path_edit.setReadOnly(True)
        browse_btn = QPushButton("Browse…")
        path_row.addWidget(path_edit, 1)
        path_row.addWidget(browse_btn)
        path_group_layout.addLayout(path_row)
        path_hint = QLabel("Select the Jana2020 root folder; Phase Studio looks for its SUPERFLIP subfolder.")
        path_hint.setWordWrap(True)
        path_hint.setStyleSheet("color: #52658b;")
        path_group_layout.addWidget(path_hint)
        content_layout.addWidget(path_group)

        status_group = QGroupBox("Detection Status")
        status_layout = QVBoxLayout(status_group)
        content_layout.addWidget(status_group)

        state_label = QLabel("")
        state_label.setObjectName("settingsCallout")
        state_label.setTextFormat(Qt.RichText)
        state_label.setWordWrap(True)
        content_layout.addWidget(state_label)

        explain_label = QLabel("")
        explain_label.setWordWrap(True)
        explain_label.setTextFormat(Qt.RichText)
        content_layout.addWidget(explain_label)

        signature_label = QLabel("")
        signature_label.setWordWrap(True)
        signature_label.setTextFormat(Qt.RichText)
        signature_label.setStyleSheet("color: #52658b;")
        content_layout.addWidget(signature_label)

        result_label = QLabel("")
        result_label.setWordWrap(True)
        result_label.setVisible(False)
        content_layout.addWidget(result_label)

        log_view = QTextEdit()
        log_view.setReadOnly(True)
        log_view.setVisible(False)
        log_view.setMaximumHeight(140)
        content_layout.addWidget(log_view)
        content_layout.addStretch(1)

        footer = QWidget()
        footer.setObjectName("wizardFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(14, 8, 14, 12)
        close_btn = QPushButton("Close")
        remove_btn = QPushButton("Remove integration")
        primary_btn = QPushButton("Install integration")
        primary_btn.setObjectName("primaryButton")
        # Disabled from construction, before the first refresh() has run --
        # never rely on Qt's default-enabled state for a button whose real
        # state depends on detecting a payload/writable directory first.
        remove_btn.setEnabled(False)
        primary_btn.setEnabled(False)
        footer_layout.addWidget(close_btn)
        footer_layout.addStretch(1)
        footer_layout.addWidget(remove_btn)
        footer_layout.addWidget(primary_btn)
        outer.addWidget(footer)

        state: Dict[str, object] = {"jana_root": None, "superflip_dir": None, "report": None, "install_state": ji.IntegrationState.NOT_INSTALLED}

        def resolve_initial_root() -> Optional[Path]:
            configured_paths = []
            for key in ("superflip_exe", "edma_exe"):
                text = self._path_value(key).strip() if key in self.inputs else ""
                if text:
                    configured_paths.append(Path(text))
            return ji.detect_jana_root(configured_paths)

        def clear_status_layout() -> None:
            while status_layout.count():
                child = status_layout.takeAt(0)
                widget = child.widget()
                if widget is not None:
                    widget.setParent(None)
                    widget.deleteLater()

        def status_row(ok: bool, text: str) -> QLabel:
            mark = "✓" if ok else "✗"
            color = "#2264b8" if ok else "#b42318"
            label = QLabel(f"<span style='color:{color};font-weight:600;'>{mark}</span>&nbsp;&nbsp;{html.escape(text)}")
            label.setTextFormat(Qt.RichText)
            return label

        def refresh(jana_root: Optional[Path]) -> None:
            state["jana_root"] = jana_root
            path_edit.setText(str(jana_root) if jana_root is not None else "")
            superflip_dir = ji.superflip_dir_for_root(jana_root) if jana_root is not None else None
            state["superflip_dir"] = superflip_dir
            report = ji.inspect_jana_superflip_dir(superflip_dir) if superflip_dir is not None else None
            state["report"] = report
            install_state = ji.classify_install_state(report, ji.bundled_integration_version()) if report is not None else ji.IntegrationState.NOT_INSTALLED
            state["install_state"] = install_state

            clear_status_layout()
            if report is None:
                status_layout.addWidget(status_row(False, "No Jana2020 installation selected."))
            else:
                status_layout.addWidget(status_row(report.exists, "SUPERFLIP directory detected"))
                status_layout.addWidget(status_row(report.has_original_exe or (report.has_superflip_exe and not report.has_marker), "Original Superflip detected"))
                status_layout.addWidget(status_row(report.has_edma_exe, "EDMA detected"))
                if not report.is_writable and report.exists:
                    status_layout.addWidget(status_row(False, "Directory is not writable with the current Windows permissions"))

            state_text = {
                ji.IntegrationState.NOT_INSTALLED: "Not installed",
                ji.IntegrationState.INSTALLED_CURRENT: f"Installed · version {ji.bundled_integration_version()}",
                ji.IntegrationState.UPDATE_AVAILABLE: f"Update available · installed {report.marker.version if report and report.marker else '?'}, bundled {ji.bundled_integration_version()}",
                ji.IntegrationState.REPAIR_REQUIRED: "Repair required",
                ji.IntegrationState.CONFLICT: "Conflict detected",
            }.get(install_state, "Not installed")
            state_label.setText(f"<b>Status:</b> {html.escape(state_text)}")

            if install_state == ji.IntegrationState.CONFLICT:
                explain_label.setText(
                    "<b>Existing Superflip backup detected.</b> Phase Studio did not modify this installation "
                    "because its ownership could not be verified. Nothing was changed."
                )
            elif install_state == ji.IntegrationState.NOT_INSTALLED:
                explain_label.setText(
                    "Phase Studio will:<br>"
                    "&bull; preserve the existing Superflip executable as <code>superflip_original.exe</code><br>"
                    "&bull; install the Phase Studio Jana2020 launcher as <code>superflip.exe</code><br>"
                    "&bull; install its required runtime files<br>"
                    "&bull; leave EDMA and all Jana2020 crystallographic data unchanged"
                )
            elif install_state == ji.IntegrationState.UPDATE_AVAILABLE:
                explain_label.setText("A newer Phase Studio Jana2020 launcher is available. Updating preserves the original Superflip executable and replaces only Phase-Studio-owned files.")
            elif install_state == ji.IntegrationState.REPAIR_REQUIRED:
                explain_label.setText("The Phase Studio integration is incomplete (a required file is missing). Repair replaces only Phase-Studio-owned files; the original Superflip executable is preserved.")
            else:
                explain_label.setText("The installed Phase Studio Jana2020 launcher is up to date.")

            payload_dir = ji.resolve_bundled_jana_payload_dir()
            if payload_dir is None:
                signature_label.setText(
                    "<b>Integration package: Not available</b><br>"
                    "The Jana2020 integration package is not available in this Phase Studio build."
                )
            else:
                sig = ji.authenticode_signature_status(payload_dir / ji.WRAPPER_EXE_NAME)
                sig_text = {"signed": "Signed", "unsigned": "Unsigned"}.get(sig, "Unknown")
                signature_label.setText(f"<b>Integration package: Ready</b><br>Wrapper signature: {sig_text}")

            can_write = report is not None and report.exists and report.is_writable
            primary_btn.setText({
                ji.IntegrationState.UPDATE_AVAILABLE: "Update integration",
                ji.IntegrationState.REPAIR_REQUIRED: "Repair integration",
                ji.IntegrationState.INSTALLED_CURRENT: "Repair integration",
            }.get(install_state, "Install integration"))
            primary_btn.setEnabled(can_write and install_state != ji.IntegrationState.CONFLICT and payload_dir is not None)

            # Remove is only ever safe when a verified Phase Studio marker
            # proves ownership of the installed integration AND a valid
            # (non-empty) original Superflip backup still exists to restore
            # -- not merely "some state other than not-installed/conflict",
            # since REPAIR_REQUIRED can itself mean the backup went missing.
            owns_installation = report is not None and report.has_marker and report.marker is not None
            original_backup_path = report.directory / ji.ORIGINAL_EXE_NAME if report is not None else None
            has_valid_backup = False
            if owns_installation and original_backup_path is not None:
                try:
                    has_valid_backup = original_backup_path.stat().st_size > 0
                except OSError:
                    has_valid_backup = False
            remove_btn.setEnabled(can_write and owns_installation and has_valid_backup)
            apply_safe_dialog_geometry(dialog, 640, 640)

        def browse_clicked() -> None:
            start_dir = str(state["jana_root"]) if state.get("jana_root") else r"C:\Jana2020"
            picked = QFileDialog.getExistingDirectory(dialog, "Select the Jana2020 installation folder", start_dir)
            if picked:
                refresh(Path(picked))

        def show_result(result: object, success_detail: str = "") -> None:
            result_label.setVisible(True)
            log_view.setVisible(bool(result.log))
            log_view.setPlainText("\n".join(result.log))
            if result.success:
                result_label.setStyleSheet("color: #2264b8;")
                text = f"<b>{html.escape(result.message)}</b>"
                if success_detail:
                    text += f"<br>{success_detail}"
                result_label.setText(text)
            else:
                result_label.setStyleSheet("color: #b42318;")
                result_label.setText(f"<b>{html.escape(result.message)}</b>")

        def install_clicked() -> None:
            superflip_dir = state.get("superflip_dir")
            if not superflip_dir:
                return
            # A failed (or unexpectedly raised) attempt must never leave the
            # dialog's buttons out of sync with the real on-disk state --
            # refresh() always runs in `finally`, whatever happened above.
            try:
                payload_dir = ji.resolve_bundled_jana_payload_dir()
                if payload_dir is None:
                    show_result(ji.OperationResult(False, "error", "Bundled Jana2020 integration payload was not found in this Phase Studio installation."))
                    return
                result = ji.install_or_update_integration(superflip_dir, payload_dir, bundled_version=ji.bundled_integration_version())
                success_detail = ""
                if result.success:
                    success_detail = (
                        f"Jana2020:<br>{html.escape(str(state['jana_root']))}<br><br>"
                        f"Original Superflip:<br>{html.escape(str(Path(superflip_dir) / ji.ORIGINAL_EXE_NAME))}<br><br>"
                        f"Phase Studio launcher:<br>{html.escape(str(Path(superflip_dir) / ji.WRAPPER_EXE_NAME))}"
                    )
                show_result(result, success_detail)
            finally:
                refresh(state["jana_root"])

        def remove_clicked() -> None:
            superflip_dir = state.get("superflip_dir")
            if not superflip_dir:
                return
            confirmation = QMessageBox.question(
                dialog,
                "Remove Jana2020 Integration",
                "Restore the original Superflip executable and remove the Phase Studio launcher?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if confirmation != QMessageBox.Yes:
                return
            try:
                result = ji.remove_integration(superflip_dir)
                show_result(result)
            finally:
                refresh(state["jana_root"])

        browse_btn.clicked.connect(browse_clicked)
        primary_btn.clicked.connect(install_clicked)
        remove_btn.clicked.connect(remove_clicked)
        close_btn.clicked.connect(dialog.reject)

        refresh(resolve_initial_root())
        apply_safe_dialog_geometry(dialog, 640, 640)
        dialog.exec()

    def _replay_metrics_tab(self, key: str) -> None:
        """Re-run the last _render_metrics_tab() call for this tab with its
        original series data, so a Reset view / Full range / Detail control
        (or a double-click reset) can update the displayed limits without
        waiting for the next data-driven refresh."""
        args = self._metrics_last_render_args.get(key)
        if args is None:
            return
        self._render_metrics_tab(key, args["series"], raw=args["raw"], raw_ylabel=args["raw_ylabel"])

    def _reset_metrics_view(self, key: Optional[str]) -> None:
        if key is None:
            return
        interaction = self.metrics_interactions.get(key)
        if interaction is not None:
            interaction.reset_view()

    def _set_metrics_view_mode(self, key: Optional[str], mode: str) -> None:
        if key is None:
            return
        interaction = self.metrics_interactions.get(key)
        if interaction is not None:
            interaction.set_mode(mode)

    def _current_metrics_key(self) -> Optional[str]:
        if not hasattr(self, "metrics_tabs"):
            return None
        index = self.metrics_tabs.currentIndex()
        if 0 <= index < len(self._metrics_tab_keys):
            return self._metrics_tab_keys[index]
        return None

    def _on_metrics_tab_changed(self, index: int) -> None:
        key = self._metrics_tab_keys[index] if 0 <= index < len(self._metrics_tab_keys) else None
        supports_detail = key in self._metrics_detail_supported_keys
        if hasattr(self, "metrics_full_range_btn"):
            self.metrics_full_range_btn.setVisible(supports_detail)
        if hasattr(self, "metrics_detail_btn"):
            self.metrics_detail_btn.setVisible(supports_detail)
        self._on_metrics_view_changed(key)

    def _on_metrics_view_changed(self, key: Optional[str]) -> None:
        # The control strip is shared/single, in the tab bar's corner, and
        # always reflects whichever tab is currently selected -- an
        # interaction change on a background tab (not realistically
        # reachable by the mouse, but defensive) must not touch it.
        if key is None or key != self._current_metrics_key():
            return
        interaction = self.metrics_interactions.get(key)
        if interaction is None:
            return
        in_manual = interaction.user_modified
        if hasattr(self, "metrics_detail_btn"):
            self.metrics_detail_btn.setEnabled(interaction.detail_available)
            self.metrics_detail_btn.setChecked(not in_manual and interaction.mode == "detail")
        if hasattr(self, "metrics_full_range_btn"):
            self.metrics_full_range_btn.setChecked(not in_manual and interaction.mode != "detail")
        if hasattr(self, "metrics_reset_btn"):
            self.metrics_reset_btn.setEnabled(interaction.user_modified or interaction.mode == "detail")

    def _layout_metrics_figure(self, key: str) -> None:
        figure = self.metrics_figures[key]
        canvas = self.metrics_canvases[key]
        width = max(1.0, float(canvas.width()))
        height = max(1.0, float(canvas.height()))
        has_data = bool(self.results)
        # A single-series tab (e.g. Powder repartitioning) omits its legend
        # entirely -- the y-axis label already names the one plotted metric
        # -- so it should reclaim the margin a legend would otherwise cost,
        # rather than leaving a wide empty band on the right.
        has_legend = has_data and bool(figure.legends)
        legend_gap_pixels = 8.0
        left_pixels = 86.0 if has_data else 70.0
        left = min(0.18, max(0.07, left_pixels / width))
        bottom = min(0.22, max(0.12, 34.0 / height))
        if has_data:
            top = 1.0 - min(0.08, max(0.035, 10.0 / height))
            if has_legend:
                # Reserve a compact, fixed-width band for the vertical legend.
                # Keeping this budget pixel based avoids wasting plot width on
                # large canvases while still fitting the longest label at
                # moderately narrow widths.
                legend_width_pixels = 112.0
                outer_right_pixels = 8.0
                right = 1.0 - min(
                    0.32,
                    (legend_width_pixels + legend_gap_pixels + outer_right_pixels) / width,
                )
            else:
                right = 1.0 - min(0.04, max(0.02, 18.0 / width))
        else:
            right = 1.0 - min(0.04, max(0.02, 18.0 / width))
            top = 1.0 - min(0.16, max(0.07, 22.0 / height))
        figure.subplots_adjust(left=left, right=right, bottom=bottom, top=top)
        if has_legend:
            legend_left = right + (legend_gap_pixels / width)
            legend_center_y = (bottom + top) / 2.0
            figure.legends[0].set_bbox_to_anchor(
                (legend_left, legend_center_y),
                transform=figure.transFigure,
            )

    def _render_metrics_tab(
        self,
        key: str,
        series: List[Tuple[str, List[Optional[float]], bool, str, str, str]],
        *,
        raw: bool = False,
        raw_ylabel: str = "",
    ) -> None:
        """Render one convergence tab. By default, each series is rescaled to a
        shared 0-1 "Best/Worst" score so metrics with unrelated units (RMSD,
        recall, reference match, ...) can be compared on one axis. Pass raw=True
        for a tab with a single metric already in one meaningful unit (for
        example a percentage), where that rescaling would hide whether the
        actual value is trending down/up and should instead be plotted as-is.

        Visualization only: the values plotted/shown here (and in hover
        tooltips) are exactly the stored CycleResult metrics or, for
        non-raw tabs, a display-only 0-1 rescaling of them for a shared axis
        -- nothing here recomputes or alters a scientific value."""
        self._metrics_last_render_args[key] = {"series": series, "raw": raw, "raw_ylabel": raw_ylabel}
        interaction = self.metrics_interactions.get(key)
        if interaction is not None:
            interaction.notify_redraw_start()
        figure = self.metrics_figures[key]
        canvas = self.metrics_canvases[key]
        figure.clear()
        ax = figure.add_subplot(111)
        self.metrics_axes[key] = ax
        figure.patch.set_facecolor("#ffffff")
        ax.set_facecolor("#ffffff")
        cycles = [r.cycle for r in self.results]
        if not cycles:
            self._metrics_hover_series[key] = []
            status = str(getattr(self, "_run_status", "READY")).upper()
            if status in {"RUNNING", "STOPPING"}:
                empty_message = "Waiting for reconstruction metrics…"
            elif status in {"ERROR", "CANCELLED"}:
                empty_message = "No reconstruction metrics available."
            else:
                empty_message = "Run phasing to display reconstruction metrics."
            ax.set_axis_off()
            ax.text(
                0.5,
                0.50,
                empty_message,
                ha="center",
                va="center",
                color="#7183a6",
                fontsize=8.5,
                transform=ax.transAxes,
            )
            self._layout_metrics_figure(key)
            canvas.draw_idle()
            return

        ax.set_title("")
        ax.set_xlabel("")
        figure.text(0.5, 0.018, "Cycle", ha="center", va="bottom", color="#14204a", fontsize=8.5)
        detail_ylim: Optional[Tuple[float, float]] = None
        if raw:
            all_finite = [
                float(v)
                for _label, values, *_rest in series
                for v in values
                if v is not None and np.isfinite(float(v))
            ]
            if all_finite:
                lo = min(0.0, min(all_finite))
                hi = max(all_finite)
                pad = max(1e-9, (hi - lo) * 0.08)
                full_ylim = (lo - pad, hi + pad)
                candidate_detail = robust_detail_range(all_finite)
                if candidate_detail is not None:
                    full_span = full_ylim[1] - full_ylim[0]
                    detail_span = candidate_detail[1] - candidate_detail[0]
                    # Only offer Detail when it would actually narrow the
                    # view meaningfully -- otherwise it's the same as Full
                    # range and just adds a confusing extra control.
                    if full_span > 0 and detail_span < full_span * 0.92:
                        detail_ylim = candidate_detail
            else:
                full_ylim = (0.0, 1.0)
            ax.set_ylabel(raw_ylabel, fontsize=7.5, color="#001170")
        else:
            full_ylim = (-0.04, 1.04)
            # Intermediate ticks stay at their numeric positions (0.25/0.5/0.75)
            # so the horizontal gridlines remain useful, but only the two
            # semantic endpoints get a label -- "Worst 0.00"/"Best 1.00" read
            # as redundant once the axis is understood as a quality scale.
            ax.set_yticks([0.0, 0.25, 0.5, 0.75, 1.0])
            ax.set_yticklabels(["Worst", "", "", "", "Best"])
            ax.set_ylabel("Normalized score", fontsize=7.5, color="#001170")
        try:
            cycles_to_run = max(1, self._spin_value("cycles"))
        except Exception:
            cycles_to_run = max(cycles) if cycles else 1
        max_completed = max(cycles) if cycles else 0
        run_status = str(getattr(self, "_run_status", "READY")).upper()
        if run_status in {"RUNNING", "STOPPING"}:
            # Live run: fit the currently populated cycles plus a little
            # right-side headroom for the next point, rather than jumping
            # straight to the full planned cycle count -- 12 of 50 planned
            # cycles otherwise compresses all the active data into the left
            # ~24% of the plot. Headroom grows with progress so the viewport
            # doesn't visibly jump every single cycle, and is capped at the
            # planned total.
            headroom = max(2, round(max_completed * 0.1))
            x_max = min(cycles_to_run, max(max_completed + headroom, 1))
        else:
            # Not currently running (finished, stopped early, or not yet
            # started): fit the data that actually exists instead of
            # stretching out to a planned count that will never be reached
            # for a run stopped before completion.
            x_max = max_completed if cycles else cycles_to_run
        full_xlim = (0.75, float(x_max) + 0.25)
        if interaction is not None and interaction.user_modified:
            # A manual zoom/pan may no longer align with one-tick-per-cycle;
            # let Matplotlib choose sensible ticks for whatever is visible.
            ax.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=10, min_n_ticks=2))
        elif x_max <= 30:
            ax.set_xticks(list(range(1, x_max + 1)))
        else:
            ax.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=12, min_n_ticks=2))
        ax.grid(True, axis="y", color="#cbd7ea", linewidth=0.6, alpha=0.64)
        ax.grid(True, axis="x", color="#cbd7ea", linewidth=0.5, alpha=0.42)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        ax.spines["left"].set_color("#001170")
        ax.spines["bottom"].set_color("#001170")
        ax.tick_params(colors="#001170")
        ax.title.set_color("#001170")
        ax.xaxis.label.set_color("#001170")
        ax.yaxis.label.set_color("#001170")

        def best_score(values: Sequence[Optional[float]], higher_is_better: bool) -> List[float]:
            arr = np.asarray([np.nan if v is None else float(v) for v in values], dtype=float)
            finite = np.isfinite(arr)
            out = np.full_like(arr, np.nan, dtype=float)
            if not np.any(finite):
                return out.tolist()
            lo = float(np.nanmin(arr[finite]))
            hi = float(np.nanmax(arr[finite]))
            if abs(hi - lo) < 1e-12:
                out[finite] = 1.0
            else:
                scaled = (arr[finite] - lo) / (hi - lo)
                out[finite] = scaled if higher_is_better else 1.0 - scaled
            return out.tolist()

        plotted = 0
        hover_series: List[Tuple[str, List[int], List[Optional[float]], List[Optional[float]], str]] = []
        for label, values, higher_is_better, color, marker, linestyle in series:
            if raw:
                y = [np.nan if v is None else float(v) for v in values]
            else:
                y = best_score(values, higher_is_better)
            finite_mask = np.isfinite(np.asarray(y, dtype=float))
            if not np.any(finite_mask):
                continue
            plotted += 1
            ax.plot(
                cycles,
                y,
                color=color,
                marker=marker,
                linestyle=linestyle,
                linewidth=2.1,
                markersize=5.5,
                markeredgecolor="#ffffff",
                markeredgewidth=0.8,
                label=label,
            )
            # No persistent "latest cycle" ring: the line ending already shows
            # the newest point, and a permanent hollow-circle overlay reads as
            # a leftover hover state even when the pointer isn't over it. Only
            # an actual hover (MetricsPlotInteraction) emphasizes a marker now.
            unit = "%" if ("%" in label or ("%" in raw_ylabel and raw)) else ""
            hover_series.append((label, list(cycles), list(y), list(values), unit))
        self._metrics_hover_series[key] = hover_series
        if plotted > 1:
            handles, labels = ax.get_legend_handles_labels()
            figure.legend(
                handles,
                labels,
                loc="center left",
                bbox_to_anchor=(0.82, 0.5),
                ncol=1,
                frameon=False,
                fontsize=7.2,
                handlelength=1.4,
                labelspacing=0.28,
                handletextpad=0.4,
                borderaxespad=0.0,
            )
        elif not plotted:
            ax.text(
                0.5,
                0.5,
                "No finite metrics yet",
                ha="center",
                va="center",
                color="#7183a6",
                transform=ax.transAxes,
            )
        # A single-series tab (Powder repartitioning) omits its legend: the
        # y-axis label already uniquely names the one plotted metric, and a
        # one-item legend just repeats it while wasting horizontal space.

        view_mode = "full"
        if interaction is not None:
            view_mode = interaction.apply_limits(ax, full_xlim, full_ylim, detail_ylim)
        else:
            ax.set_xlim(*full_xlim)
            ax.set_ylim(*full_ylim)

        if view_mode == "detail":
            ylo, yhi = ax.get_ylim()
            clipped = sum(
                1
                for _label, values, *_rest in series
                for v in values
                if v is not None and np.isfinite(float(v)) and not (ylo <= float(v) <= yhi)
            )
            if clipped:
                noun = "point" if clipped == 1 else "points"
                ax.text(
                    0.02,
                    0.965,
                    f"{clipped} {noun} outside detail range · Full range to view",
                    ha="left",
                    va="top",
                    color="#52658b",
                    fontsize=7.0,
                    style="italic",
                    transform=ax.transAxes,
                    bbox=dict(boxstyle="square,pad=0.25", facecolor="#ffffff", edgecolor="none", alpha=0.82),
                )

        self._layout_metrics_figure(key)
        canvas.draw_idle()

    def _update_plot(self) -> None:
        def series_has_data(series) -> bool:
            return any(v is not None for _label, values, *_rest in series for v in values)

        def set_tab_visible(key: str, series) -> None:
            try:
                index = self._metrics_tab_keys.index(key)
            except ValueError:
                return
            # Before any cycle has completed there is nothing to distinguish
            # "no data yet" from "irrelevant for this run" -- keep every tab
            # visible (showing the normal "Run phasing..." placeholder) until
            # results start arriving, only then hide tabs that stayed empty.
            self.metrics_tabs.setTabVisible(index, (not self.results) or series_has_data(series))

        superflip_series = [
            ("Reference match", [r.superflip_ref_match for r in self.results], False, "#001170", "D", ":"),
            ("SF RMSD", [r.superflip_metric for r in self.results], False, "#44b7ff", "v", "-."),
            ("Recall", [r.superflip_recall for r in self.results], True, "#2264b8", "^", "-"),
            ("Precision", [r.superflip_precision for r in self.results], True, "#082a8a", "P", "--"),
            ("Heavy atoms found", [r.superflip_heavy_atom_count for r in self.results], True, "#7183a6", "h", ":"),
        ]
        self._render_metrics_tab("superflip", superflip_series)
        set_tab_visible("superflip", superflip_series)

        deblur_series = [
            ("SharpED RMSD", [r.deblur_metric for r in self.results], False, "#001170", "X", "--"),
            ("Map correlation", [r.recycle_map_correlation for r in self.results], True, "#2264b8", "*", "-"),
            ("Recall", [r.deblur_recall for r in self.results], True, "#44b7ff", "^", "-"),
            ("Precision", [r.deblur_precision for r in self.results], True, "#082a8a", "P", "--"),
            ("Heavy atoms found", [r.deblur_heavy_atom_count for r in self.results], True, "#7183a6", "h", ":"),
        ]
        self._render_metrics_tab("deblur", deblur_series)
        set_tab_visible("deblur", deblur_series)

        superflip_omit_series = [
            ("Omit map correlation", [r.omit_superflip_correlation for r in self.results], True, "#2264b8", "*", "-"),
            ("R_free", [r.omit_superflip_rfree for r in self.results], False, "#001170", "o", "-"),
        ]
        self._render_metrics_tab("superflip_omit", superflip_omit_series)
        set_tab_visible("superflip_omit", superflip_omit_series)

        deblur_omit_series = [
            ("Omit map correlation", [r.omit_deblur_correlation for r in self.results], True, "#2264b8", "*", "-"),
            ("R_free", [r.omit_deblur_rfree for r in self.results], False, "#001170", "o", "-"),
        ]
        self._render_metrics_tab("deblur_omit", deblur_omit_series)
        set_tab_visible("deblur_omit", deblur_omit_series)

        powder_repartition_series = [
            ("Mean intensity change (%)", [r.powder_repartition_avg_change_percent for r in self.results], False, "#001170", "o", "-"),
        ]
        self._render_metrics_tab(
            "powder_repartition",
            powder_repartition_series,
            raw=True,
            raw_ylabel="Mean intensity change (%)",
        )
        set_tab_visible("powder_repartition", powder_repartition_series)

        intensity_correction_series = [
            ("Mean intensity change (%)", [r.intensity_correction_avg_change_percent for r in self.results], False, "#001170", "o", "-"),
        ]
        self._render_metrics_tab(
            "intensity_correction",
            intensity_correction_series,
            raw=True,
            raw_ylabel="Mean intensity change (%)",
        )
        set_tab_visible("intensity_correction", intensity_correction_series)

    def _element_color(self, element: str) -> str:
        # This extended blue scale is intentionally exclusive to structure atoms.
        palette = {
            "H": "#74C9FF", "C": "#001170", "N": "#0E50AF", "O": "#1FA5FF",
            "B": "#2264B8", "F": "#44B7FF", "Na": "#082A8A", "Mg": "#126AC7",
            "Al": "#1684DE", "Si": "#2DAEFF", "P": "#0B3798", "S": "#44B7FF",
            "Cl": "#1FA5FF", "K": "#071F82", "Ca": "#0E50AF", "Mn": "#126AC7",
            "Fe": "#082A8A", "Co": "#0B3798", "Ni": "#126AC7", "Cu": "#1684DE",
            "Zn": "#2264B8", "Br": "#2DAEFF", "Ag": "#44B7FF", "I": "#0E50AF",
            "Au": "#1FA5FF", "Hg": "#1684DE", "Pb": "#071F82",
        }
        symbol = clean_element_symbol(element)
        if symbol in palette:
            return palette[symbol]
        fallback_scale = ("#001170", "#082A8A", "#0B3798", "#0E50AF", "#126AC7", "#1684DE", "#1FA5FF", "#2DAEFF", "#44B7FF")
        return fallback_scale[element_atomic_number(symbol) % len(fallback_scale)]

    def _structure_cartesian_geometry(self, atoms: Sequence[AtomSite]) -> Tuple[np.ndarray, np.ndarray]:
        fractional_corners = np.asarray(
            [
                [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 1.0, 0.0],
                [0.0, 0.0, 1.0], [1.0, 0.0, 1.0], [0.0, 1.0, 1.0], [1.0, 1.0, 1.0],
            ],
            dtype=np.float64,
        )
        fractional_atoms = np.asarray([wrap_frac(atom.frac) for atom in atoms], dtype=np.float64)
        cell = self.structure_cell
        if cell is None or min(float(cell.a), float(cell.b), float(cell.c)) <= 0:
            return fractional_atoms, fractional_corners

        def orthogonalize(points: np.ndarray) -> np.ndarray:
            cartesian: List[List[float]] = []
            for point in points:
                position = cell.orthogonalize(gemmi.Fractional(float(point[0]), float(point[1]), float(point[2])))
                cartesian.append([float(position.x), float(position.y), float(position.z)])
            return np.asarray(cartesian, dtype=np.float64)

        return orthogonalize(fractional_atoms), orthogonalize(fractional_corners)

    def _plot_structure_atoms(self, ax, atoms: Sequence[AtomSite], empty_text: str = "No structure available") -> str:
        if not atoms:
            ax.set_axis_off()
            ax.text2D(0.5, 0.50, empty_text, ha="center", va="center", fontsize=8, color="#5d6b86", transform=ax.transAxes)
            return ""

        non_h_atoms = [a for a in atoms if clean_element_symbol(a.element) not in {"H", "D", "He"}]
        if not non_h_atoms:
            ax.set_axis_off()
            ax.text2D(0.5, 0.50, "No non-H/He atoms", ha="center", va="center", fontsize=8, color="#5d6b86", transform=ax.transAxes)
            return ""

        ax.set_axis_on()
        ax.axison = True
        ax.set_xticks([]); ax.set_yticks([]); ax.set_zticks([])
        ax.view_init(elev=self.structure_elev, azim=self.structure_azim)
        ax.set_proj_type("ortho")
        try:
            for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
                axis.pane.set_facecolor("#ffffff")
                axis.pane.set_edgecolor("#ffffff")
                axis.pane.set_alpha(0.0)
                axis.line.set_color("#ffffff")
                axis._axinfo["grid"]["color"] = "#ffffff"
        except Exception:
            pass
        ranked_atoms = sorted(non_h_atoms, key=lambda atom: element_atomic_number(atom.element), reverse=True)
        plot_atoms = ranked_atoms[:800]
        coords, cell_corners = self._structure_cartesian_geometry(plot_atoms)
        bounds_min = np.min(cell_corners, axis=0)
        bounds_max = np.max(cell_corners, axis=0)
        spans = np.maximum(bounds_max - bounds_min, 1.0e-6)
        padding = spans * 0.025
        ax.set_xlim(bounds_min[0] - padding[0], bounds_max[0] + padding[0])
        ax.set_ylim(bounds_min[1] - padding[1], bounds_max[1] + padding[1])
        ax.set_zlim(bounds_min[2] - padding[2], bounds_max[2] + padding[2])
        display_aspect = spans / max(float(np.max(spans)), 1.0e-6)
        ax.set_box_aspect(display_aspect, zoom=1.18)

        cell_edges = (
            (0, 1), (0, 2), (0, 4), (1, 3), (1, 5), (2, 3),
            (2, 6), (3, 7), (4, 5), (4, 6), (5, 7), (6, 7),
        )
        cell_segments: List[np.ndarray] = []
        cell_midpoints: List[np.ndarray] = []
        edge_steps = np.linspace(0.0, 1.0, 9)
        for start, end in cell_edges:
            start_point = cell_corners[start]
            end_point = cell_corners[end]
            for t0, t1 in zip(edge_steps[:-1], edge_steps[1:]):
                segment = np.asarray(
                    [start_point * (1.0 - t0) + end_point * t0, start_point * (1.0 - t1) + end_point * t1],
                    dtype=np.float64,
                )
                cell_segments.append(segment)
                cell_midpoints.append(np.mean(segment, axis=0))
        cell_collection = Line3DCollection(cell_segments, linewidths=0.62)
        ax.add_collection3d(cell_collection)

        atom_base_colors = np.asarray([to_rgb(self._element_color(a.element)) for a in plot_atoms], dtype=np.float64)
        atom_count = len(non_h_atoms)
        count_scale = float(np.interp(
            atom_count,
            [10, 50, 200, 500, 1000, 2000],
            [1.30, 1.0, 0.72, 0.48, 0.34, 0.22],
        ))
        sizes = np.asarray(
            [max(4.0, min(76.0, (10.0 + 1.2 * element_atomic_number(a.element)) * count_scale)) for a in plot_atoms],
            dtype=np.float64,
        )
        scatter = ax.scatter(
            coords[:, 0], coords[:, 1], coords[:, 2], s=sizes, c=atom_base_colors,
            alpha=1.0, edgecolors="#ffffff", linewidths=0.18, depthshade=False,
        )
        depth_artists = StructureDepthArtists(
            scatter=scatter,
            atom_coordinates=coords,
            atom_base_colors=atom_base_colors,
            atom_sizes=sizes,
            atom_draw_order=np.arange(len(coords), dtype=np.int64),
            cell_collection=cell_collection,
            cell_midpoints=np.asarray(cell_midpoints, dtype=np.float64),
            cell_corners=cell_corners,
        )
        self._structure_depth_artists.append(depth_artists)
        self._update_structure_depth_artist(depth_artists, self.structure_elev, self.structure_azim)
        shown = len(plot_atoms)
        suffix = "" if shown == len(non_h_atoms) else f" · displaying {shown:,} heaviest"
        return f"{len(non_h_atoms):,} non-H/He atoms{suffix}"

    def _update_structure_depth_artist(self, artists: StructureDepthArtists, elev: float, azim: float) -> None:
        atom_fade = structure_depth_fade(
            artists.atom_coordinates,
            artists.atom_coordinates,
            elev,
            azim,
        )
        atom_colors = blend_structure_colors(artists.atom_base_colors, atom_fade)
        camera_depth = structure_camera_depth(artists.atom_coordinates, elev, azim)
        draw_order = np.argsort(camera_depth, kind="stable")  # rear first, nearest/front last
        artists.atom_draw_order = draw_order
        ordered_coordinates = artists.atom_coordinates[draw_order]
        ordered_colors = atom_colors[draw_order]
        artists.scatter._offsets3d = (
            ordered_coordinates[:, 0],
            ordered_coordinates[:, 1],
            ordered_coordinates[:, 2],
        )
        artists.scatter.set_sizes(artists.atom_sizes[draw_order])
        artists.scatter.set_facecolors(
            np.column_stack((ordered_colors, np.ones(len(ordered_colors), dtype=np.float64)))
        )

        edge_fade = structure_depth_fade(
            artists.cell_midpoints,
            artists.cell_midpoints,
            elev,
            azim,
            front_hold=0.20,
            gamma=1.20,
            maximum=0.58,
        )
        edge_colors = blend_structure_colors(np.asarray(to_rgb("#44b7ff"), dtype=np.float64), edge_fade)
        artists.cell_collection.set_color(np.column_stack((edge_colors, np.ones(len(edge_colors), dtype=np.float64))))

    def _update_structure_depth_cue(self, elev: float, azim: float) -> None:
        for artists in self._structure_depth_artists:
            self._update_structure_depth_artist(artists, elev, azim)

    def _safe_parse_structure(self, path: Optional[Path]) -> List[AtomSite]:
        if path is None or not Path(path).is_file():
            return []
        try:
            _, sg, _ = parse_cif_cell_and_sg(Path(path))
            return expand_atoms_by_symmetry(parse_cif_atoms(Path(path)), sg)
        except Exception as exc:
            key = str(Path(path))
            if key not in self._structure_parse_errors and hasattr(self, "log_text"):
                self._structure_parse_errors.add(key)
                report = build_error_report(
                    exc,
                    subsystem="Structure viewer",
                    operation="Load structure preview",
                    paths=(Path(path),),
                )
                self._append_execution_log(
                    f"Structure preview could not load {Path(path).name}.",
                    level="WARNING",
                    subsystem="Structure viewer",
                )
                self._append_execution_log(report.diagnostic_block(), level="DETAIL", subsystem="Structure viewer")
            return []

    def _begin_structure_rotation(self, event) -> None:
        ax = getattr(event, "inaxes", None)
        self._structure_rotation_source = ax if ax in self.structure_axes else None

    def _apply_structure_rotation(self, source_ax, *, redraw: bool = True) -> None:
        if source_ax is None or source_ax not in self.structure_axes:
            return
        elev = float(getattr(source_ax, "elev", self.structure_elev))
        azim = float(getattr(source_ax, "azim", self.structure_azim))
        self.structure_elev = elev
        self.structure_azim = azim
        for axis in self.structure_axes:
            axis.view_init(elev=elev, azim=azim)
        self._update_structure_depth_cue(elev, azim)
        if redraw:
            self.structure_canvas.draw_idle()

    def _sync_structure_view_from_event(self, event) -> None:
        source_ax = self._structure_rotation_source
        if source_ax is None:
            source_ax = getattr(event, "inaxes", None)
        if source_ax is None or source_ax not in self.structure_axes:
            return
        self._apply_structure_rotation(source_ax)

    def _finish_structure_rotation(self, event) -> None:
        source_ax = self._structure_rotation_source
        if source_ax is None:
            source_ax = getattr(event, "inaxes", None)
        self._apply_structure_rotation(source_ax, redraw=False)
        self._structure_rotation_source = None
        self.structure_canvas.draw()

    def _layout_structure_figure(self) -> None:
        if not hasattr(self, "structure_figure"):
            return
        height = max(1.0, float(self.structure_canvas.height())) if hasattr(self, "structure_canvas") else 390.0
        title_band = min(0.15, max(0.075, 30.0 / height))
        metadata_band = min(0.11, max(0.055, 24.0 / height))
        axes_top = 1.0 - title_band
        self.structure_figure.subplots_adjust(left=0.002, right=0.998, bottom=metadata_band, top=axes_top, wspace=0.035)
        title_y = axes_top + title_band * 0.52
        for title_text in getattr(self, "structure_title_texts", []):
            title_text.set_y(title_y)
        for metadata_text in getattr(self, "structure_metadata_texts", []):
            metadata_text.set_y(metadata_band * 0.44)
        for separator in getattr(self, "structure_separators", []):
            separator.set_ydata([max(0.08, metadata_band + 0.01), axes_top - 0.01])

    def _update_structure_views(self) -> None:
        self.structure_figure.clear()
        self.structure_figure.patch.set_facecolor("#ffffff")
        self.structure_axes = []
        self._structure_depth_artists = []
        status = str(getattr(self, "_run_status", "READY")).upper()
        waiting = status in {"RUNNING", "STOPPING"}
        failed = status in {"ERROR", "CANCELLED"}
        panels = [
            ("Reference", self.reference_atoms_for_plot, "No reference structure"),
            (
                "Superflip",
                self.superflip_atoms_for_plot,
                "Waiting for Superflip result…" if waiting else ("Superflip result unavailable" if failed else "No Superflip structure available"),
            ),
            (
                "SharpED",
                self.deblur_atoms_for_plot,
                "Waiting for SharpED result…" if waiting else ("SharpED result unavailable" if failed else "No SharpED structure available"),
            ),
        ]
        has_interactive_structure = any(
            any(clean_element_symbol(atom.element) not in {"H", "D", "He"} for atom in atoms)
            for _title, atoms, _empty_text in panels
        )
        self.structure_canvas.setToolTip("")
        self.structure_rotation_hint.setVisible(has_interactive_structure)
        panel_metadata = []
        for idx, (_title, atoms, empty_text) in enumerate(panels, start=1):
            ax = self.structure_figure.add_subplot(1, 3, idx, projection="3d")
            self.structure_axes.append(ax)
            panel_metadata.append(self._plot_structure_atoms(ax, atoms, empty_text))
        self.structure_title_texts = [
            self.structure_figure.text(
                x_position,
                0.96,
                title,
                ha="center",
                va="center",
                fontsize=10,
                fontweight="bold",
                color="#001170",
            )
            for x_position, (title, _atoms, _empty_text) in zip((1.0 / 6.0, 0.5, 5.0 / 6.0), panels)
        ]
        self.structure_metadata_texts = [
            self.structure_figure.text(
                x_position,
                0.03,
                metadata,
                ha="center",
                va="center",
                fontsize=7.5,
                color="#52658b",
            )
            for x_position, metadata in zip((1.0 / 6.0, 0.5, 5.0 / 6.0), panel_metadata)
        ]
        self.structure_separators = []
        for x_position in (1.0 / 3.0, 2.0 / 3.0):
            separator = Line2D(
                [x_position, x_position], [0.08, 0.90],
                transform=self.structure_figure.transFigure,
                color="#cbd7ea", linewidth=0.45, alpha=0.62,
            )
            self.structure_figure.add_artist(separator)
            self.structure_separators.append(separator)
        self._layout_structure_figure()
        self.structure_canvas.draw_idle()

    def get_config(self) -> RunConfig:
        input_source_mode = normalize_input_source_mode(self._combo_value("input_source_mode") if "input_source_mode" in self.inputs else "")
        reference_xplor: Optional[Path] = None
        first_model_text = self._path_value("first_cycle_modelfile")
        first_model = Path(first_model_text).expanduser().resolve() if first_model_text else None
        jana_inflip_text = self._path_value("jana_inflip") if "jana_inflip" in self.inputs else ""
        jana_inflip = Path(jana_inflip_text).expanduser().resolve() if jana_inflip_text else None
        hkl_text = self._path_value("hkl")
        reference_cif_text = self._path_value("reference_cif")
        external_reference_file = Path(reference_cif_text).expanduser().resolve() if reference_cif_text else None
        superflip_referencefile = external_reference_file
        hkl_path = Path(hkl_text).expanduser().resolve() if hkl_text else Path("__phase_studio_no_external_hkl_selected__").resolve()
        if external_reference_file is not None and external_reference_file.suffix.lower() in REFERENCE_STRUCTURE_SUFFIXES:
            reference_cif_path = external_reference_file
        else:
            reference_cif_path = Path("__phase_studio_no_external_reference_cif_selected__").resolve()
        if input_source_mode == INPUT_MODE_INFLIP and external_reference_file is None:
            hkl_path = Path("__phase_studio_use_hkl_from_inflip__").resolve()
            reference_cif_path = Path("__phase_studio_use_reference_from_inflip__").resolve()
            superflip_referencefile = None
        referencefile_mode = referencefile_mode_for_path(superflip_referencefile)
        modelfile_source_value = normalize_modelfile_source(self._combo_value("modelfile_source"))
        cycles_value = max(1, self._spin_value("cycles"))
        if modelfile_source_value == "none":
            cycles_value = 1
        crystal_metadata = self._resolve_crystal_metadata_from_inputs()
        resolved_wavelength, wavelength_source = resolve_powder_wavelength(
            self._dspin_value("powder_wavelength"), jana_inflip, external_reference_file,
        )
        if self._check_value("redistribute_overlaps") and resolved_wavelength > 0 and wavelength_source != "manual entry":
            self.log(f"Powder overlap repartitioning: wavelength {resolved_wavelength:g} A auto-detected from {wavelength_source}.", level="DETAIL")
        return RunConfig(
            hkl=hkl_path,
            reference_cif=reference_cif_path,
            superflip_reference_xplor=reference_xplor,
            superflip_referencefile=superflip_referencefile,
            first_cycle_modelfile=first_model,
            input_source_mode=input_source_mode,
            jana_inflip=jana_inflip,
            crystal_metadata=crystal_metadata,
            jana_return_to_jana=bool(jana_inflip is not None),
            work_dir=Path(self._path_value("work_dir")).expanduser().resolve(),
            cycles=cycles_value,
            superflip_exe=self._path_value("superflip_exe") or "superflip",
            edma_exe=self._path_value("edma_exe") or "EDMA",
            composition_override="",
            plimit_superflip=self._dspin_value("plimit_superflip"),
            plimit_deblur=self._dspin_value("plimit_deblur"),
            merge_distance=self._dspin_value("merge_distance"),
            edma_maxima=self._line_value("edma_maxima") or "all",
            edma_fullcell=self._combo_value("edma_fullcell") or "no",
            edma_numberofatoms=self._line_value("edma_numberofatoms") or "composition",
            edma_centerofcharge=self._check_value("edma_centerofcharge"),
            edma_chlimit=self._line_value("edma_chlimit") or "0.2500",
            edma_chlimlist=self._line_value("edma_chlimlist") or "0.0057 relative",
            extra_edma_keywords=self._multiline_value("extra_edma_keywords"),
            damping_factor=self._dspin_value("damping_factor"),
            modelfile_source=modelfile_source_value,
            reconstruction_mode=normalize_reconstruction_mode(self._combo_value("reconstruction_mode")),
            run_edma_recycle_final=self._check_value("run_edma_recycle_final"),
            exclude_atoms=self._line_value("exclude_atoms") or "none",
            perform_algorithm=self._combo_value("perform_algorithm") or "CF",
            map_export_format=normalize_map_export_format(self._combo_value("map_export_format")),
            structure_export_format=normalize_structure_export_format(self._combo_value("structure_export_format")),
            referencefile_mode=referencefile_mode,
            voxel=self._line_value("voxel"),
            bestdensities_count=self._spin_value("bestdensities_count"),
            bestdensities_metric=normalize_bestdensities_metric(self._combo_value("bestdensities_metric")),
            bestdensities_symmetry=normalize_bestdensities_metric(self._combo_value("bestdensities_metric")) == "symmetry",
            polish=self._check_value("polish"),
            maxcycles=self._spin_value("maxcycles"),
            repeatmode=self._spin_value("repeatmode"),
            randomseed=self._line_value("randomseed") or "AUTO",
            delta=self._line_value("delta") or "AUTO",
            weakratio=self._line_value("weakratio") or "0.000",
            biso=self._line_value("biso") or "0.000",
            reflection_data_mode=normalize_reflection_data_mode(self._combo_value("reflection_data_mode")),
            first_cycle_like_attachment=False,
            i_over_sigma_min=self._dspin_value("i_over_sigma_min"),
            resolution_d_min=self._dspin_value("resolution_d_min"),
            normalize=self._combo_value("normalize") or "local",
            nresshells=self._spin_value("nresshells"),
            missing=self._line_value("missing"),
            searchsymmetry=self._combo_value("searchsymmetry") or "average",
            derivesymmetry=self._line_value("derivesymmetry") or "yes",
            electrons=self._line_value("electrons"),
            dataitemwidths="auto",
            extra_superflip_keywords=self._multiline_value("extra_superflip_keywords"),
            map_feedback_missing_enabled=self._check_value("map_feedback_missing_enabled"),
            map_feedback_missing_from_cycle=self._spin_value("map_feedback_missing_from_cycle"),
            map_feedback_missing_percent_limit=self._dspin_value("map_feedback_missing_percent_limit"),
            map_feedback_intensity_enabled=self._check_value("map_feedback_intensity_enabled"),
            map_feedback_intensity_from_cycle=self._spin_value("map_feedback_intensity_from_cycle"),
            map_feedback_intensity_damping=self._dspin_value("map_feedback_intensity_damping"),
            map_feedback_intensity_max_i_over_sigma=self._dspin_value("map_feedback_intensity_max_i_over_sigma"),
            redistribute_overlaps=self._check_value("redistribute_overlaps"),
            powder_redistribution_from_cycle=self._spin_value("powder_redistribution_from_cycle"),
            powder_wavelength=resolved_wavelength,
            powder_separation_factor=self._dspin_value("powder_separation_factor"),
            powder_redistribution_mix=self._dspin_value("powder_redistribution_mix"),
            run_sharped=self._check_value("run_sharped") and modelfile_source_value != "superflip_xplor",
            symmetrize_deblurred_map=self._check_value("symmetrize_deblurred_map") and modelfile_source_value != "superflip_xplor",
            run_edma_superflip=self._check_value("run_edma_superflip"),
            run_edma_deblurred=self._check_value("run_edma_deblurred"),
            compute_omit_maps=self._check_value("compute_omit_maps"),
            compute_omit_rfree=self._check_value("compute_omit_maps") and self._check_value("compute_omit_rfree"),
            sharped_base_url=self._line_value("sharped_base_url") or "https://jana.fzu.cz",
            sharped_api_token=self._line_value("sharped_api_token") or os.environ.get("SHARPED_API_TOKEN", ""),
            sharped_model=self._combo_value("sharped_model") or "default",
            sharped_elements=self._line_value("sharped_elements"),
            sharped_outres=self._dspin_value("sharped_outres"),
            sharped_max_upload_mb=self._dspin_value("sharped_max_upload_mb"),
            sharped_timeout_seconds=self._spin_value("sharped_timeout_seconds"),
            sharped_poll_seconds=self._spin_value("sharped_poll_seconds"),
            sharped_max_polls=self._spin_value("sharped_max_polls"),
        )

    def _resolve_configured_data_mode(self, cfg: RunConfig) -> str:
        # In pure Jana2020 .inflip mode the HKL format control is disabled and its
        # stored value ignored (dataformat always comes straight from the
        # .inflip file) -- force AUTO here too so a stale/corrupted widget
        # value can never override that, regardless of what is still sitting
        # in cfg.reflection_data_mode.
        mode = normalize_input_source_mode(cfg.input_source_mode)
        effective_configured_mode = (
            REFLECTION_DATA_MODE_AUTO if mode == INPUT_MODE_INFLIP else cfg.reflection_data_mode
        )
        return resolve_reflection_data_mode_from_sources(cfg.hkl, effective_configured_mode, cfg.jana_inflip)

    def _resolve_configured_data_mode_for_ui(self) -> str:
        """Best-effort equivalent of _resolve_configured_data_mode() for live
        widget state (before a RunConfig exists), used to gate controls that
        only make sense for a particular HKL format -- e.g. powder overlap
        repartitioning requires FWHM-carrying data. Never raises: falls back
        to the configured mode itself if paths are missing/unreadable."""
        mode = normalize_input_source_mode(self._combo_value("input_source_mode") if "input_source_mode" in self.inputs else "")
        configured = (
            REFLECTION_DATA_MODE_AUTO if mode == INPUT_MODE_INFLIP
            else (self._combo_value("reflection_data_mode") if "reflection_data_mode" in self.inputs else REFLECTION_DATA_MODE_AUTO)
        )
        hkl_text = self._path_value("hkl").strip() if "hkl" in self.inputs else ""
        inflip_text = self._path_value("jana_inflip").strip() if "jana_inflip" in self.inputs else ""
        inflip_path = Path(inflip_text) if inflip_text else None
        try:
            return resolve_reflection_data_mode_from_sources(Path(hkl_text), configured, inflip_path)
        except Exception:
            return normalize_reflection_data_mode(configured)

    def _validate_run_config(self, cfg: RunConfig) -> Tuple[List[str], str]:
        issues: List[str] = []
        details: List[str] = []
        mode = normalize_input_source_mode(cfg.input_source_mode)
        hkl_text = self._path_value("hkl").strip()
        ref_text = self._path_value("reference_cif").strip()
        ref_suffix = cfg.superflip_referencefile.suffix.lower() if cfg.superflip_referencefile is not None else ""
        if mode in {INPUT_MODE_INFLIP, INPUT_MODE_INFLIP_OVERRIDES}:
            if cfg.jana_inflip is None or not cfg.jana_inflip.is_file():
                issues.append("The Jana2020 .inflip file does not exist or cannot be read.")
                details.append(f"Jana2020 .inflip: {cfg.jana_inflip or '(not selected)'}")
            if mode == INPUT_MODE_INFLIP_OVERRIDES:
                if hkl_text and not cfg.hkl.is_file():
                    issues.append("The external HKL override does not exist.")
                    details.append(f"HKL override: {cfg.hkl}")
                if ref_text and (cfg.superflip_referencefile is None or not cfg.superflip_referencefile.is_file()):
                    issues.append("The external reference file does not exist.")
                    details.append(f"Reference: {cfg.superflip_referencefile}")
        elif not cfg.hkl.is_file():
            issues.append("The external HKL file does not exist.")
            details.append(f"HKL: {cfg.hkl}")
        if cfg.first_cycle_modelfile is not None and not cfg.first_cycle_modelfile.is_file():
            issues.append("The initial model file does not exist.")
            details.append(f"Initial model: {cfg.first_cycle_modelfile}")
        if cfg.superflip_referencefile is not None:
            if not cfg.superflip_referencefile.is_file():
                issues.append("The external reference file does not exist.")
                details.append(f"Reference: {cfg.superflip_referencefile}")
            elif ref_suffix not in REFERENCE_FILE_SUFFIXES:
                issues.append("The external reference format is not supported.")
                details.append(f"Reference suffix: {ref_suffix or '(none)'}")
        if cfg.redistribute_overlaps and cfg.powder_wavelength <= 0:
            issues.append(
                "Powder overlap repartitioning is enabled, but no Wavelength (Å) could be resolved from a manual "
                "entry, the .inflip file, or the reference file's _diffrn_radiation_wavelength tag."
            )
            details.append("Wavelength (Å): Basic → Map feedback → Powder overlap repartitioning")
        if cfg.redistribute_overlaps and not reflection_mode_has_fwhm(self._resolve_configured_data_mode(cfg)):
            issues.append(
                "Powder overlap repartitioning is enabled, but the configured reflection data does not carry a "
                "FWHM value (hkl I fwhm / hkl F fwhm). This mechanism only applies to FWHM-carrying data."
            )
            details.append("Enable powder overlap repartitioning: Basic → Map feedback → Powder overlap repartitioning")
        reconstruction_mode = normalize_reconstruction_mode(cfg.reconstruction_mode)
        is_recycling = reconstruction_mode != "superflip"
        if (cfg.run_sharped or is_recycling) and not cfg.sharped_api_token.strip():
            issues.append("A SharpED API token is required for the selected workflow.")
        needs_superflip = not is_recycling or reconstruction_mode == "sharped_recycle"
        needs_edma = (not is_recycling and (cfg.run_edma_superflip or cfg.run_edma_deblurred)) or (is_recycling and cfg.run_edma_recycle_final)
        for exe, label, needed in (
            (cfg.superflip_exe, "Superflip", needs_superflip),
            (cfg.edma_exe, "EDMA", needs_edma),
        ):
            if needed and resolve_executable_for_validation(exe) is None:
                issues.append(f"The {label} executable was not found.")
                details.append(f"{label} executable: {exe or '(not selected)'}")
        return list(dict.fromkeys(issues)), sanitize_error_details("\n".join(details))

    def start_run(self) -> None:
        if self.worker and self.worker.is_alive():
            self._append_execution_log("Pipeline is already running.", level="WARNING", subsystem="Pipeline")
            return
        try:
            cfg = self.get_config()
        except Exception as exc:
            self._show_error_report(build_error_report(exc, subsystem="Input", operation="Pre-run validation"))
            return
        issues, technical_details = self._validate_run_config(cfg)
        if issues:
            self._show_error_report(build_validation_report(issues, technical_details=technical_details))
            return
        try:
            cfg.work_dir.mkdir(parents=True, exist_ok=True)
            self.last_run_config = cfg
            self.save_settings()
        except Exception as exc:
            self._show_error_report(
                build_error_report(exc, subsystem="Files", operation="Create working directory", paths=(cfg.work_dir,))
            )
            return
        mode = normalize_input_source_mode(cfg.input_source_mode)
        if mode == INPUT_MODE_INFLIP:
            self._append_execution_log("Input mode: Jana2020 .inflip. Embedded HKL data will be used.")
        elif mode == INPUT_MODE_INFLIP_OVERRIDES:
            if not self._path_value("hkl").strip():
                self._append_execution_log("HKL override is empty; the Jana2020 .inflip fbegin/endf block will be used.", level="DETAIL")
            if not self._path_value("reference_cif").strip():
                self._append_execution_log("External reference file is empty; no external reference density or atom sites will be used.", level="DETAIL")
        self.stop_after_cycle.clear()
        self.stop_now.clear()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setValue(0)
        self._set_overall_progress_text("Running")
        self._cycle_progress_state = None
        self.current_cycle_progress.setRange(0, 0)
        self.current_cycle_detail.setText("Preparing pipeline…")
        self.current_cycle_stage_counter.setText("Preparing")
        self._set_run_status("Running")
        self.run_btn.setEnabled(False)
        self.handoff_btn.setEnabled(False)
        self.run_btn.setText("Running…")
        self.log_text.horizontalScrollBar().setValue(0)
        self._append_execution_log("Preparing validated pipeline inputs…", level="DETAIL")
        QApplication.processEvents()
        self.worker = threading.Thread(target=self.pipeline_worker, args=(cfg,), daemon=True)
        self.worker.start()

    def continue_run(self) -> None:
        if self.worker and self.worker.is_alive():
            self._append_execution_log("Pipeline is already running.", level="WARNING", subsystem="Pipeline")
            return
        state = self._resume_state
        if state is None:
            self._append_execution_log("Nothing to continue: no previous run to resume.", level="WARNING", subsystem="Pipeline")
            return
        requested_cycles = max(1, self._spin_value("cycles"))
        if requested_cycles <= state.completed_cycles:
            self._show_error_report(build_validation_report([
                f"The previous run already completed {state.completed_cycles} cycle(s). "
                f"Increase Cycles above {state.completed_cycles} before continuing."
            ]))
            return
        state.cfg.cycles = requested_cycles
        self.last_run_config = state.cfg
        self.stop_after_cycle.clear()
        self.stop_now.clear()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setValue(0)
        self._set_overall_progress_text("Running")
        self._cycle_progress_state = None
        self.current_cycle_progress.setRange(0, 0)
        self.current_cycle_detail.setText("Resuming pipeline…")
        self.current_cycle_stage_counter.setText("Preparing")
        self._set_run_status("Running")
        self.run_btn.setEnabled(False)
        self.handoff_btn.setEnabled(False)
        self.run_btn.setText("Running…")
        self._append_execution_log(
            f"Continuing pipeline from cycle {state.completed_cycles + 1} of {requested_cycles}, "
            "reusing the previous run's metadata, reflections and cycle feedback.",
            level="DETAIL",
        )
        QApplication.processEvents()
        self.worker = threading.Thread(
            target=self.pipeline_worker, args=(None,), kwargs={"resume_state": state}, daemon=True
        )
        self.worker.start()

    def pipeline_worker(self, cfg: Optional[RunConfig], resume_state: Optional[PipelineState] = None) -> None:
        if resume_state is not None:
            try:
                self.log(
                    f"=== Pipeline resumed at cycle {resume_state.completed_cycles + 1} of {resume_state.cfg.cycles} ===",
                    level="STEP",
                )
                self.msg_queue.put(("progress_setup", resume_state.cfg.cycles))
                self.msg_queue.put(("progress", resume_state.completed_cycles))
                if normalize_reconstruction_mode(resume_state.cfg.reconstruction_mode) == "superflip":
                    self._run_pipeline_cycles(resume_state)
                else:
                    self._run_sharped_recycle_cycles(resume_state)
            except Exception as exc:
                self.msg_queue.put((
                    "error_report",
                    build_error_report(exc, operation="Run pipeline", extra_details=traceback.format_exc()),
                ))
            return
        try:
            self.log("=== Pipeline started ===", level="STEP")
            mode = normalize_input_source_mode(cfg.input_source_mode)
            self.log("Input", level="STEP")
            self.log(f"  Mode: {INPUT_MODE_LABELS.get(mode, mode)}")
            self.log(f"  Work directory: {cfg.work_dir}")
            if mode in {INPUT_MODE_INFLIP, INPUT_MODE_INFLIP_OVERRIDES}:
                if cfg.jana_inflip is None:
                    raise RuntimeError("Jana input mode selected, but no Jana2020 .inflip file is configured.")
                self.log(f"  Jana2020 .inflip: {cfg.jana_inflip}", level="DETAIL")
                if mode == INPUT_MODE_INFLIP or not cfg.hkl.is_file():
                    cfg.hkl = extract_embedded_hkl_from_inflip(cfg.jana_inflip, cfg.work_dir)
                    self.log("  HKL source: embedded fbegin/endf block exported from Jana2020 .inflip", level="DETAIL")
                else:
                    self.log("  HKL source: external override", level="DETAIL")

                declared_ref = inflip_declared_reference(cfg.jana_inflip)
                if not cfg.reference_cif.is_file():
                    if declared_ref is not None and declared_ref.is_file() and declared_ref.suffix.lower() in REFERENCE_STRUCTURE_SUFFIXES:
                        cfg.reference_cif = declared_ref
                        self.log(f"  Reference structure: {cfg.reference_cif}")
                elif cfg.reference_cif.suffix.lower() in REFERENCE_STRUCTURE_SUFFIXES:
                    self.log(f"  Reference structure: {cfg.reference_cif}")

                if cfg.superflip_referencefile is None and declared_ref is not None and declared_ref.is_file() and declared_ref.suffix.lower() in REFERENCE_DENSITY_SUFFIXES:
                    cfg.superflip_referencefile = declared_ref
                    cfg.referencefile_mode = referencefile_mode_for_path(cfg.superflip_referencefile)
                    self.log(f"  Reference density: {cfg.superflip_referencefile}")
            else:
                if cfg.superflip_referencefile is not None:
                    self.log(f"  Reference: {cfg.superflip_referencefile}")
            self.log(f"  HKL: {cfg.hkl}")
            configured_data_mode = self._resolve_configured_data_mode(cfg)
            value_col, sigma_col, include_000 = reflection_columns_for_mode(configured_data_mode)
            refl_raw = read_hkl(cfg.hkl, value_col=value_col, sigma_col=sigma_col, include_000=include_000)
            refl = merge_duplicate_reflections(refl_raw)
            current_reflections = list(refl)
            self.log(f"  Reflections: {len(refl_raw)} parsed / {len(refl)} unique", level="INFO")
            if str(cfg.referencefile_mode).strip().lower() in {"reference_xplor", "reference_density"} and cfg.superflip_reference_xplor is None and cfg.superflip_referencefile is None:
                cfg.referencefile_mode = "omit"
            atom_source: Optional[Path] = None
            for candidate in (cfg.superflip_referencefile, cfg.reference_cif):
                if (
                    candidate is not None
                    and Path(candidate).is_file()
                    and Path(candidate).suffix.lower() in REFERENCE_STRUCTURE_SUFFIXES
                ):
                    atom_source = Path(candidate)
                    break
            ref_ctx = reference_context_from_metadata(cfg.crystal_metadata, atom_source, cfg.work_dir)
            self.msg_queue.put(("structure_cell", (
                ref_ctx.cell.a, ref_ctx.cell.b, ref_ctx.cell.c,
                ref_ctx.cell.alpha, ref_ctx.cell.beta, ref_ctx.cell.gamma,
            )))
            self.msg_queue.put(("reference_atoms", expand_atoms_by_symmetry(ref_ctx.atoms, ref_ctx.spacegroup)))
            self.log("Crystal metadata", level="STEP")
            metadata_label = METADATA_SOURCE_LABELS.get(cfg.crystal_metadata.source, cfg.crystal_metadata.source)
            self.log(f"  Source: {metadata_label}", level="INFO")
            if cfg.crystal_metadata.source_path is not None:
                self.log(f"  Metadata file: {cfg.crystal_metadata.source_path}", level="DETAIL")
            self.log(f"  Cell: {ref_ctx.cell.a:.5f} {ref_ctx.cell.b:.5f} {ref_ctx.cell.c:.5f} {ref_ctx.cell.alpha:.3f} {ref_ctx.cell.beta:.3f} {ref_ctx.cell.gamma:.3f}")
            self.log(f"  Space group: {compact_spacegroup_symbol(ref_ctx.spacegroup)} (#{ref_ctx.spacegroup.number})")
            self.log(f"  Composition: {ref_ctx.composition}")
            self.log(
                f"  Atom sites: {atom_source.name if atom_source is not None else 'none'} · {len(ref_ctx.atoms)} atoms",
                level="INFO",
            )
            sharped_elements = cfg.sharped_elements.strip() or sharped_elements_from_composition(ref_ctx.composition)
            reconstruction_mode = normalize_reconstruction_mode(cfg.reconstruction_mode)
            if reconstruction_mode != "superflip":
                variant = "SharpED (experimental), random-phase start, no Superflip" if reconstruction_mode == "sharped_recycle_random" else "1st Superflip, then SharpED (beta)"
                self.log(f"Phasing method: {variant}", level="STEP")
            requested_modelfile_mode = normalize_modelfile_source(cfg.modelfile_source)
            modelfile_mode = requested_modelfile_mode
            use_xplor_modelfile = modelfile_mode in {"superflip_xplor", "deblurred_xplor"}
            use_superflip_xplor_modelfile = modelfile_mode == "superflip_xplor"
            use_cif_modelfile = modelfile_mode == "deblurred_edma_cif"
            workflow = ["Superflip"]
            if cfg.run_edma_superflip:
                workflow.append("EDMA")
            if cfg.run_sharped and not use_superflip_xplor_modelfile:
                workflow.append("SharpED")
            if cfg.symmetrize_deblurred_map and not use_superflip_xplor_modelfile:
                workflow.append("symmetry averaging")
            if cfg.run_edma_deblurred and not use_superflip_xplor_modelfile:
                workflow.append("EDMA")
            self.log("Workflow", level="STEP")
            self.log("  Stages: " + " → ".join(workflow), level="INFO")
            self.log(f"  Cycles: {cfg.cycles}", level="INFO")
            self.log(f"  Next-cycle model: {modelfile_source_display_label(modelfile_mode)}", level="INFO")
            if use_xplor_modelfile:
                self.log(
                    f"  XPLOR damping 1/x: {max(0.001, min(1.0, float(cfg.damping_factor))):g}",
                    level="INFO",
                )
            self.log("External programs", level="STEP")
            self.log(f"  Superflip: {cfg.superflip_exe}")
            self.log(f"  EDMA: {cfg.edma_exe}")
            self.log("SharpED", level="STEP")
            self.log(f"  Server: {cfg.sharped_base_url}")
            self.log(f"  Model: {cfg.sharped_model or 'default'}")
            self.log(f"  Elements: {sharped_elements}")

            self.log(f"EDMA plimit after Superflip: {cfg.plimit_superflip:g} sigma multiplier", level="DETAIL")
            self.log(f"EDMA plimit after SharpED: {cfg.plimit_deblur:g} sigma multiplier", level="DETAIL")
            self.log(f"EDMA maxima/fullcell/numberofatoms: {cfg.edma_maxima} / {cfg.edma_fullcell} / {cfg.edma_numberofatoms}", level="DETAIL")
            self.log(f"SharpED maximum upload size: {cfg.sharped_max_upload_mb:g} MB" if cfg.sharped_max_upload_mb > 0 else "SharpED maximum upload size: disabled", level="DETAIL")
            if use_xplor_modelfile:
                self.log(
                    f"XPLOR damping detail: effective old factor {effective_xplor_damping_factor(cfg.damping_factor):g}",
                    level="DETAIL",
                )
            if use_superflip_xplor_modelfile:
                self.log("Next-cycle XPLOR modelfile uses the Superflip map; SharpED is not required for cycling.", level="DETAIL")
            if use_cif_modelfile:
                self.log("CIF modelfiles are written without an explicit CIF format keyword; Superflip infers CIF from the .cif extension.", level="DETAIL")
            self.log(f"Superflip perform: {cfg.perform_algorithm.upper()}")
            self.log(
                "Output formats: "
                f"map={normalize_map_export_format(cfg.map_export_format)}, "
                f"structure={normalize_structure_export_format(cfg.structure_export_format)}"
            )
            self.log(f"Optional functions: EDMA/Superflip={'yes' if cfg.run_edma_superflip else 'no'}, SharpED={'yes' if cfg.run_sharped else 'no'}, Superflip symmetry/SharpED={'yes' if cfg.symmetrize_deblurred_map else 'no'}, EDMA/SharpED={'yes' if cfg.run_edma_deblurred else 'no'}")
            if cfg.first_cycle_modelfile is not None:
                self.log(f"First-cycle external modelfile: {cfg.first_cycle_modelfile}")
            explicit_superflip_referencefile = cfg.superflip_referencefile
            if explicit_superflip_referencefile is not None:
                self.log("External reference role: structure and Superflip referencefile", level="DETAIL")
                if explicit_superflip_referencefile.suffix.lower() == ".cif" and not parse_cif_atoms(explicit_superflip_referencefile):
                    self.log(
                        "Selected reference CIF contains no readable atom sites; it is used for "
                        "crystallographic metadata only and the Superflip referencefile keyword is omitted."
                    )
                    explicit_superflip_referencefile = None
            referencefile_mode = str(cfg.referencefile_mode or "none").strip().lower()
            if explicit_superflip_referencefile is not None:
                referencefile_mode = referencefile_mode_for_path(explicit_superflip_referencefile)
            elif referencefile_mode == "reference_cif" and explicit_superflip_referencefile is None:
                referencefile_mode = "omit"
                self.log("Superflip referencefile keyword omitted: no external reference file was selected.")
            if referencefile_mode == "reference_cif":
                if explicit_superflip_referencefile is not None:
                    self.log("Superflip referencefile format: inferred from CIF suffix", level="DETAIL")
                else:
                    self.log(f"Superflip referencefile: {ref_ctx.work_ref_cif} (format inferred from CIF suffix)", level="DETAIL")
            elif referencefile_mode in {"reference_xplor", "reference_density"} and (explicit_superflip_referencefile is not None or cfg.superflip_reference_xplor is not None):
                self.log(f"Superflip referencefile: {explicit_superflip_referencefile or cfg.superflip_reference_xplor} (format inferred from filename)", level="DETAIL")
            elif referencefile_mode == "omit":
                self.log(
                    "Superflip referencefile keyword: no external reference file selected; "
                    "cycle 1 omits it, later cycles fill it in automatically from the previous "
                    "cycle's EDMA CIF (or XPLOR map if EDMA produced no usable peaks).",
                    level="DETAIL",
                )
            else:
                self.log("Superflip referencefile keyword: no", level="DETAIL")
            self.log(f"Superflip bestdensities: {cfg.bestdensities_count} {'symmetry' if cfg.bestdensities_symmetry else cfg.bestdensities_metric}")
            self.log(f"Superflip polish: {'yes' if cfg.polish else 'no'}")
            self.log(f"Superflip HKL data mode: {format_reflection_data_mode(configured_data_mode)}")
            if cfg.resolution_d_min > 0:
                self.log(f"Superflip resolution cutoff: d >= {cfg.resolution_d_min:g} A")
            # One concise section at workflow start, never repeated per cycle --
            # canonical user-facing method names only, never internal RunConfig
            # field names (see Basic -> Map feedback for the same labels).
            map_feedback_lines: List[str] = []
            if cfg.map_feedback_missing_enabled:
                map_feedback_lines.append(f"  Missing-reflection completion · from cycle {cfg.map_feedback_missing_from_cycle}")
            if cfg.map_feedback_intensity_enabled:
                map_feedback_lines.append(f"  Intensity correction · from cycle {cfg.map_feedback_intensity_from_cycle}")
            if cfg.redistribute_overlaps:
                map_feedback_lines.append(f"  Powder overlap repartitioning · from cycle {cfg.powder_redistribution_from_cycle}")
                map_feedback_lines.append(f"  Wavelength: {cfg.powder_wavelength:g} Å")
                map_feedback_lines.append(f"  Separation factor: {cfg.powder_separation_factor:g}")
                map_feedback_lines.append(f"  Map ratio mix: {cfg.powder_redistribution_mix:g}")
            if map_feedback_lines:
                self.log("[Map feedback]\n" + "\n".join(map_feedback_lines))
            else:
                self.log("[Map feedback] Disabled")
            self.msg_queue.put(("progress_setup", cfg.cycles))
            data_modes_needed = {configured_data_mode}
            observed_hkls: Dict[str, Path] = {}
            for data_mode in sorted(data_modes_needed):
                observed_hkl = cfg.work_dir / observed_hkl_name_for_mode(data_mode)
                n_written = write_observed_reflections(observed_hkl, refl, cfg.i_over_sigma_min, data_mode=data_mode, cell=ref_ctx.cell, resolution_d_min=cfg.resolution_d_min)
                observed_hkls[data_mode] = observed_hkl
                self.log(f"Prepared HKL for {data_mode}: {observed_hkl} ({n_written} reflections)")
            omit_test_hkls: FrozenSet[Tuple[int, int, int]] = frozenset()
            if cfg.compute_omit_maps and reconstruction_mode == "superflip":
                omit_test_hkls = select_omit_test_set(refl, cfg.randomseed)
                self.log(f"Omit maps: excluding {len(omit_test_hkls)}/{len(refl)} reflections (fixed for this run) for cross-validation.", level="DETAIL")
            state = PipelineState(
                cfg=cfg,
                ref_ctx=ref_ctx,
                observed_hkls=observed_hkls,
                configured_data_mode=configured_data_mode,
                referencefile_mode=referencefile_mode,
                explicit_superflip_referencefile=explicit_superflip_referencefile,
                modelfile_mode=modelfile_mode,
                use_xplor_modelfile=use_xplor_modelfile,
                use_cif_modelfile=use_cif_modelfile,
                use_superflip_xplor_modelfile=use_superflip_xplor_modelfile,
                sharped_elements=sharped_elements,
                exclude_labels=parse_atom_label_list(cfg.exclude_atoms),
                progress_stages=cycle_progress_stages(cfg),
                current_reflections=current_reflections,
                omit_test_hkls=omit_test_hkls,
            )
            self._resume_state = state
            if reconstruction_mode == "superflip":
                self._run_pipeline_cycles(state)
            else:
                self._run_sharped_recycle_cycles(state)
        except Exception as exc:
            self.msg_queue.put((
                "error_report",
                build_error_report(
                    exc,
                    operation="Run pipeline",
                    extra_details=traceback.format_exc(),
                ),
            ))

    def _run_pipeline_cycles(self, state: PipelineState) -> None:
        cfg = state.cfg
        ref_ctx = state.ref_ctx
        observed_hkls = state.observed_hkls
        configured_data_mode = state.configured_data_mode
        referencefile_mode = state.referencefile_mode
        explicit_superflip_referencefile = state.explicit_superflip_referencefile
        modelfile_mode = state.modelfile_mode
        use_xplor_modelfile = state.use_xplor_modelfile
        use_cif_modelfile = state.use_cif_modelfile
        use_superflip_xplor_modelfile = state.use_superflip_xplor_modelfile
        sharped_elements = state.sharped_elements
        exclude_labels = state.exclude_labels
        progress_stages = state.progress_stages
        all_results = state.all_results
        # Some Superflip diagnostics (e.g. the normalize-keyword-unsupported
        # notice) repeat byte-for-byte on every cycle since Superflip's input
        # is regenerated each time; demote every repeat after the first to
        # DETAIL for the whole run instead of showing it at full prominence
        # once per cycle. Nothing is ever suppressed -- only the repeats.
        seen_repeated_superflip_warnings: set = set()
        superflip_log = make_run_scoped_dedup_log(
            self.log,
            seen_repeated_superflip_warnings,
            ("Superflip normalize value", "  Ignored duplicate/managed Superflip keyword"),
        )
        for cyc in range(state.completed_cycles + 1, cfg.cycles + 1):
            if self.stop_after_cycle.is_set():
                self.msg_queue.put(("cancelled", state.completed_cycles))
                return
            self._emit_cycle_progress(
                cyc,
                cfg.cycles,
                progress_stages,
                "Preparing cycle",
                detail="preparing model and reflections",
            )
            cycle_dir = cfg.work_dir / f"cycle_{cyc:03d}"; cycle_dir.mkdir(parents=True, exist_ok=True)
            self.log(f"=== Cycle {cyc} of {cfg.cycles} ===", level="STEP")
            model_for_sf: Optional[Path] = None
            model_source = "none"
            model_metric = state.current_model_metric
            if cyc == 1 and cfg.first_cycle_modelfile is not None:
                model_source = "external_first_cycle"
                model_for_sf = cfg.first_cycle_modelfile
                self.log(f"[Cycle model] Source: external first-cycle model · {model_for_sf}")
            elif state.current_model is not None and use_xplor_modelfile:
                model_source = modelfile_mode
                model_for_sf = state.current_model
                self.log(f"[Cycle {cyc}] Next-cycle model · {modelfile_source_display_label(modelfile_mode)} (from cycle {cyc - 1}) · {model_for_sf}")
                self.log("  CIF-only exclude settings skipped for XPLOR modelfile.", level="DETAIL")
            elif state.current_model is not None and use_cif_modelfile:
                model_source = "deblurred_edma_cif"
                model_for_sf = cycle_dir / f"cycle_{cyc:03d}_modelfile_prepared.cif"
                model_for_sf, removed, kept = write_filtered_cif(state.current_model, model_for_sf, exclude_labels)
                self.log(f"[Cycle {cyc}] Next-cycle model · {modelfile_source_display_label('deblurred_edma_cif')} (from cycle {cyc - 1})")
                self.log(f"[Cycle model] Prepared CIF model · {model_for_sf}", level="DETAIL")
                self.log(f"  removed={removed}, kept={kept}", level="DETAIL")
                self.log("  Superflip infers CIF from the .cif extension; no explicit format keyword is written.", level="DETAIL")
                model_metric = nearest_metric_to_reference(model_for_sf, ref_ctx)
            elif cyc > 1 and modelfile_mode == "none":
                self.log("[Cycle model] No Superflip modelfile for this cycle.")
            observed_hkl_for_cycle = observed_hkls[configured_data_mode]
            sf_prefix = f"cycle_{cyc:03d}_superflip"
            reference_file_for_cycle: Optional[Path] = None
            reference_format_for_cycle = ""
            if referencefile_mode == "reference_cif":
                reference_file_for_cycle = explicit_superflip_referencefile if explicit_superflip_referencefile is not None else ref_ctx.work_ref_cif
            elif referencefile_mode in {"reference_xplor", "reference_density"}:
                reference_file_for_cycle = explicit_superflip_referencefile if explicit_superflip_referencefile is not None else cfg.superflip_reference_xplor
            elif referencefile_mode == "omit" and cyc > 1:
                # No user-selected reference file: without one, Superflip cannot fix the
                # phase origin against the previous cycle and the density map drifts.
                # Anchor it automatically on the most recent previous-cycle EDMA CIF, or
                # on the previous-cycle XPLOR map when EDMA produced no usable peaks.
                if state.auto_reference_cif is not None:
                    reference_file_for_cycle = state.auto_reference_cif
                    self.log(f"[Cycle reference] Auto referencefile (previous-cycle EDMA CIF): {reference_file_for_cycle}", level="DETAIL")
                elif state.auto_reference_xplor is not None:
                    reference_file_for_cycle = state.auto_reference_xplor
                    self.log(f"[Cycle reference] Auto referencefile (previous-cycle XPLOR map, EDMA unavailable): {reference_file_for_cycle}", level="DETAIL")
            sf_voxel = cfg.voxel
            sf_extra_superflip_keywords = cfg.extra_superflip_keywords
            if cfg.run_sharped and not use_superflip_xplor_modelfile:
                sf_voxel = sharped_limited_superflip_voxel(cfg.voxel, ref_ctx.cell, cfg.sharped_max_upload_mb, self.log)
                if sf_voxel != cfg.voxel and cfg.polish:
                    sf_extra_superflip_keywords = append_superflip_keyword(
                        sf_extra_superflip_keywords,
                        f"finevoxel {sf_voxel}",
                    )
            effective_repeat = 1 if model_for_sf is not None else max(1, int(cfg.repeatmode))

            def make_superflip_progress_relay(detail: str) -> Optional[Callable[[str], None]]:
                # Live sub-progress is only meaningful when Superflip will
                # actually attempt more than one repeat with THIS generated
                # input (the effective, not just configured, repeatmode) --
                # see SuperflipRepeatProgressParser for the parsed syntax.
                if effective_repeat <= 1:
                    return None
                tracker = SuperflipRepeatProgressParser(effective_repeat)

                def relay(line: str) -> None:
                    progress = tracker.feed(line)
                    if progress is not None:
                        self._emit_cycle_progress(
                            cyc,
                            cfg.cycles,
                            progress_stages,
                            "Superflip",
                            sub_index=progress.repeat,
                            sub_total=progress.repeat_total,
                            detail=detail,
                            busy=True,
                        )

                relay.tracker = tracker  # type: ignore[attr-defined]
                return relay

            if effective_repeat == 1:
                self._emit_cycle_progress(
                    cyc,
                    cfg.cycles,
                    progress_stages,
                    "Superflip",
                    sub_index=1,
                    sub_total=1,
                    detail="running",
                    busy=True,
                )
            else:
                # effective_repeat (Superflip's own repeatmode setting) is
                # internal/developer-oriented and stays out of the compact
                # primary status line; it is already visible in the pipeline's
                # own settings-summary log lines at cycle/run start.
                self._emit_cycle_progress(
                    cyc,
                    cfg.cycles,
                    progress_stages,
                    "Superflip",
                    detail="running",
                    busy=True,
                )
            # XPLOR is always requested (mandatory internal working map for EDMA/SharpED);
            # the single map-format choice only adds CCP4 or Jana m80/m81 on top of it.
            sf_map_format = normalize_map_export_format(cfg.map_export_format)
            sf_export_ccp4 = sf_map_format == "ccp4"
            sf_export_jana = sf_map_format == "jana"
            sf_progress_relay = make_superflip_progress_relay("running")
            sf_map = run_superflip_cycle(cycle_dir, sf_prefix, ref_ctx, observed_hkl_for_cycle, model_for_sf, reference_file_for_cycle, reference_format_for_cycle, cfg.superflip_exe, cfg.perform_algorithm, "xplor", sf_export_jana, True, sf_export_ccp4, sf_export_jana, sf_voxel, cfg.bestdensities_count, cfg.bestdensities_metric, cfg.bestdensities_symmetry, cfg.polish, cfg.maxcycles, cfg.repeatmode, cfg.randomseed, cfg.delta, cfg.weakratio, cfg.biso, configured_data_mode, cfg.normalize, cfg.nresshells, cfg.missing, cfg.searchsymmetry, cfg.derivesymmetry, cfg.electrons, cfg.dataitemwidths, sf_extra_superflip_keywords, superflip_log, self.stop_now, on_output_line=sf_progress_relay)
            if sf_progress_relay is not None and not sf_progress_relay.tracker.saw_progress:  # type: ignore[attr-defined]
                self.log("[Superflip] Live repeat progress unavailable for this executable.", level="DETAIL")
            self.log(f"Superflip map: {sf_map}")
            if self.stop_now.is_set():
                raise RuntimeError("Immediate stop requested.")
            export_phased_reflections_from_map(
                cfg.map_export_format, cycle_dir / sf_prefix, sf_map, state.current_reflections,
                cfg.i_over_sigma_min, configured_data_mode, ref_ctx.cell, cfg.resolution_d_min, self.log,
            )
            omit_sf_map: Optional[Path] = None
            omit_sf_correlation: Optional[float] = None
            omit_sf_rfree: Optional[float] = None
            if cfg.compute_omit_maps and state.omit_test_hkls:
                self._emit_cycle_progress(cyc, cfg.cycles, progress_stages, "Superflip", detail="omit map · running", busy=True)
                omit_reflections = [r for r in state.current_reflections if (int(r.h), int(r.k), int(r.l)) not in state.omit_test_hkls]
                omit_hkl = cycle_dir / f"{sf_prefix}_omit_input.hkl"
                write_observed_reflections(omit_hkl, omit_reflections, cfg.i_over_sigma_min, data_mode=configured_data_mode, cell=ref_ctx.cell, resolution_d_min=cfg.resolution_d_min)
                omit_prefix = f"{sf_prefix}_omit"
                omit_progress_relay = make_superflip_progress_relay("omit map · running")
                omit_sf_map = run_superflip_cycle(cycle_dir, omit_prefix, ref_ctx, omit_hkl, model_for_sf, reference_file_for_cycle, reference_format_for_cycle, cfg.superflip_exe, cfg.perform_algorithm, "xplor", False, True, False, False, sf_voxel, cfg.bestdensities_count, cfg.bestdensities_metric, cfg.bestdensities_symmetry, cfg.polish, cfg.maxcycles, cfg.repeatmode, cfg.randomseed, cfg.delta, cfg.weakratio, cfg.biso, configured_data_mode, cfg.normalize, cfg.nresshells, cfg.missing, cfg.searchsymmetry, cfg.derivesymmetry, cfg.electrons, cfg.dataitemwidths, sf_extra_superflip_keywords, superflip_log, self.stop_now, on_output_line=omit_progress_relay)
                self.log(f"Omit Superflip map ({len(state.omit_test_hkls)} reflections excluded): {omit_sf_map}")
                omit_sf_correlation = xplor_map_correlation(sf_map, omit_sf_map)
                if cfg.compute_omit_rfree:
                    predictions = xplor_fft_predictions(omit_sf_map, list(state.omit_test_hkls))
                    omit_sf_rfree = compute_rfree(state.current_reflections, state.omit_test_hkls, configured_data_mode, predictions)
                self.log(
                    f"[Omit] Superflip map correlation={('n/a' if omit_sf_correlation is None else f'{omit_sf_correlation:.4f}')}"
                    f" · R_free={('n/a' if omit_sf_rfree is None else f'{omit_sf_rfree:.4f}')}",
                    subsystem="Superflip",
                )
            sf_log_metrics = parse_superflip_cycle_metrics(cycle_dir, sf_prefix)
            self._emit_cycle_progress(
                cyc,
                cfg.cycles,
                progress_stages,
                "Superflip",
                detail="reading metrics",
            )
            if sf_log_metrics.rvalue is not None:
                peaks_text = "n/a" if sf_log_metrics.peaks is None else f"{float(sf_log_metrics.peaks):.3g}"
                symm_text = "n/a" if sf_log_metrics.symm is None else f"{float(sf_log_metrics.symm):.3g}"
                ref_match_text = "n/a" if sf_log_metrics.ref_match is None else f"{float(sf_log_metrics.ref_match):.3g}"
                success_rate_text = "n/a" if sf_log_metrics.success_rate is None else f"{float(sf_log_metrics.success_rate):.3g}"
                self.log(
                    "[Superflip] Metrics\n"
                    f"  R={sf_log_metrics.rvalue:.3f} · "
                    f"Peaks={peaks_text} · Symm={symm_text}\n"
                    f"  Derived SG={sf_log_metrics.derived_sg or 'n/a'} · "
                    f"Saved run={sf_log_metrics.saved_run if sf_log_metrics.saved_run is not None else 'n/a'} · "
                    f"Ref.match={ref_match_text} · SR={success_rate_text}%",
                    subsystem="Superflip",
                )
            sf_edma_dir = cycle_dir / "edma_superflip"
            if cfg.run_edma_superflip:
                self._emit_cycle_progress(cyc, cfg.cycles, progress_stages, "EDMA · Superflip map", busy=True)
                sf_edma_cif = run_edma_on_xplor(
                    sf_map, sf_edma_dir, sf_prefix, ref_ctx, cfg.plimit_superflip,
                    cfg.merge_distance, cfg.edma_exe, self.log,
                    self.stop_now, cfg.edma_maxima, cfg.edma_fullcell,
                    cfg.edma_numberofatoms, cfg.edma_centerofcharge, cfg.edma_chlimit,
                    cfg.edma_chlimlist, cfg.extra_edma_keywords, cfg.structure_export_format,
                    write_m40=cfg.jana_inflip is not None,
                )
            else:
                sf_edma_dir.mkdir(parents=True, exist_ok=True)
                sf_edma_cif = sf_edma_dir / f"{sf_prefix}_edma.cif"
                write_structure_bundle(sf_edma_cif, ref_ctx.cell, ref_ctx.spacegroup, ref_ctx.spacegroup_hm, [], cfg.structure_export_format)
                self.log("EDMA after Superflip disabled; empty placeholder CIF/XYZ/PDB written.")
            sf_metric = nearest_metric_to_reference(sf_edma_cif, ref_ctx) if cfg.run_edma_superflip else None
            sf_metric_text = "n/a" if sf_metric is None else f"{float(sf_metric):.3f}"
            sf_recall: Optional[float] = None
            sf_precision: Optional[float] = None
            sf_heavy_atoms: Optional[float] = None
            if cfg.run_edma_superflip:
                sf_recall_precision = atom_recall_precision(sf_edma_cif, ref_ctx, cfg.merge_distance)
                if sf_recall_precision is not None:
                    sf_recall, sf_precision = sf_recall_precision
                else:
                    sf_heavy_atoms = count_heavy_atoms(sf_edma_cif)
            self.log(
                f"[EDMA] Completed · Superflip map · RMSD={sf_metric_text} Å\n"
                f"  output: {sf_edma_cif}",
                subsystem="EDMA",
            )
            self.msg_queue.put(("structure_update", ("superflip", sf_edma_cif)))
            deblur_map = cycle_dir / f"cycle_{cyc:03d}_deblurred.xplor"
            if cfg.run_sharped and not use_superflip_xplor_modelfile:
                if self.stop_now.is_set():
                    raise RuntimeError("Immediate stop requested.")
                self._emit_cycle_progress(cyc, cfg.cycles, progress_stages, "SharpED", detail="preparing upload", busy=True)
                run_sharped_deblur(
                    sf_map,
                    deblur_map,
                    cfg.sharped_base_url,
                    cfg.sharped_api_token,
                    cfg.sharped_model,
                    sharped_elements,
                    cfg.sharped_outres,
                    cfg.sharped_max_upload_mb,
                    cfg.sharped_timeout_seconds,
                    cfg.sharped_poll_seconds,
                    cfg.sharped_max_polls,
                    self.log,
                    self.stop_now,
                    progress=lambda detail, cycle=cyc: self._emit_cycle_progress(
                        cycle,
                        cfg.cycles,
                        progress_stages,
                        "SharpED",
                        detail=detail,
                        busy=detail != "completed",
                    ),
                )
            else:
                shutil.copy2(sf_map, deblur_map)
                if use_superflip_xplor_modelfile:
                    self.log("SharpED skipped; the Superflip map (XPLOR) is used for the next-cycle modelfile.")
                else:
                    self.log(f"SharpED disabled; the {result_map_label('deblurred')} is a copy of the Superflip map.")
            self.log(f"{result_map_label('deblurred')}: {deblur_map}")
            omit_deblur_correlation: Optional[float] = None
            omit_deblur_rfree: Optional[float] = None
            if cfg.compute_omit_maps and state.omit_test_hkls and omit_sf_map is not None and cfg.run_sharped and not use_superflip_xplor_modelfile:
                if self.stop_now.is_set():
                    raise RuntimeError("Immediate stop requested.")
                self._emit_cycle_progress(cyc, cfg.cycles, progress_stages, "SharpED", detail="omit map · preparing upload", busy=True)
                omit_deblur_map = cycle_dir / f"{sf_prefix}_omit_deblurred.xplor"
                run_sharped_deblur(
                    omit_sf_map, omit_deblur_map, cfg.sharped_base_url, cfg.sharped_api_token, cfg.sharped_model,
                    sharped_elements, cfg.sharped_outres, cfg.sharped_max_upload_mb, cfg.sharped_timeout_seconds,
                    cfg.sharped_poll_seconds, cfg.sharped_max_polls, self.log, self.stop_now,
                    progress=lambda detail, cycle=cyc: self._emit_cycle_progress(
                        cycle, cfg.cycles, progress_stages, "SharpED", detail=f"omit map · {detail}", busy=detail != "completed",
                    ),
                )
                self.log(f"Omit {result_map_label('deblurred')}: {omit_deblur_map}")
                omit_deblur_correlation = xplor_map_correlation(deblur_map, omit_deblur_map)
                if cfg.compute_omit_rfree:
                    predictions = xplor_fft_predictions(omit_deblur_map, list(state.omit_test_hkls))
                    omit_deblur_rfree = compute_rfree(state.current_reflections, state.omit_test_hkls, configured_data_mode, predictions)
                self.log(
                    f"[Omit] {result_map_label('deblurred')} correlation={('n/a' if omit_deblur_correlation is None else f'{omit_deblur_correlation:.4f}')}"
                    f" · R_free={('n/a' if omit_deblur_rfree is None else f'{omit_deblur_rfree:.4f}')}",
                    subsystem="SharpED",
                )
            if cfg.symmetrize_deblurred_map and not use_superflip_xplor_modelfile:
                if self.stop_now.is_set():
                    raise RuntimeError("Immediate stop requested.")
                self._emit_cycle_progress(
                    cyc,
                    cfg.cycles,
                    progress_stages,
                    "Superflip symmetry averaging",
                    detail="running",
                    busy=True,
                )
                sym_prefix = f"cycle_{cyc:03d}_deblurred_symmetrized"
                self.log(f"  Superflip symmetry uses the {result_map_label('deblurred').lower()} XPLOR map as both modelfile and referencefile.")
                deblur_map = run_superflip_symmetrize_map(
                    cycle_dir=cycle_dir,
                    prefix=sym_prefix,
                    ref_ctx=ref_ctx,
                    input_map=deblur_map,
                    superflip_exe=cfg.superflip_exe,
                    output_format="xplor",
                    voxel=cfg.voxel,
                    searchsymmetry=cfg.searchsymmetry,
                    derivesymmetry=cfg.derivesymmetry,
                    log=self.log,
                    stop_event=self.stop_now,
                )
            deblur_prefix = f"cycle_{cyc:03d}_deblurred"
            deblur_edma_dir = cycle_dir / "edma_deblurred"
            if cfg.run_edma_deblurred and not use_superflip_xplor_modelfile:
                self._emit_cycle_progress(cyc, cfg.cycles, progress_stages, f"EDMA · {result_map_label('deblurred')}", busy=True)
                deblur_edma_cif = run_edma_on_xplor(
                    deblur_map, deblur_edma_dir, deblur_prefix, ref_ctx, cfg.plimit_deblur,
                    cfg.merge_distance, cfg.edma_exe, self.log,
                    self.stop_now, cfg.edma_maxima, cfg.edma_fullcell,
                    cfg.edma_numberofatoms, cfg.edma_centerofcharge, cfg.edma_chlimit,
                    cfg.edma_chlimlist, cfg.extra_edma_keywords, cfg.structure_export_format,
                    write_m40=cfg.jana_inflip is not None,
                )
            else:
                deblur_edma_dir.mkdir(parents=True, exist_ok=True)
                deblur_edma_cif = deblur_edma_dir / f"{deblur_prefix}_edma.cif"
                write_structure_bundle(deblur_edma_cif, ref_ctx.cell, ref_ctx.spacegroup, ref_ctx.spacegroup_hm, [], cfg.structure_export_format)
                if use_superflip_xplor_modelfile:
                    self.log(f"EDMA after {result_map_label('deblurred').lower()} skipped for Superflip XPLOR cycling; empty placeholder CIF/XYZ/PDB written.")
                else:
                    self.log(f"EDMA after {result_map_label('deblurred').lower()} disabled; empty placeholder CIF/XYZ/PDB written.")
            deblur_metric = nearest_metric_to_reference(deblur_edma_cif, ref_ctx) if cfg.run_edma_deblurred else None
            deblur_metric_text = "n/a" if deblur_metric is None else f"{float(deblur_metric):.3f}"
            deblur_recall: Optional[float] = None
            deblur_precision: Optional[float] = None
            deblur_heavy_atoms: Optional[float] = None
            if cfg.run_edma_deblurred:
                deblur_recall_precision = atom_recall_precision(deblur_edma_cif, ref_ctx, cfg.merge_distance)
                if deblur_recall_precision is not None:
                    deblur_recall, deblur_precision = deblur_recall_precision
                else:
                    deblur_heavy_atoms = count_heavy_atoms(deblur_edma_cif)
            self._emit_cycle_progress(cyc, cfg.cycles, progress_stages, "Finalizing cycle", detail="calculating metrics")
            self.log(
                f"[EDMA] Completed · {result_map_label('deblurred')} · RMSD={deblur_metric_text} Å\n"
                f"  output: {deblur_edma_cif}",
                subsystem="EDMA",
            )
            self.msg_queue.put(("structure_update", ("deblur", deblur_edma_cif)))
            result = CycleResult(
                cycle=cyc,
                model_source=model_source,
                model_in=model_for_sf,
                model_metric=model_metric,
                superflip_map=sf_map,
                superflip_edma_cif=sf_edma_cif,
                superflip_metric=sf_metric,
                deblur_map=deblur_map,
                deblur_edma_cif=deblur_edma_cif,
                deblur_metric=deblur_metric,
                superflip_saved_run=sf_log_metrics.saved_run,
                superflip_rvalue=sf_log_metrics.rvalue,
                superflip_peaks=sf_log_metrics.peaks,
                superflip_symm=sf_log_metrics.symm,
                superflip_derived_sg=sf_log_metrics.derived_sg,
                superflip_ref_match=sf_log_metrics.ref_match,
                superflip_fom=sf_log_metrics.fom,
                superflip_success_rate=sf_log_metrics.success_rate,
                superflip_mean_cycles=sf_log_metrics.mean_cycles,
                omit_superflip_correlation=omit_sf_correlation,
                omit_superflip_rfree=omit_sf_rfree,
                omit_deblur_correlation=omit_deblur_correlation,
                omit_deblur_rfree=omit_deblur_rfree,
                superflip_recall=sf_recall,
                superflip_precision=sf_precision,
                superflip_heavy_atom_count=sf_heavy_atoms,
                deblur_recall=deblur_recall,
                deblur_precision=deblur_precision,
                deblur_heavy_atom_count=deblur_heavy_atoms,
                powder_repartition_avg_change_percent=state.pending_powder_repartition_change_percent,
                intensity_correction_avg_change_percent=state.pending_intensity_correction_change_percent,
            )
            state.pending_powder_repartition_change_percent = None
            state.pending_intensity_correction_change_percent = None
            all_results.append(result)
            write_metrics_csv(cfg.work_dir / "metrics.csv", all_results)
            self.msg_queue.put(("result", result))
            if cyc < cfg.cycles:
                add_missing = cfg.map_feedback_missing_enabled and cyc >= cfg.map_feedback_missing_from_cycle and cfg.map_feedback_missing_percent_limit > 0
                correct_intensities = cfg.map_feedback_intensity_enabled and cyc >= cfg.map_feedback_intensity_from_cycle and cfg.map_feedback_intensity_damping > 0
                redistribute = cfg.redistribute_overlaps and cyc >= cfg.powder_redistribution_from_cycle and cfg.powder_wavelength > 0
                if cfg.redistribute_overlaps and cyc >= cfg.powder_redistribution_from_cycle and cfg.powder_wavelength <= 0:
                    self.log("Overlap repartitioning enabled but Wavelength is 0; skipping for this cycle.", level="WARNING")
                if add_missing or correct_intensities or redistribute:
                    if add_missing or correct_intensities:
                        state.current_reflections, state.pending_intensity_correction_change_percent = apply_map_feedback_to_reflections(
                            state.current_reflections,
                            configured_data_mode,
                            deblur_map,
                            ref_ctx.cell,
                            cfg.resolution_d_min,
                            add_missing,
                            cfg.map_feedback_missing_percent_limit,
                            correct_intensities,
                            cfg.map_feedback_intensity_damping,
                            cfg.map_feedback_intensity_max_i_over_sigma,
                            self.log,
                        )
                    if redistribute:
                        state.current_reflections, state.pending_powder_repartition_change_percent = redistribute_overlap_reflections(
                            state.current_reflections,
                            configured_data_mode,
                            deblur_map,
                            ref_ctx.cell,
                            cfg.powder_wavelength,
                            cfg.powder_separation_factor,
                            cfg.powder_redistribution_mix,
                            self.log,
                            log_path=cycle_dir / f"cycle_{cyc:03d}_powder_repartitioning.log",
                        )
                    feedback_hkl = cfg.work_dir / f"cycle_{cyc + 1:03d}_map_feedback_for_superflip.hkl"
                    n_feedback = write_observed_reflections(
                        feedback_hkl,
                        state.current_reflections,
                        cfg.i_over_sigma_min,
                        data_mode=configured_data_mode,
                        cell=ref_ctx.cell,
                        resolution_d_min=cfg.resolution_d_min,
                    )
                    observed_hkls[configured_data_mode] = feedback_hkl
                    self.log(f"Prepared map-feedback HKL for cycle {cyc + 1}: {feedback_hkl} ({n_feedback} reflections)")
            if use_xplor_modelfile:
                next_xplor_model = sf_map if use_superflip_xplor_modelfile else deblur_map
                effective_damping = effective_xplor_damping_factor(cfg.damping_factor)
                if state.current_model is not None and effective_damping > 1.0:
                    damped_model = cycle_dir / f"cycle_{cyc:03d}_damped_modelfile.xplor"
                    state.current_model = blend_xplor_maps(state.current_model, next_xplor_model, damped_model, effective_damping, self.log)
                else:
                    state.current_model = next_xplor_model
                state.current_model_metric = sf_metric if use_superflip_xplor_modelfile else deblur_metric
            elif use_cif_modelfile:
                if cfg.run_edma_deblurred:
                    state.current_model = deblur_edma_cif
                    state.current_model_metric = deblur_metric
                elif cfg.run_edma_superflip:
                    state.current_model = sf_edma_cif
                    state.current_model_metric = sf_metric
                else:
                    state.current_model = None
                    state.current_model_metric = None
            else:
                state.current_model = None
                state.current_model_metric = None
            if cfg.run_edma_deblurred and not use_superflip_xplor_modelfile and cif_has_readable_atoms(deblur_edma_cif):
                state.auto_reference_cif = deblur_edma_cif
            elif cfg.run_edma_superflip and cif_has_readable_atoms(sf_edma_cif):
                state.auto_reference_cif = sf_edma_cif
            else:
                state.auto_reference_cif = None
            state.auto_reference_xplor = deblur_map
            state.completed_cycles = cyc
            self.log(f"Cycle {cyc} complete.", level="SUCCESS")
            self.msg_queue.put(("progress", state.completed_cycles))
            self._emit_cycle_progress(
                cyc,
                cfg.cycles,
                progress_stages,
                "Finalizing cycle",
                detail="completed",
                complete=True,
            )
            if self.stop_after_cycle.is_set():
                self.msg_queue.put(("cancelled", state.completed_cycles))
                return
        self.msg_queue.put(("done", state.completed_cycles))

    def _run_sharped_recycle_cycles(self, state: PipelineState) -> None:
        """SharpED phase-recycling algorithm: Superflip runs at most once (or not at
        all in the random-start variant); every cycle deblurs the previous map with
        SharpED, reads phi_calc by FFT from that deblurred map for every measured
        hkl, and recomposes a map from |Fobs| + phi_calc for the next cycle."""
        cfg = state.cfg
        ref_ctx = state.ref_ctx
        reflections = state.current_reflections
        configured_data_mode = state.configured_data_mode
        sharped_elements = state.sharped_elements
        all_results = state.all_results
        random_start = normalize_reconstruction_mode(cfg.reconstruction_mode) == "sharped_recycle_random"
        progress_stages = ["Preparing cycle", "Superflip", "SharpED", "Phase calculation", "Finalizing cycle"]
        for cyc in range(state.completed_cycles + 1, cfg.cycles + 1):
            if self.stop_after_cycle.is_set():
                self.msg_queue.put(("cancelled", state.completed_cycles))
                return
            self._emit_cycle_progress(cyc, cfg.cycles, progress_stages, "Preparing cycle", detail="preparing input map")
            cycle_dir = cfg.work_dir / f"cycle_{cyc:03d}"; cycle_dir.mkdir(parents=True, exist_ok=True)
            self.log(f"=== Cycle {cyc} of {cfg.cycles} (SharpED phase recycling) ===", level="STEP")

            sf_log_metrics = SuperflipLogMetrics()
            if state.recycle_map is None:
                if random_start:
                    input_map = cycle_dir / f"cycle_{cyc:03d}_random_phase_start.xplor"
                    self.log("[Cycle 1] No Superflip: synthesizing a map from |Fobs| and independent random phases.", level="DETAIL")
                    compose_random_phase_map(input_map, reflections, configured_data_mode, ref_ctx.cell, ref_ctx.spacegroup, cfg.randomseed, f"cycle_{cyc:03d}_random_start", self.log)
                else:
                    self._emit_cycle_progress(cyc, cfg.cycles, progress_stages, "Superflip", sub_index=1, sub_total=1, detail="running", busy=True)
                    sf_prefix = f"cycle_{cyc:03d}_superflip"
                    observed_hkl_for_cycle = state.observed_hkls[configured_data_mode]
                    sf_map_format = normalize_map_export_format(cfg.map_export_format)
                    sf_export_ccp4 = sf_map_format == "ccp4"
                    sf_export_jana = sf_map_format == "jana"
                    reference_file_for_cycle: Optional[Path] = None
                    if state.referencefile_mode == "reference_cif":
                        reference_file_for_cycle = state.explicit_superflip_referencefile if state.explicit_superflip_referencefile is not None else ref_ctx.work_ref_cif
                    elif state.referencefile_mode in {"reference_xplor", "reference_density"}:
                        reference_file_for_cycle = state.explicit_superflip_referencefile if state.explicit_superflip_referencefile is not None else cfg.superflip_reference_xplor
                    input_map = run_superflip_cycle(
                        cycle_dir, sf_prefix, ref_ctx, observed_hkl_for_cycle, None, reference_file_for_cycle, "",
                        cfg.superflip_exe, cfg.perform_algorithm, "xplor", sf_export_jana, True, sf_export_ccp4, sf_export_jana,
                        cfg.voxel, cfg.bestdensities_count, cfg.bestdensities_metric, cfg.bestdensities_symmetry, cfg.polish,
                        cfg.maxcycles, cfg.repeatmode, cfg.randomseed, cfg.delta, cfg.weakratio, cfg.biso, configured_data_mode,
                        cfg.normalize, cfg.nresshells, cfg.missing, cfg.searchsymmetry, cfg.derivesymmetry, cfg.electrons,
                        cfg.dataitemwidths, cfg.extra_superflip_keywords, self.log, self.stop_now,
                    )
                    self.log(f"[Cycle 1] Superflip map: {input_map}")
                    if self.stop_now.is_set():
                        raise RuntimeError("Immediate stop requested.")
                    export_phased_reflections_from_map(
                        cfg.map_export_format, cycle_dir / sf_prefix, input_map, reflections,
                        cfg.i_over_sigma_min, configured_data_mode, ref_ctx.cell, cfg.resolution_d_min, self.log,
                    )
                    sf_log_metrics = parse_superflip_cycle_metrics(cycle_dir, sf_prefix)
            else:
                input_map = state.recycle_map

            if self.stop_now.is_set():
                raise RuntimeError("Immediate stop requested.")
            self._emit_cycle_progress(cyc, cfg.cycles, progress_stages, "SharpED", detail="preparing upload", busy=True)
            deblur_map = cycle_dir / f"cycle_{cyc:03d}_deblurred.xplor"
            run_sharped_deblur(
                input_map, deblur_map, cfg.sharped_base_url, cfg.sharped_api_token, cfg.sharped_model, sharped_elements,
                cfg.sharped_outres, cfg.sharped_max_upload_mb, cfg.sharped_timeout_seconds, cfg.sharped_poll_seconds,
                cfg.sharped_max_polls, self.log, self.stop_now,
                progress=lambda detail, cycle=cyc: self._emit_cycle_progress(
                    cycle, cfg.cycles, progress_stages, "SharpED", detail=detail, busy=detail != "completed",
                ),
            )
            self.log(f"{result_map_label('deblurred')}: {deblur_map}")
            if self.stop_now.is_set():
                raise RuntimeError("Immediate stop requested.")

            self._emit_cycle_progress(cyc, cfg.cycles, progress_stages, "Phase calculation", busy=True)
            composed_map = cycle_dir / f"cycle_{cyc:03d}_fobs_phicalc.xplor"
            compose_fobs_phicalc_map(composed_map, reflections, configured_data_mode, deblur_map, f"cycle_{cyc:03d}_fobs_phicalc", ref_ctx.spacegroup, self.log)
            self.log(f"Composed |Fobs|+phi_calc map: {composed_map}")
            map_correlation = xplor_map_correlation(composed_map, input_map)
            if map_correlation is not None:
                self.log(f"[Cycle {cyc}] Map correlation vs. previous cycle: {map_correlation:.4f}", level="DETAIL")
            state.recycle_map = composed_map

            is_final_cycle = cyc == cfg.cycles
            deblur_edma_cif = cycle_dir / f"cycle_{cyc:03d}_edma.cif"
            deblur_metric: Optional[float] = None
            if is_final_cycle and cfg.run_edma_recycle_final:
                self._emit_cycle_progress(cyc, cfg.cycles, progress_stages, "Finalizing cycle", detail="EDMA on final map", busy=True)
                edma_dir = cycle_dir / "edma_final"
                deblur_edma_cif = run_edma_on_xplor(
                    composed_map, edma_dir, f"cycle_{cyc:03d}_final", ref_ctx, cfg.plimit_deblur,
                    cfg.merge_distance, cfg.edma_exe, self.log,
                    self.stop_now, cfg.edma_maxima, cfg.edma_fullcell,
                    cfg.edma_numberofatoms, cfg.edma_centerofcharge, cfg.edma_chlimit,
                    cfg.edma_chlimlist, cfg.extra_edma_keywords, cfg.structure_export_format,
                    write_m40=cfg.jana_inflip is not None,
                )
                deblur_metric = nearest_metric_to_reference(deblur_edma_cif, ref_ctx)
                self.log(f"[EDMA] Completed · Final map · output: {deblur_edma_cif}", subsystem="EDMA")
                self.msg_queue.put(("structure_update", ("deblur", deblur_edma_cif)))
            else:
                write_structure_bundle(deblur_edma_cif, ref_ctx.cell, ref_ctx.spacegroup, ref_ctx.spacegroup_hm, [], cfg.structure_export_format)

            result = CycleResult(
                cycle=cyc,
                model_source="sharped_recycle_random" if random_start else "sharped_recycle",
                model_in=input_map,
                model_metric=None,
                superflip_map=input_map,
                superflip_edma_cif=deblur_edma_cif,
                superflip_metric=None,
                deblur_map=composed_map,
                deblur_edma_cif=deblur_edma_cif,
                deblur_metric=deblur_metric,
                superflip_saved_run=sf_log_metrics.saved_run,
                superflip_rvalue=sf_log_metrics.rvalue,
                superflip_peaks=sf_log_metrics.peaks,
                superflip_symm=sf_log_metrics.symm,
                superflip_derived_sg=sf_log_metrics.derived_sg,
                superflip_ref_match=sf_log_metrics.ref_match,
                superflip_fom=sf_log_metrics.fom,
                superflip_success_rate=sf_log_metrics.success_rate,
                superflip_mean_cycles=sf_log_metrics.mean_cycles,
                recycle_map_correlation=map_correlation,
            )
            all_results.append(result)
            write_metrics_csv(cfg.work_dir / "metrics.csv", all_results)
            self.msg_queue.put(("result", result))
            state.completed_cycles = cyc
            self.log(f"Cycle {cyc} complete.", level="SUCCESS")
            self.msg_queue.put(("progress", state.completed_cycles))
            self._emit_cycle_progress(cyc, cfg.cycles, progress_stages, "Finalizing cycle", detail="completed", complete=True)
            if self.stop_after_cycle.is_set():
                self.msg_queue.put(("cancelled", state.completed_cycles))
                return
        self.msg_queue.put(("done", state.completed_cycles))


class PhaseStudioSplash(QSplashScreen):
    def __init__(self) -> None:
        pixmap = QPixmap(500, 205)
        pixmap.fill(QColor("#ffffff"))
        super().__init__(pixmap)
        self.setObjectName("phaseStudioSplash")
        self.setFixedSize(500, 205)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 17)
        root.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(12)
        title_stack = QVBoxLayout()
        title_stack.setSpacing(2)
        title = QLabel(f"Phase Studio {__version__}")
        title.setObjectName("splashTitle")
        subtitle = QLabel("Superflip · SharpED · EDMA workflow")
        subtitle.setObjectName("splashSubtitle")
        title_stack.addWidget(title)
        title_stack.addWidget(subtitle)
        header.addLayout(title_stack, 1)
        logo = QLabel()
        logo.setObjectName("splashLogo")
        logo.setPixmap(create_phase_studio_logo_pixmap(72))
        logo.setAlignment(Qt.AlignRight | Qt.AlignTop)
        header.addWidget(logo, 0, Qt.AlignTop)
        root.addLayout(header)

        # Keep the title/status relationship compact while retaining a little
        # breathing room above the footer at the fixed splash size.
        root.addStretch(2)
        self.status_label = QLabel("Loading application…")
        self.status_label.setObjectName("splashStatus")
        root.addWidget(self.status_label)
        self.progress = QProgressBar()
        self.progress.setObjectName("splashProgress")
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        root.addWidget(self.progress)
        footer = QLabel("Crystallographic reconstruction workspace")
        footer.setObjectName("splashFooter")
        root.addWidget(footer)
        root.addStretch(1)

    def set_status(self, text: str) -> None:
        self.status_label.setText(str(text))


def create_startup_splash() -> PhaseStudioSplash:
    return PhaseStudioSplash()


def initialize_main_window(
    app: QApplication,
    splash: PhaseStudioSplash,
    window_factory: Callable[[], IterativeSuperflipPipelineQtGUI] = IterativeSuperflipPipelineQtGUI,
) -> Optional[IterativeSuperflipPipelineQtGUI]:
    try:
        splash.set_status("Initializing interface…")
        app.processEvents()
        win = window_factory()
        splash.set_status("Finalizing workspace…")
        app.processEvents()
        win.show()
        app.processEvents()
        splash.set_status("Ready")
        splash.finish(win)
        return win
    except Exception as exc:
        splash.close()
        app.processEvents()
        report = build_error_report(
            exc,
            subsystem="Startup",
            operation="Initialize Phase Studio",
            extra_details=traceback.format_exc(),
        )
        report = ErrorReport(
            category="startup",
            subsystem="Startup",
            title="Phase Studio could not start",
            summary="Application initialization failed.",
            guidance="Close this dialog, review the technical details, and restart Phase Studio.",
            technical_details=report.technical_details,
            operation=report.operation,
            severity="error",
        )
        show_phase_studio_error(None, report)
        return None


def main() -> None:
    app = QApplication(sys.argv)
    apply_phase_studio_style(app)
    splash = create_startup_splash()
    splash.show()
    app.processEvents()
    win = initialize_main_window(app, splash)
    if win is None:
        raise SystemExit(1)
    raise SystemExit(app.exec())

if __name__ == "__main__":
    main()
