# Proposed text changes

All owner decisions are **Pending**. No proposal in this file has been applied to the application. Scientific algorithm decisions are separate from wording approval.

## UI-001 — Minimum observed value/σ

Current:

`Minimum observed value/σ`

Suggested:

`Minimum intensity significance I/σ(I) [only when uncertainties are available]`

Reason:

The legacy writer actually divides value by the fifth field even in FWHM mode. A wording-only fix cannot repair that scientific defect. Separate mode-aware filtering decision required; existing algorithm unchanged. FWHM is an angular peak width, not uncertainty.

Classification:

Scientific correction

Owner decision:

`Pending`

## UI-002 — Reference model

Current:

`Reference model`

Suggested:

`Reference structure (evaluation and optional Superflip density alignment)`

Reason:

Reference-backed validation is not independent evidence. Superflip referencefile also aligns resulting density. Distinguish evaluation, referencefile and modelfile roles.

Classification:

Clarity

Owner decision:

`Pending`

## UI-003 — XPLOR damping (1/x)

Current:

`XPLOR damping (1/x)`

Suggested:

`New-map weight for XPLOR recycling`

Reason:

The GUI inverse x is clipped to [0.001,1], converted to f=1/x, and the blend is (1-x) previous + x new where applicable. A help formula is clearer than the reciprocal alone.

Classification:

Clarity

Owner decision:

`Pending`

## UI-004 — Correction damping

Current:

`Correction damping`

Suggested:

`Intensity-correction weight`

Reason:

Correction damping and XPLOR damping are different operations. Explain the existing applied intensity formula and limiting branch rather than implying equal meanings of damping.

Classification:

Clarity

Owner decision:

`Pending`

## UI-005 — I/σ(I) limit

Current:

`I/σ(I) limit`

Suggested:

`Correct reflections below I/σ(I)`

Reason:

Strictly-below weak-reflection gate; amplitude-mode significance uses F/[2σ(F)]. This differs from the input-filter cutoff and is unavailable for FWHM significance. Equality matters.

Classification:

Clarity

Owner decision:

`Pending`

## UI-006 — Map ratio mix

Current:

`Map ratio mix`

Suggested:

`Map-predicted fraction of overlap repartitioning`

Reason:

Mix=0 preserves observed ratios; mix=1 uses map ratios. Group sums remain fixed. It does not set a global map amplitude scale.

Classification:

Clarity

Owner decision:

`Pending`

## UI-007 — Separation factor

Current:

`Separation factor`

Suggested:

`Overlap-group separation factor`

Reason:

Dimensionless factor used with angular separation and FWHM, not a physical separation in angstrom. Retain a tooltip defining the actual grouping inequality and units.

Classification:

Clarity

Owner decision:

`Pending`

## UI-008 — Maximum added reflections (%)

Current:

`Maximum added reflections (%)`

Suggested:

`Maximum added HKL (% of the existing reflection set)`

Reason:

Name the actual denominator and distinguish absent original HKL from newly allowed/missing HKL and from reflections crossing the writer filter. Confirm denominator in the existing completion branch before accepting replacement.

Classification:

Clarity

Owner decision:

`Pending`

## UI-009 — Compute OMIT validation maps (5% holdout)

Current:

`Compute OMIT validation maps (5% holdout)`

Suggested:

`Compute maps with a 5% reflection holdout`

Reason:

Reflection holdout is distinct from an atom-omission model-bias experiment. Keep the existing OMIT term only with its specific reflection-based definition and immutable holdout explanation.

Classification:

Clarity

Owner decision:

`Pending`

## UI-010 — Calculate R_free on the 5% holdout

Current:

`Calculate R_free on the 5% holdout`

Suggested:

`Calculate holdout R on the excluded 5% reflections`

Reason:

Do not imply independently refined R_free or independent validation when a reference/remote prediction influences evaluation. State amplitude/intensity convention and denominator used by compute_rfree.

Classification:

Clarity

Owner decision:

`Pending`

## UI-011 — Superflip threshold

Current:

`Superflip threshold`

Suggested:

`Superflip EDMA peak threshold (σ)`

Reason:

The two EDMA controls should both state density-standard-deviation units. This sigma is not an intensity measurement uncertainty.

Classification:

Consistency

Owner decision:

`Pending`

## UI-012 — SharpED threshold (σ)

Current:

`SharpED threshold (σ)`

Suggested:

`SharpED EDMA peak threshold (σ)`

Reason:

Identify peak extraction rather than implying a SharpED inference threshold. Existing EDMA sigma threshold behavior remains unchanged.

Classification:

Consistency

Owner decision:

`Pending`

## UI-013 — Atom-count mode

Current:

`Atom-count mode`

Suggested:

`EDMA site-count selection`

Reason:

Raw maxima, retained CIF sites, independent ASU sites and Jana m40 sites can differ. A detected peak is not a chemically validated atom.

Classification:

Clarity

Owner decision:

`Pending`

## UI-014 — Biso

Current:

`Biso`

Suggested:

`Superflip map-sharpening Biso (Å²)`

Reason:

This overall map parameter is distinct from atom-specific physical displacement parameters. EDMA peak density must never be called an ADP. Verify the executable-specific keyword convention.

Classification:

Clarity

Owner decision:

`Pending`

## UI-015 — Normalization

Current:

`Normalization`

Suggested:

`Requested normalization (backend compatibility applies)`

Reason:

The existing compatibility path may omit normalize atoms rather than send it. A requested GUI value is not proof of the effective generated keyword; show that distinction in help.

Classification:

Clarity

Owner decision:

`Pending`

## UI-016 — Random seed

Current:

`Random seed`

Suggested:

`Superflip random seed (AUTO uses system time)`

Reason:

AUTO is uncontrolled unless the backend reports and provenance captures the actual seed. A saved configuration alone does not guarantee exact reproduction.

Classification:

Clarity

Owner decision:

`Pending`

## UI-017 — Model

Current:

`Model`

Suggested:

`SharpED model selection`

Reason:

A catalog/display name is not an immutable model/checkpoint identity. Record actual API model identifier and server-supplied version separately.

Classification:

Clarity

Owner decision:

`Pending`

## UI-018 — Output resolution (Å)

Current:

`Output resolution (Å)`

Suggested:

`SharpED requested output resolution (Å)`

Reason:

Inference request parameter is not measured experimental resolution, dmin, d98 or a guaranteed attained resolution.

Classification:

Clarity

Owner decision:

`Pending`

## UI-019 — Density selection metric

Current:

`Density selection metric`

Suggested:

`Superflip best-density selection criterion`

Reason:

This selects retained native density attempts. It differs from Phase Studio candidate recommendation and from map feedback magnitude. reference and symmetry are distinct criteria.

Classification:

Clarity

Owner decision:

`Pending`

## UI-020 — Workflow preset

Current:

`Workflow preset`

Suggested:

`Starting-parameter preset`

Reason:

Recommended can imply scientific endorsement. Presets are editable initial values; preserve all numerical values and clearly state their scope and that existing untouched settings can persist.

Classification:

Clarity

Owner decision:

`Pending`
