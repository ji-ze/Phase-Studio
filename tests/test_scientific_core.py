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

    # =========================================================================
    # process_utils: pure, dependency-free helpers used by both app.py and
    # jana_superflip.py.
    # =========================================================================
    check("process_utils.text_encoding() returns a non-empty string", bool(process_utils.text_encoding()))
    check("process_utils.allow_external_process_foreground(-1) is False for an invalid PID", process_utils.allow_external_process_foreground(-1) is False)

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
