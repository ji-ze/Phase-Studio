# FWHM scientific data-flow correction, 2.0.7

This report supersedes the unresolved filtering finding in the earlier
[provenance audit](RUN_PROVENANCE_2_0_7.md). PR #21 remains a draft. The correction
changes scientific inputs; it does **not** establish equivalent reconstruction
results. The saved 25-cycle run was not rerun and no paid SharpED job was started.

## Old defect and corrected policy

The old input filter divided the observed value by `Reflection.sigma` without
consulting the declared mode. That field also stores the fifth-column FWHM in
legacy in-memory records. Consequently I/FWHM or F/FWHM was treated like
measurement significance. The observed writer also labelled widths as sigma;
both optional reflection exporters propagated widths as sigma(I), and duplicate
merging could use inverse-squared widths as statistical weights. Missing-HKL
completion estimated an auxiliary value from neighbouring value/auxiliary ratios.

The correction passes the declared mode through the actual filter, duplicate
merger and all three reflection writers. There is no relabelling-only workaround:

* FWHM input **requires significance threshold 0**. A configured positive value
  raises an actionable error before a scientific run or output-file mutation.
  The full application's existing value is not silently reset. The Wizard shows
  that the observed filter is disabled for verified FWHM input and explicitly
  passes 0 through its options/import mapping; that override is logged.
* With the threshold disabled, finite nonnegative I or F is eligible. Zero is a
  valid recorded observation and is retained; it is not treated as missing HKL.
  Negative and nonfinite values are excluded, not clipped into fabricated zero
  observations. Missing/unparseable values remain parser rejections. For FWHM
  native input the measured width must additionally be finite and positive.
* Invalid value/width records are removed from the execution/feedback population
  before cycle processing, while original observations remain in the original
  snapshot and diagnostic inventory. They cannot become valid merely because a
  later powder redistribution clips or redistributes them.
* Genuine uncertainty modes retain their established **mode-native** filter:
  I/sigma(I) for I input, F/sigma(F) for F input, inclusive `>= threshold`.
  The historical configuration key `i_over_sigma_min` does not mean that
  amplitude input has always been filtered in the intensity domain. Missing,
  nonfinite or nonpositive uncertainty cannot pass a positive threshold. If no
  usable uncertainties exist, a positive threshold is rejected with instructions
  to supply uncertainties or choose 0. Threshold 0 supports uncertainty-free data.
* Existing resolution filtering still applies independently. These rules do
  not promise to keep every original record in an arbitrary dataset.

The implementation retains the legacy `Reflection.sigma` storage name to avoid
breaking existing records and public helper calls. Its meaning is determined by
the declared mode, not inferred from the name or numeric magnitude. It is never
used as measurement uncertainty on a FWHM path.

The writer boundary also rejects unresolved AUTO layouts. Callers must resolve
or select the physical column meaning before filtering or export; numerical
magnitudes alone are not evidence that an auxiliary field is an uncertainty.
[IUCr defines powder peak FWHM as a width in 2theta](https://www.iucr.org/__data/iucr/cif/dictionaries/cif_pd_1.0.1.dic.pdf).

## Column trace

| Declared mode | External columns after h k l | Internal auxiliary meaning | Native Superflip dataformat | Native phase representation |
| --- | --- | --- | --- | --- |
| I, sigma(I) | I, sigma(I); auxiliary may be unavailable | Measured uncertainty or unavailable | intensity dummy | No phase supplied |
| F, sigma(F) | F, sigma(F); auxiliary may be unavailable | Measured uncertainty or unavailable | amplitude dummy | No phase supplied |
| I, phase, sigma(I) | I, phase in degrees, sigma(I) | Measured uncertainty or unavailable | intensity phase dummy | Turns; unknown phase `?` |
| F, phase, sigma(F) | F, phase in degrees, sigma(F) | Measured uncertainty or unavailable | amplitude phase dummy | Turns; unknown phase `?` |
| I, FWHM | I, FWHM in degrees of 2theta | Measured peak width | intensity fwhm | No phase supplied |
| F, FWHM | F, FWHM in degrees of 2theta | Measured peak width | amplitude fwhm | No phase supplied |

`parse_reflection_line` preserves missing auxiliary `?`/`.` as unavailable.
`reflection_columns_for_mode` selects column 5 or 6. Jana embedded phases already
arrive in turns and the existing extraction converts them to degrees. The native
writer converts degrees back to turns and now correctly labels its phase header
`phase(turns)`. Both readers recognize that generated header for round trips.
An unknown native phase remains `?`, rather than acquiring an invented 0-degree
phase. The existing seven-decimal value/auxiliary serialization remains explicit;
very small positive values can round to zero at that precision.

Superflip ignores `dummy` columns. In an uncertainty-free native list, a zero
dummy sentinel means unavailable, not a measured zero uncertainty; the header
states this. No such sentinel is exported as a genuine measurement uncertainty
by the optional phased HKL/FCF writers. FWHM values are retained as measured
angular widths, not converted, squared or divided into significance.

The native FWHM path also verifies the mandatory positive `lambda` keyword.
An existing explicit native lambda remains authoritative; otherwise the resolved
measured wavelength is appended. Missing/invalid lambda is an actionable error.
This does not silently resolve the separate wavelength-source-priority review.
[Superflip manual, dataformat and lambda](https://superflip.fzu.cz/download/superflip_user_manual.pdf).

## Duplicate and missing-HKL handling

Genuine-sigma duplicate observations keep the established inverse-variance
weighted mean and propagated uncertainty. Nonfinite values cannot poison a
valid duplicate group. FWHM duplicates with the same verified width use an
unweighted mean of finite observed values and retain that width. Conflicting
or unavailable duplicate widths are rejected with a request for an authoritative
merged peak list; no inverse-variance interpretation or invented mean width is
used. Literal HKL grouping is unchanged.

A map prediction has no measured uncertainty. Newly completed HKL therefore
carry unavailable sigma, never an estimate inferred from ratios. A positive
measurement-significance gate cannot accept them as measured observations.
FWHM missing-reflection completion is rejected because an absent observed peak
has no measured width to supply to native FWHM grouping. Disable completion for
that mode; uncertainty-independent intensity correction and powder overlap
repartitioning remain supported. The Wizard already separates these mechanisms.

Powder repartitioning independently rejects non-FWHM input and invalid values
or widths before entering its existing calculation. Its actual ratios, blending
and group-conservation formulas remain unchanged and retain strict AST guards.
Map Feedback's separate positive weak-reflection gate is also unchanged:
I/sigma(I) for I, approximately F/[2 sigma(F)] for positive F, with a strict
`< limit`. It must not be confused with the mode-native observed-input filter.

## Optional exports and Jana consumers

Both `write_standardized_hkl_with_phase` and `write_shelx_fcf` use the same
mode-aware observed filter. They require genuine finite positive uncertainties
for every retained export record. FWHM or missing uncertainties cause an
actionable rejection **before opening/replacing the target file**. The user can
choose XPLOR, CCP4 or Jana map export or provide measured uncertainties.

For genuine intensity input the export retains I and sigma(I). For positive
amplitude input it writes I=F² and the established first-order propagation
sigma(I) approximately 2 F sigma(F). At F=0 that approximation cannot provide a
positive intensity uncertainty; export is rejected rather than inventing one.
Low-signal nonlinear uncertainty modelling is not introduced by this fix.
[IUCr definitions distinguish measured structure factors and their uncertainties](https://www.iucr.org/__data/iucr/cif/dictionaries/cif_core_2.4.2.dic.pdf).

The phased HKL columns remain `h k l I sigma(I) phase(deg)`. FCF retains its
existing measured/calculated squared-factor and calculated-phase loop. Calculated
values/phases still come from the reconstructed map where supplied; no FWHM is
ever written under the sigma tag. Reconstruction-free placeholder behaviour in
FCF is unchanged and remains explicitly labelled.

The call sites include initial Superflip input, OMIT/holdout input, every
post-feedback next-cycle input, and phased exports for both result families.
They all pass the resolved mode. Selection and Jana handoff still use the
selected map and its corresponding thresholded CIF/m40 identity; they do not
reinterpret this auxiliary column. Native Jana/Superflip pass-through preserves
the incoming declared dataformat. Final m80/m81 import and handoff protocol are
unchanged. Existing Jana/selection authorities remain required acceptance gates.

## Saved 25-cycle inventory, read-only

The actual saved original extracted list contains 4,690 unique records; the
legacy first written file contains 4,413. The corrected policy, with threshold
0 and no resolution cutoff, writes **4,690** because this particular original
list has finite nonnegative intensities and positive finite measured widths.

| Population | Count | Corrected disposition |
| --- | ---: | --- |
| Previously retained HKL | 4,413 | Retained |
| Formerly excluded zero intensities | 136 | Retained as zero observations |
| Formerly excluded positive intensities | 141 | Retained without I/FWHM filtering |
| Formerly excluded total | 277 | All explicitly inventoried |
| New corrected first written input | 4,690 | No new HKL invented |

The actual serialized corrected file has 136 zero and 4,554 positive values
(minimum positive I=0.0001). Every written I and measured width equals its
original parsed value exactly at the existing file precision: maximum
intensity difference 0 and maximum width difference 0. This checks input
serialization only, not equivalence of subsequent scientific results.

This is not proof that the historical threshold was exactly 2; that effective
setting was not serialized. A legacy ratio cutoff of 2 reproduces the actual
omitted set, with the compatible interval documented in the earlier audit.

`packaging/tools/verify_fwhm_policy_207.py` writes the complete 277-record ledger
to local ignored `build/fwhm207/verification-complete/formerly_excluded.csv` and
a corrected initial HKL outside the original run. It hashes **746 original
files before and after**; all remain identical. The ledger and private scientific
files are not committed. Aggregate and synthetic verification evidence is in
`verification/fwhm207.json`.

These changed inputs can change native overlap groups, phasing, maps, SharpED
outputs, validation scores and selected candidates. None of those new outcomes
is known without rerunning the appropriate calculation. Historical result and
feedback diagnostics continue to describe the historical saved artifacts;
the earlier replay agreement is not numerical equivalence to the corrected run.

## Verification and limits

New independent numerical contracts cover all six declared modes, threshold
boundaries, zero/negative/nonfinite/missing values, missing/nonfinite widths,
uncertainty-free native input, genuine-sigma duplicate goldens, width-conflict
refusal, sigma propagation, rejection without file mutation, phase units and
unknown phases, powder group conservation and width preservation. Existing
correction formulas remain AST-pinned after validating only exact new boundary
guards and removal of fabricated uncertainties. Changed parser/filter/export
functions are pinned to final policy commit ca40e03 instead of exempted from
scientific regression checking; all unaffected functions retain the released
baseline. Synthetic native probes cover I, F, both phased modes, both FWHM modes
and uncertainty-free intensity input, using the installed scientific Superflip
binary SHA-256 `2933a0c5245f4addc6365f26e5e4ca73a113e875a5901587db2bdd201a80bf3e`.
All seven produce finite maps. They are controlled Fourier compatibility checks,
not reruns of the real structure solution or claims of recovered chemistry.

An actual pipeline-preparation regression supplies 100 valid FWHM observations
and four invalid observations (negative/NaN intensity and zero/missing width),
with OMIT enabled. It verifies that the holdout, validation population and
work-data population collectively contain only the 100 valid observations,
and that the original source bytes are unchanged. This pins the former
holdout reconstruction path so it cannot restore rejected records. The test
stops before cycle execution and forbids native launches.

## Final quality gates

All gates below were run after the final runtime change, in the requested order:

* Entire regression: **692 passed, 4 existing conditional skips, 37 subtests
  passed**, 564.90 seconds. No tests were excluded to obtain this result.
* Independent authorities: scientific core 46, Jana completion 195, Autosolve
  orchestration 79, workflow states 141, Result Selection viewer 72, review EDMA
  20, displacement parameters 42, execution logging 16; fullscreen script exit
  0. All nine scripts succeeded.
* Independent native overlap verification: all eight cases match actual
  Superflip group membership, including separated/identical/transitive/variable
  widths, wavelength/default-separation changes, explicit groups and a separate
  631-record powder fixture (91 groups, 193 affected reflections). This is
  separate from the 4,690-record historical inventory.
* Seven native format probes and the 746-file historical integrity check were
  repeated successfully on the final code. All I/width values in the corrected
  historical input remain exact; no original scientific file is changed.
* Fresh standalone ONEFILE and Jana ONEDIR builds pass native-dependency and
  distribution-boundary audits; the developer ZIP was extracted and all 407
  files verified. Both final frozen acceptance probes exit 0 with `ok=true`
  and `original_input_unchanged=true`. Every runtime Python source is
  byte-identical to the isolated build snapshot. Unsigned test builds remain
  local under ignored `build/a207-fwhm-final/`, not published releases.

The added Wizard guidance initially failed two existing geometry tests. It was
compacted into the existing format row; all original size/DPI assertions were
retained and the complete suite rerun. The holdout test specifically exercises
actual preparation, rather than merely repeating a filter-helper assertion.

PR #21 stays draft pending independent scientific review. No signing/SignPath
change, 2.0.6 release/tag change, merge or publication is included. Full-window
high-DPI clipping, physical/mixed-monitor and live Jana acceptance, broader
Pending terminology proposals and the wavelength-source-priority review remain
separate gates. Automated fixture checks do not close those acceptance gaps.
No uncertainty-calibration model for SharpED predictions is introduced: carried
experimental uncertainties remain source uncertainties, not a claim about the
accuracy or posterior uncertainty of model-corrected intensities.
