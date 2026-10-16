# HKL diagnostics modernization — Phase Studio 2.0.4

## Scope and audit baseline

Work started on `development/2.0.4` with the existing dirty 2.0.4 working tree
preserved. The pre-change source snapshot is
`build/hkl-modernization/app_before.py`. Baseline checks passed: scientific core
46/46 and final UI 30/30. The supplied real validation/completeness screenshots
were inspected; unmodified copies are under
`docs/screenshots/2.0.4-hkl-diagnostics/before/`.

Both Jana Wizard actions and standalone Basic/Input actions call the same
`test_hkl_load_dialog` / `open_hkl_completeness_dialog` entry points. Their
existing background-task delivery is retained, with cooperative cancellation.
The Wizard's own summary uses shared cached parsing; inputs larger than 1 MB
now load in a worker, with Qt-thread delivery of the completed summary.
No Professional initialization or window-activation logic changed.

Parsing still uses `parse_reflection_line`; solution workflows still use their
unchanged `read_hkl`. Diagnostic loading adds an explicit integral-index check
and reports rejected records rather than letting `int(float(index))` silently
truncate them. It retains negative values, nonfinite numeric raw fields and
the existing phase-format `000` protocol row for inspection. Missing/invalid
fields are not filled with invented scientific values.

Symmetry uses the existing parsed `CrystalMetadata.spacegroup`, Gemmi operations
and reciprocal ASU. No independent setting tables or new overlap algorithm were
introduced. Current text HKL inputs do not establish unmerged/scaled observation
provenance, anomalous measurement policy, or powder-profile data. The report
states these limitations instead of fabricating advanced metrics.

## Metric audit

| Metric | Original definition and validity | Final treatment |
| --- | --- | --- |
| Parsed records | Rows accepted by the existing parser; not proof of experimental validity | Retained, plus rejected-row/invalid-index diagnostics and examples |
| Unique reflections | Exact literal `(h,k,l)` groups after duplicate merging, including a retained protocol `000` | Explicitly labeled literal unique; separate physical symmetry-orbit count excludes `000` |
| Symmetry-independent count | Implicit in coverage, absent from validation | Explicit Gemmi ASU count; coverage's Friedel-combined convention disclosed; optional explicit non-Friedel orbit counting does not modify raw observations |
| Auxiliary coverage | Merely non-None sigma/FWHM fields, including invalid numbers | Positive finite auxiliary availability, missing and invalid counts separated; dummy sigma excluded from uncertainty capability |
| Phase-field coverage | Non-None fields counted, making missing powder phases look like poor quality | Absent field described as expected for a declared phase-free format; finite, missing and invalid fields distinguished; numerical zero counts as populated; phase provenance remains unverified |
| I/FWHM or F/FWHM | Value divided by width; descriptive and unit-dependent, not significance | Removed from diagnostic cards, tables, graphs and analytical exports. Existing legacy helper behavior remains unchanged for workflow compatibility |
| I/σ(I) | Direct ratio for a declared genuine intensity uncertainty | Retained only for finite values and positive finite uncertainties; per-record means/medians and shell statistics |
| Amplitude significance | Existing `abs(F)/(2σ(F))`, approximating I/σ(I) | Explicitly labeled derived, using I≈F² and first-order σ(I)≈2|F|σ(F); unreliable near zero. Direct F/σ(F) also visible in validation |
| Missing σ estimate | UI supplied sqrt(abs(value)), even for processed/amplitude data without a counting model | Removed. Missing uncertainty displays n/a, never a Poisson estimate |
| First shell crossing below mean significance 3 | Linear interpolation between shell means; descriptive, not an independent quality cutoff | Removed from primary summary; valid per-shell significance and weak fractions remain in the report; no width-based cutoff |
| Completeness | Distinct indexed ASU orbits intersected with allowed theoretical orbits, divided by theoretical count | Accurately labeled symmetry-allowed HKL coverage; explicit caveat for powder overlap and unknown observed/generated provenance |
| Resolution shells | Equal-width sinθ/λ intervals from 0 through the highest input reciprocal resolution; `(lo, hi]` | Preserved; raw-record means/medians, valid significance, original-unit widths and supported overlap fraction share one export/plot result |
| Empty-shell ratio | Internal/CSV value 0 despite denominator zero; UI sometimes a dash | Undefined: report/JSON null, CSV/UI n/a, plot gap; never 0% or 100% |
| d_min | Minimum finite nonzero-index d from the reciprocal cell metric | Unchanged for valid input |
| d98 | Highest-resolution theoretical boundary at which cumulative coverage from sinθ/λ=0 is ≥98%; may dip below 98% at intermediate boundaries | Same definition and integration direction; not an independent experimental cutoff. One verified floating-point boundary correction described below |
| FWHM histogram | Width distribution; constant arrays became a redundant one-bin chart | Constant-width summary based on the entire valid array; otherwise width versus resolution; intensity distribution shown separately without truncation |

Numerical definitions: constant widths and conflicting duplicate values use
`rtol=1e-7`, `atol=1e-12`. For ochlor this tolerates only about 5×10⁻⁹ in
width, far smaller than its stated four-decimal input precision. Exact nonzero
forbidden values are counted descriptively; they are not automatically labeled
experimental errors. A separate ≥3 significance count is available only with
valid uncertainty semantics; amplitude significance is explicitly derived.
Weak fractions default to thresholds 1, 2 and 3; positive finite thresholds can
be supplied to the common analysis authority.

## Verified numerical correction

Gemmi's theoretical enumeration and the existing reciprocal metric can round
the exact d_min boundary differently. In ochlor, `(0,7,5)` has d_min but was
omitted from the old theoretical set. Reducing the enumeration cutoff by only
10⁻¹⁵ relative included that exact reflection. A controlled nonsymmorphic,
nonorthogonal test independently enumerates a reciprocal bounding box, uses
`UnitCell.calculate_d_array` and the actual systematic-absence operations, and
confirms the inclusive count.

The diagnostic calculation now generates with a 10⁻¹² relative boundary guard,
then filters by its own reciprocal metric at the original d_min. The tolerance
is 10⁻¹² relative in sinθ/λ, with a minimum of eight floating-point ULPs.
The underlying theoretical helper, symmetry provider and phasing calculations
are unchanged.

| Real input | Before | After |
| --- | --- | --- |
| ochlor d_min (Å) | 1.1990790613015834 | identical |
| ochlor allowed/input orbits in the coverage domain | 630 / 630 | 631 / 631 |
| ochlor final shell allowed/input count | 144 / 144 | 145 / 145 |
| ochlor coverage | 100% | 100% |
| ochlor d98 (Å) | 1.1995604591213296 | 1.1990790613015834 |
| 2int3total d_min (Å) | 0.7255092594101177 | identical |
| 2int3total d98 (Å) | 0.8161153076022714 | identical |
| 2int3total covered/allowed physical orbits | 328605 / 362947 | identical |

No other nonempty-shell counts or coverage changed for either real input.
The d98 definition itself did not change. This numerical impact is intentional,
not a claim that the previous ochlor d98 was preserved.

## Common report, capabilities and implemented diagnostics

`phase_studio/hkl_diagnostics.py` supplies a frozen read-only report containing
source/provenance, declared format, cell/space group, availability with reasons,
counts, warnings, assumptions, duplicate/absence examples and shell plot data.

- Counts distinguish raw records, literal indices and symmetry orbits; report
  duplicates, conflicting finite values, systematic absences, missing/nonfinite
  data, invalid auxiliary fields, zeros, negatives and protocol `000`.
- Impossible cell geometry is rejected before reciprocal calculations.
- Declared Jana `dataformat` and explicitly selected external layouts establish
  column semantics. AUTO filename/default guesses do **not** establish genuine
  uncertainty or peak-width semantics; those inputs receive a warning and no
  fabricated significance. Current input readers cannot prove merged/unmerged
  observation provenance from the mere presence of duplicate indices.
- Powder reports use separate original intensity and width statistics. Widths
  retain their supplied units; unknown units remain **input units**.
- Overlap can use explicitly supplied group definitions, or a clearly labeled
  estimate only with explicit compatible degrees-2theta widths, wavelength and
  valid peak positions. Estimated grouping calls the existing
  `assign_powder_overlap_groups` authority without repartitioning intensities.
- Available overlap reports include group counts, affected indices/fraction,
  largest group, group-size distribution, per-shell fraction and a geometric
  group count. That last count is **not** claimed to be a measured number of
  independent observations. Integrated-intensity fractions require finite,
  nonnegative actual intensity input and a positive total.
- Shared shell results feed plots, CSV and JSON. Analytical exports include
  quantity/format, units, availability and reasons; undefined metrics are n/a
  or JSON null. The diagnostic shell CSV schema is intentionally extended;
  workflow metrics CSVs and scientific structure/map exports are unchanged.

Not implemented (P2 / unavailable with current readers): merging R factors,
CC1/2, experimental multiplicity, anomalous completeness, physical Wilson B
estimates, full-pattern Rp/Rwp/Rexp/GoF, Scherrer/strain and analytical PDF
reports. These require new verified unmerged/scaled, anomalous or profile input
contracts. Repeated synthetic text rows test that merging metrics remain
unavailable; they are not used to claim experimental merging-statistic validation.
Directional/cone completeness and a full overlap-group search UI are also deferred;
the current validator supports HKL-prefix search over all parsed records, with
at most 200 displayed matches and sortable raw-value cells.

Scientific references used to check prerequisites:
[Gemmi reflection/absence documentation](https://github.com/project-gemmi/gemmi/blob/master/docs/hkl.rst)
and [Evans & Murshudov, 2013](https://doi.org/10.1107/S0907444913000061).
All stated project numbers come from local calculations, not those references.

## Real powder acceptance — ochlor

Source: `C:/Users/honzi/Documents/ochlor/ochlor_Superflip.inflip`.
631 parsed, 631 literal unique, 631 symmetry-independent physical orbits;
P21/n setting from the project metadata; no forbidden entries, duplicates,
invalid values or invalid widths. FWHM is **0.0527 across all 631 records**.
Median Iobs **1488.4404**; mean Iobs **1668.0881402535658**.
No phase column: expected format characteristic, not a failed quality check.

Width units/profile metadata are not established. Therefore real overlap is
**unavailable**; no wavelength or angular-width convention was assumed, no
independent peak count was invented, and no intensity repartitioning occurred.
Known-unit overlap screenshots use explicitly labeled synthetic fixtures only.

## Real amplitude acceptance — 2int3total

Source: `C:/Users/honzi/Documents/flipovani-phase-studio/2int3total.inflip`,
used only for statistics following the user's explicit authorization.
328606 raw/literal-unique records, including one `000`; 328605 physical orbits;
P-1 with the project's nonorthogonal cell. All 328606 numerical phase fields
are populated; this does not prove experimentally solved phase provenance.
No forbidden entries or duplicates. 67888 physical records have zero F values.

Derived mean I/σ(I) **2.0053738116814785**; median
**0.3333259417004747**, using the explicitly stated amplitude approximation.
Fractions below derived significance 1, 2, 3 are approximately
**71.3525%, 80.4288%, 84.7945%**. No experimental I/σ(I) or merging statistics
are claimed from these amplitude records.

An isolated worker audit measured roughly **9.03 s** loading/report creation,
**3.02 s** coverage analysis and **0.00048 s** cached reopening. The reader's
cache-miss count did not increase when switching to completeness. During the
12.05 s worker run Qt delivered **270 heartbeat callbacks**, with a largest
measured gap of **0.168 s**. These are workstation observations, not universal
performance guarantees. Bounded caches use path/stat identity, declared format,
cell, symmetry, provenance and analysis parameters; file/format changes invalidate
them. GUI search is debounced and large tables are not materialized in full.

The real-input audit compares raw reflection fields byte/value-equivalently and
hashes source files before/after. Both source SHA256 values remained identical:

- ochlor: `9136270c5e8ab6850ac6bd4390c301f17a32dcc83994184d8562735b9a26b88c`
- 2int3total: `07a3de15e54ba130f75e960358aef1ff6087b09f0ea5d9604f00090cb9d21642`

Artifacts: `build/hkl-modernization/real-acceptance.json`,
`*-diagnostics.json`, `*-shells.csv`, and `real-audit.log`.

## GUI and screenshot acceptance

`phase_studio/hkl_diagnostics_ui.py` retains the existing diagnostic styling,
input-summary helpers, Copy summary, CSV and PNG/PDF/SVG plot exports. It adds
searchable validation samples and a progressive-disclosure report, removes
absent phase columns and invented uncertainties, and uses a vertical plot/table
splitter. Fixed footer actions remain outside the splitter. The compact summary
can scroll independently in a short window. Normal 1120×900 logical captures
show **seven complete resolution-bin rows**; narrow/expanded views retain table
scrolling and adjustable allocation.

Actual PySide6 widget grabs, not simulated screenshots:
`docs/screenshots/2.0.4-hkl-diagnostics/scale-{1,1.25,1.5}/`.
Each scale includes real ochlor validation/completeness/constant-width,
advanced unavailable-overlap and narrow views; labeled synthetic amplitude,
variable-width, supported estimated overlap and symmetry-warning views;
and real 2int3total validation/completeness. Available overlap has its own plot
tab/screenshot. Companion CSV, JSON, plot PNG and geometry JSON document the
displayed values. Captures use Qt's offscreen platform with explicit scale
factors; they are not manual physical-monitor DPI acceptance tests.

The screenshot tool is `packaging/tools/capture_hkl_diagnostics_204.py`.
The real numerical/performance tool is
`packaging/tools/audit_hkl_diagnostics_204.py`.

## Tests and release boundary

New automated fixtures cover declared/inferred formats, amplitude derivation,
zero/missing phases, real-sigma requirements, full-array constant detection,
exact/equivalent/conflicting duplicates, nonsymmorphic absences, Friedel policy,
invalid and negative values, impossible cells, an independently enumerated
inclusive resolution boundary, undefined shells, supplied/estimated/unavailable
overlap, configurable weak fractions, cache invalidation, strict analytical
exports, original-file preservation and cancellation.

Qt tests run at 100%, 125% and 150%, including six-or-more visible bin rows,
CSV/table/plot correspondence, advanced disclosure, HKL search, missing sigma,
normal/narrow geometry, cancellation without a result dialog, and a >1 MB Wizard
summary running off the Qt thread. Existing scientific core golden checks remain
46/46. Separate Jana handoff, density alignment, displacement, workflow and Wizard
regressions are logged in `build/hkl-modernization/test_*.log`.

No Superflip/SharpED calculation was started for this audit. No EDMA extraction,
Map Feedback, intensity repartitioning, ranking, authentication, scientific map
or structure writers, or Jana handoff algorithms changed. No version/license
change, release build, commit, push, tag or publication was performed.

Final validation results:

- Full suite: **285 passed, 1 skipped, 37 subtests passed**, 229.05 s;
  `build/hkl-modernization/pytest-verified.log`.
- Focused HKL, Wizard and distribution guards: **41 passed**;
  `build/hkl-modernization/focused-verified.log`.
- Latest HKL scientific/UI tests, including real Cancel-button interaction,
  active overlap-tab SVG export, PDF output and large-summary worker delivery:
  **19 passed**; `build/hkl-modernization/diagnostics-final.log`. Each GUI test
  executes at all three scale factors.
- **709 separate script checks passed**: scientific core 46, final UI 30,
  Jana completion 192, workflow states 141, density alignment 41, displacement
  parameters 44, Wizard hierarchy 21, redesign 44, icons 58, geometry 74 and
  text clipping 18.
- The default suite's skip is the opt-in real-project test. It was separately
  enabled for ochlor and **passed** without a map-feedback calculation;
  `build/hkl-modernization/real-opt-in.log`.
- Independent AST comparison to the pre-task dirty source confirms **240
  existing top-level functions unchanged**. Only the two approved HKL diagnostic
  functions changed; one uncached diagnostic loader was added. The historical
  distribution guard exempts only those two diagnostic functions, retaining
  its existing comparisons for the symmetry, phasing and writer authorities.
- Screenshot geometry confirms seven complete bin rows for both real datasets
  at each of 100%, 125% and 150%. Real ochlor, supported synthetic overlap and
  real 2int3total at 150% were visually inspected. There are **59 PNG artifacts**,
  including plot exports and the two untouched before screenshots.
- Syntax checks and `git diff --check` passed.

Files added in this pass: `phase_studio/hkl_diagnostics.py`,
`phase_studio/hkl_diagnostics_ui.py`, `tests/test_hkl_diagnostics.py`,
`tests/test_hkl_diagnostics_ui.py`, the two capture/audit tools, this report and
the screenshot directory. Existing files changed in this pass: `app.py`
(diagnostic entry points/views), `jana_superflip.py` (large HKL summary only),
`tests/test_final_ui.py` (new width-plot contract) and
`tests/test_split_distribution.py` (the narrowly scoped diagnostic exception).

Not performed: a new phasing/inference run, native Jana2020 import/refinement,
physical-monitor manual DPI acceptance, or experimental validation of unmerged
merging/profile/overlap quality. These results establish read-only diagnostic
behavior on the supplied files and controlled fixtures, not experimental truth
about the underlying structures.
