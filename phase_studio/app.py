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
import hashlib
import html
import io
import json
import math
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, FrozenSet, List, Optional, Sequence, Tuple

import numpy as np

from phase_studio.displacement import (
    IsotropicDisplacementKind,
    biso_to_uiso,
    export_uiso_statistics,
    match_uiso_by_fractional_coordinate,
    normalize_export_uiso,
    normalize_jana_m40_isotropic_displacements,
    parse_edma_coo_isotropic_displacements,
    uiso_to_biso,
)
from phase_studio.edma_defaults import NORMAL_EDMA_THRESHOLD_SIGMA
from phase_studio.jana_density import origin_preserving_conversion_lines, validate_converted_density, validate_jana_density_pair
from phase_studio.structure_camera import StructureCameraController

try:
    from phase_studio.map_quality import (
        FrozenReflection,
        MapQualityMetrics,
        ResultCandidate,
        ResultRecommendation,
        ValidationContext,
        ValidationProfile,
        compute_map_quality,
        make_validation_context,
        profile_definition,
        recommend_best_result,
        scaled_amplitude_metrics,
        with_holdout_metrics,
        with_reference_metrics,
    )
except Exception:
    from map_quality import (  # type: ignore[no-redef]
        FrozenReflection,
        MapQualityMetrics,
        ResultCandidate,
        ResultRecommendation,
        ValidationContext,
        ValidationProfile,
        compute_map_quality,
        make_validation_context,
        profile_definition,
        recommend_best_result,
        scaled_amplitude_metrics,
        with_holdout_metrics,
        with_reference_metrics,
    )

try:
    from phase_studio.version import VERSION as __version__
except Exception:
    from version import VERSION as __version__

try:
    from phase_studio.xplor_io import XplorMap, read_xplor_map, write_xplor_map
except Exception:
    from xplor_io import XplorMap, read_xplor_map, write_xplor_map  # type: ignore[no-redef]

try:
    from phase_studio.sharped_tiling import decide_sharped_submission, run_tiled_sharped_inference
except Exception:
    from sharped_tiling import decide_sharped_submission, run_tiled_sharped_inference  # type: ignore[no-redef]

try:
    from phase_studio.autosolve_policy import AdaptiveCyclePolicy
except Exception:
    from autosolve_policy import AdaptiveCyclePolicy  # type: ignore[no-redef]

try:
    from phase_studio import autosolve_review as guided
except Exception:
    import autosolve_review as guided  # type: ignore[no-redef]

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
    from phase_studio.sharped_server_client import SharpEDServerClient, DEFAULT_SERVER_URL, reconcile_model_selection
except Exception:
    from sharped_server_client import SharpEDServerClient, DEFAULT_SERVER_URL, reconcile_model_selection

try:
    from phase_studio.sharped_map_scaling import (
        SHARPED_MAP_VALUE_EXPONENT_DEFAULT,
        SHARPED_MAP_VALUE_EXPONENT_MAX,
        SHARPED_MAP_VALUE_EXPONENT_MIN,
        apply_signed_power,
        describe_map_value_exponent,
        invert_signed_power,
        map_value_scaling_is_identity,
        normalize_map_value_exponent,
    )
except Exception:
    from sharped_map_scaling import (  # type: ignore[no-redef]
        SHARPED_MAP_VALUE_EXPONENT_DEFAULT,
        SHARPED_MAP_VALUE_EXPONENT_MAX,
        SHARPED_MAP_VALUE_EXPONENT_MIN,
        apply_signed_power,
        describe_map_value_exponent,
        invert_signed_power,
        map_value_scaling_is_identity,
        normalize_map_value_exponent,
    )

try:
    from phase_studio.process_utils import allow_external_process_foreground, no_console_popen_kwargs, text_encoding
except Exception:
    from process_utils import allow_external_process_foreground, no_console_popen_kwargs, text_encoding

try:
    from phase_studio.performance import TimingToken, WorkflowProfiler, profile_stage
except Exception:
    from performance import TimingToken, WorkflowProfiler, profile_stage

try:
    from phase_studio.inflip_io import (
        define_m80_inflip_legacy as define_m80_inflip_from_model,
        first_token_legacy as inflip_first_token,
        inflip_header_for_m80_legacy as inflip_header_for_m80,
        insert_before_fbegin_legacy as insert_before_fbegin,
        split_inflip_line_legacy as split_inflip_line,
        without_keywords_legacy as without_inflip_keywords,
    )
except Exception:
    from inflip_io import (  # type: ignore[no-redef]
        define_m80_inflip_legacy as define_m80_inflip_from_model,
        first_token_legacy as inflip_first_token,
        inflip_header_for_m80_legacy as inflip_header_for_m80,
        insert_before_fbegin_legacy as insert_before_fbegin,
        split_inflip_line_legacy as split_inflip_line,
        without_keywords_legacy as without_inflip_keywords,
    )

try:
    from phase_studio.input_context import (
        INPUT_MODE_EXTERNAL, INPUT_MODE_INFLIP, INPUT_MODE_INFLIP_OVERRIDES,
        INPUT_MODE_LABELS, METADATA_SOURCE_INFLIP, METADATA_SOURCE_LABELS,
        METADATA_SOURCE_MANUAL, METADATA_SOURCE_REFERENCE, active_jana_inflip,
        default_metadata_source, input_control_availability,
        jana_handoff_available, normalize_input_source_mode,
        normalize_metadata_source, reconcile_metadata_source,
        resolve_run_inputs, uses_embedded_hkl,
    )
except Exception:
    from input_context import (  # type: ignore[no-redef]
        INPUT_MODE_EXTERNAL, INPUT_MODE_INFLIP, INPUT_MODE_INFLIP_OVERRIDES,
        INPUT_MODE_LABELS, METADATA_SOURCE_INFLIP, METADATA_SOURCE_LABELS,
        METADATA_SOURCE_MANUAL, METADATA_SOURCE_REFERENCE, active_jana_inflip,
        default_metadata_source, input_control_availability,
        jana_handoff_available, normalize_input_source_mode,
        normalize_metadata_source, reconcile_metadata_source,
        resolve_run_inputs, uses_embedded_hkl,
    )

try:
    from phase_studio.result_selection import ResultSelectionDialog, create_result_preview_host, result_warning_callout_text
except Exception:
    from result_selection import ResultSelectionDialog, create_result_preview_host, result_warning_callout_text

try:
    from phase_studio.workflow_metrics_ui import (
        layout_metrics_figure,
        metrics_legend_width_pixels,
        render_metrics_tab,
        update_metrics_plot,
    )
except Exception:
    from workflow_metrics_ui import (  # type: ignore[no-redef]
        layout_metrics_figure,
        metrics_legend_width_pixels,
        render_metrics_tab,
        update_metrics_plot,
    )

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
    from PySide6.QtCore import Qt, QTimer, QSettings, QStandardPaths, QUrl, QPoint, QRect, QRectF, QSize
    from PySide6.QtGui import QColor, QDesktopServices, QFont, QFontDatabase, QFontInfo, QGuiApplication, QIcon, QKeySequence, QPainter, QPen, QPixmap, QShortcut, QTextBlockFormat, QTextCharFormat, QTextCursor
    from PySide6.QtWidgets import (
        QApplication, QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame,
        QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLayout, QLineEdit, QMainWindow, QMessageBox,
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
    # Canonical internal isotropic displacement representation. Exporters
    # convert explicitly when their protocol requires Biso (PDB).
    uiso_angstrom2: Optional[float] = None


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
    # 2.0.0: "autosolve" is a third Wizard launch mode. It always runs the
    # same ordinary-cycle mechanism as "phase_recycling" (reconstruction_mode
    # stays "superflip"), but drives the run itself via an adaptive cycle
    # policy and an automatic Jana2020 handoff -- no result selector, no
    # manual "Pass to Jana2020" click. See _autosolve_on_run_done() below.
    launch_mode: str = "standalone"
    wizard_map_source: str = ""  # "superflip" or "deblurred"; only meaningful when launch_mode == "phase_recycling"
    autosolve_option: str = ""  # "A" or "B"; only meaningful when launch_mode == "autosolve"


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
class ProjectComposition:
    """One run-wide composition authority, with its scientific meaning."""

    value: str
    source: str
    semantic_type: str
    confidence: str


@dataclass(frozen=True)
class CrystalMetadata:
    """Validated crystallographic metadata selected for one pipeline run."""

    cell: gemmi.UnitCell
    spacegroup: gemmi.SpaceGroup
    spacegroup_hm: str
    composition: str
    source: str
    source_path: Optional[Path] = None
    project_composition: Optional[ProjectComposition] = None


@dataclass(frozen=True)
class StructureJobUpdate:
    """Immutable worker-to-GUI state for one automatic EDMA candidate."""

    run_id: str
    source: str
    cycle: int
    map_path: Path
    map_sha256: str
    threshold: float
    request_id: str
    generation: int
    status: str
    structure_path: Optional[Path] = None
    structure_sha256: str = ""
    edma_asu_composition: str = ""
    superflip_initialization: str = ""
    reflection_input_provenance: str = ""

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
    subsystem: str = "Workflow"
    category: str = "USER_PROGRESS"
    timestamp: str = ""


class RunDiagnosticLog:
    """Complete timestamped per-run forensic log, safe for worker threads."""

    def __init__(self, path: Path, cfg: "RunConfig") -> None:
        self._lock = threading.Lock()
        jana_inflip = getattr(cfg, "jana_inflip", None)
        project = Path(jana_inflip).resolve().parent if jana_inflip else None
        requested_path = Path(path).expanduser().resolve()
        run_id = str(getattr(cfg, "run_id", "") or requested_path.parent.name)
        self.path = requested_path
        self.fallback_reason = ""
        self.persistent = True
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._stream = self.path.open("a", encoding="utf-8", errors="replace")
        except OSError as exc:
            # A diagnostic failure must never stop the scientific run or
            # redirect into the installation tree.  The OS temp directory is
            # the final writable runtime fallback.
            self.fallback_reason = str(exc)
            self.path = (
                Path(tempfile.gettempdir()) / "PhaseStudio" / "logs" / run_id / "log.txt"
            ).resolve()
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._stream = self.path.open("a", encoding="utf-8", errors="replace")
            except OSError as fallback_exc:
                self.fallback_reason += f"; runtime fallback unavailable: {fallback_exc}"
                self.persistent = False
                self._stream = io.StringIO()
        input_path = Path(jana_inflip).resolve() if jana_inflip else getattr(cfg, "hkl", "not recorded")
        run_directory = Path(getattr(cfg, "work_dir", self.path.parent)).resolve()
        superflip_exe = Path(getattr(cfg, "superflip_exe", "not recorded")).expanduser()
        edma_exe = Path(getattr(cfg, "edma_exe", "not recorded")).expanduser()
        jana_root = (
            superflip_exe.parent.parent
            if superflip_exe.parent.name.casefold() == "superflip" else "not resolved"
        )
        integration_root = (
            Path(sys.executable).resolve().parent
            if getattr(sys, "frozen", False) else "development source tree"
        )
        project_log = project / "log.txt" if project is not None else "standalone"
        sharped_endpoint = str(getattr(cfg, "sharped_base_url", "") or "not configured")
        self._stream.write("\n" + "=" * 72 + "\n")
        self._stream.write(f"Phase Studio version: {__version__}\n")
        self._stream.write(f"Started: {datetime.now().astimezone().isoformat(timespec='seconds')}\n")
        self._stream.write(f"Run: {run_id}\n")
        self._stream.write(f"Jana project directory: {project if project is not None else 'standalone'}\n")
        self._stream.write(f"Project log: {project_log}\n")
        self._stream.write(f"Run log: {self.path}\n")
        self._stream.write(f"Input .inflip: {input_path}\n")
        self._stream.write(f"Run directory: {run_directory}\n")
        self._stream.write(f"Jana root: {jana_root}\n")
        self._stream.write(f"Phase Studio integration root: {integration_root}\n")
        self._stream.write(f"Superflip executable: {superflip_exe}\n")
        self._stream.write(f"EDMA executable: {edma_exe}\n")
        self._stream.write(f"SharpED endpoint: {sharped_endpoint}\n")
        if self.fallback_reason:
            self._stream.write(
                f"WARNING: requested run log {requested_path} was unavailable: {self.fallback_reason}\n"
            )
        self._stream.write("=" * 72 + "\n")
        self._stream.flush()
        if project is not None:
            # Keep the easily discoverable project-level wrapper log as the
            # session index; full forensic traffic remains in this run log.
            try:
                project_log.parent.mkdir(parents=True, exist_ok=True)
                with project_log.open("a", encoding="utf-8", errors="replace") as stream:
                    stream.write("\n" + "=" * 60 + "\n")
                    stream.write(
                        f"Phase Studio {__version__} · {run_id} · "
                        f"{datetime.now().astimezone().isoformat(timespec='seconds')}\n"
                    )
                    stream.write(f"Jana project directory: {project}\n")
                    stream.write(f"Input .inflip: {Path(jana_inflip).resolve()}\n")
                    stream.write(f"Run directory: {run_directory}\n")
                    stream.write(f"Run log: {self.path}\n")
                    stream.write("=" * 60 + "\n")
            except OSError as exc:
                self._stream.write(
                    f"WARNING: project log {project_log} could not be updated: {exc}\n"
                )
                self._stream.flush()

    def write(self, record: ExecutionLogRecord) -> None:
        timestamp = record.timestamp or datetime.now().astimezone().strftime("%H:%M:%S.%f")[:-3]
        line = f"{timestamp} [{record.category}][{record.subsystem}] {record.text}\n"
        with self._lock:
            try:
                self._stream.write(line)
                self._stream.flush()
            except OSError:
                # Logging is ancillary; worker/UI progress must continue.
                pass

    def close(self) -> None:
        with self._lock:
            try:
                self._stream.close()
            except Exception:
                pass


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
            resolved_subsystem = "Workflow"

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
    if resolved_level == "ERROR":
        category = "ERROR"
    elif resolved_level == "WARNING":
        category = "WARNING"
    elif resolved_level in {"DETAIL", "COMMAND"}:
        category = "DIAGNOSTIC"
    elif resolved_level == "SUCCESS":
        category = "SCIENTIFIC_RESULT"
    else:
        category = "USER_PROGRESS"
    if "superflip normalize value" in lowered and resolved_level != "ERROR":
        # Expected compatibility behavior, even when the originating caller
        # used WARNING before semantic GUI filtering was introduced.
        category = "DIAGNOSTIC"
    forensic_markers = (
        "sha-256", "dimensions ", "index ranges", "axes ", "min/max ",
        "mean/std ", "current working dir", "executable dir", "compatibility",
        "ignored duplicate", "effective old factor", "plimit", "output path:",
        "tile_", "job submitted", "downloading result to", "tls trust:",
        "temporary xplor", "_in.xplor", "_out.xplor", "output:",
    )
    if category not in {"WARNING", "ERROR"} and re.search(
        r"(?:^|\])\s*processing(?:…|\.\.\.)?$", stripped, re.IGNORECASE,
    ):
        category = "DIAGNOSTIC"
    has_absolute_path = bool(re.search(r"(?:[A-Za-z]:[\\/]|/(?:home|tmp|Users)/)", text))
    if category not in {"WARNING", "ERROR"} and (
        any(marker in lowered for marker in forensic_markers) or has_absolute_path
    ):
        category = "DIAGNOSTIC"
    return ExecutionLogRecord(
        text=text, level=resolved_level, subsystem=resolved_subsystem, category=category,
        timestamp=datetime.now().astimezone().strftime("%H:%M:%S.%f")[:-3],
    )


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
    validation_profile: str = ValidationProfile.REFERENCE_FREE.value
    superflip_quality: Optional[MapQualityMetrics] = None
    deblur_quality: Optional[MapQualityMetrics] = None
    # Provenance (2.0.1): the exact SharpED model and the EDMA thresholds this
    # cycle actually used, stamped by _record_completed_cycle_result.
    sharped_model: str = ""
    superflip_edma_sigma: Optional[float] = None
    deblur_edma_sigma: Optional[float] = None
    superflip_edma_enabled: bool = True
    deblur_edma_enabled: bool = True
    run_id: str = ""


@dataclass
class OrdinaryCycleCheckpoint:
    """Completed work for the one ordinary cycle that is still in progress.

    A checkpoint is deliberately limited to the existing ordinary pipeline.
    It records the real stage outputs needed by the next stage; completed
    ``CycleResult`` objects remain the authority for finalized cycles.
    """

    cycle: int
    superflip_completed: bool = False
    superflip_edma_completed: bool = False
    superflip_validation_completed: bool = False
    sharped_completed: bool = False
    sharped_edma_completed: bool = False
    validation_completed: bool = False
    result_recorded: bool = False
    feedback_completed: bool = False
    continuation_completed: bool = False
    values: Dict[str, object] = field(default_factory=dict)

    def first_incomplete_stage(self) -> str:
        for complete, label in (
            (self.superflip_completed, "Superflip"),
            (self.superflip_edma_completed, "EDMA / Superflip"),
            (self.superflip_validation_completed, "Superflip validation"),
            (self.sharped_completed, "SharpED"),
            (self.sharped_edma_completed, "EDMA / SharpED"),
            (self.validation_completed, "validation"),
            (self.result_recorded, "reports"),
            (self.feedback_completed, "Map Feedback"),
            (self.continuation_completed, "cycle finalization"),
        ):
            if not complete:
                return label
        return "cycle finalization"

    def invalidate_from(self, stage: str) -> None:
        """Discard a missing stage output and every dependent checkpoint."""
        order = (
            "superflip", "superflip_edma", "superflip_validation", "sharped",
            "sharped_edma", "validation", "result", "feedback", "continuation",
        )
        flags = {
            "superflip": "superflip_completed",
            "superflip_edma": "superflip_edma_completed",
            "superflip_validation": "superflip_validation_completed",
            "sharped": "sharped_completed",
            "sharped_edma": "sharped_edma_completed",
            "validation": "validation_completed",
            "result": "result_recorded",
            "feedback": "feedback_completed",
            "continuation": "continuation_completed",
        }
        start = order.index(stage)
        for name in order[start:]:
            setattr(self, flags[name], False)


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
    sharped_api_token: str = field(repr=False)
    sharped_model: str
    sharped_elements: str
    sharped_outres: float
    sharped_map_value_exponent: float
    sharped_max_upload_mb: float
    sharped_timeout_seconds: int
    sharped_poll_seconds: int
    sharped_max_polls: int
    # 2.0.0: "manual" (the configured plimit_* multipliers, unchanged) or
    # "auto" (per-map data-supported calibration, phase_studio/
    # edma_threshold.py). Only Autosolve sets "auto"; every other launch keeps
    # the established manual behavior.
    edma_threshold_mode: str = "manual"
    run_id: str = ""


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
    validation_context: Optional[ValidationContext] = None
    pending_powder_repartition_change_percent: Optional[float] = None
    pending_intensity_correction_change_percent: Optional[float] = None
    performance_profiler: Optional[WorkflowProfiler] = None
    performance_root: Optional[TimingToken] = None
    ordinary_cycle_checkpoint: Optional[OrdinaryCycleCheckpoint] = None
    # Guided Autosolve (2.0.1): set when the user seeds a refinement block,
    # consumed by that block's first cycle so its log names the real source.
    refinement_seed_note: Optional[str] = None
    run_id: str = ""
    sharped_models_by_map: Dict[str, str] = field(default_factory=dict)


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
        stage_name = {
            "EDMA · Superflip map": "EDMA · Charge-flipping solution",
            "EDMA · SharpED map": "EDMA · Structure prediction",
        }.get(self.stage_name, self.stage_name)
        parts = [f"Cycle {self.cycle_index} of {self.cycle_total}", stage_name]
        if self.detail:
            # Call sites pass lowercase detail phrases ("running", "preparing
            # upload", ...); capitalize just the leading letter here, in one
            # place, for sentence-case display rather than editing every
            # _emit_cycle_progress() call site individually.
            parts.append(self.detail[:1].upper() + self.detail[1:])
        return " · ".join(part for part in parts if part)


@dataclass(frozen=True)
class RunScopedPayload:
    run_id: str
    payload: object


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
    diagnostics: object = None
    format_verified: bool = True

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
    diagnostics: object = None
    format_verified: bool = True

REFERENCE_STRUCTURE_SUFFIXES = {".cif", ".ins", ".res"}
REFERENCE_DENSITY_SUFFIXES = {".xplor", ".ccp4", ".map", ".m80", ".m81", ".jana"}
REFERENCE_FILE_SUFFIXES = REFERENCE_STRUCTURE_SUFFIXES | REFERENCE_DENSITY_SUFFIXES

# --- Authoritative file-dialog filters ---------------------------------------
# Every model/reference selector in the application and in the Jana2020 Wizard
# builds its filter here, from the suffix sets above, so no selector can drift
# into offering a format the code cannot actually handle.
#
# What each set is derived from, audited against the real code paths:
#
#   REFERENCE_STRUCTURE_SUFFIXES  structures parsed for reference comparison
#                                 (parse_cif_atoms / reference handling)
#   REFERENCE_DENSITY_SUFFIXES    density maps accepted as a reference
#   SUPERFLIP_MODEL_SUFFIXES      what run_superflip_cycle() will actually pass
#                                 to Superflip as a modelfile -- .xplor (through
#                                 normalize_xplor_for_superflip_modelfile), .cif
#                                 and .ccp4. Anything else raises there, so
#                                 nothing else may be offered.
#   WRAPPER_REFERENCE_SUFFIXES    the narrower set the single-pass Jana2020
#                                 wrapper validates (.cif / .xplor). It is NOT a
#                                 filter oversight: the wrapper rejects the rest.
SUPERFLIP_MODEL_SUFFIXES = {".xplor", ".ccp4", ".cif"}
WRAPPER_REFERENCE_SUFFIXES = {".cif", ".xplor"}


def _filter_group(label: str, suffixes: "Iterable[str]") -> str:
    patterns = " ".join("*" + s for s in sorted(suffixes))
    return f"{label} ({patterns})"


def supported_structure_filters() -> str:
    """File-dialog filter for structure models only."""
    return _filter_group("Structure models", REFERENCE_STRUCTURE_SUFFIXES)


def supported_density_map_filters() -> str:
    """File-dialog filter for density maps only."""
    return _filter_group("Density maps", REFERENCE_DENSITY_SUFFIXES)


def supported_reference_filters() -> str:
    """Filter for a reference model: a structure OR a density map."""
    return ";;".join([
        _filter_group("All supported reference files", REFERENCE_FILE_SUFFIXES),
        supported_structure_filters(),
        supported_density_map_filters(),
        "All files (*)",
    ])


def supported_model_filters() -> str:
    """Filter for an initial/recycled Superflip model file.

    Exactly the formats run_superflip_cycle() accepts as a modelfile.
    """
    structures = SUPERFLIP_MODEL_SUFFIXES & REFERENCE_STRUCTURE_SUFFIXES
    maps = SUPERFLIP_MODEL_SUFFIXES - REFERENCE_STRUCTURE_SUFFIXES
    return ";;".join([
        _filter_group("All supported model files", SUPERFLIP_MODEL_SUFFIXES),
        _filter_group("Density maps", maps),
        _filter_group("Structure models", structures),
        "All files (*)",
    ])


def supported_wrapper_reference_filters() -> str:
    """Reference filter for the single-pass Jana2020 wrapper workflows.

    Deliberately narrower than supported_reference_filters(): the wrapper
    validates the selection against .cif/.xplor and rejects anything else, so
    offering more here would only produce a late error.
    """
    return ";;".join([
        _filter_group("Supported reference files", WRAPPER_REFERENCE_SUFFIXES),
        _filter_group("Structure models", WRAPPER_REFERENCE_SUFFIXES & REFERENCE_STRUCTURE_SUFFIXES),
        _filter_group("Density maps", WRAPPER_REFERENCE_SUFFIXES & REFERENCE_DENSITY_SUFFIXES),
        "All files (*)",
    ])


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
            expanded.append(AtomSite(
                label=f"{atom.label}_{op_idx+1}", element=atom.element, frac=frac,
                density=atom.density, uiso_angstrom2=atom.uiso_angstrom2,
            ))
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


def display_composition_from_formula(formula: str) -> str:
    """Normalize display composition while retaining H/D as scientific data."""
    text = str(formula or "").strip().strip("'\"")
    if not text or text in {".", "?"}:
        return ""
    parts: List[str] = []
    for elem, count_text in re.findall(r"([A-Z][a-z]?|D)\s*([0-9]+(?:\.[0-9]+)?)?", text):
        elem = clean_element_symbol(elem)
        count = float(count_text) if count_text else 1.0
        count_str = str(int(round(count))) if abs(count - round(count)) < 1e-2 else f"{count:g}"
        parts.append(f"{elem}{count_str}")
    return " ".join(parts)


def _jana_canonical_project_stem(inflip_path: Path) -> Path:
    """Return Jana's project stem for a launcher/solution ``.inflip``."""
    path = Path(inflip_path).expanduser().resolve()
    stem = path.stem
    for suffix in ("_Superflip", "_Sol"):
        if stem.casefold().endswith(suffix.casefold()):
            canonical = path.with_name(stem[:-len(suffix)] + path.suffix)
            if canonical.is_file():
                return canonical.with_suffix("")
    return path.with_suffix("")


def jana_model_composition(inflip_path: Path, spacegroup: gemmi.SpaceGroup) -> Optional[ProjectComposition]:
    """Read Jana's live model composition from its m40/m50 project pair.

    The m40 header is Jana's authoritative model-site count and each site
    names an atom type from m50's ``atlist``.  Space-group multiplicity and
    m50's explicit ``unitsnumb`` convert those occupied sites to Jana's
    composition per declared formula unit.  No EDMA peaks, displayed atoms,
    GCD reduction, or guessed Z value participate.
    """
    stem = _jana_canonical_project_stem(Path(inflip_path))
    m40 = stem.with_suffix(".m40")
    m50 = stem.with_suffix(".m50")
    if not (m40.is_file() and m50.is_file()):
        return None
    context_lines = m50.read_text(encoding=text_encoding(), errors="replace").splitlines()
    atom_types: List[str] = []
    units = 0.0
    for raw in context_lines:
        parts = raw.split()
        if not parts:
            continue
        if parts[0].casefold() == "atlist":
            atom_types = [clean_element_symbol(item) for item in parts[1:]]
        elif parts[0].casefold() == "unitsnumb" and len(parts) > 1:
            try:
                units = float(parts[1])
            except ValueError:
                units = 0.0
    if not atom_types or units <= 0:
        return None
    lines = m40.read_text(encoding=text_encoding(), errors="replace").splitlines()
    try:
        site_count = int(lines[0].split()[0])
    except (IndexError, ValueError):
        return None
    counts: Dict[str, float] = collections.OrderedDict((element, 0.0) for element in atom_types)
    parsed = 0
    number = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?")
    for raw in lines[5:]:
        if parsed >= site_count or raw.startswith("-"):
            break
        label = raw[:10].strip()
        if not label or not label[0].isalpha():
            continue
        values = number.findall(raw[10:])
        if len(values) < 6:
            continue
        try:
            type_index = int(float(values[0])) - 1
            occupancy = float(values[2])
            frac = np.asarray([float(values[3]), float(values[4]), float(values[5])], dtype=np.float64)
        except (ValueError, IndexError):
            continue
        if not 0 <= type_index < len(atom_types) or occupancy <= 0:
            continue
        # gemmi already removes coincident special-position images.
        probe = AtomSite(label=label, element=atom_types[type_index], frac=wrap_frac(frac))
        multiplicity = len(expand_atoms_by_symmetry([probe], spacegroup))
        counts[atom_types[type_index]] += occupancy * multiplicity / units
        parsed += 1
    if parsed != site_count:
        return None
    parts: List[str] = []
    for element, amount in counts.items():
        if amount <= 1.0e-8:
            continue
        shown = str(int(round(amount))) if abs(amount - round(amount)) < 1.0e-5 else f"{amount:g}"
        parts.append(f"{element}{shown}")
    if not parts:
        return None
    return ProjectComposition(
        value=" ".join(parts), source=str(m40), semantic_type="jana_model", confidence="authoritative",
    )


def project_composition_for_metadata(metadata: Optional[CrystalMetadata]) -> ProjectComposition:
    """Return the single composition authority shared by every viewer."""
    if metadata is not None and metadata.project_composition is not None:
        return metadata.project_composition
    if metadata is not None and metadata.composition:
        semantic = "superflip_search" if metadata.source == METADATA_SOURCE_INFLIP else "chemical_formula"
        confidence = "search_only" if semantic == "superflip_search" else "authoritative"
        return ProjectComposition(metadata.composition, str(metadata.source_path or metadata.source), semantic, confidence)
    return ProjectComposition("", "", "unavailable", "unavailable")


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
        iuiso = lower.index("_atom_site_u_iso_or_equiv") if "_atom_site_u_iso_or_equiv" in lower else None
        ibiso = lower.index("_atom_site_b_iso_or_equiv") if "_atom_site_b_iso_or_equiv" in lower else None
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
                    uiso = None
                    if iuiso is not None and len(parts) > iuiso:
                        parsed_uiso = parse_cif_number(parts[iuiso], math.nan)
                        if np.isfinite(parsed_uiso) and parsed_uiso >= 0.0:
                            uiso = float(parsed_uiso)
                    elif ibiso is not None and len(parts) > ibiso:
                        parsed_biso = parse_cif_number(parts[ibiso], math.nan)
                        if np.isfinite(parsed_biso) and parsed_biso >= 0.0:
                            uiso = biso_to_uiso(float(parsed_biso))
                    atoms.append(AtomSite(label=label, element=elem, frac=frac, uiso_angstrom2=uiso))
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
                gemmi_uiso = getattr(site, "u_iso", None)
                uiso = float(gemmi_uiso) if gemmi_uiso is not None and np.isfinite(gemmi_uiso) and gemmi_uiso >= 0.0 else None
                atoms.append(AtomSite(label=site.label, element=elem, frac=frac, uiso_angstrom2=uiso))
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


EDMA_ASU_EQUIVALENCE_TOLERANCE_ANGSTROM = 0.05


def edma_asu_atoms(
    atoms: Sequence[AtomSite], cell: gemmi.UnitCell, spacegroup: gemmi.SpaceGroup,
    tolerance_angstrom: float = EDMA_ASU_EQUIVALENCE_TOLERANCE_ANGSTROM,
) -> List[AtomSite]:
    """Reduce EDMA coordinates to element-sensitive symmetry orbits.

    EDMA normally writes independent maxima, but ``fullcell yes`` and some
    imported artifacts can contain symmetry copies.  Compare fractional
    coordinates periodically in Cartesian distance and keep one input site
    per orbit.  This also collapses repeated images of a special-position
    site.  It deliberately does not perform formula/GCD normalization.
    """
    operations = full_spacegroup_ops(spacegroup)
    if not operations:
        operations = [gemmi.Op("x,y,z")]
    representatives: List[AtomSite] = []
    representative_orbits: List[List[np.ndarray]] = []
    tolerance = max(1.0e-6, float(tolerance_angstrom))
    for atom in atoms:
        element = clean_element_symbol(atom.element)
        frac = wrap_frac(atom.frac)
        equivalent = False
        for old, orbit in zip(representatives, representative_orbits):
            if clean_element_symbol(old.element) != element:
                continue
            if any(frac_distance_angstrom(cell, frac, mate) <= tolerance for mate in orbit):
                equivalent = True
                break
        if equivalent:
            continue
        representatives.append(AtomSite(
            label=atom.label, element=element, frac=frac, density=atom.density,
            uiso_angstrom2=atom.uiso_angstrom2,
        ))
        representative_orbits.append([apply_gemmi_op(op, frac) for op in operations])
    return representatives


def edma_asu_composition_from_cif(path: Optional[Path]) -> str:
    """Return the selected EDMA artifact's asymmetric-unit site counts."""
    if path is None or not Path(path).is_file():
        return ""
    try:
        resolved = Path(path)
        atoms = parse_cif_atoms(resolved)
        cell, spacegroup, _hm = parse_cif_cell_and_sg(resolved)
        independent = edma_asu_atoms(atoms, cell, spacegroup)
    except Exception:
        return ""
    counts: Dict[str, int] = collections.OrderedDict()
    for atom in independent:
        element = clean_element_symbol(atom.element)
        counts[element] = counts.get(element, 0) + 1
    return " ".join(f"{element}{count}" for element, count in counts.items())


def structure_formula_from_cif(path: Optional[Path]) -> str:
    """Return formula metadata belonging to one concrete structure.

    The declared CIF formula is kept when present. Otherwise the formula is
    derived from that CIF's own independent atom records. No input,
    reference, run-global, or display-expanded composition is consulted.
    """
    if path is None:
        return ""
    resolved = Path(path)
    if not resolved.is_file():
        return ""
    declared = composition_from_formula(
        raw_cif_value(resolved, ["_chemical_formula_sum", "_chemical_formula_moiety"])
    )
    if declared:
        return declared
    try:
        atoms = parse_cif_atoms(resolved)
    except Exception:
        return ""
    return composition_from_atoms(atoms) if atoms else ""


def structure_composition_display(
    path: Optional[Path], authoritative_composition: str = "",
    authoritative_label: str = "Composition",
) -> Tuple[str, str]:
    """Return the honest label/value pair used by scientific viewers.

    Jana/input composition is the crystallographic authority.  A CIF's own
    declared formula is the next-best authority.  Counting coordinate rows is
    explicitly labelled as detected composition and retains H/He because
    renderer visibility is unrelated to scientific composition.
    """
    authoritative = display_composition_from_formula(str(authoritative_composition or ""))
    if authoritative:
        return str(authoritative_label or "Composition"), authoritative
    resolved = Path(path) if path is not None else None
    if resolved is None or not resolved.is_file():
        return "Composition", ""
    declared = display_composition_from_formula(
        raw_cif_value(resolved, ["_chemical_formula_sum", "_chemical_formula_moiety"]),
    )
    if declared:
        return "Composition", declared
    try:
        atoms = parse_cif_atoms(resolved)
    except Exception:
        return "Composition", ""
    counts: Dict[str, int] = collections.Counter()
    order: List[str] = []
    for atom in atoms:
        element = clean_element_symbol(atom.element)
        if element not in counts:
            order.append(element)
        counts[element] += 1
    detected = " ".join(f"{element}{counts[element]}" for element in order if counts[element])
    return "Detected composition", detected


def crystal_metadata_composition_label(metadata: Optional[CrystalMetadata]) -> str:
    """Name the scientific concept represented by CrystalMetadata.composition."""
    authority = project_composition_for_metadata(metadata)
    if authority.semantic_type == "superflip_search":
        return "Superflip input composition"
    return "Composition"

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
                expanded.append(AtomSite(
                    label=atom.label, element=elem, frac=frac, density=atom.density,
                    uiso_angstrom2=atom.uiso_angstrom2,
                ))
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
        project_composition=ProjectComposition(
            composition, str(path), "chemical_formula", "authoritative",
        ),
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
                out.append(AtomSite(
                    label=a.label, element=a.element, frac=f, density=a.density,
                    uiso_angstrom2=a.uiso_angstrom2,
                ))
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

def atom_reference_match_metrics(
    model_cif: Optional[Path], ref_ctx: ReferenceContext, merge_distance: float, same_element: bool = True,
) -> Optional[Tuple[Optional[float], Optional[float], int, int]]:
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
    model, returns (0.0, None, 0, 0) -- recall is 0, precision has no
    denominator (nothing was found to be right or wrong about).  The final
    two values are model-side true positives and false positives for reporting.
    """
    def heavy(atoms: Sequence[AtomSite]) -> List[AtomSite]:
        return [a for a in atoms if clean_element_symbol(a.element) not in {"H", "He"}]
    if not ref_ctx.atoms:
        return None
    ref_full = heavy(expanded_unique_atoms(heavy(ref_ctx.atoms), ref_ctx.cell, ref_ctx.spacegroup))
    if not ref_full:
        return None
    model_atoms = heavy(parse_cif_atoms(Path(model_cif))) if model_cif is not None and Path(model_cif).is_file() else []
    if not model_atoms:
        return (0.0, None, 0, 0)
    _, model_sg, _ = parse_cif_cell_and_sg(Path(model_cif))
    model_full = heavy(expanded_unique_atoms(model_atoms, ref_ctx.cell, model_sg))
    if not model_full:
        return (0.0, None, 0, 0)
    def nearest_distance(a: AtomSite, candidates: Sequence[AtomSite]) -> Optional[float]:
        same = [b for b in candidates if not same_element or clean_element_symbol(a.element) == clean_element_symbol(b.element)]
        if not same:
            return None
        return min(frac_distance_angstrom(ref_ctx.cell, a.frac, b.frac) for b in same)
    matched_ref = sum(1 for a in ref_full if (d := nearest_distance(a, model_full)) is not None and d <= merge_distance)
    matched_model = sum(1 for a in model_full if (d := nearest_distance(a, ref_full)) is not None and d <= merge_distance)
    recall = matched_ref / len(ref_full)
    precision = matched_model / len(model_full)
    return (recall, precision, matched_model, len(model_full) - matched_model)


def atom_recall_precision(
    model_cif: Optional[Path], ref_ctx: ReferenceContext, merge_distance: float, same_element: bool = True,
) -> Optional[Tuple[Optional[float], Optional[float]]]:
    """Backward-compatible recall/precision view of the shared match result."""
    metrics = atom_reference_match_metrics(model_cif, ref_ctx, merge_distance, same_element)
    if metrics is None:
        return None
    return metrics[0], metrics[1]

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
    _loaded: Optional[HklLoadResult] = None,
) -> HklAnalysis:
    mode = normalize_reflection_data_mode(data_mode)
    format_verified = mode != REFLECTION_DATA_MODE_AUTO
    if mode == REFLECTION_DATA_MODE_AUTO:
        mode = resolve_reflection_data_mode(hkl_path, mode)
    value_col, sigma_col, include_000 = reflection_columns_for_mode(mode)
    from phase_studio.hkl_diagnostics import read_diagnostic_reflections, build_diagnostics, shell_statistics, validate_cell, check_cancelled
    check_cancelled()
    validate_cell(cell)
    raw = _loaded.reflections if _loaded is not None else list(read_diagnostic_reflections(hkl_path, mode)[0])
    unique = _loaded.unique_reflections if _loaded is not None else merge_duplicate_reflections(raw)
    gstar = reciprocal_metric_tensor(cell)
    unique_hkls = np.asarray([[int(r.h), int(r.k), int(r.l)] for r in unique], dtype=np.int32)
    unique_stls = hkl_stl_array_from_metric(gstar, unique_hkls)
    nonzero = np.any(unique_hkls != 0, axis=1) if unique_hkls.size else np.asarray([], dtype=bool)
    valid_stl = np.isfinite(unique_stls) & (unique_stls > 0.0) & nonzero
    ds = (1.0 / (2.0 * unique_stls[valid_stl])).astype(np.float64) if np.any(valid_stl) else np.asarray([], dtype=np.float64)
    if ds.size == 0:
        raise ValueError("No non-zero HKL reflections with finite d-spacing were found.")
    d_min = float(np.min(ds))
    # Inclusive input-resolution boundary. Gemmi's independently rounded
    # metric can otherwise omit an observed reflection exactly at d_min.
    # Generate with a tiny guard, then filter using this analysis's own metric.
    boundary_stl = 0.5 / d_min
    boundary_tolerance = max(1e-12 * boundary_stl, 8 * float(np.spacing(boundary_stl)))
    theory_stl_by_key = {
        key: stl for key, stl in theoretical_unique_hkl_stl_from_observed(
            unique, cell, sg, d_min * (1.0 - 1e-12)
        ).items() if stl <= boundary_stl + boundary_tolerance
    }
    check_cancelled()
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
        completeness = 100.0 * float(observed_counts[idx]) / float(theory_counts[idx]) if theory_counts[idx] else math.nan
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
        if theory_idx % 4096 == 0:
            check_cancelled()
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
    analysis = HklAnalysis(
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
        format_verified=_loaded.format_verified if _loaded is not None else format_verified,
    )
    from dataclasses import replace
    diagnostics = _loaded.diagnostics if _loaded is not None else build_diagnostics(analysis)
    analysis.diagnostics = replace(diagnostics, shells=shell_statistics(analysis, diagnostics))
    return analysis

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
    return xplor_fft_predictions_from_map(xmap, hkls)


def xplor_fft_predictions_from_map(
    xmap: XplorMap,
    hkls: Sequence[Tuple[int, int, int]],
) -> Dict[Tuple[int, int, int], Tuple[float, float]]:
    """Calculate requested coefficients from an XPLOR map already in memory."""
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
    predictions = xplor_fft_predictions_from_map(xmap, hkls)
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
    return scaled_amplitude_metrics(fobs, fcalc).r_factor


def select_orbit_safe_holdout(
    reflections: Sequence[Reflection],
    spacegroup: gemmi.SpaceGroup,
    seed_text: str,
    fraction: float = 0.05,
) -> FrozenSet[Tuple[int, int, int]]:
    """Select whole symmetry/Friedel orbits for a fixed experimental holdout."""
    measured = {(int(r.h), int(r.k), int(r.l)) for r in reflections if (int(r.h), int(r.k), int(r.l)) != (0, 0, 0)}
    if not measured:
        return frozenset()
    operations = full_spacegroup_ops(spacegroup) or [gemmi.Op("x,y,z")]

    def orbit_key(hkl: Tuple[int, int, int]) -> Tuple[int, int, int]:
        equivalents = []
        for operation in operations:
            transformed = tuple(int(value) for value in operation.apply_to_hkl(hkl))
            equivalents.extend((transformed, tuple(-value for value in transformed)))
        return min(equivalents)

    groups: Dict[Tuple[int, int, int], List[Tuple[int, int, int]]] = {}
    for hkl in sorted(measured):
        groups.setdefault(orbit_key(hkl), []).append(hkl)
    seed_value = str(seed_text or "").strip()
    rng = np.random.default_rng(int(seed_value) if seed_value.isdigit() else 987654321)
    keys = sorted(groups)
    rng.shuffle(keys)
    target = max(1, round(len(measured) * max(0.0, min(1.0, fraction))))
    selected: set[Tuple[int, int, int]] = set()
    for key in keys:
        group = groups[key]
        if selected and len(selected) >= target:
            break
        selected.update(group)
    return frozenset(selected)


def reference_phases_from_atoms(
    reflections: Sequence[Reflection], ref_ctx: ReferenceContext,
) -> Dict[Tuple[int, int, int], float]:
    """Calculate reference phases on measured hkl from the existing atom model."""
    if not ref_ctx.atoms:
        return {}
    atoms = expanded_unique_atoms(ref_ctx.atoms, ref_ctx.cell, ref_ctx.spacegroup)
    phases: Dict[Tuple[int, int, int], float] = {}
    for reflection in reflections:
        hkl = (int(reflection.h), int(reflection.k), int(reflection.l))
        if hkl == (0, 0, 0):
            continue
        coefficient = 0.0j
        for atom in atoms:
            try:
                weight = float(gemmi.Element(clean_element_symbol(atom.element)).atomic_number)
            except Exception:
                weight = float(ATOMIC_NUMBER_HINTS.get(clean_element_symbol(atom.element), 1))
            # numpy.fft uses the crystallographic exp(-2*pi*i*h.r) convention.
            angle = -2.0 * math.pi * float(np.dot(np.asarray(hkl, dtype=np.float64), atom.frac))
            coefficient += weight * complex(math.cos(angle), math.sin(angle))
        if abs(coefficient) > 1.0e-15:
            phases[hkl] = float(math.atan2(coefficient.imag, coefficient.real))
    return phases


def build_validation_context(
    reflections: Sequence[Reflection],
    data_mode: str,
    ref_ctx: ReferenceContext,
    free_hkls: FrozenSet[Tuple[int, int, int]],
) -> ValidationContext:
    frozen = tuple(
        FrozenReflection(
            int(reflection.h), int(reflection.k), int(reflection.l),
            math.sqrt(reflection_value_as_intensity(reflection, data_mode)),
        )
        for reflection in reflections
        if (int(reflection.h), int(reflection.k), int(reflection.l)) != (0, 0, 0)
    )
    return make_validation_context(
        frozen,
        free_hkls=free_hkls,
        reference_model=str(ref_ctx.cif_path) if ref_ctx.atoms else None,
        reference_phases=reference_phases_from_atoms(reflections, ref_ctx),
        unit_cell=(
            ref_ctx.cell.a, ref_ctx.cell.b, ref_ctx.cell.c,
            ref_ctx.cell.alpha, ref_ctx.cell.beta, ref_ctx.cell.gamma,
        ),
    )


def assess_xplor_map(
    path: Path,
    context: ValidationContext,
    profiler: Optional[WorkflowProfiler] = None,
) -> MapQualityMetrics:
    with profile_stage(profiler, "Map-quality metrics"):
        try:
            xmap = read_xplor_map(path)
            return compute_map_quality(xmap.data, xmap.grid, xmap.cell, xmap.axis_order, context)
        except Exception as exc:
            return MapQualityMetrics(
                n_measured_reflections=len(context.original_measured_reflections),
                n_work_reflections=len(context.work_reflections),
                n_free_reflections=len(context.free_reflections),
                n_triplets=len(context.triplet_set),
                unavailable_reason=str(exc),
            )


def format_validation_log_line(
    cycle: int, source: str, profile: ValidationProfile | str, metrics: MapQualityMetrics,
) -> str:
    compact_labels = {
        "amplitude_rf": "R",
        "amplitude_cc": "CC",
        "triplet_c3": "C3",
    }
    fields = []
    for metric in profile_definition(profile).primary_metrics:
        value = metrics.value(metric.key)
        label = compact_labels.get(metric.key, metric.label)
        fields.append(f"{label} {'n/a' if value is None else f'{value:.3f}'}")
    family = "Charge-flipping solution" if str(source).casefold() == "superflip" else "Structure prediction"
    return f"Validation · {family} · Cycle {int(cycle)} · " + " · ".join(fields)

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
    excluded_hkls: FrozenSet[Tuple[int, int, int]] = frozenset(),
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
    damping = max(0.0, min(1.0, float(intensity_damping or 0.0)))
    max_i_over_sigma = max(0.0, float(intensity_max_i_over_sigma or 0.0))
    if correct_intensities and damping > 0 and max_i_over_sigma > 0:
        if reflection_mode_has_fwhm(mode):
            raise ValueError("FWHM is a peak width, not an intensity uncertainty. Use threshold 0 for uncertainty-independent map correction.")
        if not any(r.sigma is not None and r.sigma > 0 and math.isfinite(float(r.sigma)) and math.isfinite(r.value) for r in current):
            raise ValueError("Significance filtering requires finite positive measured uncertainties. Use threshold 0 for uncertainty-independent map correction.")
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
    change_percentages: List[float] = []
    if correct_intensities and damping > 0:
        corrected_reflections: List[Reflection] = []
        for r in current:
            key = (int(r.h), int(r.k), int(r.l))
            raw_i, map_phase = predictions.get(key, (0.0, 0.0))
            if max_i_over_sigma > 0:
                if r.value <= 0 or not math.isfinite(float(r.value)) or r.sigma is None or r.sigma <= 0 or not math.isfinite(float(r.sigma)) or (float(r.value) / float(r.sigma)) >= max_i_over_sigma:
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
            candidates = [
                hkl for hkl in candidate_missing_hkls_from_bounds(current, cell, resolution_d_min)
                if hkl not in excluded_hkls
            ]
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
        project_composition = jana_model_composition(path, spacegroup)
        if project_composition is None:
            project_composition = ProjectComposition(
                composition, str(path), "superflip_search", "search_only",
            )
        return CrystalMetadata(
            cell, spacegroup, hm, composition, resolved_source, path, project_composition,
        )

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
        project_composition=ProjectComposition(
            composition, "manual crystal metadata", "chemical_formula", "user_supplied",
        ),
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
    from phase_studio.hkl_diagnostics import cached_load_result
    return cached_load_result(request)


def _build_uncached_hkl_load_result(request: HklAnalysisRequest) -> HklLoadResult:
    from phase_studio.hkl_diagnostics import read_diagnostic_reflections, build_diagnostics
    hkl_path, data_mode, cell, sg, hm, source_note = resolve_hkl_analysis_inputs(request)
    value_col, sigma_col, include_000 = reflection_columns_for_mode(data_mode)
    reflections = list(read_diagnostic_reflections(hkl_path, data_mode)[0])
    unique = merge_duplicate_reflections(reflections)
    result = HklLoadResult(
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
    # An AUTO filename/default guess is not evidence that column 5 is sigma.
    # Embedded Jana columns and explicitly selected external formats are declared.
    embedded = request.mode == INPUT_MODE_INFLIP or (request.mode == INPUT_MODE_INFLIP_OVERRIDES and not request.hkl_text)
    result.format_verified = (embedded and bool(embedded_reflection_data_mode_from_inflip(Path(request.jana_text)))) or normalize_reflection_data_mode(request.configured_mode) != REFLECTION_DATA_MODE_AUTO
    if embedded:
        from phase_studio.powder_diagnostics import standard_powder_context
        result.powder_diagnostic_context = standard_powder_context(Path(request.jana_text))
        if result.powder_diagnostic_context.get('unsupported_layout'):
            raise ValueError(result.powder_diagnostic_context['error'])
    result.diagnostics = build_diagnostics(result)
    return result


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


def write_text_lines_platform(path: Path, lines: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\r\n".join(str(line) for line in lines).rstrip("\r\n") + "\r\n"
    path.write_bytes(text.encode(text_encoding(), errors="replace"))


def _copy_verified_handoff_artifact(source: Path, target: Path, expected_hash: str) -> Path:
    """Atomically copy a closed candidate artifact and verify its exact bytes."""
    source = Path(source).expanduser().resolve()
    target = Path(target).expanduser().resolve()
    if not source.is_file() or source.stat().st_size <= 0:
        raise RuntimeError(f"Selected Jana2020 handoff artifact is unavailable: {source}")
    actual_hash = file_sha256(source)
    if not expected_hash or actual_hash != expected_hash:
        raise RuntimeError(
            "Jana2020 handoff was stopped because the selected result no longer "
            "matches its completed file. No alternative result was substituted."
        )
    if source == target:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(
        f".{target.name}.tmp-{os.getpid()}-{threading.get_ident()}"
    )
    try:
        with source.open("rb") as input_stream, temporary.open("wb") as output_stream:
            shutil.copyfileobj(input_stream, output_stream, length=1024 * 1024)
            output_stream.flush()
            os.fsync(output_stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    if file_sha256(target) != expected_hash:
        raise RuntimeError(
            "Jana2020 handoff was stopped because the copied result failed its "
            "content check. No alternative result was substituted."
        )
    return target


def _jana_protocol_output_paths(inflip_lines: Sequence[str], jana_cwd: Path) -> Tuple[Path, Path]:
    declared: List[Path] = []
    for line in inflip_lines:
        parts = split_inflip_line(line)
        if parts and parts[0].strip().lower() == "outputfile":
            declared = [
                jana_cwd / token.strip().strip('"')
                for token in parts[1:] if token.strip().strip('"')
            ]
            break
    m80 = next((path for path in declared if path.suffix.lower() == ".m80"), None)
    m81 = next((path for path in declared if path.suffix.lower() == ".m81"), None)
    if m80 is None or m81 is None:
        raise RuntimeError(
            "Jana2020 handoff requires the original .inflip to declare both m80 and m81 outputs."
        )
    return m80, m81


def _jana_protocol_keyword_path(
    inflip_lines: Sequence[str], jana_cwd: Path, keyword: str,
) -> Optional[Path]:
    """Resolve a single-path Jana/Superflip protocol keyword.

    Jana's successful Superflip route carries the atomic solution through the
    EDMA ``writem40`` file.  It is separate from the ``outputfile`` m80/m81
    density pair and must retain the basename supplied by Jana's original
    .inflip.
    """
    wanted = str(keyword).strip().lower()
    for line in inflip_lines:
        parts = split_inflip_line(line)
        if parts and parts[0].strip().lower() == wanted and len(parts) > 1:
            value = parts[1].strip().strip('"')
            if value:
                path = Path(value)
                return (path if path.is_absolute() else jana_cwd / path).resolve()
    return None


def _edma_m40_for_structure(structure_path: Path) -> Path:
    """Return the m40 emitted by the same EDMA job as a canonical CIF."""
    structure_path = Path(structure_path).expanduser().resolve()
    direct = structure_path.with_suffix(".m40")
    if direct.is_file():
        return direct
    # Threshold review promotes the CIF into a content-addressed canonical
    # directory together with its m40.  Older workspaces may still point at a
    # promoted CIF without that companion; never guess another threshold.
    raise RuntimeError(
        "Jana2020 handoff was stopped because the selected EDMA structure has "
        f"no matching Jana model artifact: {direct}. No map-only fallback was used."
    )


def _m40_model_count(path: Path) -> int:
    """Read EDMA/Jana's model-site count from the first m40 record."""
    try:
        first = Path(path).read_text(
            encoding=text_encoding(), errors="replace",
        ).splitlines()[0]
        return int(first.split()[0])
    except (OSError, IndexError, ValueError) as exc:
        raise RuntimeError(f"Jana2020 model artifact is not readable: {path}") from exc


def _jana_conversion_lines(
    original_lines: Sequence[str], base_name: str, model_name: str,
    output_m81: str, output_m80: str, output_xplor: str,
) -> List[str]:
    lines = define_m80_inflip_from_model(
        inflip_header_for_m80(original_lines), base_name, model_name,
    )
    replacement = f'outputfile "{output_m81}" "{output_m80}" "{output_xplor}"'
    for index, line in enumerate(lines):
        parts = split_inflip_line(line)
        if parts and parts[0].strip().lower() == "outputfile":
            lines[index] = replacement
            break
    else:
        lines.insert(0, replacement)
    return lines


def _require_current_protocol_file(path: Path, role: str) -> Path:
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError(f"Jana2020 {role} conversion did not create: {path}")
    return path


def _validate_jana_m50(path: Path, role: str = "m50") -> Path:
    """Validate Jana's project/model context without pretending it is an atom list.

    Jana stores sites in m40.  Its m50 is the companion project context (cell,
    symmetry, atom types and refinement sections), so a site-count parser would
    reject valid files.  The successful Superflip-only route preserves this
    context byte-for-byte while Jana publishes it under the active solution
    stem.
    """
    path = _require_current_protocol_file(Path(path), role)
    text = path.read_text(encoding=text_encoding(), errors="replace")
    lowered = text.casefold()
    required = ("version jana", "cell ", "end")
    if any(token not in lowered for token in required) or (
        "spgroup " not in lowered and "spacegroup " not in lowered
    ):
        raise RuntimeError(
            f"Jana2020 {role} is not a valid Jana project context: {path}"
        )
    return path


def _jana_original_m50(inflip_path: Path, output_m50: Path) -> Path:
    """Resolve Jana's canonical project context, not a generated solution alias.

    Jana commonly launches ``<project>_Superflip.inflip`` while its authoritative
    context is ``<project>.m50``.  The generated ``_Superflip.m50`` is an output
    alias and may be missing, empty, or left from a failed run.  A suffix is
    stripped only when the corresponding canonical .inflip exists, so arbitrary
    user project names are never guessed.
    """
    inflip_path = Path(inflip_path).resolve()
    stem = inflip_path.stem
    candidates: List[Path] = []
    for suffix in ("_Superflip", "_Sol"):
        if stem.casefold().endswith(suffix.casefold()):
            canonical_stem = stem[:-len(suffix)]
            canonical_inflip = inflip_path.with_name(canonical_stem + inflip_path.suffix)
            if canonical_inflip.is_file():
                candidates.append(inflip_path.with_name(canonical_stem + ".m50"))
    candidates.extend((inflip_path.with_suffix(".m50"), Path(output_m50)))
    seen: set[str] = set()
    errors: List[str] = []
    for candidate in candidates:
        key = str(candidate.resolve())
        if key in seen:
            continue
        seen.add(key)
        try:
            return _validate_jana_m50(candidate, "input/original m50")
        except RuntimeError as exc:
            errors.append(str(exc))
    raise RuntimeError(
        "Jana2020 handoff could not find a valid canonical project m50. "
        + " | ".join(errors)
    )


def _publish_protocol_transaction(artifacts: Sequence[Tuple[Path, Path]]) -> None:
    """Publish a validated protocol set and roll back if any replace fails."""
    prepared: List[Tuple[Path, Path]] = []
    backups: List[Tuple[Path, Optional[Path]]] = []
    token = f"{os.getpid()}-{threading.get_ident()}-{time.time_ns()}"
    try:
        for source, target in artifacts:
            source = Path(source).resolve()
            target = Path(target).resolve()
            _require_current_protocol_file(source, target.suffix or target.name)
            temporary = target.with_name(f".{target.name}.publish-{token}")
            shutil.copyfile(source, temporary)
            if file_sha256(temporary) != file_sha256(source):
                raise RuntimeError(f"Jana2020 staged publication check failed: {target}")
            prepared.append((temporary, target))
        for temporary, target in prepared:
            backup: Optional[Path] = None
            if target.exists():
                backup = target.with_name(f".{target.name}.backup-{token}")
                os.replace(target, backup)
            backups.append((target, backup))
            os.replace(temporary, target)
        for _target, backup in backups:
            if backup is not None and backup.exists():
                try:
                    backup.unlink()
                except OSError:
                    pass
    except Exception:
        for target, backup in reversed(backups):
            try:
                if target.exists():
                    target.unlink()
                if backup is not None and backup.exists():
                    os.replace(backup, target)
            except OSError:
                pass
        raise
    finally:
        for temporary, _target in prepared:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _next_handoff_snapshot_dir(project_dir: Path) -> Path:
    output_dir = Path(project_dir).resolve() / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    for sequence in range(1, 1_000_000):
        run_dir = output_dir / f"run_{sequence:04d}"
        try:
            run_dir.mkdir()
            handed_to_jana = run_dir / "handed_to_jana"
            handed_to_jana.mkdir()
            return handed_to_jana
        except FileExistsError:
            continue
    raise RuntimeError(f"Cannot allocate Jana2020 handoff snapshot under {output_dir}")


def _write_handoff_snapshot(
    *, cfg: RunConfig, candidate: ResultCandidate, jana_cwd: Path,
    workflow: str, source_label: str, superflip_exe: Path,
    artifacts: Sequence[Tuple[str, Path, Path]], log: Callable[[str], None],
) -> Path:
    """Archive exact final live bytes after a successful verified publication."""
    snapshot_dir = _next_handoff_snapshot_dir(jana_cwd)
    records: List[Tuple[str, Path, Path, Path, int, str]] = []
    try:
        for role, source, final in artifacts:
            final = _require_current_protocol_file(Path(final), role).resolve()
            snapshot = snapshot_dir / final.name
            shutil.copyfile(final, snapshot)
            final_hash = file_sha256(final)
            if file_sha256(snapshot) != final_hash:
                raise RuntimeError(f"Jana2020 handoff snapshot check failed: {snapshot}")
            records.append(
                (role, Path(source).resolve(), final, snapshot.resolve(), final.stat().st_size, final_hash)
            )
        lines = [
            f"Phase Studio version: {__version__}",
            f"Run ID: {candidate.run_id or cfg.run_id or 'legacy'}",
            f"Timestamp: {datetime.now().astimezone().isoformat(timespec='seconds')}",
            f"Jana project directory: {Path(jana_cwd).resolve()}",
            f"Jana project stem: {Path(cfg.jana_inflip).stem if cfg.jana_inflip else ''}",
            f"Workflow: {workflow}",
            f"Source: {source_label}",
            f"Cycle: {int(candidate.cycle)}",
            f"SharpED model: {candidate.sharped_model or 'not applicable'}",
            f"EDMA enabled: {'yes' if candidate.edma_enabled else 'no'}",
            f"EDMA threshold: {float(candidate.edma_sigma):.2f} sigma" if candidate.edma_sigma is not None else "EDMA threshold: not applicable",
            f"EDMA asymmetric-unit composition: {candidate.edma_asu_composition or 'unavailable'}",
            f"ResultCandidate ID: {candidate.candidate_id}",
            f"Superflip executable: {Path(superflip_exe).resolve()}",
            f"EDMA executable: {Path(cfg.edma_exe).expanduser().resolve()}",
            "HANDED TO JANA: YES",
            "",
            "Protocol parity reference: Superflip only",
            "Required artifacts: m40 (with EDMA), m50, m80, m81",
            "Overall protocol parity: PASS",
            "",
        ]
        for role, source, final, snapshot, size, digest in records:
            lines.extend([
                final.name,
                f"  role: {role}",
                f"  source path before publication: {source}",
                f"  final Jana path: {final}",
                f"  snapshot path: {snapshot}",
                f"  size: {size}",
                f"  SHA-256: {digest}",
                "  published/snapshot hash: PASS",
                "",
            ])
        manifest = snapshot_dir / "handoff_manifest.txt"
        manifest.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    except Exception:
        failure = snapshot_dir / "handoff_failed.txt"
        failure.write_text("HANDED TO JANA: YES\nSNAPSHOT COMPLETE: NO\n", encoding="utf-8")
        raise
    log(f"Jana2020 handoff snapshot: {snapshot_dir}")
    return snapshot_dir


def return_phase_studio_result_to_jana(
    cfg: RunConfig,
    result: CycleResult,
    candidate: ResultCandidate,
    log: Callable[[str], None],
    stop_event: Optional[threading.Event] = None,
) -> None:
    if not cfg.jana_return_to_jana or cfg.jana_inflip is None:
        raise RuntimeError("Jana2020 handoff requires a Jana2020 .inflip primary input.")
    inflip_path = Path(cfg.jana_inflip)
    if not inflip_path.is_file():
        raise RuntimeError(f"Jana2020 .inflip no longer exists: {inflip_path}")
    jana_cwd = inflip_path.parent
    base_name = inflip_path.stem
    source_key = str(candidate.source).strip().lower()
    if source_key.startswith("super"):
        expected_map = Path(result.superflip_map).resolve()
        expected_structure = Path(result.superflip_edma_cif).resolve()
        target_map = jana_cwd / f"{base_name}-phase-studio-superflip-cycle_{int(result.cycle):03d}.xplor"
        source_label = result_map_label("superflip")
        family_name = "phase-rietveld"
    else:
        expected_map = Path(result.deblur_map).resolve()
        expected_structure = Path(result.deblur_edma_cif).resolve()
        target_map = jana_cwd / f"{base_name}-deb.xplor"
        source_label = result_map_label("deblurred")
        family_name = "model-prediction"
    source_map = Path(candidate.map_path).resolve()
    source_structure = Path(candidate.structure_path).resolve() if candidate.structure_path else None
    run_ids = {
        str(value).strip() for value in (cfg.run_id, result.run_id, candidate.run_id)
        if str(value).strip()
    }
    if len(run_ids) > 1:
        raise RuntimeError(
            "Jana2020 handoff was stopped because the selected map and structure "
            "do not belong to the same Phase Studio run."
        )
    if int(candidate.cycle) != int(result.cycle):
        raise RuntimeError("Selected Jana2020 candidate cycle does not match its completed result.")
    if source_map != expected_map or (
        candidate.edma_enabled and source_structure != expected_structure
    ):
        raise RuntimeError(
            "Jana2020 handoff was stopped because the selected source/cycle/threshold "
            "identity no longer matches its completed result. No alternative result was substituted."
        )
    if candidate.edma_enabled and (
        source_structure is None or not candidate.usable_structure or not candidate.structure_sha256
        or not candidate.jana_model_path or not candidate.jana_model_sha256
    ):
        raise RuntimeError(
            "Jana2020 handoff was stopped because the selected EDMA structure could not "
            "be prepared. The map was not passed alone because EDMA is enabled for this workflow."
        )
    threshold_name = (
        f"-{float(candidate.edma_sigma):.2f}sigma".replace(".", "p")
        if candidate.edma_sigma is not None else ""
    )
    target_structure = jana_cwd / (
        f"{base_name}-phase-studio-{family_name}-cycle_{int(candidate.cycle):03d}"
        f"{threshold_name}.cif"
    )
    if file_sha256(source_map) != candidate.map_sha256:
        raise RuntimeError("Jana2020 selected map changed after completion. No alternative result was substituted.")
    if candidate.edma_enabled:
        assert source_structure is not None
        if file_sha256(source_structure) != candidate.structure_sha256:
            raise RuntimeError("Jana2020 selected structure changed after completion. No alternative result was substituted.")
        source_m40 = _edma_m40_for_structure(source_structure)
        if source_m40 != Path(candidate.jana_model_path).expanduser().resolve():
            raise RuntimeError(
                "Jana2020 handoff was stopped because the selected EDMA model "
                "does not match the completed candidate identity."
            )
        source_m40_hash = candidate.jana_model_sha256
        if file_sha256(source_m40) != source_m40_hash:
            raise RuntimeError(
                "Jana2020 handoff was stopped because the selected EDMA m40 "
                "changed after completion. No map-only fallback was used."
            )
        source_m40_sites = _m40_model_count(source_m40)
        selected_cif_sites = len(parse_cif_atoms(source_structure))
        if selected_cif_sites > 0 and source_m40_sites <= 0:
            raise RuntimeError(
                "Jana2020 handoff was stopped because the selected EDMA structure "
                "contains atoms but its Jana m40 model is empty. No map-only "
                "fallback was used."
            )
        if candidate.jana_model_site_count is not None and source_m40_sites != int(candidate.jana_model_site_count):
            raise RuntimeError(
                "Jana2020 handoff was stopped because the selected EDMA m40 "
                "site count changed after completion."
            )
    log("[Jana2020 handoff]")
    log(f"  Run: {candidate.run_id or result.run_id or cfg.run_id or 'legacy'}")
    log(f"  Candidate: {candidate.candidate_id}")
    log(f"  Result: {'Charge-flipping solution' if source_key.startswith('super') else 'Structure prediction'}")
    log(f"  Source: {source_label}")
    log(f"  Cycle: {int(candidate.cycle)}")
    if candidate.edma_enabled and candidate.edma_sigma is not None:
        log(f"  EDMA threshold: {float(candidate.edma_sigma):.2f} sigma")
    elif not candidate.edma_enabled:
        log("  EDMA: disabled")
        log("  Jana2020 will derive the structure from the selected map.")
    if candidate.sharped_model:
        log(f"  SharpED model: {candidate.sharped_model}")
    log(f"  Map: {target_map.name} · SHA-256 {candidate.map_sha256[:12]}")
    if candidate.edma_enabled:
        log(
            f"  Structure: {target_structure.name} · "
            f"{candidate.detected_atom_count or 0} EDMA sites · "
            f"SHA-256 {candidate.structure_sha256[:12]}"
        )
        log(
            f"  EDMA Jana model: {source_m40.name} · {source_m40_sites} sites · "
            f"SHA-256 {source_m40_hash[:12]}"
        )
    original = Path(str(cfg.superflip_exe)).expanduser().resolve()
    if not original.is_file():
        raise RuntimeError(f"Jana2020 handoff Superflip executable was not found: {original}")
    # The conversion is isolated from every live project output.  This keeps a
    # second run from consuming an m40/m50/m80/m81 left by the first run.
    candidate_dir_name = re.sub(
        r"[^A-Za-z0-9_.-]+", "_", candidate.candidate_id or candidate.run_id or "legacy",
    ).strip("._") or "candidate"
    calc_dir = Path(cfg.work_dir).expanduser().resolve() / "jana_handoff" / candidate_dir_name
    if calc_dir.exists():
        shutil.rmtree(calc_dir)
    calc_dir.mkdir(parents=True)
    calc_map_inflip = calc_dir / "calc_m81.inflip"
    original_lines = inflip_path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    target_m80, target_m81 = _jana_protocol_output_paths(original_lines, jana_cwd)
    target_edma_m40 = _jana_protocol_keyword_path(original_lines, jana_cwd, "writem40")
    output_base = _jana_protocol_keyword_path(original_lines, jana_cwd, "outputbase")
    if output_base is None:
        raise RuntimeError(
            "Jana2020 handoff was stopped because the original .inflip does not declare outputbase."
        )
    target_m40 = output_base.with_suffix(".m40")
    target_m50 = output_base.with_suffix(".m50")
    original_m50 = _jana_original_m50(inflip_path, target_m50)
    original_m50_hash = file_sha256(original_m50)
    original_m50_size = original_m50.stat().st_size
    staged_original_m50 = calc_dir / target_m50.name
    shutil.copyfile(original_m50, staged_original_m50)
    _validate_jana_m50(staged_original_m50, "staged input/original m50")
    log(
        f"  Input/original m50: {original_m50} · {original_m50_size} bytes · "
        f"SHA-256 {original_m50_hash} · validation PASS"
    )
    if candidate.edma_enabled and target_edma_m40 is None:
        raise RuntimeError(
            "Jana2020 handoff was stopped because the original .inflip does not "
            "declare writem40 for the selected EDMA model. No map-only fallback was used."
        )
    target_ready = jana_cwd / f"{base_name}-ready.xplor"
    staging_started = time.perf_counter()
    staged_map = calc_dir / "selected_map.xplor"
    shutil.copyfile(source_map, staged_map)
    if file_sha256(staged_map) != candidate.map_sha256:
        raise RuntimeError("Jana2020 selected map changed while staging the handoff")
    staged_structure: Optional[Path] = None
    if candidate.edma_enabled:
        assert source_structure is not None
        staged_structure = calc_dir / "selected_structure.cif"
        shutil.copyfile(source_structure, staged_structure)
        if file_sha256(staged_structure) != candidate.structure_sha256:
            raise RuntimeError("Jana2020 selected structure changed while staging the handoff")
    map_m81 = calc_dir / target_m81.name
    map_m80 = calc_dir / target_m80.name
    map_xplor = calc_dir / target_ready.name
    map_lines = _jana_conversion_lines(
        original_lines, base_name, staged_map.name,
        map_m81.name, map_m80.name, map_xplor.name,
    )
    map_lines = origin_preserving_conversion_lines(map_lines, staged_map)
    write_text_lines_platform(calc_map_inflip, map_lines)
    staging_seconds = time.perf_counter() - staging_started
    log("  Preparing m80/m81 pair...")
    log(f"Jana2020 map-side Superflip input: {calc_map_inflip}")
    log(f"Jana2020 selected map: {source_map} · SHA-256 {file_sha256(source_map)[:12]}")
    conversion_started = time.perf_counter()
    try:
        run_command(
            [str(original), str(calc_map_inflip)],
            cwd=calc_dir,
            log_path=Path(cfg.work_dir) / "jana2020_return_map.log",
            log=log,
            stop_event=stop_event,
            allow_foreground=True,
            hide_console=True,
        )
        external_seconds = time.perf_counter() - conversion_started
        _require_current_protocol_file(map_m81, "map-side m81")
        _require_current_protocol_file(map_m80, "map-side m80")
        _require_current_protocol_file(map_xplor, "map-side XPLOR")
        validation_started = time.perf_counter()
        alignment = validate_converted_density(staged_map, map_xplor)
        grid_validation_seconds = time.perf_counter() - validation_started
        alignment.update(validate_jana_density_pair(map_xplor, map_m81, map_m80))
        alignment["conversion_seconds"] = time.perf_counter() - conversion_started
        alignment["staging_io_and_input_seconds"] = staging_seconds
        alignment["superflip_conversion_seconds"] = external_seconds
        alignment["full_grid_validation_seconds"] = grid_validation_seconds
        alignment["source_map_sha256"] = candidate.map_sha256
        alignment["selected_cif_sha256"] = candidate.structure_sha256
        alignment["candidate_id"] = candidate.candidate_id
        alignment["edma_sigma"] = candidate.edma_sigma
        alignment["selected_m40_sha256"] = candidate.jana_model_sha256
        alignment["selected_cif_sites"] = candidate.detected_atom_count
        alignment["published_m40_sites"] = candidate.jana_model_site_count
        (calc_dir / "density_alignment.json").write_text(json.dumps(alignment, indent=2), encoding="utf-8")
        log(f"  Density frame preserved: shift (0,0,0), relative L2 {alignment['relative_l2']:.6g}, correlation {alignment['correlation']:.12g}")
    except Exception:
        raise

    # Real Superflip-only probing establishes that Superflip writes m80/m81
    # and leaves m50 unchanged; Jana copies that valid context to the solution
    # stem while m40 carries the selected sites.  Reproduce those semantics
    # explicitly so the GUI handoff does not delete m50 and return a zero model.
    staged_m50 = calc_dir / f"published-{target_m50.name}"
    shutil.copyfile(staged_original_m50, staged_m50)
    _validate_jana_m50(staged_m50, "output m50")
    publication: List[Tuple[Path, Path]] = [
        (staged_map, target_map),
        (map_m81, target_m81),
        (map_m80, target_m80),
        (map_xplor, target_ready),
        (staged_m50, target_m50),
    ]
    snapshot_artifacts: List[Tuple[str, Path, Path]] = [
        ("selected map sidecar", source_map, target_map),
        ("selected map density (m81)", map_m81, target_m81),
        ("selected candidate protocol output (m80)", map_m80, target_m80),
        ("Jana/Superflip project context (m50)", staged_original_m50, target_m50),
        ("Jana-ready selected map", map_xplor, target_ready),
    ]
    if candidate.edma_enabled:
        assert target_edma_m40 is not None
        assert source_structure is not None
        assert staged_structure is not None
        publication.append((staged_structure, target_structure))
        snapshot_artifacts.append(("exact selected EDMA CIF", source_structure, target_structure))
        staged_m40 = calc_dir / f"published-{target_edma_m40.name}"
        shutil.copyfile(source_m40, staged_m40)
        if file_sha256(staged_m40) != source_m40_hash or _m40_model_count(staged_m40) != source_m40_sites:
            raise RuntimeError("Jana2020 staged m40 does not match the selected EDMA candidate.")
        publication.append((staged_m40, target_edma_m40))
        snapshot_artifacts.append(("exact selected EDMA writem40 input", source_m40, target_edma_m40))
    snapshot_artifacts.append(("density frame validation", calc_dir / "density_alignment.json", calc_dir / "density_alignment.json"))
    _publish_protocol_transaction(publication)
    if target_m40.resolve() != (target_edma_m40.resolve() if target_edma_m40 else None):
        # outputbase.m40 is created by Jana from the declared writem40 input.
        # A raw EDMA m40 has a different header/origin representation and must
        # never be published under this post-import name.
        if target_m40.exists():
            target_m40.unlink()
    if not candidate.edma_enabled:
        # Map-driven Jana continuation must not see a model from an earlier
        # selected candidate.  No replacement m40 is fabricated.
        for stale in {target_m40.resolve(), target_edma_m40.resolve() if target_edma_m40 else None}:
            if stale is not None and stale.exists():
                stale.unlink()
    for output, role in (
        (target_m81, "selected-map m81"),
        (target_m80, "selected-map m80"),
        (target_ready, "selected-map XPLOR"),
    ):
        _require_current_protocol_file(output, role)
        log(f"Jana2020 protocol output ({role}): {output.name} · SHA-256 {file_sha256(output)[:12]}")
    if candidate.edma_enabled:
        assert target_edma_m40 is not None
        _require_current_protocol_file(target_edma_m40, "selected-model writem40")
        log(
            f"Jana2020 model protocol input: {target_edma_m40} · "
            f"sites {_m40_model_count(target_edma_m40)} · "
            f"SHA-256 {file_sha256(target_edma_m40)[:12]}"
        )
        live_protocol_sites = _m40_model_count(target_edma_m40)
        log(f"Selected model sites: {source_m40_sites}")
        log(f"Live Jana writem40 sites: {live_protocol_sites}")
        if source_m40_sites > 0 and live_protocol_sites <= 0:
            log("ERROR: Jana2020 handoff aborted because live writem40 is empty.")
            raise RuntimeError(
                "Jana2020 handoff was stopped because the selected model has sites "
                "but the live writem40 artifact is empty."
            )
        _require_current_protocol_file(target_edma_m40, "selected-model writem40")
        if file_sha256(target_edma_m40) != source_m40_hash:
            raise RuntimeError("Jana2020 live writem40 does not match the selected EDMA candidate.")
        log(f"Jana2020 model input for Jana import: {target_edma_m40}")
        log(f"Jana2020 post-import model pathname: {target_m40}")
    _validate_jana_m50(target_m50, "published m50")
    if file_sha256(target_m50) != original_m50_hash:
        raise RuntimeError("Jana2020 published m50 does not match the captured project context.")
    log(
        f"Jana2020 protocol output (m50): {target_m50} · {target_m50.stat().st_size} bytes · "
        f"SHA-256 {file_sha256(target_m50)} · validation PASS"
    )
    for path, role in ((target_m80, "m80"), (target_m81, "m81")):
        log(f"Jana2020 protocol output ({role}): {path} · {path.stat().st_size} bytes · SHA-256 {file_sha256(path)}")
    _write_handoff_snapshot(
        cfg=cfg,
        candidate=candidate,
        jana_cwd=jana_cwd,
        workflow="Phase recycling" if int(cfg.cycles) > 1 else "Single-cycle",
        source_label=source_label,
        superflip_exe=original,
        artifacts=snapshot_artifacts,
        log=log,
    )
    log("Jana2020 final Superflip handoff completed.")



def perform_jana_handoff(
    cfg: RunConfig,
    result: CycleResult,
    candidate: ResultCandidate,
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
        candidate=candidate,
        log=log,
        stop_event=stop_event,
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

def resolve_jana_m90_path(inflip_path: Optional[Path]) -> Optional[Path]:
    """The Jana2020 .m90 reflection-data file that normally accompanies a
    .inflip file: same directory, same stem, .m90 extension. Returns None if
    there is no .inflip or no matching .m90 file actually exists."""
    if inflip_path is None:
        return None
    candidate = Path(inflip_path).with_suffix(".m90")
    return candidate if candidate.is_file() else None


def parse_m90_wavelength(m90_path: Path) -> float:
    """Extract the radiation wavelength from a Jana2020 .m90 reflection-data
    file's header section.

    The header is a sequence of "keyword value keyword value ..." lines (the
    same tokenization convention as .inflip -- see parse_inflip_settings)
    ending in a line reading exactly "end", followed by the raw reflection
    data table (a "Data <blockname>" line, then one row per reflection). The
    wavelength is the value immediately following the "lambda" keyword, e.g.
    "lambda 1.54184 lpfactor 1 monangle 13.2885 perfmono 0.5". Only the
    header is scanned -- the reflection data table is never treated as
    keyword/value pairs, however coincidentally its tokens might look."""
    try:
        text = Path(m90_path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return 0.0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower() == "end":
            break
        tokens = stripped.split()
        for index, token in enumerate(tokens):
            if token.lower() == "lambda" and index + 1 < len(tokens):
                value = parse_cif_number(tokens[index + 1], 0.0)
                if value > 0:
                    return value
    return 0.0


def resolve_powder_wavelength(
    manual_value: float,
    inflip_path: Optional[Path],
    reference_cif_path: Optional[Path],
    jana_m90_path: Optional[Path] = None,
) -> Tuple[float, str]:
    """Resolve the powder-repartitioning wavelength.

    Priority: a manually entered nonzero value wins outright; otherwise a
    Jana2020 .m90 reflection-data file's own "lambda" header value; otherwise
    the Jana .inflip file's lambda/wavelength line; otherwise the reference
    file's _diffrn_radiation_wavelength CIF tag. Returns (value,
    source_description).
    """
    if manual_value > 0:
        return manual_value, "manual entry"
    if jana_m90_path is not None and Path(jana_m90_path).is_file():
        value = parse_m90_wavelength(Path(jana_m90_path))
        if value > 0:
            return value, f"Jana2020 .m90 file ({Path(jana_m90_path).name})"
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
        # Phase Studio never emits a normalize keyword: this function returns no
        # lines for every value. The previous "may be unsupported by this
        # executable" implied a per-executable capability check that is not
        # performed, so it is stated as what actually happens instead -- no
        # claim of certainty about the binary, and no vague hedge either.
        log(
            f"Superflip normalize value {normalize!r} is not passed to Superflip; "
            "the normalize keyword is omitted for compatibility."
        )
    return []

def write_structure_cif(
    output_cif: Path,
    cell: gemmi.UnitCell,
    sg: gemmi.SpaceGroup,
    sg_hm: str,
    atoms: Sequence[AtomSite],
    composition: str = "",
    *,
    bound_edma_uiso: bool = False,
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
            include_uiso = any(atom.uiso_angstrom2 is not None for atom in atoms)
            f.write("loop_\n_atom_site_label\n_atom_site_type_symbol\n_atom_site_fract_x\n_atom_site_fract_y\n_atom_site_fract_z\n")
            if include_uiso:
                f.write("_atom_site_U_iso_or_equiv\n")
            counts: Dict[str, int] = collections.Counter()
            for a in atoms:
                elem = clean_element_symbol(a.element)
                counts[elem] += 1
                f0 = wrap_frac(a.frac)
                uiso = ""
                if include_uiso:
                    if a.uiso_angstrom2 is None:
                        uiso = " ."
                    else:
                        value = float(a.uiso_angstrom2)
                        if bound_edma_uiso:
                            value = normalize_export_uiso(
                                value, IsotropicDisplacementKind.UISO,
                            ).uiso_angstrom2
                        uiso = f" {value:.6f}"
                f.write(f"{elem}{counts[elem]} {elem} {f0[0]:.6f} {f0[1]:.6f} {f0[2]:.6f}{uiso}\n")


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

def write_structure_pdb(
    output_pdb: Path,
    cell: gemmi.UnitCell,
    sg_hm: str,
    atoms: Sequence[AtomSite],
    *,
    bound_edma_uiso: bool = False,
) -> None:
    output_pdb.parent.mkdir(parents=True, exist_ok=True)
    with output_pdb.open("w", encoding="utf-8") as f:
        f.write(f"CRYST1{cell.a:9.3f}{cell.b:9.3f}{cell.c:9.3f}{cell.alpha:7.2f}{cell.beta:7.2f}{cell.gamma:7.2f} {sg_hm[:11]:<11}    1\n")
        for idx, atom in enumerate(atoms, start=1):
            elem = clean_element_symbol(atom.element)
            x, y, z = fractional_to_cartesian(cell, atom.frac)
            name = (atom.label or f"{elem}{idx}")[:4]
            if atom.uiso_angstrom2 is None:
                biso = 0.0
            else:
                uiso = float(atom.uiso_angstrom2)
                if bound_edma_uiso:
                    uiso = normalize_export_uiso(
                        uiso, IsotropicDisplacementKind.UISO,
                    ).uiso_angstrom2
                biso = uiso_to_biso(uiso)
            f.write(
                f"HETATM{idx:5d} {name:<4} UNK A   1    "
                f"{x:8.3f}{y:8.3f}{z:8.3f}{1.00:6.2f}{biso:6.2f}          {elem:>2}\n"
            )
        f.write("END\n")

def write_structure_bundle(
    output_cif: Path,
    cell: gemmi.UnitCell,
    sg: gemmi.SpaceGroup,
    sg_hm: str,
    atoms: Sequence[AtomSite],
    structure_format: str = "cif",
    *,
    bound_edma_uiso: bool = False,
) -> None:
    """Write the CIF that EDMA/next-cycle modelfiles always need, plus one optional
    extra structure format (xyz or pdb) selected by the user."""
    write_structure_cif(
        output_cif, cell, sg, sg_hm, atoms,
        bound_edma_uiso=bound_edma_uiso,
    )
    fmt = normalize_structure_export_format(structure_format)
    if fmt == "xyz":
        write_structure_xyz(output_cif.with_suffix(".xyz"), cell, atoms)
    elif fmt == "pdb":
        write_structure_pdb(
            output_cif.with_suffix(".pdb"), cell, sg_hm, atoms,
            bound_edma_uiso=bound_edma_uiso,
        )


def edma_scientific_source_cif(export_cif: Path) -> Path:
    """Return the unbounded EDMA CIF retained for later scientific use."""
    path = Path(export_cif)
    raw = path.with_name(path.stem + "_scientific_raw.cif")
    return raw if raw.is_file() and raw.stat().st_size > 0 else path

def write_filtered_cif(input_cif: Path, output_cif: Path, exclude_labels: Sequence[str]) -> Tuple[Path, int, int]:
    scientific_input = edma_scientific_source_cif(input_cif)
    atoms = parse_cif_atoms(scientific_input)
    cell, sg, hm = parse_cif_cell_and_sg(scientific_input)
    exclude = {normalize_atom_label(x) for x in exclude_labels}
    kept: List[AtomSite] = []
    removed = 0
    for a in atoms:
        if normalize_atom_label(a.label) in exclude:
            removed += 1
            continue
        kept.append(AtomSite(
            label=a.label, element=a.element, frac=wrap_frac(a.frac), density=a.density,
            uiso_angstrom2=a.uiso_angstrom2,
        ))
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
    hide_console: bool = False,
) -> int:
    """Run an external command, writing its complete raw stdout/stderr to
    log_path unchanged, byte for byte (including any bare '\\r' console
    overwrite sequences some tools emit) -- this is a live-streaming reader,
    not a filter, and never alters what a diagnostic log-file comparison
    would see.

    on_output_line, when given, is called with each decoded line as it
    arrives WHILE the process is still running (best-effort progress
    observation only; a raised exception from it is swallowed so a parsing
    bug can never fail the run or block stop_event/timeout handling).

    hide_console=True starts the child without a visible console window on
    Windows (see process_utils.no_console_popen_kwargs). It changes nothing
    else: the command line, working directory, captured stdout/stderr, exit
    code and stop_event/timeout termination all behave identically. Opt in
    per call site rather than globally -- a console that IS part of the user
    interface must keep showing."""
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
            launch_kwargs: Dict[str, object] = {}
            if hide_console:
                # No console window for a GUI-launched calculation process.
                # stdin is pointed at DEVNULL only in this branch: the hidden
                # console has no reachable input, so an unexpected prompt
                # would otherwise block invisibly and forever instead of
                # failing fast into the log below.
                launch_kwargs.update(no_console_popen_kwargs())
                launch_kwargs["stdin"] = subprocess.DEVNULL
            proc = subprocess.Popen(
                list(cmd),
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                **launch_kwargs,
            )
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
        # below waits briefly on that queue, so new output and the reader's EOF
        # sentinel wake it immediately. The short timeout keeps stop_event and
        # command deadlines responsive even when the child is silent.
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
            try:
                raw_bytes = line_queue.get(timeout=0.05)
            except queue.Empty:
                continue
            if raw_bytes is None:
                reader_done = True
                # EOF normally coincides with process exit. A bounded native
                # wait observes that exit immediately instead of paying one
                # more queue timeout; if a child deliberately closes stdout
                # early, cancellation/deadline checks resume after 50 ms.
                try:
                    proc.wait(timeout=0.05)
                except subprocess.TimeoutExpired:
                    pass
                continue
            relay(raw_bytes)
            while True:
                try:
                    raw_bytes = line_queue.get_nowait()
                except queue.Empty:
                    break
                if raw_bytes is None:
                    reader_done = True
                    break
                relay(raw_bytes)
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

def run_superflip_cycle(cycle_dir: Path, prefix: str, ref_ctx: ReferenceContext, observed_hkl: Path, model_file: Optional[Path], reference_file: Optional[Path], reference_format: str, superflip_exe: str, perform_algorithm: str, output_format: str, write_auxiliary_outputs: bool, export_superflip_xplor: bool, export_superflip_ccp4: bool, export_superflip_jana: bool, voxel: str, bestdensities_count: int, bestdensities_metric: str, bestdensities_symmetry: bool, polish: bool, maxcycles: int, repeatmode: int, randomseed: str, delta: str, weakratio: str, biso: str, reflection_data_mode: str, normalize: str, nresshells: int, missing: str, searchsymmetry: str, derivesymmetry: str, electrons: str, dataitemwidths: str, extra_superflip_keywords: str, log: Callable[[str], None], stop_event: Optional[threading.Event] = None, on_output_line: Optional[Callable[[str], None]] = None, profiler: Optional[WorkflowProfiler] = None) -> Path:
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
    with profile_stage(profiler, "Superflip process", "external"):
        run_command(
            [superflip_exe, inp.name],
            cwd=cycle_dir,
            log_path=log_path,
            log=log,
            stop_event=stop_event,
            allow_foreground=True,
            on_output_line=on_output_line,
            hide_console=True,
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
    profiler: Optional[WorkflowProfiler] = None,
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
    with profile_stage(profiler, "Superflip symmetry process", "external"):
        run_command(
            [superflip_exe, inp.name],
            cwd=sym_dir,
            log_path=log_path,
            log=log,
            stop_event=stop_event,
            allow_foreground=True,
            hide_console=True,
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
    map_value_exponent: float = SHARPED_MAP_VALUE_EXPONENT_DEFAULT,
    profiler: Optional[WorkflowProfiler] = None,
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
    effective_max_upload_mb = float(max_upload_mb or 0.0)
    if effective_max_upload_mb <= 0 and any(
        host in str(base_url).lower() for host in ("jana.fzu.cz", "sharped.fzu.cz")
    ):
        # The public server enforces a real 100 MB limit even when Phase
        # Studio's own check is disabled; an oversized map is tiled (below)
        # rather than failing, so this only supplies the effective budget.
        effective_max_upload_mb = 100.0
    upload_map = input_map

    # Reversible map-value scaling. Exactly one forward transform happens here,
    # on the very last file handed to the client, and exactly one inverse
    # transform happens below on the file the server actually returned -- once
    # per SharpED request, regardless of retries, polling or download probing
    # inside SharpEDServerClient.execute(). For the default exponent 1.0 (and
    # for the explicit 0.0 bypass) nothing at all runs and `upload_map` stays
    # the untouched file the pre-feature workflow uploaded.
    exponent = normalize_map_value_exponent(map_value_exponent)
    scaling_active = not map_value_scaling_is_identity(exponent)
    exponent_note = describe_map_value_exponent(exponent)
    if exponent_note:
        log_both(exponent_note)
    if scaling_active:
        # Written to a separate file: `input_map` is the Superflip/recycled map
        # the rest of the workflow still needs in its original value domain.
        scaled_upload_map = output_map.parent / f"{output_map.stem}.sharped_input.xplor"
        source_map = read_xplor_map(upload_map)
        write_xplor_map(
            scaled_upload_map,
            XplorMap(
                title=source_map.title,
                grid=source_map.grid,
                cell=source_map.cell,
                axis_order=source_map.axis_order,
                data=apply_signed_power(source_map.data, exponent),
            ),
            title=source_map.title,
        )
        del source_map
        upload_map = scaled_upload_map
        log_both(f"SharpED map value detail: exponent {exponent:.3f} applied to {scaled_upload_map.name}")

    client = SharpEDServerClient(base_url=base_url, timeout=float(timeout))
    client.performance_profiler = profiler
    selected_model = model.strip()
    if not selected_model or selected_model.lower() in {"default", "server default", "sharped default"}:
        models = client.get_models(log=log_both)
        selected_model = models.default_model or "SharpED latest"
        if models.models:
            log_both("SharpED server models: " + ", ".join(models.models))
        log_both(f"SharpED server default model: {selected_model}")

    tiled_submission = decide_sharped_submission(upload_map, effective_max_upload_mb) == "tiled"

    def _infer_one(request_map: Path, response_map: Path) -> None:
        def request_log(line: str) -> None:
            # A server-complete TILE is not a complete SharpED map. The
            # tiling authority publishes "Tile i/n complete" only after the
            # returned tile has been read and accumulated; the final map is
            # complete only after reconstruction is written.
            if tiled_submission and str(line).strip().casefold() == "[sharped] completed":
                return
            log_both(line)

        client.execute(
            file_path=request_map,
            bearer_token=api_token.strip(),
            out_path=response_map,
            elements=elements.strip() or "C N O",
            model=selected_model,
            outres=outres,
            poll_seconds=poll_seconds,
            max_polls=max_polls,
            log=request_log,
            stop_event=stop_event,
        )

    # 2.0.0: one authoritative size decision, never a grid coarsening. A map
    # at/under the limit is sent exactly as before; an oversized map is
    # tiled (full periodic P1 cell, equal-size overlapping tiles, Gaussian-
    # weighted reassembly) onto its own original, unchanged grid.
    if tiled_submission:
        run_tiled_sharped_inference(upload_map, output_map, effective_max_upload_mb, _infer_one, log_both)
    else:
        _infer_one(upload_map, output_map)
    if not output_map.is_file() or output_map.stat().st_size == 0:
        raise RuntimeError(f"SharpED did not create output map: {output_map}")
    log_both(f"[SharpED] Downloaded {output_map.name}")
    if scaling_active:
        # Read back what the server produced (never a cached copy of the
        # upload) and undo the transform in place, before EDMA, symmetrization,
        # metrics, phase recycling, export or the Jana2020 hand-off see it.
        returned_map = read_xplor_map(output_map)
        write_xplor_map(
            output_map,
            XplorMap(
                title=returned_map.title,
                grid=returned_map.grid,
                cell=returned_map.cell,
                axis_order=returned_map.axis_order,
                data=invert_signed_power(returned_map.data, exponent),
            ),
            title=returned_map.title,
        )
        log_both(f"SharpED map value detail: inverse exponent 1/{exponent:.3f} applied to {output_map.name}")
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

# --- Element colours: THE single authority (presentation only) -------------
# Period of the periodic table = colour family (a CIELCh hue range); the
# element's position within its period = a deterministic hue offset plus
# alternating lightness/chroma, so neighbours stay distinguishable while the
# period grouping remains recognizable. Computed from the atomic number (via
# element_atomic_number(), i.e. gemmi's own element data) -- no per-element
# colour table. Lanthanides/actinides sit inside periods 6/7 and inherit
# those families. Colour encodes chemical identity only.
ELEMENT_PERIOD_LAST_Z = (2, 10, 18, 36, 54, 86, 118)
# period -> (hue centre deg, hue span deg, base chroma), CIELCh(ab), chosen
# for readability on the white renderer background.
ELEMENT_PERIOD_COLOR_FAMILIES = {
    1: (250.0, 30.0, 22.0),   # slate blue-grey
    2: (35.0, 70.0, 62.0),    # red / orange
    3: (100.0, 60.0, 60.0),   # olive / yellow-green
    4: (150.0, 100.0, 52.0),  # green
    5: (215.0, 90.0, 45.0),   # teal / cyan
    6: (300.0, 100.0, 55.0),  # blue-violet / purple
    7: (345.0, 50.0, 55.0),   # magenta / rose
}
ELEMENT_COLOR_LIGHTNESS_SHORT = (50.0, 64.0)          # periods of <= 8 elements
ELEMENT_COLOR_LIGHTNESS_LONG = (40.0, 54.0, 68.0)     # periods of 18 / 32
ELEMENT_COLOR_CHROMA_ALTERNATION = (0.8, 1.25)
UNKNOWN_ELEMENT_COLOR = "#9A9A9A"


def element_period_position(atomic_number: int) -> Optional[Tuple[int, int, int]]:
    """(period, zero-based position within the period, period length) for
    Z = 1..118, else None."""
    z = int(atomic_number)
    if z < 1 or z > ELEMENT_PERIOD_LAST_Z[-1]:
        return None
    first = 1
    for period, last in enumerate(ELEMENT_PERIOD_LAST_Z, start=1):
        if z <= last:
            return period, z - first, last - first + 1
        first = last + 1
    return None


def _cielch_to_hex(lightness: float, chroma: float, hue_deg: float) -> str:
    a = chroma * math.cos(math.radians(hue_deg))
    b = chroma * math.sin(math.radians(hue_deg))
    fy = (lightness + 16.0) / 116.0
    fx, fz = fy + a / 500.0, fy - b / 200.0

    def inverse(t: float) -> float:
        return t ** 3 if t ** 3 > 0.008856 else (t - 16.0 / 116.0) / 7.787

    x, y, zz = 0.95047 * inverse(fx), inverse(fy), 1.08883 * inverse(fz)
    linear = (
        3.2406 * x - 1.5372 * y - 0.4986 * zz,
        -0.9689 * x + 1.8758 * y + 0.0415 * zz,
        0.0557 * x - 0.2040 * y + 1.0570 * zz,
    )

    def encode(c: float) -> int:
        c = 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1.0 / 2.4)) - 0.055
        return int(round(min(1.0, max(0.0, c)) * 255))

    return "#{:02X}{:02X}{:02X}".format(*(encode(c) for c in linear))


def element_color(element: str) -> str:
    """The one element-colour authority for every structure view and legend.
    Deterministic: the same element always gets the same colour; anything
    that does not resolve to a real element gets UNKNOWN_ELEMENT_COLOR."""
    placement = element_period_position(element_atomic_number(element))
    if placement is None:
        return UNKNOWN_ELEMENT_COLOR
    period, position, length = placement
    hue_centre, hue_span, chroma = ELEMENT_PERIOD_COLOR_FAMILIES[period]
    fraction = position / (length - 1) if length > 1 else 0.5
    hue = hue_centre + hue_span * (fraction - 0.5)
    lightness_steps = ELEMENT_COLOR_LIGHTNESS_LONG if length > 8 else ELEMENT_COLOR_LIGHTNESS_SHORT
    lightness = lightness_steps[position % len(lightness_steps)]
    chroma *= ELEMENT_COLOR_CHROMA_ALTERNATION[position % 2]
    return _cielch_to_hex(lightness, chroma, hue)


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
    profiler: Optional[WorkflowProfiler] = None,
    map_label: Optional[str] = None,
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
    if not map_label:
        map_label = result_map_label("deblurred" if "deblur" in prefix.lower() else "superflip")
    # Indentation classifies the technical map identity as detailed output;
    # the user-facing stage banner uses Charge-flipping solution / Structure prediction.
    log(f"  [EDMA] {map_label} · threshold {plimit_sigma:g} σ")
    if map_sigma is None:
        log(f"  plimit={float(absolute_plimit):g}")
    else:
        log(f"  map σ={map_sigma:g} · plimit={float(absolute_plimit):g}")
    # EDMA is a console executable started by the GUI; its console window is
    # not part of the user interface (all of its output is captured into
    # edma_log below), so it runs hidden. Command line, working directory,
    # captured output, exit-code handling and stop_event termination are
    # deliberately unchanged.
    with profile_stage(profiler, "EDMA process", "external"):
        run_command(
            [edma_exe, inp.name],
            cwd=out_dir,
            log_path=edma_log,
            log=log,
            stop_event=stop_event,
            hide_console=True,
        )
    m40_records = []
    if write_m40:
        m40_path = out_dir / f"{outbase}.m40"
        if m40_path.is_file() and m40_path.stat().st_size > 0:
            # EDMA's writem40 continuation field is emitted in the Biso
            # representation, while Jana2020 consumes that field as Uiso.
            # Declare the source representation explicitly and normalize it
            # once, before this artifact can be canonicalized or handed on.
            m40_records = normalize_jana_m40_isotropic_displacements(
                m40_path, source_kind=IsotropicDisplacementKind.BISO,
            )
            if m40_records:
                source_values = [record.source_value for record in m40_records]
                raw_uiso_values = [record.raw_uiso_angstrom2 for record in m40_records]
                final_uiso_values = [record.uiso_angstrom2 for record in m40_records]
                lower = sum(record.clamp_direction == "lower" for record in m40_records)
                upper = sum(record.clamp_direction == "upper" for record in m40_records)
                log(
                    f"  [EDMA] Jana m40 displacement export · source Biso "
                    f"{min(source_values):.6f}-{max(source_values):.6f} A^2 · raw Uiso "
                    f"{min(raw_uiso_values):.6f}-{max(raw_uiso_values):.6f} A^2 · allowed "
                    f"0.010-0.150 A^2 · lower-clamped {lower} · upper-clamped {upper} · "
                    f"unchanged {len(m40_records) - lower - upper} · final "
                    f"{min(final_uiso_values):.6f}-{max(final_uiso_values):.6f} A^2"
                )
        else:
            # Preserve non-Jana/fixture execution compatibility. Any attempt
            # to publish a Jana candidate still fails later at the established
            # canonical artifact boundary because no m40 can be hash-pinned.
            log(f"  [EDMA] Requested Jana m40 output is unavailable: {m40_path}")
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
    coo_displacements = parse_edma_coo_isotropic_displacements(
        coo, source_kind=IsotropicDisplacementKind.BISO,
    )
    frac, dens = parse_edma_coo(coo)
    raw_edma_sites = len(frac)
    if len(frac) == 0:
        log(f"EDMA coordinate output contains no peaks above plimit for {xplor_map.name}; writing empty CIF.")
        write_structure_bundle(
            cif, ref_ctx.cell, ref_ctx.spacegroup, ref_ctx.spacegroup_hm, [], structure_format,
            bound_edma_uiso=True,
        )
        return cif
    frac, dens = symmetry_merge_peaks(frac, dens, ref_ctx, merge_distance_a)
    elements = assign_elements_by_reference_composition(dens, ref_ctx.atoms, ref_ctx.composition)
    atoms = [
        AtomSite(
            label=f"{elements[i]}{i+1}", element=elements[i], frac=frac[i], density=float(dens[i]),
            uiso_angstrom2=(
                match_uiso_by_fractional_coordinate(frac[i], coo_displacements)
                if coo_displacements else None
            ),
        )
        for i in range(len(frac))
    ]
    # Preserve the canonical raw EDMA values in a separate scientific source
    # CIF. Later CIF-seeded cycles resolve this sidecar automatically; user and
    # Jana-facing artifacts receive the bounded export representation.
    raw_cif = cif.with_name(cif.stem + "_scientific_raw.cif")
    write_structure_cif(
        raw_cif, ref_ctx.cell, ref_ctx.spacegroup, ref_ctx.spacegroup_hm, atoms,
    )
    write_structure_bundle(
        cif, ref_ctx.cell, ref_ctx.spacegroup, ref_ctx.spacegroup_hm, atoms, structure_format,
        bound_edma_uiso=True,
    )
    raw_uiso = [float(atom.uiso_angstrom2) for atom in atoms if atom.uiso_angstrom2 is not None]
    if len(raw_uiso) != len(atoms):
        raise RuntimeError(f"EDMA displacement export is missing values for {len(atoms) - len(raw_uiso)} sites: {coo}")
    stats = export_uiso_statistics(raw_uiso)
    source_biso = [record.source_value for record in coo_displacements]
    log(
        f"  [EDMA] Displacement export · source Biso "
        f"{min(source_biso):.6f}-{max(source_biso):.6f} A^2 · {stats.site_count} sites · raw Uiso "
        f"{stats.raw_min:.6f}-{stats.raw_max:.6f} A^2 · allowed 0.010-0.150 A^2 · "
        f"lower-clamped {stats.lower_clamped} · upper-clamped {stats.upper_clamped} · "
        f"unchanged {stats.unchanged} · final {stats.final_min:.6f}-{stats.final_max:.6f} A^2 · "
        f"raw scientific CIF {raw_cif.name}"
    )
    clamped_sites = stats.lower_clamped + stats.upper_clamped
    independent_sites = len(edma_asu_atoms(atoms, ref_ctx.cell, ref_ctx.spacegroup))
    jana_sites = _m40_model_count(m40_path) if write_m40 and m40_path.is_file() else None
    lineage = {
        "threshold_sigma": float(plimit_sigma), "raw_edma_sites": raw_edma_sites,
        "cif_sites": len(atoms), "independent_asu_sites": independent_sites,
        "jana_m40_sites": jana_sites, "jana_selection": "numberofatoms composition",
    }
    cif.with_name(cif.stem + "_site_counts.json").write_text(
        json.dumps(lineage, indent=2), encoding="utf-8",
    )
    log(f"  [EDMA] Site lineage · raw detected {raw_edma_sites} · independent ASU {independent_sites} · "
        f"Jana m40 {jana_sites if jana_sites is not None else 'not requested'} · composition-constrained selection")
    if clamped_sites * 2 >= stats.site_count:
        log(
            f"  [EDMA] Warning: {clamped_sites} of {stats.site_count} exported sites "
            f"were clamped to the Uiso safety interval"
        )
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


QUALITY_CSV_COLUMNS = (
    "cycle", "source", "validation_profile", "map_path", "structure_path",
    "reference_f05", "reference_precision", "reference_recall", "reference_tp",
    "reference_fp", "reference_rmsd", "reference_phase_agreement",
    "amplitude_rf", "amplitude_cc", "amplitude_scale",
    "r_work", "r_free", "cc_work", "cc_free", "omit_map_correlation",
    "triplet_c3", "entropy_normalized", "map_concentration",
    "standardized_peakiness", "negative_density_mass",
    "n_measured_reflections", "n_work_reflections", "n_free_reflections",
    "n_triplets", "unavailable_reason",
    # Existing per-cycle fields retained for downstream compatibility. They
    # repeat on the two source rows belonging to the same cycle.
    "model_source", "model_in", "model_rmsd_A",
    "superflip_map", "superflip_edma_cif", "superflip_rmsd_A",
    "deblur_map", "deblur_edma_cif", "deblur_rmsd_A",
    "superflip_saved_run", "superflip_rvalue", "superflip_peaks",
    "superflip_symm", "superflip_derived_sg", "superflip_ref_match",
    "superflip_fom", "superflip_success_rate_percent", "superflip_mean_cycles",
    "recycle_map_correlation", "omit_superflip_correlation",
    "omit_superflip_rfree", "omit_deblur_correlation", "omit_deblur_rfree",
    "superflip_recall", "superflip_precision", "superflip_heavy_atom_count",
    "deblur_recall", "deblur_precision", "deblur_heavy_atom_count",
    "powder_repartition_avg_change_percent",
    "intensity_correction_avg_change_percent",
)


def file_sha256(path: Path) -> str:
    """Return the byte identity used by preview and Jana2020 handoff."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def allocate_run_directory(base_dir: Path) -> Tuple[str, Path]:
    """Atomically allocate the next Phase Studio-owned run directory."""
    base = Path(base_dir).expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    for sequence in range(1, 1_000_000):
        run_id = f"run_{sequence:04d}"
        candidate = base / run_id
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        return run_id, candidate
    raise RuntimeError(f"Cannot allocate a new run directory under {base}")


def xplor_artifact_identity(path: Path) -> Dict[str, object]:
    """Scientific map metadata used to audit SharpED/EDMA/Jana lineage."""
    resolved = Path(path).expanduser().resolve()
    xmap = read_xplor_map(resolved)
    values = np.asarray(xmap.data, dtype=np.float64).reshape(-1)
    return {
        "path": str(resolved),
        "sha256": file_sha256(resolved),
        "dimensions": (int(xmap.grid[0]), int(xmap.grid[3]), int(xmap.grid[6])),
        "index_ranges": (
            (int(xmap.grid[1]), int(xmap.grid[2])),
            (int(xmap.grid[4]), int(xmap.grid[5])),
            (int(xmap.grid[7]), int(xmap.grid[8])),
        ),
        "cell": tuple(float(value) for value in xmap.cell),
        "axis_order": str(xmap.axis_order),
        "minimum": float(np.min(values)),
        "maximum": float(np.max(values)),
        "mean": float(np.mean(values)),
        "std": float(np.std(values)),
    }


def format_xplor_artifact_identity(identity: Dict[str, object]) -> str:
    return (
        f"{identity['path']} · SHA-256 {str(identity['sha256'])[:12]} · "
        f"dimensions {identity['dimensions']} · ranges {identity['index_ranges']} · "
        f"cell {identity['cell']} · axes {identity['axis_order']} · "
        f"min/max {float(identity['minimum']):.6g}/{float(identity['maximum']):.6g} · "
        f"mean/std {float(identity['mean']):.6g}/{float(identity['std']):.6g}"
    )


def describe_xplor_artifact(path: Path) -> str:
    """Best-effort audit text; diagnostics must never break a valid stage."""
    resolved = Path(path).expanduser().resolve()
    try:
        return format_xplor_artifact_identity(xplor_artifact_identity(resolved))
    except Exception as exc:
        digest = file_sha256(resolved)[:12] if resolved.is_file() else "missing"
        return f"{resolved} · SHA-256 {digest} · metadata unavailable ({sanitize_error_details(exc)})"


def cif_artifact_identity(path: Path) -> Dict[str, object]:
    """Raw scientific CIF identity before any viewer transformation."""
    resolved = Path(path).expanduser().resolve()
    atoms = parse_cif_atoms(resolved)
    cell, spacegroup, hm = parse_cif_cell_and_sg(resolved)
    elements = collections.Counter(clean_element_symbol(atom.element) for atom in atoms)
    data_block = ""
    for line in resolved.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip().lower().startswith("data_"):
            data_block = line.strip()[5:]
            break
    return {
        "path": str(resolved),
        "sha256": file_sha256(resolved),
        "data_block": data_block,
        "atom_count": len(atoms),
        "elements": dict(sorted(elements.items())),
        "cell": (
            float(cell.a), float(cell.b), float(cell.c),
            float(cell.alpha), float(cell.beta), float(cell.gamma),
        ),
        "space_group": str(hm or ""),
        "symmetry_operations": len(spacegroup.operations()),
        "coordinate_representation": "fractional asymmetric-unit sites",
    }


_candidate_hash_cache: Dict[Tuple[str, int, int], str] = {}


def candidate_artifact_sha256(path: Path) -> str:
    """Cache completed-artifact hashes by resolved path and file identity."""
    resolved = Path(path).resolve()
    stat = resolved.stat()
    key = (str(resolved), int(stat.st_mtime_ns), int(stat.st_size))
    digest = _candidate_hash_cache.get(key)
    if digest is None:
        digest = file_sha256(resolved)
        _candidate_hash_cache[key] = digest
    return digest


def seal_result_candidate(candidate: ResultCandidate) -> ResultCandidate:
    """Attach immutable, source/cycle/threshold-specific artifact identity."""
    map_path = Path(candidate.map_path).expanduser().resolve()
    structure_path = Path(candidate.structure_path).expanduser().resolve()
    map_hash = candidate_artifact_sha256(map_path) if map_path.is_file() else ""
    structure_hash = candidate_artifact_sha256(structure_path) if structure_path.is_file() else ""
    jana_model_path = structure_path.with_suffix(".m40")
    jana_model_hash = (
        candidate_artifact_sha256(jana_model_path) if jana_model_path.is_file() else ""
    )
    jana_model_sites: Optional[int] = None
    if jana_model_hash:
        try:
            jana_model_sites = _m40_model_count(jana_model_path)
        except RuntimeError:
            jana_model_hash = ""
    formula = ""
    detected: Optional[int] = None
    unit_cell: Optional[Tuple[float, float, float, float, float, float]] = None
    space_group = ""
    edma_asu_composition = ""
    if candidate.usable_structure and structure_path.is_file():
        try:
            atoms = parse_cif_atoms(structure_path)
            detected = len(atoms)
            formula = structure_formula_from_cif(structure_path)
            cell, _sg, hm = parse_cif_cell_and_sg(structure_path)
            unit_cell = (
                float(cell.a), float(cell.b), float(cell.c),
                float(cell.alpha), float(cell.beta), float(cell.gamma),
            )
            space_group = str(hm or "")
            edma_asu_composition = edma_asu_composition_from_cif(structure_path)
        except Exception:
            pass
    source_id = "superflip" if candidate.source == "superflip" else "sharped"
    threshold_id = (
        f"t{float(candidate.edma_sigma):.2f}" if candidate.edma_sigma is not None else "t-na"
    )
    identity_hash = (structure_hash or map_hash or "missing")[:12]
    run_id = str(candidate.run_id or "").strip()
    run_prefix = f"{run_id}:" if run_id else ""
    candidate_id = f"{run_prefix}{source_id}:c{int(candidate.cycle):03d}:{threshold_id}:{identity_hash}"
    return replace(
        candidate,
        map_path=str(map_path),
        structure_path=str(structure_path),
        candidate_id=candidate_id,
        map_sha256=map_hash,
        structure_sha256=structure_hash,
        jana_model_path=str(jana_model_path) if jana_model_hash else "",
        jana_model_sha256=jana_model_hash,
        jana_model_site_count=jana_model_sites,
        formula=formula,
        detected_atom_count=detected,
        unit_cell=unit_cell,
        space_group=space_group,
        edma_asu_composition=edma_asu_composition,
    )


def promote_threshold_structure(
    source_path: Path, output_dir: Path, source: str, cycle: int, threshold: float,
) -> Path:
    """Copy a completed EDMA result to a content-addressed immutable artifact."""
    source_path = Path(source_path).resolve()
    if not source_path.is_file() or source_path.stat().st_size <= 0:
        raise RuntimeError(f"Completed EDMA structure is unavailable: {source_path}")
    digest = file_sha256(source_path)
    family = "superflip" if source == "superflip" else "sharped"
    threshold_text = f"{float(threshold):.2f}".replace(".", "p")
    canonical_dir = Path(output_dir).resolve() / "canonical"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    target = canonical_dir / (
        f"{family}_cycle_{int(cycle):03d}_{threshold_text}sigma_{digest[:12]}.cif"
    )
    source_m40 = source_path.with_suffix(".m40")
    target_m40 = target.with_suffix(".m40")
    source_raw_cif = edma_scientific_source_cif(source_path)
    target_raw_cif = target.with_name(target.stem + "_scientific_raw.cif")
    if target.is_file():
        if file_sha256(target) != digest:
            raise RuntimeError(f"Canonical candidate artifact changed unexpectedly: {target}")
    else:
        temporary = target.with_name(
            f".{target.name}.tmp-{os.getpid()}-{threading.get_ident()}"
        )
        try:
            with source_path.open("rb") as input_stream, temporary.open("wb") as output_stream:
                shutil.copyfileobj(input_stream, output_stream, length=1024 * 1024)
                output_stream.flush()
                os.fsync(output_stream.fileno())
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()
    if file_sha256(target) != digest:
        raise RuntimeError(f"Canonical candidate promotion failed its hash check: {target}")
    if source_m40.is_file():
        m40_digest = file_sha256(source_m40)
        if not target_m40.is_file():
            _copy_verified_handoff_artifact(source_m40, target_m40, m40_digest)
        elif file_sha256(target_m40) != m40_digest:
            raise RuntimeError(f"Canonical Jana model artifact changed unexpectedly: {target_m40}")
    if source_raw_cif != source_path:
        raw_digest = file_sha256(source_raw_cif)
        if not target_raw_cif.is_file():
            _copy_verified_handoff_artifact(source_raw_cif, target_raw_cif, raw_digest)
        elif file_sha256(target_raw_cif) != raw_digest:
            raise RuntimeError(
                f"Canonical EDMA scientific source artifact changed unexpectedly: {target_raw_cif}"
            )
    site_counts = source_path.with_name(source_path.stem + "_site_counts.json")
    if site_counts.is_file():
        target_counts = target.with_name(target.stem + "_site_counts.json")
        _copy_verified_handoff_artifact(site_counts, target_counts, file_sha256(site_counts))
    return target


def result_candidates_from_results(results: Sequence[CycleResult], *, include_unavailable: bool = False) -> List[ResultCandidate]:
    candidates: List[ResultCandidate] = []
    for result in results:
        model_source = str(result.model_source or "").strip().casefold()
        initialization = {
            "none": "Random phase start",
            "sharped_recycle_random": "Random phase start",
            "deblurred_xplor": "SharpED-seeded",
            "deblurred_edma_cif": "SharpED structure-seeded",
            "sharped_recycle": "SharpED-seeded",
            "superflip_xplor": "Charge-flipping-map seeded",
            "external_first_cycle": "External model-seeded",
        }.get(model_source, "Recorded model seed" if model_source else "Random phase start")
        feedback_adjusted = (
            result.intensity_correction_avg_change_percent is not None
            or result.powder_repartition_avg_change_percent is not None
        )
        reflection_provenance = (
            "Map Feedback-adjusted reflection data"
            if feedback_adjusted else "Original measured reflection data"
        )
        for source, quality, map_path, structure_path in (
            ("superflip", result.superflip_quality, Path(result.superflip_map), Path(result.superflip_edma_cif)),
            ("deblurred", result.deblur_quality, Path(result.deblur_map), Path(result.deblur_edma_cif)),
        ):
            if quality is None:
                continue
            usable_map = map_path.is_file() and map_path.stat().st_size > 0
            if not usable_map and not include_unavailable:
                continue
            usable_structure = False
            if structure_path.is_file() and structure_path.stat().st_size > 0:
                try:
                    usable_structure = bool(parse_cif_atoms(structure_path))
                except Exception:
                    usable_structure = False
            candidate = ResultCandidate(
                cycle=int(result.cycle), source=source,
                map_path=str(map_path.resolve()), structure_path=str(structure_path.resolve()), metrics=quality,
                usable_map=usable_map, usable_structure=usable_structure,
                map_feedback_change_percent=result.intensity_correction_avg_change_percent,
                superflip_initialization=initialization if source == "superflip" else "",
                reflection_input_provenance=reflection_provenance,
                edma_sigma=(
                    result.superflip_edma_sigma if source == "superflip"
                    else result.deblur_edma_sigma
                ),
                edma_enabled=(
                    result.superflip_edma_enabled if source == "superflip"
                    else result.deblur_edma_enabled
                ),
                sharped_model=result.sharped_model if source == "deblurred" else "",
                run_id=result.run_id,
            )
            candidates.append(seal_result_candidate(candidate))
    return candidates


def write_metrics_csv(path: Path, results: Sequence[CycleResult]) -> None:
    """Write one stable machine-readable row for every cycle/source candidate."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=QUALITY_CSV_COLUMNS)
        writer.writeheader()
        for candidate in result_candidates_from_results(results):
            cycle_result = next(result for result in results if int(result.cycle) == int(candidate.cycle))
            row = {
                "cycle": candidate.cycle,
                "source": "superflip" if candidate.source == "superflip" else "sharped",
                "validation_profile": profile_definition(results[0].validation_profile).profile.value if results else "",
                "map_path": candidate.map_path,
                "structure_path": candidate.structure_path if candidate.usable_structure else "",
            }
            quality_end = QUALITY_CSV_COLUMNS.index("unavailable_reason") + 1
            for column in QUALITY_CSV_COLUMNS[5:quality_end]:
                value = getattr(candidate.metrics, column, "")
                row[column] = "" if value is None else value
            legacy_values = {
                "model_source": cycle_result.model_source,
                "model_in": cycle_result.model_in,
                "model_rmsd_A": cycle_result.model_metric,
                "superflip_map": cycle_result.superflip_map,
                "superflip_edma_cif": cycle_result.superflip_edma_cif,
                "superflip_rmsd_A": cycle_result.superflip_metric,
                "deblur_map": cycle_result.deblur_map,
                "deblur_edma_cif": cycle_result.deblur_edma_cif,
                "deblur_rmsd_A": cycle_result.deblur_metric,
                "superflip_saved_run": cycle_result.superflip_saved_run,
                "superflip_rvalue": cycle_result.superflip_rvalue,
                "superflip_peaks": cycle_result.superflip_peaks,
                "superflip_symm": cycle_result.superflip_symm,
                "superflip_derived_sg": cycle_result.superflip_derived_sg,
                "superflip_ref_match": cycle_result.superflip_ref_match,
                "superflip_fom": cycle_result.superflip_fom,
                "superflip_success_rate_percent": cycle_result.superflip_success_rate,
                "superflip_mean_cycles": cycle_result.superflip_mean_cycles,
                "recycle_map_correlation": cycle_result.recycle_map_correlation,
                "omit_superflip_correlation": cycle_result.omit_superflip_correlation,
                "omit_superflip_rfree": cycle_result.omit_superflip_rfree,
                "omit_deblur_correlation": cycle_result.omit_deblur_correlation,
                "omit_deblur_rfree": cycle_result.omit_deblur_rfree,
                "superflip_recall": cycle_result.superflip_recall,
                "superflip_precision": cycle_result.superflip_precision,
                "superflip_heavy_atom_count": cycle_result.superflip_heavy_atom_count,
                "deblur_recall": cycle_result.deblur_recall,
                "deblur_precision": cycle_result.deblur_precision,
                "deblur_heavy_atom_count": cycle_result.deblur_heavy_atom_count,
                "powder_repartition_avg_change_percent": cycle_result.powder_repartition_avg_change_percent,
                "intensity_correction_avg_change_percent": cycle_result.intensity_correction_avg_change_percent,
            }
            row.update({key: "" if value is None else value for key, value in legacy_values.items()})
            writer.writerow(row)


def write_map_quality_report(
    path: Path,
    results: Sequence[CycleResult],
    selected_candidate: Optional[ResultCandidate] = None,
) -> None:
    candidates = result_candidates_from_results(results)
    if not results:
        return
    profile = ValidationProfile(results[0].validation_profile)
    definition = profile_definition(profile)
    # One recommendation PER SOURCE (Superflip and SharpED are never ranked
    # against each other) -- the same recommend_best_result the Result
    # Selection dialog uses for each of its source tables.
    per_source = {}
    for source in ("superflip", "deblurred"):
        source_candidates = [c for c in candidates if c.source == source]
        if source_candidates:
            per_source[source] = recommend_best_result(profile, source_candidates)
    lines = [
        "MAP QUALITY ASSESSMENT",
        "",
        f"Assessment: {definition.assessment_label}",
    ]
    for source, source_recommendation in per_source.items():
        chosen = source_recommendation.recommended_candidate
        lines.append(f"Recommended {result_source_title(source)} cycle: {chosen.label if chosen is not None else 'Unavailable'}")
        lines.append(f"  Reason: {source_recommendation.reason}")
    lines.extend([
        "",
        "Selection criteria:",
    ])
    for index, metric in enumerate(definition.primary_metrics, start=1):
        direction = "higher is better" if metric.higher_is_better else "lower is better"
        lines.append(f"{index}. {metric.label} — {direction}")
    lines.extend(["", "Candidates:"])
    show_feedback_column = any(c.map_feedback_change_percent is not None for c in candidates)
    header = ["Cycle", "Source"] + [metric.label for metric in definition.primary_metrics]
    if show_feedback_column:
        header.append("Map Feedback change (%)")
    lines.append(" | ".join(header))
    lines.append(" | ".join("---" for _ in header))
    for candidate in candidates:
        values = []
        for metric in definition.primary_metrics:
            value = candidate.metrics.value(metric.key)
            values.append("n/a" if value is None else f"{value:.6g}")
        if show_feedback_column:
            feedback_value = candidate.map_feedback_change_percent
            values.append("—" if feedback_value is None else f"{feedback_value:+.1f}%")
        lines.append(" | ".join([str(candidate.cycle), result_source_title(candidate.source)] + values))
    lines.extend(["", "All computed metrics:"])
    for candidate in candidates:
        lines.append(f"{candidate.label}:")
        available = []
        for metric in definition.all_report_metrics:
            value = getattr(candidate.metrics, metric.key, None)
            if value is not None:
                available.append(f"  {metric.key}: {value}")
        for key in (
            "n_measured_reflections", "n_work_reflections",
            "n_free_reflections", "n_triplets",
        ):
            available.append(f"  {key}: {getattr(candidate.metrics, key)}")
        lines.extend(available or ["  No valid metrics available."])
        if candidate.metrics.unavailable_reason:
            lines.append(f"  unavailable_reason: {candidate.metrics.unavailable_reason}")
    lines.extend(["", "Final user selection:"])
    if selected_candidate is None:
        lines.append("Pending")
    else:
        lines.append(selected_candidate.label)
        same_source = per_source.get(selected_candidate.source)
        recommended = same_source.recommended_candidate if same_source is not None else None
        lines.append(
            f"Recommended {result_source_title(selected_candidate.source)} cycle accepted"
            if recommended is not None and selected_candidate == recommended
            else f"Manual override (recommended {result_source_title(selected_candidate.source)} cycle: "
            f"{recommended.label if recommended is not None else 'unavailable'})"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# -----------------------------------------------------------------------------
# Qt GUI
# -----------------------------------------------------------------------------

CONFIG_FORM_VERTICAL_SPACING = 5
CONFIG_FORM_HORIZONTAL_SPACING = 14
CONFIG_PAGE_MARGIN_HORIZONTAL = 10
CONFIG_PAGE_MARGIN_VERTICAL = 8
CONFIG_MAJOR_SECTION_SPACING = 10
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


class FlowLayout(QLayout):
    """A left-to-right row that wraps to additional lines instead of
    shrinking its children -- used for the Help navigation link row, whose
    settings page is deliberately width-flexible (QSizePolicy.Ignored) and
    can otherwise end up narrower than the full "Setup / Input / Workflow /
    ... " link row needs, silently eliding several link labels at once.
    Wrapping guarantees every label always renders in full. Standard Qt
    FlowLayout recipe (Qt's own "Flow Layout" example), trimmed to what this
    app needs."""

    def __init__(self, parent: Optional[QWidget] = None, margin: int = 0, spacing: int = 4) -> None:
        super().__init__(parent)
        self._items: List[object] = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def addItem(self, item) -> None:  # noqa: N802 - Qt override
        self._items.append(item)

    def count(self) -> int:  # noqa: N802 - Qt override
        return len(self._items)

    def itemAt(self, index: int):  # noqa: N802 - Qt override
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):  # noqa: N802 - Qt override
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):  # noqa: N802 - Qt override
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - Qt override
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - Qt override
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect) -> None:  # noqa: N802 - Qt override
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):  # noqa: N802 - Qt override
        return self.minimumSize()

    def minimumSize(self):  # noqa: N802 - Qt override
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        left, top, right, bottom = self.getContentsMargins()
        size += QSize(left + right, top + bottom)
        return size

    def _do_layout(self, rect, test_only: bool) -> int:
        left, top, right, bottom = self.getContentsMargins()
        effective_rect = rect.adjusted(left, top, -right, -bottom)
        x, y = effective_rect.x(), effective_rect.y()
        line_height = 0
        spacing = self.spacing()
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + spacing
            if next_x - spacing > effective_rect.right() and line_height > 0:
                x = effective_rect.x()
                y += line_height + spacing
                next_x = x + hint.width() + spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + bottom


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
    "metadata_source": "Selects the authoritative source for unit-cell, space-group and composition metadata, independently of the reflection-data source -- for example, External HKL input with metadata taken from a Jana2020 .inflip or reference structure.",
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
    "superflip_exe": "Absolute path to the active Jana2020 scientific Superflip executable. Default: <active Jana2020 root>\\SUPERFLIP\\superflip.exe.",
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
    "compute_omit_maps": "Freeze a symmetry/Friedel-orbit-safe 5% holdout before the workflow and exclude it from every work-data and feedback step. Enables cross-validation metrics and profile-aware result recommendation for both Superflip and SharpED. Roughly doubles Superflip/SharpED time per cycle.",
    "compute_omit_rfree": "R_free is calculated automatically whenever the frozen 5% holdout is enabled because it is a primary cross-validation metric. Result recommendation uses explicit lexicographic criteria; no combined numeric score is created.",
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
    "reflection_data_mode": "Exact HKL column order. 'Set from .inflip' imports Jana's dataformat. The other choices use the displayed h k l · value · optional phase · uncertainty layout. Phase is in degrees; Phase Studio converts it to Superflip turns. FWHM choices describe peak width, not measurement uncertainty, so uncertainty-based significance is unavailable.",
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
    "powder_wavelength": "Radiation wavelength in Å, required to compute 2θ for powder overlap repartitioning. If left at 0, it is auto-detected from the Jana .m90 file, then the .inflip file's lambda/wavelength line, then from the reference file's _diffrn_radiation_wavelength tag; enter it manually if neither source has it.",
    "powder_separation_factor": "Multiplier of the mean FWHM (in the same 2θ-like units as the data) used to decide whether two reflections' Bragg peaks overlap: delta(2θ) < separation_factor * (FWHM1 + FWHM2) / 2. Matches Superflip's own fwhmseparation keyword.",
    "powder_redistribution_mix": "Blend factor for powder overlap repartitioning: 0 keeps each reflection's observed share of its group's total intensity; 1 replaces it entirely with the share implied by intensities calculated from the processed map. The group total is always conserved regardless of this value.",
    "sharped_base_url": "SharpED inference server base URL. The reference client uses https://sharped.fzu.cz/.",
    "sharped_api_token": "User API token sent as Authorization: Bearer during upload/status/download.",
    "show_beta_features": "When off (default), beta and experimental Phasing methods and the settings that only apply to them are hidden entirely from the Basic tabs, not just disabled. Enable to make them selectable.",
    "sharped_model": "SharpED server model name. Use default to query /sharp-ed/models and select the server default.",
    "sharped_elements": "Chemical elements sent to the SharpED server. Leave blank to derive unique non-H elements from the reference composition.",
    "sharped_outres": "Requested output sampling/resolution of the SharpED density map.",
    "sharped_map_value_exponent": "Reversible signed power transform sign(x)·|x|^a applied to map values before SharpED and inverted automatically on the returned SharpED map; 1.0 leaves values unchanged and 0 disables the transform. Only voxel values are affected — grid, cell, symmetry, format and the SharpED request itself are untouched.",
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


from phase_studio.ui_branding import (
    create_phase_studio_logo_pixmap, create_phase_studio_app_icon,
    apply_phase_studio_app_icon, create_phase_studio_brand_header,
    create_phase_studio_context_banner, apply_safe_dialog_geometry,
    fit_dialog_to_available_screen, clamp_window_to_available_screen,
    install_screen_geometry_guard, close_bootloader_splash,
    create_callout_label, phase_studio_brand_font,
)
from phase_studio.credentials import credential_store
from phase_studio.requirements_ui import (
    run_remediation_loop,
    show_requirement_remediation_dialog,
)
from phase_studio.review_edma import ReviewEDMAExecutor, ReviewOutcome, ReviewRequest


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
        self._restored_window_geometry = False
        self._restore_maximized_requested = False
        self.msg_queue: "queue.Queue[Tuple[str, object]]" = queue.Queue()
        self.review_edma_executor = ReviewEDMAExecutor(
            lambda outcome: self.msg_queue.put(("review_edma_done", outcome))
        )
        self.worker: Optional[threading.Thread] = None
        self.hkl_task_worker: Optional[threading.Thread] = None
        self._hkl_task_generation = 0
        self._active_hkl_task_id: Optional[int] = None
        self._completed_hkl_task_ids: set[int] = set()
        self.stop_after_cycle = threading.Event()
        self.stop_now = threading.Event()
        self.results: List[CycleResult] = []
        self._operation_states: dict = {}
        self._sharped_display_phases: dict = {}
        self.result_recommendation: Optional[ResultRecommendation] = None
        self.current_validation_profile = ValidationProfile.REFERENCE_FREE
        self.last_run_config: Optional[RunConfig] = None
        self._run_diagnostic_log: Optional[RunDiagnosticLog] = None
        self._resume_state: Optional[PipelineState] = None
        # 2.0.0 Autosolve: the adaptive-cycle policy driving the run currently
        # in progress (None outside launch_mode == "autosolve"), and which
        # stage that policy belongs to. "search" is Option A's whole run and
        # Option B's initial search; "map_feedback" is Option B's one
        # automatic refinement stage after the search converges.
        self._autosolve_policy: Optional[AdaptiveCyclePolicy] = None
        self._autosolve_stage: str = "search"
        # Set by AutosolveWindow's "Pass to Jana2020" action during a run,
        # alongside request_immediate_stop(): the resulting "cancelled" event
        # opens Result Selection over the completed results instead of just
        # leaving them idle the way an ordinary Cancel does (see
        # _poll_queue's "cancelled" handling).
        self._autosolve_pass_now_requested: bool = False
        # Shared early-Jana-handoff intent.  Completed candidates are frozen
        # before unfinished work is stopped, then Result Selection is opened
        # from the GUI queue terminal callback.
        self._handoff_pending: bool = False
        self._handoff_candidate_snapshot: Optional[List[ResultCandidate]] = None
        self._handoff_results_snapshot: Optional[List[CycleResult]] = None
        self._handoff_initial_source: Optional[str] = None
        self._handoff_selector_scheduled: bool = False
        # Autosolve end point, observed by AutosolveWindow: "idle" ->
        # "stopping" (Pass to Jana2020 pressed during a run) -> "selecting"
        # (the shared Result Selection is open) -> "handing_off" (user chose
        # a result) or "declined" (selector closed without a handoff).
        self.autosolve_handoff_state: str = "idle"
        # The visible window that should own the Result Selection dialog in
        # Autosolve (AutosolveWindow sets itself; this backend stays hidden).
        self.autosolve_dialog_parent = None
        # 2.0.1 guided Autosolve (see phase_studio/autosolve_review.py): the
        # dedicated Predicted-structure records, the two Review panels, the
        # current refinement block, and measured timings for the report.
        self.autosolve_predictions: List[guided.PredictionRecord] = []
        self.autosolve_panels: Dict[str, guided.ReviewPanel] = {}
        self.autosolve_refinement: Optional[dict] = None
        self.autosolve_activity: str = ""
        self.autosolve_timings: Dict[str, List[float]] = {}
        self._autosolve_task: Optional[threading.Thread] = None
        self._autosolve_search_deblur_sigma: float = 2.0
        self._sharped_catalog_models: Tuple[str, ...] = ()
        self.reference_atoms_for_plot: List[AtomSite] = []
        self.superflip_atoms_for_plot: List[AtomSite] = []
        self.deblur_atoms_for_plot: List[AtomSite] = []
        self._structure_source_paths: Dict[str, Optional[Path]] = {
            "reference": None, "superflip": None, "deblur": None,
        }
        self.structure_cell: Optional[gemmi.UnitCell] = None
        self.structure_axes: List[object] = []
        self._structure_interactive_axes: List[object] = []
        self._structure_depth_artists: List[StructureDepthArtists] = []
        self.structure_elev = 20.0
        self.structure_azim = 35.0
        # Zoom/pan is shared by the panels exactly like rotation is, and like
        # elev/azim it survives a re-render. Matplotlib's 3D zoom (right drag)
        # and pan (middle drag) both work by rewriting the axes' 3D limits, so
        # one pair of remembered limit triples covers both: the base limits the
        # cell geometry produces, and the limits currently displayed. The base
        # acts as a fingerprint -- when a new cell makes it change, the stored
        # view is stale and is dropped instead of being applied to a different
        # crystal.
        self.structure_view_base_limits: Optional[Tuple[Tuple[float, float], ...]] = None
        self.structure_view_limits: Optional[Tuple[Tuple[float, float], ...]] = None
        self._structure_view_drag_source: Optional[object] = None
        self._configuration_locked = False
        self.jana_wizard_context = JanaWizardContext()
        # One-shot guard so the Wizard Phase-recycling selector opens exactly
        # once per completed run. Reset when a new run starts, so a second run
        # in the same session opens it again.
        self._jana_auto_selector_shown = False
        self._workflow_log_once: set = set()
        self._active_run_id: str = ""
        self._run_event_context = threading.local()
        self._structure_job_lock = threading.Lock()
        self._structure_job_generation = 0
        self._structure_jobs: Dict[Tuple[str, int], StructureJobUpdate] = {}
        self._live_structures: Dict[str, StructureJobUpdate] = {}
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
        QTimer.singleShot(0, self._apply_adaptive_window_geometry)
        self.help_shortcut = QShortcut(QKeySequence(Qt.Key_F1), self)
        self.help_shortcut.setContext(Qt.WindowShortcut)
        self.help_shortcut.activated.connect(self._open_context_help)
        self.load_settings()
        QTimer.singleShot(250, self.refresh_sharped_models)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll_queue)
        self.timer.start(50)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not getattr(self, '_updates_attached', False):
            self._updates_attached = True
            from phase_studio.update_ui import update_service
            update_service().attach(self)

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

        brand_header=create_phase_studio_brand_header()
        from phase_studio.update_ui import wizard_update_menu
        self.version_menu=wizard_update_menu(self,mode=None,automatic=False)
        self.version_menu.setText(__version__)
        self.version_menu.setToolTip('Version and updates')
        self.version_menu.setAccessibleName('Version '+__version__+', updates')
        badge=brand_header.findChild(QLabel,'versionBadge')
        if badge is not None:
            badge.parentWidget().layout().replaceWidget(badge,self.version_menu)
            badge.hide()
        self.version_menu.menu().addSeparator()
        self.version_menu.menu().addAction('About Phase Studio').triggered.connect(lambda:self._open_help_section('about'))
        left_layout.addWidget(brand_header)

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
        basic_contents_row = FlowLayout(spacing=4)
        basic_contents_label = QLabel("CONTENTS")
        basic_contents_label.setObjectName("helpContentsLabel")
        basic_contents_row.addWidget(basic_contents_label)
        for link_text, anchor in (
            ("Setup", "setup"), ("Input", "input"), ("Workflow", "workflow"),
            ("Output", "output"), ("Map feedback", "map_feedback"), ("Jana2020", "jana_integration"), ("About", "about"),
        ):
            link = QToolButton()
            link.setObjectName("helpNavLink")
            link.setText(link_text)
            link.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            link.setCursor(Qt.PointingHandCursor)
            link.clicked.connect(lambda _checked=False, target=anchor: self._open_help_section(target))
            basic_contents_row.addWidget(link)
        basic_help_tab.addLayout(basic_contents_row)
        setup_help_layout = self._add_help_section(basic_help_tab, "setup", "Phase Studio guide", """
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
            <p>After a successful Jana2020 run, <b>Pass to Jana2020</b> opens the result selector with the profile-aware recommendation preselected. In standalone use, <b>Save map and model</b> opens the same selector. Final interpretation and refinement remain in Jana2020.</p>
        """)
        setup_help_layout.insertWidget(1, WorkflowDiagram())
        self._add_help_callout(setup_help_layout, "Tip", "Validate the reflection interpretation and review the selected preset values before starting a run.", kind="tip")
        self._add_back_to_contents(setup_help_layout)
        input_help_layout = self._add_help_section(basic_help_tab, "input", "Input reference", """
            <h3>Data input</h3>
            <p><b>Input mode</b> chooses the reflection source: <b>Jana2020 .inflip</b>, <b>Jana2020 .inflip with overrides</b>, or <b>External HKL</b>. In Jana modes, the .inflip file's fbegin/endf block is the default HKL source and its cell/space-group/composition keywords can provide crystallographic metadata; External mode uses reflection data loaded independently of Jana2020 and requires metadata from another source.</p>
            <p><b>Jana2020 .inflip file</b> is the Superflip input file used by the two Jana input modes.</p>
            <p><b>External HKL file</b> replaces only the fbegin/endf block in override mode, or is the required reflection source in external mode.</p>
            <p><b>HKL format</b> is the exact displayed column order. <b>Set from .inflip</b> imports Jana's dataformat. For example, <b>h k l · F · phase · σ(F)</b> means Miller indices, amplitude, phase in degrees, and amplitude uncertainty. FWHM formats contain peak width rather than measurement uncertainty, so validation and completeness show intensity and peak width separately; no uncertainty-based significance is inferred.</p>
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
            <p>Both recycling methods are hidden unless <b>Show beta and experimental features</b> is checked on Advanced &rarr; Setup. Selecting one disables Next-cycle model, XPLOR damping, Symmetrize SharpED map and the per-cycle EDMA checkboxes below it, since the method defines its own next-cycle map; use <b>Run EDMA on final map</b> (Optional processing) instead. Each completed map is assessed with the active three-metric validation profile; the cycle-to-cycle map correlation remains available in the detailed output.</p>
            <p><b>Next-cycle model</b> (Superflip phasing method only) is the authoritative source for cycle 2 onward: <b>None</b> forces a one-cycle run; <b>Superflip map (XPLOR)</b> cycles without SharpED processing; <b>SharpED map (XPLOR)</b> uses the SharpED-processed XPLOR map; <b>SharpED structure (EDMA CIF)</b> uses the EDMA structure extracted from the SharpED map and ignores XPLOR damping.</p>
            <p><b>XPLOR damping (1/x)</b> (Superflip phasing method, XPLOR next-cycle models only) is the inverse damping factor: 1.0 means no damping, 0.5 is equivalent to the previous factor 2.0, 0.25 to factor 4.0.</p>
            <p><b>Excluded atoms</b> removes selected atom labels from CIF modelfiles before the next Superflip cycle (comma/semicolon/whitespace-separated); it does not apply to XPLOR-only model paths.</p>
            <h3>SharpED model</h3>
            <p><b>Model</b> is the SharpED server model name sent with every deblurring request; <b>Refresh models</b> fetches the current list from the configured server and updates this selector. Server URL and API token are on Advanced &rarr; Setup; elements, output resolution, map value exponent and network/upload settings are on Advanced &rarr; SharpED.</p>
            <h3>Optional processing</h3>
            <p>Under <b>Superflip cycle</b> (used when Phasing method is Superflip):</p>
            <ul>
                <li><b>Run EDMA on Superflip map</b> &mdash; peak-search the Superflip XPLOR map and export CIF/XYZ/PDB.</li>
                <li><b>Run SharpED</b> &mdash; process the Superflip map with the SharpED server. If disabled, the SharpED map used downstream is just a copy of the Superflip map.</li>
                <li><b>Symmetrize SharpED map with Superflip (beta)</b> &mdash; after SharpED processing, run Superflip in symmetry mode (no charge flipping) with the SharpED map as modelfile, averaging it according to the supplied space-group symmetry. Hidden unless beta/experimental features are enabled.</li>
                <li><b>Run EDMA on SharpED map</b> &mdash; peak-search the SharpED (or symmetrized) XPLOR map and export CIF/XYZ/PDB.</li>
                <li><b>Compute OMIT validation maps (5% holdout)</b> &mdash; freezes a symmetry/Friedel-orbit-safe holdout before cycle 1 and excludes it from every work-data and feedback step. Enables the cross-validation assessment profiles and OMIT map correlation. Roughly doubles Superflip/SharpED time per cycle.</li>
                <li><b>Calculate R_free on the 5% holdout</b> &mdash; is selected automatically with the option above and reports R_free from reflections never admitted to work data. Recommendation follows the active profile's explicit three-metric priority without a combined score.</li>
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
        map_feedback_layout = self._add_help_section(basic_help_tab, "map_feedback", "Map feedback reference", f"""
            <p>Each of the three mechanisms below has its own <b>Enable</b> checkbox at the top of its group; unchecking it grays out the rest of that group and skips the mechanism entirely. <b>Start after cycle</b> keeps its own 1-999 range regardless of the current <b>Cycles</b> value (Basic &rarr; Workflow), so it can be set up ahead of raising Cycles; the fields below it stay grayed out with a hint whenever the current Cycles value cannot reach the configured starting cycle.</p>
            <h3>Missing-reflection completion</h3>
            <p><b>Start after cycle</b> is the first completed cycle whose map is used to add missing reflections for the next cycle. <b>Maximum added reflections (%)</b> caps generated missing reflections as a percent of the current reflection count, preventing feedback from overwhelming measured data.</p>
            <h3>Intensity correction</h3>
            <p><b>Start after cycle</b> is the first completed cycle whose map is used to damp observed intensities for the next cycle. <b>Correction damping</b> ranges from 0 (keeps observed values) to 1 (replaces them with scaled map-derived values). <b>Apply when value/&sigma; &lt;</b> limits correction to weak non-zero reflections below this value/&sigma;; 0 applies it to all non-zero reflections. The average intensity change across corrected reflections is plotted on the <b>Intensity correction</b> convergence tab (lower is better).</p>
            <h3>Powder overlap repartitioning</h3>
            <p>Only applies to reflections carrying an FWHM value ({html.escape(format_reflection_data_mode(REFLECTION_DATA_MODE_INTENSITY_FWHM))} or {html.escape(format_reflection_data_mode(REFLECTION_DATA_MODE_AMPLITUDE_FWHM))}). <b>Start after cycle</b> is the first completed cycle whose map is used to redistribute overlapping reflections for the next cycle. Reflections whose Bragg peaks overlap in a powder pattern -- delta(2θ) below <b>Separation factor</b> times the mean of their FWHM, Superflip's own <code>fwhmseparation</code> convention -- have their combined observed intensity redistributed between them using intensities calculated by FFT from that cycle's map (the SharpED map when SharpED deblurring is enabled, otherwise a copy of the Superflip map), blended by <b>Map ratio mix</b> (0 keeps the observed split, 1 uses the map split fully; default 1). The group total is always conserved. <b>Wavelength</b> is required to compute 2θ; if left at 0 it is auto-detected first from the loaded <code>.inflip</code> file's <code>lambda</code>/<code>wavelength</code> line, then from the reference file's <code>_diffrn_radiation_wavelength</code> tag -- enter it manually if neither source has it. Each time it runs, a <code>cycle_NNN_powder_repartitioning.log</code> file is written with the number of overlap groups considered, their average size, their average intensity change, and the before/after intensities for every reflection in the 3 groups with the largest d-spacing. The average intensity change per group is also plotted on the <b>Powder repartitioning</b> convergence tab (lower is better).</p>
        """)
        self._add_help_callout(map_feedback_layout, "Warning", "Missing-reflection completion and intensity correction rewrite the observed HKL data fed into later cycles, not just the model. Review the reconstruction carefully before trusting downstream cycles.", kind="warning")
        self._add_back_to_contents(map_feedback_layout)
        jana_integration_layout = self._add_help_section(basic_help_tab, "jana_integration", "Jana2020 data and workflows", """
            <p>Phase Studio supports Jana2020 .inflip data and scientific workflows.
            When launched from the Jana2020 Workflow Wizard, completed results can
            be selected and sent back with <b>Pass to Jana2020</b>.</p>
            <p>Jana developers integrate the complete Phase Studio
            developer ONEDIR package containing Phase_studio.exe and its complete _internal runtime. Do not replace the scientific Superflip executable.</p>
        """)
        self._add_back_to_contents(jana_integration_layout)
        about_layout = self._add_help_section(basic_help_tab, "about", "About Phase Studio", f"""
            <h2>Phase Studio</h2>
            <p>Phase Studio is a crystallographic reconstruction workflow integrating Superflip, SharpED and EDMA with Jana2020-oriented workflows.</p>
            <h3>Developed at</h3>
            <p>Department of Structure Analysis<br>Institute of Physics of the Czech Academy of Sciences</p>
            <h3>Phase Studio author and lead developer</h3>
            <p><b>Jiří Zelenka</b><br><a href="mailto:zelenka@fzu.cz">zelenka@fzu.cz</a></p>
            <p>Fyzikální ústav AV ČR, v. v. i. (Institute of Physics of the Czech Academy of Sciences).</p>
            <p>Phase Studio is free open-source software under the MIT license. Scientific publications reporting work performed with Phase Studio should cite Jiří Zelenka, Phase Studio, version {__version__}, <a href="https://github.com/ji-ze/Phase-Studio">the software repository</a>. Citation is the project's scientific-attribution policy, separate from the MIT license.</p>
            <h3>SharpED developers — separate hosted service</h3>
            <p><b>Jiří Zelenka</b></p>
            <p><b>Jan Rohlíček</b><br><a href="mailto:rohlicek@fzu.cz">rohlicek@fzu.cz</a></p>
            <p><b>Monika Kučeráková</b></p><p><b>Zdeněk Buk</b></p>
            <p>SharpED account, personal API token and the applicable access entitlement/service terms are required for inference. A free Phase Studio license does not include a SharpED subscription or free inference entitlement.</p>
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
        from phase_studio.update_ui import add_update_controls
        add_update_controls(about_layout, self)
        self._add_back_to_contents(about_layout)
        basic_help_tab.addSpacing(CONFIG_MAJOR_SECTION_SPACING)
        basic_help_tab.addStretch(1)

    def _build_advanced_setup_tab(self) -> None:
        setup_tab = self._add_settings_tab("Setup", advanced=True)
        self._create_settings_page_header(setup_tab, "Setup", "adv_setup")
        programs_form = self._add_form_group(setup_tab, "External programs")
        self._add_path(programs_form, "superflip_exe", "Superflip executable", r"C:\Jana2020\SUPERFLIP\superflip.exe", "file", "Executables (*.exe);;All files (*)")
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
        self._add_text(sharped_api_form, "sharped_base_url", "Server URL", DEFAULT_SERVER_URL)
        self._add_text(sharped_api_form, "sharped_api_token", "SharpED access key", os.environ.get("SHARPED_API_TOKEN", ""))
        try:
            self.inputs["sharped_api_token"].setEchoMode(QLineEdit.Password)  # type: ignore[attr-defined]
        except Exception:
            pass
        token_link_row = QHBoxLayout()
        self.sharped_account_button = QPushButton("Account access…")
        self.sharped_account_button.clicked.connect(self._manage_sharped_access)
        token_link_row.addWidget(self.sharped_account_button)
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
        self._create_settings_page_header(superflip_tab, "Superflip", "superflip")
        calculation_form = self._add_form_group(superflip_tab, "Calculation")
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
        self._create_settings_page_header(edma_tab, "EDMA", "edma")
        peak_form = self._add_form_group(edma_tab, "Peak extraction")
        self._add_dspin(peak_form, "plimit_superflip", "Superflip threshold", NORMAL_EDMA_THRESHOLD_SIGMA, 0.0, 100.0, 0.1, 3)
        self._add_dspin(peak_form, "plimit_deblur", "SharpED threshold (σ)", NORMAL_EDMA_THRESHOLD_SIGMA, 0.0, 100.0, 0.1, 3)
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
        self._create_settings_page_header(sharped_advanced_tab, "SharpED", "sharped")
        inference_form = self._add_form_group(sharped_advanced_tab, "Inference")
        self._add_text(inference_form, "sharped_elements", "Elements", "")
        self.inputs["sharped_elements"].setPlaceholderText("Auto from composition")  # type: ignore[attr-defined]
        self._add_dspin(inference_form, "sharped_outres", "Output resolution (Å)", 0.2, 0.001, 10.0, 0.05, 4)
        self._add_dspin(
            inference_form, "sharped_map_value_exponent", "Map value exponent",
            SHARPED_MAP_VALUE_EXPONENT_DEFAULT,
            SHARPED_MAP_VALUE_EXPONENT_MIN, SHARPED_MAP_VALUE_EXPONENT_MAX, 0.05, 3,
        )

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
        advanced_contents_row = FlowLayout(spacing=4)
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
        advanced_help_tab.addLayout(advanced_contents_row)
        adv_setup_help_layout = self._add_help_section(advanced_help_tab, "adv_setup", "Setup reference", """
            <h3>External programs</h3>
            <p><b>Superflip executable</b> is the absolute path to the scientific executable under the active Jana2020 root (normally <code>SUPERFLIP\\superflip.exe</code>).</p>
            <p><b>EDMA executable</b> is the absolute path to the Jana2020 EDMA executable used for peak extraction and structure export from XPLOR density maps (default <code>C:\\Jana2020\\SUPERFLIP\\EDMA.exe</code>).</p>
            <p>Superflip and EDMA are external third-party programs, distributed by their own authors and not bundled with Phase Studio. Both are normally installed with Jana2020; if a path is not configured, Phase Studio looks for them in <code>C:\\Jana2020\\SUPERFLIP</code> when a workflow starts and fills the path in automatically. Official downloads: <a href="https://superflip.fzu.cz/download/superflip_win.zip">superflip_win.zip</a> and <a href="https://superflip.fzu.cz/download/EDMA_win.zip">EDMA_win.zip</a>; license information at <a href="https://superflip.fzu.cz/">superflip.fzu.cz</a>.</p>
            <p>Requirements are checked immediately before a workflow starts, and only for the stages that workflow actually uses -- a workflow that never runs EDMA is never asked for EDMA.</p>
            <h3>SharpED connection</h3>
            <p><b>Server URL</b> is the SharpED inference-server base URL; the documented Public API uses <code>https://jana.fzu.cz/</code>. <b>API token</b> authorizes upload/status/download requests and is never written to logs or error messages.</p>
            <p>SharpED processing needs an active Jana2020 or SharpED account. Sign in at <a href="https://sharped.fzu.cz/sharp-ed">sharped.fzu.cz/sharp-ed</a> and create a token with <b>Create token</b>, then paste it into <b>API token</b> above.</p>
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
        self._add_help_callout(superflip_help_layout, "Starting point", "CF and the supplied preset values are initial settings only; choose parameters appropriate for the dataset and intended method.", kind="tip")
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
        self._add_help_callout(edma_help_layout, "Important", "Select each EDMA threshold for its map and assess the resulting peaks; there is no universal threshold.", kind="warning")
        self._add_back_to_contents(edma_help_layout, advanced=True)
        sharped_help_layout = self._add_help_section(advanced_help_tab, "sharped", "SharpED guide", """
            <h3>What SharpED does</h3>
            <p>SharpED processes and deblurs the XPLOR density map from Superflip. After EDMA extraction the result can be inspected in Structure Comparison, used for EDMA, optionally symmetrized, used as a next-cycle XPLOR model, or handed to Jana2020. If server processing is disabled, the workflow continues without a genuinely processed SharpED result.</p>
            <p><b>Model</b> selection is on Basic &rarr; Workflow. Server connection is on Advanced &rarr; Setup (server URL/API token); elements, output resolution, map value exponent and upload/network settings are on Advanced &rarr; SharpED (everything else below).</p>
            <h3>1. Server connection</h3>
            <p><b>Server URL</b> is the inference-server address. <b>API token</b> authenticates server requests. Obtain a token from the SharpED project and API-token page.</p>
            <h3>2. Model and elements</h3>
            <p><b>Model</b> (Basic &rarr; Workflow) is sent to the server; <b>Refresh models</b> updates the selector; <code>default</code> uses the server default. <b>Elements</b> are sent to SharpED; when blank, Phase Studio derives unique non-hydrogen elements from the reference composition.</p>
            <h3>3. Output resolution</h3>
            <p><b>Output resolution (&Aring;)</b> is the requested sampling/resolution of the SharpED density map.</p>
            <h3>4. Map value exponent</h3>
            <p><b>Map value exponent</b> <i>a</i> applies a reversible signed power transform to the voxel values of the map sent to SharpED, and the exact inverse transform to the map SharpED returns. Forward: <code>sign(x)&middot;|x|<sup>a</sup></code>. Inverse: <code>sign(x)&middot;|x|<sup>1/a</sup></code>. The transform is signed because density maps contain negative voxel values, for which a plain <code>x<sup>a</sup></code> is not real-valued.</p>
            <p>Qualitatively, <i>a</i> &lt; 1 compresses the dynamic range of the absolute map values, <i>a</i> = 1 (the default) leaves the map unchanged, and <i>a</i> &gt; 1 expands the dynamic range. <i>a</i> = 0 disables the transform entirely &mdash; <code>x<sup>0</sup></code> discards the magnitude and cannot be inverted, so it is treated as a bypass rather than as a transform.</p>
            <p>Only voxel values are affected. Grid, origin, cell, symmetry, map dimensions, map format, metadata and the SharpED request parameters are all unchanged, and everything downstream of SharpED (EDMA, symmetrization, metrics, phase recycling, visualization, export and the Jana2020 hand-off) always sees values in the original map-value domain. No normalization, shifting, clipping or rescaling of any kind is added.</p>
            <p>This is an experimental preprocessing option offered for exploration. Phase Studio makes no claim that any particular exponent improves crystallographic results; the default of 1.000 reproduces the standard workflow exactly.</p>
            <h3>5. Upload and network</h3>
            <p><b>Upload limit</b> checks XPLOR size locally; its application default is 100 MB and 0 disables this local check (confirm the actual limit with the configured service). If Voxel grid is empty/omit, Phase Studio can add a coarser Superflip voxel keyword before map calculation so the native Superflip XPLOR fits under this limit. <b>HTTP timeout</b> covers model queries, upload, status and download requests and is enforced at 600 seconds minimum. <b>Polling interval</b> sets the delay between status checks. <b>Maximum polls</b> limits those checks; <b>-1</b> means no fixed polling limit.</p>
            <h3>6. SharpED in iterative workflows</h3>
            <p><b>Run SharpED</b> (Basic &rarr; Workflow &rarr; Optional processing) enables server processing; if disabled, the SharpED map used downstream is a copy of the Superflip map. <b>Symmetrize SharpED map with Superflip (beta)</b> performs symmetry averaging, not another charge-flipping reconstruction. Next-cycle model's <b>SharpED map (XPLOR)</b> option feeds the SharpED map into the next cycle; <b>SharpED structure (EDMA CIF)</b> feeds its EDMA structure instead.</p>
            <h3>7. Phase-recycling methods (beta/experimental)</h3>
            <p><b>1st Superflip, then SharpED (beta)</b> and <b>SharpED (experimental)</b> use SharpED for phase recycling instead of iterative Superflip cycling. They are hidden from the Phasing method list by default; check <b>Show beta and experimental features</b> (Advanced &rarr; Setup) to select them. Neither is production-ready.</p>
        """, advanced=True)
        sharped_link_row = QHBoxLayout()
        sharped_link_row.addWidget(QLabel("SharpED project and API token"))
        sharped_link_row.addWidget(self._external_link_icon("https://sharped.fzu.cz/", "Open the SharpED project and API-token page"))
        sharped_link_row.addStretch(1)
        sharped_help_layout.addLayout(sharped_link_row)
        self._add_help_callout(sharped_help_layout, "Important", "SharpED processing requires a valid API token and network access.", kind="warning")
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
        # Result handoff is visible only in a Jana Wizard session.
        self.jana_action_btn = QPushButton("Save map and model")
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
        self.stop_now_btn.setToolTip("Terminate the currently running external Superflip/EDMA process and stop the workflow as soon as possible.")
        self.clear_btn.setToolTip("Clear the log panel and reset the plotted metrics for the current GUI session.")
        self.run_btn.clicked.connect(self.start_run)
        self.continue_btn.clicked.connect(self.continue_run)
        self.stop_btn.clicked.connect(self.request_stop_after_cycle)
        self.stop_now_btn.clicked.connect(self.request_immediate_stop)
        self.clear_btn.clicked.connect(self.clear_log_plot)
        self.jana_action_btn.clicked.connect(self._on_jana_action_clicked)
        # Stretch and minimum width follow each button's own text (see
        # _fit_primary_action_buttons), so at constrained logical widths the
        # longest label -- "Save map and model" -- keeps its full text instead
        # of receiving the same third of the row as "Run phasing".
        self._primary_action_row = primary_buttons
        primary_buttons.addWidget(self.run_btn, 1)
        primary_buttons.addWidget(self.continue_btn, 1)
        primary_buttons.addWidget(self.jana_action_btn, 1)
        # Allocate by measured label length. QSizePolicy.Ignored keeps this row
        # responsive, so the stretch factors must still reserve enough width
        # for "Stop immediately" at Windows high-DPI scales.
        self._secondary_action_row = secondary_buttons
        secondary_buttons.addWidget(self.stop_btn, 10)
        secondary_buttons.addWidget(self.stop_now_btn, 7)
        secondary_buttons.addWidget(self.clear_btn, 5)
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
        self.overall_progress_label = QLabel("Overall workflow")
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
        self.progress_bar.setToolTip("Cycle-level progress indicator for the iterative workflow.")
        run_status_layout.addWidget(self.progress_bar)
        current_cycle_header = QHBoxLayout()
        current_cycle_label = QLabel("Current operation")
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
        # between cycles -- see _apply_cycle_progress_state(). Grouped into
        # its own tight sub-layout (1px) so the label reads as visually
        # attached to its bar, distinct from the normal 3px spacing between
        # otherwise-unrelated Run Status rows.
        self.superflip_repeat_group = QWidget()
        superflip_repeat_layout = QVBoxLayout(self.superflip_repeat_group)
        superflip_repeat_layout.setContentsMargins(0, 0, 0, 0)
        superflip_repeat_layout.setSpacing(1)
        self.superflip_repeat_detail = QLabel("")
        self.superflip_repeat_detail.setObjectName("superflipRepeatDetail")
        self.superflip_repeat_detail.setWordWrap(True)
        superflip_repeat_layout.addWidget(self.superflip_repeat_detail)
        self.superflip_repeat_progress = QProgressBar()
        self.superflip_repeat_progress.setObjectName("superflipRepeatProgress")
        self.superflip_repeat_progress.setRange(0, 1)
        self.superflip_repeat_progress.setValue(0)
        self.superflip_repeat_progress.setTextVisible(False)
        self.superflip_repeat_progress.setFixedHeight(6)
        self.superflip_repeat_progress.setToolTip("Superflip's own repeatmode attempt counter for the running Superflip stage -- subordinate to the stage progress above.")
        superflip_repeat_layout.addWidget(self.superflip_repeat_progress)
        self.superflip_repeat_group.setVisible(False)
        run_status_layout.addWidget(self.superflip_repeat_group)
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
        # Some tab names are genuinely long; scroll
        # rather than silently elide several of them at once when the panel
        # is narrow.
        self.metrics_tabs.setUsesScrollButtons(True)
        self.metrics_tabs.tabBar().setElideMode(Qt.ElideNone)
        self.metrics_figures: Dict[str, Figure] = {}
        self.metrics_axes: Dict[str, object] = {}
        self.metrics_canvases: Dict[str, FigureCanvas] = {}
        self.metrics_interactions: Dict[str, MetricsPlotInteraction] = {}
        self._metrics_hover_series: Dict[str, list] = {}
        self._metrics_last_render_args: Dict[str, dict] = {}
        self._metrics_tab_keys: List[str] = []
        initial_definition = profile_definition(ValidationProfile.REFERENCE_FREE)
        self._metrics_detail_supported_keys = {"quality_0", "quality_1", "quality_2", "map_feedback_change"}
        tab_specs = [
            (
                f"quality_{index}", metric.label,
                f"{metric.label}. {'Higher is better.' if metric.higher_is_better else 'Lower is better.'}",
            )
            for index, metric in enumerate(initial_definition.primary_metrics)
        ]
        # Restored historical diagnostic (removed from display, never from
        # computation, by the "exactly three metrics" standardization). Always
        # built as a 4th tab -- like the other three -- so it can be shown or
        # hidden live via setTabVisible() as the Map Feedback intensity
        # correction checkbox is toggled, instead of being torn down and
        # rebuilt. update_metrics_plot() hides it whenever that checkbox is
        # off. It is diagnostic only: never a ranking/recommendation input.
        tab_specs.append((
            "map_feedback_change", "Map Feedback change (%)",
            "Average intensity change caused by that cycle's map-based intensity correction, "
            "relative to the observed reflection intensities before correction. Lower is better; "
            "it should shrink toward 0% as the map increasingly agrees with the observed data. "
            "Each cycle's point reflects the correction that fed its input, so it lags one cycle "
            "behind the correction run itself.",
        ))
        for key, title, tooltip in tab_specs:
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
            self.metrics_tabs.setTabToolTip(tab_index, tooltip)
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
        self.metrics_tabs.setTabVisible(len(tab_specs) - 1, False)
        self.assessment_label = QLabel(f"Assessment: {initial_definition.assessment_label}")
        self.assessment_label.setObjectName("metricsAssessmentLabel")
        metrics_layout.addWidget(self.assessment_label)
        # ----- Shared interaction control strip: its own row, ABOVE the tab
        # bar, rather than a QTabWidget corner widget sharing the tab bar's
        # own horizontal strip -- 6 scientific tab names (some, like "Powder
        # repartitioning", genuinely long) need that whole strip for
        # themselves, or Qt silently elides several of them at once. Always
        # acts on whichever tab is currently selected. -----
        metrics_toolbar = QWidget()
        metrics_toolbar_layout = QHBoxLayout(metrics_toolbar)
        metrics_toolbar_layout.setContentsMargins(6, 0, 4, 4)
        metrics_toolbar_layout.setSpacing(6)
        self.metrics_hint_label = QLabel("Wheel zoom · Drag pan · Double-click reset")
        self.metrics_hint_label.setObjectName("metricsHintLabel")
        metrics_toolbar_layout.addWidget(self.metrics_hint_label)
        metrics_toolbar_layout.addStretch(1)
        self.metrics_full_range_btn = QPushButton("Full range")
        self.metrics_detail_btn = QPushButton("Detail")
        for btn in (self.metrics_full_range_btn, self.metrics_detail_btn):
            btn.setObjectName("metricsViewToggle")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
        metrics_mode_group = QButtonGroup(metrics_toolbar)
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
        metrics_toolbar_layout.addWidget(self.metrics_full_range_btn)
        metrics_toolbar_layout.addWidget(self.metrics_detail_btn)
        self.metrics_reset_btn = QPushButton("Reset view")
        self.metrics_reset_btn.setObjectName("metricsControlButton")
        self.metrics_reset_btn.setCursor(Qt.PointingHandCursor)
        self.metrics_reset_btn.setToolTip("Return to the automatically calculated full-data view.")
        self.metrics_reset_btn.setEnabled(False)
        self.metrics_reset_btn.clicked.connect(lambda _checked=False: self._reset_metrics_view(self._current_metrics_key()))
        metrics_toolbar_layout.addWidget(self.metrics_reset_btn)
        metrics_layout.addWidget(metrics_toolbar)
        metrics_layout.addWidget(self.metrics_tabs, 1)
        self.metrics_tabs.currentChanged.connect(self._on_metrics_tab_changed)
        self._on_metrics_tab_changed(self.metrics_tabs.currentIndex())
        self.result_splitter.addWidget(metrics_section)

    def _build_structure_comparison_section(self) -> None:
        structure_section, structure_layout = self._make_result_section("STRUCTURE COMPARISON")
        self.structure_view_mode = "molecule"
        controls = QHBoxLayout()
        self.structure_element_legend = QLabel("")
        self.structure_element_legend.setObjectName("elementLegend")
        self.structure_element_legend.setTextFormat(Qt.RichText)
        self.structure_element_legend.setWordWrap(True)
        controls.addWidget(self.structure_element_legend, 1)
        controls.addWidget(QLabel("View:"))
        self.structure_molecule_view_button = QPushButton("Complete molecules")
        self.structure_full_cell_view_button = QPushButton("Full cell")
        for button in (self.structure_molecule_view_button, self.structure_full_cell_view_button):
            button.setObjectName("metricsViewToggle")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
        self.structure_view_group = QButtonGroup(structure_section)
        self.structure_view_group.setExclusive(True)
        self.structure_view_group.addButton(self.structure_molecule_view_button)
        self.structure_view_group.addButton(self.structure_full_cell_view_button)
        self.structure_molecule_view_button.setChecked(True)
        self.structure_molecule_view_button.toggled.connect(
            lambda checked: checked and self._set_classic_structure_view_mode("molecule")
        )
        self.structure_full_cell_view_button.toggled.connect(
            lambda checked: checked and self._set_classic_structure_view_mode("cell")
        )
        controls.addWidget(self.structure_molecule_view_button)
        controls.addWidget(self.structure_full_cell_view_button)
        from phase_studio.structure_camera import camera_settings_button
        controls.addWidget(camera_settings_button(self))
        self._classic_detached_viewers = {}
        self.structure_fullscreen_buttons = {}
        structure_layout.addLayout(controls)
        self.classic_review_controls = {}
        review_row = QHBoxLayout()
        review_row.setContentsMargins(0, 0, 0, 0)
        review_row.setSpacing(8)
        for panel, label in (("reference", "Reference"), ("superflip", "Superflip"), ("deblur", "SharpED")):
            column = QWidget()
            column.setObjectName(f"classicReviewColumn_{panel}")
            column_layout = QVBoxLayout(column)
            column_layout.setContentsMargins(4, 2, 4, 2)
            column_layout.setSpacing(3)
            header = QHBoxLayout()
            heading = QLabel(label)
            heading.setStyleSheet("font-weight:600; color:#001170;")
            header.addWidget(heading)
            header.addStretch(1)
            fullscreen = QPushButton("Fullscreen")
            fullscreen.setObjectName("metricsControlButton")
            fullscreen.setCursor(Qt.PointingHandCursor)
            fullscreen.setToolTip(f"Open only the {label} structure in a detached interactive viewer.")
            fullscreen.clicked.connect(lambda _checked=False, p=panel: self._open_classic_structure_fullscreen(p))
            fullscreen.setEnabled(False)
            header.addWidget(fullscreen)
            column_layout.addLayout(header)
            self.structure_fullscreen_buttons[panel] = fullscreen

            controls_for_panel = {"column": column, "fullscreen": fullscreen}
            if panel != "reference":
                navigation = QWidget()
                nav = QHBoxLayout(navigation)
                nav.setContentsMargins(0, 0, 0, 0)
                nav.setSpacing(4)
                previous = QToolButton(); previous.setText("◀")
                combo = QComboBox(); combo.addItem("Latest", None)
                combo.setToolTip("Follow the latest completed cycle, or inspect an older completed cycle.")
                next_button = QToolButton(); next_button.setText("▶")
                latest = QToolButton(); latest.setText("Latest")
                nav.addWidget(previous); nav.addWidget(combo, 1); nav.addWidget(next_button); nav.addWidget(latest)
                navigation.setVisible(False)
                column_layout.addWidget(navigation)
                metadata = QLabel("")
                metadata.setWordWrap(True)
                metadata.setAlignment(Qt.AlignCenter)
                metadata.setVisible(False)
                column_layout.addWidget(metadata)
                threshold_actions = QWidget()
                actions = QHBoxLayout(threshold_actions)
                actions.setContentsMargins(0, 0, 0, 0)
                actions.setSpacing(5)
                actions.addStretch(1)
                add_atoms = QPushButton("+ atoms")
                remove_atoms = QPushButton("- atoms")
                actions.addWidget(add_atoms); actions.addWidget(remove_atoms); actions.addStretch(1)
                threshold_actions.setVisible(False)
                column_layout.addWidget(threshold_actions)
                previous.clicked.connect(lambda _checked=False, p=panel: self._step_classic_cycle(p, -1))
                next_button.clicked.connect(lambda _checked=False, p=panel: self._step_classic_cycle(p, 1))
                latest.clicked.connect(lambda _checked=False, c=combo: c.setCurrentIndex(0))
                combo.currentIndexChanged.connect(lambda _index, p=panel: self._classic_cycle_changed(p))
                add_atoms.clicked.connect(lambda _checked=False, p=panel: self._classic_adjust_threshold(p, True))
                remove_atoms.clicked.connect(lambda _checked=False, p=panel: self._classic_adjust_threshold(p, False))
                controls_for_panel.update(
                    navigation=navigation, previous=previous, combo=combo, next=next_button,
                    latest=latest, metadata=metadata, threshold_actions=threshold_actions,
                    add=add_atoms, remove=remove_atoms,
                )
            self.classic_review_controls[panel] = controls_for_panel
            review_row.addWidget(column, 1)
        structure_layout.addLayout(review_row)
        self.structure_rotation_hint = QLabel(
            "Left-drag: rotate · Right/Middle/Shift-left-drag: pan · Wheel: zoom · Double-click: fit"
            " — orientation stays in sync"
            " · Hydrogen and helium atoms hidden"
        )
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
        self.structure_canvas.mpl_connect("resize_event", lambda _event: self._layout_structure_figure())
        self._classic_camera = StructureCameraController(
            self.structure_canvas,
            lambda: self._structure_interactive_axes,
            fit=self._fit_classic_structure_view,
            reset=self._reset_classic_structure_view,
            orientation_changed=self._classic_camera_orientation_changed,
        )
        structure_layout.addWidget(self.structure_canvas, 1)
        self.result_splitter.addWidget(structure_section)

    @staticmethod
    def _classic_candidate_source(panel: str) -> str:
        return "superflip" if panel == "superflip" else "deblurred"

    def _classic_candidates(self, panel: str) -> List[ResultCandidate]:
        if panel not in {"superflip", "deblur"}:
            return []
        source = self._classic_candidate_source(panel)
        return sorted(
            (candidate for candidate in self._result_candidates() if candidate.source == source),
            key=lambda candidate: int(candidate.cycle),
        )

    def _classic_selected_candidate(self, panel: str) -> Optional[ResultCandidate]:
        candidates = self._classic_candidates(panel)
        if not candidates:
            return None
        controls = getattr(self, "classic_review_controls", {}).get(panel, {})
        combo = controls.get("combo")
        cycle = combo.currentData() if isinstance(combo, QComboBox) else None
        if cycle is None:
            return candidates[-1]
        return next((candidate for candidate in candidates if int(candidate.cycle) == int(cycle)), candidates[-1])

    def _sync_classic_review_controls(self) -> None:
        """Expose only completed canonical candidates in each result panel."""
        controls_by_panel = getattr(self, "classic_review_controls", {})
        for panel in ("superflip", "deblur"):
            controls = controls_by_panel.get(panel, {})
            combo = controls.get("combo")
            if not isinstance(combo, QComboBox):
                continue
            candidates = self._classic_candidates(panel)
            selected_cycle = combo.currentData()
            follow_latest = selected_cycle is None
            combo.blockSignals(True)
            combo.clear(); combo.addItem("Latest", None)
            for candidate in candidates:
                combo.addItem(f"Cycle {candidate.cycle}", int(candidate.cycle))
            if not follow_latest and selected_cycle is not None:
                index = combo.findData(int(selected_cycle))
                combo.setCurrentIndex(index if index >= 0 else 0)
            combo.blockSignals(False)
            available = bool(candidates)
            controls["navigation"].setVisible(available)
            controls["metadata"].setVisible(available)
            controls["threshold_actions"].setVisible(available)
            controls["fullscreen"].setEnabled(available)
            if available:
                self._apply_classic_candidate(panel)
            else:
                controls["metadata"].clear()
                controls["add"].setEnabled(False)
                controls["remove"].setEnabled(False)
        reference_controls = controls_by_panel.get("reference", {})
        if reference_controls:
            reference_controls["fullscreen"].setEnabled(bool(self.reference_atoms_for_plot))

    def _apply_classic_candidate(self, panel: str) -> None:
        candidate = self._classic_selected_candidate(panel)
        controls = getattr(self, "classic_review_controls", {}).get(panel, {})
        if candidate is None:
            return
        path = Path(candidate.structure_path)
        self._structure_source_paths[panel] = path
        atoms = self._classic_structure_atoms(path)
        if panel == "superflip":
            self.superflip_atoms_for_plot = atoms
        else:
            self.deblur_atoms_for_plot = atoms
        composition_label, composition = self._classic_structure_composition(panel)
        try:
            detected = len(parse_cif_atoms(path))
        except Exception:
            detected = 0
        model = f"<br>{html.escape(candidate.sharped_model)}" if candidate.sharped_model else ""
        threshold = (
            f"EDMA {guided.format_sigma(candidate.edma_sigma)} · "
            if candidate.edma_sigma is not None else ""
        )
        controls["metadata"].setText(
            f"<b>{'Superflip' if panel == 'superflip' else 'SharpED'} · Cycle {candidate.cycle}</b>{model}<br>"
            f"{html.escape(composition_label)}: {html.escape(composition or 'Unavailable')}<br>"
            f"{threshold}{detected:,} EDMA sites"
        )
        tunable = candidate.edma_sigma is not None and candidate.usable_map
        controls["add"].setEnabled(tunable)
        controls["remove"].setEnabled(tunable)
        combo = controls["combo"]
        row = combo.currentIndex()
        last_cycle_index = combo.count() - 1
        controls["previous"].setEnabled(last_cycle_index > 1 and (row == 0 or row > 1))
        controls["next"].setEnabled(row > 0 and row < last_cycle_index)
        controls["latest"].setEnabled(row != 0)

    def _classic_cycle_changed(self, panel: str) -> None:
        self._apply_classic_candidate(panel)
        self._update_structure_views()
        detached = getattr(self, "_classic_detached_viewers", {}).get(panel)
        if detached is not None and detached.isVisible():
            detached.render()

    def _step_classic_cycle(self, panel: str, direction: int) -> None:
        controls = getattr(self, "classic_review_controls", {}).get(panel, {})
        combo = controls.get("combo")
        if not isinstance(combo, QComboBox) or combo.count() <= 1:
            return
        current = combo.currentIndex()
        if current == 0:
            current = combo.count() - 1
        target = max(1, min(combo.count() - 1, current + int(direction)))
        combo.setCurrentIndex(target)

    def _classic_adjust_threshold(self, panel: str, add_atoms: bool) -> None:
        candidate = self._classic_selected_candidate(panel)
        if candidate is None:
            return
        controls = self.classic_review_controls.get(panel, {})

        def completed(updated, report, _request) -> None:
            if report is not None:
                if "metadata" in controls:
                    controls["metadata"].setText(
                        "EDMA threshold update failed. Previous completed structure retained."
                    )
                return
            if updated is None:
                return
            self._sync_classic_review_controls()
            self._apply_classic_candidate(panel)
            self._update_structure_views()
            detached = getattr(self, "_classic_detached_viewers", {}).get(panel)
            if detached is not None and detached.isVisible():
                detached.render()

        request = self.request_result_candidate_retune(candidate, add_atoms, completed)
        if request is not None and "metadata" in controls:
            controls["metadata"].setText(
                f"EDMA {guided.format_sigma(request.threshold)} · updating…<br>"
                f"Current handoff: EDMA {guided.format_sigma(candidate.edma_sigma)}"
            )

    def _classic_fullscreen_presentation(self, panel: str) -> dict:
        from phase_studio.autosolve_window import prepare_structure_presentation

        candidate = self._classic_selected_candidate(panel)
        path = self._structure_source_paths.get(panel)
        composition_label, composition = self._classic_structure_composition(panel)
        data = prepare_structure_presentation(
            path, self.structure_view_mode, composition, composition_label,
        )
        title = {"reference": "Reference", "superflip": "Charge-flipping solution", "deblur": "Structure prediction"}[panel]
        source = {"reference": "Reference", "superflip": "Superflip", "deblur": "SharpED"}[panel]
        cycle = f" · Cycle {candidate.cycle}" if candidate is not None else ""
        model = f" · {html.escape(candidate.sharped_model)}" if candidate is not None and candidate.sharped_model else ""
        metadata = (
            f"{source}{model}{cycle}<br><b>{html.escape(data.get('composition_label', 'Composition'))}:</b> "
            f"{html.escape(data.get('composition') or 'Unavailable')}"
        )
        if candidate is not None and candidate.edma_sigma is not None:
            metadata += (
                f"<br>EDMA {guided.format_sigma(candidate.edma_sigma)} · "
                f"{int(data.get('detected', 0)):,} EDMA sites"
            )
        data["metadata"] = metadata
        data["title"] = f"Phase Studio — {title}{cycle}"
        return data

    def _open_classic_structure_fullscreen(self, panel: str = "reference") -> None:
        from phase_studio.fullscreen_viewer import show_single_structure_viewer

        title = {"reference": "Reference", "superflip": "Superflip", "deblur": "SharpED"}.get(panel, "Structure")
        result_panel = panel in {"superflip", "deblur"}
        self._classic_detached_viewers[panel] = show_single_structure_viewer(
            self,
            f"Phase Studio — {title}",
            lambda p=panel: self._classic_fullscreen_presentation(p),
            color_for=self._element_color,
            existing=self._classic_detached_viewers.get(panel),
            set_mode=lambda mode: (
                self.structure_molecule_view_button.setChecked(mode == "molecule")
                if mode == "molecule" else self.structure_full_cell_view_button.setChecked(True)
            ),
            adjust_threshold=(lambda add, p=panel: self._classic_adjust_threshold(p, add)) if result_panel else None,
            previous_cycle=(lambda p=panel: self._step_classic_cycle(p, -1)) if result_panel else None,
            next_cycle=(lambda p=panel: self._step_classic_cycle(p, 1)) if result_panel else None,
            latest_cycle=(lambda p=panel: self.classic_review_controls[p]["combo"].setCurrentIndex(0)) if result_panel else None,
            elev=self.structure_elev,
            azim=self.structure_azim,
        )

    def _set_classic_structure_view_mode(self, mode: str) -> None:
        self.structure_view_mode = "cell" if mode == "cell" else "molecule"
        for panel, attribute in (
            ("reference", "reference_atoms_for_plot"),
            ("superflip", "superflip_atoms_for_plot"),
            ("deblur", "deblur_atoms_for_plot"),
        ):
            source_path = self._structure_source_paths.get(panel)
            if source_path is not None and source_path.is_file():
                setattr(self, attribute, self._classic_structure_atoms(source_path))
        self.settings.setValue("viewer/structure_view_mode", self.structure_view_mode)
        self.settings.sync()
        self._update_structure_views()

    def _build_execution_log_section(self) -> None:
        log_section, log_layout = self._make_result_section("EXECUTION LOG")
        log_actions = QHBoxLayout()
        log_actions.setContentsMargins(0, 0, 0, 0)
        log_actions.addStretch(1)
        self.execution_log_expanded = False
        self.execution_log_expand_button = QToolButton()
        self.execution_log_expand_button.setObjectName("diagnosticTextAction")
        self.execution_log_expand_button.setText("Expand log")
        self.execution_log_expand_button.setToolTip("Show more execution and provenance messages.")
        self.execution_log_expand_button.clicked.connect(self._toggle_execution_log)
        log_actions.addWidget(self.execution_log_expand_button)
        self.execution_log_open_button = QToolButton()
        self.execution_log_open_button.setObjectName("diagnosticTextAction")
        self.execution_log_open_button.setText("Open log")
        self.execution_log_open_button.setToolTip("Open the complete timestamped run diagnostic log.")
        self.execution_log_open_button.clicked.connect(self._open_run_diagnostic_log)
        self.execution_log_open_button.setEnabled(False)
        log_actions.addWidget(self.execution_log_open_button)
        log_layout.addLayout(log_actions)
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

    def _set_execution_log_expanded(self, expanded: bool) -> None:
        self.execution_log_expanded = bool(expanded)
        self.execution_log_expand_button.setText(
            "Collapse log" if self.execution_log_expanded else "Expand log"
        )
        sizes = self.result_splitter.sizes()
        total = max(sum(sizes), 700)
        log_height = max(240, int(total * 0.34)) if self.execution_log_expanded else 120
        remaining = max(300, total - log_height)
        self.result_splitter.setSizes([
            max(120, int(remaining * 0.27)),
            max(260, int(remaining * 0.73)),
            log_height,
        ])

    def _toggle_execution_log(self) -> None:
        self._set_execution_log_expanded(not self.execution_log_expanded)

    def _open_run_diagnostic_log(self) -> None:
        diagnostic = getattr(self, "_run_diagnostic_log", None)
        if diagnostic is not None and diagnostic.path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(diagnostic.path)))

    # ----- Basic-tab builders, one per tab, called in order from _build_ui.
    # Each assigns the same self.* attributes, connects the same signals, and
    # keeps the same widget defaults/tooltips/object names as before this
    # extraction (2026 maintainability refactor) -- purely a code-motion out
    # of _build_ui's own body, no behavior change. -----

    def _build_input_tab(self) -> None:
        input_tab = self._add_settings_tab("Input")
        self._create_settings_page_header(input_tab, "Data input", "input")
        data_input_form = self._add_form_group(input_tab, "")
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
        self.metadata_composition_heading = QLabel("Composition")
        metadata_summary_layout.addRow("Cell lengths", self.metadata_cell_summary)
        metadata_summary_layout.addRow("Cell angles", self.metadata_cell_angles_summary)
        metadata_summary_layout.addRow("Space group", self.metadata_spacegroup_summary)
        metadata_summary_layout.addRow(
            self.metadata_composition_heading, self.metadata_composition_summary,
        )
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
        # Slightly tighter top margin than the shared subsection default so
        # this section's heading is visible sooner below Crystal metadata's
        # summary in a normal 1080p window -- scoped to this one group via a
        # dynamic property, not a change to every subsection's spacing.
        reference_form.parentWidget().setProperty("tightTop", True)
        # "Reference model", not "Reference structure": this selector validly
        # accepts either a structure model or a density map (see
        # REFERENCE_FILE_SUFFIXES), so naming it a structure was misleading.
        self._add_path(reference_form, "reference_cif", "Reference model", "", "file", supported_reference_filters())
        self.inputs["jana_inflip"].on_change = self._jana_inflip_path_changed  # type: ignore[attr-defined]
        self.inputs["reference_cif"].on_change = self._reference_path_changed  # type: ignore[attr-defined]
        self._add_path(reference_form, "first_cycle_modelfile", "Initial model (cycle 1)", "", "file", supported_model_filters())
        input_tab.addSpacing(CONFIG_MAJOR_SECTION_SPACING)
        input_tab.addStretch(1)

    def _build_workflow_tab(self) -> None:
        workflow_tab = self._add_settings_tab("Workflow")
        self._create_settings_page_header(workflow_tab, "Reconstruction", "workflow")
        workflow_form = self._add_form_group(workflow_tab, "")
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
        self.reconstruction_mode_warning = self._settings_callout("", "", kind="warning")
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
            "Next-cycle model determines how subsequent cycles are initialized. Selecting None "
            "limits the workflow to a single cycle. XPLOR damping applies only to XPLOR-based recycling."
        )
        workflow_note.setProperty("compactPadding", True)
        workflow_form.addRow("", workflow_note)
        self.recycle_note = self._settings_callout(
            "Phasing method",
            "Beta/experimental methods recycle phases through SharpED instead of iterative Superflip cycling. "
            "See Open guide above for exactly how each method differs."
        )
        workflow_form.addRow("", self.recycle_note)

        model_form = self._add_form_group(workflow_tab, "SharpED model")
        self._add_combo(model_form, "sharped_model", "Model", ["default"], "default")
        try:
            self.inputs["sharped_model"].lineEdit().setReadOnly(False)  # type: ignore[attr-defined]
            self.inputs["sharped_model"].lineEdit().setCursor(Qt.CursorShape.IBeamCursor)  # type: ignore[attr-defined]
        except Exception:
            pass
        self.refresh_models_btn = QPushButton("Refresh models")
        self.refresh_models_btn.setToolTip("Fetch the current list of SharpED server models and update the model selector.")
        self.refresh_models_btn.clicked.connect(self.refresh_sharped_models)
        model_form.addRow("", self.refresh_models_btn)
        settings_links_row = QHBoxLayout()
        settings_links_row.setSpacing(10)
        connection_settings_link = QToolButton()
        connection_settings_link.setObjectName("settingsNavLink")
        connection_settings_link.setText("Connection settings →")
        connection_settings_link.setCursor(Qt.PointingHandCursor)
        connection_settings_link.setToolTip("Open Advanced → Setup (server URL, API token).")
        connection_settings_link.clicked.connect(lambda _checked=False: self._open_configuration_page("Setup", advanced=True))
        inference_settings_link = QToolButton()
        inference_settings_link.setObjectName("settingsNavLink")
        inference_settings_link.setText("Inference settings →")
        inference_settings_link.setCursor(Qt.PointingHandCursor)
        inference_settings_link.setToolTip("Open Advanced → SharpED (elements, output resolution, map value exponent, network/upload settings).")
        inference_settings_link.clicked.connect(lambda _checked=False: self._open_configuration_page("SharpED", advanced=True))
        settings_links_row.addWidget(connection_settings_link)
        settings_links_row.addWidget(inference_settings_link)
        settings_links_row.addStretch(1)
        model_form.addRow("", settings_links_row)

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
        self._create_settings_page_header(output_tab, "Output", "output")
        output_form = self._add_form_group(output_tab, "")
        self._add_path(output_form, "work_dir", "Working directory", str(cwd / "iterative_superflip_qt_run"), "dir")
        self._add_combo(output_form, "map_export_format", "Map format", ["xplor", "ccp4", "jana", "HKL reflections with phases", "ShelX (fcf)"], "xplor")
        self._add_combo(output_form, "structure_export_format", "Structure format", ["cif", "xyz", "pdb"], "cif")
        output_form.addRow("", self._settings_callout(
            "Note",
            "Internal XPLOR maps and CIF structures required by the workflow are retained automatically. "
            "The selected formats control additional files for external use. "
            "HKL reflections with phases and ShelX (fcf) save reflection data instead of an extra map."
        ))
        output_tab.addSpacing(CONFIG_MAJOR_SECTION_SPACING)
        output_tab.addStretch(1)

    def _build_map_feedback_tab(self) -> None:
        feedback_tab = self._add_settings_tab("Map feedback")
        self._create_settings_page_header(feedback_tab, "Map feedback", "map_feedback")
        feedback_tab.addWidget(self._settings_callout(
            "Warning",
            "The operations on this page modify the reflection data supplied to subsequent cycles. "
            "Results from these cycles should therefore be validated against the original measured data.",
            kind="warning",
        ))
        missing_feedback_form = self._add_form_group(feedback_tab, "Missing-reflection completion")
        self._add_checkbox(missing_feedback_form, "map_feedback_missing_enabled", "Enable missing-reflection completion", False, align_with_fields=True)
        self._add_spin(missing_feedback_form, "map_feedback_missing_from_cycle", "Start after cycle", 1, 1, 999, 1)
        self._add_dspin(missing_feedback_form, "map_feedback_missing_percent_limit", "Maximum added reflections (%)", 0.0, 0.0, 100.0, 1.0, 3)

        intensity_feedback_form = self._add_form_group(feedback_tab, "Intensity correction")
        self._add_checkbox(intensity_feedback_form, "map_feedback_intensity_enabled", "Enable intensity correction", False, align_with_fields=True)
        self._add_spin(intensity_feedback_form, "map_feedback_intensity_from_cycle", "Start after cycle", 1, 1, 999, 1)
        self._add_dspin(intensity_feedback_form, "map_feedback_intensity_damping", "Correction damping", 0.0, 0.0, 1.0, 0.05, 3)
        self._add_dspin(intensity_feedback_form, "map_feedback_intensity_max_i_over_sigma", "Apply when value/σ <", 0.0, 0.0, 1000.0, 0.5, 3)
        intensity_feedback_form.addRow("", self._settings_callout("Note", "At 0, correction applies to all non-zero reflections."))

        powder_feedback_form = self._add_form_group(feedback_tab, "Powder overlap repartitioning")
        self._add_checkbox(powder_feedback_form, "redistribute_overlaps", "Enable powder overlap repartitioning (FWHM data)", False, align_with_fields=True)
        self._add_spin(powder_feedback_form, "powder_redistribution_from_cycle", "Start after cycle", 1, 1, 999, 1)
        self._add_dspin(powder_feedback_form, "powder_wavelength", "Wavelength (Å)", 0.0, 0.0, 10.0, 0.01, 5)
        self._add_dspin(powder_feedback_form, "powder_separation_factor", "Separation factor", 0.2, 0.001, 100.0, 0.05, 3)
        self._add_dspin(powder_feedback_form, "powder_redistribution_mix", "Map ratio mix", 1.0, 0.0, 1.0, 0.05, 3)
        powder_feedback_form.addRow("", self._settings_callout(
            "Note",
            "Available only for FWHM reflection data. Wavelength is detected automatically when possible. "
            "Repartitioning preserves the total observed intensity of each overlap group."
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

    def _create_settings_page_header(self, page_layout: QVBoxLayout, title: str, guide_target: Optional[str] = None) -> None:
        """The one consistent LEVEL 1 heading every Basic/Advanced
        configuration subpage uses: page title on the left, exactly one
        "Open guide" action on the right when this page has corresponding
        Help content, with a subtle separator below (2026 UI hierarchy
        pass). Subsections within the page (_add_form_group) no longer
        carry their own guide links -- a page has at most one."""
        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        heading = QLabel(title)
        heading.setObjectName("pageHeading")
        header_row.addWidget(heading, 1)
        if guide_target:
            guide = QToolButton()
            guide.setObjectName("guideLink")
            guide.setText("Open guide")
            guide.setCursor(Qt.PointingHandCursor)
            guide.setToolTip("Open the relevant section in Help (F1).")
            guide.clicked.connect(lambda _checked=False, target=guide_target: self._open_help_section(target))
            header_row.addWidget(guide)
        page_layout.addLayout(header_row)
        rule = QFrame()
        rule.setObjectName("pageHeadingRule")
        rule.setFixedHeight(2)
        rule.setFrameShape(QFrame.NoFrame)
        page_layout.addWidget(rule)

    def _add_form_group(self, page_layout: QVBoxLayout, title: str) -> QFormLayout:
        """One consistent LEVEL 2 subsection heading (bold navy title, plain
        separator via QGroupBox's own QSS chrome) -- or, when title is empty,
        a bare form with no heading/border at all, for a page's own leading
        fields that already sit directly under that page's LEVEL 1 heading
        (_create_settings_page_header) and so need no heading of their own.
        No subsection carries its own "Open guide" link any more -- a page
        has exactly one, in its LEVEL 1 heading."""
        if not title:
            form_widget = QWidget()
            form_widget.setObjectName("bareSettingsGroup")
            form = self._configure_form(QFormLayout(form_widget))
            page_layout.addWidget(form_widget)
            return form
        box = QGroupBox(title)
        box.setObjectName("settingsGroup")
        form = self._configure_form(QFormLayout(box))
        page_layout.addWidget(box)
        return form

    def _settings_callout(self, title: str, text: str, kind: str = "note") -> QLabel:
        """Callers that mutate the label's text later via setText() (e.g. the
        Phasing-method warning, whose message depends on the selected
        method) keep whatever kind was set here at construction. See
        create_callout_label() in ui_branding.py for the shared presentation."""
        return create_callout_label(title, text, kind)

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

    def _add_help_callout(self, section_layout: QVBoxLayout, label: str, text: str, kind: str = "note") -> None:
        """Same warning/note/tip kind system as _settings_callout(), applied
        to Help-page callouts -- Basic and Advanced Help intentionally share
        this one callout style rather than each having its own."""
        callout = QLabel(f"<b>{label}</b><br>{text}")
        callout.setObjectName("helpCallout")
        callout.setProperty("calloutKind", kind)
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
        return default_metadata_source(
            self._combo_value("input_source_mode") if "input_source_mode" in self.inputs else "",
            self._path_value("reference_cif") if "reference_cif" in self.inputs else "",
            REFERENCE_STRUCTURE_SUFFIXES,
        )

    def _input_mode_user_changed(self, _index: int = -1) -> None:
        self._metadata_source_user_selected = False
        self._set_metadata_source(self._default_metadata_source_for_input())
        self._sync_input_source_mode_widgets()

    def _idle_ready_message(self) -> str:
        mode = normalize_input_source_mode(self._combo_value("input_source_mode"))
        inflip = self._path_value("jana_inflip").strip()
        hkl = self._path_value("hkl").strip()
        input_path = Path(hkl).expanduser() if mode == INPUT_MODE_EXTERNAL and hkl else None
        if mode in {INPUT_MODE_INFLIP, INPUT_MODE_INFLIP_OVERRIDES} and inflip:
            input_path = Path(inflip).expanduser()
        if input_path is not None and input_path.is_file():
            return "Ready. Review the settings and run phasing."
        return "Ready. Select an input to begin."

    def _sync_idle_ready_log(self) -> None:
        if (self.worker is not None or self.results or self.last_run_config is not None
                or str(self._run_status).upper() != "READY"):
            return
        current = self.log_text.toPlainText().strip()
        if current and not current.startswith("Ready"):
            return
        self.log_text.clear()
        self._last_log_record = None
        self._append_execution_log(self._idle_ready_message())

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
        self._sync_idle_ready_log()
        self.save_settings()

    def _hkl_path_changed(self) -> None:
        # Mirrors _jana_inflip_path_changed()'s map-feedback refresh: an
        # external HKL file's detected format also gates powder overlap
        # repartitioning (FWHM-carrying data only).
        self._sync_map_feedback_widgets()
        self._sync_idle_ready_log()
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
        mode = normalize_input_source_mode(self._combo_value("input_source_mode"))
        jana_text = self._path_value("jana_inflip").strip() if "jana_inflip" in self.inputs else ""
        reference_text = self._path_value("reference_cif").strip() if "reference_cif" in self.inputs else ""
        manual_cell, manual_number, manual_symbol, manual_composition = self._manual_metadata_values()
        return resolve_crystal_metadata(
            self._metadata_source_value(),
            jana_inflip=active_jana_inflip(mode, jana_text),
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
            inline_guidance = (
                "Select a valid Jana2020 .inflip file to continue."
                if report.category == "inflip" else report.guidance
            )
            self.metadata_error_text.setText(f"{report.title}.\n{inline_guidance}")
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
        mode = normalize_input_source_mode(self._combo_value("input_source_mode"))
        inflip_text = self._path_value("jana_inflip").strip()
        reference_text = self._path_value("reference_cif").strip()
        resolved_source = reconcile_metadata_source(
            source, mode, inflip_text, reference_text, REFERENCE_STRUCTURE_SUFFIXES,
        )
        if resolved_source != source:
            widget = self.inputs.get("metadata_source")
            if isinstance(widget, QComboBox):
                index = widget.findText(METADATA_SOURCE_LABELS[resolved_source])
                if index >= 0:
                    self._syncing_metadata_controls = True
                    try:
                        widget.setCurrentIndex(index)
                    finally:
                        self._syncing_metadata_controls = False
            self._metadata_source_user_selected = False
            source = resolved_source
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
            self.metadata_composition_heading.setText(
                crystal_metadata_composition_label(metadata)
            )
            self.metadata_summary_panel.setVisible(True)
            self._clear_metadata_error()
        except Exception as exc:
            self.metadata_cell_summary.setText("")
            self.metadata_cell_angles_summary.setText("")
            self.metadata_spacegroup_summary.setText("")
            self.metadata_composition_summary.setText("")
            self.metadata_composition_heading.setText("Composition")
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
            omit_rfree_widget.setChecked(omit_maps_enabled)
            omit_rfree_widget.setEnabled(False)
            omit_rfree_widget.setToolTip(
                INPUT_TOOLTIPS.get("compute_omit_rfree", "") if omit_maps_enabled
                else "Requires 'Compute omit maps' to be enabled."
            )
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
                else f"Requires FWHM-carrying reflection data ({format_reflection_data_mode(REFLECTION_DATA_MODE_INTENSITY_FWHM)} or {format_reflection_data_mode(REFLECTION_DATA_MODE_AMPLITUDE_FWHM)}); no FWHM format is currently detected for the configured HKL source."
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
        if hasattr(self, "metrics_tabs") and "map_feedback_change" in self._metrics_tab_keys:
            feedback_index = self._metrics_tab_keys.index("map_feedback_change")
            self.metrics_tabs.setTabVisible(feedback_index, self._check_value("map_feedback_intensity_enabled"))

    def _sync_input_source_mode_widgets(self) -> None:
        if self._configuration_locked:
            return
        mode = normalize_input_source_mode(self._combo_value("input_source_mode") if "input_source_mode" in self.inputs else "")
        availability = input_control_availability(mode, self._metadata_source_value())
        for key, enabled in availability.items():
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
                if not availability["reflection_data_mode"] else INPUT_TOOLTIPS.get("reflection_data_mode", "")
            )
        jana_inflip_widget = self.inputs.get("jana_inflip")
        if isinstance(jana_inflip_widget, PathRow):
            jana_inflip_widget.set_tooltip(
                INPUT_TOOLTIPS.get("jana_inflip", "") if availability["jana_inflip"]
                else "Not used in External HKL mode."
            )
        hkl_widget = self.inputs.get("hkl")
        if isinstance(hkl_widget, PathRow):
            hkl_widget.set_tooltip(
                INPUT_TOOLTIPS.get("hkl", "") if availability["hkl"]
                else "Not used with the Jana2020 .inflip input mode; reflections come from the .inflip file."
            )
        self._sync_metadata_source_widgets()
        self._sync_map_feedback_widgets()
        self._sync_idle_ready_log()

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

    def _manage_sharped_access(self) -> None:
        from phase_studio import requirements as reqs
        base_url = self._line_value("sharped_base_url") or DEFAULT_SERVER_URL
        previous = credential_store.get(base_url)
        value = show_requirement_remediation_dialog(
            self, reqs.RequirementStatus(reqs.RequirementKind.SHARPED, reqs.RequirementState.OK),
            self._line_value("sharped_api_token"), sharped_base_url=base_url,
            sharped_probe=lambda key: reqs.check_sharped_api(
                base_url, key, client_factory=getattr(self, "_preflight_client_factory", None)),
        )
        if value is not None or (previous and not credential_store.get(base_url)):
            self._set_widget_value_from_string(self.inputs["sharped_api_token"], value or "")
            self.save_settings()

    def load_settings(self) -> None:
        saved_metadata_source = self.settings.value("inputs/metadata_source", None)
        for key, widget in self.inputs.items():
            if key == "sharped_api_token":
                continue
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

        base_url = self._line_value("sharped_base_url") or DEFAULT_SERVER_URL
        saved_key = credential_store.load_settings(self.settings, base_url=base_url)
        if saved_key:
            self._set_widget_value_from_string(self.inputs["sharped_api_token"], saved_key)
        credential_store.bind_input(
            self.inputs["sharped_api_token"],
            lambda: self._line_value("sharped_base_url") or DEFAULT_SERVER_URL,
        )

        # Migrate legacy generic executable names to the Jana2020 installation
        # defaults while preserving any explicit custom absolute path.
        executable_defaults = {
            "superflip_exe": r"C:\Jana2020\SUPERFLIP\superflip.exe",
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
        saved_structure_view = str(self.settings.value("viewer/structure_view_mode", "molecule"))
        if saved_structure_view == "cell":
            self.structure_full_cell_view_button.setChecked(True)
        else:
            self.structure_molecule_view_button.setChecked(True)
        self._sync_input_source_mode_widgets()
        self._sync_metadata_source_widgets()
        geom = self.settings.value("window/geometry", None)
        if geom is not None:
            try:
                self.restoreGeometry(geom)
                self._restored_window_geometry = True
            except Exception:
                pass
        self._restore_maximized_requested = str(
            self.settings.value("window/maximized", "false")
        ).strip().lower() in {"1", "true", "yes", "on"}
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
        if not running:
            progress = getattr(self, "_hkl_progress_dialog", None)
            if progress is not None:
                progress.close()
                progress.deleteLater()
                self._hkl_progress_dialog = None
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
        from PySide6.QtWidgets import QProgressDialog
        from phase_studio.hkl_diagnostics import diagnostic_cancellation
        from concurrent.futures import CancelledError
        cancel_event = threading.Event()
        self._hkl_cancel_event = cancel_event
        progress = QProgressDialog(label + "…", "Cancel", 0, 0, self)
        progress.setWindowTitle("HKL diagnostics")
        progress.setMinimumDuration(500)
        progress.setAutoClose(False)
        progress.canceled.connect(cancel_event.set)
        self._hkl_progress_dialog = progress
        progress.setValue(0)

        def worker() -> None:
            try:
                with diagnostic_cancellation(cancel_event):
                    result = worker_fn()
                if not cancel_event.is_set():
                    self.msg_queue.put((done_kind, (task_id, result)))
            except CancelledError:
                pass
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
            source_value.setToolTip("Use Copy path to copy the full reflection-source path.")
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
        source_value.setToolTip("Use Copy path to copy the full reflection-source path.")
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
        from phase_studio.hkl_diagnostics_ui import validation_dialog
        return validation_dialog(self, result)

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
            from phase_studio.hkl_diagnostics import cached_analysis
            return cached_analysis(request)

        self._start_hkl_background_task("HKL completeness analysis", worker, "hkl_completeness_result")

    def _build_hkl_completeness_dialog(self, analysis: HklAnalysis) -> QDialog:
        from phase_studio.hkl_diagnostics_ui import completeness_dialog
        return completeness_dialog(self, analysis)

    def _show_hkl_completeness_dialog(self, analysis: HklAnalysis) -> None:
        dialog = self._build_hkl_completeness_dialog(analysis)
        # The builder fits the work area, then restores and clamps the
        # user's saved geometry. A deferred second fit would overwrite it.
        dialog.exec()

    def save_settings(self) -> None:
        for key, widget in self.inputs.items():
            if key == "sharped_api_token":
                continue
            self.settings.setValue(f"inputs/{key}", self._widget_value_as_string(widget))
        try:
            credential_store.save_input(self._line_value("sharped_api_token"),
                                        self._line_value("sharped_base_url") or DEFAULT_SERVER_URL)
        except (OSError, ValueError):
            # The current widget retains session access; never fall back to a
            # plaintext persistent setting when secure saving fails.
            pass
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("window/maximized", bool(self.isMaximized()))
        if hasattr(self, "main_splitter"):
            self.settings.setValue("window/main_splitter", self.main_splitter.saveState())
        if hasattr(self, "result_splitter"):
            self.settings.setValue("window/result_splitter", self.result_splitter.saveState())
        self.settings.setValue("viewer/structure_view_mode", getattr(self, "structure_view_mode", "molecule"))
        self.settings.sync()

    def _apply_adaptive_window_geometry(self) -> None:
        """Respect real maximize state; otherwise stay inside this monitor's work area."""
        if self._restore_maximized_requested:
            self.showMaximized()
            install_screen_geometry_guard(self)
            return
        # restoreGeometry() can encode a maximized state.  The separate setting
        # records whether that state was an explicit user choice.
        if self.isMaximized():
            self.showNormal()
        if self._restored_window_geometry:
            # A normal rectangle saved on a larger/differently scaled monitor
            # must not reopen as a pseudo-maximized window here.  Explicit
            # maximize intent took the branch above.
            clamp_window_to_available_screen(
                self, width_fraction=0.92, height_fraction=0.90,
                center_if_resized=True,
            )
            install_screen_geometry_guard(self)
            return
        fit_dialog_to_available_screen(
            self, QSize(1420, 880), width_fraction=0.92, height_fraction=0.90,
        )

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.review_edma_executor.cancel_all()
        if self._run_diagnostic_log is not None:
            self._run_diagnostic_log.close()
            self._run_diagnostic_log = None
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

    def _set_overall_progress_value(self, value: int) -> None:
        """The overall (completed-cycle) progress value never decreases within
        one run: a fresh start_run() resets the floor, while progress_setup /
        continue_run() re-emissions (e.g. Autosolve extending its budget from
        10 to 15 cycles) keep the value already reached."""
        floor = int(getattr(self, "_overall_progress_floor", 0))
        value = max(int(value), floor)
        self._overall_progress_floor = value
        maximum = self.progress_bar.maximum()
        self.progress_bar.setValue(min(value, maximum) if maximum > 0 else value)

    def _set_overall_progress_text(self, text: str) -> None:
        display = str(text)
        self.progress_bar.setFormat(display)
        if hasattr(self, "overall_progress_value"):
            self.overall_progress_value.setText(display)

    def clear_log_plot(self) -> None:
        self.review_edma_executor.cancel_all()
        self.log_text.clear()
        self.log_text.horizontalScrollBar().setValue(0)
        self._last_log_record = None
        self.results.clear()
        self._structure_jobs.clear()
        self._operation_states.clear()
        self._live_structures.clear()
        self._handoff_pending = False
        self._handoff_candidate_snapshot = None
        self._handoff_results_snapshot = None
        self._handoff_initial_source = None
        self._handoff_selector_scheduled = False
        self._autosolve_pass_now_requested = False
        self.result_recommendation = None
        self.current_validation_profile = ValidationProfile.REFERENCE_FREE
        self.reference_atoms_for_plot.clear()
        self.superflip_atoms_for_plot.clear()
        self.deblur_atoms_for_plot.clear()
        for panel in self._structure_source_paths:
            self._structure_source_paths[panel] = None
        self.structure_cell = None
        self._overall_progress_floor = 0
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
        if hasattr(self, "classic_review_controls"):
            self._sync_classic_review_controls()
        self._update_plot()
        self._update_structure_views()
        self._sync_idle_ready_log()

    def _begin_fresh_run_context(self, cfg: RunConfig) -> None:
        """Give a top-level Run its own artifacts and clean scientific state."""
        self._autosolve_prediction_cycles = set()
        self.review_edma_executor.cancel_all()
        run_id, run_dir = allocate_run_directory(cfg.work_dir)
        cfg.run_id = run_id
        cfg.work_dir = run_dir
        if cfg.jana_inflip is not None and Path(cfg.jana_inflip).is_file():
            diagnostics = run_dir / "diagnostics"
            diagnostics.mkdir(parents=True, exist_ok=True)
            incoming = diagnostics / "incoming.inflip"
            shutil.copyfile(cfg.jana_inflip, incoming)
            (diagnostics / "incoming_context.json").write_text(
                json.dumps({"source": str(cfg.jana_inflip), "sha256": file_sha256(incoming),
                            "purpose": "Diagnostic copy; original Jana context remains authoritative"}, indent=2),
                encoding="utf-8",
            )
        if self._run_diagnostic_log is not None:
            self._run_diagnostic_log.close()
        self._run_diagnostic_log = RunDiagnosticLog(run_dir / "log.txt", cfg)
        if hasattr(self, "execution_log_open_button"):
            self.execution_log_open_button.setEnabled(self._run_diagnostic_log.path.is_file())
        if self._run_diagnostic_log.fallback_reason:
            self._append_execution_log(
                (
                    "Preferred run log was unavailable; diagnostics are being written to a safe runtime location."
                    if self._run_diagnostic_log.persistent else
                    "Persistent diagnostic logging is unavailable; scientific execution will continue."
                ),
                level="WARNING", subsystem="Logging",
            )

        # A finished worker may still have terminal messages waiting for the
        # next timer tick. They belong to the previous run and must not append
        # results or change Run 2's terminal state.
        retained_messages = []
        stale_kinds = {
            "log", "result", "validation_profile", "structure_update", "structure_state",
            "reference_atoms", "structure_cell", "handoff_done",
            "handoff_error", "autosolve_prediction_done",
            "autosolve_prediction_error", "autosolve_threshold_done",
            "autosolve_threshold_error", "progress_setup", "cycle_progress",
            "progress", "error", "error_report", "cancelled", "stopped", "done",
        }
        try:
            while True:
                message = self.msg_queue.get_nowait()
                if not message or message[0] not in stale_kinds:
                    retained_messages.append(message)
        except queue.Empty:
            pass
        for message in retained_messages:
            self.msg_queue.put(message)

        for viewer in getattr(self, "_classic_detached_viewers", {}).values():
            try:
                viewer.close()
            except Exception:
                pass
        if hasattr(self, "_classic_detached_viewers"):
            self._classic_detached_viewers.clear()

        self._active_run_id = run_id
        self.results.clear()
        self._structure_jobs.clear()
        self._operation_states.clear()
        self._live_structures.clear()
        self.result_recommendation = None
        self._resume_state = None
        self._handoff_pending = False
        self._handoff_candidate_snapshot = None
        self._handoff_results_snapshot = None
        self._handoff_initial_source = None
        self._handoff_selector_scheduled = False
        self._autosolve_pass_now_requested = False
        self.autosolve_handoff_state = "idle"
        self.autosolve_predictions.clear()
        self.autosolve_panels.clear()
        self.autosolve_refinement = None
        self.autosolve_activity = ""
        self.autosolve_timings.clear()
        self.current_validation_profile = ValidationProfile.REFERENCE_FREE
        self.reference_atoms_for_plot.clear()
        self.superflip_atoms_for_plot.clear()
        self.deblur_atoms_for_plot.clear()
        for panel in self._structure_source_paths:
            self._structure_source_paths[panel] = None
        self.structure_cell = None
        self._structure_parse_errors.clear()
        self.log_text.clear()
        self._last_log_record = None
        self._sync_classic_review_controls()
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
        diagnostic_log = getattr(self, "_run_diagnostic_log", None)
        if diagnostic_log is not None:
            diagnostic_log.write(record)

        # The GUI is a concise scientific progress view. The complete record,
        # including paths, hashes, commands and map statistics, was persisted
        # above before this presentation filter is applied.
        if record.category in {"DIAGNOSTIC", "TRACE"}:
            return False
        # The idle line is a placeholder, not part of a run's history.
        if record.text != "Ready. Select an input to begin." and self.log_text.document().firstBlock().text() == "Ready. Select an input to begin.":
            cursor = QTextCursor(self.log_text.document().firstBlock())
            cursor.select(QTextCursor.BlockUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()
        repeatable_status = bool(
            record.subsystem.lower() == "sharped"
            and re.search(r"(?:server status:|\]\s*(?:processing|completed|uploading|downloading))", record.text, re.IGNORECASE)
        )
        if repeatable_status:
            status_match = re.search(
                r"(?:server status:\s*|\]\s*)(processing|completed|uploading|downloading|submitted)",
                record.text, re.IGNORECASE,
            )
            status_key = status_match.group(1).casefold() if status_match else record.text.casefold()
            states = getattr(self, "_last_gui_status_by_subsystem", {})
            subsystem_key = record.subsystem.casefold()
            if states.get(subsystem_key) == status_key:
                return False
            states[subsystem_key] = status_key
            self._last_gui_status_by_subsystem = states
        # Consecutive, byte-identical INFO/SUCCESS/DETAIL lines are almost always
        # presentation noise (e.g. a settings-loading step logged from more than
        # one code path with the same summary), not new information. WARNING,
        # ERROR and STEP lines are never suppressed this way, even if repeated,
        # since a recurring warning is meaningful on every cycle it appears.
        duplicate_informational = record.level.upper() in {"INFO", "SUCCESS", "DETAIL"}
        same_as_last = bool(
            self._last_log_record is not None
            and (
                self._last_log_record.text,
                self._last_log_record.level,
                self._last_log_record.subsystem,
                self._last_log_record.category,
            ) == (record.text, record.level, record.subsystem, record.category)
        )
        if (repeatable_status or duplicate_informational) and same_as_last:
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
        # Three visual levels, not one color per log level: NORMAL (INFO,
        # STEP, SUCCESS, COMMAND -- day-to-day output), DETAIL (secondary,
        # de-emphasized), WARNING/ERROR (always prominent). The underlying
        # level is unchanged and still written in full to the on-disk log;
        # this only simplifies the on-screen color scheme.
        prominent_colors = {"WARNING": "#8a5a00", "ERROR": "#b42318"}
        if record.level in prominent_colors:
            log_color = prominent_colors[record.level]
        elif record.level == "DETAIL":
            log_color = "#7183a6"
        else:
            log_color = "#14204a"
        text_format.setForeground(QColor(log_color))
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

    # Compatibility/configuration notices that describe a STABLE property of
    # the current executable or settings, so they say exactly the same thing on
    # every Superflip call. They were emitted for the normal calculation, again
    # for the OMIT calculation, and again for every cycle -- on a 5-cycle OMIT
    # run that is the same three lines up to twenty times, burying the
    # scientifically interesting output. They are reported once per workflow.
    # Matching is on the full message text, so a genuinely NEW warning (a
    # different keyword, a different value) is still reported the first time it
    # appears. The per-process Superflip/EDMA log files keep every occurrence.
    LOG_ONCE_PER_WORKFLOW_PREFIXES = (
        "Superflip normalize value",
        "Superflip executable does not support",
        "  Ignored duplicate/managed Superflip keyword",
    )

    def log(self, message: str, *, level: str = "", subsystem: str = "") -> None:
        text = str(message)
        if text.startswith(self.LOG_ONCE_PER_WORKFLOW_PREFIXES):
            seen = getattr(self, "_workflow_log_once", None)
            if seen is None:
                seen = set()
                self._workflow_log_once = seen
            if text in seen:
                return
            seen.add(text)
        work_dir = self.last_run_config.work_dir if self.last_run_config is not None else None
        self._queue_run_event("log", classify_log_record(
            message,
            level=level,
            subsystem=subsystem,
            work_dir=work_dir,
        ))

    def _queue_run_event(
        self, kind: str, payload: object, run_id: Optional[str] = None,
    ) -> None:
        owner = str(
            run_id if run_id is not None
            else getattr(self._run_event_context, "run_id", self._active_run_id)
        )
        self.msg_queue.put((kind, RunScopedPayload(owner, payload) if owner else payload))

    def _run_display_operation(self, state: PipelineState, cycle: int, name: str, call):
        """Publish real job lifetime; scientific call and return value are unchanged."""
        # Branch-executor threads do not inherit the parent's threading.local.
        # Bind progress/log callbacks to this job rather than whichever run is
        # globally active by the time a late callback arrives.
        self._run_event_context.run_id = str(state.run_id)
        with self._structure_job_lock:
            self._structure_job_generation += 1
            job_id = f"operation:{self._structure_job_generation}"
        self._queue_run_event("operation_state", (job_id, name, cycle, "running"), state.run_id)
        try:
            return call()
        finally:
            self._queue_run_event("operation_state", (job_id, name, cycle, "finished"), state.run_id)

    def active_workflow_operations(self) -> List[str]:
        """GUI-thread lifecycle state, including independent EDMA branches."""
        if str(getattr(self, "_run_status", "")).upper() not in {"RUNNING", "REVIEW"}:
            return []
        labels = [f"{name} · Cycle {cycle} · {self._sharped_display_phases.get(cycle, 'Processing') if name == 'SharpED' else 'Running'}"
                  for name, cycle, status in self._operation_states.values() if status == "running"]
        for update in self._structure_jobs.values():
            if update.status in {"queued", "running"}:
                family = "Charge-flipping solution" if update.source == "superflip" else "Structure prediction"
                labels.append(f"EDMA · {family} · Cycle {update.cycle} · "
                              f"{'Queued' if update.status == 'queued' else 'Running'}")
        for role, panel in self.autosolve_panels.items():
            if panel.busy:
                labels.append(f"EDMA · {panel.title} · Cycle {panel.cycle} · Running")
        return list(dict.fromkeys(labels))

    def _new_structure_job(
        self, state: PipelineState, source: str, cycle: int, map_path: Path, threshold: float,
        *, superflip_initialization: str = "", reflection_input_provenance: str = "",
    ) -> StructureJobUpdate:
        """Create and queue a uniquely identified automatic EDMA request."""
        resolved_map = Path(map_path).resolve()
        with self._structure_job_lock:
            self._structure_job_generation += 1
            generation = self._structure_job_generation
        map_hash = file_sha256(resolved_map) if resolved_map.is_file() else ""
        request_id = f"automatic:{source}:{cycle}:{generation}:{map_hash[:12]}"
        update = StructureJobUpdate(
            run_id=str(state.run_id), source=str(source), cycle=int(cycle),
            map_path=resolved_map, map_sha256=map_hash, threshold=float(threshold),
            request_id=request_id, generation=generation, status="queued",
            superflip_initialization=str(superflip_initialization),
            reflection_input_provenance=str(reflection_input_provenance),
        )
        self._queue_run_event("structure_state", update, state.run_id)
        return update

    def _structure_job_status(
        self, job: StructureJobUpdate, status: str, structure_path: Optional[Path] = None,
    ) -> StructureJobUpdate:
        resolved = Path(structure_path).resolve() if structure_path is not None else None
        update = replace(
            job, status=str(status), structure_path=resolved,
            structure_sha256=(file_sha256(resolved) if resolved is not None and resolved.is_file() else ""),
            edma_asu_composition=(
                edma_asu_composition_from_cif(resolved)
                if str(status) == "complete" and resolved is not None else ""
            ),
        )
        self._queue_run_event("structure_state", update, job.run_id)
        return update

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
        self._queue_run_event("cycle_progress", CycleProgressState(
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
        ))

    def _apply_cycle_progress_state(self, state: CycleProgressState) -> None:
        if state.cycle_index == 1 and state.stage_name == 'Superflip' and self._cycle_progress_state is None:
            self._sharped_display_phases.clear()
        if state.stage_name == 'SharpED':
            detail = state.detail.casefold()
            # Server-completed may describe one tile, not the reconstructed map.
            for token, label in (('uploading', 'Uploading'), ('downloading', 'Downloading'), ('processing', 'Server processing'), ('completed', 'Processing')):
                if token in detail:
                    self._sharped_display_phases[state.cycle_index] = label
                    break
        self._cycle_progress_state = state
        if state.complete:
            self._set_overall_progress_value(state.cycle_index)
        stage_total = max(1, int(state.stage_total))
        if state.busy and not state.complete:
            # Unknown-duration stage (e.g. waiting on the SharpED server):
            # an empty-looking static bar reads as stalled/broken, not busy.
            self.current_cycle_progress.setRange(0, 0)
        else:
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
            self.superflip_repeat_group.setVisible(False)
            return
        sub_total = int(sub_total)
        sub_index = max(1, min(int(sub_index), sub_total))
        self.superflip_repeat_detail.setText(f"Superflip repeat {sub_index} of {sub_total}")
        self.superflip_repeat_progress.setRange(0, sub_total)
        self.superflip_repeat_progress.setValue(sub_index)
        self.superflip_repeat_group.setVisible(True)

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
            self.current_cycle_detail.setText("Stopped after current cycle" if terminal == "Stopped" else terminal)
            return

        stage_total = max(1, int(state.stage_total))
        stage_index = max(1, min(stage_total, int(state.stage_index)))
        self.current_cycle_progress.setRange(0, stage_total)
        self.current_cycle_progress.setValue(max(self.current_cycle_progress.value(), stage_index))
        self.current_cycle_stage_counter.setText(f"{terminal} at stage {stage_index} of {stage_total}")
        outcome = "stopped by user" if terminal == "Stopped" else terminal.lower()
        stage_name = {
            "EDMA · Superflip map": "EDMA · Charge-flipping solution",
            "EDMA · SharpED map": "EDMA · Structure prediction",
        }.get(state.stage_name, state.stage_name)
        parts = [f"Cycle {state.cycle_index} of {state.cycle_total}", f"{stage_name} {outcome}"]
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
        self._append_execution_log(
            "Workflow cancelled by the user.", level="WARNING", subsystem="Workflow"
        )

    def _finish_cancelled_run_for_request(self) -> None:
        """Cancelled terminal state, whichever queued event carried it
        ("cancelled", or a "stopped"/"done" overtaken by an immediate
        request). Autosolve's "Pass to Jana2020" uses immediate cancel as
        its vehicle; only then does Result Selection open afterwards, over
        the already completed results. A plain Cancel never sets the flag,
        so every other launch mode is unaffected."""
        if self._handoff_pending:
            self._finish_handoff_stop()
            return
        self._finish_cancelled_run()
        if self._autosolve_pass_now_requested:
            self._autosolve_pass_now_requested = False
            self._autosolve_handoff(self._autosolve_candidate_source())

    def _finish_handoff_stop(self) -> None:
        """Terminalize an early Pass request without misreporting Cancel."""
        if self._handoff_selector_scheduled:
            return
        self._handoff_selector_scheduled = True
        self.worker = None
        completed = len(self._handoff_results_snapshot or self.results)
        total = max(1, int(getattr(self.last_run_config, "cycles", 1)), completed)
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(min(completed, total))
        self._set_overall_progress_text("Stopped for Jana2020 handoff")
        self._set_terminal_cycle_state("Stopped")
        self.stop_after_cycle.clear()
        self.stop_now.clear()
        self._set_run_status("Stopped")
        self.run_btn.setText("Run phasing")
        self._autosolve_pass_now_requested = False
        self._append_execution_log(
            "Completed results retained. Opening Jana2020 result selection.",
            level="SUCCESS", subsystem="Jana2020",
        )
        self._update_action_states()
        if self.jana_wizard_context.launch_mode == "autosolve":
            self._autosolve_handoff(self._handoff_initial_source or self._autosolve_candidate_source())
        else:
            QTimer.singleShot(0, self._open_pending_handoff_selector)

    def _open_pending_handoff_selector(self) -> None:
        """GUI-thread continuation after every owned worker has terminated."""
        if not self._handoff_pending:
            return
        initial_source = self._handoff_initial_source
        if self.jana_wizard_context.launch_mode == "autosolve":
            self.autosolve_handoff_state = "selecting"
        started = self.open_result_selector(
            "jana", dialog_parent=self.autosolve_dialog_parent,
            initial_source=initial_source,
        )
        self._handoff_pending = False
        self._handoff_candidate_snapshot = None
        self._handoff_results_snapshot = None
        self._handoff_initial_source = None
        self._handoff_selector_scheduled = False
        self._sync_jana_action_button()
        if self.jana_wizard_context.launch_mode == "autosolve":
            self.autosolve_handoff_state = "handing_off" if started else "declined"
        if not started:
            self._append_execution_log(
                "Result Selection closed without passing a result. Completed results remain available.",
                subsystem="Jana2020",
            )

    def _finish_stopped_run(self, completed_cycles: int) -> None:
        """Terminal state for "Stop after current cycle": the requested cycle
        finished normally, so every completed result stays valid and usable.

        Deliberately distinct from _finish_cancelled_run(): calling this a
        cancellation told the user their completed, scientifically valid
        cycles had been thrown away, which is not what happened.
        """
        self.worker = None
        completed = max(int(completed_cycles), len(self.results))
        total_cycles = max(1, int(getattr(self.last_run_config, "cycles", 1)), completed)
        self.progress_bar.setRange(0, total_cycles)
        self.progress_bar.setValue(min(completed, total_cycles))
        self._set_overall_progress_text("Stopped")
        self._set_terminal_cycle_state("Stopped")
        self.stop_after_cycle.clear()
        self.stop_now.clear()
        self._set_run_status("Stopped")
        self.run_btn.setText("Run phasing")
        self.run_btn.setEnabled(True)
        self._update_action_states()
        self._append_execution_log(
            f"Workflow stopped after cycle {completed} as requested.",
            level="WARNING",
            subsystem="Workflow",
        )
        self._append_execution_log(
            "Completed results are available.",
            subsystem="Workflow",
        )
        # A partially completed workflow is still a usable result set: the
        # Jana2020 hand-off stays available for whatever finished.
        self._sync_jana_action_button()
        if self._jana_wizard_handoff_available():
            QTimer.singleShot(0, self._auto_open_jana_result_selector)

    def _set_run_status(self, status: str) -> None:
        previous_status = getattr(self, "_run_status", "READY")
        normalized = str(status).strip().upper() or "READY"
        normalized = {
            "IDLE": "READY",
            "DONE": "COMPLETE",
            "COMPLETED": "COMPLETE",
            "FAILED": "ERROR",
            "CANCELED": "CANCELLED",
            # A graceful "Stop after current cycle" is its own terminal state:
            # the cycle completed and its results are valid. It must never be
            # folded into CANCELLED, which means an immediate interruption.
            "STOP": "STOPPED",
            # The pipeline is still RUNNING for button-enablement purposes while a
            # stop is pending; the "stopping" badge is shown separately via
            # _show_stopping_badge() without changing the stored _run_status.
            "STOPPING": "RUNNING",
        }.get(normalized, normalized)
        self._run_status = normalized
        if normalized == "RUNNING" and previous_status != "RUNNING" and hasattr(self, "log_text"):
            self._append_execution_log("Workflow started.", subsystem="Workflow")
        if hasattr(self, "status_badge"):
            self.status_badge.setText(normalized)
            self.status_badge.setProperty("runState", normalized.lower())
            self.status_badge.style().unpolish(self.status_badge)
            self.status_badge.style().polish(self.status_badge)
        if hasattr(self, "current_cycle_progress"):
            self.current_cycle_progress.setVisible(normalized == "RUNNING")
        if normalized == "ERROR" and hasattr(self, "execution_log_expand_button"):
            self._set_execution_log_expanded(True)
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
        return jana_handoff_available(
            results_available=bool(self.results),
            run_inflip=(self.last_run_config.jana_inflip if self.last_run_config else None),
            launched_from_jana=self.jana_wizard_context.launched_from_jana_wizard,
            launch_mode=self.jana_wizard_context.launch_mode,
        )

    def _sync_window_title(self) -> None:
        """Single source of truth for the window title, driven entirely by
        launch context (jana_wizard_context.launched_from_jana_wizard) --
        never inferred from whether a .inflip happens to be loaded. Keeps the wrapper launch context visible."""
        if self.jana_wizard_context.launched_from_jana_wizard:
            self.setWindowTitle(f"Phase Studio {__version__} for Jana2020")
        else:
            self.setWindowTitle(f"Phase Studio {__version__}")

    def _sync_jana_action_button(self) -> None:
        """Expose the shared result selector with context-specific wording."""
        if not hasattr(self, "jana_action_btn"):
            return
        launched = self.jana_wizard_context.launched_from_jana_wizard
        self.jana_action_btn.setVisible(True)
        self.jana_action_btn.setText(
            "Preparing handoff…" if launched and self._handoff_pending else
            ("Pass to Jana2020" if launched else "Save map and model")
        )
        self._fit_primary_action_buttons()
        self.jana_action_btn.setToolTip(
            "Select a completed workflow result to pass to Jana2020."
            if launched else
            "Select and save an existing completed map and structure model."
        )
        active = str(getattr(self, "_run_status", "READY")).upper() == "RUNNING"
        available = self._jana_wizard_handoff_available() if launched else bool(self._result_candidates())
        self.jana_action_btn.setEnabled(available and not self._handoff_pending and (launched or not active))

    def _fit_primary_action_buttons(self) -> None:
        """Keep every primary action label fully readable: each button's
        minimum width is its own text-derived size hint (font metrics +
        stylesheet padding), and the row's stretch is allocated in
        proportion to those hints. Recomputed whenever a label changes."""
        rows = (
            (getattr(self, "_primary_action_row", None), (self.run_btn, self.continue_btn, self.jana_action_btn)),
            (getattr(self, "_secondary_action_row", None), (self.stop_btn, self.stop_now_btn, self.clear_btn)),
        )
        for row, buttons in rows:
            if row is None:
                continue
            for button in buttons:
                button.ensurePolished()
                hint = int(button.sizeHint().width())
                button.setMinimumWidth(hint)
                row.setStretchFactor(button, max(1, hint))

    def _on_jana_action_clicked(self) -> None:
        if self.jana_wizard_context.launched_from_jana_wizard:
            if str(getattr(self, "_run_status", "")).upper() == "RUNNING":
                self.request_jana_handoff_now()
            else:
                self.open_jana_handoff_dialog()
        else:
            self.open_result_selector(context="standalone")

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

    def request_autosolve_pass_now(self) -> None:
        """AutosolveWindow's "Pass to Jana2020": stop the active work
        IMMEDIATELY (the same established immediate-cancel mechanism Cancel
        itself uses -- never waits for the in-flight cycle to finish, never
        starts another stage), then hand off the best ALREADY COMPLETED
        candidate -- see the "cancelled" handling in _poll_queue. An
        in-flight cycle that was only partially through Superflip/EDMA/
        SharpED/validation/Map Feedback never reaches _finalize_completed_
        cycle(), so it was never appended to self.results in the first
        place; only genuinely finished cycles are ever eligible."""
        if str(getattr(self, "_run_status", "")).upper() != "RUNNING":
            # Nothing is running any more (the run finished or was stopped):
            # go straight to the shared Result Selection.
            self._autosolve_handoff(self._autosolve_candidate_source())
            return
        self.autosolve_handoff_state = "stopping"
        requested = self.request_jana_handoff_now(self._autosolve_candidate_source())
        self._autosolve_pass_now_requested = requested
        if not requested:
            self.autosolve_handoff_state = "idle"

    def request_jana_handoff_now(self, initial_source: Optional[str] = None) -> bool:
        """Freeze completed candidates, then stop only unfinished active work."""
        if self._handoff_pending:
            return False
        candidates = result_candidates_from_results(self.results)
        if not candidates:
            self._append_execution_log(
                "No completed result is available yet. The calculation is still running.",
                level="WARNING", subsystem="Jana2020",
            )
            return False
        if str(getattr(self, "_run_status", "")).upper() != "RUNNING":
            return self.open_result_selector("jana", initial_source=initial_source)
        self._handoff_pending = True
        self._handoff_candidate_snapshot = list(candidates)
        self._handoff_results_snapshot = list(self.results)
        self._handoff_initial_source = initial_source
        self._handoff_selector_scheduled = False
        self._append_execution_log(
            "Jana2020 handoff requested. Completed results retained.",
            level="STEP", subsystem="Jana2020",
        )
        self._annotate_cycle_progress("Preparing Jana2020 handoff…")
        self._sync_jana_action_button()
        self.request_immediate_stop()
        return True

    def request_immediate_stop(self) -> None:
        # Publish the higher-priority intent first. The worker may inspect the
        # flags between these two calls, and must never see an immediate request
        # as graceful-only.
        self.stop_now.set()
        self.stop_after_cycle.set()
        self._annotate_cycle_progress(
            "Stopping unfinished calculation…" if self._handoff_pending else "Stopping immediately…"
        )
        self._update_action_states()
        self._show_stopping_badge()
        self.log(
            "Stopping unfinished calculation for Jana2020 handoff."
            if self._handoff_pending else "Immediate stop requested.",
            level="DETAIL",
        )

    def _requested_workflow_stop_kind(self) -> str:
        """Return the authoritative terminal intent in priority order."""
        if self.stop_now.is_set():
            return "cancelled"
        if self.stop_after_cycle.is_set():
            return "stopped"
        return ""

    def _emit_requested_workflow_stop(self, completed_cycles: int) -> bool:
        """Emit the authoritative requested terminal intent, if any."""
        kind = self._requested_workflow_stop_kind()
        if not kind:
            return False
        self._queue_run_event(kind, int(completed_cycles))
        return True

    def refresh_sharped_models(self) -> None:
        base_widget = self.inputs.get("sharped_base_url")
        timeout_widget = self.inputs.get("sharped_timeout_seconds")
        base_url = base_widget.text().strip() if isinstance(base_widget, QLineEdit) else DEFAULT_SERVER_URL
        timeout = 20
        if isinstance(timeout_widget, QSpinBox):
            timeout = max(5, min(60, int(timeout_widget.value())))

        def worker() -> None:
            try:
                client = SharpEDServerClient(base_url=base_url or DEFAULT_SERVER_URL, timeout=float(timeout))
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
            set_value("plimit_superflip", str(NORMAL_EDMA_THRESHOLD_SIGMA))
            set_value("plimit_deblur", str(NORMAL_EDMA_THRESHOLD_SIGMA))
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
        else:
            raise ValueError(f"Configuration page is unavailable: {name}")
        self.show()
        self.raise_()
        self.activateWindow()
        tabs.currentWidget().setFocus()

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
            return [ErrorAction("Set up Superflip", row.browse, True)] if isinstance(row, PathRow) else []
        if category == "edma_missing":
            row = self.inputs.get("edma_exe")
            return [ErrorAction("Set up EDMA", row.browse, True)] if isinstance(row, PathRow) else []
        if category in {"file_permission", "file_write"}:
            row = self.inputs.get("work_dir")
            return [ErrorAction("Choose folder…", row.browse, True)] if isinstance(row, PathRow) else []
        if category == "sharped_authentication":
            return [ErrorAction("Account access…", self._manage_sharped_access, True)]
        if category in {"sharped_model_missing", "sharped_catalogue"}:
            return [ErrorAction("Try again", lambda: (
                setattr(self, "_retry_model_preflight", True)
                if getattr(self, "_start_request_active", False) else self.refresh_sharped_models()
            ), True)]
        if category.startswith("sharped_"):
            return []
        if category == "input_validation":
            summary = report.summary.casefold()
            actions: List[ErrorAction] = []
            for token, key, label in (
                (".inflip", "jana_inflip", "Select .inflip…"),
                ("external hkl", "hkl", "Select HKL…"),
                ("initial model", "first_cycle_modelfile", "Select model…"),
                ("reference file", "reference_cif", "Select reference…"),
                ("superflip", "superflip_exe", "Locate Superflip…"),
                ("edma", "edma_exe", "Locate EDMA…"),
            ):
                row = self.inputs.get(key)
                if token in summary and isinstance(row, PathRow):
                    actions.append(ErrorAction(label, row.browse, not actions))
            if "sharped api token" in summary or "sharped access key" in summary or "sharped model" in summary:
                actions.append(ErrorAction(
                    "Open SharpED settings",
                    lambda: self._open_configuration_page("Setup", advanced=True),
                    not actions,
                ))
            if not actions:
                actions.append(ErrorAction("Open Input", lambda: self._open_configuration_page("Input"), True))
            return actions
        if category in {"hkl_invalid", "metadata", "unit_cell", "space_group", "composition", "inflip"}:
            return [ErrorAction("Open Input settings", lambda: self._open_configuration_page("Input"), True)]
        return []

    def _show_error_report(self, report: ErrorReport, *, write_log: bool = True) -> str:
        if write_log and hasattr(self, "log_text"):
            # The concise line is enough for the normal workflow log; the full
            # diagnostic (including any traceback) is not duplicated here -- it
            # stays fully available via the error dialog's "Show details".
            self._append_execution_log(report.title + ".", level="ERROR", subsystem=report.subsystem)
        if report.category == "sharped_authentication":
            from phase_studio import requirements as reqs

            status = reqs.RequirementStatus(
                kind=reqs.RequirementKind.SHARPED,
                state=reqs.RequirementState.TOKEN_REJECTED,
            )
            current = self._line_value("sharped_api_token") if "sharped_api_token" in self.inputs else ""
            classified = reqs._classify_sharped_error(RuntimeError(report.technical_details))
            if classified.state in {reqs.RequirementState.TOKEN_REJECTED, reqs.RequirementState.ACCESS_DENIED}:
                status = classified
            base_url = self._line_value("sharped_base_url") or DEFAULT_SERVER_URL
            token = show_requirement_remediation_dialog(
                self, status, current, sharped_base_url=base_url,
                sharped_probe=lambda key: reqs.check_sharped_api(
                    base_url, key, client_factory=getattr(self, "_preflight_client_factory", None)),
            )
            if token is not None:
                widget = self.inputs.get("sharped_api_token")
                if widget is not None:
                    self._set_widget_value_from_string(widget, token)
                if self.last_run_config is not None:
                    self.last_run_config.sharped_api_token = token
                try:
                    self.save_settings()
                except Exception:
                    pass
                return "Set token"
            return ""
        return show_phase_studio_error(self, report, self._error_actions(report))

    def _handle_pipeline_error(self, report: ErrorReport) -> None:
        cancelled = report.category == "cancelled"
        if cancelled:
            self._finish_cancelled_run_for_request()
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
        plot_dirty = False
        structure_dirty = False
        actions_dirty = False
        try:
            processed = 0
            while processed < 250:
                kind, payload = self.msg_queue.get_nowait()
                processed += 1
                if isinstance(payload, RunScopedPayload):
                    event_run_id = str(payload.run_id).strip()
                    active_run_id = str(self._active_run_id).strip()
                    if event_run_id and active_run_id and event_run_id != active_run_id:
                        continue
                    payload = payload.payload
                hkl_task_id: Optional[int] = None
                if kind.startswith("hkl_") and isinstance(payload, tuple) and len(payload) == 2 and isinstance(payload[0], int):
                    hkl_task_id, payload = payload
                    if hkl_task_id != self._active_hkl_task_id:
                        continue
                    if kind != "hkl_task_finished":
                        if hkl_task_id in self._completed_hkl_task_ids:
                            continue
                        self._completed_hkl_task_ids.add(hkl_task_id)
                if kind == "operation_state":
                    job_id, name, cycle, status = payload
                    previous = self._operation_states.get(job_id)
                    if previous is None or previous[2] != "finished":
                        self._operation_states[job_id] = (name, cycle, status)
                elif kind == "log":
                    self._append_execution_log(payload)
                    actions_dirty = True
                elif kind == "result":
                    result = payload  # type: ignore[assignment]
                    self.results.append(result)  # type: ignore[arg-type]
                    self._structure_source_paths["superflip"] = Path(result.superflip_edma_cif) if result.superflip_edma_cif else None  # type: ignore[attr-defined]
                    self._structure_source_paths["deblur"] = Path(result.deblur_edma_cif) if result.deblur_edma_cif else None  # type: ignore[attr-defined]
                    self.superflip_atoms_for_plot = self._classic_structure_atoms(result.superflip_edma_cif)  # type: ignore[attr-defined]
                    self.deblur_atoms_for_plot = self._classic_structure_atoms(result.deblur_edma_cif)  # type: ignore[attr-defined]
                    self._sync_classic_review_controls()
                    plot_dirty = True
                    structure_dirty = True
                    actions_dirty = True
                elif kind == "validation_profile":
                    try:
                        self.current_validation_profile = ValidationProfile(str(payload))
                    except (TypeError, ValueError):
                        self.current_validation_profile = ValidationProfile.REFERENCE_FREE
                    plot_dirty = True
                elif kind == "structure_update":
                    panel, cif_path = payload  # type: ignore[misc]
                    result_panel = "superflip" if str(panel) == "superflip" else "deblur"
                    # Once canonical completed candidates exist, a live
                    # in-progress file must not replace a pinned/history view.
                    if self._classic_candidates(result_panel):
                        continue
                    atoms = self._classic_structure_atoms(Path(cif_path))
                    if str(panel) == "superflip":
                        self._structure_source_paths["superflip"] = Path(cif_path)
                        self.superflip_atoms_for_plot = atoms
                    elif str(panel) == "deblur":
                        self._structure_source_paths["deblur"] = Path(cif_path)
                        self.deblur_atoms_for_plot = atoms
                    structure_dirty = True
                elif kind == "structure_state" and isinstance(payload, StructureJobUpdate):
                    update = payload
                    key = (update.source, int(update.cycle))
                    previous = self._structure_jobs.get(key)
                    if previous is not None and update.generation < previous.generation:
                        continue
                    if previous is not None and update.generation == previous.generation and previous.status in {"complete", "failed", "cancelled"}:
                        if update.status in {"queued", "running"}:
                            continue
                    # A map file reused under the same name is still a
                    # different scientific request. Reject the old hash.
                    if update.map_path.is_file() and update.map_sha256:
                        try:
                            if file_sha256(update.map_path) != update.map_sha256:
                                continue
                        except OSError:
                            continue
                    self._structure_jobs[key] = update
                    if update.status == "complete" and update.structure_path is not None:
                        if not update.structure_path.is_file():
                            continue
                        if update.structure_sha256 and file_sha256(update.structure_path) != update.structure_sha256:
                            continue
                        current = self._live_structures.get(update.source)
                        if current is None or (update.cycle, update.generation) >= (current.cycle, current.generation):
                            self._live_structures[update.source] = update
                            panel = "superflip" if update.source == "superflip" else "deblur"
                            self._structure_source_paths[panel] = update.structure_path
                            atoms = self._classic_structure_atoms(update.structure_path)
                            if panel == "superflip":
                                self.superflip_atoms_for_plot = atoms
                            else:
                                self.deblur_atoms_for_plot = atoms
                            structure_dirty = True
                elif kind == "reference_atoms":
                    reference_payload = payload  # type: ignore[assignment]
                    reference_path = None
                    if isinstance(reference_payload, tuple) and len(reference_payload) == 2:
                        reference_payload, reference_path = reference_payload
                    self._structure_source_paths["reference"] = Path(reference_path) if reference_path else None
                    if self._structure_source_paths["reference"] is not None:
                        self.reference_atoms_for_plot = self._classic_structure_atoms(
                            self._structure_source_paths["reference"]
                        )
                    else:
                        self.reference_atoms_for_plot = list(reference_payload)  # type: ignore[arg-type]
                    self._sync_classic_review_controls()
                    structure_dirty = True
                elif kind == "structure_cell":
                    values = tuple(float(value) for value in payload)  # type: ignore[arg-type]
                    if len(values) == 6 and min(values[:3]) > 0:
                        self.structure_cell = gemmi.UnitCell(*values)
                        structure_dirty = True
                elif kind == "sharped_models":
                    default_model, models = payload  # type: ignore[misc]
                    widget = self.inputs.get("sharped_model")
                    if isinstance(widget, QComboBox):
                        current = widget.currentText().strip() or "default"
                        values, displayed = reconcile_model_selection(current, list(models), str(default_model))
                        widget.blockSignals(True)
                        widget.clear()
                        widget.addItems(values)
                        widget.setCurrentText(displayed)
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
                elif kind == "autosolve_prediction_done":
                    record, elapsed = payload  # type: ignore[misc]
                    self._autosolve_on_prediction_done(record, elapsed)
                elif kind == "autosolve_prediction_error":
                    self._autosolve_on_prediction_error(payload)  # type: ignore[arg-type]
                elif kind == "autosolve_threshold_done":
                    role, sigma, cif, elapsed = payload  # type: ignore[misc]
                    self._autosolve_on_threshold_done(role, sigma, cif, elapsed)
                elif kind == "autosolve_threshold_error":
                    role, sigma, report = payload  # type: ignore[misc]
                    self._autosolve_on_threshold_error(role, sigma, report)
                elif kind == "review_edma_done" and isinstance(payload, ReviewOutcome):
                    self.review_edma_executor.complete(payload)
                elif kind == "handoff_error" and self.autosolve_in_review():
                    # Guided Review: the results stay; the user may try again.
                    self.autosolve_handoff_state = "idle"
                    report = payload if isinstance(payload, ErrorReport) else build_error_report(payload, subsystem="Jana2020", operation="Jana2020 handoff")
                    self._show_error_report(report)
                elif kind == "handoff_error":
                    self._set_run_status("Error")
                    report = payload if isinstance(payload, ErrorReport) else build_error_report(payload, subsystem="Jana2020", operation="Jana2020 handoff")
                    self._show_error_report(report)
                    self.handoff_btn.setEnabled(bool(self.results and self.last_run_config and self.last_run_config.jana_inflip is not None))
                elif kind == "progress_setup":
                    self._set_run_status("Running")
                    total = max(1, int(payload))
                    self.progress_bar.setRange(0, total)
                    self._set_overall_progress_value(0)
                    self._set_overall_progress_text("Running")
                    self.current_cycle_progress.setRange(0, 0)
                    self.current_cycle_detail.setText(f"Cycle 1 of {total} · Preparing cycle")
                    self.current_cycle_stage_counter.setText("Preparing")
                    self._apply_superflip_repeat_state(None)
                elif kind == "cycle_progress":
                    self._apply_cycle_progress_state(payload)  # type: ignore[arg-type]
                elif kind == "progress":
                    self._set_overall_progress_value(int(payload))
                    self._set_overall_progress_text("Running")
                elif kind in {"error", "error_report"}:
                    report = payload if isinstance(payload, ErrorReport) else build_error_report(payload, operation="Run workflow")
                    self._handle_pipeline_error(report)
                elif kind == "cancelled":
                    self._finish_cancelled_run_for_request()
                elif kind == "stopped":
                    if self._handoff_pending and self._handoff_selector_scheduled:
                        continue
                    # An immediate request may arrive after the worker queued a
                    # graceful terminal event but before the GUI consumes it.
                    if self._requested_workflow_stop_kind() == "cancelled":
                        self._finish_cancelled_run_for_request()
                    else:
                        self._finish_stopped_run(int(payload) if payload is not None else len(self.results))
                elif kind == "done":
                    if self._handoff_pending and self._handoff_selector_scheduled:
                        continue
                    # The Run controls remain active until this queued event is
                    # consumed, so a last-moment immediate request still wins.
                    if self._requested_workflow_stop_kind() == "cancelled":
                        self._finish_cancelled_run_for_request()
                        continue
                    if self.jana_wizard_context.launch_mode == "autosolve":
                        # A guided-Autosolve block finished: the adaptive
                        # decision below continues, predicts or opens Review.
                        # This is never a terminal COMPLETE.
                        self.worker = None
                        self.stop_after_cycle.clear()
                        self.stop_now.clear()
                        if payload is not None:
                            self._set_overall_progress_value(int(payload))
                        self._append_execution_log(
                            f"[Autosolve] Cycle block finished at cycle {payload}.", level="DETAIL", subsystem="Autosolve",
                        )
                        QTimer.singleShot(0, self._autosolve_on_run_done)
                        continue
                    self.worker = None
                    self.stop_after_cycle.clear()
                    self.stop_now.clear()
                    self._set_run_status("Complete")
                    self._append_execution_log("Workflow complete", level="SUCCESS")
                    if payload is not None:
                        self.progress_bar.setValue(int(payload))
                    self._set_overall_progress_text("Complete")
                    if self._cycle_progress_state is None:
                        self.current_cycle_detail.setText("Workflow complete")
                        self.current_cycle_stage_counter.setText("Completed")
                    self.run_btn.setEnabled(True)
                    self.run_btn.setText("Run phasing")
                    self._sync_jana_action_button()
                    if self.jana_wizard_context.launch_mode == "autosolve":
                        # Autosolve drives its own adaptive continue/extend/stop
                        # decisions; only at its end point does it open the
                        # shared Result Selection (_autosolve_handoff), not the
                        # Wizard's auto-open path below.
                        QTimer.singleShot(0, self._autosolve_on_run_done)
                    # Auto-opening the result selector is Jana-Wizard-owned
                    # functionality: a standalone session that happens to
                    # load a Jana2020 .inflip manually must never trigger it
                    # (spec: only a session actually launched from the
                    # Wizard -- either Full configuration or Phase recycling
                    # -- is eligible).
                    elif self._jana_wizard_handoff_available():
                        # Defer the modal selector until this queue-drain turn
                        # finishes. Wizard auto-runs and manually started Full
                        # configuration runs share the same behavior.
                        QTimer.singleShot(0, self._auto_open_jana_result_selector)
        except queue.Empty:
            pass
        # A worker can enqueue several state changes before one timer tick
        # (for example two structure updates followed by the completed result).
        # Apply their final state once per bounded batch so the GUI never pays
        # for redraws that could not have become visible between queue items.
        if plot_dirty:
            self._update_plot()
        if structure_dirty:
            self._update_structure_views()
        if actions_dirty:
            self._update_action_states()

    def _auto_open_jana_result_selector(self) -> None:
        """Open the shared Jana2020 selector after a usable Wizard run.

        Nothing here is speculative: "Opening..." is logged immediately before
        the real open request and a confirmation only after the selector has
        actually been constructed and shown, so the execution log can never
        claim a selector that never appeared. A failure is reported, never
        swallowed -- in a windowed build an escaping exception would otherwise
        vanish with no stderr to print to, which is exactly how this looked
        like "the log says it opened but nothing happened".
        """
        # Re-check rather than trust the state captured at completion time:
        # this runs one event-loop turn later, so a Clear (or a new run) could
        # have invalidated the results in between.
        if not self._jana_wizard_handoff_available():
            return
        if self._jana_auto_selector_shown:
            return
        self._jana_auto_selector_shown = True
        self._append_execution_log(
            "Opening Jana2020 Result Selection…",
            subsystem="Jana2020",
        )
        try:
            self.open_jana_result_selector()
        except Exception as exc:
            self._append_execution_log(
                f"The Jana2020 result selector could not be opened: {exc}",
                level="ERROR",
                subsystem="Jana2020",
            )
            self._show_error_report(
                build_error_report(
                    exc,
                    subsystem="Jana2020",
                    operation="Open Jana2020 result selector",
                    extra_details=traceback.format_exc(),
                )
            )
        finally:
            # "Send to Jana2020" stays available either way: after a normal
            # close it is the manual way back in, and after a failure it is
            # the retry. It is never disabled merely because the automatic
            # open was already attempted.
            self._sync_jana_action_button()

    def _autosolve_candidate_source(self) -> str:
        """Which ResultCandidate.source Autosolve is driving/ranking against
        right now: Option A only ever tracks Superflip's own stream; Option B
        tracks SharpED's stream for both its initial search and its one Map
        Feedback refinement stage. map_quality.py's ranking is never asked to
        compare Superflip against SharpED as competing sources."""
        return "superflip" if self.jana_wizard_context.autosolve_option == "A" else "deblurred"

    def _autosolve_models_available(self) -> bool:
        """Preflight: the exact UNIVERSAL API identifier must be in the live
        catalog that the SharpED requirement check just fetched (no second
        request, no fuzzy match, no fallback to another model)."""
        missing = guided.missing_required_models(self._sharped_catalog_models)
        if not missing:
            self._append_execution_log(
                "[Autosolve] SharpED models resolved from the live catalog: "
                + ", ".join(f"'{name}'" for name in guided.REQUIRED_SHARPED_MODELS) + ".",
                level="DETAIL", subsystem="SharpED",
            )
            return True
        self._show_error_report(ErrorReport(
            category="sharped_model_missing", subsystem="SharpED",
            title="Required SharpED model is unavailable",
            summary="Autosolve requires UNIVERSAL, but it is not in the current live SharpED catalogue.",
            guidance="Check the catalogue again or close this message and return to your workflow.",
            technical_details="Required explicit API model: UNIVERSAL. No fallback was selected.",
            operation="Autosolve preflight",
        ))
        return False

    def _autosolve_on_run_done(self) -> None:
        """Called once per completed cycle block. The initial shared phase
        search is a fixed five cycles and then generates the Predicted
        structure. Later three-cycle refinement/correction blocks extend
        only on a STRICT improvement of the selected source's
        stream (unmodified recommend_best_result via AdaptiveCyclePolicy),
        otherwise returns to Review."""
        state = self._resume_state
        if state is None or self._autosolve_policy is None:
            self._append_execution_log(
                "[Autosolve] No active adaptive-cycle policy; stopping without a handoff.",
                level="ERROR",
                subsystem="Autosolve",
            )
            return
        stage = self._autosolve_stage
        refining = stage == guided.STAGE_REFINEMENT
        if stage == guided.STAGE_SEARCH:
            completed = int(state.completed_cycles)
            self._append_execution_log(
                f"[Autosolve] Initial phase-search block completed at cycle {completed}.",
                subsystem="Autosolve",
            )
            self._autosolve_begin_prediction()
            return
        if refining:
            source = guided.goal_source(self.jana_wizard_context.autosolve_option)
            candidates = (
                self.autosolve_observed_candidates() if source == "superflip" else self.autosolve_predicted_candidates()
            )
        else:
            candidates = self.autosolve_observed_candidates()
        completed = int(state.completed_cycles)
        decision = self._autosolve_policy.on_cycle_completed(completed, candidates)
        if decision == "extend":
            new_limit = self._autosolve_policy.state.current_cycle_limit
            if new_limit > self._autosolve_cycles_maximum():
                self._append_execution_log(
                    f"[Autosolve] Cycle {completed}: the solution improved, but another block would exceed "
                    f"the workflow maximum of {self._autosolve_cycles_maximum()} cycles; stopping automatic cycling.",
                    level="WARNING", subsystem="Autosolve",
                )
                decision = "stop"
            else:
                if refining and self.autosolve_refinement is not None:
                    self._autosolve_prediction_cycles = set(getattr(self, "_autosolve_prediction_cycles", ()))
                    self._autosolve_prediction_cycles.update(range(completed + 1, new_limit + 1))
                    self.autosolve_refinement["block"] = int(self.autosolve_refinement["block"]) + 1
                    self.autosolve_refinement["block_start"] = completed + 1
                    self._append_execution_log(
                        f"[Autosolve] Cycle {completed}: the solution improved -- refinement continues with "
                        f"block {self.autosolve_refinement['block']} (cycles {completed + 1}–{new_limit}), "
                        f"SharpED · {guided.PREDICTION_MODEL}, EDMA "
                        f"{guided.format_sigma(self.autosolve_refinement['threshold_sigma'])}.",
                        subsystem="Autosolve",
                    )
                else:
                    self._append_execution_log(
                        f"[Autosolve] Cycle {completed}: the last block improved the recommendation -- "
                        f"extending the search to cycle {new_limit}.",
                        subsystem="Autosolve",
                    )
                self._set_widget_value_from_string(self.inputs["cycles"], str(new_limit))
                self.continue_run()
                return
        if decision == "stop":
            if refining:
                if self.autosolve_refinement is not None:
                    self.autosolve_timings.setdefault("refinement_run", []).append(
                        time.perf_counter() - float(self.autosolve_refinement.get("started", time.perf_counter()))
                    )
                self._append_execution_log(
                    f"[Autosolve] Cycle {completed}: no strict improvement of the "
                    + ("Charge-flipping solution" if guided.goal_source(self.jana_wizard_context.autosolve_option) == "superflip" else "Structure prediction")
                    + " ranking -- automatic refinement stops.",
                    subsystem="Autosolve",
                )
                self._autosolve_enter_review()
                return
            self._append_execution_log(
                f"[Autosolve] Cycle {completed}: the phase search converged.",
                subsystem="Autosolve",
            )
            self._autosolve_begin_prediction()
            return
        # "continue" means this "done" event does not fall on a decision
        # point (cyc != the policy's current limit). Under Autosolve's own
        # block-based execution this should never actually happen -- a "done"
        # event only ever fires once cfg.cycles (== the policy's limit) is
        # reached -- so this is defensive: do nothing rather than guess.
        self._append_execution_log(
            f"[Autosolve] Cycle {completed} is not an adaptive-cycle decision point "
            f"(expected {self._autosolve_policy.state.current_cycle_limit}); taking no action.",
            level="WARNING",
            subsystem="Autosolve",
        )

    # ===== 2.0.1 guided Autosolve: prediction, Review, refinement =========
    # Every scientific step below is an existing production stage: the
    # ordinary cycle loop, _run_configured_sharped_stage,
    # _run_configured_edma_stage, assess_xplor_map and the unmodified
    # ranking (recommend_best_result / AdaptiveCyclePolicy). See
    # phase_studio/autosolve_review.py for the policy constants.

    def autosolve_observed_candidates(self) -> List[ResultCandidate]:
        return [candidate for candidate in self._result_candidates() if candidate.source == "superflip"]

    def autosolve_predicted_candidates(self) -> List[ResultCandidate]:
        """Completed PREDICTION_MODEL results only: the dedicated predictions
        plus each refinement cycle's own SharpED result. Phase-search SharpED
        output (PHASE_SEARCH_MODEL) is an internal aid, never a Predicted
        structure."""
        # The ordinary Wizard workflow displays every completed SharpED
        # cycle immediately. The progressive-model filter belongs only to
        # adaptive Autosolve, where phase-boost maps are internal search aids.
        if self.jana_wizard_context.launch_mode == "phase_recycling":
            return [candidate for candidate in self._result_candidates() if candidate.source == "deblurred"]
        # Search and prediction now use the same network. Stage provenance,
        # rather than model identity, distinguishes refinement from search.
        progressive_cycles = set(getattr(self, "_autosolve_prediction_cycles", ()))
        candidates = [
            candidate for candidate in self._result_candidates()
            if candidate.source == "deblurred" and int(candidate.cycle) in progressive_cycles
        ]
        taken = {int(candidate.cycle) for candidate in candidates}
        for record in self.autosolve_predictions:
            if int(record.cycle) not in taken:
                candidates.append(record.candidate())
        return sorted(candidates, key=lambda candidate: int(candidate.cycle))

    def _autosolve_best(self, candidates: Sequence[ResultCandidate]) -> Optional[ResultCandidate]:
        return recommend_best_result(self._active_validation_profile(), list(candidates)).recommended_candidate

    def _autosolve_prediction_for_cycle(self, cycle: int) -> Optional[guided.PredictionRecord]:
        return next((record for record in self.autosolve_predictions if int(record.cycle) == int(cycle)), None)

    def _autosolve_panel_for_candidate(self, role: str, candidate: Optional[ResultCandidate]) -> Optional[guided.ReviewPanel]:
        """A ReviewPanel describing `candidate` exactly as recorded by the
        workflow (its own map, its own EDMA structure and the threshold that
        structure was actually extracted at)."""
        if candidate is None:
            return None
        result = self._cycle_result_for_candidate(candidate)
        cfg = self.last_run_config
        if role == guided.ROLE_OBSERVED:
            sigma = getattr(result, "superflip_edma_sigma", None) if result is not None else None
            if sigma is None:
                sigma = float(cfg.plimit_superflip) if cfg is not None else guided.OBSERVED_THRESHOLD_SIGMA
            model = ""
        else:
            record = self._autosolve_prediction_for_cycle(candidate.cycle)
            if record is not None and Path(record.map_path) == Path(candidate.map_path):
                sigma, model = record.edma_sigma, record.sharped_model
            else:
                sigma = getattr(result, "deblur_edma_sigma", None) if result is not None else None
                if sigma is None:
                    sigma = float(cfg.plimit_deblur) if cfg is not None else 2.0
                model = getattr(result, "sharped_model", "") if result is not None else ""
        sigma = guided.normalize_sigma(sigma)
        return guided.ReviewPanel(
            role=role,
            cycle=int(candidate.cycle),
            map_path=Path(candidate.map_path),
            current_cif=Path(candidate.structure_path),
            threshold_sigma=sigma,
            sharped_model=model,
            edma_asu_composition=candidate.edma_asu_composition,
            superflip_initialization=candidate.superflip_initialization,
            reflection_input_provenance=candidate.reflection_input_provenance,
            recorded_cif=Path(candidate.structure_path),
            recorded_sigma=sigma,
        )

    def autosolve_panel_shows_refinement_seed(self, role: str) -> bool:
        """True while `role` is displaying the exact structure/threshold a
        running refinement block was seeded from, because no completed
        candidate from that block exists yet to rank against it. The panel
        gets its "Seed · Cycle N" caption from this, instead of the normal
        "Best · Cycle N" -- see autosolve_display_panel()."""
        refinement = self.autosolve_refinement
        if (
            self._autosolve_stage != guided.STAGE_REFINEMENT or refinement is None
            or refinement.get("role") != role or role not in self.autosolve_panels
        ):
            return False
        candidates = self.autosolve_observed_candidates() if role == guided.ROLE_OBSERVED else self.autosolve_predicted_candidates()
        block_start = int(refinement.get("block_start", 0))
        return not any(int(c.cycle) >= block_start for c in candidates)

    def autosolve_display_panel(self, role: str) -> Optional[guided.ReviewPanel]:
        """What a panel shows right now. In Review: the user-tuned panel.
        Otherwise the best COMPLETED candidate of that role (never an
        in-flight cycle); no Structure prediction exists before the first
        dedicated prediction.

        While a refinement block is running, the panel that SEEDED it keeps
        showing exactly the structure/threshold it was seeded from -- never
        the pre-refinement "best", and never a silent jump back to a
        default-threshold result -- until a genuinely new completed
        candidate from this block actually exists. Once one does, ranking
        takes back over so "Best · Cycle N" is never stale."""
        if self.jana_wizard_context.launch_mode == "phase_recycling":
            candidates = (
                self.autosolve_observed_candidates()
                if role == guided.ROLE_OBSERVED else self.autosolve_predicted_candidates()
            )
            latest = max(candidates, key=lambda candidate: int(candidate.cycle), default=None)
            completed = self._autosolve_panel_for_candidate(role, latest)
            source = guided.ROLE_SOURCE[role]
            live = self._live_structures.get(source)
            if live is None or live.structure_path is None:
                return completed
            if completed is not None and int(completed.cycle) > int(live.cycle):
                return completed
            model = ""
            if role == guided.ROLE_PREDICTED:
                cfg = self.last_run_config
                model = str(cfg.sharped_model) if cfg is not None else ""
            return guided.ReviewPanel(
                role=role, cycle=int(live.cycle), map_path=Path(live.map_path),
                current_cif=Path(live.structure_path), threshold_sigma=float(live.threshold),
                sharped_model=model, recorded_cif=Path(live.structure_path),
                edma_asu_composition=live.edma_asu_composition,
                superflip_initialization=live.superflip_initialization,
                reflection_input_provenance=live.reflection_input_provenance,
                recorded_sigma=float(live.threshold),
            )
        if self.autosolve_in_review() and role in self.autosolve_panels:
            return self.autosolve_panels[role]
        if self.autosolve_panel_shows_refinement_seed(role):
            return self.autosolve_panels[role]
        if role == guided.ROLE_OBSERVED:
            return self._autosolve_panel_for_candidate(role, self._autosolve_best(self.autosolve_observed_candidates()))
        return self._autosolve_panel_for_candidate(role, self._autosolve_best(self.autosolve_predicted_candidates()))

    def autosolve_is_jana(self) -> bool:
        """Jana2020-launched sessions pass results to Jana2020; standalone
        sessions can only save them (and can never enter the handoff)."""
        cfg = self.last_run_config
        return bool(
            self.jana_wizard_context.launched_from_jana_wizard
            and cfg is not None and cfg.jana_inflip is not None
            and getattr(cfg, "jana_return_to_jana", True)
        )

    def autosolve_data_modified(self, cycle: Optional[int] = None) -> bool:
        """True when Map Feedback (powder repartitioning or intensity
        correction) modified the reflection data feeding into `cycle` or any
        earlier cycle -- i.e. that result path used modified data."""
        for result in self.results:
            if cycle is not None and int(result.cycle) > int(cycle):
                continue
            if result.powder_repartition_avg_change_percent is not None or result.intensity_correction_avg_change_percent is not None:
                return True
        return False

    def autosolve_warning_text(self, role: str) -> Optional[str]:
        panel = self.autosolve_display_panel(role)
        modified = self.autosolve_data_modified(panel.cycle if panel is not None else None)
        if role == guided.ROLE_PREDICTED:
            return result_warning_callout_text("deblurred", modified)
        return result_warning_callout_text("superflip", modified)

    def _autosolve_cycles_maximum(self) -> int:
        widget = self.inputs.get("cycles")
        return int(widget.maximum()) if hasattr(widget, "maximum") else 999

    # ----- first prediction -----

    def _autosolve_begin_prediction(self) -> None:
        """The shared phase search converged: generate the Predicted
        structure from the best completed Observed-data (Superflip) map with
        ONE PREDICTION_MODEL SharpED inference, then EDMA."""
        state = self._resume_state
        observed = self._autosolve_best(self.autosolve_observed_candidates())
        if state is None or observed is None:
            self._append_execution_log(
                "[Autosolve] No completed Observed-data result is available; the Predicted "
                "structure cannot be generated.",
                level="ERROR", subsystem="Autosolve",
            )
            self._autosolve_enter_review()
            return
        existing = next(
            (c for c in self.autosolve_predicted_candidates() if int(c.cycle) == int(observed.cycle)), None,
        )
        if existing is not None:
            self._append_execution_log(
                f"[Autosolve] The Structure prediction for Charge-flipping solution Cycle {observed.cycle} already exists; "
                "SharpED is not run again.",
                subsystem="Autosolve",
            )
            self._autosolve_enter_tuning()
            return
        self._autosolve_stage = guided.STAGE_PREDICTING
        self.stop_now.clear()
        self.stop_after_cycle.clear()
        self._set_run_status("Running")
        self._append_execution_log(
            f"[Autosolve] Generating predicted structure · SharpED · {guided.PREDICTION_MODEL} · "
            f"from the best Charge-flipping solution map (Cycle {observed.cycle}).",
            level="STEP", subsystem="Autosolve",
        )
        self.autosolve_activity = "Generating predicted structure…"
        observed_map = Path(observed.map_path)
        cycle = int(observed.cycle)
        run_id = str(state.run_id or self._active_run_id)

        def worker() -> None:
            started = time.perf_counter()
            try:
                record = self._autosolve_run_prediction(state, observed_map, cycle)
                self._queue_run_event(
                    "autosolve_prediction_done",
                    (record, time.perf_counter() - started),
                    run_id,
                )
            except Exception as exc:
                self._queue_run_event(
                    "autosolve_prediction_error",
                    build_error_report(
                        exc, subsystem="SharpED", operation="Generate predicted structure",
                        extra_details=traceback.format_exc(),
                    ),
                    run_id,
                )

        self._autosolve_task = threading.Thread(target=worker, daemon=True)
        self._autosolve_task.start()

    def _autosolve_run_prediction(self, state: PipelineState, observed_map: Path, cycle: int) -> guided.PredictionRecord:
        """Worker-thread body: the same SharpED -> optional symmetry
        averaging -> EDMA -> map-quality sequence a cycle's SharpED stage
        runs, with the model fixed to PREDICTION_MODEL."""
        cfg = state.cfg
        prediction_dir = cfg.work_dir / "autosolve_prediction" / f"from_cycle_{cycle:03d}"
        prediction_dir.mkdir(parents=True, exist_ok=True)
        prefix = f"prediction_cycle_{cycle:03d}"
        output_map = prediction_dir / f"{prefix}_progressive.xplor"
        stages = list(state.progress_stages)
        self._run_configured_sharped_stage(
            state, observed_map, output_map, cycle, stages,
            detail_prefix="predicted structure · ", model=guided.PREDICTION_MODEL,
        )
        prediction_map = output_map
        if cfg.symmetrize_deblurred_map:
            if self.stop_now.is_set():
                raise RuntimeError("Immediate stop requested.")
            prediction_map = run_superflip_symmetrize_map(
                cycle_dir=prediction_dir, prefix=f"{prefix}_symmetrized", ref_ctx=state.ref_ctx,
                input_map=output_map, superflip_exe=cfg.superflip_exe, output_format="xplor",
                voxel=cfg.voxel, searchsymmetry=cfg.searchsymmetry, derivesymmetry=cfg.derivesymmetry,
                log=self.log, stop_event=self.stop_now, profiler=state.performance_profiler,
            )
        if self.stop_now.is_set():
            raise RuntimeError("Immediate stop requested.")
        sigma = guided.normalize_sigma(guided.PREDICTED_THRESHOLD_SIGMA)
        edma_cif = self._run_configured_edma_stage(
            state, prediction_map, prediction_dir / "edma", prefix, sigma,
            map_label="Structure prediction map", explicit_threshold=True,
        )
        quality = self._autosolve_assess_sharped_map(state, prediction_map, edma_cif)
        return guided.PredictionRecord(
            cycle=cycle, observed_map=observed_map, map_path=prediction_map, edma_cif=edma_cif,
            edma_sigma=sigma, sharped_model=guided.PREDICTION_MODEL, quality=quality,
            usable_structure=cif_has_readable_atoms(edma_cif),
            edma_asu_composition=edma_asu_composition_from_cif(edma_cif),
        )

    def _autosolve_assess_sharped_map(self, state: PipelineState, map_path: Path, edma_cif: Path) -> Optional[MapQualityMetrics]:
        """Exactly the per-cycle SharpED-side quality sequence
        (assess_xplor_map -> reference metrics -> holdout metrics); the OMIT
        tie-breaker is unavailable here and is skipped, never zeroed, by the
        ranking."""
        cfg = state.cfg
        metric, match = self._edma_reference_metrics(edma_cif, state.ref_ctx, cfg.merge_distance, True)
        recall = precision = None
        true_positives = false_positives = None
        if match is not None:
            recall, precision, true_positives, false_positives = match
        if state.validation_context is None:
            return None
        quality = assess_xplor_map(map_path, state.validation_context, state.performance_profiler)
        quality = with_reference_metrics(
            quality, precision=precision, recall=recall, rmsd=metric,
            true_positives=true_positives, false_positives=false_positives,
        )
        if state.omit_test_hkls:
            quality = with_holdout_metrics(quality, quality, None)
        return quality

    def _autosolve_on_prediction_done(self, record: guided.PredictionRecord, elapsed: float) -> None:
        self._autosolve_task = None
        self.autosolve_predictions = [r for r in self.autosolve_predictions if int(r.cycle) != int(record.cycle)]
        self.autosolve_predictions.append(record)
        self.autosolve_timings.setdefault("prediction", []).append(float(elapsed))
        self._append_execution_log(
            f"[Autosolve] Structure prediction ready · SharpED · {record.sharped_model} · "
            f"EDMA {guided.format_sigma(record.edma_sigma)} · from Cycle {record.cycle} "
            f"({elapsed:.1f} s).",
            level="SUCCESS", subsystem="Autosolve",
        )
        self._autosolve_enter_tuning()

    def _autosolve_on_prediction_error(self, report: ErrorReport) -> None:
        self._autosolve_task = None
        if self.stop_now.is_set():
            # Stopped on purpose (Cancel, or Pass to Jana2020 which then
            # opens Result Selection over the completed search results).
            self._autosolve_stage = guided.STAGE_PREDICTION_FAILED
            self._finish_cancelled_run_for_request()
            return
        self._autosolve_stage = guided.STAGE_PREDICTION_FAILED
        self.autosolve_activity = ""
        self._set_run_status("Error")
        self._show_error_report(report)
        self._append_execution_log(
            "[Autosolve] The Structure prediction could not be generated. The completed phase "
            "search is kept; Retry generates only the prediction again.",
            level="ERROR", subsystem="Autosolve",
        )

    # ----- Review -----

    def autosolve_in_review(self) -> bool:
        """Initial Predicted-model tuning or the Final Review: waiting for
        the user, no scientific work running."""
        return self._autosolve_stage in guided.REVIEW_STAGES

    def _autosolve_clear_activity(self, text: str = "Review") -> None:
        """Idle review presentation: no stale Cycle/Stage/SharpED line."""
        self._cycle_progress_state = None
        self.autosolve_activity = ""
        self.current_cycle_progress.setRange(0, 1)
        self.current_cycle_progress.setValue(0)
        self.current_cycle_detail.setText(text)
        self.current_cycle_stage_counter.setText("")
        self._apply_superflip_repeat_state(None)
        self._set_overall_progress_text(text)

    def _autosolve_refresh_panels(self) -> None:
        """Each panel shows its role's best COMPLETED candidate; a panel that
        still shows that same result keeps the user's tuned structure and
        threshold (so a refinement seeded at 0.7 sigma is still 0.7 sigma)."""
        for role, candidates in (
            (guided.ROLE_OBSERVED, self.autosolve_observed_candidates()),
            (guided.ROLE_PREDICTED, self.autosolve_predicted_candidates()),
        ):
            best = self._autosolve_best(candidates)
            existing = self.autosolve_panels.get(role)
            if (
                existing is not None and best is not None
                and existing.cycle == int(best.cycle) and Path(existing.map_path) == Path(best.map_path)
            ):
                existing.busy_sigma = None
                continue
            panel = self._autosolve_panel_for_candidate(role, best)
            if panel is None:
                self.autosolve_panels.pop(role, None)
            else:
                self.autosolve_panels[role] = panel

    def _autosolve_enter_waiting_state(self, stage: str) -> None:
        self._autosolve_stage = stage
        self._autosolve_task = None
        self.worker = None
        self.stop_now.clear()
        self.stop_after_cycle.clear()
        self._autosolve_refresh_panels()
        self._set_run_status("Review")
        self._autosolve_clear_activity("Review")

    def _autosolve_enter_tuning(self) -> None:
        """Stage A -- initial Predicted-model tuning. Charge-flipping solution is shown
        read-only for comparison; only the Structure prediction's threshold
        can change; the one decision is "Refine 3 cycles". No handoff yet."""
        self._autosolve_enter_waiting_state(guided.STAGE_TUNING)
        predicted = self.autosolve_panels.get(guided.ROLE_PREDICTED)
        self._append_execution_log(
            "[Autosolve] Predicted-model tuning · "
            + (f"Structure prediction: Cycle {predicted.cycle}, EDMA {guided.format_sigma(predicted.threshold_sigma)}" if predicted else "no Structure prediction")
            + ". Adjust its EDMA threshold, then Refine 3 cycles.",
            level="STEP", subsystem="Autosolve",
        )

    def _autosolve_enter_review(self) -> None:
        """Stage B -- Final Review, after a refinement block: both panels are
        independently tunable and offer all four actions. A deliberate
        waiting state, not COMPLETE/STOPPED/CANCELLED/FAILED."""
        self._autosolve_enter_waiting_state(guided.STAGE_REVIEW)
        observed = self.autosolve_panels.get(guided.ROLE_OBSERVED)
        predicted = self.autosolve_panels.get(guided.ROLE_PREDICTED)
        self._append_execution_log(
            "[Autosolve] Final Review · "
            + (f"Charge-flipping solution: Cycle {observed.cycle}, EDMA {guided.format_sigma(observed.threshold_sigma)}" if observed else "no Charge-flipping solution")
            + " · "
            + (f"Structure prediction: Cycle {predicted.cycle}, EDMA {guided.format_sigma(predicted.threshold_sigma)}" if predicted else "no Structure prediction")
            + ". Adjust the EDMA thresholds, recalculate, or pass a result.",
            level="STEP", subsystem="Autosolve",
        )
        plan, detail = self.autosolve_correction_plan()
        if plan is None and detail:
            self._append_execution_log(
                f"[Autosolve] Measured-data correction is not available: {detail}",
                level="WARNING", subsystem="Autosolve",
            )

    def autosolve_review_busy(self) -> bool:
        return any(panel.busy for panel in self.autosolve_panels.values())

    def autosolve_panel_tunable(self, role: str) -> bool:
        """Final Review: both panels. Initial tuning: the Structure prediction
        only (Charge-flipping solution is comparison-only until the first refinement)."""
        if self._autosolve_stage == guided.STAGE_REVIEW:
            return True
        return self._autosolve_stage == guided.STAGE_TUNING and role == guided.ROLE_PREDICTED

    def autosolve_adjust_threshold(self, role: str, add_atoms: bool) -> bool:
        """+ atoms / - atoms: EDMA ONLY, on the panel's unchanged canonical
        map, one variable step lower / higher (0.2 sigma at/above 0.8, 0.1
        below). Never runs Superflip or SharpED. One EDMA at a time: while
        any panel recalculates, no second recalculation starts."""
        if not self.autosolve_panel_tunable(role) or self.autosolve_review_busy():
            return False
        panel = self.autosolve_panels.get(role)
        state = self._resume_state
        if panel is None or state is None:
            return False
        new_sigma = guided.stepped_threshold(panel.threshold_sigma, add_atoms)
        if new_sigma is None:
            return False
        panel.busy_sigma = new_sigma
        panel.error = ""
        map_path = Path(panel.map_path)
        out_dir = state.cfg.work_dir / "autosolve_review" / f"{role}_cycle_{panel.cycle:03d}"
        prefix = f"{role}_cycle_{panel.cycle:03d}_edma_{new_sigma:.1f}sigma".replace(".", "p")
        self._append_execution_log(
            f"[Autosolve] {panel.title}: recalculating structure at {guided.format_sigma(new_sigma)} "
            "(EDMA only, same map).",
            subsystem="Autosolve",
        )
        activity = f"{panel.title} · EDMA {guided.format_sigma(new_sigma)} · recalculating structure"
        self.autosolve_activity = activity
        self._cycle_progress_state = None
        self.current_cycle_detail.setText(activity)
        self.current_cycle_stage_counter.setText("EDMA")
        self.current_cycle_progress.setRange(0, 0)
        map_label = "Charge-flipping solution (Superflip) map" if role == guided.ROLE_OBSERVED else "Structure prediction map"
        run_id = str(state.run_id or self._active_run_id)

        def worker() -> None:
            started = time.perf_counter()
            try:
                cif = self._run_configured_edma_stage(
                    state, map_path, out_dir, prefix, new_sigma, map_label=map_label, explicit_threshold=True,
                )
                self._queue_run_event(
                    "autosolve_threshold_done",
                    (role, new_sigma, cif, time.perf_counter() - started),
                    run_id,
                )
            except Exception as exc:
                self._queue_run_event(
                    "autosolve_threshold_error",
                    (role, new_sigma, build_error_report(
                        exc, subsystem="EDMA", operation="Recalculate structure at a new threshold",
                        extra_details=traceback.format_exc(),
                    )),
                    run_id,
                )

        threading.Thread(target=worker, daemon=True).start()
        return True

    def _autosolve_on_threshold_done(self, role: str, sigma: float, cif: Path, elapsed: float) -> None:
        panel = self.autosolve_panels.get(role)
        if panel is None or not self.autosolve_in_review():
            return
        previous_m40 = Path(panel.current_cif).with_suffix(".m40")
        previous_model_hash = file_sha256(previous_m40) if previous_m40.is_file() else ""
        panel.busy_sigma = None
        self._autosolve_clear_activity("Review")
        panel.history.append(panel.threshold_sigma)
        panel.threshold_sigma = guided.normalize_sigma(sigma)
        panel.current_cif = Path(cif)
        panel.edma_asu_composition = edma_asu_composition_from_cif(Path(cif))
        self.autosolve_timings.setdefault("threshold_edma", []).append(float(elapsed))
        atoms = parse_cif_atoms(Path(cif))
        self._append_execution_log(
            f"[Autosolve] {panel.title} · EDMA {guided.format_sigma(sigma)} · "
            f"{panel.edma_asu_composition or 'no atoms'} ({len(atoms)} CIF EDMA sites, {elapsed:.1f} s).",
            level="SUCCESS", subsystem="Autosolve",
        )
        m40 = Path(cif).with_suffix(".m40")
        if m40.is_file():
            unchanged = bool(previous_model_hash) and file_sha256(m40) == previous_model_hash
            self._append_execution_log(
                f"[Autosolve] {panel.title} · Jana model {'unchanged' if unchanged else 'updated'} · "
                f"{_m40_model_count(m40)} sites · composition-constrained EDMA selection",
                subsystem="EDMA",
            )

    def _autosolve_on_threshold_error(self, role: str, sigma: float, report: ErrorReport) -> None:
        panel = self.autosolve_panels.get(role)
        if panel is not None:
            panel.busy_sigma = None
        if not self.autosolve_in_review():
            return  # cancelled while EDMA ran: nothing to report
        self._autosolve_clear_activity("Review")
        if panel is not None:
            panel.error = f"EDMA at {guided.format_sigma(sigma)} failed; the previous structure is kept."
        self._show_error_report(report)

    # ----- Recalculate: model-seeded three-cycle refinement -----

    def autosolve_recalculate(self, role: str) -> bool:
        """Use THIS panel's current structure, at THIS panel's current
        threshold, as the Superflip initial model for a new block of
        REFINEMENT_BLOCK_CYCLES cycles; every SharpED call in refinement uses
        PREDICTION_MODEL and every structure fed forward is extracted at
        the captured threshold."""
        if not self.autosolve_panel_tunable(role) or self.autosolve_review_busy():
            return False
        panel = self.autosolve_panels.get(role)
        state = self._resume_state
        if panel is None or state is None:
            return False
        action_label = guided.REFINE_LABEL if self._autosolve_stage == guided.STAGE_TUNING else guided.RECALCULATE_LABEL
        seed = Path(panel.current_cif)
        if not cif_has_readable_atoms(seed):
            self._show_error_report(build_validation_report([
                f"The {panel.title} structure at {guided.format_sigma(panel.threshold_sigma)} has no atoms, "
                "so it cannot be used as the Superflip initial model. Choose + atoms first."
            ]))
            return False
        completed = int(state.completed_cycles)
        new_limit = completed + guided.REFINEMENT_BLOCK_CYCLES
        if new_limit > self._autosolve_cycles_maximum():
            self._show_error_report(build_validation_report([
                f"Refinement would exceed the workflow maximum of {self._autosolve_cycles_maximum()} cycles."
            ]))
            return False
        cfg = state.cfg
        threshold = guided.normalize_sigma(panel.threshold_sigma)
        cfg.sharped_model = guided.PREDICTION_MODEL
        self._autosolve_prediction_cycles = set(getattr(self, "_autosolve_prediction_cycles", ()))
        self._autosolve_prediction_cycles.update(range(completed + 1, new_limit + 1))
        cfg.plimit_deblur = threshold
        cfg.run_sharped = True
        cfg.run_edma_deblurred = True
        seed_note = f"{panel.title} · Cycle {panel.cycle} · EDMA {guided.format_sigma(threshold)}"
        state.current_model = seed
        state.current_model_metric = None
        state.auto_reference_cif = seed
        state.ordinary_cycle_checkpoint = None
        state.refinement_seed_note = seed_note
        self.autosolve_refinement = {
            "role": role, "seed": seed, "threshold_sigma": threshold, "seed_note": seed_note,
            "cycle": panel.cycle, "block": 1, "block_start": completed + 1, "started": time.perf_counter(),
        }
        self._autosolve_stage = guided.STAGE_REFINEMENT
        self._autosolve_policy = AdaptiveCyclePolicy(
            self._active_validation_profile(), initial=new_limit, block_size=guided.REFINEMENT_BLOCK_CYCLES,
        )
        self._append_execution_log(
            f"[Autosolve] {action_label} · {panel.title} Cycle {panel.cycle} at "
            f"{guided.format_sigma(threshold)} is the Superflip initial model · refinement block 1 "
            f"(cycles {completed + 1}–{new_limit}) · SharpED · {guided.PREDICTION_MODEL} · "
            f"EDMA {guided.format_sigma(threshold)}.",
            level="STEP", subsystem="Autosolve",
        )
        self._set_widget_value_from_string(self.inputs["cycles"], str(new_limit))
        self.continue_run()
        return True

    def autosolve_refinement_cycle_in_block(self) -> Optional[Tuple[int, int, int]]:
        """(cycle within the current block, block size, block number) for the
        running refinement cycle, from the authoritative progress state."""
        info = getattr(self, "autosolve_refinement", None)
        progress_state = getattr(self, "_cycle_progress_state", None)
        if self._autosolve_stage != guided.STAGE_REFINEMENT or not info or progress_state is None:
            return None
        block_start = int(info["block_start"])
        index = int(progress_state.cycle_index) - block_start + 1
        if not 1 <= index <= guided.REFINEMENT_BLOCK_CYCLES:
            return None
        return index, guided.REFINEMENT_BLOCK_CYCLES, int(info["block"])

    # ----- Pass to Jana2020 / Save map and model -----

    def _autosolve_result_for_panel(self, panel: guided.ReviewPanel) -> Optional[CycleResult]:
        """The CycleResult the established handoff/export authority receives:
        the panel's own cycle, its canonical map and the structure at the
        CURRENT threshold (never the stale default-threshold model)."""
        base = next((result for result in self.results if int(result.cycle) == int(panel.cycle)), None)
        if base is None:
            return None
        if panel.role == guided.ROLE_OBSERVED:
            return replace(base, superflip_edma_cif=Path(panel.current_cif), superflip_edma_sigma=panel.threshold_sigma)
        record = self._autosolve_prediction_for_cycle(panel.cycle)
        if record is not None and Path(record.map_path) == Path(panel.map_path):
            return replace(
                base, deblur_map=Path(record.map_path), deblur_edma_cif=Path(panel.current_cif),
                deblur_quality=record.quality, sharped_model=record.sharped_model,
                deblur_edma_sigma=panel.threshold_sigma,
            )
        return replace(base, deblur_edma_cif=Path(panel.current_cif), deblur_edma_sigma=panel.threshold_sigma)

    def _write_autosolve_provenance(self, panel: guided.ReviewPanel, action: str) -> Path:
        cfg = self.last_run_config
        path = Path(cfg.work_dir if cfg is not None else Path.cwd()) / "autosolve_result_provenance.json"
        entry = {
            "action": action,
            "role": panel.role,
            "title": panel.title,
            "source": panel.source,
            "cycle": int(panel.cycle),
            "map": str(panel.map_path),
            "map_sha256": guided.file_sha256(Path(panel.map_path)),
            "model": str(panel.current_cif),
            "edma_threshold_sigma": float(panel.threshold_sigma),
            "recorded_threshold_sigma": panel.recorded_sigma,
            "sharped_model": panel.sharped_model if panel.role == guided.ROLE_PREDICTED else "",
            "phase_search_sharped_model": guided.PHASE_SEARCH_MODEL,
            "measured_data_modified": self.autosolve_data_modified(panel.cycle),
            "phase_studio_version": __version__,
        }
        history = []
        if path.is_file():
            try:
                history = json.loads(path.read_text(encoding="utf-8")).get("entries", [])
            except Exception:
                history = []
        history.append(entry)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"entries": history}, indent=2), encoding="utf-8")
        return path

    def _write_autosolve_correction_provenance(self, kind: str, start_cycle: int) -> Path:
        cfg = self.last_run_config
        path = Path(cfg.work_dir if cfg is not None else Path.cwd()) / "autosolve_result_provenance.json"
        history = []
        if path.is_file():
            try:
                history = json.loads(path.read_text(encoding="utf-8")).get("entries", [])
            except Exception:
                history = []
        state = self._resume_state
        original = None
        if state is not None and getattr(state, "observed_hkls", None):
            original = str(next(iter(state.observed_hkls.values())))
        history.append({
            "action": "measured_data_correction",
            "correction": guided.CORRECTION_LABELS[kind],
            "routine": "powder overlap repartitioning" if kind == guided.CORRECTION_POWDER else "weak/suspect-intensity correction",
            "from_cycle": int(start_cycle),
            "measured_reflection_data_modified": True,
            "original_measured_data": original,
            "phase_studio_version": __version__,
        })
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"entries": history}, indent=2), encoding="utf-8")
        return path

    def autosolve_pass_panel(self, role: str) -> bool:
        """Pass to Jana2020 (Jana session) or Save map and model (standalone)
        for THIS panel's current map/model pairing, through the established
        handoff/export authority. SharpED is never rerun here."""
        panel = self.autosolve_panels.get(role)
        if (
            self._autosolve_stage != guided.STAGE_REVIEW or panel is None or panel.busy
            or self.autosolve_handoff_state in {"stopping", "selecting", "handing_off"}
        ):
            return False
        result = self._autosolve_result_for_panel(panel)
        if result is None:
            return False
        structure_ok = cif_has_readable_atoms(Path(panel.current_cif))
        candidate = ResultCandidate(
            cycle=int(panel.cycle), source=panel.source, map_path=str(panel.map_path),
            structure_path=str(panel.current_cif),
            metrics=(result.superflip_quality if panel.role == guided.ROLE_OBSERVED else result.deblur_quality) or MapQualityMetrics(),
            usable_map=Path(panel.map_path).is_file(), usable_structure=structure_ok,
            edma_sigma=float(panel.threshold_sigma), sharped_model=panel.sharped_model,
            edma_asu_composition=panel.edma_asu_composition,
        )
        if not self.autosolve_is_jana():
            saved = self._export_selected_candidate(candidate)
            if saved:
                self._write_autosolve_provenance(panel, "save")
            return saved
        # Promote the panel's threshold-specific EDMA structure to the
        # canonical candidate pairing, then converge on the shared Result
        # Selection authority. No SharpED or EDMA recomputation occurs here.
        if panel.source == "superflip":
            result.superflip_edma_cif = Path(panel.current_cif)
            result.superflip_edma_sigma = float(panel.threshold_sigma)
        else:
            result.deblur_edma_cif = Path(panel.current_cif)
            result.deblur_edma_sigma = float(panel.threshold_sigma)
            result.sharped_model = panel.sharped_model or result.sharped_model
        self._write_autosolve_provenance(panel, "open_result_selection")
        self._autosolve_handoff(panel.source)
        return True

    # ----- measured-data correction (existing Map Feedback algorithms) -----

    def autosolve_correction_plan(self) -> Tuple[Optional[str], str]:
        """Which existing measured-data correction applies to this dataset,
        using the established eligibility logic (FWHM data with a resolvable
        wavelength -> Powder repartitioning; non-FWHM data -> suspect/weak
        intensity correction; FWHM data without a wavelength -> neither)."""
        state = self._resume_state
        if state is None:
            return None, ""
        cfg = state.cfg
        data_mode = self._resolve_configured_data_mode(cfg)
        if reflection_mode_has_fwhm(data_mode):
            m90_path = resolve_jana_m90_path(cfg.jana_inflip)
            wavelength, wavelength_source = resolve_powder_wavelength(
                0.0, cfg.jana_inflip, cfg.reference_cif, jana_m90_path=m90_path,
            )
            if wavelength <= 0:
                return None, (
                    "The reflection data carries FWHM values (powder data), but no radiation "
                    "wavelength could be resolved from a Jana2020 .m90 file, the .inflip file, or "
                    "the reference CIF, so powder overlap repartitioning cannot run."
                )
            return guided.CORRECTION_POWDER, f"wavelength {wavelength:g} Å from {wavelength_source}"
        return guided.CORRECTION_INTENSITY, ""

    def _autosolve_apply_correction(self, kind: str, start_cycle: int) -> None:
        """The established Autosolve Map Feedback configuration, unchanged."""
        cfg = self._resume_state.cfg
        if kind == guided.CORRECTION_POWDER:
            m90_path = resolve_jana_m90_path(cfg.jana_inflip)
            wavelength, _source = resolve_powder_wavelength(
                0.0, cfg.jana_inflip, cfg.reference_cif, jana_m90_path=m90_path,
            )
            cfg.redistribute_overlaps = True
            cfg.powder_redistribution_from_cycle = start_cycle
            cfg.powder_wavelength = wavelength
            cfg.powder_separation_factor = 0.200
            cfg.powder_redistribution_mix = 0.3
        else:
            cfg.map_feedback_intensity_enabled = True
            cfg.map_feedback_intensity_from_cycle = start_cycle
            cfg.map_feedback_intensity_max_i_over_sigma = 3.0
            cfg.map_feedback_intensity_damping = 0.100

    def autosolve_request_correction(self, kind: str) -> bool:
        """User-initiated only: run the existing automatic correction exactly
        as the established Autosolve Map Feedback stage does (a fresh adaptive
        search stage on the corrected data from the next cycle), then
        generate a new Structure prediction and return to Review."""
        plan, _detail = self.autosolve_correction_plan()
        state = self._resume_state
        if (
            self._autosolve_stage != guided.STAGE_REVIEW or self.autosolve_review_busy()
            or plan is None or plan != kind or state is None
        ):
            return False
        completed = int(state.completed_cycles)
        new_limit = completed + guided.REFINEMENT_BLOCK_CYCLES
        if new_limit > self._autosolve_cycles_maximum():
            self._show_error_report(build_validation_report([
                f"Data correction would exceed the workflow maximum of {self._autosolve_cycles_maximum()} cycles."
            ]))
            return False
        self._autosolve_apply_correction(kind, completed + 1)
        self._write_autosolve_correction_provenance(kind, completed + 1)
        cfg = state.cfg
        cfg.sharped_model = guided.PHASE_SEARCH_MODEL
        cfg.plimit_deblur = self._autosolve_search_deblur_sigma
        self._autosolve_stage = guided.STAGE_CORRECTION
        self._autosolve_policy = AdaptiveCyclePolicy(
            self._active_validation_profile(), initial=new_limit,
            block_size=guided.REFINEMENT_BLOCK_CYCLES,
        )
        self._append_execution_log(
            f"[Autosolve] {guided.CORRECTION_LABELS[kind]} requested · the measured reflection data "
            f"supplied to cycle {completed + 1} onward are modified by the existing Map Feedback "
            "correction; the phase search continues on the corrected data.",
            level="STEP", subsystem="Autosolve",
        )
        self._set_widget_value_from_string(self.inputs["cycles"], str(new_limit))
        self.continue_run()
        return True

    def autosolve_cancel(self) -> None:
        """Cancel: stop running work immediately (the established mechanism);
        from Review, where nothing runs, end the session without passing a
        result. Either way the terminal state is CANCELLED."""
        worker_alive = self.worker is not None and self.worker.is_alive()
        task_alive = self._autosolve_task is not None and self._autosolve_task.is_alive()
        if worker_alive or task_alive or str(getattr(self, "_run_status", "")).upper() == "RUNNING":
            self.request_immediate_stop()
            return
        self.stop_now.set()
        self._autosolve_stage = "cancelled"
        self._finish_cancelled_run()

    def autosolve_retry(self) -> bool:
        """Retry after a failure, reusing every completed stage: a failed
        prediction reruns only the prediction; a failed cycle resumes via
        the established Continue checkpoints."""
        if self._autosolve_stage == guided.STAGE_PREDICTION_FAILED:
            self._autosolve_begin_prediction()
            return True
        if self._resume_state is not None and str(getattr(self, "_run_status", "")).upper() == "ERROR":
            self.continue_run()
            return True
        return False

    def _autosolve_handoff(self, source: str) -> None:
        """Autosolve's end point (search finished, or Pass to Jana2020
        pressed): open the SAME shared Result Selection every other Jana2020
        handoff uses, with this goal's source active and each source's
        recommended COMPLETED cycle preselected. The user may switch source
        or override the cycle; only "Pass to Jana2020" in the selector hands
        off, through the selector's own canonical map/model pairing. No
        second selection logic, and never an in-flight cycle (only recorded
        CycleResults become candidates)."""
        if not self._result_candidates() or self.last_run_config is None:
            self.autosolve_handoff_state = "declined"
            self._append_execution_log(
                "[Autosolve] No completed result is available yet. Nothing was passed to Jana2020.",
                level="ERROR",
                subsystem="Autosolve",
            )
            return
        profile = self._active_validation_profile()
        recommended = recommend_best_result(
            profile, [c for c in self._result_candidates() if c.source == source]
        ).recommended_candidate
        summary = (
            f"recommended {result_source_title(source)} result: Cycle {recommended.cycle}"
            if recommended is not None else f"no recommended {result_source_title(source)} result"
        )
        self._append_execution_log(
            f"[Autosolve] Opening Result Selection ({summary}). Choose the result to pass to Jana2020.",
            level="STEP",
            subsystem="Autosolve",
        )
        self.autosolve_handoff_state = "selecting"
        QTimer.singleShot(0, lambda: self._autosolve_open_result_selection(source))

    def _autosolve_open_result_selection(self, source: str) -> None:
        started = self.open_result_selector(
            "jana", dialog_parent=self.autosolve_dialog_parent, initial_source=source,
        )
        self._handoff_pending = False
        self._handoff_candidate_snapshot = None
        self._handoff_results_snapshot = None
        self._handoff_initial_source = None
        self._handoff_selector_scheduled = False
        self._sync_jana_action_button()
        if started:
            self.autosolve_handoff_state = "handing_off"
            return
        self.autosolve_handoff_state = "declined"
        self._append_execution_log(
            "[Autosolve] Result Selection closed without passing a result to Jana2020. "
            "The completed results remain available; use Pass to Jana2020 to choose again.",
            subsystem="Autosolve",
        )

    def _result_candidates(self, *, include_unavailable: bool = False) -> List[ResultCandidate]:
        if self._handoff_pending and self._handoff_candidate_snapshot is not None:
            return list(self._handoff_candidate_snapshot)
        return result_candidates_from_results(self.results, include_unavailable=include_unavailable)

    def _active_validation_profile(self) -> ValidationProfile:
        for result in self.results:
            try:
                return ValidationProfile(result.validation_profile)
            except (TypeError, ValueError):
                continue
        return self.current_validation_profile

    @staticmethod
    def _review_candidate_key(candidate: ResultCandidate) -> tuple:
        return (
            str(candidate.run_id), str(candidate.source), int(candidate.cycle),
            str(candidate.map_sha256 or candidate.map_path),
        )

    @classmethod
    def _review_cache_key(cls, candidate: ResultCandidate, threshold: float) -> tuple:
        return cls._review_candidate_key(candidate) + (round(float(threshold), 6),)

    def request_result_candidate_retune(
        self, candidate: ResultCandidate, add_atoms: bool,
        callback: Callable[[Optional[ResultCandidate], Optional[ErrorReport], ReviewRequest], None],
    ) -> Optional[ReviewRequest]:
        """Queue an isolated EDMA-only review and return to Qt immediately."""
        state = self._resume_state
        if state is None or candidate.edma_sigma is None or not candidate.edma_enabled:
            return None
        key = self._review_candidate_key(candidate)
        base_sigma = self.review_edma_executor.requested_threshold(
            key, float(candidate.edma_sigma),
        )
        new_sigma = guided.stepped_threshold(base_sigma, add_atoms)
        if new_sigma is None:
            return None
        self.review_edma_executor.remember(
            self._review_cache_key(candidate, float(candidate.edma_sigma)), candidate,
        )
        run_id = str(candidate.run_id or state.run_id or self._active_run_id)
        source_tag = "superflip" if candidate.source == "superflip" else "sharped"
        request_tag = f"{time.time_ns()}-{os.getpid()}"
        output_dir = (
            state.cfg.work_dir / "review_edma" / (run_id or "legacy")
            / f"{source_tag}_cycle_{candidate.cycle:03d}"
            / f"request_{request_tag}_{float(new_sigma):.2f}sigma".replace(".", "p")
        )
        prefix = (
            f"review_{source_tag}_cycle_{candidate.cycle:03d}_{request_tag}_"
            f"{float(new_sigma):.2f}sigma"
        ).replace(".", "p")
        family = "Charge-flipping solution" if candidate.source == "superflip" else "Structure prediction"
        live_job = (
            self._new_structure_job(
                state, candidate.source, int(candidate.cycle), Path(candidate.map_path), float(new_sigma),
            )
            if hasattr(self, "_new_structure_job") else None
        )
        self._append_execution_log(
            f"{family} · EDMA recalculation started · {float(new_sigma):.2f} sigma",
            subsystem="EDMA",
        )
        self._append_execution_log(
            f"Review EDMA request {request_tag} · run {run_id} · candidate {candidate.candidate_id} · "
            f"source map SHA-256 {candidate.map_sha256 or 'unavailable'} · threshold {float(new_sigma):.6f} · "
            f"input {Path(candidate.map_path)} · output directory {output_dir}",
            level="DETAIL", subsystem="EDMA",
        )

        def job(review_stop: threading.Event) -> ResultCandidate:
            self._run_event_context.run_id = run_id
            try:
                if live_job is not None:
                    self._structure_job_status(live_job, "running")
                cif = self._run_configured_edma_stage(
                    state, Path(candidate.map_path), output_dir, prefix, float(new_sigma),
                    map_label=(
                        "Charge-flipping solution map" if candidate.source == "superflip"
                        else "Structure prediction map"
                    ),
                    explicit_threshold=True,
                    stop_event=review_stop,
                )
                canonical_cif = promote_threshold_structure(
                    Path(cif), output_dir, candidate.source, candidate.cycle, float(new_sigma),
                )
                return seal_result_candidate(replace(
                    candidate, structure_path=str(canonical_cif),
                    edma_sigma=float(new_sigma), usable_structure=True,
                ))
            except BaseException:
                # Completed review artifacts are the cache.  Failed/cancelled
                # request workspaces contain no handoff-capable result.
                shutil.rmtree(output_dir, ignore_errors=True)
                raise

        def completed(outcome: ReviewOutcome) -> None:
            request = outcome.request
            if request.run_id and request.run_id != str(self._active_run_id):
                return
            if outcome.error is not None:
                if live_job is not None:
                    self._structure_job_status(live_job, "failed")
                report = build_error_report(
                    outcome.error, subsystem="EDMA",
                    operation="Adjust selected result threshold",
                )
                self._append_execution_log(
                    "[Results] EDMA threshold update failed; the previous completed structure was retained.",
                    level="ERROR", subsystem="EDMA",
                )
                self._append_execution_log(
                    f"Review EDMA request {request_tag} failed after {outcome.elapsed:.3f} s · "
                    f"candidate {request.candidate_id} · threshold {request.threshold:.6f} · "
                    f"input {Path(candidate.map_path)} · output directory {output_dir} · {report.diagnostic_block()}",
                    level="DETAIL", subsystem="EDMA",
                )
                callback(None, report, request)
                return
            updated = outcome.value if isinstance(outcome.value, ResultCandidate) else None
            if updated is None:
                return
            result = self._cycle_result_for_candidate(candidate)
            if result is None or (
                updated.run_id and result.run_id and str(updated.run_id) != str(result.run_id)
            ):
                return
            canonical_cif = Path(updated.structure_path)
            if live_job is not None:
                self._structure_job_status(live_job, "complete", canonical_cif)
            if updated.source == "superflip":
                result.superflip_edma_cif = canonical_cif
                result.superflip_edma_sigma = float(updated.edma_sigma)
            else:
                result.deblur_edma_cif = canonical_cif
                result.deblur_edma_sigma = float(updated.edma_sigma)
            cache_note = " (cached)" if outcome.cache_hit else ""
            try:
                detected_sites = len(parse_cif_atoms(canonical_cif))
            except Exception:
                detected_sites = 0
            self._append_execution_log(
                f"{family} · EDMA updated · {detected_sites:,} detected sites · "
                f"{float(updated.edma_sigma):.2f} sigma{cache_note}",
                subsystem="EDMA",
            )
            unchanged_model = bool(candidate.jana_model_sha256) and (
                updated.jana_model_sha256 == candidate.jana_model_sha256
            )
            self._append_execution_log(
                f"{family} · Jana model {'unchanged' if unchanged_model else 'updated'} · "
                f"{updated.jana_model_site_count if updated.jana_model_site_count is not None else 'unavailable'} sites · "
                "composition-constrained EDMA selection",
                subsystem="EDMA",
            )
            self._append_execution_log(
                f"Review EDMA request {request_tag} complete · run {request.run_id} · "
                f"candidate {request.candidate_id} · source map SHA-256 {candidate.map_sha256 or 'unavailable'} · "
                f"threshold {request.threshold:.6f} · input {Path(candidate.map_path)} · "
                f"output {canonical_cif} · resulting SHA-256 {updated.structure_sha256 or 'unavailable'} · "
                f"duration {outcome.elapsed:.3f} s",
                level="DETAIL", subsystem="EDMA",
            )
            callback(updated, None, request)

        return self.review_edma_executor.request(
            key=key,
            cache_key=self._review_cache_key(candidate, float(new_sigma)),
            run_id=run_id,
            candidate_id=candidate.candidate_id,
            source=candidate.source,
            cycle=int(candidate.cycle),
            threshold=float(new_sigma),
            job=job,
            callback=completed,
        )

    def _retune_result_candidate(
        self, candidate: ResultCandidate, add_atoms: bool,
    ) -> Optional[ResultCandidate]:
        """Re-run EDMA only for one completed selector candidate.

        The canonical map never changes and neither Superflip nor SharpED is
        called.  The threshold-specific CIF is promoted onto the matching
        CycleResult so preview, export, and Jana handoff all use the same
        structure object.
        """
        state = self._resume_state
        if state is None or candidate.edma_sigma is None:
            return None
        new_sigma = guided.stepped_threshold(candidate.edma_sigma, add_atoms)
        if new_sigma is None:
            return None
        source_tag = "superflip" if candidate.source == "superflip" else "sharped"
        prefix = f"selector_{source_tag}_cycle_{candidate.cycle:03d}_{new_sigma:.2f}sigma".replace(".", "p")
        output_dir = state.cfg.work_dir / "result_selection_edma"
        try:
            cif = self._run_configured_edma_stage(
                state,
                Path(candidate.map_path),
                output_dir,
                prefix,
                new_sigma,
                map_label=("Charge-flipping solution map" if candidate.source == "superflip" else "Structure prediction map"),
                explicit_threshold=True,
            )
        except Exception as exc:
            self._show_error_report(build_error_report(
                exc, subsystem="EDMA", operation="Adjust selected result threshold",
            ))
            return None
        result = self._cycle_result_for_candidate(candidate)
        if result is None:
            return None
        try:
            canonical_cif = promote_threshold_structure(
                Path(cif), output_dir, candidate.source, candidate.cycle, new_sigma,
            )
        except Exception as exc:
            self._show_error_report(build_error_report(
                exc, subsystem="EDMA", operation="Promote selected threshold result",
            ))
            return None
        if candidate.source == "superflip":
            result.superflip_edma_cif = canonical_cif
            result.superflip_edma_sigma = float(new_sigma)
        else:
            result.deblur_edma_cif = canonical_cif
            result.deblur_edma_sigma = float(new_sigma)
        self._append_execution_log(
            f"[Results] {result_source_title(candidate.source)} Cycle {candidate.cycle} "
            f"recalculated by EDMA at {guided.format_sigma(new_sigma)}.",
            subsystem="Results",
        )
        return seal_result_candidate(replace(
            candidate, structure_path=str(canonical_cif), edma_sigma=float(new_sigma),
            usable_structure=True,
        ))

    def open_jana_result_selector(self, source_mode: str = "switchable", initial_source: str = "") -> None:
        """Compatibility entry point for the unified profile-aware selector."""
        self.open_result_selector(
            context="jana", dialog_parent=self.autosolve_dialog_parent,
            initial_source=initial_source or None,
        )

    def _cycle_result_for_candidate(self, candidate: ResultCandidate) -> Optional[CycleResult]:
        source = self._handoff_results_snapshot if self._handoff_pending and self._handoff_results_snapshot is not None else self.results
        return next((
            result for result in source
            if int(result.cycle) == int(candidate.cycle)
            and (
                not candidate.run_id or not result.run_id
                or str(result.run_id) == str(candidate.run_id)
            )
        ), None)

    def _export_selected_candidate(self, candidate: ResultCandidate) -> bool:
        destination_text = QFileDialog.getExistingDirectory(
            self,
            "Save selected result",
            str(self.last_run_config.work_dir if self.last_run_config is not None else Path.home()),
        )
        if not destination_text:
            return False
        destination = Path(destination_text)
        sources = [Path(candidate.map_path)]
        if candidate.usable_structure:
            sources.append(Path(candidate.structure_path))
        targets = [destination / source.name for source in sources]
        existing = [target for target in targets if target.exists()]
        if existing:
            names = "\n".join(target.name for target in existing)
            answer = QMessageBox.question(
                self,
                "Replace existing result files?",
                "The following files already exist:\n\n" + names + "\n\nReplace them?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return False
        destination.mkdir(parents=True, exist_ok=True)
        for source, target in zip(sources, targets):
            shutil.copy2(source, target)
        self._append_execution_log(
            f"[Results] Saved {candidate.label} · {len(targets)} file(s) · {destination}",
            level="SUCCESS",
            subsystem="Results",
        )
        return True

    def _initial_result_source(
        self, cfg: Optional[RunConfig], superflip_available: bool, sharped_available: bool,
    ) -> str:
        """Prefer completed SharpED predictions for combined runs.

        Explicit Autosolve callers can still supply their goal family. This
        presentation choice never changes either family's scientific ranking.
        """
        preferred = "superflip"
        wizard_context = self.jana_wizard_context
        if cfg is not None and cfg.run_sharped and sharped_available:
            preferred = "deblurred"
        elif wizard_context.launch_mode == "phase_recycling" and wizard_context.wizard_map_source in ("superflip", "deblurred"):
            # The Wizard's "Map used for Jana2020 handoff" choice. It never
            # changes the feed-forward map (always SharpED, see
            # build_jana_handoff_import); it only decides which source
            # Result Selection opens on.
            preferred = wizard_context.wizard_map_source
        elif cfg is not None:
            mode = normalize_modelfile_source(str(getattr(cfg, "modelfile_source", "")))
            if mode in ("deblurred_xplor", "deblurred_edma_cif"):
                preferred = "deblurred"
        if preferred == "deblurred" and not sharped_available:
            return "superflip"
        if preferred == "superflip" and not superflip_available:
            return "deblurred"
        return preferred

    def open_result_selector(
        self, context: str = "standalone", *, dialog_parent: Optional[QWidget] = None,
        initial_source: Optional[str] = None,
    ) -> bool:
        """Open the shared profile-aware selector for Jana2020 or standalone.
        Returns True when the user chose a result (export or handoff started),
        False when nothing was selected. `initial_source` lets a caller whose
        goal defines the primary source (Autosolve) open on that tab;
        `dialog_parent` lets a visible front end own the dialog."""
        requested_source = initial_source
        candidates = self._result_candidates(include_unavailable=True)
        if not candidates:
            self._show_error_report(build_error_report(
                RuntimeError("No completed map is available for result selection."),
                subsystem="Results",
                operation="Open result selector",
                severity="warning",
            ))
            return False
        is_jana = str(context).strip().lower() == "jana"
        cfg = self.last_run_config
        if is_jana and (cfg is None or cfg.jana_inflip is None):
            self._show_error_report(build_error_report(
                RuntimeError("Jana2020 handoff requires a run started from a Jana2020 .inflip file."),
                subsystem="Jana2020",
                operation="Jana2020 handoff",
                severity="warning",
            ))
            return False

        profile = self._active_validation_profile()
        definition = profile_definition(profile)
        superflip_candidates = [c for c in candidates if c.source == "superflip"]
        sharped_candidates = [c for c in candidates if c.source == "deblurred"]
        superflip_recommendation = recommend_best_result(profile, superflip_candidates)
        sharped_recommendation = recommend_best_result(profile, sharped_candidates)

        # SharpED disabled for this run still leaves a "deblurred" map/quality
        # on each CycleResult -- a byte-for-byte copy of the Superflip map,
        # kept only for pipeline uniformity. Candidates built from it are not
        # a real SharpED result, so cfg.run_sharped gates the tab on top of
        # (not instead of) candidate presence.
        superflip_tab_available = bool(superflip_candidates)
        sharped_tab_available = bool(sharped_candidates) and (cfg is None or cfg.run_sharped)
        initial_source = self._initial_result_source(cfg, superflip_tab_available, sharped_tab_available)
        if (requested_source == "superflip" and superflip_tab_available) or (
            requested_source == "deblurred" and sharped_tab_available
        ):
            initial_source = requested_source
        map_feedback_intensity_enabled = bool(cfg.map_feedback_intensity_enabled) if cfg is not None else False

        self.result_recommendation = (
            superflip_recommendation if initial_source == "superflip" else sharped_recommendation
        )

        preview_host = create_result_preview_host(
            self, self.structure_cell, self.structure_elev, self.structure_azim,
        )
        dialog = ResultSelectionDialog(
            dialog_parent if dialog_parent is not None else self,
            superflip_candidates,
            sharped_candidates,
            profile,
            definition,
            superflip_recommendation,
            sharped_recommendation,
            superflip_tab_available=superflip_tab_available,
            sharped_tab_available=sharped_tab_available,
            initial_source=initial_source,
            map_feedback_intensity_enabled=map_feedback_intensity_enabled,
            jana_context=is_jana,
            preview_host=preview_host,
            parse_structure=self._safe_parse_structure,
            reference_atoms=self.reference_atoms_for_plot,
            source_title=result_source_title,
            authoritative_composition=(
                project_composition_for_metadata(cfg.crystal_metadata).value if cfg is not None else ""
            ),
            authoritative_composition_label=crystal_metadata_composition_label(
                cfg.crystal_metadata if cfg is not None else None
            ),
            adjust_threshold_async=self.request_result_candidate_retune,
        )
        # A run owns its explicit selection; QSettings and a previous run do not.
        session_key = (str(getattr(cfg, "run_id", "")),
                       str(getattr(cfg, "work_dir", "")),
                       () if getattr(cfg, "run_id", "") else
                       tuple(sorted((c.run_id, c.source, c.cycle, c.map_sha256, c.map_path)
                                    for c in candidates)))
        previous_session = getattr(self, "_result_selection_session", None)
        session_matches = previous_session is not None and previous_session[0] == session_key
        restored = session_matches and bool(previous_session[1].get("source") or previous_session[1].get("candidates"))
        if session_matches:
            dialog.restore_selection(previous_session[1])
        if cfg is not None and cfg.run_sharped:
            dialog.set_sharped_expected(automatic=not restored and requested_source is None
                and not (session_matches and previous_session[1].get("fallback_shown")))

        # Keep the completion dialog owned by, and visibly above, whichever
        # Phase Studio front end initiated it.  Queue activation until exec()
        # has created and shown the native child window.
        from phase_studio.ui_branding import activate_owned_dialog
        diagnostic = getattr(self, "_run_diagnostic_log", None)
        activation_log = (
            lambda message: diagnostic.write(ExecutionLogRecord(
                message, "DETAIL", "Window activation", "DIAGNOSTIC",
            ))
            if diagnostic is not None else None
        )
        activate_owned_dialog(dialog, diagnostic_log=activation_log)

        self._append_execution_log(
            f"[Results] Result selector opened · {definition.assessment_label}",
            level="DETAIL", subsystem="Results",
        )
        accepted = dialog.exec() == QDialog.Accepted
        self._result_selection_session = (session_key, dialog.selection_state())
        if not accepted:
            return False
        if not dialog.selection_snapshot.ready:
            self._append_execution_log("[Results] Handoff unavailable: " + dialog.selection_snapshot.reason,
                level="WARNING", subsystem="Jana2020" if is_jana else "Results")
            return False
        chosen = dialog.selected_candidate
        active_recommendation = dialog.active_recommendation
        if active_recommendation is not None:
            self.result_recommendation = active_recommendation.with_selected(chosen)
        if cfg is not None:
            write_map_quality_report(cfg.work_dir / "map_quality_assessment.txt", self.results, chosen)
        if not is_jana:
            self._export_selected_candidate(chosen)
            return True

        result = self._cycle_result_for_candidate(chosen)
        if result is None:
            return False
        self._append_execution_log(
            f"[Jana2020] Hand-off candidate · run {chosen.run_id or 'legacy'} · "
            f"{chosen.candidate_id} · {chosen.label} · "
            f"structure SHA-256 {chosen.structure_sha256[:12]}",
            level="STEP",
            subsystem="Jana2020",
        )
        self._start_jana_handoff(cfg, result, chosen)
        return True

    def _start_jana_handoff(
        self, cfg: RunConfig, result: CycleResult, candidate: ResultCandidate,
    ) -> None:
        """The one Jana2020 handoff authority (perform_jana_handoff in a
        worker thread), shared by Result Selection and guided Autosolve."""
        self.handoff_btn.setEnabled(False)

        def handoff_worker() -> None:
            self._run_event_context.run_id = str(candidate.run_id or cfg.run_id)
            try:
                perform_jana_handoff(cfg, result, candidate, log=self.log)
                self._queue_run_event("handoff_done", None, candidate.run_id or cfg.run_id)
            except Exception as exc:
                self._queue_run_event("handoff_error", build_error_report(
                    exc,
                    subsystem="Jana2020",
                    operation="Jana2020 handoff",
                    extra_details=traceback.format_exc(),
                ), candidate.run_id or cfg.run_id)

        threading.Thread(target=handoff_worker, daemon=True).start()

    def open_jana_handoff_dialog(self) -> None:
        """Entry point for the main window's "Send to Jana2020" button.
        Dispatches to the one shared open_jana_result_selector(): locked to
        the Wizard's own choice for a Phase-recycling session, switchable
        between Superflip/SharpED for a Full-configuration session."""
        self.open_jana_result_selector()

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

    # --- Metric legend band -----------------------------------------------
    # The reserved band used to be a flat 112 px, which is narrower than the
    # legend the validation tabs actually draw ("Omit map correlation" needs
    # ~133 px), so the longest labels were clipped at the canvas edge. The
    # band is now measured from the real legend and clamped: the minimum is
    # the previous fixed value, so tabs whose labels already fitted keep
    # exactly the layout they had.
    METRICS_LEGEND_MIN_WIDTH_PX = 112.0
    METRICS_LEGEND_MAX_WIDTH_PX = 190.0
    METRICS_LEGEND_TEXT_PADDING_PX = 6.0

    def _metrics_legend_width_pixels(self, figure) -> float:
        return metrics_legend_width_pixels(self, figure)

    def _layout_metrics_figure(self, key: str) -> None:
        layout_metrics_figure(self, key)

    def _render_metrics_tab(
        self,
        key: str,
        series: List[Tuple[str, List[Optional[float]], bool, str, str, str]],
        *,
        raw: bool = False,
        raw_ylabel: str = "",
    ) -> None:
        render_metrics_tab(self, key, series, raw=raw, raw_ylabel=raw_ylabel)

    def _update_plot(self) -> None:
        update_metrics_plot(self)

    def _element_color(self, element: str) -> str:
        """Every structure view (Professional comparison, result-selector
        preview, Autosolve panels) and every legend call this, which returns
        the one module-level authority, element_color()."""
        return element_color(element)

    def _structure_cartesian_geometry(self, atoms: Sequence[AtomSite]) -> Tuple[np.ndarray, np.ndarray]:
        fractional_corners = np.asarray(
            [
                [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 1.0, 0.0],
                [0.0, 0.0, 1.0], [1.0, 0.0, 1.0], [0.0, 1.0, 1.0], [1.0, 1.0, 1.0],
            ],
            dtype=np.float64,
        )
        # Complete-molecule coordinates may intentionally extend beyond the
        # displayed unit cell.  Wrapping them here would split molecules back
        # across cell boundaries and defeat the shared viewer semantics.
        preserve_molecules = getattr(self, "_structure_view_mode", "molecule") == "molecule"
        fractional_atoms = np.asarray(
            [atom.frac if preserve_molecules else wrap_frac(atom.frac) for atom in atoms],
            dtype=np.float64,
        )
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
        plot_atoms = list(non_h_atoms)
        coords, cell_corners = self._structure_cartesian_geometry(plot_atoms)
        view_mode = getattr(self, "structure_view_mode", getattr(self, "view_mode", "molecule"))
        fit_points = cell_corners if view_mode == "cell" else coords
        bounds_min = np.min(fit_points, axis=0)
        bounds_max = np.max(fit_points, axis=0)
        spans = np.maximum(bounds_max - bounds_min, 1.0e-6)
        padding = spans * 0.025
        base_limits = tuple(
            (float(bounds_min[i] - padding[i]), float(bounds_max[i] + padding[i]))
            for i in range(3)
        )
        display_aspect = spans / max(float(np.max(spans)), 1.0e-6)
        ax.set_box_aspect(display_aspect, zoom=1.18)
        # Each panel fits its own geometry. Rotation is synchronized below,
        # while scale and center remain independent so a small molecule does
        # not become tiny beside a larger result.
        self._apply_structure_axis_limits(ax, base_limits)
        self._structure_interactive_axes.append(ax)

        cell_edges = (
            (0, 1), (0, 2), (0, 4), (1, 3), (1, 5), (2, 3),
            (2, 6), (3, 7), (4, 5), (4, 6), (5, 7), (6, 7),
        )
        cell_segments: List[np.ndarray] = []
        cell_midpoints: List[np.ndarray] = []
        edge_steps = np.linspace(0.0, 1.0, 9)
        if view_mode == "cell":
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
        if cell_segments:
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
        # Keep Axes3D for camera interaction while suppressing every graph
        # artifact.  In Full cell the explicit Line3DCollection above is the
        # sole visible box.
        ax.set_axis_off()
        shown = len(plot_atoms)
        # "atoms shown" (not "non-H/He atoms") since the viewer header
        # already explains hydrogen/helium are hidden -- no need to repeat
        # the exclusion rule here. When only the heaviest subset is actually
        # drawn, say so explicitly instead, rather than call the full count
        # "shown".
        return f"{shown:,} atoms shown"

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

        if len(artists.cell_midpoints):
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

    def _classic_structure_atoms(self, path: Optional[Path]) -> List[AtomSite]:
        """Prepare one classic comparison panel with the shared viewer semantics."""
        if path is None or not Path(path).is_file():
            return []
        try:
            resolved = Path(path)
            raw_atoms = parse_cif_atoms(resolved)
            _cell, sg, _hm = parse_cif_cell_and_sg(resolved)
            if getattr(self, "structure_view_mode", "molecule") == "cell":
                return expand_atoms_by_symmetry(raw_atoms, sg)
            from phase_studio.autosolve_window import build_complete_molecule_view

            return list(build_complete_molecule_view(raw_atoms, _cell, sg).atoms)
        except Exception:
            # Keep the established error reporting and full-cell fallback.
            return self._safe_parse_structure(path)

    def _classic_structure_composition(self, panel: str) -> Tuple[str, str]:
        """Return metadata belonging to the exact structure shown."""
        path = self._structure_source_paths.get(panel)
        if panel == "reference":
            return structure_composition_display(path)
        resolved = Path(path).resolve() if path is not None else None
        for candidate in self._result_candidates():
            if candidate.structure_path and Path(candidate.structure_path).resolve() == resolved:
                return "EDMA asymmetric-unit composition", candidate.edma_asu_composition
        source = "superflip" if panel == "superflip" else "deblurred"
        live = self._live_structures.get(source)
        if live is not None and live.structure_path is not None and live.structure_path.resolve() == resolved:
            return "EDMA asymmetric-unit composition", live.edma_asu_composition
        return "EDMA asymmetric-unit composition", ""

    def _classic_structure_formula(self, panel: str, _atoms: Sequence[AtomSite]) -> str:
        """Compatibility helper for callers that need the structure CIF value."""
        return structure_formula_from_cif(self._structure_source_paths.get(panel))

    @staticmethod
    def _structure_axis_limits(ax) -> Optional[Tuple[Tuple[float, float], ...]]:
        """The axes' current 3D limits, or None if they cannot be read.

        Matplotlib's 3D navigation expresses both zoom (right drag) and pan
        (middle drag) purely as changes to these limits, so reading and writing
        them is all that is needed to mirror either gesture onto the other
        panels."""
        try:
            return (
                (float(ax.get_xlim3d()[0]), float(ax.get_xlim3d()[1])),
                (float(ax.get_ylim3d()[0]), float(ax.get_ylim3d()[1])),
                (float(ax.get_zlim3d()[0]), float(ax.get_zlim3d()[1])),
            )
        except Exception:
            return None

    @staticmethod
    def _apply_structure_axis_limits(ax, limits: Optional[Tuple[Tuple[float, float], ...]]) -> None:
        if not limits or len(limits) != 3:
            return
        try:
            ax.set_xlim3d(limits[0][0], limits[0][1], auto=False)
            ax.set_ylim3d(limits[1][0], limits[1][1], auto=False)
            ax.set_zlim3d(limits[2][0], limits[2][1], auto=False)
        except Exception:
            pass

    def _begin_structure_view_drag(self, event) -> None:
        # Only a panel that actually drew a structure may drive the shared
        # view: an empty panel never had its limits or view angles set, so
        # letting it be the source would push matplotlib's defaults onto the
        # panels that do have content.
        ax = getattr(event, "inaxes", None)
        self._structure_view_drag_source = ax if ax in self._structure_interactive_axes else None

    def _classic_camera_orientation_changed(self, elev: float, azim: float, _source_axis) -> None:
        self.structure_elev, self.structure_azim = float(elev), float(azim)
        _source_axis.view_init(elev=elev, azim=azim, roll=_source_axis.roll)
        self._update_structure_depth_cue(elev, azim)

    def _fit_classic_structure_view(self) -> None:
        for axis in self._structure_interactive_axes:
            limits = getattr(self, "_classic_fit_limits", {}).get(axis)
            self._apply_structure_axis_limits(axis, limits)
        self.structure_canvas.draw_idle()

    def _reset_classic_structure_view(self) -> None:
        self.structure_elev, self.structure_azim = 20.0, 35.0
        for axis in self._structure_interactive_axes:
            axis.view_init(elev=self.structure_elev, azim=self.structure_azim)
        self._fit_classic_structure_view()

    def _apply_structure_view(self, source_ax, *, redraw: bool = True) -> None:
        """Mirror one panel's camera and zoom/pan onto every other panel."""
        if source_ax is None or source_ax not in self._structure_interactive_axes:
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
        source_ax = self._structure_view_drag_source
        if source_ax is None:
            source_ax = getattr(event, "inaxes", None)
        if source_ax is None or source_ax not in self._structure_interactive_axes:
            return
        self._apply_structure_view(source_ax)

    def _finish_structure_view_drag(self, event) -> None:
        source_ax = self._structure_view_drag_source
        if source_ax is None:
            source_ax = getattr(event, "inaxes", None)
        self._apply_structure_view(source_ax, redraw=False)
        self._structure_view_drag_source = None
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
        self._structure_interactive_axes = []
        self._structure_depth_artists = []
        self._classic_fit_limits = {}
        status = str(getattr(self, "_run_status", "READY")).upper()
        waiting = status in {"RUNNING", "STOPPING"}
        failed = status in {"ERROR", "CANCELLED"}
        panels = [
            ("reference", "Reference", self.reference_atoms_for_plot, "No reference structure selected"),
            (
                "superflip", "Superflip",
                self.superflip_atoms_for_plot,
                "Waiting for Superflip result…" if waiting else "Superflip structure unavailable",
            ),
            (
                "deblur", "SharpED",
                self.deblur_atoms_for_plot,
                "Waiting for SharpED result…" if waiting else "SharpED structure unavailable",
            ),
        ]
        for panel, _title, atoms, _empty_text in panels:
            button = getattr(self, "structure_fullscreen_buttons", {}).get(panel)
            if button is not None:
                button.setEnabled(bool(atoms))
        visible_elements = sorted({
            clean_element_symbol(atom.element)
            for _panel, _title, atoms, _empty_text in panels for atom in atoms
            if clean_element_symbol(atom.element) not in {"H", "D", "He"}
        }, key=lambda element: (-element_atomic_number(element), element))
        if hasattr(self, "structure_element_legend"):
            entries = "&nbsp;&nbsp;&nbsp; ".join(
                f'<span style="color:{self._element_color(element)}; font-size:12pt;">&#9679;</span>'
                f"&nbsp;{html.escape(element)}" for element in visible_elements
            )
            self.structure_element_legend.setText(
                f'<span style="color:#52658b;">Elements:</span>&nbsp;&nbsp; {entries}' if entries else ""
            )
        has_interactive_structure = any(
            any(clean_element_symbol(atom.element) not in {"H", "D", "He"} for atom in atoms)
            for _panel, _title, atoms, _empty_text in panels
        )
        self.structure_canvas.setToolTip("")
        self.structure_rotation_hint.setVisible(has_interactive_structure)
        panel_metadata = []
        for idx, (panel, _title, atoms, empty_text) in enumerate(panels, start=1):
            ax = self.structure_figure.add_subplot(1, 3, idx, projection="3d")
            self.structure_axes.append(ax)
            atom_metadata = self._plot_structure_atoms(ax, atoms, empty_text)
            if ax in self._structure_interactive_axes:
                self._classic_fit_limits[ax] = self._structure_axis_limits(ax)
            composition_label, composition = self._classic_structure_composition(panel)
            composition_text = f"{composition_label}: {composition}" if composition else ""
            panel_metadata.append(
                f"{composition_text} · {atom_metadata}"
                if composition_text and atom_metadata else (composition_text or atom_metadata)
            )
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
            for x_position, (_panel, title, _atoms, _empty_text) in zip((1.0 / 6.0, 0.5, 5.0 / 6.0), panels)
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
        self._classic_camera.refresh_axes()
        self.structure_canvas.draw_idle()

    def get_config(self) -> RunConfig:
        resolved_inputs = resolve_run_inputs(
            input_mode=self._combo_value("input_source_mode") if "input_source_mode" in self.inputs else "",
            hkl_value=self._path_value("hkl"),
            jana_inflip_value=self._path_value("jana_inflip") if "jana_inflip" in self.inputs else "",
            reference_value=self._path_value("reference_cif"),
            first_model_value=self._path_value("first_cycle_modelfile"),
            launched_from_jana_wizard=self.jana_wizard_context.launched_from_jana_wizard,
            structure_suffixes=REFERENCE_STRUCTURE_SUFFIXES,
        )
        input_source_mode = resolved_inputs.input_source_mode
        referencefile_mode = referencefile_mode_for_path(resolved_inputs.superflip_referencefile)
        modelfile_source_value = normalize_modelfile_source(self._combo_value("modelfile_source"))
        cycles_value = max(1, self._spin_value("cycles"))
        if modelfile_source_value == "none":
            cycles_value = 1
        crystal_metadata = self._resolve_crystal_metadata_from_inputs()
        resolved_wavelength, wavelength_source = resolve_powder_wavelength(
            self._dspin_value("powder_wavelength"), resolved_inputs.jana_inflip,
            resolved_inputs.external_reference_file,
        )
        if self._check_value("redistribute_overlaps") and resolved_wavelength > 0 and wavelength_source != "manual entry":
            self.log(f"Powder overlap repartitioning: wavelength {resolved_wavelength:g} A auto-detected from {wavelength_source}.", level="DETAIL")
        return RunConfig(
            hkl=resolved_inputs.hkl,
            reference_cif=resolved_inputs.reference_cif,
            superflip_reference_xplor=None,
            superflip_referencefile=resolved_inputs.superflip_referencefile,
            first_cycle_modelfile=resolved_inputs.first_cycle_modelfile,
            input_source_mode=input_source_mode,
            jana_inflip=resolved_inputs.jana_inflip,
            crystal_metadata=crystal_metadata,
            jana_return_to_jana=resolved_inputs.jana_return_to_jana,
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
            sharped_base_url=self._line_value("sharped_base_url") or DEFAULT_SERVER_URL,
            sharped_api_token=self._line_value("sharped_api_token") or os.environ.get("SHARPED_API_TOKEN", ""),
            sharped_model=self._combo_value("sharped_model") or "default",
            sharped_elements=self._line_value("sharped_elements"),
            sharped_outres=self._dspin_value("sharped_outres"),
            sharped_map_value_exponent=normalize_map_value_exponent(self._dspin_value("sharped_map_value_exponent")),
            sharped_max_upload_mb=self._dspin_value("sharped_max_upload_mb"),
            sharped_timeout_seconds=self._spin_value("sharped_timeout_seconds"),
            sharped_poll_seconds=self._spin_value("sharped_poll_seconds"),
            sharped_max_polls=self._spin_value("sharped_max_polls"),
            edma_threshold_mode=str(getattr(self, "edma_threshold_mode", "manual") or "manual"),
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
        inflip_path = active_jana_inflip(mode, inflip_text)
        try:
            return resolve_reflection_data_mode_from_sources(Path(hkl_text), configured, inflip_path)
        except Exception:
            return normalize_reflection_data_mode(configured)

    def _validate_run_config(self, cfg: RunConfig) -> Tuple[List[str], str]:
        issues: List[str] = []
        details: List[str] = []
        mode = normalize_input_source_mode(cfg.input_source_mode)
        ref_suffix = cfg.superflip_referencefile.suffix.lower() if cfg.superflip_referencefile is not None else ""
        if mode in {INPUT_MODE_INFLIP, INPUT_MODE_INFLIP_OVERRIDES}:
            if cfg.jana_inflip is None or not cfg.jana_inflip.is_file():
                issues.append("The Jana2020 .inflip file does not exist or cannot be read.")
                details.append(f"Jana2020 .inflip: {cfg.jana_inflip or '(not selected)'}")
            if mode == INPUT_MODE_INFLIP_OVERRIDES:
                if not uses_embedded_hkl(cfg.hkl) and not cfg.hkl.is_file():
                    issues.append("The external HKL override does not exist.")
                    details.append(f"HKL override: {cfg.hkl}")
                if cfg.superflip_referencefile is not None and not cfg.superflip_referencefile.is_file():
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
                "entry, the Jana .m90 file, the .inflip file, or the reference file's _diffrn_radiation_wavelength tag."
            )
            details.append("Wavelength (Å): Basic → Map feedback → Powder overlap repartitioning")
        if cfg.redistribute_overlaps and not reflection_mode_has_fwhm(self._resolve_configured_data_mode(cfg)):
            issues.append(
                "Powder overlap repartitioning is enabled, but the configured reflection data does not carry a "
                f"FWHM value ({format_reflection_data_mode(REFLECTION_DATA_MODE_INTENSITY_FWHM)} or {format_reflection_data_mode(REFLECTION_DATA_MODE_AMPLITUDE_FWHM)}). This mechanism only applies to FWHM-carrying data."
            )
            details.append("Enable powder overlap repartitioning: Basic → Map feedback → Powder overlap repartitioning")
        return list(dict.fromkeys(issues)), sanitize_error_details("\n".join(details))

    def _apply_requirement_value(self, cfg: RunConfig, kind: object, value: str, *, detected: bool) -> None:
        """Synchronize a repaired requirement into this run, Setup and QSettings."""
        from phase_studio import requirements as reqs

        key = {
            reqs.RequirementKind.SUPERFLIP: "superflip_exe",
            reqs.RequirementKind.EDMA: "edma_exe",
            reqs.RequirementKind.SHARPED: "sharped_api_token",
        }[kind]
        widget = self.inputs.get(key)
        if widget is not None:
            self._set_widget_value_from_string(widget, value)
        setattr(cfg, key, value)
        if kind is reqs.RequirementKind.SHARPED:
            self.settings.remove("inputs/sharped_api_token")
        else:
            self.settings.setValue(f"inputs/{key}", value)
        self.settings.sync()
        try:
            self.save_settings()
        except Exception:
            pass
        if kind is not reqs.RequirementKind.SHARPED:
            label = "Superflip" if kind is reqs.RequirementKind.SUPERFLIP else "EDMA"
            verb = "detected automatically" if detected else "configured"
            self._append_execution_log(
                f"{label} executable {verb}: {value}", level="DETAIL", subsystem="Setup",
            )

    def _ensure_workflow_requirements(self, cfg: RunConfig) -> bool:
        """Run preflight, repair one dedicated requirement at a time, then re-check."""
        from phase_studio import requirements as reqs

        reconstruction_mode = normalize_reconstruction_mode(cfg.reconstruction_mode)
        is_recycling = reconstruction_mode != "superflip"
        required = reqs.requirements_for_workflow(
            needs_superflip=not is_recycling or reconstruction_mode == "sharped_recycle",
            needs_edma=(
                (not is_recycling and (cfg.run_edma_superflip or cfg.run_edma_deblurred))
                or (is_recycling and cfg.run_edma_recycle_final)
            ),
            needs_sharped=bool(cfg.run_sharped or is_recycling),
        )

        active_jana_tools_directory = None
        if self.jana_wizard_context.launched_from_jana_wizard:
            from phase_studio.jana_superflip import application_dir, resolve_jana_installation_root
            active_jana_tools_directory = resolve_jana_installation_root(application_dir()) / "SUPERFLIP"

        def check() -> object:
            if not required.kinds():
                return reqs.PreflightResult()
            return reqs.run_preflight(
                required,
                superflip_path=cfg.superflip_exe,
                edma_path=cfg.edma_exe,
                sharped_base_url=cfg.sharped_base_url,
                sharped_token=cfg.sharped_api_token,
                jana_dir=getattr(self, "_preflight_jana_dir", active_jana_tools_directory),
                client_factory=getattr(self, "_preflight_client_factory", None),
                accept_suggestion=lambda _status: True,
            )

        def current_value(kind: object) -> str:
            if kind is reqs.RequirementKind.SUPERFLIP:
                return cfg.superflip_exe
            if kind is reqs.RequirementKind.EDMA:
                return cfg.edma_exe
            return cfg.sharped_api_token

        def on_success(result: object) -> None:
            for checked in result.statuses:
                if checked.kind is reqs.RequirementKind.SHARPED and checked.ok:
                    self._sharped_catalog_models = tuple(getattr(checked, "sharped_models", ()) or ())
                if (
                    checked.kind is reqs.RequirementKind.SHARPED
                    and checked.ok
                    and checked.sharped_default_model
                    and str(getattr(cfg, "sharped_model", "default") or "").strip().lower()
                    in {"", "default", "server default", "sharped default"}
                ):
                    cfg.sharped_model = checked.sharped_default_model

        effective_check = check
        if self.jana_wizard_context.launch_mode == "autosolve":
            from phase_studio.requirements_ui import check_requirements_responsively

            def effective_check():
                result = check_requirements_responsively(check, self if self.isVisible() else None)
                if result is None:
                    raise InterruptedError("Autosolve preflight cancelled")
                return result

        return run_remediation_loop(
            self,
            effective_check,
            current_value,
            lambda kind, value, detected: self._apply_requirement_value(
                cfg, kind, value, detected=detected,
            ),
            on_success,
            download_dir=getattr(self, "_preflight_download_dir", None),
            download_opener=getattr(self, "_preflight_download_opener", None),
            sharped_base_url=cfg.sharped_base_url,
            sharped_probe=lambda key: reqs.check_sharped_api(
                cfg.sharped_base_url, key,
                client_factory=getattr(self, "_preflight_client_factory", None),
            ),
        )

    def start_run(self) -> None:
        if getattr(self, "_start_request_active", False):
            return
        self._start_request_active = True
        try:
            self._start_run_checked()
        except InterruptedError:
            self._append_execution_log("Requirements check cancelled; no calculation started.", subsystem="Workflow")
        finally:
            self._start_request_active = False

    def _start_run_checked(self) -> None:
        if self.worker and self.worker.is_alive():
            self._append_execution_log("Workflow is already running.", level="WARNING", subsystem="Workflow")
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
        while True:
            if not self._ensure_workflow_requirements(cfg):
                return
            if self.jana_wizard_context.launch_mode != "autosolve":
                break
            self._retry_model_preflight = False
            if self._autosolve_models_available():
                break
            if not self._retry_model_preflight:
                return
        if self.jana_wizard_context.launch_mode == "autosolve":
            cfg.sharped_model = guided.AUTOSOLVE_MODEL
            # The internal phase-boost feed-forward threshold (the established
            # SharpED-side value), kept for any later search continuation.
            self._autosolve_search_deblur_sigma = float(cfg.plimit_deblur)
        try:
            self._begin_fresh_run_context(cfg)
            self.last_run_config = cfg
            self.save_settings()
        except Exception as exc:
            self._show_error_report(
                build_error_report(exc, subsystem="Files", operation="Create working directory", paths=(cfg.work_dir,))
            )
            return
        mode = normalize_input_source_mode(cfg.input_source_mode)
        if mode == INPUT_MODE_INFLIP:
            self._append_execution_log(
                "Input mode: Jana2020 .inflip. Embedded HKL data will be used.",
                level="DETAIL",
            )
        elif mode == INPUT_MODE_INFLIP_OVERRIDES:
            if uses_embedded_hkl(cfg.hkl):
                self._append_execution_log("HKL override is empty; the Jana2020 .inflip fbegin/endf block will be used.", level="DETAIL")
            if cfg.superflip_referencefile is None:
                self._append_execution_log("External reference file is empty; no external reference density or atom sites will be used.", level="DETAIL")
        self.stop_after_cycle.clear()
        self.stop_now.clear()
        self._jana_auto_selector_shown = False
        # Fresh workflow: stable compatibility notices are reported again.
        self._workflow_log_once = set()
        # Overall progress is determinate from the start (0 of N cycles, N is
        # known) and never regresses within this run -- see
        # _set_overall_progress_value(). Only stage-local bars show the
        # indeterminate busy state for unknown-duration work.
        self._overall_progress_floor = 0
        self.progress_bar.setRange(0, max(1, int(getattr(cfg, "cycles", 1))))
        self._set_overall_progress_value(0)
        self._set_overall_progress_text("Running")
        self._cycle_progress_state = None
        self.current_cycle_progress.setRange(0, 0)
        self.current_cycle_detail.setText("Validating input and preparing Superflip files…")
        self.current_cycle_stage_counter.setText("Preparing")
        self._set_run_status("Running")
        self.run_btn.setEnabled(False)
        self.handoff_btn.setEnabled(False)
        self.run_btn.setText("Running…")
        self.log_text.horizontalScrollBar().setValue(0)
        self._append_execution_log("Validating input and preparing Superflip files…", level="DETAIL")
        QApplication.processEvents()
        self.worker = threading.Thread(target=self.pipeline_worker, args=(cfg,), daemon=True)
        self.worker.start()

    def continue_run(self) -> None:
        if self.worker and self.worker.is_alive():
            self._append_execution_log("Workflow is already running.", level="WARNING", subsystem="Workflow")
            return
        state = self._resume_state
        if state is None:
            self._append_execution_log("Nothing to continue: no previous run to resume.", level="WARNING", subsystem="Workflow")
            return
        requested_cycles = max(1, self._spin_value("cycles"))
        if requested_cycles <= state.completed_cycles:
            self._show_error_report(build_validation_report([
                f"The previous run already completed {state.completed_cycles} cycle(s). "
                f"Increase Cycles above {state.completed_cycles} before continuing."
            ]))
            return
        state.cfg.cycles = requested_cycles
        # Continue preserves the captured scientific configuration. Only
        # connection controls may be repaired after a failed SharpED request;
        # changing them does not invalidate completed Superflip/EDMA outputs.
        state.cfg.sharped_base_url = self._line_value("sharped_base_url") or DEFAULT_SERVER_URL
        state.cfg.sharped_api_token = (
            self._line_value("sharped_api_token") or os.environ.get("SHARPED_API_TOKEN", "")
        )
        state.cfg.sharped_timeout_seconds = self._spin_value("sharped_timeout_seconds")
        state.cfg.sharped_poll_seconds = self._spin_value("sharped_poll_seconds")
        state.cfg.sharped_max_polls = self._spin_value("sharped_max_polls")
        self.last_run_config = state.cfg
        if self.jana_wizard_context.launch_mode == "autosolve":
            state.cfg.sharped_model = guided.AUTOSOLVE_MODEL
        self.stop_after_cycle.clear()
        self.stop_now.clear()
        self._jana_auto_selector_shown = False
        # Fresh workflow: stable compatibility notices are reported again.
        self._workflow_log_once = set()
        # Continuing (including Autosolve's adaptive extension): keep the
        # overall bar determinate at the completed-cycle count of the new
        # total -- never drop back to busy/0.
        self.progress_bar.setRange(0, max(1, int(requested_cycles)))
        self._set_overall_progress_value(state.completed_cycles)
        self._set_overall_progress_text("Running")
        self._cycle_progress_state = None
        self.current_cycle_progress.setRange(0, 0)
        self.current_cycle_detail.setText("Resuming workflow…")
        self.current_cycle_stage_counter.setText("Preparing")
        self._set_run_status("Running")
        self.run_btn.setEnabled(False)
        self.handoff_btn.setEnabled(False)
        self.run_btn.setText("Running…")
        checkpoint = state.ordinary_cycle_checkpoint
        resume_cycle = checkpoint.cycle if checkpoint is not None else state.completed_cycles + 1
        resume_stage = checkpoint.first_incomplete_stage() if checkpoint is not None else "Preparing cycle"
        self._append_execution_log(
            f"Continuing workflow at {resume_stage} in cycle {resume_cycle} of {requested_cycles}, "
            "reusing valid completed stage outputs and the previous run's scientific configuration.",
            level="DETAIL",
        )
        QApplication.processEvents()
        self.worker = threading.Thread(
            target=self.pipeline_worker, args=(None,), kwargs={"resume_state": state}, daemon=True
        )
        self.worker.start()

    def pipeline_worker(self, cfg: Optional[RunConfig], resume_state: Optional[PipelineState] = None) -> None:
        worker_run_id = (
            resume_state.run_id if resume_state is not None
            else (cfg.run_id if cfg is not None else "")
        )
        self._run_event_context.run_id = str(worker_run_id)
        if resume_state is not None:
            profiler = WorkflowProfiler.from_environment()
            resume_state.performance_profiler = profiler
            resume_state.performance_root = profiler.start("Total workflow")
            try:
                with profiler.stage("Continue run preparation"):
                    checkpoint = resume_state.ordinary_cycle_checkpoint
                    resume_cycle = checkpoint.cycle if checkpoint is not None else resume_state.completed_cycles + 1
                    resume_stage = checkpoint.first_incomplete_stage() if checkpoint is not None else "Preparing cycle"
                    self.log(
                        f"=== Workflow resumed at {resume_stage} · cycle {resume_cycle} of {resume_state.cfg.cycles} ===",
                        level="STEP",
                    )
                    self._queue_run_event("progress_setup", resume_state.cfg.cycles)
                    self._queue_run_event("progress", resume_state.completed_cycles)
                if normalize_reconstruction_mode(resume_state.cfg.reconstruction_mode) == "superflip":
                    self._run_pipeline_cycles(resume_state)
                else:
                    self._run_sharped_recycle_cycles(resume_state)
                self._finish_performance_profile(
                    resume_state, self._requested_workflow_stop_kind() or "complete"
                )
            except Exception as exc:
                self._finish_performance_profile(
                    resume_state, self._requested_workflow_stop_kind() or "failed"
                )
                self._queue_run_event(
                    "error_report",
                    build_error_report(exc, operation="Run workflow", extra_details=traceback.format_exc()),
                )
            return
        profiler = WorkflowProfiler.from_environment()
        performance_root = profiler.start("Total workflow")
        preparation_timing = profiler.start("Phase Studio preparation")
        state: Optional[PipelineState] = None
        try:
            self.log(f"Run {cfg.run_id or 'legacy'} started", level="STEP")
            mode = normalize_input_source_mode(cfg.input_source_mode)
            self.log(f"  Mode: {INPUT_MODE_LABELS.get(mode, mode)}", level="DETAIL")
            self.log(f"  Work directory: {cfg.work_dir}", level="DETAIL")
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
            self.log(f"  Reflections: {len(refl_raw)} parsed / {len(refl)} unique", level="DETAIL")
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
            self._queue_run_event("structure_cell", (
                ref_ctx.cell.a, ref_ctx.cell.b, ref_ctx.cell.c,
                ref_ctx.cell.alpha, ref_ctx.cell.beta, ref_ctx.cell.gamma,
            ))
            self._queue_run_event(
                "reference_atoms",
                (expand_atoms_by_symmetry(ref_ctx.atoms, ref_ctx.spacegroup), atom_source),
            )
            input_path = cfg.jana_inflip if mode in {INPUT_MODE_INFLIP, INPUT_MODE_INFLIP_OVERRIDES} else cfg.hkl
            self.log(
                f"Input: {INPUT_MODE_LABELS.get(mode, mode)} · {Path(input_path).name}",
                level="STEP",
            )
            self.log(f"Reflections: {len(refl):,} unique", level="INFO")
            metadata_label = METADATA_SOURCE_LABELS.get(cfg.crystal_metadata.source, cfg.crystal_metadata.source)
            self.log(f"  Source: {metadata_label}", level="INFO")
            if cfg.crystal_metadata.source_path is not None:
                self.log(f"  Metadata file: {cfg.crystal_metadata.source_path}", level="DETAIL")
            self.log(f"  Cell: {ref_ctx.cell.a:.5f} {ref_ctx.cell.b:.5f} {ref_ctx.cell.c:.5f} {ref_ctx.cell.alpha:.3f} {ref_ctx.cell.beta:.3f} {ref_ctx.cell.gamma:.3f}")
            self.log(f"  Space group: {compact_spacegroup_symbol(ref_ctx.spacegroup)} (#{ref_ctx.spacegroup.number})")
            self.log(f"  Composition: {ref_ctx.composition}")
            self.log(
                f"  Initial atomic model: {len(ref_ctx.atoms)} sites"
                if atom_source is not None else "  Initial atomic model: not provided",
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
            if cfg.run_sharped and not use_superflip_xplor_modelfile:
                workflow.append("SharpED")
            if cfg.symmetrize_deblurred_map and not use_superflip_xplor_modelfile:
                workflow.append("symmetry averaging")
            self.log(
                f"Workflow: {' + '.join(workflow)} · {cfg.cycles} "
                f"{'cycle' if int(cfg.cycles) == 1 else 'cycles'}",
                level="STEP",
            )
            self.log("  Main progression: " + " → ".join(workflow), level="DETAIL")
            if cfg.run_sharped and not use_superflip_xplor_modelfile:
                self.log(f"SharpED model: {cfg.sharped_model}", level="INFO")
            edma_summary = []
            if cfg.run_edma_superflip:
                edma_summary.append(f"Charge-flipping solution {float(cfg.plimit_superflip):.2f} σ")
            if cfg.run_edma_deblurred and not use_superflip_xplor_modelfile:
                edma_summary.append(f"Structure prediction {float(cfg.plimit_deblur):.2f} σ")
            if edma_summary:
                self.log("EDMA: " + " · ".join(edma_summary), level="INFO")
            feedback_enabled = bool(
                cfg.map_feedback_missing_enabled
                or cfg.map_feedback_intensity_enabled
                or cfg.redistribute_overlaps
            )
            self.log(f"Map Feedback: {'On' if feedback_enabled else 'Off'}", level="INFO")
            edma_sources = []
            if cfg.run_edma_superflip:
                edma_sources.append("completed Superflip maps")
            if cfg.run_edma_deblurred and not use_superflip_xplor_modelfile:
                edma_sources.append("completed SharpED maps")
            if edma_sources:
                self.log(
                    "  EDMA structure extraction runs asynchronously for " + " and ".join(edma_sources) + ".",
                    level="INFO",
                )
            self.log(f"  Cycles: {cfg.cycles}", level="INFO")
            next_cycle_kind = "input" if modelfile_mode in {"superflip_xplor", "deblurred_xplor"} else "model"
            self.log(
                f"  Next-cycle {next_cycle_kind}: {modelfile_source_display_label(modelfile_mode)}",
                level="INFO",
            )
            if use_xplor_modelfile:
                self.log(
                    f"  XPLOR damping 1/x: {max(0.001, min(1.0, float(cfg.damping_factor))):g}",
                    level="INFO",
                )
            # Full executable/server provenance belongs in the persistent run
            # log header.  DETAIL keeps these useful records out of the short
            # GUI event stream and avoids empty visible section headings.
            self.log("External programs", level="DETAIL")
            self.log(f"  Superflip: {cfg.superflip_exe}", level="DETAIL")
            self.log(f"  EDMA: {cfg.edma_exe}", level="DETAIL")
            self.log("SharpED", level="DETAIL")
            self.log(f"  Server: {cfg.sharped_base_url}", level="DETAIL")
            self.log(f"  Model: {cfg.sharped_model or 'default'}", level="DETAIL")
            self.log(f"  Elements: {sharped_elements}", level="DETAIL")
            # Provenance: a finished run's log must always say which map value
            # exponent produced it. Non-default values are reported at the
            # normal tier; the default stays a detailed diagnostic so a default
            # run's log reads exactly as it did before this setting existed.
            sharped_exponent = normalize_map_value_exponent(cfg.sharped_map_value_exponent)
            if sharped_exponent == 0.0:
                self.log("  Map value scaling: disabled (exponent 0)")
            elif map_value_scaling_is_identity(sharped_exponent):
                self.log(f"  Map value exponent: {sharped_exponent:.3f} (map values unchanged)", level="DETAIL")
            else:
                self.log(f"  Map value exponent: {sharped_exponent:.3f}")

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
                self.log("[Map feedback]\n" + "\n".join(map_feedback_lines), level="DETAIL")
            else:
                self.log("[Map feedback] Disabled", level="DETAIL")
            self._queue_run_event("progress_setup", cfg.cycles)
            omit_test_hkls: FrozenSet[Tuple[int, int, int]] = frozenset()
            if cfg.compute_omit_maps:
                omit_test_hkls = select_orbit_safe_holdout(refl, ref_ctx.spacegroup, cfg.randomseed)
            validation_context = build_validation_context(
                refl, configured_data_mode, ref_ctx, omit_test_hkls,
            )
            self._queue_run_event("validation_profile", validation_context.profile.value)
            if omit_test_hkls:
                current_reflections = [
                    reflection for reflection in refl
                    if (int(reflection.h), int(reflection.k), int(reflection.l)) not in omit_test_hkls
                ]
            definition = profile_definition(validation_context.profile)
            holdout_text = (
                f"5% holdout · {len(validation_context.free_reflections)} free reflections"
                if validation_context.free_reflections else "no holdout"
            )
            assessment_text = definition.assessment_label
            if holdout_text.casefold() not in assessment_text.casefold():
                assessment_text += f" · {holdout_text}"
            self.log(
                f"Assessment: {assessment_text}",
                subsystem="Validation",
            )
            data_modes_needed = {configured_data_mode}
            observed_hkls: Dict[str, Path] = {}
            for data_mode in sorted(data_modes_needed):
                observed_hkl = cfg.work_dir / observed_hkl_name_for_mode(data_mode)
                n_written = write_observed_reflections(observed_hkl, current_reflections, cfg.i_over_sigma_min, data_mode=data_mode, cell=ref_ctx.cell, resolution_d_min=cfg.resolution_d_min)
                observed_hkls[data_mode] = observed_hkl
                self.log(
                    f"Prepared HKL for {format_reflection_data_mode(data_mode)}: "
                    f"{observed_hkl} ({n_written} reflections)"
                )
            if omit_test_hkls:
                self.log(
                    f"Holdout: excluded {len(omit_test_hkls)}/{len(refl)} reflections in complete symmetry/Friedel orbits; "
                    "the fixed set is excluded from every work-data cycle and feedback step.",
                    level="DETAIL",
                    subsystem="Validation",
                )
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
                validation_context=validation_context,
                performance_profiler=profiler,
                performance_root=performance_root,
                run_id=cfg.run_id,
            )
            self._resume_state = state
            if preparation_timing is not None:
                preparation_timing.stop()
            if reconstruction_mode == "superflip":
                self._run_pipeline_cycles(state)
            else:
                self._run_sharped_recycle_cycles(state)
            self._finish_performance_profile(
                state, self._requested_workflow_stop_kind() or "complete"
            )
        except Exception as exc:
            if preparation_timing is not None:
                preparation_timing.stop()
            if state is not None:
                self._finish_performance_profile(
                    state, self._requested_workflow_stop_kind() or "failed"
                )
            else:
                if performance_root is not None:
                    performance_root.stop()
                if cfg is not None:
                    profiler.write_report(cfg.work_dir / "workflow_performance.txt", "failed")
            self._queue_run_event(
                "error_report",
                build_error_report(
                    exc,
                    operation="Run workflow",
                    extra_details=traceback.format_exc(),
                ),
            )

    @staticmethod
    def _finish_performance_profile(state: PipelineState, outcome: str) -> None:
        profiler = state.performance_profiler
        if profiler is None or not profiler.enabled:
            return
        if state.performance_root is not None:
            state.performance_root.stop()
            state.performance_root = None
        profiler.write_report(state.cfg.work_dir / "workflow_performance.txt", outcome)

    def _record_completed_cycle_result(self, state: PipelineState, result: CycleResult) -> None:
        """Persist and publish one fully constructed cycle result."""
        cfg = state.cfg
        if state.run_id != cfg.run_id:
            raise RuntimeError("Run context changed while recording a completed cycle.")
        result.run_id = state.run_id
        result.sharped_model = str(cfg.sharped_model or "") if cfg.run_sharped else ""
        recycling = str(result.model_source).startswith("sharped_recycle")
        result.superflip_edma_enabled = bool(cfg.run_edma_superflip) and not recycling
        result.deblur_edma_enabled = (
            bool(cfg.run_edma_recycle_final) if recycling
            else bool(cfg.run_edma_deblurred)
        )
        result.superflip_edma_sigma = (
            float(cfg.plimit_superflip) if result.superflip_edma_enabled else None
        )
        result.deblur_edma_sigma = (
            float(cfg.plimit_deblur) if result.deblur_edma_enabled else None
        )
        pending_results = [item for item in state.all_results if item.cycle != result.cycle]
        pending_results.append(result)
        pending_results.sort(key=lambda item: item.cycle)
        with profile_stage(state.performance_profiler, "Reports and CSV"):
            write_metrics_csv(state.cfg.work_dir / "metrics.csv", pending_results)
            write_map_quality_report(
                state.cfg.work_dir / "map_quality_assessment.txt", pending_results
            )
        state.all_results[:] = pending_results
        for source, quality in (
            ("superflip", result.superflip_quality), ("deblurred", result.deblur_quality),
        ):
            if quality is not None:
                self.log(
                    format_validation_log_line(result.cycle, source, result.validation_profile, quality),
                    subsystem="Validation",
                )
        self._queue_run_event("result", result, state.run_id)

    @staticmethod
    def _validation_profile_for_result(state: PipelineState) -> str:
        return (
            state.validation_context.profile.value
            if state.validation_context is not None else ValidationProfile.REFERENCE_FREE.value
        )

    def _finalize_completed_cycle(
        self, state: PipelineState, cycle: int, progress_stages: Sequence[str],
    ) -> bool:
        """Checkpoint one valid cycle and apply terminal-intent precedence."""
        self.log(f"Cycle {cycle} complete.", level="SUCCESS")
        self._emit_cycle_progress(
            cycle, state.cfg.cycles, progress_stages, "Finalizing cycle",
            detail="completed", complete=True,
        )
        state.completed_cycles = cycle
        self._queue_run_event("progress", state.completed_cycles, state.run_id)
        return self._emit_requested_workflow_stop(state.completed_cycles)

    def _run_configured_sharped_stage(
        self, state: PipelineState, input_map: Path, output_map: Path, cycle: int,
        progress_stages: Sequence[str], detail_prefix: str = "", model: Optional[str] = None,
    ) -> Path:
        """Run one explicitly selected SharpED stage with shared plumbing.
        `model` overrides cfg.sharped_model for one call (2.0.1's dedicated
        Predicted-structure inference); cycles pass nothing."""
        cfg = state.cfg
        self._run_event_context.run_id = str(state.run_id)
        self._emit_cycle_progress(
            cycle, cfg.cycles, progress_stages, "SharpED",
            detail=detail_prefix + "preparing upload", busy=True,
        )
        effective_model = model or cfg.sharped_model
        self.log(
            f"SharpED upload started · {effective_model}",
            level="INFO", subsystem="SharpED",
        )
        self.log(
            f"[SharpED] Model: {effective_model}",
            level="DETAIL", subsystem="SharpED",
        )
        self.log(
            f"[SharpED] Run/cycle: {state.run_id or 'legacy'} / {cycle}",
            level="DETAIL", subsystem="SharpED",
        )
        self.log(
            "[SharpED] Input map · " + describe_xplor_artifact(input_map),
            level="DETAIL", subsystem="SharpED",
        )
        result = self._run_display_operation(state, cycle, "SharpED", lambda: run_sharped_deblur(
            input_map, output_map, cfg.sharped_base_url, cfg.sharped_api_token, effective_model,
            state.sharped_elements, cfg.sharped_outres, cfg.sharped_max_upload_mb,
            cfg.sharped_timeout_seconds, cfg.sharped_poll_seconds, cfg.sharped_max_polls,
            self.log, self.stop_now,
            progress=lambda detail: self._emit_cycle_progress(
                cycle, cfg.cycles, progress_stages, "SharpED",
                detail=detail_prefix + detail, busy=detail != "completed",
            ),
            map_value_exponent=cfg.sharped_map_value_exponent,
            profiler=state.performance_profiler,
        ))
        self.log(
            "[SharpED] Output map · " + describe_xplor_artifact(result),
            level="DETAIL", subsystem="SharpED",
        )
        state.sharped_models_by_map[str(Path(result).resolve())] = str(effective_model)
        return result

    def _run_configured_edma_stage(
        self, state: PipelineState, input_map: Path, output_dir: Path,
        prefix: str, plimit: float, map_label: Optional[str] = None, explicit_threshold: bool = False,
        stop_event: Optional[threading.Event] = None,
    ) -> Path:
        """Run EDMA with captured configuration and an explicit map role.
        `map_label` names the map in the log (e.g. the Structure prediction
        map); `explicit_threshold` (guided Autosolve's user-chosen value)
        always uses `plimit` exactly, never the automatic selection."""
        self._run_event_context.run_id = str(state.run_id)
        cfg = state.cfg
        if not explicit_threshold and str(getattr(cfg, "edma_threshold_mode", "manual")).lower() == "auto":
            return self._run_auto_threshold_edma_stage(state, input_map, output_dir, prefix)
        model = state.sharped_models_by_map.get(str(Path(input_map).resolve()), "")
        family = "Structure prediction" if model else "Charge-flipping solution"
        self.log(
            f"{family} · EDMA started · {float(plimit):.2f} σ",
            level="INFO", subsystem="EDMA",
        )
        self.log(
            "[EDMA] "
            f"Run {state.run_id or 'legacy'} · Source {'Structure prediction' if model else 'Charge-flipping solution'} · "
            f"SharpED model {model or 'n/a'} · Map "
            + describe_xplor_artifact(input_map)
            + f" · Threshold {float(plimit):.2f} sigma",
            level="DETAIL", subsystem="EDMA",
        )
        result = run_edma_on_xplor(
            input_map, output_dir, prefix, state.ref_ctx, plimit, cfg.merge_distance,
            cfg.edma_exe, self.log, stop_event or self.stop_now, cfg.edma_maxima, cfg.edma_fullcell,
            cfg.edma_numberofatoms, cfg.edma_centerofcharge, cfg.edma_chlimit, cfg.edma_chlimlist,
            cfg.extra_edma_keywords, cfg.structure_export_format,
            write_m40=cfg.jana_inflip is not None,
            profiler=state.performance_profiler,
            map_label=map_label,
        )
        identity = cif_artifact_identity(result)
        self.log(
            "[EDMA] Raw structure · "
            f"{identity['path']} · SHA-256 {str(identity['sha256'])[:12]} · "
            f"block {identity['data_block'] or 'unnamed'} · atoms {identity['atom_count']} · "
            f"elements {identity['elements']} · cell {identity['cell']} · "
            f"space group {identity['space_group']} · symmetry operators {identity['symmetry_operations']} · "
            f"{identity['coordinate_representation']}",
            level="DETAIL", subsystem="EDMA",
        )
        return result

    def _run_auto_threshold_edma_stage(
        self, state: PipelineState, input_map: Path, output_dir: Path, prefix: str,
    ) -> Path:
        """Autosolve's per-map automatic EDMA threshold (phase_studio/
        edma_threshold.py): the existing EDMA extraction is run at several
        thresholds (in parallel, cached by map SHA-256 + sigma + EDMA
        settings/version + composition), each extracted structure is scored
        against the measured reflections, and the lowest data-supported
        threshold is chosen. The chosen structure is then produced by the
        normal run_edma_on_xplor call at that threshold into the canonical
        output directory, so the displayed structure, formula, ranking,
        next-cycle reference and exports all refer to the same EDMA result.
        Candidates are extracted with composition-only element assignment, so
        the selected threshold never depends on whether a reference is
        loaded; reference metrics are recorded only as validation."""
        import dataclasses
        import json

        from phase_studio import edma_threshold as auto

        cfg = state.cfg
        source = "deblurred" if "deblur" in prefix.lower() else "superflip"
        label = result_map_label(source)
        calibration: Optional[object] = None
        with profile_stage(state.performance_profiler, "EDMA threshold calibration", "phase_studio"):
            try:
                evaluator = getattr(state, "_edma_agreement_evaluator", None)
                if evaluator is None and state.validation_context is not None:
                    evaluator = auto.ModelAgreementEvaluator(
                        state.validation_context, state.ref_ctx.cell, state.ref_ctx.spacegroup,
                    )
                    state._edma_agreement_evaluator = evaluator  # type: ignore[attr-defined]
                if evaluator is None:
                    raise RuntimeError("no measured reflections available for model agreement")
                try:
                    composition = parse_composition_counts(state.ref_ctx.composition)
                except Exception:
                    composition = []
                edma_version = getattr(state, "_edma_exe_sha256", None)
                if edma_version is None:
                    try:
                        edma_version = auto.file_sha256(Path(cfg.edma_exe))
                    except Exception:
                        edma_version = str(cfg.edma_exe)
                    state._edma_exe_sha256 = edma_version  # type: ignore[attr-defined]
                context_key = json.dumps([
                    edma_version, cfg.edma_maxima, cfg.edma_fullcell, cfg.edma_numberofatoms,
                    bool(cfg.edma_centerofcharge), cfg.edma_chlimit, cfg.edma_chlimlist,
                    cfg.extra_edma_keywords, float(cfg.merge_distance), state.ref_ctx.composition,
                    state.ref_ctx.spacegroup.hm, [state.ref_ctx.cell.a, state.ref_ctx.cell.b, state.ref_ctx.cell.c,
                                                 state.ref_ctx.cell.alpha, state.ref_ctx.cell.beta, state.ref_ctx.cell.gamma],
                ])
                cache = auto.EdmaCandidateCache(cfg.work_dir / "edma_threshold_cache", auto.file_sha256(input_map), context_key)
                composition_only_ctx = dataclasses.replace(state.ref_ctx, atoms=[])
                candidates_dir = output_dir / "auto_threshold"
                stats: Dict[str, int] = {}

                def quiet_log(_message: str, *args, **kwargs) -> None:
                    return None

                def extract(sigma: float) -> List[object]:
                    candidate_dir = candidates_dir / f"sigma_{sigma:.2f}"
                    cif = run_edma_on_xplor(
                        input_map, candidate_dir, prefix, composition_only_ctx, sigma, cfg.merge_distance,
                        cfg.edma_exe, quiet_log, self.stop_now, cfg.edma_maxima, cfg.edma_fullcell,
                        cfg.edma_numberofatoms, cfg.edma_centerofcharge, cfg.edma_chlimit, cfg.edma_chlimlist,
                        cfg.extra_edma_keywords, cfg.structure_export_format,
                        write_m40=False, profiler=None,
                    )
                    try:
                        (candidate_dir / input_map.name).unlink()  # large per-candidate map copy
                    except OSError:
                        pass
                    return [
                        auto.PeakSite(clean_element_symbol(a.element), tuple(float(v) for v in a.frac), float(a.density or 0.0))
                        for a in parse_cif_atoms(cif)
                    ]

                self.log(
                    f"[EDMA] {label} · Auto threshold calibration "
                    f"({len(auto.AUTO_EDMA_COARSE_SIGMAS)} coarse thresholds, "
                    f"{auto.AUTO_EDMA_COARSE_SIGMAS[0]:g}–{auto.AUTO_EDMA_COARSE_SIGMAS[-1]:g} σ)…",
                    subsystem="EDMA",
                )
                calibration = auto.calibrate_edma_threshold(
                    source,
                    auto.cached_parallel_extractor(extract, cache, auto.AUTO_EDMA_PARALLEL_WORKERS, stats),
                    evaluator,
                    composition,
                    stop_event=self.stop_now,
                )
                calibration.edma_calls = int(stats.get("edma_runs", 0))
                calibration.cache_hits = int(stats.get("cache_hits", 0))
            except InterruptedError:
                raise
            except Exception as exc:
                if self.stop_now.is_set():
                    raise
                calibration = auto.ThresholdCalibration(
                    mode=auto.EDMA_THRESHOLD_MODE_AUTO, source=source,
                    selected_sigma=float(auto.AUTO_EDMA_FALLBACK_SIGMA[source]), fallback_used=True,
                    message=f"{auto.FALLBACK_MESSAGE} ({type(exc).__name__}: {exc})",
                    criterion="", candidate_sigmas=[], candidates=[],
                    composition_available=False, holdout_available=False,
                )

        chosen = float(calibration.selected_sigma)
        cif = run_edma_on_xplor(
            input_map, output_dir, prefix, state.ref_ctx, chosen, cfg.merge_distance,
            cfg.edma_exe, self.log, self.stop_now, cfg.edma_maxima, cfg.edma_fullcell,
            cfg.edma_numberofatoms, cfg.edma_centerofcharge, cfg.edma_chlimit, cfg.edma_chlimlist,
            cfg.extra_edma_keywords, cfg.structure_export_format,
            write_m40=cfg.jana_inflip is not None,
            profiler=state.performance_profiler,
        )
        # Validation only (never an input to the selector above): reference
        # metrics for the selected threshold and the fixed fallback threshold,
        # so each run records how the automatic choice compares with the old
        # fixed default. Limited to those two -- the reference matcher is
        # O(N_model x N_reference) per candidate.
        if state.ref_ctx.atoms:
            validation: Dict[str, object] = {}
            wanted = {round(chosen, 4), round(float(auto.AUTO_EDMA_FALLBACK_SIGMA[source]), 4)}
            for candidate in calibration.candidates:
                if round(candidate.sigma, 4) not in wanted:
                    continue
                candidate_cif = output_dir / "auto_threshold" / f"sigma_{candidate.sigma:.2f}" / f"{prefix}_edma.cif"
                if not candidate_cif.is_file():
                    continue
                try:
                    match = atom_reference_match_metrics(candidate_cif, state.ref_ctx, cfg.merge_distance)
                    if match is None:
                        continue
                    recall, precision = match[0], match[1]
                    validation[f"{candidate.sigma:.2f}"] = {
                        "precision": precision, "recall": recall,
                        "f05": (1.25 * precision * recall / (0.25 * precision + recall))
                        if precision is not None and recall is not None and (0.25 * precision + recall) > 0 else None,
                        "rmsd": nearest_metric_to_reference(candidate_cif, state.ref_ctx),
                    }
                except Exception:
                    continue
            calibration.reference_validation = validation or None
        try:
            (output_dir / f"{prefix}_edma_threshold.json").write_text(calibration.to_json(), encoding="utf-8")
        except OSError:
            pass
        selected = calibration.selected
        if calibration.fallback_used:
            self.log(f"[EDMA] {label} · {calibration.message} Using {chosen:.2f} σ.", level="WARNING", subsystem="EDMA")
        else:
            agreement = ""
            if selected is not None and selected.r_all is not None and selected.cc_all is not None:
                agreement = f" · model R_F {selected.r_all:.3f}, CC_F {selected.cc_all:.3f}"
                if calibration.holdout_available and selected.r_free is not None and selected.cc_free is not None:
                    agreement += f" · model R_free {selected.r_free:.3f}, CC_free {selected.cc_free:.3f}"
                else:
                    agreement += " (all-data, non-independent)"
            self.log(
                f"[EDMA] {label} · Auto threshold {chosen:.2f} σ"
                f" · {len(calibration.candidates)} thresholds evaluated ({calibration.edma_calls} EDMA runs,"
                f" {calibration.cache_hits} cached, {calibration.seconds:.1f} s){agreement}",
                subsystem="EDMA",
            )
        return cif

    @staticmethod
    def _edma_reference_metrics(
        cif_path: Path, ref_ctx: ReferenceContext, merge_distance: float, enabled: bool,
    ) -> Tuple[Optional[float], Optional[Tuple[float, float, int, int]]]:
        if not enabled:
            return None, None
        return (
            nearest_metric_to_reference(cif_path, ref_ctx),
            atom_reference_match_metrics(cif_path, ref_ctx, merge_distance),
        )

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
        exclude_labels = state.exclude_labels
        progress_stages = state.progress_stages
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
        # Automatic EDMA is a side branch from an immutable completed map.
        # Two workers bound the number of EDMA/SharpED subprocess-launch tasks
        # while keeping them independent of the main workflow worker and Qt.
        branch_executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix=f"workflow-branches-{state.run_id or 'legacy'}",
        )
        for cyc in range(state.completed_cycles + 1, cfg.cycles + 1):
            if self._emit_requested_workflow_stop(state.completed_cycles):
                branch_executor.shutdown(wait=True, cancel_futures=False)
                return
            self._emit_cycle_progress(
                cyc,
                cfg.cycles,
                progress_stages,
                "Preparing cycle",
                detail="preparing model and reflections",
            )
            cycle_dir = cfg.work_dir / f"cycle_{cyc:03d}"; cycle_dir.mkdir(parents=True, exist_ok=True)
            self.log(f"Cycle {cyc} of {cfg.cycles}", level="STEP")
            checkpoint = state.ordinary_cycle_checkpoint
            if checkpoint is None or checkpoint.cycle != cyc:
                checkpoint = OrdinaryCycleCheckpoint(cycle=cyc)
                state.ordinary_cycle_checkpoint = checkpoint
            elif any((
                checkpoint.superflip_completed,
                checkpoint.superflip_edma_completed,
                checkpoint.sharped_completed,
                checkpoint.sharped_edma_completed,
                checkpoint.validation_completed,
                checkpoint.result_recorded,
            )):
                self.log(
                    f"[Continue] Resuming cycle {cyc} at its first incomplete stage; "
                    "completed scientific outputs will be reused.",
                    level="STEP",
                )
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
                seed_note = getattr(state, "refinement_seed_note", None)
                if seed_note:
                    # First cycle of a user-seeded refinement block: the model
                    # is the user's selected structure, not the previous cycle.
                    self.log(f"[Refinement seed] {seed_note} · {state.current_model}", level="STEP")
                    self.log(f"  Superflip initial model: {model_for_sf}")
                    state.refinement_seed_note = None
                else:
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
            elif referencefile_mode == "omit" and cyc == 1 and cfg.first_cycle_modelfile is not None:
                # No user-selected reference file, but an Initial model was supplied:
                # anchor cycle 1's phase origin against that same model, mirroring the
                # automatic previous-cycle anchor a continuing series already gets above
                # -- a fresh series has no previous cycle, but the Initial model itself
                # is the scientifically equivalent anchor (it is the same file a
                # continuing series would have used as both modelfile and referencefile
                # had this cycle instead been reached by continuation).
                reference_file_for_cycle = cfg.first_cycle_modelfile
                self.log(f"[Cycle reference] Auto referencefile (Initial model): {reference_file_for_cycle}", level="DETAIL")
            # 2.0.0: the scientific map grid is never coarsened to satisfy the
            # SharpED upload-size limit -- Superflip always uses the grid the
            # user/settings actually intend. A map exceeding the limit goes
            # through tiled SharpED inference instead (sharped_tiling.py),
            # inside run_sharped_deblur, on the map SharpED actually receives.
            sf_voxel = cfg.voxel
            sf_extra_superflip_keywords = cfg.extra_superflip_keywords
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
            saved_sf_map = checkpoint.values.get("superflip_map")
            if (
                checkpoint.superflip_completed
                and isinstance(saved_sf_map, Path)
                and saved_sf_map.is_file()
                and saved_sf_map.stat().st_size > 0
            ):
                sf_map = saved_sf_map
                self.log(f"[Continue] Reusing completed Superflip map: {sf_map}")
                sf_progress_relay = None
            else:
                checkpoint.invalidate_from("superflip")
                self.log("Superflip started", level="INFO", subsystem="Superflip")
                sf_map = self._run_display_operation(state, cyc, "Superflip", lambda: run_superflip_cycle(cycle_dir, sf_prefix, ref_ctx, observed_hkl_for_cycle, model_for_sf, reference_file_for_cycle, reference_format_for_cycle, cfg.superflip_exe, cfg.perform_algorithm, "xplor", sf_export_jana, True, sf_export_ccp4, sf_export_jana, sf_voxel, cfg.bestdensities_count, cfg.bestdensities_metric, cfg.bestdensities_symmetry, cfg.polish, cfg.maxcycles, cfg.repeatmode, cfg.randomseed, cfg.delta, cfg.weakratio, cfg.biso, configured_data_mode, cfg.normalize, cfg.nresshells, cfg.missing, cfg.searchsymmetry, cfg.derivesymmetry, cfg.electrons, cfg.dataitemwidths, sf_extra_superflip_keywords, superflip_log, self.stop_now, on_output_line=sf_progress_relay, profiler=state.performance_profiler))
                checkpoint.values["superflip_map"] = sf_map
                checkpoint.superflip_completed = True
                self.log("Superflip complete", level="SUCCESS", subsystem="Superflip")
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
            omit_sf_quality: Optional[MapQualityMetrics] = None
            if cfg.compute_omit_maps and state.omit_test_hkls:
                self._emit_cycle_progress(cyc, cfg.cycles, progress_stages, "Superflip", detail="omit map · running", busy=True)
                omit_reflections = [r for r in state.current_reflections if (int(r.h), int(r.k), int(r.l)) not in state.omit_test_hkls]
                omit_hkl = cycle_dir / f"{sf_prefix}_omit_input.hkl"
                write_observed_reflections(omit_hkl, omit_reflections, cfg.i_over_sigma_min, data_mode=configured_data_mode, cell=ref_ctx.cell, resolution_d_min=cfg.resolution_d_min)
                omit_prefix = f"{sf_prefix}_omit"
                omit_progress_relay = make_superflip_progress_relay("omit map · running")
                saved_omit_sf_map = checkpoint.values.get("omit_superflip_map")
                if (
                    isinstance(saved_omit_sf_map, Path)
                    and saved_omit_sf_map.is_file()
                    and saved_omit_sf_map.stat().st_size > 0
                ):
                    omit_sf_map = saved_omit_sf_map
                    omit_progress_relay = None
                else:
                    omit_sf_map = self._run_display_operation(state, cyc, "Superflip", lambda: run_superflip_cycle(cycle_dir, omit_prefix, ref_ctx, omit_hkl, model_for_sf, reference_file_for_cycle, reference_format_for_cycle, cfg.superflip_exe, cfg.perform_algorithm, "xplor", False, True, False, False, sf_voxel, cfg.bestdensities_count, cfg.bestdensities_metric, cfg.bestdensities_symmetry, cfg.polish, cfg.maxcycles, cfg.repeatmode, cfg.randomseed, cfg.delta, cfg.weakratio, cfg.biso, configured_data_mode, cfg.normalize, cfg.nresshells, cfg.missing, cfg.searchsymmetry, cfg.derivesymmetry, cfg.electrons, cfg.dataitemwidths, sf_extra_superflip_keywords, superflip_log, self.stop_now, on_output_line=omit_progress_relay, profiler=state.performance_profiler))
                    checkpoint.values["omit_superflip_map"] = omit_sf_map
                self.log(f"Omit Superflip map ({len(state.omit_test_hkls)} reflections excluded): {omit_sf_map}")
                omit_sf_correlation = xplor_map_correlation(sf_map, omit_sf_map)
                if state.validation_context is not None:
                    omit_sf_quality = assess_xplor_map(omit_sf_map, state.validation_context, state.performance_profiler)
                    omit_sf_rfree = omit_sf_quality.r_free
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
            sharped_future: Optional[Future] = None
            if cfg.run_edma_superflip:
                sf_structure_job = self._new_structure_job(
                    state, "superflip", cyc, sf_map, cfg.plimit_superflip,
                    superflip_initialization={
                        "none": "Random phase start",
                        "deblurred_xplor": "SharpED-seeded",
                        "deblurred_edma_cif": "SharpED structure-seeded",
                        "superflip_xplor": "Charge-flipping-map seeded",
                        "external_first_cycle": "External model-seeded",
                    }.get(str(model_source).casefold(), "Recorded model seed"),
                    reflection_input_provenance=(
                        "Map Feedback-adjusted reflection data"
                        if state.pending_intensity_correction_change_percent is not None
                        or state.pending_powder_repartition_change_percent is not None
                        else "Original measured reflection data"
                    ),
                )
                self._emit_cycle_progress(cyc, cfg.cycles, progress_stages, "EDMA · Superflip map", busy=True)
                saved_sf_edma_cif = checkpoint.values.get("superflip_edma_cif")
                if (
                    checkpoint.superflip_edma_completed
                    and isinstance(saved_sf_edma_cif, Path)
                    and saved_sf_edma_cif.is_file()
                    and saved_sf_edma_cif.stat().st_size > 0
                ):
                    sf_edma_cif = saved_sf_edma_cif
                    self.log(f"[Continue] Reusing completed EDMA/Superflip structure: {sf_edma_cif}")
                    self._structure_job_status(sf_structure_job, "complete", sf_edma_cif)
                else:
                    # SharpED is a sibling consumer of the completed Superflip
                    # map, not a descendant of this EDMA branch. Preserve an
                    # independently completed SharpED map across Continue.
                    checkpoint.superflip_edma_completed = False
                    checkpoint.superflip_validation_completed = False
                    checkpoint.validation_completed = False
                    checkpoint.result_recorded = False
                    checkpoint.feedback_completed = False
                    checkpoint.continuation_completed = False
                    self.log(
                        f"[Cycle {cyc}][EDMA:Superflip] started",
                        level="DETAIL", subsystem="EDMA",
                    )
                    def run_superflip_edma_branch() -> Path:
                        self._structure_job_status(sf_structure_job, "running")
                        structure = self._run_configured_edma_stage(
                            state, sf_map, sf_edma_dir, sf_prefix, cfg.plimit_superflip,
                        )
                        self._structure_job_status(sf_structure_job, "complete", structure)
                        return structure

                    sf_edma_future = branch_executor.submit(run_superflip_edma_branch)
                    # The primary SharpED request consumes the same closed map
                    # and has no dependency on the EDMA structure. Start it now
                    # instead of placing it behind EDMA's process wait.
                    deblur_map_for_future = cycle_dir / f"cycle_{cyc:03d}_deblurred.xplor"
                    if cfg.run_sharped and not use_superflip_xplor_modelfile and not checkpoint.sharped_completed:
                        checkpoint.invalidate_from("sharped")
                        self.log(
                            f"[Cycle {cyc}][SharpED] upload started",
                            level="DETAIL", subsystem="SharpED",
                        )
                        def run_primary_sharped_branch() -> Path:
                            result_path = self._run_configured_sharped_stage(
                                state, sf_map, deblur_map_for_future, cyc, progress_stages,
                            )
                            # Preserve this independently completed branch even
                            # if the concurrent Superflip-map EDMA branch fails.
                            checkpoint.values["deblur_map"] = result_path
                            checkpoint.sharped_completed = True
                            return result_path

                        sharped_future = branch_executor.submit(run_primary_sharped_branch)
                    try:
                        sf_edma_cif = sf_edma_future.result()
                    except BaseException:
                        # The SharpED branch is independent. Let it finish and
                        # checkpoint its valid map before reporting only the
                        # failed EDMA candidate branch.
                        if sharped_future is not None:
                            try:
                                sharped_future.result()
                            except BaseException:
                                pass
                        branch_executor.shutdown(wait=True, cancel_futures=False)
                        raise
                    self.log(
                        f"[Cycle {cyc}][EDMA:Superflip] complete",
                        level="DETAIL", subsystem="EDMA",
                    )
                    checkpoint.values["superflip_edma_cif"] = sf_edma_cif
                    checkpoint.superflip_edma_completed = True
            else:
                sf_edma_dir.mkdir(parents=True, exist_ok=True)
                sf_edma_cif = sf_edma_dir / f"{sf_prefix}_edma.cif"
                write_structure_bundle(sf_edma_cif, ref_ctx.cell, ref_ctx.spacegroup, ref_ctx.spacegroup_hm, [], cfg.structure_export_format)
                self.log("EDMA after Superflip disabled; empty placeholder CIF/XYZ/PDB written.")
                checkpoint.values["superflip_edma_cif"] = sf_edma_cif
                checkpoint.superflip_edma_completed = True
            sf_metric, sf_match = self._edma_reference_metrics(
                sf_edma_cif, ref_ctx, cfg.merge_distance, cfg.run_edma_superflip
            )
            sf_metric_text = "n/a" if sf_metric is None else f"{float(sf_metric):.3f}"
            sf_recall: Optional[float] = None
            sf_precision: Optional[float] = None
            sf_tp: Optional[int] = None
            sf_fp: Optional[int] = None
            sf_heavy_atoms: Optional[float] = None
            if cfg.run_edma_superflip:
                if sf_match is not None:
                    sf_recall, sf_precision, sf_tp, sf_fp = sf_match
                else:
                    sf_heavy_atoms = count_heavy_atoms(sf_edma_cif)
            sf_quality: Optional[MapQualityMetrics] = None
            if state.validation_context is not None:
                saved_sf_quality = checkpoint.values.get("superflip_quality")
                if checkpoint.superflip_validation_completed and isinstance(saved_sf_quality, MapQualityMetrics):
                    sf_quality = saved_sf_quality
                else:
                    sf_quality = assess_xplor_map(sf_map, state.validation_context, state.performance_profiler)
                    sf_quality = with_reference_metrics(
                        sf_quality,
                        precision=sf_precision,
                        recall=sf_recall,
                        rmsd=sf_metric,
                        true_positives=sf_tp,
                        false_positives=sf_fp,
                    )
                    if state.omit_test_hkls:
                        sf_quality = with_holdout_metrics(
                            sf_quality, sf_quality, omit_sf_correlation,
                        )
                    checkpoint.values["superflip_quality"] = sf_quality
                    checkpoint.superflip_validation_completed = True
            else:
                checkpoint.superflip_validation_completed = True
            self.log(
                f"Charge-flipping solution · EDMA complete · {len(parse_cif_atoms(sf_edma_cif)):,} sites detected · "
                f"{float(cfg.plimit_superflip):.2f} σ"
                + (f" · RMSD {float(sf_metric):.3f} Å" if sf_metric is not None else ""),
                level="SUCCESS", subsystem="EDMA",
            )
            deblur_map = cycle_dir / f"cycle_{cyc:03d}_deblurred.xplor"
            if cfg.run_sharped and not use_superflip_xplor_modelfile:
                saved_deblur_map = checkpoint.values.get("deblur_map")
                if (
                    checkpoint.sharped_completed
                    and isinstance(saved_deblur_map, Path)
                    and saved_deblur_map.is_file()
                    and saved_deblur_map.stat().st_size > 0
                ):
                    deblur_map = saved_deblur_map
                    self.log(f"[Continue] Reusing completed SharpED map: {deblur_map}")
                else:
                    checkpoint.invalidate_from("sharped")
                    if self.stop_now.is_set():
                        raise RuntimeError("Immediate stop requested.")
                    if sharped_future is not None:
                        deblur_map = Path(sharped_future.result())
                    else:
                        self._run_configured_sharped_stage(
                            state, sf_map, deblur_map, cyc, progress_stages
                        )
                    self.log(
                        f"[Cycle {cyc}][SharpED] map complete",
                        level="DETAIL", subsystem="SharpED",
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
            omit_deblur_quality: Optional[MapQualityMetrics] = None
            if checkpoint.sharped_completed:
                omit_deblur_correlation = checkpoint.values.get("omit_deblur_correlation")  # type: ignore[assignment]
                omit_deblur_rfree = checkpoint.values.get("omit_deblur_rfree")  # type: ignore[assignment]
                omit_deblur_quality = checkpoint.values.get("omit_deblur_quality")  # type: ignore[assignment]
            if (not checkpoint.sharped_completed and cfg.compute_omit_maps and state.omit_test_hkls
                    and omit_sf_map is not None and cfg.run_sharped and not use_superflip_xplor_modelfile):
                if self.stop_now.is_set():
                    raise RuntimeError("Immediate stop requested.")
                omit_deblur_map = cycle_dir / f"{sf_prefix}_omit_deblurred.xplor"
                self._run_configured_sharped_stage(
                    state, omit_sf_map, omit_deblur_map, cyc, progress_stages,
                    detail_prefix="omit map · ",
                )
                self.log(f"Omit {result_map_label('deblurred')}: {omit_deblur_map}")
                omit_deblur_correlation = xplor_map_correlation(deblur_map, omit_deblur_map)
                if state.validation_context is not None:
                    omit_deblur_quality = assess_xplor_map(omit_deblur_map, state.validation_context, state.performance_profiler)
                    omit_deblur_rfree = omit_deblur_quality.r_free
                self.log(
                    f"[Omit] {result_map_label('deblurred')} correlation={('n/a' if omit_deblur_correlation is None else f'{omit_deblur_correlation:.4f}')}"
                    f" · R_free={('n/a' if omit_deblur_rfree is None else f'{omit_deblur_rfree:.4f}')}",
                    subsystem="SharpED",
                )
            if not checkpoint.sharped_completed and cfg.symmetrize_deblurred_map and not use_superflip_xplor_modelfile:
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
                    profiler=state.performance_profiler,
                )
            checkpoint.values["omit_deblur_correlation"] = omit_deblur_correlation
            checkpoint.values["omit_deblur_rfree"] = omit_deblur_rfree
            checkpoint.values["omit_deblur_quality"] = omit_deblur_quality
            checkpoint.values["deblur_map"] = deblur_map
            checkpoint.sharped_completed = True
            deblur_prefix = f"cycle_{cyc:03d}_deblurred"
            deblur_edma_dir = cycle_dir / "edma_deblurred"
            if cfg.run_edma_deblurred and not use_superflip_xplor_modelfile:
                deblur_structure_job = self._new_structure_job(
                    state, "deblurred", cyc, deblur_map, cfg.plimit_deblur,
                )
                self._emit_cycle_progress(cyc, cfg.cycles, progress_stages, f"EDMA · {result_map_label('deblurred')}", busy=True)
                saved_deblur_edma_cif = checkpoint.values.get("deblur_edma_cif")
                if (
                    checkpoint.sharped_edma_completed
                    and isinstance(saved_deblur_edma_cif, Path)
                    and saved_deblur_edma_cif.is_file()
                    and saved_deblur_edma_cif.stat().st_size > 0
                ):
                    deblur_edma_cif = saved_deblur_edma_cif
                    self.log(f"[Continue] Reusing completed EDMA/SharpED structure: {deblur_edma_cif}")
                    self._structure_job_status(deblur_structure_job, "complete", deblur_edma_cif)
                else:
                    checkpoint.invalidate_from("sharped_edma")
                    self._structure_job_status(deblur_structure_job, "running")
                    deblur_edma_cif = self._run_configured_edma_stage(
                        state, deblur_map, deblur_edma_dir, deblur_prefix, cfg.plimit_deblur,
                    )
                    self._structure_job_status(deblur_structure_job, "complete", deblur_edma_cif)
                    checkpoint.values["deblur_edma_cif"] = deblur_edma_cif
                    checkpoint.sharped_edma_completed = True
            else:
                deblur_edma_dir.mkdir(parents=True, exist_ok=True)
                deblur_edma_cif = deblur_edma_dir / f"{deblur_prefix}_edma.cif"
                write_structure_bundle(deblur_edma_cif, ref_ctx.cell, ref_ctx.spacegroup, ref_ctx.spacegroup_hm, [], cfg.structure_export_format)
                if use_superflip_xplor_modelfile:
                    self.log(f"EDMA after {result_map_label('deblurred').lower()} skipped for Superflip XPLOR cycling; empty placeholder CIF/XYZ/PDB written.")
                else:
                    self.log(f"EDMA after {result_map_label('deblurred').lower()} disabled; empty placeholder CIF/XYZ/PDB written.")
                checkpoint.values["deblur_edma_cif"] = deblur_edma_cif
                checkpoint.sharped_edma_completed = True
            deblur_metric, deblur_match = self._edma_reference_metrics(
                deblur_edma_cif, ref_ctx, cfg.merge_distance, cfg.run_edma_deblurred
            )
            deblur_metric_text = "n/a" if deblur_metric is None else f"{float(deblur_metric):.3f}"
            deblur_recall: Optional[float] = None
            deblur_precision: Optional[float] = None
            deblur_tp: Optional[int] = None
            deblur_fp: Optional[int] = None
            deblur_heavy_atoms: Optional[float] = None
            if cfg.run_edma_deblurred:
                if deblur_match is not None:
                    deblur_recall, deblur_precision, deblur_tp, deblur_fp = deblur_match
                else:
                    deblur_heavy_atoms = count_heavy_atoms(deblur_edma_cif)
            deblur_quality: Optional[MapQualityMetrics] = None
            if cfg.run_sharped and not use_superflip_xplor_modelfile and state.validation_context is not None:
                saved_deblur_quality = checkpoint.values.get("deblur_quality")
                if checkpoint.validation_completed and isinstance(saved_deblur_quality, MapQualityMetrics):
                    deblur_quality = saved_deblur_quality
                else:
                    deblur_quality = assess_xplor_map(deblur_map, state.validation_context, state.performance_profiler)
                    deblur_quality = with_reference_metrics(
                        deblur_quality,
                        precision=deblur_precision,
                        recall=deblur_recall,
                        rmsd=deblur_metric,
                        true_positives=deblur_tp,
                        false_positives=deblur_fp,
                    )
                    if state.omit_test_hkls:
                        deblur_quality = with_holdout_metrics(
                            deblur_quality, deblur_quality, omit_deblur_correlation,
                        )
                    checkpoint.values["deblur_quality"] = deblur_quality
            checkpoint.validation_completed = True
            self._emit_cycle_progress(cyc, cfg.cycles, progress_stages, "Finalizing cycle", detail="calculating metrics")
            self.log(
                f"Structure prediction · EDMA complete · {len(parse_cif_atoms(deblur_edma_cif)):,} sites detected · "
                f"{float(cfg.plimit_deblur):.2f} σ"
                + (f" · RMSD {float(deblur_metric):.3f} Å" if deblur_metric is not None else ""),
                level="SUCCESS", subsystem="EDMA",
            )
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
                validation_profile=self._validation_profile_for_result(state),
                superflip_quality=sf_quality,
                deblur_quality=deblur_quality,
            )
            existing_result = next(
                (item for item in state.all_results if item.cycle == cyc), None,
            )
            if checkpoint.result_recorded and existing_result is not None:
                result = existing_result
            else:
                checkpoint.result_recorded = False
                self._record_completed_cycle_result(state, result)
                checkpoint.result_recorded = True
            state.pending_powder_repartition_change_percent = None
            state.pending_intensity_correction_change_percent = None
            if cyc < cfg.cycles and not checkpoint.feedback_completed:
                add_missing = cfg.map_feedback_missing_enabled and cyc >= cfg.map_feedback_missing_from_cycle and cfg.map_feedback_missing_percent_limit > 0
                correct_intensities = cfg.map_feedback_intensity_enabled and cyc >= cfg.map_feedback_intensity_from_cycle and cfg.map_feedback_intensity_damping > 0
                redistribute = cfg.redistribute_overlaps and cyc >= cfg.powder_redistribution_from_cycle and cfg.powder_wavelength > 0
                if cfg.redistribute_overlaps and cyc >= cfg.powder_redistribution_from_cycle and cfg.powder_wavelength <= 0:
                    self.log("Overlap repartitioning enabled but Wavelength is 0; skipping for this cycle.", level="WARNING")
                if add_missing or correct_intensities or redistribute:
                    feedback_reflections = state.current_reflections
                    intensity_change = None
                    powder_change = None
                    if add_missing or correct_intensities:
                        feedback_reflections, intensity_change = apply_map_feedback_to_reflections(
                            feedback_reflections,
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
                            excluded_hkls=state.omit_test_hkls,
                        )
                    if redistribute:
                        feedback_reflections, powder_change = redistribute_overlap_reflections(
                            feedback_reflections,
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
                        feedback_reflections,
                        cfg.i_over_sigma_min,
                        data_mode=configured_data_mode,
                        cell=ref_ctx.cell,
                        resolution_d_min=cfg.resolution_d_min,
                    )
                    observed_hkls[configured_data_mode] = feedback_hkl
                    state.current_reflections = feedback_reflections
                    state.pending_intensity_correction_change_percent = intensity_change
                    state.pending_powder_repartition_change_percent = powder_change
                    self.log(f"Prepared map-feedback HKL for cycle {cyc + 1}: {feedback_hkl} ({n_feedback} reflections)")
            checkpoint.feedback_completed = True
            if not checkpoint.continuation_completed and use_xplor_modelfile:
                next_xplor_model = sf_map if use_superflip_xplor_modelfile else deblur_map
                effective_damping = effective_xplor_damping_factor(cfg.damping_factor)
                if state.current_model is not None and effective_damping > 1.0:
                    damped_model = cycle_dir / f"cycle_{cyc:03d}_damped_modelfile.xplor"
                    state.current_model = blend_xplor_maps(state.current_model, next_xplor_model, damped_model, effective_damping, self.log)
                else:
                    state.current_model = next_xplor_model
                state.current_model_metric = sf_metric if use_superflip_xplor_modelfile else deblur_metric
            elif not checkpoint.continuation_completed and use_cif_modelfile:
                if cfg.run_edma_deblurred:
                    state.current_model = deblur_edma_cif
                    state.current_model_metric = deblur_metric
                elif cfg.run_edma_superflip:
                    state.current_model = sf_edma_cif
                    state.current_model_metric = sf_metric
                else:
                    state.current_model = None
                    state.current_model_metric = None
            elif not checkpoint.continuation_completed:
                state.current_model = None
                state.current_model_metric = None
            if not checkpoint.continuation_completed and cfg.run_edma_deblurred and not use_superflip_xplor_modelfile and cif_has_readable_atoms(deblur_edma_cif):
                state.auto_reference_cif = edma_scientific_source_cif(deblur_edma_cif)
            elif not checkpoint.continuation_completed and cfg.run_edma_superflip and cif_has_readable_atoms(sf_edma_cif):
                state.auto_reference_cif = edma_scientific_source_cif(sf_edma_cif)
            elif not checkpoint.continuation_completed:
                state.auto_reference_cif = None
            if not checkpoint.continuation_completed:
                state.auto_reference_xplor = deblur_map
                checkpoint.continuation_completed = True
            if self._finalize_completed_cycle(state, cyc, progress_stages):
                branch_executor.shutdown(wait=True, cancel_futures=False)
                return
            state.ordinary_cycle_checkpoint = None
        branch_executor.shutdown(wait=True, cancel_futures=False)
        self._queue_run_event("done", state.completed_cycles, state.run_id)

    def _run_sharped_recycle_cycles(self, state: PipelineState) -> None:
        """SharpED phase-recycling algorithm: Superflip runs at most once (or not at
        all in the random-start variant); every cycle deblurs the previous map with
        SharpED, reads phi_calc by FFT from that deblurred map for every measured
        hkl, and recomposes a map from |Fobs| + phi_calc for the next cycle."""
        cfg = state.cfg
        ref_ctx = state.ref_ctx
        reflections = state.current_reflections
        configured_data_mode = state.configured_data_mode
        random_start = normalize_reconstruction_mode(cfg.reconstruction_mode) == "sharped_recycle_random"
        progress_stages = ["Preparing cycle", "Superflip", "SharpED", "Phase calculation", "Finalizing cycle"]
        for cyc in range(state.completed_cycles + 1, cfg.cycles + 1):
            if self._emit_requested_workflow_stop(state.completed_cycles):
                return
            self._emit_cycle_progress(cyc, cfg.cycles, progress_stages, "Preparing cycle", detail="preparing input map")
            cycle_dir = cfg.work_dir / f"cycle_{cyc:03d}"; cycle_dir.mkdir(parents=True, exist_ok=True)
            self.log(f"Cycle {cyc} of {cfg.cycles} · SharpED phase recycling", level="STEP")

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
                        profiler=state.performance_profiler,
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
            deblur_map = cycle_dir / f"cycle_{cyc:03d}_deblurred.xplor"
            self._run_configured_sharped_stage(
                state, input_map, deblur_map, cyc, progress_stages
            )
            self.log(f"{result_map_label('deblurred')}: {deblur_map}")
            if self.stop_now.is_set():
                raise RuntimeError("Immediate stop requested.")

            self._emit_cycle_progress(cyc, cfg.cycles, progress_stages, "Phase calculation", busy=True)
            composed_map = cycle_dir / f"cycle_{cyc:03d}_fobs_phicalc.xplor"
            with profile_stage(state.performance_profiler, "Phase recycling Fourier composition"):
                compose_fobs_phicalc_map(composed_map, reflections, configured_data_mode, deblur_map, f"cycle_{cyc:03d}_fobs_phicalc", ref_ctx.spacegroup, self.log)
            self.log(f"Composed |Fobs|+phi_calc map: {composed_map}")
            map_correlation = xplor_map_correlation(composed_map, input_map)
            if map_correlation is not None:
                self.log(f"[Cycle {cyc}] Map correlation vs. previous cycle: {map_correlation:.4f}", level="DETAIL")
            state.recycle_map = composed_map

            is_final_cycle = cyc == cfg.cycles
            deblur_edma_cif = cycle_dir / f"cycle_{cyc:03d}_edma.cif"
            deblur_metric: Optional[float] = None
            deblur_recall: Optional[float] = None
            deblur_precision: Optional[float] = None
            deblur_tp: Optional[int] = None
            deblur_fp: Optional[int] = None
            if is_final_cycle and cfg.run_edma_recycle_final:
                self._emit_cycle_progress(cyc, cfg.cycles, progress_stages, "Finalizing cycle", detail="EDMA on final map", busy=True)
                edma_dir = cycle_dir / "edma_final"
                deblur_edma_cif = self._run_configured_edma_stage(
                    state, composed_map, edma_dir, f"cycle_{cyc:03d}_final",
                    cfg.plimit_deblur,
                )
                deblur_metric, match = self._edma_reference_metrics(
                    deblur_edma_cif, ref_ctx, cfg.merge_distance, True
                )
                if match is not None:
                    deblur_recall, deblur_precision, deblur_tp, deblur_fp = match
                self.log(f"[EDMA] Completed · Final map · output: {deblur_edma_cif}", subsystem="EDMA")
                self._queue_run_event("structure_update", ("deblur", deblur_edma_cif), state.run_id)
            else:
                write_structure_bundle(deblur_edma_cif, ref_ctx.cell, ref_ctx.spacegroup, ref_ctx.spacegroup_hm, [], cfg.structure_export_format)

            superflip_quality: Optional[MapQualityMetrics] = None
            deblur_quality: Optional[MapQualityMetrics] = None
            if state.validation_context is not None:
                if cyc == 1 and not random_start:
                    superflip_quality = assess_xplor_map(input_map, state.validation_context, state.performance_profiler)
                deblur_quality = assess_xplor_map(composed_map, state.validation_context, state.performance_profiler)
                deblur_quality = with_reference_metrics(
                    deblur_quality,
                    precision=deblur_precision,
                    recall=deblur_recall,
                    rmsd=deblur_metric,
                    true_positives=deblur_tp,
                    false_positives=deblur_fp,
                )

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
                validation_profile=self._validation_profile_for_result(state),
                superflip_quality=superflip_quality,
                deblur_quality=deblur_quality,
            )
            self._record_completed_cycle_result(state, result)
            if self._finalize_completed_cycle(state, cyc, progress_stages):
                return
        self._queue_run_event("done", state.completed_cycles, state.run_id)


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
        title = QLabel("PHASE STUDIO")
        title.setObjectName("splashTitle")
        title.setFont(phase_studio_brand_font(title.font()))
        title.setProperty("resolvedBrandFontFamily", QFontInfo(title.font()).family())
        subtitle = QLabel(
            '<span style="color:#52658b;">by </span>'
            '<span style="color:#2264b8; font-weight:600;">SharpED</span>'
        )
        subtitle.setObjectName("splashSubtitle")
        subtitle.setTextFormat(Qt.RichText)
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
        self.progress.setRange(0, 100)
        self.progress.setValue(12)
        self.progress.setTextVisible(False)
        root.addWidget(self.progress)
        footer = QLabel("Crystallographic reconstruction workspace")
        footer.setObjectName("splashFooter")
        root.addWidget(footer)
        root.addStretch(1)

    def set_status(self, text: str, progress: Optional[int] = None) -> None:
        self.status_label.setText(str(text))
        if progress is None:
            lowered = str(text).casefold()
            if "initializ" in lowered:
                progress = 38
            elif "jana2020" in lowered:
                progress = 62
            elif "finaliz" in lowered:
                progress = 86
            elif lowered.strip() == "ready":
                progress = 100
        if progress is not None:
            self.progress.setValue(max(self.progress.value(), min(100, int(progress))))


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
    apply_phase_studio_app_icon(app)
    apply_phase_studio_style(app)
    splash = create_startup_splash()
    splash.show()
    app.processEvents()
    close_bootloader_splash()
    win = initialize_main_window(app, splash)
    if win is None:
        raise SystemExit(1)
    if os.environ.get("PHASE_STUDIO_STARTUP_PROBE") == "1":
        QTimer.singleShot(250, app.quit)
    raise SystemExit(app.exec())

if __name__ == "__main__":
    main()
