"""Origin-preserving conversion guards for an already completed Jana density."""
from __future__ import annotations

import math
import struct
import time
from pathlib import Path
import numpy as np

from phase_studio.inflip_io import first_token
from phase_studio.xplor_io import read_xplor_map


def origin_preserving_conversion_lines(lines: list[str], source_map: Path) -> list[str]:
    """Retain the selected map frame; never search, average or derive symmetry.

    EDMA extracts coordinates in this map's frame. A second symmetry search
    during format conversion moves the density without moving those sites.
    Superflip's default voxel size also resamples the map unless explicit.
    """
    source = read_xplor_map(source_map)
    grid = source.grid
    if source.axis_order != "ZYX" or any(
        grid[i + 1] != 0 or grid[i + 2] != grid[i] - 1 for i in (0, 3, 6)
    ):
        raise ValueError("Jana density conversion requires a full-cell zero-start ZYX map; unsupported map frame was not transformed")
    removed = {"searchsymmetry", "derivesymmetry", "voxel", "referencefile", "referenceformat"}
    output = [line for line in lines if first_token(line) not in removed]
    output.extend([
        "modelformat xplor", "searchsymmetry no", "derivesymmetry no",
        f"voxel {grid[0]} {grid[3]} {grid[6]}",
    ])
    return output


def validate_converted_density(source_map: Path, converted_map: Path) -> dict:
    """Reject shifted, resampled, averaged or scaled output before publication."""
    source = read_xplor_map(source_map)
    converted = read_xplor_map(converted_map)
    if source.grid != converted.grid or source.axis_order != converted.axis_order:
        raise ValueError("Jana conversion changed the selected density grid or axis setting")
    if not np.allclose(source.cell, converted.cell, rtol=0, atol=1e-4):
        raise ValueError("Jana conversion changed the selected density unit cell")
    a, b = source.data, converted.data
    if not np.all(np.isfinite(a)) or not np.all(np.isfinite(b)):
        raise ValueError("Jana density contains nonfinite values")
    norm = float(np.sqrt(np.sum(a * a)))
    error = float(np.sqrt(np.sum((a - b) ** 2))) / max(norm, 1e-30)
    # Both files carry five-digit mantissas. FFT/serialization noise is
    # expected, but a crystallographic shift or symmetry average is not.
    if error > 5e-4:
        raise ValueError(f"Jana conversion changed selected density values/frame (relative L2 {error:.6g})")
    correlation = float(np.corrcoef(a, b)[0, 1]) if np.std(a) > 0 and np.std(b) > 0 else 1.0
    if not math.isfinite(correlation):
        raise ValueError("Jana density equivalence could not be validated")
    return {
        "method": "Superflip origin-preserving format conversion",
        "fractional_origin_shift": [0.0, 0.0, 0.0],
        "grid": list(source.grid), "cell": list(source.cell),
        "relative_l2": error, "correlation": correlation,
        "source_mean": float(a.mean()), "output_mean": float(b.mean()),
        "source_sigma": float(a.std()), "output_sigma": float(b.std()),
    }


def validate_jana_density_pair(xplor_path: Path, m81_path: Path, m80_path: Path) -> dict:
    """Verify the installed Superflip's Jana direct-record and Fourier conventions.

    m81 records use nx*ny float32 values; the first record is the grid header.
    m80's calculated complex coefficient is columns 8/9 (one-based), using
    the positive exponential convention and cell-volume normalization.
    These conventions are pinned by actual installed-binary probes.
    """
    started = time.perf_counter()
    xmap = read_xplor_map(xplor_path)
    xplor_read_seconds = time.perf_counter() - started
    started = time.perf_counter()
    nx, ny, nz = (xmap.grid[i] for i in (0, 3, 6))
    with m81_path.open('rb') as stream:
        header = stream.read(28)
    dims = struct.unpack("<7i", header)
    if dims[:3] != (nx, ny, nz) or dims[6] != nx * ny:
        raise ValueError("Jana m81 grid header does not match the converted density")
    binary = np.memmap(m81_path, mode="r", dtype="<f4", offset=4 * nx * ny, shape=(nx * ny * nz,))
    binary_error = float(np.sqrt(np.sum((binary - xmap.data) ** 2))) / max(float(np.linalg.norm(xmap.data)), 1e-30)
    if binary_error > 5e-4:
        raise ValueError(f"Jana m81 disagrees with converted XPLOR (relative L2 {binary_error:.6g})")
    m81_validation_seconds = time.perf_counter() - started
    started = time.perf_counter()
    a,b,c,alpha,beta,gamma = xmap.cell
    ca,cb,cg = (math.cos(math.radians(angle)) for angle in (alpha,beta,gamma))
    volume = a*b*c*math.sqrt(1-ca*ca-cb*cb-cg*cg+2*ca*cb*cg)
    spectrum = np.fft.fftn(xmap.data.reshape(nz,ny,nx)).conjugate() * (volume / xmap.data.size)
    import re
    number = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+-]?\d+)?")
    errors, expected_values = [], []
    with m80_path.open(encoding="ascii") as stream:
        for index, line in enumerate(stream):
            if index >= 256:
                break
            values = [float(token.replace('D','E')) for token in number.findall(line)]
            if len(values) < 9:
                raise ValueError("Jana m80 has an incomplete Fourier record")
            h,k,l = (int(value) for value in values[:3])
            expected = spectrum[l % nz, k % ny, h % nx]
            errors.append(abs(complex(values[7], values[8]) - expected))
            expected_values.append(abs(expected))
    if not errors:
        raise ValueError("Jana m80 has no Fourier records")
    fourier_error = float(max(errors) / max(max(expected_values), 1e-30))
    if fourier_error > 5e-4:
        raise ValueError(f"Jana m80 phases/amplitudes disagree with m81 density (relative error {fourier_error:.6g})")
    return {"m81_relative_l2": binary_error, "m80_relative_error": fourier_error,
            "pair_xplor_read_seconds": xplor_read_seconds,
            "m81_validation_seconds": m81_validation_seconds,
            "m80_fft_and_check_seconds": time.perf_counter() - started,
            "m80_checked_coefficients": len(errors), "fourier_convention": "positive exponential, volume normalized"}
