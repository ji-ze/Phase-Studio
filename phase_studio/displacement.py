"""Unit-aware isotropic atomic-displacement conversions and Jana m40 I/O."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from pathlib import Path
import re
import tempfile
from typing import Sequence


EIGHT_PI_SQUARED = 8.0 * math.pi**2
UISO_MIN = 0.010
UISO_MAX = 0.150


class IsotropicDisplacementKind(str, Enum):
    BISO = "Biso"
    UISO = "Uiso"


@dataclass(frozen=True)
class ExportUisoNormalization:
    """One explicitly typed displacement normalized for file export."""

    source_value: float
    source_kind: IsotropicDisplacementKind
    raw_uiso_angstrom2: float
    uiso_angstrom2: float
    clamp_direction: str = ""

    @property
    def was_clamped(self) -> bool:
        return bool(self.clamp_direction)


@dataclass(frozen=True)
class ExportUisoStatistics:
    site_count: int
    raw_min: float
    raw_max: float
    lower_clamped: int
    upper_clamped: int
    unchanged: int
    final_min: float
    final_max: float


def _finite_nonnegative(value: float, name: str) -> float:
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0.0:
        raise ValueError(f"{name} must be a finite non-negative value in angstrom squared")
    return numeric


def biso_to_uiso(biso: float) -> float:
    """Convert Biso (angstrom squared) to Uiso (angstrom squared)."""
    return _finite_nonnegative(biso, "Biso") / EIGHT_PI_SQUARED


def uiso_to_biso(uiso: float) -> float:
    """Convert Uiso (angstrom squared) to Biso (angstrom squared)."""
    return _finite_nonnegative(uiso, "Uiso") * EIGHT_PI_SQUARED


def as_uiso(value: float, source_kind: IsotropicDisplacementKind) -> float:
    """Return canonical Uiso using an explicit source representation."""
    if source_kind is IsotropicDisplacementKind.BISO:
        return biso_to_uiso(value)
    if source_kind is IsotropicDisplacementKind.UISO:
        return _finite_nonnegative(value, "Uiso")
    raise ValueError(f"Unsupported isotropic displacement representation: {source_kind!r}")


def normalize_export_uiso(
    value: float,
    source_kind: IsotropicDisplacementKind,
) -> ExportUisoNormalization:
    """Convert an explicitly typed finite value to Uiso and apply export limits.

    Negative finite source values are permitted at this protective output
    boundary and clamp to ``UISO_MIN``. General physical conversion helpers
    remain strict and reject negative displacement parameters.
    """
    source_value = float(value)
    if not math.isfinite(source_value):
        raise ValueError(f"{source_kind.value} must be finite for structure export")
    if source_kind is IsotropicDisplacementKind.BISO:
        raw_uiso = source_value / EIGHT_PI_SQUARED
    elif source_kind is IsotropicDisplacementKind.UISO:
        raw_uiso = source_value
    else:
        raise ValueError(f"Unsupported isotropic displacement representation: {source_kind!r}")
    if raw_uiso < UISO_MIN:
        final = UISO_MIN
        direction = "lower"
    elif raw_uiso > UISO_MAX:
        final = UISO_MAX
        direction = "upper"
    else:
        final = raw_uiso
        direction = ""
    return ExportUisoNormalization(
        source_value=source_value,
        source_kind=source_kind,
        raw_uiso_angstrom2=raw_uiso,
        uiso_angstrom2=final,
        clamp_direction=direction,
    )


def export_uiso_statistics(
    values: Sequence[float],
    *,
    source_kind: IsotropicDisplacementKind = IsotropicDisplacementKind.UISO,
) -> ExportUisoStatistics:
    """Summarize conversion and clamping for one exported atomic model."""
    normalized = [normalize_export_uiso(value, source_kind) for value in values]
    if not normalized:
        raise ValueError("At least one displacement value is required for export statistics")
    raw = [item.raw_uiso_angstrom2 for item in normalized]
    final = [item.uiso_angstrom2 for item in normalized]
    lower = sum(item.clamp_direction == "lower" for item in normalized)
    upper = sum(item.clamp_direction == "upper" for item in normalized)
    return ExportUisoStatistics(
        site_count=len(normalized), raw_min=min(raw), raw_max=max(raw),
        lower_clamped=lower, upper_clamped=upper,
        unchanged=len(normalized) - lower - upper,
        final_min=min(final), final_max=max(final),
    )


@dataclass(frozen=True)
class JanaM40IsotropicSite:
    label: str
    fractional: tuple[float, float, float]
    source_value: float
    source_kind: IsotropicDisplacementKind
    raw_uiso_angstrom2: float
    uiso_angstrom2: float
    clamp_direction: str = ""


def parse_edma_coo_isotropic_displacements(
    path: Path,
    *,
    source_kind: IsotropicDisplacementKind,
) -> list[JanaM40IsotropicSite]:
    """Read EDMA peak coordinates and their Biso-representation field.

    EDMA's documented nine-column maxima table is ``xyz``, ``xyz_coc``,
    charge, density/B-scale isotropic value, and volume. The eighth column is
    the same source quantity EDMA places in its m40 isotropic continuation
    field. Keeping the representation explicit prevents magnitude-based unit
    guessing and supplies the full peak set used by Phase Studio CIF/PDB.
    """
    records: list[JanaM40IsotropicSite] = []
    for line_number, raw in enumerate(Path(path).read_text(encoding="utf-8", errors="strict").splitlines(), start=1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        try:
            values = [float(token) for token in raw.split()]
        except ValueError as exc:
            raise ValueError(f"Invalid EDMA coordinate record at line {line_number}: {path}") from exc
        if len(values) < 9:
            raise ValueError(f"Incomplete EDMA coordinate record at line {line_number}: {path}")
        normalized = normalize_export_uiso(values[7], source_kind)
        records.append(
            JanaM40IsotropicSite(
                label=f"peak-{len(records) + 1}",
                fractional=(values[0], values[1], values[2]),
                source_value=normalized.source_value,
                source_kind=source_kind,
                raw_uiso_angstrom2=normalized.raw_uiso_angstrom2,
                uiso_angstrom2=normalized.uiso_angstrom2,
                clamp_direction=normalized.clamp_direction,
            )
        )
    return records


_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?"
_SITE_LINE = re.compile(
    r"^\s*(?P<label>\S+)\s+\d+\s+\d+\s+"
    + _NUMBER + r"\s*(?P<x>" + _NUMBER + r")\s*"
    r"(?P<y>" + _NUMBER + r")\s*(?P<z>" + _NUMBER + r")\s*$"
)
_CONTINUATION = re.compile(
    r"^(?P<leading>\s*)(?P<value>" + _NUMBER + r")"
    r"(?P<rest>\s+" + _NUMBER + r"(?:\s+.*)?\s*)$"
)


def normalize_jana_m40_isotropic_displacements(
    path: Path,
    *,
    source_kind: IsotropicDisplacementKind,
) -> list[JanaM40IsotropicSite]:
    """Normalize an m40 atom continuation field to Uiso exactly once.

    EDMA ``writem40`` output declares the first value on the continuation
    record in the Biso representation. Jana's corresponding isotropic field
    is Uiso. The caller must state the source representation; values are never
    classified from their magnitude.
    """
    m40 = Path(path)
    lines = m40.read_text(encoding="utf-8", errors="strict").splitlines(keepends=True)
    if not lines:
        raise ValueError(f"Empty Jana m40 file: {m40}")
    try:
        expected_sites = int(lines[0].split()[0])
    except (IndexError, ValueError) as exc:
        raise ValueError(f"Invalid Jana m40 site-count header: {m40}") from exc

    records: list[JanaM40IsotropicSite] = []
    output = list(lines)
    index = 0
    while index < len(lines):
        match = _SITE_LINE.match(lines[index].rstrip("\r\n"))
        if match is None:
            index += 1
            continue
        continuation_index = index + 1
        if continuation_index >= len(lines):
            raise ValueError(f"Missing isotropic displacement record for {match.group('label')} in {m40}")
        newline = "\r\n" if lines[continuation_index].endswith("\r\n") else ("\n" if lines[continuation_index].endswith("\n") else "")
        continuation = _CONTINUATION.match(lines[continuation_index].rstrip("\r\n"))
        if continuation is None:
            raise ValueError(f"Invalid isotropic displacement record for {match.group('label')} in {m40}")
        normalized = normalize_export_uiso(float(continuation.group("value")), source_kind)
        source_value = normalized.source_value
        uiso = normalized.uiso_angstrom2
        output[continuation_index] = (
            f"{continuation.group('leading')}{uiso:.6f}{continuation.group('rest')}{newline}"
        )
        records.append(
            JanaM40IsotropicSite(
                label=match.group("label"),
                fractional=(float(match.group("x")), float(match.group("y")), float(match.group("z"))),
                source_value=source_value,
                source_kind=source_kind,
                raw_uiso_angstrom2=normalized.raw_uiso_angstrom2,
                uiso_angstrom2=uiso,
                clamp_direction=normalized.clamp_direction,
            )
        )
        index += 2

    if len(records) != expected_sites:
        raise ValueError(
            f"Jana m40 declares {expected_sites} sites but {len(records)} complete isotropic records were found: {m40}"
        )

    if source_kind is IsotropicDisplacementKind.BISO or any(
        record.clamp_direction for record in records
    ):
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", delete=False, dir=m40.parent,
            prefix=m40.name + ".", suffix=".tmp",
        ) as stream:
            temporary = Path(stream.name)
            stream.writelines(output)
        temporary.replace(m40)
    return records


def match_uiso_by_fractional_coordinate(
    fractional: Sequence[float],
    records: Sequence[JanaM40IsotropicSite],
    *,
    tolerance: float = 2.0e-6,
) -> float:
    """Match an EDMA coordinate to its explicitly normalized m40 site."""
    target = tuple(float(value) % 1.0 for value in fractional)
    matches: list[tuple[float, JanaM40IsotropicSite]] = []
    for record in records:
        source = tuple(value % 1.0 for value in record.fractional)
        delta = tuple(min(abs(a - b), 1.0 - abs(a - b)) for a, b in zip(target, source))
        distance = math.sqrt(sum(value * value for value in delta))
        if distance <= tolerance:
            matches.append((distance, record))
    if not matches:
        raise ValueError(f"No normalized m40 displacement matches fractional coordinate {target!r}")
    matches.sort(key=lambda item: item[0])
    # Internal atomic sites retain the canonical raw Uiso. File writers apply
    # the bounded export policy without changing scientific source values.
    return matches[0][1].raw_uiso_angstrom2
