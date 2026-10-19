# HKL scientific typography and UI refinement — 2.0.4

> Historical acceptance snapshot. These post-release changes are now assigned
> to **2.0.5 (unreleased)**. The subsequent final-polish report is
> `HKL_ADVANCED_FINAL_POLISH_2_0_5.md`; the preferred Advanced Diagnostics height
> is now 530 logical pixels. Older evidence retains its original filenames.

This is a presentation change on the current working tree based on `75600c4`.
**No established scientific algorithms or numerical outputs changed.** The
application version remains 2.0.4. No commit, push, tag or release was created.
The earlier, uncommitted Jana Wizard geometry work and `docs/workshop/` were
preserved.

## Implementation

Files belonging to this pass:

- `phase_studio/scientific_typography.py`: shared Qt rich-text and Matplotlib
  mathtext vocabulary; scoped scientific table header rendering.
- `phase_studio/hkl_diagnostics_ui.py`: Advanced Diagnostics layout, summaries,
  contextual bin tables and overlap chart presentation.
- `tests/test_hkl_ui_refinement.py`: mathematical markup, real subscript
  structure, rendering, schema vocabulary and cross-bin record semantics.
- `tests/test_hkl_advanced_ui.py`, `tests/test_hkl_presentation_ui.py`,
  `tests/test_hkl_diagnostics_ui.py`: existing GUI guards updated for actual
  rich text, percentage display, categorical group sizes and contextual tables.
- `packaging/tools/capture_hkl_refinement_204.py`: reproducible actual QtAgg
  screenshots and assertions at three scale factors.
- This report.

The typography layer uses italic principal variables with upright descriptive
subscripts, including d-min, d-98, observed intensity/amplitude, significance,
unit-cell parameters, angles and supported R-factor names. Mathematical `sin`
is upright. Degrees 2θ retain the verified physical interpretation. Normal
prose, technical abbreviations and product names remain upright. In particular,
the English article “a” is not treated as a cell parameter in prose.

Tables retain plain header item text for sorting and accessibility. A scoped
`QHeaderView` paints the rich display using `QTextDocument`; numeric data cells
contain no markup. Matplotlib uses mathtext and constrained layout. No global
application font policy changed; Science Gothic remains restricted to the
existing wordmarks.

Copy summary supplies formatted HTML together with the unchanged plain-text
summary. JSON field names, CSV schemas and raw report definitions are unchanged.
Export CSV continues to export the established shell-statistics schema even
when the overlap view is selected; Export plot continues to export the active
figure. The original report retains complete overlap membership and metadata.

## Advanced Diagnostics

All seven existing tabs remain, with a preferred initial size of 1050 × 600 Qt
logical pixels. Existing geometry/tab persistence, screen clamping, independent
window ownership and fixed Close footer are retained. Each tab has its own
vertical scroll area; navigation and disclosures do not resize the window.

Counts & symmetry has separate reflection-count and crystal-symmetry sections.
The parsed-record count is prominent; the original space-group setting and Hall
symbol remain accessible in tooltips/provenance. Cell lengths and angles have
individual rows. Labels use adaptive column proportions rather than a fixed
narrow label width.

Resolution presents the actual minimum resolution, cumulative 98% boundary,
coverage and domain before short definitions and the full expandable original
methodology. The completeness dialog reuses its existing analysis. Opening
Advanced Diagnostics from Validation obtains the resolution summary once using
the existing `analyze_hkl_data` authority and already-loaded records. Invalid or
origin-only input still opens diagnostics, with an explicit unavailable reason.

Peak overlap shows four primary metrics once: overlapping groups, affected
records with denominator and percentage, input-intensity fraction, and largest
group. Secondary group totals and a discrete two-column group-size breakdown
are in Group details. Verified wavelength, units and the grouping criterion are
concise; full provenance and denominators remain in Overlap methodology.
The warning about geometric groups, experimental independence and the absence
of intensity repartitioning remains visible.

## Completeness plots and contextual bins

Analysis retains its original shell values. Peak overlap switches the lower
table to interval limits, original input records, affected original records,
affected percentage and the within-interval physical input-intensity fraction.
The Advanced Diagnostics action is a normal right-aligned secondary button.
The vertical chart/table splitter initially favors charts, approximately 65/35,
and the fixed export/Close footer remains outside it.

Group sizes are discrete categories, for example “2 HKL”, rather than a
continuous half-integer axis. Bars display their exact counts. The resolution
plot displays 100 × the existing overlap fractions on a 0–100% scale. Underlying
fractions and exports retain their original values.

The overlap QtAgg canvas has a practical minimum height and its own vertical
scroll area when constrained. Constrained layout keeps full axis labels and
titles inside the canvas. Enlarging the table cannot paint it over the plots.
Actual embedded canvases were rendered and their label bounds checked; this is
not solely a standalone Matplotlib image test.

### Cross-bin convention and unavailable data

No new group-to-bin convention was introduced. The group-count column is
deliberately omitted because a transitive group can cross interval boundaries.
Each original non-000 record contributes to exactly its existing `(lo, hi]`
interval; affected status is taken directly from authoritative global group
membership. No groups are recalculated, split, merged or counted twice.

The overlap table and plot use identical existing shell boundaries. Affected
percentage is affected original records / original input records. The intensity
percentage is the sum of input intensities of affected records / all input
intensities in that interval; it is unavailable for zero denominators or invalid
physical intensities. Empty intervals display N/A, not zero. Small record-count
intervals use modest display precision and retain full numeric values in item
metadata. Global statistics are untouched.

No overlap tab or fabricated statistics are shown without the existing verified
capability. Existing missing-wavelength prompts remain. FWHM is never promoted
to measurement uncertainty. The optional additional per-group inspection panel
was not added; original membership remains available in the diagnostic export.

## Numerical preservation

Real reference input: `build/powder-final/wizard-input/ochlor_Superflip.inflip`,
SHA-256 `9136270c5e8ab6850ac6bd4390c301f17a32dcc83994184d8562735b9a26b88c`.

| Quantity | Original accepted result | Final result |
|---|---:|---:|
| Parsed records | 631 | 631 |
| Literal HKL / symmetry-independent orbits | 631 / 631 | 631 / 631 |
| Excluded 000 | 0 | 0 |
| Overlapping groups | 91 | 91 |
| Total / non-overlapping groups | 529 / 438 | 529 / 438 |
| Affected original records | 193 | 193 |
| Affected fraction (%) | 30.5863708399 | 30.5863708399 |
| Input intensity fraction (%) | 21.0635613111 | 21.0635613111 |
| Largest group | 4 | 4 |
| Groups of size 2 / 3 / 4 | 81 / 9 / 1 | 81 / 9 / 1 |
| Minimum resolution (Å) | 1.1990790613015834 | 1.1990790613015834 |
| Cumulative 98% boundary (Å) | 1.1990790613015834 | 1.1990790613015834 |

Original and post-navigation JSON exports are byte-identical within each DPI
run, and the scientific input file hash remains unchanged. All three DPI runs
produce identical scientific values. `preservation.json` records those results.

`app.py`, `hkl_diagnostics.py` and `powder_diagnostics.py` match HEAD exactly
after normalizing Git line endings. AST comparison also confirms the existing
report/presentation and numeric-formatting authorities are unchanged. The
previous dirty Wizard source still has SHA-256
`887d5e964ac4dd2ef0927b6c85fdb30a648ac15e54e036fd025bb1a0ae0baf55`.
Superflip, SharpED, EDMA, structure exports and Jana handoff were not modified.

## Visual acceptance

Evidence: `build/acceptance-hkl-ui-refinement-2.0.4/index.html`.
There are 45 actual PySide6 screenshots: 15 per scale factor 1, 1.25 and 1.5.
The harness declares an available 2560 × 1600 physical-pixel work area; Advanced
Diagnostics remains 1050 × 600 logical pixels at all three scales. Existing
GUI tests separately exercise constrained screens and geometry restoration.

Each DPI directory includes:

1. Completeness — Analysis.
2. Completeness — Peak overlap.
3. Enlarged overlap resolution table.
4. Advanced — Input.
5. Advanced — Counts & symmetry.
6. Advanced — Absences & duplicates.
7. Advanced — Values.
8. Advanced — Resolution.
9. Advanced — Peak overlap, collapsed.
10. Advanced — Availability & limitations.
11. Expanded overlap methodology.
12. Expanded discrete group details.
13. Format-verified amplitude/sigma controlled fixture.
14. Controlled powder fixture with varying verified widths.
15. Controlled input without overlap capability.

Images 01–12 use real ochlor data. Images 13–15 are explicitly labelled synthetic
fixtures; their declared sigma values test genuine uncertainty-column semantics,
not experimentally verified measurements. The cross-bin and zero-denominator
cases have separate numerical/GUI regression assertions. Every screenshot was
visually inspected in DPI contact sheets, with additional full-size inspection
of the overlap graphs, crystal symmetry, input provenance and resolution.

These are offscreen Qt rendering tests. Physical-monitor transitions, native
Windows title-bar behavior and a live Jana2020 session were not manually tested
in this pass. No inference request, phasing run or live handoff was performed.
No executable was rebuilt or distributed in this UI-only task.

## Verification

- Focused HKL, powder and three-DPI GUI tests: **45 passed**.
- Final contextual-bin/origin-only GUI and typography guards: **11 passed**.
- Final typography, mathtext and cross-bin checks: **10 passed**.
- Scientific golden checks (`tests/test_scientific_core.py`): **46 passed**.
- Final complete pytest suite: **367 passed, 1 skipped, 37 subtests passed** in
  **316.13 s**, recorded in `build/hkl-refinement-completed-suite.log`.
  The preceding complete run also passed (314.84 s). The final focused set
  passed again after the tooltip refinements: **45 passed** in 32.27 s,
  `build/hkl-refinement-completed-focused.log`.
- All three actual QtAgg capture runs: passed, including unchanged report/input
  hashes, seven-tab geometry and embedded axis-label bounds.
- Python compilation and `git diff --check`: passed.

The skipped test is the existing opt-in real-project applicability check.
No scientific expected values were updated to make tests pass. Screenshot
inventories remain under ignored `build/`; no large acceptance directory was
added to version control.
