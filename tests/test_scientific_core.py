"""Golden regression baseline for Phase Studio's pure scientific/parsing
functions.

This is a plain-Python test (no pytest dependency; run with
`python tests/test_scientific_core.py`), following the same
checks-list-plus-exit-code convention used by this project's other
regression scripts. It exists specifically to catch any future change that
alters a scientific result for a fixed input -- see docs/ARCHITECTURE.md
for the "same input, same result" rule this repository is refactored under.

The expected values below were captured directly from a real run of the
current code (not hand-derived), then pinned here as the baseline. If a
future, intentional change to the underlying algorithm needs to update one
of these numbers, that is a signal to treat the change with extra care and
document why the result changed -- not to update the test without
understanding the cause.
"""
import math
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


def close(a, b, tol=1e-9):
    return math.isclose(float(a), float(b), rel_tol=tol, abs_tol=tol)


# A small, fully hand-verifiable "hkl F sigma" fixture (1-indexed columns:
# h k l F sigma), including one duplicate (h,k,l) = (1,1,0) pair to exercise
# inverse-variance-weighted merging.
FIXTURE_LINES = [
    "  1  0  0    12.500   0.800",
    "  0  1  0    18.300   0.900",
    "  0  0  1     5.100   0.700",
    "  1  1  0    22.400   1.100",
    "  1  1  0    23.000   1.050",
    "  1  0  1     9.900   0.850",
    "  2  0  0     3.200   0.600",
    "  0  2  0    14.700   0.950",
]


def main():
    import gemmi
    import phase_studio.app as appmod
    import phase_studio.process_utils as process_utils

    tmpdir = Path(tempfile.mkdtemp())
    hkl_path = tmpdir / "fixture.hkl"
    hkl_path.write_text("\n".join(FIXTURE_LINES) + "\n")

    # =========================================================================
    # read_hkl(): exact reflection values, in file order, for amplitude+sigma
    # columns (value_col=4, sigma_col=5) -- the default.
    # =========================================================================
    reflections = appmod.read_hkl(hkl_path, value_col=4, sigma_col=5, include_000=False)
    check("read_hkl: parses all 8 fixture lines", len(reflections) == 8)
    expected_raw = [
        (1, 0, 0, 12.5, 0.8),
        (0, 1, 0, 18.3, 0.9),
        (0, 0, 1, 5.1, 0.7),
        (1, 1, 0, 22.4, 1.1),
        (1, 1, 0, 23.0, 1.05),
        (1, 0, 1, 9.9, 0.85),
        (2, 0, 0, 3.2, 0.6),
        (0, 2, 0, 14.7, 0.95),
    ]
    raw_matches = all(
        r.h == eh and r.k == ek and r.l == el and close(r.value, ev) and close(r.sigma, es)
        for r, (eh, ek, el, ev, es) in zip(reflections, expected_raw)
    )
    check("read_hkl: every parsed (h,k,l,F,sigma) matches the pinned baseline exactly", raw_matches)
    check("read_hkl: no phase column parsed for a 5-column amplitude+sigma line", all(r.phase is None for r in reflections))

    # =========================================================================
    # merge_duplicate_reflections(): the (1,1,0) duplicate pair must combine
    # via inverse-variance weighting, matching the pinned baseline exactly.
    # =========================================================================
    unique = appmod.merge_duplicate_reflections(reflections)
    check("merge_duplicate_reflections: 8 raw -> 7 unique (one (1,1,0) duplicate pair)", len(unique) == 7)
    merged_110 = next((r for r in unique if (r.h, r.k, r.l) == (1, 1, 0)), None)
    check("merge_duplicate_reflections: (1,1,0) present in the merged set", merged_110 is not None)
    if merged_110 is not None:
        check(
            "merge_duplicate_reflections: (1,1,0) merged value matches the pinned inverse-variance-weighted baseline",
            close(merged_110.value, 22.713945945945948),
        )
        check(
            "merge_duplicate_reflections: (1,1,0) merged sigma matches the pinned baseline",
            close(merged_110.sigma, 0.7595233213507507),
        )
    for (h, k, l, v, s) in [(1, 0, 0, 12.5, 0.8), (0, 1, 0, 18.3, 0.9), (0, 0, 1, 5.1, 0.7),
                             (1, 0, 1, 9.9, 0.85), (2, 0, 0, 3.2, 0.6), (0, 2, 0, 14.7, 0.95)]:
        match = next((r for r in unique if (r.h, r.k, r.l) == (h, k, l)), None)
        check(f"merge_duplicate_reflections: non-duplicate ({h},{k},{l}) unchanged", match is not None and close(match.value, v) and close(match.sigma, s))

    # =========================================================================
    # analyze_hkl_data(): completeness/resolution results for a fixed cell,
    # space group, and bin count -- exact pinned baseline.
    # =========================================================================
    cell = gemmi.UnitCell(10.0, 12.0, 15.0, 90.0, 90.0, 90.0)
    sg = gemmi.SpaceGroup("P 1")
    analysis = appmod.analyze_hkl_data(
        hkl_path, appmod.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA, cell, sg, sg.hm,
        source_note="fixture", bin_count=4,
    )
    check("analyze_hkl_data: reflections_unique count matches merge_duplicate_reflections (7)", len(analysis.reflections_unique) == 7)
    check("analyze_hkl_data: d_min matches the pinned baseline (5.0 A for this cell/fixture)", close(analysis.d_min, 5.0))
    check("analyze_hkl_data: d_full_98 matches the pinned baseline (10.0 A for this cell/fixture)", close(analysis.d_full_98, 10.0))
    check("analyze_hkl_data: bin_count=4 produces exactly 4 bins", len(analysis.bins) == 4)

    # =========================================================================
    # reflection_columns_for_mode() / normalize_reflection_data_mode():
    # mode-token normalization, pinned exactly.
    # =========================================================================
    check(
        "reflection_columns_for_mode: amplitude+sigma -> (value_col=4, sigma_col=5, include_000=False)",
        appmod.reflection_columns_for_mode(appmod.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA) == (4, 5, False),
    )
    check(
        "reflection_columns_for_mode: intensity -> (value_col=4, sigma_col=5, include_000=False)",
        appmod.reflection_columns_for_mode(appmod.REFLECTION_DATA_MODE_INTENSITY) == (4, 5, False),
    )
    check(
        "reflection_columns_for_mode: amplitude+phase+sigma -> (value_col=4, sigma_col=6, include_000=True)",
        appmod.reflection_columns_for_mode(appmod.REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA) == (4, 6, True),
    )

    # =========================================================================
    # Presentation/terminology functions: pinned canonical labels (see
    # docs/ARCHITECTURE.md, "Where UI formatting belongs").
    # =========================================================================
    check("reflection_value_label: amplitude mode -> 'Fobs'", appmod.reflection_value_label(appmod.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA) == "Fobs")
    check("reflection_value_label: intensity mode -> 'Iobs'", appmod.reflection_value_label(appmod.REFLECTION_DATA_MODE_INTENSITY) == "Iobs")
    check("reflection_sigma_label: FWHM mode -> 'FWHM' (never a sigma symbol)", appmod.reflection_sigma_label(appmod.REFLECTION_DATA_MODE_AMPLITUDE_FWHM) == "FWHM")
    check("reflection_primary_snr_label: amplitude+FWHM -> 'F/FWHM'", appmod.reflection_primary_snr_label(appmod.REFLECTION_DATA_MODE_AMPLITUDE_FWHM) == "F/FWHM")
    check("reflection_primary_snr_label: intensity+FWHM -> 'I/FWHM'", appmod.reflection_primary_snr_label(appmod.REFLECTION_DATA_MODE_INTENSITY_FWHM) == "I/FWHM")

    orbit_reflections = [
        appmod.Reflection(sign * h, sign * k, sign * l, 10.0)
        for h, k, l in ((1, 0, 0), (0, 1, 0), (1, 1, 0), (2, 1, 0), (1, 2, 0))
        for sign in (-1, 1)
    ]
    holdout_a = appmod.select_orbit_safe_holdout(orbit_reflections, gemmi.SpaceGroup("P 1"), "123")
    holdout_b = appmod.select_orbit_safe_holdout(orbit_reflections, gemmi.SpaceGroup("P 1"), "123")
    check("holdout split is deterministic for a fixed seed", holdout_a == holdout_b)
    check("holdout split selects complete measured Friedel pairs", all(tuple(-v for v in hkl) in holdout_a for hkl in holdout_a))

    # =========================================================================
    # process_utils: pure, dependency-free helpers used by both app.py and
    # jana_superflip.py.
    # =========================================================================
    check("process_utils.text_encoding() returns a non-empty string", bool(process_utils.text_encoding()))
    check("process_utils.allow_external_process_foreground(-1) is False for an invalid PID", process_utils.allow_external_process_foreground(-1) is False)

    reference_path = tmpdir / "reference.cif"
    model_path = tmpdir / "model.cif"
    atoms = [
        appmod.AtomSite("C1", "C", appmod.np.asarray((0.10, 0.20, 0.30))),
        appmod.AtomSite("O1", "O", appmod.np.asarray((0.45, 0.55, 0.65))),
    ]
    appmod.write_structure_cif(reference_path, cell, sg, "P 1", atoms)
    appmod.write_structure_cif(model_path, cell, sg, "P 1", atoms)
    reference_context = appmod.load_reference_context(reference_path, tmpdir / "reference_work")
    match_metrics = appmod.atom_reference_match_metrics(model_path, reference_context, 0.2)
    check("reference matching reports true positives", match_metrics is not None and match_metrics[2] == 2)
    check("reference matching reports false positives", match_metrics is not None and match_metrics[3] == 0)

    # Frozen holdout indices are forbidden from missing-reflection completion.
    # Stub only map prediction/candidate discovery; exercise the real feedback
    # update and its unchanged intensity conversion path.
    original_candidates = appmod.candidate_missing_hkls_from_bounds
    original_predictions = appmod.xplor_fft_predictions
    held_out = (3, 0, 0)
    allowed = (4, 0, 0)
    try:
        appmod.candidate_missing_hkls_from_bounds = lambda *_args: [held_out, allowed]
        appmod.xplor_fft_predictions = lambda _path, hkls: {tuple(hkl): (4.0, 0.0) for hkl in hkls}
        updated, _change = appmod.apply_map_feedback_to_reflections(
            unique,
            appmod.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA,
            tmpdir / "stub.xplor",
            cell,
            0.0,
            True,
            100.0,
            False,
            0.0,
            0.0,
            lambda _message: None,
            excluded_hkls=frozenset({held_out}),
        )
        updated_hkls = {(r.h, r.k, r.l) for r in updated}
        check("map feedback: frozen holdout never enters missing-reflection completion", held_out not in updated_hkls)
        check("map feedback: an allowed missing reflection can still be added", allowed in updated_hkls)
    finally:
        appmod.candidate_missing_hkls_from_bounds = original_candidates
        appmod.xplor_fft_predictions = original_predictions

    # Exact Superflip input baseline. A model-seeded calculation must force a
    # single deterministic repeat and omit randomseed; an unseeded calculation
    # must preserve both configured values.
    superflip_hkl = tmpdir / "superflip_guard.hkl"
    superflip_hkl.write_text("   1   0   0      12.5       0.8\n# ignored\n", encoding="utf-8")
    superflip_context = appmod.ReferenceContext(
        cif_path=tmpdir / "guard.cif",
        work_ref_cif=tmpdir / "guard_work.cif",
        cell=gemmi.UnitCell(10, 11, 12, 90, 90, 90),
        spacegroup=gemmi.SpaceGroup("P 1"),
        spacegroup_hm="P 1",
        composition="C 2 O 1",
        atoms=[],
    )
    writer_args = dict(
        prefix="gold", ref_ctx=superflip_context, observed_hkl=superflip_hkl,
        output_xplor="gold.xplor", reference_file=None, reference_format="cif",
        perform_algorithm="CF", output_format="xplor", write_auxiliary_outputs=False,
        export_superflip_xplor=True, export_superflip_ccp4=False,
        export_superflip_jana=False, voxel="", bestdensities_count=3,
        bestdensities_metric="contrast", bestdensities_symmetry=False, polish=True,
        maxcycles=100, repeatmode=7, randomseed="12345", delta="AUTO",
        weakratio="0.2", biso="0.0",
        reflection_data_mode=appmod.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA,
        normalize="none", nresshells=1, missing="", searchsymmetry="average",
        derivesymmetry="yes", electrons="", dataitemwidths="4 14 14",
        extra_superflip_keywords="", log=None,
    )
    common_body = """title gold
perform CF
outputfile gold.xplor
outputformat xplor
{model_line}dimension  3
cell 10.000000 11.000000 12.000000 90.0000 90.0000 90.0000
spacegroup P 1
centro no
centers
  0.000000  0.000000  0.000000
endcenters
symmetry
  x1 x2 x3
endsymmetry
composition C 2 O 1

# Keywords for density modification
repeatmode {repeatmode}
bestdensities 3 rvalue
maxcycles 100
delta AUTO
weakratio 0.2
Biso 0.0
polish yes
{randomseed_line}searchsymmetry average
derivesymmetry yes
dataformat amplitude dummy
fbegin
   1   0   0      12.5       0.8
endf
"""
    plain_input = tmpdir / "plain.inflip"
    appmod.write_superflip_input(plain_input, model_file=None, **writer_args)
    check(
        "Superflip input: unseeded output matches the exact golden text",
        plain_input.read_text(encoding="utf-8") == common_body.format(
            model_line="", repeatmode=7, randomseed_line="randomseed 12345\n",
        ),
    )
    seeded_input = tmpdir / "seeded.inflip"
    appmod.write_superflip_input(
        seeded_input, model_file=tmpdir / "seed.xplor", **writer_args,
    )
    check(
        "Superflip input: model-seeded output forces repeatmode 1 and omits randomseed",
        seeded_input.read_text(encoding="utf-8") == common_body.format(
            model_line="modelfile seed.xplor\n", repeatmode=1, randomseed_line="",
        ),
    )

    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)

    failed = [name for name, ok in results_log if not ok]
    print()
    if failed:
        print(f"{len(failed)} check(s) FAILED: {failed}")
        sys.exit(1)
    else:
        print(f"All {len(results_log)} checks passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
