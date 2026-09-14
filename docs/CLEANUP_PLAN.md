# Phase Studio 1.0.9 cleanup plan

Status: planning only. Measurements are from commit `8cc87b9` on
`release/1.0.9-split-distribution`. No production change is part of this plan.

## Measurement method and compatibility boundary

"LOC" below means nonblank, non-comment physical source lines. Python
docstrings and multiline strings count because they still consume maintenance
and model context. Physical line counts are also shown where useful. Generated
`build/`, `dist/`, caches, binaries, icons, and generated Store assets are
excluded. Build source includes Python, PowerShell, spec files, the MSIX
manifest/example identity, and `pyproject.toml`.

All cleanup is constrained by a same-input, same-settings, same-result rule.
It must preserve Superflip input and repeat/random-seed behavior, EDMA commands
and thresholds, SharpED request/model behavior, map transforms, HKL parsing and
merging, completeness and resolution values, phase recycling, Map Feedback,
OMIT/R_free, ranking, generated maps/models, and Jana2020 handoff. It must also
preserve every current workflow, visible string, layout, default, object name,
enabled state, high-DPI behavior, process-console policy, cancellation state,
QSettings key, output name/column, marker format, entry point, and distribution
profile unless a separately documented migration is approved.

## 1. Current size

| Surface | Files | Physical lines | Production LOC |
|---|---:|---:|---:|
| Runtime package (`phase_studio`) | 17 | 22,826 | 19,959 |
| Build/package/config source | 20 | 2,165 | 1,673 |
| **Production total** | **37** | **24,991** | **21,632** |
| Regression scripts | 18 | 4,763 | 3,827 |
| Current documents in `docs/` | 5 | 1,039 | not production LOC |

The 14,649-line `app.py` contains 13,082 LOC: 60.5% of all production
LOC and 65.5% of runtime LOC. That concentration, rather than the total number
of files, is the main context problem.

### Runtime inventory

Imports list the important internal or heavyweight dependencies rather than
every standard-library name.

| File | LOC | Responsibility | Important dependencies | Main callers | Cleanup potential |
|---|---:|---|---|---|---|
| `phase_studio/app.py` | 13,082 | Scientific parsing/calculation, full Qt GUI, run orchestration, plots, result selection, Jana handoff | NumPy, gemmi, PySide6, Matplotlib; nearly every shared module | `standalone`, Jana full-configuration launch, tests | **Very high:** 700+ proven dead LOC, real duplicate parsers/plumbing, and several context boundaries |
| `phase_studio/jana_superflip.py` | 2,345 | Lightweight Jana wrapper, Wizard, wrapper-only execution, handoff into full GUI | SharpED client, process/requirements/UI helpers; lazy import of `app` | `superflip.spec`, wrapper executable, tests | **Medium:** repeated preflight/model/inflip plumbing; preserve lightweight startup and console behavior |
| `phase_studio/ui_style.py` | 1,383 | Exact Qt stylesheet, widget polish, wheel safety | PySide6 | Full GUI, Wizard, installer | Low raw savings; large because the appearance definition is explicit |
| `phase_studio/jana_integration.py` | 580 | Jana ownership detection and transactional install/update/remove | Version, filesystem/ZIP/hash utilities | Installer UI, distribution tests | Low; one unreferenced verification helper needs entry-point proof |
| `phase_studio/map_quality.py` | 507 | Validation profiles, immutable metrics, candidate ranking/recommendation | NumPy, gemmi | Full GUI, result selector, tests | Low; cohesive scientific policy and should stay explicit |
| `phase_studio/sharped_server_client.py` | 425 | One-host model discovery and authenticated upload/poll/download lifecycle | urllib/SSL, performance profiler | Full GUI and Wizard execution/model refresh, requirements | Low; authoritative protocol boundary |
| `phase_studio/error_reporting.py` | 410 | Error classification, redaction, reports/dialogs | PySide6 | Full GUI, Wizard, installer | Low to medium; already a useful consolidation, avoid another error layer |
| `phase_studio/requirements.py` | 408 | Pure pre-run checks and safe remediation primitives | SharpED client (lazy), urllib/ZIP/filesystem | Full GUI and Wizard | Medium; core is shared, but callers repeat the repair loop |
| `phase_studio/jana_installer.py` | 267 | Separate Jana installer GUI | Jana integration, branding/style | Installer entry profile | Low; deliberately separate from the scientific GUI |
| `phase_studio/ui_branding.py` | 192 | Shared branded headers, banners, icons, safe geometry | PySide6 | All three GUIs | Low; current helpers already remove repetition |
| `phase_studio/performance.py` | 129 | Profiling events and reports | Standard library | Run orchestration, SharpED client | None apparent; small and cohesive |
| `phase_studio/sharped_map_scaling.py` | 108 | Reversible signed map transform | NumPy | Both SharpED execution paths, tests | **Do not reduce:** compact scientific boundary |
| `phase_studio/process_utils.py` | 104 | Platform process flags, streaming/cancellation helpers | subprocess/threading | Full GUI and wrapper | Low; policies are shared without conflating console behavior |
| `phase_studio/standalone.py` | 11 | Standalone entry point | Lazy `app.main` | PyInstaller and console script | None; necessary import boundary |
| `phase_studio/__init__.py` | 3 | Package version export | `version` | Package consumers | None |
| `phase_studio/__main__.py` | 3 | `python -m phase_studio` entry | `standalone` | Python launcher | None |
| `phase_studio/version.py` | 2 | Canonical version | None | Runtime and build source | None; one owner is desirable |

### Packaging/build inventory

| File | LOC | Responsibility and dependencies | Main callers | Cleanup potential |
|---|---:|---|---|---|
| `packaging/pyinstaller/portable_runtime.py` | 301 | Collect, validate, and manifest the portable Qt/scientific runtime | Both authoritative PyInstaller specs | Low; shared code already avoids two copies |
| `packaging/tools/audit_dependencies.py` | 237 | Distribution dependency/security audit | Build scripts/developer checks | Low; defensive distribution verification |
| `packaging/tools/verify_imports.py` | 191 | Frozen import/runtime verification | Build scripts | Low; packaging regression boundary |
| `packaging/build_store_msix.ps1` | 134 | Standalone ONEDIR build, MSIX staging/validation/signing | Store release procedure | Low; distinct Store path |
| `packaging/pyinstaller/PhaseStudio.spec` | 124 | Shared standalone and installer ONEFILE definitions | root/profile selector specs, Windows build | Low; currently authoritative |
| `packaging/build_windows.ps1` | 120 | Standalone, Jana installer, and Jana wrapper release orchestration | Developer release procedure | Low; authoritative non-Store path |
| `superflip.spec` | 94 | Authoritative ONEDIR Jana wrapper | Windows build | **Do not merge** with full GUI spec; payload/startup differ |
| `packaging/pyinstaller/runtime_hooks/pyi_rth_dll_isolation.py` | 84 | Protect frozen Qt from foreign DLL/plugin paths | PyInstaller spec | None without a distribution matrix proving removal safe |
| `packaging/generate_store_assets.py` | 79 | Generate required Store images from canonical icon | Manual Store preparation | Low; generated outputs are excluded from source LOC |
| `packaging/tools/check_distribution.py` | 69 | Verify expected release layout | Windows build | Low |
| `packaging/msix/AppxManifest.template.xml` | 61 | MSIX manifest template | Store build | None; Store contract |
| `packaging/sign_test_msix.ps1` | 57 | Local test signing | Developer Store testing | Low; update the 1.0.8 example name when editing docs/script, but it is not dead |
| `pyproject.toml` | 40 | Package metadata, dependencies, entry points | Build tools/installers | None |
| `packaging/tools/package_jana_payload.py` | 26 | Create verified embedded Jana payload | Release preparation | None; installer contract |
| `packaging/common.ps1` | 19 | Shared PowerShell build helpers | Both build scripts | None |
| `packaging/pyinstaller/windows_version.py` | 18 | Windows version-resource generation | Specs | None |
| `packaging/msix/store_identity.example.json` | 7 | Store identity schema/example | Store preparation | None; not a runtime identity |
| `PhaseStudio.spec` | 4 | Root standalone convenience forwarder | documented build command | Negligible saving; still referenced |
| `packaging/pyinstaller/PhaseStudioJanaInstaller.spec` | 4 | Select installer profile in shared spec | Windows build | Negligible saving; still referenced |
| `packaging/pyinstaller/PhaseStudioStore.spec` | 4 | Select Store ONEDIR profile in shared spec | Store build and tests | Negligible saving; still referenced |

The three four-line selector specs resemble wrappers but are current build
entry points. Removing 12 LOC would force complexity into command lines and
documentation and would invalidate tested paths, so they are not cleanup
targets.

### Tests and documentation

| Test script (LOC) | Protected behavior |
|---|---|
| `test_final_ui.py` (72), `test_ui_hierarchy.py` (339), `test_wheel_safety.py` (237) | Text, hierarchy, object properties, layout/style safety |
| `test_wizard_geometry.py` (356), `test_wizard_models.py` (154) | Wizard geometry, asynchronous model discovery/default preservation |
| `test_preflight_ui.py` (276), `test_requirements.py` (266) | Conditional checks, repair/recheck/resume, redaction |
| `test_scientific_core.py` (169), `test_model_formats.py` (150) | HKL/scientific golden values and file formats |
| `test_map_quality.py` (204), `test_metric_legends.py` (79), `test_jana_completion.py` (252) | Four validation profiles, ranking, display, selector/handoff |
| `test_sharped_api_contract.py` (123), `test_sharped_map_scaling.py` (266) | Exact host/auth/model lifecycle and reversible map values |
| `test_process_launch.py` (348), `test_workflow_states.py` (153) | Console/cancellation/stop semantics and terminal states |
| `test_split_distribution.py` (261) | Split entry points, ownership transactions, upgrade, scientific parity |
| `test_performance.py` (122) | Profiling and bounded hot paths |

The suite is 18 independent scripts and 691 checks. Its self-contained design
is intentionally dependency-free, but it repeats path setup, Qt application
setup, module stubs, and check/report scaffolding. A small `tests/support.py`
could remove an estimated 100-160 LOC across 8-12 scripts. Do this only when a
script is already being edited, and keep every assertion. Do not convert the
suite to a framework merely for cleanup.

Current documents are `ARCHITECTURE.md` (365 lines),
`PERFORMANCE_AUDIT_1_0_9.md` (299), `SHARPED_MODEL_DISCOVERY.md` (180),
`RELEASE_1_0_9.md` (133), and `SHARPED_TEMPORARY_BRIDGE.md` (62).
`SHARPED_TEMPORARY_BRIDGE.md` already labels itself historical, but it and the
release note still contain temporary migration language. Move historical
records intact to `docs/history/`; keep `ARCHITECTURE.md` as the short current
authority and correct its obsolete `compute_rfree` reference. Keep the
performance audit as measured evidence or move it with the other versioned
records. This improves normal reading context but deliberately does not claim a
repository LOC reduction.

The root documentation also includes `README.md` (193 lines), `MANUAL.md`
(819), and `BUILDING.md` (290), plus the Store-specific
`packaging/README_STORE.md` (50) and asset instructions (30). Keep their roles
explicit: README for orientation, MANUAL for user behavior, BUILDING for all
authoritative developer distribution commands, and Store files only for Store
details. Link rather than repeat profile/runtime explanations. Treat every
visible workflow description in the MANUAL as a compatibility checklist during
cleanup.

## 2. Ranked hotspots

| Rank | Hotspot | Size/context cause | Finding |
|---:|---|---|---|
| 1 | `app.py` | A, B, C, D, F, G, H, I, J | It combines pure crystallography, formats, complete GUI construction, settings, process control, plots, selectors, and orchestration. Most code is real, but one entire 708-line selector is dead and parsing/preflight/model state repeat elsewhere. |
| 2 | Full GUI run methods (`pipeline_worker`, ordinary cycles, SharpED recycle cycles) | A, D, F, H, I | Execution, checkpoint state, progress events, file generation, and error handling are interleaved. They are reachable and behavior-sensitive; extraction is justified only after baselines define state transitions and command/file outputs. |
| 3 | `jana_superflip.py` | A, B, D, F, H | Wrapper, Wizard, and full-GUI bridge coexist to preserve a lightweight authoritative executable. Repetition with `app.py` exists around inflip parsing, requirements, model state, and handoff values. |
| 4 | HKL validation/completeness UI in `app.py` | A, B, G | Two large dialogs contain real tables/plots/explanations plus repeated branded/table/card construction. Moving them can reduce Basic-control context; only common chrome offers raw LOC savings. |
| 5 | Result selection and metrics presentation | A, B, E, G, J | The new profile-aware selector is cohesive. The superseded selector was retained beside it and is unreachable. Ranking itself is correctly centralized in `map_quality.py`. |
| 6 | `ui_style.py` | A, B | Its large stylesheet is the explicit appearance contract. Moving CSS text would only relocate lines and risks visual drift. |
| 7 | Packaging/runtime collection | A, F | Size comes from four distribution profiles, DLL isolation, and verification. History shows the 1.0.9 split consolidated portable-runtime logic already. |

### Largest functions and methods

| Function/method | Lines | Classification | Planned treatment |
|---|---:|---|---|
| `_open_legacy_jana_result_selector` | 708 | Dead replacement/history layer | Delete in Phase 1 |
| `_run_pipeline_cycles` | 546 | Mixes orchestration responsibilities; behavior-sensitive | Establish event/file baselines, then extract explicit stage functions only if call context falls materially |
| `_build_hkl_completeness_dialog` | 536 | Large but mostly cohesive; repeated presentation chrome | Keep behavior; later move with the paired HKL dialog and reuse existing UI helpers |
| nested legacy-selector `rebuild` | 410 | Dead with its owner | Delete in Phase 1 |
| Jana Wizard page builders (largest 345, 317, 250) | 912 combined | Cohesive repeated Qt construction | Keep; apply only proven small row/footer helpers |
| `pipeline_worker` | 300 | Mixes pre-run/resume/terminal coordination | Structural boundary after state baselines |
| Jana wrapper `run` | 267 | Large but appropriately cohesive transaction with restoration | Do not split merely by length |
| `_render_metrics_tab` | 256 | Cohesive plotting plus duplicated formatting | Share metric value/label formatting only |
| `open_result_selector` | 254 | Cohesive UI, but misplaced in giant host and coupled through preview methods | Extract as one result-selection component after dead selector removal |
| `_build_input_tab` | 208 | Cohesive UI construction | Keep unless Basic-control context remains excessive after larger removals |
| `apply_phase_studio_style` | 206 | Explicit appearance definition | Do not touch now |
| `show_requirement_remediation_dialog` | 180 | Shared behavior currently located in `app.py` | Extract with the repeated repair loop in Phase 2 |
| `_poll_queue` | 175 | Many event types and state mirrors | First reduce event/state ownership; avoid a cosmetic split |
| `run_command` | 174 | Cohesive GUI-owned child-process policy | Keep separate from wrapper-visible process policy |

### Relevant 1.0.8 to 1.0.9 history

| Commit/history point | Audit conclusion |
|---|---|
| `411e431` split standalone and Jana installer builds | This established the current distribution boundaries. The profile selector specs and separate installer entry remain reachable and tested. |
| `bb57b26` added temporary split SharpED metadata/inference endpoints | The bridge was temporary by design. Later `396270c` restored `https://jana.fzu.cz`; current code has one `DEFAULT_SERVER_URL` and no dual-host routing. Preserve the design record as history, not current architecture. |
| `2e1a87b` and `a83e6d1` changed live model discovery/UI release behavior | Current discovery/default resolution is centralized in the client, while two Qt views still duplicate selection reconciliation. There is no old production catalog to delete safely. |
| `57567f2`, then `5dee420`, developed shared preflight and remediation | Pure checks are centralized and current. The remaining cleanup is duplicated caller/UI plumbing, not deletion of defensive executable/authentication checks. |
| `3b63e41` added profile-aware quality and automatic result selection | Git diff and current references prove the prior selector was renamed and left unreachable. This is the highest-value safe deletion. Old ranking helpers need individual proof because they are scientific public functions, even when repository callers are absent. |
| `8cc87b9` reduced run overhead | Caches, batched FFT work, bounded status checks, and timing hooks reflect measured performance work. They are not cleanup artifacts merely because they add defensive/cache state. |

The history also confirms that the old standalone Jana-management UI and the
1.0.8 monolithic distribution are not live alternate paths in the current
tree. Their behavior is covered as absence/upgrade behavior in
`test_split_distribution.py`; no second installer implementation or superseded
authoritative spec was found.

## 3. Dead and obsolete candidates

Repository search, AST reference inspection, callers, tests, packaging specs,
and the 1.0.8-to-1.0.9 history were considered together. Qt overrides, signal
callbacks, callable objects, lazy imports, PyInstaller hooks, and entry points
are excluded from SAFE based on static results alone.

| Candidate | Evidence | Confidence | Removable LOC |
|---|---|---|---:|
| `_open_legacy_jana_result_selector` | Added/renamed when commit `3b63e41` introduced `open_result_selector`; only the definition remains and all completion paths call the new selector | **SAFE** | 708 |
| `_source_map_path`, `_source_structure_path`, `_source_quality`, `_source_available_for_results`, `_default_handoff_source` | Every reference is inside the dead selector/helper chain; the current selector uses `ResultCandidate` paths directly | **SAFE after deleting the selector in the same commit** | about 25 |
| `CONFIG_GUIDED_GROUP_MARGINS`, `CONFIG_GUIDED_GROUP_SPACING` | Definitions only; active spacing uses the established `PHASE_STUDIO_*` values | **SAFE** | 2 |
| `fitted_dialog_client_size` imported by `app.py` | No use in `app.py`; the function itself remains used by `ui_branding.py` | **SAFE** | 1 import line |
| `jana_superflip.extract_embedded_hkl` | Definition only; full GUI uses the stricter `extract_embedded_hkl_from_inflip` with an explicit work directory | **LIKELY** | about 24 |
| `jana_integration.verify_installed` | Definition only; installer uses inspection/state/transaction functions and distribution tests do not invoke it | **LIKELY** because it is module-level and could be an undocumented external import | 27 |
| Old pure helpers in `app.py`: `get_cif_block`, `manual_cif_value`, `reference_context_with_external_atom_sites`, `atom_recall_precision`, `is_systematically_absent_hkl`, `sintheta_over_lambda_from_metric`, `canonical_hkl`, `reflection_amplitude_signal_to_noise`, `theoretical_unique_hkls_from_observed`, `format_superflip_fixed_reflection`, `infer_dataitemwidths_from_hkl`, `xplor_fft_intensity_phase`, `select_omit_test_set`, `compute_rfree`, `resample_xplor_map`, `without_inflip_keywords`, `write_reference_cif_from_inflip`, `warn_if_windows_unsigned_exe` | No repository caller was found; several have newer cached/batched/profile-aware equivalents. Architecture docs still mention one old name, and scientific/file compatibility makes name search insufficient proof. | **UNCERTAIN individually** | about 290 total |
| `open_jana_result_selector` adapter | It delegates to the new selector, but automatic handoff and tests still use the name | **NOT DEAD** | 0 |
| QSettings legacy-key reads and value aliases | Reachable during upgrade from older installations | **NOT DEAD** | 0 |
| SharpED TLS certificate fallback and download auth candidates | Reachable failure/protocol behavior on Windows; not an endpoint bridge | **NOT DEAD** | 0 |
| Selector spec files and root spec | Called by current scripts/documented commands and asserted by distribution tests | **NOT DEAD** | 0 |

The immediately safe production reduction is approximately **735 LOC** (use a
range of 720-750 until the actual diff is counted). The LIKELY helpers should
move to SAFE only after frozen-entry import scans and a clean complete suite.
The uncertain scientific helpers require focused golden tests or historical
call-site proof before deletion. No safe obsolete class, dataclass field,
feature flag, environment variable, commented-out implementation block, or
unreachable packaging branch was proven in this pass.

## 4. Duplication and fix layers

| Area | Approximate duplicate LOC / copies | Safe consolidation? | Expected net reduction | Decision |
|---|---:|---|---:|---|
| Old and current result selectors | 708 / 2 implementations | Yes: old path is unreachable | 708 | Phase 1 deletion, no abstraction |
| Requirements repair/recheck/resume plumbing | 110-150 / 3 paths (full GUI, Wizard, wrapper entry) | Yes with UI/state tests; checks already share `requirements.py` | 60-90 | One explicit remediation runner/dialog boundary |
| SharpED model refresh and selection reconciliation | 70-100 / 2 Qt UIs | Partly; network/catalog authority already lives in client, while widget timing differs | 30-50 | Share pure selection reconciliation; retain UI-specific async wiring |
| `.inflip` token/read/insert/block parsing | 70-110 / 2 implementations | Yes after byte-for-byte fixtures; wrapper must stay lightweight | 35-65 | Small pure `inflip_io` module, no import of `app` |
| Metric value/label/table formatting | 60-90 / 3 presentations | Yes for pure strings/schema; layouts remain distinct | 25-45 | Put schema/formatters next to `map_quality`, keep Qt code local |
| Branded dialog/table/action-footer construction | 100-160 / 4+ dialogs | Only identical geometry/object properties | 40-70 | Extend existing branding helpers; no declarative UI framework |
| Report/CSV metric row assembly | 45-70 / 2-3 outputs | Yes if exact column/order golden files are added first | 20-35 | Shared ordered row builder |
| SharpED request preparation in full GUI and wrapper | 45-70 / 2 paths | Technically possible but scientifically/protocol sensitive | 20-35 | Defer; client lifecycle is already shared and savings are marginal |
| File selector/form rows | 60-100 / many rows | Appearance and source-note behavior differ | 20-40 at most | Consolidate only visually identical rows while editing them |
| Process invocation/monitoring | Superficially similar / 2 policies | **No**: full GUI hides children; wrapper owns one visible streaming console | 0 | Preserve separate policies over a shared low-level utility |
| Packaging runtime staging | Previously duplicated | Already consolidated in `portable_runtime.py` | 0 further | Keep current authority |

Successive fixes created four visible layers:

1. Result selection has an original selector, a retained compatibility method,
   and a later profile-aware replacement. Runtime invariants now permit direct
   deletion of the original implementation; the small live adapter remains.
2. SharpED discovery/default resolution passed through temporary endpoint
   designs, but current protocol authority is one `DEFAULT_SERVER_URL` and one
   client. Historical bridge documentation remains; production does not contain
   the dual-host bridge. Do not recreate endpoint fallback while consolidating
   GUI model state.
3. Preflight checks were centralized in `requirements.py`, while each UI kept
   its own repair loop and state application. Consolidate that plumbing without
   weakening per-workflow conditional requirements or Skip semantics.
4. QSettings and output schemas contain migration/legacy layers. These remain
   reachable compatibility code in 1.0.9 and must stay until a separately
   versioned migration policy establishes when old installations are no longer
   supported.

## 5. State and architecture complexity

| Value | Authoritative state | Required mirrors | Excess/obsolete mirrors and action |
|---|---|---|---|
| Available SharpED models/default | Successful catalog snapshot in `SharpEDServerClient` result | Full GUI and Wizard combo contents/session cache | Two selection-reconciliation implementations; share a pure `previous selection + catalog -> displayed selection` function |
| Selected SharpED model | `RunConfig.sharped_model` or `JanaRunOptions.model` once a run starts | Editing combo and QSettings before start | Never infer run selection again from widgets after config capture |
| Workflow/terminal state | `PipelineState` plus explicit terminal event | Status/progress widgets and action enablement | `_poll_queue`, booleans, and labels mirror it; route all updates through the existing state application methods |
| Current cycle | `PipelineState.current_cycle` during execution; `CycleResult.cycle` after completion | Progress display | Remove any locally recomputed display counters only after stop/resume tests pin them |
| Validation profile | Resolved profile stored on run/results | Combo/display labels | Selector scans results as fallback; make completed-run profile explicit before removing fallback |
| Reference/holdout presence | Resolved validation data and metrics | Summary labels | Several booleans are derived repeatedly; derive a frozen display summary once per completed run |
| Result candidate/recommendation | `map_quality.ResultCandidate` and `ResultRecommendation` | Selected table row | Old source-based selector state disappears with the dead selector |
| Executable paths | Captured `RunConfig`/`JanaRunOptions`; QSettings before run | Path editors | Keep Jana auto-detection as input resolution, then execute only captured paths |
| Jana launch context | `JanaWizardContext`/handoff import at launch | Window banner/action state | Remove source-mode concepts belonging only to the old selector |
| User configuration | Existing QSettings keys feeding a captured config | Widgets while editing | Widgets must not become execution authority; keep all existing keys and migration reads |

Avoid a state registry, event bus, or service layer. The useful rule is simple:
widgets edit values, immutable/captured configuration owns a run, `PipelineState`
owns active execution, and `CycleResult`/recommendation objects own completed
results.

## 6. Import/dependency graph

The current top-level graph is acyclic. `app.py` imports the shared scientific,
SharpED, requirements, process, quality, error, branding, and style modules.
`jana_superflip.py` deliberately delays PySide/full-GUI imports and imports
`app.py` only when opening full configuration. `requirements.py` delays the
SharpED client import. `jana_installer.py` stays independent of NumPy, gemmi,
Matplotlib, and the full application.

The harmful edge is the Wizard remediation path importing
`show_requirement_remediation_dialog` from the 13,082-LOC `app.py`. Move that
dialog and shared repair loop to a small requirements UI boundary. The wrapper
must continue to avoid full-GUI/scientific imports for wrapper-only workflows.
Likewise, shared inflip primitives must be pure and lightweight. There is no
evidence for duplicate utility modules or a circular dependency that warrants a
larger architecture change.

## 7. Context-window analysis

Estimates count whole nonblank modules/tests a maintainer normally has to inspect
to change behavior safely; a targeted human may read selected ranges, but a
coding model often needs the containing module to rule out coupled state.

| Common task | Current normal context | Approx. current LOC | Target context after justified cleanup | Approx. target LOC / benefit |
|---|---|---:|---|---:|
| A. Change a SharpED API request | client, requirements, both call sites in `app`/Wizard, scaling, API/model tests | 16,500-17,000 | client + explicit request contract + focused tests; callers consume one result type | 900-1,400 / 92% less |
| B. Add a validation metric | `map_quality`, giant `app`, selector/plot/report paths, 3 tests | 14,000-14,700 | quality schema + result presentation/report modules + focused tests | 2,000-3,000 / 80% less |
| C. Modify one Basic-tab control | `app`, style/branding, UI/settings tests | 15,000-16,000 | focused Basic configuration UI/state section + style helper + tests | 2,500-4,000 / 75% less |
| D. Change Jana handoff | Wizard/wrapper, giant `app`, result selection, handoff tests | 15,500-16,500 | pure handoff mapping + thin launch adapters + tests | 2,000-3,000 / 82% less |
| E. Change Result Selection | giant `app`, `map_quality`, completion/UI tests | 13,800-14,400 | one result-selection component + quality policy + tests | 1,500-2,200 / 85% less |
| F. Modify packaging | relevant spec/build script, `portable_runtime`, distribution test/docs | 1,000-2,200 | Current architecture is already near target; use the authoritative profile table | 900-1,800 / modest benefit |
| G. Debug Superflip execution | giant `app`, wrapper, process helper, process/scientific tests | 15,800-16,500 | explicit GUI execution stages or wrapper transaction + shared pure inflip/process primitives | 3,500-5,500 / 65-75% less |

Moving all 13,082 lines into arbitrary smaller files would not achieve these
targets. The reduction comes from deleting the selector, sharing actual parsing
and repair logic, then placing each cohesive presentation/execution boundary
behind small explicit inputs and outputs.

## 8. Target architecture where change is justified

1. Keep `map_quality.py`, `sharped_server_client.py`,
   `sharped_map_scaling.py`, `process_utils.py`, and `requirements.py` as direct
   policy boundaries. Add helpers there only when responsibility matches.
2. Add one lightweight pure inflip module for tokenization, ordered keyword
   edits, and block extraction used by both `app` and the wrapper. It must not
   import Qt, NumPy, gemmi, Matplotlib, or `app`.
3. Add one small requirements-remediation UI module so both GUIs share the
   repair/recheck result contract without the Wizard importing `app`.
4. After Phase 1, move the current result-selection dialog and its preview
   adapter into one component accepting candidates, profile, context, and
   explicit save/handoff callbacks. Move exact metric/report formatters with
   their schemas. This mostly reduces context; it should also remove callback
   and formatting copies.
5. If profiling and state baselines remain green, express ordinary execution as
   a short list of explicit stages operating on `PipelineState`. Keep stage
   code visible and direct. Do not introduce a generic task engine.
6. Consider moving the paired HKL validation/completeness dialogs together only
   after shared scientific inputs are immutable. This is context extraction,
   not a raw LOC claim.

No QML, generated UI, dependency-injection container, event bus, plugin system,
dynamic registry, giant service object, or inheritance hierarchy is justified.

## 9. Phased cleanup plan and estimates

### Phase 1 — safe deletion

Delete the old selector and its private helper chain, the two unused constants,
and the unused import. Make the selector deletion one reviewable commit and run
selector, UI, workflow-state, and full tests. Promote either LIKELY helper only
after frozen import/entry-point scans prove it private and unused. Audit the
uncertain pure helpers one family at a time; do not batch-delete scientific
functions.

Expected production result: 720-800 LOC removed, 0-10 added, low regression
risk, very high result-selection context benefit.

### Phase 2 — low-risk consolidation

Consolidate requirements remediation, pure model-selection reconciliation,
exact metric/report formatting, and only visually identical Qt chrome. Add a
small shared test support module opportunistically without reducing assertions.
Move version-specific documents to `docs/history/` and make current architecture
text agree with current symbols and one-host SharpED behavior.

Expected production result: 300-500 LOC removed, 80-180 added, **200-350 net
reduction**. Risk is low to moderate and is bounded by existing UI, preflight,
request, CSV, and object-name baselines.

### Phase 3 — structural simplification

Extract shared pure inflip operations, the result-selection component, and—only
after state-event baselines—the explicit run-stage boundary. Consider paired HKL
dialogs for context reduction. Every extraction must either remove a duplicate
or reduce a listed task's context by at least 40%; reject moves that merely add
files and forwarding layers.

Expected production result: 600-900 removed, 250-450 added, **350-550 net
reduction**. More important, common GUI/scientific tasks should need 65-90% less
whole-module context. Risk is moderate to high, so use one boundary per commit.

### Phase 4 — do not touch now

Do not simplify scientific formulas/transforms, merge the two process-console
policies, collapse packaging profiles, remove QSettings/file migrations, rewrite
the stylesheet, replace the UI technology, or genericize orchestration. Revisit
only for a concrete bug or measured need with new golden evidence.

### Estimated result

| Measure | Current | Realistic target | Change |
|---|---:|---:|---:|
| Production LOC | 21,632 | 19,900-20,300 | 1,300-1,700 fewer (6-8%) |
| `app.py` LOC | 13,082 | roughly 10,500-11,300 | deletion plus justified context extraction; repository LOC does not fall by all moved lines |
| Safe deletion | — | 720-800 | 3-4% immediate production reduction |
| Further net consolidation | — | 550-900 | duplicated plumbing/formatting/parsing, after added shared code |
| Typical A-E/G task context | 13,800-17,000 | 1,500-5,500 | approximately 65-90% lower, depending on task |

The target deliberately avoids an implausible large percentage: most remaining
code implements real scientific, GUI, error, compatibility, and distribution
behavior. A 6-8% raw reduction paired with a much larger context reduction is a
more credible outcome than deleting defensive or scientific code.

## 10. Regression strategy and behavioral baselines

Before production cleanup, preserve the current 18-script/691-check green
baseline and add only gaps needed for the next commit:

- Pin small scientific golden fixtures for Superflip input text, seeded/unseeded
  repeat behavior, EDMA command/thresholds, HKL parse/merge/completeness,
  d_min/d_98, map feedback, OMIT/R_free, FFT/map output, and resulting file
  hashes or numeric arrays with explicit tolerances.
- Record exact SharpED request URL, headers, multipart fields/model sentinel,
  status polling, download authentication, and before/after map arrays using
  mocked transport. No live credential belongs in a baseline.
- Pin Jana handoff value precedence, generated `.inflip`/m80 inputs, selected
  map/model paths, marker ownership, original-file restoration, and wrapper
  exit/console behavior.
- Add golden result-candidate ordering, all four profile recommendations, metric
  labels/values, metrics CSV column order/content, and human-readable report
  text.
- Build a QSettings compatibility matrix from representative old/current keys.
  Load each fixture, assert captured `RunConfig`/`JanaRunOptions`, save it, and
  assert stable key/value meaning. Never use the developer's real settings.
- Keep structural Qt tests for object names, hierarchy, texts, defaults,
  enabled/disabled transitions, model-refresh timing, geometry clamping, and
  stop/cancel outcomes. Add a short manual visual checklist at 100%, 125%, and
  150% scale for the Basic tab, Wizard pages, remediation dialogs, result
  selector, and metrics/structure views; do not use pixel screenshots as the
  sole UI oracle.
- For packaging, assert the four authoritative profiles, entry points, included
  modules/runtime/DLL policy, Jana payload manifest, Store manifest identity
  substitution, absence of management UI from standalone, and frozen smoke
  starts. Compare distribution manifests before and after packaging edits.

Focused tests should run after each conceptual change; all 18 scripts run before
each commit that crosses module boundaries or changes packaging. Use the current
dependency-free command documented in `BUILDING.md` and require zero failed
scripts/checks. Scientific golden changes are a stop signal, not values to
update casually.

## 11. Do-not-touch areas

- Scientific equations and transformations, including symmetry/orbit caching,
  systematic absences, completeness/resolution, FFT conventions, signed map
  scaling, Map Feedback, OMIT/R_free, and ranking order.
- Superflip repeat/random-seed input semantics, fixed-width/file formatting,
  EDMA thresholds, and command working directories.
- SharpED's single configured server lifecycle, token headers, `DEFAULT` model
  resolution, compatibility probe, polling, TLS handling, and download auth.
- Separate hidden-child full-GUI execution and visible streaming wrapper
  execution policies.
- Jana transactional ownership markers, hashes, rollback, payload verification,
  and restoration of the original `.inflip`/executable.
- Existing QSettings keys and migrations, output filenames, metrics CSV columns,
  Jana marker formats, and user configuration interpretation.
- Qt appearance strings/layout/object names/high-DPI geometry and the current
  standalone/installer/wrapper/Store profile boundaries.

## 12. Recommended first five commits

1. **Add cleanup guard baselines.** Add the missing exact Superflip/EDMA input,
   Jana handoff, CSV/report, QSettings migration, and packaging-manifest fixtures
   needed by the following commits. Make no production behavior change.
2. **Remove the unreachable legacy result selector.** Delete the 708-line method
   and its now-private dead source helper chain. Run result selector, Jana
   completion, terminal-state, UI hierarchy, and the complete suite.
3. **Remove proven unused symbols.** Delete the two guided-spacing constants and
   the unused import. Delete `extract_embedded_hkl`/`verify_installed` only if a
   frozen import scan and distribution smoke test promote them from LIKELY to
   SAFE; otherwise leave them for a later commit.
4. **Share requirements remediation without importing the full app.** Move the
   dialog/result contract to a small module and replace the repeated GUI/Wizard
   repair loops while preserving text, object names, settings updates, Skip,
   and resume behavior.
5. **Unify pure `.inflip` primitives.** Introduce the lightweight parser/editor,
   switch one caller at a time, compare byte-for-byte fixtures, then remove the
   duplicate implementations. Preserve lazy imports and wrapper-only startup.

Each commit starts and ends with green focused tests; commits 2, 4, and 5 also
run the complete suite. Do not combine these into a broad formatting, rename, or
module-move diff, and do not push cleanup until each reviewable unit has passed
its scientific and distribution baselines.
