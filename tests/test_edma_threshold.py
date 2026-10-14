"""Regression tests for phase_studio/edma_threshold.py -- Autosolve's per-map
automatic EDMA threshold calibration.

Deterministic synthetic fixtures stand in for EDMA: a known structure whose
atoms appear progressively as the threshold is lowered, plus spurious noise
peaks below a defined noise onset. "Measured" amplitudes are the structure
factors of the true structure with fixed multiplicative noise. Covers the
noise-onset plateau, map-specific selection, the composition constraint,
the no-composition case, the genuine holdout (no work-reflection leakage),
reference independence through the real app integration, fallback, cache,
and user stop.

Plain Python test (no pytest dependency); run with
`python tests/test_edma_threshold.py`.
"""
import os
import sys
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gemmi
import numpy as np

results_log = []
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def check(name, cond):
    results_log.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL") + " - " + name)


from phase_studio import edma_threshold as auto
from phase_studio.map_quality import FrozenReflection, make_validation_context

CELL = gemmi.UnitCell(11.0, 12.0, 13.0, 90.0, 90.0, 90.0)
SG = gemmi.SpaceGroup("P 1")
ELEMENTS = ("Fe", "S", "O", "C")


def random_structure(rng, n, min_distance=1.9):
    orth = np.asarray(CELL.orth.mat.tolist())
    sites = []
    while len(sites) < n:
        f = rng.random(3)
        ok = True
        for other in sites:
            d = f - np.asarray(other.frac)
            d -= np.round(d)
            if np.linalg.norm(orth @ d) < min_distance:
                ok = False
                break
        if ok:
            sites.append(auto.PeakSite(ELEMENTS[len(sites) % len(ELEMENTS)], tuple(float(v) for v in f)))
    return sites


def hkl_set(d_min=1.1):
    out = []
    for h in range(-10, 11):
        for k in range(-11, 12):
            for l in range(0, 13):
                if (h, k, l) <= (0, 0, 0) and l == 0 and (k < 0 or (k == 0 and h <= 0)):
                    continue
                if (h, k, l) == (0, 0, 0):
                    continue
                if CELL.calculate_d([h, k, l]) >= d_min:
                    out.append((h, k, l))
    return out


HKL = hkl_set()


def measured_context(true_sites, noise=0.03, seed=7, free_fraction=0.0, corrupt_work=False):
    placeholder = make_validation_context([FrozenReflection(h, k, l, 1.0) for h, k, l in HKL], unit_cell=None)
    evaluator = auto.ModelAgreementEvaluator(placeholder, CELL, SG)
    fo = evaluator.fcalc(true_sites)
    rng = np.random.default_rng(seed)
    fo = fo * (1.0 + noise * rng.standard_normal(len(fo)))
    fo = np.abs(fo)
    free = []
    if free_fraction > 0:
        pick = np.random.default_rng(11).random(len(HKL)) < free_fraction
        free = [HKL[i] for i in np.nonzero(pick)[0]]
    free_set = set(free)
    if corrupt_work:
        bad = np.random.default_rng(99)
        fo = np.asarray([
            v if HKL[i] in free_set else v * (0.2 + 1.6 * bad.random()) for i, v in enumerate(fo)
        ])
    reflections = [FrozenReflection(h, k, l, float(a)) for (h, k, l), a in zip(HKL, fo)]
    context = make_validation_context(reflections, free_hkls=free, unit_cell=None)
    return auto.ModelAgreementEvaluator(context, CELL, SG)


def fixture_extractor(true_sites, top, bottom, noise_onset, n_noise=70, seed=3, extra=()):
    """Peak heights: true atoms spread from `top` down to `bottom` (in
    sigma); `n_noise` spurious peaks with heights below `noise_onset`;
    optional `extra` (sites, height) pairs."""
    rng = np.random.default_rng(seed)
    heights = np.linspace(top, bottom, len(true_sites))
    noise_sites = random_structure(np.random.default_rng(seed + 100), n_noise, min_distance=1.2)
    noise_heights = rng.uniform(0.2, noise_onset, n_noise)
    calls = []

    def extract(sigma):
        calls.append(sigma)
        chosen = [s for s, h in zip(true_sites, heights) if h >= sigma]
        chosen += [s for s, h in zip(noise_sites, noise_heights) if h >= sigma]
        chosen += [s for s, h in extra if h >= sigma]
        return chosen

    extract.calls = calls
    extract.noise = set(noise_sites)
    return extract


def run(extract, evaluator, source="superflip", composition=(), cache=None, stop_event=None, stats=None):
    return auto.calibrate_edma_threshold(
        source, auto.cached_parallel_extractor(extract, cache, 4, stats), evaluator, composition, stop_event=stop_event,
    )


def main():
    rng = np.random.default_rng(1)
    true_a = random_structure(rng, 24)
    evaluator_a = measured_context(true_a)

    # =================================================================
    # 44. Synthetic noise onset: agreement improves, plateaus, then noise
    # peaks explode; the lowest pre-noise threshold is chosen.
    # =================================================================
    extract_a = fixture_extractor(true_a, top=3.4, bottom=1.02, noise_onset=0.83)
    cal = run(extract_a, evaluator_a)
    by_sigma = {c.sigma: c for c in cal.candidates}
    check("calibration succeeds (no fallback)", not cal.fallback_used)
    check(
        "agreement improves as real atoms accumulate (R_F 3.0σ > R_F 1.2σ)",
        by_sigma[3.0].r_all > by_sigma[1.2].r_all,
    )
    check("agreement plateaus once every real atom is present (1.0σ ≈ 0.95σ)", abs(by_sigma[1.0].r_all - by_sigma.get(0.95, by_sigma[1.0]).r_all) < 1e-9)
    check("the low-threshold noise explosion is visible in the peak counts", by_sigma[0.6].n_cell_atoms > by_sigma[1.0].n_cell_atoms + 20)
    selected_sites = extract_a(cal.selected_sigma)
    check(
        f"the lowest pre-noise threshold is chosen ({cal.selected_sigma:.2f}σ: all 24 real atoms, no noise peak)",
        len([s for s in selected_sites if s not in extract_a.noise]) == 24
        and not any(s in extract_a.noise for s in selected_sites),
    )
    check("the selected threshold is below the first all-atoms coarse point (fine search used)", cal.selected_sigma < 1.0 + 1e-9)
    check("thresholds below the noise onset are rejected", all(c.rejected for c in cal.candidates if c.sigma < 0.83))
    check("the selection is labelled all-data / non-independent (no holdout here)", "non-independent" in cal.criterion)
    check("the compact UI label", cal.compact_label() == f"EDMA: Auto · {cal.selected_sigma:.2f}σ")
    check("coarse-to-fine: at most 10 coarse + 3 fine evaluations", len(cal.candidates) <= 13)

    # =================================================================
    # 45. Different maps legitimately select different thresholds.
    # =================================================================
    true_b = random_structure(np.random.default_rng(2), 30)
    evaluator_b = measured_context(true_b, seed=8)
    extract_b = fixture_extractor(true_b, top=4.6, bottom=1.65, noise_onset=1.45, seed=5)
    cal_sf_b = run(extract_b, evaluator_b)
    cal_se_a = run(fixture_extractor(true_a, top=3.0, bottom=1.25, noise_onset=1.08, seed=9), evaluator_a, source="deblurred")
    selections = {round(cal.selected_sigma, 2), round(cal_sf_b.selected_sigma, 2), round(cal_se_a.selected_sigma, 2)}
    check(f"Superflip map A / Superflip map B / SharpED map A select different sigmas {sorted(selections)}", len(selections) == 3)
    check("no selection is the old fixed 1.20σ / 2.00σ by construction", not ({1.2, 2.0} & selections) or not any(
        c.fallback_used for c in (cal, cal_sf_b, cal_se_a)
    ))
    sites_b = extract_b(cal_sf_b.selected_sigma)
    check(
        f"map B selects its own lowest pre-noise threshold ({cal_sf_b.selected_sigma:.2f}σ: all 30 real atoms, no noise)",
        1.45 - 1e-9 <= cal_sf_b.selected_sigma <= 1.65 + 1e-9
        and len([x for x in sites_b if x not in extract_b.noise]) == 30 and not any(x in extract_b.noise for x in sites_b),
    )
    check("SharpED map A selects within its own real-atom window", 1.08 < cal_se_a.selected_sigma <= 1.25 + 1e-9)

    # =================================================================
    # 46. Composition constraint: a grossly over-populated low-threshold
    # model is not preferred merely because all-data R_F moves slightly.
    # =================================================================
    true_c = random_structure(np.random.default_rng(4), 20)
    faint = random_structure(np.random.default_rng(40), 34, min_distance=1.3)
    faint = [f for f in faint if all(np.linalg.norm(np.asarray(CELL.orth.mat.tolist()) @ ((np.asarray(f.frac) - np.asarray(t.frac)) - np.round(np.asarray(f.frac) - np.asarray(t.frac)))) > 1.5 for t in true_c)]
    evaluator_c = measured_context(true_c + [auto.PeakSite("C", s.frac) for s in faint], seed=12)
    extra = [(auto.PeakSite("C", s.frac), 0.9) for s in faint]
    extract_c = fixture_extractor(true_c, top=3.2, bottom=1.25, noise_onset=0.5, n_noise=5, seed=21, extra=extra)
    composition = [("Fe", 5), ("S", 5), ("O", 5), ("C", 5), ("H", 40)]
    cal_comp = run(extract_c, evaluator_c, composition=composition)
    cal_nocomp = run(extract_c, evaluator_c)
    selected_comp = next(c for c in cal_comp.candidates if abs(c.sigma - cal_comp.selected_sigma) < 1e-9)
    check("composition present: expected observable atoms exclude H (20, not 60)", auto.expected_observable_atoms(composition) == 20)
    check(
        f"with composition the over-populated 0.9σ model is not chosen ({cal_comp.selected_sigma:.2f}σ, {selected_comp.n_cell_atoms} atoms)",
        selected_comp.composition_ratio is not None and selected_comp.composition_ratio <= auto.OVERPOPULATION_FACTOR,
    )
    check(
        "over-populated candidates carry an explicit composition rejection",
        any("over-populated" in " ".join(c.rejected) for c in cal_comp.candidates),
    )

    # =================================================================
    # 47. No composition: still selects from agreement/stability alone.
    # =================================================================
    check("no composition: calibration still succeeds", not cal_nocomp.fallback_used and not cal_nocomp.composition_available)
    cal_nocomp_a = run(extract_a, evaluator_a, composition=())
    check("no composition: noise-onset fixture still picks the pre-noise plateau", abs(cal_nocomp_a.selected_sigma - cal.selected_sigma) < 1e-9)

    # =================================================================
    # Composition reliability gate: a placeholder composition (one formula
    # unit per element for a large cell) is treated as unavailable, never
    # as a constraint that rejects every candidate.
    # =================================================================
    placeholder = [("Ag", 2), ("S", 2), ("C", 2), ("H", 2), ("O", 2), ("N", 2)]
    check("placeholder composition -> unreliable for a 66 000 A^3 cell", auto.reliable_expected_atoms(placeholder, 66000.0) is None)
    check("plausible composition -> reliable (koala2-like: 1020 atoms in 22 540 A^3)", auto.reliable_expected_atoms([("Ag", 124), ("S", 88), ("B", 768), ("O", 40), ("H", 704)], 22540.0) == 1020)
    cal_placeholder = run(extract_a, evaluator_a, composition=[("Fe", 1), ("S", 1)])
    check("an implausible composition does not reject everything (no fallback, composition ignored)", not cal_placeholder.fallback_used and not cal_placeholder.composition_available)

    # =================================================================
    # Practical-equivalence plateau: tiny but "significant" agreement
    # differences (many reflections) do not push the choice to a higher
    # threshold than the margin allows.
    # =================================================================
    check("practical-equivalence margins are fixed central constants", auto.PLATEAU_CC_MARGIN == 0.01 and auto.PLATEAU_R_MARGIN == 0.005)
    plateau = [c for c in cal.candidates if c.on_plateau]
    check("the noise-onset fixture's plateau spans several all-atom thresholds", len(plateau) >= 2)

    # =================================================================
    # 48. Genuine holdout: acceptance uses model R_free / CC_free only --
    # corrupting ONLY work reflections cannot change the decision.
    # =================================================================
    evaluator_free = measured_context(true_a, free_fraction=0.2)
    evaluator_free_corrupt = measured_context(true_a, free_fraction=0.2, corrupt_work=True)
    check("a genuine holdout is recognized", evaluator_free.holdout_available)
    check("the acceptance mask is exactly the free set", np.array_equal(evaluator_free.criterion_mask(), evaluator_free.free_mask))
    cal_free = run(extract_a, evaluator_free)
    cal_free_corrupt = run(extract_a, evaluator_free_corrupt)
    check("holdout criterion is labelled R_free / CC_free", "R_free" in cal_free.criterion)
    check("model R_free / CC_free are reported", cal_free.selected.r_free is not None and cal_free.selected.cc_free is not None)
    check(
        "no leakage: corrupting only work reflections leaves the free-set decision unchanged",
        abs(cal_free.selected_sigma - cal_free_corrupt.selected_sigma) < 1e-9,
    )
    check(
        "...while all-data R_F does change (the corruption is real)",
        abs(cal_free.selected.r_all - cal_free_corrupt.selected.r_all) > 0.05,
    )

    # =================================================================
    # 37. Fallback: extraction failure / too few peaks -> 1.20σ / 2.00σ.
    # =================================================================
    def failing(_sigma):
        raise RuntimeError("EDMA exploded")

    cal_fail_sf = run(failing, evaluator_a, source="superflip")
    cal_fail_se = run(failing, evaluator_a, source="deblurred")
    check("EDMA failure -> Superflip fallback 1.20σ", cal_fail_sf.fallback_used and cal_fail_sf.selected_sigma == 1.20)
    check("EDMA failure -> SharpED fallback 2.00σ", cal_fail_se.fallback_used and cal_fail_se.selected_sigma == 2.00)
    check("fallback message is recorded", cal_fail_sf.message.startswith("Auto EDMA threshold inconclusive; fallback used."))
    cal_empty = run(lambda _s: [], evaluator_a)
    check("too few peaks -> fallback", cal_empty.fallback_used)

    # =================================================================
    # 38. Cache: the same map/sigma is never run twice.
    # =================================================================
    tmp = Path(tempfile.mkdtemp())
    cache = auto.EdmaCandidateCache(tmp, "a" * 64, "settings")
    stats1, stats2 = {}, {}
    first = run(fixture_extractor(true_a, 3.4, 1.02, 0.83), evaluator_a, cache=cache, stats=stats1)
    second_extract = fixture_extractor(true_a, 3.4, 1.02, 0.83)
    second = run(second_extract, evaluator_a, cache=auto.EdmaCandidateCache(tmp, "a" * 64, "settings"), stats=stats2)
    check("cache: second calibration runs EDMA zero times", stats2.get("edma_runs", 0) == 0 and second_extract.calls == [])
    check("cache: identical selection from cached candidates", abs(first.selected_sigma - second.selected_sigma) < 1e-9)
    other = auto.EdmaCandidateCache(tmp, "b" * 64, "settings")
    check("cache is keyed by the map hash (a different map misses)", other.get(1.0) is None)

    # =================================================================
    # User stop propagates (never silently turned into a fallback).
    # =================================================================
    stop = threading.Event()
    stop.set()
    try:
        run(extract_a, evaluator_a, stop_event=stop)
        stopped = False
    except InterruptedError:
        stopped = True
    check("a user stop propagates out of calibration", stopped)

    # =================================================================
    # 49. Reference independence through the real app integration: the
    # candidates are extracted with composition-only element assignment and
    # the selected sigma is identical with and without a reference.
    # =================================================================
    import phase_studio.app as appmod

    appmod.IterativeSuperflipPipelineQtGUI.save_settings = lambda self: None
    appmod.IterativeSuperflipPipelineQtGUI.load_settings = lambda self: None
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([sys.argv[0]])
    backend = appmod.IterativeSuperflipPipelineQtGUI()
    seen_reference_atoms = []
    extract_real = fixture_extractor(true_a, 3.4, 1.02, 0.83)

    def fake_run_edma(xplor_map, out_dir, prefix, ref_ctx, plimit_sigma, *args, **kwargs):
        out_dir.mkdir(parents=True, exist_ok=True)
        seen_reference_atoms.append((round(plimit_sigma, 4), len(ref_ctx.atoms)))
        sites = extract_real(round(plimit_sigma, 4))
        atoms = [appmod.AtomSite(label=f"{s.element}{i + 1}", element=s.element, frac=np.asarray(s.frac), density=1.0) for i, s in enumerate(sites)]
        cif = out_dir / f"{prefix}_edma.cif"
        appmod.write_structure_bundle(cif, CELL, SG, SG.hm, atoms, "cif")
        return cif

    def state_with(reference_atoms, work):
        (work / "map.xplor").write_text("fake map", encoding="utf-8")
        ref_ctx = appmod.ReferenceContext(
            cif_path=work / "ref.cif", work_ref_cif=work / "ref.cif", cell=CELL, spacegroup=SG,
            spacegroup_hm=SG.hm, composition="Fe6 S6 O6 C6", atoms=reference_atoms,
        )
        cfg = SimpleNamespace(
            edma_threshold_mode="auto", work_dir=work, merge_distance=0.5, edma_exe=str(work / "EDMA.exe"),
            edma_maxima="all", edma_fullcell="no", edma_numberofatoms="composition", edma_centerofcharge=True,
            edma_chlimit="0.2500", edma_chlimlist="0.0057 relative", extra_edma_keywords="",
            structure_export_format="cif", jana_inflip=None,
        )
        return SimpleNamespace(cfg=cfg, ref_ctx=ref_ctx, validation_context=None, performance_profiler=None), work / "map.xplor"

    selected = {}
    for label, reference_atoms in (("without reference", []), ("with reference", [
        appmod.AtomSite(label="Fe1", element="Fe", frac=np.asarray(true_a[0].frac), density=1.0),
    ])):
        work = Path(tempfile.mkdtemp())
        state, map_path = state_with(reference_atoms, work)
        state._edma_agreement_evaluator = evaluator_a
        seen_reference_atoms.clear()
        with patch.object(appmod, "run_edma_on_xplor", fake_run_edma):
            cif = backend._run_auto_threshold_edma_stage(state, map_path, work / "edma_superflip", "cycle_001_superflip")
        provenance = (work / "edma_superflip" / "cycle_001_superflip_edma_threshold.json")
        selected[label] = appmod.json.loads(provenance.read_text(encoding="utf-8")) if hasattr(appmod, "json") else __import__("json").loads(provenance.read_text(encoding="utf-8"))
        candidate_calls = seen_reference_atoms[:-1]
        check(f"{label}: every calibration candidate used composition-only assignment", all(n == 0 for _s, n in candidate_calls))
        check(f"{label}: the canonical CIF is produced at the selected threshold", seen_reference_atoms[-1][0] == round(selected[label]["selected_sigma"], 4) and cif.is_file())
        check(f"{label}: provenance records mode, label and candidate range", selected[label]["mode"] == "auto" and selected[label]["label"].startswith("EDMA: Auto · ") and len(selected[label]["candidate_sigmas"]) >= 10)
    check(
        "reference independence: identical selected sigma with and without a reference",
        selected["with reference"]["selected_sigma"] == selected["without reference"]["selected_sigma"],
    )
    check(
        "reference metrics appear only as validation, never without a reference",
        selected["without reference"]["reference_validation"] is None,
    )
    check("manual mode is untouched: RunConfig default is manual", appmod.RunConfig.__dataclass_fields__["edma_threshold_mode"].default == "manual")
    check(
        "Autosolve's threshold mode comes from one central constant (2.0.0: manual, per the real-data validation)",
        auto.AUTOSOLVE_EDMA_THRESHOLD_MODE == auto.EDMA_THRESHOLD_MODE_MANUAL,
    )
    launcher = (Path(auto.__file__).with_name("jana_superflip.py")).read_text(encoding="utf-8")
    check("the Autosolve launcher reads that constant (no hard-coded mode)", "win.edma_threshold_mode = AUTOSOLVE_EDMA_THRESHOLD_MODE" in launcher)

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
