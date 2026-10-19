# Unified GUI remediation — Phase Studio 2.0.5

Implemented offline on the existing dirty `development/2.0.5` tree. No version,
scientific algorithm, protocol, API endpoint or release change. Previous HKL
Completeness/Advanced Diagnostics work and workshop drafts were preserved.

## Corrections and retained behavior

| Area | Implemented correction / verified existing behavior |
|---|---|
| Initial Jana wizard | Two-row, three-column cell table keeps each variable, original-precision number and unit together using nonbreaking spaces. Existing reflection/crystal/action layout still reorganizes responsively. Four approved workflow cards, icons, full-card activation, optional input persistence, scrolling and fixed footer remain unchanged. |
| SharpED configuration | Explicit Not connected / Credentials available — not yet verified / Connected / Authentication expired / Connection unavailable statuses replace the ambiguous account caption. Account management updates the originating wizard after return. Failed catalogue refresh explicitly labels retained entries as cached and blocks unverified model selection. Existing PEAK A/SEED cycle policy, manual override/Restore automatic, removed-model preflight, compact controls and public catalogue refresh remain intact. Autosolve policy is untouched. |
| Authentication | Distinct opening-browser, waiting, credential-exchange and cancellation presentations; existing asynchronous workers, reopen/cancel, retry, late-result guards, parent activation and secure storage retained. Manual-key verification says Verifying credentials. No additional authentication endpoint or paid job is introduced. |
| Map Feedback | Disabled state reduced to two concise lines. Enabled status names the effective methods in the existing execution order. Existing no-op, zero damping/mix/additions, single-cycle applicability, genuine-uncertainty gating, hidden inactive parameters and measured-wavelength requirements remain intact. |
| HKL Validation | Integrity + Advanced Diagnostics row followed by a search/count/copy toolbar. Search is 350–450 logical pixels, has clear action and immediate Enter handling, and searches original parsed records (including duplicates), rather than the merged list. Keeps the 200-result UI cap. Added context-menu copy; original numeric values, numeric sorting/alignment and disabled-without-selection copy remain. Verified powder widths are explicitly labelled degrees 2θ. Enter no longer activates an unrelated auto-default diagnostics/export/Close action. |
| HKL Completeness | Full mode hides manual range controls; Custom reveals them. Input details collapse above the plots; summaries remain available in the disclosure/tooltips/Advanced Diagnostics. Wide two-panel graphs fit the default viewport with axis labels; narrow layouts stack the same axes without rebuilding scientific data or canvases. Bin table and fixed footer remain accessible. Full histogram bounds use actual finite extrema, rather than Matplotlib's padded limits. Compact range display retains 15-decimal stored precision. One-line visible/outside count, original bins, log-zero handling, reciprocal/d axis conversion and shared overlap inspector remain. |

### Authentication evidence boundary

The existing manual-key preflight calls **public** `get_models()`. Its OK response
does not prove that a key is accepted, so the UI deliberately retains
**Credentials available — not yet verified**. A successful server-side OAuth
exchange establishes **Connected**; expiry and key replacement invalidate that
presentation. Session verification is associated with the credential's hash,
never its displayed value. Temporary failures do not delete saved credentials.
No claim is made that public model discovery verifies SharpED job authorization.

OAuth state/PKCE validation, token exchange, secure persistence, request headers,
scientific uploads and reauthorization infrastructure were not changed. Browser
opening is never treated as successful authentication. Cancellation still closes
only the connection attempt, consistent with the established dialog lifecycle.

### Histogram boundary investigation

The negative full-range limit in the earlier positive-intensity screenshot was
Matplotlib's automatically padded x-axis boundary. It was not a fabricated value
in the dataset. Full mode now uses finite physical-input min/max (constant-value
input uses the existing histogram edge interval). Actual negative observations
are retained. Changing range/scale never rebins, truncates or changes the data.

## Modified files for this task

- `phase_studio/jana_superflip.py`
- `phase_studio/sharped_access.py`
- `phase_studio/hkl_diagnostics_ui.py` (already dirty from the preceding HKL work)
- `tests/test_wizard_layout_polish.py`, `tests/test_oauth_ui.py`,
  `tests/test_sharped_access.py`, `tests/test_hkl_diagnostics_ui.py`,
  `tests/test_hkl_completeness_interactive.py`
- `packaging/tools/capture_configuration_polish_205.py` (updated truthful-status assertions)
- `packaging/tools/capture_gui_remediation_205.py`
- This report.

`tests/test_hkl_advanced_ui.py`, the two earlier HKL acceptance reports/tools and
`docs/workshop/` also remain dirty/untracked from earlier tasks; they were not
discarded or committed. Final Git status is recorded in
`build/gui-remediation-git-status.txt`.

## Scientific preservation

Real input identity is checked against accepted hashes. Both datasets are freshly
parsed locally, not replaced by similarly named data. Before/after interaction,
input hashes and diagnostic JSON/CSV bytes are identical; output bytes also match
the preceding accepted HKL exports.

| Real input | Records | d_min (Å) | d98 (Å) | Input SHA-256 |
|---|---:|---:|---:|---|
| ochlor | 631 | 1.1990790613015834 | 1.1990790613015834 | `9136270c5e8ab6850ac6bd4390c301f17a32dcc83994184d8562735b9a26b88c` |
| 2int3total | 328606 | 0.7255092594101177 | 0.8161153076022714 | `07a3de15e54ba130f75e960358aef1ff6087b09f0ea5d9604f00090cb9d21642` |

ochlor overlap remains 91 groups, 193/631 affected records,
30.58637083993661%, 21.06356131111815% physical input intensity, largest group 4;
81 pairs, 9 triples and 1 quadruple. These are computed data, not UI constants.
Full per-scale hashes and timings are in the capture `evidence.json` files.

## Tests and performance

- Broader targeted wizard/model/auth/update/feedback/HKL/powder suite:
  **195 passed, 1 skipped, 5 subtests passed** (239.00 s).
- Final focused interaction guards: **62 passed** (45.60 s).
- Scientific golden script: **46 checks passed**.
- Jana completion/integration script: **192 checks passed**.
- Full pytest suite: **428 passed, 1 skipped, 37 subtests passed**
  (404.70 s / 6 min 44 s), exit code 0.
- `git diff --check` and Python syntax checks: **passed**.

The first wider run found two cell-layout regressions and two obsolete UI text
assertions (4 failed, 180 passed, 1 skipped). The layout was corrected rather than
relaxing its geometry guards; only expected cell markup and new authentication
state wording were updated. Additional cancellation wording assertions were
aligned with the explicit cancelled state. No scientific golden was changed.

Large-HKL timings measure actual Qt construction/first paint and exact HKL search
plus event processing, excluding initial file parsing/diagnostic calculation.
Before-state evidence measured 0.782 s for Completeness construction/first paint
and 3.902 s for Enter/search processing. The latter exposed QDialog's unrelated
auto-default action. Final measurements at 100/125/150% were respectively
**0.737 / 0.660 / 0.674 s** for Completeness construction/first paint and
**0.0318 / 0.0290 / 0.0365 s** for exact search plus event processing. These local
offscreen measurements are observations, not physical-display frame-rate claims.

## Screenshots and geometry

Reproducible tool: `packaging/tools/capture_gui_remediation_205.py`.
`--before` loads the actual three source files saved at task start from
`build/gui-remediation-205-before/`, without reverting the working tree.

Evidence root: `build/acceptance-gui-remediation-2.0.5/`.
There are **15 before-state PNGs and 45 final PNGs** (15 per scale).
Reviewed overview sheets are `review-1.0.jpg`, `review-1.25.jpg`, `review-1.5.jpg`.

- Before: [100% screenshots](../build/acceptance-gui-remediation-2.0.5/before/scale-1.0/).
- After: [100%](../build/acceptance-gui-remediation-2.0.5/after/scale-1.0/),
  [125%](../build/acceptance-gui-remediation-2.0.5/after/scale-1.25/),
  [150%](../build/acceptance-gui-remediation-2.0.5/after/scale-1.5/).
- [Default graphs, 150%](../build/acceptance-gui-remediation-2.0.5/after/scale-1.5/10-analysis-default.png).
- [Advanced input, 100%](../build/acceptance-gui-remediation-2.0.5/after/scale-1.0/02-advanced-input.png).
- [Validation toolbar](../build/acceptance-gui-remediation-2.0.5/after/scale-1.0/09-validation.png).

Each scale captures initial/advanced wizard, configuration/advanced settings,
authentication ready/waiting/timeout, feedback disabled/powder-enabled, validation,
Analysis default/custom/log+d, Peak overlap and large-HKL analysis. Wizard input
and catalogue are clearly identified offline fixtures; authentication waiting and
timeout are simulated presentations, never a fabricated live connection. HKL
views use the actual real datasets above. Images were inspected, including plot
axes, table rows, button visibility, cell alignment, disclosures and field widths.

Existing geometry tests additionally exercise smaller available screens,
oversized saved geometry, stable navigation, persistent state, visible footers
and three Qt scale factors. The capture asserts default plot-canvas fit and at
least five visible bin rows. Narrow/high-DPI wizard content can scroll; cards stay
reachable and the footer stays outside that scroll area. Narrow graphs stack and
scroll vertically; no claim is made that all expanded detail fits simultaneously.
Measured default Analysis canvas/viewport sizes are 1100×341, 1100×282 and
1100×183 logical pixels, with 8/6/5 fully visible bin rows. At 150%, Custom range,
Peak overlap and additional large-data panels can require their independent chart
scrollbar; axis labels remain accessible by scrolling. The full-viewport assertion
applies to the default ochlor Analysis view, not every expanded chart state.

## Limits and Git/release state

Actual native multi-monitor transitions and installed Jana2020 window activation
were not manually tested. Dialogs were exercised through the real Jana launcher
classes with isolated fixture project context and through standalone diagnostic
parents. No live OAuth/account test, paid inference or scientific end-to-end Jana
handoff was performed; those remain follow-up acceptance work as requested.

Version remains **2.0.5**. No build, commit, push, history rewrite, release or binary
publication was performed in this remediation. Existing EXEs predate these fixes.
