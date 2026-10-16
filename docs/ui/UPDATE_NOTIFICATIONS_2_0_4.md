# Phase Studio 2.0.4 — release update notifications

## Acceptance gate and scope

The prior [HKL Advanced Diagnostics acceptance](HKL_ADVANCED_DIAGNOSTICS_2_0_4.md) was reviewed. Its 35 focused HKL/powder/UI tests passed again in the starting working tree (30.73 seconds). Existing uncommitted HKL source, tests and report remain preserved. No serious unresolved starting regression was found. Version remains **2.0.4**.

This feature is informational. It does not download executables, install software, modify Jana files, request elevation or start scientific processing. No commit, push, tag, release or release build is made in this task.

## Implementation

| File / authority | Responsibility |
|---|---|
| `phase_studio/update_checker.py` | Stable version parsing, `Release`, metadata validation, numeric comparison and one public HTTPS retrieval |
| `phase_studio/update_ui.py` / `UpdateState` | Dedicated persistent state, atomic cross-process check/notification claims and optional cache |
| `phase_studio/update_ui.py` / `UpdateService` | One QApplication-owned service, daemon network worker, queued Qt delivery, window registration and deduplication |
| `phase_studio/update_ui.py` / `UpdateNotice` | Compact nonmodal notification and explicit official-browser action |
| `phase_studio/app.py` | Existing Help → About action/preference; delayed registration on the main window's first show |
| `phase_studio/jana_superflip.py` | Wizard footer Updates menu, shared service registration and explicit Jana distribution identity for Professional mode |
| `phase_studio/autosolve_window.py` | First-show registration of Execution/Autosolve, including launches that do not show Professional mode |
| `tests/test_update_checker.py`, `tests/test_update_ui.py` | Mocked transport/version, state, concurrency, GUI and real launch-path checks |

All modes use the same service. Existing scientific startup/handoff functions were not exempted from their golden checks or rewritten to accommodate notifications. No scientific golden expectation was changed.

## Release source, validation and privacy

One `GET https://api.github.com/repos/ji-ze/Phase-Studio/releases/latest` is made with `User-Agent: PhaseStudio/<VERSION>`, the GitHub JSON Accept header and API-version header. Installed VERSION comes directly from `phase_studio/version.py`. Repository `ji-ze/Phase-Studio` and the browser destination `https://github.com/ji-ze/Phase-Studio/releases` are trusted constants.

The checker uses its own stdlib `http.client.HTTPSConnection`, with certificate/hostname verification and a four-second timeout for connection and response socket operations. It has no authenticated SharpED/Jana client, cookies or custom authorization opener. It sends no token, account identity, scientific data, path, installation ID or project information. HTTP redirects are not followed, responses are capped at 256 KiB, and no automatic retry occurs. HTTP errors (including 403/429), DNS/offline/TLS errors, timeouts, malformed JSON and unexpected schemas fail silently for automatic checks. Manual checks receive only the specified generic message.

Both draft/prerelease flags must explicitly be false. Only a stable three-component numeric tag is accepted, with optional v/V prefix and SemVer build metadata. Prerelease suffixes, invalid forms and leading-zero numeric components are rejected. Comparison uses integer tuples, never lexicographic strings; build metadata does not affect precedence. Release body/HTML and response-supplied URLs are discarded. Only a canonical validated version is displayed as plain text.

Tests confirm installed **2.0.4** produces no automatic notification for **2.0.3**, **2.0.4** or older releases; mocked **2.0.5**, **2.1.0** and **3.0.0** compare as newer. No claim is made that the mocked future release is published.

## Timing and local storage

Registration schedules the automatic check 1.5 seconds after the normal window opens; network I/O runs on a daemon thread and result delivery is queued to the GUI thread. Qt remains responsive, and an unfinished worker cannot delay process exit. Headless/offscreen and startup-probe runs do not automatically contact GitHub; tests inject a mocked worker explicitly.

State uses the established `PhaseStudio/PhaseStudio` QSettings authority with a separate `updates/` prefix:

- `enabled` (default true).
- `lastAttempt` (saved before a request, including failed attempts).
- `latestStable` and `lastSuccess` (validated version cache, at most 24 hours old).
- `notifiedVersion` (highest version already offered).

The shared Windows-user application context throttles automatic checks across standalone/Jana windows and EXE replacements to at most once per 24 hours. It does not create separate quotas for different executable paths. A short QLockFile in the user's generic-data `PhaseStudio` directory protects cross-process claims; network work never holds the lock. An application-session guard also prevents duplicates if settings cannot be stored. If settings cannot persist a claim or the lock is busy, automatic checks are skipped rather than starting repeated requests. Manual checks remain available.

An automatic notification claims its version when shown; Later, the window close action and subsequent windows therefore do not repeat it. A higher version can notify again. Manual checking deliberately bypasses the automatic preference, interval and dismissal, and replaces a currently visible older notice rather than opening duplicates. A manual request during an existing check reuses its pending result. Closed/destroyed owners do not receive orphan dialogs.

## UI and distribution distinction

Standalone: **Help → About → Check for updates**, with **Notify me when new versions are available**. Jana Wizard: the footer **Updates** menu exposes the same action/preference. Controls share the same service and synchronize their preference/busy state.

Notifications use the existing navy/cyan theme and ordinary interface font. They use `show()`, NonModal and ShowWithoutActivating, never a modal `exec()` loop or automatic foreground activation. They have no installer action. **View release on GitHub** is the sole browser-opening path and always opens the constant official Releases URL; **Later** only dismisses. Jana notices additionally explain: “The version integrated into Jana2020 may be updated through a Jana2020 software release.” Downloading a standalone EXE is not described as updating Jana.

## Tests and visual acceptance

Update-only tests: **48 passed**. They cover older/equal/newer versions, invalid and prerelease/draft metadata, request headers/privacy, oversized/invalid schemas, offline/TLS/timeouts, HTTP/rate-limit failures, intervals/cache, stored dismissal, shared windows/independent state instances, read-only state, manual opt-out bypass, nonblocking Qt, destroyed owners, both actual launch UIs, browser action and three DPI scales. All responses are mocked; none depends on live GitHub.

The release-boundary/scientific AST suite plus updater tests passed **68 tests**. The final update-only run, including read-only state handling, passed **48 tests** (8.79 seconds). The complete final suite passed **352 tests, 1 skipped, 37 subtests**, zero failures (319.22 seconds). The skip remains the opt-in real scientific workflow test; no live inference acceptance is implied. Scientific/Jana and UI scripts passed **587 checks**: scientific core 46, Jana completion 192, workflow state 141, density alignment 41, displacement 44, Wizard geometry 75, Wizard text clipping 18 and final UI 30.

Fifteen actual PySide6 client-area images are stored only under:

`build/acceptance-updates-2.0.4/scale-{1,1.25,1.5}/`

1. `01-manual-no-update.png`.
2. `02-standalone-new-version.png`.
3. `03-jana-new-version.png`.
4. `04-manual-failure.png`.
5. `05-later-reopened-no-prompt.png`.

All five states were visually inspected at 100%, 125% and 150%. Each clearly identifies mocked metadata or the controlled dismissal test. Captures use a controlled 1920 × 1040 physical-pixel available screen and actual Qt scaling. The reopened Wizard uses its existing body scrolling at the restricted 150% logical height; footer actions remain visible. Tests verify nonmodal/show-without-activation flags and GUI responsiveness. Capture instrumentation records zero real browser openings and zero live GitHub/SharpED requests. The public ten-image Wizard collection is unchanged.

## Packaging and remaining limitations

Compilation and Git whitespace checks pass. Source ModuleGraph analysis from both `phase_studio.standalone` and `phase_studio.jana_superflip` discovers the two new modules. All required stdlib modules and Qt Core/Gui/Widgets are already in both existing ONEFILE/ONEDIR runtime dependency sets, and both existing profile-boundary checks pass. No new third-party dependency, installer or build-spec modification is needed.

These are source/dependency checks against the existing distributions, not frozen execution of the new feature. A requested future release build must include and smoke-test it; the previously produced EXEs do not contain these working-tree edits. Live GitHub access and physical native Windows/Jana focus/multi-monitor acceptance were not performed. The checker uses direct HTTPS, without authenticated enterprise proxy configuration; DNS resolution follows OS behavior while connection/read socket operations have the configured timeout. Unavailable connectivity is silent automatically and uses generic feedback manually.

Authentication, HKL/overlap engines, Superflip/SharpED/EDMA calculations, maps, candidate ranking and Jana handoff data/protocol are unchanged. The original HKL acceptance assets and other local uncommitted materials are preserved.
