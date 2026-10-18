# Jana2020 Wizard geometry, navigation and layout — 2.0.4

> Historical acceptance snapshot. This post-release working-tree change is now
> assigned to **2.0.5 (unreleased)**; see `RELEASE_NOTES_2_0_5.md`. Existing 2.0.4
> artifact names describe the earlier snapshot, not a newly published release.

Validated 2026-10-17. Base commit: `75600c46d36ad6e434678e6515a443eb6fc56610`.
These changes are uncommitted. Version remains **2.0.4**.

## Root cause and architecture

The Wizard already used one `QDialog`, a `QStackedWidget` with three pages,
one scroll area and a shared header/footer. However, every Next/Back called
`_adjust_dialog_size()`, which reapplied top-level geometry. Its preferred-height
function explicitly calculated a content-dependent height for configuration
and feedback, unlike the landing page. Page-2 growth callbacks could also refit
the outer dialog. Thus a stable-looking shared window still shrank/expanded
and recentered during navigation. This was not a screenshot-DPI comparison error.

There are no separate Superflip-only or Autosolve configuration pages in this
Wizard: those tiles preserve their existing direct preflight/execution paths.
Professional mode opens the separate full workspace. Authentication, dependency,
HKL, Result Selection and execution windows remain independent interfaces.

## Shared geometry authority

- `_adjust_dialog_size()` applies outer geometry **once**, after the shared
  footer exists. Its initial client target is **1000 × 760 logical pixels**,
  capped to the available screen. All subsequent calls resize only the current
  scroll body at the actual user-selected width.
- The current page remains pinned to its own measured content requirement,
  rather than the largest hidden page. The layout watcher handles both growth
  and shrinkage on every page, including long model-status messages returning
  to short text. No page's preferred height is reapplied to the outer window.
- Branding, context banner and footer retain shared heights. Manual resizing
  remains possible; expanding settings, changing warnings or completing model
  discovery cannot replace the user's rectangle.
- `wizard/windowGeometry` and `wizard/windowRect` in the existing Jana Wizard
  QSettings store preserve user geometry. Restored geometry is clamped with the
  existing frame-aware screen helper. These are one pair of window keys, never
  per-page keys; they do not overwrite independent-dialog settings or scientific
  configuration. A missing key retains the normal default.
- Back/Next resets the content scroll offset and dismisses ordinary Qt tooltips.
  The footer remains outside the scroll area, with the primary action on the right.

## Layout and navigation

- The four approved SVG assets, including Autosolve's focus-frame atomic icon,
  are unchanged. All four cards fit the default collapsed desktop view.
- The model editor is bounded to 240–420 logical pixels; its popup retains
  existing content-aware sizing. The masked key editor is capped at 340 and
  Account access at 180. The scientific validation callout is unchanged.
- Both single-crystal and powder feedback use the same two-column container
  when wide enough and stack on narrow screens. Missing-completion parameters
  now hide/reveal like the other feedback options; values and enablement rules
  are retained. Powder still has no invented significance filter.
- The existing update service/menu is now attached to the top-right **2.0.4**
  button, not the footer. Both existing actions, preference synchronization and
  Jana distribution distinction are preserved. Tests exercise the actual menu
  service and its new ancestry. There is no new update mechanism.
- The optional-input tooltip is short; navigation hides transient tooltips.
  Scientific validation warnings keep their meaning. Science Gothic remains
  restricted to the two existing wordmarks; no asset/font redesign occurred.

## Actual geometry measurements

Tests declare a 2560 × 1400 physical work area at each Qt scale. The values below
are Qt **logical client coordinates**, not PNG dimensions or physical-monitor
measurements. Initial, configuration, expanded settings, model refresh, warning,
single/powder feedback and Back transitions share exactly the same rectangle.
Native-frame rectangles were also recorded and checked for equality per profile.

| DPI | Initial client rectangle (x, y, width, height) | Header / banner / footer |
|---|---|---|
| 100% | `780, 320, 1000, 760` | `63 / 48 / 63` logical px |
| 125% | `524, 180, 1000, 760` | `63 / 48 / 63` logical px |
| 150% | `353, 86, 1000, 760` | `63 / 48 / 63` logical px |

The user-resized `920 × 700` client rectangle survives navigation and reopening.
On a declared 1366 × 768 physical screen at 150%, the restored window clamps
to a `908 × 510` logical client (`910 × 512` frame), wholly within the available
screen. Content scrolls and the footer stays visible. Normal desktop collapsed
pages have no vertical scrollbar; long text/expanded or constrained cases scroll.
Every tested case has zero horizontal scroll range.

Independent source HKL windows retained their own sizes: Validation `1060 × 680`,
Completeness `1180 × 835`, Advanced `1000 × 570` in the normal 100% fixture.
Their actual construction and opening/closing left the Wizard rectangle intact.

## Tests, screenshots and frozen runtime

- Final complete pytest: **357 passed, 1 skipped, 37 subtests passed**, 322.38 s.
  The skip is the existing opt-in real-project test, not a hidden UI failure.
- Scientific golden checks: **46 passed**, unchanged expected outputs.
- Wizard geometry policy: **75 checks passed**; model catalogue/policy:
  **44 passed**; tile/icon actions: **58 passed**; Jana startup isolation:
  **17 passed**; independent authentication geometry: **3 DPI checks passed**;
  main action-footer regression runner: **24 checks passed**.
- Focused authentication/update/feedback/Wizard UI suite: **49 passed,
  1 skipped, 5 subtests passed**. Final navigation and configuration matrix:
  **4 passed**, including all three scale factors and the long-status shrink case.
- Historical UI expectations asserting smaller configuration windows or
  450–550-wide model editors were updated to the requested stable geometry and
  compact editor. No scientific golden expectation was changed.
- Python compilation and `git diff --check` passed.
- Final Jana developer ONEDIR rebuilt locally: native dependency audit has
  **0 unresolved non-OS dependencies**; import audit **100 PE files, 0 blocking
  problems, 0 conflicting duplicate DLL names**. Distribution boundaries pass;
  ZIP extraction and hashes pass for **904 files**.
- The companion frozen navigation probe uses the **actual Jana spec, DLL
  isolation hook, production modules and assets**, with a dedicated QA entry
  instead of the normal launcher. It repeats the source navigation, resize,
  persistence, HKL and constrained-screen assertions at all three scales:
  **3/3 passed**. This distinction is intentional, not a claim of native Jana use.
- The actual `Phase_studio.exe` contains the current geometry/menu code and
  passes version, branding and mock OAuth checks. Mock OAuth sends no inference.

Ten final current-widget PNGs and an offline gallery are in
`build/acceptance-wizard-geometry-2.0.4/`; open `index.html` or `contact.jpg`.
`01`–`08` are each **1000 × 760 physical px** at 100%; `09` is **1250 × 950**
at 125%. `10` intentionally uses a constrained 150% screen and restored size.
Capture `08` composites the actual dialog and popup Qt surfaces because a
separate native popup is absent from `QWidget.grab()`. Other captures are direct
widget grabs. Fixture input/model data and uncertainty/powder states are controlled;
the images are not real server/scientific acceptance. Full rect/frame, independent
dialog and frozen-probe measurements are JSON files in the same ignored directory.

The local working-tree QA package is
`dist/wg204/release/PhaseStudio-Jana2020-2.0.4.zip`, with its complete ONEDIR beside
`release/`. Its exact source/artifact hashes are in the acceptance `build-manifest.json`.
It must not be described as a new tagged release or a build of unmodified main.

## Modified files and preservation

- `phase_studio/jana_superflip.py`: Wizard-only geometry, layout and menu placement.
- `packaging/tools/capture_wizard_geometry_204.py`: isolated actual-widget capture
  and navigation worker; no external executable/job or live login is invoked.
- `tests/test_wizard_navigation_geometry.py`: three-process DPI regression.
- `tests/test_wizard_geometry.py`, `tests/test_wizard_models.py`,
  `tests/test_configuration_ui.py`, `tests/test_update_ui.py`: matching UI guards.
- This report.

All 27 module-level Jana functions and the existing nested option-building,
save-values and effective scientific-setting functions remain AST-identical to
the base commit. Superflip/SharpED/EDMA calculations, HKL/powder algorithms,
coordinates, intensities, ranking and Jana scientific publication code were not
modified. Automatic model policy remains PEAK A for one cycle and SEED for two
or more; manual overrides remain stable across catalogue completion and Back.
Standalone model policy, OAuth lifecycle, credential storage, scientific warnings
and independent analysis/execution geometry are unchanged.

No commit, push, tag or release publication was performed. Existing unrelated
workshop files are preserved. Native Jana2020 foreground/ownership and real
physical-monitor/multi-monitor acceptance still require a manual workstation
check; offscreen and frozen-probe results do not establish those behaviors.
