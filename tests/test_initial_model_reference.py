"""Regression tests for Initial-model vs. continuation Superflip reference-anchor equivalence.

A user reported that the exact same model file X produced a noticeably worse
Superflip result when supplied as "Initial model (cycle 1)"
(RunConfig.first_cycle_modelfile) in a fresh run than when that same file was
the "current model" (PipelineState.current_model) driving a continuing
cycle's Superflip run. Investigation (via a real, only-run_command-faked
execution of the production cycle loop) found the dominant, universally
reproducible cause: a continuing cycle N>1 automatically gets a
`referencefile` keyword in its .inflip, anchoring Superflip's phase origin
against the previous cycle's own output (app.py's cycle loop,
`referencefile_mode == "omit" and cyc > 1`); a fresh run's cycle 1 never got
this, purely because a fresh PipelineState has no previous cycle.

A second, real-execution reproduction then proved CASE 1: in the app's
default configurations, `PipelineState.current_model` (X) and
`PipelineState.auto_reference_cif`/`auto_reference_xplor` (the continuation's
automatic reference anchor) are assigned the *same file* -- so the missing
cycle-1 anchor is fully recoverable from the Initial model alone, with no
invented previous-cycle state. The fix: `referencefile_mode == "omit"` at
`cyc == 1` with a supplied `first_cycle_modelfile` now anchors on that model,
exactly mirroring the automatic previous-cycle anchor a continuing series
already got. An explicit user-selected reference (`reference_cif` /
`reference_xplor` / `reference_density`) is untouched and always wins; a
fresh run with no Initial model still gets no automatic reference at all.

This is deliberately plain-Python (no pytest dependency), following this
project's usual checks-list-plus-exit-code convention; run with
`python tests/test_initial_model_reference.py`.
"""
import hashlib
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

results_log = []


def check(name, cond):
    results_log.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL") + " - " + name)


HKL_LINES = [
    "  1  0  0    12.500   0.800",
    "  0  1  0    18.300   0.900",
    "  0  0  1     5.100   0.700",
    "  1  1  0    22.400   1.100",
    "  1  0  1     9.900   0.850",
    "  2  0  0     3.200   0.600",
    "  0  2  0    14.700   0.950",
]

CIF = """data_test
_cell_length_a 10.0
_cell_length_b 10.0
_cell_length_c 10.0
_cell_angle_alpha 90.0
_cell_angle_beta 90.0
_cell_angle_gamma 90.0
_space_group_name_H-M_alt 'P 1'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
C1 C 0.10 0.10 0.10
O1 O 0.50 0.40 0.35
"""

OTHER_CIF = """data_other
_cell_length_a 10.0
_cell_length_b 10.0
_cell_length_c 10.0
_cell_angle_alpha 90.0
_cell_angle_beta 90.0
_cell_angle_gamma 90.0
_space_group_name_H-M_alt 'P 1'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
X1 Si 0.25 0.25 0.25
"""


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_fake_map(appmod, path, seed=0):
    import numpy as np
    n = 6
    rng = np.random.default_rng(seed)
    values = rng.normal(size=n ** 3)
    xmap = appmod.XplorMap(
        title="fake superflip map",
        grid=(n, 0, n - 1, n, 0, n - 1, n, 0, n - 1),
        cell=(10.0, 10.0, 10.0, 90.0, 90.0, 90.0),
        axis_order="ZYX",
        data=np.asarray(values, dtype=np.float64),
    )
    appmod.write_xplor_map(path, xmap)
    return path


def build_cfg(appmod, tjc, tmp, **overrides):
    inflip = tmp / "job.inflip"
    inflip.write_text("title fixture\n", encoding="utf-8")
    cfg = tjc.make_run_config(appmod, tmp, inflip)
    cfg.jana_inflip = None
    cfg.cycles = 2
    cfg.reconstruction_mode = "superflip"
    cfg.referencefile_mode = "omit"
    cfg.explicit_superflip_referencefile = None
    cfg.first_cycle_modelfile = None
    cfg.modelfile_source = "deblurred_edma_cif"
    cfg.map_export_format = "xplor"
    cfg.structure_export_format = "cif"
    cfg.reflection_data_mode = appmod.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA
    cfg.run_sharped = False
    cfg.run_edma_superflip = False
    cfg.run_edma_deblurred = True
    cfg.symmetrize_deblurred_map = False
    cfg.compute_omit_maps = False
    cfg.superflip_exe = str(tmp / "superflip.exe")
    cfg.edma_exe = str(tmp / "edma.exe")
    cfg.perform_algorithm = "superflip"
    cfg.voxel = "auto"
    cfg.maxcycles = 1000
    cfg.repeatmode = 5
    cfg.randomseed = "1234"
    cfg.delta = "AUTO"
    cfg.weakratio = "0.0"
    cfg.biso = "0.0"
    cfg.normalize = ""
    cfg.nresshells = 8
    cfg.missing = ""
    cfg.searchsymmetry = "average"
    cfg.derivesymmetry = "yes"
    cfg.electrons = ""
    cfg.dataitemwidths = ""
    cfg.extra_superflip_keywords = ""
    cfg.bestdensities_count = 0
    cfg.bestdensities_metric = ""
    cfg.bestdensities_symmetry = False
    cfg.polish = False
    cfg.i_over_sigma_min = 0.0
    cfg.resolution_d_min = 0.0
    cfg.merge_distance = 0.5
    cfg.plimit_superflip = 3.0
    cfg.plimit_deblur = 3.0
    cfg.damping_factor = 0.0
    # Map Feedback stays off throughout this file: it is a separate,
    # already-legitimate source of continuation-vs-fresh non-equivalence
    # (a continuing series can carry forward feedback-modified reflections
    # that a fresh run, by definition, never had) and is out of scope for
    # this fix, which only restores the missing reference anchor.
    cfg.map_feedback_missing_enabled = False
    cfg.map_feedback_intensity_enabled = False
    cfg.redistribute_overlaps = False
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def make_state(appmod, cfg, tmp):
    import gemmi
    observed = tmp / "observed.hkl"
    observed.write_text("\n".join(HKL_LINES) + "\n", encoding="utf-8")
    ref_cif = tmp / "reference.cif"
    ref_cif.write_text(CIF, encoding="utf-8")
    atoms = appmod.parse_cif_atoms(ref_cif)
    ref_ctx = appmod.ReferenceContext(
        cif_path=ref_cif, work_ref_cif=ref_cif,
        cell=gemmi.UnitCell(10, 10, 10, 90, 90, 90),
        spacegroup=gemmi.SpaceGroup("P 1"), spacegroup_hm="P 1",
        composition="C 2 O 1", atoms=atoms,
    )
    mode = cfg.modelfile_source
    use_xplor = mode in {"superflip_xplor", "deblurred_xplor"}
    return appmod.PipelineState(
        cfg=cfg, ref_ctx=ref_ctx,
        observed_hkls={cfg.reflection_data_mode: observed},
        configured_data_mode=cfg.reflection_data_mode,
        referencefile_mode=cfg.referencefile_mode,
        explicit_superflip_referencefile=cfg.explicit_superflip_referencefile,
        modelfile_mode=mode,
        use_xplor_modelfile=use_xplor,
        use_cif_modelfile=(mode == "deblurred_edma_cif"),
        use_superflip_xplor_modelfile=(mode == "superflip_xplor"),
        sharped_elements="C", exclude_labels=[],
        progress_stages=appmod.cycle_progress_stages(cfg),
        current_reflections=appmod.read_hkl(observed, value_col=4, sigma_col=5, include_000=False),
    )


def run_pipeline(appmod, win, state, snapshots, tag):
    """Run the real _run_pipeline_cycles, faking only external processes --
    write_superflip_input, run_superflip_cycle, write_filtered_cif and the
    real cycle-loop model/reference-selection logic under test all execute
    for real."""
    sf_inputs = []
    seed = [0]

    def fake_run_command(cmd, cwd, **kwargs):
        cmd = [str(c) for c in cmd]
        cwd = Path(cwd)
        log_path = kwargs.get("log_path")
        if log_path:
            Path(log_path).write_text("fake superflip log\n", encoding="utf-8")
        name = cmd[1] if len(cmd) > 1 else ""
        if name.endswith(".inflip"):
            prefix = name[:-len(".inflip")]
            sf_inputs.append(cwd / name)
            snapshots[(tag, cwd.name)] = {
                "current_model": state.current_model,
                "auto_reference_cif": state.auto_reference_cif,
                "auto_reference_xplor": state.auto_reference_xplor,
            }
            seed[0] += 1
            write_fake_map(appmod, cwd / f"{prefix}.xplor", seed=seed[0])
        return 0

    def fake_edma(xplor_map, out_dir, prefix, ref_ctx, *a, **kw):
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{prefix}_edma.cif"
        out.write_text(CIF, encoding="utf-8")
        return out

    with patch.object(appmod, "run_command", side_effect=fake_run_command), \
         patch.object(appmod, "run_edma_on_xplor", side_effect=fake_edma), \
         patch.object(appmod, "parse_superflip_cycle_metrics",
                      return_value=appmod.SuperflipLogMetrics()), \
         patch.object(appmod, "write_metrics_csv"), \
         patch.object(appmod, "write_map_quality_report"):
        state.cfg.work_dir.mkdir(parents=True, exist_ok=True)
        win.results = []
        win._run_pipeline_cycles(state)
    return sf_inputs


def inflip_lines_excluding_harmless(path):
    """The .inflip content with the title/outputfile lines (which always
    encode the cycle's own prefix, e.g. cycle_001_superflip vs
    cycle_002_superflip) stripped, so the remaining lines are directly
    comparable across a fresh cycle 1 and a continuation cycle 2."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return [l for l in lines if not (l.startswith("title ") or l.startswith("outputfile "))]


def main():
    import phase_studio.app as appmod
    import test_jana_completion as tjc
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([sys.argv[0]])
    appmod.IterativeSuperflipPipelineQtGUI.save_settings = lambda self: None
    appmod.IterativeSuperflipPipelineQtGUI.load_settings = lambda self: None
    win = appmod.IterativeSuperflipPipelineQtGUI()
    win._set_run_status("Running")

    # ----- CIF mode -----------------------------------------------------
    snaps = {}
    tmp_a = Path(tempfile.mkdtemp(prefix="A_cif_"))
    cfg_a = build_cfg(appmod, tjc, tmp_a, modelfile_source="deblurred_edma_cif", cycles=2)
    state_a = make_state(appmod, cfg_a, tmp_a)
    inflips_a = run_pipeline(appmod, win, state_a, snaps, "A")
    cyc2_a = next(p for p in inflips_a if p.parent.name == "cycle_002")
    snap2 = snaps[("A", "cycle_002")]
    X = Path(snap2["current_model"])
    R_auto = Path(snap2["auto_reference_cif"]) if snap2["auto_reference_cif"] else None
    check("continuation cycle 2 has an auto referencefile", R_auto is not None)
    check(
        "continuation's current_model (X) and auto_reference_cif are the same file",
        R_auto is not None and X.resolve() == R_auto.resolve(),
    )
    check("continuation cycle 2 .inflip actually contains a referencefile line",
          any(l.startswith("referencefile ") for l in cyc2_a.read_text(encoding="utf-8").splitlines()))

    # Stash X somewhere stable so fresh runs below don't reach back into A's tree.
    keep = Path(tempfile.mkdtemp(prefix="keep_cif_"))
    Xk = keep / "X_initial_model.cif"
    shutil.copy2(X, Xk)
    other_cif = keep / "other_reference.cif"
    other_cif.write_text(OTHER_CIF, encoding="utf-8")

    # (1) THE FIX: fresh cycle 1, Initial model = X, referencefile_mode="omit"
    # must now automatically anchor on X, and its .inflip must be equivalent
    # (aside from title/outputfile) to the continuation's cycle-2 .inflip.
    tmp_b = Path(tempfile.mkdtemp(prefix="B_cif_"))
    cfg_b = build_cfg(appmod, tjc, tmp_b, modelfile_source="deblurred_edma_cif", cycles=1,
                       first_cycle_modelfile=Xk, referencefile_mode="omit")
    state_b = make_state(appmod, cfg_b, tmp_b)
    inflips_b = run_pipeline(appmod, win, state_b, snaps, "B")
    cyc1_b = next(p for p in inflips_b if p.parent.name == "cycle_001")
    check("fresh Initial-model run (omit mode) gets an automatic referencefile",
          any(l.startswith("referencefile ") for l in cyc1_b.read_text(encoding="utf-8").splitlines()))
    check(
        "fresh Initial-model run's staged reference content matches X",
        sha(cyc1_b.parent / "superflip_referencefile.cif") == sha(Xk),
    )
    check(
        "fresh Initial-model run's .inflip is equivalent to continuation's (aside from title/outputfile)",
        inflip_lines_excluding_harmless(cyc1_b) == inflip_lines_excluding_harmless(cyc2_a),
    )

    # (2) PRECEDENCE: an explicit user-selected reference must never be
    # silently overridden by the new Initial-model auto-anchor.
    tmp_c = Path(tempfile.mkdtemp(prefix="C_cif_"))
    cfg_c = build_cfg(appmod, tjc, tmp_c, modelfile_source="deblurred_edma_cif", cycles=1,
                       first_cycle_modelfile=Xk, referencefile_mode="reference_cif",
                       explicit_superflip_referencefile=other_cif)
    state_c = make_state(appmod, cfg_c, tmp_c)
    inflips_c = run_pipeline(appmod, win, state_c, snaps, "C")
    cyc1_c = next(p for p in inflips_c if p.parent.name == "cycle_001")
    check(
        "explicit referencefile selection stays authoritative over an Initial model",
        sha(cyc1_c.parent / "superflip_referencefile.cif") == sha(other_cif)
        and sha(cyc1_c.parent / "superflip_referencefile.cif") != sha(Xk),
    )

    # (3) NO-INITIAL-MODEL REGRESSION: a fresh cycle 1 with no Initial model
    # and omit mode must still get no automatic reference at all -- nothing
    # invented out of thin air.
    tmp_d = Path(tempfile.mkdtemp(prefix="D_cif_"))
    cfg_d = build_cfg(appmod, tjc, tmp_d, modelfile_source="deblurred_edma_cif", cycles=1,
                       first_cycle_modelfile=None, referencefile_mode="omit")
    state_d = make_state(appmod, cfg_d, tmp_d)
    inflips_d = run_pipeline(appmod, win, state_d, snaps, "D")
    cyc1_d = next(p for p in inflips_d if p.parent.name == "cycle_001")
    check(
        "fresh cycle 1 with no Initial model still gets no automatic referencefile",
        not any(l.startswith("referencefile ") for l in cyc1_d.read_text(encoding="utf-8").splitlines()),
    )

    # (4) CONTINUATION REGRESSION: cycles beyond 1 are untouched -- still
    # anchored on the previous cycle's own output, never on an Initial model
    # (first_cycle_modelfile is not even part of that branch's condition).
    check(
        "continuation cycle 2's referencefile is still the previous-cycle auto-reference, unaffected by the fix",
        R_auto is not None and sha(cyc2_a.parent / "superflip_referencefile.cif") == sha(R_auto),
    )

    # ----- XPLOR mode -----------------------------------------------------
    snaps_x = {}
    tmp_ax = Path(tempfile.mkdtemp(prefix="A_xplor_"))
    cfg_ax = build_cfg(appmod, tjc, tmp_ax, modelfile_source="deblurred_xplor", cycles=2,
                        run_sharped=False, run_edma_deblurred=False, run_edma_superflip=False)
    state_ax = make_state(appmod, cfg_ax, tmp_ax)
    inflips_ax = run_pipeline(appmod, win, state_ax, snaps_x, "AX")
    cyc2_ax = next(p for p in inflips_ax if p.parent.name == "cycle_002")
    snap2x = snaps_x[("AX", "cycle_002")]
    Xx = Path(snap2x["current_model"])
    Rx = Path(snap2x["auto_reference_xplor"]) if snap2x["auto_reference_xplor"] else None
    check("XPLOR continuation's current_model and auto_reference_xplor are the same file",
          Rx is not None and Xx.resolve() == Rx.resolve())

    keep_x = Path(tempfile.mkdtemp(prefix="keep_xplor_"))
    Xxk = keep_x / "X_initial_model.xplor"
    shutil.copy2(Xx, Xxk)
    tmp_bx = Path(tempfile.mkdtemp(prefix="B_xplor_"))
    cfg_bx = build_cfg(appmod, tjc, tmp_bx, modelfile_source="deblurred_xplor", cycles=1,
                        run_sharped=False, run_edma_deblurred=False, run_edma_superflip=False,
                        first_cycle_modelfile=Xxk, referencefile_mode="omit")
    state_bx = make_state(appmod, cfg_bx, tmp_bx)
    inflips_bx = run_pipeline(appmod, win, state_bx, snaps_x, "BX")
    cyc1_bx = next(p for p in inflips_bx if p.parent.name == "cycle_001")
    check("XPLOR fresh Initial-model run (omit mode) gets an automatic referencefile",
          any(l.startswith("referencefile ") for l in cyc1_bx.read_text(encoding="utf-8").splitlines()))
    check(
        "XPLOR fresh Initial-model run's .inflip is equivalent to continuation's (aside from title/outputfile)",
        inflip_lines_excluding_harmless(cyc1_bx) == inflip_lines_excluding_harmless(cyc2_ax),
    )

    win.timer.stop()
    win.close()
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
