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

## Adding a new golden regression test

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
