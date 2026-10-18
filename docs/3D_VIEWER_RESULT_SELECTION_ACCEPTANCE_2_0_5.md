# 2.0.5 viewer and Result Selection acceptance

Recorded 2026-10-18. Evidence remains local in build/acceptance-3d-viewer-2.0.5; scientific datasets and generated screenshots are not release source assets.

## Camera and interface

The shared controller uses a virtual sphere and proper 3x3 rotation matrices, adapted to Matplotlib elevation/azimuth/roll. Screen-space tests verify drag direction through poles and azimuth wrapping. Raw motion is coalesced on a 16 ms timer; release flushes the final endpoint. Artists and geometry remain reusable during movement. Right/middle/Shift-left pan, wheel zoom, double-click Fit, F/R and fullscreen shortcuts remain supported. Camera ? Invert mouse rotation defaults off and persists under viewer/invertMouseRotation in the existing PhaseStudio user settings. Automatic rotation pauses for interaction and two seconds afterward, and stops while hidden or inactive without clearing the user preference.

The candidate table starts at 28% width and persists user resizing. Metric help is compact and anchored to the table; double-click opens complete scientific definitions. Detached titles identify the selected family and cycle. The live widget is reparented and restored, preserving candidate/threshold/camera identity. A native Qt show hang caused by moving the Fullscreen button between existing layouts was resolved by creating it directly in its final layout.

## Matched real-draw measurements

QtAgg CPU rendering, 40 actual draw frames per row. These are local microbenchmarks, not monitor refresh rates or a GPU claim. Before/after selector modules share the same optimized geometry builder to isolate removal of redundant per-frame fitting. Timing varies with host load.

| Scene | Mode | Atoms | Median before ms | Median after ms | p95 after ms |
|---|---|---:|---:|---:|---:|
| small | molecule | 2 | 1.88 | 0.87 | 1.00 |
| small | cell | 4 | 1.98 | 1.01 | 1.14 |
| dense | molecule | 280 | 4.78 | 3.29 | 3.46 |
| dense | cell | 320 | 4.86 | 4.26 | 4.49 |
| large | molecule | 800 | 8.26 | 7.12 | 7.37 |
| large | cell | 1400 | 14.50 | 11.59 | 11.87 |
| ochlor-real-edma | molecule | 21 | 2.18 | 1.18 | 1.37 |
| ochlor-real-edma | cell | 104 | 2.98 | 1.93 | 2.09 |

The separate instrumented benchmark records allocations, CPU time and timer latency. Its tracemalloc overhead must not be interpreted as native interaction speed. An initial empty ochlor reference in that instrumented run is not a valid model performance measurement; the selector benchmark uses an existing EDMA CIF with 21 molecule-display atoms and 104 full-cell atoms. Complete-molecule mode retains the established component selection and 800-site limit; full-cell mode retains all 1,400 sites in the large fixture. No new decimation is used.

## Connectivity and scientific safeguards

Minimum-image connectivity batches the same 27 neighbours with NumPy using O(N) working memory, retaining scalar handling for near ties and cutoffs. Nine old/new orthogonal and skew-cell cases have identical graphs, metadata and displayed coordinates. Boundary-crossing pairs/chains, separate molecules and special-position symmetry deduplication have explicit tests. The viewer does not write scientific coordinates. Source hashes and geometry hashes match in every paired benchmark row. Maps, EDMA thresholds, candidate ranking, export normalization and Jana handoff computations are unchanged by this viewer pass.

## Verification

- Full suite before subsequent Autosolve remediation: 406 passed, 1 skipped, 37 subtests, 360.36 s.
- Final focused camera/execution tests: 28 passed.
- Actual fullscreen script completed successfully after the native Qt fix; Result Selection script: all 72 checks passed.
- Scientific golden checks: 46 passed; Jana checks: 192 passed; EDMA review: 20 passed.
- Periodic old/new parity: 9 cases passed.
- Ten actual Qt screenshots were inspected, including compact tooltip, detached molecule/cell, boundary molecule, 1,400-site full cell, pending threshold and 125%/150% variants. They are controlled fixtures, with synthetic metrics/map identities and no Jana publication. Missing Jana models correctly disable Pass.

## Remaining acceptance

Offscreen captures use controlled logical screen geometry; they do not certify physical multi-monitor/DPI behavior. Native Windows mouse interaction, actual Jana acceptance and a newly frozen executable require separate manual acceptance. No paid inference, new scientific run or EXE build was performed for this viewer pass. Later Autosolve model changes are documented separately.
