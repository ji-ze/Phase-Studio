# Execution window, viewer fitting and progress — 2.0.3

This work follows the user's standing instruction that subsequent prompts apply
to 2.0.3. It preserves the preceding Wizard, configuration and Map Feedback
changes. No release artifacts or Git history were changed.

## A. Viewer improvements

The small structures had two concrete causes:

1. The execution window fitted a three-dimensional bounding sphere to the
   square drawing box. An elongated molecule can occupy only a small fraction
   of that sphere in the current projection.
2. Matplotlib Axes3D keeps a square active axes rectangle inside the wider panel.
   Its aspect adjustment occurs at draw time. A fit measured before that
   adjustment can use stale transforms after resizing. Rebuilt artists also
   revert to clipping against that artificial square.

`phase_studio/structure_camera.py::fit_projected_structure` now measures the
actual displayed Cartesian geometry in the current orthographic orientation,
using the laid-out panel rectangle. It applies the axes aspect first, measures
the projected bounding box, fits its dominant dimension to 78%, and centres it
by changing camera limits. Atom coordinates, marker sizes and connectivity are
unchanged. `set_structure_viewport_clip` confines artists to their own panel
rectangle rather than the smaller square.

The execution window supplies displayed molecular coordinates, or the displayed
atoms plus cell-frame corners in Full cell. Invisible secondary peaks do not
enter the fit. Existing representation construction and its finite framework
fragment policy remain unchanged; Full-cell rendering is not decimated.

The native canvas resize event and a zero-interval queued Qt fit replace the
arbitrary 80 ms settling delay. Only authorized initial/automatic fits run;
manual interaction removes the affected panel from pending fits. Ordinary
layout updates preserve a manually adjusted camera.

Charge-flipping and prediction panels remember their own orientation, limits
and fit state across redraws. A newly available result in one panel no longer
resets the other. Existing candidate/extent transition rules still authorize
reframing, applied only to the affected panel. Mouse interaction mathematics
are unchanged. The experimental Autosolve camera policy remains intact.

The detached single-structure viewer reuses projected fitting, opens with the
selected panel's orientation, and preserves an interacted camera when the
presentation has not changed.

Measured with the same synthetic structures in a 1500 × 1000 logical window:

| Structure | Before projected fill | After |
|---|---:|---:|
| Dense 60-site structure | 53.3% | 78.0% |
| Elongated 24-site molecule | 22.6% | 78.0% |

Fill means the larger of projected width/panel width and projected height/panel
height. The smaller fraction depends on molecular aspect ratio. It excludes
marker radius. Numeric capture metadata is saved beside the build screenshots.

## B. Layout improvements

`phase_studio/autosolve_window.py` retains equal-width white scientific panels,
their shared divider and the fixed footer. Source, cycle and actual recorded
initialization/model provenance stay in the header; their duplicate detail row
is hidden for the ordinary workflow.

- Previous/next, Latest selection, panel Fit and Fullscreen are together.
- EDMA threshold/site count sits beside + atoms and − atoms.
- ASU composition uses chemical subscripts and belongs to the completed
  threshold-specific CIF. Representation changes do not alter EDMA site counts.
- Empty controls remain disabled; completed structures appear independently.
- One compact validation warning spans both panels.
- Camera controls explicitly say “Both viewers”; panel Fit, double-click and
  keyboard interaction target the relevant viewer. Detailed controls are in the
  short rotate/zoom hint's tooltip. Representation remains shared.
- Execution captions/placeholders and normal UI text use Segoe UI. Shared
  Science Gothic branding, regular weight and zero tracking remain unchanged.
- The compact log uses Segoe UI 10 pt and 3–5 visible rows. Existing expand,
  open-file, full diagnostic logging and manual-scroll preservation remain.
- The ordinary canvas can shrink to a 140-pixel minimum without pushing out the
  footer, while retaining its dominant stretch in normal windows.

## C. Workflow state and handoff

The real scheduler runs primary Superflip and SharpED sequentially. It can run
Superflip-map EDMA and SharpED concurrently. A single latest stage cannot fully
describe these sibling jobs.

`phase_studio/app.py::_run_display_operation` publishes actual Superflip/SharpED
call lifetimes with unique job IDs, captured cycle and run ownership. The existing
GUI-thread `_poll_queue` consumes them. `active_workflow_operations` combines
those lifetimes with existing EDMA job states and review activity. New-run/reset
paths clear the display state. Finished job IDs cannot be resurrected by a late
running event; completed/failed EDMA generations reject backward status updates.

Branch threads do not inherit `threading.local`. Scientific-operation entry
points now bind progress/log callbacks to their captured run ID, so late callbacks
cannot acquire a newer global run's identity. Existing RunScopedPayload filtering
continues to reject old-run events on the GUI thread.

The upper banner reports the cycle and overall state; the lower area names real
active operations, including overlaps. The overall bar retains existing genuine
cycle milestones. Unknown-duration activity remains indeterminate; Superflip
repeat counts retain their own subordinate bar and are not workflow percentages.
Immediate-stop intent freezes activity animation while the worker acknowledges
the stop. Terminal states do not retain a running animation.

Interactive EDMA failure now publishes a terminal failed job state. The last
completed structure and threshold remain available. Its error message is scoped
to the exact run/source/cycle/map identity, rather than leaking to another
candidate selected in that panel.

Early handoff was already supported. It formerly requested immediate stop without
an execution-window confirmation. The footer now asks before stopping remaining
work and opening Result Selection. Keep running is the default. The confirmation
names eligible completed families/cycles/thresholds, not a newer live preview
that has not reached handoff eligibility. Result Selection still determines the
actual candidate to publish; this is not an automatic transfer of the preview.

Pass is disabled without an eligible completed candidate and while an interactive
threshold extraction is pending. After completion it opens the existing selector
without an early-stop confirmation. Standalone retains file-export wording.
Snapshot construction, scientific conversion, protocol validation and transactional
publication/rollback remain unchanged. No Superflip, SharpED or EDMA computation
is added to Pass.

## D. Scientific integrity

Scientific calculations and golden expectations were not changed. Camera and
representation controls do not write structures or maps. Normal EDMA defaults
remain 0.50σ for both families; adaptive threshold stepping remains unchanged.
Uiso conversion/clamping at 0.010–0.150 Å², compact molecular exports, origin
preservation, ranking and Jana M40/M50/M80/M81 publication were not modified.

The asynchronous UI test executes the real review executor and candidate
promotion with a controlled EDMA output fixture. It verifies 0.50 → 0.40σ,
retains the old structure while pending, preserves the other family and source
map bytes, and makes the completed threshold-specific artifact available.
It also verifies failed extraction retains that artifact and ends job activity.
Superflip/SharpED calls are forbidden by mocks in this EDMA-only test.

The opt-in ochlor check reads the real `ochlor.inflip` and saved
`run_0002/cycle_003/cycle_003_deblurred.xplor`, derives 631 reflections in an
isolated temporary workspace and verifies original input/map bytes unchanged.
Source map SHA256:
`ce7cdadc67e9a7067216acc47da9b421ee191680c5ffd945047b190357cdc620`.

No fresh SharpED inference or real Jana2020 GUI acceptance was performed.
Jana protocol correctness is supported by the existing automated completion,
selection, export and transactional rollback tests; manual Jana acceptance is
still required.

## E. Tests and rendered evidence

- Focused new module: **11 tests passed**, with clean native process exit.
- Three Qt scale processes cover empty/completed layouts at 1280×720,
  1500×850, 1920×1080 and 2560×1440 logical pixels: 24 configurations.
  Projected fit, clipping bounds, equal columns, warnings and footer separation
  are checked. Compact, elongated and 1200-point dense geometry are also checked
  in three orientations without coordinate mutation.
- Existing Autosolve window: **253 checks passed**; fullscreen: **15**.
- All **52 direct script suites / 2,261 checks passed**.
- Full unittest: **93 tests passed**; pytest: **93 tests + 5 subtests passed**.
- Scientific core goldens: **46**; Jana completion: **192**; workflow states:
  **141**; Result Selection: **72**; displacement exports: **44**; EDMA defaults:
  **17**; API contract/scaling/tiling: **15 / 83 / 33**, all passed.
- Compile check and `git diff --check` passed. No scientific golden files changed.

During development, the new test assertions completed but Qt's native application
destructor hung at interpreter shutdown. The harness now explicitly disposes its
owned application while Python is alive. Superseded hung helpers were stopped;
only cleanly exited final runs count above. Failed intermediate runs were not
counted as successful validation.

Reproduction tools: `packaging/tools/capture_execution.py` and
`tests/test_execution_redesign.py`. Final logs are under `build/execution-*`;
direct suite summary is `build/direct-test-summary-execution-2.0.3.txt`.

These are actual application-runtime QtAgg renders with explicitly synthetic
structures, maps and lifecycle events. They are not fresh scientific runs.
The before capture loads the recorded pre-task execution-window implementation
without reverting the dirty working tree. No reference screenshot was attached,
so comparison uses that actual runtime baseline.

| State | Screenshot |
|---|---|
| Before | [Both results before](screenshots/2.0.3-execution/00-before-both-ready.png) |
| Initial empty | [Empty](screenshots/2.0.3-execution/01-empty.png) |
| Superflip running | [Running](screenshots/2.0.3-execution/02-superflip-running.png) |
| Charge-flipping available, SharpED active | [Progressive](screenshots/2.0.3-execution/03-charge-flipping-ready.png) |
| Both families | [Both](screenshots/2.0.3-execution/04-both-ready.png) |
| Elongated prediction | [Elongated](screenshots/2.0.3-execution/05-elongated-fitted.png) |
| Dense charge-flipping | [Dense](screenshots/2.0.3-execution/06-dense-fitted.png) |
| Full cell | [Cell](screenshots/2.0.3-execution/07-full-cell.png) |
| Complete molecules | [Molecules](screenshots/2.0.3-execution/08-complete-molecules.png) |
| Interactive extraction pending | [Pending](screenshots/2.0.3-execution/09-interactive-edma-pending.png) |
| Interactive extraction completed | [Completed threshold](screenshots/2.0.3-execution/10-interactive-edma-completed.png) |
| Two active operation records | [Concurrent](screenshots/2.0.3-execution/11-concurrent-operations.png) |
| Workflow completed | [Complete](screenshots/2.0.3-execution/12-completed.png) |
| Actual early-stop confirmation | [Confirmation](screenshots/2.0.3-execution/13-early-handoff-confirmation.png) |
| Reduced height | [760 logical pixels](screenshots/2.0.3-execution/14-reduced-height.png) |
| Laptop-sized viewport | [1280×720 logical](screenshots/2.0.3-execution/laptop-1280x720.png) |
| 125% Qt scale | [125%](screenshots/2.0.3-execution/15-scale-125.png) |
| 150% Qt scale | [150%](screenshots/2.0.3-execution/16-scale-150.png) |

Normal captures are 1500×1000 logical pixels; scale 1.25 produces 1875×1250
device pixels, and scale 1.5 produces 2250×1500. Qt scaling is verified, but
physical Windows display scaling, native window chrome, very small available
screen areas and a real Jana session still need manual acceptance.

No new frozen executable was built. Existing 2.0.2 release binaries remain
unchanged and do not contain this 2.0.3 UI. No commit, push, tag or publication
was performed. LICENSE, CITATION, authorship and API terms were not changed.
