# Map Feedback diagnostic restoration and split Result Selection

Phase Studio 1.0.10 is a focused feature release on top of stable 1.0.9. It
restores a historical diagnostic, splits the shared Result Selection dialog by
result source, and bumps the canonical version. No scientific computation
changes: Superflip, SharpED, EDMA, HKL parsing, Map Feedback's own
calculations, R_free/OMIT, the three existing profile metrics, and ranking
order are all unchanged.

## What changed

### 1. Version bump to 1.0.10

`phase_studio/version.py` is the single canonical source; every runtime
surface (window titles, splash/about, CLI `--version`, the Windows EXE
file/product version resource, the MSIX package version, the Jana2020
integration marker, error dialogs, HKL/FCF export headers) derives from it.
The public artifact filenames, which are plain string literals rather than
derived values, were updated by hand in the build script, the PyInstaller
spec, the distribution-verification tool, and the pinned test assertions:

- `dist/release/PhaseStudio-1.0.10-x64.exe`
- `dist/release/PhaseStudio-Jana2020-Installer-1.0.10-x64.exe`

Upgrade compatibility with 1.0.9 installations and settings is preserved —
nothing about the settings schema, `.inflip` handling, or integration marker
format changed.

### 2. Restored Map Feedback change metric

Before the Workflow Metrics UI was standardized to exactly three displayed
metrics (commit `3b63e41`), a "Mean intensity change (%)" tab existed for Map
Feedback's intensity correction step. Git history showed **two** historical
percentage-change metrics that coexisted at removal time — one for intensity
correction (`intensity_correction_avg_change_percent`), one for powder overlap
repartitioning (`powder_repartition_avg_change_percent`), both literally
titled "Mean intensity change (%)" but measuring different things. After
review, only the **intensity correction** metric was restored, gated
specifically by the "Enable intensity correction" checkbox
(`map_feedback_intensity_enabled`) — not by missing-reflection completion or
powder repartitioning, and not the powder-repartitioning metric.

The restoration is presentation-only: `CycleResult.intensity_correction_avg_change_percent`
was already computed every run and already written to `metrics.csv`; only the
dedicated tab and Result Selection column had been removed. Recovered
semantics, unchanged from the historical implementation:

- Per corrected reflection: `|corrected_intensity − observed_intensity| / observed_intensity × 100`
  (unsigned percentage), averaged across all reflections Map Feedback actually
  corrected that cycle.
- Computed once per cycle (not per source); the same figure is shown on both
  the Superflip and SharpED rows of a given cycle.
- Lower is better; the value lags one cycle behind the correction that
  produced it (it describes the correction feeding *into* that cycle).

Displayed as a 4th Workflow Metrics tab and a 4th Result Selection table
column, both hidden/absent when intensity correction is off. It is diagnostic
only: `recommend_best_result` never reads it, so automatic recommendations for
identical scientific results are byte-for-byte unchanged whether or not this
metric is visible.

### 3. Split Result Selection by result source

Superflip and SharpED candidates were previously one flat table with a
"Source" column and one shared recommendation/selection. They are now two
independent views, switched by a compact segmented control (reusing the
existing `metricsViewToggle` visual language) shown only when both sources
have usable candidates:

- Separate candidate tables (no more "Source" column — each table is already
  source-specific).
- Separate recommendations, each computed by the same unchanged
  `recommend_best_result` ranking, called once per filtered candidate list —
  no new ranking subsystem, no SharpED bonus, no later-cycle bonus.
- Separate remembered manual selections; switching sources never overwrites
  the other source's pick.
- The final action (`Pass to Jana2020` / `Save map and model`) always
  operates on whichever candidate is selected in the currently visible
  source — switching source never happens implicitly.
- A source with no usable candidates (or SharpED disabled for the run) hides
  its tab/switch entirely rather than showing an empty table. `cfg.run_sharped`
  gates this on top of candidate presence, since a disabled SharpED run still
  leaves a placeholder `deblur_map` copied from Superflip.
- Compact inline warnings (not modal): SharpED always carries a
  neural-network-validation warning; Superflip carries a Map Feedback warning
  only when intensity correction is enabled; SharpED with intensity correction
  on shows one combined callout instead of two.

## Verification

All 19 automated test files (a mix of `unittest`/`pytest` and this project's
existing script-style `check()`/`main()` tests) pass, totaling 906 individual
checks — no scientific regression:

- `tests/test_map_quality.py`, `tests/test_split_distribution.py` — unchanged
  ranking behavior; version/artifact-name assertions updated to 1.0.10.
- `tests/test_jana_completion.py` — extended in place for the split dialog:
  independent per-source tables/recommendations/selection persistence,
  active-source-at-click-time handoff and save, single-source-only and
  `run_sharped=False`-with-a-populated-candidate edge cases, all four warning
  combinations, and the 4th column's presence/absence and `—` fallback. All
  pre-existing Jana handoff, standalone save, CSV, and report checks
  (including the pinned metrics.csv schema) pass unchanged.
- `tests/test_metric_legends.py`, `tests/test_ui_hierarchy.py` — updated for
  the always-present-but-conditionally-visible 4th Workflow Metrics tab
  (3 visible with Map Feedback intensity correction off, 4 with it on); added
  coverage that the 4th tab plots the cycle-level diagnostic correctly and
  toggles visibility live with the checkbox.
- Every other existing test file (Wizard geometry/models, SharpED API
  contract and map scaling, workflow states, requirements/preflight,
  scientific core, process launch, model formats, input context, wheel
  safety, performance) passes unchanged.

## Remaining manual acceptance

Not yet performed as part of this change: a real GUI pass at 100%/125%/150%
Windows display scaling with 1/2/4/10/30 candidates per source; an actual
Superflip+SharpED run exercising the restored metric and split dialog
end-to-end (only offscreen/fixture-driven tests were run); rebuilding the
standalone and Jana2020 installer EXEs and MSIX with the 1.0.10 version; and
signing/clean-machine trust checks, consistent with 1.0.9's own remaining
acceptance items.
