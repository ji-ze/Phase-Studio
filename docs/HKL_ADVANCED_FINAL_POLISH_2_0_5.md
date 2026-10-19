# HKL Advanced Diagnostics final polish — 2.0.5

The user's subsequent version instruction assigns **all changes since the
published `v2.0.4` tag to 2.0.5 (unreleased)**, superseding the original polish
prompt's instruction to retain 2.0.4. This report and the new evidence therefore
use 2.0.5. No commit, push, tag, EXE build or public release was performed.

## Focused changes

The existing seven-tab dialog, scientific report authority, disclosures,
QSettings namespace and export formats remain. This is not a new architecture.

- `phase_studio/hkl_diagnostics_ui.py`: preferred initial geometry changes from
  **1050 × 600** to **1050 × 530 logical pixels**. The window remains resizable;
  saved dimensions/tab selection and available-screen clamping are preserved.
  Labels now use regular weight; section headings and primary values retain
  emphasis. Provenance, methodology and caveats use muted context colors. The
  Input fields are spaced into three aligned logical groups.
- Values separates input integrity, phase diagnostics, and value/width
  statistics. Verified powder labels use **Median FWHM (°)** and **FWHM range
  (°)**, with the degrees-2θ convention retained separately and in tooltips.
  FWHM is explicitly an angular width, never a measurement uncertainty.
- Resolution displays **Analyzed resolution range: d ≥ [dataset minimum] Å**.
  The full original definitions remain; the equivalent reciprocal-space interval
  is an additional presentation explanation using the same existing boundary.
- Peak overlap retains the four approved metrics and adds a compact dynamic
  group-size distribution line. Full group details, methodology, provenance and
  the independence/no-repartitioning warning remain. No new chart was added.
- Availability uses a scoped light-blue selection (`#e8f0fa`) and dark-blue text
  (`#153c70`), with a thin keyboard-focus border. Viewport-relative columns are
  25% / 18% / 57%. Wrapped rows determine table height; the tab's outer scroll
  area handles overflow, rather than nesting a second table scrollbar.
- `phase_studio/scientific_typography.py`: the existing shared renderer now
  recognizes standalone lambda/theta/alpha/beta/gamma words as Greek variables.
  Scientific variables remain italic and descriptive subscripts upright. Raw
  filenames and copied/full input paths remain literal, including names such as
  `alpha.hkl` inside a `lambda` directory. No protocol keys were renamed.

Scientific labels continue to use the normal application UI font. Science Gothic
branding policy is unchanged. Native mouse/keyboard selection and selected-row
explanation updates remain functional; statuses are still words, not color-only
indicators. No availability rule was changed for visual consistency.

## Seven-tab review

| Tab | Final behavior |
|---|---|
| Input | All provenance fields, literal filename/full-path copy, regular labels, aligned groups and scientific cell notation |
| Counts & symmetry | Approved two-column structure, bold section headings/primary 631 count, regular field labels and italic cell variables |
| Absences & duplicates | Conditional all-clear summary emphasized; original examples, N/A semantics and interpretation notes retained |
| Values | Three distinct sections; actual phase-field availability; observed-value subscripts; explicit angular widths |
| Resolution | Dataset-derived d-min/d-98/coverage and clear lower-bound range; original methodology and powder caveat |
| Peak overlap | Original four KPIs, one compact distribution line, full disclosures and read-only scientific caveat |
| Availability & limitations | Subtle readable selection, proportional columns, wrapped reasons, keyboard selection and complete selected explanation |

All seven tabs retain the same outer geometry during navigation and disclosure
changes. Close remains outside the scrollable page. Longer Values content and
expanded methodology scroll vertically. No unnecessary horizontal scrollbar was
observed at normal desktop sizes; constrained-screen guards also pass.

## Scientific invariants

Real inputs were checked against the existing retained baseline in
`build/hkl-presentation/real-acceptance.json` before constructing the final
dialogs. Reports are prepared once and reused for all DPI rendering; the
capture process does not calculate scientific metrics while rendering.

| Quantity | Existing baseline | Final |
|---|---:|---:|
| ochlor parsed / literal / independent records | 631 / 631 / 631 | 631 / 631 / 631 |
| ochlor minimum resolution (Å) | 1.1990790613015834 | 1.1990790613015834 |
| ochlor cumulative 98% boundary (Å) | 1.1990790613015834 | 1.1990790613015834 |
| ochlor overlapping / total / non-overlapping groups | 91 / 529 / 438 | 91 / 529 / 438 |
| ochlor affected records | 193 / 631 | 193 / 631 |
| ochlor affected fraction (%) | 30.5863708399 | 30.5863708399 |
| ochlor overlap input-intensity fraction (%) | 21.0635613111 | 21.0635613111 |
| ochlor group sizes 2 / 3 / 4 | 81 / 9 / 1 | 81 / 9 / 1 |
| ochlor median FWHM (degrees 2θ) | 0.0527 | 0.0527 |
| 2int3total parsed records | 328606 | 328606 |
| 2int3total minimum resolution (Å) | 0.7255092594101177 | 0.7255092594101177 |
| 2int3total cumulative 98% boundary (Å) | 0.8161153076022714 | 0.8161153076022714 |
| 2int3total mean F/σ(F) | 4.010747623362957 | 4.010747623362957 |
| 2int3total median F/σ(F) | 0.6666518834009494 | 0.6666518834009494 |

Input hashes are unchanged:

- ochlor: `9136270c5e8ab6850ac6bd4390c301f17a32dcc83994184d8562735b9a26b88c`.
- 2int3total: `07a3de15e54ba130f75e960358aef1ff6087b09f0ea5d9604f00090cb9d21642`.

Within each DPI run, report-only JSON exports before and after navigation are
byte-identical. CSV exported after rendering is byte-identical to the prepared
CSV for that dataset. JSON/CSV keys and schemas are unchanged. Real powder
widths and genuine amplitude uncertainty columns retain their existing meaning.

`app.py`, `hkl_diagnostics.py` and `powder_diagnostics.py` remain identical to
HEAD after normalizing Git line endings. AST checks confirm the existing
`presentation_report`, `_report`, `number` and `_display_number` authorities
are unchanged. No new scientific calculation was added to the dialog renderer.
The earlier validation entry point's use of the existing analysis authority is
unchanged by this focused pass. Superflip, SharpED, EDMA, original observations,
reflection grouping, symmetry, numerical goldens and Jana handoff were untouched.

## Version designation

- `phase_studio/version.py` is now **2.0.5**, the single runtime/package/build
  resource authority; `phase_studio.__version__` agrees.
- `CITATION.cff` and README citation examples are 2.0.5. The previous release
  date is not falsely attached to an unreleased version.
- README distinguishes current development 2.0.5 from published 2.0.4.
- `RELEASE_NOTES_2_0_5.md` covers the earlier Wizard geometry work, shared HKL
  typography, completeness/overlap tables, this polish and post-tag repository
  hygiene follow-ups. It is a local draft, not a GitHub release.
- Current capture tools use the runtime version for output directories; older
  filenames/evidence are retained as historical snapshots. Earlier local
  acceptance reports now explain their assignment to the 2.0.5 development cycle.
- Update-notification tests use a future version derived from the runtime
  version, preventing an old mocked 2.0.5 release from being mistaken for a newer
  release after this bump. Production update logic is unchanged.
- Generated Windows version-resource bytes were checked in memory as 2.0.5.
  No old 2.0.4 executable or ZIP was relabelled as a new build.

The prior dirty Wizard implementation and unrelated `docs/workshop/` drafts
were preserved. This designation does not publish local workshop drafts.

## Tests and visual evidence

New/updated guards are in `tests/test_hkl_advanced_ui.py`,
`tests/test_hkl_ui_refinement.py`, `tests/test_about_version.py` and
`tests/test_update_ui.py`. Existing HKL, powder, completeness and Wizard tests
remain in place.

Version expectations in `tests/test_split_distribution.py`,
`tests/test_execution_logging.py` and `tests/test_jana_completion.py` now follow
the requested 2.0.5 designation. The successful Jana integration fixture uses
the runtime version; the deliberately mismatched older fixture and rejection
guard remain. An initial full run's sole failure was the old canonical 2.0.4
expectation, not a numerical or workflow regression.

- Final focused HKL/powder/typography/update/Wizard set: **49 passed** (65.72 s).
- Final geometry guard after table scroll policy adjustment: **1 passed**
  across 100%, 125%, 150% (4.79 s).
- Final filename/typography/metadata/update guards: **14 passed** (15.22 s).
- Scientific golden checks: **46 passed**.
- Jana completion/handoff guards: **192 passed**.
- Project/run logging guards: **16 passed**.
- Distribution/version guards: **22 passed**.
- Final complete pytest: **368 passed, 1 skipped, 37 subtests passed** in
  **375.15 s**, `build/hkl-advanced-final-205-completed-suite.log`. The skip is
  the existing opt-in real-project applicability test.
- Python compilation and `git diff --check`: passed.

Actual final-code screenshots and geometry/export evidence:
`build/acceptance-hkl-advanced-final-2.0.5/index.html`.

There are **39 screenshots**: all seven ochlor tabs plus expanded overlap,
resolution and availability methodology, and the real 2int3total Values,
Resolution and Availability tabs at **each** of 100%, 125%, 150% Qt scaling.
All captures use real retained reports, not reconstructed mockups or synthetic
observations. Each dataset's seven tabs are navigated and checked even where
only representative amplitude screenshots are saved.

Every DPI run checks fresh 1050 × 530 geometry, unchanged geometry through
navigation/expansion, fixed Close, absent horizontal scrolling, proportional
availability columns, keyboard selection, literal source paths and restored
explicit 1100 × 650 user resizing. Existing tests check 640 × 420 screen clamping.
All 39 screenshots were visually inspected in DPI contact sheets; Peak overlap,
Availability and Resolution were additionally inspected at full size.

The source tool is `packaging/tools/capture_hkl_advanced_final_205.py`.
Its preparation phase takes the authorized real amplitude input through
`PHASE_STUDIO_LARGE_INFLIP`; the rendering phase uses its locally prepared report
cache and makes no server, phasing or handoff request. Evidence includes
`numerical-invariants.json`, `preservation.json`, `version-verification.json`
and per-DPI geometry/unchanged export files.

## Limits

These are actual offscreen PySide6 windows with a declared 2560 × 1600 physical
pixel work area and real device-pixel ratios. Live Windows monitor transitions,
native title bars and a real Jana2020 session were not manually accepted in this
pass. The Values tab and expanded methodology may require vertical scrolling at
the compact preferred height; the Close action remains visible. Existing saved
geometry is deliberately restored rather than overwritten by the new default.

The existing EXE distributions remain their original versions. Preparing or
publishing 2.0.5 binaries is a separate task requiring an explicit request.
