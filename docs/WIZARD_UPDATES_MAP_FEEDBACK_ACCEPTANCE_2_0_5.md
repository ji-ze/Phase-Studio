# Wizard, updates and Map Feedback acceptance — 2.0.5

Date: 2026-10-18. Version remains 2.0.5. Existing dirty work was retained. No build, commit, push, merge, release, live GitHub request or paid SharpED inference was performed.

## Findings and scope

The preceding responsiveness/update pass already provides measured Input Summary columns, reduced spacing, shared geometry, safe restore, Jana-relative initial centering, native menu placement, asynchronous public release checks, persistence, successful-check interval and retry backoff. These implementations were reused and exercised again, rather than duplicated. See `WIZARD_RESPONSIVENESS_AND_UPDATES_2_0_5.md` for baseline measurements and backend details.

The original physical-screen clipping was not reproduced in controlled Qt at 950×990 or 790×825 logical pixels. Shorter windows legitimately scroll above the fixed footer. Existing corrections recover 17 logical pixels at normal width and 63 pixels of scroll extent at 790-pixel width. This pass does not claim a newly identified native Jana/DPI root cause. Initial layout, icons, card labels, model-selection policy and navigation are retained.

Confirmed remaining defects were an unconditional scientific warning, unconditional combined-order explanation, an uncertainty-inappropriate correction section title, and a numeric wavelength editor that rounded manual values to five decimal places. Reducing the cycle count could also silently clamp a previously selected start cycle.

## Implemented changes

Map Feedback now derives its callout directly from the same checkboxes, numeric editors, parsed data capability and wavelength resolver used by submission. It introduces no separate saved settings or scientific state machine.

| State | Presentation |
| --- | --- |
| Both methods off | **Map Feedback disabled**, neutral information icon; no modification warning or operation sequence |
| One-cycle workflow | Requires at least 2 cycles; checkboxes unavailable, stored selections and values retained |
| Checked method with zero effect | Explicit **This setting currently has no effect** explanation |
| At least one eligible operation | Compact **Scientific warning** to validate against original measured diffraction data |
| Active plus ineffective method | Warning for the active method plus identification of the ineffective selection |

Every callout distinguishes immutable original experimental input from derived reflection data supplied to subsequent cycles. Turning Map Feedback off does not claim that unrelated workflow processing is disabled.

The cycle summary reports the configured count and each effective method's actual eligible subsequent range. With three cycles and start after 1, this is 2–3; start after 2 affects cycle 3. Sequence text appears only for applicable effective methods and retains the existing order: completion/intensity correction before powder repartitioning, then next cycle. A positive configuration is described as something that **may** affect values, not a guarantee that a particular map contains useful predictions or overlapping reflections.

Zero intensity damping, zero maximum additions and zero powder mix are recognized as numerically ineffective configurations. Threshold zero remains a valid special mode selecting map-supported predictions without significance filtering. No numeric parameter is changed to make a method effective.

When cycle count decreases, an existing later start value remains intact rather than being clamped away. Existing Run validation blocks a start leaving no subsequent cycle. Switching to one cycle disables feedback without clearing selections, and returning to multiple cycles preserves parameters. Existing session-only default-off policy remains: no new cross-project automatic enabling or QSettings migration is introduced.

## Scientific terminology and wavelength

Without verified genuine uncertainties, the section is **Map-supported intensity correction (experimental)**, with a no-σ-filter checkbox and explicit threshold-zero explanation. With genuine uncertainties, existing weak-reflection wording, I/σ(I) gate (measured for intensity inputs; estimated as F/[2σ(F)] for amplitudes, a first-order approximation updated in 2.0.6) and completion controls remain. Powder controls depend on parsed FWHM capability, not filenames. FWHM is explicitly **peak width in degrees 2θ**, not σ(I).

Automatic wavelength continues to use the existing resolver: manual entry, matching Jana .m90, .inflip metadata, then reference CIF. The resolved value and source are displayed when automatic repartitioning is enabled. Missing wavelength produces an input requirement and blocks invalid repartitioning through existing validation; no radiation value is guessed. The manual editor now retains eight decimal places, including 1.541866 Å, while zero still means Automatic. The screenshot wavelength comes from a matching **synthetic** .m90 fixture; it is not a claim of live ochlor execution.

Disabled methods retain concise checkbox summaries and hide their parameters/extended explanations. Enabled methods expose the existing controls in independent balanced columns at wide widths and stacked panels at narrower widths. The existing content scroll area and fixed footer remain unchanged.

## Updates and geometry verification

The existing shared UpdateService now supplies a small blue dot on version buttons only when a newer eligible release is known. Busy checks alone do not establish availability. Equal/older metadata and failed checks clear the known availability indicator. QObject-bound receivers safely disconnect when buttons are destroyed. The dot does not alter button text, native keyboard interaction or menu layout.

The reused checker selects the highest published stable semantic version from bounded public GitHub API pages, excludes drafts/prereleases and validates specific release URLs. Manual checks work despite notification opt-out, have a checking state and nonmodal result feedback. Automatic checks retain persisted 24-hour-after-success scheduling, bounded failure backoff and duplicate notification suppression. Standalone and Jana reuse the same backend. No credential or scientific client is involved, and no asset is downloaded or executed.

This pass uses mocked release responses only. No claim is made about current public GitHub availability or the latest published version.

## Scientific preservation evidence

Only presentation/capability descriptions within `_sync_page3_for_data_type` and `_build_page3`, plus preservation of start-editor values in its dependency callback, changed in the Wizard relative to the pre-task copy. AST comparison confirms **149 existing functions unchanged**, including the complete `run.build_options` function. No changes were made in this pass to app.py or any scientific implementation, parser, equations, inference, EDMA, ranking, exports or Jana handoff.

Existing regression tests exercise real intensity-correction and repartitioning functions, unchanged reflection arrays, threshold-zero numerics, genuine uncertainty filtering, FWHM rejection as uncertainty, actual cycle engine ordering and retry without double application. Golden references were not regenerated. Source/PNG evidence is recorded in `build/acceptance-wizard-mapfeedback-updates-2.0.5/preservation.json`.

## Automated tests

The complete final suite passed in 355.81 seconds (5:55).

| Verification | Result |
| --- | --- |
| Complete pytest suite | **391 passed, 1 skipped, 37 subtests passed, 0 failures** |
| Initial focused feedback/update checks | 82 passed, 1 skipped, 5 subtests passed, 0 failures |
| Feedback tests with added state/cycle regression | 16 passed, 1 skipped, 5 subtests passed, 0 failures |
| Final three-scale update, geometry and navigation tests | 4 passed, 0 failures |
| Scientific golden checks | 46 passed, 0 failures |
| Jana completion checks | 192 passed, 0 failures |
| Actual final Qt capture worker | Passed at 100%, 125% and 150%, including expanded feedback |
| Separate opt-in ochlor metadata/input preservation test | 1 passed, 0 failures; 631 reflections |
| Python compilation | Passed |
| git diff --check | Passed; inherited LF/CRLF warning only |

Counts overlap and must not be summed. The skipped feedback test is the opt-in real-project test in ordinary suite runs. It was additionally run explicitly against the existing local ochlor project copy at `build/powder-final/wizard-input/ochlor_Superflip.inflip`: 631 reflections, parsed FWHM capability and matching m90 wavelength resolver checked, original input bytes unchanged. This is metadata/input verification, not a new scientific execution. Early focused runs emitted a pytest-cache permission warning; subsequent commands use the writable `build/pytest-cache` directory.

Logs: `build/mapfeedback-updates-focused.log`, `mapfeedback-states.log`, `wizard-feedback-ui-final.log`, `wizard-feedback-full-suite.log`, `wizard-feedback-scientific.log`, `wizard-feedback-jana.log`, `wizard-feedback-real-ochlor.log`, `feedback-capture.log`, `feedback-capture-125.log`, `feedback-capture-150.log`.

## Screenshots

Ten actual final PySide6 captures under `build/acceptance-wizard-mapfeedback-updates-2.0.5/` were individually visually inspected:

1. `01-initial-normal.png` — four full workflow cards and footer.
2. `02-initial-reduced.png` — 790×825 logical window, complete readable cards.
3. `03-initial-dpi-125.png` — controlled 125% Qt scale.
4. `04-version-menu.png` — actual native popup, captured independently of the parent.
5. `05-update-available-mock.png` — actual notification visibly marked **CONTROLLED MOCK**, not a published release claim.
6. `06-feedback-disabled.png` — neutral disabled message, hidden parameters.
7. `07-powder-only.png` — active repartitioning, verified synthetic m90 provenance, automatic wavelength.
8. `08-intensity-only.png` — active no-σ correction and only its sequence.
9. `09-both-enabled.png` — both parameter sets, effective cycle ranges and correct ordering.
10. `10-one-cycle.png` — retained checked selections, unavailable methods, no misleading active warning.

No clipped descriptions or overlapping controls were observed in these captures. Footer and outer geometry stay consistent. The earlier and current automated geometry suites additionally cover scrolling, 150% scale, restored geometry, negative monitor coordinates and menu keyboard behavior. Reflection files, metadata and scientific executables in the new capture worker are controlled fixtures; none is executed as a scientific program.

## Changed files in this pass

- `phase_studio/jana_superflip.py`: state-dependent descriptions, terminology, precision and start-value preservation.
- `phase_studio/update_ui.py`: shared known-release signal and version-button indicator.
- `tests/test_map_feedback_applicability.py`: disabled/active/no-op, ranges, ordering, persistence and immutable-input regression.
- `tests/test_update_ui.py`: indicator checks for newer, older and failed responses.
- `packaging/tools/capture_feedback_updates_205.py`: isolated actual-widget offline capture and acceptance assertions.
- This report; ignored build evidence and pre-task source copies.

All unrelated dirty files remain preserved.

## Remaining limitations

Controlled offscreen Qt screenshots and simulated screen geometry do not establish acceptance on physical mixed-DPI monitors or a running native Jana2020 window. That manual check remains required. No live GitHub request was needed; all network outcomes tested here are mocks. No real ochlor computation or paid inference was run. Empty overlap groups or maps without supported predictions can still produce unchanged data despite eligible positive settings, as in the unchanged backend; the UI deliberately says **may affect**. No new binary was requested or produced.
