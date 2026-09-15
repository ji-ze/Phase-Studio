"""Pure resolution of editable input values into one workflow input context."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Collection, Optional


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

NO_EXTERNAL_HKL = "__phase_studio_no_external_hkl_selected__"
USE_HKL_FROM_INFLIP = "__phase_studio_use_hkl_from_inflip__"
NO_EXTERNAL_REFERENCE = "__phase_studio_no_external_reference_cif_selected__"
USE_REFERENCE_FROM_INFLIP = "__phase_studio_use_reference_from_inflip__"


def normalize_metadata_source(value: str) -> str:
    text = str(value or "").strip().lower()
    if text in {METADATA_SOURCE_INFLIP, "inflip", "jana", "jana .inflip", "jana2020 .inflip"}:
        return METADATA_SOURCE_INFLIP
    if text in {METADATA_SOURCE_REFERENCE, "reference", "reference file", "reference structure"}:
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


def optional_resolved_path(value: str) -> Optional[Path]:
    text = str(value or "").strip()
    return Path(text).expanduser().resolve() if text else None


def active_jana_inflip(input_mode: str, value: str) -> Optional[Path]:
    mode = normalize_input_source_mode(input_mode)
    return optional_resolved_path(value) if mode in {INPUT_MODE_INFLIP, INPUT_MODE_INFLIP_OVERRIDES} else None


@dataclass(frozen=True)
class ResolvedRunInputs:
    """Resolved path portion of RunConfig; it never owns mutable GUI state."""

    input_source_mode: str
    hkl: Path
    jana_inflip: Optional[Path]
    external_reference_file: Optional[Path]
    reference_cif: Path
    superflip_referencefile: Optional[Path]
    first_cycle_modelfile: Optional[Path]
    jana_return_to_jana: bool


def resolve_run_inputs(
    *,
    input_mode: str,
    hkl_value: str,
    jana_inflip_value: str,
    reference_value: str,
    first_model_value: str,
    launched_from_jana_wizard: bool,
    structure_suffixes: Collection[str],
) -> ResolvedRunInputs:
    mode = normalize_input_source_mode(input_mode)
    inflip = active_jana_inflip(mode, jana_inflip_value)
    external_reference = optional_resolved_path(reference_value)
    first_model = optional_resolved_path(first_model_value)
    hkl = optional_resolved_path(hkl_value) or Path(NO_EXTERNAL_HKL).resolve()
    reference_cif = (
        external_reference
        if external_reference is not None and external_reference.suffix.lower() in structure_suffixes
        else Path(NO_EXTERNAL_REFERENCE).resolve()
    )
    superflip_reference = external_reference
    if mode == INPUT_MODE_INFLIP and external_reference is None:
        hkl = Path(USE_HKL_FROM_INFLIP).resolve()
        reference_cif = Path(USE_REFERENCE_FROM_INFLIP).resolve()
        superflip_reference = None
    return ResolvedRunInputs(
        input_source_mode=mode,
        hkl=hkl,
        jana_inflip=inflip,
        external_reference_file=external_reference,
        reference_cif=reference_cif,
        superflip_referencefile=superflip_reference,
        first_cycle_modelfile=first_model,
        jana_return_to_jana=bool(inflip is not None and launched_from_jana_wizard),
    )


def default_metadata_source(
    input_mode: str, reference_value: str, structure_suffixes: Collection[str],
) -> str:
    mode = normalize_input_source_mode(input_mode)
    if mode in {INPUT_MODE_INFLIP, INPUT_MODE_INFLIP_OVERRIDES}:
        return METADATA_SOURCE_INFLIP
    reference = optional_resolved_path(reference_value)
    if reference is not None and reference.is_file() and reference.suffix.lower() in structure_suffixes:
        return METADATA_SOURCE_REFERENCE
    return METADATA_SOURCE_MANUAL


def reconcile_metadata_source(
    requested_source: str,
    input_mode: str,
    jana_inflip_value: str,
    reference_value: str,
    structure_suffixes: Collection[str],
) -> str:
    source = normalize_metadata_source(requested_source)
    inflip = active_jana_inflip(input_mode, jana_inflip_value)
    reference = optional_resolved_path(reference_value)
    inflip_available = bool(inflip is not None and inflip.is_file())
    reference_available = bool(
        reference is not None and reference.is_file()
        and reference.suffix.lower() in structure_suffixes
    )
    if source == METADATA_SOURCE_INFLIP and inflip_available:
        return source
    if source == METADATA_SOURCE_REFERENCE and reference_available:
        return source
    if source == METADATA_SOURCE_MANUAL:
        return source
    if reference_available:
        return METADATA_SOURCE_REFERENCE
    if inflip_available:
        return METADATA_SOURCE_INFLIP
    return METADATA_SOURCE_MANUAL


def input_control_availability(input_mode: str, metadata_source: str) -> dict[str, bool]:
    mode = normalize_input_source_mode(input_mode)
    return {
        "jana_inflip": mode in {INPUT_MODE_INFLIP, INPUT_MODE_INFLIP_OVERRIDES}
        or normalize_metadata_source(metadata_source) == METADATA_SOURCE_INFLIP,
        "hkl": mode in {INPUT_MODE_INFLIP_OVERRIDES, INPUT_MODE_EXTERNAL},
        "reference_cif": True,
        "reflection_data_mode": mode != INPUT_MODE_INFLIP,
    }


def jana_handoff_available(
    *, results_available: bool, run_inflip: Optional[Path], launched_from_jana: bool, launch_mode: str,
) -> bool:
    return bool(
        results_available and run_inflip is not None and launched_from_jana
        and launch_mode in {"full_configuration", "phase_recycling"}
    )


def uses_embedded_hkl(path: Path) -> bool:
    return Path(path).name in {NO_EXTERNAL_HKL, USE_HKL_FROM_INFLIP}
