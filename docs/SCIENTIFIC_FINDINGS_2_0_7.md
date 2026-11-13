# Scientific findings — independent 2.0.7 audit

Baseline: `6e59aecbe5df4811783f0c999ca1d211347b2570` (application identical to
`836cd26`). Fresh baseline: 993 passed, four skipped, 37 subtests; all nine
authority entry points passed. These regression gates did not detect the
counterexamples below. No numerical golden was regenerated without independent
justification: six serializer assertions that encoded loss of `1e-8` to zero
were corrected after mathematical and native verification.

N01–N11 are corrected in final source
`2d381b7a8503111c093a3f24e31d4ae5cd351ee8`: three P0, six P1 and two P2 findings.
Final verification: 1,026 pytest passes, four explicit skips, 37 subtests, all nine
authorities, native comparisons and both development profiles. See the
[complete audit](NUMERICAL_METHODOLOGICAL_AUDIT_2_0_7.md) for tolerances and limits.

| ID / severity | Independently established counterexample | Cause and affected result |
|---|---|---|
| N01 / P1 | Cell (10,10,12,90,90,60), fractional delta (.49,.49,0): explicit lattice minimum 5.00299910054 Å, old result 8.48704895709 Å | Rounding each fractional component is not a closest-image algorithm for skew cells. Reference distances, merging and matching can change. Gemmi 0.7.5's nearest-PBC-image helper also rounds components; replacing the function with that helper would not fix it. |
| N02 / P1 | General C2 atom has four full-cell positions; old reference expansion returns two. Fm-3m stress case omits 144 positions. | `sym_ops` omits centering translations. Reference counts/matching and reference-phase proxies can change; primitive space groups are unaffected by this correction. |
| N03 / P0 | P21 (0,1,0) must be systematically absent; old synthesis creates intensity 1 | Symmetry copies overwrite coefficients rather than enforcing extinction. Random-start and Fobs+phi recycling maps can contain forbidden Fourier content. |
| N04 / P0 | P-1 reflection with requested amplitude 1 and phase 60° produces intensity 0.25 | Taking the real part of a non-Hermitian inverse transform attenuates the observed amplitude. Centric phases need their symmetry restriction before real-map synthesis. Complex self-conjugate Nyquist coefficients and inconsistent Friedel/symmetry duplicates also require explicit rejection. |
| N05 / P1 | Eight-point cosine at h=1 is reported as intensity 65536 at h=9 | Modulo indexing silently aliases an undersampled reflection. Map-derived export, feedback and recycling can use a different coefficient from the requested HKL. |
| N06 / P2 | Exact Fo=2Fc fit: common factor 1e-100 makes the scale unavailable; 1e200 gives scale 0, R=1 instead of scale 2, R=0 | Absolute epsilon floors and unnormalized dot products introduce unit dependence and overflow. Same issue exists in the experimental bootstrap. |
| N07 / P0, experimental | Work Fo=2Fc, free Fo=Fc: expected work-scaled R_free=1; experimental EDMA candidate/bootstrapping return 0 | Free-set scale is fitted on free data in a second implementation, despite the earlier correction to map-quality R_free. A holdout below the calibration sample minimum also falls back to all-data fitting/selection. Disabled-by-default automatic threshold calibration is affected; default fixed thresholds are not. |
| N08 / P1 | Valid two-site CIF with one wrapped row: Gemmi reads two sites, old parser returns one | Line-based parsing returns a partial result before the standards-aware fallback. Wrapped/quoted records can silently disappear from previews, metrics and derived model operations. |
| N09 / P1 | I=1e-9, sigma=2e-10 serialize as two zeros | Fixed seven-decimal output destroys small measured values/uncertainties. The same floor affects I/F/FWHM/phased writers and uncertainty propagation exports. Ordinary exactly representable seven-decimal records retain their spelling. |
| N10 / P1 | Identical flattened arrays on different grid shapes produce correlation 1 | Correlation compared values without checking the coordinate frame. Incompatible grids/cells now yield unavailable agreement. |
| N11 / P2, experimental | Constant Fo/Fc with finite values around 1e200 and 1e-200 gives NaN overall-B correction | Forming the ratio before taking its logarithm overflows. Logarithm differences retain the finite linear fit. |

All before-state calculations, fixed seeds, input arrays and failed checks are
retained locally under `build/adversarial-audit207/`. The baseline checkout is
immutable. These findings supersede the earlier bounded audit's absence of new
P0/P1 findings; that report's 14 passing cases were insufficient to expose them.

## Methodological qualifications

- Powder intensities from one overlapping peak can be correlated even when
  crystallographic/Friedel holdout orbits are separate. Current partitioning
  does not establish statistical independence of powder extraction errors.
- Choosing the minimum R_free across candidates reuses a validation set. It is
  not an untouched final prediction-error estimate. Prior models and pretrained
  inference models may carry additional information not tracked by a free flag.
- The experimental EDMA criterion remains X-ray IT92/point-atom only and disabled
  by default. Its bootstrap assumes a sampling model that does not represent
  powder covariance. Fixing its scale does not validate the method for electron
  diffraction or chemical structure determination.
- Reference phase agreement is an atomic-number-weighted proxy, without
  occupancy, ADPs or resolution-dependent scattering factors. Reference RMS
  distance uses symmetric nearest-neighbor, potentially many-to-one matches in
  the supplied origin; it is not a globally aligned bijective structural RMSD.
- Centered negative-density mass is algebraically 0.5 for every nonconstant
  mean-centered map. Its clarified label identifies that fact; it is not used
  in ranking. Changing to physical-zero negativity needs a separate baseline
  policy, so its numerical definition is preserved.
- First-order sigma(I)=2F sigma(F) is not a low-signal statistical model. Negative
  intensity exclusion is the reconstruction policy, not an unbiased estimator.
  Predictions are not measurements and receive no fabricated sigma.
- Native Superflip score/FOM parsing is not a direct average angular phase
  error. No FOM-to-angle transform was found in the reviewed current code.

The Selexipag 3,796-native versus 3,795-geometric member difference remains
visible. Its mathematical gap exceeds the criterion by 7.871850887e-7 degrees.
The installed 2020 executable and available 2014 source are different versions;
the exact compiler/intermediate arithmetic is UNVERIFIED. Execution must use
the actual native table; widening a geometric tolerance is not a correction.
