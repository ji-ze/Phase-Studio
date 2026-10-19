# HKL Completeness — scientific clarity and interaction acceptance

Version remains **2.0.5**. This pass changes the existing read-only HKL dialog,
not Superflip, SharpED, EDMA, ranking, Map Feedback or Jana handoff. No internet
research, new dependency, executable build or release publication was used.

## Implementation

- Powder summaries and tables identify **Indexed HKL coverage**, with a tooltip
  defining representation of symmetry-allowed orbits and explicitly excluding
  any claim of experimentally independent or resolved powder observations.
  Advanced Diagnostics retains the complete accepted definitions.
- Separate card-level explanations distinguish d_min from the existing
  cumulative ≥98% d98 definition, including when their numerical values match.
  Existing Qt rich text, scientific table-header painting and Matplotlib math
  text retain italic variables, proper subscripts and upright units.
- A saved presentation-only axis preference switches between sin θ / λ and d,
  using d = 1/(2 sin θ / λ). Nonpositive or nonfinite coordinates are unavailable,
  never invalid plotted resolutions. The d axis runs from larger to smaller d.
  Analysis, Peak overlap, bin tables and hover descriptions share the convention;
  each tab has its own synchronized axis control. Canonical bins do not change.
- Hover inspects existing histogram bars or existing resolution-line points.
  It reads canonical bin statistics and input-record counts, does not scan the
  raw dataset on movement, and does not redraw the Matplotlib canvas.
- Histograms retain their original bins and values. Controls provide full,
  percentile-focus and custom ranges, explicit Apply/Reset, linear/log counts
  and counts of observations outside the viewport. Sorted raw values allow
  O(log N) outside-range queries. Zero-count bars are hidden in log mode.
- Visual acceptance caught a real rendering defect: masking the zero baseline
  of a positive log bar removed its whole polygon. Clipping that drawing
  baseline while keeping zero-count bins hidden restores positive bars without
  changing counts, bins or introducing invented logarithmic observations.
- Overlap group sizes remain discrete categories with counts above bars. The
  overlap curve uses the exact title **Input HKL records in overlapping groups
  (%)**, percentage ticks and a zero-based, data-dependent upper limit capped
  at 100%. Ochlor's approximately 45% maximum produces a 50% upper limit.
- Read-only group inspection uses the existing diagnostic HKL → group mapping.
  It does not call a grouping/repartitioning algorithm. It shows group IDs,
  original HKL/value/FWHM, group size and d; calculated 2θ is available only
  with verified positive finite wavelength metadata. Missing exact membership
  disables inspection. Nearest-neighbor separations are not stored by the
  diagnostic and are explicitly omitted, rather than reconstructed.
- Group-size and canonical resolution-interval filters preserve transitive
  membership. Selecting a bin limits the inspector; clicking a group-size bar
  opens its corresponding filter. Exact initial shell edges survive an Apply
  that changes only group size, despite rounded spin-box presentation.
- The inspector uses QAbstractTableModel/QTableView and stable NumPy numeric sorting,
  not a widget per record. Original record order is retained until the user
  asks to sort. Replacing the scientific header before enabling sorting avoids
  an unintended initial sort of large datasets. Repeated modal inspectors are
  released after closing. Copy includes full-precision original cell values.
- Bin tables have explicit Bin min/Bin max headers, numeric sorting and row
  alignment, interval tooltips and selected-row copying. Normal 1120×900
  presentation preserves at least five rows; the table minimum reserves five rows. Footer
  actions remain fixed. Existing independent chart/table scrolling remains
  available at reduced logical heights.

## Scientific parity on actual inputs

The capture tool reparses the local reference inputs with the existing request
and cached-analysis APIs. It verifies their original source hashes, compares
the saved pre-change UI implementation against the current presentation, and
exports again after display interaction. CSV and JSON are byte-identical
before/after for both inputs. No golden numerical expectation was changed.

| Input | Records | d_min (Å) | d98 (Å) |
|---|---:|---:|---:|
| ochlor | 631 | 1.1990790613015834 | 1.1990790613015834 |
| 2int3total | 328606 | 0.7255092594101177 | 0.8161153076022714 |

Ochlor retains all verified overlap results:

- 529 total groups; 438 singleton groups; 91 overlapping groups.
- 193 affected records, 30.58637083993661% of the 631 input records.
- 21.06356131111815% of finite nonnegative physical input intensity in
  overlapping groups; this denominator is explained in the metric tooltip.
- Largest group: 4. Distribution: 81 groups of 2, 9 of 3 and 1 of 4.
- The inspector contains exactly 193 original records with the same group IDs.

Original source SHA256 values:

- ochlor: `9136270c5e8ab6850ac6bd4390c301f17a32dcc83994184d8562735b9a26b88c`
- 2int3total: `07a3de15e54ba130f75e960358aef1ff6087b09f0ea5d9604f00090cb9d21642`

Local evidence includes fresh JSON/CSV comparisons, source hashes, complete
overlap counts and timing measurements under
`build/acceptance-hkl-completeness-2.0.5/`. Timing is local CPU/Qt acceptance,
not a physical-monitor or GPU benchmark. On the initial measured run, the large
dialog constructed in approximately 0.5 s excluding first paint; five explicit
axis-change renders took approximately 1.5 s. Queued-update timings are recorded
separately and must not be described as frame-render latency.

## Automated verification

- Focused HKL/GUI suite: **44 tests passed**, including the real-button,
  log-bar rendering and 100,000-record sorting/filtering checks.
- Complete suite: **427 passed, 1 skipped, 37 subtests passed**, 444.17 seconds.
  This includes the existing scientific, workflow-state and authentication guards.
- New interaction cases cover axis conversion and invalid coordinates, powder
  versus amplitude labels, log/linear bars, custom/reset ranges, outside counts,
  hover without redraw, categorical sizes, percentage limits, numeric copying,
  exact group membership and boundary filtering, export parity, missing
  wavelength/membership, nonfinite-only and constant/zero/negative histograms.
- A 100,000-record synthetic inspector verifies lazy cells and bounded widget
  count. The eight new tests, including that fixture, pass in approximately
  2–3 s after removal of the unintended initial sort, including an explicit
  descending sort and preservation of that order after filtering.
- Existing scientific golden script: **46 checks passed**.
- Existing Jana completion script: **192 checks passed**.
- One existing UI export assertion was updated to the explicitly requested
  overlap chart title. Numerical reference expectations remain untouched.
- Source/test/tool compilation and `git diff --check` passed. Diagnostic CSV
  and JSON schemas were not edited; both real-input byte comparisons passed at
  all three captured scale factors, including exports after UI interaction.

## Visual evidence

The reproducible tool is `packaging/tools/capture_hkl_completeness_205.py`.
It produces ten actual Qt captures at each of 100%, 125% and 150% scaling,
including the baseline, both Analysis axes, log counts, Peak overlap, selected
bin, group details, reduced geometry and the large amplitude input. These use
real diagnostic data; only the automated 100,000-record table test is synthetic.

Representative local files:

- [Before Analysis](../build/acceptance-hkl-completeness-2.0.5/scale-1.0/00-before-analysis.png)
- [Analysis](../build/acceptance-hkl-completeness-2.0.5/scale-1.0/01-analysis-default.png)
- [Alternative d axis](../build/acceptance-hkl-completeness-2.0.5/scale-1.0/02-analysis-d-axis.png)
- [Log histogram](../build/acceptance-hkl-completeness-2.0.5/scale-1.0/03-histogram-log.png)
- [Peak overlap](../build/acceptance-hkl-completeness-2.0.5/scale-1.0/04-overlap.png)
- [Selected bin](../build/acceptance-hkl-completeness-2.0.5/scale-1.0/05-overlap-selected-bin.png)
- [Group inspection](../build/acceptance-hkl-completeness-2.0.5/scale-1.0/06-overlap-group-detail.png)
- [Reduced window](../build/acceptance-hkl-completeness-2.0.5/scale-1.0/07-reduced-window.png)
- [150% overlap](../build/acceptance-hkl-completeness-2.0.5/scale-1.5/04-overlap.png)

These are offscreen Qt captures with controlled logical screen geometry. At
shorter logical heights, plots retain independent scrolling so their complete
axes remain accessible; this is not claimed to show every full plot and table
simultaneously without scrolling. The fixed footer remains reachable. No
physical-monitor, live Jana or new phasing acceptance is claimed.

## Changed source and scope

Production changes are confined to `phase_studio/hkl_diagnostics_ui.py`.
Regression changes are in `tests/test_hkl_completeness_interactive.py` and the
existing title assertion in `tests/test_hkl_diagnostics_ui.py`; the capture tool
and this report provide acceptance evidence. Existing workshop drafts remain
untouched. There is no new EXE or release in this task.
