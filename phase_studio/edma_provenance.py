"""Read-only provenance for EDMA peak exports, which do not measure ADPs."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path


def edma_export_provenance(coo: Path, cif: Path, m40: Path | None) -> dict:
    """Record original maxima without mistaking density/charge for Biso.

    EDMA_lib.f90, WriteAtom, m40forjana branch writes rho and cc. The
    ordinary atomic-m40 branch writes Biso/(8*pi*pi) instead. These are
    different protocols and must never share a displacement conversion.
    """
    peaks = []
    for line_number, line in enumerate(coo.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        numeric, marker, _comment = line.partition("!")
        values = [float(value) for value in numeric.split()]
        indexed = (len(values) == 5 and values[0] > 1
                   and values[0].is_integer() and values[1] < 1.5)
        if (len(values) not in (4, 9) and not indexed) or not all(math.isfinite(value) for value in values):
            raise ValueError(f"Invalid EDMA maxima record at line {line_number}")
        peaks.append(dict(source_line=line_number, fractional=values[1:4] if indexed else values[:3],
                          center_of_charge=values[3:6] if len(values) == 9 else None,
                          integrated_charge=values[6] if len(values) == 9 else None,
                          peak_density=values[7] if len(values) == 9 else values[4] if indexed else values[3],
                          basin_volume=values[8] if len(values) == 9 else None,
                          edma_error_marker=bool(marker)))
    files = {"coo": coo, "cif": cif}
    if m40 is not None and m40.is_file():
        files["jana_peak_m40"] = m40
    return {
        "schema": 1, "adp": "unavailable: no atomic displacement parameter in EDMA maxima",
        "jana_m40_protocol": "m40forjana yes: continuation = peak density, integrated charge",
        "uiso_interval_for_physical_adp": [0.010, 0.150],
        "lower_clamped": 0, "upper_clamped": 0,
        "files": {key: {"name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                  for key, path in files.items()},
        "raw_peaks": peaks,
    }
