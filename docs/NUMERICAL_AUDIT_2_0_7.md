# Focused numerical and methodological audit — 2.0.7

Audited application commit: **`836cd2696dd29bcfba90bf3706135242610d59be`**,
verified against remote `development/2.0.7` and draft PR #21 on 2026-11-12.
**Verdict: GO WITH WARNINGS for the bounded numerical scope below.** This is
neither chemical structure validation nor permission to release 2.0.7; existing
production and interactive acceptance gates remain NO-GO.

## Scope and results

Reviewed the existing scientific corrections, actual workflow call sites,
native overlap provenance, frozen validation context, map I/O and Jana density
guards before executing **14 independent cases**. All 14 passed. Added **zero
permanent regression tests** and changed **no application/scientific code**.
Saved native outputs were reused; no native reconstruction, paid inference,
large sweep or Windows rebuild was run. This report is the only tracked change.

| Scientific area | Independent reference | Maximum discrepancy | Verdict |
|---|---|---|---|
| Fourier phases | Analytical impulse, direct atomic/Fourier sums, saved native +90° map | 2.95e-15 complex coefficient; 8.24e-18 density; 2.66e-6° native phase | PASS |
| I/F and uncertainties | Analytical propagation; 70-digit Decimal inverse-variance average | 0 at reported binary precision | PASS within stated approximation |
| Powder overlap | Independently parsed saved Superflip table; existing 60-digit Bragg oracle | 0 native membership differences; Bragg gap error 4.62e-15° | PASS; native/geometry distinction retained |
| Map Feedback | Direct density sums, median scaling, analytical damping and conservation | 3.56e-15 group-member intensity; 0 group-total error; 4.45e-16 correction error | PASS |
| R_work/R_free | Analytic work-only scale and residual; complete symmetry/Friedel orbits | 6.67e-16 residual; 0 orbit leaks in selected case | PASS numerically; independence limitations below |
| Coordinate transformations | Gemmi CCP4 reader, monoclinic reciprocal metric, direct volume-normalized Jana Fourier sum | 4.97e-7 density; 0 Å d-spacing error; 7.52e-6 relative Jana coefficient error | PASS within serialization bounds |

Each case records actual values, tolerance and PASS/FAIL in ignored local
`build/numerical-audit207/results.json`; its reproducible probe uses only existing
dependencies and is saved as `build/numerical-audit207/audit.py`. Detailed data
and local paths are not committed.

| Case | Mathematical expectation and independent comparison | Acceptance |
|---|---|---|
| A1 | Off-origin impulse on unequal axes: F(h)=2.5 exp(+2πi h·r); opposite HKL conjugates, F(000)=2.5 | Complex absolute error ≤1e-12 |
| A2 | P31 atomic screw orbit: construct equivalent coefficients from direct real-space atomic sums; compare every synthesized voxel with ΣF exp(−2πi h·r)/N | Absolute density error ≤1e-14 |
| A3 | Previously generated native Superflip map with +90° input phases; read it using current extraction | Wrapped phase error ≤1e-4°, allowing native text rounding |
| B1 | F=3, σ(F)=0.2 gives I=9, σ(I)≈1.2 and I/σ(I)=7.5; zero intensity retained, negative input excluded, zero-F sigma export rejected | Seven-decimal export error ≤5e-8; exact policy outcomes |
| B2 | Duplicate values 10±s and 20±2s, s=1e-200: mean 12, sigma s/√1.25, independently evaluated with Decimal | Relative error ≤1e-15; finite output |
| B3 | A native dummy column supplies no measured sigma; FWHM supplies a width, not uncertainty | Both positive significance requests rejected; dummy extraction preserves value and removes sigma meaning |
| C1 | Independently parse all 4,690 saved native rows; compare actual execution membership; compare boundary geometry with archived high-precision oracle | Exact native membership; geometric gap error ≤1e-12° |
| C2 | Native group 329, mix 0.25: I′j=0.75 Ij+0.25 ΣI·Pj/ΣP, with P from direct sums over the saved density | Member error ≤1e-9·max(1,ΣI); total 147.5565 conserved exactly; widths unchanged |
| C3 | Three orthogonal cosine components; independently calculate median intensity scale and 0.5 damping, applying the strict weak gate | Absolute error ≤1e-12; strong measurement and all sigmas unchanged |
| D1 | Select complete P21/Friedel orbits, then attempt missing completion with a deliberately symmetry-inconsistent impulse map | No withheld orbit or systematic absence added; new predictions have no measurement sigma |
| D2 | Work Fobs=2Fcalc, free Fobs=Fcalc: work-fitted k=2, R_work=0, R_free=1; independently synthesize the density | Both legacy helper and map-quality residual error ≤1e-12 |
| D3 | Off-origin analytical atom: internal negative-exponent reference phases and map phases agree, cosine score 1 | Absolute score error ≤1e-12; no external sign change implied |
| E1 | Compare every saved CCP4 voxel with independently decoded XPLOR layout; reject unsupported axes; check monoclinic d-spacing analytically | Per-voxel native E12.5 rounding plus float32 bound; largest error/bound 0.99714; d error ≤1e-12 Å |
| E2 | Read saved Jana m81 and evaluate 12 m80 coefficients by direct positive-exponent sums with cell-volume/N normalization | Coefficient relative error ≤5e-4; binary relative L2=1.55e-5, also below existing 5e-4 guard |

Synthetic double-precision tolerances distinguish sign, symmetry and scale errors
from floating arithmetic. E1 uses the actual format's last-place rounding, not
an arbitrary percentage. E2 also checks the existing production guard; its
5e-4 threshold is a compatibility tolerance, not a claimed experimental accuracy.
Previously validated complete Jana candidate/map/model hash and frame checks
at this exact commit were reviewed rather than rerun. No new interactive Jana
import or refinement acceptance is implied.

## Findings and methodological limits

**No new P0/P1 numerical defect was established in these cases.** Earlier fixes
for conjugated external phases, free-set scale fitting, unsafe duplicate
weights, fabricated dummy uncertainty, forbidden/held-out completion and
positional native output formats remain intact. No goldens were regenerated.

1. **P2 — native versus mathematical powder boundary.** The saved native table
   has 3,796 overlapping members in 794 groups; double-precision geometry has
   3,795 members. For (−22,2,5) and (16,2,8), the mathematical gap exceeds
   0.00288° by 7.871850887e-7°. The current execution path correctly uses the
   verified native table, including group 329, rather than forcing the estimate
   to match. This previously documented discrepancy is not a new defect.
   Installed-compiler arithmetic remains UNVERIFIED; no emulation was attempted.

2. **P2 — independence is conditional, not established by an R_free label.**
   `select_orbit_safe_holdout` protects crystallographic symmetry/Friedel orbits;
   it does not group different reflections sharing a powder peak. Their
   extracted intensities can be correlated. Nor can the code prove that a user
   initial model or pretrained predictor has never seen relevant information.
   The frozen context preserves original observations through feedback, and
   work-only scaling is correct, but independent powder validation remains
   **UNVERIFIED** without extraction covariance/group-aware experimental design.
   No particular saved run is asserted to be contaminated.

3. **P2 — selection versus final validation.** `recommend_best_result` uses
   R_free for candidate selection in holdout profiles. The selected minimum is
   therefore a validation-set selection score, not an untouched final test
   estimate. Feedback agreement with modified working intensities is likewise
   not independent evidence: predicted observations receive no measured sigma,
   and the frozen original-data context is essential. Repeated selection and
   tuning still require a separate untouched assessment for final accuracy.

4. **P2 — approximation limits.** F/[2σ(F)] is first-order error propagation,
   not an exact low-signal significance model. Rejecting negative intensities
   is the declared nonnegative reconstruction input policy, not a general
   unbiased intensity estimator or a French–Wilson treatment. Reference phases
   use atomic-number weights without occupancy or resolution-dependent atomic
   form factors/ADPs; the score is a simplified structural proxy, not a full
   scattering-model residual. Its paired negative-exponent convention is
   internally consistent, despite the misleading “crystallographic” comment in
   `reference_phases_from_atoms`; external interchange correctly uses the
   positive exponent. Do not interpret that comment as an algorithmic sign bug.

5. **P2 — non-discriminating diagnostic.** The reported negative-density mass
   uses mean-centered values. Algebraically Σρ=0 implies Σmax(−ρ,0)/Σ|ρ|=1/2
   for every nonconstant centered map. It cannot rank map quality or quantify
   negative mass relative to a physical zero. It is report-only and is absent
   from every recommendation criterion. Retained the established background-
   invariant definition; replacing it with raw-density negativity would require
   an explicit physical-baseline policy, not a numerical precision patch.

These limitations qualify scientific interpretation. They do not justify
silently changing symmetry, uncertainty distributions, selection algorithms or
the meaning of already recorded outputs during this bounded audit. No historical
maps, models or numerical scores were rewritten. Use the limitations above when
interpreting existing scores; unconditional claims of statistical independence
are not supported by this audit.

Primary convention references: [Gemmi scattering](https://gemmi.readthedocs.io/en/stable/scattering.html)
and [REFMAC work/free scaling and prior-model requirements](https://www.ccp4.ac.uk/html/refmac5/keywords/xray-principal.html).
Existing project evidence: [scientific corrections](SCIENTIFIC_VALIDATION_2_0_7.md),
[native boundary/provenance](RELEASE_READINESS_2_0_7.md) and
[Jana handoff corrections](REGRESSION_REPAIR_2_0_7_20261111.md).

## Final verification and disposition

- New numerical verification: **14/14 PASS**, zero new permanent tests.
- Existing full regression on the exact unchanged application commit:
  **993 passed, 4 skipped, 37 subtests passed**, exit 0, 1920.35 seconds.
  All nine recorded authority entry points returned 0. These are reviewed prior
  results, **not new executions in this audit**. Full regression and authorities
  were not repeated because no source correction was necessary.
- Every reused native/input/oracle file was SHA-256 checked before/after and
  remained unchanged. Application files match the audited commit. Existing local
  test-file flags, workshop files and screenshot evidence were preserved.
- No Windows binaries were rebuilt; existing testing packages remain at
  `836cd26`. No dependencies, production keys, released 2.0.6 files or paid jobs
  were changed. PR #21 remains draft; no merge, tag, signing or publication.

**Final scientific verdict: GO WITH WARNINGS for the tested numerical paths;
independent experimental/chemical validation remains UNVERIFIED.** No claim of
exhaustive absence of P0/P1 defects or production release readiness is made.
