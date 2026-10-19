# Viewer and Jana handoff remediation — 2.0.5

## Finding and correction

The deterministic reproduction selected Cycle 2, opened the detached viewer,
then selected Cycle 3 in that same live widget. Its geometry and selector
metadata advanced, but the detached host retained its original Cycle 2 title.
See `build/viewer-identity-reproduction.log`. This establishes a stale title;
it does not establish that the scientific handoff previously substituted maps.

The existing frozen `ResultCandidate` remains the scientific authority.
`ResolvedCandidateSnapshot` freezes the selection identity and the actual
displayed atoms, coordinates, bonds, representation and composition together.
Identity includes run, source, cycle, candidate ID, map hash, EDMA threshold,
structure hash and Jana model hash. Geometry caches include these identities.
Detached metadata follows that same selection. Accept freezes the candidate;
late row signals cannot change it, and closed dialogs ignore selection events.
Pass checks the rendered snapshot against the selected identity.

A second regression appeared during screenshot inspection: reparenting the
canvas changes its viewport without resizing the selector. Canvas resize now
schedules Fit unless the user has deliberately adjusted the camera. The
fullscreen title test also checks projected geometry stays inside the viewport.

## Workflow and viewer changes

- Completed-cycle state and counter commit before the completion log event.
  Metrics/finalization remain visibly Finalizing until that boundary.
- Completed-candidate EDMA controls have independent busy state. Missing
  retained run context, executable, or map produces an explicit disabled reason.
  The existing isolated asynchronous review worker and stale-response guards
  remain the authority; no live Jana project model is rewritten on adjustment.
- Camera controls share persisted inversion, rotation sensitivity and optional
  conventional CPK-style element colors. Default colors are unchanged. Manual
  interaction pauses auto rotation; geometry is not rebuilt during rotation.
- Main and fullscreen preserve camera orientation, roll, limits and zoom.
  Fullscreen EDMA enablement follows the parent candidate controls.
- Damping filenames/factors remain in the detailed log rather than normal
  execution messages. No damping mathematics changed.

## Scientific and handoff evidence

Actual, read-only ochlor `run_0010` supplies both sources, Cycles 1–3, at
0.50 sigma. SharpED Cycle 2 has 16 CIF sites / 14 Jana-model sites; Cycle 3
has 20 / 16. These distinct counts remain associated with their actual map,
model hashes and cycle in selector, detached viewer and frozen selection.

| Actual SharpED candidate | Candidate ID | Map SHA-256 |
| --- | --- | --- |
| Cycle 2, 0.50 sigma | `run_0010:sharped:c002:t0.50:5c86839b111f` | `22367691b85c06fbe0220412abe51b347c8a133d570745cdac0804e95a152749` |
| Cycle 3, 0.50 sigma | `run_0010:sharped:c003:t0.50:40c75aaf2d51` | `b65452d489d78c50865a87886cb279ba25759777a62c774ed9576008dc73d951` |

Stored `run_0009` additionally supplies actual SharpED Cycle 2 at 0.50 and
0.60 sigma; its own map is used, never a map from run_0010. Other threshold
and asynchronous permutations use explicitly controlled offline fixtures.

`identity-evidence.json` at each capture scale records candidate identities,
map/model hashes, actual rendered-coordinate hashes and counts. All original
map/CIF/m40 source bytes were checked unchanged after capture. Displayed
complete molecules, raw EDMA sites, independent ASU sites and Jana-model sites
are deliberately distinct quantities; display expansion does not add EDMA sites.

The protocol suite verifies a manually selected Cycle 2 remains the handoff
choice despite later Cycle 3 selection signals, exact selected map/model hash
pairing, no second scientific recomputation, threshold-specific selection,
stale-artifact rejection and repeated-run isolation. Existing publication writes
the selected model to `_tmp.m40` and produces m80/m81 through the existing
conversion authority. The original valid, nonempty m50 context remains byte
identical; a fabricated replacement is not generated. Scientific writers,
ranking, atom coordinates/occupancies, extraction and thresholds are unchanged.

Jana2020 is installed, but a native interactive import/refinement acceptance
was **not performed**. Automated protocol tests and screenshots are not proof
that Jana accepted and continued refining the real project. That final manual
acceptance remains required; original ochlor project files were not overwritten.
The inspected `C:/Jana2020/SUPERFLIP` installation advertises integration 2.0.2
and `superflip_original.exe`, but that original executable is absent in that
directory. It is not a verified current 2.0.5 native acceptance environment;
this task did not replace or repair the user's installation.

Connectivity checks cover symmetry expansion, periodic molecule completion,
ASU/display count separation and representation round trips. Actual molecule
and full-cell screenshots were inspected. No demonstrated connectivity
algorithm regression justified changing scientific coordinates or bonding rules.
Numerical fixtures retain the 0.8-Angstrom boundary-crossing bond, 1.2-Angstrom
multi-wrap chain bonds, separate molecules and special-position deduplication;
source CIF bytes remain unchanged.
Some stored noisy candidates remain fragmented; this work does not claim to
scientifically repair those solutions. Full-cell outlines are unit-cell edges,
not inferred molecular bonds.

## Performance and screenshots

`build/acceptance-viewer-remediation-2.0.5/benchmark-{before,after}.json`
records 24 cases: actual ochlor, dense 320-site and large 1400-site fixtures;
main/fullscreen, molecules/full cell, manual/automatic rotation. All paired
atom counts and coordinate hashes are identical. Hardware:
Intel64 Family 6 Model 198 Stepping 2, Windows 11, QtAgg CPU rasterization.

| Across the same 24 cases | Before | After |
| --- | ---: | ---: |
| Average measured mean frame, ms | 5.131 | 4.801 |
| Average measured p95 frame, ms | 6.194 | 5.131 |
| Worst mean frame, ms | 12.457 | 12.656 |
| Worst p95 frame, ms | 18.292 | 13.303 |
| Average identical-candidate refresh, ms | 934.287 | 0.258 |

Unchanged previews now retain artists rather than rebuild the scene. This is
the substantial measured improvement; individual rotation means do not all
improve. These are short CPU timing samples, not physical monitor/GPU FPS claims.

Capture evidence is under `build/acceptance-viewer-remediation-2.0.5/`:
28 real-data PNGs at each of 100%, 125%, 150% scaling, and 11 actual Qt execution
window PNGs using explicitly labeled synthetic lifecycle fixtures. Includes
final-cycle Finalizing, completed workflow, running subsequent cycle, both
sources/cycles/representations, same-window navigation, real thresholds, camera
menu and visible footers. Contact sheets and individual fullscreen captures
were visually inspected; the discovered clipping was corrected and recaptured.
Offscreen Qt uses an emulated desktop; physical Windows monitor acceptance
remains separate.

## Modified files and repository boundary

This pass changes `phase_studio/{app,autosolve_window,result_selection,
fullscreen_viewer,structure_camera}.py`, selector/execution/camera/Jana/viewer
regression tests, and adds the real-data capture/benchmark/fixture tools plus
this report. The distribution AST guard permits only the explicitly opt-in CPK
prelude, checks its exact gate, then still compares the entire original default
color function to v2.0.3. No scientific function was newly exempted and no golden
scientific output was replaced. Two older test harnesses were corrected: interactions now occur
in a live dialog, and geometry-cache tests explicitly prime their cleared cache
before asserting camera reuse. Scientific expectations were not weakened.

Earlier dirty HKL, wizard, authentication, documentation and workshop work was
preserved. Version remains 2.0.5 on `development/2.0.5`. No commit, push, tag,
release or binary publication was performed by this pass.

## Test results

| Check | Result | Log under `build/` |
| --- | --- | --- |
| Complete final suite | **435 passed, 1 skipped, 37 subtests passed**, 415.36 s | `viewer-remediation-full-final.log` |
| Focused selector / execution / camera | 56 passed | `viewer-remediation-focused.log` |
| Final selector, including fullscreen viewport containment | 25 passed | `viewer-final-resize-test.log` |
| Scientific core goldens | 46 checks passed | `viewer-scientific-golden.log` |
| Jana completion / selected handoff protocol | 195 checks passed | `viewer-jana-protocol.log` |
| Viewer / representation / connectivity script | 72 checks passed | `viewer-connectivity-golden.log` |
| Review EDMA | 20 checks passed | `viewer-review-edma.log` |
| Autosolve orchestration | 79 checks passed | `viewer-orchestration.log` |
| Workflow states | 141 checks passed | `viewer-workflow.log` |
| Released scientific AST guard | Passed | `viewer-ast-golden.log` |
| Actual-data captures and source hash invariance | Passed at all three scales | `viewer-real-capture-{1,125,150}.log` |
| Final whitespace/conflict check | `git -c core.safecrlf=false diff --check` passed | No content errors |

The first full run found only the optional visual-palette AST mismatch
(434 passed, 1 failed, 1 skipped, 37 subtests passed). That guard was corrected
as described above; the complete final run passes, including the final canvas
resize correction and viewport regression. Scientific output goldens remain
unchanged. The staged index is empty; source/test/report changes remain local.
