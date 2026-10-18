# Wizard responsiveness and release updates — 2.0.5

Verified on 2026-10-18. Version remains 2.0.5. Existing uncommitted work was preserved. No build, commit, push, release, paid inference or live GitHub request was performed in this pass.

## 1. Reproduction

The supplied clipping could not be reproduced at 950×990 or 790×825 **logical** pixels in the controlled Qt baseline: all four cards were visible. At 790×640, secondary cards required scrolling; the existing scrollbar could reach them and the fixed footer did not overlap them. This does not establish the cause of the original physical-screen screenshots.

## 2. Confirmed causes and measurements

The old summary used an arbitrary 800-pixel window breakpoint, adding an unnecessary actions row even when its columns fitted. Excess spacing also consumed height. Measurements use the same fixture before and after this task:

| Logical window | Summary before/after | Scroll maximum before/after |
| --- | --- | --- |
| 1000×760 | 128 / 123 | 0 / 0 |
| 950×990 | 128 / 123 | 0 / 0 |
| 790×825 | 178 / 123 | 0 / 0 |
| 790×640 | 178 / 123 | 142 / 79 |
| 760×640 | 178 / 123 | 173 / 110 |

At the normal width, secondary cards start 17 logical pixels earlier. At 790 pixels, eliminating the unnecessary actions row and reducing spacing saves 63 pixels of scroll extent. Baseline and final measurements are in `build/acceptance-wizard-updates-2.0.5/{baseline,after}-geometry.json`.

## 3. Geometry

The existing single initial geometry authority is retained. Page changes and advanced expansion do not resize the outer window. Saved geometry is restored and clamped to available screen geometry; a valid saved rectangle can also restore without the geometry byte array. With no saved position, a known Jana window supplies the initial center and relevant screen. Read-only Windows foreground/owner geometry detection converts monitor-relative physical pixels to Qt coordinates. No foreground activation or topmost flags were added.

## 4. Responsive Input Summary

Reflection data, crystal data and equal-sized analysis actions share a wide row. The breakpoint is calculated from actual text/font requirements, form spacing and button size hints. Rich scientific labels use QTextDocument measurement. Actions move below the information columns when necessary; the information columns can also stack. No reflection values, unit-cell values, composition or accepted typography changed.

## 5. Workflow cards and scrolling

Spacing was reduced without reducing fonts or changing SVGs. Primary card minimum height was already 76 logical pixels and remains so. Secondary card minimums, full-card activation, keyboard operation and Recommended styling are retained. Fixed footer and additional bottom margin leave complete cards reachable at short heights. Expanded options and the 150% DPI fixture legitimately require scrolling; visibility of all content simultaneously is not claimed.

## 6. Existing backend findings

The existing checker, shared service, background worker, QSettings and notification infrastructure were corrected and reused. The old latest-release endpoint could not establish the highest semantic version, errors collapsed into an ambiguous empty result, and retry eligibility relied on an attempt rather than a successful check.

## 7. Manual checks

The top-right version menu now also serves the main application window. Check for updates runs on the existing worker, disables its action with “Checking for updates…” and prevents concurrent duplicate checks. Manual requests report newer release, up-to-date, network, service/rate-limit or invalid-metadata outcomes. Destroyed widget receivers disconnect safely. View release opens only on user action.

## 8. Automatic notifications

Automatic checks remain asynchronous and nonmodal. The previous successful check controls the 24-hour interval. Failed attempts use a persisted 15-minute initial retry interval, exponential backoff capped at 24 hours, and bounded server retry hints. The existing last-notified release prevents repeated automatic alerts. Disabling notifications also dismisses an existing automatic notice; manual checks remain available. No installer, asset download, self-replacement, UAC or Jana installation changes are implemented.

## 9. Persistence

The existing PhaseStudio/PhaseStudio QSettings namespace and enabled preference are preserved. Successful timestamp, cached stable version and verified release URL, last-notified version, retry deadline and failure count survive process restart. Existing lock-file synchronization is reused. Failed requests never advance the successful timestamp or erase credentials. Update preference actions reflect and update the stored setting.

## 10. Release eligibility and URLs

Public HTTPS release-list API requests select the highest eligible published stable version using the established semantic-version policy, including optional v prefix. Drafts, prereleases, unpublished entries and invalid version tags cannot become updates. Equal/older versions do not prompt. Runtime version comes from the authoritative application version.

Pagination is bounded to five pages of 100 entries; reaching the bound with a full page reports incomplete metadata rather than choosing an arbitrary partial result. Each response is capped at 2 MiB and socket operations have a four-second timeout. Specific links must be HTTPS GitHub pages in ji-ze/Phase-Studio/releases/tag, with matching tag/version and no query/fragment. Missing or untrusted links fall back to the official releases listing.

## 11. Error behavior and diagnostics

Offline feedback says “Unable to check for updates” and “Check your internet connection and try again.” Service/rate-limit and malformed metadata have separate nontechnical feedback. Failed checks cannot generate update alerts. Detailed safe codes, HTTP status or exception class are logged through Python logging and a bounded UTF-8 `updates.log` under the application's per-user generic data location (`PhaseStudio/updates.log`). Raw exception messages, private request headers and local project paths are not logged by the checker. Log write failure cannot break the workflow.

## 12. Integration and menu

Standalone and Jana windows use the same UpdateService and parser. Main-window startup retains its existing lifecycle; installing the menu does not start a premature check during construction. The compact native popup uses its actual button/screen anchor and clamps within available geometry. Keyboard navigation, Escape, checked preference and focus restoration are verified, including a simulated negative-coordinate screen. About remains separated below update actions. No redundant settings window is introduced.

## 13. Privacy and scientific preservation

The checker creates an independent verified-TLS HTTPS connection to the public GitHub API. Requests contain constant public headers and runtime version only: no authorization, cookies, SharpED/Jana credentials, project paths, reflections or structures. Tests inspect mocked requests. No scientific or authentication client is reused.

AST comparison against copies taken before this task confirms 143 existing Jana functions unchanged, including scientific option generation and handoff, and 598 app functions unchanged; the only app function changed is header construction. All 26 existing branding functions are unchanged; Jana parent geometry lookup is added. Evidence: `source-preservation.json`. Scientific golden files were not updated.

## 14. Automated verification

| Check | Result |
| --- | --- |
| Complete pytest suite | **390 passed, 0 failed, 1 skipped; 37 subtests passed** (404.55 s) |
| Final focused Wizard/update suite | **71 passed, 0 failed** |
| Follow-up logging and Qt acceptance tests | **2 passed, 0 failed** |
| Scientific golden checks | **46 passed** |
| Jana completion checks | **192 passed** |
| Python compilation | Passed |
| git diff --check | Passed; existing LF/CRLF warning only |

The focused/full counts overlap and must not be added. Mocked responses cover ordering, versions, publication, pagination, URLs, rate limits, errors, preference persistence, retry scheduling, GUI responsiveness, duplicate prevention and shared launchers. Actual Qt acceptance runs at 100%, 125% and 150% scale. Development-time layout assertions initially exposed unstable minimum-size-hint wrapping; replacing that measurement with text-document measurement resolved them before final verification.

Logs: `build/wizard-updates-full-suite.log`, `wizard-updates-focused-final.log`, `wizard-updates-logging-final.log`, `wizard-updates-scientific.log`, `wizard-updates-jana.log`. Screenshot hashes and preservation evidence: `build/acceptance-wizard-updates-2.0.5/verification.json`.

## 15. Screenshot acceptance

All ten images in `build/acceptance-wizard-updates-2.0.5/` were captured from final actual PySide6 widgets and visually inspected:

1. `01-initial-normal.png` — complete cards and fixed footer.
2. `02-initial-reduced.png` — reduced window, readable summary and cards.
3. `03-advanced-input-expanded.png` — expanded options; content scrolls independently.
4. `04-initial-dpi-125.png` — 125% scale, complete cards.
5. `05-initial-dpi-150.png` — 150% scale, scrolled to show complete secondary cards; upper summary is intentionally above the viewport.
6. `06-jana-parent-fixture.png` — controlled Jana-style Qt parent centering.
7. `07-version-menu.png` — actual native popup captured separately; anchor/work-area placement asserted programmatically.
8. `08-manual-up-to-date-mock.png` — visibly labeled mock metadata.
9. `09-new-release-mock.png` — visibly labeled mock newer release.
10. `10-update-failure-mock.png` — visibly labeled mock failure.

Geometry and fixture descriptions are recorded in `geometry-dpi-*.json`. Icons, descriptions, contrast and accessible scroll endpoints were checked. A short viewport can cut a card at its current scroll position; the complete card remains reachable above the footer.

## 16. Remaining limitations

No live GitHub release check was performed; mock versions are not evidence of published releases. Controlled Qt captures do not prove native Jana launch or physical mixed-DPI/multiple-monitor acceptance. Windows native parent detection, taskbar placement and physical DPI should still receive manual acceptance on the target machine. The simulated tests include reduced work area, off-screen restored coordinates, right screen edge, negative monitor coordinates and keyboard popup behavior. The five-page release history cap deliberately produces an error if the eligible maximum cannot be established within that bound. No packaged executable was built or validated in this task.

## 17. Files changed in this pass

Production: `phase_studio/jana_superflip.py`, `ui_branding.py`, `app.py`, `update_checker.py`, `update_ui.py`.

Tests: `tests/test_update_checker.py`, `test_update_ui.py`, `test_update_release_list.py` (new), `test_wizard_layout_polish.py`, `test_wizard_updates_acceptance.py` (new).

Acceptance tooling: `packaging/tools/capture_wizard_updates_205.py` (new), separator-aware menu expectation in `capture_wizard_geometry_204.py`; this report. Ignored build evidence includes baseline copies, measurements, screenshots, logs and the preservation verifier. Other dirty files belong to earlier tasks and were preserved.
