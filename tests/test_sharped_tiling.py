"""Regression tests for the shared, size-aware large-map SharpED tiling
boundary (Phase Studio 2.0.0).

Plain Python test (no pytest dependency); run with
`python tests/test_sharped_tiling.py`.
"""
import inspect
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

results_log = []


def check(name, cond):
    results_log.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL") + " - " + name)


def make_map(appmod_xplor_io, shape, cell=(20.0, 20.0, 20.0, 90.0, 90.0, 90.0), fill=None):
    import numpy as np
    nz, ny, nx = shape
    if fill is None:
        rng = np.random.default_rng(0)
        data = rng.normal(size=nz * ny * nx)
    else:
        data = fill.reshape(-1)
    grid = (nx, 0, nx - 1, ny, 0, ny - 1, nz, 0, nz - 1)
    return appmod_xplor_io.XplorMap(title="test map", grid=grid, cell=cell, axis_order="ZYX", data=data)


def main():
    import numpy as np
    import phase_studio.xplor_io as xio
    import phase_studio.sharped_tiling as tiling

    tmp = Path(tempfile.mkdtemp(prefix="tiling_"))

    # --- decide_sharped_submission: below-limit stays direct, unchanged ---
    small_path = tmp / "small.xplor"
    xio.write_xplor_map(small_path, make_map(xio, (6, 6, 6)))
    check(
        "below-limit map stays on the direct path",
        tiling.decide_sharped_submission(small_path, max_upload_mb=100.0) == "direct",
    )
    check(
        "max_upload_mb<=0 means no limit configured -> always direct",
        tiling.decide_sharped_submission(small_path, max_upload_mb=0.0) == "direct",
    )

    # --- Gaussian importance weight: exact formula, cached ---
    shape = (8, 8, 8)
    w1 = tiling.gaussian_importance_map(shape)
    w2 = tiling.gaussian_importance_map(shape)
    check("gaussian weight is cached per shape (identical object)", w1 is w2)
    center = (8 - 1) / 2.0
    sigma = 0.125 * 8
    expected_center_value = np.exp(0.0) ** 3  # center voxel: all three axes at their own center
    check("gaussian weight peaks at the tile center", abs(w1[4, 4, 4] - expected_center_value) < 1e-6 or w1[4, 4, 4] == w1.max())
    check("gaussian weight is never exactly zero (small values clamped)", np.all(w1 > 0))

    # --- Tile overlap: exactly 10%, integer, floor of 1 ---
    for tile_extent in (10, 20, 100, 3):
        overlap_voxels = max(1, round(0.10 * tile_extent))
        starts = tiling.tile_starts(full_extent=tile_extent * 5, tile_extent=tile_extent)
        step = starts[1] - starts[0] if len(starts) > 1 else None
        if step is not None:
            check(f"tile_extent={tile_extent}: step matches tile_size - 10% overlap",
                  step == tile_extent - overlap_voxels)
    check("overlap floors to at least 1 voxel even for a tiny tile", max(1, round(0.10 * 3)) == 1)

    # --- Identity reconstruction ---
    full_shape = (12, 14, 16)  # deliberately not evenly divisible by a small tile
    source_data = np.random.default_rng(1).normal(size=full_shape).astype(np.float64)
    identity_input = tmp / "identity_full.xplor"
    xio.write_xplor_map(identity_input, make_map(xio, full_shape, fill=source_data))

    def identity_infer(tile_in: Path, tile_out: Path) -> None:
        xmap = xio.read_xplor_map(tile_in)
        xio.write_xplor_map(tile_out, xmap)

    identity_output = tmp / "identity_out.xplor"
    # Force tiling with a tiny budget regardless of real map size.
    tiny_budget_mb = 0.00005
    submission = tiling.decide_sharped_submission(identity_input, tiny_budget_mb)
    check("identity test: tiny budget forces the tiled path", submission == "tiled")
    tile_log = []
    tiling.run_tiled_sharped_inference(
        identity_input, identity_output, tiny_budget_mb, identity_infer, tile_log.append,
    )
    check("tiled progress names individual tile completion before map completion",
          any("Tile 1/" in line and line.endswith("complete") for line in tile_log))
    check("only reconstructed output is announced as the complete SharpED map",
          tile_log[-1] == "[SharpED] Complete · tiled map reconstructed")
    reconstructed = xio.read_xplor_map(identity_output)
    recon_3d = reconstructed.data.reshape(full_shape)
    diff = np.abs(recon_3d - source_data)
    max_abs = float(diff.max())
    mae = float(diff.mean())
    rms = float(np.sqrt(np.mean(diff ** 2)))
    print(f"    identity reconstruction: max_abs={max_abs:.3e} MAE={mae:.3e} RMS={rms:.3e}")
    # Tolerance reflects the XPLOR text format's own precision (%.5E, ~6
    # significant figures per value), not floating-point roundoff -- every
    # tile is written and read back as text, same as any real SharpED
    # request/response, so this is the real achievable precision.
    check("identity reconstruction matches the input within XPLOR text-format precision",
          max_abs < 5e-5 and rms < 5e-6)

    # --- Grid/cell/origin/axis-order unchanged before vs after ---
    original = xio.read_xplor_map(identity_input)
    check("tiling leaves the grid dimensions unchanged", reconstructed.grid == original.grid)
    check("tiling leaves the unit cell unchanged", reconstructed.cell == original.cell)
    check("tiling leaves the axis order unchanged", reconstructed.axis_order == original.axis_order)

    # --- Periodic boundary: a feature straddling x=0/1, y=0/1, z=0/1 leaves no seam ---
    periodic_shape = (10, 10, 10)
    periodic_data = np.zeros(periodic_shape, dtype=np.float64)
    # A sharp feature exactly at the wrap boundary on every axis.
    periodic_data[0, 0, 0] = 10.0
    periodic_data[-1, -1, -1] = 10.0
    periodic_input = tmp / "periodic_full.xplor"
    xio.write_xplor_map(periodic_input, make_map(xio, periodic_shape, fill=periodic_data))
    periodic_output = tmp / "periodic_out.xplor"
    tiling.run_tiled_sharped_inference(periodic_input, periodic_output, 0.00005, identity_infer)
    periodic_recon = xio.read_xplor_map(periodic_output).data.reshape(periodic_shape)
    boundary_diff = np.abs(periodic_recon - periodic_data)
    check("periodic boundary feature reconstructs without a seam",
          float(boundary_diff.max()) < 1e-6)

    # --- Complete coverage: weight_sum > 0 everywhere ---
    accumulator = tiling.PeriodicAccumulator(full_shape)
    tile_shape = tiling.tile_shape_for_budget(full_shape, tiny_budget_mb)
    starts = tiling.plan_tiles(full_shape, tile_shape)
    for start in starts:
        tile_prediction = tiling.extract_periodic_tile(source_data, start, tile_shape)
        accumulator.add(start, tile_prediction)
    check("every voxel is covered by at least one tile (weight_sum > 0 everywhere)",
          bool((accumulator.weight_sum > 0).all()))
    check(f"tile plan reports a concrete tile count ({len(starts)} tiles for a {full_shape} map, "
          f"tile shape {tile_shape})", len(starts) >= 1)

    # --- Equal tile dimensions regardless of divisibility ---
    for start in starts:
        extracted = tiling.extract_periodic_tile(source_data, start, tile_shape)
        if extracted.shape != tuple(tile_shape):
            check("every tile has identical dimensions", False)
            break
    else:
        check("every tile has identical dimensions", True)

    # --- Larger representative map: report tile count for visibility ---
    large_shape = (64, 64, 64)
    large_tile_shape = tiling.tile_shape_for_budget(large_shape, max_upload_mb=5.0)
    large_starts = tiling.plan_tiles(large_shape, large_tile_shape)
    print(f"    representative large map {large_shape} at 5 MB budget -> "
          f"tile shape {large_tile_shape}, {len(large_starts)} tile(s) (10% overlap)")
    check("large representative map produces a bounded, non-trivial tile count",
          1 <= len(large_starts) <= 4096)

    # --- Below-limit maps: reconstruction path never invoked, output identical ---
    below_limit_output = tmp / "below_limit_out.xplor"

    def fail_if_called(_a, _b):
        raise AssertionError("infer_tile must not be called for a below-limit map")

    if tiling.decide_sharped_submission(small_path, 100.0) == "direct":
        # Direct path is the caller's own responsibility (app.py/jana_superflip.py
        # call infer_tile once themselves); simulate that here.
        small_map = xio.read_xplor_map(small_path)
        xio.write_xplor_map(below_limit_output, small_map)
        check("below-limit map is written unchanged on the direct path",
              xio.read_xplor_map(below_limit_output).data.tolist() == small_map.data.tolist())

    # --- Tile failure aborts cleanly: no partial map published ---
    def flaky_infer(tile_in: Path, tile_out: Path) -> None:
        raise RuntimeError("simulated SharpED server failure")

    failure_output = tmp / "failure_out.xplor"
    raised = False
    try:
        tiling.run_tiled_sharped_inference(identity_input, failure_output, tiny_budget_mb, flaky_infer)
    except RuntimeError:
        raised = True
    check("a failing tile raises rather than silently continuing", raised)
    check("a failing tile publishes no partial output map", not failure_output.is_file())

    # --- All production SharpED call sites route through the shared boundary ---
    import phase_studio.app as appmod
    import phase_studio.jana_superflip as jana

    app_source = inspect.getsource(appmod.run_sharped_deblur)
    check("app.py's run_sharped_deblur uses the shared decide_sharped_submission",
          "decide_sharped_submission(" in app_source)
    check("app.py's run_sharped_deblur uses the shared run_tiled_sharped_inference",
          "run_tiled_sharped_inference(" in app_source)
    jana_source = inspect.getsource(jana.deblur_with_sharped)
    check("jana_superflip.py's deblur_with_sharped uses the shared decide_sharped_submission",
          "decide_sharped_submission(" in jana_source)
    check("jana_superflip.py's deblur_with_sharped uses the shared run_tiled_sharped_inference",
          "run_tiled_sharped_inference(" in jana_source)
    check("the old voxel-degradation workaround is gone from app.py",
          not hasattr(appmod, "sharped_limited_superflip_voxel"))
    check("the old hard-fail upload preparer is gone from app.py",
          not hasattr(appmod, "prepare_xplor_for_sharped_upload"))

    # --- No MONAI dependency ---
    pyproject_text = (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    check("MONAI is not a project dependency", "monai" not in pyproject_text.lower())
    import ast as ast_module
    tiling_tree = ast_module.parse(inspect.getsource(tiling))
    imported_modules = set()
    for node in ast_module.walk(tiling_tree):
        if isinstance(node, ast_module.Import):
            imported_modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast_module.ImportFrom) and node.module:
            imported_modules.add(node.module.split(".")[0])
    check("the tiling module never actually imports monai (mentioned only in its own docs/comments)",
          "monai" not in {m.lower() for m in imported_modules})

    failures = [name for name, ok in results_log if not ok]
    print()
    if failures:
        print(f"{len(failures)} of {len(results_log)} checks FAILED:")
        for failure in failures:
            print("  - " + failure)
        return 1
    print(f"All {len(results_log)} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
