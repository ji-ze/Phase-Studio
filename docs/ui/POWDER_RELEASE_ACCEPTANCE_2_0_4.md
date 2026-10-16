# Phase Studio 2.0.4 — powder, Wizard and packaging acceptance

## Scientific result

See [verified convention and executable comparisons](POWDER_OVERLAP_2_0_4.md). Standard FWHM is degrees 2θ, resolved wavelength is required, default separation is 0.2, and adjacent peaks join transitively at the inclusive threshold. No experimental wavelength is invented. Missing wavelength produces an explicit input prompt and no dependent overlap numbers or graphs. Unknown external widths retain strict provenance requirements.

For real ochlor: **631 records, 91 multi-record groups, 193 affected (30.5863708399%), 438 singleton groups, 529 total groups, largest group four**. The fraction of supplied nonnegative physical intensity in overlapping groups is **21.06356131111815%**. Complete group membership matches the installed Superflip, not just the group totals. It remains labeled estimated geometric overlap rather than experimentally proven independent peaks.

Read-only real-data invariants:

| Dataset | d_min (Å) | d98 (Å) | Input SHA-256 |
|---|---:|---:|---|
| ochlor | 1.1990790613015834 | 1.1990790613015834 | `9136270c5e8ab6850ac6bd4390c301f17a32dcc83994184d8562735b9a26b88c` |
| 2int3total | 0.7255092594101177 | 0.8161153076022714 | `07a3de15e54ba130f75e960358aef1ff6087b09f0ea5d9604f00090cb9d21642` |

The input hashes and these resolution values match the preceding accepted baseline. Diagnostic width units/overlap capabilities intentionally change; phasing, intensity repartitioning, SharpED/EDMA, ranking, density normalization and scientific writers are unchanged by this pass. Scientific golden checks passed without updating their expected outputs.

## Tests and images

- Baseline focused HKL suite: **24 passed**.
- Final complete working-tree suite: **300 passed, 1 skipped, 37 subtests passed** in 254.74 s.
- Final focused HKL/powder/presentation tests: **34 passed**, including missing-wavelength interaction at 100%, 125% and 150%.
- Isolated export of the focused staged source: **56 passed** across HKL, powder, Wizard and distribution tests. This verifies the selected commit independently of unrelated working-tree changes.
- Existing standalone check scripts: **709 passed** — scientific core 46; final UI 30; Jana completion 192; workflow state 141; density alignment 41; displacement 44; Wizard hierarchy 21; redesign 44; tile icons 58; geometry 74; text clipping 18.
- No unresolved failures. The one skip is the existing opt-in real-project Map Feedback case without its environment variable; separate real HKL audits covered ochlor and 2int3total.
- **Exactly ten** current Qt screenshots, individually inspected: [stage/data index](../screenshots/2.0.4/wizard/README.md). The capture count excludes earlier historical screenshot directories, which were not newly recaptured or included in this commit. Offline catalogue, execution and selector fixtures are explicitly distinguished from real scientific execution.

Logs/evidence remain under ignored `build/powder-final/`: `baseline.log`, `release-suite.log`, `final-focused.log`, `staged-review.log`, `test_*.log`, `parity/report.json`, `real-invariants.json`, `build.log`, `package-manifest.json`, `frozen-smoke.json` and the two `*-fonts.json` files. No external documentation, browser login, SharpED requests or inference were used; external network access was limited to the authorized Git remote operations.

## Windows packages

Built using the existing `packaging/build_windows.ps1 -Target All -DistRoot dist/2.0.4-final` and PyInstaller specifications. The obsolete Jana installer was not built. Version resources in both executables are **2.0.4.0**.

| Artifact | Absolute path | Bytes | SHA-256 |
|---|---|---:|---|
| Standalone ONEFILE | `dist\2.0.4-final\release\PhaseStudio-2.0.4-x64.exe` | 78082913 | `70ba02bee46815cff2da625959c5740db0347166cb662a8f46bc82ad92864a7d` |
| Jana developer EXE | `dist\2.0.4-final\PhaseStudio-Jana2020-2.0.4\Phase_studio.exe` | 10090989 | `f92b938f5b184bdb3092e56d7587e8ead610b78683a3bdf092c6f448cc5104dd` |
| Developer ZIP | `dist\2.0.4-final\release\PhaseStudio-Jana2020-2.0.4.zip` | 78473472 | `149d0e3a43d6d90467f06475db1733db78f57754407711cd1643d1e082e9a5d7` |

The existing distribution naming is preserved: the developer folder `PhaseStudio-Jana2020-2.0.4/` directly contains `Phase_studio.exe` and `_internal/`. Its ZIP was extracted and all **900 files** verified against the source tree. No duplicated scientific Superflip/EDMA executables are bundled.

Acceptance:

- Both distribution-boundary checks passed.
- ONEDIR DLL audit: **14 bundled, 0 external, 0 unresolved**, one OS-version-gated import; symbol audit: **0 blocking issues, 0 conflicting duplicate DLL names** across 100 PE files.
- Both frozen PYZ archives contain the HKL, presentation and powder diagnostic modules. Test/capture utilities are absent as runtime modules.
- Both frozen font checks exited zero: bundled font and license exist, resolved Science Gothic weight **400**, letter spacing **0.0**. Scientific controls keep the regular application UI font.
- Standalone main-window initialization passed its existing offscreen startup probe, exit zero.
- Developer ONEDIR started from `C:/Jana2020`, created the native **Phase Studio 2.0.4 for Jana2020** main window, then closed normally with exit zero. The automated check hid the window; network proxies prevented external catalogue access. This is a startup smoke test, not manual scientific Jana acceptance.
- Existing resolver tests passed; the runtime lookup remains the established Jana `SUPERFLIP` path. No `SharpED/SUPERFLIP` lookup was added.

The EXEs were built from the **complete current dirty 2.0.4 working tree**, as requested. The focused commit deliberately excludes pre-existing unrelated authentication, credential-persistence, Result Selection and associated changes. Therefore the binaries are not represented as a byte-reproducible build solely of this focused commit. Those preserved changes still require their own source review/commit. The isolated-index checks above validate the focused source separately. Local generated package notes retain the pre-existing 2.0.4 OAuth section; committed release notes describe the focused HKL/Wizard work.

## Repository and limits

Active branch: **development/2.0.4**, based on `ca8503c`. The remote initially had no branch with this name; it is the destination for the authorized ordinary push. No main-branch update, force-push, history rewrite, tag, GitHub Release or binary upload is part of this task. The focused commit message is **fix: finalize Jana powder overlap diagnostics and HKL UI (2.0.4)**. Its exact hash/push result is reported after the Git command completes.

Existing unrelated edits are preserved outside the commit, including README/authentication/OAuth/credential work, selector/execution changes and their tests, earlier documentation/screenshots and local acceptance utilities. Builds, caches, project files, local executable/source evidence and private JSON sidecars are excluded. LICENSE and copyright ownership are untouched.

Remaining limits: manual physical-monitor checks, actual Jana2020 return/handoff and a complete real scientific workflow are not established by these screenshots or startup tests. No new paid inference was run. Exact executable grouping equality was observed for the documented cases, with the documented floating-point caveat. Unsupported/reordered extra powder columns are rejected rather than guessed; see the scientific report for the supported diagnostic mappings.
