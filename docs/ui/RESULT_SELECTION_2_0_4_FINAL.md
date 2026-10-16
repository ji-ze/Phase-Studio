# Jana2020 Result Selection — 2.0.4

Implemented on `development/2.0.4`, preserving the existing dirty work tree.
No distribution rebuild, installer, commit, push, tag or publication.

## Default and publication identity

`app.py::_initial_result_source` now prefers `deblurred` when the configured
combined workflow has completed SharpED candidates. Feed-forward settings and
an old Wizard preference no longer initialize an ordinary combined run on
Superflip. Explicit Autosolve `initial_source` callers retain their goal-family
override. Superflip-only runs keep the Superflip family.

Each family's recommendation still comes from its independent existing
`recommend_best_result` call. The selected table row initializes from that
recommendation. The same selected candidate drives preview identity, threshold,
ASU metadata, Jana count, bottom summary and `_start_jana_handoff`.

Closing the selector saves its in-memory family and per-family selection keys,
representation and rotation preference. Reopening the same run restores those
keys against the newly completed candidate objects; a different run resets
defaults. No candidate is restored by table row number alone, and no selection
is persisted globally in QSettings. Resizing and threshold completion do not
change the selected family. A missing SharpED result produces an explicit
Superflip fallback message. No selected candidate, missing map, pending EDMA or
missing required Jana model disables Pass with an explanation.

The publication authority/transaction was not changed. The real filesystem
handoff regression now deliberately starts with an older Superflip Wizard
preference and accepts the selector without touching a tab. It verifies the
recommended SharpED candidate's scientific map and matching model reach Jana,
preserving canonical outputs, original context, alignment validation, atomic
failure behavior, and absence of workflow reruns.

## UI and viewer

- One-line family tabs: **Charge-flipping solution / Structure prediction**.
  Active background `#001170`, white text, separate cyan keyboard focus.
- Compact assessment, source, completed/recommended cycles. Reference and
  holdout details appear when relevant; no duplicate disabled-holdout field.
- Concise footer scientific warning. Superflip uses a phase-assessment note in
  the same region, rather than an empty large warning spacer. Family switching
  retains the same canvas geometry.
- Top controls: cycle navigation, Fit, Fullscreen. Secondary row: threshold
  controls, representation and auto-rotation. Reset remains available with R
  on the focusable canvas, documented by Fit's tooltip; drag/pan/zoom remain.
- ASU and actual Jana model count remain visible. Raw EDMA peaks, retained
  sites, rendered/expanded atoms and identity are available in tooltips without
  treating them as interchangeable counts. The handoff summary includes the
  actual selected family/cycle/threshold and Jana model count.
- Existing projected Fit already targets 78% occupancy; it was retained rather
  than modifying coordinates or enlarging atom markers. At 1500×900 logical
  pixels, the identical fixture canvas grows from **1028×299 to 1028×355**:
  **18.7% more height**, measured against the released HEAD selector. Fit tests
  measure projected geometry at 0.78 occupancy, not marker sizes.
- Complete molecules fit reconstructed visible geometry; Full cell includes
  crystallographic cell segments. Nonorthogonal cells are covered. Candidate
  switches refit while keeping viewing orientation; asynchronous threshold
  generations preserve manually changed camera limits even when CIF hash
  changes. Explicit Fit refits; fullscreen reuses the live viewer.

Presentation files changed: `result_selection.py`, `app.py`,
`autosolve_window.py`, `autosolve_review.py`, `jana_superflip.py`.
The latter modules update display/log terminology only. API identifiers such
as `PEAK A (model prediction)` and `SEED (cyclic CF)`, source IDs, metrics CSV
schema and ranking formulas remain unchanged. Authentication code, branding
authority, license, citation and API terms were not modified in this pass.

## Scientific audit

R factor compares original measured amplitudes with scaled FFT map amplitudes;
Amplitude CC is their Pearson correlation. Superflip's imposed amplitudes can
produce R ≈ 0 and CC ≈ 1 even with wrong phases. These are amplitude consistency
diagnostics, not independent refinement/phase validation. Tests demonstrate
identical amplitude metrics with differing phases and differing C3.

Recommendation is lexicographic within the selected family/profile:

| Profile | Metric order |
|---|---|
| Reference + holdout | Reference F0.5, R_free, OMIT CC |
| Reference only | Reference F0.5, matched RMSD, reference phase agreement |
| Holdout only | R_free, CC_free, OMIT CC |
| Reference-free | Amplitude R, Amplitude CC, triplet C3 |

Later metrics break ties within the existing absolute/relative `1e-12`
tolerance; missing tie-breakers are skipped. Remaining ties prefer a complete
result, then the earliest cycle, then the existing stable source order. C3
alone therefore need not select the winner. Table cells expose unrounded
values because three decimal places can hide the decisive R difference.
Nonfinite/unavailable displayed values use `n/a`; calculations are unchanged.

For the captured historical ochlor SharpED candidates, R is approximately
0.455/0.462/0.445: Cycle 3 wins the first criterion, although Cycle 1 has the
higher C3. In its selected EDMA output there are **21 retained EDMA sites** and
**12 Jana model sites**. The composition-constrained Jana export is a separate
model authority; threshold changes need not increase its site count. The UI
does not force raw peaks into the Jana model or invent missing provenance.

No new scientific inconsistency was found. Golden outputs, alignment and
0.010–0.150 Å² displacement limits remain unchanged.

## Tests and acceptance evidence

- Complete pytest: **257 passed, 1 skipped, 37 subtests passed** (209.65 s).
- Final focused selector: **13 passed**, including default/candidate/summary/
  handoff identity, same-run persistence/new-run reset, fallback, nonorthogonal
  fit, pending/missing-model guard and camera retention.
- Jana completion: **192 checks passed**, including default no-interaction
  filesystem publication, manual override, stop, mutation and atomic failure.
- Selector/viewer: **72 checks passed**.
- Density alignment: **41 checks passed**.
- Scientific golden: **46 checks passed**, no scientific output differences.
- Displacement export: **44 checks passed**.
- Workflow state: **141 checks passed**; Autosolve routing: **34 passed**;
  review EDMA: **20 passed**; fullscreen script passed all its checks.
- Distribution/scientific AST guards remain active. Only the explicitly
  requested display literal is normalized in the historical AST comparison;
  affected scientific functions were not excluded.

Logs: `build/result-204-*`. Subsequent final focus/metadata accessibility changes
were checked by the focused selector suite and regenerated screenshots.

Actual PySide6 QtAgg screenshots (not mockups):

- `docs/screenshots/2.0.4-result-selection/after/scale-1/`
- `docs/screenshots/2.0.4-result-selection/after/scale-1.25/`
- `docs/screenshots/2.0.4-result-selection/after/scale-1.5/`

Each scale has 21 images: default/recommended candidate, manual family/cycle,
elongated/dense fit, Full cell/Complete molecules, pending/completed threshold,
count distinction, selected summary, reduced height, unavailable candidate and
fallback, plus replay of the existing ochlor outputs. Per-image JSON records
DPR, actual geometry, selection, file hashes and measured projected fit.
`20-real-project-default.png` shows the existing ochlor SharpED recommendation;
`16-real-project-sharped.png` and `17-real-project-superflip.png` show both
real output families. Other images use clearly synthetic file-backed fixtures
and simulated asynchronous callbacks; they are not new production calculations.
The real-project replay retains the label that reflection provenance was not
recorded in its historical metrics rather than asserting new validation.

`packaging/tools/capture_results_204.py` reproduces captures. A released-source
comparison is under `before/scale-1/`. Scientific file hashes are checked while
capturing; no original project file is changed and no new inference is submitted.

Remaining workstation acceptance: launch the current source build from actual
Jana2020, accept the untouched default SharpED candidate, inspect/refine in Jana,
and confirm the native window-manager/fullscreen behavior on the target monitor.
Automated tests cover the publication transaction with controlled external-tool
fixtures; screenshots alone do not constitute independent crystallographic
validation or a new real Jana refinement acceptance. Existing EXEs intentionally
remain from the preceding task until a separate build request.
