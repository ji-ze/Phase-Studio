# HKL presentation corrections — Phase Studio 2.0.4

Implemented and verified on 2026-10-16. This pass changes HKL diagnostic presentation only. Existing unrelated working-tree changes are preserved. No version increment, EXE build, commit, push, tag or publication was performed.

## Interface changes

- Advanced diagnostics opens a separate, owned, nonmodal dialog. Seven structured sections cover provenance, counts/symmetry, absences/duplicates, values, resolution, overlap and limitations. Opening or closing it leaves the main plot and table geometry unchanged. Closing the parent also closes its details.
- A compact Data interpretation line replaces the long introductory explanations. Full scientific qualifications remain available in the details, including phase provenance, powder coverage limitations and the distinction between widths and uncertainties.
- Amplitude inputs with genuine positive finite uncertainties emphasize **signed F/σ(F)**. The summary, main significance curve and shell table use the direct ratio. The convention retains negative F and excludes invalid uncertainties and the protocol `(0,0,0)` row from physical statistics.
- The validated **derived I/σ(I) ≈ |F|/(2σ(F))** remains available in a secondary graph tab and an optional Validation column. Its explanation includes I ≈ F², σ(I) ≈ 2|F|σ(F), failure near zero, and its distinction from measured intensity significance. Existing derived statistics and weak-reflection definitions are preserved. Powder FWHM never becomes an uncertainty.
- Constant FWHM and constant 100% shell coverage use compact summary rows. Variable widths retain a curve with their original units. Missing metrics allocate no empty chart panel.
- Histograms retain the entire finite physical input range, including zero, negative values and the high-value tail. Adaptive binning is capped at 160 bins before allocating edges. Users can select linear or logarithmic **counts**; the observed-value axis stays linear. Zero/negative counts are explicit.
- Resolution Bins uses concise headings, five-decimal shell boundaries, consistent numeric precision, right-aligned numbers, left-aligned headings and exact-value tooltips. CSV/JSON retain full precision. Undefined coverage remains undefined.
- Undefined d98 reads **Not reached**, with the specified cumulative-coverage explanation. Exported d98 stays null. Neither the definition nor the validated boundary calculation changed.
- Validation explicitly labels its first-200-record preview. Search examines all parsed records while materializing at most 200 matching rows. Numeric sorting is supported; the initial preview preserves input order. Values use consistent precision with exact-value tooltips. Zero phases remain populated, and `(0,0,0)` has no physical d or sinθ/λ.
- Available overlap has a separate **Peak overlap** tab with group count, affected fraction, largest group, group-size distribution, shell overlap and the provenance/criterion. Estimated geometric groups and authoritative supplied groups are labeled distinctly.

The standard UI palette and font are retained. Scientific tables and charts do not use Science Gothic.

## Layout and screenshots

Actual PySide6 widgets were captured at `QT_SCALE_FACTOR=1`, `1.25` and `1.5`. At 1120 × 900 logical pixels, the normal/detail-open cases retain seven complete shell rows. Restricted-height 1120 × 700 cases retain three complete rows with independent table scrolling. For multiple charts, a bounded chart viewport preserves their minimum canvas height; scrolling reaches the lower charts instead of squeezing all axes into strips. This additional scrolling is confined to short windows.

Opening Advanced diagnostics and switching graph tabs preserve plot-panel and shell-table allocation. Footer actions remain accessible. Geometry measurements are saved alongside each screenshot set. Representative screenshots were also inspected visually, including the large Validation preview, real amplitude and powder charts, estimated-overlap tab, structured details and the restricted-height chart viewport.

- [Before: expanded overlap diagnostics](../screenshots/2.0.4-hkl-presentation/before/scale-1/08-synthetic-estimated-overlap.png)
- [After: overlap tab](../screenshots/2.0.4-hkl-presentation/after/scale-1/08-synthetic-estimated-overlap-overlap.png)
- Structured-details capture remains in local acceptance evidence because it
  contains a personal filesystem path; see the [public samples](../screenshots/2.0.4-hkl-presentation/README.md).
- [Real ochlor: constant width](../screenshots/2.0.4-hkl-presentation/after/scale-1/02-real-ochlor-completeness-constant-fwhm.png)
- [Real 2int3total: Validation](../screenshots/2.0.4-hkl-presentation/after/scale-1/10-real-2int3total-validation.png)
- [Real 2int3total: 150% Completeness](../screenshots/2.0.4-hkl-presentation/after/scale-1.5/11-real-2int3total-completeness.png)
- [Restricted height: lower charts at 125%](../screenshots/2.0.4-hkl-presentation/after/scale-1.25/15-real-2int3total-restricted-height-charts-bottom.png)

All before/after captures, exported plots, CSV/JSON and geometry records are in `docs/screenshots/2.0.4-hkl-presentation/{before,after}/scale-{1,1.25,1.5}/`. Before captures preserve the preceding modernization baseline.

## Read-only real-data verification

| Project | Parsed records | d_min (Å) | d98 (Å) |
|---|---:|---:|---:|
| ochlor | 631 | 1.1990790613015834 | 1.1990790613015834 |
| 2int3total | 328606 | 0.7255092594101177 | 0.8161153076022714 |

Both frozen diagnostic reports, all existing shell fields and source-file hashes remained unchanged. The existing ochlor boundary correction is preserved, not newly introduced by this pass. `2int3total` has 328605 physical reflections plus its protocol origin record. All 328606 numerical zero phases are populated, with unverified experimental provenance; 67888 physical amplitudes are zero.

For `2int3total`, the added direct F/σ(F) has mean **4.010747623362957** and median **0.6666518834009494**. Existing derived I/σ(I) remains mean **2.0053738116814785**, median **0.3333259417004747**. The presentation adapter took approximately 0.143 s for this loaded dataset and caches its result. The new fields supplement exported diagnostics; existing derived fields retain their definitions and values.

Input SHA-256:

- ochlor: `9136270c5e8ab6850ac6bd4390c301f17a32dcc83994184d8562735b9a26b88c`
- 2int3total: `07a3de15e54ba130f75e960358aef1ff6087b09f0ea5d9604f00090cb9d21642`

The validated `phase_studio/hkl_diagnostics.py` engine is byte-identical to the start-of-pass snapshot, SHA-256 `019f81c01634299b55329e75053d2d0e774d9b065b7bd0465e7fdb40c9520142`.

## Targeted ochlor overlap investigation

Read-only inspection covered the Jana `.inflip`, `.m90`, `.m50`, `.ref`, `.prf`, `.usd`, logs and existing powder-workflow run folders. The `.m90` files provide wavelength **1.541866 Å**. The current input contains constant **0.0527** FWHM but does not explicitly bind its width units or complete group membership. Profile/refinement files do not establish a reliable mapping of the width-like columns to this exact input.

Historical powder-repartitioning logs do exist: run_0004/cycle_001 reports 91 groups/193 members; run_0006/cycle_003 reports 139 groups/336 members. They record wavelength 1.54, expose only the first three groups' memberships, and lack a source-hash binding; the latter also has widths differing from the current input. They are insufficient to reconstruct complete authoritative groups for the current 631-row source. They were not imported as current metadata. No repartitioning or intensity modification was run.

Real ochlor therefore retains **Overlap analysis unavailable — insufficient peak-width or profile metadata**. Finding a wavelength alone does not establish the missing width-unit/source correspondence.

The explicitly synthetic known-unit fixture uses 48 HKL, 1° 2θ widths, wavelength 1 Å and separation factor 1. It produces 12 estimated groups affecting 41 reflections (85.4%), largest group six. These are geometric estimates, not experimentally independent observations. Separate controlled supplied-group tests cover authoritative-group handling.

## Verification

- Complete pytest suite: **290 passed, 1 skipped, 37 subtests passed**, 243.56 s.
- Final focused HKL scientific/presentation/GUI run: **24 passed**, 21.59 s. GUI checks execute at all three DPI scales, including geometry stability across details and overlap tabs, histogram tails, direct/derived metrics, precision, search, exports, closing and cancellation.
- Existing scientific/UI/Jana standalone check scripts: **709 checks passed**: scientific core 46, final UI 30, Jana completion 192, workflow states 141, density alignment 41, displacement parameters 44, wizard hierarchy 21, redesign 44, tile icons 58, geometry 74 and text clipping 18.
- No unresolved test failures. The one suite skip is the existing opt-in real-project Map Feedback test without `PHASE_STUDIO_TEST_INFLIP`; real-data HKL acceptance was run separately on both projects.
- Read-only real-project audit and full-precision exports: `build/hkl-presentation/real-acceptance.json`, `real-audit.log` and `*-presentation.{json,csv}`. Test logs are in the same build directory.

The full suite was followed by focused verification of the final presentation adjustments. Scientific golden checks passed; the UI decision does not change selection metrics or scientific processing.

## Files and limits

This pass changes one production module, `phase_studio/hkl_diagnostics_ui.py`. Supporting changes are `tests/test_hkl_diagnostics_ui.py`, new `tests/test_hkl_presentation.py` and `tests/test_hkl_presentation_ui.py`, the capture tool, new `packaging/tools/audit_hkl_presentation_204.py`, this report and acceptance artifacts. The engine, application entry points, authentication, Superflip/SharpED/EDMA processing, ranking, map normalization, Jana handoff and scientific writers were not changed by this pass.

Real-data numerical testing, synthetic fixture testing and offscreen Qt visual testing were performed separately as described above. Manual acceptance on a physical monitor and real Jana2020 GUI acceptance were **not** performed. At 150%, a 1120 × 900 logical-pixel window is larger than a 1920 × 1080 physical display; the additional restricted-height/narrow captures exercise the constrained layout, but do not replace testing on the user's monitor. Complete source-matched ochlor overlap membership and explicit current width units remain unavailable.
