# Independent numerical and methodological audit — Phase Studio 2.0.7

Campaign begun 2026-11-12; continued 2026-11-13 (Europe/Prague).
Baseline source: `6e59aecbe5df4811783f0c999ca1d211347b2570`, verified against
remote `development/2.0.7`. It adds documentation to application source
`836cd2696dd29bcfba90bf3706135242610d59be`.

**Current status: NO-GO pending final corrected-source verification.**
See [findings](SCIENTIFIC_FINDINGS_2_0_7.md) and
[corrections and impact](SCIENTIFIC_CORRECTIONS_2_0_7.md). This broader audit
supersedes the limited scope of `NUMERICAL_AUDIT_2_0_7.md`.

## Immutable baseline

A separate clean checkout reproduced **993 passed, 4 skipped, 37 successful
subtests in 1960.87 seconds**, process exit 0. All nine authority entry points
returned 0. The skips were one opt-in real-project test, two ONEFILE runtime
cases and one ONEDIR-only case. Existing regression authorities include captured
historical goldens; they are not all independent mathematical oracles.

Environment: Windows 11, Python 3.12.13, NumPy 2.5.3, Gemmi 0.7.5, PySide6
6.11.1, pytest 9.1.1. No new dependency was installed; Decimal supplies arbitrary
precision where needed. All 103 baseline application files have a function and
SHA-256 inventory. The original baseline checkout and earlier evidence remain.

The initial independent regression batch produced **26 failures, 3 passes**;
additional isolated cases reproduced Nyquist, overall-B and bootstrap defects.
These are preserved counterexamples, not failures concealed by the green
historical suite. Corrections are verified separately and then through a fresh
complete final suite.

## Scientific scope and independent references

Reviewed execution paths: reflection parsing/filtering/writers and Fourier
recycling in `app.py`; `map_quality.py`; `edma_threshold.py`; `native_overlap.py`;
`xplor_io.py`/`jana_density.py`; HKL diagnostics, completeness and shell analysis;
feedback order/checkpoints and candidate handoff identity. The separate nine
authorities cover native workflow, EDMA, displacement parameters, result
selection and execution logging. No paid inference is part of this campaign.

| Area | Independent reference | Maximum error after focused correction | Tolerance | Verdict |
|---|---|---|---|---|
| Fourier phases | Thirty direct positive-exponent coefficients on an asymmetric grid | 9.44e-15 complex coefficient | 2e-13 absolute | PASS, final snapshot pending |
| Symmetry | Full Gemmi operations; direct atomic sums in six groups | 0 missing positions; 1.58e-17 synthesized density | Exact cardinality; 1e-13 density | PASS, final snapshot pending |
| Reflection conversion | Analytical I=F² / sigma propagation and decimal reconstruction | No loss of tested 1e-9 / 2e-10 inputs | Relative 1e-14 | PASS, final snapshot pending |
| Powder overlap | Independently decoded actual native table and high-precision boundary oracle | All baseline membership exact; all 885 groups conserved at five mixes in I/F | Per-output rounding plus floating summation bound | Baseline PASS; final pending |
| Map Feedback | Direct sums, work/holdout orbit rules and stage-specific conservation | Final matrix pending | Predeclared case-specific bound | UNVERIFIED final |
| R_work / R_free | Exact Fo=2Fc and independent work/free split | 0 in tested seven common scales | 2e-14 | PASS, final snapshot pending |
| Periodic geometry | Exhaustive images with an outer-shell singular-value bound, seed 2071112 | 8.89e-16 Å over 96 pairs | 2e-12 Å | PASS, final snapshot pending |
| EDMA/native export | Independent native parsing and frozen counterexamples | Final checks pending | Format-specific rounding | UNVERIFIED final |
| Map formats | Independent CCP4/Jana decoding; frame rejection | Final checks pending | Serialization-derived bounds | UNVERIFIED final |
| Completeness | Independently enumerated reciprocal-metric/orbit domain in three groups | 0 count differences | Exact integer counts | PASS, final snapshot pending |

Analytical truth, independent computation, installed native behavior and
experimental validity are recorded separately. In particular, the native
Selexipag boundary differs from the high-precision mathematical criterion; no
tolerance is changed to force equality. Successful native execution and saved
SharpED replay do not prove chemical correctness.

Local private evidence: `build/adversarial-audit207/`, including exact SHA and
environment, full baseline logs/JUnit, all nine authority logs, before-state
inputs, fixed-seed arrays, independent oracle scripts, powder memberships,
serialized files, native outputs and original-file hashes. No private data or
user-specific paths are included in these public reports.

## Final acceptance

Pending final exact-source regression, all nine authorities, native comparisons,
both unsigned development builds and available frozen scientific acceptance.
PR #21 remains draft. No merge, tag, production signing, key change, SignPath
bypass or release publication is authorized or performed.

Primary references: [Gemmi symmetry operations](https://gemmi.readthedocs.io/en/stable/symmetry.html),
[Gemmi unit-cell implementation](https://github.com/project-gemmi/gemmi/blob/v0.7.5/include/gemmi/unitcell.hpp),
[Gemmi scattering conventions](https://gemmi.readthedocs.io/en/stable/scattering.html),
and [REFMAC work/free scaling](https://www.ccp4.ac.uk/html/refmac5/keywords/xray-principal.html).
