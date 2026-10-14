# Phase Studio 2.0.3 — Result Selection and scientific handoff transparency

This work follows the standing instruction that the new UI passes target **2.0.3**. The older attachment's 2.0.2 title does not change the release version. No build, commit, push, tag or publication is included.

## A. Presentation and camera correction

`phase_studio/result_selection.py` retains the existing independent source tables, recommendation authorities, candidate registry and caller-owned handoff. Its candidate table now uses a fixed 40-logical-pixel recommendation star, with a tooltip explaining that the star and the highlighted manual selection mean different things. Metric widths allow both headings and formatted numeric content; long family headings wrap. The adjustable splitter retains the existing approximately 30–35% evidence / 65–70% preview allocation when space permits.

Presentation changes are in `_build_candidate_table`, `_SourceView`, `ResultSelectionDialog.__init__`, `_apply_source`, `_sync_action_button`, `_fit_preview`, `_render_preview`, `_auto_rotate_tick`, `_preview_camera_interaction`, `_change_threshold`, and `_apply_async_threshold_result`; `recorded_edma_site_lineage` is a read-only diagnostic helper. The shared branding remains Science Gothic Regular, zero tracking, only for the Phase Studio/SharpED marks; ordinary content remains Segoe UI.

The duplicate family explanation is removed from the visible layout. The compact two-line family controls and two-row, three-column assessment grid remain. A neutral validation strip reserves the same font-derived height in both families. Conditional warnings therefore do not move the preview. The selected-result summary has a 55-pixel logical minimum and states the selected cycle, completed threshold, recorded reflection provenance, scientific map and corresponding Jana model. Model/initialization detail appears in the preview metadata instead of being repeated in the footer. ASU chemical counts use native Unicode subscripts.

The root cause of the old camera behavior was fitting a rotation-safe sphere and then measuring Matplotlib's square Axes3D drawing box. That square is smaller than the rectangular Qt canvas; the default artist clip also uses it. The shared `fit_projected_structure` authority, introduced in the preceding execution-viewer pass, now measures the displayed Cartesian atom/cell geometry against the actual resolved subplot rectangle, scales it to **78% of the limiting projected dimension**, and centers it by changing camera limits. It also clips artists to that rectangle. Atom coordinates, marker sizes, connectivity and scientific files are untouched.

Measured elongated-fixture fill is **39.0764% before → 78.0000% after**, using the actual subplot rectangle in both measurements.

The selector uses a zero-interval Qt timer after layout rather than 80/120-ms camera delays. Resize refits untouched views. Manual pan/zoom/rotation survives rerendering and resize of the same candidate and representation; manual interaction stops automatic rotation. Changing candidate, family or representation starts from the documented default 20° elevation / 35° azimuth and fits the new geometry. Explicit Fit preserves orientation; Reset restores the default orientation. Untouched automatic rotation refits at the current orientation to avoid clipping. Coincident/single-site geometry has zero spatial extent and is not artificially enlarged to fill the canvas.

Fullscreen continues to reparent the **same live selected-candidate viewer**. It does not select another result or materialize another scientific structure. The existing keyboard and mouse camera controller remains in use.

An empty family now clears the preceding family's preview and disables handoff. The async threshold review tracks pending requests by run/source/cycle/map, disables Pass and atom controls for that pending candidate, retains the completed candidate until publication succeeds, and ignores stale or foreign-candidate callbacks. A failed request retains the previous completed structure and re-enables handoff. This does not change the shared EDMA executor or its scientific arguments.

## B. EDMA / Jana scientific identity

The existing export chain is:

1. EDMA raw peaks from the selected scientific map and threshold.
2. Retained export sites and symmetry-independent ASU composition.
3. The exported EDMA CIF and its diagnostic `_site_counts.json` sidecar.
4. EDMA's composition-constrained Jana model, using the existing `numberofatoms` policy.
5. The immutable candidate-associated `.m40`, sealed with its file hash and header site count.
6. The existing transactional Jana protocol conversion, staged canonical files, validation and publication.
7. The structure consumed by Jana2020, subject to real application acceptance.

The selector shows **EDMA candidate sites** separately from **Jana model atomic sites**. Jana counts come from the existing sealed `.m40` parser, never from a peak count or a newly reconstructed model. If no readable sealed model exists, it explicitly says **Jana model: prepared during handoff**. Matching diagnostic sidecars additionally supply raw peak counts; their recorded threshold and retained CIF count must match the selected candidate before they are displayed. Missing or mismatched sidecars produce no invented raw count.

Private local-project acceptance details, scientific values, hashes and structure captures are retained locally and excluded from the public source release. Synthetic file-backed fixtures exercise the differing EDMA/Jana site counts and unchanged selected artifacts without publishing a private structure. The normal EDMA threshold, export Uiso safety limits and composition-constrained model authority remain unchanged.

## C. Metric definition audit

The actual implementation is in `map_quality.compute_map_quality`, `scaled_amplitude_metrics`, `build_weighted_triplets`, and the pipeline's `build_validation_context`.

- **R factor:** observed amplitudes are frozen original measured amplitudes (`sqrt(I)` after the existing input conversion). Calculated amplitudes are absolute Fourier coefficients of the centered full-cell map. The fitted nonnegative scale is `s = dot(Fo,Fc) / dot(Fc,Fc)`, and `R = sum(abs(Fo-s*Fc))/sum(Fo)`, over finite nonnegative pairs. This is amplitude consistency, not independent atomic refinement R.
- **Amplitude CC:** Pearson correlation of the same observed and calculated amplitude arrays, available only when the arrays have sufficient variance and at least two pairs.
- **C3:** the weighted mean of `cos(phi(h)+phi(k)-phi(h+k))` using phases from that same map FFT. The deterministic measured-data triplet set is bounded by 64 strong seeds and 50,000 triplets. Weights are products of original measured amplitudes normalized by their RMS. It is not a correlation coefficient or a refinement residual.
- **Work / holdout:** both subsets are created from the frozen original measured set before Map Feedback. Holdout HKLs are excluded from the workflow's work reflections when that validation mode is enabled. R_free retains its existing minimum of three pairs. Independence depends on actually withholding those reflections; an arbitrary imported map can still contain them.
- **Map Feedback:** may alter later workflow inputs, but does not replace the frozen comparison amplitudes. The same context and formulas assess Superflip and SharpED maps. A changed map can therefore change its metrics relative to the original data. Identical maps produce identical metrics, irrespective of family.
- **Ranking:** existing profile-specific, directional metric order and tie-breaking remain unchanged. Families still have separate recommendations; these UI changes do not create a new cross-family ranking.

A synthetic Fourier regression demonstrates the important limitation: two maps with the same imposed amplitudes and different phases both give R≈0 and CC≈1, while C3 differs. Thus those ideal amplitude scores can be tautological consequences of imposed input amplitudes, rather than evidence of a correct atomic solution. The implementation does use different observed and calculated arrays; no accidental observed-versus-observed calculation was found. Tooltips now explain this limitation. No metric formula, metric schema, golden expectation or ranking policy was changed.

Rounded identical displayed scores need not mean an internal tie: ranking uses full precision and a tolerance of 1e-12. This limitation is documented without publishing private-project measurements. No ranking formula or tolerance was changed.

## D. Validation and screenshots

Final validation (all processes exited successfully):

- **53 direct test scripts, 2,268 checks**, including Jana completion **192**, workflow states **141**, existing Result Selection/viewer **72**, new selector/metric guards **7**, scientific core goldens **46**, and displacement export **44**.
- Complete unittest discovery: **100 passed** (118.162 s).
- Complete pytest discovery: **100 passed** (118.66 s).
- **51 after screenshots** across 100%, 125%, and 150% software scale factors, plus **17 before screenshots**, with metadata alongside every image. After captures passed projected-fit/bounds/footer and scientific-file hash assertions.
- Compile checks and `git diff --check` passed. No scientific golden expectations changed; the existing scientific output and CRLF hash/byte contracts remain green. Real project input/map bytes remain unchanged.

Detailed local logs: `build/direct-test-summary-selector-2.0.3.txt`, `build/selector-unittest-complete.log`, `build/selector-pytest-complete.log`, and `build/test-logs-selector-2.0.3/`.

The new focused guards cover projected geometry and file identity, manual camera preservation, source switching and warning geometry, recommendation stars, authoritative two-site `.m40` versus an actual nine-site CIF, missing model metadata, pending/success/failure/stale callback handling, unchanged `.m40` on threshold publication, empty-family behavior, sidecar threshold/site-count matching, and two metric source-array/phase-limit regressions. Existing Result Selection, Jana completion, workflow-state, scientific golden, displacement export, model/default and packaging tests remain in the complete suite.

`packaging/tools/capture_result_selection.py` captures the actual Qt/QtAgg dialog and stores each PNG with logical size, device scale, candidate identity, selected hashes, counts and measured projected fill. Its after captures assert projected 70–85% fill, in-panel bounds, visible footer and unchanged selected map/CIF/model hashes. The 100/125/150% captures include a 1500×900 dialog, 1280×720 laptop size and 1100×720 reduced width. Separate selector guards exercise 1920×1080 and 2560×1440 logical windows. Existing shared-camera golden geometry guards include compact, elongated and dense geometries at multiple orientations.

Screenshots live in [`screenshots/2.0.3-result-selection`](screenshots/2.0.3-result-selection). Each scale includes: charge-flipping recommendation, SharpED recommendation, manual SharpED selection, elongated model, dense model, Full cell, Complete molecules, pending/completed threshold, distinct EDMA/Jana counts, both family-switch states, compact selected summary, laptop/reduced windows.

The before captures load the exact saved pre-task selector source without reverting the dirty tree. Baseline source SHA-256: `17e334ae3fbe65f4be7096006d93ce5a4bc1bb8356a4146c0fef8974b319b657`.

Fixture screenshots use supplied profile metrics and file-backed candidate/model artifacts; simulated threshold completion is explicitly a UI lifecycle fixture, not a new EDMA calculation. Private real-project screenshots and their metadata are ignored and excluded from this public commit.

## E. Release readiness and limits

The selector redesign targets the current dirty **2.0.3** source. The frozen 2.0.2 release artifacts and metadata are not overwritten. A real Jana2020 GUI acceptance test of the selected map/model, including continuing refinement, remains required. Native Windows hardware/DPI acceptance and authenticated fresh Superflip + SharpED runs are not replaced by offscreen scaled rendering or protocol tests.
