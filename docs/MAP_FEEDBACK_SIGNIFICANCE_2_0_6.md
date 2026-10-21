# Map Feedback: intensity-significance threshold (2.0.6)

Weak-reflection intensity correction always accepts an **I/σ(I) limit**.
The comparison is strict: significance equal to the positive limit is excluded.

For `hkl I sigma` and `hkl I phase sigma`, significance is measured I/σ(I).
For positive amplitudes in `hkl F sigma` and `hkl F phase sigma`, first-order
uncertainty propagation of I=F² and σ(I)≈2Fσ(F) gives I/σ(I)≈F/[2σ(F)].
It is not the squared amplitude significance. For example, a limit of 2 selects
amplitudes with F/σ(F)<4, approximately.

The amplitude-derived quantity is an approximation, especially near zero or
when amplitudes were transformed from weak measured intensities. It does not
recover the original experimental I/σ(I). Zero, negative and nonfinite values,
and missing/nonpositive/nonfinite uncertainties, cannot pass a positive gate.
FWHM is never used as σ: width-only data still reject positive thresholds.

Zero retains its sentinel meaning: **no significance filtering**. Correction
then applies where a positive map prediction exists, including zero observed
values and data without genuine uncertainties, exactly as before.

`app.map_feedback_intensity_significance` is the single conversion authority.
It computes only a selection statistic; it never rewrites observations,
uncertainties or phases. GUI and Wizard use the same units and shared tooltip;
neither performs an additional conversion. Automatic format detection is unchanged.

The only intended numerical change is the set of positive amplitude observations
selected by a positive threshold. Intensity-based results, map prediction and
median scaling, damping/blending, conversion back to F, phases, output uncertainty,
HKL serialization, missing-reflection completion, powder repartitioning and
holdout exclusions retain their existing implementations.

## Existing settings

The key `map_feedback_intensity_max_i_over_sigma`, stored numerical values,
defaults, bounds and steps are unchanged. There is no migration. Older amplitude
settings were interpreted directly as F/σ(F); the same stored number now means
estimated I/σ(I). To preserve a historical approximate amplitude selection,
explicitly choose half the old numerical limit. This adjustment is never automatic.

## Regression authority

`tests/test_map_feedback_applicability.py` pins equivalent I/F decisions, the
strict boundary, zero-mode numerics, invalid measurements, both phase formats,
FWHM restrictions, both GUI labels/tooltips and stored-value compatibility.
An AST comparison against the pinned integrated baseline `b628eb9` permits only replacement
of the positive-threshold gate in `apply_map_feedback_to_reflections`; every
other statement in that function must remain identical. Existing numerical
goldens remain authoritative for intensity and uncertainty-independent paths.
