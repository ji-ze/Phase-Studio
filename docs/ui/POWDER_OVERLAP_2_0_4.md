# Jana/Superflip powder diagnostics — 2.0.4

## Locally verified convention

No internet research or SharpED API requests were used. Evidence came from `Downloads/superflip_user_manual.pdf`, the local `superflip.tar.gz` source archive, the installed `C:/Jana2020/SUPERFLIP/superflip.exe`, the active ochlor input and its matching `.m90`.

- Manual `dataformat` specifies FWHM in 2θ. Source `sf_input.f90`, subroutine `FWHM2Groups`, converts `2*asin(lambda/(2*d))/torad`, establishing **degrees 2θ**, not radians or reciprocal-space width. Width values are read directly into temporary `AMEM`; no extra width conversion is applied in that routine.
- `sf_modules.f90` initializes `FWHMlim=0.2`; `fwhmseparation` overrides it. The manual also states 0.2.
- Adjacent peaks sorted by increasing 2θ are separated only when `delta(2θ) > factor*(FWHM1+FWHM2)/2`. Equality therefore joins. Connected neighboring peaks form transitive groups. Identical positions join. Grouping uses input records before reflection expansion; symmetry-equivalent records are not automatically interchangeable with independent powder observations.
- The manual requires `lambda` for FWHM input. Source has an internal 0.710 value, but this is **never adopted as experimental wavelength**. Diagnostic priority is incoming `.inflip` lambda/wavelength, then its matching Jana `.m90`; there is no wavelength guess from FWHM magnitude or from historical run logs.
- `dataformat ... group` supplies group IDs; zero means separated. Original supplied IDs are retained in diagnostic metadata. Explicit assignments take precedence and do not require geometric recomputation or a wavelength. Superflip rejects simultaneous `group` and `fwhm`.

`phase_studio/powder_diagnostics.py` contains the diagnostic-only metadata and grouping authority. Existing Map Feedback `assign_powder_overlap_groups` and intensity repartitioning code are unchanged. Their older strict-boundary behavior is not silently changed by this diagnostic correction.

Plain external five-column HKL remains strict: selecting a column layout does not establish angular units or experimental wavelength. Standard units are inferred only from a declared embedded Superflip FWHM block, with provenance retained. Invalid explicit parameters are reported instead of replaced by defaults. Cache identity includes the matching `.m90`, so a metadata change invalidates prior diagnostic results.

The automatic diagnostic adapter supports declared `intensity fwhm`, `amplitude fwhm`, `intensity group` and `amplitude group`. Additional/reordered powder columns are rejected with an explicit mapping error rather than read as the wrong value or width. This is a remaining format limitation; it does not alter Superflip's broader input support or the phasing reader.

## Missing wavelength

Without a measured/resolved wavelength, no wavelength-dependent overlap statistics or plots are created. The dialog provides a **Wavelength (Å)** field initialized to **Required**, with no nonzero suggested value. **Analyze peak overlap** is disabled until the user supplies a positive value. The resulting diagnostic review identifies it as a user-entered diagnostic wavelength. Input files, stored configuration and scientific workflow settings are not rewritten.

d_min, d98, reciprocal-coordinate shell coverage and FWHM summaries remain available because they depend on the unit cell/indices or supplied widths, not radiation wavelength. Inaccessible Bragg positions, invalid widths or duplicate literal indices produce specific explanations rather than invented groups.

## Executable comparisons

The audit runs `perform fourier` on isolated controlled copies with supplied zero phases; it performs no phase search or SharpED inference. Expanded Superflip logs expose the full input-group table. Comparisons use membership sets, not arbitrary numeric group labels.

Installed executable: version **09/21/20 10:33**, SHA-256 `2933a0c5245f4addc6365f26e5e4ca73a113e875a5901587db2bdd201a80bf3e`.

| Case | Records | Multi-record groups | Affected records | Complete membership equality |
|---|---:|---:|---:|---|
| Separated | 3 | 0 | 0 | Yes |
| Identical positions | 6 | 1 | 2 | Yes |
| Transitive chain | 6 | 1 | 6 | Yes |
| Variable widths / factor 0.5 | 6 | 2 | 5 | Yes |
| Wavelength 1.7 Å | 6 | 1 | 2 | Yes |
| Omitted factor (default 0.2) | 6 | 1 | 2 | Yes |
| Explicit supplied IDs | 3 | 1 | 2 | Yes |
| Real ochlor | 631 | 91 | 193 | Yes |

The exact equality boundary is additionally covered by a controlled unit test. The installed executable uses finite-precision Fortran arithmetic; observed equality across these comparisons is not a proof of bitwise equivalence for every possible near-boundary floating-point input. The source-level inclusive criterion is preserved.

Real ochlor resolves **1.541866 Å** from `ochlor_Superflip.m90`, constant **0.0527 degrees 2θ**, factor **0.2**. It has **91 multi-record groups, 438 singleton groups, 529 total groups, 193/631 affected records (30.5863708399%)**, largest group four. These are **estimated geometric peak overlaps** matching the installed Superflip grouping for this input, not experimentally established independent observations. Intensity fraction is reported only when every contributing physical intensity is finite/nonnegative with positive total; it is a fraction of supplied intensities, not independent measured information.

Source ochlor SHA-256 remains `9136270c5e8ab6850ac6bd4390c301f17a32dcc83994184d8562735b9a26b88c`. Its d_min and d98 remain **1.1990790613015834 Å**. The preceding report's honest unavailable status was based on then-unverified standard units; this investigation supplies the missing local evidence and supersedes that status.

Local evidence, complete memberships and executable outputs: `build/powder-final/parity/report.json` and case subdirectories. Scientific project files and local Superflip sources/binaries are not committed. Reproduce with `packaging/tools/audit_powder_overlap_204.py` when the same local executable/project is available.

## UI and scope

Peak overlap displays affected fraction, group distribution, largest group and overlap versus resolution; structured details include total/singleton/multi-record groups, precise denominators, wavelength source, criterion and available intensity fraction. Constants retain compact summaries. Direct F/σ(F), the secondary derived I/σ(I), undefined d98 explanations, full-precision exports and stable nonmodal details are preserved. No I/FWHM significance was added.

See the [ten-window screenshot index](../screenshots/2.0.4/wizard/README.md). These are actual offscreen Qt windows; controlled execution/catalogue/selector fixtures are identified explicitly. No real browser login, remote inference or Jana publication was performed during this task. Manual acceptance in Jana and on a physical monitor remains outstanding.

Testing, packaging and Git results are recorded in `POWDER_RELEASE_ACCEPTANCE_2_0_4.md` beside this report.
