# Scientific validation of 2.0.7 — investigation in progress

This campaign is not complete. Release verdict: **NO-GO** pending the final
native, workflow, full-regression and frozen-profile gates. PR #21 must remain
draft. The initial prohibition on paid jobs was subsequently superseded by the
user's explicit authorization of real and additional automatic inference tests.
Previously saved SharpED responses remain replay evidence; new jobs are tracked
separately with their actual IDs, input/output hashes and downstream results.

## Confirmed P0: crystallographic phase sign at Fourier interchange

The application extracted phases with `numpy.fft.fftn`, whose exponent is
negative, and synthesized density with `ifftn`, whose exponent is positive.
External crystallographic phases use the opposite convention:

`F(h) = sum_r rho(r) exp(+2 pi i h.r)`;
`rho(r) = sum_h F(h) exp(-2 pi i h.r) / N` for the discrete normalization used here.

Thus a positive off-origin density was exported with conjugated phases. A
self-consistent NumPy round trip and amplitude-only tests could miss this.
Affected boundaries include map-derived phased reflection exports, external
phases supplied to synthesis, and symmetry-expanded recycling. Magnitudes and
intensities alone cannot diagnose the error. This is a scientific correction,
not a permissible precision difference or a reason to refresh numerical goldens.

Independent evidence on the clean pre-fix source `51a2c40`:

| Check | Independent expected | Before | Corrected |
|---|---:|---:|---:|
| Unit impulse at x=1/8, h=1 | +45 degrees (direct sum and Gemmi 0.7.5) | -45 | +45 |
| Native Superflip Fourier map with input phase +90 | +90 degrees | -90.0000026571 | +90.0000026571 |
| Complete non-Nyquist 1D Fourier series, peak x=1/8 | grid index 1 | index 7 | index 1 |

The native difference from 90 degrees is 2.66e-6 degrees, within the 1e-4-degree
tolerance justified by the native text map's six significant digits. Synthetic
in-memory direct-sum checks use absolute complex tolerance 1e-12; synthesis uses
1e-14. The native map is identical before and after (SHA-256
`dfe318eab055ee5272c99e7224daae0594bd6481244e786bb662765db29df09c`).
Superflip executable SHA-256 is
`2933a0c5245f4addc6365f26e5e4ca73a113e875a5901587db2bdd201a80bf3e`.

The correction conjugates the FFT of real density at both phase-extraction
entry points and uses the negative-exponent transform divided by N for synthesis.
It retains discrete normalization, observed amplitudes, and intensity filtering.
The existing internal map-quality/reference-phase pair both use negative-exponent
phases; these internally consistent, cosine-based metrics are not independently
changed by this boundary correction. Jana density export already conjugates its
FFT. Full native symmetry/recycling checks are still required before acceptance.

Six analytic regression cases failed before correction. Seven phase tests,
including actual installed Superflip execution, pass after correction. The first
neighboring-mode check passed 34 tests; this is not the final full-suite result.
Evidence and reproducible probes are under ignored
`build/scientific-validation-2.0.7/`.

Primary references: [Gemmi scattering documentation](https://gemmi.readthedocs.io/en/stable/scattering.html)
and the [Superflip manual](https://superflip.fzu.cz/download/superflip_user_manual.pdf).

## Confirmed P0: missing completion reintroduced excluded orbits

Missing-reflection completion excluded only exact holdout HKL and had no space
group argument. With actual FFT predictions from a controlled map it added
`(-1,0,0)` while `(1,0,0)` was held out, together with forbidden P21 reflections
`(0,-1,0)` and `(0,1,0)`. This contaminates the independence of the holdout and
violates systematic extinctions. Symmetry-equivalent spellings of measured HKL
could also be counted as new missing measurements.

The correction passes the actual run space group into completion, rejects its
systematic absences, excludes entire measured and holdout symmetry/Friedel
orbits, and adds at most one representative of each remaining orbit. Predicted
records still receive no fabricated measurement uncertainty. The regression uses
an intentionally symmetry-inconsistent real density file: forbidden map signal
must not make a forbidden reflection eligible. No API or FFT mock is involved.

## Native execution and powder conservation checks so far

New real Superflip FOURIER and twelve-cycle CF executions completed for each of
I/sigma, F/sigma, phased I/sigma, phased F/sigma, I/FWHM and F/FWHM. Each CF map
was processed by actual EDMA at thresholds 0.5 and 2.0 sigma: twelve EDMA
executions. These sparse P1 fixtures establish native execution compatibility,
finite map output and parseable CIF output, not successful experimental structure
solution, correct chemical assignments or interactive Jana acceptance.

Twenty-four additional overlap cases cover I/FWHM and F/FWHM, mix 0/0.25/1,
zero members, zero map signal and extreme intensity ratios. The independent
oracle directly sums the serialized density with complex exponentials, without
calling the application's FFT predictor. Both redistributed member intensities
and group totals are recomputed from the actual written HKL, squaring F where
appropriate. Bounds follow seven-decimal column rounding: 5e-8 for I and
`2*F*5e-8 + (5e-8)^2` for intensity derived from F, plus a total-scaled 1e-12
floating-point allowance. The six-digit XPLOR serialization measurably perturbs
weak Fourier components in high-dynamic-range maps; the oracle therefore uses
the actual serialized map, retaining the strict output-rounding bound.

## Additional reproduced defects

Duplicate inverse-variance averaging squared sigma directly. Finite uncertainties
1e-200 and 1e200 produced nonfinite merged values/uncertainties; averaging two
finite values of 1e308 also overflowed. Normalize weights by the smallest usable
sigma before squaring and normalize their sum before multiplying observations.
The formula is algebraically identical; independent expected values are 12 and
`sigma/sqrt(1.25)` for measurements 10±sigma and 20±2sigma. Three new cases failed
before and pass after. This corrects numerical corruption without changing FWHM
weighting or the distinction between I and F.

Native `.inflip` dummy columns were copied into the application's sigma slot.
Even a declared `dataformat amplitude dummy` could consequently participate in
significance filtering and sigma-labeled exports. The extraction boundary now
marks declared dummy fields unavailable (`?`), preserving the original source
file and actual I/F values. Legitimate explicitly supplied external I/sigma or
F/sigma inputs retain their uncertainty semantics. An actionable error requires
measured uncertainties for a positive threshold or uncertainty-bearing export.
No scientific meaning is inferred from a dummy field's numeric value.
The same rule applies to undeclared trailing fields in native `dataformat
intensity`/`amplitude`: the Superflip manual explicitly says additional numbers
are ignored. They cannot establish measurement sigma. Canonical supported native
column orders are validated before extraction; mixed sigma/width, group and
reordered layouts are rejected explicitly instead of guessing positional meanings.

Native `dataformat amplitude phase` with five total fields also left phase in
turns instead of converting to degrees, because the old conversion required six
fields. Conversion now accepts the phase-bearing five-field input. Four focused
dummy/phase cases failed before and pass after correction. Full-suite validation
of these latest changes remains required.

XPLOR reading accepted non-ZYX axes and nonzero grid origins but interpreted the
flat density as zero-origin ZYX. This can move density and change phases without
changing dimensions or statistics. Two hand-written nonconstant cubic fixtures
reproduced silent acceptance. Read and write boundaries now explicitly reject
unsupported layouts with a conversion instruction; they do not relabel the
header. Full-cell zero-origin ZYX remains the supported representation used by
the native and saved fixtures. Arbitrary-axis/submap conversion is not newly
implemented. Seventy-three focused map, tiling, scaling and numerical checks
passed after the guard.

An actual-map Map Feedback applicability cross-product exercised eight families
(six explicit layouts plus uncertainty-free I/F), eight operation combinations
and thresholds 0/2: 56 executions passed and 72 incompatible configurations were
rejected correctly. These are local synthetic FFT calculations, not inference
jobs. Thirty-six further intensity-correction cases independently recompute map
coefficients and scaling, I/σ(I) versus F/[2σ(F)] gates, and damping 0/0.5/1.

New native EDMA runs on saved real cycle-1 maps produced 127/28 sites from the
Superflip map and 93/68 sites from the SharpED map at thresholds 0.5/2.0. These
counts demonstrate threshold-dependent extraction, not chemical correctness or
new server inference. All 110 original files were hashed before and after and
remained byte-identical. The saved map's provenance and multipart identity checks
are separately documented in `FINAL_REVIEW_CORRECTIONS_2_0_7.md`.

## Acceptance boundaries

The previous snapshot `51a2c40` completed 735 pytest tests with 4 skipped and 37
passing subtests. That success does **not** establish correctness of the phase
interchange or validate the corrected source. Its packaging campaign was stopped
after discovering this defect. Existing test distributions remain historical
candidates and must not be described as accepted against the new scientific scope.

The exhaustive input/workflow/feedback matrices, native charge-flipping and EDMA,
saved-inference replay across modes, numerical comparisons, performance evidence,
and final full regression/frozen profiles remain pending in this investigation.
Live inference, interactive Jana acceptance, full-window DPI and terminology gates
must be reported separately; none is established by file generation or mocks.
Original experimental files and the published 2.0.6 release remain protected.

## Input matrix and external dependencies

| Acquisition / columns | Local native verdict | Limits |
|---|---|---|
| Single crystal I + sigma(I) | PASS, synthetic | Explicit measured-sigma declaration required |
| Single crystal F + sigma(F) | PASS, synthetic | Input gate uses F/sigma(F); feedback intensity gate uses F/[2sigma(F)] |
| Single crystal I without sigma | PASS, synthetic | Positive uncertainty gates and sigma exports unavailable |
| Single crystal F with dummy/unavailable sigma | PASS, synthetic | Native dummy is not measured sigma |
| Powder I + FWHM | PASS, synthetic and real pilots | Measured wavelength; no missing-width fabrication |
| Powder F + FWHM | PASS, synthetic | Conservation checked in I = F squared; no real F/FWHM fixture |
| Powder I + sigma(I) | PASS for extracted HKL native execution | No overlap operation without measured widths |
| Powder F + sigma(F) | PASS for extracted HKL native execution | No overlap operation without measured widths |
| Single crystal I + FWHM | BLOCKED acquisition applicability | FWHM modes encode powder angular widths; no independent acquisition-type flag establishes rejection of a mislabeled acquisition |
| Single crystal F + FWHM | BLOCKED acquisition applicability | Same limitation; never count this as single-crystal acceptance |

The detailed matrix records exact source, configuration and native artifact
hashes under `build/scientific-validation-2.0.7/input_format_matrix.json`.
Six explicit modes plus uncertainty-free I/F have each undergone native FOURIER,
twelve-cycle CF and EDMA at two thresholds (eight CF and sixteen EDMA cases).
Unsupported mixed sigma/FWHM layouts are not implemented as a combined measured
uncertainty/width representation. No column may acquire either meaning merely
because it is numeric.

Actual-data execution pilots on the corrected source additionally completed:

| Data | Reflections parsed/written | Measured lambda (A) | CF / EDMA time (s) | EDMA sites |
|---|---:|---:|---:|---:|
| Selexipag | 4690 / 4690 | 0.39986, supplied reference CIF | 3.19 / 7.69 | 520 |
| Ochlor | 631 / 631 | 1.541866, matching m90 | 0.74 / 2.02 | 262 |

These use twenty CF cycles, one repeat, fixed seed, no supplied reference/model,
and EDMA threshold 0.5 sigma. They demonstrate native compatibility and finite
outputs; convergence, chemical correctness and numerical equivalence to the
historical AAR/50-repeat/2000-cycle settings are **not** established. Timings are
single observations on a shared host, not comparative performance benchmarks.
The historical Selexipag inventory recheck independently retained all 4690 valid
records, accounting for all 277 formerly excluded rows (136 zero, 141 positive),
and preserved all 746 historical files byte-for-byte. Its old input omitted
lambda; native default use must not be confused with the measured 0.39986 A
used in the new pilot.

## Outstanding coverage and release verdicts

Machine-readable final-regression results must be read for their exact source
commit; an interrupted earlier snapshot is not a passed final suite. Frozen
profiles must also execute the bundled FFT/phase/dummy probe and match source
module bytecode before a new test distribution is accepted.

| Branch | Current release verdict | Reason / remaining evidence |
|---|---|---|
| Powder workflows | NO-GO | Local native/math evidence exists; complete inference-assisted workflow coverage not established |
| Single-crystal workflows | NO-GO | Same end-to-end and acquisition applicability limits |
| I + sigma | GO WITH WARNINGS for local processing | Genuine-sigma provenance and final regression gates remain prerequisites |
| F + sigma | GO WITH WARNINGS for local processing | First-order propagated significance is unreliable near F=0; native phase correction verified |
| I + FWHM | GO WITH WARNINGS for local processing | Width/wavelength requirements enforced; real pilots are not solved structures |
| F + FWHM | GO WITH WARNINGS for local processing | No independent real amplitude/FWHM dataset available |
| SharpED inference | NO-GO pending full matrix | Live PEAK A completed; broader real-model/data and frozen map-loading checks are in progress |
| EDMA processing | GO WITH WARNINGS | Real native executions and saved-map replay; site counts do not validate element assignment |
| Map Feedback | GO WITH WARNINGS for local processing | Independent correction/conservation and orbit tests; exhaustive inference-driven transitions not established |
| Iterative workflows | NO-GO | Regression simulations/replay do not establish every native/inference combination |
| Jana2020 output | NO-GO for live acceptance | Generated/protocol identity checks are distinct from interactive native refinement/continuation |

The full noncritical workflow pairwise matrix, all live model families, native
multi-cycle inference transitions, independent element/structure accuracy,
comparative CPU/memory/I/O performance, full-window/manual DPI, live Jana and
exhaustive terminology acceptance remain explicitly unresolved. Existing
authority scripts exercise additional deterministic branches, but neither mocks
nor saved-response replay can close these external scientific gates. This report
does not declare exhaustive validation complete or 2.0.7 release-ready.

### Overlap boundary correction and native precision limit

Feedback grouping used a strict less-than comparison, while native Fortran
separates peaks only when the gap is strictly greater than the width threshold.
Equality therefore belongs to an overlap group. An independent Bragg-law fixture
failed before correcting feedback to the inclusive boundary; diagnostic grouping
already used the inclusive rule. Twenty-five conservation/boundary cases pass.

Native pilot logs confirm receipt of 4690 Selexipag records (894 separated,
3796 overlapping, 794 groups) and 631 Ochlor records (438 separated, 193 overlapping,
91 groups). A full Selexipag comparison additionally exposes a precision-sensitive
membership difference: double-precision application geometry gives 3795 members
in the same 794 groups. One neighboring gap is 0.002880787185093 degrees versus a
0.00288-degree threshold, a difference of 7.87e-7 degrees. This is below a
single-precision ULP near the approximately 15.63-degree Bragg position; native
source uses single-precision angles and metric tensors. This is consistent with
native rounding sensitivity, but the exact floating-point path has not been
independently replicated. It remains an explicit numerical acceptance limitation,
not a group-membership PASS, and is not hidden with a widened tolerance.

Explicit native group IDs remain supported for read-only diagnostics without
being reinterpreted as sigma or recomputed from wavelength. Extraction has an
explicit diagnostic-only path for these records; execution still rejects a
layout for which the application's numerical writer has no group-preserving
mode. Unsupported diagnostic layouts are rejected by the diagnostic schema
before extraction. Regression tests retain the original group counts and verify
that significance remains unavailable. The Wizard test separately verifies that
native ignored fields provide no sigma and that parsed explicit measured-F/sigma
records enable the legitimate uncertainty gate.

The first complete scientific snapshot run reported 816 passed, six failed,
four skipped and 37 passing subtests. Those failures were retained as evidence;
they do not constitute final acceptance. Two native Windows credential/path-lock
checks subsequently passed outside sandbox restrictions. Final acceptance must
rerun the entire suite after the diagnostic/guard corrections in that native
environment; no skips or relaxed scientific tolerances substitute for it.

### Confirmed P0: fitting the holdout scale to the holdout itself

Both the legacy `compute_rfree` helper and map-quality R_free fitted a separate
least-squares scale using free-set amplitudes. This consumes test information
and can conceal an amplitude prediction error completely. In an independent
six-frequency density fixture, work predictions are exact and every free
prediction is twice its observation. Work-only scale is 1 and free R must be 1;
the old map metric instead returned approximately 1.37e-7 (text-map rounding
around an incorrectly perfect zero). This is a computational defect, not a label
correction. [REFMAC's scaling documentation](https://www.ccp4.ac.uk/html/refmac5/keywords/xray-principal.html)
specifies working-set scaling by default; the application offers no deliberate
free-set scaling policy.

The corrected paths evaluate free residuals at the scale fitted solely from work
reflections. Missing/undefined work scale gives an unavailable R_free rather
than fitting it from free data. The existing minimum of three free reflections
remains. Independent map FFT and exact prediction tests check work/free scale
differences, perturbed free observations, R_free greater than 1 and absent work
data. The five focused tests pass. Work/measured amplitude metrics, correlations,
triplet/reference metrics and ranking definitions are unchanged; holdout-based
scores and recommendations may legitimately change. Historical no-holdout replay
does not validate this correction by itself.

Snapshot 047115e completed the full suite: 823 passed, four skipped and 37 subtests
passed in 640.34 seconds. Its build controller was stopped before distribution
acceptance when this additional independently reproduced scale defect was found.
That passing snapshot is historical evidence, not final validation of the new fix.

### Confirmed P0/P1: positional native output formats

The native writer emitted several `outputfile` names but only one `outputformat`.
Superflip applies that format to the first file and guesses subsequent formats
by extension. Consequently optional Jana/CCP4 exports could contain XPLOR text,
or selecting another primary format could turn the mandatory `.xplor` into binary
or a reflection list and break downstream processing. All six new actual-native
export configurations failed before correction.

Each output now receives its own positional format: m81/jana, m80/m80,
ccp4/ccp4 and the mandatory XPLOR/xplor. A requested primary native format adds
the correctly named optional product while retaining internal XPLOR. All six
actual native cases pass. Jana m81 output matches an independently generated
single-file native Jana control byte-for-byte. Gemmi reads the binary CCP4
output and all voxels agree with XPLOR within a per-voxel bound derived from
native Fortran E12.5 text rounding and float32 binary precision. No arbitrary
relative tolerance replaces the serialization error bound.

The holdout correction was also evaluated against both published v2.0.6 and
047115e on identical complete serialized density arrays. Across four scale/data
cases, only R_free differs; every other computed metric is exactly equal.
Additional actual next-cycle runs cover powder repartitioning and saved-SharpED
map initialization with missing completion (4540 original, 45 predictions added,
4585 written). These are new native Superflip/EDMA executions from replayed maps,
not new inference. Model normalization preserves the complete density array and
original sources remain unchanged.

### Authorized live inference and actual result loading

After explicit user authorization, real PEAK A job 1868 completed on the prepared
Ochlor map. The actual uploaded bytes match the approved source hash; one upload
was accepted, and a different complete result was downloaded and parsed: 165888
finite values, grid 48x96x36, unchanged cell and canonical axes. Local native EDMA
found 60 sites at threshold 0.5 sigma. The new inferred map initialized another
actual Superflip cycle with all 631 reflections and measured lambda 1.541866 A.
No second inference was part of that local continuation.

The actual Result Selection GUI loaded this map identity and its EDMA structure.
It displays structures derived from maps, not a claim that the atomic model is
chemically correct. A separate opt-in frozen/source map-loading probe reads actual
result files, verifies hashes, computes metrics and renders their real candidates
without issuing inference or phasing. New model/data jobs are not counted as
passed until server result, loading and downstream checks complete.

The earlier frozen acceptance stalled in its test callback: it tried to capture a
closed hidden Why-this-cycle dialog before rejecting the visible confirmation.
The callback now acts only on visible dialogs. Source acceptance completes through
the actual confirmation cancellation and original assertions; no numerical or
geometry assertion is weakened.
