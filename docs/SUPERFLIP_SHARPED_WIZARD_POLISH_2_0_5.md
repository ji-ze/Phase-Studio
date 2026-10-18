# Superflip + SharpED Wizard configuration polish — 2.0.5

## Scope and implementation findings

This is a refinement of the existing Jana2020 Wizard configuration page, not a
new workflow. Version/release metadata and unrelated uncommitted work are
preserved. No branch, commit, push, PR, release or EXE build was made in this pass.
The previously built EXE predates these changes.

The existing implementation already provided shared window geometry, a fixed
footer, asynchronous model discovery, exact catalogue IDs, PEAK A/SEED cycle
policy, manual overrides, browser sign-in, secure credential binding and a
scientific warning. These authorities were reused.

Verified problems or misleading presentation before this pass:

- Cycle guidance classified runtime as “Balanced” without a measured runtime
  basis and did not explain what one cycle does.
- Automatic/manual status and catalogue count occupied separate form rows.
- Account management was accessible only inside the advanced panel.
- A removed manual model silently restored automatic selection and chose a
  different scientific model. The message announced the substitution after it
  had happened. Invalid saved manual preferences behaved similarly.
- The generic Next label did not name the next page.

No independent configuration-page geometry authority was introduced. Empty lower
space is intentional: configuration shares its outer geometry with the other
steps and its controls are not stretched to fill the height.

## Layout, labels and navigation

The page keeps the established Phase Studio/SharpED branding, version menu,
colors and standard form font. The title is `SUPERFLIP + SHARPED`, subtitle
`Configure charge flipping and SharpED processing`, followed by the existing
Jana input filename.

The compact top-aligned layout now separates processing configuration, SharpED
connection/advanced settings, and scientific validation. A small route caption
highlights Configure processing in `Choose workflow → Configure processing →
Map feedback`. It is shown only for the ordinary Superflip + SharpED route;
it does not invent a Map Feedback step for another route.

The QSpinBox keeps its range **1–999**, stored value and cycle execution semantics.
Its width is **120–140 logical pixels**. The explanation states that each cycle
processes a charge-flipping map with SharpED, that more cycles take more time,
and that improvement is possible rather than guaranteed. Numeric defaults are
unchanged: the initial controlled fixture uses the existing five-cycle default;
the three-cycle screenshots result from an explicit test edit.

The noneditable model selector is **340–420 logical pixels** wide, with Refresh
beside it and a single status row below it. Its existing popup width authority
continues to expose long model names within the available screen area.
Catalogue count is secondary information at the right of the same status row.

The existing navigation callbacks and preflight ordering are retained. The
ordinary configuration footer says **Next: Map feedback →**, because its actual
Next handler always visits Map Feedback. Back and Cancel keep their behavior.
Next itself does not start authentication, inference or scientific execution;
Run phasing still performs the existing validation and requirements checks.

## Model-selection behavior

- Automatic: `Automatically selected for 1 cycle` or the actual multiple-cycle
  count; Restore automatic is hidden.
- Manual: `Manually selected`, with the existing matching-recommendation suffix
  when applicable, and the secondary Restore automatic action.
- One cycle still selects **PEAK A (model prediction)**; two or more still select
  **SEED (cyclic CF)**, using exact IDs present in the returned catalogue.
- A manual choice equal to the recommendation remains manual across count
  changes, Back/Next and catalogue refresh.
- A missing automatic policy ID leaves no selection and blocks execution;
  the server default is not substituted.
- If a manual ID disappears, selection becomes empty, the manual state is
  retained, and an actionable message requires another model or Restore
  automatic. Execution remains blocked until explicitly resolved. This includes
  invalid saved manual preferences. No substitute model is silently selected.

The last item is the intentional correction to exceptional catalogue handling,
not a change to the normal PEAK A/SEED policy or to inference algorithms.
An explicit replacement/restore also clears the old missing-model message.

## Catalogue and authentication presentation

The existing worker thread/poll timer is retained. Refreshing models does not
block the GUI. Counts come from the actual returned list, never hardcoded GUI
model totals. Failure displays `Model list unavailable — Refresh to retry` and
keeps Refresh available. Previously loaded entries remain available for inspection
but their tooltip explicitly says they have not been reverified. A cycle edit
cannot erase the catalogue-failure execution guard. Successful retry restores
the catalogue status and existing selection policy.

This Wizard's current catalogue client fetches the server list; it has no separate
verified offline catalogue authority. No offline models or fallback catalogue
were invented. Existing session caching and retained entries are preserved.

Account access is independent of public catalogue success:

- Empty credential field: **Sign in with Jana2020**.
- A key is present but no authoritative connection result is available here:
  **SharpED account access**.

Neither public discovery nor token presence displays Connected. No decorative
network probe, expiry inference, OAuth change or extra sign-in requirement was
added. The existing Account access button is available in a compact connection
row and invokes the same account dialog. Expired-session/network remediation
remains the responsibility of that established authentication/preflight path.
The UI does not invent an expiry or connectivity verdict before those results.

OAuth Authorization Code + PKCE, credential persistence, token redaction, API
headers and endpoints are untouched. Manual access-key entry remains masked
inside Advanced SharpED settings with its original width bound and secure
credential binding. No real key was used in tests or captures.

## Advanced settings and scientific warning

Advanced SharpED settings remains collapsed initially. Its arrow tracks the
expanded state, outer geometry stays fixed, and the established content scroll
area exposes controls when necessary. Account management is available without
expanding the key field. Existing configured values are not reset.

Scientific validation remains visible outside advanced settings, using the
existing warning icon and muted background. Padding is reduced from 10/7 to
8/4 logical pixels and title/body spacing from 4 to 2. The warning still states
that predictions may contain artifacts and require validation against original
measured diffraction data and independent crystallographic refinement. It is
not presented as a processing failure.

## Geometry and visual acceptance

The existing `_adjust_dialog_size`, current-page height calculation, native
availableGeometry clamp, saved geometry and fixed footer remain unchanged.
Initial selection, configuration and Map Feedback keep the same rectangle.
The test also resizes the Wizard explicitly, then confirms Back/Next retains
that user size and position. Existing geometry tests cover restored windows.

Actual Qt processes ran at DPR **1, 1.25 and 1.5**, with declared logical work
areas corresponding to a 1920×1080 desktop minus a 40-physical-pixel taskbar.
At 100%/125% the common initial window is 1000×760 logical pixels; at 150% it
is clamped to 1000×637. Configuration remains top-aligned, and the collapsed
configuration, warning and footer fit. Advanced controls are tested as well as
ten height/disclosure combinations per DPI in the existing configuration matrix.

Exactly ten final actual PySide6 screenshots were generated and visually inspected:

1. `build/acceptance-superflip-sharped-wizard-2.0.5/01-initial-workflow.png`
2. `build/acceptance-superflip-sharped-wizard-2.0.5/02-automatic-model.png`
3. `build/acceptance-superflip-sharped-wizard-2.0.5/03-one-cycle-peak-a.png`
4. `build/acceptance-superflip-sharped-wizard-2.0.5/04-three-cycle-seed.png`
5. `build/acceptance-superflip-sharped-wizard-2.0.5/05-manual-model.png`
6. `build/acceptance-superflip-sharped-wizard-2.0.5/06-advanced-settings.png`
7. `build/acceptance-superflip-sharped-wizard-2.0.5/07-authentication-required.png`
8. `build/acceptance-superflip-sharped-wizard-2.0.5/08-map-feedback-after-next.png`
9. `build/acceptance-superflip-sharped-wizard-2.0.5/09-configuration-dpi-125.png`
10. `build/acceptance-superflip-sharped-wizard-2.0.5/10-configuration-dpi-150.png`

These use a synthetic local Jana-style input and mocked model catalogue, not a
live server or real account. Each capture's fixture status, model/manual state,
geometry, DPR and scroll range is recorded in `acceptance-dpi-*.json` beside it.
The screenshots are unaltered Qt window grabs. Offscreen tests do not establish
physical Windows/Jana2020 acceptance or a successful live authenticated session.

## Tests and scientific preservation

Final complete pytest result: **370 passed, 1 skipped, 37 subtests passed in 391.96s (0:06:31)**.

Focused configuration/policy/navigation run: **5 passed**, exercising all three
DPRs. Standalone model tests: **46 checks passed**. The first standalone run had
one obsolete expectation that an invalid saved manual choice should automatically
switch models; that expectation was updated to the explicitly requested blocking
behavior, and the rerun passed. Hierarchy/dispatch: **21 checks passed**.
Scientific golden checks: **46 passed**. Jana completion: **192 checks passed**.
Compileall and `git diff --check` passed.

The new actual-Qt guard covers automatic one/multiple cycles, matching/manual
override retention, missing manual/automatic models, explicit restore, offline
retry, no false Connected state, advanced disclosure, factual cycle guidance,
warning text, Next/Back/Cancel, requirements-check ordering and stable geometry.

AST comparison against the pre-task Wizard source confirms **142 existing
functions are unchanged**. Changed functions are UI construction/presentation,
catalogue-unavailability guards, banner text and the Next label. The scientific
option builders, effective-value functions, saved configuration generation,
execution dispatch, requirements/authentication methods, geometry authority and
Jana handoff methods remain AST-identical. No other production file was edited
in this pass. Model IDs, cycle defaults/range, Superflip/SharpED/EDMA calculations,
maps, reflection data, feedback, repartitioning, ranking, exports and handoff
formats were not changed.

Evidence/logs:

- `build/acceptance-superflip-sharped-wizard-2.0.5/source-preservation.json`
- `build/config-polish-focused-final.log`
- `build/config-polish-full-suite.log`
- `build/config-polish-models.log`
- `build/config-polish-hierarchy.log`
- `build/config-polish-scientific.log`
- `build/config-polish-jana.log`

## Files changed in this pass and limitations

- `phase_studio/jana_superflip.py`
- `tests/test_configuration_ui.py`
- `tests/test_wizard_models.py`
- `tests/test_jana_wizard_hierarchy.py`
- `tests/test_configuration_polish.py` (new)
- `packaging/tools/capture_configuration_polish_205.py` (new offline guard/capture)
- `docs/SUPERFLIP_SHARPED_WIZARD_POLISH_2_0_5.md` (this report)

Existing unrelated modifications are retained. No internet research, live
credentials or paid inference were used. Native physical-monitor behavior and
real server authentication remain manual acceptance items. There is deliberately
no new Connected/Session expired/Check connection indicator without an
authoritative result. No EXE was rebuilt for this UI task.
