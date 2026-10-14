"""Shared, size-aware SharpED map submission (Phase Studio 2.0.0).

One authoritative boundary for every caller that sends an electron-density
map to the SharpED server: maps at or below the configured upload limit are
sent exactly as before, unchanged. Maps over the limit are tiled into
equal-size, overlapping, periodic tiles of the full P1 unit cell, inferred
one at a time, and reassembled with Gaussian-weighted overlap blending onto
the ORIGINAL, unchanged grid. The map's own voxel/grid resolution is never
coarsened to satisfy the upload limit -- that is the whole point of this
module existing.

Gaussian-weighted overlap blending is conceptually equivalent to MONAI's
"gaussian" sliding-window inference mode, implemented here from scratch in
plain NumPy; MONAI is not a dependency and importing it is not required for
this feature.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Callable, Dict, List, Tuple

import numpy as np

from phase_studio.xplor_io import XplorMap, read_xplor_map, write_xplor_map

# Single authoritative overlap fraction for every tiling path in the
# application -- no per-workflow override.
OVERLAP_FRACTION = 0.10
# Per the Phase Studio 2.0.0 spec: center_i=(N_i-1)/2, sigma_i=0.125*N_i.
GAUSSIAN_SIGMA_SCALE = 0.125
# Matches app.py's own estimate_xplor_text_bytes per-value cost for this
# text map format (~12-13 bytes/value plus per-layer overhead).
BYTES_PER_VOXEL_ESTIMATE = 13.2

_GAUSSIAN_CACHE: Dict[Tuple[Tuple[int, int, int], float], np.ndarray] = {}


def sharped_upload_limit_bytes(max_upload_mb: float) -> int:
    return int(max(0.0, float(max_upload_mb or 0.0)) * 1_000_000.0)


def decide_sharped_submission(map_path: Path, max_upload_mb: float) -> str:
    """"direct" (send exactly as today, unchanged) or "tiled" (must go
    through tiled inference). A non-positive limit means "no limit
    configured" -- always direct."""
    limit_bytes = sharped_upload_limit_bytes(max_upload_mb)
    if limit_bytes <= 0:
        return "direct"
    try:
        size = Path(map_path).stat().st_size
    except OSError:
        return "direct"
    return "direct" if size <= limit_bytes else "tiled"


def gaussian_importance_map(shape: Tuple[int, int, int], sigma_scale: float = GAUSSIAN_SIGMA_SCALE) -> np.ndarray:
    """Per-axis Gaussian outer product, cached per (shape, sigma_scale) so a
    tile shape's weight is computed once and reused. Only numerically tiny
    values are clamped upward; the profile itself is never flattened."""
    key = (tuple(int(n) for n in shape), float(sigma_scale))
    cached = _GAUSSIAN_CACHE.get(key)
    if cached is not None:
        return cached
    axes = []
    for n in shape:
        n = int(n)
        center = (n - 1) / 2.0
        sigma = max(1e-6, sigma_scale * n)
        x = np.arange(n, dtype=np.float64)
        axes.append(np.exp(-0.5 * ((x - center) / sigma) ** 2))
    weight = axes[0][:, None, None] * axes[1][None, :, None] * axes[2][None, None, :]
    weight = np.clip(weight, 1e-6, None)
    _GAUSSIAN_CACHE[key] = weight
    return weight


def tile_shape_for_budget(
    full_shape: Tuple[int, int, int],
    max_upload_mb: float,
    bytes_per_voxel: float = BYTES_PER_VOXEL_ESTIMATE,
) -> Tuple[int, int, int]:
    """Largest near-cube tile shape (each axis capped at the corresponding
    full-map axis) whose serialized size fits the upload budget with
    headroom -- not a hardcoded/model-specific size, since none is
    documented for the SharpED API; derived purely from the same upload
    budget that already governs direct submission."""
    limit_bytes = sharped_upload_limit_bytes(max_upload_mb)
    if limit_bytes <= 0:
        return tuple(int(n) for n in full_shape)
    target_bytes = int(limit_bytes * 0.86)
    max_voxels = max(1, int(target_bytes / max(1e-9, bytes_per_voxel)))
    side = max(1, int(math.floor(max_voxels ** (1.0 / 3.0))))
    return tuple(min(int(n), side) for n in full_shape)


def tile_starts(full_extent: int, tile_extent: int, overlap_fraction: float = OVERLAP_FRACTION) -> List[int]:
    """Deterministic periodic tile-start coordinates covering [0,
    full_extent) with equal-size tiles (`tile_extent` voxels each,
    overlap_fraction overlap). The last tile always wraps periodically
    rather than shrinking, so every tile has identical dimensions."""
    full_extent = int(full_extent)
    tile_extent = int(tile_extent)
    if tile_extent >= full_extent:
        return [0]
    overlap_voxels = max(1, round(overlap_fraction * tile_extent))
    step = max(1, tile_extent - overlap_voxels)
    starts = list(range(0, full_extent, step))
    # Guarantee gap-free periodic coverage: the last tile must reach at
    # least to full_extent (wrapping periodically covers the remainder).
    if starts[-1] + tile_extent < full_extent:
        starts.append(max(0, full_extent - tile_extent))
    return starts


def plan_tiles(
    full_shape: Tuple[int, int, int],
    tile_shape: Tuple[int, int, int],
    overlap_fraction: float = OVERLAP_FRACTION,
) -> List[Tuple[int, int, int]]:
    """All (start_0, start_1, start_2) tile origins covering the full
    periodic grid with equal-size, overlap_fraction-overlapping tiles."""
    per_axis = [tile_starts(full_shape[axis], tile_shape[axis], overlap_fraction) for axis in range(3)]
    return [
        (s0, s1, s2)
        for s0 in per_axis[0]
        for s1 in per_axis[1]
        for s2 in per_axis[2]
    ]


def extract_periodic_tile(data3d: np.ndarray, start: Tuple[int, int, int], shape: Tuple[int, int, int]) -> np.ndarray:
    """Extract a periodic (wrapped) tile from a full 3D array. Never
    zero-pads a crystallographic boundary -- density crossing a cell edge
    wraps in from the opposite side, since the grid is periodic."""
    idx = [np.arange(s, s + n) % full for s, n, full in zip(start, shape, data3d.shape)]
    return data3d[np.ix_(*idx)]


class PeriodicAccumulator:
    """Streaming Gaussian-weighted accumulation of tile predictions back
    onto a full periodic grid. Only one tile's prediction is held at a
    time by the caller; this just accumulates the running weighted sums."""

    def __init__(self, full_shape: Tuple[int, int, int]) -> None:
        self.full_shape = tuple(int(n) for n in full_shape)
        self.density_sum = np.zeros(self.full_shape, dtype=np.float64)
        self.weight_sum = np.zeros(self.full_shape, dtype=np.float64)

    def add(self, start: Tuple[int, int, int], tile_prediction: np.ndarray) -> None:
        shape = tuple(int(n) for n in tile_prediction.shape)
        weight = gaussian_importance_map(shape)
        idx = [np.arange(s, s + n) % full for s, n, full in zip(start, shape, self.full_shape)]
        grid = np.ix_(*idx)
        self.density_sum[grid] += weight * tile_prediction
        self.weight_sum[grid] += weight

    def finalize(self) -> np.ndarray:
        if np.any(self.weight_sum <= 0):
            raise RuntimeError("Large-map tiling left at least one voxel uncovered by any tile.")
        return self.density_sum / self.weight_sum


def _tile_cell(
    full_cell: Tuple[float, float, float, float, float, float],
    tile_shape: Tuple[int, int, int],
    full_shape: Tuple[int, int, int],
) -> Tuple[float, float, float, float, float, float]:
    """A tile's own unit-cell lengths, scaled from the full map's cell by
    the fraction of the grid the tile covers on each axis -- preserves the
    map's real voxel spacing exactly; angles are unchanged."""
    a, b, c, alpha, beta, gamma = full_cell
    nz, ny, nx = full_shape
    tz, ty, tx = tile_shape
    return (a * (tx / nx), b * (ty / ny), c * (tz / nz), alpha, beta, gamma)


def run_tiled_sharped_inference(
    input_map_path: Path,
    output_map_path: Path,
    max_upload_mb: float,
    infer_tile: Callable[[Path, Path], None],
    log: Callable[[str], None] = lambda _msg: None,
) -> None:
    """Tile `input_map_path` (a full periodic XPLOR map) into equal-size,
    overlapping periodic tiles sized to fit `max_upload_mb`, call
    `infer_tile(tile_input_path, tile_output_path)` once per tile (expected
    to write a same-shape XPLOR map to tile_output_path -- this is where the
    caller actually talks to the SharpED server), and reassemble the result
    with Gaussian-weighted overlap blending onto the ORIGINAL grid at
    output_map_path. Processes one tile at a time and releases its temporary
    files before starting the next, so memory stays bounded regardless of
    map size."""
    source = read_xplor_map(input_map_path)
    nx, ny, nz = int(source.grid[0]), int(source.grid[3]), int(source.grid[6])
    full_shape = (nz, ny, nx)  # z-major, matching this app's own reshape convention
    data3d = np.asarray(source.data, dtype=np.float64).reshape(full_shape)
    tile_shape = tile_shape_for_budget(full_shape, max_upload_mb)
    starts = plan_tiles(full_shape, tile_shape)
    log(
        f"[SharpED] Large map · processing {len(starts)} periodic "
        f"tile(s) of {tile_shape[2]}x{tile_shape[1]}x{tile_shape[0]} voxels "
        f"({int(OVERLAP_FRACTION * 100)}% overlap) instead of coarsening the map."
    )
    accumulator = PeriodicAccumulator(full_shape)
    tile_dir = output_map_path.parent / f"{output_map_path.stem}_tiles"
    tile_dir.mkdir(parents=True, exist_ok=True)
    try:
        for index, start in enumerate(starts):
            tile_data = extract_periodic_tile(data3d, start, tile_shape)
            tile_in = XplorMap(
                title=f"{source.title} tile {index}",
                grid=(
                    tile_shape[2], 0, tile_shape[2] - 1,
                    tile_shape[1], 0, tile_shape[1] - 1,
                    tile_shape[0], 0, tile_shape[0] - 1,
                ),
                cell=_tile_cell(source.cell, tile_shape, full_shape),
                axis_order=source.axis_order,
                data=tile_data.reshape(-1),
            )
            tile_in_path = tile_dir / f"tile_{index:04d}_in.xplor"
            tile_out_path = tile_dir / f"tile_{index:04d}_out.xplor"
            write_xplor_map(tile_in_path, tile_in)
            try:
                infer_tile(tile_in_path, tile_out_path)
                tile_out = read_xplor_map(tile_out_path)
            except Exception as exc:
                raise RuntimeError(f"Tiled SharpED inference failed on tile {index} of {len(starts)}: {exc}") from exc
            prediction = np.asarray(tile_out.data, dtype=np.float64).reshape(tile_shape)
            accumulator.add(start, prediction)
            log(f"[SharpED] Tile {index + 1}/{len(starts)} complete")
            tile_in_path.unlink(missing_ok=True)
            tile_out_path.unlink(missing_ok=True)
        reconstructed = accumulator.finalize()
        result = XplorMap(
            title=source.title,
            grid=source.grid,
            cell=source.cell,
            axis_order=source.axis_order,
            data=reconstructed.reshape(-1),
        )
        write_xplor_map(output_map_path, result)
        log("[SharpED] Complete · tiled map reconstructed")
    finally:
        try:
            tile_dir.rmdir()
        except OSError:
            pass
