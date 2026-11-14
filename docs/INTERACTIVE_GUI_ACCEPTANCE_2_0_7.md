# Interactive GUI acceptance — Phase Studio 2.0.7

The reproduced Jana launcher failure is corrected. **Overall interactive/visual acceptance remains open**, because complete native-pointer acceptance and normal-desktop frozen visual review were not established. Passing Qt fixtures is not physical-monitor acceptance.

## Source and correction

Application and test source: `6717c5ddf5b33ec849b78fb8b5b9a8711d2ea240`, based on `b42bdd9d41cd454dccf085de8e551449d3f5883b` on `development/2.0.7`. This report is a subsequent documentation-only change. Unrelated test changes and workshop files were preserved.

**P0:** `superflip.spec` executes `jana_superflip.py` as a script, without a package namespace. Thirteen relative imports in the Wizard failed in that context. The first failure interrupted input-summary formatting; View data and Analyze data then failed before their error handling could present a dialog. Earlier package-import fixtures missed this distinction.

The correction uses absolute `phase_studio.*` imports in that launcher. Scientific algorithms, data interpretation, legal resources, the main Run Overview and production release machinery are unchanged.

Two focused tests execute the launcher with an empty package namespace and use a real modal event loop, QTest mouse events, ownership assertions, table selection, all seven analysis tabs, close and reopen. Both fail on the preserved original source and pass after correction. Eight focused/adjacent checks passed.

## Regression and builds

- Complete suite run once on the clean source checkout: **1,026 passed, two failed, four skipped, 37 subtests passed**, in 1,941.76 seconds. The original log and JUnit remain preserved.
- The failures were native Windows environment tests: Credential Manager persistence and ancestor-directory file guards. Each passed separately outside the restricted sandbox, without code changes. Combined coverage: **1,028 passed, four skipped, 37 subtests passed**. This is not a claim that the original restricted run was entirely green.
- Skips: one opt-in real-project test, two ONEFILE runtime cases and one ONEDIR-only case.
- Six relevant executable authorities passed: scientific core, Jana completion, workflow states, result selection, fullscreen viewer and execution logging. The prior independent numerical audit remains preserved; no new broad numerical campaign was started.
- Both unsigned development profiles built once from the source above in 188.38 seconds. ONEDIR extraction verified 407 files, with zero blocking runtime problems or conflicting duplicate DLL names.
- Each executable verifies **92 source-matched package modules and 66 byte-identical legal/font resources**. Both new executables passed **272 recorded Qt interaction checks** on the Windows platform. These counts include reopen/state checks, not 272 different buttons.

Local artifacts:

| Profile | Artifact under repository root | SHA-256 |
|---|---|---|
| Jana ONEDIR | `build/ig207/dist/PhaseStudio-Jana2020-2.0.7/Phase_studio.exe` | `dfd2496cd781982de50d7d5c284848d29039eef5cca77f5b30eb8ed478fb7170` |
| Complete Jana ZIP | `build/ig207/dist/release/PhaseStudio-Jana2020-2.0.7.zip` | `32cf6c3b701764d26a5c1f3434d9e0e44d596f012a0c5c230ae82c2e6f0f53a2` |
| Standalone ONEFILE | `build/ig207/dist/release/PhaseStudio-2.0.7-x64.exe` | `0c9fbfd52df2f086fb00229425ea9ffa23a631a33f949d852bf3d3c0b37a0330` |

Keep the Jana executable with its entire `_internal` directory. No installed Jana executable was replaced. No merge, tag, production signing or publication was performed.

## Interaction coverage and boundaries

The consolidated source evidence contains **285 distinct named control/state entries: 279 PASS, four NOT APPLICABLE and two BLOCKED**. These are the specifically executed entries in the appendix, not a claim that every possible dynamically created application control has been exhausted. Repeated captures and reopen checks are not counted again in that total.

Core source/frozen checks cover Wizard diagnostics and navigation, input/configuration fields, About cards and independent legal viewers, authentication disclosures, update notices, result cycles/families, scrolling, fullscreen restoration and execution logs. Source supplements cover analysis disclosures/provenance/export menus, citation search/BibTeX, camera submenus, validation errors, Map Feedback history exports, asynchronous model discovery and the final Wizard Run action.

Normal clicks use QTest and the real Qt event loop; asynchronous tests wait for explicit completion. Test settings, credentials, data copies and export destinations are isolated. Network catalogues, browser/file-dialog boundaries and native/authentication preflight are explicitly substituted where noted. The EDMA threshold and stop controls use isolated backend/running-state fixtures; they do not prove interruption of a real native scientific process. The result action verifies acceptance of the selected candidate at the caller boundary, not a new scientific handoff run.

The data fixture retained all 631 records and its original bytes. View/Analyze retain powder I/FWHM interpretation, unavailable measurement sigma, cell/space-group context and source wavelength. The original user project was never rewritten. No paid inference was submitted.

## Visual review and remaining acceptance

Actual Qt captures were inspected for the four About sections, original legal/credit/citation viewers, input table, analysis, Wizard pages, Help/settings, authentication, update notice, result selection, fullscreen, recommendation, execution logs, validation errors and recorded Map Feedback. The compact cards, original branding and independently scrollable legal content are preserved.

Controlled Qt checks pass at **100%, 125%, 150% and 200%** for both About profile presentations, stable card-switch geometry, Wizard diagnostics, modal ownership, table interaction and closing. At 200%, View/Analyze adapt to 910 × 502 logical pixels. These are controlled screen-geometry checks, not physical or mixed-monitor evidence.

| Remaining item | Status | Evidence / reason |
|---|---|---|
| Complete native foreground View/Analyze close/reopen sequence | BLOCKED | View data was visibly opened through the real packaged script entry. The initial automation driver incorrectly searched only root windows, then confused a same-named button with a window and selected a title-bar Close control. Corrected discovery was prepared, but subsequent desktop access failed. No complete native PASS is asserted. |
| Desktop availability after user unlock confirmation | BLOCKED | The automation process is user Session 2, `WinSta0/Default`; `OpenInputDesktop` still returns access denied (Win32 error 5). The isolated test application was safely closed, preserving geometry preferences. This is an automation-access limitation, not an assumption that the user failed to unlock it. |
| Normal desktop frozen visual acceptance | UNVERIFIED | During packaged captures the desktop changed to an exceptionally small viewport. Several main/result screenshots are clipped at approximately 600 × 350 pixels. Those captures are preserved and explicitly rejected as normal-desktop visual acceptance evidence. Retake on a stable desktop and assess any remaining layout defect before sign-off. |
| Physical/mixed-monitor DPI | UNVERIFIED | No physical scaling configuration or monitor transition was performed. |
| Native invocation by Jana2020 itself | UNVERIFIED | The real packaged launcher was started directly with an isolated input copy; the Jana application did not initiate this test. |
| Every remaining dynamic/conditional main-window control | UNVERIFIED | The raw widget inventory deliberately retains unverified entries. The appendix proves its named control/state outcomes only; it does not silently upgrade other controls to PASS. |
| Live authentication / production installation | BLOCKED | Requires user authentication or a separately authorized production release; no production operation was attempted. |

These limitations prevent a claim of complete GUI acceptance. The build is available for development testing with the confirmed launcher correction.

## Preserved evidence and before/after review

All screenshots and private paths remain in ignored local build evidence; none are committed to the public repository. Original evidence was not changed or deleted.

Evidence root: `build/interactive-gui207/`. Final tests/builds: `final-6717c5d/`.

- Before: `baseline-script-entry/`, `before-script-tests.log`, and `native-installed/`.
- Corrected script namespace: `corrected-script-entry/`; source visual review: `source-windows/`.
- Broader final source interactions: `controls-t/`; supplemental outcomes: `supplement-a/`, `remaining-c/`, `remaining-results-a/`, `remaining-feedback-b/`, `remaining-models-a/`.
- New frozen packages: `final-6717c5d/frozen-jana/` and `final-6717c5d/frozen-standalone/`.
- Scaling: `final-6717c5d/dpi-v2-{1.0,1.25,1.5,2.0}/`.
- Native attempts and their driver/environment failures: `final-6717c5d/native-normal-entry*/`, `desktop-access.txt`, `native-cleanup.txt`.
- Local before/after gallery: `final-6717c5d/REVIEW.html`; complete machine-readable matrix: `final-6717c5d/control-matrix.json`.

## Changed files

- `phase_studio/jana_superflip.py`: script-safe absolute imports.
- `phase_studio/interactive_gui_acceptance.py`: explicitly opted-in offline mouse/keyboard acceptance path.
- `phase_studio/packaging_acceptance.py`: opt-in dispatch for that path.
- `tests/jana_script_entry_probe_207.py` and `tests/test_jana_script_entry_207.py`: focused script-namespace regression.
- This report: results and explicit pending acceptance.

## Executed control/state matrix

PASS applies only to the stated action and safe boundary, not to an unexecuted external service or scientific run. The detailed outcome descriptions are in the local JSON matrix.

| Area | Control or state | Result |
|---|---|---|
| About | Authors | PASS |
| About | Browse licenses | PASS |
| About | Citation | PASS |
| About | Close | PASS |
| About | Contacts and credits | PASS |
| About | Copy citation | PASS |
| About | GitHub repository | PASS |
| About | License | PASS |
| About | Official releases | PASS |
| About | Read full license | PASS |
| About | Third party | PASS |
| About | View citations | PASS |
| Analyze data | Tab: &Availability && limitations | PASS |
| Analyze data | Tab: &Input | PASS |
| Analyze data | Tab: &Resolution | PASS |
| Analyze data | Tab: &Values | PASS |
| Analyze data | Tab: Absences && &duplicates | PASS |
| Analyze data | Tab: Advanced diagnostics | PASS |
| Analyze data | Tab: Counts && &symmetry | PASS |
| Analyze data | Tab: Intensity && amplitude | PASS |
| Analyze data | Tab: Overview | PASS |
| Analyze data | Tab: Peak &overlap | PASS |
| Analyze data | Tab: Powder && peak overlap | PASS |
| Analyze data | Tab: Resolution | PASS |
| Analyze data | Tab: Signal && uncertainty | PASS |
| Analyze data | Tab: Symmetry && coverage | PASS |
| Analyze data | Table selection | PASS |
| Authentication | Access-key instructions | PASS |
| Authentication | Back | PASS |
| Authentication | Connect empty key | PASS |
| Authentication | Get an access key | PASS |
| Authentication | Live sign-in and permission verification | BLOCKED |
| Authentication | Replace access key | PASS |
| Authentication | Saving options | PASS |
| Authentication | Use an access key instead | PASS |
| Camera preferences | Comparison frame | PASS |
| Camera preferences | Element colors | PASS |
| Camera preferences | Rotation sensitivity | PASS |
| Citations | CITATION.cff | PASS |
| Citations | Check component / Copy checked | PASS |
| Citations | Copy citation | PASS |
| Citations | Export BibTeX | PASS |
| Citations | Open source | PASS |
| Citations | Search | PASS |
| Detailed analysis | Copy full path | PASS |
| Detailed analysis | Copy full-precision shell rows | PASS |
| Detailed analysis | Definitions, provenance and external statistics | PASS |
| Detailed analysis | Export analysis data CSV | PASS |
| Detailed analysis | Export diagnostics JSON | PASS |
| Detailed analysis | Full provenance… | PASS |
| Detailed analysis | Import external CC1/2 statistics | PASS |
| Detailed analysis | Resolution definitions and cutoff method | PASS |
| Detailed analysis | Scrollable content 6 | PASS |
| Detailed analysis | Show diagnostic categories | PASS |
| Detailed analysis | Tab: &Availability && limitations | PASS |
| Detailed analysis | Tab: &Input | PASS |
| Detailed analysis | Tab: &Resolution | PASS |
| Detailed analysis | Tab: &Values | PASS |
| Detailed analysis | Tab: Absences && &duplicates | PASS |
| Detailed analysis | Tab: Advanced diagnostics | PASS |
| Detailed analysis | Tab: Counts && &symmetry | PASS |
| Detailed analysis | Tab: Intensity && amplitude | PASS |
| Detailed analysis | Tab: Overview | PASS |
| Detailed analysis | Tab: Peak &overlap | PASS |
| Detailed analysis | Tab: Powder && peak overlap | PASS |
| Detailed analysis | Tab: Resolution | PASS |
| Detailed analysis | Tab: Signal && uncertainty | PASS |
| Detailed analysis | Tab: Symmetry && coverage | PASS |
| Detailed analysis | Technical diagnostic categories | PASS |
| EDMA controls | Add/remove atoms | PASS |
| Error recovery | Copy details | PASS |
| Error recovery | Show details | PASS |
| Execution log | Copy | PASS |
| Execution log | Execution log category | PASS |
| Execution log | Export sanitized | PASS |
| Execution log | Filter execution component | PASS |
| Execution log | QCheckBox | PASS |
| Execution log | Search execution log | PASS |
| Fullscreen | Toggle / F11 / Escape | PASS |
| Legal | Copy original | PASS |
| Legal | Find next | PASS |
| Legal | Open original | PASS |
| Legal | Original formatting | PASS |
| Main | Maximize/restore | PASS |
| Main EDMA | Distance tolerance in Angstrom for reducing EDMA maxima to one representative per full space-group orbit before writing the CIF asymmetri… | PASS |
| Main EDMA | EDMA centerofcharge keyword. | PASS |
| Main EDMA | EDMA chlimit keyword. | PASS |
| Main EDMA | EDMA chlimlist keyword. | PASS |
| Main EDMA | EDMA fullcell keyword. | PASS |
| Main EDMA | EDMA maxima keyword. | PASS |
| Main EDMA | EDMA numberofatoms keyword for structure export. | PASS |
| Main EDMA | Peak threshold as a multiplier of the XPLOR map sigma. | PASS |
| Main Help | Open the relevant section in Help (F1). | PASS |
| Main Help | Contents 37 | PASS |
| Main Help | Contents 38 | PASS |
| Main Help | Contents 39 | PASS |
| Main Help | Contents 40 | PASS |
| Main Help | Contents 41 | PASS |
| Main Help | Contents 42 | PASS |
| Main Help | Contents 46 | PASS |
| Main Help | Contents 55 | PASS |
| Main Help | Contents 56 | PASS |
| Main Help | Contents 57 | PASS |
| Main Help | Contents 59 | PASS |
| Main Help | Contents 60 | PASS |
| Main Help | Help topic | PASS |
| Main Help | QCheckBox | PASS |
| Main Input | Choose whether reflections come from Jana2020 .inflip, selected overrides, or an external HKL file. | PASS |
| Main Input | Composition in the existing Superflip syntax, for example Ag196 S108 O40 B1000. | PASS |
| Main Input | International Tables space-group number from 1 to 230. | PASS |
| Main Input | Jana2020 Superflip input file. In Jana modes its fbegin/endf reflection block is the default HKL source, and its cell/space-group/composi… | PASS |
| Main Input | Manual unit-cell angle alpha in degrees. | PASS |
| Main Input | Manual unit-cell angle beta in degrees. | PASS |
| Main Input | Manual unit-cell angle gamma in degrees. | PASS |
| Main Input | Manual unit-cell length a in angstrom. | PASS |
| Main Input | Manual unit-cell length b in angstrom. | PASS |
| Main Input | Manual unit-cell length c in angstrom. | PASS |
| Main Input | Optional external density or structure model for cycle 1. | PASS |
| Main Input | Optional external reference. | PASS |
| Main Input | Recognized Hermann-Mauguin space-group symbol. | PASS |
| Main Input | Selects the authoritative source for unit-cell, space-group and composition metadata, independently of the reflection-data source -- for … | PASS |
| Main Map Feedback | Open recorded run… | PASS |
| Main Map feedback | Enables map-based intensity correction. | PASS |
| Main Map feedback | Enables missing-reflection completion. | PASS |
| Main Map feedback | Enables powder overlap repartitioning: each cycle, redistribute the combined observed intensity of overlapping-reflection groups (hkl I/F… | PASS |
| Main Map feedback | Measured radiation wavelength in Å. Zero resolves matching .m90, then .inflip, then reference CIF. Required by native Superflip FWHM inpu… | PASS |
| Main Output | CIF is always produced internally (used for metrics and next-cycle modelfiles). | PASS |
| Main Output | Output directory for generated HKL files, Superflip inputs, maps, EDMA results, logs and metrics.Path: C:\Users\honzi\Documents\GitHub\Ph… | PASS |
| Main Output | XPLOR is always produced internally (EDMA and SharpED require it). | PASS |
| Main Setup | Absolute path to the Jana2020 EDMA executable used for peak extraction and structure export from XPLOR density maps.Path: C:\Jana2020\SUP… | PASS |
| Main Setup | Absolute path to the active Jana2020 scientific Superflip executable.Path: C:\Jana2020\SUPERFLIP\superflip.exe | PASS |
| Main Setup | SharpED inference server base URL. | PASS |
| Main Setup | User API token sent as Authorization: Bearer during upload/status/download. | PASS |
| Main Setup | When off (default), beta and experimental Phasing methods and the settings that only apply to them are hidden entirely from the Basic tab… | PASS |
| Main SharpED | Chemical elements sent to the SharpED server. | PASS |
| Main SharpED | HTTP timeout in seconds for SharpED model query, upload, status and download requests. | PASS |
| Main SharpED | Maximum XPLOR map size uploaded to the SharpED server in megabytes. | PASS |
| Main SharpED | Maximum number of status polls. | PASS |
| Main SharpED | Requested output sampling/resolution of the SharpED density map. | PASS |
| Main SharpED | Reversible signed power transform sign(x)·/x/^a applied to map values before SharpED and inverted automatically on the returned SharpED m… | PASS |
| Main SharpED | Seconds between status polling requests. | PASS |
| Main Superflip | Adds 'polish yes' to the Superflip input, enabling Superflip's final polishing/refinement stage when supported by the executable. | PASS |
| Main Superflip | First argument of bestdensities: how many best density maps Superflip keeps. | PASS |
| Main Superflip | Maximum number of Superflip iterations per run. | PASS |
| Main Superflip | Minimum I/sigma(I) for intensity input or F/sigma(F) for amplitude input. | PASS |
| Main Superflip | Optional Superflip missing-data keyword line, for example bounds for missing reflections. | PASS |
| Main Superflip | Optional Superflip reflection normalization keyword. | PASS |
| Main Superflip | Optional resolution cutoff in Angstrom. | PASS |
| Main Superflip | Overall isotropic B factor used to sharpen the map. | PASS |
| Main Superflip | Random seed passed to Superflip. | PASS |
| Main Superflip | Second argument of bestdensities: rvalue, peakiness, symmetry or reference. | PASS |
| Main Superflip | Superflip delta keyword. | PASS |
| Main Superflip | Superflip derivesymmetry keyword. | PASS |
| Main Superflip | Superflip electrons keyword. | PASS |
| Main Superflip | Superflip perform keyword. Common values: CF, lde, general, fourier, symmetry; AAR is kept for executables that support it. | PASS |
| Main Superflip | Superflip repeatmode parameter controlling repeated independent attempts and convergence sampling. | PASS |
| Main Superflip | Superflip searchsymmetry keyword: no, shift or average. | PASS |
| Main Superflip | Superflip voxel grid. | PASS |
| Main Superflip | Superflip weakratio keyword. | PASS |
| Main Workflow | Applies a bundle of starting values for a common crystallographic workflow. | PASS |
| Main Workflow | Authoritative source for cycle 2 and later. none forces the run to one cycle; superflip_xplor cycles without SharpED deblurring; deblurre… | PASS |
| Main Workflow | Freeze a symmetry/Friedel-orbit-safe 5% holdout before the workflow and exclude it from every work-data and feedback step. Enables cross-… | PASS |
| Main Workflow | Number of iterative Superflip → EDMA → SharpED → EDMA cycles to run. | PASS |
| Main Workflow | Optional atom labels to remove from CIF modelfiles before the next Superflip cycle. | PASS |
| Main Workflow | Run EDMA peak search on the SharpED XPLOR map. Disable this when you only want map export or Superflip EDMA results. | PASS |
| Main Workflow | Run EDMA peak search on the Superflip XPLOR map and write CIF, XYZ and PDB structure exports. | PASS |
| Main Workflow | Run SharpED server deblurring on the Superflip XPLOR map. If disabled, the SharpED map is a copy of the Superflip map. | PASS |
| Main Workflow | SharpED server model name. | NOT APPLICABLE |
| Main Workflow | Superflip runs the standard charge-flipping cycle every cycle (unchanged default). | NOT APPLICABLE |
| Main authentication | Account access… | PASS |
| Main configuration | Load settings from .inflip | PASS |
| Main configuration | Tab: Advanced | PASS |
| Main configuration | Tab: Basic | PASS |
| Main configuration | Tab: EDMA | PASS |
| Main configuration | Tab: Help | PASS |
| Main configuration | Tab: Input | PASS |
| Main configuration | Tab: Map feedback | PASS |
| Main configuration | Tab: Output | PASS |
| Main configuration | Tab: Setup | PASS |
| Main configuration | Tab: SharpED | PASS |
| Main configuration | Tab: Superflip | PASS |
| Main configuration | Tab: Workflow | PASS |
| Main files | Browse for EDMA executable | PASS |
| Main files | Browse for External HKL file | NOT APPLICABLE |
| Main files | Browse for Initial model (cycle 1) | PASS |
| Main files | Browse for Jana2020 .inflip file | PASS |
| Main files | Browse for Reference model | PASS |
| Main files | Browse for Superflip executable | PASS |
| Main files | Browse for Working directory | PASS |
| Main input | Analyze data | PASS |
| Main input | View data | PASS |
| Main links | Open the Phase Studio source repository | PASS |
| Main links | Open the SharpED project and API-token page | PASS |
| Main links | Open the department website | PASS |
| Main links | Open the official EDMA website | PASS |
| Main links | Open the official Superflip website | PASS |
| Main log | Expand/collapse | PASS |
| Main log | Export sanitized diagnostics | PASS |
| Main log | Open log | PASS |
| Main menu | About Phase Studio | PASS |
| Main models | Refresh models | PASS |
| Main navigation | Connection settings → | PASS |
| Main navigation | Inference settings → | PASS |
| Main results | Clear results | PASS |
| Main validation | Run phasing | PASS |
| Main viewer | Complete molecules | PASS |
| Main viewer | Full cell | PASS |
| Main viewer | Full range | PASS |
| Map Feedback | Open recorded run | PASS |
| Map Feedback diagnostics | Tab: Actual written inputs | PASS |
| Map Feedback diagnostics | Tab: Change by source cycle | PASS |
| Map Feedback diagnostics | Tab: Cumulative input vs original | PASS |
| Map Feedback diagnostics | Tab: Operation summaries | PASS |
| Map Feedback diagnostics | Tab: Reflection changes | PASS |
| Menu | About Phase Studio | PASS |
| Menu | Export analysis data CSV | PASS |
| Menu | Export diagnostics JSON | PASS |
| Menu | Invert mouse rotation | PASS |
| Menu | Notify me when new versions are available | PASS |
| Navigation | Tab: Advanced | PASS |
| Navigation | Tab: Basic | PASS |
| Navigation | Tab: EDMA | PASS |
| Navigation | Tab: Help | PASS |
| Navigation | Tab: Input | PASS |
| Navigation | Tab: Map feedback | PASS |
| Navigation | Tab: Output | PASS |
| Navigation | Tab: Setup | PASS |
| Navigation | Tab: SharpED | PASS |
| Navigation | Tab: Superflip | PASS |
| Navigation | Tab: Workflow | PASS |
| Recommendation | Technical details / Copy full precision | PASS |
| Recorded Map Feedback | Export cycle CSV | PASS |
| Recorded Map Feedback | Export cycle JSON | PASS |
| Recorded Map Feedback | QComboBox | PASS |
| Recorded Map Feedback | Reopen cancellation | PASS |
| Recorded Map Feedback | Unavailable cumulative/written export | PASS |
| Reflection preferences | Reset to zero | PASS |
| Results | Auto rotate | PASS |
| Results | Details | PASS |
| Results | Fit | PASS |
| Results | Fullscreen | PASS |
| Results | Fullscreen restoration | PASS |
| Results | Return to Phase Studio | PASS |
| Results | Save map and model selection | PASS |
| Results | Scrollable content 0 | PASS |
| Results | View execution log | PASS |
| Results | Why this cycle? | PASS |
| Results | _cell_button | PASS |
| Results | _latest_cycle_button | PASS |
| Results | _molecule_button | PASS |
| Results | _next_cycle_button | PASS |
| Results | _previous_cycle_button | PASS |
| Results | _sharped_btn | PASS |
| Results | _superflip_btn | PASS |
| Run controls | Idle stop controls | PASS |
| Run controls | Stop after cycle | PASS |
| Run controls | Stop immediately | PASS |
| Third-party documents | Choose dependency license | PASS |
| Third-party documents | Copy original | PASS |
| Third-party documents | Find in document | PASS |
| Updates | Check for updates | PASS |
| Updates | Close development-version notice | PASS |
| Updates | Production installation | BLOCKED |
| View data | Table selection | PASS |
| Wizard | Advanced input options | PASS |
| Wizard | Analyze data | PASS |
| Wizard | Back | PASS |
| Wizard | Next | PASS |
| Wizard | Run phasing | PASS |
| Wizard | Superflip + SharpED | PASS |
| Wizard | View data | PASS |
| Wizard | autosolve | PASS |
| Wizard | navigation | PASS |
| Wizard | professional | PASS |
| Wizard | superflip | PASS |
| Wizard Map Feedback | QCheckBox | PASS |
| Wizard advanced SharpED | Private access key for your Jana2020 account. It is masked and shared with Phase Studio for this session. Remember access saves it in Win… | PASS |
| Wizard advanced input | Model or density map to seed the first Superflip cycle. If supplied, cycle 1 is model-seeded: repeatmode is forced to 1 and randomseed is… | PASS |
| Wizard advanced input | Reference CIF structure or XPLOR density map, used together with the incoming Jana2020 .inflip without replacing its embedded reflections… | PASS |
| Wizard authentication | Manage account… | PASS |
| Wizard models | Advanced SharpED settings | PASS |
| Wizard models | Manual selection / Restore automatic | PASS |
| Wizard models | Refresh | PASS |
| Wizard processing | Number of ordinary Superflip + SharpED workflow cycles. | PASS |
| Wizard processing | SharpED inference model. Select an exact model returned by the live server catalog. Automatic selection follows the Phase Studio cycle po… | NOT APPLICABLE |
