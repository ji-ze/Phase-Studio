# Map Feedback restoration and scientific applicability — 2.0.3

Applied on `development/2.0.3`, preserving the existing dirty Wizard redesign.
The standing user instruction to use 2.0.3 supersedes the attached 2.0.2
references. No version increment, licence/citation/release-note change,
commit, push, publication or frozen-package rebuild occurred in this task.

## A. Root cause and repairs

`jana_superflip.py::_sync_page3_for_data_type` explicitly hid both intensity
correction and missing-reflection completion whenever
`reflection_mode_has_fwhm(mode)` was true. History identifies `97dd307`
(`Add a Map feedback page to the Jana2020 Wizard's Phase-recycling flow`)
as the introduction of this branch; `7907210` retained it when the Wizard
became a class. The implementation in `app.py::apply_map_feedback_to_reflections`
was not removed. This was a Wizard applicability restriction, not deletion
of the numerical method.

The restriction is removed for intensity correction. Missing-reflection
completion remains a single-crystal option. Submission guards exclude
powder-only repartitioning on other input types and exclude completion on
FWHM inputs, even if an inactive checkbox retains a previous checked state.

Two concrete backend defects were also repaired:

- FWHM occupies `Reflection.sigma` internally, so a positive significance
  threshold previously could divide intensity by peak width. That combination
  is rejected before FFT computation. Positive thresholds also reject datasets
  without usable finite positive uncertainties; individual invalid uncertainties
  cannot pass the significance gate.
- If repartitioning failed after intensity correction, the current reflections
  had already changed. Resume could therefore correct them twice. Both methods
  now operate on local derived reflections; the shared state is committed only
  after both methods and next-cycle HKL writing succeed.

No correction formula or successful processing order was changed.

## B. Scientific behavior

| Input | Positive threshold | Threshold zero |
|---|---|---|
| I with valid σ(I) | Original strict I/σ(I) gate | Original map-based correction without significance filtering |
| F with valid σ(F) | Strict estimated I/σ(I) ≈ F/[2σ(F)] gate (updated in 2.0.6) | Original F²/intensity update and amplitude conversion |
| I/F with FWHM | Unavailable; peak width is never used as σ | Supported by the existing numerical routine; FWHM values are retained |
| Missing/unusable uncertainty | Unavailable | Supported without uncertainty filtering |

In 2.0.6 the threshold consistently denotes I/σ(I). For positive amplitudes,
first-order propagation uses I=F² and σ(I)≈2Fσ(F), giving F/[2σ(F)]. This is
an approximation, particularly unreliable for weak amplitudes transformed from
experimental intensities; it does not recover the original measured significance.
Saved numerical values are unchanged. Historical amplitude settings used F/σ(F);
explicitly halve an old limit to retain its approximate selection if desired.
See [the focused scientific change](MAP_FEEDBACK_SIGNIFICANCE_2_0_6.md).

Zero is an actual sentinel: the code bypasses the ratio gate and updates a
reflection when its map prediction is positive. Contrary to the old tooltip,
this also includes zero observed values. The formula is preserved, and the
GUI says **all map-supported reflections**, rather than claiming either
`I/σ(I) < 0` or nonzero-only selection.

The original order is:

`current derived/observed data → intensity correction → powder repartitioning → next-cycle HKL`

Repartitioning conserves the group totals of the data it receives, including
any preceding intensity correction. The original measured file is retained
unchanged for validation. Existing method-specific logs and the powder detail
log remain; the corrected next-cycle file is
`cycle_NNN_map_feedback_for_superflip.hkl`.

Between-cycle scheduling remains `cycle >= Start after cycle` and
`cycle < total cycles`; the Wizard enforces `1…N−1`. One cycle disables and
collapses both methods, retains their values/check states, and submits both
application flags as false. Returning to multiple cycles restores editing.

Defaults/ranges/precision are retained: correction damping 0, threshold 0,
start cycle 1, separation factor 0.2, ratio mix 1 and wavelength 0. A checked
correction with damping 0 explicitly reports that no intensity update is applied.

### Wavelength

Zero is automatic detection, not a physical zero wavelength. The Wizard now
uses the existing resolver and this incoming input's matching `.m90`, followed
by `.inflip` and reference CIF. A positive manual value retains precedence.
The resolved value is submitted at full precision, independently of the
five-decimal numeric display. Missing/nonfinite wavelength blocks active
repartitioning with an actionable message; it does not block a one-cycle run
or an independent intensity-only correction.

The existing `.m90` lookup uses the incoming filename's matching stem. A
different-name companion is not guessed from another project or standalone
settings; enter the measured wavelength when automatic lookup cannot resolve it.

### Real-project probe

The actual file available in the supplied folder is `ochlor.inflip`, with
title `ochlor_Superflip`. It supplies **631 parsed I/FWHM reflections**. The
original filename is preserved. `ochlor.m90` supplies **1.541866 Å**.

Existing `run_0002/cycle_003/cycle_003_deblurred.xplor` was used for a read-only
correction probe, with damping 0.3, threshold 0, separation 0.2 and ratio mix 1.
The corrected data were serialized and read back in temporary test storage:
631 derived reflections, unchanged HKLs/FWHM fields and unchanged original data.
Mean intensity change was **40.001881%**; the subsequent powder method reported
**45.5849807594%** mean change. These are test-exercise values, not evidence of
improved structure accuracy.

- Original `.inflip` SHA-256: `21bce8a7b9641f9a484033ab295ca80be832404a892f47286f8e58a9c259af47`
- Source map SHA-256: `ce7cdadc67e9a7067216acc47da9b421ee191680c5ffd945047b190357cdc620`

Tests confirm the original input and source map bytes remain unchanged.

## C. GUI and screenshots

Compact reflection type/format rows, a small scientific-warning callout,
top-aligned content and two consistent method panels replace the tall layout.
At wide desktop widths the panels sit side by side; narrower windows stack
them. Numeric editors use 140–180 logical pixels. Inactive parameter areas
collapse, while checkboxes and applicability explanations remain discoverable.
Back/Cancel/Run stay in the fixed footer outside the single scroll area.
Science Gothic Regular/zero tracking branding, Segoe UI controls and the
product icon remain unchanged.

Actual offscreen Qt captures:

1. [Powder, one cycle](screenshots/2.0.3-map-feedback/01-powder-one-cycle.png)
2. [Powder, three cycles](screenshots/2.0.3-map-feedback/02-powder-three-cycles.png)
3. [Repartitioning enabled, automatic measured wavelength](screenshots/2.0.3-map-feedback/03-powder-enabled-auto-wavelength.png)
4. [Valid I/σ(I), synthetic fixture](screenshots/2.0.3-map-feedback/04-measured-intensity-sigma.png)
5. [Powder without σ, existing zero mode](screenshots/2.0.3-map-feedback/05-powder-no-sigma-zero-mode.png)
6. [Both methods enabled](screenshots/2.0.3-map-feedback/06-both-enabled.png)
7. [F/σ(F), synthetic single-crystal fixture](screenshots/2.0.3-map-feedback/07-single-crystal-amplitude-sigma.png)
8. [Expanded, reduced height](screenshots/2.0.3-map-feedback/08-expanded-short.png)
9. [125% Qt scale](screenshots/2.0.3-map-feedback/09-both-125.png)
10. [150% Qt scale](screenshots/2.0.3-map-feedback/10-both-150.png)

Reproduce with `packaging/tools/capture_map_feedback.py`; opt-in
`PHASE_STUDIO_TEST_INFLIP` is copied with its matching `.m90` before parsing.
The valid-uncertainty screenshots use separate synthetic I/σ and F/σ fixtures;
FWHM values are not relabelled as uncertainties.

Both expanded powder methods fit at 900×820 logical pixels without a scrollbar.
At 900×580, central scrolling is needed (85-pixel range for the real-context
captures); the footer remains visible. Narrower layouts can require more scroll.
These are Qt scale-factor renders, not physical Windows monitor/DPI acceptance.

## D. Tests and remaining acceptance

- New focused suite: **15 tests**, including **five actual cycle-engine subcases**:
  intensity alone, powder alone, both, powder failure/resume, and delayed start
  after cycle 2 in a three-cycle run. External executables are stubbed in these
  tests; the actual FFT correction routines and next-cycle HKL serialization run.
- Real project/map test is opt-in through `PHASE_STUDIO_TEST_INFLIP` and
  `PHASE_STUDIO_TEST_MAP`; both were supplied for this audit.
- Expanded geometry/footer guards pass at 100%, 125% and 150% Qt scale.
- Complete direct run: **50 scripts, 2,247 checks**.
- `unittest`: **79 tests passed**. `pytest`: **79 tests and five subtests passed**.
  These runner totals overlap the direct scripts and are not additional unique tests.
- Scientific golden checks: **46**, unchanged; Jana completion **192**;
  workflow-state **141**; model-policy **44**; Wizard geometry **74**;
  clipping **18**; normal EDMA defaults **17**; displacement **44** all pass.
- Compilation and `git diff --check` pass.

No unrelated goldens were regenerated. No Superflip, SharpED inference,
EDMA/threshold, ranking, molecular-rendering, map-origin, displacement or Jana
handoff algorithm was changed. Invalid significance/FWHM combinations now fail
explicitly; valid existing numerical goldens remain identical.

A fresh real-machine Superflip/SharpED multi-cycle run, physical Windows display
inspection and Jana GUI acceptance were not performed here. The real saved-map
probe and automated cycle tests are not claimed as those acceptance tests.

Include `jana_superflip.py`, the guarded/transactional feedback changes in
`app.py`, the focused regression suite and current Wizard redesign in the next
2.0.3 build. Existing 2.0.2 binaries and its draft release remain unchanged.
