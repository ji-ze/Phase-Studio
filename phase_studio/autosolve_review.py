"""Phase Studio 2.0.2 guided Autosolve: shared phase search, one explicit
Structure prediction, and a Review / refinement state.

Pure policy and bookkeeping -- no Qt, no I/O beyond hashing a map file for
provenance, no scientific computation. Every scientific step is an existing
production function called by IterativeSuperflipPipelineQtGUI:

* the shared phase search is the ordinary per-cycle loop
  (``_run_pipeline_cycles``) with SharpED model PHASE_SEARCH_MODEL and the
  existing ``deblurred_edma_cif`` feed-forward (SharpED map -> EDMA ->
  structure -> next Superflip model);
* the Structure prediction is one SharpED inference (PREDICTION_MODEL) on the
  best completed Superflip map, then EDMA -- the same stage functions a
  cycle uses;
* threshold tuning reruns EDMA only, on the unchanged canonical map;
* ranking is ``map_quality.recommend_best_result`` / ``autosolve_policy``,
  unmodified.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from phase_studio.map_quality import MapQualityMetrics, ResultCandidate

# ----- Exact SharpED models (authoritative names, exact match only) -------
PHASE_SEARCH_MODEL = "koala phase boost 2"
PREDICTION_MODEL = "koala model progressive"
REQUIRED_SHARPED_MODELS = (PHASE_SEARCH_MODEL, PREDICTION_MODEL)

# ----- EDMA thresholds (multiples of the map sigma) -----------------------
# Guided Autosolve defaults: 1.0 sigma on BOTH sides -- Superflip /
# Charge-flipping solution and every SharpED-derived structure (the phase-search
# feed-forward and the first Structure prediction).
OBSERVED_THRESHOLD_SIGMA = 1.0
PREDICTED_THRESHOLD_SIGMA = 1.0
# Interactive range and variable step: 0.2 sigma at/above 0.8 sigma, 0.1
# sigma below it (down: 1.0 -> 0.8 -> 0.7 ... 0.3; up: 0.3 ... 0.7 -> 0.8 ->
# 1.0 ... 3.0). Values are kept on the 0.1-sigma grid.
THRESHOLD_MIN_SIGMA = 0.1
THRESHOLD_MAX_SIGMA = 3.0
THRESHOLD_COARSE_STEP_SIGMA = 0.2
THRESHOLD_FINE_STEP_SIGMA = 0.1
THRESHOLD_VERY_FINE_STEP_SIGMA = 0.05
THRESHOLD_FINE_BELOW_SIGMA = 0.8
THRESHOLD_VERY_FINE_BELOW_SIGMA = 0.3
# Backward-compatible name for the coarse step.
THRESHOLD_STEP_SIGMA = THRESHOLD_COARSE_STEP_SIGMA

# ----- Refinement --------------------------------------------------------
INITIAL_SEARCH_CYCLES = 5
REFINEMENT_BLOCK_CYCLES = 3

ROLE_OBSERVED = "observed"
ROLE_PREDICTED = "predicted"
ROLE_SOURCE = {ROLE_OBSERVED: "superflip", ROLE_PREDICTED: "deblurred"}
ROLE_TITLE = {ROLE_OBSERVED: "Charge-flipping solution", ROLE_PREDICTED: "Structure prediction"}

# Guided-workflow stages (IterativeSuperflipPipelineQtGUI._autosolve_stage).
STAGE_SEARCH = "search"
STAGE_PREDICTING = "predicting"
STAGE_PREDICTION_FAILED = "prediction_failed"
# Initial Predicted-model tuning: only the Structure prediction is tunable,
# its only decision is "Refine 3 cycles"; nothing can be passed yet.
STAGE_TUNING = "tuning"
# Final dual Review (after the first refinement): both panels, four actions.
STAGE_REVIEW = "review"
REVIEW_STAGES = (STAGE_TUNING, STAGE_REVIEW)
REFINE_LABEL = "Refine 3 cycles"
RECALCULATE_LABEL = "Recalculate"
STAGE_REFINEMENT = "refinement"
STAGE_CORRECTION = "map_feedback"

CORRECTION_POWDER = "powder"
CORRECTION_INTENSITY = "intensity"
CORRECTION_LABELS = {
    CORRECTION_POWDER: "Powder repartitioning",
    CORRECTION_INTENSITY: "Correct suspect intensities",
}

_EPS = 1.0e-9


def missing_required_models(catalog_models: Iterable[str]) -> List[str]:
    """Required models absent from the live catalog -- EXACT string match,
    never fuzzy, never a fallback to the server default."""
    available = {str(model) for model in catalog_models}
    return [model for model in REQUIRED_SHARPED_MODELS if model not in available]


def goal_source(option: str) -> str:
    """The candidate stream a goal judges improvement on: Charge-flipping solution
    (Superflip) for "Solve the phase problem", Structure prediction (SharpED)
    for "Predict the structure model"."""
    return "superflip" if str(option).strip().upper() != "B" else "deblurred"


def normalize_sigma(value: float) -> float:
    """Normalize the variable 0.2/0.1/0.05-sigma grid without float drift."""
    return round(float(value) + 0.0, 2) + 0.0


def stepped_threshold(value: float, add_atoms: bool) -> Optional[float]:
    """+ atoms LOWERS the threshold (more atoms), - atoms RAISES it (fewer):
    0.2 sigma at/above 0.8, 0.1 from 0.3 to below 0.8, and 0.05 below
    0.3. None when the step would leave 0.10-3.0 sigma."""
    current = normalize_sigma(value)
    if add_atoms:
        if current > THRESHOLD_FINE_BELOW_SIGMA + _EPS:
            step = THRESHOLD_COARSE_STEP_SIGMA
        elif current > THRESHOLD_VERY_FINE_BELOW_SIGMA + _EPS:
            step = THRESHOLD_FINE_STEP_SIGMA
        else:
            step = THRESHOLD_VERY_FINE_STEP_SIGMA
        candidate = normalize_sigma(current - step)
    else:
        if current < THRESHOLD_VERY_FINE_BELOW_SIGMA - _EPS:
            step = THRESHOLD_VERY_FINE_STEP_SIGMA
        elif current < THRESHOLD_FINE_BELOW_SIGMA - _EPS:
            step = THRESHOLD_FINE_STEP_SIGMA
        else:
            step = THRESHOLD_COARSE_STEP_SIGMA
        candidate = normalize_sigma(current + step)
    if candidate < THRESHOLD_MIN_SIGMA - _EPS or candidate > THRESHOLD_MAX_SIGMA + _EPS:
        return None
    return candidate


def can_add_atoms(value: float) -> bool:
    return stepped_threshold(value, add_atoms=True) is not None


def can_remove_atoms(value: float) -> bool:
    return stepped_threshold(value, add_atoms=False) is not None


def format_sigma(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{float(value):.2f} σ"


def file_sha256(path: Optional[Path]) -> str:
    if path is None or not Path(path).is_file():
        return ""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass
class PredictionRecord:
    """The dedicated first Structure prediction: one PREDICTION_MODEL SharpED
    inference on the best completed Superflip map of `cycle`."""

    cycle: int
    observed_map: Path
    map_path: Path
    edma_cif: Path
    edma_sigma: float
    sharped_model: str
    quality: Optional[MapQualityMetrics] = None
    usable_structure: bool = True
    edma_asu_composition: str = ""

    def candidate(self) -> ResultCandidate:
        return ResultCandidate(
            cycle=int(self.cycle),
            source="deblurred",
            map_path=str(self.map_path),
            structure_path=str(self.edma_cif),
            metrics=self.quality if self.quality is not None else MapQualityMetrics(),
            usable_map=Path(self.map_path).is_file(),
            usable_structure=bool(self.usable_structure),
            edma_sigma=float(self.edma_sigma),
            sharped_model=self.sharped_model,
            edma_asu_composition=self.edma_asu_composition,
        )


@dataclass
class ReviewPanel:
    """One Review panel's current, user-tunable state. The map never changes
    here; only the EDMA structure extracted from it at `threshold_sigma`."""

    role: str
    cycle: int
    map_path: Path
    current_cif: Path
    threshold_sigma: float
    sharped_model: str = ""
    edma_asu_composition: str = ""
    superflip_initialization: str = ""
    reflection_input_provenance: str = ""
    # The structure recorded by the workflow itself (before any tuning).
    recorded_cif: Optional[Path] = None
    recorded_sigma: Optional[float] = None
    # Set while an EDMA-only recalculation is running for this panel.
    busy_sigma: Optional[float] = None
    error: str = ""
    history: List[float] = field(default_factory=list)

    @property
    def source(self) -> str:
        return ROLE_SOURCE[self.role]

    @property
    def title(self) -> str:
        return ROLE_TITLE[self.role]

    @property
    def busy(self) -> bool:
        return self.busy_sigma is not None

    def technical_label(self) -> str:
        if self.role == ROLE_OBSERVED:
            return f"Superflip · EDMA {format_sigma(self.threshold_sigma)}"
        model = self.sharped_model or PREDICTION_MODEL
        return f"SharpED · {model} · EDMA {format_sigma(self.threshold_sigma)}"


def block_decision_candidates(
    candidates: Sequence[ResultCandidate], source: str,
) -> List[ResultCandidate]:
    return [candidate for candidate in candidates if candidate.source == source]
