# Current public release state

See [public release audit](PUBLIC_RELEASE_AUDIT_2_0_2.md) and root release notes.
The following technical history includes earlier internal builds; installer
references and older validation totals are historical, not the final public
distribution contract.

# Phase Studio 2.0.2

Phase Studio 2.0.2 fixes SharpED TLS validation in frozen Windows builds,
simplifies the Jana2020 Wizard, updates the guided workflows, and brings the
Result Selection structure viewer to the same crystallographic presentation
contract as the Autosolve viewer.

## Release behavior

- The authoritative SharpED Public API is `https://jana.fzu.cz/`. Model
  discovery and inference resolve from that one authority with no fallback or
  silent failover.
- Frozen Windows builds use `truststore` and the Windows certificate store.
  Certificate verification and hostname verification remain enabled.
- The normal Jana2020 Wizard shows all four workflows at once: Superflip only,
  Superflip + SharpED (Recommended), SharpED Autosolve (Experimental), and an
  equal secondary Professional mode tile. Optional reference/initial-model
  inputs use an obvious collapsed disclosure so the opening page does not
  scroll at the Full HD / 125% acceptance target.
- Superflip + SharpED defaults to five ordinary multi-cycle iterations,
  preserves the exact catalog model chosen by the user, exposes the shared
  Map Feedback controls, and runs in the focused execution window. The old
  pre-run Objective page and its hidden source state are removed; both
  Charge-flipping solution (Superflip) and Model prediction (SharpED)
  families are retained.
- Execution, Result Selection, fullscreen views and concise logs use the
  scientifically accurate Charge-flipping solution name for the reconstructed
  Superflip map. Candidate metadata records the effective Superflip seed and
  whether the reflection input was original or Map Feedback adjusted; cycle
  number is never used as a substitute for that provenance.
- Empty execution viewers show source-specific preparation/waiting states and
  keep structure-only camera, representation, cycle and fullscreen actions
  disabled until their candidate exists. Completed automatic EDMA structures
  still publish asynchronously as soon as each source finishes.
- SharpED Autosolve uses five cycles for the initial phase search and three
  cycles for every later refinement block. Thresholds persist to 0.10 sigma,
  with 0.20, 0.10, and 0.05 step bands.
- A completed candidate can be passed safely before the active calculation
  finishes. The operation freezes the completed candidate registry, stops
  unfinished work, and opens the shared Result Selection dialog on the GUI
  thread; it never hands off preview data, includes an incomplete cycle, or
  recomputes a result. This terminal route is reported as a Jana2020 handoff,
  independently from an ordinary user cancellation.
- Result Selection, its structure preview, its selected-output summary and the
  Jana2020 handoff now share one hash-pinned candidate identity. The handoff
  verifies the selected map, EDMA CIF, and EDMA-generated Jana `.m40` again.
  The selected scientific XPLOR map receives one `maxcycles 0` conversion and
  supplies the `.m80`/`.m81` density pair and ready XPLOR. The exact reviewed
  EDMA job supplies the original `.inflip`'s exact declared `writem40` model
  input. Jana imports that raw EDMA representation and creates the live
  `outputbase.m40` with its required origin/header transformation. The valid
  canonical Jana project `.m50` context is captured before conversion,
  validated, staged with the candidate, and republished with
  `writem40`/`.m80`/`.m81` as one rollback-protected protocol set.
  A missing, empty,
  changed or mismatched model artifact stops the handoff; Phase Studio never
  substitutes the latest, recommended or default-threshold result. When EDMA
  is explicitly disabled, one map conversion supplies both protocol files and
  the selector states that Jana2020 will determine the structure from the map.
- Threshold review promotes every completed EDMA interpretation to a
  source/cycle/threshold/content-specific canonical CIF. Changing between
  Complete molecules and Full cell affects rendering only and cannot alter the
  candidate ID or either artifact hash.
- Jana integration paths are anchored to the active Jana root of the launcher
  that Jana2020 actually started. The normal scientific executable is
  `<active Jana root>\SUPERFLIP\superflip.exe`; it is never redirected through
  `PATH`, another Jana installation, or a hard-coded root. The original-name
  binary is used only by a verified legacy in-place wrapper installation to
  avoid recursion. Runtime logs record the root and exact executable; a marker
  version mismatch stops before scientific work.
  The wrapper writes `log.txt` to the active Jana project directory rather
  than the installed `SUPERFLIP` integration directory.
- Result Selection now supports Complete molecules and Full cell views,
  bonds, a unit-cell frame where applicable, fit/reset/rotation controls,
  source-specific metadata, formulas, an element legend, retained per-source
  choices, EDMA-only atom-threshold adjustment, and cached batched rendering
  for large structures. Its handoff-family selector uses the primary names
  Charge-flipping solution and Model prediction, with technical provenance shown beside
  them.
- Result Selection, Autosolve, detached structure windows and the classic
  comparison now use the same camera controls: left-drag orbit, right/middle
  drag or Shift-left-drag pan, wheel zoom, double-click/F Fit, R Reset and
  Space auto-rotate where available. Camera interaction changes only the view;
  it does not rebuild scientific geometry or change the selected candidate.
- The classic three-panel comparison uses the same shared view selector,
  molecule/full-cell semantics, source-specific formula authority, and
  element-color authority. Superflip and SharpED independently expose every
  completed cycle, Latest follow mode, EDMA-only + atoms / - atoms review and
  one-structure fullscreen; Reference remains fixed and view-only. Each panel
  keeps its own fit and center while orientation remains synchronized. A
  Reference formula is never reused as a calculated candidate formula.
- Result Selection, the dual execution viewer, and the classic comparison can
  detach their live viewer fullscreen. F11 toggles fullscreen, Esc restores
  the exact same widget, and repeated activation reuses the existing window;
  selection, threshold, view mode, camera, and renderer cache therefore remain
  synchronized.
- Execution logs remain compact by default and can be expanded without losing
  automatic newest-message following. Autosolve expands its log on an error;
  inactive stage progress collapses so completed/review states give the
  structures more room. Detached inspection groups cycle, threshold, camera,
  view-mode and window actions and uses explicit Enter/Exit fullscreen labels.

## TLS audit

The release build used Python 3.12.13, OpenSSL 3.5.7, PyInstaller 6.20.0,
and truststore 0.10.4. HTTPS uses the standard-library `urllib.request` stack;
`requests`, `urllib3`, and `certifi` are not installed in the release build
environment. `SSL_CERT_FILE`, `SSL_CERT_DIR`, and `REQUESTS_CA_BUNDLE` were
unset. Python's OpenSSL defaults reported no active CA file or directory.

The server presented the `sharped.fzu.cz` leaf and its Let's Encrypt/ISRG
issuer chain. Windows built a valid chain through its trusted ISRG root. The
old frozen client failed because its OpenSSL trust mechanism did not use the
Windows trust store, so the classified root cause is **B: frozen-client
trust-store incompatibility**. No evidence of a SharpED route, DNS, TCP, or
Windows chain failure was found.

The built standalone EXE retrieved
`https://sharped.fzu.cz/sharp-ed/models` using Windows system trust. The live
response reported `koala phase boost 2` as the default and included:

- `koala phase boost`
- `koala phase boost 2`
- `koala model balanced`
- `koala model progressive`

The frozen diagnostic also confirmed certificate and hostname verification
were enabled. Catalog success does not prove authenticated inference. No
currently accepted test token was available, so an authenticated inference
request was not made.

## Final geometry and responsiveness audit (items 41–61)

41. The release-blocking Result Selection regression had two causes. Its first
    geometry clamp ran before the children and layouts existed, so the later
    two-line selector, 260-pixel preview minimum, metadata, table and action
    rows could make Qt enlarge the native window after the clamp. The summary
    and actions also lacked a single fixed footer allocation.
42. Result Selection did not restore saved geometry, so stale settings did not
    contribute to this failure. Other top-level windows still distinguish saved
    normal geometry from an explicitly maximized state and re-clamp restored
    rectangles to the current monitor.
43. Every affected top-level sizing path uses the selected parent/current
    screen's `availableGeometry()`, including native-frame allowance. Reserved
    taskbar space is never treated as usable client area.
44. The main and focused execution windows prefer 1420 × 880 and 1420 × 860,
    respectively, capped at 92% × 90% of the work area. They open normally and
    remain manually maximizable.
45. Result Selection now computes geometry only after its layout is complete.
    It prefers 1180 × 680, including native-frame allowance, capped at 90% ×
    84% of the parent monitor's `availableGeometry()`, and receives a queued
    post-show clamp against the same screen. It never inherits a maximized
    parent state. On the representative 1366 × 728 work area the client target
    is about 1180 × 572; on 2560 × 1400 it is 1180 × 680.
46. Map Feedback remains inside the Wizard's existing scrollable body, its
    footer remains outside that body, and the final scientific editor now has
    explicit bottom breathing room above the fixed actions.
47. Cycle and Map Feedback numeric editors use bounded natural widths; the
    model selector is 300–520 logical pixels. Refresh/status and SharpED
    settings share the configuration form's editor alignment.
48. Structure canvases no longer carry the obstructive camera tooltip. Every
    viewer shows the same compact `rotate · pan · zoom · fit` help line.
49. The blocking path was the GUI callback calling
    `_retune_result_candidate()` synchronously, then
    `_run_configured_edma_stage()` → `run_edma_on_xplor()` → `run_command()`.
    `run_command()` remains in its polling/wait loop until EDMA exits, so that
    entire external calculation previously occupied the Qt GUI thread.
50. `ReviewEDMAExecutor` now owns interactive review jobs independently of the
    workflow thread. Workers publish immutable outcomes to the existing Qt
    message queue; only the GUI queue consumer changes widgets/candidate state.
51. Four rapid scheduling calls complete in under 50 ms in the release guard;
    a deliberately blocked EDMA worker does not block the owner thread.
52. A concurrent workflow marker reaches all five checkpoints while review
    EDMA remains blocked. Review jobs do not consume or wait on the workflow
    execution slot.
53. Every request uses
    `review_edma/<run>/<source>_cycle_NNN/request_<id>_<sigma>/`, copies/reads the
    immutable completed canonical map, and uses unique EDMA input/log/CIF names.
    Failed or cancelled partial request directories are removed.
54. Requests carry run, candidate, source, cycle, threshold, map hash and a
    monotonic generation. Stale generations may populate their own cache but
    cannot update the current panel; a run-ID mismatch cannot touch a later run.
55. Each candidate has at most one active worker and one pending target. Rapid
    0.8 → 0.7 → 0.6 → 0.5 review runs 0.8 and 0.5 only; only 0.5 updates the UI.
56. Completed results are cached by run/source/cycle/map hash/threshold.
    Returning to a prior threshold is immediate and launches no EDMA process.
57. During review the panel states both `updating…` and the last completed
    handoff threshold. Pass remains tied to that complete candidate, so a
    partial review artifact can never reach Jana2020.
58. Starting/clearing/closing a run cancels review stop events and invalidates
    callbacks. The Run-1/Run-2 guard proves a cancelled Run-1 completion cannot
    invoke or mutate Run 2.
59. Synthetic 1366 × 728 and 2560 × 1400 work areas, plus real-dialog 100%,
    125%, and 150% DPI subprocesses, passed. At every DPI the complete outer
    frame, fixed footer, Return button and Pass/Save button were contained in
    taskbar-adjusted `availableGeometry()` and the dialog was not maximized.
60. The candidate table and preview now form the only vertically expanding
    region. Their minimums were reduced, the table accepts horizontal shrink,
    and a 34/66 splitter allocation is reapplied on resize until the user moves
    the divider. Manual vertical shrink tests keep the complete footer visible.
61. One fixed footer outside the splitter owns both the selected-output summary
    and both actions. The automated Jana auto-open test shows the real dialog,
    checks both actions' global rectangles, then clicks Pass and proves the
    accepted candidate reaches the existing handoff handler exactly once.
62. Both automatic completion and manual Result Selection use the same
    `open_result_selector()` construction and sizing path; there was no separate
    auto-open geometry path.
63. The preview canvas minimum fell from 260 to 120 logical pixels and remains
    the right panel's expanding child. Fit now measures its projected selected geometry
    to target 80% of the actual drawing canvas, within the requested 70–85%
    range. The camera help is compact and muted with its full text in a tooltip,
    and toolbar controls wrap into two rows.
64. The execution viewer canvas minimum fell from 320 to 210 logical pixels so
    panel metadata and the wrapped SharpED validation note finish above the log.
    The existing fixed bottom action row remains unchanged.
65. Each execution panel now shows EDMA threshold and detected-atom count once,
    directly beside its local +atoms/-atoms controls. Source/cycle/model remain
    on the preceding metadata line; the duplicate threshold was removed.
66. Dense structures retain every atom and bond while using bounded smaller
    markers, edge widths and bond widths. Bond construction still occurs from
    the final displayed atom set.
67. The workflow diagnostic now describes the main Superflip → SharpED
    progression and separately states that EDMA extraction runs asynchronously
    for completed Superflip and SharpED maps.
68. Updated Wizard screenshots remain under `docs/screenshots/2.0.2-wizard`.
    The available automation desktop rejected capture with an invalid display
    handle, and it exposed only one physical monitor. No fabricated or blank
    frozen screenshot was retained. The mandatory real frozen Result Selection
    screenshot, completed execution screenshot and reverse two-monitor exercise
    therefore remain manual release acceptance evidence.

## Execution logging and runtime-path audit (items 69–94)

The normal GUI Execution Log is now a concise scientific progress stream. It
shows run/cycle boundaries, the Superflip → SharpED critical progression,
asynchronous EDMA starts and results, compact validation, warnings, errors and
completion. Repeated SharpED polling states are suppressed. Absolute paths,
commands, hashes, raw map statistics, temporary names, compatibility details
and other forensic records are classified as `DIAGNOSTIC` and remain in the
complete file log. `Open log` beside `Expand log` opens that file. Records are
timestamped at event creation with millisecond precision, which preserves the
ordering of concurrent EDMA and SharpED work.

The logging/runtime writers and their resolved destinations are:

| Writer | Classification | Resolved destination |
| --- | --- | --- |
| Jana wrapper `JanaLogger` | project/session log | `<incoming .inflip parent>\log.txt` |
| GUI `RunDiagnosticLog` project index | project/session log | `<incoming .inflip parent>\log.txt` |
| GUI `RunDiagnosticLog` | complete run log | `<allocated run_####>\log.txt` |
| Superflip process capture | external-program log | `<run_####>\cycle_NNN\*.superflip.log` (or its run-scoped symmetry directory) |
| SharpED request capture | external-program/API log | beside the run-scoped output map as `*.sharped.log` |
| EDMA process capture | external-program log | the run/review EDMA output directory as `*.log` |
| Powder repartitioning | scientific audit log | `<run_####>\cycle_NNN\cycle_NNN_powder_repartitioning.log` |
| Jana return conversion | protocol audit log | `<run_####>\jana2020_return_map.log` |

Previously, the lightweight wrapper's final generated `calc_m80.inflip` used
the installed wrapper's `deblurrer` directory, and the full-GUI handoff's
`calc_m81.inflip` was likewise rooted below the installed original Superflip.
That was the concrete installation-directory write defect. The lightweight
input is now a unique, short-lived file in the immutable incoming `.inflip`
project directory. The full-GUI input is under
`<run_####>\jana_handoff\calc_m81.inflip`. Neither the log nor generated
protocol inputs are derived from `sys.executable`, `__file__`, the Superflip
executable, or a later current working directory.

`jana_project_dir` is resolved once from the absolute incoming `.inflip` before
the wrapper can change working directory. For the reported project, the
authoritative paths are:

- project log:
  `<project-directory>\log.txt`;
- input:
  `<project-directory>\sample-project_Superflip.inflip`;
- detailed run log:
  `<project-directory>\phase_studio_full_run_sample-project_Superflip\run_####\log.txt`;
- early-startup fallback when no input is known: `%TEMP%\PhaseStudio\log.txt`.

Project logs append and carry an explicit session separator, version, start
time, project/input, run ID and run-directory pointer. The run log separately
records program locations, all diagnostic categories and the Jana handoff
map/CIF/m40 identities, hashes and selected/live site counts. A non-empty
selected EDMA model producing a zero-site live Jana m40 aborts before Jana is
triggered.

Automated guards use unrelated CWD, project and simulated `Program Files`
installation roots. They prove the installation tree remains byte-identical,
no generated descendant appears there, Unicode and space-containing project
paths work, and missing project context selects the temp fallback. The wrapper
completion guard runs Superflip-only and Superflip+SharpED twice through the
real orchestration boundary and proves each generated input remains project
local. The test installation is therefore treated as read-only by the
workflow, without depending on Windows ACL behavior.

Before the final frozen acceptance run, the real files were recorded as:

| Path | Bytes | Last write UTC | SHA-256 |
| --- | ---: | --- | --- |
| `<project-directory>\log.txt` | 570 | `2026-10-08T10:22:35.0490385Z` | `83177BE41A0DD70AF4F5C908ADBCEAC43F5AA50D1F8CA826430DA6E619F16755` |
| `C:\Jana2020\SUPERFLIP\log.txt` | 305 | `2026-10-07T14:14:09.5082825Z` | `5401815FBD34ACE062121491A9E682B15479C682EC9AC5001DDEDD2591412053` |

These are the required **before** values only. A real frozen run followed by an
immediate second run has not been performed from this working session because
it requires choosing the workflow and completing the Jana2020 GUI handoff on
the affected desktop. The release must still record the after values and prove
that the project log changes, the installation log stays byte-identical, and
Run 2 receives a new `run_####\log.txt`. Logging is automation-complete but is
not declared frozen/manual accepted until that evidence exists.

## Final layout polish (items 95–110)

Result Selection now gives one- and two-row candidate sets their natural table
height instead of reserving six empty rows, leaving more vertical space for the
structure. Its existing full-width source selector, compact metadata,
validation note, expanding table/preview splitter, fixed selected-output footer
and pinned actions remain inside the available work area at 100%, 125% and 150%
DPI. The main execution view keeps the concise log compact and exposes the full
file through `Open log`.

The single-structure fullscreen viewer now has stable action groups: window
actions, navigation and camera controls, then zoom/view-mode controls. Its
metadata is compact and the interaction hint is visually secondary. Initial
fullscreen and pre-interaction resizes refit the model using the canvas aspect
ratio and consistent padding; user zoom/pan is preserved after manual camera
interaction. This removes the small, low structure presentation without
changing atoms, bonds, selection, threshold state or scientific outputs.

Synthetic work-area and real-widget guards cover 1366 × 728 and 2560 × 1400,
100%/125%/150% DPI, fixed footer accessibility, source-tab switching,
fullscreen entry/exit, camera continuity and result identity. The requested
five real before/after screenshot pairs were not available as files in this
session, and the automation desktop cannot provide a valid real Windows display
capture. They remain mandatory manual evidence; no offscreen rendering is
presented as a real frozen screenshot.

## Verification

- All 47 direct test scripts passed: **2,184 explicit checks**.
- Unittest discovery passed: **58 tests**.
- Pytest passed: **58 tests**.
- Jana completion and handoff: **192 checks**.
- Autosolve window: **255 checks**.
- Result Selection and classic viewer: **69 checks**, including controlled
  P1, P-1, special-position and input-versus-EDMA composition checks, plus bounded
  1,400-atom and 2,000-atom camera/rendering checks.
- Multi-monitor and DPI geometry: **14 checks**.
- Autosolve guided UI: **151 checks**, including metadata/log separation and
  single EDMA threshold/count presentation.
- Scientific core, EDMA thresholds, map scaling/tiling, map-quality reports,
  metrics CSV golden rows, workflow states, QSettings migration, and packaging
  boundaries all passed.
- Scientific golden outputs and schemas showed no differences.
- The complete standalone-script suite passed **2,184 checks across 47 suites**;
  pytest discovery also passed **58 tests**.
- `compileall`, `git diff --check`, wrapper dependency audit, frozen import
  verification, both ONEFILE distribution checks, and both `--version` smoke
  tests passed.

The Jana protocol was also checked with the installed Jana2020 Superflip and a
copy of the real failing project. A fresh Superflip-only probe established the
file-set reference: Superflip creates/updates `.m80`, `.m81`, and `.sflog`; it
does not modify the existing valid `.m50`. Jana's continuation supplies the
`.m40` sites and carries the `.m50` project context and `.l51` refinement-list
companion to the active solution. The selected SharpED XPLOR map is converted
once into the `.m80`/`.m81` density pair and ready XPLOR output. The exact
EDMA-produced `.m40` beside the selected threshold-specific CIF is staged under
the original `.inflip` `writem40` name. The probe used a 257-site selected CIF
and its 294-site Jana model artifact; the nonzero difference is the expected
Jana representation rather than loss of the model. Source/artifact SHA-256
prefixes were map `528104ec7267`, CIF `5daa10be5f2e`, staged `.m40`
`693c7855fe65`, fresh `.m81` `232f989d4acd`, fresh `.m80`
`254663d30bf3`, and ready XPLOR `bc856ed555ca`.

The later regression deleted the generated `_Superflip.m50` before the map
conversion, even though Superflip does not regenerate that Jana context. It
also risked confusing the raw `*_Superflip_tmp.m40` EDMA file with Jana's
post-import `*_Superflip.m40`. The corrected handoff validates and captures the
nonzero canonical `<project>.m50`, republishes it under the `.inflip`-declared
output base, hash-pins the selected EDMA file under the declared `writem40`
name, converts the exact selected map in a candidate-scoped directory, and
publishes that coherent input set together. Jana remains responsible for the
canonical, `_Sol`, and `_Superflip` post-import aliases.
Every successful pass also archives exact live bytes and a hash manifest under
`<Jana project>\output\run_####\handed_to_jana`; the archive is never searched as scientific
input. Three
sequential runs (`koala 2.0`, `koala model progressive`, then `koala 2.0`) also
passed isolated run-directory, artifact-hash and queued-event lineage checks.

The frozen integration can live in `<Jana root>\SharpED`. That directory is
the Phase Studio integration root, not the Jana installation root. Runtime
resolution now takes its parent as the Jana root and selects only
`<Jana root>\SUPERFLIP\superflip.exe` and
`<Jana root>\SUPERFLIP\EDMA.exe`; it explicitly avoids the invalid
`<Jana root>\SharpED\SUPERFLIP` path and does not search PATH or silently
select `superflip_original.exe`.

Windows launch activation now verifies the real Qt HWND with
`GetForegroundWindow`. If ordinary Qt activation is rejected by the Windows
foreground lock, Phase Studio briefly attaches the GUI input thread to the
previous foreground thread, performs the native foreground sequence, and
detaches it in `finally`. A final fallback temporarily promotes the HWND to
TOPMOST and immediately restores NOTOPMOST. The detailed project log records
both HWNDs, the fallbacks used, and the verified final foreground state.

Composition now has two explicit authorities. The Jana Workflow Input Summary
retains the `.inflip` value as `Superflip input composition`. Every completed
EDMA result instead stores `edma_asu_composition` on its hash-pinned candidate.
The execution view, Result Selection and detached/fullscreen viewers read that
candidate metadata and never substitute the run input/search composition.

The EDMA value is calculated from the selected CIF's fractional coordinates,
cell and active space group. Sites are grouped into element-sensitive symmetry
orbits using periodic minimum-image Cartesian distances and a 0.05 A tolerance;
one input site is retained per orbit, including one representative for a
special-position site. Counts are reported directly by element without GCD or
formula normalization. The raw detected-site count remains a separate line.
Threshold recalculation publishes the CIF, threshold, hashes, ASU composition
and handoff identity together; while it runs, the prior completed candidate
remains visible and handoff-capable. The handoff manifest records the selected
EDMA ASU composition as diagnostic metadata without changing Jana protocol
files or scientific handoff behavior.

The supplied repository contains the real comparison rendering but not the two
source EDMA CIF artifacts needed to calculate the requested `2int3total` 0.30
sigma Charge-flipping solution and 0.50 sigma Model prediction counts. Those two real
values and their frozen GUI screenshots remain a real-machine acceptance item;
the `.inflip` value is not used as their expected answer.

Automatic EDMA on the completed Superflip map now overlaps the primary SharpED
request through a bounded two-worker branch executor. The workflow-state guard
blocks that EDMA job and proves SharpED starts before it completes. Starting the
next Superflip cycle before SharpED-map EDMA is only scientifically independent
when the next cycle does not consume that EDMA CIF as its model or automatic
phase-origin reference; the normal `referencefile_mode=omit` workflow does
consume it. That second overlap therefore remains intentionally serialized for
the current authoritative workflow semantics rather than changing scientific
inputs under a scheduling optimization.

Automatic EDMA publication no longer waits for validation or cycle
finalization. Each queued/running/completed structure job carries its run ID,
source, cycle, map path and SHA-256, threshold, request ID, and generation.
The worker posts an immutable completion event immediately after EDMA returns;
the Qt queue validates the identity and hash before updating the viewer on the
GUI thread. A newer pending job leaves the previous completed structure visible
with an `EDMA updating…` caption. Interactive threshold jobs publish through
the same registry and retain latest-request-wins behavior.

Complete-molecule rendering now builds minimum-image periodic bonds with their
integer lattice translations, traverses that graph to unwrap each component,
and creates final display bonds only after component selection. The real
`2int3total` Model prediction changed from two displayed islands (386 primary
sites, fit radius 26.29 Å) to one connected 211-site object with 396 bonds and
a 13.91 Å fit radius. Its Full-cell view remains the separate 2,822-site,
one-cell representation. A real-data before/after rendering is stored in the
local build acceptance directory, and the deterministic 0.99/0.01 fractional
boundary fixture pins the periodic translation behavior.

Tiled SharpED progress now suppresses each tile server's generic `Completed`
message. The GUI reports `Tile i/n complete` only after that tile is read and
accumulated; only the written reconstructed map reports SharpED complete.

The Jana workflow-to-execution transition keeps the startup surface visible
while the execution window is constructed, shown, assigned a native HWND,
activated and verified. Only after the execution HWND owns the foreground is
the startup surface hidden. The shared Windows helper records the source and
target HWNDs, whether native and temporary-topmost fallbacks were needed, the
final foreground HWND, and the verified result; temporary topmost state is
always removed.

Wizard-selected automatic workflows now construct the full workflow object as
a hidden scientific backend and display only the dedicated Execution window.
They do not call the Professional-window initializer, show that window, or
activate it. Three sequential cold-start guards prove that no Professional
top-level appears for Superflip + SharpED, Autosolve or phase recycling;
Professional remains visible only when the user explicitly selects it.

Wizard configuration controls now use responsive width limits: the cycle field
uses a 140-220 px logical band and the model catalog uses a 380-550 px band.
Model refresh and status form one compact row, validation and Map Feedback
callouts use tighter aligned margins, and Map Feedback numeric grids retain
their compact fields above the fixed footer. Empty execution panels now follow
the actual asynchronous stage (`Superflip running`, `EDMA structure extraction`,
or `SharpED processing`) and rerender when that stage changes.

## Final model policy, branding and reflection diagnostics

The normal Superflip + SharpED Wizard now selects an exact live-catalog model
from the requested cycle count: one cycle uses `PEAK A (model prediction)` and
two or more cycles use `SEED (cyclic CF)`. The server's default value is retained
for diagnostics but is never inserted as a selectable alias or used to resolve
the Wizard choice. A manual selection remains selected while it is available;
the automatic policy is restored with a visible warning if a refreshed catalog
removes it. An unavailable catalog or required policy model blocks the run. The
detailed run log records both the exact API model ID and displayed name before
submission. This policy does not alter the separate SharpED Autosolve model
sequence.

The PHASE STUDIO wordmark uses the bundled variable Science Gothic face at
weight 400 and zero absolute letter spacing at the resolved font
size. The same centralized renderer supplies the Wizard,
splash and application headers. Science Gothic is redistributed under the SIL
Open Font License 1.1; its license text is packaged beside the font. Source and
frozen-runtime probes verify that Qt registers and resolves `Science Gothic`
rather than substituting another family.

Reflection diagnostics use one explicit set of definitions. Parsed unique
reflections are exact literal `(h,k,l)` triplets. The theoretical denominator
for completeness is the symmetry-reduced asymmetric-unit set. `(0,0,0)` is
retained only when a phase-bearing input/protocol requires the raw row, and is
excluded from physical resolution, completeness, d98 and significance
statistics. A numeric zero phase is a populated phase field; it does not imply
an experimentally determined phase. Significance is derived and displayed
once. The histogram includes every finite value, with explicit `<1` and `>=15`
edge bins. `d98` is the highest-resolution cumulative shell that remains at or
above 98% completeness, while the displayed threshold is the first linearly
interpolated crossing of the selected completeness level.

Map Feedback remains visible for a one-cycle run but is disabled because no
later cycle can consume it; its stored values are preserved. For iterative
runs, each feedback start cycle is capped at `N-1`.

The seven Wizard acceptance captures were regenerated at the standardized 125%
offscreen scale. Automated geometry tests cover 100%, 125% and 150% scaling;
real-monitor captures and the real Jana2020 handoff remain manual acceptance
items as listed below.

## EDMA displacement units and bounded exports

EDMA's isotropic continuation value was previously copied directly into the
Jana `.m40` Uiso field. Phase Studio now gives that boundary explicit units,
converts Biso to raw Uiso with `Uiso = Biso / (8*pi^2)`, validates finiteness,
and clamps exported Uiso to `0.010-0.150 A^2`. One normalization authority is
used by Jana `.m40`, EDMA CIF and PDB output. An explicitly Uiso source is not
converted again. Candidate CIF files carry the bounded value in
`_atom_site_U_iso_or_equiv`; PDB temperature-factor columns convert the same
bounded Uiso back to Biso. Nonfinite or missing displacement values fail
explicitly instead of being serialized.

The raw converted Uiso remains in a sibling `*_scientific_raw.cif` used for
later scientific seeding. The clamp therefore changes only exported EDMA
atomic-model displacement fields. It does not change maps, EDMA peak finding,
thresholds, coordinates, occupancies, site counts, symmetry, connectivity,
ranking or candidate identity. The detailed project log records source Biso,
raw Uiso, the allowed interval, lower/upper/unchanged counts, final range and
the raw scientific sidecar; the normal Execution Log is not filled with
per-atom output.

Fresh normal Charge-flipping solution and Model prediction workflows both
start at 0.50 sigma, regardless of cycle count or values inherited from a Jana
`.inflip`. The value remains editable. From 0.50 sigma, `+ atoms` selects 0.40
sigma and `- atoms` selects 0.60 sigma; two steps select 0.30 and 0.70 sigma.
The separate Autosolve policy retains 1.00 sigma for both streams. Professional
controls and the recommended preset share the normal-default authority, while
explicit persisted Professional/user choices remain editable.

The earlier 1.00-sigma acceptance run used the real
`2int3total_Superflip.inflip` project with the
installed EDMA at exactly 1.00 sigma for both existing completed maps. The
Charge-flipping solution produced 1,310 retained sites (`Ag262 S262 O262 N262
C262`), source Biso `0.0572-2.8671 A^2`, and raw Uiso
`0.000724-0.036312 A^2`. Its exported CIF range is
`0.010000-0.036312 A^2`: 1,202 sites were lower-clamped, zero upper-clamped,
and 108 unchanged. Its five-site Jana `.m40` range is
`0.026276-0.036312 A^2`, with all five unchanged.

The Model prediction produced 1,179 retained sites (`Ag236 S236 O236 N235
C236`), source Biso `0.0099-0.7053 A^2`, and raw Uiso
`0.000125-0.008933 A^2`. All 1,179 CIF sites were lower-clamped to `0.010000
A^2`; zero were upper-clamped. All five Jana `.m40` sites were lower-clamped
from raw `0.007332-0.008621 A^2` to `0.010000 A^2`. The corresponding PDB Biso
ranges are `0.79-2.87 A^2` and `0.79-0.79 A^2`. Both actual export sets passed
coordinate, occupancy-policy, site-count, CIF bounds, Jana parsing and
CIF/PDB physical-equivalence checks.

## Windows artifacts

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `PhaseStudio-2.0.2-x64.exe` | 80,155,548 | `804C6EBBE16B4648ED69ED2D22C5C414D274AC1F6AC2D7B0CC38DBC6722ECD31` |
| `PhaseStudio-Jana2020-Installer-2.0.2-x64.exe` | 129,633,081 | `46DD77D162B885F0C789185DB7BD6201CA1EEE9B0859B5A0DEFD447CF561BE6D` |

Both artifacts are x64 PE files (`0x8664`) with FileVersion and
ProductVersion `2.0.2`.

The final density-frame correction preserves the selected source grid and
origin instead of repeating symmetry averaging during handoff. Both normal
EDMA defaults are 0.50 sigma. The exact diagnosis, three real 2int3total cases,
numerical errors, artifact hashes, performance cost and blocked ochlor
native-map test are documented in [Jana density-frame validation](PUBLIC_RELEASE_AUDIT_2_0_2.md).

## Remaining manual acceptance

A real Jana2020 GUI acceptance run remains required on the affected Windows
machine: install this build and exercise Superflip-only, Charge-flipping solution with
EDMA, progressive-model with a distinctive threshold, EDMA-disabled, and the
immediate second-run case. Confirm the Jana information dialog contains the
selected nonzero structure and Jana continues normally. The installed
Superflip protocol preparation was verified, but that does not execute
Jana2020's GUI-side consumption after the wrapper exits. One authenticated
SharpED inference with a currently valid token, two-real-monitor screenshots at
the available DPI settings, and a real workflow-plus-concurrent-review
screenshot also remain required for the final signed release candidate.
The affected-machine Result Selection acceptance must show its OS title bar,
fixed footer, Return and Pass actions above the visible taskbar without manual
resize. That run must click Pass on Model prediction and confirm Jana receives
the selected model. Until those screenshots and the real click are recorded,
the release-blocking GUI report is verified by automation and a fresh build but
is not declared manually accepted.


## Final UX and ochlor-only verification

The final correction pass uses ochlor for real-project executable checks.
[The detailed UX and scientific report](PUBLIC_RELEASE_AUDIT_2_0_2.md) separates
implemented behavior, site counts, threshold-specific composition selection,
measured conversion costs, and pending actual Jana GUI acceptance.

Science Gothic Regular with zero tracking is confined to PHASE STUDIO and
the colored SharpED wordmark. Ordinary UI text and controls use the normal
UI font. The automatic-model checkbox is replaced by a manual indicator and
Restore automatic selection action. Powder diagnostics show actual FWHM
widths, and incoming Jana inputs are retained byte-for-byte per run.


Final source validation: all 47 direct suites pass **2,184 checks**; unittest
and pytest each pass **58 tests**. This includes the scientific golden guards,
44 displacement checks, 17 normal-EDMA default checks, 41 density-alignment
checks, 192 Jana completion checks, 72 Result Selection checks, 44 model-policy
checks, 30 final UI checks, 18 DPI clipping checks and 141 workflow-state checks.
Scientific golden outputs and schemas remain unchanged. The three real ochlor
file/numerical probes pass; actual Jana GUI acceptance remains unperformed.


Both refreshed EXEs pass their distribution boundary/version checks; the Jana
wrapper also passes native dependency and frozen import checks. Standalone and
wrapper frozen `--brand-font-check` probes resolve Science Gothic weight 400
and zero tracking from the bundled face. No commit, push, tag or publication
was performed.
