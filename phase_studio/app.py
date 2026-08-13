#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase Studio Qt application.

Iterative Superflip -> optional SharpED server deblur -> EDMA reconstruction with
persistent settings and standardized metric plotting.

Reference CIF supplies cell, symmetry, composition and metrics. Superflip
referencefile is optional and is written only when the user explicitly
selects an external reference file (CIF/Jana/XPLOR/CCP4). The first Superflip run has no
modelfile. Later cycles can use EDMA CIF coordinates, raw Superflip XPLOR, or
deblurred XPLOR as Superflip modelfile.

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
import locale
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
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

try:
    from phase_studio.sharped_server_client import SharpEDServerClient
except Exception:
    from sharped_server_client import SharpEDServerClient

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
    from PySide6.QtCore import Qt, QTimer, QSettings, QUrl, QRectF
    from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QKeySequence, QPainter, QPen, QPixmap, QShortcut
    from PySide6.QtWidgets import (
        QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
        QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
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
    from matplotlib.figure import Figure
    from matplotlib.lines import Line2D
    from matplotlib.ticker import MaxNLocator
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
class ReferenceContext:
    cif_path: Path
    work_ref_cif: Path
    cell: gemmi.UnitCell
    spacegroup: gemmi.SpaceGroup
    spacegroup_hm: str
    composition: str
    atoms: List[AtomSite]

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


INPUT_MODE_INFLIP = "jana_inflip"
INPUT_MODE_INFLIP_OVERRIDES = "jana_inflip_overrides"
INPUT_MODE_EXTERNAL = "external_hkl_cif"

INPUT_MODE_LABELS = {
    INPUT_MODE_INFLIP: "Jana .inflip",
    INPUT_MODE_INFLIP_OVERRIDES: "Jana .inflip with external HKL/reference overrides",
    INPUT_MODE_EXTERNAL: "External HKL + CIF reference",
}

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
    exclude_atoms: str
    perform_algorithm: str
    output_format: str
    write_auxiliary_outputs: bool
    export_superflip_xplor: bool
    export_superflip_ccp4: bool
    export_superflip_jana: bool
    export_standard_hkl: bool
    export_jana_project: bool
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
    map_feedback_missing_from_cycle: int
    map_feedback_missing_percent_limit: float
    map_feedback_intensity_from_cycle: int
    map_feedback_intensity_damping: float
    map_feedback_intensity_max_i_over_sigma: float
    run_sharped: bool
    symmetrize_deblurred_map: bool
    run_edma_superflip: bool
    run_edma_deblurred: bool
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

def load_reference_context(reference_cif: Path, work_dir: Path, composition_override: str = "") -> ReferenceContext:
    cell, sg, hm = parse_cif_cell_and_sg(reference_cif)
    if min(cell.a, cell.b, cell.c) <= 2.0:
        raise ValueError(f"Unphysical reference cell parsed from CIF: {cell.a} {cell.b} {cell.c}")
    atoms = parse_cif_atoms(reference_cif)
    if not atoms:
        # Jana .inflip files can provide a complete cell/space-group/reflection
        # definition without atomic coordinates.  In that mode Phase Studio can
        # still run Superflip, SharpED, EDMA and parse Superflip quality metrics;
        # only reference-coordinate RMSD is unavailable.
        atoms = []
    formula_comp = composition_from_formula(raw_cif_value(reference_cif, ["_chemical_formula_sum", "_chemical_formula_moiety"]))
    full_cell_comp = composition_from_full_cell_atoms(atoms, cell, sg)
    comp = composition_override.strip() if composition_override.strip() else (full_cell_comp or formula_comp or composition_from_atoms(atoms))
    work_ref = work_dir / "phase_studio_reference_for_metrics.cif"
    # Write a clean reference CIF for EDMA metrics and downstream structure handling. This is
    # safer than copying database CIFs with multiple blocks or unusual tags.
    write_structure_cif(work_ref, cell, sg, hm, atoms)
    return ReferenceContext(reference_cif, work_ref, cell, sg, hm, comp, atoms)



def reference_context_with_external_atom_sites(
    ref_ctx: ReferenceContext,
    external_cif: Optional[Path],
    work_dir: Path,
    composition_override: str = "",
    log: Optional[Callable[[str], None]] = None,
) -> ReferenceContext:
    """Use atom sites from an explicit reference CIF without replacing Jana HKL.

    In Jana .inflip mode, Phase Studio can synthesize a metadata-only CIF from
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

# -----------------------------------------------------------------------------
# HKL / Superflip / SharpED / EDMA
# -----------------------------------------------------------------------------

def normalize_reflection_data_mode(value: str) -> str:
    mode = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
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
    }
    mode = aliases.get(mode, mode)
    if mode == REFLECTION_DATA_MODE_AUTO:
        return REFLECTION_DATA_MODE_AUTO
    if mode in {
        REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA,
        REFLECTION_DATA_MODE_INTENSITY_PHASE_SIGMA,
        REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA,
    }:
        return mode
    return REFLECTION_DATA_MODE_INTENSITY


def reflection_mode_is_amplitude(data_mode: str) -> bool:
    return normalize_reflection_data_mode(data_mode) in {
        REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA,
        REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA,
    }


def reflection_mode_has_phase(data_mode: str) -> bool:
    return normalize_reflection_data_mode(data_mode) in {
        REFLECTION_DATA_MODE_INTENSITY_PHASE_SIGMA,
        REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA,
    }


def superflip_dataformat_for_mode(data_mode: str) -> str:
    quantity = "amplitude" if reflection_mode_is_amplitude(data_mode) else "intensity"
    return f"{quantity} phase dummy" if reflection_mode_has_phase(data_mode) else f"{quantity} dummy"

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
    if reflection_mode_is_amplitude(data_mode):
        return "sigma(Fobs)"
    return "sigma(Iobs)"

def reflection_primary_snr_label(data_mode: str) -> str:
    return "I/sigma(I)"

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

def write_standardized_hkl_with_phase(out_hkl: Path, reflections: Sequence[Reflection], i_over_sigma_min: float = 0.0, data_mode: str = REFLECTION_DATA_MODE_INTENSITY, cell: Optional[gemmi.UnitCell] = None, resolution_d_min: float = 0.0) -> int:
    out_hkl.parent.mkdir(parents=True, exist_ok=True)
    mode = normalize_reflection_data_mode(data_mode)
    d_min = max(0.0, float(resolution_d_min or 0.0))
    n = 0
    with out_hkl.open("w", encoding="utf-8") as f:
        f.write("# h k l I sigma(I) phase(deg)\n")
        f.write("# Phase Studio 1.0.1 standardized HKL export; phase is 0.0 unless supplied by the selected HKL mode.\n")
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
            phase = 0.0 if r.phase is None else float(r.phase)
            f.write(f"{r.h:5d} {r.k:5d} {r.l:5d} {intensity:14.7f} {sigma_i:14.7f} {phase:12.6f}\n")
            n += 1
    return n

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
) -> List[Reflection]:
    mode = normalize_reflection_data_mode(data_mode)
    current = [Reflection(int(r.h), int(r.k), int(r.l), float(r.value), r.sigma, r.phase) for r in reflections]
    if not current:
        return current
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
            else:
                corrected_reflections.append(r)
        current = corrected_reflections
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
        f"intensity_max_i_over_sigma={max_i_over_sigma:g}, reflections={len(current)}"
    )
    return current

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
        raise RuntimeError("Cannot damp XPLOR modelfile: previous model and deblurred map have different grids")
    if len(old_map.cell) != len(new_map.cell) or any(abs(a - b) > 1e-3 for a, b in zip(old_map.cell, new_map.cell)):
        raise RuntimeError("Cannot damp XPLOR modelfile: previous model and deblurred map have different cells")
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
        raise ValueError(f"No fbegin/endf reflection block was found in Jana .inflip: {inflip_path}")
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
    hm = "P 1"
    composition = "C1"
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
        raise ValueError(f"Jana .inflip does not contain a readable cell keyword: {inflip_path}")
    sg = get_spacegroup_from_number(hm) if re.fullmatch(r"\d+(?:\.0+)?", str(hm).strip()) else None
    if sg is None:
        sg = get_spacegroup_from_name(hm)
    try:
        hm_out = str(sg.hm).strip() or hm
    except Exception:
        hm_out = hm
    return gemmi.UnitCell(*cell_values), sg, hm_out, composition

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


def write_reference_cif_from_inflip(inflip_path: Path, output_cif: Path) -> Path:
    cell, sg, hm, composition = parse_inflip_crystallography(inflip_path)
    output_cif.parent.mkdir(parents=True, exist_ok=True)
    write_structure_cif(output_cif, cell, sg, hm, [])
    # Add formula tags used by Phase Studio/Superflip composition handling.
    with output_cif.open("a", encoding="utf-8") as f:
        f.write(f"_chemical_formula_sum '{composition}'\n")
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
    encoding = "mbcs" if os.name == "nt" else (locale.getpreferredencoding(False) or "utf-8")
    path.write_bytes(text.encode(encoding, errors="replace"))


def return_phase_studio_result_to_jana(
    cfg: RunConfig,
    result: CycleResult,
    log: Callable[[str], None],
    stop_event: Optional[threading.Event] = None,
    map_source: str = "deblurred",
) -> None:
    if not cfg.jana_return_to_jana or cfg.jana_inflip is None:
        raise RuntimeError("Jana2020 hand-off requires a Jana .inflip primary input.")
    inflip_path = Path(cfg.jana_inflip)
    if not inflip_path.is_file():
        raise RuntimeError(f"Jana2020 .inflip no longer exists: {inflip_path}")
    jana_cwd = inflip_path.parent
    base_name = inflip_path.stem
    source_key = str(map_source or "deblurred").strip().lower()
    if source_key.startswith("super"):
        source_map = Path(result.superflip_map)
        target_map = jana_cwd / f"{base_name}-phase-studio-superflip-cycle_{int(result.cycle):03d}.xplor"
        source_label = "Superflip map"
    else:
        source_map = Path(result.deblur_map)
        target_map = jana_cwd / f"{base_name}-deb.xplor"
        source_label = "deblurred map"
    if not source_map.is_file():
        raise RuntimeError(f"Selected Jana2020 hand-off map not found: {source_map}")
    if source_map.resolve() != target_map.resolve():
        shutil.copy2(source_map, target_map)
    log(f"Jana2020 hand-off source: cycle {int(result.cycle):03d}, {source_label}")
    log(f"Jana2020 hand-off map: {target_map}")
    original = Path(str(cfg.superflip_exe)).expanduser()
    calc_dir = original.parent / "deblurrer"
    calc_inflip = calc_dir / "calc_m80.inflip"
    original_lines = inflip_path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    final_lines = define_m80_inflip_from_model(inflip_header_for_m80(original_lines), base_name, target_map.name)
    write_text_lines_platform(calc_inflip, final_lines)
    log(f"Jana2020 final Superflip input: {calc_inflip}")
    run_command([str(original), str(calc_inflip)], cwd=jana_cwd, log_path=Path(cfg.work_dir) / "jana2020_return_superflip.log", log=log, stop_event=stop_event)
    log("Jana2020 final Superflip hand-off completed.")



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
        "referenceformat", "modelfile", "modelformat", "dataformat",
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
        elif key == "outputformat":
            settings["output_format"] = normalize_output_format(value)
        elif key == "outputfile":
            settings["write_auxiliary_outputs"] = "true" if len(parts) > 2 else "false"
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
        elif key == "dataformat":
            items = [p.strip().lower() for p in parts[1:]]
            if "intensity" in items and "phase" in items:
                settings["reflection_data_mode"] = REFLECTION_DATA_MODE_INTENSITY_PHASE_SIGMA
            elif "amplitude" in items and "phase" in items:
                settings["reflection_data_mode"] = REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA
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

def normalize_output_format(value: str) -> str:
    fmt = str(value or "xplor").strip().lower()
    if fmt in {"jana", "xplor", "ccp4", "m80"}:
        return fmt
    return "xplor"

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

def write_structure_cif(output_cif: Path, cell: gemmi.UnitCell, sg: gemmi.SpaceGroup, sg_hm: str, atoms: Sequence[AtomSite]) -> None:
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

def write_structure_bundle(output_cif: Path, cell: gemmi.UnitCell, sg: gemmi.SpaceGroup, sg_hm: str, atoms: Sequence[AtomSite]) -> None:
    write_structure_cif(output_cif, cell, sg, sg_hm, atoms)
    write_structure_xyz(output_cif.with_suffix(".xyz"), cell, atoms)
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

def run_command(cmd: Sequence[str], cwd: Path, log_path: Path, log: Callable[[str], None], timeout: Optional[int] = None, stop_event: Optional[threading.Event] = None) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log("  $ " + " ".join(str(x) for x in cmd))
    with log_path.open("w", encoding="utf-8", errors="replace") as lf:
        try:
            proc = subprocess.Popen(list(cmd), cwd=str(cwd), stdout=lf, stderr=subprocess.STDOUT, text=True)
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
            lf.write(message + "\n")
            raise RuntimeError(message) from exc
        deadline = None if timeout is None else time.monotonic() + float(timeout)
        while proc.poll() is None:
            if stop_event is not None and stop_event.is_set():
                lf.write("\nImmediate stop requested by user.\n")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
                raise RuntimeError(f"Immediate stop requested; terminated command: {' '.join(str(x) for x in cmd)}")
            if deadline is not None and time.monotonic() > deadline:
                proc.kill()
                proc.wait(timeout=5)
                raise RuntimeError(f"Command timed out after {timeout} seconds: {' '.join(str(x) for x in cmd)}")
            time.sleep(0.2)
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

def run_superflip_cycle(cycle_dir: Path, prefix: str, ref_ctx: ReferenceContext, observed_hkl: Path, model_file: Optional[Path], reference_file: Optional[Path], reference_format: str, superflip_exe: str, perform_algorithm: str, output_format: str, write_auxiliary_outputs: bool, export_superflip_xplor: bool, export_superflip_ccp4: bool, export_superflip_jana: bool, voxel: str, bestdensities_count: int, bestdensities_metric: str, bestdensities_symmetry: bool, polish: bool, maxcycles: int, repeatmode: int, randomseed: str, delta: str, weakratio: str, biso: str, reflection_data_mode: str, normalize: str, nresshells: int, missing: str, searchsymmetry: str, derivesymmetry: str, electrons: str, dataitemwidths: str, extra_superflip_keywords: str, log: Callable[[str], None], stop_event: Optional[threading.Event] = None) -> Path:
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
        # In Jana .inflip mode ref_ctx.work_ref_cif can be a synthetic metadata-only CIF
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
    log(f"[Superflip] input: {inp}")
    out = cycle_dir / output_name
    for stale in (out, cycle_dir / f"{prefix}.sflog"):
        try:
            if stale.is_file():
                stale.unlink()
                log(f"  Removed stale Superflip output before run: {stale.name}")
        except Exception as exc:
            log(f"  Could not remove stale Superflip output {stale}: {exc}")
    run_started_at = time.time()
    run_command([superflip_exe, inp.name], cwd=cycle_dir, log_path=log_path, log=log, stop_event=stop_event)
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
    log(f"[Superflip symmetry] input: {inp}")
    for stale in (out, sym_dir / f"{prefix}.sflog"):
        try:
            if stale.is_file():
                stale.unlink()
                log(f"  Removed stale Superflip symmetry output before run: {stale.name}")
        except Exception as exc:
            log(f"  Could not remove stale Superflip symmetry output {stale}: {exc}")
    run_started_at = time.time()
    run_command([superflip_exe, inp.name], cwd=sym_dir, log_path=log_path, log=log, stop_event=stop_event)
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
    log(f"Symmetrized deblurred map: {final_map}")
    return final_map

def sharped_elements_from_composition(composition: str) -> str:
    elements: List[str] = []
    for elem in re.findall(r"([A-Z][a-z]?|D)", str(composition or "")):
        elem = clean_element_symbol(elem)
        if elem in {"H", "D", "X"} or elem in elements:
            continue
        elements.append(elem)
    return " ".join(elements) or "C N O"

def run_sharped_deblur(input_map: Path, output_map: Path, base_url: str, api_token: str, model: str, elements: str, outres: float, max_upload_mb: float, timeout_seconds: int, poll_seconds: int, max_polls: int, log: Callable[[str], None], stop_event: Optional[threading.Event] = None) -> Path:
    output_map.parent.mkdir(parents=True, exist_ok=True)
    log_path = output_map.parent / f"{output_map.stem}.sharped.log"
    log_lines: List[str] = []

    def log_both(line: str) -> None:
        log_lines.append(line)
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

def assign_elements_by_reference_composition(density: np.ndarray, ref_atoms: Sequence[AtomSite]) -> List[str]:
    if density is None or len(density) == 0:
        return []
    counts, order = atom_element_counts(ref_atoms)
    target_counts = [(elem, counts[elem]) for elem in order if counts.get(elem, 0) > 0]
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
    write_m40_for_jana: bool = False,
    stop_event: Optional[threading.Event] = None,
    maxima: str = "all",
    fullcell: str = "no",
    numberofatoms: str = "composition",
    centerofcharge: bool = True,
    chlimit: str = "0.2500",
    chlimlist: str = "0.0057 relative",
    extra_edma_keywords: str = "",
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
        if write_m40_for_jana:
            f.write(f"composition {ref_ctx.composition}\n")
            if str(numberofatoms or "").strip():
                f.write(f"numberofatoms {str(numberofatoms).strip()}\n")
            f.write("centerofcharge yes\n" if centerofcharge else "centerofcharge no\n")
            if str(chlimit or "").strip():
                f.write(f"chlimit {str(chlimit).strip()}\n")
            if str(chlimlist or "").strip():
                f.write(f"chlimlist {str(chlimlist).strip()}\n")
            f.write("m40forjana yes\n")
            f.write(f"writem40 {outbase}.m40\n")
        for line in clean_keyword_lines(extra_edma_keywords):
            f.write(line + "\n")
    if map_sigma is None:
        log(f"[EDMA] {xplor_map.name} at {plimit_sigma:g} (input keyword: plimit {float(absolute_plimit):g})")
    else:
        log(f"[EDMA] {xplor_map.name} at {plimit_sigma:g} sigma; map sigma={map_sigma:g}, input keyword: plimit {float(absolute_plimit):g}")
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
        write_structure_bundle(cif, ref_ctx.cell, ref_ctx.spacegroup, ref_ctx.spacegroup_hm, [])
        return cif
    frac, dens = symmetry_merge_peaks(frac, dens, ref_ctx, merge_distance_a)
    elements = assign_elements_by_reference_composition(dens, ref_ctx.atoms)
    atoms = [AtomSite(label=f"{elements[i]}{i+1}", element=elements[i], frac=frac[i], density=float(dens[i])) for i in range(len(frac))]
    write_structure_bundle(cif, ref_ctx.cell, ref_ctx.spacegroup, ref_ctx.spacegroup_hm, atoms)
    return cif

def extract_jana_embedded_files(cif_path: Path, export_dir: Path, prefix: str) -> List[Path]:
    if not Path(cif_path).is_file():
        return []
    text = Path(cif_path).read_text(encoding="utf-8", errors="replace")
    extracted: List[Path] = []
    tags = {
        "_jana_m40_file": f"{prefix}_reference.m40",
        "_jana_m50_file": f"{prefix}.m50",
        "_jana_m90_file": f"{prefix}.m90",
        "_jana_m95_file": f"{prefix}.m95",
    }
    lines = text.splitlines()
    idx = 0
    while idx < len(lines):
        tag = lines[idx].strip().lower()
        if tag not in tags:
            idx += 1
            continue
        idx += 1
        while idx < len(lines) and not lines[idx].strip():
            idx += 1
        if idx >= len(lines) or lines[idx].strip() != ";":
            continue
        idx += 1
        payload: List[str] = []
        while idx < len(lines) and lines[idx].strip() != ";":
            payload.append(lines[idx])
            idx += 1
        out_path = export_dir / tags[tag]
        out_path.write_text("\n".join(payload).rstrip() + "\n", encoding="utf-8")
        extracted.append(out_path)
        idx += 1
    return extracted

def export_jana2020_project(
    export_dir: Path,
    prefix: str,
    cycle_dir: Path,
    edma_dir: Path,
    map_path: Path,
    cif_path: Path,
    ref_ctx: ReferenceContext,
    log: Callable[[str], None],
) -> Path:
    export_dir.mkdir(parents=True, exist_ok=True)
    embedded = extract_jana_embedded_files(ref_ctx.cif_path, export_dir, prefix)
    if not embedded and ref_ctx.work_ref_cif != ref_ctx.cif_path:
        embedded = extract_jana_embedded_files(ref_ctx.work_ref_cif, export_dir, prefix)
    candidates = [
        cycle_dir / f"{prefix}.m80",
        cycle_dir / f"{prefix}.m81",
        cycle_dir / f"{prefix}.sflog",
        cycle_dir / f"{prefix}.superflip.log",
        cycle_dir / f"{prefix}.inflip",
        edma_dir / f"{prefix}_edma.m40",
        edma_dir / f"{prefix}_edma.inp",
        edma_dir / f"{prefix}_edma.log",
        map_path,
        cif_path,
        ref_ctx.work_ref_cif,
    ]
    copied = 0
    for src in candidates:
        if src is None or not Path(src).is_file():
            continue
        dst = export_dir / Path(src).name
        if Path(src).resolve() != dst.resolve():
            shutil.copy2(src, dst)
        copied += 1
    copied += len(embedded)
    readme = export_dir / "README_Jana2020_export.txt"
    readme.write_text(
        "\n".join(
            [
                "Phase Studio Jana2020 export",
                f"Prefix: {prefix}",
                "",
                "Primary files:",
                f"- {prefix}.m80 / {prefix}.m81: Superflip Jana output files when produced by this Superflip build.",
                f"- {prefix}_edma.m40: EDMA/Jana peak file when produced by this EDMA build.",
                f"- {prefix}.m50 / {prefix}.m90 / {prefix}.m95: Jana project/data files extracted from an embedded Jana CIF when present.",
                f"- {Path(map_path).name}: XPLOR density map.",
                f"- {Path(cif_path).name}: EDMA peak model exported as CIF.",
                "",
                "For a full Jana project, open/use the extracted m50/m90 files together with the m40/m80/m81 files when present.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    log(f"Jana2020 export: {export_dir} ({copied} files)")
    if not (export_dir / f"{prefix}_edma.m40").is_file():
        log("  Jana2020 export note: EDMA did not produce an m40 file; m80/m81/map/CIF were still exported.")
    if not (export_dir / f"{prefix}.m50").is_file() or not (export_dir / f"{prefix}.m90").is_file():
        log("  Jana2020 export note: no embedded m50/m90 project files were found in the reference CIF.")
    return export_dir

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
            ])


# -----------------------------------------------------------------------------
# Qt GUI
# -----------------------------------------------------------------------------

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
        self.button.setFixedWidth(34)
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
    "input_source_mode": "Choose how crystallographic input is supplied: use the Jana .inflip as the primary source, use it with selected external HKL/reference replacements, or use an external HKL plus CIF reference without a Jana input file.",
    "jana_inflip": "Jana2020 Superflip input file. In Jana modes its fbegin/endf reflection block is the default HKL source, and its cell/space-group/composition keywords can provide the reference metadata.",
    "hkl": "External reflection file. In Jana override mode it replaces only the fbegin/endf reflection block; in external mode it is the required reflection source.",
    "reference_cif": "External reference file. CIF/INS/RES files provide the crystallographic reference model; Jana/XPLOR/CCP4 density maps are written as Superflip referencefile inputs. External HKL-only mode requires a CIF-compatible reference.",
    "first_cycle_modelfile": "Optional external density or structure model for cycle 1. Supported Superflip modelfile inputs are XPLOR, CCP4 and CIF.",
    "work_dir": "Output directory for generated HKL files, Superflip inputs, maps, EDMA results, logs and metrics.",
    "superflip_exe": "Absolute path to the original Jana2020 Superflip executable. Default: C:\\Jana2020\\SUPERFLIP\\superflip_original.exe. Do not select the Phase Studio wrapper named superflip.exe.",
    "edma_exe": "Absolute path to the Jana2020 EDMA executable used for peak extraction and structure export from XPLOR density maps. Default: C:\\Jana2020\\SUPERFLIP\\EDMA.exe.",
    "workflow_preset": "High-level starting preset for common crystallographic workflows. It sets only basic defaults; all advanced Superflip and EDMA keywords remain editable.",
    "cycles": "Number of iterative Superflip -> EDMA -> SharpED -> EDMA cycles to run.",
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
    "exclude_atoms": "Optional atom labels to remove from CIF modelfiles before the next Superflip cycle. Use comma, semicolon or whitespace separation.",
    "run_edma_superflip": "Run EDMA peak search on the raw Superflip XPLOR map and write CIF, XYZ and PDB structure exports.",
    "run_sharped": "Run SharpED server deblurring on the Superflip XPLOR map. If disabled, the deblurred map is a copy of the Superflip map.",
    "symmetrize_deblurred_map": "After SharpED deblurring, run Superflip in perform symmetry mode with the deblurred XPLOR as modelfile. No charge flipping is performed; the output map is averaged according to the supplied space-group symmetry and is then used for EDMA, Jana export, feedback and later-cycle XPLOR modelfiles.",
    "run_edma_deblurred": "Run EDMA peak search on the deblurred XPLOR map. Disable this when you only want map export or raw Superflip EDMA results.",
    "perform_algorithm": "Superflip perform keyword. Common values: CF, lde, general, fourier, symmetry; AAR is kept for executables that support it.",
    "output_format": "Superflip outputformat keyword. Imported Jana/Superflip templates commonly use jana while still listing an .xplor output file.",
    "write_auxiliary_outputs": "Write three outputfile names, m81, m80 and xplor, like Jana/Superflip templates.",
    "export_superflip_xplor": "Request an XPLOR map from Superflip. XPLOR is also kept internally because EDMA and SharpED consume this map format.",
    "export_superflip_ccp4": "Request an additional CCP4 map from Superflip for external crystallographic and molecular-graphics viewers.",
    "export_superflip_jana": "Request Jana density and reflection outputs from Superflip: m81 density map and m80 phased-reflection list.",
    "export_standard_hkl": "Write a standardized observed-reflection export with h k l I sigma(I) phase(deg). Phase is 0 unless supplied by the selected input mode.",
    "export_jana_project": "Create a Jana2020 export folder for each cycle with Superflip m80/m81, EDMA m40, maps, CIF and logs.",
    "referencefile_mode": "Internal automatic setting derived from External reference file. Phase Studio writes only referencefile and lets Superflip infer jana/xplor/ccp4/cif from the filename.",
    "voxel": "Superflip voxel grid. The default omit/blank skips the keyword. Use three integers, for example 180 80 160, or AUTO to compute a 0.2 A grid from the unit cell.",
    "bestdensities_count": "First argument of bestdensities: how many best density maps Superflip keeps.",
    "bestdensities_metric": "Second argument of bestdensities: rvalue, peakiness, symmetry or reference.",
    "bestdensities_symmetry": "Adds the 'symmetry' modifier to 'bestdensities 1', biasing saved-density selection toward symmetry-consistent solutions.",
    "polish": "Adds 'polish yes' to the Superflip input, enabling Superflip's final polishing/refinement stage when supported by the executable.",
    "maxcycles": "Maximum number of Superflip iterations per run.",
    "repeatmode": "Superflip repeatmode parameter controlling repeated independent attempts and convergence sampling.",
    "randomseed": "Random seed passed to Superflip. Use a fixed value for reproducibility or Superflip-supported automatic syntax if desired.",
    "delta": "Superflip delta keyword. AUTO lets Superflip estimate the flip threshold.",
    "weakratio": "Superflip weakratio keyword.",
    "biso": "Overall isotropic B factor used to sharpen the map. Use 0.000 if no sharpening is wanted.",
    "reflection_data_mode": "Exact HKL column order. 'set from inflip' imports dataformat from Jana; the four HKL modes accept I or F followed by sigma, optionally with phase in degrees before sigma. Phase Studio converts phase to Superflip turns and retains sigma for diagnostics.",
    "first_cycle_like_attachment": "Legacy option removed from the UI. Use Basic -> Workflow -> Next-cycle modelfile instead.",
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
    "map_feedback_missing_from_cycle": "First completed cycle whose final map is used to add missing reflections for the next cycle. Use 0 to disable missing-reflection completion.",
    "map_feedback_missing_percent_limit": "Maximum number of added missing reflections, expressed as a percent of the current HKL count. This prevents map feedback from overwhelming measured data.",
    "map_feedback_intensity_from_cycle": "First completed cycle whose final map is used to damp observed intensities for the next cycle. Use 0 to disable intensity correction.",
    "map_feedback_intensity_damping": "Damping factor for map-based intensity correction. 0 keeps observed data; 1 replaces them by scaled map-derived intensities.",
    "map_feedback_intensity_max_i_over_sigma": "Apply map-based intensity correction only to non-zero reflections with value/sigma below this limit. Use 0 to correct all non-zero reflections.",
    "sharped_base_url": "SharpED inference server base URL. The C++ reference client uses https://jana.fzu.cz.",
    "sharped_api_token": "User API token sent as Authorization: Bearer during upload/status/download.",
    "sharped_model": "SharpED server model name. Use default to query /sharp-ed/models and select the server default.",
    "sharped_elements": "Chemical elements sent to the SharpED server. Leave blank to derive unique non-H elements from the reference composition.",
    "sharped_outres": "Output resolution sent as the outres multipart field.",
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


class WorkflowDiagram(QWidget):
    """Compact native-Qt overview of the optional reconstruction branches."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(190)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setToolTip("Optional branches depend on the Workflow settings.")

    def paintEvent(self, event) -> None:  # type: ignore[override]
        super().paintEvent(event)
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            width = max(520.0, float(self.width()))
            scale = min(1.0, width / 760.0)
            box_w = 116.0 * scale
            box_h = 34.0
            gap = max(18.0, (width - 5.0 * box_w - 32.0) / 4.0)
            y = 30.0
            labels = ("Reflections", "Superflip", "XPLOR map", "SharpED", "Next-cycle model")
            boxes: List[QRectF] = []
            x = 8.0
            for label in labels:
                box = QRectF(x, y, box_w, box_h)
                boxes.append(box)
                painter.setPen(QPen(QColor("#44b7ff"), 1.0))
                painter.setBrush(QColor("#f2f4f9"))
                painter.drawRect(box)
                painter.setPen(QColor("#001170"))
                painter.drawText(box, Qt.AlignCenter, label)
                x += box_w + gap

            def arrow(start_x: float, start_y: float, end_x: float, end_y: float) -> None:
                painter.setPen(QPen(QColor("#2264b8"), 1.5))
                painter.drawLine(int(start_x), int(start_y), int(end_x), int(end_y))
                painter.drawLine(int(end_x), int(end_y), int(end_x - 6), int(end_y - 4))
                painter.drawLine(int(end_x), int(end_y), int(end_x - 6), int(end_y + 4))

            for first, second in zip(boxes, boxes[1:]):
                arrow(first.right() + 3, first.center().y(), second.left() - 3, second.center().y())

            edma_box = QRectF(boxes[2].center().x() - box_w / 2.0, 100.0, box_w, box_h)
            painter.setPen(QPen(QColor("#44b7ff"), 1.0))
            painter.setBrush(QColor("#f2f4f9"))
            painter.drawRect(edma_box)
            painter.setPen(QColor("#001170"))
            painter.drawText(edma_box, Qt.AlignCenter, "EDMA")
            painter.setPen(QPen(QColor("#2264b8"), 1.5))
            painter.drawLine(int(boxes[2].center().x()), int(boxes[2].bottom() + 3), int(edma_box.center().x()), int(edma_box.top() - 3))

            jana_box = QRectF(boxes[4].center().x() - box_w / 2.0, 100.0, box_w, box_h)
            painter.setPen(QPen(QColor("#44b7ff"), 1.0))
            painter.setBrush(QColor("#f2f4f9"))
            painter.drawRect(jana_box)
            painter.setPen(QColor("#001170"))
            painter.drawText(jana_box, Qt.AlignCenter, "Jana2020")
            painter.setPen(QPen(QColor("#2264b8"), 1.5))
            painter.drawLine(int(boxes[4].center().x()), int(boxes[4].bottom() + 3), int(jana_box.center().x()), int(jana_box.top() - 3))
            painter.setPen(QColor("#2264b8"))
            painter.drawText(QRectF(8.0, 152.0, width - 16.0, 24.0), Qt.AlignCenter, "Branches are optional · selected result → Jana2020")
        finally:
            painter.end()

class IterativeSuperflipPipelineQtGUI(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Phase Studio 1.0.1 for Jana2020")
        self.setWindowIcon(create_phase_studio_app_icon(64))
        self.resize(1420, 880)
        self.msg_queue: "queue.Queue[Tuple[str, object]]" = queue.Queue()
        self.worker: Optional[threading.Thread] = None
        self.hkl_task_worker: Optional[threading.Thread] = None
        self.stop_after_cycle = threading.Event()
        self.stop_now = threading.Event()
        self.results: List[CycleResult] = []
        self.last_run_config: Optional[RunConfig] = None
        self.reference_atoms_for_plot: List[AtomSite] = []
        self.superflip_atoms_for_plot: List[AtomSite] = []
        self.deblur_atoms_for_plot: List[AtomSite] = []
        self.structure_cell: Optional[gemmi.UnitCell] = None
        self.structure_axes: List[object] = []
        self.structure_elev = 20.0
        self.structure_azim = 35.0
        self._structure_rotation_source: Optional[object] = None
        self._metrics_compact_sizes: Optional[List[int]] = None
        self._metrics_expanded = False
        self._configuration_locked = False
        self._run_status = "READY"
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
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)
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
        idx = w.findText(default)
        if idx >= 0:
            w.setCurrentIndex(idx)
        form.addRow(label, w)
        self.inputs[key] = w
        self._apply_input_tooltip(key, w)
        self._apply_form_label_tooltip(form, w, key)

    def _add_checkbox(self, form: QFormLayout, key: str, label: str, default: bool = False) -> None:
        w = QCheckBox(label)
        w.setChecked(bool(default))
        form.addRow(w)
        self.inputs[key] = w
        self._apply_input_tooltip(key, w)

    def _add_spin(self, form: QFormLayout, key: str, label: str, default: int, minimum: int = 0, maximum: int = 1000000, step: int = 1) -> None:
        w = QSpinBox()
        w.setRange(minimum, maximum)
        w.setSingleStep(step)
        w.setValue(default)
        form.addRow(label, w)
        self.inputs[key] = w
        self._apply_input_tooltip(key, w)
        self._apply_form_label_tooltip(form, w, key)

    def _add_dspin(self, form: QFormLayout, key: str, label: str, default: float, minimum: float = -1e9, maximum: float = 1e9, step: float = 0.1, decimals: int = 3) -> None:
        w = QDoubleSpinBox()
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
        if not all(hasattr(self, name) for name in ("category_tabs", "basic_tabs", "help_scroll")):
            return
        self.category_tabs.setCurrentIndex(0)
        help_index = next(
            (index for index in range(self.basic_tabs.count()) if self.basic_tabs.tabText(index) == "Help"),
            -1,
        )
        if help_index < 0:
            return
        self.basic_tabs.setCurrentIndex(help_index)
        target = self.help_sections.get(str(anchor))
        if target is None:
            self.help_scroll.verticalScrollBar().setValue(0)
            return
        QTimer.singleShot(0, lambda section=target: self.help_scroll.ensureWidgetVisible(section, 0, 8))

    def _context_help_anchor(self) -> Optional[str]:
        if not hasattr(self, "category_tabs"):
            return "setup"
        if self.category_tabs.currentIndex() == 0:
            name = self.basic_tabs.tabText(self.basic_tabs.currentIndex())
            return {
                "Paths": "setup",
                "Workflow": "setup",
                "SharpED": "sharped",
                "Help": None,
            }.get(name, "setup")
        name = self.advanced_tabs.tabText(self.advanced_tabs.currentIndex())
        return {
            "Superflip": "superflip",
            "EDMA": "edma",
            "Map feedback": "map_feedback",
        }.get(name, "setup")

    def _open_context_help(self) -> None:
        anchor = self._context_help_anchor()
        if anchor is not None:
            self._open_help_section(anchor)

    def _external_link_icon(self, url: str, tooltip: str) -> QToolButton:
        def chain_pixmap(color: str) -> QPixmap:
            pixmap = QPixmap(20, 20)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            try:
                painter.setRenderHint(QPainter.Antialiasing, True)
                pen = QPen(QColor(color), 1.7)
                pen.setJoinStyle(Qt.RoundJoin)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.save()
                painter.translate(7.2, 11.7)
                painter.rotate(-38.0)
                painter.drawRoundedRect(QRectF(-5.5, -3.0, 10.0, 6.0), 3.0, 3.0)
                painter.restore()
                painter.save()
                painter.translate(12.8, 8.3)
                painter.rotate(-38.0)
                painter.drawRoundedRect(QRectF(-4.5, -3.0, 10.0, 6.0), 3.0, 3.0)
                painter.restore()
            finally:
                painter.end()
            return pixmap

        normal_pixmap = chain_pixmap("#2264b8")
        active_pixmap = chain_pixmap("#001170")
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
        link.setFixedSize(24, 24)
        link.clicked.connect(lambda _checked=False, target=url: QDesktopServices.openUrl(QUrl(target)))
        return link

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)
        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setHandleWidth(3)
        main_layout.addWidget(self.main_splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(6, 4, 8, 4)
        left_layout.setSpacing(8)
        self.main_splitter.addWidget(left)

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
        version_badge = QLabel("1.0.1")
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
        left_layout.addWidget(category_tabs, 1)

        def add_settings_tab(name: str, advanced: bool = False) -> QVBoxLayout:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            page = QWidget()
            page.setObjectName("settingsPage")
            page.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            layout = QVBoxLayout(page)
            layout.setContentsMargins(10, 10, 10, 10)
            layout.setSpacing(12)
            scroll.setWidget(page)
            (advanced_tabs if advanced else basic_tabs).addTab(scroll, name)
            if name == "Help" and not advanced:
                self.help_scroll = scroll
                self.help_page = page
            return layout

        def add_form_group(page_layout: QVBoxLayout, title: str, guide_anchor: Optional[str] = None) -> QFormLayout:
            if guide_anchor:
                box = QGroupBox()
                box_layout = QVBoxLayout(box)
                box_layout.setContentsMargins(8, 7, 8, 8)
                box_layout.setSpacing(7)
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
            form = self._configure_form(QFormLayout(box))
            page_layout.addWidget(box)
            return form

        def settings_callout(title: str, text: str) -> QLabel:
            label = QLabel(f"<b>{title}</b><br>{text}")
            label.setObjectName("settingsCallout")
            label.setTextFormat(Qt.RichText)
            label.setWordWrap(True)
            return label

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

        dashboard_header = QWidget()
        dashboard_header.setObjectName("dashboardHeader")
        dashboard_layout = QHBoxLayout(dashboard_header)
        dashboard_layout.setContentsMargins(12, 5, 12, 5)
        dashboard_text = QVBoxLayout()
        dashboard_text.setSpacing(0)
        dashboard_title = QLabel("RUN OVERVIEW")
        dashboard_title.setObjectName("dashboardTitle")
        dashboard_subtitle = QLabel("Reconstruction progress and results")
        dashboard_subtitle.setObjectName("dashboardSubtitle")
        dashboard_subtitle.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        dashboard_text.addWidget(dashboard_title)
        dashboard_text.addWidget(dashboard_subtitle)
        self.status_badge = QLabel("READY")
        self.status_badge.setObjectName("statusBadge")
        self.status_badge.setAlignment(Qt.AlignCenter)
        dashboard_layout.addLayout(dashboard_text, 1)
        dashboard_layout.addWidget(self.status_badge)
        right_layout.addWidget(dashboard_header)

        def make_result_section(title: str) -> Tuple[QWidget, QVBoxLayout]:
            section = QWidget()
            section.setObjectName("resultSection")
            section_layout = QVBoxLayout(section)
            section_layout.setContentsMargins(4, 4, 4, 4)
            section_layout.setSpacing(3)
            label = QLabel(title)
            label.setObjectName("sectionLabel")
            section_layout.addWidget(label)
            return section, section_layout

        def add_help_section(page_layout: QVBoxLayout, anchor: str, title: str, body_html: str) -> QVBoxLayout:
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
            return box_layout

        def add_help_callout(section_layout: QVBoxLayout, label: str, text: str) -> None:
            callout = QLabel(f"<b>{label}</b><br>{text}")
            callout.setObjectName("helpCallout")
            callout.setTextFormat(Qt.RichText)
            callout.setWordWrap(True)
            section_layout.addWidget(callout)

        def add_back_to_contents(section_layout: QVBoxLayout) -> None:
            row = QHBoxLayout()
            row.addStretch(1)
            link = QToolButton()
            link.setObjectName("helpNavLink")
            link.setText("↑ Contents")
            link.setCursor(Qt.PointingHandCursor)
            link.clicked.connect(lambda: self.help_scroll.verticalScrollBar().setValue(0))
            row.addWidget(link)
            section_layout.addLayout(row)

        cwd = Path.cwd()

        # Basic / Paths
        paths_tab = add_settings_tab("Paths")
        data_input_form = add_form_group(paths_tab, "Data input")
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
        except Exception:
            pass
        self._add_path(data_input_form, "jana_inflip", "Jana2020 .inflip file", "", "file", "Superflip input (*.inflip *.inp);;All files (*)")
        self._add_path(data_input_form, "hkl", "External HKL file", "", "file", "HKL files (*.hkl);;All files (*)")
        self._add_combo(
            data_input_form,
            "reflection_data_mode",
            "HKL format",
            [
                REFLECTION_DATA_MODE_SET_FROM_INFLIP,
                REFLECTION_DATA_MODE_INTENSITY,
                REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA,
                REFLECTION_DATA_MODE_INTENSITY_PHASE_SIGMA,
                REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA,
            ],
            REFLECTION_DATA_MODE_SET_FROM_INFLIP,
        )
        hkl_button_row = QHBoxLayout()
        self.test_hkl_btn = QPushButton("Validate HKL")
        self.analyze_hkl_btn = QPushButton("Analyze completeness")
        self.test_hkl_btn.setToolTip("Parse the selected HKL or Jana .inflip reflection block and show which h, k, l, value, sigma and phase fields were read.")
        self.analyze_hkl_btn.setToolTip("Open completeness and data-statistics plots for the selected HKL data.")
        self.test_hkl_btn.clicked.connect(self.test_hkl_load_dialog)
        self.analyze_hkl_btn.clicked.connect(self.open_hkl_completeness_dialog)
        hkl_button_row.addWidget(self.test_hkl_btn)
        hkl_button_row.addWidget(self.analyze_hkl_btn)
        data_input_form.addRow("", hkl_button_row)

        reference_form = add_form_group(paths_tab, "Reference and initial model")
        self._add_path(reference_form, "reference_cif", "Reference file", "", "file", "Reference files (*.cif *.ins *.res *.m80 *.m81 *.jana *.xplor *.ccp4 *.map);;CIF structures (*.cif *.ins *.res);;Jana density maps (*.m80 *.m81 *.jana);;XPLOR maps (*.xplor);;CCP4 maps (*.ccp4 *.map);;All files (*)")
        self._add_path(reference_form, "first_cycle_modelfile", "Initial model (cycle 1)", "", "file", "Model/map files (*.xplor *.ccp4 *.cif);;All files (*)")

        output_form = add_form_group(paths_tab, "Output")
        self._add_path(output_form, "work_dir", "Working directory", str(cwd / "iterative_superflip_qt_run"), "dir")

        programs_form = add_form_group(paths_tab, "External programs")
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
        paths_tab.addStretch(1)

        # Basic / Workflow
        workflow_tab = add_settings_tab("Workflow")
        workflow_form = add_form_group(workflow_tab, "Reconstruction", "setup")
        self._add_combo(workflow_form, "workflow_preset", "Workflow preset", ["custom", "MOF atomic resolution", "MOF medium resolution", "small molecule", "inorganic"], "custom")
        try:
            self.inputs["workflow_preset"].currentTextChanged.connect(self._apply_workflow_preset)  # type: ignore[attr-defined]
        except Exception:
            pass
        self._add_spin(workflow_form, "cycles", "Cycles", 1, 1, 999, 1)
        self.inputs["cycles"].valueChanged.connect(self._update_plot)  # type: ignore[attr-defined]
        self._add_text(workflow_form, "composition_override", "Composition override", "")
        workflow_form.addRow("", self._secondary_help("Leave blank to use the reference composition."))
        self._add_combo(workflow_form, "modelfile_source", "Next-cycle model", ["superflip_xplor", "deblurred_xplor", "deblurred_edma_cif", "none"], "superflip_xplor")
        try:
            self.inputs["modelfile_source"].currentTextChanged.connect(self._sync_workflow_widgets)  # type: ignore[attr-defined]
        except Exception:
            pass
        self._add_dspin(workflow_form, "damping_factor", "XPLOR damping (1/x)", 1.0, 0.001, 1.0, 0.05, 3)
        self._add_text(workflow_form, "exclude_atoms", "Excluded atoms", "none")
        workflow_note = settings_callout(
            "Note",
            "Next-cycle modelfile is authoritative: 'none' forces a one-cycle run. "
            "superflip_xplor cycles without SharpED deblurring; XPLOR damping is active for XPLOR modes only."
        )
        workflow_form.addRow("", workflow_note)

        optional_form = add_form_group(workflow_tab, "Optional processing")
        self._add_checkbox(optional_form, "run_edma_superflip", "Run EDMA on Superflip map", True)
        self._add_checkbox(optional_form, "run_sharped", "Run SharpED deblurring", True)
        self._add_checkbox(optional_form, "symmetrize_deblurred_map", "Symmetrize processed map with Superflip", False)
        self._add_checkbox(optional_form, "run_edma_deblurred", "Run EDMA on processed map", True)
        workflow_tab.addStretch(1)

        # Basic / SharpED
        sharped_tab = add_settings_tab("SharpED")
        server_form = add_form_group(sharped_tab, "Server connection", "sharped")
        self._add_text(server_form, "sharped_base_url", "Server URL", "https://jana.fzu.cz")
        self._add_text(server_form, "sharped_api_token", "API token", os.environ.get("SHARPED_API_TOKEN", ""))
        try:
            self.inputs["sharped_api_token"].setEchoMode(QLineEdit.Password)  # type: ignore[attr-defined]
        except Exception:
            pass
        token_link_row = QHBoxLayout()
        token_link_row.addWidget(QLabel("Get SharpED token"))
        token_link_row.addWidget(self._external_link_icon("https://sharped.fzu.cz/", "Open the SharpED project and API-token page"))
        token_link_row.addStretch(1)
        server_form.addRow("", token_link_row)

        model_form = add_form_group(sharped_tab, "SharpED model")
        self._add_combo(model_form, "sharped_model", "Model", ["default"], "default")
        try:
            self.inputs["sharped_model"].setEditable(True)  # type: ignore[attr-defined]
        except Exception:
            pass
        self.refresh_models_btn = QPushButton("Refresh models")
        self.refresh_models_btn.setToolTip("Fetch the current list of SharpED server models and update the model selector.")
        self.refresh_models_btn.clicked.connect(self.refresh_sharped_models)
        model_form.addRow("", self.refresh_models_btn)

        inference_form = add_form_group(sharped_tab, "Inference")
        self._add_text(inference_form, "sharped_elements", "Elements", "")
        self._add_dspin(inference_form, "sharped_outres", "Output resolution", 0.2, 0.001, 10.0, 0.05, 4)

        network_form = add_form_group(sharped_tab, "Transfer and network")
        self._add_dspin(network_form, "sharped_max_upload_mb", "Upload limit (MB)", 100.0, 0.0, 100000.0, 10.0, 1)
        self._add_spin(network_form, "sharped_timeout_seconds", "HTTP timeout (s)", 600, 600, 7200, 60)
        self._add_spin(network_form, "sharped_poll_seconds", "Polling interval (s)", 2, 1, 3600, 1)
        self._add_spin(network_form, "sharped_max_polls", "Maximum polls", -1, -1, 1000000, 1)
        network_form.addRow("", self._secondary_help("Use -1 for no fixed polling limit."))
        sharped_tab.addStretch(1)

        # Basic / Help
        reference_tab = add_settings_tab("Help")
        contents_row = QHBoxLayout()
        contents_row.setSpacing(4)
        contents_label = QLabel("CONTENTS")
        contents_label.setObjectName("helpContentsLabel")
        contents_row.addWidget(contents_label)
        for link_text, anchor in (
            ("Setup", "setup"), ("Superflip", "superflip"), ("EDMA", "edma"),
            ("SharpED", "sharped"), ("Feedback", "map_feedback"), ("About", "about"),
        ):
            link = QToolButton()
            link.setObjectName("helpNavLink")
            link.setText(link_text)
            link.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            link.setCursor(Qt.PointingHandCursor)
            link.clicked.connect(lambda _checked=False, target=anchor: self._open_help_section(target))
            contents_row.addWidget(link)
        contents_row.addStretch(1)
        reference_tab.addLayout(contents_row)
        setup_help_layout = add_help_section(reference_tab, "setup", "Systematic setup guide", """
            <h3>1. Select the input</h3>
            <p>Phase Studio can use a Jana2020 <b>.inflip</b> file, a Jana2020 .inflip file with selected external overrides, or an external HKL file with a crystallographic reference.</p>
            <p>For external reflections, select the exact HKL column order first. Use <b>Validate HKL</b> to verify how columns were parsed and <b>Analyze completeness</b> to inspect completeness and data quality before reconstruction.</p>
            <h3>2. Choose a workflow preset</h3>
            <p>Use a preset as a starting point, then adjust advanced parameters only when necessary.</p>
            <ul><li><b>Small molecule, atomic resolution:</b> small-molecule preset, charge flipping, typically 1&ndash;2 cycles.</li>
            <li><b>Inorganic:</b> symmetry-assisted density selection and an EDMA threshold around 1 sigma.</li>
            <li><b>MOF, atomic resolution:</b> SharpED/deblurred XPLOR feedback and typically 2&ndash;4 cycles.</li>
            <li><b>MOF/framework, medium resolution:</b> SharpED + EDMA CIF feedback and approximately 0.5&ndash;1 sigma peak threshold.</li></ul>
            <h3>3. Configure the iterative workflow</h3>
            <p><b>observed reflections &rarr; Superflip &rarr; XPLOR map &rarr; EDMA and/or SharpED &rarr; deblurred XPLOR &rarr; EDMA &rarr; next-cycle model</b></p>
            <p>The exact branches depend on <b>Basic &rarr; Workflow &rarr; Optional processing</b>. The next-cycle source can be Superflip XPLOR, SharpED/deblurred XPLOR, deblurred EDMA CIF, or <b>none</b>. Selecting none forces a one-cycle run.</p>
            <h3>4. Inspect each cycle</h3>
            <p>Review convergence metrics, structure previews, detected atom/peak counts, reference agreement when available, raw Superflip versus SharpED results, and the execution log. Phase Studio does not replace final crystallographic refinement.</p>
            <h3>5. Return the selected result to Jana2020</h3>
            <p>After a successful run, <b>Send to Jana2020</b> lets you select a completed cycle and map source. Final interpretation and refinement remain in Jana2020.</p>
        """)
        setup_help_layout.insertWidget(1, WorkflowDiagram())
        add_help_callout(setup_help_layout, "Tip", "Use the first cycle to establish a stable solution before enabling aggressive feedback.")
        add_back_to_contents(setup_help_layout)
        superflip_help_layout = add_help_section(reference_tab, "superflip", "Superflip guide", """
            <h3>What Superflip does</h3>
            <p>Superflip is the density-reconstruction and phase-retrieval stage. Phase Studio prepares reflections, crystallographic metadata and input, executes Superflip, then uses its density map for direct inspection, EDMA peak extraction, SharpED processing and iterative feedback.</p>
            <h3>1. Verify reflection input</h3>
            <p>Select the correct HKL format, run <b>Validate HKL</b> and <b>Analyze completeness</b>, and apply an optional d<sub>min</sub> cutoff only when appropriate. Do not compensate for incorrectly parsed input by tuning reconstruction parameters.</p>
            <h3>2. Choose the algorithm</h3>
            <p><b>Algorithm</b> maps to Superflip's <code>perform</code> keyword. <b>CF</b> is the normal charge-flipping workflow used by the presets. AAR, lde, general, fourier and symmetry are advanced modes.</p>
            <h3>3. Control iteration and repeated solutions</h3>
            <p><b>Maximum iterations</b> limits one Superflip run. <b>Repeat mode</b> controls repeated solution attempts, and <b>Random seed</b> initializes random numbers. Delta, Weak ratio and Biso are advanced parameters normally left at preset/default values. <b>Enable final polish</b> activates the final polishing option when supported.</p>
            <h3>4. Select the best density</h3>
            <p><b>Best densities: count</b> controls retained solutions. <b>Best-density metric</b> selects by rvalue, peakiness, symmetry or reference. <b>Use symmetry for best densities</b> adds the symmetry modifier.</p>
            <h3>5. Reflection handling</h3>
            <p><b>Minimum value/&sigma;</b> removes weak observations before writing the reflection block. <b>d<sub>min</sub> cutoff</b> is optional; 0 keeps all reflections. Normalization and Resolution shells control optional normalization. Missing-reflection keyword and Electrons expose the corresponding advanced Superflip options.</p>
            <h3>6. Symmetry</h3>
            <p><b>Search symmetry</b> maps to <code>searchsymmetry</code>; <b>Derive symmetry</b> maps to <code>derivesymmetry</code>.</p>
            <h3>7. Output</h3>
            <p>XPLOR is important internally because EDMA and SharpED consume XPLOR density maps. Other outputs support external inspection, Jana2020 interoperability and export.</p>
            <h3>8. Advanced keywords</h3>
            <p><b>Extra Superflip keywords</b> lets expert users append documented keywords without dedicated GUI controls.</p>
        """)
        add_help_callout(superflip_help_layout, "Recommended", "Start with CF and the supplied preset values unless you intentionally tune the calculation.")
        add_back_to_contents(superflip_help_layout)
        edma_help_layout = add_help_section(reference_tab, "edma", "EDMA guide", """
            <h3>What EDMA does in Phase Studio</h3>
            <p>EDMA extracts density maxima from an XPLOR map. Phase Studio uses these maxima to create structural models and exports, independently for the raw Superflip map and the SharpED/deblurred map when enabled.</p>
            <h3>1. Peak thresholds</h3>
            <p><b>Superflip threshold</b> and <b>SharpED threshold (&sigma;)</b> are multipliers of the corresponding map sigma. Phase Studio converts each multiplier to EDMA's absolute <code>plimit</code> for that map. A higher threshold is stricter; a lower threshold includes more maxima. There is no universal correct threshold.</p>
            <h3>2. Maxima selection and atom count</h3>
            <p><b>Maxima selection = all</b> requests all maxima above plimit. Advanced users may enter more restrictive documented EDMA syntax. <b>Atom-count mode = composition</b> requests counts consistent with chemical composition.</p>
            <h3>3. Symmetry and peak positions</h3>
            <p><b>Merge distance</b> is the tolerance used when reducing maxima to one representative per full space-group orbit for the CIF asymmetric unit. <b>Full-cell = no</b> requests symmetry-independent maxima; yes lists the full unit cell. <b>Use center of charge</b> refines positions to the charge center of each density basin.</p>
            <h3>4. Chemical filtering</h3>
            <p><b>Charge limit</b> is the minimum integrated charge for exported maxima. <b>Charge-list threshold</b> supplies EDMA's <code>chlimlist</code> setting for atom-count/composition-based export.</p>
            <h3>5. Additional keywords</h3>
            <p><b>Extra EDMA keywords</b> appends documented EDMA options not represented by dedicated controls.</p>
        """)
        add_help_callout(edma_help_layout, "Recommended", "An EDMA threshold around 1σ is a common starting point in the supplied guidance; adjust it according to peak quality.")
        add_back_to_contents(edma_help_layout)
        sharped_help_layout = add_help_section(reference_tab, "sharped", "SharpED guide", """
            <h3>What SharpED does</h3>
            <p>SharpED processes and deblurs the XPLOR density map from Superflip. After EDMA extraction the result can be inspected in Structure Comparison, used for EDMA, optionally symmetrized, used as a next-cycle XPLOR model, or handed to Jana2020. If server processing is disabled, the workflow continues without a genuinely processed SharpED result.</p>
            <h3>1. Server connection</h3>
            <p><b>Server URL</b> is the inference-server address. <b>API token</b> authenticates server requests. Obtain a token from the SharpED project and API-token page.</p>
            <h3>2. Model and elements</h3>
            <p><b>Model</b> is sent to the server; <b>Refresh models</b> updates the selector. <code>default</code> uses the server default. <b>Elements</b> are sent to SharpED; when blank, Phase Studio derives unique non-hydrogen elements from the reference composition.</p>
            <h3>3. Output resolution</h3>
            <p><b>Output resolution</b> is sent to the server as the <code>outres</code> field.</p>
            <h3>4. Upload and network</h3>
            <p><b>Upload limit</b> checks XPLOR size; the public-server default is 100 MB. HTTP timeout covers model queries, upload, status and download. Polling interval sets the delay between status checks. Maximum polls limits those checks; <b>-1</b> means no fixed polling limit.</p>
            <h3>5. SharpED in iterative workflows</h3>
            <p><b>Run SharpED deblurring</b> enables server processing. <b>Symmetrize processed map with Superflip</b> performs symmetry averaging, not another charge-flipping reconstruction. <code>deblurred_xplor</code> feeds the processed map into the next cycle; <code>deblurred_edma_cif</code> feeds its EDMA structure.</p>
        """)
        sharped_link_row = QHBoxLayout()
        sharped_link_row.addWidget(QLabel("SharpED project and API token"))
        sharped_link_row.addWidget(self._external_link_icon("https://sharped.fzu.cz/", "Open the SharpED project and API-token page"))
        sharped_link_row.addStretch(1)
        sharped_help_layout.addLayout(sharped_link_row)
        add_help_callout(sharped_help_layout, "Important", "SharpED processing requires a valid API token and network access.")
        add_back_to_contents(sharped_help_layout)
        map_feedback_layout = add_help_section(reference_tab, "map_feedback", "Map feedback", """
            <h3>Missing-reflection completion</h3>
            <p>Completion starts from the selected completed cycle. <b>Added limit (%)</b> caps generated missing reflections relative to the current reflection count.</p>
            <h3>Intensity correction</h3>
            <p>Correction starts from the selected completed cycle. Damping 0 keeps observed values; 1 replaces them with scaled map-derived values. <b>Apply below value/&sigma;</b> limits correction to weak non-zero reflections; 0 applies it to all non-zero reflections.</p>
        """)
        add_help_callout(map_feedback_layout, "Note", "Cycle 0 disables the corresponding feedback mechanism.")
        add_back_to_contents(map_feedback_layout)
        keyword_html = html.escape(SUPERFLIP_KEYWORD_REFERENCE).replace("\n", "<br>")
        add_help_section(
            reference_tab,
            "keyword_reference",
            "Advanced Superflip keyword reference",
            f'<p style="font-family: Cascadia Mono, Consolas, monospace; color: #2264b8;">{keyword_html}</p>',
        )
        about_layout = add_help_section(reference_tab, "about", "About Phase Studio", """
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
        add_back_to_contents(about_layout)
        reference_tab.addStretch(1)

        # Advanced / Superflip
        superflip_tab = add_settings_tab("Superflip", advanced=True)
        calculation_form = add_form_group(superflip_tab, "Calculation", "superflip")
        self._add_combo(calculation_form, "perform_algorithm", "Algorithm", ["CF", "AAR", "lde", "general", "fourier", "symmetry"], "CF")
        self.inputs["perform_algorithm"].setToolTip(
            INPUT_TOOLTIPS["perform_algorithm"]
        )  # type: ignore[attr-defined]
        self._add_spin(calculation_form, "maxcycles", "Maximum iterations", 1000, 1, 100000, 100)
        self._add_spin(calculation_form, "repeatmode", "Repeat mode", 12, 1, 10000, 1)
        self._add_text(calculation_form, "randomseed", "Random seed", "12345")
        self._add_text(calculation_form, "delta", "Delta", "AUTO")
        self._add_text(calculation_form, "weakratio", "Weak ratio", "0.000")
        self._add_text(calculation_form, "biso", "Biso", "0.000")
        self._add_checkbox(calculation_form, "polish", "Enable final polish", False)

        density_form = add_form_group(superflip_tab, "Density / solution selection")
        self._add_text(density_form, "voxel", "Voxel grid", "omit")
        self._add_spin(density_form, "bestdensities_count", "Best densities: count", 1, 1, 100, 1)
        self._add_combo(density_form, "bestdensities_metric", "Best-density metric", ["rvalue", "peakiness", "symmetry", "reference"], "rvalue")
        self._add_checkbox(density_form, "bestdensities_symmetry", "Use symmetry for best densities", False)
        self.inputs["bestdensities_symmetry"].setToolTip(
            INPUT_TOOLTIPS["bestdensities_symmetry"]
        )  # type: ignore[attr-defined]
        self._add_combo(density_form, "searchsymmetry", "Search symmetry", ["average", "shift", "no"], "average")
        self._add_text(density_form, "derivesymmetry", "Derive symmetry", "yes")

        reflection_form = add_form_group(superflip_tab, "Reflection handling")
        self._add_dspin(reflection_form, "i_over_sigma_min", "Minimum value/σ", 0.0, 0.0, 100.0, 0.5, 3)
        self._add_dspin(reflection_form, "resolution_d_min", "d_min cutoff (Å)", 0.0, 0.0, 20.0, 0.1, 3)
        self._add_combo(reflection_form, "normalize", "Normalization", ["none", "local", "atoms", "wilson"], "none")
        self._add_spin(reflection_form, "nresshells", "Resolution shells", 100, 0, 100000, 10)
        self._add_text(reflection_form, "missing", "Missing-reflection keyword", "bound 0.5 2.5")
        self._add_text(reflection_form, "electrons", "Electrons", "")

        output_options_form = add_form_group(superflip_tab, "Output")
        self._add_combo(output_options_form, "output_format", "Format", ["xplor", "jana", "ccp4", "m80"], "xplor")
        self._add_checkbox(output_options_form, "write_auxiliary_outputs", "Write legacy auxiliary outputs", False)
        self._add_checkbox(output_options_form, "export_superflip_xplor", "Save XPLOR map", True)
        self._add_checkbox(output_options_form, "export_superflip_ccp4", "Save CCP4 map", False)
        self._add_checkbox(output_options_form, "export_superflip_jana", "Save Jana m80/m81", False)
        self._add_checkbox(output_options_form, "export_standard_hkl", "Save standardized HKL (I/σ/phase)", False)
        self._add_checkbox(output_options_form, "export_jana_project", "Export Jana2020 project", False)

        reference_density_form = add_form_group(superflip_tab, "Reference density")
        reference_density_form.addRow(self._secondary_help(
            "The referencefile keyword is automatic: it is omitted by default and written only when a reference file is selected on Paths."
        ))
        reference_density_form.addRow(self._secondary_help(
            "dataitemwidths is unnecessary because Phase Studio writes whitespace-separated fbegin/endf records."
        ))

        additional_sf_form = add_form_group(superflip_tab, "Additional keywords")
        self._add_multiline(additional_sf_form, "extra_superflip_keywords", "Extra Superflip keywords", "", 110)
        self.load_inflip_btn = QPushButton("Load settings from .inflip")
        self.load_inflip_btn.setToolTip("Read Superflip keyword settings from an existing .inflip file. Reflection data blocks are ignored.")
        self.load_inflip_btn.clicked.connect(self.load_inflip_settings_dialog)
        additional_sf_form.addRow("", self.load_inflip_btn)
        superflip_tab.addStretch(1)

        # Advanced / EDMA
        edma_tab = add_settings_tab("EDMA", advanced=True)
        peak_form = add_form_group(edma_tab, "Peak extraction", "edma")
        self._add_dspin(peak_form, "plimit_superflip", "Superflip threshold", 0.5, 0.0, 100.0, 0.1, 3)
        self._add_dspin(peak_form, "plimit_deblur", "SharpED threshold (σ)", 0.5, 0.0, 100.0, 0.1, 3)
        self._add_text(peak_form, "edma_maxima", "Maxima selection", "all")
        self._add_text(peak_form, "edma_numberofatoms", "Atom-count mode", "composition")

        symmetry_form = add_form_group(edma_tab, "Symmetry and peak positions")
        self._add_dspin(symmetry_form, "merge_distance", "Merge distance (Å)", 0.75, 0.0, 10.0, 0.05, 3)
        self._add_combo(symmetry_form, "edma_fullcell", "Full-cell", ["no", "yes"], "no")
        self._add_checkbox(symmetry_form, "edma_centerofcharge", "Use center of charge", True)

        chemical_form = add_form_group(edma_tab, "Chemical filtering")
        self._add_text(chemical_form, "edma_chlimit", "Charge limit", "0.2500")
        self._add_text(chemical_form, "edma_chlimlist", "Charge-list threshold", "0.0057 relative")

        edma_extra_form = add_form_group(edma_tab, "Additional keywords")
        self._add_multiline(edma_extra_form, "extra_edma_keywords", "Extra EDMA keywords", "", 110)
        edma_tab.addStretch(1)

        # Advanced / Map feedback
        feedback_tab = add_settings_tab("Map feedback", advanced=True)
        missing_feedback_form = add_form_group(feedback_tab, "Missing-reflection completion", "map_feedback")
        self._add_spin(missing_feedback_form, "map_feedback_missing_from_cycle", "Start after cycle", 0, 0, 999, 1)
        self._add_dspin(missing_feedback_form, "map_feedback_missing_percent_limit", "Added limit (%)", 0.0, 0.0, 100.0, 1.0, 3)
        missing_feedback_form.addRow("", settings_callout("Note", "Cycle 0 disables missing-reflection completion."))

        intensity_feedback_form = add_form_group(feedback_tab, "Intensity correction")
        self._add_spin(intensity_feedback_form, "map_feedback_intensity_from_cycle", "Start after cycle", 0, 0, 999, 1)
        self._add_dspin(intensity_feedback_form, "map_feedback_intensity_damping", "Correction damping", 0.0, 0.0, 1.0, 0.05, 3)
        self._add_dspin(intensity_feedback_form, "map_feedback_intensity_max_i_over_sigma", "Apply below value/σ", 0.0, 0.0, 1000.0, 0.5, 3)
        intensity_feedback_form.addRow("", settings_callout("Note", "Cycle 0 disables correction; value/σ = 0 applies to all non-zero reflections."))
        feedback_tab.addStretch(1)

        # Persistent actions
        primary_buttons = QHBoxLayout()
        primary_buttons.setSpacing(8)
        secondary_buttons = QHBoxLayout()
        secondary_buttons.setSpacing(8)
        self.run_btn = QPushButton("Run pipeline")
        self.stop_btn = QPushButton("Stop after current cycle")
        self.stop_now_btn = QPushButton("Stop immediately")
        self.clear_btn = QPushButton("Clear results")
        self.handoff_btn = QPushButton("Send to Jana2020")
        self.run_btn.setObjectName("primaryButton")
        self.handoff_btn.setObjectName("handoffButton")
        for action_button in (self.run_btn, self.stop_btn, self.stop_now_btn, self.clear_btn, self.handoff_btn):
            action_button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.handoff_btn.setEnabled(False)
        self.run_btn.setToolTip("Start the complete iterative crystallographic reconstruction workflow.")
        self.stop_btn.setToolTip("Request a graceful stop after the currently running cycle has completed.")
        self.stop_now_btn.setToolTip("Terminate the currently running external Superflip/EDMA process and stop the pipeline as soon as possible.")
        self.clear_btn.setToolTip("Clear the log panel and reset the plotted metrics for the current GUI session.")
        self.handoff_btn.setToolTip("After a completed run started from a Jana .inflip, select a cycle and pass either its Superflip map or deblurred map back to Jana2020.")
        self.run_btn.clicked.connect(self.start_run)
        self.stop_btn.clicked.connect(self.request_stop_after_cycle)
        self.stop_now_btn.clicked.connect(self.request_immediate_stop)
        self.clear_btn.clicked.connect(self.clear_log_plot)
        self.handoff_btn.clicked.connect(self.open_jana_handoff_dialog)
        primary_buttons.addWidget(self.run_btn, 1)
        primary_buttons.addWidget(self.handoff_btn, 1)
        secondary_buttons.addWidget(self.stop_btn, 2)
        secondary_buttons.addWidget(self.stop_now_btn, 1)
        secondary_buttons.addWidget(self.clear_btn, 1)
        left_layout.addLayout(primary_buttons)
        left_layout.addLayout(secondary_buttons)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Idle")
        self.progress_bar.setToolTip("Cycle-level progress indicator for the iterative pipeline.")
        left_layout.addWidget(self.progress_bar)
        self.configuration_lock_hint = QLabel("Configuration locked while the pipeline is running.")
        self.configuration_lock_hint.setObjectName("configurationLockHint")
        self.configuration_lock_hint.setVisible(False)
        left_layout.addWidget(self.configuration_lock_hint)
        self._set_run_status("Ready")

        # Right-side resizable scientific dashboard
        self.result_splitter = QSplitter(Qt.Vertical)
        self.result_splitter.setObjectName("resultSplitter")
        self.result_splitter.setHandleWidth(3)
        self.result_splitter.setChildrenCollapsible(False)
        right_layout.addWidget(self.result_splitter, 1)

        metrics_section, metrics_layout = make_result_section("SUPERFLIP CONVERGENCE")
        self.figure = Figure(figsize=(7.5, 3.5), dpi=100)
        self.ax = self.figure.add_subplot(111)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setObjectName("metricsCanvas")
        self.canvas.setMinimumHeight(150)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.canvas.mpl_connect("resize_event", lambda _event: self._layout_metrics_figure())
        self.canvas.setToolTip("")
        metrics_layout.addWidget(self.canvas, 1)
        self.result_splitter.addWidget(metrics_section)

        structure_section, structure_layout = make_result_section("STRUCTURE COMPARISON")
        self.structure_figure = Figure(figsize=(7.5, 3.0), dpi=100)
        self.structure_canvas = FigureCanvas(self.structure_figure)
        self.structure_canvas.setObjectName("structureCanvas")
        self.structure_canvas.setMinimumHeight(260)
        self.structure_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.structure_canvas.setToolTip("Drag any structure preview to rotate all three views together. Hydrogens are hidden.")
        self.structure_canvas.mpl_connect("button_press_event", self._begin_structure_rotation)
        self.structure_canvas.mpl_connect("motion_notify_event", self._sync_structure_view_from_event)
        self.structure_canvas.mpl_connect("button_release_event", self._finish_structure_rotation)
        self.structure_canvas.mpl_connect("resize_event", lambda _event: self._layout_structure_figure())
        structure_layout.addWidget(self.structure_canvas, 1)
        self.result_splitter.addWidget(structure_section)

        log_section, log_layout = make_result_section("EXECUTION LOG")
        self.log_text = QTextEdit()
        self.log_text.setObjectName("executionLog")
        self.log_text.setReadOnly(True)
        self.log_text.setLineWrapMode(QTextEdit.NoWrap)
        self.log_text.setMinimumHeight(100)
        self.log_text.setToolTip("")
        log_layout.addWidget(self.log_text, 1)
        self.result_splitter.addWidget(log_section)
        self.result_splitter.setStretchFactor(0, 2)
        self.result_splitter.setStretchFactor(1, 5)
        self.result_splitter.setStretchFactor(2, 2)
        self.result_splitter.setSizes([170, 390, 140])
        self.log_text.append("Ready. Select Jana .inflip, Jana .inflip with overrides, or external HKL + CIF input mode.")
        self.log_text.append("Defaults: later-cycle Superflip modelfiles can use raw Superflip XPLOR, deblurred XPLOR, or EDMA CIF.")
        self._update_action_states()
        self._update_plot()
        self._update_structure_views()
        self._sync_input_source_mode_widgets()
        self._sync_workflow_widgets()

    def _sync_workflow_widgets(self) -> None:
        if self._configuration_locked:
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
                cycles_widget.setToolTip("Next-cycle modelfile is none, so there is no feedback model for later cycles. The run is therefore forced to one cycle.")
            else:
                cycles_widget.setEnabled(True)
                cycles_widget.setToolTip(INPUT_TOOLTIPS.get("cycles", ""))
            cycles_label = self.input_labels.get("cycles")
            if cycles_label is not None:
                cycles_label.setEnabled(mode != "none")
        if isinstance(damping_widget, QDoubleSpinBox):
            damping_widget.setEnabled(mode in {"superflip_xplor", "deblurred_xplor"})
            damping_label = self.input_labels.get("damping_factor")
            if damping_label is not None:
                damping_label.setEnabled(mode in {"superflip_xplor", "deblurred_xplor"})
            if mode in {"superflip_xplor", "deblurred_xplor"}:
                damping_widget.setToolTip(INPUT_TOOLTIPS.get("damping_factor", ""))
            else:
                damping_widget.setToolTip("XPLOR damping is used only when Next-cycle modelfile is superflip_xplor or deblurred_xplor.")
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

    def _sync_input_source_mode_widgets(self) -> None:
        if self._configuration_locked:
            return
        mode = normalize_input_source_mode(self._combo_value("input_source_mode") if "input_source_mode" in self.inputs else "")
        jana_enabled = mode in {INPUT_MODE_INFLIP, INPUT_MODE_INFLIP_OVERRIDES}
        override_enabled = mode == INPUT_MODE_INFLIP_OVERRIDES
        external_enabled = mode == INPUT_MODE_EXTERNAL
        for key, enabled in (
            ("jana_inflip", jana_enabled),
            ("hkl", override_enabled or external_enabled),
            ("reference_cif", True),
        ):
            widget = self.inputs.get(key)
            if hasattr(widget, "setEnabled"):
                widget.setEnabled(bool(enabled))  # type: ignore[attr-defined]
            label = self.input_labels.get(key)
            if label is not None:
                label.setEnabled(bool(enabled))

    def _set_configuration_locked(self, locked: bool) -> None:
        locked = bool(locked)
        was_locked = self._configuration_locked
        self._configuration_locked = locked
        for key, widget in self.inputs.items():
            if hasattr(widget, "setEnabled"):
                widget.setEnabled(not locked)  # type: ignore[attr-defined]
            label = self.input_labels.get(key)
            if label is not None:
                label.setEnabled(not locked)
        for name in ("test_hkl_btn", "analyze_hkl_btn", "refresh_models_btn", "load_inflip_btn"):
            action = getattr(self, name, None)
            if action is not None:
                action.setEnabled(not locked)
        if hasattr(self, "configuration_lock_hint"):
            self.configuration_lock_hint.setVisible(locked)
        if was_locked and not locked:
            self._sync_input_source_mode_widgets()
            self._sync_workflow_widgets()

    def _widget_value_as_string(self, widget: object) -> str:
        if isinstance(widget, PathRow):
            return widget.value()
        if isinstance(widget, QLineEdit):
            return widget.text()
        if isinstance(widget, QTextEdit):
            return widget.toPlainText()
        if isinstance(widget, QComboBox):
            return widget.currentText()
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
                idx = widget.findText(value)
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
        for key, widget in self.inputs.items():
            value = self.settings.value(f"inputs/{key}", None)
            if value is not None:
                if key == "reflection_data_mode":
                    value = normalize_reflection_data_mode(str(value))
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
        # Backward compatibility with older GUI versions that had one common
        # EDMA plimit field named "plimit".
        old_plimit = self.settings.value("inputs/plimit", None)
        if old_plimit is not None:
            if self.settings.value("inputs/plimit_superflip", None) is None and "plimit_superflip" in self.inputs:
                self._set_widget_value_from_string(self.inputs["plimit_superflip"], str(old_plimit))
            if self.settings.value("inputs/plimit_deblur", None) is None and "plimit_deblur" in self.inputs:
                self._set_widget_value_from_string(self.inputs["plimit_deblur"], str(old_plimit))
        legacy_reference_xplor = self.settings.value("inputs/superflip_reference_xplor", None)
        legacy_superflip_referencefile = self.settings.value("inputs/superflip_referencefile", None)
        referencefile_widget = self.inputs.get("reference_cif")
        if referencefile_widget is not None and not self._widget_value_as_string(referencefile_widget).strip():
            legacy_reference = legacy_superflip_referencefile or legacy_reference_xplor
            if legacy_reference:
                self._set_widget_value_from_string(referencefile_widget, str(legacy_reference))
        self._sync_input_source_mode_widgets()
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
            QMessageBox.information(self, "Loaded .inflip settings", f"Loaded {applied} GUI settings from:\n{path}\n\nHKL data format was imported when dataformat/dataitemwidths were present. Reflection records and crystallographic blocks were not copied into editable fields.")
        except Exception as exc:
            QMessageBox.critical(self, "Load .inflip failed", str(exc))

    def _collect_hkl_analysis_request(self) -> HklAnalysisRequest:
        mode = normalize_input_source_mode(self._combo_value("input_source_mode") if "input_source_mode" in self.inputs else "")
        hkl_text = self._path_value("hkl").strip() if "hkl" in self.inputs else ""
        jana_text = self._path_value("jana_inflip").strip() if "jana_inflip" in self.inputs else ""
        ref_text = self._path_value("reference_cif").strip() if "reference_cif" in self.inputs else ""
        work_text = self._path_value("work_dir").strip() if "work_dir" in self.inputs else ""
        configured_mode = self._combo_value("reflection_data_mode") if "reflection_data_mode" in self.inputs else REFLECTION_DATA_MODE_AUTO
        return HklAnalysisRequest(mode, hkl_text, jana_text, ref_text, work_text, configured_mode)

    def _resolve_hkl_analysis_inputs(self, request: HklAnalysisRequest) -> Tuple[Path, str, gemmi.UnitCell, gemmi.SpaceGroup, str, str]:
        work_dir = Path(request.work_text).expanduser().resolve() if request.work_text else Path.cwd()
        jana_path = Path(request.jana_text).expanduser().resolve() if request.jana_text else None
        use_inflip_hkl = request.mode == INPUT_MODE_INFLIP or (request.mode == INPUT_MODE_INFLIP_OVERRIDES and not request.hkl_text)
        if use_inflip_hkl:
            if jana_path is None or not jana_path.is_file():
                raise FileNotFoundError("Jana .inflip is required to test or analyze embedded HKL data.")
            hkl_path = extract_embedded_hkl_from_inflip(jana_path, work_dir)
            cell, sg, hm, _composition = parse_inflip_crystallography(jana_path)
            source_note = f"HKL source: fbegin/endf block exported from {jana_path}"
        else:
            if not request.hkl_text:
                raise FileNotFoundError("Select an external HKL file or a Jana .inflip with embedded reflections.")
            hkl_path = Path(request.hkl_text).expanduser().resolve()
            if not hkl_path.is_file():
                raise FileNotFoundError(f"HKL file not found: {hkl_path}")
            if request.ref_text and Path(request.ref_text).expanduser().is_file() and Path(request.ref_text).suffix.lower() in REFERENCE_STRUCTURE_SUFFIXES:
                ref_path = Path(request.ref_text).expanduser().resolve()
                cell, sg, hm = parse_cif_cell_and_sg(ref_path)
                source_note = f"HKL source: {hkl_path}; cell/symmetry source: {ref_path}"
            elif jana_path is not None and jana_path.is_file():
                cell, sg, hm, _composition = parse_inflip_crystallography(jana_path)
                source_note = f"HKL source: {hkl_path}; cell/symmetry source: {jana_path}"
            else:
                raise FileNotFoundError("Select a CIF-compatible reference file or Jana .inflip so Phase Studio can calculate d-spacings and completeness.")
        if use_inflip_hkl:
            data_mode = embedded_reflection_data_mode_from_inflip(jana_path) or resolve_reflection_data_mode_from_sources(hkl_path, request.configured_mode, jana_path)
        else:
            data_mode = resolve_reflection_data_mode_from_sources(hkl_path, request.configured_mode, jana_path)
        return hkl_path, data_mode, cell, sg, hm, source_note

    def _hkl_analysis_inputs(self) -> Tuple[Path, str, gemmi.UnitCell, gemmi.SpaceGroup, str, str]:
        return self._resolve_hkl_analysis_inputs(self._collect_hkl_analysis_request())

    def _build_hkl_load_result(self, request: HklAnalysisRequest) -> HklLoadResult:
        hkl_path, data_mode, cell, sg, hm, source_note = self._resolve_hkl_analysis_inputs(request)
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

    def _set_hkl_task_running(self, running: bool) -> None:
        for button_name in ("test_hkl_btn", "analyze_hkl_btn"):
            button = getattr(self, button_name, None)
            if isinstance(button, QPushButton):
                button.setEnabled(not running and not self._configuration_locked)
        pipeline_active = self.worker is not None and self.worker.is_alive()
        if running and not pipeline_active:
            self.progress_bar.setRange(0, 0)
            self.progress_bar.setFormat("HKL analysis...")
        elif not running and not pipeline_active:
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("Idle")

    def _start_hkl_background_task(self, label: str, worker_fn: Callable[[], object], done_kind: str) -> None:
        if self.hkl_task_worker is not None and self.hkl_task_worker.is_alive():
            QMessageBox.information(self, "HKL analysis already running", "Wait for the current HKL load/completeness job to finish before starting another one.")
            return
        self._set_hkl_task_running(True)
        self.log_text.append(f"{label} started in background.")

        def worker() -> None:
            try:
                result = worker_fn()
                self.msg_queue.put((done_kind, result))
            except Exception as exc:
                self.msg_queue.put(("hkl_task_error", (label, str(exc))))
            finally:
                self.msg_queue.put(("hkl_task_finished", None))

        self.hkl_task_worker = threading.Thread(target=worker, daemon=True)
        self.hkl_task_worker.start()

    def test_hkl_load_dialog(self) -> None:
        request = self._collect_hkl_analysis_request()

        def worker() -> object:
            return self._build_hkl_load_result(request)

        self._start_hkl_background_task("HKL load test", worker, "hkl_load_result")

    def _show_hkl_load_result_dialog(self, payload: object) -> None:
        result = payload  # type: ignore[assignment]
        hkl_path = result.hkl_path  # type: ignore[attr-defined]
        data_mode = result.data_mode  # type: ignore[attr-defined]
        cell = result.cell  # type: ignore[attr-defined]
        hm = result.spacegroup_hm  # type: ignore[attr-defined]
        source_note = result.source_note  # type: ignore[attr-defined]
        value_col = result.value_col  # type: ignore[attr-defined]
        sigma_col = result.sigma_col  # type: ignore[attr-defined]
        include_000 = result.include_000  # type: ignore[attr-defined]
        reflections = result.reflections  # type: ignore[attr-defined]
        unique = result.unique_reflections  # type: ignore[attr-defined]
        dialog = QDialog(self)
        dialog.setWindowTitle("HKL Load Test")
        dialog.resize(860, 560)
        layout = QVBoxLayout(dialog)
        sigma_count = sum(1 for r in reflections if r.sigma is not None)
        phase_count = sum(1 for r in reflections if r.phase is not None)
        value_label = reflection_value_label(data_mode)
        sigma_label = reflection_sigma_label(data_mode)
        snr_label = reflection_primary_snr_label(data_mode)
        summary = QLabel(
            f"{source_note}\n"
            f"HKL data format: {data_mode}; value column: {value_col}; "
            f"sigma column: {sigma_col if sigma_col is not None else 'none'}; include 000: {'yes' if include_000 else 'no'}\n"
            f"Cell: {cell.a:.5g} {cell.b:.5g} {cell.c:.5g} {cell.alpha:.4g} {cell.beta:.4g} {cell.gamma:.4g}; space group: {hm}\n"
            f"Parsed reflections: {len(reflections)}; unique HKL after duplicate merge: {len(unique)}; "
            f"{sigma_label} loaded: {sigma_count}/{len(reflections)}; phase values loaded: {phase_count}/{len(reflections)}"
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)
        headers = ["h", "k", "l", value_label, sigma_label, "phase", snr_label, "derived I/sigma", "d", "sin(theta)/lambda"]
        rows = min(50, len(reflections))
        table = QTableWidget(rows, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        for row, r in enumerate(reflections[:rows]):
            d = reflection_d_spacing(cell, int(r.h), int(r.k), int(r.l))
            stl = reflection_sintheta_over_lambda(cell, int(r.h), int(r.k), int(r.l))
            primary_snr = reflection_primary_signal_to_noise(r, data_mode)
            derived_ios = reflection_signal_to_noise(r, data_mode)
            values = [
                str(int(r.h)),
                str(int(r.k)),
                str(int(r.l)),
                f"{float(r.value):.7g}",
                "n/a" if r.sigma is None else f"{float(r.sigma):.7g}",
                "n/a" if r.phase is None else f"{float(r.phase):.7g}",
                "n/a" if primary_snr is None else f"{float(primary_snr):.7g}",
                "n/a" if derived_ios is None else f"{float(derived_ios):.7g}",
                "n/a" if not math.isfinite(d) else f"{d:.5g}",
                f"{stl:.5g}",
            ]
            for col, text in enumerate(values):
                table.setItem(row, col, QTableWidgetItem(text))
        layout.addWidget(table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject)
        buttons.button(QDialogButtonBox.Close).clicked.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.exec()

    def open_hkl_completeness_dialog(self) -> None:
        request = self._collect_hkl_analysis_request()

        def worker() -> object:
            hkl_path, data_mode, cell, sg, hm, source_note = self._resolve_hkl_analysis_inputs(request)
            analysis = analyze_hkl_data(hkl_path, data_mode, cell, sg, hm, source_note)
            return analysis

        self._start_hkl_background_task("HKL completeness analysis", worker, "hkl_completeness_result")

    def _show_hkl_completeness_dialog(self, analysis: HklAnalysis) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("HKL Completeness and Intensity Statistics")
        dialog.resize(1120, 820)
        layout = QVBoxLayout(dialog)
        d_min_text = format_resolution_d(analysis.d_min)
        d_full = format_resolution_d(analysis.d_full_98)
        sigma_label = reflection_sigma_label(analysis.data_mode)
        signal_label = reflection_primary_snr_label(analysis.data_mode)
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
        threshold_d_text = format_resolution_d(threshold_d)
        stats_box = QGroupBox("Reflection Data Summary")
        stats_layout = QVBoxLayout(stats_box)
        source_label = QLabel(analysis.source_note)
        source_label.setWordWrap(True)
        stats_layout.addWidget(source_label)
        stats = [
            ("HKL data format", analysis.data_mode),
            ("Unit cell", f"{analysis.cell.a:.5g} {analysis.cell.b:.5g} {analysis.cell.c:.5g} {analysis.cell.alpha:.4g} {analysis.cell.beta:.4g} {analysis.cell.gamma:.4g}"),
            ("Space group", analysis.spacegroup_hm),
            ("Parsed / unique reflections", f"{len(analysis.reflections_raw)} / {len(analysis.reflections_unique)}"),
            (f"{sigma_label} coverage", f"{raw_sigma_count}/{len(analysis.reflections_raw)} raw; {unique_sigma_count}/{len(analysis.reflections_unique)} unique"),
            ("Phase values", f"{phase_count}/{len(analysis.reflections_raw)} raw"),
            ("d_min", d_min_text),
            ("d_full at 98% cumulative completeness", d_full),
            (f"Median {signal_label}", median_signal),
            (f"d where mean {signal_label} falls below {signal_threshold:.1f}", threshold_d_text),
        ]
        stats_rows = int(math.ceil(len(stats) / 2.0))
        stats_table = QTableWidget(stats_rows, 4)
        stats_table.setHorizontalHeaderLabels(["Statistic", "Value", "Statistic", "Value"])
        stats_table.setAlternatingRowColors(True)
        stats_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        stats_table.verticalHeader().setVisible(False)
        stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for idx, (name, value) in enumerate(stats):
            row = idx % stats_rows
            col = 0 if idx < stats_rows else 2
            stats_table.setItem(row, col, QTableWidgetItem(name))
            stats_table.setItem(row, col + 1, QTableWidgetItem(value))
        stats_table.setMaximumHeight(190)
        stats_layout.addWidget(stats_table)
        layout.addWidget(stats_box)
        figure = Figure(figsize=(8.4, 6.2), dpi=100)
        canvas = FigureCanvas(figure)
        ax1 = figure.add_subplot(211)
        ax2 = figure.add_subplot(212)
        centers = [float(b["center"]) for b in analysis.bins]
        widths = [max(0.0001, float(b["hi"]) - float(b["lo"])) for b in analysis.bins]
        completeness = [float(b["completeness"]) for b in analysis.bins]
        mean_signal = [float(b["mean_signal_to_noise"]) if math.isfinite(float(b["mean_signal_to_noise"])) else np.nan for b in analysis.bins]
        signal_values = [reflection_primary_signal_to_noise(r, analysis.data_mode) for r in analysis.reflections_unique]
        signal_values = [float(v) for v in signal_values if v is not None and math.isfinite(float(v))]
        d_min_stl = 1.0 / (2.0 * analysis.d_min) if analysis.d_min > 0 else None
        d_full_stl = 1.0 / (2.0 * analysis.d_full_98) if analysis.d_full_98 is not None and analysis.d_full_98 > 0 else None
        figure.patch.set_facecolor("#ffffff")
        ax1.set_facecolor("#ffffff")
        ax2.set_facecolor("#ffffff")
        ax1.bar(centers, completeness, width=widths, align="center", color="#2264b8", alpha=0.72, label="Completeness")
        ax1.axhline(98.0, color="#001170", linewidth=1.0, linestyle="--")
        if d_min_stl is not None:
            ax1.axvline(d_min_stl, color="#001170", linewidth=1.1, linestyle="-", label="d_min")
            ax1.text(d_min_stl, 103.0, f"d_min\n{d_min_text}", rotation=90, va="top", ha="right", color="#001170", fontsize=8)
        if d_full_stl is not None:
            ax1.axvline(d_full_stl, color="#44b7ff", linewidth=1.1, linestyle=":", label="d_full 98%")
            ax1.text(d_full_stl, 103.0, f"d_full\n{d_full}", rotation=90, va="top", ha="left", color="#44b7ff", fontsize=8)
        ax1.set_ylabel("Completeness (%)", labelpad=6, fontsize=9)
        ax1.set_xlabel("sin(theta)/lambda")
        ax1.set_ylim(0, 105)
        ax1.grid(True, axis="y", color="#44b7ff", alpha=0.25)
        ax1b = ax1.twinx()
        ax1b.plot(centers, mean_signal, marker="o", color="#001170", linewidth=1.8, label=f"Mean {signal_label}")
        ax1b.axhline(signal_threshold, color="#2264b8", linewidth=1.0, linestyle="--", label=f"{signal_label} = {signal_threshold:.1f}")
        ax1b.set_ylabel(f"Mean {signal_label}", labelpad=6, fontsize=9)
        if threshold_stl is not None:
            ax1.axvline(threshold_stl, color="#2264b8", linewidth=1.1, linestyle="-.", label=f"{signal_label} < {signal_threshold:.1f}")
            threshold_label = f"I/sigma<3\n{threshold_d_text}" if threshold_d is not None else "I/sigma<3"
            ax1.text(threshold_stl, 103.0, threshold_label, rotation=90, va="top", ha="left", color="#001170", fontsize=8)
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax1b.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc="lower left", fontsize=8)
        histogram_denominator = max(1, len(analysis.reflections_unique))
        if signal_values:
            histogram_bins = np.arange(0.0, 16.0, 1.0)
            histogram_weights = np.full(len(signal_values), 100.0 / float(histogram_denominator), dtype=np.float64)
            ax2.hist(signal_values, bins=histogram_bins, weights=histogram_weights, color="#44b7ff", alpha=0.82)
        else:
            ax2.text(0.5, 0.5, "No sigma values available", transform=ax2.transAxes, ha="center", va="center")
        ax2.set_xlabel(signal_label)
        ax2.set_ylabel("Reflections (%)", labelpad=6, fontsize=9)
        ax2.set_xlim(0.0, 15.0)
        ax2.set_xticks(np.arange(0.0, 16.0, 1.0))
        ax2.grid(True, axis="y", color="#44b7ff", alpha=0.25)
        for axis in (ax1, ax1b, ax2):
            axis.tick_params(colors="#001170")
            axis.xaxis.label.set_color("#001170")
            axis.yaxis.label.set_color("#001170")
        figure.tight_layout(pad=1.1)
        figure.subplots_adjust(left=0.08, right=0.91)
        layout.addWidget(canvas, 1)
        headers = ["sin(theta)/lambda bin", "Observed", "Theoretical", "Completeness %", f"Mean {signal_label}"]
        table = QTableWidget(len(analysis.bins), len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        for row, item in enumerate(analysis.bins):
            values = [
                f"{float(item['lo']):.4g} - {float(item['hi']):.4g}",
                str(int(item["observed"])),
                str(int(item["theory"])),
                f"{float(item['completeness']):.2f}",
                "n/a" if not math.isfinite(float(item["mean_signal_to_noise"])) else f"{float(item['mean_signal_to_noise']):.3g}",
            ]
            for col, text in enumerate(values):
                table.setItem(row, col, QTableWidgetItem(text))
        layout.addWidget(table)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject)
        buttons.button(QDialogButtonBox.Close).clicked.connect(dialog.accept)
        layout.addWidget(buttons)
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

    def clear_log_plot(self) -> None:
        self.log_text.clear()
        self.results.clear()
        self.reference_atoms_for_plot.clear()
        self.superflip_atoms_for_plot.clear()
        self.deblur_atoms_for_plot.clear()
        self.structure_cell = None
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Idle")
        self._set_run_status("Ready")
        if hasattr(self, "handoff_btn"):
            self.handoff_btn.setEnabled(False)
        self.last_run_config = None
        self._update_plot()
        self._update_structure_views()

    def log(self, message: str) -> None:
        self.msg_queue.put(("log", message))

    def _set_run_status(self, status: str) -> None:
        normalized = str(status).strip().upper() or "READY"
        normalized = {
            "IDLE": "READY",
            "DONE": "COMPLETE",
            "COMPLETED": "COMPLETE",
            "FAILED": "ERROR",
            "CANCELED": "CANCELLED",
        }.get(normalized, normalized)
        self._run_status = normalized
        if hasattr(self, "status_badge"):
            self.status_badge.setText(normalized)
            self.status_badge.setProperty("runState", normalized.lower())
            self.status_badge.style().unpolish(self.status_badge)
            self.status_badge.style().polish(self.status_badge)
        self._update_action_states()
        if hasattr(self, "canvas") and not getattr(self, "results", []):
            self._update_plot()
        if hasattr(self, "structure_canvas"):
            self._update_structure_views()

    def _update_action_states(self) -> None:
        status = str(getattr(self, "_run_status", "READY")).upper()
        active = status in {"RUNNING", "STOPPING"}
        self._set_configuration_locked(active)
        if hasattr(self, "run_btn"):
            self.run_btn.setEnabled(not active)
        if hasattr(self, "stop_btn"):
            self.stop_btn.setEnabled(status == "RUNNING")
        if hasattr(self, "stop_now_btn"):
            self.stop_now_btn.setEnabled(status in {"RUNNING", "STOPPING"})
        if hasattr(self, "clear_btn"):
            has_results = bool(getattr(self, "results", []))
            has_log = bool(hasattr(self, "log_text") and self.log_text.toPlainText().strip())
            self.clear_btn.setEnabled(not active and (has_results or has_log))
        if active and hasattr(self, "handoff_btn"):
            self.handoff_btn.setEnabled(False)

    def request_stop_after_cycle(self) -> None:
        self.stop_after_cycle.set()
        self._set_run_status("Stopping")
        self.log("Stop after current cycle requested.")

    def request_immediate_stop(self) -> None:
        self.stop_after_cycle.set()
        self.stop_now.set()
        self._set_run_status("Stopping")
        self.log("Immediate stop requested.")

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

        if "atomic" in name:
            set_value("reflection_data_mode", REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA)
            set_value("modelfile_source", "deblurred_xplor")
            set_value("plimit_superflip", "3.0")
            set_value("plimit_deblur", "3.0")
            set_value("resolution_d_min", "0.9")
            set_value("bestdensities_symmetry", "true")
            set_value("export_superflip_xplor", "true")
            set_value("export_superflip_jana", "true")
        elif "medium" in name:
            set_value("reflection_data_mode", REFLECTION_DATA_MODE_AUTO)
            set_value("modelfile_source", "deblurred_edma_cif")
            set_value("plimit_superflip", "0.5")
            set_value("plimit_deblur", "0.5")
            set_value("resolution_d_min", "0.0")
        elif "small" in name:
            set_value("reflection_data_mode", REFLECTION_DATA_MODE_INTENSITY)
            set_value("modelfile_source", "deblurred_edma_cif")
            set_value("plimit_superflip", "0.5")
            set_value("plimit_deblur", "0.5")
            set_value("bestdensities_metric", "rvalue")
        elif "inorganic" in name:
            set_value("reflection_data_mode", REFLECTION_DATA_MODE_AUTO)
            set_value("modelfile_source", "deblurred_edma_cif")
            set_value("plimit_superflip", "1.0")
            set_value("plimit_deblur", "1.0")
            set_value("bestdensities_symmetry", "true")
        self._sync_workflow_widgets()

    def _poll_queue(self) -> None:
        try:
            processed = 0
            while processed < 250:
                kind, payload = self.msg_queue.get_nowait()
                processed += 1
                if kind == "log":
                    self.log_text.append(str(payload))
                    self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())
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
                    self.log_text.append("SharpED models refreshed.")
                elif kind == "hkl_load_result":
                    self.log_text.append("HKL load test finished.")
                    self._set_hkl_task_running(False)
                    self._show_hkl_load_result_dialog(payload)
                elif kind == "hkl_completeness_result":
                    self.log_text.append("HKL completeness analysis finished.")
                    self._set_hkl_task_running(False)
                    self._show_hkl_completeness_dialog(payload)  # type: ignore[arg-type]
                elif kind == "hkl_task_error":
                    label, message = payload  # type: ignore[misc]
                    self._set_hkl_task_running(False)
                    QMessageBox.critical(self, f"{label} failed", str(message))
                    self.log_text.append(f"\n{label} ERROR: {message}")
                elif kind == "hkl_task_finished":
                    self._set_hkl_task_running(False)
                elif kind == "handoff_done":
                    self._set_run_status("Transferred")
                    self.log_text.append("\nJana2020 hand-off completed. Phase Studio will close automatically.")
                    self.handoff_btn.setEnabled(False)
                    QTimer.singleShot(400, QApplication.instance().quit)
                elif kind == "handoff_error":
                    self._set_run_status("Error")
                    QMessageBox.critical(self, "Jana2020 hand-off failed", str(payload))
                    self.log_text.append("\nJana2020 hand-off ERROR: " + str(payload))
                    self.handoff_btn.setEnabled(bool(self.results and self.last_run_config and self.last_run_config.jana_inflip is not None))
                elif kind == "progress_setup":
                    self._set_run_status("Running")
                    total = max(1, int(payload))
                    self.progress_bar.setRange(0, total)
                    self.progress_bar.setValue(0)
                    self.progress_bar.setFormat("0/%m cycles")
                elif kind == "progress":
                    value = int(payload)
                    self.progress_bar.setValue(value)
                    self.progress_bar.setFormat(f"{value}/{self.progress_bar.maximum()} cycles")
                elif kind == "error":
                    self._set_run_status("Error")
                    QMessageBox.critical(self, "Pipeline error", str(payload))
                    self.log_text.append("\nERROR: " + str(payload))
                    self.progress_bar.setFormat("Error")
                    self.run_btn.setEnabled(True)
                    self.handoff_btn.setEnabled(False)
                    self.run_btn.setText("Run pipeline")
                elif kind == "done":
                    self._set_run_status("Complete")
                    self.log_text.append("\nDone.")
                    if payload is not None:
                        self.progress_bar.setValue(int(payload))
                    self.progress_bar.setFormat("Done")
                    self.run_btn.setEnabled(True)
                    self.run_btn.setText("Run pipeline")
                    can_handoff = bool(self.results and self.last_run_config and self.last_run_config.jana_inflip is not None)
                    self.handoff_btn.setEnabled(can_handoff)
                    if can_handoff:
                        self.log_text.append("Jana2020 hand-off is ready. Use 'Send to Jana2020' to select the cycle and map source.")
        except queue.Empty:
            pass

    def _recommended_handoff_index(self) -> int:
        if not self.results:
            return -1
        finite_symm = [
            (idx, float(r.superflip_symm))
            for idx, r in enumerate(self.results)
            if r.superflip_symm is not None and np.isfinite(float(r.superflip_symm))
        ]
        if finite_symm:
            # Superflip's Symm. column is an agreement residual; lower values mean better symmetry agreement.
            return min(finite_symm, key=lambda item: item[1])[0]
        finite_ref = [
            (idx, float(r.superflip_ref_match))
            for idx, r in enumerate(self.results)
            if r.superflip_ref_match is not None and np.isfinite(float(r.superflip_ref_match))
        ]
        if finite_ref:
            return min(finite_ref, key=lambda item: item[1])[0]
        return len(self.results) - 1

    def open_jana_handoff_dialog(self) -> None:
        cfg = self.last_run_config
        if cfg is None or cfg.jana_inflip is None:
            QMessageBox.warning(self, "Jana2020 hand-off", "This run was not started from a Jana .inflip file.")
            return
        if not self.results:
            QMessageBox.warning(self, "Jana2020 hand-off", "No completed cycle is available for hand-off.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Pass Phase Studio result to Jana2020")
        dialog.resize(1180, 560)
        layout = QVBoxLayout(dialog)
        info = QLabel(
            "Select the completed Phase Studio cycle and the map that should be used "
            "as the model for Jana2020's final Superflip hand-off. The table shows "
            "all Superflip metrics currently parsed from every completed cycle. Rvalue, "
            "Peaks, Symm. and Der.SG come from the saved-density run actually used by Superflip."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        headers = [
            "Cycle",
            "Saved run",
            "Rvalue",
            "Peaks",
            "Symm.",
            "Der.SG",
            "Ref.match",
            "FoM / Score",
            "Success rate %",
            "Mean cycles",
            "Superflip map",
            "Deblurred map",
        ]
        metrics_table = QTableWidget(len(self.results), len(headers))
        metrics_table.setHorizontalHeaderLabels(headers)
        metrics_table.setAlternatingRowColors(True)
        metrics_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        metrics_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        metrics_table.setSelectionMode(QAbstractItemView.SingleSelection)
        metrics_table.verticalHeader().setVisible(False)
        metrics_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        metrics_table.horizontalHeader().setStretchLastSection(False)

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

        for row, result in enumerate(self.results):
            values = [
                f"{int(result.cycle):03d}",
                "n/a" if result.superflip_saved_run is None else str(int(result.superflip_saved_run)),
                fmt(result.superflip_rvalue),
                fmt(result.superflip_peaks),
                fmt(result.superflip_symm),
                result.superflip_derived_sg or "n/a",
                fmt(result.superflip_ref_match),
                fmt(result.superflip_fom),
                fmt(result.superflip_success_rate),
                fmt(result.superflip_mean_cycles),
                "available" if Path(result.superflip_map).is_file() else "missing",
                "available" if Path(result.deblur_map).is_file() else "missing",
            ]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setData(Qt.UserRole, int(result.cycle))
                metrics_table.setItem(row, col, item)
        layout.addWidget(metrics_table, 1)

        form = QFormLayout()
        cycle_combo = QComboBox()
        for result in self.results:
            symm = "n/a" if result.superflip_symm is None else f"{float(result.superflip_symm):.3f}"
            rvalue = "n/a" if result.superflip_rvalue is None else f"{float(result.superflip_rvalue):.3f}"
            run_label = "n/a" if result.superflip_saved_run is None else str(int(result.superflip_saved_run))
            label = f"Cycle {int(result.cycle):03d} — saved run {run_label}, Symm. {symm}, Rvalue {rvalue}"
            cycle_combo.addItem(label, int(result.cycle))
        recommended = self._recommended_handoff_index()
        if recommended >= 0:
            cycle_combo.setCurrentIndex(recommended)
            metrics_table.selectRow(recommended)

        map_combo = QComboBox()
        map_combo.addItem("Deblurred map (SharpED output)", "deblurred")
        map_combo.addItem("Superflip map", "superflip")
        try:
            rec = self.results[recommended]
            if not Path(rec.deblur_map).is_file():
                map_combo.setCurrentIndex(1)
        except Exception:
            pass

        def sync_table_from_combo(index: int) -> None:
            if 0 <= index < metrics_table.rowCount():
                metrics_table.selectRow(index)

        def sync_combo_from_table() -> None:
            row = metrics_table.currentRow()
            if 0 <= row < cycle_combo.count() and row != cycle_combo.currentIndex():
                cycle_combo.setCurrentIndex(row)

        cycle_combo.currentIndexChanged.connect(sync_table_from_combo)
        metrics_table.itemSelectionChanged.connect(sync_combo_from_table)

        form.addRow("Cycle", cycle_combo)
        form.addRow("Map source", map_combo)
        layout.addLayout(form)

        note = QLabel(
            "The suggested cycle is selected by the best Superflip symmetry agreement "
            "(lowest Symm. residual). You can override it manually. After a successful "
            "hand-off Phase Studio closes automatically."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Pass to Jana2020")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.Accepted:
            return

        selected_cycle = int(cycle_combo.currentData())
        selected_map = str(map_combo.currentData() or "deblurred")
        selected_result = next((r for r in self.results if int(r.cycle) == selected_cycle), None)
        if selected_result is None:
            QMessageBox.warning(self, "Jana2020 hand-off", "Selected cycle is no longer available.")
            return

        self.handoff_btn.setEnabled(False)
        self.log_text.append(f"\nStarting Jana2020 hand-off from cycle {selected_cycle:03d} ({selected_map}).")

        def worker() -> None:
            try:
                perform_jana_handoff(cfg, selected_result, selected_map, log=self.log)
                self.msg_queue.put(("handoff_done", None))
            except Exception as exc:
                self.msg_queue.put(("handoff_error", exc))

        threading.Thread(target=worker, daemon=True).start()

    def _layout_metrics_figure(self) -> None:
        width = max(1.0, float(self.canvas.width()))
        height = max(1.0, float(self.canvas.height()))
        has_data = bool(self.results)
        left_pixels = 86.0 if has_data else 70.0
        left = min(0.18, max(0.07, left_pixels / width))
        right = 1.0 - min(0.04, max(0.02, 18.0 / width))
        bottom = min(0.22, max(0.12, 34.0 / height))
        if has_data:
            # Keep the figure-level legend in a stable band above the axes.
            top = 1.0 - min(0.30, max(0.20, 50.0 / height))
        else:
            top = 1.0 - min(0.16, max(0.07, 22.0 / height))
        self.figure.subplots_adjust(left=left, right=right, bottom=bottom, top=top)

    def _set_metrics_data_layout(self, has_data: bool) -> None:
        if not hasattr(self, "result_splitter"):
            return
        if has_data == self._metrics_expanded:
            return
        sizes = self.result_splitter.sizes()
        if len(sizes) != 3 or sum(sizes) <= 0:
            return
        if has_data:
            self._metrics_compact_sizes = list(sizes)
            available = sum(sizes)
            desired_metrics = min(max(sizes[0] + 45, 215), int(available * 0.34))
            increase = max(0, desired_metrics - sizes[0])
            structure_room = max(0, sizes[1] - 330)
            from_structure = min(increase, structure_room)
            from_log = min(increase - from_structure, max(0, sizes[2] - 110))
            self.result_splitter.setSizes([
                sizes[0] + from_structure + from_log,
                sizes[1] - from_structure,
                sizes[2] - from_log,
            ])
        elif self._metrics_compact_sizes:
            self.result_splitter.setSizes(self._metrics_compact_sizes)
            self._metrics_compact_sizes = None
        self._metrics_expanded = has_data

    def _update_plot(self) -> None:
        self.figure.clear()
        self.ax = self.figure.add_subplot(111)
        self.figure.patch.set_facecolor("#ffffff")
        self.ax.set_facecolor("#ffffff")
        cycles = [r.cycle for r in self.results]
        if not cycles:
            self._set_metrics_data_layout(False)
            status = str(getattr(self, "_run_status", "READY")).upper()
            if status in {"RUNNING", "STOPPING"}:
                empty_message = "Waiting for the first convergence metrics…"
            elif status in {"ERROR", "CANCELLED"}:
                empty_message = "No convergence metrics available."
            else:
                empty_message = "Run the pipeline to display convergence metrics."
            self.ax.set_axis_off()
            self.ax.text(
                0.5,
                0.50,
                empty_message,
                ha="center",
                va="center",
                color="#2264b8",
                transform=self.ax.transAxes,
            )
            self._layout_metrics_figure()
            self.canvas.draw_idle()
            return

        self._set_metrics_data_layout(True)
        self.ax.set_title("")
        self.ax.set_xlabel("")
        self.figure.text(0.5, 0.018, "Cycle", ha="center", va="bottom", color="#2264b8", fontsize=8.5)
        self.ax.set_ylim(-0.04, 1.04)
        self.ax.set_yticks([0.0, 0.25, 0.5, 0.75, 1.0])
        self.ax.set_yticklabels(["Worst 0.00", "0.25", "0.50", "0.75", "Best 1.00"])
        try:
            cycles_to_run = max(1, self._spin_value("cycles"))
        except Exception:
            cycles_to_run = max(cycles) if cycles else 1
        x_max = max([cycles_to_run] + cycles) if cycles else cycles_to_run
        self.ax.set_xlim(0.75, float(x_max) + 0.25)
        if x_max <= 30:
            self.ax.set_xticks(list(range(1, x_max + 1)))
        else:
            self.ax.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=12, min_n_ticks=2))
        self.ax.grid(True, axis="y", color="#44b7ff", linewidth=0.7, alpha=0.24)
        self.ax.grid(True, axis="x", color="#44b7ff", linewidth=0.55, alpha=0.14)
        for spine in ("top", "right"):
            self.ax.spines[spine].set_visible(False)
        self.ax.spines["left"].set_color("#001170")
        self.ax.spines["bottom"].set_color("#001170")
        self.ax.tick_params(colors="#001170")
        self.ax.title.set_color("#001170")
        self.ax.xaxis.label.set_color("#001170")
        self.ax.yaxis.label.set_color("#001170")

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

        series = [
            ("R", [r.superflip_rvalue for r in self.results], False, "#001170", "o", "-"),
            ("Peaks", [r.superflip_peaks for r in self.results], True, "#2264b8", "s", "-"),
            ("Symmetry", [r.superflip_symm for r in self.results], False, "#44b7ff", "^", "-"),
            ("Reference match", [r.superflip_ref_match for r in self.results], False, "#001170", "D", ":"),
            ("FOM", [r.superflip_fom for r in self.results], True, "#2264b8", "P", "--"),
            ("SF RMSD", [r.superflip_metric for r in self.results], False, "#44b7ff", "v", "-."),
            ("Deblur RMSD", [r.deblur_metric for r in self.results], False, "#001170", "X", "--"),
        ]
        plotted = 0
        for label, values, higher_is_better, color, marker, linestyle in series:
            y = best_score(values, higher_is_better)
            if not np.any(np.isfinite(np.asarray(y, dtype=float))):
                continue
            plotted += 1
            self.ax.plot(
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
        if plotted:
            handles, labels = self.ax.get_legend_handles_labels()
            if len(handles) == 7:
                # Matplotlib fills multi-column legends down each column.
                # Reorder only the legend handles to retain natural row order.
                legend_order = (0, 4, 1, 5, 2, 6, 3)
                handles = [handles[index] for index in legend_order]
                labels = [labels[index] for index in legend_order]
            self.figure.legend(
                handles,
                labels,
                loc="upper center",
                bbox_to_anchor=(0.5, 0.985),
                ncol=min(4, plotted),
                frameon=False,
                fontsize=7.4,
                handlelength=1.7,
                columnspacing=1.0,
                handletextpad=0.4,
                borderaxespad=0.0,
            )
        else:
            self.ax.text(
                0.5,
                0.5,
                "No finite metrics yet",
                ha="center",
                va="center",
                color="#2264b8",
                transform=self.ax.transAxes,
            )
        self._layout_metrics_figure()
        self.canvas.draw_idle()

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
            ax.text2D(0.5, 0.50, empty_text, ha="center", va="center", fontsize=9, color="#2264b8", transform=ax.transAxes)
            return ""

        non_h_atoms = [a for a in atoms if clean_element_symbol(a.element) not in {"H", "D", "He"}]
        if not non_h_atoms:
            ax.set_axis_off()
            ax.text2D(0.5, 0.50, "No non-H/He atoms", ha="center", va="center", fontsize=9, color="#2264b8", transform=ax.transAxes)
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
        for start, end in cell_edges:
            edge = cell_corners[[start, end]]
            ax.plot(edge[:, 0], edge[:, 1], edge[:, 2], color="#44b7ff", linewidth=0.55, alpha=0.46)

        colors = [self._element_color(a.element) for a in plot_atoms]
        atom_count = len(non_h_atoms)
        count_scale = float(np.interp(
            atom_count,
            [10, 50, 200, 500, 1000, 2000],
            [1.30, 1.0, 0.72, 0.48, 0.34, 0.22],
        ))
        sizes = [max(4.0, min(76.0, (10.0 + 1.2 * element_atomic_number(a.element)) * count_scale)) for a in plot_atoms]
        ax.scatter(
            coords[:, 0], coords[:, 1], coords[:, 2], s=sizes, c=colors,
            alpha=0.84, edgecolors="#ffffff", linewidths=0.18, depthshade=True,
        )
        shown = len(plot_atoms)
        suffix = "" if shown == len(non_h_atoms) else f"; first {shown} heaviest shown"
        return f"{len(non_h_atoms)} non-H/He atoms{suffix}"

    def _safe_parse_structure(self, path: Optional[Path]) -> List[AtomSite]:
        if path is None or not Path(path).is_file():
            return []
        try:
            _, sg, _ = parse_cif_cell_and_sg(Path(path))
            return expand_atoms_by_symmetry(parse_cif_atoms(Path(path)), sg)
        except Exception:
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
        status = str(getattr(self, "_run_status", "READY")).upper()
        waiting = status in {"RUNNING", "STOPPING"}
        failed = status in {"ERROR", "CANCELLED"}
        panels = [
            ("Reference", self.reference_atoms_for_plot, "No structure available"),
            (
                "Superflip",
                self.superflip_atoms_for_plot,
                "Waiting for Superflip result…" if waiting else ("Superflip result unavailable" if failed else "No structure available"),
            ),
            (
                "SharpED",
                self.deblur_atoms_for_plot,
                "Waiting for SharpED result…" if waiting else ("SharpED result unavailable" if failed else "No structure available"),
            ),
        ]
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
                color="#2264b8",
            )
            for x_position, metadata in zip((1.0 / 6.0, 0.5, 5.0 / 6.0), panel_metadata)
        ]
        self.structure_separators = []
        for x_position in (1.0 / 3.0, 2.0 / 3.0):
            separator = Line2D(
                [x_position, x_position], [0.08, 0.90],
                transform=self.structure_figure.transFigure,
                color="#44b7ff", linewidth=0.55, alpha=0.45,
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
        return RunConfig(
            hkl=hkl_path,
            reference_cif=reference_cif_path,
            superflip_reference_xplor=reference_xplor,
            superflip_referencefile=superflip_referencefile,
            first_cycle_modelfile=first_model,
            input_source_mode=input_source_mode,
            jana_inflip=jana_inflip,
            jana_return_to_jana=bool(jana_inflip is not None),
            work_dir=Path(self._path_value("work_dir")).expanduser().resolve(),
            cycles=cycles_value,
            superflip_exe=self._path_value("superflip_exe") or "superflip",
            edma_exe=self._path_value("edma_exe") or "EDMA",
            composition_override=self._line_value("composition_override"),
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
            exclude_atoms=self._line_value("exclude_atoms") or "none",
            perform_algorithm=self._combo_value("perform_algorithm") or "CF",
            output_format=normalize_output_format(self._combo_value("output_format")),
            write_auxiliary_outputs=self._check_value("write_auxiliary_outputs"),
            export_superflip_xplor=self._check_value("export_superflip_xplor"),
            export_superflip_ccp4=self._check_value("export_superflip_ccp4"),
            export_superflip_jana=self._check_value("export_superflip_jana"),
            export_standard_hkl=self._check_value("export_standard_hkl"),
            export_jana_project=self._check_value("export_jana_project"),
            referencefile_mode=referencefile_mode,
            voxel=self._line_value("voxel"),
            bestdensities_count=self._spin_value("bestdensities_count"),
            bestdensities_metric=normalize_bestdensities_metric(self._combo_value("bestdensities_metric")),
            bestdensities_symmetry=self._check_value("bestdensities_symmetry"),
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
            map_feedback_missing_from_cycle=self._spin_value("map_feedback_missing_from_cycle"),
            map_feedback_missing_percent_limit=self._dspin_value("map_feedback_missing_percent_limit"),
            map_feedback_intensity_from_cycle=self._spin_value("map_feedback_intensity_from_cycle"),
            map_feedback_intensity_damping=self._dspin_value("map_feedback_intensity_damping"),
            map_feedback_intensity_max_i_over_sigma=self._dspin_value("map_feedback_intensity_max_i_over_sigma"),
            run_sharped=self._check_value("run_sharped") and modelfile_source_value != "superflip_xplor",
            symmetrize_deblurred_map=self._check_value("symmetrize_deblurred_map") and modelfile_source_value != "superflip_xplor",
            run_edma_superflip=self._check_value("run_edma_superflip"),
            run_edma_deblurred=self._check_value("run_edma_deblurred"),
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

    def start_run(self) -> None:
        if self.worker and self.worker.is_alive():
            QMessageBox.warning(self, "Already running", "Pipeline is already running.")
            return
        try:
            cfg = self.get_config()
            mode = normalize_input_source_mode(cfg.input_source_mode)
            hkl_text = self._path_value("hkl").strip()
            ref_text = self._path_value("reference_cif").strip()
            ref_suffix = cfg.superflip_referencefile.suffix.lower() if cfg.superflip_referencefile is not None else ""
            if mode in {INPUT_MODE_INFLIP, INPUT_MODE_INFLIP_OVERRIDES}:
                if cfg.jana_inflip is None or not cfg.jana_inflip.is_file():
                    raise FileNotFoundError("Jana .inflip input mode requires a readable Jana .inflip file.")
                if mode == INPUT_MODE_INFLIP:
                    self.log_text.append("Input mode: Jana .inflip. HKL and reference metadata will be taken from the .inflip file.")
                else:
                    if hkl_text and not cfg.hkl.is_file():
                        raise FileNotFoundError(f"HKL override not found: {cfg.hkl}")
                    if ref_text and (cfg.superflip_referencefile is None or not cfg.superflip_referencefile.is_file()):
                        raise FileNotFoundError(f"External reference file not found: {cfg.superflip_referencefile}")
                    if not hkl_text:
                        self.log_text.append("HKL override is empty; the Jana .inflip fbegin/endf block will be used.")
                    if not ref_text:
                        self.log_text.append("External reference file is empty; the Jana .inflip cell/space group/composition will be used.")
            else:
                if not cfg.hkl.is_file():
                    raise FileNotFoundError(f"External HKL not found: {cfg.hkl}")
                if cfg.superflip_referencefile is None or not cfg.superflip_referencefile.is_file():
                    raise FileNotFoundError(f"External reference file not found: {cfg.superflip_referencefile}")
                if ref_suffix not in REFERENCE_STRUCTURE_SUFFIXES:
                    raise ValueError(
                        "External HKL mode requires External reference file to be a CIF/INS/RES structure, "
                        "because Phase Studio needs cell, symmetry, composition and reference atoms. "
                        "Jana/XPLOR/CCP4 density reference files are supported in Jana .inflip modes."
                    )
            if cfg.first_cycle_modelfile is not None and not cfg.first_cycle_modelfile.is_file():
                raise FileNotFoundError(f"First-cycle modelfile not found: {cfg.first_cycle_modelfile}")
            if cfg.superflip_referencefile is not None:
                if not cfg.superflip_referencefile.is_file():
                    raise FileNotFoundError(f"External reference file not found: {cfg.superflip_referencefile}")
                if ref_suffix not in REFERENCE_FILE_SUFFIXES:
                    raise ValueError("External reference file must be a Jana, XPLOR, CCP4 or CIF-compatible file.")
            if not any([cfg.export_superflip_xplor, cfg.export_superflip_ccp4, cfg.export_superflip_jana, cfg.export_standard_hkl, cfg.export_jana_project]):
                raise ValueError("Select at least one Superflip export: XPLOR, CCP4, Jana m80/m81, standardized HKL, or Jana2020 project.")
            if cfg.run_sharped and not cfg.sharped_api_token.strip():
                raise ValueError("SharpED API token is required for server inference. Fill SharpED -> API token or set SHARPED_API_TOKEN.")
            for exe, label in [(cfg.superflip_exe, "Superflip"), (cfg.edma_exe, "EDMA")]:
                missing = resolve_executable_for_validation(exe)
                if missing is None:
                    raise FileNotFoundError(f"{label} executable not found: {exe}")
            cfg.work_dir.mkdir(parents=True, exist_ok=True)
            self.last_run_config = cfg
            self.save_settings()
        except Exception as exc:
            QMessageBox.critical(self, "Input error", str(exc))
            return
        self.stop_after_cycle.clear()
        self.stop_now.clear()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Starting...")
        self._set_run_status("Running")
        self.run_btn.setEnabled(False)
        self.handoff_btn.setEnabled(False)
        self.run_btn.setText("Running...")
        self.log_text.append("\nStarting pipeline...")
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())
        QApplication.processEvents()
        self.worker = threading.Thread(target=self.pipeline_worker, args=(cfg,), daemon=True)
        self.worker.start()
    def pipeline_worker(self, cfg: RunConfig) -> None:
        try:
            self.log("=== Phase Studio pipeline started ===")
            self.log(f"Work dir: {cfg.work_dir}")
            mode = normalize_input_source_mode(cfg.input_source_mode)
            self.log(f"Input data mode: {INPUT_MODE_LABELS.get(mode, mode)}")
            if mode in {INPUT_MODE_INFLIP, INPUT_MODE_INFLIP_OVERRIDES}:
                if cfg.jana_inflip is None:
                    raise RuntimeError("Jana input mode selected, but no Jana .inflip file is configured.")
                self.log(f"Jana2020 .inflip primary input: {cfg.jana_inflip}")
                if mode == INPUT_MODE_INFLIP or not cfg.hkl.is_file():
                    cfg.hkl = extract_embedded_hkl_from_inflip(cfg.jana_inflip, cfg.work_dir)
                    self.log(f"HKL source exported from Jana .inflip: {cfg.hkl}")
                else:
                    self.log(f"HKL source override: {cfg.hkl}")

                declared_ref = inflip_declared_reference(cfg.jana_inflip)
                if mode == INPUT_MODE_INFLIP or not cfg.reference_cif.is_file():
                    if declared_ref is not None and declared_ref.is_file() and declared_ref.suffix.lower() == ".cif" and mode != INPUT_MODE_INFLIP_OVERRIDES:
                        cfg.reference_cif = declared_ref
                        self.log(f"Reference CIF declared by Jana .inflip: {cfg.reference_cif}")
                    else:
                        cfg.reference_cif = write_reference_cif_from_inflip(cfg.jana_inflip, cfg.work_dir / f"{cfg.jana_inflip.stem}_embedded_reference.cif")
                        self.log(f"Reference CIF synthesized from Jana .inflip cell/space group/composition: {cfg.reference_cif}")
                else:
                    self.log(f"External reference structure: {cfg.reference_cif}")

                if cfg.superflip_referencefile is None and declared_ref is not None and declared_ref.is_file() and declared_ref.suffix.lower() in REFERENCE_DENSITY_SUFFIXES:
                    cfg.superflip_referencefile = declared_ref
                    cfg.referencefile_mode = referencefile_mode_for_path(cfg.superflip_referencefile)
                    self.log(f"External reference density declared by Jana .inflip: {cfg.superflip_referencefile}")
            else:
                self.log(f"External HKL source: {cfg.hkl}")
                self.log(f"External reference file: {cfg.superflip_referencefile or cfg.reference_cif}")
            if str(cfg.referencefile_mode).strip().lower() in {"reference_xplor", "reference_density"} and cfg.superflip_reference_xplor is None and cfg.superflip_referencefile is None:
                cfg.referencefile_mode = "omit"
            ref_ctx = load_reference_context(cfg.reference_cif, cfg.work_dir, cfg.composition_override)
            # If the user selected a real CIF as Superflip referencefile in Jana .inflip mode,
            # do not turn it into an empty metadata-only reference.  Use its atom sites for
            # metrics/EDMA while preserving the Jana .inflip cell/spacegroup/reflection setup.
            if cfg.superflip_referencefile is not None and cfg.superflip_referencefile.suffix.lower() == ".cif":
                ref_ctx = reference_context_with_external_atom_sites(
                    ref_ctx, cfg.superflip_referencefile, cfg.work_dir, cfg.composition_override, self.log
                )
            self.msg_queue.put(("structure_cell", (
                ref_ctx.cell.a, ref_ctx.cell.b, ref_ctx.cell.c,
                ref_ctx.cell.alpha, ref_ctx.cell.beta, ref_ctx.cell.gamma,
            )))
            self.msg_queue.put(("reference_atoms", expand_atoms_by_symmetry(ref_ctx.atoms, ref_ctx.spacegroup)))
            self.log(f"Crystallographic reference CIF: {cfg.reference_cif}")
            self.log(f"Working reference CIF for EDMA/metrics: {ref_ctx.work_ref_cif}")
            self.log(f"Cell: {ref_ctx.cell.a:.5f} {ref_ctx.cell.b:.5f} {ref_ctx.cell.c:.5f} {ref_ctx.cell.alpha:.3f} {ref_ctx.cell.beta:.3f} {ref_ctx.cell.gamma:.3f}")
            self.log(f"Space group: {ref_ctx.spacegroup_hm}")
            self.log(f"Composition: {ref_ctx.composition}")
            self.log(f"Reference atoms read: {len(ref_ctx.atoms)}")
            self.log(f"EDMA plimit after Superflip: {cfg.plimit_superflip:g} sigma multiplier")
            self.log(f"EDMA plimit after deblurring: {cfg.plimit_deblur:g} sigma multiplier")
            self.log(f"EDMA maxima/fullcell/numberofatoms: {cfg.edma_maxima} / {cfg.edma_fullcell} / {cfg.edma_numberofatoms}")
            sharped_elements = cfg.sharped_elements.strip() or sharped_elements_from_composition(ref_ctx.composition)
            self.log(f"SharpED inference server: {cfg.sharped_base_url}")
            self.log(f"SharpED model: {cfg.sharped_model or 'default'}")
            self.log(f"SharpED elements: {sharped_elements}")
            self.log(f"SharpED maximum upload size: {cfg.sharped_max_upload_mb:g} MB" if cfg.sharped_max_upload_mb > 0 else "SharpED maximum upload size: disabled")
            requested_modelfile_mode = normalize_modelfile_source(cfg.modelfile_source)
            modelfile_mode = requested_modelfile_mode
            use_xplor_modelfile = modelfile_mode in {"superflip_xplor", "deblurred_xplor"}
            use_superflip_xplor_modelfile = modelfile_mode == "superflip_xplor"
            use_cif_modelfile = modelfile_mode == "deblurred_edma_cif"
            self.log(f"Next-cycle modelfile source: {modelfile_mode}")
            if use_xplor_modelfile:
                self.log(
                    f"XPLOR damping 1/x: {max(0.001, min(1.0, float(cfg.damping_factor))):g} "
                    f"(effective old factor {effective_xplor_damping_factor(cfg.damping_factor):g})"
                )
            if use_superflip_xplor_modelfile:
                self.log("Next-cycle XPLOR modelfile uses the raw Superflip map; SharpED deblurring is not required for cycling.")
            if use_cif_modelfile:
                self.log("CIF modelfiles are written without an explicit CIF format keyword; Superflip infers CIF from the .cif extension.")
            self.log(f"Superflip perform: {cfg.perform_algorithm.upper()}")
            self.log(f"Superflip requested outputformat: {cfg.output_format}")
            self.log(
                "Superflip exports: "
                f"XPLOR={'yes' if cfg.export_superflip_xplor else 'internal'}, "
                f"CCP4={'yes' if cfg.export_superflip_ccp4 else 'no'}, "
                f"m80/m81={'yes' if cfg.export_superflip_jana or cfg.write_auxiliary_outputs else 'no'}, "
                f"standard HKL={'yes' if cfg.export_standard_hkl else 'no'}"
            )
            if cfg.export_jana_project:
                self.log("Jana2020 project export: yes")
            self.log(f"Optional functions: EDMA/Superflip={'yes' if cfg.run_edma_superflip else 'no'}, SharpED={'yes' if cfg.run_sharped else 'no'}, Superflip symmetry/deblurred={'yes' if cfg.symmetrize_deblurred_map else 'no'}, EDMA/deblurred={'yes' if cfg.run_edma_deblurred else 'no'}")
            if cfg.first_cycle_modelfile is not None:
                self.log(f"First-cycle external modelfile: {cfg.first_cycle_modelfile}")
            explicit_superflip_referencefile = cfg.superflip_referencefile
            if explicit_superflip_referencefile is not None:
                self.log(f"External reference file: {explicit_superflip_referencefile}")
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
                    self.log(f"Superflip referencefile: {explicit_superflip_referencefile} (format inferred from CIF suffix)")
                else:
                    self.log(f"Superflip referencefile: {ref_ctx.work_ref_cif} (format inferred from CIF suffix)")
            elif referencefile_mode in {"reference_xplor", "reference_density"} and (explicit_superflip_referencefile is not None or cfg.superflip_reference_xplor is not None):
                self.log(f"Superflip referencefile: {explicit_superflip_referencefile or cfg.superflip_reference_xplor} (format inferred from filename)")
            else:
                self.log("Superflip referencefile keyword: no")
            self.log(f"Superflip bestdensities: {cfg.bestdensities_count} {'symmetry' if cfg.bestdensities_symmetry else cfg.bestdensities_metric}")
            self.log(f"Superflip polish: {'yes' if cfg.polish else 'no'}")
            configured_data_mode = resolve_reflection_data_mode_from_sources(cfg.hkl, cfg.reflection_data_mode, cfg.jana_inflip)
            self.log(f"Superflip HKL data mode: {configured_data_mode}")
            if cfg.resolution_d_min > 0:
                self.log(f"Superflip resolution cutoff: d >= {cfg.resolution_d_min:g} A")
            if cfg.map_feedback_missing_from_cycle > 0 or cfg.map_feedback_intensity_from_cycle > 0:
                self.log(
                    "Map feedback: "
                    f"missing_from_cycle={cfg.map_feedback_missing_from_cycle}, "
                    f"missing_limit={cfg.map_feedback_missing_percent_limit:g}%, "
                    f"intensity_from_cycle={cfg.map_feedback_intensity_from_cycle}, "
                    f"intensity_damping={cfg.map_feedback_intensity_damping:g}, "
                    f"intensity_max_value_sigma={cfg.map_feedback_intensity_max_i_over_sigma:g}"
                )
            self.msg_queue.put(("progress_setup", cfg.cycles))
            value_col, sigma_col, include_000 = reflection_columns_for_mode(configured_data_mode)
            refl_raw = read_hkl(cfg.hkl, value_col=value_col, sigma_col=sigma_col, include_000=include_000)
            refl = merge_duplicate_reflections(refl_raw)
            current_reflections = list(refl)
            data_modes_needed = {configured_data_mode}
            observed_hkls: Dict[str, Path] = {}
            for data_mode in sorted(data_modes_needed):
                observed_hkl = cfg.work_dir / observed_hkl_name_for_mode(data_mode)
                n_written = write_observed_reflections(observed_hkl, refl, cfg.i_over_sigma_min, data_mode=data_mode, cell=ref_ctx.cell, resolution_d_min=cfg.resolution_d_min)
                observed_hkls[data_mode] = observed_hkl
                self.log(f"Prepared HKL for {data_mode}: {observed_hkl} ({n_written} reflections)")
            if cfg.export_standard_hkl:
                standard_hkl = cfg.work_dir / "observed_unique_standardized_I_sigma_phase.hkl"
                n_standard = write_standardized_hkl_with_phase(standard_hkl, refl, cfg.i_over_sigma_min, configured_data_mode, cell=ref_ctx.cell, resolution_d_min=cfg.resolution_d_min)
                self.log(f"Standardized HKL export: {standard_hkl} ({n_standard} reflections)")
            self.log(f"Reflections: {len(refl_raw)} parsed / {len(refl)} unique")
            current_model: Optional[Path] = None
            current_model_metric: Optional[float] = None
            exclude_labels = parse_atom_label_list(cfg.exclude_atoms)
            all_results: List[CycleResult] = []
            completed_cycles = 0
            for cyc in range(1, cfg.cycles + 1):
                if self.stop_after_cycle.is_set():
                    self.log("Stop requested before next cycle."); break
                cycle_dir = cfg.work_dir / f"cycle_{cyc:03d}"; cycle_dir.mkdir(parents=True, exist_ok=True)
                self.log(f"\n=== Cycle {cyc} ===")
                model_for_sf: Optional[Path] = None
                model_source = "none"
                model_metric = current_model_metric
                if cyc == 1 and cfg.first_cycle_modelfile is not None:
                    model_source = "external_first_cycle"
                    model_for_sf = cfg.first_cycle_modelfile
                    self.log(f"Using external first-cycle modelfile: {model_for_sf}")
                elif current_model is not None and use_xplor_modelfile:
                    model_source = modelfile_mode
                    model_for_sf = current_model
                    self.log(f"Using {modelfile_mode} as modelfile: {model_for_sf}")
                    self.log("  CIF-only exclude settings skipped for XPLOR modelfile.")
                elif current_model is not None and use_cif_modelfile:
                    model_source = "deblurred_edma_cif"
                    model_for_sf = cycle_dir / f"cycle_{cyc:03d}_modelfile_prepared.cif"
                    model_for_sf, removed, kept = write_filtered_cif(current_model, model_for_sf, exclude_labels)
                    self.log(f"Prepared CIF modelfile: {model_for_sf}")
                    self.log(f"  removed={removed}, kept={kept}")
                    self.log("  Superflip will infer CIF from .cif extension; no explicit CIF format keyword is written.")
                    model_metric = nearest_metric_to_reference(model_for_sf, ref_ctx)
                elif cyc > 1 and modelfile_mode == "none":
                    self.log("No Superflip modelfile for this cycle.")
                observed_hkl_for_cycle = observed_hkls[configured_data_mode]
                sf_prefix = f"cycle_{cyc:03d}_superflip"
                reference_file_for_cycle: Optional[Path] = None
                reference_format_for_cycle = ""
                if referencefile_mode == "reference_cif":
                    reference_file_for_cycle = explicit_superflip_referencefile if explicit_superflip_referencefile is not None else ref_ctx.work_ref_cif
                elif referencefile_mode in {"reference_xplor", "reference_density"}:
                    reference_file_for_cycle = explicit_superflip_referencefile if explicit_superflip_referencefile is not None else cfg.superflip_reference_xplor
                sf_voxel = cfg.voxel
                sf_extra_superflip_keywords = cfg.extra_superflip_keywords
                if cfg.run_sharped and not use_superflip_xplor_modelfile:
                    sf_voxel = sharped_limited_superflip_voxel(cfg.voxel, ref_ctx.cell, cfg.sharped_max_upload_mb, self.log)
                    if sf_voxel != cfg.voxel and cfg.polish:
                        sf_extra_superflip_keywords = append_superflip_keyword(
                            sf_extra_superflip_keywords,
                            f"finevoxel {sf_voxel}",
                        )
                sf_map = run_superflip_cycle(cycle_dir, sf_prefix, ref_ctx, observed_hkl_for_cycle, model_for_sf, reference_file_for_cycle, reference_format_for_cycle, cfg.superflip_exe, cfg.perform_algorithm, cfg.output_format, cfg.write_auxiliary_outputs or cfg.export_jana_project, cfg.export_superflip_xplor, cfg.export_superflip_ccp4, cfg.export_superflip_jana or cfg.export_jana_project, sf_voxel, cfg.bestdensities_count, cfg.bestdensities_metric, cfg.bestdensities_symmetry, cfg.polish, cfg.maxcycles, cfg.repeatmode, cfg.randomseed, cfg.delta, cfg.weakratio, cfg.biso, configured_data_mode, cfg.normalize, cfg.nresshells, cfg.missing, cfg.searchsymmetry, cfg.derivesymmetry, cfg.electrons, cfg.dataitemwidths, sf_extra_superflip_keywords, self.log, self.stop_now)
                self.log(f"Superflip map: {sf_map}")
                if self.stop_now.is_set():
                    raise RuntimeError("Immediate stop requested.")
                sf_log_metrics = parse_superflip_cycle_metrics(cycle_dir, sf_prefix)
                if sf_log_metrics.rvalue is not None:
                    self.log(
                        "Superflip metrics: "
                        f"R={sf_log_metrics.rvalue:.3f}, "
                        f"Peaks={sf_log_metrics.peaks if sf_log_metrics.peaks is not None else 'n/a'}, "
                        f"Symm={sf_log_metrics.symm if sf_log_metrics.symm is not None else 'n/a'}, "
                        f"Der.SG={sf_log_metrics.derived_sg or 'n/a'}, "
                        f"Saved run={sf_log_metrics.saved_run if sf_log_metrics.saved_run is not None else 'n/a'}, "
                        f"Ref.match={sf_log_metrics.ref_match if sf_log_metrics.ref_match is not None else 'n/a'}, "
                        f"SR={sf_log_metrics.success_rate if sf_log_metrics.success_rate is not None else 'n/a'}%"
                    )
                sf_edma_dir = cycle_dir / "edma_superflip"
                if cfg.run_edma_superflip:
                    sf_edma_cif = run_edma_on_xplor(
                        sf_map, sf_edma_dir, sf_prefix, ref_ctx, cfg.plimit_superflip,
                        cfg.merge_distance, cfg.edma_exe, self.log, cfg.export_jana_project,
                        self.stop_now, cfg.edma_maxima, cfg.edma_fullcell,
                        cfg.edma_numberofatoms, cfg.edma_centerofcharge, cfg.edma_chlimit,
                        cfg.edma_chlimlist, cfg.extra_edma_keywords
                    )
                else:
                    sf_edma_dir.mkdir(parents=True, exist_ok=True)
                    sf_edma_cif = sf_edma_dir / f"{sf_prefix}_edma.cif"
                    write_structure_bundle(sf_edma_cif, ref_ctx.cell, ref_ctx.spacegroup, ref_ctx.spacegroup_hm, [])
                    self.log("EDMA after Superflip disabled; empty placeholder CIF/XYZ/PDB written.")
                if cfg.export_jana_project and cfg.run_edma_superflip:
                    export_jana2020_project(cycle_dir / "jana2020_superflip", sf_prefix, cycle_dir, sf_edma_dir, sf_map, sf_edma_cif, ref_ctx, self.log)
                sf_metric = nearest_metric_to_reference(sf_edma_cif, ref_ctx) if cfg.run_edma_superflip else None
                self.log(f"EDMA after Superflip CIF: {sf_edma_cif}")
                self.msg_queue.put(("structure_update", ("superflip", sf_edma_cif)))
                self.log(f"EDMA after Superflip RMSD: {sf_metric if sf_metric is not None else 'n/a'} Å")
                deblur_map = cycle_dir / f"cycle_{cyc:03d}_deblurred.xplor"
                if cfg.run_sharped and not use_superflip_xplor_modelfile:
                    if self.stop_now.is_set():
                        raise RuntimeError("Immediate stop requested.")
                    run_sharped_deblur(sf_map, deblur_map, cfg.sharped_base_url, cfg.sharped_api_token, cfg.sharped_model, sharped_elements, cfg.sharped_outres, cfg.sharped_max_upload_mb, cfg.sharped_timeout_seconds, cfg.sharped_poll_seconds, cfg.sharped_max_polls, self.log, self.stop_now)
                else:
                    shutil.copy2(sf_map, deblur_map)
                    if use_superflip_xplor_modelfile:
                        self.log("SharpED deblurring skipped; raw Superflip XPLOR is used for the next-cycle modelfile.")
                    else:
                        self.log("SharpED disabled; deblurred map is a copy of the Superflip map.")
                self.log(f"Deblurred map: {deblur_map}")
                if cfg.symmetrize_deblurred_map and not use_superflip_xplor_modelfile:
                    if self.stop_now.is_set():
                        raise RuntimeError("Immediate stop requested.")
                    sym_prefix = f"cycle_{cyc:03d}_deblurred_symmetrized"
                    self.log("  Superflip symmetry uses the deblurred XPLOR map as both modelfile and referencefile.")
                    deblur_map = run_superflip_symmetrize_map(
                        cycle_dir=cycle_dir,
                        prefix=sym_prefix,
                        ref_ctx=ref_ctx,
                        input_map=deblur_map,
                        superflip_exe=cfg.superflip_exe,
                        output_format=cfg.output_format,
                        voxel=cfg.voxel,
                        searchsymmetry=cfg.searchsymmetry,
                        derivesymmetry=cfg.derivesymmetry,
                        log=self.log,
                        stop_event=self.stop_now,
                    )
                    self.log(f"Deblurred map after Superflip symmetry averaging: {deblur_map}")
                deblur_prefix = f"cycle_{cyc:03d}_deblurred"
                deblur_edma_dir = cycle_dir / "edma_deblurred"
                if cfg.run_edma_deblurred and not use_superflip_xplor_modelfile:
                    deblur_edma_cif = run_edma_on_xplor(
                        deblur_map, deblur_edma_dir, deblur_prefix, ref_ctx, cfg.plimit_deblur,
                        cfg.merge_distance, cfg.edma_exe, self.log, cfg.export_jana_project,
                        self.stop_now, cfg.edma_maxima, cfg.edma_fullcell,
                        cfg.edma_numberofatoms, cfg.edma_centerofcharge, cfg.edma_chlimit,
                        cfg.edma_chlimlist, cfg.extra_edma_keywords
                    )
                else:
                    deblur_edma_dir.mkdir(parents=True, exist_ok=True)
                    deblur_edma_cif = deblur_edma_dir / f"{deblur_prefix}_edma.cif"
                    write_structure_bundle(deblur_edma_cif, ref_ctx.cell, ref_ctx.spacegroup, ref_ctx.spacegroup_hm, [])
                    if use_superflip_xplor_modelfile:
                        self.log("EDMA after deblurred map skipped for raw Superflip XPLOR cycling; empty placeholder CIF/XYZ/PDB written.")
                    else:
                        self.log("EDMA after deblurred map disabled; empty placeholder CIF/XYZ/PDB written.")
                if cfg.export_jana_project and cfg.run_edma_deblurred:
                    export_jana2020_project(cycle_dir / "jana2020_deblurred", deblur_prefix, cycle_dir, deblur_edma_dir, deblur_map, deblur_edma_cif, ref_ctx, self.log)
                deblur_metric = nearest_metric_to_reference(deblur_edma_cif, ref_ctx) if cfg.run_edma_deblurred else None
                self.log(f"EDMA after deblur CIF: {deblur_edma_cif}")
                self.msg_queue.put(("structure_update", ("deblur", deblur_edma_cif)))
                self.log(f"EDMA after deblur RMSD: {deblur_metric if deblur_metric is not None else 'n/a'} Å")
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
                )
                all_results.append(result)
                write_metrics_csv(cfg.work_dir / "metrics.csv", all_results)
                self.msg_queue.put(("result", result))
                completed_cycles = cyc
                self.msg_queue.put(("progress", completed_cycles))
                if cyc < cfg.cycles:
                    add_missing = cfg.map_feedback_missing_from_cycle > 0 and cyc >= cfg.map_feedback_missing_from_cycle and cfg.map_feedback_missing_percent_limit > 0
                    correct_intensities = cfg.map_feedback_intensity_from_cycle > 0 and cyc >= cfg.map_feedback_intensity_from_cycle and cfg.map_feedback_intensity_damping > 0
                    if add_missing or correct_intensities:
                        current_reflections = apply_map_feedback_to_reflections(
                            current_reflections,
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
                        feedback_hkl = cfg.work_dir / f"cycle_{cyc + 1:03d}_map_feedback_for_superflip.hkl"
                        n_feedback = write_observed_reflections(
                            feedback_hkl,
                            current_reflections,
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
                    if current_model is not None and effective_damping > 1.0:
                        damped_model = cycle_dir / f"cycle_{cyc:03d}_damped_modelfile.xplor"
                        current_model = blend_xplor_maps(current_model, next_xplor_model, damped_model, effective_damping, self.log)
                    else:
                        current_model = next_xplor_model
                    current_model_metric = sf_metric if use_superflip_xplor_modelfile else deblur_metric
                elif use_cif_modelfile:
                    if cfg.run_edma_deblurred:
                        current_model = deblur_edma_cif
                        current_model_metric = deblur_metric
                    elif cfg.run_edma_superflip:
                        current_model = sf_edma_cif
                        current_model_metric = sf_metric
                    else:
                        current_model = None
                        current_model_metric = None
                else:
                    current_model = None
                    current_model_metric = None
            self.msg_queue.put(("done", completed_cycles))
        except Exception as exc:
            self.msg_queue.put(("error", exc))


def create_startup_splash() -> QSplashScreen:
    pixmap = QPixmap(520, 250)
    pixmap.fill(QColor("#ffffff"))

    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(QColor("#44b7ff"), 1))
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(10, 10, 500, 230, 8, 8)

        painter.setPen(QColor("#001170"))
        title_font = QFont()
        title_font.setPointSize(20)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.drawText(34, 70, "Phase Studio 1.0.1")
        painter.drawPixmap(386, 26, create_phase_studio_logo_pixmap(96))

        painter.setPen(QColor("#001170"))
        body_font = QFont()
        body_font.setPointSize(10)
        painter.setFont(body_font)
        painter.drawText(34, 108, "Starting crystallographic pipeline workspace")
        painter.drawText(34, 134, "Loading settings, plots and structure views...")

        painter.setPen(QPen(QColor("#2264b8"), 3))
        painter.drawLine(34, 180, 486, 180)
        painter.setPen(QColor("#001170"))
        small_font = QFont()
        small_font.setPointSize(8)
        painter.setFont(small_font)
        painter.drawText(34, 210, "Superflip and EDMA are resolved from your configured paths or PATH.")
    finally:
        painter.end()

    splash = QSplashScreen(pixmap)
    splash.setWindowFlag(Qt.WindowStaysOnTopHint, True)
    splash.showMessage("Starting...", Qt.AlignBottom | Qt.AlignRight, QColor("#001170"))
    return splash


def main() -> None:
    app = QApplication(sys.argv)
    apply_phase_studio_style(app)
    splash = create_startup_splash()
    splash.show()
    app.processEvents()
    win = IterativeSuperflipPipelineQtGUI()
    win.show()
    splash.finish(win)
    raise SystemExit(app.exec())

if __name__ == "__main__":
    main()
