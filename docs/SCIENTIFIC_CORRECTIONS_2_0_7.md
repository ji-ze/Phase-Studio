# Scientific corrections — 2.0.7 adversarial audit

This development-only change addresses the independently reproduced findings in
[SCIENTIFIC_FINDINGS_2_0_7.md](SCIENTIFIC_FINDINGS_2_0_7.md). Original experimental
files, saved outputs and failed evidence are preserved. Previous results are
not rewritten and no inference is submitted.

## Minimal changes and scientific impact

- `scientific_numerics.py`: closest lattice image by bounded three-dimensional
  QR/sphere enumeration; invalid or unsupported conditioning fails explicitly.
  The search is checked against independently bounded image enumeration, not
  a helper sharing the original component-rounding assumption.
- `app.py`: reference expansion includes centering; standards-aware CIF parsing
  precedes the legacy nonstandard reader. Missing displacement data remain
  unknown. Correlation requires compatible grid, axes and unit cell.
- Fourier synthesis omits systematic absences and projects centric phases onto
  their allowed phase line without attenuating measured amplitude. It rejects
  inconsistent symmetry/Friedel coefficients and complex Nyquist bins. Random
  phases are assigned coherently to symmetry/Friedel orbits. FFT prediction
  validates layout, finite values and index support before modulo lookup.
- Reflection serialization retains ordinary legacy decimals, but uses sufficient
  significant digits when fixed decimals would destroy small values. This
  applies to native fixed/whitespace records and HKL/FCF uncertainty exports.
  Nonfinite quantities cannot be silently formatted as zero. Widths remain
  widths, and actual dummy fields remain unavailable uncertainty.
- `map_quality.py`: least-squares amplitude scaling and held-out residuals use
  normalized arithmetic instead of unit-dependent absolute floors and overflowing
  squares. Scale is still fitted exclusively on work for R_free. Ranking and
  the residual equations are unchanged.
- `edma_threshold.py`: candidate and bootstrap free residuals reuse the work
  scale. An insufficient existing holdout is not reassigned to the all-data
  criterion. Overall-B fitting uses log(Fo)-log(Fc); bootstrap residuals use the
  same stable authority. Default manual EDMA thresholds remain unchanged.
- Metric explanations identify many-to-one matching, simplified phase weights,
  validation-set reuse and constant centered negative mass. No GUI redesign.
- `packaging_acceptance.py`: both bundled profiles must execute counterexamples
  for lattice distance, centering, extinction, extreme scaling and small-value
  serialization in addition to the existing phase/holdout probes.

Prior centric/random/recycling maps, undersampled map-derived reflection outputs,
small-value exports, centered-cell reference counts, skew-cell distances and
experimental EDMA calibration results may change when recomputed. Ordinary
native reconstruction outputs are not automatically classified as incorrect:
only the identified processing paths are implicated. Re-evaluate an affected
historical conclusion against its original inputs; do not replace evidence.

Symmetry-inconsistent duplicate observations/phases and unsupported numerical
ranges now stop with an error rather than silently selecting an input-order-
dependent coefficient. This is an explicit support boundary, not an assertion
that conflicting experimental observations are physically impossible.

## Verification policy

New regressions encode independent expectations and retain the original failing
cases. Historical AST guards must pin only the specifically reviewed corrected
functions to the correction commit; numerical golden values are not refreshed.
The final exact-source full-suite, nine authorities, native all-group conservation,
source/frozen scientific checks and two development builds are required before
acceptance. See [the audit report](NUMERICAL_METHODOLOGICAL_AUDIT_2_0_7.md) for
the completed campaign status; a focused pass alone is not final acceptance.
