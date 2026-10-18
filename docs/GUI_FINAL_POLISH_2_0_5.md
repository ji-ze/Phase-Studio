# Final GUI polish — Phase Studio 2.0.5

Scope: initial Jana2020 Wizard, HKL Validation and HKL Completeness. Version remains
2.0.5, unreleased. Existing unrelated working-tree changes were retained. This
pass performs no EXE build, commit, push, tag, release or PR, and makes no external
documentation requests or live SharpED calls.

## Findings and classification

- **Reproduced defect:** at a simulated 1920×1080 desktop with 150% Qt scaling,
  the two-panel Analysis canvas could extend below its visible tab page with no
  way to reach the lower axis labels. Its minimum height exceeded the remaining
  space. The existing overlap page also required too much minimum space.
- **Not reproduced:** disappearance of the footer itself. Before changing the
  source, Close was inside the declared work area at all three tested sizes.
  Screenshot cropping, a particular Windows/taskbar configuration or another
  physical-monitor cause remains unconfirmed. No claim is made that the supplied
  screenshots prove a specific footer defect.
- **Existing behavior retained:** full-dataset prefix search, signed numeric
  sorting, bounded previews, scientific report/export authority, vertical
  splitter, four powder-overlap KPIs, logarithmic counts, async update checks,
  disclosure, workflow routing, and approved scientific SVG icons.
- **Presentation improvements:** explicit verified input type, labelled cell
  variables, clearer card states, compact summaries, visible search, selected-row
  copying, truthful interval/intensity labels, shared update/About access, and
  safe presentation-state persistence.
- **Optional enhancement implemented:** histogram focus changes only the visible
  x-range. Optional selected-HKL CSV export, median series and point hover were
  deferred to keep this pass focused.

## Jana2020 Wizard

The Reflection data section now shows `Powder / polycrystalline`, `Single crystal`
or `Not available / unverified`. Classification requires the common diagnostic
report's verified column semantics; filenames and AUTO guesses are not evidence.
The real ochlor input shows the powder label. Declared amplitude/phase/uncertainty
columns remain visible for amplitude data. The verified powder tooltip explicitly
states that FWHM is a peak width in degrees 2θ, not a measurement uncertainty.

Cell lengths and angles use labelled a, b, c, α, β, γ through the existing
scientific renderer. Original `.5g` length and `.4g` angle precision is retained.
No cell or symmetry data was transformed.

Normal, recommended, hover, focus, pressed and disabled cards have distinct scoped
styles. Recommended remains a subtle recommendation, not an active selection.
The existing darker recommendation/runtime text and four SVG assets, including
Autosolve B, are retained. Card body and child-title clicks, Enter and Space are
tested; disabled cards do not activate. Existing dispatch and debounce remain.

Advanced input options remain collapsed initially, with the existing optional
reference/initial-model tooltip. Expansion retains fixed Cancel and permits
scrolling to both secondary cards. The collapsed 1000×760 layout fits without a
scrollbar when the available logical work area permits it. Smaller work areas
scroll content rather than hiding Cancel or squeezing text.

The version control remains in the brand header. Its tooltip is `Version and
updates`, and its existing Check for updates and notification preference actions
are followed by About Phase Studio. About reads the runtime version authority.
The update service, release destination and asynchronous behavior are unchanged.
Science Gothic remains restricted to the branding wordmarks.

## HKL Validation

The top hierarchy retains source/format, cell/symmetry, three concise counts and
an interpretation note. Detailed absence/duplicate/invalid counters remain in
tooltips, Advanced diagnostics and unchanged exports. `PARSED`/warnings are not
renamed `VALID`.

The explicitly documented **input-integrity issue tally** is the sum of:

1. Invalid input-value records.
2. Invalid auxiliary widths/uncertainties.
3. Nonfinite supplied phases.
4. Invalid reciprocal values.
5. Rejected records.
6. Exact duplicate entries.
7. Conflicting duplicate groups.

Categories may overlap and mix records with groups; the tally is deliberately
not described as a count of distinct faulty reflections. All seven counters are
provided by the authoritative report. Zero is not proof of scientific validity.
Systematic absences are shown separately, because their presence alone is not
an experimental-error verdict.

Search is a bordered, focusable QLineEdit with a clear action and placeholder
`Find reflection (h k l), e.g. 0 2 0`. Existing one-, two- and three-index prefix
syntax is retained, including signed/zero indices. Filtering still visits all
parsed records after a 180 ms debounce, while creating at most 200 table rows.
The status distinguishes matches, total records and the preview cap. No per-cell
widgets or new full-dataset item model were introduced.

The h/k/l columns have equal narrow widths; numeric sorting handles negative
indices. Extended row selection and Copy selected rows/Ctrl+C include headers
and the original numeric values via their stored numeric objects, not rounded
display strings. Missing values copy as empty cells. Existing diagnostic exports
are unchanged. The main table occupies the remaining area; base footer actions
stay outside it.

The real 2int3total search targets its last parsed record, `-3 4 78`, beyond the
initial 200-row preview. One match among 328,606 records was displayed in about
**0.23 seconds including debounce and event processing**. This is one local
measurement, not a universal latency guarantee. Synthetic tests also cover
positive/zero/negative indices, no matches, clearing, sorting and multi-row copy.

## HKL Completeness, geometry and charts

The redundant INPUT SUMMARY heading/spacing is removed locally. Advanced
diagnostics occupies the shared Analysis/Peak overlap tab-bar corner, so it is
available on either page without a dedicated full row.

At the same logical geometry, the splitter begins at y=211 instead of y=279:
**68 logical pixels recovered above the splitter**. The minimum-size hint falls
from 548×907 to 540×641 for the real powder dialog. Measurement evidence is
`build/acceptance-gui-polish-2.0.5/geometry-comparison.json`.

The existing vertical splitter defaults to approximately 60/40 charts/table.
Noncollapsible panes have practical minimum heights. The bin table retains its
own scrollbar. A chart viewport exposes the entire legible canvas when space is
short; there is no enclosing whole-dialog scroll area. A short viewport may show
only part of a graph until scrolled, rather than making that part inaccessible.
The fixed Copy/export/Close footer remains below the splitter.

`hklCompleteness/windowRect` and `hklCompleteness/splitter` are additive QSettings
presentation keys in the established PhaseStudio user/application namespace.
Restore occurs after the builder's initial fit and clamps saved native frames to
the current screen work area. The old deferred second fit in the launcher is
removed because it would overwrite the restored geometry. Finished saves the
normal geometry and splitter allocation. Tests use an explicit isolated INI
format; production retains the usual configured Qt settings backend. Existing
scientific settings and credentials are untouched.

Tests exercise oversized/off-screen restoration, close/reopen, splitter restore,
maximized/restored windows, dataset/tab switching and constrained layouts at
actual Qt DPR 1, 1.25 and 1.5. The declared work areas account for a 40 physical
pixel taskbar on a 1920×1080 desktop. Native Windows monitor/taskbar acceptance
and live Jana2020 acceptance are **not** established by offscreen Qt tests.
On the 150% work area, the Wizard is 1000×637 logical pixels: its fixed Cancel
stays on screen and a 95-pixel content scroll exposes the secondary cards.
At 100% and 125% the collapsed Wizard needs no content scrolling. The shortened
150% chart viewport was also scrolled to its end to verify access to its bottom.

The real ochlor Analysis retains its two original plots, original histogram
records/binning and original mean-intensity points. Other data modes keep their
existing applicable panels; no scientific panel is fabricated to force two.
Plots reuse the shared mathtext renderer, existing compact fonts and constrained
layout. Peak-overlap group counts use integer ticks and retain categorical
`2 HKL`, `3 HKL`, `4 HKL` labels and exact bars.

Full range remains the default histogram view. Focus on main distribution sets
only x-limits to the 1st–99th percentiles and labels the view as focused with
tails retained. It does not filter records, rebin, alter statistics or change
CSV/JSON. Linear/log counts remain independent. Regression tests compare the
actual histogram patches before/after focus and verify return to the full range.

## Peak overlap definitions

Visible interval headers are Low/High; the section states `sin θ / λ (Å⁻¹)` and
tooltips retain the original `(Low, High]` convention. Machine keys and exported
shell boundaries remain unchanged.

The final column is **Affected intensity in bin (%)**. Inspection of the existing
`overlap_bin_rows` authority confirmed exactly:

`100 × sum(original intensities of affected HKL records in this interval) /
sum(all original input intensities in this same interval)`.

This is not a percentage of the entire dataset intensity. All intensities in
the interval must be finite and nonnegative and the denominator positive;
otherwise the existing result is N/A. Cross-bin groups contribute each record
to its own original interval. Affected HKL means original indexed records in
geometric groups, not independent measured powder peaks. The global intensity
KPI continues to use its original global denominator. The calculation helper is
AST-identical to the pre-task source.

Coverage tooltips explain theoretical symmetry-allowed index coverage, not
independent experimental powder information. Existing missing-wavelength prompts
and suppression of wavelength-dependent overlap numbers/graphs are retained.

## Scientific preservation and real datasets

Original inputs were read-only and retain these SHA-256 values:

| Input | Parsed records | SHA-256 |
|---|---:|---|
| ochlor | 631 | `9136270c5e8ab6850ac6bd4390c301f17a32dcc83994184d8562735b9a26b88c` |
| 2int3total | 328606 | `07a3de15e54ba130f75e960358aef1ff6087b09f0ea5d9604f00090cb9d21642` |

Ochlor retains d_min = d98 = 1.1990790613015834 Å; 91 overlapping groups,
529 total groups, 438 singletons, 193 affected records (30.5863708399%),
21.06356131111815% global affected input intensity, largest group 4, and the
81/9/1 pair/triple/quad distribution.

2int3total retains d_min = 0.7255092594101177 Å, d98 = 0.8161153076022714 Å,
mean F/σ(F) = 4.010747623362957 and median = 0.6666518834009494.

The pre-task UI source snapshot is imported against the identical prepared input
objects. Old/new reports compare equal; original JSON and CSV bytes/hashes match
before and after this pass and after actual dialog interactions at all three
capture scales. Full hashes, counters, statistics and original overlap metadata
are in `ochlor-invariants.json` and `2int3total-invariants.json` under the acceptance
directory. Prepared-path metadata is held constant during this comparison.

`_report`, `presentation_report`, `overlap_bin_rows`, `_resolution_summary` and
numeric display helpers remain AST-identical. Shared scientific typography and
update-service source are unchanged. Wizard changes are confined to UI creation
and summary rendering. Parser/analysis algorithms, measured values, ranking,
maps, exports, EDMA/Superflip/SharpED processing and Jana handoff are unchanged.
The only app.py change removes the conflicting deferred completeness-window fit.

## Validation results

Final complete suite: **369 passed, 1 skipped, 37 subtests passed in 330.10 s**.
Focused layout recovery: 3 passed, including search, restored splitter/geometry
and both diagnostic dialogs at three DPRs. Wizard/menu/layout checks: 3 passed
at three DPRs. Broader focused run before the final geometry corrections:
19 passed; this is not substituted for the final complete-suite result.

Independent checks: **46 scientific golden checks**, **192 Jana completion
checks**, **141 workflow-state checks**, and **18 standalone Wizard text/icon
clipping checks** passed. Compileall and git diff
whitespace checks passed. During development, new restore tests detected a
queued-fit conflict and an inappropriate implicit native settings constructor;
both were corrected using the existing explicit settings-format pattern and
restore-after-fit order. Old cell-text expectations were updated to the requested
labelled rich text while preserving exact displayed numeric precision.

Logs: `build/gui-polish-complete-suite-final.log`,
`build/gui-polish-layout-recheck.log`, `build/gui-polish-wizard-final.log`,
`build/gui-polish-scientific-goldens.log`, `build/gui-polish-jana-goldens.log`,
`build/gui-polish-workflow-states.log` and `build/gui-polish-preservation.log`.

## Final screenshot inventory

Exactly ten unaltered actual Qt screenshots, all visually inspected, are in
`build/acceptance-gui-polish-2.0.5/`:

1. `01-wizard-collapsed.png`
2. `02-wizard-expanded.png`
3. `03-validation-powder.png`
4. `04-validation-full-dataset-search.png`
5. `05-completeness-analysis.png`
6. `06-completeness-overlap.png`
7. `07-completeness-splitter.png`
8. `08-completeness-constrained.png`
9. `09-wizard-dpi-125.png`
10. `10-completeness-dpi-150.png`

These are offscreen source-window captures, not packaged-EXE or live Jana2020
screenshots. `geometry-*.json` records actual Qt DPR, client/frame rectangles,
declared work area and the large-dataset search measurement. Baseline source
snapshots, exports and geometry evidence are local ignored build artifacts.

## Files changed in this pass

- `phase_studio/jana_superflip.py`
- `phase_studio/hkl_diagnostics_ui.py`
- `phase_studio/app.py` (presentation launcher only)
- `tests/test_gui_final_polish.py` (new)
- `tests/test_wizard_layout_polish.py`
- `tests/test_update_ui.py`
- `packaging/tools/capture_wizard_geometry_204.py` (existing interaction guard)
- `packaging/tools/capture_gui_final_polish_205.py` (new offline acceptance tool)
- `docs/GUI_FINAL_POLISH_2_0_5.md` (this report)

No existing unrelated modifications were reverted. No new executable was built;
the previously produced 2.0.5 EXE predates this source polish.
