# Superflip + SharpED configuration UI — 2.0.3

The user's standing version instruction makes this work part of 2.0.3, despite
the older version wording in the attached brief. Existing development changes
are retained. This pass changes presentation only.

## A. Implementation

- `phase_studio/jana_superflip.py`, `_JanaWorkflowWizard._build_page2`: cycle
  editor is 110–140 logical pixels; its adjacent wrapping guidance changes at
  1, 2–3 and 4+ cycles without changing the count. The live-catalogue dropdown
  is 450–550 logical pixels; the accessible Refresh button is beside it.
- Automatic status names the cycle count rather than repeating the model ID.
  Manual status optionally identifies a matching recommendation but stays
  manual. Restore automatic is a real focusable QPushButton with hover/focus
  styling and the original restore handler. Initialization, refresh, explicit
  `activated` handling, persistence and unavailable-model safeguards remain.
- Advanced SharpED settings use the existing arrow disclosure and token field,
  without an empty group-box title/border. Expanding/collapsing recalculates
  the current page height; it does not move the footer or change parameters.
- Scientific validation uses a small standard warning icon and a light neutral
  panel. Its complete instruction names original measured diffraction data and
  independent crystallographic refinement. It wraps naturally.
- `_JanaWorkflowWizard.__init__`: source identification elides long names,
  retains the complete accessible name and full-path tooltip. `run` page
  navigation gives configuration a 16-pixel content top margin. Other pages
  retain their previous margins. Existing top-aligned stack/central scroll area
  and fixed footer are reused; unused height stays below the form.
- `phase_studio/ui_style.py`: narrowly scoped restore-link and validation-panel
  rules. Shared branding renderer, fonts, icon, colours and version are retained.
- `tests/test_wizard_models.py`: only requested width/helper-copy expectations
  change; all existing model-policy and error checks remain.
- `tests/test_jana_wizard_hierarchy.py`: requested guidance copy is updated,
  retaining explicit assertions for the effective SEED model and automatic mode.
- `tests/test_configuration_ui.py`: actual Qt geometry, catalogue, matching
  manual selection, keyboard restore, refresh and Back/Next/Cancel checks.
- `packaging/tools/capture_configuration.py`: reproducible runtime rendering
  with explicitly synthetic input/catalogue fixtures, isolated settings and no
  scientific execution or API request.

No changes in this pass to scientific calculations, API authority/authentication,
EDMA defaults, exported structures, ranking or Jana handoff.

## B. Before/after rendered evidence

Actual application-runtime Qt captures, not design mockups:

| State | Screenshot |
|---|---|
| Before, 3 cycles | [Before](screenshots/2.0.3-configuration/00-before-three-cycles.png) |
| 1 cycle, PEAK A automatic | [Automatic PEAK A](screenshots/2.0.3-configuration/01-one-cycle-auto.png) |
| 3 cycles, SEED automatic | [Automatic SEED](screenshots/2.0.3-configuration/02-three-cycles-auto.png) |
| 3 cycles, SEED manual, matches recommendation | [Manual SEED](screenshots/2.0.3-configuration/03-three-cycles-seed-manual.png) |
| 3 cycles, PEAK A manual | [Manual PEAK A](screenshots/2.0.3-configuration/04-three-cycles-peak-manual.png) |
| Automatic restored | [Restored](screenshots/2.0.3-configuration/05-restored-auto.png) |
| Advanced expanded | [Expanded](screenshots/2.0.3-configuration/06-advanced-expanded.png) |
| 800 logical pixels high | [Shorter window](screenshots/2.0.3-configuration/07-height-800.png) |
| 125% Qt scale | [125%](screenshots/2.0.3-configuration/08-scale-125.png) |
| 150% Qt scale | [150%](screenshots/2.0.3-configuration/09-scale-150.png) |

Before and standard after captures both use a 900 × 820 logical-pixel window.
The before image records the initial catalogue-loading state. After captures
wait for the synthetic catalogue to finish loading. Dropdown models are fixture
API responses; production still reads the dynamic server catalogue.

The separate Refresh row, multi-line cycle explanation, repeated recommendation
model name and empty advanced group-box chrome are removed. Both collapsed and
expanded configurations fit at 750, 800, 850, 1080 and 1200 logical pixels high
with zero vertical/horizontal scroll range in the tested 900-pixel width. The
warning and footer remain fully visible. No layout spreads controls vertically
to consume extra height. Shorter screens may use the existing central scrollbar.

The 125% capture is 1125 × 1025 device pixels; the 150% capture is 1350 × 1230,
each representing the same 900 × 820 logical window. All requested height/scale
combinations were rendered. Additional height images remain under
`build/configuration-2.0.3/after/scale-*`.

No reference screenshot was supplied with this attachment, so visual comparison
uses the actual pre-change runtime capture. These are offscreen PySide6 renders;
physical Windows display scaling, accessibility font enlargement and real Jana
GUI acceptance still need a manual check.

## C. Validation

The three new unittest cases each launch an isolated Qt process at scale 1,
1.25 or 1.5. Each process checks five heights with advanced settings both
collapsed/expanded (30 geometry configurations total), then checks cycle
guidance, exact PEAK A/SEED IDs, manual matching, refresh preservation, keyboard
restore, Back/Next/Cancel and absence of a Professional backing window.

- Existing model-policy suite: 44 checks passed.
- Wizard hierarchy/navigation: 21 checks passed.
- All 51 direct script suites passed: 2,250 checks. On encountering the two old
  helper-copy assertions, the run stopped; after updating those assertions,
  that suite and all remaining suites passed. Earlier successful suites were
  retained in the aggregate rather than rerun without a relevant change.
- Scientific core golden suite: all 46 checks passed; Jana completion: 192;
  workflow states: 141; Wizard geometry: 74; scaled text clipping: 18;
  EDMA defaults: 17; displacement-parameter exports: 44. These guards passed
  without scientific-output expectation changes in this pass.
- Unittest discovery with the real-project inputs enabled: 82 tests passed,
  none skipped (88.627 seconds).
- Pytest with the same inputs: 82 tests and 5 subtests passed (88.96 seconds).
  Cache writes were disabled for this final run.
- Compile check and `git diff --check` passed. Release metadata is unchanged.

The opt-in ochlor test reads `ochlor.inflip` and the saved
`run_0002/cycle_003/cycle_003_deblurred.xplor`, derives 631 reflections in an
isolated test directory, and verifies original input/map bytes are unchanged.
The source map SHA256 remains
`ce7cdadc67e9a7067216acc47da9b421ee191680c5ffd945047b190357cdc620`.
No Superflip process, SharpED inference or real Jana handoff is launched here.

## D. Windows build integration

This UI is in the current 2.0.3 source runtime. No new frozen Windows executable
was built. Existing 2.0.2 release binaries remain unchanged and do not include
this UI. No commit, push, tag or publication was performed by this pass.
