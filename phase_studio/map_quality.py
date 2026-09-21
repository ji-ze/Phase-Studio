"""Profile-aware, source-neutral map-quality assessment.

This module contains no Qt code and performs no workflow I/O.  A workflow
freezes :class:`ValidationContext` once from the original experimental data;
every Superflip and SharpED map is then assessed against that same context.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import Enum
from typing import Iterable, Mapping, Optional, Sequence, Tuple

import numpy as np

Hkl = Tuple[int, int, int]


class ValidationProfile(str, Enum):
    REFERENCE_AND_HOLDOUT = "reference_and_holdout"
    REFERENCE_ONLY = "reference_only"
    HOLDOUT_ONLY = "holdout_only"
    REFERENCE_FREE = "reference_free"


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    label: str
    higher_is_better: bool

    @property
    def arrow_label(self) -> str:
        return f"{self.label} {'↑' if self.higher_is_better else '↓'}"


@dataclass(frozen=True)
class ValidationProfileDefinition:
    profile: ValidationProfile
    assessment_label: str
    description: str
    primary_metrics: Tuple[MetricDefinition, MetricDefinition, MetricDefinition]
    report_only_metrics: Tuple[MetricDefinition, ...]

    @property
    def all_report_metrics(self) -> Tuple[MetricDefinition, ...]:
        """Primary plus diagnostic metrics, de-duplicated in stable order."""
        ordered = []
        seen = set()
        for metric in self.primary_metrics + self.report_only_metrics:
            if metric.key not in seen:
                ordered.append(metric)
                seen.add(metric.key)
        return tuple(ordered)

    @property
    def recommendation_reason(self) -> str:
        first, second, third = self.primary_metrics
        direction = "highest" if first.higher_is_better else "lowest"
        return (
            f"Recommended by {direction} {first.label}; "
            f"{second.label} and {third.label} are tie-breakers."
        )


REFERENCE_F05 = MetricDefinition("reference_f05", "Reference F0.5", True)
REFERENCE_PRECISION = MetricDefinition("reference_precision", "Reference precision", True)
REFERENCE_RECALL = MetricDefinition("reference_recall", "Reference recall", True)
REFERENCE_TP = MetricDefinition("reference_tp", "Reference true positives", True)
REFERENCE_FP = MetricDefinition("reference_fp", "Reference false positives", False)
REFERENCE_RMSD = MetricDefinition("reference_rmsd", "Matched-peak RMSD", False)
REFERENCE_PHASE = MetricDefinition("reference_phase_agreement", "Reference phase agreement", True)
AMPLITUDE_RF = MetricDefinition("amplitude_rf", "Amplitude agreement R factor", False)
AMPLITUDE_CC = MetricDefinition("amplitude_cc", "Amplitude CC", True)
AMPLITUDE_SCALE = MetricDefinition("amplitude_scale", "Amplitude scale", True)
R_WORK = MetricDefinition("r_work", "R_work", False)
R_FREE = MetricDefinition("r_free", "R_free", False)
CC_WORK = MetricDefinition("cc_work", "CC_work", True)
CC_FREE = MetricDefinition("cc_free", "CC_free", True)
OMIT_CC = MetricDefinition("omit_map_correlation", "OMIT map correlation", True)
TRIPLET_C3 = MetricDefinition("triplet_c3", "Weighted triplet C3", True)
ENTROPY = MetricDefinition("entropy_normalized", "Normalized map entropy", False)
CONCENTRATION = MetricDefinition("map_concentration", "Map concentration", True)
PEAKINESS = MetricDefinition("standardized_peakiness", "Standardized peakiness", True)
NEGATIVE_MASS = MetricDefinition("negative_density_mass", "Negative-density mass fraction", False)

COMMON_REPORT_METRICS = (
    REFERENCE_PRECISION, REFERENCE_RECALL, REFERENCE_TP, REFERENCE_FP,
    AMPLITUDE_RF, AMPLITUDE_CC, AMPLITUDE_SCALE,
    R_WORK, R_FREE, CC_WORK, CC_FREE, OMIT_CC, TRIPLET_C3,
    ENTROPY, CONCENTRATION, PEAKINESS, NEGATIVE_MASS,
)

PROFILE_DEFINITIONS = {
    ValidationProfile.REFERENCE_AND_HOLDOUT: ValidationProfileDefinition(
        ValidationProfile.REFERENCE_AND_HOLDOUT,
        "Reference + cross-validation",
        "Reference-backed structural assessment with a frozen 5% experimental holdout.",
        (REFERENCE_F05, R_FREE, OMIT_CC),
        COMMON_REPORT_METRICS + (REFERENCE_RMSD, REFERENCE_PHASE),
    ),
    ValidationProfile.REFERENCE_ONLY: ValidationProfileDefinition(
        ValidationProfile.REFERENCE_ONLY,
        "Reference-backed",
        "Agreement with a supplied reference structure using measured reflections.",
        (REFERENCE_F05, REFERENCE_RMSD, REFERENCE_PHASE),
        COMMON_REPORT_METRICS,
    ),
    ValidationProfile.HOLDOUT_ONLY: ValidationProfileDefinition(
        ValidationProfile.HOLDOUT_ONLY,
        "Cross-validation",
        "Independent assessment against a frozen 5% experimental holdout.",
        (R_FREE, CC_FREE, OMIT_CC),
        COMMON_REPORT_METRICS,
    ),
    ValidationProfile.REFERENCE_FREE: ValidationProfileDefinition(
        ValidationProfile.REFERENCE_FREE,
        "Reference-free · no holdout",
        "Reference-free map assessment; these metrics are not independent validation.",
        (AMPLITUDE_RF, AMPLITUDE_CC, TRIPLET_C3),
        COMMON_REPORT_METRICS,
    ),
}


def determine_validation_profile(reference_available: bool, holdout_enabled: bool) -> ValidationProfile:
    if reference_available and holdout_enabled:
        return ValidationProfile.REFERENCE_AND_HOLDOUT
    if reference_available:
        return ValidationProfile.REFERENCE_ONLY
    if holdout_enabled:
        return ValidationProfile.HOLDOUT_ONLY
    return ValidationProfile.REFERENCE_FREE


def profile_definition(profile: ValidationProfile | str) -> ValidationProfileDefinition:
    return PROFILE_DEFINITIONS[ValidationProfile(profile)]


@dataclass(frozen=True)
class FrozenReflection:
    h: int
    k: int
    l: int
    amplitude: float

    @property
    def hkl(self) -> Hkl:
        return int(self.h), int(self.k), int(self.l)


@dataclass(frozen=True)
class WeightedTriplet:
    h: Hkl
    k: Hkl
    h_plus_k: Hkl
    weight: float


@dataclass(frozen=True)
class ValidationContext:
    original_measured_reflections: Tuple[FrozenReflection, ...]
    work_reflections: Tuple[FrozenReflection, ...]
    free_reflections: Tuple[FrozenReflection, ...]
    reference_model: Optional[str]
    triplet_set: Tuple[WeightedTriplet, ...]
    triplet_weights: Tuple[float, ...]
    reference_phases: Tuple[Tuple[Hkl, float], ...]
    unit_cell: Optional[Tuple[float, float, float, float, float, float]]
    profile: ValidationProfile


def build_weighted_triplets(
    reflections: Sequence[FrozenReflection], *, seed_count: int = 64, max_triplets: int = 50_000,
) -> Tuple[WeightedTriplet, ...]:
    """Build deterministic measured-data triplets in O(N * seed_count).

    The strongest measured normalized amplitudes are used as the bounded set
    of ``k`` candidates.  Membership of ``h+k`` is an O(1) lookup.  This avoids
    a blind O(N²) pair search while retaining the high-weight relationships
    that dominate the statistic.
    """
    by_hkl = {r.hkl: r for r in reflections if r.hkl != (0, 0, 0) and r.amplitude > 0}
    if len(by_hkl) < 3:
        return ()
    amplitudes = np.asarray([r.amplitude for r in by_hkl.values()], dtype=np.float64)
    rms = float(math.sqrt(float(np.mean(np.square(amplitudes)))))
    if rms <= 1.0e-15:
        return ()
    e_values = {hkl: float(r.amplitude) / rms for hkl, r in by_hkl.items()}
    strongest = sorted(by_hkl, key=lambda hkl: (-e_values[hkl], hkl))[:max(1, int(seed_count))]
    triplets = []
    seen = set()
    for h in sorted(by_hkl):
        for k in strongest:
            total = (h[0] + k[0], h[1] + k[1], h[2] + k[2])
            if total == (0, 0, 0) or total not in by_hkl:
                continue
            pair = tuple(sorted((h, k)))
            identity = (pair[0], pair[1], total)
            if identity in seen:
                continue
            seen.add(identity)
            weight = e_values[h] * e_values[k] * e_values[total]
            if np.isfinite(weight) and weight > 0:
                triplets.append(WeightedTriplet(h, k, total, float(weight)))
                if len(triplets) >= max_triplets:
                    return tuple(triplets)
    return tuple(triplets)


def make_validation_context(
    measured_reflections: Iterable[FrozenReflection],
    *,
    free_hkls: Iterable[Hkl] = (),
    reference_model: Optional[str] = None,
    reference_phases: Optional[Mapping[Hkl, float]] = None,
    unit_cell: Optional[Sequence[float]] = None,
) -> ValidationContext:
    measured = tuple(
        r for r in measured_reflections
        if r.hkl != (0, 0, 0) and np.isfinite(r.amplitude) and r.amplitude >= 0
    )
    free_keys = frozenset(tuple(map(int, hkl)) for hkl in free_hkls)
    free = tuple(r for r in measured if r.hkl in free_keys)
    work = tuple(r for r in measured if r.hkl not in free_keys)
    triplets = build_weighted_triplets(measured)
    phases = tuple(sorted(
        ((tuple(map(int, hkl)), float(value)) for hkl, value in (reference_phases or {}).items()),
        key=lambda item: item[0],
    ))
    profile = determine_validation_profile(bool(reference_model), bool(free))
    return ValidationContext(
        original_measured_reflections=measured,
        work_reflections=work,
        free_reflections=free,
        reference_model=reference_model,
        triplet_set=triplets,
        triplet_weights=tuple(t.weight for t in triplets),
        reference_phases=phases,
        unit_cell=(tuple(float(value) for value in unit_cell[:6]) if unit_cell is not None else None),
        profile=profile,
    )


@dataclass(frozen=True)
class ScaledAmplitudeMetrics:
    r_factor: Optional[float]
    correlation: Optional[float]
    scale: Optional[float]
    count: int


def scaled_amplitude_metrics(observed: Sequence[float], calculated: Sequence[float]) -> ScaledAmplitudeMetrics:
    pairs = [
        (float(fo), float(fc)) for fo, fc in zip(observed, calculated)
        if np.isfinite(fo) and np.isfinite(fc) and fo >= 0 and fc >= 0
    ]
    if not pairs:
        return ScaledAmplitudeMetrics(None, None, None, 0)
    fo = np.asarray([pair[0] for pair in pairs], dtype=np.float64)
    fc = np.asarray([pair[1] for pair in pairs], dtype=np.float64)
    denominator = float(np.dot(fc, fc))
    fo_sum = float(np.sum(fo))
    if denominator <= 1.0e-15 or fo_sum <= 1.0e-15:
        return ScaledAmplitudeMetrics(None, None, None, len(pairs))
    scale = max(0.0, float(np.dot(fo, fc)) / denominator)
    r_factor = float(np.sum(np.abs(fo - scale * fc)) / fo_sum)
    correlation = None
    if len(pairs) >= 2 and float(np.std(fo)) > 1.0e-15 and float(np.std(fc)) > 1.0e-15:
        correlation = float(np.corrcoef(fo, fc)[0, 1])
    return ScaledAmplitudeMetrics(r_factor, correlation, scale, len(pairs))


@dataclass(frozen=True)
class MapQualityMetrics:
    reference_f05: Optional[float] = None
    reference_precision: Optional[float] = None
    reference_recall: Optional[float] = None
    reference_tp: Optional[int] = None
    reference_fp: Optional[int] = None
    reference_rmsd: Optional[float] = None
    reference_phase_agreement: Optional[float] = None
    amplitude_rf: Optional[float] = None
    amplitude_cc: Optional[float] = None
    amplitude_scale: Optional[float] = None
    r_work: Optional[float] = None
    r_free: Optional[float] = None
    cc_work: Optional[float] = None
    cc_free: Optional[float] = None
    omit_map_correlation: Optional[float] = None
    triplet_c3: Optional[float] = None
    entropy_normalized: Optional[float] = None
    map_concentration: Optional[float] = None
    standardized_peakiness: Optional[float] = None
    negative_density_mass: Optional[float] = None
    n_measured_reflections: int = 0
    n_work_reflections: int = 0
    n_free_reflections: int = 0
    n_triplets: int = 0
    unavailable_reason: str = ""

    def value(self, key: str) -> Optional[float]:
        value = getattr(self, key, None)
        if value is None:
            return None
        try:
            result = float(value)
        except (TypeError, ValueError):
            return None
        return result if np.isfinite(result) else None


def f_score(precision: Optional[float], recall: Optional[float], beta: float = 0.5) -> Optional[float]:
    if precision is None or recall is None:
        return None
    p, r = float(precision), float(recall)
    beta2 = float(beta) ** 2
    denominator = beta2 * p + r
    if denominator <= 0:
        return 0.0 if p == 0 and r == 0 else None
    return float((1.0 + beta2) * p * r / denominator)


def with_reference_metrics(
    metrics: MapQualityMetrics,
    *,
    precision: Optional[float],
    recall: Optional[float],
    rmsd: Optional[float],
    true_positives: Optional[int] = None,
    false_positives: Optional[int] = None,
) -> MapQualityMetrics:
    return replace(
        metrics,
        reference_f05=f_score(precision, recall, 0.5),
        reference_precision=precision,
        reference_recall=recall,
        reference_tp=true_positives,
        reference_fp=false_positives,
        reference_rmsd=rmsd,
    )


def with_holdout_metrics(
    metrics: MapQualityMetrics,
    holdout_metrics: MapQualityMetrics,
    omit_map_correlation: Optional[float],
) -> MapQualityMetrics:
    return replace(
        metrics,
        r_work=holdout_metrics.r_work,
        r_free=holdout_metrics.r_free,
        cc_work=holdout_metrics.cc_work,
        cc_free=holdout_metrics.cc_free,
        omit_map_correlation=omit_map_correlation,
    )


def _valid_full_cell_map(
    density: np.ndarray,
    grid: Sequence[int],
    cell: Sequence[float],
    axis_order: str,
) -> tuple[Optional[Tuple[int, int, int]], str]:
    if len(grid) < 9 or len(cell) < 6:
        return None, "Map header lacks full unit-cell/grid metadata."
    nx, ny, nz = int(grid[0]), int(grid[3]), int(grid[6])
    if nx <= 0 or ny <= 0 or nz <= 0 or density.size != nx * ny * nz:
        return None, "Map grid dimensions do not match its density samples."
    if tuple(map(int, grid[1:3] + grid[4:6] + grid[7:9])) != (0, nx - 1, 0, ny - 1, 0, nz - 1):
        return None, "Map is cropped; Fourier validation requires a periodic full-cell map."
    if any(not np.isfinite(float(v)) or float(v) <= 0 for v in cell[:3]):
        return None, "Map unit-cell lengths are unavailable or invalid."
    if any(not np.isfinite(float(v)) or not 0 < float(v) < 180 for v in cell[3:6]):
        return None, "Map unit-cell angles are unavailable or invalid."
    if str(axis_order or "").strip().upper() != "ZYX":
        return None, "Map axis order is unsupported for crystallographic Fourier sampling."
    return (nx, ny, nz), ""


def compute_map_quality(
    density: Sequence[float] | np.ndarray,
    grid: Sequence[int],
    cell: Sequence[float],
    axis_order: str,
    context: ValidationContext,
) -> MapQualityMetrics:
    """Transform one periodic map once and derive all source-neutral metrics."""
    values = np.asarray(density, dtype=np.float64).reshape(-1)
    dimensions, reason = _valid_full_cell_map(values, tuple(grid), tuple(cell), axis_order)
    counts = dict(
        n_measured_reflections=len(context.original_measured_reflections),
        n_work_reflections=len(context.work_reflections),
        n_free_reflections=len(context.free_reflections),
        n_triplets=0,
    )
    if dimensions is None:
        return MapQualityMetrics(unavailable_reason=reason, **counts)
    nx, ny, nz = dimensions
    if context.unit_cell is not None and any(
        not math.isclose(float(map_value), float(expected), rel_tol=5.0e-5, abs_tol=5.0e-4)
        for map_value, expected in zip(cell[:6], context.unit_cell)
    ):
        return MapQualityMetrics(
            unavailable_reason="Map unit cell does not match the frozen experimental unit cell.",
            **counts,
        )
    for reflection in context.original_measured_reflections:
        h, k, l = reflection.hkl
        if not (-(nx // 2) <= h <= (nx - 1) // 2 and -(ny // 2) <= k <= (ny - 1) // 2 and -(nz // 2) <= l <= (nz - 1) // 2):
            return MapQualityMetrics(
                unavailable_reason="Map grid undersamples at least one measured reflection.",
                **counts,
            )
    centered = values - float(np.mean(values))
    rms_density = float(math.sqrt(float(np.mean(np.square(centered))))) if centered.size else 0.0
    absolute = np.abs(centered)
    absolute_sum = float(np.sum(absolute))
    entropy = concentration = peakiness = negative_mass = None
    if centered.size > 1 and absolute_sum > 1.0e-15:
        probabilities = absolute[absolute > 0] / absolute_sum
        raw_entropy = -float(np.sum(probabilities * np.log(probabilities)))
        entropy = raw_entropy / math.log(float(centered.size))
        concentration = 1.0 - entropy
        negative_mass = float(np.sum(np.maximum(-centered, 0.0)) / absolute_sum)
    if rms_density > 1.0e-15:
        z = centered / rms_density
        peakiness = float(np.mean(np.power(z, 3)))

    coefficients = np.fft.fftn(centered.reshape((nz, ny, nx)))
    amplitudes = {}
    phases = {}
    for reflection in context.original_measured_reflections:
        h, k, l = reflection.hkl
        coefficient = coefficients[l % nz, k % ny, h % nx]
        amplitudes[reflection.hkl] = float(abs(coefficient))
        phases[reflection.hkl] = float(np.angle(coefficient))

    def amplitude_subset(reflections: Sequence[FrozenReflection]) -> ScaledAmplitudeMetrics:
        usable = [r for r in reflections if r.hkl in amplitudes]
        return scaled_amplitude_metrics(
            [r.amplitude for r in usable],
            [amplitudes[r.hkl] for r in usable],
        )

    measured_metrics = amplitude_subset(context.original_measured_reflections)
    work_metrics = amplitude_subset(context.work_reflections)
    free_metrics = amplitude_subset(context.free_reflections)

    triplet_numerator = triplet_denominator = 0.0
    used_triplets = 0
    for triplet in context.triplet_set:
        if triplet.h not in phases or triplet.k not in phases or triplet.h_plus_k not in phases:
            continue
        delta = phases[triplet.h] + phases[triplet.k] - phases[triplet.h_plus_k]
        triplet_numerator += triplet.weight * math.cos(delta)
        triplet_denominator += triplet.weight
        used_triplets += 1
    triplet_c3 = (
        float(triplet_numerator / triplet_denominator)
        if used_triplets and triplet_denominator > 1.0e-15 else None
    )

    reference_phase_agreement = None
    reference_phases = dict(context.reference_phases)
    phase_terms = []
    phase_weights = []
    measured_by_hkl = {r.hkl: r for r in context.original_measured_reflections}
    for hkl, reference_phase in reference_phases.items():
        if hkl in phases and hkl in measured_by_hkl:
            phase_terms.append(math.cos(phases[hkl] - float(reference_phase)))
            phase_weights.append(max(0.0, measured_by_hkl[hkl].amplitude))
    if phase_terms and sum(phase_weights) > 1.0e-15:
        reference_phase_agreement = float(np.average(phase_terms, weights=phase_weights))

    return MapQualityMetrics(
        reference_phase_agreement=reference_phase_agreement,
        amplitude_rf=measured_metrics.r_factor,
        amplitude_cc=measured_metrics.correlation,
        amplitude_scale=measured_metrics.scale,
        r_work=work_metrics.r_factor,
        # Preserve the existing R_free minimum-sample rule.
        r_free=free_metrics.r_factor if free_metrics.count >= 3 else None,
        cc_work=work_metrics.correlation,
        cc_free=free_metrics.correlation,
        triplet_c3=triplet_c3,
        entropy_normalized=entropy,
        map_concentration=concentration,
        standardized_peakiness=peakiness,
        negative_density_mass=negative_mass,
        n_measured_reflections=measured_metrics.count,
        n_work_reflections=work_metrics.count,
        n_free_reflections=free_metrics.count,
        n_triplets=used_triplets,
    )


@dataclass(frozen=True)
class ResultCandidate:
    cycle: int
    source: str
    map_path: str
    structure_path: str
    metrics: MapQualityMetrics
    usable_map: bool = True
    usable_structure: bool = True
    # Diagnostic only -- the average reflection-intensity change Map Feedback's
    # intensity correction applied feeding INTO this cycle. Cycle-level, not
    # source-specific (both this cycle's Superflip and SharpED candidates carry
    # the same value); never read by recommend_best_result.
    map_feedback_change_percent: Optional[float] = None

    @property
    def label(self) -> str:
        source = "Superflip" if self.source == "superflip" else "SharpED"
        return f"Cycle {self.cycle} · {source}"


@dataclass(frozen=True)
class ResultRecommendation:
    profile: ValidationProfile
    recommended_candidate: Optional[ResultCandidate]
    selected_candidate: Optional[ResultCandidate]
    reason: str

    def with_selected(self, candidate: Optional[ResultCandidate]) -> "ResultRecommendation":
        return replace(self, selected_candidate=candidate)


def _finite_metric(candidate: ResultCandidate, key: str) -> Optional[float]:
    return candidate.metrics.value(key)


def recommend_best_result(
    profile: ValidationProfile | str,
    candidates: Sequence[ResultCandidate],
) -> ResultRecommendation:
    definition = profile_definition(profile)
    primary = definition.primary_metrics[0]
    eligible = [c for c in candidates if c.usable_map and _finite_metric(c, primary.key) is not None]
    if not eligible:
        return ResultRecommendation(
            definition.profile,
            None,
            candidates[0] if candidates else None,
            "Automatic recommendation unavailable. Choose a completed result manually.",
        )

    remaining = list(eligible)
    skipped_metrics = []
    for metric in definition.primary_metrics:
        values = [_finite_metric(candidate, metric.key) for candidate in remaining]
        if any(value is None for value in values):
            # A missing tie-breaker is skipped for the current tied group. It
            # is never treated as zero and never penalizes a valid map.
            skipped_metrics.append(metric.label)
            continue
        finite_values = [float(value) for value in values if value is not None]
        best = max(finite_values) if metric.higher_is_better else min(finite_values)
        remaining = [
            candidate for candidate, value in zip(remaining, finite_values)
            if math.isclose(value, best, rel_tol=1.0e-12, abs_tol=1.0e-12)
        ]
        if len(remaining) == 1:
            break

    complete = [candidate for candidate in remaining if candidate.usable_map and candidate.usable_structure]
    if complete:
        remaining = complete
    earliest_cycle = min(int(candidate.cycle) for candidate in remaining)
    remaining = [candidate for candidate in remaining if int(candidate.cycle) == earliest_cycle]
    source_order = {"superflip": 0, "deblurred": 1, "sharped": 1}
    recommended = min(remaining, key=lambda candidate: (source_order.get(candidate.source, 99), candidate.source))
    reason = definition.recommendation_reason
    if skipped_metrics:
        reason += " Missing tie-breakers were skipped: " + ", ".join(skipped_metrics) + "."
    return ResultRecommendation(
        definition.profile,
        recommended,
        recommended,
        reason,
    )
