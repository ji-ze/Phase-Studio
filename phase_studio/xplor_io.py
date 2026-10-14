"""XPLOR map I/O, shared by the full scientific GUI (phase_studio.app) and
the lightweight Jana2020 wrapper (phase_studio.jana_superflip) without
either needing to import the other. Kept dependency-light (numpy only) so
the wrapper's frozen build stays small and fast.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import numpy as np


@dataclass
class XplorMap:
    title: str
    grid: Tuple[int, int, int, int, int, int, int, int, int]
    cell: Tuple[float, float, float, float, float, float]
    axis_order: str
    data: np.ndarray


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
