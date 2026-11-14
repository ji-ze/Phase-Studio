# Independent numerical and methodological audit — Phase Studio 2.0.7

Campaign begun 2026-11-12; continued 2026-11-13 (Europe/Prague).
Baseline source: `6e59aecbe5df4811783f0c999ca1d211347b2570`, verified against
remote `development/2.0.7`. It adds documentation to application source
`836cd2696dd29bcfba90bf3706135242610d59be`.

**Final status: PASS for the audited development scope. No release authorization.**
Final application/test source: `2d381b7a8503111c093a3f24e31d4ae5cd351ee8`.
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
precision where needed. All 94 baseline Python application modules have a function and
SHA-256 inventory. The original baseline checkout and earlier evidence remain.

The initial independent regression batch produced **26 failures, 3 passes**;
additional isolated cases reproduced Nyquist, overall-B and bootstrap defects.
Replaying the complete final counterexample set against the immutable baseline
produced **30 failures, 3 passes and 12 numerical warnings**; all 33 pass after
correction. The final full suite reports no warnings.
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

| Area | Independent reference | Maximum error on final source | Tolerance | Verdict |
|---|---|---|---|---|
| Fourier phases | Thirty direct positive-exponent coefficients on an asymmetric grid | 9.44e-15 complex coefficient | 2e-13 absolute | PASS |
| Symmetry | Full Gemmi operations; direct atomic sums in six groups | 0 missing positions; 1.58e-17 synthesized density | Exact cardinality; 1e-13 density | PASS |
| Reflection conversion | Analytical I=F² / sigma propagation and decimal reconstruction | No loss of tested 1e-9 / 2e-10 inputs | Relative 1e-14 | PASS |
| Powder overlap | Independently decoded native table and high-precision boundary oracle | 1.37e-12 in-memory group sum; 8.39e-6 after F serialization and squaring; exact native membership | In-memory 1e-12 relative / 1e-9 absolute; sum of per-record rounding bounds on disk | PASS, all 885 groups at five mixes in I/F |
| Map Feedback | Independent scaling/damping calculation; holdout-orbit enumeration; actual next native cycle | 4.45e-16 correction; zero orbit leakage in tested cases | 1e-12 correction; exact exclusion | PASS |
| R_work / R_free | Exact Fo=2Fc and independent work/free split | 0 across seven common scales; 8.89e-16 separate residual example | 2e-14 scale campaign; 1e-12 residual | PASS |
| Periodic geometry | Exhaustive images with an outer-shell singular-value bound, seed 2071112 | 8.89e-16 Å over 96 pairs | 2e-12 Å | PASS |
| EDMA/native export | Native execution; independent saved native phase; bundled counterexamples | 2.66e-6 degrees saved native phase; chemical accuracy N/A | 1e-4 degrees; operational checks separately | PASS operationally |
| Map formats | Independent CCP4/Jana decoding; direct Fourier sum; frame rejection | 4.97e-7 CCP4/XPLOR absolute; 7.52e-6 Jana coefficient relative | Per-voxel serialization bound (maximum 5.02e-7); 5e-4 coefficient relative | PASS |
| Completeness | Independently enumerated reciprocal-metric/orbit domain in three groups | 0 count differences | Exact integer counts | PASS |

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

The final exact-source full suite passed **1,026 tests, 4 skipped and 37 subtests
in 1998.55 seconds**, exit 0. Skips retain the baseline reasons above. All nine
authority entry points passed; the separate experimental EDMA suite passed all
49 checks. The seven seeded campaigns and all 14 independent interchange cases
passed on this same source.

Twenty fresh native powder runs passed (two datasets, I/F, five mixtures), with
unchanged original hashes and exact next-cycle native memberships. Fresh native
Superflip/EDMA pilots completed for anti-B18H22, Selexipag and Ochlor. These are
20-cycle operational pilots, not demonstrated convergence or solved structures.
All seven native reflection formats plus uncertainty-free intensity passed.
Eight saved SharpED jobs loaded in source and both frozen profiles with inference
and upload calls forbidden and original hashes unchanged.

Both unsigned Windows builds passed. Each executable contains **91 source-matched
application modules** and **66 byte-identical legal/font resources**. About checks
passed at 100%, 125%, 150% and 200%, including narrow/short layouts, Windows-backend
rendering and Unicode extraction. All compared About screenshots matched source
pixels. Source and both executables passed the new scientific counterexamples and
actual native Jana handoff checks. Actual screenshots were visually inspected;
offscreen and Windows-backend captures do not prove physical mixed-DPI acceptance.
Both profiles also passed the main-GUI matrix at four scales and the Windows
backend (870 fresh screenshots across those ten runs). Original-file verification
covered 38 distinct reused experimental/native/oracle files. Final source has
95 Python modules; checkout differences from the working tree are line endings
only. Neither development entry executable has an Authenticode signature.

The earlier `0ff780c` full run is retained: six failures, 1,020 passes, four skips,
37 subtests. Those six assertions encoded the disproved small-value rounding loss.
Its native check also exposed rejected exponent notation. The corrected decimal
implementation and justified expectation change preceded the complete passing
run above. An earlier authority timeout, file-permission failures and local
controller report-schema errors are preserved; they are not counted as passes.

Exact skew-cell distances cost more than component rounding. The final real-data
EDMA stages took approximately 170, 38 and 7.5 seconds respectively; older runs
took approximately 34, 7.5 and 1.9 seconds under different system load. These are
not controlled benchmarks. Orthogonal fast paths and scalar arithmetic reduce
overhead, but quadratic peak merging remains a performance limitation.

No confirmed N01–N11 P0/P1 defect remains open in the tested paths. This finite
campaign does not certify all datasets or statistical independence: powder
covariance, validation-set reuse, simplified reference metrics and unsupported
conditioning remain explicitly qualified in the findings report.
PR #21 remains draft. No merge, tag, production signing, key change, SignPath
bypass or release publication is authorized or performed.

Primary references: [Gemmi symmetry operations](https://gemmi.readthedocs.io/en/stable/symmetry.html),
[Gemmi unit-cell implementation](https://github.com/project-gemmi/gemmi/blob/v0.7.5/include/gemmi/unitcell.hpp),
[Gemmi scattering conventions](https://gemmi.readthedocs.io/en/stable/scattering.html),
and [REFMAC work/free scaling](https://www.ccp4.ac.uk/html/refmac5/keywords/xray-principal.html).
