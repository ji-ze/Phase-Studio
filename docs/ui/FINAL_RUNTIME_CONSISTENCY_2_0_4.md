# Phase Studio 2.0.4 runtime and distribution acceptance

## Changes

Execution removes the idle placeholder on the first actual visible event and records a real transition to Running once. Completed-cycle events advance overall progress; displaying an individual live structure does not complete a workflow cycle.

Early Pass to Jana2020 requires a usable completed candidate from the active run. The click additionally verifies the sealed map/model identity and Jana readiness before the existing explicit stop confirmation. The final selector and publication checks remain authoritative; handoff does not rerun EDMA. Structure prediction is the default valid family, with independent family selection/view state. Metrics-only unavailable results remain inspectable. Available cycles counts actual available source candidates, not historical overall workflow progress.

Map Feedback explains damping zero, completion zero percent and powder mix zero without changing their values. Powder map-supported intensity correction remains available without a sigma filter. No overlap grouping, correction, repartitioning, ranking, default numerical settings or scientific coordinate calculations were changed in this pass.

Overlap presentation distinguishes all groups, multi-record groups, isolated records, affected records and intensity fraction. Structure marker areas are larger and shared between viewers; projection/fit remains display-only. Wizard configuration and feedback heights include content, branding, context and the fixed footer; authentication uses its existing content fit. Main workflow cards and branding fonts are preserved.

## Validation and scientific scope

The working-source complete suite passed 303 tests with 1 skipped and 37 subtests; no failures. The skipped opt-in real workflow test is not claimed as live inference acceptance. Separate scientific/Jana/UI scripts passed 798 checks, including 75 Wizard geometry checks. Golden expectations were not regenerated to accommodate changes.

Actual ochlor input still has 631 records: 91 overlapping groups, 438 isolated records, 529 total groups, 193 affected records (30.586%), largest group four records and intensity fraction 21.064%. Controlled grouping and actual ochlor memberships were compared again with installed Superflip; the validated grouping engine is unchanged.

Three isolated file-level handoffs passed using real existing matching-context ochlor Cycle 3 maps: SharpED at 0.50 sigma, SharpED at 0.40 sigma and Superflip at 0.50 sigma. Local EDMA and Superflip format conversion were used; no new inference was submitted. Checks cover threshold identity, map/model hashes, original context, lineage/site counts, coordinates and occupancy, bounded Uiso, density alignment and original-project immutability. The origin shift is zero; conversion error is within the established tolerance. Raw EDMA and composition-constrained Jana models can have different counts, which the UI states separately.

A second historical run, `run_0006`, was correctly rejected against today's Jana context: map cell (8.2533, 18.8476, 6.7048, 90, 92.58, 90) differs from the context (8.2512, 18.8436, 6.7032, 90, 92.58, 90). Neither source data nor the guard was modified to make this mismatched pairing pass.

The ten reviewed Qt captures and their precise real-data/fixture provenance are indexed in [the screenshot package](../screenshots/2.0.4/wizard/README.md). Seven were refreshed. Execution and selection show an explicitly identified offline replay of an actual completed historical Cycle 3, not a new authenticated calculation. DPI/restricted geometry checks use controlled screen conditions; physical-monitor acceptance remains pending.

Real Jana2020 GUI acceptance and live authenticated SharpED inference were not performed by this pass. File-level scientific checks and native executable startup do not replace those manual checks. No public release, tag, main merge or installer is requested or created.

## Clean build and publication

Source commit: `df890051610989e9f45837c765477d47c6e9e816`.

Both distributions are to be built from the detached clean worktree at that exact revision, using the existing Windows build process. Artifact measurements, clean-suite results and smoke acceptance are recorded below after completion. The source worktree's ignored build outputs do not change its tracked source status.


The clean-revision suite also passed **303 tests, 1 skipped, 37 subtests**, zero failures, in 323.20 seconds. Builds used Python 3.12.13, PyInstaller 6.20.0 and the existing `packaging/build_windows.ps1 -Target All` process. The first ONEDIR attempt hit Windows MAX_PATH at a 260-character legal-file path. Relocating the identical clean worktree to `build/r204` resolved this without changing source or excluding legal material.

| Artifact | Absolute delivery path | Bytes | SHA-256 |
|---|---|---:|---|
| Standalone ONEFILE | `C:\Users\honzi\Documents\GitHub\Phase-Studio\dist\2.0.4-clean\release\PhaseStudio-2.0.4-x64.exe` | 78085479 | `87b9332d5fff3ae66e5dd8b513eacfd30be149303639e6f7638c6da48c1ce180` |
| Jana developer EXE (requires its ONEDIR) | `C:\Users\honzi\Documents\GitHub\Phase-Studio\dist\2.0.4-clean\PhaseStudio-Jana2020-2.0.4\Phase_studio.exe` | 10093508 | `5dc1dd361f7e79bb95dde2ee85812c5380d7ae3227cd99b2a8cfad9e77dfc567` |
| Jana developer ZIP | `C:\Users\honzi\Documents\GitHub\Phase-Studio\dist\2.0.4-clean\release\PhaseStudio-Jana2020-2.0.4.zip` | 78474941 | `ee6c288fd0e58fc2de35bf0e524d2dbe036616bd642c8557a35da05506f63a30` |

Both PE versions are 2.0.4.0. Both frozen profiles passed version invocation, Science Gothic asset/license/family/Regular weight 400/zero tracking checks and a mocked local OAuth callback/exchange with responsive Qt. No remote OAuth or inference was used. Their module analyses contain only Phase Studio Python paths inside the clean worktree. All recorded runtime/packaging source hashes match the selected commit after building. Delivery copies match the original clean-build hashes; the ZIP contains 900 byte-identical ONEDIR files. Test/capture modules are absent from the executable Python archives.

The developer dependency audit reports 14 bundled dependencies, zero external and zero unresolved dependencies; the Windows built-in ICU requirement is OS-gated (Windows 10 1903+). Symbol verification covered 100 PE files with zero blocking problems and zero conflicting duplicate DLL names. Profile/distribution boundaries and ZIP extraction checks passed.

The standalone startup probe initialized its main window and exited zero. The developer executable opened the native `Phase Studio 2.0.4 for Jana2020` window from the Jana installation working directory and closed normally with exit zero. This is application startup, not scientific GUI acceptance within Jana.

A packaged cross-process Windows Credential Manager check wrote a synthetic key from standalone, read it from the developer EXE and removed it from standalone, using only `FZU/PhaseStudio/SelfTest/CredentialPersistence`. All three succeeded. The restricted sandbox initially rejected writes with Windows error 1312 (no logon session); repeating in the real user logon context passed. Production credential targets were not touched. OAuth access remains session-only by the established server contract; persistent manual keys use WinCred.

### Real handoff results

| Existing source map | Threshold | EDMA CIF sites | Jana model sites | Exported Jana Uiso range (A^2) |
|---|---:|---:|---:|---|
| `cycle_003_deblurred.xplor` | 0.50 | 21 | 12 | [0.01, 0.081025] |
| `cycle_003_deblurred.xplor` | 0.40 | 22 | 12 | [0.01, 0.081025] |
| `cycle_003_superflip.xplor` | 0.50 | 67 | 12 | [0.068807, 0.15] |

These are isolated file-level publications into copied matching-context projects. Original ochlor files are unchanged. They do not establish all-workflow real-machine acceptance or validation of the mismatched historical run_0006.

### Git and retained local work

Branch/destination: `development/2.0.4` on `https://github.com/ji-ze/Phase-Studio.git`.

- `f9b6fe9c9bbfe4ee031c2ae51edc81e80fb25f19` ? `feat: record validated Jana sign-in and secure credential lifecycle (2.0.4)`.
- `df890051610989e9f45837c765477d47c6e9e816` ? `fix: align execution lifecycle, result readiness and feedback UI (2.0.4)`; exact runtime/build source.
- A subsequent documentation-only acceptance commit records this report and supplies the public sign-in guide. It does not change the built runtime.

No tracked runtime edits remain outside these commits. Historical untracked auth audit/probe files, earlier screenshot sets, workshop materials and unused local capture/audit helpers remain preserved in the original workspace; they are excluded from the build, commits and push. Ignored build logs, copied real-data validation workspaces and distribution outputs likewise stay local. No artifacts are uploaded and no GitHub release/tag is created.

Reproduction/evidence paths (local, intentionally not committed): `build/release-consistency/clean-suite.log`, `build-clean-short.log`, `source-manifest.json`, `package-manifest.json`, `clean-verification.json`, `frozen-smoke.json`, `powder-parity.log`, individual scientific/UI script logs, and `build/selection-integrity-real/acceptance.json`.
