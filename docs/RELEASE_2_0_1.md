# Phase Studio 2.0.1

2.0.1 turns Autosolve into a guided release built on the stable 2.0.0 code.
Both Autosolve goals now share one phase search. Autosolve generates one
**Predicted structure**, lets the user tune it in an **initial tuning**
stage, then runs one model-seeded five-cycle refinement block. Only after
that does **Final Review** open, where both **Observed data** and
**Predicted structure** are independently tunable, recalculable and can be
passed or saved.

Unchanged:
- the Advanced *Phase recycling with Superflip + SharpED* workflow (ordinary
  loop, user-controlled settings);
- the Professional *1st Superflip, then SharpED (beta)* method
  (`sharped_recycle`);
- every scientific algorithm.

## Exact SharpED models

| Stage | Model (exact string) |
|---|---|
| Common phase search | `koala phase boost 2` |
| First Predicted structure and every refinement cycle | `koala model progressive` |

- **Preflight.** Both names must be in the live SharpED catalog. The check
  reuses the one public request preflight already makes; no extra request is
  added.
- **No substitutes.** Matching is exact. There is no fuzzy match and no
  fallback to the server default, to another koala model, or to
  `koala phase boost` without the `2`.
- **Failure.** If either model is missing, Autosolve does not start, and the
  message names the missing model.
- **Provenance.** Every completed result stores the exact model it used, in
  `CycleResult.sharped_model` and in `autosolve_result_provenance.json`. Each
  SharpED submission is preceded by an explicit `[SharpED] Model: <name>` log
  line, so the model actually used is never ambiguous from the log alone.

## Shared phase search

Both goals, *Solve the phase problem* and *Predict the structure model*, run
the same ordinary per-cycle loop. Each cycle runs:

1. Superflip.
2. EDMA on the Superflip map at **1.0 σ**, giving the Observed data
   candidate.
3. SharpED with `koala phase boost 2`.
4. EDMA at **1.0 σ** on that map. The resulting **structure** becomes the
   next cycle's Superflip initial model.

Both sides of the shared search use the same 1.0 σ default (previously 1.0 σ
Superflip / 2.0 σ SharpED); the generated EDMA input's `plimit` line and the
recorded `CycleResult.superflip_edma_sigma` / `deblur_edma_sigma` confirm it
each cycle.

**Feed-forward.** The SharpED map's EDMA **structure**, not the raw map,
becomes the next Superflip initial model (the existing `deblurred_edma_cif`
mode). A regression test reads the generated Superflip input and the actual
prepared CIF's atoms to prove it.

**Budget.** The established budget is unchanged: 10 cycles, +5 while the last
block improves. The search is ranked on the Observed data for both goals. The
old automatic Option B Map Feedback stage is replaced by the user-initiated
correction described below.

## Predicted structure and the two review stages

- **Observed data.** The best completed Superflip result, chosen by the
  existing profile-aware ranking.
- **Predicted structure.** After the search, SharpED runs exactly once with
  `koala model progressive` on the best Observed data map, then EDMA at
  1.0 σ. Its EDMA input/log is explicitly labelled "Predicted structure map"
  (never "Superflip map"), and it is assessed with the same map-quality
  sequence a cycle uses. Phase-boost output during the search is never
  called a Predicted structure.

**Stage A — initial Predicted-model tuning.** Immediately after the first
prediction, Autosolve enters a tuning stage, not Final Review:

- Observed data is shown **read-only**, for comparison only -- no threshold
  controls, no Recalculate, nothing to pass.
- Predicted structure exposes **+ atoms**, **- atoms** and **Refine 5
  cycles** only -- no Pass to Jana2020 / Save yet.
- There is **no Jana2020 handoff available anywhere** during the shared
  search, the first prediction, or this tuning stage: the (now removed)
  global footer "Pass to Jana2020" button no longer exists in the guided
  view, and no panel offers it yet either.

**Refine 5 cycles** takes the Predicted structure's *current, tuned*
structure and threshold and uses it as the seed for the first refinement
block (see below). Once that block finishes, Autosolve enters:

**Stage B — Final Review.** Both panels become independently tunable, each
with all four actions: **+ atoms**, **- atoms**, **Recalculate**, and
**Pass to Jana2020** (or **Save map and model** standalone). This is the
first point at which a result can be passed or saved. Observed data starts
at 1.0 σ; the Predicted structure keeps whatever threshold the refinement
was actually seeded and run at (never silently reset to a hard-coded
default).

## Threshold controls

Both panels, in whichever stage exposes them, share one policy:

- **Default:** 1.0 σ on both sides.
- **Range:** 0.3–3.0 σ (previously 0.6–3.0 σ).
- **Variable step:** 0.2 σ at/above 0.8 σ, 0.1 σ below it, so the sequence
  going down from e.g. 1.4 σ is `1.4, 1.2, 1.0, 0.8, 0.7, 0.6, 0.5, 0.4,
  0.3` and going up from 0.3 σ is `0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0, 1.2,
  … 3.0`. Values are kept exactly on the 0.1 σ grid (no floating-point
  display drift).
- **+ atoms** lowers the threshold (more peaks survive); **- atoms** raises
  it (fewer peaks survive) -- unchanged semantics.
- At a bound, the button that would leave the range is disabled rather than
  silently doing nothing.

**Threshold steps rerun EDMA only.**
- Each click costs Superflip 0, SharpED 0, EDMA 1, with no SharpED split,
  upload or download.
- The canonical map is unchanged (its SHA-256 is checked in tests).
- Only one EDMA recalculation runs at a time across both panels (the shared
  EDMA executable is treated as single-worker); every panel action is
  disabled while any panel is busy, so the UI never shows a mix of
  active/disabled controls that looks accidental.
- The structure, atom count, composition and preview update after each
  step. The map itself never changes.

## Refinement

Both **Refine 5 cycles** (tuning stage) and **Recalculate** (Final Review)
start the same mechanism: the pressed panel's *current* structure, at its
*current* threshold, seeds a five-cycle refinement block:

- the first cycle's Superflip initial model is exactly that structure (a
  hash/content-identity test proves the actually-prepared
  `current_modelfile.cif` derives from the selected candidate, not from a
  stale default-threshold structure or the previous cycle's own output);
- every SharpED call in the block uses `koala model progressive`, never
  `koala phase boost 2`;
- every structure fed forward inside the block is extracted at the
  captured `refinement_edma_threshold_sigma`, fixed for the whole block;
- the Observed-data side of the block keeps the standard 1.0 σ.
- The first cycle's log names the real seed explicitly --
  `[Refinement seed] Predicted structure · Cycle N · EDMA X σ` -- instead of
  the misleading "from cycle 10" wording a plain per-cycle feed-forward
  label would otherwise show. From the second cycle on, the usual
  previous-cycle description resumes.
- While a block runs, the last completed Observed/Predicted results stay on
  screen (never blanked, never a partially written file), and the seed's
  source/cycle/threshold is shown in the running status so it is visibly
  the user's chosen structure, not a reverted default.

**Automatic +5.** After a block, another five cycles start only if the
goal's own stream strictly improved, using the existing lexicographic
ranking:

- Observed data for *Solve the phase problem*;
- Predicted structure for *Predict the structure model*.

Ties resolve to the earlier cycle; an unavailable primary metric is never
treated as an improvement. Otherwise Final Review opens (or re-opens,
unchanged, if already there). The existing Cycles maximum (999) is the hard
bound -- refinement never starts a block that would exceed it.

## Handoff and save (Final Review only)

Both actions reuse the established authority, shared as
`_start_jana_handoff`. That authority receives the panel's cycle, canonical
map, current-threshold structure and SharpED provenance.

- The Jana2020 protocol is unchanged: the selected map goes to Jana2020, and
  m80/m81 are derived from it by Jana's Superflip call, as before.
- The current-threshold structure is recorded in the provenance file and in
  the map-quality report.
- Standalone Save copies the current map/model pair and can never enter the
  handoff.
- There is exactly one handoff mechanism on screen: the panel's own action.
  The 2.0.0-era global "Pass to Jana2020" footer button is gone from the
  guided view entirely (its backend orchestration remains available for
  direct/automated use, but nothing in the UI calls it).

## Measured-data correction

Using the existing eligibility and configuration, Final Review offers one
of:

- **Powder repartitioning**, for FWHM data with a resolvable wavelength;
- **Correct suspect intensities**, for other data.

Clicking either first shows an explicit confirmation dialog naming the
correction and stating that the original measured data are retained; the
correction only runs if the user confirms ("Cancel" / "Correct intensities"
or "Repartition intensities"). Once confirmed, the phase search continues
on the corrected data from the next cycle, and a new Predicted structure is
generated (returning to the tuning stage). The original measured reflection
file is never overwritten, and the provenance file records that measured
data were modified and which routine ran.

## Progress presentation

- **Review states show no stale process line.** Entering either review
  stage clears the cycle/stage row to a plain "Review"; the previous
  "SharpED · downloading" / "Stage N of M" text (left over from the last
  real cycle event) no longer lingers once review begins.
- **EDMA-only recalculation** shows only that operation, e.g. "Predicted
  structure · EDMA 0.7 σ · recalculating structure…" -- never a SharpED
  line, since SharpED does not run.
- **Refinement** shows "Refinement cycle N of 5" (and "block 2 (the
  solution improved)" once an automatic extension starts), plus the seed's
  source/cycle/threshold.

## Failures

- A failed first prediction keeps the completed search; **Retry** reruns
  only the prediction.
- A failed threshold step keeps the previous structure/threshold; the panel
  shows an inline error instead of losing state.
- A failed refinement cycle resumes through the existing Continue
  checkpoints, reusing every already-completed stage.

## Measured performance

Measured with the real EDMA on koala2, cycle 5 (illustrative step sizes; the
actual variable-step sequence used in the guided UI is 0.2 σ at/above 0.8 σ
and 0.1 σ below):

| Operation | Time | Result |
|---|---|---|
| Observed data, one EDMA-only step | ~11.3 s | threshold change reproduces the expected atom count at each step, map unchanged |
| Predicted structure, one EDMA-only step | ~11.1 s | threshold change reproduces the expected atom count at each step, map unchanged |
| Parse and composition update | ≤ 0.01 s | — |

The first prediction and the refinement blocks depend on the live SharpED
server and on the dataset. They are measured at manual acceptance.

## Scientific guardrails

Unchanged:
- Superflip, SharpED transport, the EDMA algorithm;
- HKL handling, normalization, R_free, OMIT;
- validation formulas and ranking;
- Map Feedback, powder and intensity-correction mathematics;
- the Jana protocol.

The scientific golden suite and the split-distribution scientific baseline
pass unchanged.

## Acceptance status (automated)

- **Tests.** 35 test files, **1,750 checks**, all passing. The pre-
  correction-pass baseline was 35 files / 1,732, and no check was removed.
  `test_autosolve_guided.py` (139 checks) was rewritten against the real
  ordinary cycle loop, the real Superflip/EDMA input writers, and a fake
  SharpED transport that inspects the actual multipart request body's model
  field (not GUI labels or RunConfig fields), behind an offline guard.
  Collateral tests elsewhere in the suite that pinned the removed footer
  button or the pre-correction threshold defaults were updated to match
  (`test_autosolve_window.py`, `test_autosolve_window_routing.py`,
  `test_action_footer_widths.py`, `test_jana_wizard_tile_icons.py`,
  `test_ui_copy.py`).
- **Scientific goldens.** `test_scientific_core.py` 41/41; the
  `test_split_distribution.py` scientific baseline (including its AST-level
  frozen-function comparison against `main`) passes.

**Artifacts.** Clean build from `9f8186b`, into `dist/rc4/release/` (an
installer instance manually launched from Explorer at 14:22 still held
`dist/release`, the same situation documented for the 2.0.0 acceptance pass;
it was left running rather than killed). All three distribution checks pass.

| | Size (bytes) | SHA-256 |
|---|---|---|
| `PhaseStudio-2.0.1-x64.exe` | 80 379 658 | `FC5AFB5C91E2846A86EE6C9277C6DBAF2845F07251F9ACF4B6A35236B13C0429` |
| `PhaseStudio-Jana2020-Installer-2.0.1-x64.exe` | 128 569 883 | `C3A439B51E473ECAD3AD8DC6B16DBCE98FE9413CFB5CBB24FB71DD36745A9F87` |

Both are x64 (0x8664), FileVersion/ProductVersion 2.0.1, and NotSigned.

**Defender** (platform 4.18.26080.4, engine 1.1.26080.3, signatures
1.459.378.0, real-time protection on, no exclusions):
- local scans are clean;
- internet-marked (ZoneId=3) copies are clean;
- a real browser download was **not performed**, so the 1.0.9 cloud-ML
  detection is not shown to be fixed.

**Frozen smoke** (real screen captures of the rebuilt EXEs):
- **Standalone:** splash 0.29 s, main window "Phase Studio 2.0.1" 3.96 s.
- **Installer:** splash 0.21 s, "Phase Studio 2.0.1 - Jana2020 Integration"
  5.99 s.
- **Built wrapper:** with a real `.inflip` (`2int3total.inflip`, copied
  without its companion HKL files, so the Wizard correctly shows "Not
  available" for crystal data rather than starting a phasing run), "Phase
  Studio 2.0.1 for Jana2020" (the Wizard) appears at 9.63 s, and Cancel
  returns the wrapper's established cancel code 1.
- **All:** no console; `C:\Jana2020\SUPERFLIP\superflip.exe` is
  byte-identical before and after.
- **Not exercised in the frozen EXE:** the full Autosolve run (phase search
  → prediction → Predicted-model tuning → refinement → Final Review). It
  needs an installed wrapper, a real Jana2020 job with usable reflection
  data, and a live SharpED token -- none available in this environment. It
  is manual item M-1.

**Manual-screenshot-acceptance substitute (item 53 A-E).** Since a live
end-to-end run could not be driven through the frozen EXE, the five
requested states were instead captured by running the exact same,
just-rebuilt source tree's `AutosolveWindow`/backend classes directly (real
Qt, real code paths: `_sync_review_controls`, `_refresh_tick`, and for state
E the real `_autosolve_enter_review()` entry point, not a hand-set flag) and
taking real widget screen captures. All five match spec:
- **A -- initial Predicted-model tuning:** Observed data column has no
  action controls; Predicted structure shows exactly `+ atoms` / `- atoms` /
  `Refine 5 cycles`; no Pass/Save action anywhere; headline "Predict the
  structure model · Predicted-model tuning".
- **B -- refinement running:** headline "Refinement cycle 1 of 5 · Cycle 11
  of 15 · Superflip"; "Refinement seed: Cycle 1 · EDMA 0.7 σ" shown under
  the Predicted panel; no Pass/Save action anywhere.
- **C -- Final Review:** both panels show all four actions
  (`+ atoms` / `- atoms` / `Recalculate` / `Save map and model` in this
  standalone-context fixture); Observed data at 1.0 σ, Predicted structure
  still at 0.7 σ (the refinement threshold, not reset).
- **D -- correction confirmation:** exact required wording ("Correcting
  suspect intensities modifies the measured reflection data used by
  subsequent calculations. The original measured data will be retained for
  validation. Continue with intensity correction?") with "Cancel" /
  "Correct intensities" buttons.
- **E -- idle Final Review, no stale progress:** before
  `_autosolve_enter_review()`, the progress row read literally "Cycle 4 of
  10 · SharpED · downloading" / "Stage 4 of 6" (simulating the exact
  reported symptom); after the real entry point ran, both read "Review" /
  empty, confirming the fix.

## Manual acceptance (required before tagging)

- **M-1 Frozen Autosolve end to end.** Run on a controlled Jana2020 copy
  with a real job (usable reflection data) and a live SharpED token:
  1. Autosolve;
  2. common search (check the log for `[SharpED] Model: koala phase boost 2`
     before each submission, EDMA at 1.0 σ on both sides, and the CIF model
     feed-forward);
  3. "Generating predicted structure…", then `[SharpED] Model: koala model
     progressive`;
  4. initial Predicted-model tuning (Observed data read-only);
  5. + atoms / - atoms on the Predicted structure (about 11 s each on
     koala2-scale data; confirm no SharpED request in the log);
  6. Refine 5 cycles (confirm the `[Refinement seed] …` log line and that
     cycle 11's actual Superflip input uses the tuned structure);
  7. automatic +5 or Final Review;
  8. in Final Review, + atoms / - atoms / Recalculate on Observed data too;
  9. Pass to Jana2020 from each panel (confirm no global "Pass to Jana2020"
     button exists anywhere);
  10. the measured-data correction confirmation dialog and, once confirmed,
      m80/m81 consumption in Jana2020.
- **M-2 Real Windows scaling.** Check the Review panel actions (both
  stages) at real 100/125/150% on a 1366×768 or larger display. Qt
  1/1.25/1.5 offscreen geometry already passes.
- **M-3 Browser download.** Download both artifacts through a normal browser
  with Defender on.
- **M-4 Timings.** Measure the first prediction and one refinement block on
  the live server.
- **M-5 Installer lifecycle.** Install, update, repair and remove on a
  controlled Jana2020 copy.
