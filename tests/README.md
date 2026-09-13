# Phase Studio regression tests

Plain Python scripts, not pytest (pytest is not a project dependency).
Each file is self-contained and runnable directly:

```powershell
python tests\test_scientific_core.py
```

Each script prints one `PASS`/`FAIL` line per check and exits non-zero if
anything failed, so it also works as a CI step (`python tests\test_x.py`
for every file, checking the exit code) without any additional tooling.

## What's here

- `test_split_distribution.py` -- canonical version and separate entry points,
  no standalone management UI, installer detection/install/update/repair/remove,
  1.0.8 upgrade, ownership/hash conflicts and transaction rollback. Also compares
  scientific functions with the integrated baseline; standard-library unittest.


- `test_sharped_catalog.py` -- standard-library unittest coverage of the real
  model response schema, atomic catalog/default replacement, selection intent,
  multipart DEFAULT/explicit uploads through both application entry points,
  late QSettings restoration, widget reconstruction, restart, shared preflight
  and Wizard state, failed refreshes, custom servers, and bounded reuse.
  Run directly with `python tests/test_sharped_catalog.py`; no pytest required.

- `test_scientific_core.py` -- golden regression baseline for the pure
  parsing/analysis functions in `phase_studio/app.py`: HKL parsing
  (`read_hkl`), duplicate-reflection merging, completeness analysis
  (`analyze_hkl_data`), reflection-data-mode column/label mapping, and the
  `process_utils` helpers. All expected values were captured from a real
  run of the current code and pinned here -- a change to any of these
  numbers for the same fixture input means a scientific result changed,
  which should never happen as a side effect of a refactor. See
  `docs/ARCHITECTURE.md` for the "same input, same result" rule this
  applies to project-wide.

- `test_sharped_map_scaling.py` -- the reversible signed power transform
  applied to map voxel values around a SharpED request
  (`phase_studio/sharped_map_scaling.py`). Covers the pure maths for the
  pinned input set at every documented exponent, the exact-identity
  behavior at the default `a = 1.0` and at the `a = 0` bypass, and two
  mocked server round trips through the real `run_sharped_deblur()` (an
  identity server, which must recover the original map, and a
  value-changing server, which proves the inverse is applied to the
  server's actual output rather than to a cached copy of the upload).

- `test_process_launch.py` -- how external calculation processes are
  launched. EDMA must start without a visible console window on Windows
  (`CREATE_NO_WINDOW`), while its command line, working directory, captured
  stdout, exit code and `stop_event` cancellation stay exactly as before.
  Also pins that console hiding is opt-in per call site rather than global,
  and that no creation flags are forced on Linux/macOS. Covers the Superflip
  console policy too: hidden when the full Phase Studio GUI owns execution
  (it already shows run status, progress, the log and cancellation), and for
  the wrapper-only workflows one visible console owned by the wrapper, with
  the child's output teed out progressively rather than buffered until exit.

- `test_metric_legends.py` -- Workflow-metrics legend determinism. Walks the
  real lifecycle (no data -> first cycle -> second cycle -> re-render -> tab
  switch -> view reset -> completion) and checks after every step that each
  multi-metric tab shows a legend matching exactly the series it plotted,
  with no duplicate or empty entries, and that the two genuinely
  single-metric tabs still omit theirs. The first-cycle case is the
  regression itself: the legend used to disappear whenever only one series
  happened to carry finite values.

- `test_jana_completion.py` -- the Jana2020 Wizard completion path. Drives
  the real pipeline message queue and Qt event loop to COMPLETE and checks
  that the locked result selector opens automatically exactly once, on the
  Wizard's own map source, with "Send to Jana2020" left enabled and
  reopening the same locked selector. Also covers Full configuration
  (manual, switchable, never auto-opened), standalone (never auto-opened),
  and the locked-source-unavailable error path. Uses structures that
  actually parse, because the original failure only appeared once the
  selector had real atoms to render.

- `test_wizard_geometry.py` -- the Jana2020 Wizard's window geometry: the
  preferred width is substantially wider than the old narrow layout, always
  clamped inside the available screen at 1920x1080 / 1600x900 / 1366x768,
  the header and footer stay outside the scrollable body, and the window
  height follows the page actually on screen instead of the tallest page in
  the stack.

- `test_workflow_states.py` -- the four user-facing workflow terminal states.
  COMPLETE, STOPPED, CANCELLED and FAILED must stay distinct; in particular a
  graceful "Stop after current cycle" is STOPPED, keeps its completed results,
  says so in the execution log, and leaves the Jana2020 hand-off available --
  it is never reported as a cancellation.

- `test_wizard_models.py` -- the Wizard's SharpED model list. The list is
  fetched automatically when a SharpED page is entered (never for Superflip
  only), exactly once, asynchronously, and cached for the session; an explicit
  user choice survives a refresh; the resolved server default is shown while
  the internal `default` sentinel is preserved; a failure stays concise with
  Refresh models still available. The server is stubbed, so the request count
  itself is asserted.

## Adding a new golden regression test

`test_sharped_bridge.py` tests the temporary metadata/inference split, separate
compatibility state, disabled unsupported selections, exact DEFAULT resolution,
job-host confinement, authentication/redaction, and future unified deployment.
It uses mocked HTTP transport and real client/Qt code; no live token is needed.

1. Build a small, fully hand-verifiable fixture (few reflections/cycles,
   not a large randomized one) so a human can sanity-check the pinned
   expected values, not just trust whatever the code currently produces.
2. Run the function once, print its real output, and pin that exact value
   -- do not hand-derive an expected value separately from what the code
   actually computes; the point is to catch *future* drift, not to
   re-verify the algorithm itself.
3. Prefer testing pure functions directly (no `QApplication` required)
   where possible; this project's dialogs mix a fair amount of scientific
   logic into Qt-bound methods, so a widening set of pure, directly
   testable functions is itself a maintainability goal, not just a testing
   convenience.
