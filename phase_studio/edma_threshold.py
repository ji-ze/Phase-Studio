"""EXPERIMENTAL -- automatic, per-map EDMA threshold (plimit) calibration.

Disabled by default and not validated for production use: Phase Studio
2.0.0 Autosolve uses the fixed 1.20 sigma (Superflip) / 2.00 sigma (SharpED)
thresholds. This engine is reachable only through the development constant
AUTOSOLVE_EDMA_THRESHOLD_MODE below (or RunConfig.edma_threshold_mode); it
has no UI control. On the real koala2 X-ray validation it chose thresholds
with lower reference F0.5 than the fixed defaults and added ~70% cycle time
(docs/RELEASE_2_0_0.md, "Experimental: data-driven EDMA threshold
calibration"). The model-agreement Fcalc is X-ray only (gemmi IT92); it must
not be applied to electron-diffraction amplitudes.

Goal: for ONE density map, choose the LOWEST EDMA sigma threshold whose
extracted structure is still supported by the measured diffraction data.

What this module does NOT do: it never changes EDMA, its peak search, map
normalization, Superflip, SharpED, phase recycling, Map Feedback or result
ranking. It only runs the existing EDMA extraction at several thresholds
(through an injected `extract` callable) and decides between the results.

Why model-derived agreement: the existing amplitude R_F / CC / C3 metrics
(map_quality.compute_map_quality) are computed from the density MAP itself,
so they are identical for every EDMA threshold of the same map. Here every
candidate structure is turned back into structure factors (gemmi, X-ray
IT92 form factors, point atoms) on the ORIGINAL measured reflections, put on
the measured scale with the standard overall treatment k*exp(-B s^2/4) (B by
deterministic log-linear least squares, k and R/CC by the established
map_quality.scaled_amplitude_metrics), and compared with the measured
amplitudes. Without the overall B, point-atom Fcalc does not fall off with
resolution the way measured amplitudes do, and the comparison barely
distinguishes one threshold from another.

Selection is a constraint/plateau rule, not a weighted score:

1. evaluate each threshold (coarse grid, then a fine grid below the lowest
   accepted coarse threshold);
2. hard-reject candidates that are clearly unphysical: too few atoms,
   impossible short contacts, gross over-population relative to a reliable
   composition, or an isolated-peak explosion;
3. find the low-threshold instability boundary: a robust (median/MAD)
   outlier in the number of newly appearing peaks per unit sigma that is NOT
   accompanied by a significant agreement improvement -- that threshold and
   everything below it are rejected;
4. among the rest, the agreement plateau: candidates whose model agreement is,
   at 95% confidence, within a practical-equivalence margin of the best R and,
   separately, of the best CC -- a deterministic paired bootstrap over
   reflections (fixed seed);
5. choose the LOWEST sigma on the plateau. Anything inconclusive falls back
   to the established Autosolve default for that map source.

The acceptance criterion uses the genuine pre-existing orbit-safe holdout
(ValidationContext.free_reflections -- frozen before the first Superflip run
and excluded from every work-data step) when there is one: model R_free /
CC_free. Without one it uses all-data model R_F / CC_F, which is labelled as
non-independent. No free set is ever created here.

A reference structure is never an input: the selector has no reference
parameter at all. Reference F0.5 / precision / recall / RMSD may be attached
to the result afterwards purely as validation of the method.
"""
from __future__ import annotations

import hashlib
import json
import math
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import gemmi
import numpy as np

from phase_studio.map_quality import ValidationContext, scaled_amplitude_metrics

# ---------------------------------------------------------------------------
# Central configuration (every threshold-search literal lives here).
# ---------------------------------------------------------------------------
EDMA_THRESHOLD_MODE_MANUAL = "manual"
EDMA_THRESHOLD_MODE_AUTO = "auto"
# The EDMA threshold mode Autosolve launches with. Deliberately MANUAL (the
# established 1.20 sigma Superflip / 2.00 sigma SharpED) for 2.0.0: on the
# only real reference dataset with a solved structure (koala2 3D ED, 6 maps)
# the data-driven selection chose thresholds with LOWER reference F0.5 than
# the fixed defaults for every Superflip map and 2 of 3 SharpED maps
# (kinematic point-atom agreement falls as correct light-atom peaks are
# added); the held-out 2int3total map was unsolved and could not validate.
# Switch to EDMA_THRESHOLD_MODE_AUTO only once a criterion validates.
AUTOSOLVE_EDMA_THRESHOLD_MODE = EDMA_THRESHOLD_MODE_MANUAL
# Descending coarse grid, in multiples of the map sigma (EDMA plimit
# semantics as used by run_edma_on_xplor: plimit = multiplier * map sigma).
AUTO_EDMA_COARSE_SIGMAS: Tuple[float, ...] = (3.0, 2.6, 2.2, 1.9, 1.6, 1.4, 1.2, 1.0, 0.8, 0.6)
AUTO_EDMA_FINE_STEP = 0.05
AUTO_EDMA_MAX_FINE_POINTS = 3
# Established fixed Autosolve thresholds -- used only as the safe fallback.
AUTO_EDMA_FALLBACK_SIGMA: Mapping[str, float] = {"superflip": 1.20, "deblurred": 2.00}
AUTO_EDMA_PARALLEL_WORKERS = 4
# Plateau test.
BOOTSTRAP_RESAMPLES = 200
BOOTSTRAP_SEED = 20260923
PLATEAU_CONFIDENCE = 0.95
# Practical-equivalence margins (fixed BEFORE the held-out validation): with
# tens of thousands of reflections a paired bootstrap flags CC differences of
# a few thousandths as "significant"; the plateau therefore asks whether a
# candidate's shortfall against the best is, at 95% confidence, within a
# margin too small to matter for choosing a peak list.
PLATEAU_CC_MARGIN = 0.01
PLATEAU_R_MARGIN = 0.005
# A composition only constrains the threshold if it is plausible for the
# cell: expected observable atoms per cell must give 5-150 A^3 per atom
# (dense inorganics ~10-20, organics/proteins ~15-25, porous frameworks
# higher).
# Placeholder compositions (e.g. one formula unit of each element for a
# large cell) are otherwise treated as unavailable.
COMPOSITION_MIN_VOLUME_PER_ATOM = 5.0
COMPOSITION_MAX_VOLUME_PER_ATOM = 150.0
# Hard plausibility limits (deliberately conservative).
MIN_CANDIDATE_ATOMS = 3
MIN_CRITERION_REFLECTIONS = 20
SHORT_CONTACT_ANGSTROM = 0.8
MAX_SHORT_CONTACT_FRACTION = 0.05
ISOLATED_NEIGHBOR_ANGSTROM = 3.0
ISOLATED_EXPLOSION_MIN_FRACTION = 0.5
ISOLATED_EXPLOSION_FACTOR = 2.0
OVERPOPULATION_FACTOR = 1.5
PEAK_JUMP_MAD_K = 5.0
# Elements EDMA's output is never expected to resolve; excluded from both
# the structure factors and the composition checks.
NON_OBSERVED_ELEMENTS = frozenset({"H", "D", "He"})

FALLBACK_MESSAGE = "Auto EDMA threshold inconclusive; fallback used."


@dataclass(frozen=True)
class PeakSite:
    """One extracted asymmetric-unit site (a light, module-local view of
    app.AtomSite, so this module never imports the GUI)."""

    element: str
    frac: Tuple[float, float, float]
    density: float = 0.0


@dataclass
class CandidateEvaluation:
    sigma: float
    n_sites: int = 0
    n_cell_atoms: int = 0
    new_peaks: Optional[int] = None
    r_all: Optional[float] = None
    cc_all: Optional[float] = None
    r_free: Optional[float] = None
    cc_free: Optional[float] = None
    short_contact_fraction: Optional[float] = None
    isolated_fraction: Optional[float] = None
    composition_ratio: Optional[float] = None
    on_plateau: bool = False
    rejected: List[str] = field(default_factory=list)
    error: str = ""


@dataclass
class ThresholdCalibration:
    mode: str
    source: str
    selected_sigma: float
    fallback_used: bool
    message: str
    criterion: str
    candidate_sigmas: List[float]
    candidates: List[CandidateEvaluation]
    composition_available: bool
    holdout_available: bool
    edma_calls: int = 0
    cache_hits: int = 0
    seconds: float = 0.0
    reference_validation: Optional[Dict[str, object]] = None

    @property
    def selected(self) -> Optional[CandidateEvaluation]:
        return next((c for c in self.candidates if math.isclose(c.sigma, self.selected_sigma)), None)

    def compact_label(self) -> str:
        """The one-line UI text, e.g. "EDMA: Auto · 1.15σ"."""
        suffix = " (fallback)" if self.fallback_used else ""
        return f"EDMA: Auto · {self.selected_sigma:.2f}σ{suffix}"

    def to_json(self) -> str:
        payload = asdict(self)
        payload["label"] = self.compact_label()
        return json.dumps(payload, indent=2, sort_keys=True)


# ---------------------------------------------------------------------------
# Candidate grid
# ---------------------------------------------------------------------------
def generate_threshold_candidates(coarse: Sequence[float] = AUTO_EDMA_COARSE_SIGMAS) -> List[float]:
    return sorted({round(float(s), 4) for s in coarse}, reverse=True)


def generate_fine_candidates(
    accepted_sigma: float,
    next_lower_sigma: Optional[float],
    step: float = AUTO_EDMA_FINE_STEP,
    max_points: int = AUTO_EDMA_MAX_FINE_POINTS,
) -> List[float]:
    """Fine thresholds strictly between the lowest accepted coarse threshold
    and the next lower (rejected) coarse threshold."""
    if next_lower_sigma is None:
        return []
    fine: List[float] = []
    value = accepted_sigma - step
    while value > next_lower_sigma + 1.0e-9 and len(fine) < max_points:
        fine.append(round(value, 4))
        value -= step
    return fine


# ---------------------------------------------------------------------------
# Model-derived agreement
# ---------------------------------------------------------------------------
class ModelAgreementEvaluator:
    """Structure factors of an extracted model on the ORIGINAL measured
    reflections (never the feedback-modified working set), X-ray IT92 form
    factors, point atoms (u_iso = 0 -- EDMA peaks carry no ADPs), full
    space-group symmetry. Built once per run; parsed HKL is reused for every
    candidate of every map."""

    def __init__(self, context: ValidationContext, cell: gemmi.UnitCell, spacegroup: gemmi.SpaceGroup) -> None:
        self.cell = cell
        self.spacegroup = spacegroup
        measured = context.original_measured_reflections
        self.hkl = np.asarray([r.hkl for r in measured], dtype=np.int64).reshape(-1, 3)
        self.fo = np.asarray([r.amplitude for r in measured], dtype=np.float64)
        free_keys = {r.hkl for r in context.free_reflections}
        self.free_mask = np.asarray([tuple(h) in free_keys for h in map(tuple, self.hkl)], dtype=bool)
        self.holdout_available = int(self.free_mask.sum()) >= MIN_CRITERION_REFLECTIONS
        self.work_mask = ~self.free_mask
        self.s2 = np.asarray([1.0 / cell.calculate_d([int(h), int(k), int(l)]) ** 2 for h, k, l in self.hkl], dtype=np.float64)
        self._calculator = gemmi.StructureFactorCalculatorX(cell)

    def criterion_mask(self) -> np.ndarray:
        """Reflections the ACCEPTANCE decision uses: the genuine free set when
        it exists, otherwise all measured reflections."""
        return self.free_mask if self.holdout_available else np.ones(len(self.fo), dtype=bool)

    def criterion_label(self) -> str:
        return "model R_free / CC_free (genuine holdout)" if self.holdout_available else (
            "all-data model R_F / CC_F (non-independent agreement)"
        )

    def fcalc(self, sites: Sequence[PeakSite]) -> np.ndarray:
        structure = gemmi.SmallStructure()
        structure.cell = self.cell
        structure.spacegroup_hm = self.spacegroup.hm
        for index, site in enumerate(sites):
            if site.element in NON_OBSERVED_ELEMENTS:
                continue
            entry = gemmi.SmallStructure.Site()
            entry.label = f"{site.element}{index + 1}"
            entry.element = gemmi.Element(site.element)
            entry.fract = gemmi.Fractional(*site.frac)
            entry.occ = 1.0
            entry.u_iso = 0.0
            structure.add_site(entry)
        structure.setup_cell_images()
        calc = self._calculator
        raw = np.asarray(
            [abs(calc.calculate_sf_from_small_structure(structure, [int(h), int(k), int(l)])) for h, k, l in self.hkl],
            dtype=np.float64,
        )
        return apply_overall_b(self.fo, raw, self.s2, self.criterion_fit_mask())

    def criterion_fit_mask(self) -> np.ndarray:
        """Reflections the overall-B fit may see: WORK reflections only when a
        genuine holdout exists (so no free-set information enters the
        scaling), otherwise all."""
        return self.work_mask if self.holdout_available else np.ones(len(self.fo), dtype=bool)


def apply_overall_b(fo: np.ndarray, fc: np.ndarray, s2: np.ndarray, fit_mask: np.ndarray) -> np.ndarray:
    """fc * exp(-B s^2 / 4) with the overall B from a deterministic
    log-linear least-squares fit of ln(Fo/Fc) against s^2/4 on `fit_mask`
    (the linear scale k is then fitted by scaled_amplitude_metrics)."""
    ok = fit_mask & (fo > 0) & (fc > 0) & np.isfinite(fo) & np.isfinite(fc)
    if int(ok.sum()) < MIN_CRITERION_REFLECTIONS:
        return fc
    x = s2[ok] / 4.0
    y = np.log(fo[ok] / fc[ok])
    x_mean = float(np.mean(x))
    denominator = float(np.sum((x - x_mean) ** 2))
    if denominator <= 1.0e-15:
        return fc
    b_value = -float(np.sum((x - x_mean) * (y - float(np.mean(y))))) / denominator
    return fc * np.exp(-b_value * s2 / 4.0)


def assess_model_data_agreement(fo: np.ndarray, fc: np.ndarray, mask: np.ndarray) -> Tuple[Optional[float], Optional[float]]:
    """Established least-squares-scaled R and Pearson CC on `mask`."""
    if int(mask.sum()) < MIN_CRITERION_REFLECTIONS:
        return None, None
    metrics = scaled_amplitude_metrics(fo[mask], fc[mask])
    return metrics.r_factor, metrics.correlation


def _bootstrap_r_cc(fo: np.ndarray, fc: np.ndarray, samples: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """R and CC for every bootstrap resample (rows of `samples` are index
    draws over the criterion reflections), re-scaling per resample exactly
    like scaled_amplitude_metrics does."""
    fo_b = fo[samples]
    fc_b = fc[samples]
    scale = np.maximum(0.0, np.sum(fo_b * fc_b, axis=1) / np.maximum(np.sum(fc_b * fc_b, axis=1), 1.0e-15))
    r = np.sum(np.abs(fo_b - scale[:, None] * fc_b), axis=1) / np.maximum(np.sum(fo_b, axis=1), 1.0e-15)
    fo_c = fo_b - fo_b.mean(axis=1, keepdims=True)
    fc_c = fc_b - fc_b.mean(axis=1, keepdims=True)
    cc = np.sum(fo_c * fc_c, axis=1) / np.maximum(
        np.sqrt(np.sum(fo_c * fo_c, axis=1) * np.sum(fc_c * fc_c, axis=1)), 1.0e-15
    )
    return r, cc


# ---------------------------------------------------------------------------
# Geometry / composition diagnostics
# ---------------------------------------------------------------------------
def expand_to_cell(sites: Sequence[PeakSite], spacegroup: gemmi.SpaceGroup) -> Tuple[np.ndarray, List[str]]:
    """Unique full-cell fractional positions (wrapped into [0,1)), 1e-3 dedupe."""
    ops = [op.translated(cen) for op in spacegroup.operations().sym_ops for cen in spacegroup.operations().cen_ops]
    frac: List[np.ndarray] = []
    elements: List[str] = []
    seen = set()
    for site in sites:
        for op in ops:
            position = np.mod(np.asarray(op.apply_to_xyz(list(site.frac)), dtype=np.float64), 1.0)
            key = (site.element, *np.round(position, 3) % 1.0)
            if key in seen:
                continue
            seen.add(key)
            frac.append(position)
            elements.append(site.element)
    return np.asarray(frac, dtype=np.float64).reshape(-1, 3), elements


def nearest_neighbor_distances(frac: np.ndarray, cell: gemmi.UnitCell) -> np.ndarray:
    """Periodic nearest-neighbor Cartesian distance per atom (minimum image
    over the 27 neighboring cells -- exact for any cell edge > the distances
    of interest here)."""
    n = len(frac)
    if n < 2:
        return np.full(n, np.inf)
    orth = np.asarray(cell.orth.mat.tolist(), dtype=np.float64)
    # Minimum image alone is exact for every distance below half the
    # smallest perpendicular cell width; only very small cells need the
    # 27-cell search for the largest distance of interest here.
    perpendicular_widths = 1.0 / np.linalg.norm(np.linalg.inv(orth), axis=1)
    if float(np.min(perpendicular_widths)) > 2.0 * ISOLATED_NEIGHBOR_ANGSTROM:
        shifts = np.zeros((1, 3), dtype=np.float64)
    else:
        shifts = np.asarray([(a, b, c) for a in (-1, 0, 1) for b in (-1, 0, 1) for c in (-1, 0, 1)], dtype=np.float64)
    nearest = np.full(n, np.inf)
    chunk = max(1, 4_000_000 // max(1, n * len(shifts)))
    for start in range(0, n, chunk):
        block = frac[start:start + chunk]
        delta = frac[None, :, :] - block[:, None, :]
        delta -= np.round(delta)
        best = np.full((len(block), n), np.inf)
        for shift in shifts:
            cart = (delta + shift) @ orth.T
            best = np.minimum(best, np.linalg.norm(cart, axis=2))
        for row in range(len(block)):
            best[row, start + row] = np.inf  # self
        nearest[start:start + len(block)] = best.min(axis=1)
    return nearest


def reliable_expected_atoms(composition: Sequence[Tuple[str, int]], cell_volume: float) -> Optional[int]:
    """expected_observable_atoms(), but only when it is plausible for the
    cell volume (COMPOSITION_MIN/MAX_VOLUME_PER_ATOM); otherwise None, i.e.
    the composition is treated as unavailable rather than as a constraint."""
    expected = expected_observable_atoms(composition)
    if not expected or cell_volume <= 0:
        return None
    volume_per_atom = cell_volume / float(expected)
    if COMPOSITION_MIN_VOLUME_PER_ATOM <= volume_per_atom <= COMPOSITION_MAX_VOLUME_PER_ATOM:
        return expected
    return None


def expected_observable_atoms(composition: Sequence[Tuple[str, int]]) -> Optional[int]:
    """Expected non-H/D/He atoms per cell from a reliable composition (the
    elements EDMA's peaks are actually assigned to)."""
    total = sum(int(count) for element, count in composition if element not in NON_OBSERVED_ELEMENTS and int(count) > 0)
    return total if total > 0 else None


# ---------------------------------------------------------------------------
# Evaluation + selection
# ---------------------------------------------------------------------------
@dataclass
class _Evaluated:
    info: CandidateEvaluation
    fc: Optional[np.ndarray]


def evaluate_edma_candidate(
    sigma: float,
    sites: Sequence[PeakSite],
    evaluator: ModelAgreementEvaluator,
    expected_atoms: Optional[int],
) -> _Evaluated:
    info = CandidateEvaluation(sigma=float(sigma), n_sites=len(sites))
    observed = [s for s in sites if s.element not in NON_OBSERVED_ELEMENTS]
    frac, _elements = expand_to_cell(observed, evaluator.spacegroup)
    info.n_cell_atoms = len(frac)
    if len(observed) < MIN_CANDIDATE_ATOMS:
        info.rejected.append(f"fewer than {MIN_CANDIDATE_ATOMS} atoms")
        return _Evaluated(info, None)
    nearest = nearest_neighbor_distances(frac, evaluator.cell)
    info.short_contact_fraction = float(np.mean(nearest < SHORT_CONTACT_ANGSTROM))
    info.isolated_fraction = float(np.mean(nearest > ISOLATED_NEIGHBOR_ANGSTROM))
    if expected_atoms:
        info.composition_ratio = info.n_cell_atoms / float(expected_atoms)
    fc = evaluator.fcalc(observed)
    info.r_all, info.cc_all = assess_model_data_agreement(evaluator.fo, fc, np.ones(len(fc), dtype=bool))
    if evaluator.holdout_available:
        info.r_free, info.cc_free = assess_model_data_agreement(evaluator.fo, fc, evaluator.free_mask)
    if info.r_all is None or info.cc_all is None:
        info.rejected.append("structure-factor agreement unavailable")
        return _Evaluated(info, None)
    return _Evaluated(info, fc)


def select_lowest_supported_threshold(
    evaluated: Sequence[_Evaluated],
    evaluator: ModelAgreementEvaluator,
) -> Optional[float]:
    """Applies the plateau/constraint rule (module docstring) in place on the
    CandidateEvaluation records and returns the chosen sigma, or None."""
    ordered = sorted(evaluated, key=lambda e: e.info.sigma, reverse=True)
    mask = evaluator.criterion_mask()
    criterion_index = np.nonzero(mask)[0]
    if len(criterion_index) < MIN_CRITERION_REFLECTIONS:
        return None
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    samples = criterion_index[rng.integers(0, len(criterion_index), size=(BOOTSTRAP_RESAMPLES, len(criterion_index)))]
    fo = evaluator.fo
    boot: Dict[float, Tuple[np.ndarray, np.ndarray]] = {}
    for item in ordered:
        if item.fc is not None:
            boot[item.info.sigma] = _bootstrap_r_cc(fo, item.fc, samples)

    def significantly_better(lower: _Evaluated, higher: _Evaluated) -> bool:
        """Agreement at `lower` significantly better than at `higher`."""
        if lower.info.sigma not in boot or higher.info.sigma not in boot:
            return False
        r_low, cc_low = boot[lower.info.sigma]
        r_high, cc_high = boot[higher.info.sigma]
        upper_q = PLATEAU_CONFIDENCE * 100.0
        return bool(np.percentile(r_low - r_high, upper_q) < 0.0 or np.percentile(cc_high - cc_low, upper_q) < 0.0)

    # Hard plausibility rejections.
    reference_isolated = None
    for item in ordered:
        info = item.info
        if item.fc is None:
            continue
        if info.short_contact_fraction is not None and info.short_contact_fraction > MAX_SHORT_CONTACT_FRACTION:
            info.rejected.append(f"short contacts < {SHORT_CONTACT_ANGSTROM} Å in {info.short_contact_fraction:.0%} of atoms")
        if info.composition_ratio is not None and info.composition_ratio > OVERPOPULATION_FACTOR:
            info.rejected.append(f"over-populated: {info.composition_ratio:.2f}× the expected observable atoms")
        if info.isolated_fraction is not None:
            if reference_isolated is None:
                reference_isolated = info.isolated_fraction
            elif (
                info.isolated_fraction > ISOLATED_EXPLOSION_MIN_FRACTION
                and info.isolated_fraction > ISOLATED_EXPLOSION_FACTOR * max(reference_isolated, 1.0e-6)
            ):
                info.rejected.append(f"isolated-peak explosion ({info.isolated_fraction:.0%} isolated)")

    # Instability boundary: robust outlier in newly appearing peaks per unit
    # sigma, not supported by a significant agreement improvement.
    valid = [item for item in ordered if item.fc is not None]
    rates: List[Tuple[_Evaluated, _Evaluated, float]] = []
    for higher, lower in zip(valid, valid[1:]):
        new = lower.info.n_cell_atoms - higher.info.n_cell_atoms
        lower.info.new_peaks = new
        step = max(higher.info.sigma - lower.info.sigma, 1.0e-6)
        rates.append((higher, lower, new / step))
    if len(rates) >= 3:
        values = np.asarray([rate for _h, _l, rate in rates], dtype=np.float64)
        median = float(np.median(values))
        mad = float(np.median(np.abs(values - median))) * 1.4826
        limit = median + PEAK_JUMP_MAD_K * max(mad, 0.05 * abs(median), 1.0)
        for higher, lower, rate in rates:
            if rate > limit and not significantly_better(lower, higher):
                cut = lower.info.sigma
                for item in valid:
                    if item.info.sigma <= cut + 1.0e-9:
                        item.info.rejected.append(
                            f"below the peak-count instability onset at {cut:.2f}σ (unsupported by agreement)"
                        )
                break

    admissible = [item for item in valid if not item.info.rejected]
    if not admissible:
        return None
    # The plateau is judged against the best R AND, separately, the best CC:
    # a candidate must be statistically compatible with each.
    free = evaluator.holdout_available
    r_of = (lambda item: item.info.r_free) if free else (lambda item: item.info.r_all)
    cc_of = (lambda item: item.info.cc_free) if free else (lambda item: item.info.cc_all)
    best_r = min(admissible, key=lambda item: (r_of(item) if r_of(item) is not None else math.inf))
    best_cc = max(admissible, key=lambda item: (cc_of(item) if cc_of(item) is not None else -math.inf))
    r_best = boot[best_r.info.sigma][0]
    cc_best = boot[best_cc.info.sigma][1]
    plateau: List[_Evaluated] = []
    upper_q = PLATEAU_CONFIDENCE * 100.0
    for item in admissible:
        r_c, cc_c = boot[item.info.sigma]
        r_ok = float(np.percentile(r_c - r_best, upper_q)) <= PLATEAU_R_MARGIN
        cc_ok = float(np.percentile(cc_best - cc_c, upper_q)) <= PLATEAU_CC_MARGIN
        item.info.on_plateau = bool(r_ok and cc_ok)
        if item.info.on_plateau:
            plateau.append(item)
        else:
            item.info.rejected.append("agreement worse than the best candidate beyond the practical-equivalence margin")
    if not plateau:
        return None
    return min(item.info.sigma for item in plateau)


Extractor = Callable[[float], Sequence[PeakSite]]


def calibrate_edma_threshold(
    source: str,
    extract_many: Callable[[Sequence[float]], Dict[float, object]],
    evaluator: ModelAgreementEvaluator,
    composition: Sequence[Tuple[str, int]] = (),
    coarse: Sequence[float] = AUTO_EDMA_COARSE_SIGMAS,
    stop_event: Optional[threading.Event] = None,
) -> ThresholdCalibration:
    """Coarse-to-fine calibration for one map. `extract_many(sigmas)` returns
    {sigma: sequence of PeakSite | Exception} (it may run EDMA in parallel
    and use a cache). A user stop (stop_event) is re-raised; any other
    failure yields the safe fallback."""
    import time

    started = time.perf_counter()
    fallback = float(AUTO_EDMA_FALLBACK_SIGMA.get(source, AUTO_EDMA_FALLBACK_SIGMA["superflip"]))
    expected_atoms = reliable_expected_atoms(composition, float(evaluator.cell.volume))
    evaluated: Dict[float, _Evaluated] = {}
    calls = {"n": 0}

    def run(sigmas: Sequence[float]) -> None:
        todo = [s for s in sigmas if s not in evaluated]
        if not todo:
            return
        results = extract_many(todo)
        calls["n"] += len(todo)
        if stop_event is not None and stop_event.is_set():
            raise InterruptedError("EDMA threshold calibration stopped")
        for sigma in todo:
            result = results.get(sigma)
            if isinstance(result, BaseException) or result is None:
                info = CandidateEvaluation(sigma=float(sigma), error=str(result or "no result"))
                info.rejected.append("EDMA extraction failed")
                evaluated[sigma] = _Evaluated(info, None)
            else:
                evaluated[sigma] = evaluate_edma_candidate(sigma, list(result), evaluator, expected_atoms)

    def result(selected: Optional[float], message: str = "") -> ThresholdCalibration:
        candidates = sorted((e.info for e in evaluated.values()), key=lambda c: c.sigma, reverse=True)
        return ThresholdCalibration(
            mode=EDMA_THRESHOLD_MODE_AUTO,
            source=source,
            selected_sigma=float(selected if selected is not None else fallback),
            fallback_used=selected is None,
            message=message or (FALLBACK_MESSAGE if selected is None else "Lowest data-supported threshold selected."),
            criterion=evaluator.criterion_label(),
            candidate_sigmas=[c.sigma for c in candidates],
            candidates=candidates,
            composition_available=expected_atoms is not None,
            holdout_available=evaluator.holdout_available,
            edma_calls=calls["n"],
            seconds=time.perf_counter() - started,
        )

    try:
        coarse_grid = generate_threshold_candidates(coarse)
        run(coarse_grid)
        chosen = select_lowest_supported_threshold(list(evaluated.values()), evaluator)
        if chosen is None:
            return result(None)
        lower = [s for s in coarse_grid if s < chosen - 1.0e-9]
        fine = generate_fine_candidates(chosen, max(lower) if lower else None)
        if fine:
            run(fine)
            for item in evaluated.values():
                item.info.rejected.clear()
                item.info.on_plateau = False
            chosen = select_lowest_supported_threshold(list(evaluated.values()), evaluator)
        return result(chosen)
    except InterruptedError:
        raise
    except Exception as exc:  # pathological map / Fcalc failure -> fallback
        return result(None, f"{FALLBACK_MESSAGE} ({type(exc).__name__}: {exc})")


# ---------------------------------------------------------------------------
# Cache + parallel extraction plumbing (EDMA itself is injected)
# ---------------------------------------------------------------------------
def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class EdmaCandidateCache:
    """Extracted sites per (map SHA-256, sigma, EDMA settings/version,
    composition context), as small JSON files -- the same map/sigma
    combination is never run through EDMA twice."""

    def __init__(self, directory: Path, map_sha256: str, context_key: str) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.prefix = hashlib.sha256(f"{map_sha256}|{context_key}".encode("utf-8")).hexdigest()[:24]

    def _path(self, sigma: float) -> Path:
        return self.directory / f"{self.prefix}_{sigma:.4f}.json"

    def get(self, sigma: float) -> Optional[List[PeakSite]]:
        path = self._path(sigma)
        if not path.is_file():
            return None
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
            return [PeakSite(str(r[0]), (float(r[1]), float(r[2]), float(r[3])), float(r[4])) for r in rows]
        except Exception:
            return None

    def put(self, sigma: float, sites: Iterable[PeakSite]) -> None:
        rows = [[s.element, *s.frac, s.density] for s in sites]
        self._path(sigma).write_text(json.dumps(rows), encoding="utf-8")


def cached_parallel_extractor(
    extract: Extractor,
    cache: Optional[EdmaCandidateCache],
    workers: int = AUTO_EDMA_PARALLEL_WORKERS,
    stats: Optional[Dict[str, int]] = None,
) -> Callable[[Sequence[float]], Dict[float, object]]:
    """Wraps a single-threshold `extract` into `extract_many`: cache first,
    the remaining thresholds through a small thread pool (each EDMA call is
    its own external process in its own directory)."""

    def extract_many(sigmas: Sequence[float]) -> Dict[float, object]:
        out: Dict[float, object] = {}
        todo: List[float] = []
        for sigma in sigmas:
            hit = cache.get(sigma) if cache is not None else None
            if hit is not None:
                out[sigma] = hit
                if stats is not None:
                    stats["cache_hits"] = stats.get("cache_hits", 0) + 1
            else:
                todo.append(sigma)

        def one(sigma: float) -> object:
            try:
                sites = list(extract(sigma))
                if cache is not None:
                    cache.put(sigma, sites)
                return sites
            except Exception as exc:  # recorded per candidate
                return exc

        if todo:
            with ThreadPoolExecutor(max_workers=max(1, min(workers, len(todo)))) as pool:
                for sigma, value in zip(todo, pool.map(one, todo)):
                    out[sigma] = value
            if stats is not None:
                stats["edma_runs"] = stats.get("edma_runs", 0) + len(todo)
        return out

    return extract_many
