"""Phase Studio 2.0.0 Autosolve's dedicated top-level window.

AutosolveWindow is a NEW, simplified front end -- not a mode of the full
Phase Studio GUI reached by hiding configuration panes. The structure
comparison is the dominant content; a compact status line, the shared
Execution Log (kept small), and the shared bottom progress bars fill the
rest, then exactly two actions: Cancel and "Pass to Jana2020" (which opens
the shared Result Selection -- see IterativeSuperflipPipelineQtGUI.
_autosolve_handoff).

`backend` is a real `IterativeSuperflipPipelineQtGUI` instance that is
constructed but never shown -- the actual scientific engine (RunConfig,
PipelineState, _run_pipeline_cycles, EDMA, SharpED, ranking, Jana handoff).
AutosolveWindow never re-implements any of that; it only presents what
`backend` is already doing:

- The structure-rendering and synchronized-camera methods are borrowed as
  unbound functions straight from IterativeSuperflipPipelineQtGUI, exactly
  the way `create_result_preview_host()` (result_selection.py) already
  borrows the same methods for the Jana2020 result selector's mini preview.
- The bottom progress bars (`run_status_panel`, containing the overall
  progress bar, the per-cycle/stage progress bar and the Superflip-repeat
  sub-progress bar) and the Execution Log (`log_text`) are not copied --
  the real widget objects are reparented from `backend` into this window,
  so backend's own existing update calls (`_apply_cycle_progress_state`,
  `_append_execution_log`, ...) keep writing into the exact widgets the
  user sees here, with no second implementation of either.

Bond rendering is the one genuinely NEW piece: no atom-connectivity
algorithm existed anywhere in Phase Studio to reuse (confirmed by search),
so `compute_bonds()` below adds a presentation-only, distance-based bond
detector using gemmi's own established covalent-radius data (gemmi is
already a hard dependency, used for every other crystallographic
calculation in this app) -- not an invented radius table, and not a change
to any scientific coordinate.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import gemmi
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.colors import to_rgb
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.transforms import offset_copy
from mpl_toolkits.mplot3d.art3d import Line3DCollection
import html
import json

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from phase_studio.app import (
    AtomSite,
    IterativeSuperflipPipelineQtGUI,
    StructureDepthArtists,
    blend_structure_colors,
    clean_element_symbol,
    composition_from_atoms,
    element_atomic_number,
    expand_atoms_by_symmetry,
    edma_asu_atoms,
    _m40_model_count,
    parse_cif_atoms,
    parse_cif_cell_and_sg,
    structure_depth_fade,
)
from phase_studio.map_quality import ResultCandidate, recommend_best_result
from phase_studio import autosolve_review as guided
from phase_studio.ui_branding import create_phase_studio_app_icon, create_phase_studio_brand_header
from phase_studio.fullscreen_viewer import show_single_structure_viewer
from phase_studio.structure_camera import StructureCameraController, fit_projected_structure, set_structure_viewport_clip, structure_marker_sizes
from phase_studio.version import VERSION as __version__

# Idle rotation: slow enough to read the structure while it turns, fast
# enough that it visibly reads as "live" rather than static.
AUTO_ROTATE_INTERVAL_MS = 60
AUTO_ROTATE_DEGREES_PER_TICK = 0.4
# Resume delay after a manual interaction (drag/scroll/reset) ends, so
# rotation does not snap back on immediately -- a short pause reads as
# intentional, not broken.
AUTO_ROTATE_RESUME_DELAY_SECONDS = 1.2
# Status/recommendation polling. The backend's own internal QTimer (50ms)
# already drains its message queue and mutates self.results/_resume_state/
# _autosolve_policy on its own -- this timer only re-reads that already-
# updated state to refresh the display; it is not a second orchestration
# loop and never mutates backend state itself (except Cancel/Pass-now).
REFRESH_INTERVAL_MS = 200

PREPARING_TEXT = "Preparing Autosolve…"
# Autosolve end-point states published by the backend (autosolve_handoff_state).
# The footer action can safely stop unfinished work and open the same shared
# Result Selection used by Final Review panel actions.
HANDOFF_STATE_HEADLINES = {
    "stopping": "Stopping current calculation…",
    "selecting": "Choose the result to pass to Jana2020…",
    "handing_off": "Passing the selected result to Jana2020…",
}
CANCEL_TOOLTIP = "Stop the calculation without passing a result to Jana2020."
RETRY_TOOLTIP = (
    "Retry the failed step. Completed stages are reused: a failed prediction generates only the "
    "Structure prediction again; a failed cycle resumes at its first incomplete stage."
)
ADD_ATOMS_TOOLTIP = (
    "Lower this panel's EDMA threshold by the configured step to extract more atoms from the SAME map "
    "(EDMA only; Superflip and SharpED are not rerun)."
)
REMOVE_ATOMS_TOOLTIP = (
    "Raise this panel's EDMA threshold by the configured step to extract fewer atoms from the SAME map "
    "(EDMA only; Superflip and SharpED are not rerun)."
)
RECALCULATE_TOOLTIP = (
    "Use this panel's current structure, at its current threshold, as the Superflip initial model "
    "and run a 3-cycle refinement block with SharpED '" + guided.PREDICTION_MODEL + "'. Another "
    "3 cycles follow automatically only while the selected source's ranking strictly improves."
)
REFINE_TOOLTIP = (
    "Use the Structure prediction at its current threshold as the Superflip initial model and run "
    "3 refinement cycles with SharpED '" + guided.PREDICTION_MODEL + "'. Both results can be "
    "tuned, recalculated and passed afterwards."
)
CORRECTION_CONFIRMATION = {
    guided.CORRECTION_INTENSITY: (
        "Correct suspect intensities",
        "Correcting suspect intensities modifies the measured reflection data used by "
        "subsequent calculations.\n\nThe original measured data will be retained for "
        "validation.\n\nContinue with intensity correction?",
        "Correct intensities",
    ),
    guided.CORRECTION_POWDER: (
        "Powder repartitioning",
        "Powder repartitioning modifies the measured reflection data used by subsequent "
        "calculations.\n\nThe original measured data will be retained for validation.\n\n"
        "Continue with powder repartitioning?",
        "Repartition intensities",
    ),
}
PASS_PANEL_TOOLTIP = "Pass this panel's map, and its structure at the current threshold, to Jana2020."
SAVE_PANEL_TOOLTIP = "Save this panel's map and its structure at the current threshold."
PREDICTED_PLACEHOLDER = "Generated after the phase search"
PREDICTING_PLACEHOLDER = "Generating predicted structure…"

# --- Presentation-only bond detection (NEW code -- see module docstring) ---
BOND_TOLERANCE = 1.15
MAX_BOND_LENGTH_ANGSTROM = 2.6
# Atoms read more clearly as a recognizable structure (vs. a scatter of
# dots) at a larger marker scale than the shared renderer's own default,
# which was tuned for the denser multi-panel comparison grid elsewhere.
PRESENTATION_ATOM_SCALE = 1.7
BOND_COLOR = "#5d6b86"
BOND_LINEWIDTH = 1.3

# --- Camera fit, derived from the displayed content (no fixed zoom factor).
# Every panel is framed by a bounding SPHERE around what it actually shows:
# with an orthographic projection a sphere projects to the same circle at
# every rotation, so a fit computed once stays crop-free while the view
# auto-rotates. The *_FILL values are the target fraction of the panel's
# drawing square that sphere's diameter should occupy. ---
MOLECULE_VIEW_FILL = 0.80
FULL_CELL_VIEW_FILL = 0.80
# Floor for a single atom / very small fragment, so a lone peak is not
# magnified into a screen-filling disc.
MIN_FIT_RADIUS_ANGSTROM = 1.0
# A re-render (new candidate, threshold recalculation, ...) only resets the
# user's zoom/pan when the displayed extent actually moved by more than
# this fraction of its previous fit radius -- an ordinary +/- atoms nudge
# with a similar extent leaves their current framing alone.
FIT_EXTENT_CHANGE_RATIO = 0.15

# --- Complete-molecules / asymmetric-unit view (NEW -- see module docstring
# for the root-cause analysis of why bonding across the whole, already
# symmetry-expanded unit cell was wrong). Bond growth starts from the raw
# asymmetric-unit atoms and only pulls in a symmetry/periodic image when it
# is actually within bonding distance of an atom already accepted into the
# fragment -- never the whole cell at once. ---
MOLECULE_PERIODIC_TRANSLATIONS = 1  # neighbor cells searched on each axis: -1, 0, 1
# Same ceiling the shared Full-cell renderer uses for its heaviest-atom
# subset, so neither mode draws more markers than the other can.
MAX_MOLECULE_ATOMS = 800
MOLECULE_ATOM_MARKER_SIZE = 130.0
# Unassigned (single, unbonded) peaks: drawn only as a faint secondary layer,
# and only where they already fall inside the fitted molecule sphere -- they
# never contribute to the camera extent.
SECONDARY_PEAK_MARKER_SIZE = 42.0
SECONDARY_PEAK_WHITE_BLEND = 0.72
# Complete molecules keeps the completed structure as the only visual focus:
# the faint unassigned-peak layer is computed (and never affects Fit) but is
# not drawn by default. Full cell still shows every peak.
SHOW_SECONDARY_PEAKS_IN_MOLECULE_VIEW = False
# Execution Log: a whole number of text rows (never a half-clipped top row
# when auto-scrolled to the newest message), 3-6 rows by screen height.
LOG_MIN_VISIBLE_LINES = 3
LOG_MAX_VISIBLE_LINES = 5
LOG_SCREEN_HEIGHT_PER_LINE = 240
# Same symbols the shared renderer drops (_plot_structure_atoms).
RENDERER_HIDDEN_ELEMENTS = frozenset({"H", "D", "He"})
RENDERER_MAX_ATOMS = 800
# Sanity guard (visible-regression guard): a chemically local fragment
# should never approach O(N^2) bonds. If growth or bond detection ever
# produces more than this many bonds per atom on average, something is
# wrong with the candidate pool/cutoff -- skip drawing bonds for that panel
# entirely rather than silently repeating the previous all-to-all bug.
MAX_BONDS_PER_ATOM = 6


@dataclass
class _BondArtist:
    collection: object
    midpoints: np.ndarray


def compute_bonds(
    atoms: Sequence[AtomSite],
    coords: np.ndarray,
    tolerance: float = BOND_TOLERANCE,
    max_length: float = MAX_BOND_LENGTH_ANGSTROM,
) -> List[Tuple[int, int]]:
    """Presentation-only bond detection: atoms i and j are bonded iff their
    Cartesian distance is within `tolerance` times the sum of their gemmi
    covalent radii, capped at `max_length` so a generous tolerance can never
    draw a chemically implausible long "bond". This is new code -- no
    connectivity algorithm existed anywhere in Phase Studio to reuse -- and
    it never changes the underlying atom coordinates, only what gets drawn
    on top of them."""
    n = len(atoms)
    if n < 2:
        return []
    radii = np.asarray(
        [gemmi.Element(clean_element_symbol(a.element)).covalent_r or 0.75 for a in atoms],
        dtype=np.float64,
    )
    bonds: List[Tuple[int, int]] = []
    for i in range(n - 1):
        deltas = coords[i + 1:] - coords[i]
        distances = np.linalg.norm(deltas, axis=1)
        limits = np.minimum(max_length, tolerance * (radii[i] + radii[i + 1:]))
        hits = np.nonzero((distances > 1.0e-3) & (distances <= limits))[0]
        for offset in hits:
            bonds.append((i, i + 1 + int(offset)))
    return bonds


def _bond_count_is_sane(n_atoms: int, n_bonds: int) -> bool:
    """Regression guard (see module docstring): a chemically local fragment
    should never approach O(N^2) connectivity."""
    return n_bonds <= max(1, n_atoms) * MAX_BONDS_PER_ATOM


def bond_graph_problems(
    n_atoms: int,
    coords: np.ndarray,
    bonds: Sequence[Tuple[int, int]],
    max_length: float = MAX_BOND_LENGTH_ANGSTROM,
) -> List[str]:
    """Bond-count/graph sanity check for what is about to be DRAWN: returns
    a list of human-readable problems (empty == sane). Catches every way the
    earlier all-to-all failure could come back -- an O(N^2) bond count, the
    same pair drawn twice, a self-bond, a "bond" longer than the hard
    length cap, or two coincident atom copies (a symmetry mate re-added on
    top of an equivalent atom, which then bonds to everything its twin
    bonds to)."""
    problems: List[str] = []
    if not _bond_count_is_sane(n_atoms, len(bonds)):
        problems.append(f"{len(bonds)} bonds for {n_atoms} atoms exceeds {MAX_BONDS_PER_ATOM} per atom")
    normalized = [(min(i, j), max(i, j)) for i, j in bonds]
    if len(set(normalized)) != len(normalized):
        problems.append("duplicate bonds")
    if any(i == j for i, j in normalized):
        problems.append("self-bond")
    if any(i < 0 or j >= n_atoms for i, j in normalized):
        problems.append("bond index out of range")
    elif normalized:
        lengths = np.linalg.norm(
            coords[[j for _i, j in normalized]] - coords[[i for i, _j in normalized]], axis=1
        )
        if float(np.max(lengths)) > max_length + 1.0e-6:
            problems.append("bond longer than the hard length cap")
    if n_atoms > 1:
        rounded = {tuple(np.round(c, 2)) for c in coords}
        if len(rounded) != n_atoms:
            problems.append("coincident duplicate atoms")
    return problems


def _cell_matrices(cell: gemmi.UnitCell) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """gemmi's own orthogonalization transform as numpy arrays (matrix,
    translation, inverse matrix) -- identical to cell.orthogonalize() /
    cell.fractionalize(), vectorized. Deliberately WITHOUT the renderer's
    wrap_frac pre-step: fragment atoms legitimately sit outside [0,1)
    (periodic neighbor-cell images), and wrapping them back into the home
    cell would silently mis-place them and break bond distances."""
    orth = np.asarray(cell.orth.mat.tolist(), dtype=np.float64)
    vec = np.asarray(cell.orth.vec.tolist(), dtype=np.float64)
    return orth, vec, np.linalg.inv(orth)


def _orthogonalize_frac(cell: gemmi.UnitCell, frac: np.ndarray) -> np.ndarray:
    """Single-point form of _cell_matrices()'s transform (kept for callers
    that need one position)."""
    pos = cell.orthogonalize(gemmi.Fractional(float(frac[0]), float(frac[1]), float(frac[2])))
    return np.array([pos.x, pos.y, pos.z], dtype=np.float64)


def _covalent_radius(element: str) -> float:
    return float(gemmi.Element(clean_element_symbol(element)).covalent_r or 0.75)


class _NeighborGrid:
    """Uniform spatial hash over the candidate pool: a bonding-distance
    query then only measures the pool atoms in the 27 surrounding voxels,
    instead of every image of every asymmetric-unit atom. Pure performance
    -- returns exactly the same neighbors a brute-force scan would."""

    def __init__(self, coords: np.ndarray, voxel: float) -> None:
        self.coords = coords
        self.voxel = max(float(voxel), 0.5)
        self.buckets: dict = {}
        for index, key in enumerate(map(tuple, np.floor(coords / self.voxel).astype(np.int64))):
            self.buckets.setdefault(key, []).append(index)

    def candidates(self, point: np.ndarray) -> np.ndarray:
        cx, cy, cz = (int(v) for v in np.floor(point / self.voxel))
        found: List[int] = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    found.extend(self.buckets.get((cx + dx, cy + dy, cz + dz), ()))
        return np.asarray(found, dtype=np.int64)


@dataclass
class CompleteMoleculeView:
    """What Complete-molecules mode draws for one candidate.

    `atoms`/`coords`/`bonds` are the PRIMARY content: every connected
    (bonded, >= 2 atom) component grown from the asymmetric unit, each
    completed with exactly the symmetry/periodic mates it needs, and placed
    by a whole lattice translation next to the largest one. `fit_center`/
    `fit_radius` are the bounding sphere of that primary content only -- the
    camera never looks at anything else. `secondary_*` are unassigned single
    peaks that happen to fall inside that sphere, for an optional faint
    layer; peaks outside it are simply not drawn in this mode (Full cell
    still shows every one, and nothing is ever removed from the EDMA result,
    CIF, metrics, recommendation or Jana handoff)."""

    atoms: List[AtomSite]
    coords: np.ndarray
    bonds: List[Tuple[int, int]]
    secondary_atoms: List[AtomSite]
    secondary_coords: np.ndarray
    fit_center: np.ndarray
    fit_radius: float
    unassigned_peak_count: int = 0


def _bounding_sphere(coords: np.ndarray) -> Tuple[np.ndarray, float]:
    if len(coords) == 0:
        return np.zeros(3, dtype=np.float64), MIN_FIT_RADIUS_ANGSTROM
    center = (np.min(coords, axis=0) + np.max(coords, axis=0)) / 2.0
    radius = float(np.max(np.linalg.norm(coords - center, axis=1)))
    return center, max(radius, MIN_FIT_RADIUS_ANGSTROM)


def _nearest_lattice_shift(
    coords: np.ndarray, target: np.ndarray, orth: np.ndarray, frac_of: np.ndarray
) -> np.ndarray:
    """The whole-cell translation (fractional integer vector) that brings the
    centroid of `coords` closest to `target`. A lattice translation maps a
    crystal onto itself, so the moved component is still a genuine periodic
    mate -- this only chooses WHICH equivalent copy is drawn."""
    delta_frac = frac_of @ (target - coords.mean(axis=0))
    base = np.round(delta_frac)
    best, best_distance = base, float("inf")
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                shift = base + np.array([dx, dy, dz], dtype=np.float64)
                distance = float(np.linalg.norm(orth @ (delta_frac - shift)))
                if distance < best_distance:
                    best, best_distance = shift, distance
    return best


def periodic_connectivity_unwrap(
    atoms: Sequence[AtomSite], cell: gemmi.UnitCell,
    tolerance: float = BOND_TOLERANCE,
    max_length: float = MAX_BOND_LENGTH_ANGSTROM,
) -> Tuple[List[AtomSite], np.ndarray, List[Tuple[int, int]], bool]:
    """Build minimum-image bonds and unwrap every connected component.

    Each edge retains the integer lattice translation of its selected image.
    Traversal propagates those translations, so a molecule crossing a cell
    face remains one compact object.  A contradictory translation around a
    graph cycle marks an extended periodic framework; its finite independent
    representation is still bounded by the caller's selected sites.
    """
    if not atoms:
        return [], np.zeros((0, 3), dtype=np.float64), [], False
    orth, vec, frac_of = _cell_matrices(cell)
    frac = np.asarray([a.frac for a in atoms], dtype=np.float64)
    radii = np.asarray([_covalent_radius(a.element) for a in atoms], dtype=np.float64)
    adjacency: List[List[Tuple[int, np.ndarray]]] = [[] for _ in atoms]
    bonds: List[Tuple[int, int]] = []
    for i in range(len(atoms) - 1):
        for j in range(i + 1, len(atoms)):
            base = np.round(frac[i] - frac[j]).astype(np.int64)
            best_shift = base
            best_distance = float("inf")
            # Rounding each fractional axis is insufficient in a skewed
            # cell; the 27 neighboring integer translations are exact for
            # the local crystallographic minimum-image search used here.
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        shift = base + np.asarray((dx, dy, dz), dtype=np.int64)
                        delta = frac[j] + shift - frac[i]
                        distance = float(np.linalg.norm(delta @ orth.T))
                        if distance < best_distance:
                            best_distance, best_shift = distance, shift
            limit = min(max_length, tolerance * (radii[i] + radii[j]))
            if 1.0e-3 < best_distance <= limit:
                shift = np.asarray(best_shift, dtype=np.int64)
                adjacency[i].append((j, shift))
                adjacency[j].append((i, -shift))
                bonds.append((i, j))

    offsets: List[Optional[np.ndarray]] = [None] * len(atoms)
    components: List[List[int]] = []
    extended = False
    for seed in range(len(atoms)):
        if offsets[seed] is not None:
            continue
        offsets[seed] = np.zeros(3, dtype=np.int64)
        component: List[int] = []
        stack = [seed]
        while stack:
            i = stack.pop()
            component.append(i)
            assert offsets[i] is not None
            for j, edge_shift in adjacency[i]:
                wanted = offsets[i] + edge_shift
                if offsets[j] is None:
                    offsets[j] = wanted
                    stack.append(j)
                elif not np.array_equal(offsets[j], wanted):
                    extended = True
        components.append(component)

    unwrapped_frac = frac + np.asarray(offsets, dtype=np.int64)
    coords = unwrapped_frac @ orth.T + vec
    # Put distinct independent components into the nearest equivalent
    # packing around the largest component without changing connectivity.
    components.sort(key=len, reverse=True)
    anchor = coords[components[0]].mean(axis=0)
    for component in components[1:]:
        indices = np.asarray(component, dtype=np.int64)
        shift = _nearest_lattice_shift(coords[indices], anchor, orth, frac_of)
        unwrapped_frac[indices] += shift
        coords[indices] += orth @ shift
    unwrapped_atoms = [
        AtomSite(a.label, a.element, unwrapped_frac[i].copy(), a.density)
        for i, a in enumerate(atoms)
    ]
    return unwrapped_atoms, coords, bonds, extended


def build_complete_molecule_view(
    seed_atoms: Sequence[AtomSite],
    cell: gemmi.UnitCell,
    sg: gemmi.SpaceGroup,
    tolerance: float = BOND_TOLERANCE,
    max_length: float = MAX_BOND_LENGTH_ANGSTROM,
    max_atoms: int = MAX_MOLECULE_ATOMS,
) -> CompleteMoleculeView:
    """Grows the connected molecular/structural components of the RAW
    asymmetric unit (`seed_atoms`, e.g. from parse_cif_atoms -- NOT already
    symmetry-expanded), breadth-first, pulling in a symmetry-equivalent or
    periodic-neighbor image ONLY when it is within bonding distance of an
    atom already accepted into the component.

    Each asymmetric-unit atom is represented once: when a component reaches
    any image of another seed, that seed is marked covered and never starts
    a second, equivalent copy of the same molecule elsewhere in the cell
    (the source of both duplicate bonding and wildly separated fragments in
    the previous version). Components are then shifted by whole lattice
    vectors to sit next to the largest one.

    Single unbonded peaks are NOT primary content: they never enter the fit
    bounds; the ones already inside the primary sphere are returned as a
    secondary layer. If nothing at all is bonded (e.g. an early noisy
    cycle), the asymmetric-unit peaks themselves are the primary content, so
    the panel is never blank.

    A pure, read-only, presentation-only transform: never mutates
    `seed_atoms`, never writes to disk."""
    raw_seeds = [a for a in seed_atoms if clean_element_symbol(a.element) not in {"H", "D", "He"}]
    empty = np.zeros((0, 3), dtype=np.float64)
    if not raw_seeds:
        return CompleteMoleculeView([], empty, [], [], empty, np.zeros(3), MIN_FIT_RADIUS_ANGSTROM)
    # EDMA/P1 exports can contain exact or periodically equivalent copies.
    # Collapse only same-element sites that are crystallographically
    # coincident; the deliberately tight Cartesian tolerance cannot merge
    # distinct chemical sites.
    seeds: List[AtomSite] = []
    for atom in raw_seeds:
        duplicate = False
        for kept in seeds:
            if clean_element_symbol(atom.element) != clean_element_symbol(kept.element):
                continue
            delta = np.asarray(atom.frac, dtype=np.float64) - np.asarray(kept.frac, dtype=np.float64)
            delta -= np.round(delta)
            if np.linalg.norm(_orthogonalize_frac(cell, delta)) <= 0.05:
                duplicate = True
                break
        if not duplicate:
            seeds.append(atom)
    # A periodically bonded framework has no finite "complete molecule".
    # Bound its presentation fragment relative to the asymmetric unit so a
    # MOF cannot expand toward the full-cell population (or the global 800
    # marker ceiling) merely because every symmetry image remains bonded.
    # Small molecules still complete freely; Full cell remains the authority
    # for viewing every crystallographic image.
    max_atoms = min(int(max_atoms), max(64, 2 * len(seeds)))

    orth, vec, frac_of = _cell_matrices(cell)
    offsets = np.asarray(
        [
            (dx, dy, dz)
            for dx in range(-MOLECULE_PERIODIC_TRANSLATIONS, MOLECULE_PERIODIC_TRANSLATIONS + 1)
            for dy in range(-MOLECULE_PERIODIC_TRANSLATIONS, MOLECULE_PERIODIC_TRANSLATIONS + 1)
            for dz in range(-MOLECULE_PERIODIC_TRANSLATIONS, MOLECULE_PERIODIC_TRANSLATIONS + 1)
        ],
        dtype=np.float64,
    )

    # Candidate pool: every symmetry image (the established
    # expand_atoms_by_symmetry, which wraps into [0,1)) of every seed, in the
    # home cell and its 26 neighbors, remembering which seed AND which
    # space-group operation (expand_atoms_by_symmetry's own "_<op_idx+1>"
    # label suffix -- op 0 is always the identity, by the same gemmi
    # convention full_spacegroup_ops relies on) it came from.
    pool_atoms: List[AtomSite] = []
    pool_seed: List[int] = []
    pool_op: List[int] = []
    pool_frac: List[np.ndarray] = []
    for seed_index, seed in enumerate(seeds):
        for image in expand_atoms_by_symmetry([seed], sg):
            op_idx = int(image.label.rsplit("_", 1)[1]) - 1
            for offset in offsets:
                pool_frac.append(image.frac + offset)
                pool_atoms.append(image)
                pool_seed.append(seed_index)
                pool_op.append(op_idx)
    pool_frac_array = np.asarray(pool_frac, dtype=np.float64)
    pool_coords = pool_frac_array @ orth.T + vec
    pool_radii = np.asarray([_covalent_radius(a.element) for a in pool_atoms], dtype=np.float64)
    grid = _NeighborGrid(pool_coords, max_length)

    def key_of(element: str, coord: np.ndarray) -> tuple:
        return (clean_element_symbol(element), *(round(float(v), 2) for v in coord))

    covered = np.zeros(len(seeds), dtype=bool)
    components: List[Tuple[List[AtomSite], List[np.ndarray]]] = []
    total_atoms = 0
    for seed_index, seed in enumerate(seeds):
        if covered[seed_index] or total_atoms >= max_atoms:
            continue
        seed_coord = np.asarray(seed.frac, dtype=np.float64) @ orth.T + vec
        comp_atoms: List[AtomSite] = [seed]
        comp_coords: List[np.ndarray] = [seed_coord]
        accepted = {key_of(seed.element, seed_coord)}
        # A completed independent component contains each ASU site once.
        # Its particular symmetry/translation image is selected by the
        # bond that reaches it.  This is the key distinction from the old
        # walk, which admitted the same site once for every space-group
        # operation and therefore accumulated equivalent molecules.
        placed_seed = {seed_index}
        placed_seed_op = {seed_index: 0}
        frontier = [0]
        while frontier and total_atoms + len(comp_atoms) < max_atoms:
            next_frontier: List[int] = []
            for fi in frontier:
                point = comp_coords[fi]
                near = grid.candidates(point)
                if near.size == 0:
                    continue
                distances = np.linalg.norm(pool_coords[near] - point, axis=1)
                limits = np.minimum(max_length, tolerance * (_covalent_radius(comp_atoms[fi].element) + pool_radii[near]))
                valid = near[(distances > 1.0e-3) & (distances <= limits)]
                # Several periodic/symmetry images of one seed may satisfy a
                # cutoff.  Retain only its nearest bonded realization.
                best_by_seed: dict[int, int] = {}
                for pi_value in valid:
                    pi = int(pi_value)
                    candidate_seed = pool_seed[pi]
                    if candidate_seed in placed_seed:
                        continue
                    previous = best_by_seed.get(candidate_seed)
                    if previous is None or np.linalg.norm(pool_coords[pi] - point) < np.linalg.norm(pool_coords[previous] - point):
                        best_by_seed[candidate_seed] = pi
                for pi in best_by_seed.values():
                    key = key_of(pool_atoms[pi].element, pool_coords[pi])
                    if key in accepted:
                        continue
                    accepted.add(key)
                    placed_seed.add(pool_seed[pi])
                    placed_seed_op[pool_seed[pi]] = pool_op[pi]
                    source = pool_atoms[pi]
                    comp_atoms.append(AtomSite(label=source.label, element=source.element, frac=pool_frac_array[pi].copy(), density=source.density))
                    comp_coords.append(pool_coords[pi])
                    next_frontier.append(len(comp_atoms) - 1)
                    if total_atoms + len(comp_atoms) >= max_atoms:
                        break
                if total_atoms + len(comp_atoms) >= max_atoms:
                    break
            frontier = next_frontier
        # A molecule lying on a crystallographic symmetry element can need
        # one non-identity mate of an ASU site to become chemically whole.
        # Admit at most one such mate per seed, and only when it is directly
        # bonded to the already realized component.  General-position
        # equivalent molecules are not bonded and periodic frameworks stay
        # bounded instead of walking through every operation/cell.
        symmetry_completed_seeds: set[int] = set()
        # Large connected ASU graphs are periodic frameworks in practice;
        # they have no finite molecular completion and must remain one
        # independent crystallographic component rather than being doubled
        # through symmetry.  Small molecular/special-position components
        # still receive the one required non-identity mate per site.
        completion_frontier = list(range(len(comp_atoms))) if len(comp_atoms) <= 64 else []
        while completion_frontier:
            current_index = completion_frontier.pop(0)
            existing_atom, point = comp_atoms[current_index], comp_coords[current_index]
            near = grid.candidates(point)
            if near.size == 0:
                continue
            distances = np.linalg.norm(pool_coords[near] - point, axis=1)
            limits = np.minimum(max_length, tolerance * (_covalent_radius(existing_atom.element) + pool_radii[near]))
            valid = [
                int(pi) for pi in near[(distances > 1.0e-3) & (distances <= limits)]
                if pool_seed[int(pi)] in placed_seed
                and pool_op[int(pi)] != placed_seed_op.get(pool_seed[int(pi)], pool_op[int(pi)])
            ]
            for seed_id in sorted({pool_seed[pi] for pi in valid}):
                if seed_id in symmetry_completed_seeds:
                    continue
                options = [pi for pi in valid if pool_seed[pi] == seed_id]
                pi = min(options, key=lambda item: float(np.linalg.norm(pool_coords[item] - point)))
                key = key_of(pool_atoms[pi].element, pool_coords[pi])
                if key in accepted or total_atoms + len(comp_atoms) >= max_atoms:
                    continue
                accepted.add(key)
                symmetry_completed_seeds.add(seed_id)
                source = pool_atoms[pi]
                comp_atoms.append(AtomSite(label=source.label, element=source.element, frac=pool_frac_array[pi].copy(), density=source.density))
                comp_coords.append(pool_coords[pi])
                completion_frontier.append(len(comp_atoms) - 1)
        covered[list(placed_seed)] = True
        components.append((comp_atoms, comp_coords))
        total_atoms += len(comp_atoms)

    bonded = [c for c in components if len(c[0]) >= 2]
    singles = [c for c in components if len(c[0]) < 2]
    if not bonded:
        # Nothing is connected at all: show the asymmetric-unit peaks
        # themselves (compacted), rather than an empty panel.
        bonded, singles = singles, []

    bonded.sort(key=lambda c: len(c[0]), reverse=True)
    anchor_coords = np.asarray(bonded[0][1], dtype=np.float64)
    anchor_center = anchor_coords.mean(axis=0)

    def placed(component: Tuple[List[AtomSite], List[np.ndarray]]) -> Tuple[List[AtomSite], np.ndarray]:
        atoms, coords = component
        coords_array = np.asarray(coords, dtype=np.float64)
        shift = _nearest_lattice_shift(coords_array, anchor_center, orth, frac_of)
        if not np.any(shift):
            return list(atoms), coords_array
        moved = [
            AtomSite(label=a.label, element=a.element, frac=np.asarray(a.frac, dtype=np.float64) + shift, density=a.density)
            for a in atoms
        ]
        return moved, coords_array + orth @ shift

    # Which bonded components define the view: the largest one, plus any
    # other that is either comparable in size (Z' > 1, two similar
    # molecules) or genuinely packed against it (a counter-ion / co-former
    # within one bond length of the main component's sphere). Small bonded
    # fragments further away -- typically noise peaks that happen to sit
    # within bonding distance of one another -- are demoted to the
    # secondary layer, exactly like single peaks, so they cannot inflate Fit.
    largest_size = len(bonded[0][0])
    primary_atoms: List[AtomSite] = list(bonded[0][0])
    primary_coords: List[np.ndarray] = list(anchor_coords)
    demoted: List[Tuple[List[AtomSite], np.ndarray]] = []
    for component in bonded[1:]:
        atoms, coords = placed(component)
        # Independent Z' molecules have comparable complete component sizes.
        # A much smaller disconnected EDMA island is usually an incomplete
        # peak fragment and must not be promoted beside the main object just
        # because it barely exceeds half its site count.
        if len(atoms) >= 0.8 * largest_size:
            primary_atoms.extend(atoms)
            primary_coords.extend(coords)
        else:
            demoted.append((atoms, coords))
    # The component-selection pass above decides which crystallographic
    # sites belong in this representation. Build the FINAL drawable graph
    # from those sites with periodic minimum-image edges, then unwrap it.
    # This avoids both torn boundary-crossing molecules and ghost bonds from
    # atoms discarded during selection.
    primary_atoms, coords_array, bonds, _extended_framework = periodic_connectivity_unwrap(
        primary_atoms, cell, tolerance=tolerance, max_length=max_length,
    )
    if bond_graph_problems(len(primary_atoms), coords_array, bonds, max_length):
        bonds = []
    center, radius = _bounding_sphere(coords_array)

    secondary_atoms: List[AtomSite] = []
    secondary_coords: List[np.ndarray] = []
    for atoms, coords in demoted + [placed(component) for component in singles]:
        for atom, coord in zip(atoms, coords):
            if float(np.linalg.norm(coord - center)) <= radius:
                secondary_atoms.append(atom)
                secondary_coords.append(coord)

    return CompleteMoleculeView(
        atoms=primary_atoms,
        coords=coords_array,
        bonds=bonds,
        secondary_atoms=secondary_atoms,
        secondary_coords=np.asarray(secondary_coords, dtype=np.float64).reshape(-1, 3),
        fit_center=center,
        fit_radius=radius,
        unassigned_peak_count=len(singles) + sum(len(atoms) for atoms, _coords in demoted),
    )


def build_complete_molecule_fragment(
    seed_atoms: Sequence[AtomSite],
    cell: gemmi.UnitCell,
    sg: gemmi.SpaceGroup,
    tolerance: float = BOND_TOLERANCE,
    max_length: float = MAX_BOND_LENGTH_ANGSTROM,
    max_atoms: int = MAX_MOLECULE_ATOMS,
) -> Tuple[List[AtomSite], np.ndarray, List[Tuple[int, int]]]:
    """(atoms, cartesian_coords, bonds) of build_complete_molecule_view()'s
    primary content."""
    view = build_complete_molecule_view(seed_atoms, cell, sg, tolerance, max_length, max_atoms)
    return view.atoms, view.coords, view.bonds


_MOLECULE_VIEW_CACHE: dict = {}


def _complete_molecule_view_for_path(path: Optional[Path]) -> Optional[CompleteMoleculeView]:
    """Read-only re-parse of the same CIF already being displayed, purely
    to recover the raw asymmetric-unit atoms + cell/space group that the
    already-expanded AtomSite lists elsewhere in this module don't carry.
    Never touches EDMA output/the candidate CIF/the map/the recommendation/
    the Jana handoff -- this is a viewer-only transform, and on ANY failure
    (missing file, unparseable CIF, empty asymmetric unit) it returns None
    so the caller can fall back cleanly to Full-cell rather than presenting
    a broken bonded view. Cached per (path, mtime, size): switching view
    mode or re-rendering an unchanged candidate does not regrow it."""
    if path is None:
        return None
    try:
        resolved = Path(path)
        if not resolved.is_file():
            return None
        stat = resolved.stat()
        cache_key = (str(resolved), stat.st_mtime_ns, stat.st_size)
        if cache_key in _MOLECULE_VIEW_CACHE:
            return _MOLECULE_VIEW_CACHE[cache_key]
        cell, sg, _ = parse_cif_cell_and_sg(resolved)
        seed_atoms = parse_cif_atoms(resolved)
        if not seed_atoms:
            return None
        view = build_complete_molecule_view(seed_atoms, cell, sg)
        if len(_MOLECULE_VIEW_CACHE) > 16:
            _MOLECULE_VIEW_CACHE.clear()
        _MOLECULE_VIEW_CACHE[cache_key] = view
        return view
    except Exception:
        return None


def prepare_structure_presentation(
    path: Optional[Path], view_mode: str = "molecule", composition: str = "",
    composition_label: str = "Composition",
) -> dict:
    """One read-only geometry authority for embedded and detached viewers."""
    resolved = Path(path) if path is not None else None
    if resolved is None or not resolved.is_file():
        return {"atoms": [], "coords": np.zeros((0, 3)), "bonds": [], "cell_segments": [],
                "composition": str(composition or ""), "formula": str(composition or ""),
                "composition_label": str(composition_label or "Composition"),
                "detected": 0, "fit": None}
    raw_atoms = parse_cif_atoms(resolved)
    cell, sg, _hm = parse_cif_cell_and_sg(resolved)
    independent_composition = str(composition or "").strip() or composition_from_atoms(raw_atoms)
    counts = {"independent_asu_sites": len(edma_asu_atoms(raw_atoms, cell, sg))}
    if str(view_mode) != "cell":
        view = build_complete_molecule_view(raw_atoms, cell, sg)
        return {
            "atoms": view.atoms, "coords": view.coords, "bonds": view.bonds,
            "cell_segments": [], "composition": independent_composition,
            "formula": independent_composition, "composition_label": composition_label,
            "detected": len(raw_atoms), "displayed": len(view.atoms), **counts,
            "fit": (view.fit_center, view.fit_radius),
        }
    atoms = expand_atoms_by_symmetry(raw_atoms, sg)
    coords = []
    for atom in atoms:
        pos = cell.orthogonalize(gemmi.Fractional(*map(float, atom.frac)))
        coords.append((pos.x, pos.y, pos.z))
    array = np.asarray(coords, dtype=np.float64).reshape(-1, 3)
    corners = []
    for frac in ((0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0),
                 (0, 0, 1), (1, 0, 1), (0, 1, 1), (1, 1, 1)):
        pos = cell.orthogonalize(gemmi.Fractional(*frac))
        corners.append(np.asarray((pos.x, pos.y, pos.z), dtype=np.float64))
    edges = ((0, 1), (0, 2), (0, 4), (1, 3), (1, 5), (2, 3),
             (2, 6), (3, 7), (4, 5), (4, 6), (5, 7), (6, 7))
    segments = [np.asarray((corners[i], corners[j])) for i, j in edges]
    content = np.vstack((array, np.asarray(corners))) if len(array) else np.asarray(corners)
    center, radius = _bounding_sphere(content)
    return {
        "atoms": atoms, "coords": array, "bonds": [], "cell_segments": segments,
        "composition": independent_composition, "formula": independent_composition,
        "composition_label": composition_label,
        "detected": len(raw_atoms), "displayed": len(atoms), **counts, "fit": (center, radius),
    }


def structure_site_summary(path: Path, data: dict, view_mode: str) -> str:
    """Describe detection, independent sites and rendering without conflating them."""
    m40 = Path(path).with_suffix(".m40")
    try:
        jana_sites = str(_m40_model_count(m40)) if m40.is_file() else "unavailable"
    except RuntimeError:
        jana_sites = "unavailable"
    raw_sites = "not recorded"
    sidecar = Path(path).with_name(Path(path).stem + "_site_counts.json")
    if sidecar.is_file():
        try:
            raw_sites = str(json.loads(sidecar.read_text(encoding="utf-8"))["raw_edma_sites"])
        except (OSError, ValueError, KeyError):
            pass
    representation = "Full cell" if view_mode == "cell" else "Complete molecules"
    return (f"Raw EDMA detected sites: {raw_sites}; CIF EDMA sites: {data.get('detected', 0)}; "
            f"independent ASU sites: {data.get('independent_asu_sites', 0)}; "
            f"displayed in {representation}: {data.get('displayed', len(data.get('atoms', [])))}; "
            f"Jana m40 sites: {jana_sites}. Display expansion does not detect additional sites.")


_UNIT_ZOOM_SPHERE_FILL: Optional[float] = None


def _unit_zoom_sphere_fill() -> float:
    """Fraction of a 3D axes' drawing square that a sphere's DIAMETER spans
    when the axes' limits are the cube circumscribing that sphere, box
    aspect is 1:1:1, box zoom is 1.0 and the projection is orthographic.

    Measured once from matplotlib itself (not assumed), so the camera fit
    stays exact across matplotlib versions. The value does not depend on
    elevation/azimuth or on the canvas size -- Axes3D always draws into the
    largest square inside its subplot -- which is what makes a
    sphere-based fit rotation-safe."""
    global _UNIT_ZOOM_SPHERE_FILL
    if _UNIT_ZOOM_SPHERE_FILL is not None:
        return _UNIT_ZOOM_SPHERE_FILL
    measured = 0.5947
    try:
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from mpl_toolkits.mplot3d import proj3d

        figure = Figure(figsize=(4.0, 4.0), dpi=100)
        FigureCanvasAgg(figure)
        axis = figure.add_subplot(1, 1, 1, projection="3d")
        axis.set_proj_type("ortho")
        axis.set_xlim3d(-1.0, 1.0)
        axis.set_ylim3d(-1.0, 1.0)
        axis.set_zlim3d(-1.0, 1.0)
        axis.set_box_aspect((1.0, 1.0, 1.0), zoom=1.0)
        axis.view_init(elev=20.0, azim=35.0)
        figure.canvas.draw()
        azim = np.radians(35.0)
        screen_right = np.array([-np.sin(azim), np.cos(azim), 0.0])
        projection = axis.get_proj()
        p0 = proj3d.proj_transform(0.0, 0.0, 0.0, projection)
        p1 = proj3d.proj_transform(*screen_right, projection)
        d0 = axis.transData.transform((p0[0], p0[1]))
        d1 = axis.transData.transform((p1[0], p1[1]))
        extent = axis.get_window_extent()
        value = float(np.linalg.norm(d1 - d0) / (min(extent.width, extent.height) / 2.0))
        if 0.1 < value < 2.0:
            measured = value
    except Exception:
        pass
    _UNIT_ZOOM_SPHERE_FILL = measured
    return measured


# Shared layout spacing for every horizontal band of the window, so the
# status header, view toolbar, formula row, log, progress panel and footer
# all start on the same left edge as the branded header (whose own
# contentsMargins are 12px, see create_phase_studio_brand_header()).
SECTION_GUTTER = 12
SECTION_VPAD = 5
TOOLBAR_GROUP_SPACING = 6
TOOLBAR_SECTION_SPACING = 16
# Structure panel captions (matplotlib figure text), in points.
PANEL_TITLE_FONT_PT = 10.5
PANEL_SUBTITLE_FONT_PT = 9.0
PANEL_CAPTION_TOP_PAD_PT = 6.0
PANEL_CAPTION_LINE_GAP_PT = 3.0
PANEL_CAPTION_BOTTOM_PAD_PT = 8.0


class AutosolveWindow(QMainWindow):
    # Borrowed rendering/camera-sync methods -- identical set to
    # create_result_preview_host()'s _PreviewHost (result_selection.py), just
    # bound onto a real, visible QMainWindow instead of a throwaway object.
    # _update_structure_depth_cue and _apply_structure_view are NOT
    # borrowed: they are overridden below (bond/secondary-layer depth cue;
    # per-panel relative camera sync, since Complete-molecules panels each
    # frame their own fragment rather than one shared unit cell).
    _structure_cartesian_geometry = IterativeSuperflipPipelineQtGUI._structure_cartesian_geometry
    _element_color = IterativeSuperflipPipelineQtGUI._element_color
    _plot_structure_atoms = IterativeSuperflipPipelineQtGUI._plot_structure_atoms
    _update_structure_depth_artist = IterativeSuperflipPipelineQtGUI._update_structure_depth_artist
    _structure_axis_limits = staticmethod(IterativeSuperflipPipelineQtGUI._structure_axis_limits)
    _apply_structure_axis_limits = staticmethod(IterativeSuperflipPipelineQtGUI._apply_structure_axis_limits)
    _begin_structure_view_drag = IterativeSuperflipPipelineQtGUI._begin_structure_view_drag
    _sync_structure_view_from_event = IterativeSuperflipPipelineQtGUI._sync_structure_view_from_event
    _finish_structure_view_drag = IterativeSuperflipPipelineQtGUI._finish_structure_view_drag

    def __init__(
        self, backend: IterativeSuperflipPipelineQtGUI, option: str,
        inflip_path: Optional[Path] = None, workflow_name: str = "SharpED Autosolve",
    ) -> None:
        super().__init__()
        self.backend = backend
        self.option = "B" if str(option).strip().upper() == "B" else "A"
        # The Jana2020 job this window was launched for. Once the backend
        # captures its RunConfig, that captured jana_inflip is authoritative
        # (see _active_inflip_path) -- never QSettings or the work directory.
        self._launch_inflip_path = Path(inflip_path) if inflip_path else None
        self._displayed_elements: List[str] = []
        self.workflow_name = str(workflow_name or "SharpED Autosolve")
        self._ordinary_dual_workflow = self.workflow_name.casefold() == "superflip + sharped"
        # This window is shared by the ordinary recommended workflow and the
        # separate experimental Autosolve workflow.  Keep their preparation
        # language instance-local so the experimental name cannot leak into
        # an ordinary Superflip + SharpED run.
        self._preparing_text = (
            "Preparing workflow…" if self._ordinary_dual_workflow else PREPARING_TEXT
        )
        self.setWindowTitle(f"Phase Studio {__version__} — {self.workflow_name}")
        self.setWindowIcon(create_phase_studio_app_icon(64))
        # The shared Result Selection dialog opened at Autosolve's end point
        # belongs to this visible window, not to the hidden backend.
        backend.autosolve_dialog_parent = self

        # Shared structure-view state the borrowed methods above operate on
        # -- same attribute names create_result_preview_host()'s _PreviewHost
        # uses, own independent state (not aliased to backend's).
        self.structure_cell = None
        self.structure_axes: list = []
        self._structure_interactive_axes: list = []
        self._structure_depth_artists: list = []
        self._secondary_depth_artists: list = []
        self._bond_artists: List[_BondArtist] = []
        self.structure_elev = 20.0
        self.structure_azim = 35.0
        self.structure_view_base_limits = None
        self.structure_view_limits = None
        self._structure_view_drag_source = None
        self.structure_canvas = None
        # Camera: each panel owns its content-derived center, radius and
        # limits.  Only orientation is shared between panels.
        self._axis_fits: dict = {}
        self._axis_roles: dict = {}
        self._pending_fit_roles: set = set()
        self._manual_camera_roles: set = set()
        self._view_zoom = 1.0
        self._view_pan = np.zeros(3, dtype=np.float64)
        # Per-role memory of the last fitted extent, so a genuine data
        # transition (new candidate, or the same candidate's extent
        # changing materially -- e.g. a big threshold move revealing many
        # more/fewer atoms) resets zoom/pan to a fresh fit, while ordinary
        # +/- atoms nudges that barely change the extent leave the user's
        # current zoom/pan alone. Never touched by mouse interaction.
        self._last_fit_cycle_by_role: dict = {}
        self._last_fit_radius_by_role: dict = {}

        self._last_superflip_cycle: Optional[int] = None
        self._last_deblurred_cycle: Optional[int] = None
        self._last_reference_available = False
        self._rendered_once = False
        self._auto_rotate_enabled = True
        self._last_interaction_time = 0.0
        # Complete molecules (default -- most useful for a recognizable
        # fragment, especially early/no-reference cycles) vs Full cell
        # (unit-cell atom/peak context, never bonded). One shared mode for
        # every visible panel.
        self.view_mode = "molecule"
        self._last_superflip_candidate: Optional[ResultCandidate] = None
        self._last_deblurred_candidate: Optional[ResultCandidate] = None
        self._panel_captions: list = []
        # 2.0.1: what each panel currently shows (ReviewPanel or None) and the
        # signature it was rendered from.
        self._last_panels: dict = {guided.ROLE_OBSERVED: None, guided.ROLE_PREDICTED: None}
        self._render_signature = None
        self._panel_atom_counts: dict = {}
        self._panel_retune_errors: dict = {}
        self._detached_viewer = None

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(create_phase_studio_brand_header())
        root.addWidget(self._build_status_header())
        root.addWidget(self._build_view_toolbar())
        root.addWidget(self._build_element_legend())

        # Structures are the primary content: a large stretch factor relative
        # to every other section below dominates the available height.
        self.structure_figure = Figure(figsize=(14.0, 7.5), dpi=100)
        self.structure_figure.patch.set_facecolor("#ffffff")
        self.structure_canvas = FigureCanvas(self.structure_figure)
        self.structure_canvas.setObjectName("autosolveStructureCanvas")
        # The canvas absorbs height reductions before scientific metadata,
        # the bounded log, progress, or the fixed action footer are clipped.
        self.structure_canvas.setMinimumHeight(140 if self._ordinary_dual_workflow else 210)
        self.structure_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.structure_canvas.mpl_connect("resize_event", self._on_structure_resize)
        self.structure_canvas.setToolTip("")
        self._structure_fit_timer = QTimer(self)
        self._structure_fit_timer.setSingleShot(True)
        self._structure_fit_timer.setInterval(0)
        self._structure_fit_timer.timeout.connect(self._apply_automatic_structure_fit)
        self._camera = StructureCameraController(
            self.structure_canvas,
            lambda: self._structure_interactive_axes,
            fit=self._fit_active_structure_view,
            reset=self._reset_active_structure_view,
            orientation_changed=self._camera_orientation_changed,
            interaction=self._camera_interaction,
            toggle_auto_rotate=lambda: self.auto_rotate_button.toggle(),
        )
        root.addWidget(self.structure_canvas, 14)

        # One column per panel under it (equal stretch, matching the
        # equal-width subplot grid): composition, technical origin, and in
        # Review the four panel actions.
        root.addWidget(self._build_review_area())
        self.validation_note = QLabel(
            "SharpED predictions require validation against the original measured diffraction data "
            "and independent crystallographic refinement."
        )
        self.validation_note.setWordWrap(True)
        self.validation_note.setStyleSheet("color: #52658b; padding: 3px 12px;")
        self.validation_note.setVisible(False)
        root.addWidget(self.validation_note)
        root.addWidget(self._build_correction_row())

        self.log_section_widget = self._build_log_section()
        root.addWidget(self.log_section_widget, 0)
        # The real widget, moved here from the (never-shown) backend window --
        # backend's own _append_execution_log keeps writing into it exactly
        # as it always has; nothing here re-implements log rendering. Kept
        # compact so it stays secondary to the structures.
        self._log_layout.addWidget(backend.log_text, 0)
        if self._ordinary_dual_workflow:
            backend.log_text.setStyleSheet('font-family: "Segoe UI"; font-size: 10pt;')
        backend.log_text.horizontalScrollBar().rangeChanged.connect(lambda *_: QTimer.singleShot(0, self._fit_log_height))
        # Follow the newest line unless the user scrolls up. The backend only
        # auto-scrolls while the view is within a few pixels of the bottom;
        # a height refit used to leave it ~28 px short, so it stopped
        # following and froze on a half-visible top line.
        self._log_following = True
        log_bar = backend.log_text.verticalScrollBar()
        log_bar.rangeChanged.connect(lambda _min, maximum: self._keep_log_at_bottom())
        log_bar.actionTriggered.connect(lambda _action: QTimer.singleShot(0, self._update_log_following))
        self._fit_log_height()

        # The real progress-bar panel, moved here from `backend` -- its own
        # _apply_cycle_progress_state()/_apply_superflip_repeat_state()/
        # _set_overall_progress_text() keep updating these exact widgets.
        # No stretch factor and no height cap: it sizes to its own sizeHint.
        self._compact_run_status_panel()
        root.addWidget(backend.run_status_panel)

        root.addWidget(self._build_action_row())

        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_tick)
        self._refresh_timer.start(REFRESH_INTERVAL_MS)

        self._rotate_timer = QTimer(self)
        self._rotate_timer.timeout.connect(self._auto_rotate_tick)
        self._rotate_timer.start(AUTO_ROTATE_INTERVAL_MS)

        self._refresh_tick()

    # ----- Construction helpers -----

    def _build_status_header(self) -> QWidget:
        # One compact line ("Predict the structure model · Cycle 3 of 10 ·
        # Superflip · Running"). The best cycle per source is NOT repeated
        # here -- it is shown once, directly above each structure.
        header = QWidget()
        header.setObjectName("dashboardHeader")
        layout = QVBoxLayout(header)
        layout.setContentsMargins(SECTION_GUTTER, SECTION_VPAD, SECTION_GUTTER, SECTION_VPAD)
        layout.setSpacing(1)
        self.status_headline = QLabel("Autosolve")
        self.status_headline.setObjectName("dashboardTitle")
        # Secondary context line: the Jana2020 .inflip being solved (basename,
        # middle-elided when long, full path in the tooltip). Hidden while
        # there is nothing to show so it never reserves a blank line.
        self.status_secondary = QLabel("")
        self.status_secondary.setObjectName("dashboardSubtitle")
        self.status_secondary.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.status_secondary.setVisible(False)
        layout.addWidget(self.status_headline)
        layout.addWidget(self.status_secondary)
        return header

    def _build_view_toolbar(self) -> QWidget:
        # [Fit] [Reset view] [Auto rotate]      View: [Complete molecules | Full cell]
        # Text-only: Phase Studio has no established icons for these view
        # actions, and text-only is preferred over introducing another
        # visual family. One shared height for every control.
        bar = QWidget()
        bar.setObjectName("autosolveViewToolbar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(SECTION_GUTTER, 3, SECTION_GUTTER, 3)
        layout.setSpacing(TOOLBAR_GROUP_SPACING)
        hint = QLabel("Drag to rotate · Wheel to zoom")
        hint.setToolTip("Left-drag: rotate · Right/Middle/Shift-left-drag: pan · "
                        "Wheel: zoom · Double-click or F: fit active viewer · R: reset active viewer")
        hint.setObjectName("progressSectionLabel")
        layout.addWidget(hint)
        layout.addStretch(1)

        fit_button = QToolButton()
        fit_button.setObjectName("viewToolButton")
        fit_button.setText("Fit")
        fit_button.setToolTip("Fit the displayed structure to the panel, keeping the current rotation.")
        fit_button.clicked.connect(self._fit_structure_view)
        reset_button = QToolButton()
        reset_button.setObjectName("viewToolButton")
        reset_button.setText("Reset view")
        reset_button.setToolTip("Reset rotation, zoom and pan to the default view.")
        reset_button.clicked.connect(self._reset_structure_view)
        self.auto_rotate_button = QToolButton()
        self.auto_rotate_button.setObjectName("viewToggleButton")
        self.auto_rotate_button.setCheckable(True)
        self.auto_rotate_button.setChecked(True)
        self.auto_rotate_button.setText("Auto rotate: On")
        self.auto_rotate_button.setToolTip("Slowly rotate the structures while idle. Click to toggle.")
        self.auto_rotate_button.toggled.connect(self._on_auto_rotate_toggled)
        self.fit_button = fit_button
        self.reset_button = reset_button
        camera_label = QLabel("Both viewers" if self._ordinary_dual_workflow else "Camera")
        camera_label.setObjectName("progressSectionLabel")
        layout.addWidget(camera_label)
        layout.addWidget(fit_button)
        layout.addWidget(reset_button)
        layout.addWidget(self.auto_rotate_button)
        if self._ordinary_dual_workflow:
            fit_button.setToolTip("Fit both displayed structures. Use the panel Fit action to fit only one.")
            reset_button.setToolTip("Reset both viewers. Press R over the active viewer to reset only that view.")
            self.auto_rotate_button.setToolTip("Rotate both viewers while idle. Manual rotation stops automatic rotation.")

        self._cycle_combos = {}

        layout.addSpacing(TOOLBAR_SECTION_SPACING)
        view_label = QLabel("Representation")
        view_label.setObjectName("progressSectionLabel")
        layout.addWidget(view_label)
        # A true segmented control: adjoining buttons (zero spacing), one
        # shared border, exclusive group, solid-fill checked state.
        self.view_mode_group = QButtonGroup(self)
        self.view_mode_group.setExclusive(True)
        segment_row = QHBoxLayout()
        segment_row.setContentsMargins(0, 0, 0, 0)
        segment_row.setSpacing(0)
        self.molecule_view_button = QToolButton()
        self.molecule_view_button.setObjectName("viewModeSegmentLeft")
        self.molecule_view_button.setText("Complete molecules")
        self.molecule_view_button.setToolTip(
            "Connected molecular/structural fragments of the asymmetric unit, completed with "
            "the symmetry mates they need, with chemically local bonds. Isolated peaks do not "
            "affect the framing."
        )
        self.molecule_view_button.setCheckable(True)
        self.molecule_view_button.setChecked(True)
        self.full_cell_view_button = QToolButton()
        self.full_cell_view_button.setObjectName("viewModeSegmentRight")
        self.full_cell_view_button.setText("Full cell")
        self.full_cell_view_button.setToolTip(
            "The complete unit-cell atom/peak distribution with the cell frame, without bond connectivity."
        )
        self.full_cell_view_button.setCheckable(True)
        self.view_mode_group.addButton(self.molecule_view_button)
        self.view_mode_group.addButton(self.full_cell_view_button)
        self.molecule_view_button.toggled.connect(
            lambda checked: checked and self._set_view_mode("molecule")
        )
        self.full_cell_view_button.toggled.connect(
            lambda checked: checked and self._set_view_mode("cell")
        )
        segment_row.addWidget(self.molecule_view_button)
        segment_row.addWidget(self.full_cell_view_button)
        layout.addLayout(segment_row)

        self.view_toolbar_buttons = (
            fit_button, reset_button, self.auto_rotate_button,
            self.molecule_view_button, self.full_cell_view_button,
        )
        for button in self.view_toolbar_buttons:
            button.setToolButtonStyle(Qt.ToolButtonTextOnly)
            button.setCursor(Qt.PointingHandCursor)
            # Reachable by Tab, but a mouse click (or the window opening)
            # never leaves a focus border on a view control.
            button.setFocusPolicy(Qt.TabFocus)
            button.ensurePolished()
        common_height = max(button.sizeHint().height() for button in self.view_toolbar_buttons)
        for button in self.view_toolbar_buttons:
            button.setFixedHeight(common_height)
        # Every control in this toolbar acts on rendered structure data.
        # Keep the checked preferences while disabling the actions until a
        # completed structure is actually present.
        self.structure_action_buttons = self.view_toolbar_buttons
        for button in self.structure_action_buttons:
            button.setEnabled(False)
        return bar

    def _cycle_candidates(self, role: str):
        return (
            self.backend.autosolve_observed_candidates()
            if role == guided.ROLE_OBSERVED else self.backend.autosolve_predicted_candidates()
        )

    def _sync_cycle_browsers(self) -> None:
        for role, combo in self._cycle_combos.items():
            selected = combo.currentData()
            cycles = [int(candidate.cycle) for candidate in self._cycle_candidates(role)]
            combo.setEnabled(bool(cycles))
            existing = [combo.itemData(index) for index in range(combo.count())]
            wanted = [None, *cycles]
            if existing == wanted:
                continue
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("Latest", None)
            for cycle in cycles:
                combo.addItem(f"Cycle {cycle}", cycle)
            index = combo.findData(selected)
            combo.setCurrentIndex(index if index >= 0 else 0)
            combo.blockSignals(False)

    def _cycle_selection_changed(self, _role: str) -> None:
        self._render_signature = None
        self._refresh_tick()

    def _step_panel_cycle(self, role: str, direction: int) -> None:
        combo = self._cycle_combos.get(role)
        if combo is None or combo.count() <= 1:
            return
        current = combo.currentIndex()
        if current == 0:
            current = combo.count() - 1
        combo.setCurrentIndex(max(1, min(combo.count() - 1, current + int(direction))))

    def _panel_fullscreen_presentation(self, role: str) -> dict:
        panel = self._display_panel(role)
        if panel is None:
            return {}
        composition_label = "EDMA asymmetric-unit composition"
        composition = panel.edma_asu_composition
        data = prepare_structure_presentation(
            Path(panel.current_cif), self.view_mode, composition, composition_label,
        )
        family = (
            "Charge-flipping solution" if self._ordinary_dual_workflow and role == guided.ROLE_OBSERVED else
            "Structure prediction" if self._ordinary_dual_workflow else panel.title
        )
        source = "Superflip" if role == guided.ROLE_OBSERVED else "SharpED"
        model = f" · {panel.sharped_model}" if panel.sharped_model else ""
        lineage = " · ".join(
            item for item in (
                getattr(panel, "reflection_input_provenance", ""),
                getattr(panel, "superflip_initialization", ""),
            ) if item
        )
        data["metadata"] = (
            f"{source}{model} · Cycle {panel.cycle}<br>"
            + (f"{html.escape(lineage)}<br>" if lineage else "")
            + f"<b>{html.escape(data.get('composition_label', 'Composition'))}:</b> "
            f"{html.escape(data.get('composition') or 'Unavailable')}<br>"
            f"EDMA {guided.format_sigma(panel.threshold_sigma)} · "
            f"{int(data.get('detected', 0)):,} EDMA sites"
            f"<br>{html.escape(structure_site_summary(Path(panel.current_cif), data, self.view_mode))}"
        )
        data["title"] = f"Phase Studio — {family} · Cycle {panel.cycle}"
        return data

    def _open_panel_fullscreen(self, role: str) -> None:
        panel = self._display_panel(role)
        if panel is None:
            return
        family = (
            "Charge-flipping solution" if self._ordinary_dual_workflow and role == guided.ROLE_OBSERVED else
            "Structure prediction" if self._ordinary_dual_workflow else panel.title
        )
        combo = self._cycle_combos.get(role)
        panel_axis = next((axis for axis, axis_role in self._axis_roles.items() if axis_role == role), None)
        self._panel_detached_viewers[role] = show_single_structure_viewer(
            self,
            f"Phase Studio — {family} · Cycle {panel.cycle}",
            lambda r=role: self._panel_fullscreen_presentation(r),
            color_for=self._element_color,
            existing=self._panel_detached_viewers.get(role),
            set_mode=lambda mode: (
                self.molecule_view_button.setChecked(mode == "molecule")
                if mode == "molecule" else self.full_cell_view_button.setChecked(True)
            ),
            adjust_threshold=lambda add, r=role: self._adjust_panel_threshold(r, add),
            previous_cycle=(lambda r=role: self._step_panel_cycle(r, -1)) if combo is not None else None,
            next_cycle=(lambda r=role: self._step_panel_cycle(r, 1)) if combo is not None else None,
            latest_cycle=(lambda c=combo: c.setCurrentIndex(0)) if combo is not None else None,
            elev=panel_axis.elev if self._ordinary_dual_workflow and panel_axis is not None else self.structure_elev,
            azim=panel_axis.azim if self._ordinary_dual_workflow and panel_axis is not None else self.structure_azim,
        )

    def _display_panel(self, role: str):
        combo = self._cycle_combos.get(role)
        cycle = combo.currentData() if combo is not None else None
        if cycle is None:
            return self.backend.autosolve_display_panel(role)
        candidate = next((item for item in self._cycle_candidates(role) if int(item.cycle) == int(cycle)), None)
        return self.backend._autosolve_panel_for_candidate(role, candidate)

    def _sync_view_controls(self) -> None:
        has_structure = bool(self._structure_interactive_axes)
        for button in self.structure_action_buttons:
            if button.isEnabled() != has_structure:
                button.setEnabled(has_structure)

    def _build_element_legend(self) -> QWidget:
        """Compact, informational element-colour legend between the view
        controls and the structures: only elements actually rendered in the
        visible panels, each swatch drawn with the SAME colour authority the
        renderer uses (IterativeSuperflipPipelineQtGUI._element_color). Wraps
        to a second line when many elements are present."""
        strip = QWidget()
        strip.setObjectName("autosolveElementLegend")
        layout = QHBoxLayout(strip)
        layout.setContentsMargins(SECTION_GUTTER, 0, SECTION_GUTTER, 2)
        self.element_legend = QLabel("")
        self.element_legend.setObjectName("elementLegend")
        self.element_legend.setTextFormat(Qt.RichText)
        self.element_legend.setWordWrap(True)
        self.element_legend.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(self.element_legend, 1)
        strip.setVisible(False)
        self._legend_strip = strip
        return strip

    def legend_entries(self) -> List[Tuple[str, str]]:
        """(element, colour) pairs currently shown in the legend."""
        return [(element, self._element_color(element)) for element in self._displayed_elements]

    def _refresh_legend_text(self) -> None:
        entries = self.legend_entries()
        if not entries:
            self._legend_strip.setVisible(False)
            return
        items = "&nbsp;&nbsp;&nbsp; ".join(
            f'<span style="white-space:nowrap;"><span style="color:{color}; font-size:12pt;">&#9679;</span>'
            f"&nbsp;{html.escape(element)}</span>"
            for element, color in entries
        )
        self.element_legend.setText(f'<span style="color:#52658b;">Elements:</span>&nbsp;&nbsp; {items}')
        self._legend_strip.setVisible(True)

    @staticmethod
    def _renderer_visible_elements(atoms: Sequence[AtomSite]) -> List[str]:
        """Exactly the elements the shared Full-cell renderer draws: it drops
        H/D/He and keeps at most the 800 heaviest atoms."""
        visible = [a for a in atoms if clean_element_symbol(a.element) not in RENDERER_HIDDEN_ELEMENTS]
        ranked = sorted(visible, key=lambda atom: element_atomic_number(atom.element), reverse=True)[:RENDERER_MAX_ATOMS]
        return [clean_element_symbol(a.element) for a in ranked]

    def _set_displayed_elements(self, elements: Sequence[str]) -> None:
        unique = sorted({clean_element_symbol(e) for e in elements if e}, key=lambda e: (-element_atomic_number(e), e))
        self._displayed_elements = unique
        self._refresh_legend_text()

    def _build_log_section(self) -> QWidget:
        section = QWidget()
        section.setObjectName("resultSection")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(SECTION_GUTTER, 4, SECTION_GUTTER, 4)
        layout.setSpacing(3)
        heading_row = QHBoxLayout()
        heading = QLabel("EXECUTION LOG")
        heading.setObjectName("sectionLabel")
        heading_row.addWidget(heading)
        heading_row.addStretch(1)
        self._log_expanded = False
        self.log_expand_button = QToolButton()
        self.log_expand_button.setObjectName("viewToolButton")
        self.log_expand_button.setText("Expand log")
        self.log_expand_button.setToolTip("Show more execution and provenance messages.")
        self.log_expand_button.clicked.connect(self._toggle_log_expanded)
        heading_row.addWidget(self.log_expand_button)
        self.log_open_button = QToolButton()
        self.log_open_button.setObjectName("viewToolButton")
        self.log_open_button.setText("Open log")
        self.log_open_button.setToolTip("Open the complete timestamped run diagnostic log.")
        self.log_open_button.clicked.connect(self.backend._open_run_diagnostic_log)
        heading_row.addWidget(self.log_open_button)
        layout.addLayout(heading_row)
        self._log_layout = layout
        return section

    def _toggle_log_expanded(self) -> None:
        self._log_expanded = not self._log_expanded
        self.log_expand_button.setText("Collapse log" if self._log_expanded else "Expand log")
        self._fit_log_height()

    def _compact_run_status_panel(self) -> None:
        """Presentation-only re-arrangement of the reparented backend panel
        into Autosolve's compact form:

            Overall                                         <value>
            [bar]
            Cycle 3 of 10 · Superflip · Running         Stage 2 of 6
            [bar]
            (Superflip repeat sub-progress, only while meaningful)

        The redundant "RUN STATUS" title and "Current cycle" caption are
        hidden (the cycle/stage text itself takes the caption's place), and
        the full GUI's "Configuration locked while the calculation is
        running." hint is detached -- Autosolve has no configuration panel
        to lock. The same widget objects are kept, so backend's own update
        calls still drive every one of them."""
        backend = self.backend
        panel = backend.run_status_panel
        layout = panel.layout()
        layout.setContentsMargins(SECTION_GUTTER, 4, SECTION_GUTTER, 6)
        title = panel.findChild(QLabel, "runStatusTitle")
        if title is not None:
            title.setVisible(False)

        # Detach the configuration-lock hint into a never-shown holder, so
        # backend's own _set_configuration_locked() can keep calling
        # setVisible() on it harmlessly.
        self._detached_widgets_holder = QWidget(self)
        self._detached_widgets_holder.setVisible(False)
        lock_hint = getattr(backend, "configuration_lock_hint", None)
        if lock_hint is not None:
            layout.removeWidget(lock_hint)
            lock_hint.setParent(self._detached_widgets_holder)

        # Move the cycle/stage text into the "Current cycle" caption's slot.
        detail = backend.current_cycle_detail
        counter = backend.current_cycle_stage_counter
        # QLabel auto-indents by half an "x" when it has a frame width and
        # indent == -1; pin it so the text starts on the "Overall" edge.
        detail.setIndent(0)
        for index in range(layout.count()):
            row = layout.itemAt(index).layout()
            if row is None or row.indexOf(counter) < 0:
                continue
            caption_item = row.itemAt(0)
            caption = caption_item.widget() if caption_item is not None else None
            if isinstance(caption, QLabel) and caption is not detail:
                caption.setVisible(False)
            layout.removeWidget(detail)
            row.insertWidget(0, detail, 1)
            break

        # Superflip-repeat sub-progress sits BELOW the stage bar it belongs to.
        repeat_group = backend.superflip_repeat_group
        layout.removeWidget(repeat_group)
        layout.insertWidget(layout.indexOf(backend.current_cycle_progress) + 1, repeat_group)
        panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        # Reserve the repeat row even while it is hidden; it becomes visible
        # during Superflip and must not outgrow the compact bounded panel.
        panel.setMaximumHeight(
            max(panel.minimumSizeHint().height(), panel.sizeHint().height())
            + repeat_group.sizeHint().height() + 8
        )
        if self._ordinary_dual_workflow:
            panel.setMaximumHeight(16777215)  # Active jobs may need several real status lines.

    def _build_review_area(self) -> QWidget:
        self.formula_row_widget = QWidget()
        self.formula_row = QHBoxLayout(self.formula_row_widget)
        self.formula_row.setContentsMargins(SECTION_GUTTER, 0, SECTION_GUTTER, SECTION_VPAD)
        self.formula_row.setSpacing(6)
        # Reference's slot stays blank (the known input, not a ranked result).
        self.reference_column = QWidget()
        reference_layout = QVBoxLayout(self.reference_column)
        reference_layout.setContentsMargins(0, 0, 0, 0)
        self.reference_formula_label = QLabel("")
        self.reference_formula_label.setObjectName("autosolveFormula")
        reference_layout.addWidget(self.reference_formula_label)
        reference_layout.addStretch(1)
        self.reference_column.setVisible(False)
        self.formula_row.addWidget(self.reference_column, 1)
        self.review_columns: dict = {}
        self._panel_detached_viewers: dict = {}
        for role in (guided.ROLE_OBSERVED, guided.ROLE_PREDICTED):
            column = QWidget()
            column.setObjectName(f"autosolveReviewColumn_{role}")
            layout = QVBoxLayout(column)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(2)
            navigation = QWidget()
            navigation_layout = QHBoxLayout(navigation)
            navigation_layout.setContentsMargins(0, 0, 0, 0)
            navigation_layout.setSpacing(5)
            navigation_layout.addStretch(1)
            cycle_combo = None
            if self._ordinary_dual_workflow:
                cycle_combo = QComboBox()
                cycle_combo.addItem("Latest", None)
                cycle_combo.setToolTip("Follow the latest completed cycle, or pin a completed cycle for inspection.")
                cycle_combo.currentIndexChanged.connect(lambda _index, r=role: self._cycle_selection_changed(r))
                self._cycle_combos[role] = cycle_combo
                previous = QToolButton()
                previous.setText("‹")
                previous.setAccessibleName("Previous completed candidate")
                previous.clicked.connect(lambda _=False,r=role: self._step_panel_cycle(r,-1))
                following = QToolButton()
                following.setText("›")
                following.setAccessibleName("Next completed candidate")
                following.clicked.connect(lambda _=False,r=role: self._step_panel_cycle(r,1))
                navigation_layout.addWidget(previous)
                navigation_layout.addWidget(cycle_combo)
                navigation_layout.addWidget(following)
            fullscreen_button = QPushButton("Fullscreen")
            fullscreen_button.setToolTip("Open this structure alone in a detached interactive viewer.")
            fullscreen_button.clicked.connect(lambda _=False, r=role: self._open_panel_fullscreen(r))
            panel_fit = QPushButton("Fit")
            panel_fit.setToolTip("Fit only this structure, preserving its orientation.")
            panel_fit.clicked.connect(lambda _=False, r=role: self._fit_panel(r))
            if self._ordinary_dual_workflow:
                navigation_layout.addWidget(panel_fit)
            navigation_layout.addWidget(fullscreen_button)
            navigation_layout.addStretch(1)
            formula = QLabel("")
            formula.setObjectName("autosolveFormula")
            formula.setAlignment(Qt.AlignCenter)
            formula.setWordWrap(True)
            detail = QLabel("")
            detail.setObjectName("autosolveReviewDetail")
            detail.setAlignment(Qt.AlignCenter)
            detail.setWordWrap(True)
            threshold = QLabel("")
            threshold.setObjectName("autosolveEdmaThreshold")
            threshold.setAlignment(Qt.AlignCenter)
            threshold.setVisible(False)
            actions = QWidget()
            actions_layout = QHBoxLayout(actions)
            actions_layout.setContentsMargins(0, 2, 0, 0)
            actions_layout.setSpacing(6)
            add_button = QPushButton("+ atoms")
            add_button.setToolTip(ADD_ATOMS_TOOLTIP)
            remove_button = QPushButton("- atoms")
            remove_button.setToolTip(REMOVE_ATOMS_TOOLTIP)
            recalc_button = QPushButton("Recalculate")
            recalc_button.setToolTip(RECALCULATE_TOOLTIP)
            pass_button = QPushButton("Pass to Jana2020")
            pass_button.setObjectName("primaryButton")
            for button in (add_button, remove_button, recalc_button, pass_button):
                button.setMinimumWidth(button.sizeHint().width())
            actions_layout.addStretch(1)
            if self._ordinary_dual_workflow:
                actions_layout.addWidget(threshold)
            for button in (add_button, remove_button, recalc_button, pass_button):
                actions_layout.addWidget(button)
            actions_layout.addStretch(1)
            actions.setVisible(False)
            add_button.clicked.connect(lambda _=False, r=role: self._adjust_panel_threshold(r, True))
            remove_button.clicked.connect(lambda _=False, r=role: self._adjust_panel_threshold(r, False))
            recalc_button.clicked.connect(lambda _=False, r=role: self.backend.autosolve_recalculate(r))
            pass_button.clicked.connect(lambda _=False, r=role: self._on_pass_panel(r))
            status = QLabel("")
            status.setObjectName("autosolveReviewStatus")
            status.setAlignment(Qt.AlignCenter)
            # One reserved line: showing/clearing the busy or seed text never
            # changes the review area's height, so no row or the structure
            # canvas above ever jumps.
            status.setMinimumHeight(status.fontMetrics().lineSpacing())
            warning = QLabel("")
            warning.setObjectName("autosolveReviewWarning")
            warning.setWordWrap(True)
            warning.setAlignment(Qt.AlignCenter)
            warning.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            warning.setVisible(False)
            for widget in (navigation, formula, detail, threshold, actions, status, warning):
                if self._ordinary_dual_workflow and widget in (detail, threshold):
                    detail.setVisible(False)
                    continue
                layout.addWidget(widget)
            if self._ordinary_dual_workflow:
                formula.setMinimumHeight(formula.fontMetrics().lineSpacing())
                warning.setVisible(False)
            # Top-aligned, so both panels' composition, origin and actions sit
            # on the same rows even when only one carries a warning.
            layout.addStretch(1)
            self.review_columns[role] = dict(
                column=column, formula=formula, detail=detail, threshold=threshold, actions=actions,
                add=add_button, remove=remove_button, recalc=recalc_button, pass_=pass_button,
                fullscreen=fullscreen_button, cycle_combo=cycle_combo,
                fit=panel_fit,
                previous=previous if self._ordinary_dual_workflow else None,
                following=following if self._ordinary_dual_workflow else None,
                status=status, warning=warning,
            )
            self.formula_row.addWidget(column, 1)
        self.formula_labels: List[QLabel] = [self.review_columns[r]["formula"] for r in (guided.ROLE_OBSERVED, guided.ROLE_PREDICTED)]
        self.edma_threshold_labels: List[QLabel] = [self.review_columns[r]["threshold"] for r in (guided.ROLE_OBSERVED, guided.ROLE_PREDICTED)]
        return self.formula_row_widget

    def _build_correction_row(self) -> QWidget:
        """The existing automatic measured-data corrections, shown only when
        the established eligibility logic says they apply, and only in
        Review. They never run until the user asks."""
        self.correction_row_widget = QWidget()
        layout = QHBoxLayout(self.correction_row_widget)
        layout.setContentsMargins(SECTION_GUTTER, 0, SECTION_GUTTER, SECTION_VPAD)
        layout.setSpacing(8)
        label = QLabel("Measured data:")
        label.setObjectName("autosolveReviewDetail")
        layout.addStretch(1)
        layout.addWidget(label)
        self.correction_buttons: dict = {}
        for kind in (guided.CORRECTION_POWDER, guided.CORRECTION_INTENSITY):
            button = QPushButton(guided.CORRECTION_LABELS[kind])
            button.setToolTip(
                "Run the existing automatic Map Feedback correction on the measured reflection data "
                "from the next cycle, continue the phase search on the corrected data, and generate "
                "a new Structure prediction. The modified data are recorded in the provenance."
            )
            button.clicked.connect(lambda _=False, k=kind: self._on_correction(k))
            button.setVisible(False)
            layout.addWidget(button)
            self.correction_buttons[kind] = button
        layout.addStretch(1)
        self.correction_row_widget.setVisible(False)
        return self.correction_row_widget

    def _on_pass_panel(self, role: str) -> None:
        column = self.review_columns[role]
        column["pass_"].setEnabled(False)
        if not self.backend.autosolve_pass_panel(role):
            column["pass_"].setEnabled(True)

    def _adjust_panel_threshold(self, role: str, add_atoms: bool) -> None:
        if not self._ordinary_dual_workflow:
            self.backend.autosolve_adjust_threshold(role, add_atoms)
            return
        panel = self._last_panels.get(role)
        if panel is None:
            return
        candidate = next(
            (item for item in self._cycle_candidates(role) if int(item.cycle) == int(panel.cycle)),
            None,
        )
        if candidate is None:
            return

        error_key = self.backend._review_candidate_key(candidate)

        def completed(updated, report, _request) -> None:
            if report is not None:
                self._panel_retune_errors[error_key] = "EDMA threshold update failed. Previous completed structure retained."
                self._refresh_tick()
                return
            if updated is not None:
                self._panel_retune_errors.pop(error_key, None)
                self._render_signature = None
                self._refresh_tick()

        request = self.backend.request_result_candidate_retune(candidate, add_atoms, completed)
        if request is not None:
            self._panel_retune_errors.pop(error_key, None)
            self.review_columns[role]["status"].setText(
                f"EDMA {guided.format_sigma(request.threshold)} · updating… "
                f"Current handoff: EDMA {guided.format_sigma(candidate.edma_sigma)}"
            )

    def _sync_review_controls(self) -> None:
        """Initial tuning: Structure prediction + atoms / - atoms / Refine 3
        cycles only; Charge-flipping solution read-only; nothing can be passed. Final
        Review: both panels, + atoms / - atoms / Recalculate / Pass. One EDMA
        at a time: while any panel recalculates, every panel action waits
        (one consistent busy state)."""
        backend = self.backend
        stage = getattr(backend, "_autosolve_stage", guided.STAGE_SEARCH)
        run_status = str(getattr(backend, "_run_status", "")).upper()
        waiting = stage in guided.REVIEW_STAGES and run_status == "REVIEW"
        final = waiting and stage == guided.STAGE_REVIEW
        any_busy = backend.autosolve_review_busy() if waiting else False
        handing_off = str(getattr(backend, "autosolve_handoff_state", "idle")) == "handing_off"
        is_jana = backend.autosolve_is_jana()
        refinement = getattr(backend, "autosolve_refinement", None) or {}
        refining = stage == guided.STAGE_REFINEMENT and run_status == "RUNNING"
        for role, column in self.review_columns.items():
            panel = self._last_panels.get(role)
            review_candidate = None
            review_busy = False
            requested_sigma = None
            if self._ordinary_dual_workflow and panel is not None:
                review_candidate = next(
                    (item for item in self._cycle_candidates(role) if int(item.cycle) == int(panel.cycle)),
                    None,
                )
                if review_candidate is not None:
                    review_key = backend._review_candidate_key(review_candidate)
                    review_busy = backend.review_edma_executor.is_busy(review_key)
                    requested_sigma = backend.review_edma_executor.requested_threshold(
                        review_key, float(review_candidate.edma_sigma),
                    )
            has_structure = panel is not None and Path(panel.current_cif).is_file()
            column["fullscreen"].setEnabled(has_structure)
            column["fit"].setEnabled(has_structure)
            combo = column.get("cycle_combo")
            if combo is not None:
                combo.setEnabled(bool(self._cycle_candidates(role)))
                index = combo.currentIndex()
                column["previous"].setEnabled(combo.count() > 2 and (index == 0 or index > 1))
                column["following"].setEnabled(0 < index < combo.count()-1)
            tunable = (
                panel is not None and (
                    (waiting and backend.autosolve_panel_tunable(role))
                    or self._ordinary_dual_workflow
                )
            )
            column["actions"].setVisible(tunable or self._ordinary_dual_workflow)
            column["pass_"].setVisible(final)
            column["recalc"].setVisible(not self._ordinary_dual_workflow)
            recalc_text = guided.RECALCULATE_LABEL if final else guided.REFINE_LABEL
            if column["recalc"].text() != recalc_text:
                column["recalc"].setText(recalc_text)
                column["recalc"].setMinimumWidth(column["recalc"].sizeHint().width())
            column["recalc"].setToolTip(RECALCULATE_TOOLTIP if final else REFINE_TOOLTIP)
            pass_text = "Pass to Jana2020" if is_jana else "Save map and model"
            if column["pass_"].text() != pass_text:
                column["pass_"].setText(pass_text)
                column["pass_"].setMinimumWidth(column["pass_"].sizeHint().width())
            column["pass_"].setToolTip(PASS_PANEL_TOOLTIP if is_jana else SAVE_PANEL_TOOLTIP)
            status = ""
            if panel is None:
                for key in ("add", "remove", "recalc", "pass_"):
                    column[key].setEnabled(False)
                column["detail"].setText("")
                column["threshold"].setText("")
                column["threshold"].setVisible(False)
            else:
                idle = tunable and not any_busy and not handing_off
                control_sigma = requested_sigma if requested_sigma is not None else panel.threshold_sigma
                column["add"].setEnabled(idle and guided.can_add_atoms(control_sigma))
                column["remove"].setEnabled(idle and guided.can_remove_atoms(control_sigma))
                column["recalc"].setEnabled(idle)
                column["pass_"].setEnabled(idle and final)
                count = self._panel_atom_counts.get(role)
                source = "Superflip" if role == guided.ROLE_OBSERVED else "SharpED"
                model = f" · {panel.sharped_model}" if panel.sharped_model else ""
                column["detail"].setText(f"{source} · Cycle {panel.cycle}{model}")
                provenance = getattr(panel, "reflection_input_provenance", "")
                initialization = getattr(panel, "superflip_initialization", "")
                column["detail"].setToolTip(" · ".join(
                    item for item in (provenance, initialization) if item
                ))
                threshold_text = f"EDMA {guided.format_sigma(panel.threshold_sigma)}"
                if count is not None:
                    threshold_text += f" · {count:,} {'sites' if self._ordinary_dual_workflow else 'EDMA sites'}"
                column["threshold"].setText(threshold_text)
                column["threshold"].setVisible(True)
                if review_busy and requested_sigma is not None and review_candidate is not None:
                    status = (
                        f"EDMA {guided.format_sigma(requested_sigma)} · updating… "
                        f"Current handoff: EDMA {guided.format_sigma(review_candidate.edma_sigma)}"
                    )
                elif panel.busy:
                    status = f"Recalculating structure at {guided.format_sigma(panel.busy_sigma)}…"
                elif panel.error:
                    status = panel.error
                elif self._ordinary_dual_workflow:
                    status = self._panel_retune_errors.get(backend._review_candidate_key(review_candidate), "") if review_candidate is not None else ""
            # Only while this role is STILL showing the seed itself (the
            # panel caption then reads "Seed · Cycle N" too) -- once a new
            # completed candidate from the block supersedes it, the caption
            # switches back to "Best · Cycle N" and this line must not keep
            # claiming the panel is still the seed.
            if refining and refinement.get("seed_note") and backend.autosolve_panel_shows_refinement_seed(role):
                status = f"Refinement seed: Cycle {refinement.get('cycle')} · EDMA {guided.format_sigma(refinement.get('threshold_sigma'))}"
            column["status"].setText(status)
            warning = backend.autosolve_warning_text(role) if panel is not None else None
            column["warning"].setText(warning or "")
            column["warning"].setToolTip(warning or "")
            column["warning"].setVisible(bool(warning) and not self._ordinary_dual_workflow)
        if self._ordinary_dual_workflow:
            self.validation_note.setVisible(True)
        plan = None
        if final:
            plan, _detail = backend.autosolve_correction_plan()
        for kind, button in self.correction_buttons.items():
            button.setVisible(plan == kind)
            # Busy/handoff disable it; hiding it would resize the review
            # area and move every row above.
            button.setEnabled(plan == kind and not any_busy and not handing_off)
        self.correction_row_widget.setVisible(plan is not None)

    def _build_action_row(self) -> QWidget:
        footer = QWidget()
        footer.setObjectName("wizardFooter")
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(SECTION_GUTTER, 6, SECTION_GUTTER, 8)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setToolTip(CANCEL_TOOLTIP)
        self.retry_button = QPushButton("Retry")
        self.retry_button.setToolTip(RETRY_TOOLTIP)
        self.retry_button.setVisible(False)
        self.pass_now_button = QPushButton("Pass to Jana2020")
        self.pass_now_button.setObjectName("primaryButton")
        self.pass_now_button.setToolTip(
            "Stop unfinished work safely and open Result Selection using completed results only."
        )
        self.pass_now_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._on_cancel)
        self.retry_button.clicked.connect(lambda: self.backend.autosolve_retry())
        self.pass_now_button.clicked.connect(self._on_pass_now)
        layout.addStretch(1)
        layout.addWidget(self.retry_button)
        layout.addWidget(self.pass_now_button)
        layout.addWidget(self.cancel_button)
        return footer

    # ----- Actions -----

    def _completed_handoff_candidates(self, *, verify=False):
        active = str(getattr(self.backend, '_active_run_id', '') or '')
        candidates = [c for c in self.backend._result_candidates()
                      if (not active or c.run_id == active)
                      and c.usable_map and (not c.edma_enabled or c.usable_structure)]
        if verify:
            from phase_studio.result_selection import candidate_selection
            candidates = [c for c in candidates if candidate_selection(c,jana=self.backend.autosolve_is_jana()).ready]
        return candidates

    def _on_pass_now(self) -> None:
        """Early handoff stops unfinished jobs only after explicit confirmation."""
        candidates = self._completed_handoff_candidates(verify=True)
        if not candidates:
            return
        if any(self.backend.review_edma_executor.is_busy(self.backend._review_candidate_key(c)) for c in candidates):
            return
        if str(getattr(self.backend, "_run_status", "")).upper() == "RUNNING":
            descriptions = []
            for role in (guided.ROLE_OBSERVED, guided.ROLE_PREDICTED):
                panel = self._last_panels.get(role)
                eligible = [c for c in candidates if c.source == guided.ROLE_SOURCE[role]]
                selected = next((c for c in eligible if panel is not None and c.cycle == panel.cycle
                                 and c.edma_sigma == panel.threshold_sigma), None)
                selected = selected or max(eligible, key=lambda c: c.cycle, default=None)
                if selected is not None:
                    threshold = (f"EDMA {guided.format_sigma(selected.edma_sigma)}"
                                 if selected.edma_sigma is not None else "Map-only result")
                    descriptions.append(
                        f"{guided.ROLE_TITLE[role]} · completed Cycle {selected.cycle} · {threshold}"
                    )
            box = QMessageBox(self)
            destination = "Jana2020" if self.backend.autosolve_is_jana() else "file export"
            box.setWindowTitle(f"Choose a completed result for {destination}")
            box.setIcon(QMessageBox.Question)
            box.setText("The workflow is still running. Stop the remaining calculations and "
                        f"open Result Selection to choose a completed result for {destination}?")
            box.setInformativeText("\n".join(descriptions) +
                                   "\nOnly completed results are eligible. The result and threshold "
                                   "you choose in Result Selection determine the handoff.")
            cancel = box.addButton("Keep running", QMessageBox.RejectRole)
            accept = box.addButton("Stop and choose result", QMessageBox.AcceptRole)
            box.setDefaultButton(cancel)
            self._last_early_handoff_dialog = box
            box.exec()
            if box.clickedButton() is not accept:
                return
        self.backend.request_autosolve_pass_now()

    def _on_cancel(self) -> None:
        self.backend.autosolve_cancel()

    def _on_correction(self, kind: str) -> None:
        """Measured-data correction: explicit confirmation first; nothing is
        modified unless the user confirms."""
        if self._confirm_correction(kind):
            self.backend.autosolve_request_correction(kind)

    def _confirm_correction(self, kind: str) -> bool:
        title, text, accept_text = CORRECTION_CONFIRMATION[kind]
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(title)
        box.setText(text)
        cancel = box.addButton("Cancel", QMessageBox.RejectRole)
        accept = box.addButton(accept_text, QMessageBox.AcceptRole)
        box.setDefaultButton(cancel)
        self._last_correction_dialog = box
        box.exec()
        return box.clickedButton() is accept

    def _set_status_secondary(self, text: str) -> None:
        """Kept for compatibility: the secondary line is the input line."""
        self._refresh_input_label()

    def _active_inflip_path(self) -> Optional[Path]:
        """The CURRENT job's .inflip: the backend's captured RunConfig once a
        run has started, otherwise the path this window was launched with."""
        cfg = getattr(self.backend, "last_run_config", None)
        captured = getattr(cfg, "jana_inflip", None) if cfg is not None else None
        if captured:
            return Path(captured)
        return self._launch_inflip_path

    def _refresh_input_label(self) -> None:
        path = self._active_inflip_path()
        if path is None:
            self.status_secondary.setVisible(False)
            self.status_secondary.setToolTip("")
            return
        prefix = "Jana2020 input: "
        metrics = self.status_secondary.fontMetrics()
        available = max(40, self.status_secondary.width() - metrics.horizontalAdvance(prefix) - 4)
        name = path.name
        if metrics.horizontalAdvance(name) > available:
            # Middle elision keeps the job's start and the ".inflip" suffix.
            name = metrics.elidedText(name, Qt.ElideMiddle, available)
        text = prefix + name
        if self.status_secondary.text() != text:
            self.status_secondary.setText(text)
        self.status_secondary.setToolTip(str(path))
        self.status_secondary.setVisible(True)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._refresh_input_label()
        self._refresh_legend_text()

    # ----- Execution Log: whole rows only -----

    def _log_line_pitch(self) -> float:
        """Height of one log row exactly as the document lays it out (the
        backend formats every block at 112% proportional line height), from
        the real document layout when rows exist."""
        log = self.backend.log_text
        document = log.document()
        layout = document.documentLayout()
        # Row pitch = distance between consecutive block tops. (A block's own
        # bounding rect excludes the proportional line-height spacing, so its
        # height alone understates the real pitch.)
        tops = []
        block = document.firstBlock()
        while block.isValid() and len(tops) < 33:
            tops.append(layout.blockBoundingRect(block).top())
            block = block.next()
        if len(tops) >= 2:
            return float(np.median(np.diff(tops)))
        from PySide6.QtGui import QFontMetricsF

        return QFontMetricsF(log.font()).height() * 1.12

    def _update_log_following(self) -> None:
        bar = self.backend.log_text.verticalScrollBar()
        self._log_following = bar.maximum() - bar.value() <= 2

    def _keep_log_at_bottom(self) -> None:
        if getattr(self, "_log_following", True):
            bar = self.backend.log_text.verticalScrollBar()
            if bar.value() != bar.maximum():
                bar.setValue(bar.maximum())

    def _log_visible_lines(self) -> int:
        screen = self.screen() or QGuiApplication.primaryScreen()
        height = screen.availableGeometry().height() if screen is not None else 1000
        return int(max(LOG_MIN_VISIBLE_LINES, min(LOG_MAX_VISIBLE_LINES, round(height / LOG_SCREEN_HEIGHT_PER_LINE))))

    def _fit_log_height(self) -> None:
        """Size the log so its viewport is exactly N rows plus the document's
        bottom margin. Auto-scrolled to the newest row, the viewport's top
        edge then lands exactly on a row boundary -- a row is either fully
        visible or not visible at all, never cut in half -- and the log stays
        compact (3-6 rows, secondary to the structures). Re-run whenever the
        horizontal scrollbar appears or disappears."""
        log = self.backend.log_text
        log.ensurePolished()
        pitch = self._log_line_pitch()
        rows = 12 if getattr(self, "_log_expanded", False) else self._log_visible_lines()
        viewport_target = int(round(rows * pitch + log.document().documentMargin()))
        chrome = log.height() - log.viewport().height()
        if chrome <= 0 or not log.isVisible():
            margins = log.contentsMargins()
            chrome = margins.top() + margins.bottom() + 2 * log.frameWidth()
            if log.horizontalScrollBar().isVisible():
                chrome += log.horizontalScrollBar().sizeHint().height()
        if log.height() != viewport_target + chrome or log.minimumHeight() != log.maximumHeight():
            log.setFixedHeight(viewport_target + chrome)
        self._log_visible_rows = rows
        self._keep_log_at_bottom()

    def _on_auto_rotate_toggled(self, checked: bool) -> None:
        self._auto_rotate_enabled = checked
        self.auto_rotate_button.setText("Auto rotate: On" if checked else "Auto rotate: Off")

    def _set_view_mode(self, mode: str) -> None:
        """One shared mode for every panel; switching mode re-fits extent (a
        tightly-fit molecule fragment and the full cell have very different
        sizes) but keeps the current rotation -- it never resets to a random
        viewpoint."""
        if mode == self.view_mode:
            return
        self.view_mode = mode
        self._mark_interaction()
        self._view_zoom = 1.0
        self._view_pan = np.zeros(3, dtype=np.float64)
        self._render_structures(self._last_panels[guided.ROLE_OBSERVED], self._last_panels[guided.ROLE_PREDICTED])

    def showEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().showEvent(event)
        # The log's frame/chrome height is only exact once it is really
        # shown; the pre-show fit uses an estimate, which left the top row
        # partly cut. Refit after this show has been laid out.
        QTimer.singleShot(0, self._fit_log_height)
        # Initial keyboard focus on the structure view (the primary content),
        # not on whichever toolbar button happens to come first.
        QTimer.singleShot(0, lambda: self.structure_canvas.setFocus(Qt.OtherFocusReason))
        if not getattr(self, '_updates_attached', False):
            self._updates_attached = True
            from phase_studio.update_ui import update_service
            jana = bool(self._launch_inflip_path) or self.backend.autosolve_is_jana()
            update_service().attach(self, mode='jana' if jana else None)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        try:
            self.backend.request_immediate_stop()
        except Exception:
            pass
        super().closeEvent(event)

    # ----- Camera: shared orientation, independent per-panel fit/pan/zoom -----

    def _fit_execution_axis(self, axis) -> None:
        points = [artist.atom_coordinates for artist in self._structure_depth_artists
                  if artist.scatter.axes is axis]
        if self.view_mode == "cell":
            points += [artist.cell_corners for artist in self._structure_depth_artists
                       if artist.scatter.axes is axis]
        if SHOW_SECONDARY_PEAKS_IN_MOLECULE_VIEW:
            points += [artist.atom_coordinates for artist in self._secondary_depth_artists
                       if artist.scatter.axes is axis]
        if points:
            fit_projected_structure(axis, np.vstack(points))

    def _fit_panel(self, role: str) -> None:
        for axis, axis_role in self._axis_roles.items():
            if axis_role == role and axis in self._structure_interactive_axes:
                self._mark_interaction()
                self._manual_camera_roles.add(role)
                self._pending_fit_roles.discard(role)
                self._fit_execution_axis(axis)
        self.structure_canvas.draw_idle()

    def _on_structure_resize(self, _event) -> None:
        self._layout_structure_panels()
        if self._ordinary_dual_workflow:
            for axis in self._structure_interactive_axes:
                set_structure_viewport_clip(axis)
            self._pending_fit_roles.update(set(self._axis_roles.values()) - self._manual_camera_roles)
            # Only geometry still awaiting its initial fit may be reframed.
            # Existing camera views survive ordinary resize/docking updates.
            self._structure_fit_timer.start()

    def _fit_active_structure_view(self) -> None:
        axis = self._camera.active_axis
        if self._ordinary_dual_workflow and axis in self._structure_interactive_axes:
            self._mark_interaction()
            self._fit_execution_axis(axis)
            self.structure_canvas.draw_idle()
        else:
            self._fit_structure_view()

    def _reset_active_structure_view(self) -> None:
        axis = self._camera.active_axis
        if self._ordinary_dual_workflow and axis in self._structure_interactive_axes:
            axis.view_init(elev=20, azim=35)
            self._fit_active_structure_view()
            self._update_structure_depth_cue(20, 35)
        else:
            self._reset_structure_view()

    def _fit_axis(self, axis, center: np.ndarray, radius: float, fill: float) -> None:
        """Frame `axis` on the bounding sphere (center, radius) of what it
        displays: cubic limits around the sphere, equal box aspect, and a box
        zoom chosen so the sphere's diameter spans `fill` of the panel's
        drawing square at every rotation. Derived entirely from the content;
        no fixed zoom factor."""
        radius = max(float(radius), MIN_FIT_RADIUS_ANGSTROM)
        axis.set_box_aspect((1.0, 1.0, 1.0), zoom=float(fill) / _unit_zoom_sphere_fill())
        self._axis_fits[axis] = (np.asarray(center, dtype=np.float64), radius)
        self._apply_axis_camera(axis)

    def _camera_limits(self, axis) -> Optional[Tuple[Tuple[float, float], ...]]:
        fit = self._axis_fits.get(axis)
        if fit is None:
            return None
        center, radius = fit
        focus = center + self._view_pan * radius
        half = radius * self._view_zoom
        return tuple((float(focus[i] - half), float(focus[i] + half)) for i in range(3))

    def _fit_limits(self, axis) -> Optional[Tuple[Tuple[float, float], ...]]:
        fit = self._axis_fits.get(axis)
        if fit is None:
            return None
        center, radius = fit
        return tuple((float(center[i] - radius), float(center[i] + radius)) for i in range(3))

    def _apply_axis_camera(self, axis) -> None:
        limits = self._camera_limits(axis)
        if limits is not None:
            self._apply_structure_axis_limits(axis, limits)

    def _apply_camera_to_all(self) -> None:
        for axis in self._structure_interactive_axes:
            self._apply_axis_camera(axis)
        first = self._structure_interactive_axes[0] if self._structure_interactive_axes else None
        self.structure_view_base_limits = self._fit_limits(first) if first is not None else None
        self.structure_view_limits = self._camera_limits(first) if first is not None else None

    def _apply_structure_view(self, source_ax, *, redraw: bool = True) -> None:
        """Mirror orientation while leaving every panel's limits local."""
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

    # ----- Mouse controls: left-drag rotate (borrowed), right-drag pan,
    # wheel zoom, double-click reset. Orientation is synchronized; limits are local. -----

    def _camera_orientation_changed(self, elev: float, azim: float, _source_axis) -> None:
        if self._ordinary_dual_workflow:
            _source_axis.view_init(elev=elev, azim=azim)
            self._update_structure_depth_cue(elev, azim)
            return
        self.structure_elev, self.structure_azim = float(elev), float(azim)
        for axis in self._structure_interactive_axes:
            axis.view_init(elev=elev, azim=azim)
        self._update_structure_depth_cue(elev, azim)

    def _camera_interaction(self, kind: str) -> None:
        self._mark_interaction()
        if self._ordinary_dual_workflow and kind in {"rotate", "pan", "zoom", "fit"}:
            role = self._axis_roles.get(self._camera.active_axis)
            if role is not None:
                self._manual_camera_roles.add(role)
                self._pending_fit_roles.discard(role)
        if (kind == "rotate" or self._ordinary_dual_workflow and kind in {"pan", "zoom"}) and self.auto_rotate_button.isChecked():
            self.auto_rotate_button.setChecked(False)

    def _on_canvas_button_press(self, event) -> None:
        if getattr(event, "dblclick", False):
            self._fit_structure_view()
            return
        self._mark_interaction()
        self._begin_structure_view_drag(event)

    def _on_canvas_button_release(self, event) -> None:
        self._finish_structure_view_drag(event)
        self._mark_interaction()

    def _on_structure_scroll(self, event) -> None:
        axis = getattr(event, "inaxes", None)
        if axis is None or axis not in self._structure_interactive_axes:
            return
        self._mark_interaction()
        factor = 0.9 if getattr(event, "button", "up") == "up" else (1.0 / 0.9)
        limits = []
        for low, high in (axis.get_xlim3d(), axis.get_ylim3d(), axis.get_zlim3d()):
            center = (float(low) + float(high)) / 2.0
            half = (float(high) - float(low)) * factor / 2.0
            limits.append((center - half, center + half))
        self._apply_structure_axis_limits(axis, tuple(limits))
        self.structure_canvas.draw_idle()

    def _mark_interaction(self) -> None:
        self._last_interaction_time = time.monotonic()

    def _fit_structure_view(self) -> None:
        """Fit to the displayed content -- zoom/pan reset, rotation kept."""
        self._mark_interaction()
        if self._ordinary_dual_workflow:
            self._manual_camera_roles.update(self._axis_roles.values())
            self._pending_fit_roles.clear()
            for axis in self._structure_interactive_axes:
                self._fit_execution_axis(axis)
            self.structure_canvas.draw_idle()
            return
        self._view_zoom = 1.0
        self._view_pan = np.zeros(3, dtype=np.float64)
        self._apply_camera_to_all()
        self.structure_canvas.draw_idle()

    def _apply_automatic_structure_fit(self) -> None:
        """Apply an already-authorized fit after Qt settles canvas geometry."""
        if self._ordinary_dual_workflow:
            if self.structure_canvas.width() <= 1 or self.structure_canvas.height() <= 1:
                return
            for axis, role in self._axis_roles.items():
                if role in self._pending_fit_roles:
                    self._fit_execution_axis(axis)
            self._pending_fit_roles.clear()
            self.structure_canvas.draw_idle()
            return
        self._apply_camera_to_all()
        self.structure_canvas.draw_idle()

    def _reset_structure_view(self) -> None:
        """Full reset: rotation, zoom and pan back to the default view."""
        self._mark_interaction()
        self.structure_elev = 20.0
        self.structure_azim = 35.0
        for axis in self.structure_axes:
            axis.view_init(elev=self.structure_elev, azim=self.structure_azim)
        if self._ordinary_dual_workflow:
            self._fit_structure_view()
            self._update_structure_depth_cue(self.structure_elev, self.structure_azim)
            return
        self._view_zoom = 1.0
        self._view_pan = np.zeros(3, dtype=np.float64)
        self._apply_camera_to_all()
        self._update_structure_depth_cue(self.structure_elev, self.structure_azim)
        self.structure_canvas.draw_idle()

    # ----- Depth cue: atoms via the borrowed per-artist updater, bonds via
    # the bond-specific one below (both driven by the same elev/azim). -----

    def _update_structure_depth_cue(self, elev: float, azim: float) -> None:
        for artists in self._structure_depth_artists:
            axis = artists.scatter.axes
            self._update_structure_depth_artist(artists, axis.elev if axis is not None else elev,
                                                axis.azim if axis is not None else azim)
        for artists in self._secondary_depth_artists:
            self._update_structure_depth_artist(artists, elev, azim)
        for bond in self._bond_artists:
            axis = bond.collection.axes
            fade = structure_depth_fade(
                bond.midpoints, bond.midpoints, axis.elev if axis is not None else elev,
                axis.azim if axis is not None else azim,
                front_hold=0.20, gamma=1.20, maximum=0.55,
            )
            base = np.asarray([0.365, 0.420, 0.525])
            colors = blend_structure_colors(base, fade)
            bond.collection.set_color(np.column_stack((colors, np.ones(len(colors)))))

    # ----- Live status / structure refresh -----

    def _auto_rotate_tick(self) -> None:
        if not self._auto_rotate_enabled:
            return
        if self._structure_view_drag_source is not None or self._camera._drag is not None:
            return
        if time.monotonic() - self._last_interaction_time < AUTO_ROTATE_RESUME_DELAY_SECONDS:
            return
        if not self.structure_axes:
            return
        self.structure_azim = (self.structure_azim + AUTO_ROTATE_DEGREES_PER_TICK) % 360.0
        for axis in self.structure_axes:
            axis.view_init(elev=axis.elev if self._ordinary_dual_workflow else self.structure_elev,
                           azim=(axis.azim + AUTO_ROTATE_DEGREES_PER_TICK) % 360 if self._ordinary_dual_workflow else self.structure_azim)
        self._update_structure_depth_cue(self.structure_elev, self.structure_azim)
        self.structure_canvas.draw_idle()

    def _refresh_tick(self) -> None:
        backend = self.backend
        self._sync_cycle_browsers()
        if str(getattr(backend, "_run_status", "")).upper() == "ERROR" and not self._log_expanded:
            self._toggle_log_expanded()

        candidates = backend._result_candidates()
        candidates_available = bool(self._completed_handoff_candidates())
        interactive_pending = any(backend.review_edma_executor.is_busy(backend._review_candidate_key(candidate))
                                  for candidate in candidates)
        handing_off_now = str(getattr(backend, "autosolve_handoff_state", "idle")) in {
            "stopping", "selecting", "handing_off",
        }
        self.pass_now_button.setText(
            "Pass to Jana2020" if backend.autosolve_is_jana() else "Save map and model"
        )
        self.pass_now_button.setEnabled(candidates_available and not handing_off_now and not interactive_pending)

        handoff_state = str(getattr(backend, "autosolve_handoff_state", "idle"))
        busy_headline = HANDOFF_STATE_HEADLINES.get(handoff_state)
        if busy_headline is not None:
            # The run is ending or a result is being chosen: explicit
            # end-point feedback replaces the cycle/stage text.
            self.status_headline.setText(busy_headline)
            self._sync_review_controls()
            return
        declined = handoff_state == "declined"

        stage = getattr(backend, "_autosolve_stage", guided.STAGE_SEARCH)
        # ONE authoritative cycle/stage source: backend._cycle_progress_state,
        # the exact same CycleProgressState object _apply_cycle_progress_state
        # uses to drive the bottom cycle/stage row, so the two can never
        # disagree. None means no real cycle/stage event has arrived yet: no
        # cycle number is shown at all (never an internal zero-based count).
        progress_state = getattr(backend, "_cycle_progress_state", None)
        waiting = stage in guided.REVIEW_STAGES
        if progress_state is None:
            cycle_stage_text = self._preparing_text
            # Only before the first cycle event: Review states own the
            # progress row themselves ("Review" / the EDMA-only activity).
            preparing_detail = (
                "Validating input and preparing Superflip files…"
                if self._ordinary_dual_workflow else self._preparing_text
            )
            if not waiting and stage != guided.STAGE_PREDICTING and backend.current_cycle_detail.text() != preparing_detail:
                backend.current_cycle_detail.setText(preparing_detail)
                backend.current_cycle_stage_counter.setText("")
        else:
            cycle_stage_text = progress_state.display_text()
        run_status = str(getattr(backend, "_run_status", "")).upper()
        running = run_status == "RUNNING"
        if stage == guided.STAGE_PREDICTING:
            cycle_stage_text = "Generating predicted structure…"
        elif stage == guided.STAGE_PREDICTION_FAILED and run_status != "CANCELLED":
            cycle_stage_text = "Structure prediction failed · Retry generates only the prediction"
        elif waiting and run_status == "REVIEW":
            base = "Predicted-model tuning" if stage == guided.STAGE_TUNING else "Final Review"
            activity = str(getattr(backend, "autosolve_activity", "") or "")
            cycle_stage_text = base + (f" · {activity}…" if activity else "")
        elif stage == guided.STAGE_REFINEMENT and running:
            in_block = backend.autosolve_refinement_cycle_in_block()
            if in_block is not None:
                index, total, block = in_block
                prefix = f"Refinement cycle {index} of {total}"
                if block > 1:
                    prefix += f" · block {block} (the solution improved)"
                cycle_stage_text = f"{prefix} · {cycle_stage_text}"
        elif stage == guided.STAGE_CORRECTION and running:
            cycle_stage_text = f"Data correction · {cycle_stage_text}"
        if declined and not running:
            cycle_stage_text = "Stopped · no result passed to Jana2020"
        if self._ordinary_dual_workflow:
            operations = backend.active_workflow_operations()
            cycle_text = (
                f"Cycle {progress_state.cycle_index} of {progress_state.cycle_total}"
                if progress_state is not None else self._preparing_text
            )
            cycle_stage_text = (f"{cycle_text} · {run_status.title() or 'Preparing'}"
                                if progress_state is not None else self._preparing_text)
            if progress_state is None and run_status in {"COMPLETE", "STOPPED", "CANCELLED", "ERROR"}:
                cycle_stage_text = run_status.title()
            if declined and not running:
                cycle_stage_text = "Stopped · no result passed to Jana2020"
            if running and backend.stop_now.is_set():
                cycle_stage_text = f"{cycle_text} · Stopping"
                backend.current_cycle_detail.setText("Stopping unfinished calculations…")
                backend.current_cycle_stage_counter.setText("Stop requested")
                backend.current_cycle_progress.setRange(0, 1)
                backend.current_cycle_progress.setValue(0)
                backend.superflip_repeat_group.setVisible(False)
            elif running:
                backend.current_cycle_detail.setText("\n".join(operations) if operations else
                    (progress_state.display_text() if progress_state is not None else preparing_detail))
                backend.current_cycle_stage_counter.setText("Active operations" if operations else "")
                if operations:
                    backend.current_cycle_progress.setRange(0, 0)
            else:
                backend.superflip_repeat_group.setVisible(False)
                backend.current_cycle_progress.setRange(0, 1)
                backend.current_cycle_progress.setValue(0)
        self.status_headline.setText(f"{self.workflow_name} · {cycle_stage_text}")
        # Item 25: the cycle-loop progress bars (Overall / stage) are
        # meaningless once the workflow is idle in Predicted-model tuning
        # or Final Review -- they just sit at their last completed value,
        # duplicating what the headline above already says ("Review").
        # Collapsed here rather than removed: the exact same widgets
        # backend's own progress calls keep updating, so nothing about the
        # cycle loop itself changes -- they simply reappear, already
        # correct, the moment a new block starts running.
        backend.run_status_panel.setVisible(not (waiting and run_status == "REVIEW"))
        self._refresh_input_label()

        failed = run_status == "ERROR" or (stage == guided.STAGE_PREDICTION_FAILED and run_status != "CANCELLED")
        self.retry_button.setVisible(failed)

        observed = self._display_panel(guided.ROLE_OBSERVED)
        predicted = self._display_panel(guided.ROLE_PREDICTED)
        # Reference atoms populate asynchronously, part-way through cycle 1,
        # independently of either recommendation -- its own arrival must
        # trigger a re-render too.
        reference_available = bool(self.backend.reference_atoms_for_plot)

        def key(panel):
            if panel is None:
                return None
            return (panel.cycle, str(panel.map_path), str(panel.current_cif), panel.threshold_sigma)

        progress_stage = str(getattr(progress_state, "stage_name", "") or "")
        signature = (
            key(observed), key(predicted), reference_available,
            stage == guided.STAGE_PREDICTING, progress_stage,
            (tuple(operations), run_status) if self._ordinary_dual_workflow else (),
        )
        if not self._rendered_once or signature != self._render_signature:
            self._rendered_once = True
            self._render_signature = signature
            self._last_reference_available = reference_available
            self._render_structures(observed, predicted)
            for detached in self._panel_detached_viewers.values():
                if detached is not None and detached.isVisible():
                    detached.render()
        self._sync_review_controls()

    def _atoms_for_candidate(self, candidate: Optional[ResultCandidate]) -> List[AtomSite]:
        if candidate is None or not candidate.usable_structure:
            return []
        return self.backend._safe_parse_structure(Path(candidate.structure_path))

    def _structure_path_for_candidate(self, candidate: Optional[ResultCandidate]) -> Optional[Path]:
        if candidate is None or not candidate.usable_structure:
            return None
        path = Path(candidate.structure_path)
        return path if path.is_file() else None

    def _reference_path(self) -> Optional[Path]:
        cfg = getattr(self.backend, "last_run_config", None)
        if cfg is None:
            return None
        path = getattr(cfg, "reference_cif", None)
        if path is None:
            return None
        path = Path(path)
        return path if path.is_file() else None

    def _plot_full_cell_panel(self, axis, atoms: Sequence[AtomSite], empty_text: str) -> bool:
        """Full-cell mode: the borrowed, UNMODIFIED _plot_structure_atoms
        (the same renderer the full Structure Comparison uses) draws atoms +
        unit-cell frame; markers are enlarged for legibility. NO bonds:
        connecting atoms across an entire already symmetry-expanded unit
        cell is exactly what produced the earlier all-to-all bug. Framed on
        the bounding sphere of the cell frame and every drawn atom, so the
        complete cell context always stays in view at any rotation."""
        metadata = self._plot_structure_atoms(axis, atoms, empty_text)
        self._configure_axes_controls(axis)
        if not metadata or not self._structure_depth_artists:
            return False
        artists = self._structure_depth_artists[-1]
        artists.atom_sizes = artists.atom_sizes * PRESENTATION_ATOM_SCALE
        artists.scatter.set_sizes(artists.atom_sizes)
        content = np.vstack((artists.cell_corners, artists.atom_coordinates))
        center, radius = _bounding_sphere(content)
        self._fit_axis(axis, center, radius, FULL_CELL_VIEW_FILL)
        return True

    def _plot_molecule_panel(self, axis, view: CompleteMoleculeView, empty_text: str) -> bool:
        """Complete-molecules mode: pre-computed Cartesian coordinates from
        build_complete_molecule_view(), which may legitimately sit outside
        the home unit cell (periodic-image atoms) -- the borrowed
        _plot_structure_atoms cannot be reused here because it re-wraps
        every frac into [0,1). No unit-cell wireframe: the view is framed
        tightly on the completed fragments (view.fit_center/fit_radius) and
        a global cell box would dominate it."""
        if len(view.atoms) == 0:
            axis.set_axis_off()
            axis.text2D(0.5, 0.50, empty_text, ha="center", va="center", fontsize=8, color="#5d6b86", transform=axis.transAxes)
            self._configure_axes_controls(axis)
            return False
        axis.set_axis_on()
        axis.axison = True
        axis.set_xticks([]); axis.set_yticks([]); axis.set_zticks([])
        axis.view_init(elev=self.structure_elev, azim=self.structure_azim)
        axis.set_proj_type("ortho")
        try:
            for pane_axis in (axis.xaxis, axis.yaxis, axis.zaxis):
                pane_axis.pane.set_facecolor("#ffffff")
                pane_axis.pane.set_edgecolor("#ffffff")
                pane_axis.pane.set_alpha(0.0)
                pane_axis.line.set_color("#ffffff")
                pane_axis._axinfo["grid"]["color"] = "#ffffff"
        except Exception:
            pass
        self._structure_interactive_axes.append(axis)
        self._fit_axis(axis, view.fit_center, view.fit_radius, MOLECULE_VIEW_FILL)
        self._configure_axes_controls(axis)
        # No unit-cell wireframe: an empty Line3DCollection keeps the shared
        # depth-cue updater (which re-colors artists.cell_collection every
        # redraw) working without drawing anything. Never added to the axes.
        def empty_cell() -> dict:
            return dict(
                cell_collection=Line3DCollection([], linewidths=0.0),
                cell_midpoints=np.zeros((0, 3), dtype=np.float64),
                cell_corners=np.zeros((8, 3), dtype=np.float64),
            )

        # Optional faint secondary layer: unassigned peaks that already fall
        # inside the fitted sphere. Drawn first (behind), smaller, blended
        # toward white; never part of the fit.
        if SHOW_SECONDARY_PEAKS_IN_MOLECULE_VIEW and len(view.secondary_atoms):
            secondary_colors = np.asarray([to_rgb(self._element_color(a.element)) for a in view.secondary_atoms], dtype=np.float64)
            secondary_colors = secondary_colors + (1.0 - secondary_colors) * SECONDARY_PEAK_WHITE_BLEND
            secondary_sizes = np.full(len(view.secondary_atoms), SECONDARY_PEAK_MARKER_SIZE, dtype=np.float64)
            secondary_scatter = axis.scatter(
                view.secondary_coords[:, 0], view.secondary_coords[:, 1], view.secondary_coords[:, 2],
                s=secondary_sizes, c=secondary_colors, alpha=1.0, linewidths=0.0, depthshade=False,
            )
            secondary_artists = StructureDepthArtists(
                scatter=secondary_scatter,
                atom_coordinates=view.secondary_coords,
                atom_base_colors=secondary_colors,
                atom_sizes=secondary_sizes,
                atom_draw_order=np.arange(len(view.secondary_coords), dtype=np.int64),
                **empty_cell(),
            )
            self._secondary_depth_artists.append(secondary_artists)
            self._update_structure_depth_artist(secondary_artists, self.structure_elev, self.structure_azim)

        coords = view.coords
        atom_base_colors = np.asarray([to_rgb(self._element_color(a.element)) for a in view.atoms], dtype=np.float64)
        sizes = structure_marker_sizes(len(view.atoms))
        scatter = axis.scatter(
            coords[:, 0], coords[:, 1], coords[:, 2], s=sizes, c=atom_base_colors,
            alpha=1.0, edgecolors="#ffffff", linewidths=0.3, depthshade=False,
        )
        depth_artists = StructureDepthArtists(
            scatter=scatter,
            atom_coordinates=coords,
            atom_base_colors=atom_base_colors,
            atom_sizes=sizes,
            atom_draw_order=np.arange(len(coords), dtype=np.int64),
            **empty_cell(),
        )
        self._structure_depth_artists.append(depth_artists)
        self._update_structure_depth_artist(depth_artists, self.structure_elev, self.structure_azim)

        if view.bonds:
            segments = np.asarray([[coords[i], coords[j]] for i, j in view.bonds])
            midpoints = segments.mean(axis=1)
            collection = Line3DCollection(segments, linewidths=BOND_LINEWIDTH)
            collection.set_color(BOND_COLOR)
            axis.add_collection3d(collection)
            self._bond_artists.append(_BondArtist(collection=collection, midpoints=midpoints))
        axis.set_axis_off()
        return True

    @staticmethod
    def _edma_threshold_provenance(path: Optional[Path]) -> Optional[dict]:
        """The Auto-threshold provenance written next to this EDMA CIF by
        IterativeSuperflipPipelineQtGUI._run_auto_threshold_edma_stage."""
        if path is None:
            return None
        provenance = Path(path).with_name(Path(path).name.replace("_edma.cif", "_edma_threshold.json"))
        if not provenance.is_file():
            return None
        try:
            return json.loads(provenance.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _edma_threshold_label(self, path: Optional[Path]) -> str:
        data = self._edma_threshold_provenance(path)
        return str(data.get("label", "")) if data else ""

    def _edma_threshold_tooltip(self, path: Optional[Path]) -> str:
        summary = structure_site_summary(path, prepare_structure_presentation(path, self.view_mode), self.view_mode) if path else ""
        data = self._edma_threshold_provenance(path)
        if not data:
            return summary
        lines = [
            summary,
            f"EDMA threshold mode: Auto · selected {float(data['selected_sigma']):.2f} σ",
            f"Candidates: {min(data['candidate_sigmas']):.2f}–{max(data['candidate_sigmas']):.2f} σ "
            f"({len(data['candidate_sigmas'])} evaluated)" if data.get("candidate_sigmas") else "",
            f"Criterion: {data.get('criterion', '')}",
        ]
        selected = next((c for c in data.get("candidates", []) if abs(float(c["sigma"]) - float(data["selected_sigma"])) < 1e-9), None)
        if selected and selected.get("r_all") is not None:
            lines.append(f"Model R_F {selected['r_all']:.3f} · CC_F {selected['cc_all']:.3f} · {selected['n_cell_atoms']} atoms/cell")
        if data.get("fallback_used"):
            lines.append(str(data.get("message", "")))
        return "\n".join(line for line in lines if line)

    def _configure_axes_controls(self, axis) -> None:
        try:
            axis.mouse_init(rotate_btn=1, pan_btn=3, zoom_btn=2)
        except Exception:
            pass

    def _layout_structure_panels(self) -> None:
        """Place each panel's two-line caption (source / "Best · Cycle N")
        at a fixed POINT distance from the top edge, and start the 3D axes
        just below it -- so the caption never collides with the structure
        and never drifts at a different window height or DPI scale."""
        figure = self.structure_figure
        height_pt = max(1.0, float(figure.get_figheight()) * 72.0)
        band_pt = (
            PANEL_CAPTION_TOP_PAD_PT + PANEL_TITLE_FONT_PT * 1.25 + PANEL_CAPTION_LINE_GAP_PT
            + PANEL_SUBTITLE_FONT_PT * 1.25 + PANEL_CAPTION_BOTTOM_PAD_PT
        )
        top = max(0.5, 1.0 - band_pt / height_pt)
        figure.subplots_adjust(left=0.005, right=0.995, bottom=0.005, top=top, wspace=0.02)

    def _panel_atoms(self, panel) -> List[AtomSite]:
        if panel is None or not Path(panel.current_cif).is_file():
            return []
        return self.backend._safe_parse_structure(Path(panel.current_cif))

    @staticmethod
    def _panel_path(panel) -> Optional[Path]:
        if panel is None:
            return None
        path = Path(panel.current_cif)
        return path if path.is_file() else None

    def _render_structures(self, observed_panel, predicted_panel) -> None:
        """Charge-flipping solution (left) and Structure prediction (right). Each panel
        shows exactly the structure its ReviewPanel names -- in Review the
        user-tuned threshold's structure, otherwise the best COMPLETED
        candidate's recorded structure."""
        previous_cameras = {
            role: (axis.elev, axis.azim, self._structure_axis_limits(axis),
                   getattr(axis, "_phase_fit_zoom", None))
            for axis, role in self._axis_roles.items() if axis in self._structure_interactive_axes
        } if self._ordinary_dual_workflow else {}
        self._last_panels = {guided.ROLE_OBSERVED: observed_panel, guided.ROLE_PREDICTED: predicted_panel}
        self._last_superflip_cycle = observed_panel.cycle if observed_panel is not None else None
        self._last_deblurred_cycle = predicted_panel.cycle if predicted_panel is not None else None

        reference_atoms = list(self.backend.reference_atoms_for_plot)
        superflip_atoms = self._panel_atoms(observed_panel)
        deblurred_atoms = self._panel_atoms(predicted_panel)
        self._panel_atom_counts = {
            role: len(parse_cif_atoms(path)) if path is not None else None
            for role, path in (
                (guided.ROLE_OBSERVED, self._panel_path(observed_panel)),
                (guided.ROLE_PREDICTED, self._panel_path(predicted_panel)),
            )
        }
        predicting = getattr(self.backend, "_autosolve_stage", "") == guided.STAGE_PREDICTING

        # Reference only appears when actually available; Superflip and
        # SharpED are always shown (each following its OWN recommendation,
        # which may point at different cycles). `path` is the raw on-disk
        # CIF -- Complete-molecules mode re-parses it (asymmetric unit +
        # cell/space group), independent of the symmetry-expanded `atoms`
        # list Full-cell mode uses.
        def best_caption(role: str, panel) -> str:
            if panel is None:
                return ""
            if self._ordinary_dual_workflow:
                source = "Superflip" if role == guided.ROLE_OBSERVED else "SharpED"
                model = (
                    f" · {panel.sharped_model}" if role == guided.ROLE_PREDICTED
                    and getattr(panel, "sharped_model", "") else ""
                )
                source_token = guided.ROLE_SOURCE[role]
                pending = [
                    update for (job_source, _cycle), update in self.backend._structure_jobs.items()
                    if job_source == source_token and update.status in {"queued", "running"}
                    and int(update.cycle) > int(panel.cycle)
                ]
                if pending:
                    next_cycle = max(int(update.cycle) for update in pending)
                    return f"{source} · Cycle {panel.cycle}{model} · Latest · Cycle {next_cycle} EDMA updating…"
                if role == guided.ROLE_OBSERVED:
                    initialization = getattr(panel, "superflip_initialization", "")
                    return f"{source} · Cycle {panel.cycle}" + (
                        f" · {initialization}" if initialization else ""
                    )
                return f"{source} · Cycle {panel.cycle}{model}"
            prefix = "Seed" if self.backend.autosolve_panel_shows_refinement_seed(role) else "Best"
            return f"{prefix} · Cycle {panel.cycle}"

        observed_title = (
            "Charge-flipping solution" if self._ordinary_dual_workflow
            else guided.ROLE_TITLE[guided.ROLE_OBSERVED]
        )
        predicted_title = (
            "Structure prediction" if self._ordinary_dual_workflow
            else guided.ROLE_TITLE[guided.ROLE_PREDICTED]
        )

        progress_state = getattr(self.backend, "_cycle_progress_state", None)
        stage_name = str(getattr(progress_state, "stage_name", "") or "").casefold()
        if "validation" in stage_name and ("superflip" in stage_name or "charge-flipping" in stage_name):
            observed_waiting = "Validation running…"
        elif "edma" in stage_name and (
            "superflip" in stage_name or "charge-flipping solution" in stage_name
        ):
            observed_waiting = "EDMA structure extraction running…"
        elif "superflip" in stage_name:
            observed_waiting = "Superflip running…"
        else:
            observed_waiting = "Preparing Superflip…"
        if "edma" in stage_name and (
            "deblur" in stage_name or "sharped" in stage_name or "model prediction" in stage_name
        ):
            predicted_waiting = "EDMA structure extraction running…"
        elif "sharped" in stage_name:
            predicted_waiting = "SharpED processing…"
        else:
            predicted_waiting = "Waiting for the Superflip map…"
        if self._ordinary_dual_workflow and self.backend._operation_states:
            live_names = {name for name, _cycle, status in self.backend._operation_states.values() if status == "running"}
            edma_sources = {job.source for job in self.backend._structure_jobs.values() if job.status in {"queued", "running"}}
            observed_waiting = ("Superflip running…" if "Superflip" in live_names else
                                "EDMA structure extraction running…" if "superflip" in edma_sources else
                                "Waiting for a completed Charge-flipping structure…")
            predicted_waiting = ("SharpED processing…" if "SharpED" in live_names else
                                 "EDMA structure extraction running…" if "deblurred" in edma_sources else
                                 "Waiting for the Superflip map…")
        if self.backend._run_status in {"CANCELLED", "STOPPED", "ERROR"}:
            observed_waiting = f"{self.backend._run_status.title()} · no completed Charge-flipping structure"
            predicted_waiting = f"{self.backend._run_status.title()} · no completed Structure prediction"

        superflip_best = best_caption(guided.ROLE_OBSERVED, observed_panel)
        deblurred_best = best_caption(guided.ROLE_PREDICTED, predicted_panel)
        panels: List[Tuple[str, Sequence[AtomSite], str, str, Optional[Path], str, Optional[int]]] = []
        if reference_atoms:
            panels.append((
                "Reference", reference_atoms, "Reference structure unavailable", "Input structure",
                self._reference_path(), "reference", None,
            ))
        panels.append((
            observed_title, superflip_atoms,
            (observed_waiting if self._ordinary_dual_workflow
             else "Waiting for the first Charge-flipping solution result…"),
            superflip_best, self._panel_path(observed_panel), guided.ROLE_OBSERVED,
            observed_panel.cycle if observed_panel is not None else None,
        ))
        panels.append((
            predicted_title, deblurred_atoms,
            (("Generating Structure prediction…" if predicting else predicted_waiting)
             if self._ordinary_dual_workflow
             else (PREDICTING_PLACEHOLDER if predicting else PREDICTED_PLACEHOLDER)),
            deblurred_best, self._panel_path(predicted_panel), guided.ROLE_PREDICTED,
            predicted_panel.cycle if predicted_panel is not None else None,
        ))

        self.structure_figure.clear()
        self.structure_axes = []
        self._structure_interactive_axes = []
        self._structure_depth_artists = []
        self._secondary_depth_artists = []
        self._bond_artists = []
        self._axis_fits = {}
        self._axis_roles = {}
        self._layout_structure_panels()
        count = len(panels)
        # A quiet one-pixel-equivalent boundary makes each scientific result
        # read as its own panel without enclosing the viewer in heavy boxes.
        for boundary in range(1, count):
            x = boundary / count
            self.structure_figure.add_artist(Line2D(
                [x, x], [0.02, 0.98], transform=self.structure_figure.transFigure,
                color="#dce4f0", linewidth=0.8, zorder=0,
            ))
        displayed_elements: List[str] = []
        role_axes: List[Tuple[str, Optional[int], object]] = []
        for index, (_title, atoms, empty_text, _best, path, role, cycle) in enumerate(panels, start=1):
            axis = self.structure_figure.add_subplot(1, count, index, projection="3d")
            self.structure_axes.append(axis)
            self._axis_roles[axis] = role
            role_axes.append((role, cycle, axis))
            if self.view_mode == "molecule":
                view = _complete_molecule_view_for_path(path)
                if view is not None:
                    if self._plot_molecule_panel(axis, view, empty_text):
                        displayed_elements += [clean_element_symbol(a.element) for a in view.atoms]
                        if SHOW_SECONDARY_PEAKS_IN_MOLECULE_VIEW:
                            displayed_elements += [clean_element_symbol(a.element) for a in view.secondary_atoms]
                else:
                    # Unavailable for this specific candidate -> fall back
                    # cleanly to Full cell for THIS panel only; the shared
                    # mode control is unaffected.
                    if self._plot_full_cell_panel(axis, atoms, empty_text):
                        displayed_elements += self._renderer_visible_elements(atoms)
            else:
                if self._plot_full_cell_panel(axis, atoms, empty_text):
                    displayed_elements += self._renderer_visible_elements(atoms)

        # Refit (reset the shared zoom/pan to a fresh default) only at a
        # genuine data transition for some role: it has no prior fit yet,
        # its candidate (cycle) changed, or its extent moved by more than
        # FIT_EXTENT_CHANGE_RATIO -- never merely because THIS render ran
        # (e.g. an ordinary +/- atoms nudge with a similar extent leaves
        # the user's current framing alone; see item 19-22).
        force_refit = False
        seen_roles = set()
        for role, cycle, axis in role_axes:
            fit = self._axis_fits.get(axis)
            if fit is None:
                continue
            radius = float(fit[1])
            seen_roles.add(role)
            prev_cycle = self._last_fit_cycle_by_role.get(role)
            prev_radius = self._last_fit_radius_by_role.get(role)
            if prev_radius is None or prev_cycle != cycle or abs(radius - prev_radius) > FIT_EXTENT_CHANGE_RATIO * prev_radius:
                force_refit = True
                if self._ordinary_dual_workflow:
                    self._pending_fit_roles.add(role)
                    self._manual_camera_roles.discard(role)
            if self._ordinary_dual_workflow and role in previous_cameras:
                elev, azim, limits, zoom = previous_cameras[role]
                axis.view_init(elev=elev, azim=azim)
                if role not in self._pending_fit_roles:
                    self._apply_structure_axis_limits(axis, limits)
                    if zoom is not None:
                        axis.set_box_aspect((1, 1, 1), zoom=zoom)
                        axis._phase_fit_zoom = zoom
            self._last_fit_cycle_by_role[role] = cycle
            self._last_fit_radius_by_role[role] = radius
        for stale_role in set(self._last_fit_cycle_by_role) - seen_roles:
            self._last_fit_cycle_by_role.pop(stale_role, None)
            self._last_fit_radius_by_role.pop(stale_role, None)
        if force_refit:
            self._view_zoom = 1.0
            self._view_pan = np.zeros(3, dtype=np.float64)

        if not self._ordinary_dual_workflow:
            self._apply_camera_to_all()
        self._camera.refresh_axes()
        if self._ordinary_dual_workflow:
            for axis in self._structure_interactive_axes:
                set_structure_viewport_clip(axis)
            self._update_structure_depth_cue(self.structure_elev, self.structure_azim)
        self._set_displayed_elements(displayed_elements)
        self._sync_view_controls()

        # Source name + its recommended cycle, once, directly above each
        # structure (bold title, lighter subtitle), at fixed point offsets
        # from the top edge -- see _layout_structure_panels().
        self._panel_captions = []
        title_offset = -PANEL_CAPTION_TOP_PAD_PT
        subtitle_offset = title_offset - PANEL_TITLE_FONT_PT * 1.25 - PANEL_CAPTION_LINE_GAP_PT
        for index, (title, _atoms, _empty_text, best, _path, _role, _cycle) in enumerate(panels):
            x_position = (index + 0.5) / count
            title_text = self.structure_figure.text(
                x_position, 1.0, title, ha="center", va="top",
                fontsize=PANEL_TITLE_FONT_PT, fontweight="bold", color="#001170",
                fontfamily="Segoe UI",
                transform=offset_copy(self.structure_figure.transFigure, fig=self.structure_figure, y=title_offset, units="points"),
            )
            self._panel_captions.append(title_text)
            if best:
                subtitle_text = self.structure_figure.text(
                    x_position, 1.0, best, ha="center", va="top",
                    fontsize=PANEL_SUBTITLE_FONT_PT, color="#52658b",
                    fontfamily="Segoe UI",
                    transform=offset_copy(self.structure_figure.transFigure, fig=self.structure_figure, y=subtitle_offset, units="points"),
                )
                self._panel_captions.append(subtitle_text)

        # Formula row: one persistent column per panel, aligned under it
        # (equal stretch, matching the equal-width subplot grid above).
        # Chemical formula of the structure actually shown -- updated after
        # every threshold change. Reference's slot stays blank.
        self.reference_column.setVisible(bool(reference_atoms))
        for role, atoms, panel in (
            (guided.ROLE_OBSERVED, superflip_atoms, observed_panel),
            (guided.ROLE_PREDICTED, deblurred_atoms, predicted_panel),
        ):
            column = self.review_columns[role]
            path = self._panel_path(panel)
            composition_label = "ASU composition" if self._ordinary_dual_workflow else "EDMA asymmetric-unit composition"
            text = panel.edma_asu_composition if panel is not None and path is not None else ""
            display_composition = text.translate(str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")) if self._ordinary_dual_workflow else text
            column["formula"].setText(f"{composition_label}: {display_composition}" if text else "")
            display_title = (
                ("Charge-flipping solution" if role == guided.ROLE_OBSERVED else "Structure prediction")
                if self._ordinary_dual_workflow else guided.ROLE_TITLE[role]
            )
            column["formula"].setToolTip(f"{display_title} EDMA asymmetric-unit composition" if text else "")
            count = self._panel_atom_counts.get(role)
            threshold = f"EDMA {guided.format_sigma(panel.threshold_sigma)}" if text and panel is not None else ""
            if threshold and count is not None:
                threshold += f" · {count:,} EDMA sites"
            column["threshold"].setText(threshold)
            column["threshold"].setVisible(bool(threshold))
            column["threshold"].setToolTip(self._edma_threshold_tooltip(path) if threshold else "")

        for axis in self.structure_axes:
            for label in axis.texts:
                label.set_fontfamily("Segoe UI")
        self.structure_canvas.draw_idle()
        if force_refit:
            if not self._ordinary_dual_workflow:
                QTimer.singleShot(0, self._apply_automatic_structure_fit)
            self._structure_fit_timer.start()
