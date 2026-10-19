# Static version and application menu — post-release 2.0.5 correction

## Scope and Qt implementation

The released header combined the version and native dropdown arrow in one
QToolButton. Wizard and standalone/Professional now use one shared
`install_application_header_menu` in `phase_studio/update_ui.py`:

- Static QLabel `v` + authoritative VERSION, ordinary application font at
  13 logical pixels, regular weight, muted navy, no interaction or tab stop.
- Separate 30×30 QToolButton with a 16×16 horizontal-ellipsis SVG, delivered
  through the existing established-icon renderer/inventory. It has no text
  glyph or native menu indicator; hover/pressed/focus are explicit and subtle.
- Transparent QWidget/QHBoxLayout with zero margins, 8px spacing and vertical
  centering replaces the old badge slot in the existing wordmark title row.
  No manual icon offsets or window resize are used.
- Existing asynchronous update action, persisted notification preference and
  existing About callback are reused. Popup positioning still clamps to the
  work area and opens leftward from the right edge where needed.
- The optional blue indicator requires a fresh successful newer-release check
  in the current service session. Unknown state, unverified cached objects,
  current/older versions and network failures do not light it. It expires at
  the existing check interval. Opening the menu does not acknowledge/dismiss it.

Execution, result selection, sign-in and other badge-only branded dialogs are
unchanged. Workflow SVGs, Science Gothic wordmark/subtitle, scientific
typography and version 2.0.5 are preserved. The new ellipsis is the only added
approved asset. No scientific computation, model policy, credential storage,
OAuth, candidate authority or Jana output writer was changed.

## Acceptance evidence

`build/acceptance-application-menu-2.0.5/scale-{1.0,1.25,1.5}` contains eight
actual Qt states per scale, plus a separate raw popup (**27 PNG captures**)
and semantic/geometry metadata:
closed/open Wizard menu, controlled verified-update dot, configuration,
Map Feedback, standalone controls, parent-backed close-up and actual About.
The newer-release state is explicitly a controlled offline fixture, not a
claim that GitHub has published another release.
The combined open-menu view composes actual dialog/popup grabs at their live
global positions because offscreen Qt cannot grab the desktop; the raw popup
and placement assertions are retained separately. No control is mocked visually.

All three DPI profiles verify separate widget types, authoritative version,
noninteractive label, icon provenance/size, hit area, label/button/wordmark
centering, Return/Enter/Space, Escape/item navigation, mouse clicks across the
button, persisted preference reload, every menu action, screen-edge and
negative-monitor placement, stable Wizard geometry/navigation, retained update
notification policy, current/failure/stale states, standalone About routing and
unchanged badge-only dialogs. The actual modal Wizard About is inspected and
closed through a timer, with parent and version checks.

Visual inspection found an unintended white wrapper background; the group was
made transparent and all profiles recaptured. Close-ups are grabbed from the
real parent header to include its background. No pixel-equality golden or
scientific expectation was changed. Existing tooltip tests check visible text
within the application's standard rich-tooltip wrapper.

Focused update/Wizard/diagnostic tests: **63 passed**. Final three-DPI visual
checks: **3 passed**. Approved icon/keyboard script: **58 checks passed**.
Scientific core: **46 checks passed**; Jana completion: **195 checks passed**.
Complete suite: **450 passed, 1 skipped, 37 subtests passed in 407.04 seconds**
(`build/application-menu-full-suite.log`). Final UI/source-diagnostic checks:
**5 passed**; latest three-scale capture checks **3 passed**. Whitespace checks pass.

Physical Windows/Jana foreground behavior remains a native-machine acceptance
limit; actual Qt parent/modality tests do not establish that desktop behavior.

## Published-release boundary and safe integration

At task start [v2.0.5](https://github.com/ji-ze/Phase-Studio/releases/tag/v2.0.5)
already existed, pointing to `87b2dcce9276916b94162230bfc26af43be96c38`.
Its standalone and Jana assets are preserved. This is a source-only follow-up
on `development/2.0.5`, prepared for a separate review PR against main.
No version bump, moved tag, force-push, replaced binary or republished release
is part of this correction. A future public binary update requires a separate
controlled release decision. No new Windows artifact/hash is claimed here.

Changed production files: `app.py`, `jana_superflip.py`, `ui_branding.py`,
`update_ui.py`, `assets/application_menu.svg`. Tests and capture tools cover the
new component and adapt only previous dropdown/approved-asset UI expectations.
Test files: `test_application_menu.py`, `test_update_ui.py`,
`test_jana_wizard_tile_icons.py`. Capture tools: `capture_application_menu_205.py`,
`capture_gui_final_polish_205.py`, `capture_wizard_geometry_204.py`.
Unrelated workshop drafts remain local and excluded.
