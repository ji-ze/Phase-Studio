# Execution window acceptance — 2.0.5

Date: 2026-10-18. Version remains 2.0.5. Existing unrelated edits were retained. No release EXE, commit, push, tag, paid inference or live Jana publication was performed.

## Architecture inspected

- `autosolve_window.AutosolveWindow` owns the dual Matplotlib canvas, independent cycle controls, per-panel camera memory, metadata rows, compact/expanded log and fixed footer. It reparents the existing backend's log and progress widgets rather than duplicating them.
- `app.IterativeSuperflipPipelineQtGUI` owns RunConfig/PipelineState, run-scoped queued events, cycle execution, operation lifetimes and completed CycleResults. Superflip subprocess management and SharpED upload/poll/download remain in their existing authorities.
- `_run_pipeline_cycles` submits Superflip-map EDMA and the primary SharpED call as sibling branch-executor tasks after the map closes. Each EDMA branch emits a run-scoped StructureJobUpdate immediately. GUI `_poll_queue` validates run, cycle, source, generation and map/structure hashes before publishing `_live_structures`. Whole-cycle completion is separate.
- Interactive EDMA uses `review_edma.ReviewEdmaExecutor`, request generations and isolated output directories. Candidate identity includes run/source/cycle/map hash; threshold forms the cache identity. Completion promotes a canonical content-addressed structure and updates its model/composition atomically. Stale requests and earlier runs are rejected. No scheduling or numerical code was changed.
- `ResultSelectionDialog`, `candidate_selection`, `_start_jana_handoff` and `perform_jana_handoff` remain the final selection/validation/publication authorities. Execution-window browsing is inspection; the user makes the final source/cycle/threshold choice in Result Selection.

## Confirmed defects and corrections

The screen examples demonstrate that a running cycle may legitimately coexist with completed structures from an earlier cycle. They do not demonstrate that those structures are scientifically mismatched or that EDMA was serialized. Source inspection confirmed existing independent branches and generation/hash guards.

The actual UI inconsistency was that a valid live EDMA structure could already be displayed while its cycle was absent from the navigation list until the entire cycle was recorded. A run-scoped per-source completed-panel cache now makes these validated live completions browsable immediately. Latest still follows the backend's latest usable source-specific completion. Manual cycle selection remains pinned as newer completions arrive. The cache clears on a new run and removes missing structure files. It is a presentation cache, not a new handoff authority.

Completed-result captions now explicitly distinguish the displayed source/cycle/model/seed from the currently running workflow cycle. Pending EDMA captions no longer misleadingly label a manually selected result as Latest. Caption space is reserved above the axes. Candidate-specific threshold, EDMA site count and ASU composition remain sourced from the same selected panel. No input composition is substituted.

Empty states now explain Running Superflip, Waiting for Superflip, map ready/EDMA running, SharpED uploading/processing/downloading and cancellation/failure. The explanatory text is centered and more readable. Actual existing progress events supply upload/download phases; no SharpED start is inferred from a mere pending map. Server-completed progress remains “Processing” until a validated structure arrives, because it may describe a tile rather than the reconstructed map.

Cycle controls now adjust to their contents and reserve enough text width, fixing the clipped “Cycle 1” label found during capture review. Fit/fullscreen require a real structure. Threshold controls remain unavailable for live-only panels until a recorded candidate exists for the EDMA review authority.

## Rendering, progress and logs

The existing renderer already uses a projected-content fit with 0.80 target fill, viewport clipping, per-axis content bounds, independent camera memory and compatible-update preservation. These mechanisms passed compact/elongated/dense rotation and geometry tests and were retained. No atom coordinates, bonds, symmetry expansion or camera scale were changed as a layout shortcut. Short screens necessarily reduce canvas height to preserve metadata, progress and footer. Both Fit operations still fit each panel independently.

Overall text now reflects the same completed-cycle counter as the overall bar, rather than leaving a stale “0 of 3” label. Only completed-cycle events advance that count. Concurrent active operations remain individually listed; unknown duration remains indeterminate. Actual Superflip repeat numerator/denominator remains the third progress level.

Existing compact-log classification already writes the full diagnostic record before filtering paths/commands/details, deduplicates repeated statuses and suppresses misleading tile-level reconstruction completion. This infrastructure was reused unchanged. Expand log retains a bounded log height and Open log remains attached to the existing detailed project-local log. Expanded-log captures preserve progress and footer. The synthetic capture log intentionally contains only fixture lifecycle events, not a real scientific history.

## Handoff safety decision

**Early handoff is explicitly prevented in the ordinary Superflip + SharpED execution window while the workflow is RUNNING.** The disabled button explains: “Wait for completion, or stop the workflow before choosing a completed result.” Its handler also refuses programmatic invocation during an active run. Existing Cancel/stop cleanup remains authoritative; no subprocess or poller is abandoned to publish a result.

After workflow completion/termination, the existing Result Selection path remains available for completed candidates. Pending review EDMA prevents handoff until the requested result is complete. Clicking with no coherent validated candidate emits an actionable warning instead of silently doing nothing. Preview data and live-only panels never become publication candidates through the new presentation cache. The separate experimental Autosolve flow retains its established confirmation behavior; it was not redesigned here.

Final publication revalidates the exact selected map/model/threshold, uses the original Jana .inflip context, and fails on changed artifacts. It does not run new EDMA or choose another candidate on Pass. The existing maxcycles=0 map conversion is protocol serialization, not a new phasing calculation.

### m50 protocol clarification

Inspection of the working protocol and the earlier real installed-Superflip probe, documented in `RELEASE_2_0_2.md`, establishes that Superflip writes m80/m81 and **does not rewrite the valid m50 project context**. The current handoff captures and validates the nonempty canonical project m50 and publishes it under the required output basename. Its hash must match the captured context. This is the recorded Superflip-only reference behavior, not a shortcut to avoid updating a model. Atomic sites come from the exact EDMA m40. Inventing new m50 bytes would violate the verified protocol; no such change was made.

### Exact automated handoff evidence

The 192 Jana completion checks passed, including canonical m50 selection rather than an empty `_Superflip` alias; threshold 0.30 model differing from 0.50; handed-off model hash equal to selected preview candidate hash; selected map and threshold-specific m40 feeding their respective protocol sides; exactly one map conversion; matching published m80/m81; all required protocol roles in an immutable audit snapshot; exact live-byte/snapshot parity; separate snapshots for later passes; second-run identity isolation; and safe failure on a mutated candidate. These controlled tests are not a new manual acceptance inside a live Jana2020 GUI.

## Verification

| Check | Result |
| --- | --- |
| Complete pytest suite | **393 passed, 1 skipped, 37 subtests passed, 0 failures** (369.00 s) |
| Focused execution/selector/viewer pytest | 15 passed, 0 failures |
| Workflow state checks | 141 passed |
| Review EDMA checks | 20 passed |
| EDMA threshold checks | 49 passed |
| Execution logging checks | 16 passed |
| Scientific golden checks | 46 passed |
| Jana completion checks | 192 passed |
| Python compilation and git diff --check | Passed; inherited LF/CRLF warning only |

Counts overlap and must not be summed. The skipped test is the existing opt-in real-project feedback check. An initial focused test still expected the formerly enabled early-handoff button after EDMA completion during RUNNING; it was updated to assert the required safe refusal and availability after STOPPED. The final focused run passed. Final caption and control-width refinements were additionally covered by the focused execution/three-scale geometry tests.

AST preservation evidence confirms all **556 other engine functions/methods unchanged**, including cycle scheduling, scientific functions and Jana protocol. Only engine initialization of display-phase metadata, active-operation labels and GUI progress-state application changed. `build/acceptance-execution-2.0.5/preservation.json` records this comparison and screenshot hashes.

Logs are `build/execution-{focused-final,selector-focused,full-suite,scientific,jana,workflow,review-edma,edma-threshold,log-checks,capture,preservation}-205.log`, plus capture logs for 125% and 150%.

## Visual evidence

`build/acceptance-execution-2.0.5/scale-1/` contains ten final actual Qt captures:

1. `01-cycle1-superflip.png` — empty structures with truthful running/waiting states.
2. `02-superflip-edma-ready-sharped-processing.png` — independent left completion before right result.
3. `03-cycle2-both-completed.png` — both completed source streams.
4. `04-cycle3-displaying-cycle2.png` — active cycle 3, completed cycle 2 structures.
5. `05-manual-older-candidate.png` — left pinned to 1, right follows Latest 2.
6. `06-threshold-change-pending.png` — previous completed structures/metadata retained.
7. `07-all-cycles-completed.png` — complete workflow and final candidate availability.
8. `08-expanded-log.png` — expanded log without hidden progress/footer.
9. `09-early-handoff-safely-disabled.png` — active-run handoff unavailable.
10. `10-narrow-display.png` — 1280×800 logical window.

`scale-1.25/` and `scale-1.5/` retain cycle-3 and narrow-window captures, giving **14 PNGs** total. All are visibly marked **SYNTHETIC EXECUTION STATE — OFFLINE UI FIXTURE — NO SCIENTIFIC RUN / JANA PUBLICATION**. The workers exercised all states at each scale; JSON records logical dimensions, DPR and projected fit. These screenshots were visually inspected for captions, control readability, overlap and footer visibility. Controlled Qt scaling is not physical mixed-monitor acceptance.

## Files and limitations

Changed in this pass: `phase_studio/autosolve_window.py`, GUI-only portions of `phase_studio/app.py`, `tests/test_execution_redesign.py`, new `packaging/tools/capture_execution_acceptance_205.py`, the obsolete early-confirmation capture in `packaging/tools/capture_execution.py`, and this report. Prior dirty files were preserved.

No live SharpED request, new real-project scientific computation or live Jana GUI handoff was performed. A manual acceptance with installed Jana remains necessary. The screenshot maps are deliberately non-scientific identity fixtures and are never published; actual protocol consistency is covered by the separate handoff tests. Early Pass is intentionally unavailable during ordinary workflow execution; users must wait or stop first, then choose the completed result. Scientific algorithms, outputs and golden references remain unchanged.
