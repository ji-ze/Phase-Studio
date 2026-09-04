# Phase Studio architecture

A concise, practical map of the codebase for anyone making a change. This
is not exhaustive documentation of every function -- it exists so a future
change touches as few files as possible and carries low regression risk.

## The one non-negotiable rule

**Same input -> same scientific result, always.** Superflip input
generation, parameters, `repeatmode`/`randomseed` behavior, SharpED
requests, EDMA execution, HKL parsing, completeness/`d_min`/`d_98`,
symmetry operations, map/structure generation, validation metrics
(OMIT/R_free), ranking, and the Jana2020 handoff must never change as a
side effect of a refactor, a performance change, or a UI change. If a
change to any of these is ever genuinely needed, it is its own task, with
its own explicit review -- never bundled with anything else.

## Entry points

- `phase_studio/app.py` -- `main()` launches the standalone GUI
  (`IterativeSuperflipPipelineQtGUI`). This is also the module PyInstaller
  freezes for the developer-distribution build (`PhaseStudio.spec`,
  `packaging/pyinstaller/PhaseStudio.spec`).
- `phase_studio/jana_superflip.py` -- `main()` is the entry point frozen as
  `superflip.exe` by the repository-root `superflip.spec` (the
  authoritative, ONEDIR, already-verified-against-a-real-Jana2020
  build -- see "Jana2020 integration" below). Depending on the incoming
  `.inflip` and user choice, it either runs a lightweight single-pass
  Superflip(+SharpED) workflow directly, or launches the full
  `phase_studio.app` GUI (`launch_phase_studio_from_jana`).
- `phase_studio/__main__.py` -- `python -m phase_studio`, delegates to
  `phase_studio.app.main()`.

## Major modules and responsibilities

| Module | Responsibility |
|---|---|
| `phase_studio/app.py` | The full GUI (`IterativeSuperflipPipelineQtGUI`, a `QMainWindow`) **and** the scientific pipeline: HKL parsing, completeness analysis, Superflip/EDMA/SharpED orchestration, map feedback, validation, ranking, plotting, settings persistence. By far the largest module (~13k lines); see "Known size/coupling issues" below. |
| `phase_studio/jana_superflip.py` | The Jana2020 wrapper/launcher: `.inflip` parsing and manipulation, the Jana2020 Wizard dialog (`show_jana_dialog`), the single-pass Superflip(+SharpED) execution path, and building the handoff (`build_jana_handoff_import`) that pre-fills `phase_studio.app`'s widgets when it launches the full GUI. Deliberately keeps PySide6/matplotlib/numpy/gemmi imports deferred (function-local) so the lightweight single-pass path stays cheap to start. |
| `phase_studio/jana_integration.py` | The transactional Jana2020\SUPERFLIP install/update/repair/remove engine (detect -> stage -> verify -> swap, with rollback). Pure file-system logic, deliberately Qt-free so it is independently testable; `app.py` provides the dialog that drives it. |
| `phase_studio/process_utils.py` | Small, dependency-free process helpers (`text_encoding`, `allow_external_process_foreground`) shared by `app.py` and `jana_superflip.py`. Stdlib-only by design -- both the heavy full-GUI path and the lightweight single-pass wrapper path import it without paying any extra import cost. |
| `phase_studio/error_reporting.py` | `ErrorReport`/`build_error_report()`/`show_phase_studio_error()`: the one translation point from a raised exception to a structured, non-raw-traceback user-facing dialog (title/summary/guidance + collapsible technical details). |
| `phase_studio/sharped_server_client.py` | HTTP client for the SharpED deblurring service (upload, poll, download). |
| `phase_studio/ui_style.py` | The application's QSS/visual style (dark navy + medium blue, flat scientific desktop look) and a `QProxyStyle` for custom combo/spin-box arrows. Pure Qt styling, no business logic. |
| `phase_studio/version.py` | The single source of truth for the application version (`VERSION`). Everything else (window titles, splash screen, Jana2020 integration marker, `pyproject.toml`'s dynamic version, the MSIX package version) derives from this one string -- see "How to bump the version" below. |

## Scientific pipeline flow (standalone / Open full configuration)

```
widgets (Basic/Advanced tabs)
    -> get_config()                     RunConfig (one dataclass, ~90 fields)
    -> pipeline_worker() [background thread]
        -> _run_pipeline_cycles() / _run_sharped_recycle_cycles()
            per cycle:
                write_superflip_input() -> run Superflip (run_command())
                -> optional SharpED deblur (SharpEDServerClient)
                -> optional EDMA peak search (run_command())
                -> map feedback (missing-reflection completion /
                   intensity correction / powder overlap repartitioning)
                -> metrics (nearest_metric_to_reference, compute_rfree,
                   xplor_map_correlation, ...) -> CycleResult
        -> self.msg_queue.put(("result"/"progress"/..., payload))
    -> QTimer (200 ms) -> _poll_queue() [GUI thread]
        -> applies each message to widgets/plots/tables
```

Background threads **only** call `self.msg_queue.put(...)`; they never
touch a widget directly. All GUI mutation happens in `_poll_queue()` on the
GUI thread. Keep this discipline for any new background work.

## Configuration flow

`RunConfig` (a dataclass, `app.py`) is the one authoritative representation
of a scientific run's configuration. `get_config()` reads every relevant
widget into it; `_apply_workflow_preset()` and `load_settings()`/
`save_settings()` go the other direction (preset/QSettings -> widgets).
`JanaRunOptions` (`jana_superflip.py`) is the Wizard's equivalent for the
Jana2020 launch path, translated into main-window widget values by
`build_jana_handoff_import()` before `RunConfig` is ever built.

**Persisted `QSettings` keys are a compatibility surface.** Existing users'
saved settings must keep working -- never rename or repurpose a
`QSettings` key without an explicit migration path.

## Jana2020 integration flow

Two independent things share the name "Jana2020 integration":

1. **The wrapper/launcher** (`superflip.exe`, built by the repository-root
   `superflip.spec`, ONEDIR): this is what Jana2020 actually launches. It
   is authoritative and intentionally the *only* Jana wrapper build --
   `packaging/pyinstaller/` has no competing Jana spec. Do not migrate it
   to ONEFILE; do not add a second one.
2. **The install/update/repair/remove engine** (`jana_integration.py`):
   manages copying that wrapper into a real `Jana2020\SUPERFLIP`
   installation, preserving the user's original `Superflip.exe` as
   `superflip_original.exe`, with a JSON ownership marker, staged
   installs, and rollback on failure. Driven by the "Jana2020 Integration"
   dialog in `app.py` (`open_install_to_jana_dialog`).

`packaging/build_windows.ps1` builds both the standalone app and the Jana
wrapper, then stages a copy of the wrapper into
`dist\PhaseStudio\JanaIntegration\` (a plain file copy -- never a second
PyInstaller build) so the running standalone app can find and install it.
`packaging/build_store_msix.ps1` delegates the actual build to
`build_windows.ps1` and stages its already-built output into the MSIX
layout; it does not rebuild anything itself. Both scripts share small
helpers from `packaging/common.ps1`.

## SharpED flow

`SharpEDServerClient` (`sharped_server_client.py`) uploads an XPLOR map,
polls until the server finishes, and downloads the deblurred result. Two
independent call sites use it: the main pipeline (`run_sharped_deblur` in
`app.py`, part of a phasing cycle) and the Jana Wizard's model-list refresh
(`jana_superflip.py`, `show_jana_dialog`'s `refresh_available_models`).
Both use the same background-thread + `queue.Queue` + `QTimer`-poll
pattern independently (200 ms interval in `app.py`, 100 ms in the Wizard)
-- this is an accepted, intentional duplication of a small pattern for two
genuinely different purposes, not a bug.

## Where UI formatting belongs

Canonical, reusable display-formatting functions already live in
`app.py` as plain module-level functions (no `self`, no `QApplication`
required to call them) -- for example `reflection_value_label()`,
`reflection_sigma_label()`, `reflection_primary_snr_label()`,
`result_map_label()`, `result_structure_label()`,
`format_reflection_data_mode()`, `modelfile_source_display_label()`.
**Add a new display label here, as a small pure function, rather than
inline string literals scattered across dialogs** -- this is what let the
2026 terminology pass (canonical "Superflip map"/"SharpED map" wording,
mode-aware significance labels) touch one function instead of every call
site.

Internal identifiers (`deblurred_xplor`, `superflip_xplor`, QSettings keys,
`.inflip` keyword names) are never renamed to match display wording --
only the presentation layer changes.

## Where scientific calculations belong

Scientific/parsing functions in `app.py` are plain module-level functions
operating on plain data (`Path`, dataclasses, `gemmi` objects, `numpy`
arrays) -- e.g. `read_hkl()`, `analyze_hkl_data()`,
`merge_duplicate_reflections()`, `apply_map_feedback_to_reflections()`,
`compute_rfree()`. **Keep new scientific logic in this shape**: a function
callable without a `QMainWindow` instance, so it can be covered by
`tests/test_scientific_core.py`-style golden regression tests. Several
existing dialog-construction methods (`_build_hkl_completeness_dialog`,
`open_jana_result_selector`) currently compute-and-format inline as part
of building the dialog; new work should prefer computing first (a plain
function) and formatting/displaying second, even if both still end up
called from the same method for now.

## How to add a Basic/Advanced setting

1. Add the field to `RunConfig` (`app.py`).
2. Add the widget in `_build_ui()` and register it in `self.inputs`.
3. Add its tooltip to `INPUT_TOOLTIPS`.
4. Read it in `get_config()`.
5. Add it to `save_settings()`/`load_settings()` for persistence.
6. If it's Jana-Wizard-settable, add the corresponding field to
   `JanaRunOptions` and thread it through `build_jana_handoff_import()`.

## How to add a workflow metric

1. Compute it where the relevant cycle data is available (usually inside
   `_run_pipeline_cycles()`), as a plain value on `CycleResult`.
2. Add a presentation label via a small formatting function (see "Where UI
   formatting belongs"), not an inline string.
3. Surface it in `_render_metrics_tab()` and/or `write_metrics_csv()` and,
   if it should feed the phase-recycling Selection score, in
   `open_jana_result_selector()`'s ranking-columns list.

## How to add a result-source label

Add it to the same small set of presentation functions
(`result_map_label`, `result_structure_label`, ...) -- do not introduce a
second, differently-worded label for the same source elsewhere.

## How to add a Jana Wizard setting

Mirror "How to add a Basic/Advanced setting" inside `show_jana_dialog()`
(`jana_superflip.py`): add the widget, add it to `JanaRunOptions`, thread
it through `build_options()`/`attempt_run()`, and (if it should also
control the full-GUI hand-off) add it to `build_jana_handoff_import()`'s
`handoff_values` dict.

## How to add a diagnostic tab / dialog

Reuse the existing branded chrome builders (`create_phase_studio_brand_header`,
`create_phase_studio_context_banner`) rather than building a new dialog's
header from scratch -- every dialog in the app already shares this look.

## How to bump the application version

Edit `phase_studio/version.py`'s `VERSION` only. Every other version
string (window titles, splash screen, Jana2020 integration marker,
`pyproject.toml`'s package version, the MSIX four-part version in
`build_store_msix.ps1`) derives from it already.

## Main-window and Jana Wizard construction

`app.py`'s `IterativeSuperflipPipelineQtGUI._build_ui()` and
`jana_superflip.py`'s Jana2020 Wizard were each originally a single flat
function (~1,250 and ~1,300 lines respectively) building an entire
window/dialog's worth of widgets, with dozens of nested closures sharing one
mutable scope. A 2026 maintainability pass decomposed both, purely as code
motion (zero behavior change, verified via construction tests, click-driven
tests exercising real widget interaction, and the full regression suite at
every step):

- `_build_ui()` is now ~95 lines that call 14 focused builder methods, one
  per Basic/Advanced tab plus the run-controls/metrics/structure-comparison/
  execution-log sections (`_build_input_tab`, `_build_workflow_tab`, ...,
  `_build_metrics_section`, etc.). 7 shared closures used across several of
  them (`_add_settings_tab`, `_add_form_group`, `_add_help_section`, ...)
  became ordinary bound methods.
- `show_jana_dialog()` is now a 2-line wrapper around a
  `_JanaWorkflowWizard(args, inflip_path).run()` controller class. Its
  ~50 nested closures were converted in three verified stages: (1) every
  name shared across more than one closure was promoted to a `self.*`
  attribute (scope-checked so the one genuine local shadow was left alone);
  (2) the dozen closures actually called from a different "page" than the
  one they were defined in (e.g. selecting a workflow card on page 1 needs
  to update page 2's widgets) were promoted to real methods
  (`_workflow_changed`, `_adjust_dialog_size`, `_get_backing_window`, ...);
  (3) the remaining flat body was split into `__init__` (chrome/settings
  setup), `_build_page1`/`_build_page2`/`_build_page3`, and `run()` (footer,
  navigation, `dialog.exec()`). The four execution paths (Superflip only /
  Superflip + SharpED / Phase recycling / Open full configuration) and
  Cancel are each covered by a headless test that clicks through the real
  widgets (`QTest.mouseClick`/`.click()`), not just constructs the dialog.

Both were deliberately pure "extract method" passes -- no widget default,
object name, tooltip, signal connection, or layout hierarchy changed:
`app.py`/`jana_superflip.py`'s own module-level scientific/parsing functions
were untouched throughout.

## The Jana Wizard's shared HKL analysis

The Wizard's page 1 input summary and its reflection-data-mode detection
(gates whether page 3 shows single-crystal or powder/FWHM map-feedback
controls) call `resolve_hkl_analysis_inputs()` / `build_hkl_load_result()` /
`build_hkl_analysis_request_from_inflip()` -- plain module-level functions
in `app.py`, not methods, since the actual HKL-parsing/completeness
computation never touched `self` to begin with. This is the same
computation the main GUI's own `_collect_hkl_analysis_request()` /
`test_hkl_load_dialog()` / `open_hkl_completeness_dialog()` use for its
"Jana2020 .inflip" input mode -- one implementation, reachable without
constructing a window.

The Wizard's "Validate HKL" / "Analyze completeness" buttons still construct
a hidden, never-shown `IterativeSuperflipPipelineQtGUI()` (`_get_backing_
window()`) -- but now *only* to reuse those two methods' actual dialog
presentation (plots, diagnostic-dialog chrome shared with the main app), not
for computation. Eliminating that hidden window too would mean duplicating
substantial dialog UI code, not just computation, so it's deliberately left
as-is; see that pass's engineering report for the full reasoning.
