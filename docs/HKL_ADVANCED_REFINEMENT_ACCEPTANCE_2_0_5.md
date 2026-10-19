# HKL Advanced Diagnostics — final presentation refinement (2.0.5)

Implemented offline against the existing 2.0.5 working tree. This supplements
`HKL_ADVANCED_FINAL_POLISH_2_0_5.md`; its older 1050 × 530 initial geometry is
superseded here. The preceding Completeness improvements remain present.

## Changes

- The initial client size is 1000 × 600 logical pixels, clamped to the available
  screen. Existing `hklAdvanced/geometry`, `size` and `tab` settings still restore
  user changes. Tab switches and disclosure expansion do not resize the window.
- Shared `_DiagnosticRows` uses a responsive label column up to 240 pixels,
  18-pixel spacing and top-aligned selectable values. The Counts panels use
  independent 200/100-pixel label columns and aligned section headings.
- Input retains the filename, exact-path copy and tooltip, and expanded provenance.
  One **Copy input summary** action includes the full source path, format, cell,
  symmetry setting, phase and provenance information. Ctrl+C copies the focused
  scientific value or selected Availability rows. QLabel selection/context copying
  remains available; literal paths are copied without mathematical conversion.
- Cell lengths retain four decimal places and angles three; each length has its
  own upright Å unit. Existing shared typography renders variables and subscripts.
- Counting tooltips explain original records, literal triplets, symmetry/Friedel
  conventions and protocol/excluded 000. Systematic absences have a definition.
- The all-clear integrity summary requires known zero counters. Unavailable
  significance is explicitly unassessed, never implicitly zero. Absent phase
  columns remain N/A; genuine zero-degree phases remain populated.
- Advanced Peak overlap reuses the existing original-record group inspector and
  its data/model; no regrouping or independent inspector implementation. The four
  summary metrics remain compact; affected fraction is shown to three decimals.
  Metric values are selectable. Validation and Completeness views provide their
  already analyzed original records to the inspector.
- Seven independently scrolling pages, fixed tabs/Close, wrapped availability
  reasons, Available/Limited/Unavailable distinctions, existing theme, Escape and
  Ctrl+Tab/Ctrl+Shift+Tab navigation are preserved.

Production change: `phase_studio/hkl_diagnostics_ui.py`.
Tests extended: `tests/test_hkl_advanced_ui.py`.
Reproducible capture/parity tool:
`packaging/tools/capture_hkl_advanced_refinement_205.py`.
Other pre-existing dirty files belong to the preceding Completeness task or
unrelated workshop drafts; they were preserved.

## Scientific preservation

The real ochlor and 2int3total inputs were freshly parsed locally. Before/after
dialog interaction, report dataclass equality, input SHA-256 and CSV/JSON byte
identity passed at 100%, 125% and 150%. Export bytes also match the preceding
accepted Completeness exports. The same prepared-HKL path is used for that
comparison, so provenance filenames are identical as well as scientific values.

| Quantity | ochlor | 2int3total |
|---|---:|---:|
| Parsed records | 631 | 328606 |
| d_min (Å) | 1.1990790613015834 | 0.7255092594101177 |
| d98 (Å) | 1.1990790613015834 | 0.8161153076022714 |

ochlor: 91 overlapping groups; 193/631 affected records;
30.58637083993661% affected fraction; 21.06356131111815% intensity fraction;
largest group 4; distribution 81 pairs, 9 triples, 1 quadruple.
The shared inspector displays the same 193 original records and group IDs.

Unchanged export SHA-256:

| Dataset | Export | SHA-256 |
|---|---|---|
| ochlor | CSV | `7aa9e2164cd4f2dd8909462e1f7c8ce20a4c2887a5f0a77d2edd330f676209dc` |
| ochlor | JSON | `3bf3bf470fffd90f025d9c3f880553e330a08f005edf2057fe808b4e5e153453` |
| 2int3total | CSV | `f968bd0257161ce598719a991ab6288f951743120e093cfe4b0b37d63eccfbc5` |
| 2int3total | JSON | `8295547c941a97e1a75cef7c4ab5ae0d67adc04b6937ae461ef18ade4f4a748b` |

No parsing, merging, crystallographic operators, cell geometry, resolution or
overlap algorithms, scientific export routines, Superflip/SharpED/EDMA logic,
ranking or Jana protocol was modified. No scientific golden was changed.

## Automated acceptance

- Focused HKL and GUI tests: **44 passed** (46.70 s).
- Extended advanced-view regression: **1 passed** (6.11 s), with isolated Qt
  checks at all three scales. Covers default/saved/clamped geometry, all tabs,
  disclosures, value/summary/path/Ctrl+C copying, tab keys, Escape, genuine and
  absent phases, unknown integrity counters, original-record inspector,
  availability, scientific formatting and immutable report/export guards.
- Scientific golden script: **all 46 checks passed**.
- Existing powder diagnostics and UI tests: **10 passed** (4.03 s).
- Jana completion script: **all 192 checks passed**.
- Complete project suite: **427 passed, 1 skipped, 37 subtests passed**
  (438.11 s / 7 min 18 s).
- Real-data capture/parity: **passed at 1.0, 1.25 and 1.5**.
- `git diff --check`: passed.

Logs: `build/hkl-advanced-refinement-{focused,final-ui,full,scientific,jana}.log`.

## Screenshots and visual review

36 final PNG screenshots (12 per scale), with machine-readable `evidence.json`,
are in `build/acceptance-hkl-advanced-refinement-2.0.5/scale-{1.0,1.25,1.5}/`.

Default tabs at 100%:

- [Input](../build/acceptance-hkl-advanced-refinement-2.0.5/scale-1.0/01-input.png)
- [Counts & symmetry](../build/acceptance-hkl-advanced-refinement-2.0.5/scale-1.0/02-counts.png)
- [Absences & duplicates](../build/acceptance-hkl-advanced-refinement-2.0.5/scale-1.0/03-absences.png)
- [Values](../build/acceptance-hkl-advanced-refinement-2.0.5/scale-1.0/04-values.png)
- [Resolution](../build/acceptance-hkl-advanced-refinement-2.0.5/scale-1.0/05-resolution.png)
- [Peak overlap](../build/acceptance-hkl-advanced-refinement-2.0.5/scale-1.0/06-overlap.png)
- [Availability](../build/acceptance-hkl-advanced-refinement-2.0.5/scale-1.0/07-availability.png)

Additional reviewed states:

- [Selected availability row, 150%](../build/acceptance-hkl-advanced-refinement-2.0.5/scale-1.5/08-selected-availability.png)
- [Expanded methodology, 125%](../build/acceptance-hkl-advanced-refinement-2.0.5/scale-1.25/09-expanded-methodology.png)
- [Methodology, 150%](../build/acceptance-hkl-advanced-refinement-2.0.5/scale-1.5/10-scrolled-methodology.png)
- [Shared overlap inspector, 125%](../build/acceptance-hkl-advanced-refinement-2.0.5/scale-1.25/11-original-overlap-records.png)
- [Small window, 150%](../build/acceptance-hkl-advanced-refinement-2.0.5/scale-1.5/12-small-window.png)

Reviewed screenshots show readable values, aligned cell fields, true subscripts,
wrapped explanations and accessible fixed Close buttons. Narrow windows use Qt's
tab-bar navigation arrows; long/expanded content remains vertically scrollable.

These are actual Qt offscreen captures with real device scale factors and a
controlled available-screen rectangle. Native monitor transitions and physical
display acceptance were not performed. No live Jana test, network authentication,
new inference, EXE build, push or release publication was performed for this task.
Version remains **2.0.5**.
