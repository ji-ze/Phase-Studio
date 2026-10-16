# HKL Advanced Diagnostics — focused 2.0.4 acceptance

## Scope and corrections

This pass changes only the Qt advanced diagnostics presentation and its tests. Version remains 2.0.4. No release EXE, commit, push, tag or release is produced by this task.

- Initial size is 1000 × 570 logical pixels, clamped by the existing screen geometry authority. The dialog remains resizable; its geometry, client size and selected tab use dedicated `hklAdvanced/*` QSettings keys. Switching tabs never resizes the window. Each tab has one content scroll area; Close stays outside it.
- Seven readable tabs retain the existing categories, with escaped literal ampersands, distinct keyboard mnemonics and a scrollable tab bar. Shared two-column rows provide constrained labels, top-aligned wrapping values, selectable scientific text and consistent spacing. Diagnostic fonts remain the standard UI font; branding fonts are not applied.
- Input starts with the filename and scientific context. Full paths remain in the report, filename tooltip, Copy full path action and expandable source provenance. Known Jana2020/Superflip file provenance is distinguished from undocumented experimental observation processing, merging and scaling history.
- Verified space-group settings use Gemmi's short symbol with screw subscripts and international number, for example P2₁/n (#14). Exact original Hermann–Mauguin setting and Hall symbol remain accessible; no symmetry operators or transformations change. Cell lengths and angles have explicit units and consistent precision.
- Absences/duplicates retain all existing counts and representative examples. The all-clear summary is conditional on actual relevant counters and warnings. Significance is N/A when genuine measurement uncertainties are absent, never an uncomputed zero.
- Values separate integrity from intensity/width or amplitude/uncertainty statistics. A verified format without phases shows **N/A — phase column not supplied**, rather than missing/finite/nonfinite counters. Formats with a phase column retain the original three counters. Unverified column semantics are explicitly distinguished. FWHM remains a width in verified degrees 2θ, never a measurement uncertainty.
- Resolution shows concise coverage/d98 definitions and the powder independence caveat. Expandable full definitions preserve the allowed domain, input d_min, 000/absence exclusions, Friedel convention, reciprocal tolerance and cumulative-boundary caveats. Applicable direct and derived significance statistics remain available.
- Peak overlap has four compact key metrics, the complete detailed counts/distribution, expandable metadata/methodology and the independence/read-only limitation. All values come from the existing report. No repartitioning or overlap recomputation is triggered by the detail view.
- Availability is a dynamic Analysis / Status / Reason table. Row selection reveals the full original scientific explanation. Estimated geometric overlap is Limited; missing genuine uncertainties make significance Unavailable; verified genuine uncertainties make it Available (or Limited if some records are unusable). Full method/provenance notes remain expandable.

## Counter inspection and scientific preservation

The existing parser/counters were inspected first. For formats without a phase column, `phase_missing` is intentionally zero; for phase-bearing formats it counts parsed records with `phase is None`. `phase_nonfinite` counts present nonfinite values, while finite zero degrees is populated. Presentation is the defect, so parser and counting code were not changed. Tests exercise no phase column, valid zero phase, a missing `?` phase and nonfinite `inf` phase. Existing parser handling of literal `nan` was not reinterpreted.

`phase_studio/hkl_diagnostics.py`, `powder_diagnostics.py` and `app.py` retain their pre-task SHA-256 hashes. Existing scientific expected values/golden files are untouched. JSON and CSV exports are byte-identical between the pre-task presentation adapter and the updated dialog, for both actual reference inputs; diagnostics objects are also unchanged by opening/using the view.

| Reference | Records | d_min (Å) | d98 (Å) |
|---|---:|---:|---:|
| ochlor | 631 | 1.1990790613015834 | 1.1990790613015834 |
| 2int3total | 328606 | 0.7255092594101177 | 0.8161153076022714 |

ochlor overlap remains: 529 total groups, 438 singletons, 91 overlapping groups, 193 affected records (30.586%), largest group four, intensity fraction 21.064%. Distribution remains 81 groups of two, nine groups of three and one group of four. Membership in the unchanged exported diagnostics is identical.

The original `<local-project>/ochlor_Superflip.inflip` is no longer present. The accepted real-data reference is its previously retained byte-identical copy, `build/powder-final/wizard-input/ochlor_Superflip.inflip`, with matching Jana `.m90`. Its SHA-256 is `9136270c5e8ab6850ac6bd4390c301f17a32dcc83994184d8562735b9a26b88c`. The current different `ochlor.inflip` was not silently substituted. `2int3total.inflip` is read directly from the existing local dataset and its prior source hash is verified. Original inputs are unchanged.

## Visual acceptance

All seven tabs were individually captured and visually inspected at 100%, 125% and 150%: **21 actual PySide6 client-area screenshots**. Final recaptures are byte-identical to those inspected. Images show the real ochlor reference diagnostics, not fabricated numerical fixtures.

Directory: `build/acceptance-hkl-advanced-2.0.4/scale-{1,1.25,1.5}/`.

Each contains `01-input.png`, `02-counts-symmetry.png`, `03-absences-duplicates.png`, `04-values.png`, `05-resolution.png`, `06-peak-overlap.png`, `07-availability-limitations.png`.

All retain 1000 × 570 logical geometry across tab changes, readable text, visible Close, no overlapping labels and no horizontal scrollbar. The controlled offscreen capture supplies a 1920 × 1040 physical-pixel available desktop and actual Qt device scale. Tests separately clamp a restored oversized dialog into 640 × 420 available geometry with Close still visible. This is controlled Qt/DPI acceptance, not a physical multi-monitor Windows/Jana acceptance test. Longer expanded details use the single outer tab scroll area.

Captures, source snapshots, before/after exports and local verification scripts stay in the ignored build directory. The existing public Wizard screenshot collection remains exactly ten images and is unchanged.

## Changed files and verification

- `phase_studio/hkl_diagnostics_ui.py`: reusable information rows, disclosures, geometry/state persistence and all seven detail tabs.
- `tests/test_hkl_advanced_ui.py`: phase semantics, actual availability, space-group display, path/provenance, absent uncertainties, metadata, unchanged exports, geometry/state and three-scale checks.
- `tests/test_hkl_diagnostics_ui.py`: selects the capability row before asserting that its full CC1/2 explanation is accessible.
- This acceptance report.

Compilation and Git whitespace checks pass. Final focused HKL/powder/presentation/UI tests: **35 passed**, zero failed (29.45 seconds). Complete suite: **304 passed, 1 skipped, 37 subtests passed**, zero failed (267.48 seconds). The skipped test is the existing opt-in real workflow check; no claim of new live inference is made. Separate scientific/Jana/UI scripts passed 494 checks: scientific core 46, Jana completion 192, workflow state 141, Jana density alignment 41, displacement parameters 44 and final UI 30.

Local evidence includes `focused-final.log`, `full-suite.log`, the six `test_*.log` files, `real-data-verification.json`, `scientific-source-before.json`, `visual-inspection.json` and each scale directory's `acceptance.json`, all under `build/acceptance-hkl-advanced-2.0.4/`.

No internet research, server inference, authentication changes or real Jana GUI acceptance was performed. Unknown experimental processing provenance remains unknown; geometric overlap and HKL coverage do not establish independent powder measurements.
