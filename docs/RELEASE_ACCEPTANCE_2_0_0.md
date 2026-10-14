# Phase Studio 2.0.0 — Release Candidate Acceptance

Status: **release candidate, READY FOR MANUAL FINAL ACCEPTANCE (Addendum B)**. The routing
decision of Addendum A1/A6 is resolved (the ordinary loop is intentional). Nothing is
pushed, tagged or published. The final `v2.0.0` tag must point at the exact
source commit the accepted binaries were built from (see §2).

"Verified" means checked here, on this machine, by the method stated.
"Not performed" means it was not checked. Those items belong to the manual
acceptance on a real Windows 11 + Jana2020 installation (§42, *Manual
acceptance checklist*).

## 1. Branch

| | |
|---|---|
| Starting branch | `release/1.0.9-split-distribution` |
| Starting commit | `a16f692` |
| History | HEAD continues directly from the released 1.0.9 source (`411e431`, merged into `main` as `v1.0.9` = `5bfdc2d`). `main` only adds two uploaded 1.0.9 PDF guides. No rebase, no history rewrite; the old branch and all tags are untouched. |
| New release branch | `release/2.0.0` (created at `a16f692`) |

## 2. Exact final commit

- **Binaries built from:** `b493bf8` ("Add release-acceptance tests: …").
- **Report commit:** this report is committed after the build. It is
  documentation-only, and `docs/` is not bundled into any executable (the
  PyInstaller datas are `phase_studio/assets` and style data only).
- **Tag:** the final tag should point at the report commit or at `b493bf8`.
  Both contain byte-identical application sources.

Commits added in this pass (2.0.0 implementation commits unchanged):
`2830664` period-based element colours · `4099a58` Result Selection
per-source labels/report · `b812bbc` MANUAL wording · `b493bf8`
acceptance tests.

## 3. Working-tree state

Clean at build time (`git status` empty) and at report time.

## 4. Version audit

**All current surfaces read 2.0.0.**
- **Source:** `phase_studio/version.py` `VERSION = "2.0.0"` is the single
  source.
- **Derived from it:**
  - `pyproject.toml` (`dynamic = ["version"]`, `attr = phase_studio.version.VERSION`);
  - the brand header / version badge, main-window title, Jana Wizard, Autosolve window;
  - the installer title "Phase Studio 2.0.0 - Jana2020 Integration" and its `--version` output (2.0.0);
  - `jana_integration` (`PHASE_STUDIO_VERSION`) and the integration marker (`phase_studio_integration.json` `"version": "2.0.0"`);
  - the PE resources (`windows_version.py` reads `version.py`);
  - the MSIX template (`{{PACKAGE_VERSION}}`) and the artifact filenames;
  - `BUILDING.md`, `RELEASE_2_0_0.md` and the tests.
- **Historical references:** `RELEASE_1_0_9.md`, `RELEASE_1_0_10.md` and the
  1.0.9 PDFs keep their 1.0.9 references and were left alone.
- **Fixed:** one stale current-behaviour sentence in `MANUAL.md`
  ("temporary Phase Studio 1.0.9 default …"), commit `b812bbc`.

## 5–8. Final artifacts (clean rebuild from `b493bf8`)

| | Standalone | Jana installer |
|---|---|---|
| File | `dist/release/PhaseStudio-2.0.0-x64.exe` | `dist/release/PhaseStudio-Jana2020-Installer-2.0.0-x64.exe` |
| Size (bytes) | 80 205 280 | 128 251 501 |
| SHA-256 | `C90FE3ABD967B5FB8EFD1B1CDD66D88C46151AAFC1143137E2EE88B6A7A1A542` | `D58F996DBC60713595F52BC07884644777B05F8A4B2D4A625F7DA918084B5981` |
| Build checks | PASS standalone: 2.0.0, ONEFILE, distribution boundary verified | PASS installer: 2.0.0, ONEFILE, distribution boundary verified (the wrapper passed as ONEDIR) |

Superseded pre-rebuild artifacts (built from `a16f692`, recorded before any
change): standalone `E9E8856573BAC7E9F67062039D61D43B9CBD4B5B047F499C44B521D9FC0195DF`
(80 202 299 B), installer `D0FE830C5B0728FA60DCBC40BDE95A9D684B21E3AAEF9B16469F2652CD999F07`
(128 252 752 B). Both were also clean on the Defender local scan.

## 9. PE metadata (both artifacts)

- **Architecture:** x64 (machine `0x8664`).
- **FileVersion / ProductVersion:** `2.0.0` / `2.0.0`.
- **ProductName:** `Phase Studio`.
- **FileDescription:** `PhaseStudio-2.0.0-x64` or
  `PhaseStudio-Jana2020-Installer-2.0.0-x64`.
- **OriginalFilename:** empty. See MINOR M1.

## 10. Authenticode

**NotSigned (both).** See FUTURE F3.

## 11. Defender versions

- **OS:** Windows 11 Education, build 26200.
- **Defender:** platform (AMProductVersion) 4.18.26080.4, engine
  1.1.26080.3, security intelligence 1.459.359.0 (updated 23 Sep 2026
  11:25).
- **Configuration:** real-time protection on, AMRunningMode Normal. No
  exclusions were added and no settings were changed.

## 12. Defender local scan

`MpCmdRun -Scan -ScanType 3 -File` on both final artifacts found **no
threats**. The pre-rebuild artifacts were also clean.

## 13. Browser-download acceptance

**Not performed as a real public browser download.** That would require
publishing an artifact.

**What the 1.0.9 incident was,** from this machine's own Defender history:
- The detection was `Trojan:Win32/Sabsik.TE.A!ml` (ThreatID 2147780193), a
  **Microsoft Defender Antivirus cloud machine-learning detection**.
- It was raised by the browser-download scan (DetectionSourceType 4) on
  `PhaseStudio-1.0.9-x64.exe`, downloaded from GitHub release-assets on
  18 Sep 2026.
- The file was quarantined before it was executed (DidThreatExecute False).
- So it was **Defender AV, not SmartScreen and not a browser reputation
  block.**

**Local proxy, recorded as a proxy only.** Copies of both final artifacts
were given a Mark-of-the-Web Zone.Identifier (ZoneId=3, GitHub HostUrl).
Real-time protection was left to see them for 45 s, then they were scanned.
Result: no detection, and the files were not removed.

This does **not** show the ML verdict a real browser download will receive,
so the antivirus problem is **not** declared solved. Manual acceptance item
MA-1 covers it.

## 14–15. Standalone startup (frozen EXE, not Python)

The exact `dist/release/PhaseStudio-2.0.0-x64.exe` was launched three times.

| Qt scale factor | Branded splash | Qt splash | Main window "Phase Studio 2.0.0" |
|---|---|---|---|
| 1.0 | 0.26 s | 3.13 s | 3.60 s |
| 1.25 | 0.14 s | 2.95 s | 3.43 s |
| 1.5 | 0.16 s | 3.02 s | 3.45 s |

In every run:
- The two processes were the ONEFILE bootloader and its child, as expected.
- There was no console window, no duplicate main window, and no startup
  exception.
- It closed gracefully with exit code 0.

Settings came from this machine's existing profile, so this was not a
first-run test.

## 16. Scaling

- **Display:** this session's display is **1268×600 physical, 96 DPI
  (100%)**, which is below the supported 1366×768 minimum.
- **What was tested:** Windows 125% and 150% scaling were not switched (no
  system settings were changed). The frozen EXE was launched with
  `QT_SCALE_FACTOR` 1.25 and 1.5 instead.
- **Offscreen GUI tests:** clipping tests at 100/125/150% ran on a real
  populated `.inflip`: the Wizard, the goal page, the Autosolve states, the
  legend and filename, and the palette renders. None were clipped.
- **Real-screen capture at 100%:** Phase Studio branding, `2.0.0`,
  Basic/Advanced, and the Input / Workflow / Output / Map feedback / Help
  tabs were correct. On this 1268-px-wide display, the **"Save map and model"
  button text is clipped**, and the 736-px window extends below a 600-px
  screen (MINOR M2). Measured offscreen, the button fits at 1366, 1600 and
  1920 widths.
- **Later captures:** they failed ("handle is invalid") once the desktop was
  no longer capturable. Real 125% and 150% Windows scaling is manual item
  MA-2.

## 17. Standalone scientific smoke

**Not performed through the frozen EXE:** driving the GUI end to end needs
interactive input. MA-3 covers it.

The scientific core is covered by the automated suite: the scientific
goldens, workflow states, SharpED API contract, tiling, map quality and
recommendation.

## 18. Fixed EDMA thresholds

**Verified in code and tests.**
- Autosolve overrides are `plimit_superflip "1.20"` and `plimit_deblur
  "2.00"` (`jana_superflip.py`).
- `AUTOSOLVE_EDMA_THRESHOLD_MODE = EDMA_THRESHOLD_MODE_MANUAL`
  (`edma_threshold.py`), and the `RunConfig.edma_threshold_mode` default is
  `"manual"`.
- The auto branch is only reachable by changing that constant. There is no
  UI control.
- Tests: `test_edma_threshold.py`, and `test_autosolve_window_routing.py`
  (effective 1.20 σ / 2.00 σ on the configured backend).

## 19. Autosolve cyclic mechanism

**Verified in code: Autosolve uses the ordinary per-cycle loop.**
- It applies the "recommended" preset (`reconstruction_mode` Superflip) and
  runs `_run_pipeline_cycles`.
- Each cycle is: Superflip → EDMA/Superflip → SharpED → EDMA/SharpED →
  validation → result → optional Map Feedback → next-cycle model.
- The adaptive extension and Option B Map Feedback continue through
  `continue_run()`, which stays in that loop.
- `_run_sharped_recycle_cycles` is a separate, unmerged function.

**Finding for your decision (DOCUMENTATION D1).** The Wizard's Advanced card
"Phase recycling with Superflip + SharpED" **also** runs the ordinary loop
(the "recommended" preset, with the code comment "Phase recycling still runs
the ordinary full pipeline"). The specialized `sharped_recycle` algorithm is
reachable only from Professional mode's *Phasing method → 1st Superflip, then
SharpED (beta)*. This predates 2.0.0 and was not changed, because of the
scientific freeze.

## 20. SharpED split / reassembly

**Verified in code and tests.**
- **Where splitting happens:** only inside `run_sharped_deblur` (app) and
  the wrapper's SharpED call, through `decide_sharped_submission`. A map
  within the limit goes **direct**, with no split.
- **What reassembly produces:** exactly one output map. The grid 9-tuple
  (indices and origin), cell and axis order are copied from the input. Voxel
  spacing is kept through the per-tile cell scaling, tiles wrap
  periodically, and any uncovered voxel raises an error.
- **What it doesn't create:** no extra cycles, candidates, recommendations
  or Map Feedback states.
- **Handoff and export:** they use explicit canonical paths, so tile files
  are never picked up.
- **Tests (`test_sharped_tiling.py`, 31 checks):** identity reassembly on a
  map that doesn't divide evenly, unchanged grid/cell/axes, the seam, full
  coverage, the direct path, and a failed tile publishing no output.
- **Gaps:** MINOR M3 (tile temp files left behind after a failed tile) and
  FUTURE F2 (blend normalization, non-zero origin, non-ZYX axis order).

## 21–23. Result Selection

**Verified in code and tests (`test_jana_completion.py`, 145 checks).**
- **Source switch:** Superflip | SharpED. The candidates are split before
  the dialog opens, and each source has its own table.
- **Per-source state:** each source's view owns its ordered rows,
  recommendation, selected cycle, recommendation reason and preview state.
- **Recommendations:** two independent calls to `recommend_best_result`,
  one per source. There is no cross-source ranking, no SharpED bonus and no
  later-cycle bonus. The tie-break prefers the earlier cycle.
- **Ranking:** the four profile definitions are exactly the specified
  lexicographic ones, with no weighted score (`test_map_quality.py`).

Fixed in this pass (`4099a58`):
- rows now read "Cycle N · Superflip" / "Cycle N · SharpED";
- `map_quality_report.txt` now records the recommended Superflip cycle and
  the recommended SharpED cycle separately, instead of one cross-source
  "Automatic recommendation".

## 24. Map Feedback fourth metric

- **Visibility:** with Map Feedback off, the tables show exactly the 3
  profile metrics. With it on, they add **"Map Feedback change (%)"**
  (label corrected in `4099a58`).
- **Definition:** the historical one, the mean |new−obs|/obs × 100 over the
  intensity-corrected reflections (`intensity_correction_avg_change_percent`).
- **Scope:** it is a cycle-level value, shown identically for both sources.
- **Diagnostic only:** a new test proves it never changes the
  recommendation, for all four profiles (`test_map_quality.py`).

## 25. Validation warnings

**Verified:** all four combinations have the specified texts.
- SharpED: always shown.
- Superflip with Map Feedback on: the Map Feedback warning.
- Superflip with Map Feedback off: no warning.
- SharpED with Map Feedback on: one combined concise warning.

There are no modal popups.

## 26–27. Period-based element colours

`app.element_color()` is the single authority (commit `2830664`).
- **Derivation:**
  - atomic number from the existing `element_atomic_number()` (gemmi
    element data);
  - period 1–7 selects a CIELCh hue family;
  - position within the period selects a deterministic hue offset plus
    alternating lightness and chroma;
  - lanthanides and actinides inherit periods 6 and 7;
  - unknown labels get one neutral grey;
  - there is no per-element colour table.
- **Who uses it:** the Professional renderer, the result-selector preview,
  every Autosolve panel and the legend.
- **Tests (`test_element_colors.py`, 46 checks):**
  - all 118 elements are valid, deterministic, and at least 2.19:1 on white;
  - none is near-black (L* at least 39.8);
  - same-period neighbours differ by ΔE76 of at least 11.4;
  - the required pairs differ by ΔE76 of at least 14: C/N 26.7, C/O 27.7,
    O/F 32.9, O/Cl 78, Si/P/S/Cl ≥ 14.1, Fe/Co/Ni ≥ 17, Cu/Zn 22.3,
    Ag/Cd 21.4, Pt/Au 37.4, Au/Hg 28.5, **Au/S 113.9**, C/Au 66.9;
  - the renderer and legend use the same authority, and no colour dictionary
    exists anywhere.
- **Visual acceptance:** the real renderer and legend were rendered for
  periods 1–3, the first transition series, period-5 transition metals,
  heavy period 6 including Au/S, and the f-block (lanthanides and actinides),
  each at 100/125/150%. The legend matched the renderer every time.
- **Trade-off (MINOR M7):** within a long period, neighbours such as
  Fe/Co/Ni are distinguishable but not dramatically different, and the
  renderer's existing depth fade lightens rear atoms further.

## 28. Long `.inflip` filename

**Verified by automated tests (`test_autosolve_window.py`).**
- short and medium names are shown in full;
- very long names are middle-elided, keeping `.inflip`, and fit their label
  without widening the window;
- the full path is in the tooltip;
- the name comes from the captured `RunConfig.jana_inflip`, or before a run
  starts, the launch path, and follows sequential jobs.

The offscreen 100/125/150% renders show no clipping.

## 29. Jana installer

**Frozen EXE:** `--version` prints `2.0.0` (exit 0). A launch showed the
branded splash at 0.18 s and the dialog "Phase Studio 2.0.0 - Jana2020
Integration" at 5.61 s, with no console. It closed gracefully with exit
code 0. Launching it changed nothing in `C:\Jana2020\SUPERFLIP`: every hash
was identical afterwards.

**Not performed:** a visual check of the controls, and install / update /
repair / remove through the frozen GUI (MA-4). No installation was run on
the real Jana2020, and this report does not modify it.

The install engine itself is covered by `test_split_distribution.py`:
- detect / install / update / repair / remove;
- the 1.0.9 upgrade;
- ownership and hash conflicts;
- transaction rollback.

**Read-only baseline of the installed `C:\Jana2020\SUPERFLIP`** (an earlier
2.0.0 wrapper build, not the final one):

| File | Size (bytes) | SHA-256 |
|---|---|---|
| `superflip.exe` | 9 473 502 | `95170DF01B0228A183A7FDCCB1DF9CDB6906197A8EE53A1956E1A8BA66E887C8` |
| `superflip_original.exe` | 2 871 758 | `2933A0C5245F4ADDC6365F26E5E4CA73A113E875A5901587DB2BDD201A80BF3E` |
| `EDMA.exe` | 807 962 | `EA648B36D048102BEE3BD56AB02069B054CEBC3EC287F4762FE17CB989DBF59B` |
| `phase_studio_integration.json` | 225 | `65F618A8E73EF0FFDD1D8E05879CFA386272E28A8C417B6F836973A182E7DEB6` |
| `_internal/` | 842 files | — |

## 30–36. Jana wrapper flows

**Not performed through real Jana2020 on the installed final wrapper** (MA-5).
These flows need Jana2020 itself and interactive Wizard input:
- 30: wrapper
- 31: Superflip only
- 32: Superflip + SharpED
- 33: Autosolve
- 34: Advanced phase recycling
- 35: Open full configuration
- 36: Pass to Jana2020

**Automated coverage** (`test_jana_completion.py`, `test_process_launch.py`,
`test_jana_wizard_hierarchy.py`, `test_autosolve_window_routing.py`,
`test_preflight_ui.py`):
- Superflip-only never opens the full GUI and passes the original `.inflip`
  once;
- the wrapper-owned visible console;
- Autosolve opens the dedicated window;
- Professional mode / Open full configuration opens the idle full GUI;
- the handoff uses the active source and selected cycle, and the canonical
  map bytes (never the preview), with exactly one call;
- the established m80/m81 protocol (`define_m80_inflip_from_model`, pinned).

## 37. Continue / resume

**Verified in code and tests (`test_workflow_states.py`, 95 checks).**
- Stage-level checkpoints are kept. After a SharpED upload, polling, download
  or post-processing failure, resume re-runs only SharpED onward. The call
  counts are Superflip 1, EDMA/Superflip 1, SharpED 2, EDMA/SharpED 1.
- Exactly one result row, no duplicated metrics.
- Map Feedback resume and continue-after-stop are covered too.
- **Gap (MINOR M4):** an OMIT-SharpED or symmetrization failure re-runs the
  main SharpED, though not Superflip.

## 38. Terminal states

**Verified (tests):**
- COMPLETE, STOPPED (graceful), CANCELLED (immediate) and FAILED stay
  distinct;
- precedence is CANCELLED > STOPPED > continuation, for both request orders;
- queued stopped/done events upgrade to CANCELLED.

**Naming nuances (MINOR M6):** the stored state for FAILED is `"ERROR"`, and
a cancelled cycle's detail reads "stopped by user".

## 39. Packaging boundaries and process safety

**Packaging, verified by `check_distribution.py` on the final build:**
- **Standalone:** ONEFILE. It contains `phase_studio.app` and no installer
  UI or Jana payload.
- **Installer:** ONEFILE. It has no scientific GUI and contains the wrapper
  ZIP and manifest, SHA-256-matched to the wrapper source.
- **Wrapper:** ONEDIR (`superflip.exe` + `_internal`).
- **Note (MINOR M5):** the read-only `jana_integration` module is bundled in
  the standalone for its marker lookup.

**Process safety:** there are no `taskkill`, `/IM`, kill-by-name or psutil
hits anywhere in `phase_studio/` or `packaging/`. The only
terminate()/kill() calls target the `Popen` handle Phase Studio itself
started.

## 40. Full automated test count

**31 test files, 1,469 checks, all passing:**
- the 2.0.0 baseline of 1,434;
- plus 29 new period-palette checks;
- plus 6 new acceptance checks: 4 for the per-source report, 1 for the
  medium filename, and 1 unit test for the diagnostic-only Map Feedback
  metric.

No test was removed.

## 41. Scientific goldens

**Unchanged and passing.** `test_scientific_core.py` passes 41 of 41, and
`test_split_distribution.py`'s scientific-function baseline comparison
against `main` passes. No golden file was modified. The palette change is
presentation-only.

## 42. Remaining release blockers

**None found** by the automated suite, the code audits, or the frozen-EXE
checks performed here.

### Manual acceptance checklist (required before tagging)

- **MA-1 Browser download.** Download both final artifacts through a normal
  browser from a public-style location, with real-time protection on, no
  exclusions, and no launch before the download completes. Record whether
  Defender AV (`!ml`), SmartScreen or the browser intervenes.
- **MA-2 Windows scaling.** At real 100/125/150%, on a display of at least
  1366×768, check both apps for clipping, including the "Save map and model"
  button.
- **MA-3 Standalone smoke run.** Through the frozen EXE: input → preflight →
  Superflip → EDMA → SharpED → metrics → Result Selection → Save map and
  model.
- **MA-4 Installer.** On a controlled Jana2020 copy: install, update, repair
  and remove. Verify `superflip.exe` + `_internal/` and
  `superflip_original.exe` are preserved and `EDMA.exe` is untouched. Update
  the installed earlier wrapper build to the final one.
- **MA-5 Jana flows.** Through Jana2020: Superflip only, Superflip + SharpED,
  Autosolve (1.20 σ / 2.00 σ, Superflip | SharpED selection), Advanced phase
  recycling, Open full configuration → Run → Pass to Jana2020 (recommended
  and manual cycles of both sources, and a STOPPED result), and m80/m81
  consumption.

### MINOR

- **M1:** PE `OriginalFilename` is empty, and `FileDescription` repeats the
  filename.
- **M2:** below the supported 1366 px width, the "Save map and model" text
  clips; below 736 px height, the main window exceeds the screen.
- **M3:** SharpED tile temp files remain after a failed or cancelled tile.
  They are never exported, but in wrapper runs they are left in the Jana job
  folder.
- **M4:** an OMIT-SharpED or symmetrization failure re-runs the main SharpED
  on resume.
- **M5:** `jana_integration` (read-only marker lookup) is bundled in the
  standalone.
- **M6:** FAILED is stored as `"ERROR"`, and the cancelled-cycle detail
  wording says "stopped by user".
- **M7:** same-period neighbours are distinguishable (ΔE ≥ 11) but not
  dramatically so, since period = colour family.

### DOCUMENTATION

- **D1 (resolved, B1):** the Advanced "Phase recycling with Superflip +
  SharpED" card runs the ordinary loop, the same as Autosolve.
  `sharped_recycle` is Professional-only. This is intentional.
- **D2:** stale comments: `PhaseStudio.spec` line 1 ("portable ONEDIR spec
  is authoritative") and `jana_superflip.py` (mentions "Install to
  Jana2020").
- **D3:** in the Professional `sharped_recycle` mode, the Superflip cycle-1
  candidate carries the SharpED/final EDMA CIF.

## Addendum A — correction pass (24 Sep 2026)

### A1. Advanced "Phase recycling with Superflip + SharpED": routing STOPPED (resolved in B1: intentional)

The request was to route the Wizard's Advanced card to the existing
specialized recycling implementation. The existing implementation was
audited first, and nothing was changed.

**What the specialized mode is.** `_run_sharped_recycle_cycles`, selected by
`RunConfig.reconstruction_mode = "sharped_recycle"`. In Professional mode it
appears as *Phasing method → "1st Superflip, then SharpED (beta)"*, hidden
unless "Show beta and experimental features" is on, and labelled "Beta
feature … does not work well with some models" / "Neither is
production-ready".

**What it does:**
- **Superflip runs at most once** (cycle 1), with **no model file** and no
  automatic previous-cycle reference.
- **Every later cycle:** SharpED deblurs the current map (through the same
  `_run_configured_sharped_stage`, so map splitting is the same SharpED
  adapter), then `compose_fobs_phicalc_map` rebuilds the next map from
  |Fobs| and φcalc obtained by FFT of the deblurred map.
- **No Map Feedback step.** No OMIT maps.
- **EDMA runs only on the final cycle's map**, and only when
  `run_edma_recycle_final` is set. The other cycles get an empty
  placeholder CIF.

**Recording, states, candidates and handoff:**
- **Recording:** one `CycleResult` per cycle (`model_source
  "sharped_recycle"`), with cycle-level checkpoints only.
- **Terminal states:** the shared completion, stop and cancel gates.
- **Result Selection:** exactly **one real Superflip candidate** (cycle 1,
  the only cycle with a Superflip quality) and one recycled SharpED
  candidate per cycle.
- **Jana handoff:** the standard `perform_jana_handoff`. The SharpED
  handoff map is the composed `cycle_NNN_fobs_phicalc.xplor`.

**Why it was stopped (item 9).** There is a genuine conflict with the
Wizard card's inputs. The card collects, and `launch_phase_studio_from_jana`
forwards, settings the specialized mode silently discards:
- the next-cycle **map source** (Superflip map vs SharpED map; page 2);
- the whole **Map Feedback page**: missing-reflection completion,
  intensity correction and powder repartitioning (page 3);
- the **initial model** (`first_cycle_modelfile`);
- the **OMIT/holdout** option;
- **per-cycle EDMA**.

Professional mode greys these out as "Ignored" for this method. Routing the
card unchanged would run a beta algorithm under a production-looking card
while ignoring the user's Map Feedback and model choices. Resolving that
requires a product decision (A6), not a routing edit. **Nothing was
changed.** The card still runs the ordinary loop.

### A2. Autosolve and the specialized mode: invocation counts

`test_workflow_states.py` now runs deterministic mocks over 3 cycles.

| | Superflip | SharpED | Recomposition | EDMA | Result Selection candidates |
|---|---|---|---|---|---|
| Ordinary loop (Autosolve, `"superflip"`) | 3 | 3 | 0 | 6 | Superflip 1–3, SharpED 1–3 |
| Specialized (`"sharped_recycle"`) | 1 | 3 | 3 | 1 (final map) | 1 Superflip, SharpED 1–3 |

The tests also check that Autosolve applies the "recommended" preset (the
ordinary loop) and never selects `sharped_recycle`. They check that
Professional's "1st Superflip, then SharpED (beta)" resolves to
`sharped_recycle`, and that the two loops are separate code paths. Autosolve
is unchanged.

### A3. Action-button clipping: fixed

- **Root cause.** The clipped control in the acceptance run was the **main
  window's** primary action row, not the Result Selection dialog. It gave
  each button an equal third of the row (`QSizePolicy.Ignored` with equal
  stretch), so "Save map and model" was cut at about 1268 logical px. The
  secondary row's hand-picked 10/7/5 stretch also clipped "Stop immediately"
  and "Clear results" below 1268 px.
- **Fix (`91f6131`).** Each action button's minimum width is its own
  text-derived size hint, and each row's stretch follows those hints. They
  are recomputed when the context label changes. The window minimum width is
  unchanged at 1017 px.
- **Test (`test_action_footer_widths.py`, 18 checks).** It covers the main
  window and the Result Selection dialog, in the standalone ("Save map and
  model") and Jana ("Pass to Jana2020") contexts, at logical widths
  1024 / 1152 / 1200 / 1268 / 1280 / 1366 / 1440 / 1920, with 1 / 2 / 4 /
  10 / 30 candidates, at QT_SCALE_FACTOR 1 / 1.25 / 1.5. No action label is
  clipped.
- **Before the fix,** the same test failed at 1024–1280. The Result
  Selection dialog footer already fit everywhere.
- **Limit.** This is Qt logical geometry, not physical Windows scaling;
  MA-2 remains.

### A4. Tests, goldens, artifacts, Defender

**Tests:** **32 test files, 1,500 checks, all passing.** That's the 1,469
baseline plus 18 width checks and 13 invocation/routing checks; none were
removed. Scientific goldens: `test_scientific_core.py` 41/41, and the
split-distribution scientific baseline passes, unchanged.

**Artifacts** (clean rebuild from `d1d8784`, working tree clean, all three
distribution checks PASS):

| | Size (bytes) | SHA-256 |
|---|---|---|
| `PhaseStudio-2.0.0-x64.exe` | 80 206 989 | `FA2324A6F556B8D67CBE32AB626D1401CE8802DF33A4E14F67306AE964ACCB0F` |
| `PhaseStudio-Jana2020-Installer-2.0.0-x64.exe` | 128 253 957 | `956F9E6586CC8B190D811B514B110CF98A69FD3F9DF009B1446CC86FEDF967A1` |

Both are x64 with FileVersion and ProductVersion 2.0.0, and both are
NotSigned. They supersede the `b493bf8` artifacts in §5–8.

**Defender** (platform 4.18.26080.4, engine 1.1.26080.3, signatures
1.459.359.0):
- the local scans of both artifacts are clean;
- the internet-marked (Zone.Identifier) copies are clean, with no
  detections and no removal.

The real browser-download test is **still not performed**. The 1.0.9
detection (`Trojan:Win32/Sabsik.TE.A!ml`, a Defender cloud-ML detection at
browser download, not SmartScreen) is **not** shown to be fixed.

### A5. Frozen-EXE smoke (rebuilt artifacts)

- **Standalone:** splash at 0.28 s, main window "Phase Studio 2.0.0" at
  3.69 s.
- **Installer:** splash at 0.14 s, "Phase Studio 2.0.0 - Jana2020
  Integration" at 5.45 s.
- **Both:** no console, graceful exit with code 0. `C:\Jana2020\SUPERFLIP`
  was verified byte-identical afterwards.
- **Screen:** the desktop was no longer capturable (it reported 640×480,
  which looks like a locked or disconnected session). So there was no
  visual check of the rebuilt EXEs, and the button fix is verified by the
  offscreen geometry test only.
- **Result Selection:** it was not opened in the frozen EXE, because that
  requires completed results. That is part of MA-3.

### A6. Decision needed to close A1

Choose one:
- **(a) Route the card to `sharped_recycle`,** and make the card honest about
  it: hide or disable the next-cycle map source, the Map Feedback page, the
  initial model and OMIT for this card, and show the existing beta warning.
  This is UI only, with no algorithm change, and exposes a
  beta/not-production-ready method as a Wizard workflow.
- **(b) Keep the card on the ordinary loop and rename it** so the label
  matches the science. The specialized method stays Professional-only
  (beta).
- **(c) Remove the card** for 2.0.0.

Until one is chosen, the Wizard label does not match the intended product
structure. The other manual acceptance items (MA-1 to MA-5) are unchanged.

**Resolved (B1):** the product decision is to keep the card on the ordinary
loop. `sharped_recycle` stays Professional-only.

## Addendum B — frozen-EXE UI/UX correction pass (24 Sep 2026)

### B1. Routing decision (EXPECTED BEHAVIOR)

- **Advanced "Phase recycling with Superflip + SharpED"** runs the ordinary
  per-cycle loop (`_run_pipeline_cycles`, reconstruction mode `superflip`),
  the same as Autosolve. Autosolve chooses the continuation automatically;
  Advanced keeps the user's settings (initial model, Map Feedback, cycles,
  OMIT, handoff map).
- **`sharped_recycle`** stays Professional-only (beta).
- **Test.** This is now pinned behaviourally
  (`test_autosolve_window_routing.py`): for both handoff-map choices and
  both Autosolve goals, the backend each launch actually starts runs
  `superflip`, never `sharped_recycle`.
- **Finding** (CONFIRMED BUG, UI only). The Advanced *"Map used for Jana2020
  handoff"* radio was dead: `wizard_map_source` was set but never read. Its
  tooltips claimed it also chose the next-cycle map. Since `9f0183b` the
  next cycle is always initialized from the SharpED map; that is deliberate,
  keeps SharpED running every cycle, and is unchanged here.
- **Fix.** The choice now sets Result Selection's starting tab, and the
  tooltips say exactly that.
- **Card copy.** The requested card text ("…user control over the model/map
  used to initialize the next cycle") would have claimed next-cycle map
  control that does not exist. It reads: "Iterate Superflip and SharpED
  over multiple cycles while keeping user control over the initial model,
  Map Feedback and the map passed to Jana2020."
- **Open wording decision.** If the next-cycle map should become
  user-selectable, that is a science change (Superflip input), outside this
  freeze.

### B2. Findings

| # | Item | Classification | Result |
|---|---|---|---|
| 1 | "Choose one of the two previous expert workflows" | CONFIRMED STALE COPY | "Choose an expert workflow" (subtitle, heading, tooltip) |
| 2 | Phase-recycling card vs Autosolve | CONFIRMED STALE COPY | new description (B1); `sharped_recycle` not mentioned |
| 3 | "Option A/B" in user-facing text | CONFIRMED STALE COPY | only in the Autosolve launch log; now the goal names. Static scan: no other occurrence |
| 4 | "…passed to Jana2020 with no further input" | CONFIRMED STALE COPY | log now describes the Result Selection handoff |
| 5–8 | "Pass to Jana2020 now" bypassed Result Selection | CONFIRMED BUG | see B3 |
| 9 | Autosolve warning wording | CONFIRMED STALE COPY | exact requested wording |
| 10 | Both Autosolve choices | EXPECTED BEHAVIOR | kept |
| 11–12 | Viewer controls active with no structure | CONFIRMED BUG | disabled until the first rendered model (including one-sided); view mode stays available |
| 13–15 | Overall progress bar half-filled / resetting | CONFIRMED BUG | see B4 |
| 16–17 | Duplicate atoms/bonds (Complete molecules, Full cell) | VISUAL SUSPICION NOT REPRODUCED | 93 real CIFs: 36,004 molecule atoms, 85,836 bonds, 107,216 full-cell atoms; 0 coincident atoms (< 0.01 Å), 0 duplicate or self bonds. No change |
| 18 | Period palette legend vs renderer | EXPECTED BEHAVIOR | unchanged; `test_element_colors.py` legend == renderer passes |
| 19–20 | "Best · Cycle N" | EXPECTED BEHAVIOR | kept; caption and structure update in one render call |
| 21 | Log top row clipped | CONFIRMED BUG | see B5 |
| 22 | "pipeline" in user-facing text | EXPECTED BEHAVIOR | 0 user-facing occurrences (static scan, now a test) |
| 23 | Input summary science | EXPECTED BEHAVIOR | unchanged |
| 24 | Button sizing after relabel | EXPECTED BEHAVIOR | Autosolve footer/toolbar added to the width test: not clipped at 1024–1920 px, Qt 100/125/150% |
| — | Goal-page warning cut at Qt 150% | CONFIRMED BUG (found by the regression suite) | see B6 |

### B3. Pass to Jana2020 (items 5–8, 27)

- **Before.** Autosolve's automatic end point and "Pass to Jana2020 now"
  both handed the recommended candidate of one source directly to
  `perform_jana_handoff`, without Result Selection.
- **Now.** Both open the same `ResultSelectionDialog`:
  - it opens on the goal's source, with the recommended completed cycle
    preselected;
  - the user may override the cycle or source;
  - only the confirmed choice is passed, through the selector's own handoff;
  - closing the selector passes nothing and re-enables the action.
- **Label.** The button is now "Pass to Jana2020". "Now" carried no
  distinction the tooltip doesn't already state.
- **Immediate stop.** Pressing it during a run still stops immediately
  (Cancel's mechanism). Only recorded `CycleResult`s are candidates, so an
  in-flight cycle, preview or temp file can never be offered. The test
  checks that every offered map is a recorded completed-cycle map.
- **Race fixed.** If the worker had already queued "stopped" or "done",
  CANCELLED still won (precedence unchanged) but the pass request was lost,
  and the window stayed on "Stopping…" with both buttons disabled. All three
  cancelled paths now honour it.

### B4. Overall progress (items 13–15)

- **Cause.** `start_run`/`continue_run` set the overall bar to
  indeterminate `(0, 0)`, which a static frame shows as half-filled. The
  following `progress_setup` reset it to 0, and so did Autosolve's 10 → 15
  extension and the Map Feedback stage.
- **Fix.** The bar is determinate 0..N from the start, with a per-run
  monotonic floor. Stage-local bars remain busy for unknown-duration work
  (EXPECTED).
- **Test.** `test_overall_progress.py` (18 checks).

### B5. Execution Log top row (item 21)

- **Cause.** The log's height was fitted before the window was shown, using
  an estimated frame height. It was 6 px too tall, so the top row was cut by
  about 9 px at Qt 100/125/150%, in the production path.
- **Why the existing test missed it.** It called the fit by hand after
  showing the window.
- **Fix.** The window refits itself once shown.
- **Test.** A production-path check was added.

### B6. Wizard goal page at Qt 150%

- **Cause.** The longer warning needs an extra line when the Wizard body
  scrolls on a short screen, because the scrollbar narrows the page. The
  stack was pinned from the scrollbar-free width (102 < 119 px).
- **Fix.** The page is re-measured at its real width after each fit and
  whenever the width changes; the pin only grows.
- **Test update.** `test_wizard_geometry.py`'s three pin checks now compare
  against that real width. They are the same checks; none was removed.

### B7. Commits (from `cb93b16`)

| Commit | Change |
|---|---|
| `a28b3f6` | Overall progress determinate and non-regressing |
| `dde25b1` | Autosolve end point through the shared Result Selection |
| `7347bdf` | Data-aware viewer actions; log refits once shown |
| `cdc4370` | Wizard copy; handoff-map choice sets the Result Selection tab |
| `3ae9411` | Wizard page pinned at its real width |

### B8. Tests and goldens

- **Tests.** **34 test files, 1,593 checks, all passing**: the 1,500
  baseline plus 93 new. Two new files: `test_ui_copy.py` (25) and
  `test_overall_progress.py` (18). Checks pinning the old direct handoff and
  labels were rewritten to the new contract; none were dropped.
- **Goldens.** `test_scientific_core.py` 41/41;
  `test_split_distribution.py` 20/20, including the scientific-function
  baseline against `main`. No golden changed.
- **Science.** Unchanged:
  - Superflip inputs;
  - SharpED API use;
  - EDMA thresholds (1.20 σ / 2.00 σ fixed; Auto-EDMA experimental and
    off);
  - Map Feedback, HKL handling, normalization, OMIT, R_free;
  - metrics, rankings, map splitting;
  - Jana handoff content.
- **Environment note.** With `QT_QPA_FONTDIR=C:\Windows\Fonts` set
  globally, one pre-existing check (`test_autosolve_window.py`, "very long
  name is elided") also fails on unmodified `cb93b16`. The baseline and
  this run use the default offscreen fonts. The width and clipping tests set
  the font dir in their own child processes.

### B9. Artifacts (clean rebuild from `3ae9411`, into `dist\rc3\release`)

`dist\release` could not be cleaned: an installer instance started from
Explorer at 10:00 was still open and holding the old file. It was left
running. All three distribution checks PASS.

| | Size (bytes) | SHA-256 |
|---|---|---|
| `PhaseStudio-2.0.0-x64.exe` | 80 344 599 | `6C9DE158E95B5C4673C81E9EDD81B9F9F666711D5DFF5551E89DB2BB5CB214BC` |
| `PhaseStudio-Jana2020-Installer-2.0.0-x64.exe` | 128 534 735 | `550ED7AB2C999468C9E4A0F21160A8CA010CB1A7F53A42CC05373347983076A7` |

- **Both:** x64 (0x8664), FileVersion/ProductVersion 2.0.0, NotSigned.
- **Supersede** the A4 artifacts.

**Defender** (platform 4.18.26080.4, engine 1.1.26080.3, signatures
1.459.366.0, real-time protection on, no exclusions):
- local scans clean;
- internet-marked (ZoneId=3) copies clean.

The real browser-download test is **still not performed**. The 1.0.9
`Trojan:Win32/Sabsik.TE.A!ml` detection is **not** shown to be fixed.

### B10. Frozen-EXE smoke

Display 1920×1080, Windows 125%.

- **Standalone:** splash at 0.25 s, main window "Phase Studio 2.0.0" at
  3.67 s.
- **Installer:** splash at 0.21 s, "Phase Studio 2.0.0 - Jana2020
  Integration" at 5.76 s.
- **Both:** no console, graceful exit with code 0.
- **Jana folder:** `C:\Jana2020\SUPERFLIP\superflip.exe` is
  byte-identical, and every file keeps its size and time. The folder's own
  modification time changes on installer launch because of the existing
  write probe (`check_writable`: create and delete a temp file).
- **Screenshots:** the desktop was not capturable ("handle is invalid"), so
  there was no visual check of the rebuilt EXEs. The layout fixes are
  verified by Qt offscreen geometry at scale 1/1.25/1.5 only; that is not
  physical Windows scaling (MA-2).
- **Result Selection:** the Autosolve handoff through Result Selection was
  not exercised in the frozen EXE (it needs a Jana run; MA-5).

### B11. Release status

No automated blocker remains. Still open:
- the manual items MA-1 to MA-5;
- in MA-5, the Autosolve → Result Selection → Pass to Jana2020 path and the
  Advanced handoff-map tab;
- MA-2 at real Windows scaling.

**READY FOR MANUAL FINAL ACCEPTANCE.**

## 43. Future work

- **F1: Auto-EDMA validation.** Additional solved datasets, ideally one
  X-ray and one 3D ED, each with:
  - real measured reflections and a reliable reference;
  - threshold-dependent EDMA results;
  - SharpED output distinct from Superflip;
  - enough quality variation for F0.5 to separate thresholds.

  Any future criterion must be radiation-aware. The engine stays off by
  default.
- **F2: Tiling tests.** Add tests for blend normalization of independently
  normalized tiles, a non-zero map origin, and non-ZYX axis order.
- **F3: Authenticode.** Code-signing the release binaries would reduce the
  cloud-ML and SmartScreen risk seen with 1.0.9.
- **F4: Real public-download Defender test.** Run it against a draft or
  pre-release once publishing is authorized.
