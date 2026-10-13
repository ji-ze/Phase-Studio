# Autosolve and the new Jana Wizard hierarchy

Phase Studio 2.0.0 is a major Jana2020 Wizard / UX release. It adds
**Autosolve**, a simplified front end that orchestrates existing scientific
machinery (Superflip, SharpED, EDMA, Map Feedback, Powder repartitioning,
weak-intensity correction, `map_quality.py` ranking, Jana2020 handoff) behind
two guided choices, while leaving Professional mode (the complete expert
interface) and the two existing lightweight Wizard workflows ("Advanced")
untouched. It also adds shared large-map P1-tiling support for SharpED
uploads and removes an existing voxel-degradation workaround that no longer
applies once tiling exists.

No scientific algorithm was rewritten. This document is filled in
progressively as each implementation phase lands; see the final section for
the complete phase-by-phase status.

## New Jana Wizard hierarchy

**Primary actions:**
- **Original Superflip** — today's wrapper-only "Superflip only" workflow,
  unchanged (native console, no Phase Studio main window, no SharpED).
- **Autosolve by Superflip + SharpED** — the new guided flow (below).

**Secondary actions:**
- **Advanced** — today's "Superflip + SharpED" and "Phase recycling with
  Superflip + SharpED" Wizard cards, unchanged in every scientific respect.
- **Professional mode** — the one authoritative entry to the full Phase
  Studio GUI (does not auto-start). The old "Open full configuration" footer
  button duplicated this and has been removed.

**UX pass (post-routing-fix):** Original Superflip and Autosolve are large,
fully-clickable action tiles on the landing page — clicking either performs
the action immediately, no separate Next/Run confirmation. The Autosolve
goal page (Option A/B) works the same way: clicking a tile starts Autosolve
directly; the Option B warning is always visible underneath its tile (not
gated on selecting it first, since selecting now means starting). Both
pages' footers are minimal (Cancel, plus Back on the goal page).
`AutosolveWindow` was reworked so structures dominate the window (~65-75%
of content height): atoms are enlarged and connected by bonds (a new,
presentation-only distance-based detector using gemmi's own covalent-radius
data — no connectivity algorithm existed anywhere in Phase Studio to reuse),
mouse controls are left-drag rotate / right-drag pan / wheel zoom /
double-click reset, auto-rotation pauses on interaction and resumes after a
short idle delay, the top status collapses to one compact line plus a
best-cycles line, and the Execution Log and progress strip are capped to a
small fraction of the window.

## Autosolve

Two choices, both driving the same underlying mechanism the Jana Wizard's
existing "Phase recycling with Superflip + SharpED" workflow already uses
(`reconstruction_mode="superflip"`, `modelfile_source="deblurred_xplor"`,
`run_sharped=True`): every cycle, Superflip runs, SharpED deblurs its map,
and the deblurred map seeds the next cycle's Superflip run
(`damping_factor=1.0` — undamped, pure feed-forward of the latest SharpED
map). EDMA runs every cycle for both the Superflip and SharpED maps
(`plimit_superflip=1.20`, `plimit_deblur=2.00`), so both sources accumulate a
real, independently rankable candidate per cycle.

- **Option A — "Solve the phase problem on the original data"**: Map
  Feedback stays off; the recommended *Superflip* cycle (via
  `map_quality.py`'s unmodified ranking) is passed to Jana2020.
- **Option B — "Predict the structure model"**: the same initial search,
  ranked on the *SharpED* candidates; once the adaptive search converges, one
  automatic Map Feedback refinement stage runs (Powder repartitioning if
  valid FWHM data and wavelength are available, otherwise weak-intensity
  correction), continuing the same run via Continue/Resume; the recommended
  SharpED cycle is passed to Jana2020. Carries a persistent, non-blocking
  warning that SharpED's neural-network prediction and Map Feedback's
  reflection modification both require validation against the original
  measured data and an independent refinement.

Both options use an adaptive cycle budget (10, then +5 while the most
recently completed block still improves the relevant recommendation,
evaluated with the same unmodified `recommend_best_result` — no invented
scoring), a "Pass to Jana2020" action, and immediate Cancel. Both the
automatic end point and "Pass to Jana2020" open the shared Result Selection
dialog on the goal's source (Superflip for "Solve the phase problem",
SharpED for "Predict the structure model") with the recommended cycle
preselected; the user may choose another cycle, and only the confirmed
result is passed to Jana2020. Closing Result Selection passes nothing.

## Large-map SharpED tiling

Every SharpED map upload (ordinary workflows, Advanced, Autosolve,
Professional mode) now goes through one shared decision: maps under the
configured upload limit are sent exactly as before; maps over the limit are
tiled (equal-size, 10%-overlap, periodic P1 tiles), inferred per tile, and
reassembled with Gaussian-weighted overlap blending (`sigma_scale=0.125`, no
MONAI dependency) on the original, unchanged grid. The previous workaround —
silently coarsening Superflip's own voxel grid so the map would fit under the
upload limit — is removed; the scientific grid the user configured is never
degraded to satisfy an upload-size constraint.

## Status

Implementation proceeds in the phases below; this section is updated as each
lands.

- [x] Phase 1 — Version bump to 2.0.0
- [x] Phase 2 — Jana Wizard entry redesign
- [x] Phase 3 — Adaptive-cycle policy
- [x] Phase 4 — Option B Map Feedback stage transition (Continue/Resume)
- [x] Phase 5 — Autosolve window
- [x] Phase 6 — Option A / Option B orchestration
- [x] Phase 7 — Large-map P1 tiling + voxel-degradation removal

Phases 4 and 6 landed together: `main()`'s `"autosolve"` dispatch now calls
`launch_autosolve_from_jana()` (`jana_superflip.py`), which builds the
Autosolve `RunConfig` overrides (undamped feed-forward, EDMA every cycle,
`plimit_superflip=1.20`/`plimit_deblur=2.00`) the same way "Phase recycling"
already does, then starts a real, fully automatic run:
`IterativeSuperflipPipelineQtGUI._autosolve_on_run_done()` (hooked into the
existing "done" queue event) drives the adaptive 10→+5→+5… cycle budget via
`AdaptiveCyclePolicy`, `_autosolve_begin_map_feedback_stage()` reconfigures
the *same* `PipelineState` for Option B's one Map Feedback stage (Powder
repartitioning when FWHM data and a resolvable wavelength are both
available, otherwise weak-intensity correction) and continues it via the
existing Continue/Resume machinery, and `_autosolve_handoff()` calls the
existing `perform_jana_handoff()` automatically once the relevant stream
(Superflip for Option A, SharpED for Option B) stops improving.

New in the wavelength-resolution chain: `resolve_powder_wavelength()` gained
an optional `jana_m90_path` source (`parse_m90_wavelength`/
`resolve_jana_m90_path`), inserted between manual entry and the `.inflip`
lambda line, parsing the radiation wavelength from a Jana2020 `.m90`
reflection-data file's own header (`lambda <value> ...`) when one exists
alongside the `.inflip`. If Option B's data has FWHM values but no
wavelength can be resolved from any of the three sources, Autosolve stops
with a specific remediation message and hands off the search-stage result —
it never silently falls back to weak-intensity correction.

Phase 5 landed as a routing fix on top of the above: `launch_autosolve_from_jana()`
now constructs `IterativeSuperflipPipelineQtGUI` purely as a hidden scientific
backend (never shown) and displays `phase_studio/autosolve_window.py`'s
`AutosolveWindow` instead, maximized. `AutosolveWindow` borrows its structure-
rendering/camera-sync methods from `IterativeSuperflipPipelineQtGUI` the same
way `create_result_preview_host()` already does for the Jana2020 result
selector, and reparents (rather than duplicates) the backend's own Execution
Log and progress-bar widgets. Structure tiles follow each source's own current
recommendation (not simply the latest cycle); the Reference tile only appears
when a reference is actually available (2 tiles otherwise). `busy=True` now
also actually switches the per-cycle progress bar to indeterminate, benefiting
the full GUI too.

**"Pass to Jana2020" (revised; formerly "Pass to Jana2020 now")**: stops the
active work IMMEDIATELY (the same `request_immediate_stop()` mechanism Cancel
itself uses -- never waits for the in-flight cycle), then opens Result
Selection over the ALREADY COMPLETED candidates, with the best one
preselected; the confirmed choice is handed off.
An in-flight cycle is never appended to `self.results` until it genuinely
finishes, so it is automatically excluded with no extra filtering logic. With
zero completed candidates, no handoff is attempted and a concise message is
logged instead.

**Autosolve Superflip EDMA threshold**: lowered from 1.30σ to 1.20σ
(`plimit_superflip`); SharpED stays at 2.00σ (`plimit_deblur`).

**Structure-view modes**: `AutosolveWindow` now offers "Complete molecules"
(default) and "Full cell", synchronized across every visible panel. Full cell
shows the symmetry-expanded unit cell's atoms with NO bond connectivity --
the previous attempt to bond atoms across an entire already-expanded unit
cell produced a near-all-to-all web, since many symmetry-equivalent
molecules pack close together purely from crystal packing, not chemistry.
Complete molecules instead grows ONE chemically-connected fragment outward
from the raw asymmetric-unit atoms (`build_complete_molecule_fragment()` in
`autosolve_window.py`), pulling in a symmetry/periodic-neighbor image only
when it is actually within bonding distance of an atom already in the
fragment, then bonds only that small local set -- never the whole cell.

## Jana Wizard / Autosolve UI quality pass

A follow-up, UI-only pass over the Jana Wizard and `AutosolveWindow` — no
scientific routing or behavior was touched.

**Tile icons**: all four primary-page action tiles (Original Superflip,
Autosolve, and the Autosolve goal page's "Solve the phase problem" /
"Predict the structure model") now carry a small navy/cyan vector icon on
their left edge, drawn with plain `QPainter` primitives in
`ui_branding.py` (reflections/density-map/atom-cluster/arrow glyphs
composed per tile's own science) — no external assets, no new dependency.
The two secondary buttons (Advanced, Professional mode) get restrained,
muted-color icons of their own so they stay visually subordinate to the
two dominant tiles. `_ActionTile` (`jana_superflip.py`) was rewritten so
the whole tile is a genuine click target: pointing-hand cursor, native
hover/focus QSS states, a custom `pressed` property for a pressed state,
and Enter/Space keyboard activation, verified with real `QTest`
mouse/keyboard simulation, not direct callback invocation.

**One authoritative cycle/stage source**: `AutosolveWindow`'s header
previously derived its cycle count independently from
`backend._resume_state.completed_cycles` — correctly 0 while cycle 1 was
still running, but that produced a visible "Cycle 0 of 10" next to a
bottom progress row that was already correctly showing "Cycle 1" from
`backend._cycle_progress_state`. The header now reads
`backend._cycle_progress_state.display_text()` directly — the exact same
object the bottom row already used — so the two can never disagree again,
and before any real cycle event arrives the header reads "Preparing
Autosolve…" rather than exposing the internal zero-based count.

**Progress-panel clipping**: traced to a `setMaximumHeight(90)` cap added
in an earlier pass's "make it compact" pass, smaller than the panel's
actual content (label rows + progress bars + the conditional
Superflip-repeat row). Removed; the panel now sizes to its own
`sizeHint()` with no stretch factor, so it can never be squeezed again.

**"Pass to Jana2020" / Cancel feedback**: both buttons now carry
tooltips spelling out the immediate-stop-vs-no-handoff distinction;
clicking "Pass to Jana2020" immediately shows "Stopping current
calculation…" and disables both buttons against duplicate presses. Once the
backend reaches a terminal cancelled/stopped state it shows "Choose the
result to pass to Jana2020…" while Result Selection is open, then "Passing
the selected result to Jana2020…"; if Result Selection is closed without a
choice, the action is re-enabled.

**Goal-page warning**: shortened to stay tied only to the "Predict the
structure model" tile; the previous full detail moved to that tile's own
tooltip rather than being dropped.

**Structure-view toolbar**: Fit / Reset view / Auto rotate / the
Complete-molecules–Full-cell toggle all gained small line-art icons
(`ui_branding.py`); the view-mode toggle is now a true adjoining segmented
control (shared border, solid-fill "checked" state) instead of two
independent-looking toggle buttons. `QToolButton` falls back to
icon-only display once a real icon is set, so `ToolButtonTextBesideIcon`
was set explicitly on all five buttons to keep their meaningful text
(on/off state, which view mode) visible beside the icon.

Verified with 62 new/extended checks across `test_jana_wizard_hierarchy.py`,
`test_jana_wizard_tile_icons.py` (new), and `test_autosolve_window.py`
(icon-pixel verification, real click/keyboard tile routing, header/bottom
cycle-text agreement across 4 stage cases, the cycle-zero regression,
progress-clipping regression across 4 stage scenarios at 3 representative
font scales, and the toolbar icon/segmented-control checks) — full existing
suite (28 test files) re-run clean afterwards.

## Visual-consistency pass (supersedes the tile/toolbar icons above)

Presentation only. No scientific calculation, threshold, recommendation
rule or Jana handoff changed.

**Icons: established inventory only.** Before 2.0.0, Phase Studio used
exactly four icon sources: the Phase Studio monitor mark (app, title-bar and
taskbar icon, brand-header logo, `assets/phase_studio.ico`), the
external-link chain glyph, and Qt's standard `SP_MessageBoxWarning` and
`QMessageBox.Information` icons. The 11 line-art glyphs added in the
previous UI pass came from none of these, so they were removed and nothing
was drawn to replace them. These four sources are now listed in
`ui_branding.ESTABLISHED_ICON_INVENTORY`, and icons are applied through
`apply_established_icon()`, which tags each widget with its source.

| Action | Icon |
| --- | --- |
| Professional mode (opens the full Phase Studio application) | Phase Studio mark |
| Autosolve goal-page warning | Qt `SP_MessageBoxWarning`, one text line high |
| Original Superflip, Autosolve, Solve the phase problem, Predict the structure model, Advanced | text-only |
| Fit, Reset view, Auto rotate, Complete molecules, Full cell | text-only |

Gap: Phase Studio has no established icon for maps, workflows or
automation, structures, fitting, rotation or unit cells. Those actions stay
text-only rather than start a new icon family.

**Tiles**: text-only, with shared `TILE_*` geometry constants. Subtitles are
single-line, because the Wizard's QScrollArea ignores height-for-width, so a
wrapping label made two equally short tiles different heights. Focus
changes a 1px margin plus a 1px border into a 0px margin plus a 2px border,
so the text never shifts. The chevron width comes from the glyph's real
advance. The goal page uses the same zero margins as page 1. The warning
starts on the "Predict the structure model" text edge and sits 4px below
that tile, where the tiles themselves are 8px apart.

**Autosolve window**:
- Each panel caption reads "Superflip / Best · Cycle N". Best cycles are no
  longer repeated in the header, and the label below each structure shows
  the chemical formula only, at 10pt.
- The "Configuration locked while the calculation is running." hint is
  detached from the Autosolve progress panel. The Professional GUI keeps it.
- The progress panel reads: Overall and its bar; then "Cycle N of M · stage
  · state", with "Stage i of n" on the same row, and its bar; then Superflip
  repeat sub-progress only while it applies, thinner and lighter than the
  stage bar.
- The view toolbar is one text-only family with a shared height: Fit, Reset
  view and Auto rotate (a checkable toggle with a filled "on" state), then
  "View:" and a Complete molecules | Full cell segmented control. The
  toolbar never takes focus at startup.
- "Pass to Jana2020" is disabled until this goal's first completed
  result exists; its tooltip says why. `#primaryButton:disabled` had no
  style before, so a disabled primary button looked enabled.

**Complete molecules**: `build_complete_molecule_view()` grows connected
components from the asymmetric unit. Each seed is represented once: reaching
any image of another seed marks it covered, so the same molecule is not
started twice. Components are placed next to the largest one by whole
lattice translations. The camera is framed from the largest component plus
any component that is comparable in size (at least 50%) or packed against
it. Single peaks and small remote fragments are drawn only as a faint
secondary layer inside that sphere, and they never set the Fit bounds. This
is a viewer filter only. On the real koala2 P2₁/n EDMA output, the previous
builder never grew anything: the 334-peak asymmetric unit was already over
its 200-atom cap, so it showed the raw asymmetric unit with a fit radius of
about 22 Å. The new view completes the cluster, with a fit radius of about
15 Å.

**Camera fit**: derived from the displayed content, with no fixed zoom
factor (`PRESENTATION_ZOOM_FACTOR` is removed). Each panel is framed on its
own bounding sphere, with cubic limits, a 1:1:1 box and ortho projection.
The sphere's projected size at zoom 1 is measured from matplotlib. It does
not depend on rotation or canvas size, so the fit is crop-free while the
view auto-rotates. Targets: molecules at 78% of the panel's drawing square,
Full cell at 92% of the sphere around the cell frame and every drawn atom.
Zoom and pan are synchronized as a relative zoom/pan of each panel's own
fit.

**Bond sanity**: `bond_graph_problems()` rejects an O(N²) bond count,
duplicate bonds, self-bonds, over-cap bond lengths and coincident duplicate
atoms. Full cell still draws no bonds.

**Checks**: `test_jana_wizard_tile_icons.py` now checks the icon inventory,
assets and icon-drawing functions against the approved set, compares every
Wizard and Autosolve action's icon pixel-for-pixel with its inventory
source, and checks paired tile geometry, focus stability and warning
alignment. `test_autosolve_window.py` adds checks for completed molecules,
orphan peaks, fill (60–80%, no crop at 6 rotations), Full-cell frame
visibility, per-panel fit, relative zoom, bond sanity, the lock-hint
removal, compact progress and pass-now gating. Offscreen screenshots at
QT_SCALE_FACTOR 1, 1.25 and 1.5 found no horizontal or vertical label or
button clipping in any of the 9 states.

## Final visual QA and Autosolve context

### Wizard text clipping (root cause and fix)

After a real `.inflip` loaded, the main tiles' titles and subtitles had their
glyphs cut off. The Wizard pins its page stack with `setFixedHeight()` to the
current page's height. The `.inflip` input summary is filled in one
event-loop turn later, with the two-line cell, reflection counts, composition
and "From .inflip" notes, and that made page 1 taller than the pinned height:
488 → 505 px on `ucla-sharped_Superflip.inflip`. Qt then squeezed the
compressible tiles below their own minimum. The tiles got 61 px instead of
69, the title 16 px instead of 22, and the subtitle 15 px instead of 17. This
happened at every scale. The fixes:
- The stack is never pinned below the page's `minimumSizeHint()`.
- After population, the posted layout requests are flushed and the stack is
  re-pinned before anything paints.
- Every page is watched for `LayoutRequest`, so any later growth re-fits the
  dialog.
- `QFormLayout` mis-distributed height between word-wrapped rows, cropping the
  two-line Cell value. Each summary value's minimum is now its own
  height-for-width.

`test_wizard_text_clipping.py` runs child processes at 100/125/150% on a
populated `.inflip`, including descender strings.

### Tile icons

The only established Phase Studio icons are the monitor mark, the chain
glyph, and Qt's warning and information icons. By decision, the four primary
tiles use shipped Qt standard icons from one monochrome family. No artwork
was drawn.

| Tile | Qt standard icon |
|---|---|
| Original Superflip | `SP_MediaPlay` |
| Autosolve | `SP_MediaSeekForward` |
| Solve the phase problem | `SP_FileDialogDetailedView` |
| Predict the structure model | `SP_FileDialogListView` |

All of them are listed in `ESTABLISHED_ICON_INVENTORY`.

### Autosolve window

- **Execution Log:** its viewport is exactly N measured row pitches plus the
  document's bottom margin, with N from 3 to 6 by screen height. Auto-scrolled
  to the newest message, the top edge lands on a row boundary. It re-sizes
  when the horizontal scrollbar appears.
- **Formula:** 11.5pt (was 10pt), formula only.
- **Complete molecules:** hides the faint unassigned-peak layer. It was already
  excluded from Fit.
- **Input line:** "Jana2020 input: <basename>" appears as a secondary line,
  middle-elided so `.inflip` stays visible, with the full path in the tooltip.
  The source is the backend's captured `RunConfig.jana_inflip`, or before a
  run starts, the path the window was launched with.
- **Element legend:** a strip between the view controls and the structures.
  It shows the union of elements actually rendered in the current mode, using
  the renderer's own `_element_color` (no second palette), and wraps when many
  elements are present.

## Element colours (period-based)

The legend exposed that the original brand-blue palette gave Ag and S the
same colour, and O, Cl and Au another shared one. After an interim CPK-style
table, 2.0.0 uses a **systematic period-based colour system**.

`app.element_color()` is the single colour authority.
`IterativeSuperflipPipelineQtGUI._element_color` delegates to it, and it is
used by the Professional comparison, the result-selector preview, every
Autosolve panel and the element legend.

How a colour is derived:
- The element is resolved through the existing parsing (`clean_element_symbol`
  and `element_atomic_number`, which is gemmi's element data), giving Z.
- Z gives the period and the position within the period (1–118).
- The period selects a CIELCh hue family:
  - 1: slate blue-grey
  - 2: red/orange
  - 3: olive/yellow-green
  - 4: green
  - 5: teal/cyan
  - 6: blue-violet/purple
  - 7: magenta/rose
- The position adds a deterministic hue offset, plus alternating lightness
  (L* 50/64 for short periods, 40/54/68 for long ones) and chroma.
- Lanthanides and actinides inherit the period 6 and 7 families.
- There is no per-element colour table. Unknown labels get one neutral grey,
  `UNKNOWN_ELEMENT_COLOR`.

Measured on white:
- all 118 elements are at least 2.19:1 against white, and none is near-black
  (L* at least 39.8);
- the tested pairs are at least ΔE76 14: C/N, C/O, O/F, O/Cl, Si/P/S/Cl,
  Fe/Co/Ni, Cu/Zn, Ag/Cd, Pt/Au, Au/Hg, Au/S (113), C/Au, and the old
  collisions;
- every same-period neighbour pair is at least 11.

Only colour changed. Coordinates, radii, bonds, camera, maps and data are
untouched. Colour encodes chemical identity only.

`test_element_colors.py` pins all of this, and fails if any element-to-colour
dictionary appears in the package.

## Experimental: data-driven EDMA threshold calibration (disabled by default)

**Production Autosolve thresholds for 2.0.0: Superflip 1.20 σ, SharpED
2.00 σ (fixed).** Autosolve does not calibrate thresholds.

`phase_studio/edma_threshold.py` implements an experimental per-map
calibration. It is **disabled by default and not validated for production
use**. It is reachable only through the development constant
`AUTOSOLVE_EDMA_THRESHOLD_MODE` (`"manual"` in 2.0.0) or
`RunConfig.edma_threshold_mode`. It has no UI control and is not a documented
user feature.

**Engine.** For each map, the existing EDMA extraction runs over
3.0 → 0.6 σ (10 coarse points, then up to 3 fine points at 0.05 σ). Runs go
4 in parallel and are cached by map SHA-256, σ, EDMA settings, the executable
hash and composition. Each candidate is scored as follows:
- Candidates are extracted with composition-only element assignment, so the
  result does not depend on whether a reference is loaded.
- Fcalc is computed with gemmi (X-ray IT92, point atoms, full symmetry) on the
  original measured reflections.
- Scaling is k·exp(−B·s²/4).
- The criterion is model R_free / CC_free when a genuine holdout exists,
  otherwise all-data R_F / CC_F, labelled non-independent.

Selection is a constraint/plateau rule:
1. Hard rejections: short contacts, over-population against a composition
   plausible for the cell, and isolated-peak explosions.
2. A MAD change-point on newly appearing peaks marks the instability onset.
3. The plateau is the set of candidates within a practical-equivalence margin
   of the best R and the best CC (δ_CC = 0.01, δ_R = 0.005, paired bootstrap,
   one-sided 95%).
4. The lowest σ on the plateau is chosen.

**Real validation, frozen as a failed validation of this criterion.** The
reference was used only to score the choices afterwards. The dataset is
koala2: Ag cluster, P2₁/n, **single-crystal X-ray, Mo Kα 0.71073 Å, 95 K**,
per Jana `m95`: `lambda 0.71073 radtype 1`. It is not electron diffraction;
"koala" is the SharpED model name.

| Map (koala2 cycles 2 / 5 / 9) | Auto σ → F0.5 | Fixed σ → F0.5 |
|---|---|---|
| Superflip | 1.85 → 0.48 · 2.10 → 0.39 · 1.90 → 0.46 | 1.20 → 0.55 · 0.55 · 0.55 |
| SharpED | 2.85 → 0.51 · 1.80 → 0.54 · 2.85 → 0.51 | 2.00 → 0.54 · 0.54 · 0.53 |

Under the first, strict-significance criterion, Superflip reached
0.36–0.47. SharpED is about equal or slightly worse overall.

- **Runtime:** about +100–110 s per 43 MB koala2 map, roughly +70% per
  cycle, and 454 s on a 120 MB map.
- **Held-out 2int3total:** also X-ray Mo Kα. It was unsolved at every
  threshold (F0.5 at most 0.055), and its "SharpED" map is byte-identical to
  its Superflip map, so it could not validate.

**Scattering-factor audit.** For koala2, X-ray IT92 factors were physically
appropriate, so the failure is not a radiation mismatch.
- **Rank correlation:** on these correctly modelled X-ray maps, kinematic
  model agreement is *negatively* rank-correlated with structural quality
  across the thresholds of every map:
  - Spearman ρ(CC_F, F0.5) = −0.49 to −0.96;
  - ρ(−R_F, F0.5) = −0.66 to −0.92.

  Point atoms, quota element labels and 0.2–0.4 Å peak-position errors mean
  that adding correct peaks lowers agreement.
- **Variants tried:** charge-weighted and resolution-restricted variants,
  tried on the development set, showed the same behaviour.
- **Freeze:** the result is frozen. The margins are not to be retuned against
  koala2.

**Radiation awareness required for any future work.** Model-to-data
agreement must use the scattering model of the experiment:
- X-ray data: X-ray factors (gemmi `StructureFactorCalculatorX`, IT92);
- electron diffraction: electron factors, where gemmi 0.7.5 already provides
  `StructureFactorCalculatorE`, `DensityCalculatorE` and the C4322 electron
  coefficients (International Tables Vol. C, Table 4.3.2.2), with no new data
  source needed;
- neutrons: gemmi `…N`.

The current engine is X-ray-only and must not be applied to ED amplitudes.
Even with electron factors, 3D ED amplitudes carry substantial dynamical
scattering, so a simple kinematic R_F / CC_F may not track structural quality
at all. That has to be shown on solved ED data, not assumed.

**Future validation datasets.** At least one additional **solved** dataset,
preferably one X-ray and one 3D ED, each with:
- real measured reflections and a reliable reference structure;
- a non-trivial EDMA threshold dependence;
- SharpED output distinct from Superflip output;
- enough quality that F0.5 separates thresholds.

No electron-diffraction dataset exists in the current development data.

## Remaining manual acceptance

Not performed as part of this change: a real Jana2020/SharpED-server/Superflip
end-to-end run (no such environment is available here — only offscreen Qt
with faked subprocess/network calls). AutosolveWindow was visually reviewed
via `QWidget.grab()` screenshots rendered through the offscreen Qt platform
(2-tile/3-tile layout, idle/running/busy/complete states, the 9-scenario
UI-quality-pass acceptance set at 100%/150% scale factors) — a real-display,
high-DPI pass on Windows has not been done. Both are listed explicitly so
they are not mistaken for "done."
