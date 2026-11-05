# Scientific validation of 2.0.7 — investigation in progress

This campaign is not complete. Release verdict: **NO-GO** pending the final
native, workflow, full-regression and frozen-profile gates. PR #21 must remain
draft. No live paid inference is authorized and no new live inference has been
performed. Previously saved SharpED responses are replay evidence only.

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
