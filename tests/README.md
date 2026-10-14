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


- `test_sharped_api_contract.py` -- standard-library unittest coverage proving
  that model discovery and the complete authenticated lifecycle use the same
  historical base URL, preserve token headers, resolve DEFAULT historically,
  and never route a custom server request to a hidden production host.

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

- `test_metric_legends.py` -- all four profile-driven three-tab layouts,
  direction labels, Superflip/SharpED series, and deterministic legends.

- `test_jana_completion.py` -- the shared profile-aware result selector in
  Jana2020 and standalone contexts: automatic completion/graceful-stop open,
  all four column sets, absence of Selection score, matching recommendations,
  and the standalone Save map and model action.

- `test_input_context.py` -- pure and GUI-bound guards for the resolved input
  boundary: External/embedded HKL, active versus stale Jana `.inflip`, metadata
  precedence, reference/initial models, captured `RunConfig`, QSettings
  compatibility, and Jana-versus-standalone handoff eligibility.

- `test_map_quality.py` -- pure periodic-map metrics, immutable validation
  data, all four profiles, and exact source-neutral lexicographic ranking.

- `test_requirements.py` -- pure shared preflight checks: executable identity,
  wrapper-safe Jana auto-detection, conditional requirement sets, safe official
  ZIP extraction, SharpED reachability/authentication classification, and token
  redaction.

- `test_preflight_ui.py` -- click-driven Qt coverage from the full window's
  Run phasing button and every Jana Wizard run path. It verifies the three
  dedicated remediation dialogs, silent success, repair/re-check/resume,
  settings synchronization, and Skip semantics.

- `test_wizard_geometry.py` -- the Jana2020 Wizard's window geometry: the
  preferred width is substantially wider than the old narrow layout, always
  clamped inside the available screen at 1920x1080 / 1600x900 / 1366x768,
  the header and footer stay outside the scrollable body, and every main step
  keeps one stable outer window geometry while only the body scrolls.

- `test_workflow_states.py` -- the four user-facing workflow terminal states.
  COMPLETE, STOPPED, CANCELLED and FAILED must stay distinct; in particular a
  graceful "Stop after current cycle" is STOPPED, keeps its completed results,
  says so in the execution log, and leaves the Jana2020 hand-off available --
  it is never reported as a cancellation.

- `test_wizard_models.py` -- the Wizard's SharpED model list. The list is
  fetched automatically when a SharpED page is entered (never for Superflip
  only), exactly once, asynchronously, and cached for the session; an explicit
  user choice survives cycle changes and refreshes; the live catalog drives
  the canonical one-cycle and multi-cycle recommendations; a failure stays
  concise with Refresh models still available. The server is stubbed, so the
  request count itself is asserted.

- `test_requirement_dialog_scaling.py` -- SharpED/EDMA remediation-dialog
  frame and button bounds at 100%, 125%, and 150% scaling.

- `test_edma_threshold.py` -- the per-map automatic EDMA threshold
  (`phase_studio/edma_threshold.py`). Deterministic synthetic fixtures stand in
  for EDMA: a known structure whose atoms appear as the threshold drops, plus
  noise peaks below a defined onset. It covers:
  - the noise-onset plateau, where the lowest pre-noise threshold is chosen;
  - different maps selecting different thresholds;
  - the composition constraint, the placeholder-composition gate and the
    no-composition case;
  - the genuine holdout: corrupting only work reflections cannot change the
    decision;
  - reference independence through the real app integration, with EDMA
    patched out;
  - fallback, cache and user stop.

- `test_element_colors.py` -- the one period-based element-colour authority
  (`app.element_color`). It checks:
  - all 118 elements get a valid, deterministic colour, and period metadata
    is correct, including the f-block;
  - same-period elements are not identical, and neighbours and the required
    pairs are distinguishable (CIELAB ΔE);
  - every colour is readable on white and none is near-black;
  - unknown labels get a neutral fallback;
  - the renderer, preview, Autosolve and legend use the same authority, and no
    element-to-colour table exists.

- `test_wizard_text_clipping.py` -- no Jana Wizard tile, input-summary or
  warning text is cropped before or after the deferred `.inflip` input-summary
  population, including descender strings. Each check runs in a child process
  at QT_SCALE_FACTOR 1, 1.25 and 1.5, on a synthetic `.inflip` shaped like a
  real job. It also checks identical paired-tile geometry and visible tile
  icons.

## Adding a new golden regression test

`test_sharped_api_contract.py` proves model discovery, upload, polling, and
download all derive from one configured base URL, with the historical token
headers and DEFAULT resolution. It uses mocked HTTP transport; no live token is
needed.

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
